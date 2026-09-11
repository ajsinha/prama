"""A REST API as a source.

The awkward part of a REST source is not the HTTP. It is that an API has none of
the properties a control quietly assumes a table has, and a connector that
papers over the difference produces evidence that cannot be defended.

**A page is not a population.** An endpoint returns a page, and a connector that
reads one and stops has silently truncated the dataset — a completeness control
over the first hundred rows of forty thousand passes, and means nothing. This
follows pagination to the end, and when a page cap stops it, that fact travels
with the read rather than being discarded.

**A read is not a snapshot.** Rows change between page one and page forty, so a
REST read is never a consistent point in time. :class:`Snapshot` says
``exact=False`` and the reason, because the evidence record carries that flag
and deterministic replay depends on it: a control that replayed against a
"snapshot" the API cannot reproduce would give a different verdict and blame the
data.

**The first record is not the schema.** JSON records differ — an optional field
is absent rather than null, and a numeric field arrives as a string on the one
record that came from a different upstream. The schema is inferred across a
sample and *disagreements are reported*, because a column typed from record one
is a type nobody checked.

**429 is an answer, not an error.** An API saying "slow down" is working
correctly. The connector honours ``Retry-After`` and reports how long it waited,
so a read that took eleven minutes is explained rather than mysterious.

Authentication is a resolved secret, never a literal: ``credential_field`` names
where it lands, and the connector puts it in a header rather than a query string
— a token in a URL is a token in every access log between here and the server.

Needs the ``rest`` extra.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from prama.connect.capability import CapabilityMatrix
from prama.connect.spi import (
    ColumnSchema,
    Connector,
    ConnectorError,
    DiscoveredObject,
    HealthReport,
    HealthState,
    ObjectSchema,
    SamplePlan,
    Snapshot,
    SnapshotKind,
    SourceKind,
    UnauthorisedError,
    UnreachableError,
)
from prama.core.clock import utc_now
from prama.core.registry import PluginManifest

if TYPE_CHECKING:  # pragma: no cover
    import pyarrow as pa

#: Rows per Arrow batch. Small relative to a file connector because an API page
#: is small, and batching across many pages would hold the whole response set.
BATCH_ROWS = 5_000

#: How many pages a single read will follow before stopping. A bound rather than
#: a preference: an endpoint whose "next" link cycles would otherwise read
#: forever, and a hung read is worse than a short one because nobody can see it.
DEFAULT_PAGE_LIMIT = 1_000

#: Nothing. A REST source has no query engine, so the compiler may rely on none
#: of it and controls evaluate locally over the Arrow this yields.
CAPABILITIES = CapabilityMatrix.of()


class RestConnector(Connector):
    """A JSON-over-HTTP endpoint, read page by page."""

    plugin_key = "rest"
    source_kind = SourceKind.API
    #: A bearer token, an API key — whatever the deployment resolved. It lands
    #: in a header; see the module docstring.
    credential_field = "token"

    @classmethod
    def manifest(cls) -> PluginManifest:
        return cls.describe_manifest(
            key="rest",
            display_name="REST API (JSON)",
            capabilities=CAPABILITIES.to_capabilities(),
            description=(
                "A JSON-over-HTTP endpoint. Follows pagination to the end and says "
                "when a page cap stopped it; reports its snapshot as inexact, "
                "because rows change between the first page and the last."
            ),
        )

    def __init__(self, config: dict[str, Any], **kwargs: Any) -> None:
        super().__init__(config, **kwargs)
        self._base = str(self.config.get("base_url", "")).rstrip("/")
        self._endpoints = tuple(self.config.get("endpoints") or ())
        self._records_path = str(self.config.get("records_path", ""))
        self._next_path = str(self.config.get("next_path", ""))
        self._page_param = str(self.config.get("page_param", ""))
        self._page_size = int(self.config.get("page_size", 100))
        self._page_limit = int(self.config.get("page_limit", DEFAULT_PAGE_LIMIT))
        # The literal key, not self.credential_field: the overlay audit scans
        # for config reads by name, and an indirect read is one it cannot see —
        # so a field described in the UI and never read would pass unnoticed.
        self._token = str(self.config.get("token", "") or "")
        self._header = str(self.config.get("auth_header", "Authorization"))
        self._scheme = str(self.config.get("auth_scheme", "Bearer"))
        self._timeout = float(self.config.get("timeout_seconds", 30.0))
        self._sample_records = int(self.config.get("schema_sample_records", 200))
        self._region = str(self.config.get("region", ""))
        #: The residency check, optional as everywhere else. Reading is mostly
        #: an ingress, but the credential leaves and the API's region is where
        #: this tenant's data is currently sitting.
        self._gate: Any = None
        self._client: Any = None
        #: Set by the last read. Carried rather than logged, because "we stopped
        #: at the cap" is a fact about the data, not about the run.
        self.last_read_truncated = False
        self.last_read_pages = 0
        self.last_read_waited_seconds = 0.0

    # -- lifecycle ---------------------------------------------------------

    async def open(self) -> None:
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - exercised by the extra
            raise ConnectorError(
                "the REST connector needs the 'rest' extra, which is not installed",
                code="CONNECT.REST_UNAVAILABLE",
                remedy='Install it: pip install -e ".[rest]".',
            ) from exc
        if self._gate is not None:
            self._gate.require(
                "source-read",
                destination=self._region,
                jurisdiction=self._region,
                subject=f"a read from {self._base}",
            )
        self._client = httpx.AsyncClient(timeout=self._timeout, headers=self._headers())

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self._token:
            # A header, never a query string: a token in a URL is a token in
            # every access log, proxy log and browser history between here and
            # the server.
            headers[self._header] = f"{self._scheme} {self._token}".strip()
        return headers

    def _http(self) -> Any:
        if self._client is None:
            raise ConnectorError(
                "the REST connector was used before it was opened",
                code="CONNECT.NOT_OPEN",
                remedy="Use the connector as an async context manager, or call open() first.",
            )
        return self._client

    # -- contract ----------------------------------------------------------

    async def health(self) -> HealthReport:
        checked = utc_now()
        if not self._base:
            return HealthReport(
                state=HealthState.MISCONFIGURED,
                detail="no base_url is configured, so there is nothing to reach",
                checked_at=checked,
            )
        # Outside the try: a connector used before open() is a bug in the
        # caller, and reporting it as UNREACHABLE sends somebody to the network
        # team for a mistake in the code.
        client = self._http()
        try:
            response = await client.get(self._url(self._endpoints[:1] or ("",)))
        except Exception as exc:
            return HealthReport(
                state=HealthState.UNREACHABLE,
                detail=f"{self._base} did not answer: {type(exc).__name__}",
                checked_at=checked,
            )
        if response.status_code in (401, 403):
            return HealthReport(
                state=HealthState.UNAUTHORISED,
                detail=(
                    f"{self._base} answered {response.status_code}. The credential "
                    "resolved; the server declined it."
                ),
                checked_at=checked,
            )
        if response.status_code >= 500:
            return HealthReport(
                state=HealthState.DEGRADED,
                detail=f"{self._base} answered {response.status_code}",
                checked_at=checked,
            )
        return HealthReport(state=HealthState.HEALTHY, detail="", checked_at=checked)

    async def discover(self, path: tuple[str, ...] = ()) -> list[DiscoveredObject]:
        """The configured endpoints.

        An API does not enumerate itself. There is no list-everything call, and
        guessing paths would produce datasets nobody declared — so discovery
        returns what the configuration names and nothing else.
        """
        if path:
            return []
        return [
            DiscoveredObject(
                path=(endpoint,),
                kind="endpoint",
                estimated_rows=None,
                comment="a JSON endpoint; its row count is unknown until it is read",
            )
            for endpoint in self._endpoints
        ]

    async def describe(self, path: tuple[str, ...]) -> ObjectSchema:
        records, _, _ = await self._collect(path, limit=self._sample_records)
        columns, disagreements = _infer(records)
        # Disagreements land on the column they are about rather than in a
        # summary. A note saying "three columns have mixed types" sends
        # somebody to find which three.
        noted = dict(disagreements)
        return ObjectSchema(
            path=path,
            columns=tuple(
                dataclasses.replace(column, comment=noted.get(column.name, column.comment))
                for column in columns
            ),
        )

    async def snapshot(self, path: tuple[str, ...]) -> Snapshot:  # noqa: ARG002
        """Never exact, and the reason travels with it.

        Rows change between the first page and the last, so there is no instant
        this read corresponds to. A connector claiming otherwise would make
        deterministic replay give a different verdict and blame the data.
        """
        now = utc_now()
        return Snapshot(
            kind=SnapshotKind.WALL_CLOCK,
            identifier=now.isoformat(),
            captured_at=now,
            detail={
                "why_inexact": (
                    "a REST read is not a point in time: rows can change between "
                    "the first page and the last, so this cannot be replayed "
                    "against the same data"
                )
            },
        )

    async def read(
        self, path: tuple[str, ...], *, plan: SamplePlan | None = None
    ) -> AsyncIterator[pa.RecordBatch]:
        import pyarrow as pa

        if plan is not None and plan.predicate:
            # Refused, not ignored. This connector declares no predicate
            # pushdown, and reading the whole endpoint while labelling the
            # result as one segment would attribute an API's data to a slice it
            # never came from.
            raise ConnectorError(
                "the REST connector cannot apply a predicate at the source",
                code="CONNECT.NO_PREDICATE",
                remedy=(
                    "It declares no predicate pushdown. Reading everything and "
                    "calling it a segment would state one slice's rates as the "
                    "dataset's. Filter after the read, or use a source that can."
                ),
                context={"predicate": plan.predicate},
            )
        limit = plan.rows if plan is not None and plan.rows else 0
        records, truncated, pages = await self._collect(path, limit=limit)
        self.last_read_truncated = truncated
        self.last_read_pages = pages
        if not records:
            return
        columns, _ = _infer(records)
        names = [column.name for column in columns]
        for start in range(0, len(records), BATCH_ROWS):
            chunk = records[start : start + BATCH_ROWS]
            yield pa.RecordBatch.from_pydict(
                {name: [_scalar(row.get(name)) for row in chunk] for name in names}
            )

    # -- paging ------------------------------------------------------------

    async def _collect(
        self, path: tuple[str, ...], *, limit: int = 0
    ) -> tuple[list[dict[str, Any]], bool, int]:
        """Every record, following pagination, and whether it stopped early."""
        client = self._http()
        url = self._url(path)
        # None, not {}: httpx treats an empty params dict as "replace the query
        # string", which silently strips `?page=2` off a next link and refetches
        # page one forever. The read looks successful and returns the first page
        # repeated, which is the worst shape a truncation can take.
        params: dict[str, Any] | None = None
        if self._page_param:
            params = {}
            params[self._page_param] = 1
            params.setdefault("page_size", self._page_size)

        collected: list[dict[str, Any]] = []
        waited = 0.0
        pages = 0
        # The first URL counts. Without it a "next" pointing back at page one is
        # detected only after page one has been read a second time, so the read
        # returns duplicates and calls itself complete.
        seen_urls: set[str] = {url}

        while pages < self._page_limit:
            response, slept = await self._get(client, url, params)
            waited += slept
            pages += 1
            body = _json(response, url)
            page = _records(body, self._records_path)
            collected.extend(page)

            if limit and len(collected) >= limit:
                collected = collected[:limit]
                self.last_read_waited_seconds = waited
                return collected, False, pages

            nxt = _next_link(body, self._next_path)
            if nxt:
                if nxt in seen_urls:
                    # An exact repeat is a cycle, and following it reads
                    # forever. This catches the common shapes — a link pointing
                    # at itself, or looping among a fixed set of URLs — and it
                    # cannot catch a page addressed two ways (`/orders` and
                    # `/orders?page=1` are the same page only if the server's
                    # default is 1, which is not knowable here). Normalising
                    # them would be a guess about the server. The page cap is
                    # the backstop for everything this misses, and a read
                    # stopped by it says so.
                    break
                seen_urls.add(nxt)
                url, params = nxt, None
                continue
            if self._page_param and page:
                params = dict(params or {})
                params[self._page_param] = int(params.get(self._page_param, 1)) + 1
                continue
            break

        self.last_read_waited_seconds = waited
        truncated = pages >= self._page_limit
        return collected, truncated, pages

    async def _get(self, client: Any, url: str, params: dict[str, Any] | None) -> tuple[Any, float]:
        """One request, honouring a 429 rather than treating it as a failure."""
        slept = 0.0
        for _attempt in range(5):
            response = await client.get(url, params=params)
            if response.status_code == 429:
                wait = _retry_after(response)
                slept += wait
                await asyncio.sleep(wait)
                continue
            if response.status_code in (401, 403):
                raise UnauthorisedError(
                    f"{url} answered {response.status_code}",
                    remedy=(
                        "The credential resolved and the server declined it. Check "
                        "the token's scope, not its spelling."
                    ),
                    context={"url": url, "status": str(response.status_code)},
                )
            if response.status_code >= 400:
                raise UnreachableError(
                    f"{url} answered {response.status_code}",
                    remedy="Check the endpoint path and the server's own logs.",
                    context={"url": url, "status": str(response.status_code)},
                )
            return response, slept
        raise UnreachableError(
            f"{url} asked us to slow down five times running",
            remedy=(
                f"The server is rate-limiting harder than this read can absorb; "
                f"we waited {slept:.0f}s in total. Read less, or read it less often."
            ),
            context={"url": url},
        )

    def _url(self, path: tuple[str, ...]) -> str:
        leaf = "/".join(str(part).strip("/") for part in path if str(part).strip("/"))
        return f"{self._base}/{leaf}" if leaf else self._base


# -- helpers ---------------------------------------------------------------


def _retry_after(response: Any) -> float:
    raw = response.headers.get("Retry-After", "")
    try:
        return max(0.0, min(float(raw), 60.0))
    except (TypeError, ValueError):
        return 1.0


def _json(response: Any, url: str) -> Any:
    try:
        return response.json()
    except Exception as exc:
        raise ConnectorError(
            f"{url} did not return JSON",
            code="CONNECT.NOT_JSON",
            remedy=(
                "This connector reads JSON. If the endpoint serves something else, "
                "it is a different source kind."
            ),
            context={"url": url},
        ) from exc


def _records(body: Any, records_path: str) -> list[dict[str, Any]]:
    """The records inside a response envelope."""
    node = body
    for part in (p for p in records_path.split(".") if p):
        node = node.get(part) if isinstance(node, dict) else None
    if node is None:
        node = body
    if isinstance(node, dict):
        node = [node]
    if not isinstance(node, list):
        return []
    return [row for row in node if isinstance(row, dict)]


def _next_link(body: Any, next_path: str) -> str:
    if not next_path or not isinstance(body, dict):
        return ""
    node: Any = body
    for part in (p for p in next_path.split(".") if p):
        node = node.get(part) if isinstance(node, dict) else None
    return str(node) if isinstance(node, str) and node else ""


def _infer(
    records: list[dict[str, Any]],
) -> tuple[list[ColumnSchema], list[tuple[str, str]]]:
    """Columns across the whole sample, and every disagreement found.

    Not from the first record. An optional field is absent rather than null, and
    a numeric field arrives as a string on the one record that came from a
    different upstream — so a schema taken from record one is a type nobody
    checked.
    """
    seen: dict[str, set[str]] = {}
    present: dict[str, int] = {}
    for record in records:
        for key, value in record.items():
            seen.setdefault(key, set()).add(_type_of(value))
            present[key] = present.get(key, 0) + 1

    columns: list[ColumnSchema] = []
    disagreements: list[tuple[str, str]] = []
    total = len(records)
    for name, kinds in seen.items():
        concrete = sorted(kinds - {"null"})
        if len(concrete) > 1:
            disagreements.append(
                (name, f"arrives as {' and as '.join(concrete)} across the sample")
            )
        columns.append(
            ColumnSchema(
                name=name,
                type_name=concrete[0] if concrete else "null",
                nullable="null" in kinds or present.get(name, 0) < total,
                ordinal=len(columns),
            )
        )
    return columns, disagreements


def _type_of(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "double"
    if isinstance(value, (list, dict)):
        return "json"
    return "string"


def _scalar(value: Any) -> Any:
    """Arrow takes scalars; a nested value becomes its JSON text.

    Flattening would invent columns the API never promised, and dropping it
    would lose a field a control might be about.
    """
    if isinstance(value, (list, dict)):
        import json

        return json.dumps(value, sort_keys=True)
    return value
