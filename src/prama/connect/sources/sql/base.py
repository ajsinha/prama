"""The choreography every SQL source shares.

Health, discovery, description, snapshot and paged reading are the same dance
whichever database is on the other end. Writing it once means a new SQL source
is a dialect and a driver rather than a fifth copy of this logic with its own
subtly different idea of what a sample is.

Two things this base insists on, because they are the difference between a tool
that can be pointed at production and one that cannot:

* **Reading cannot write.** Enforced by the server through the dialect's session
  setup, not by our own discipline in avoiding UPDATE statements.
* **A read has a ceiling.** Row and byte budgets are checked as batches arrive,
  and exceeding one truncates the read and says so, rather than running until
  someone notices the database is struggling.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from prama.connect.pacing import LoadPacer
from prama.connect.sources.sql.dialect import SqlDialect
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
)
from prama.core.clock import utc_now
from prama.core.log import get_logger
from prama.core.registry import Capability

if TYPE_CHECKING:  # pragma: no cover
    import pyarrow as pa

_log = get_logger(__name__)

#: Rows per Arrow batch. Large enough that per-batch overhead disappears, small
#: enough that a budget is enforced promptly and memory stays bounded.
BATCH_ROWS = 10_000

#: Default ceiling on a single statement. A profiling query that runs for an
#: hour against a production database is indistinguishable, from the database's
#: point of view, from an attack.
DEFAULT_STATEMENT_TIMEOUT_MS = 60_000


class SqlConnector(Connector):
    """A relational source, driven by a :class:`SqlDialect`.

    Subclasses supply connection management and two primitives — ``_fetch`` and
    ``_stream`` — and inherit the rest of the contract.
    """

    source_kind = SourceKind.RELATIONAL
    #: Set by each concrete connector.
    dialect: SqlDialect

    def __init__(self, config: dict[str, Any], **kwargs: Any) -> None:
        super().__init__(config, **kwargs)
        self._include_views = bool(self.config.get("include_views", True))
        self._statement_timeout_ms = int(
            self.config.get("statement_timeout_ms", DEFAULT_STATEMENT_TIMEOUT_MS)
        )
        self._schemas = tuple(self.config.get("schemas") or ())
        #: What the last read cost and how it was paced. Recorded with the
        #: read's evidence, and fed back so the next cost preview is measured
        #: rather than unknown.
        self.last_read: dict[str, Any] = {}

    # -- driver primitives -------------------------------------------------

    @abstractmethod
    async def _fetch(self, sql: str, *params: Any) -> list[tuple[Any, ...]]:
        """Run a statement and return every row. For catalogue-sized results."""

    # Declared without ``async`` so that an implementation written as an async
    # generator satisfies it: an async generator function returns the iterator
    # directly rather than a coroutine yielding one.
    @abstractmethod
    def _stream(self, sql: str, batch_rows: int) -> AsyncIterator[list[tuple[Any, ...]]]:
        """Run a statement and yield row chunks without materialising the whole.

        Separate from ``_fetch`` because the distinction is the whole point: a
        table read must never depend on the result fitting in memory.
        """

    @abstractmethod
    def _column_names(self) -> tuple[str, ...]:
        """Column names from the most recent ``_stream`` statement."""

    # -- contract ----------------------------------------------------------

    async def health(self) -> HealthReport:
        checked = utc_now()
        started = utc_now()
        try:
            await self._fetch("SELECT 1")
        except Exception as exc:
            state, detail = self.classify_failure(exc)
            return HealthReport(state=state, detail=detail, checked_at=checked)
        latency = (utc_now() - started).total_seconds() * 1000
        try:
            objects = await self.discover()
        except Exception as exc:
            # Reachable but the catalogue is closed: a permissions problem, and
            # a distinct one from being unable to connect at all. Conflating
            # them sends someone to the network team for a grant.
            _, detail = self.classify_failure(exc)
            return HealthReport(
                state=HealthState.UNAUTHORISED,
                detail=f"connected, but the catalogue could not be read: {detail}",
                checked_at=checked,
                latency_ms=latency,
                missing_permissions=("catalogue read",),
            )
        return HealthReport(
            state=HealthState.HEALTHY,
            detail=f"{len(objects)} readable object(s)",
            checked_at=checked,
            latency_ms=latency,
        )

    async def discover(self, path: tuple[str, ...] = ()) -> list[DiscoveredObject]:
        rows = await self._fetch(self.dialect.list_objects_sql(include_views=self._include_views))
        found: list[DiscoveredObject] = []
        for schema, name, kind, row_estimate, byte_estimate, comment in rows:
            qualified = (str(schema), str(name))
            if self._schemas and schema not in self._schemas:
                continue
            if not self.policy.permits_path(qualified):
                continue
            if path and qualified[: len(path)] != path:
                continue
            found.append(
                DiscoveredObject(
                    path=qualified,
                    kind=str(kind).lower(),
                    estimated_rows=int(row_estimate) if row_estimate is not None else None,
                    estimated_bytes=int(byte_estimate) if byte_estimate is not None else None,
                    comment=str(comment or ""),
                )
            )
        # Largest first: someone scanning an unfamiliar source is looking for
        # the tables that matter, and those are usually the big ones.
        found.sort(key=lambda o: (-(o.estimated_bytes or o.estimated_rows or 0), o.qualified_name))
        return found

    async def describe(self, path: tuple[str, ...]) -> ObjectSchema:
        self._check_permitted(path)
        schema, name = self._split(path)
        rows = await self._fetch(self.dialect.describe_sql(), schema, name)
        if not rows:
            raise ConnectorError(
                f"no table or view named {'.'.join(path)!r}",
                code="CONNECT.OBJECT_MISSING",
                remedy="Discovery lists what this source contains.",
                context={"object": ".".join(path)},
            )
        columns = tuple(
            ColumnSchema(
                name=str(row[0]),
                type_name=str(row[1]).upper(),
                nullable=_as_bool(row[2]),
                ordinal=int(row[3]),
                comment=str(row[4] or ""),
                precision=int(row[5]) if row[5] is not None else None,
                scale=int(row[6]) if row[6] is not None else None,
            )
            for row in rows
        )
        return ObjectSchema(
            path=path, columns=columns, estimated_rows=await self._estimate_rows(path)
        )

    async def snapshot(self, path: tuple[str, ...]) -> Snapshot:
        self._check_permitted(path)
        statement = self.dialect.snapshot_sql()
        if statement is None:
            # No marker available. Wall clock is weak, and saying so is the
            # point: evidence recorded against it cannot claim to be replayable.
            return Snapshot(
                kind=SnapshotKind.WALL_CLOCK,
                identifier=utc_now().isoformat(),
                captured_at=utc_now(),
                detail={
                    "object": ".".join(path),
                    "note": (
                        f"{self.dialect.name} offers no point-in-time marker; this "
                        "snapshot cannot be replayed exactly"
                    ),
                },
            )
        rows = await self._fetch(statement)
        return Snapshot(
            kind=self.dialect.snapshot_kind,
            identifier=str(rows[0][0]),
            captured_at=utc_now(),
            detail={"object": ".".join(path), "dialect": self.dialect.name},
        )

    async def read(
        self, path: tuple[str, ...], *, plan: SamplePlan | None = None
    ) -> AsyncIterator[pa.RecordBatch]:
        """Stream an object, stopping at whichever ceiling is reached first."""
        import pyarrow as pa

        self._check_permitted(path)
        plan = plan or SamplePlan()
        budget = _Budget(plan, self.policy)
        pacer = LoadPacer(self.policy.load_ceiling)
        statement = self.dialect.stream_sql(path, plan)
        rows_seen = 0
        bytes_seen = 0
        async for chunk in pacer.pace(self._stream(statement, budget.batch_rows)):
            if not chunk:
                continue
            allowed = budget.allow(len(chunk))
            if allowed <= 0:
                budget.report(path, rows_seen)
                break
            if allowed < len(chunk):
                chunk = chunk[:allowed]
            names = self._column_names()
            columns = list(zip(*chunk, strict=True))
            batch = pa.RecordBatch.from_arrays(
                [pa.array(list(column)) for column in columns], names=list(names)
            )
            budget.consume(batch.nbytes)
            rows_seen += batch.num_rows
            bytes_seen += batch.nbytes
            yield batch
            if budget.exhausted:
                budget.report(path, rows_seen)
                break
        self._record_read(path, rows_seen, bytes_seen, pacer)

    def _record_read(
        self, path: tuple[str, ...], rows: int, byte_count: int, pacer: LoadPacer
    ) -> None:
        """Keep what this read actually cost.

        The working time, not the wall clock: the waiting a load ceiling
        imposes is not the source's speed, and folding it into a throughput
        measurement would make every subsequent estimate progressively slower
        for no reason.
        """
        self.last_read = {
            "object": ".".join(path),
            "rows": rows,
            "bytes": byte_count,
            "seconds": round(pacer.report.working_seconds, 3),
            "pacing": pacer.report.to_dict(),
        }

    def pushdown_capabilities(self) -> tuple[Capability, ...]:
        return self.dialect.capabilities.to_capabilities()

    # -- helpers -----------------------------------------------------------

    def classify_failure(self, exc: Exception) -> tuple[HealthState, str]:
        """Turn a driver exception into a state someone can act on.

        The distinction that matters is *whose problem it is*: unreachable sends
        someone to the network, unauthorised sends them to whoever grants
        access. Reporting both as "connection failed" wastes a day.
        """
        message = str(exc).lower()
        if any(word in message for word in ("password", "authentication", "permission", "denied")):
            return HealthState.UNAUTHORISED, str(exc)
        if any(word in message for word in ("timeout", "timed out")):
            return HealthState.DEGRADED, f"the source did not respond in time: {exc}"
        return HealthState.UNREACHABLE, str(exc)

    async def _estimate_rows(self, path: tuple[str, ...]) -> int | None:
        """A row count, but never at the cost of scanning the table.

        A catalogue estimate a few percent out is useful. A ``count(*)`` against
        a billion-row production table, issued because somebody opened a dataset
        page, is not something a business tool should ever do — so a dialect
        with no cheap estimate returns nothing, and the UI shows "unknown"
        rather than buying a number with an outage.
        """
        statement = self.dialect.estimate_rows_sql()
        if statement is None:
            return None
        schema, name = self._split(path)
        try:
            rows = await self._fetch(statement, schema, name)
        except Exception as exc:
            _log.debug("row estimate unavailable for %s: %s", ".".join(path), exc)
            return None
        if not rows or rows[0][0] is None:
            return None
        estimate = int(rows[0][0])
        return estimate if estimate >= 0 else None

    def _split(self, path: tuple[str, ...]) -> tuple[str, str]:
        if len(path) == 1:
            return "public", path[0]
        return path[-2], path[-1]

    def _check_permitted(self, path: tuple[str, ...]) -> None:
        if not path:
            raise ConnectorError(
                "no object was named",
                code="CONNECT.OBJECT_MISSING",
                remedy="Give the schema and table name.",
            )
        if not self.policy.permits_path(path):
            raise UnauthorisedError(
                f"the read policy for this connection does not allow {'.'.join(path)!r}",
                remedy=("Add it to the connection's allowed paths, or read a permitted object."),
                context={"object": ".".join(path)},
            )


class _Budget:
    """Row and byte ceilings for one read.

    Rows are capped exactly, because the count is known before the data is.
    Bytes can only be enforced between batches — the size of a batch is not
    knowable until it has been fetched — so a byte ceiling may be overshot by at
    most one batch. That is a real limit and is stated rather than hidden: a
    caller who needs a hard byte cap sets a row cap too.
    """

    def __init__(self, plan: SamplePlan, policy: Any) -> None:
        self._row_limit = _least(plan.rows, policy.max_rows_read)
        self._byte_limit = policy.max_bytes_scanned
        self.rows = 0
        self.bytes = 0
        self.truncated = False

    @property
    def batch_rows(self) -> int:
        """How many rows to ask the source for at a time.

        Never more than the read will actually keep. Fetching ten thousand rows
        across the network to discard all but twenty-five is work a production
        database does on the customer's behalf for no reason.
        """
        if self._row_limit is None:
            return BATCH_ROWS
        return max(1, min(BATCH_ROWS, self._row_limit))

    @property
    def exhausted(self) -> bool:
        if self._row_limit is not None and self.rows >= self._row_limit:
            return True
        return self._byte_limit is not None and self.bytes >= self._byte_limit

    def allow(self, offered: int) -> int:
        """How many of the offered rows the budget still permits."""
        if self._byte_limit is not None and self.bytes >= self._byte_limit:
            self.truncated = True
            return 0
        if self._row_limit is None:
            self.rows += offered
            return offered
        room = self._row_limit - self.rows
        if room <= 0:
            self.truncated = True
            return 0
        if offered > room:
            self.truncated = True
        taken = min(offered, room)
        self.rows += taken
        return taken

    def consume(self, nbytes: int) -> None:
        self.bytes += nbytes
        if self._byte_limit is not None and self.bytes >= self._byte_limit:
            self.truncated = True

    def report(self, path: tuple[str, ...], rows_seen: int) -> None:
        if self.truncated:
            _log.info(
                "read of %s stopped at the configured ceiling after %d rows (%d bytes)",
                ".".join(path),
                rows_seen,
                self.bytes,
            )


def _least(*values: int | None) -> int | None:
    present = [v for v in values if v is not None]
    return min(present) if present else None


def _as_bool(value: Any) -> bool:
    """Nullability arrives as a bool, as ``YES``/``NO``, or as 0/1."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().upper() in ("YES", "Y", "TRUE", "T", "1")
    return bool(value)
