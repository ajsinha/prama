"""A connector for fixed-width text extracts: the worked example of docs/developer/connectors.md.

A mainframe or a vendor feed often delivers a file with no delimiter at all:
each field sits at a fixed position, and the layout lives in a copybook or a
PDF. This connector reads a folder of such files, given that layout as
``name:start-end`` positions (1-based and inclusive, as a copybook states them).

What it shows, in the order the guide walks it:

* the **five abstract methods** of `prama.connect.spi.Connector`
  (``health``, ``discover``, ``describe``, ``snapshot``, ``read``);
* configuration read **only** through ``self.config.get(...)``, so the form a
  data architect fills in is derived from this file (``root_path`` and
  ``layout`` have no default, so the form marks them required);
* an **overlay** that adds presentation and nothing else;
* **honest refusals**: a sampling strategy it cannot perform and a predicate it
  cannot apply are refused with a remedy, never silently widened to a full read;
* **no pushdown**: it declares no capability, so a control on one of these files
  is evaluated locally over the Arrow batches ``read`` yields.

It is not registered with the product. ``register`` puts it in a registry the
caller passes, which is how the test exercises it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

from prama_kernel.clock import utc_now

from prama.connect.capability import CapabilityMatrix
from prama.connect.config_schema import FieldPresentation, InputKind
from prama.connect.registry import ConnectorRegistry
from prama.connect.spi import (
    ColumnSchema,
    Connector,
    ConnectorError,
    DiscoveredObject,
    HealthReport,
    HealthState,
    ObjectSchema,
    SamplePlan,
    SamplingStrategy,
    Snapshot,
    SnapshotKind,
    SourceKind,
    UnauthorisedError,
    Verification,
)
from prama.core.registry import PluginManifest

if TYPE_CHECKING:  # pragma: no cover
    import pyarrow as pa

#: Declares nothing. Correct, and fully functional: the engine reads Arrow and
#: evaluates locally. A connector earns pushdown by claiming it, and a file has
#: no query engine to claim it for.
CAPABILITIES = CapabilityMatrix()

#: Rows per Arrow batch.
BATCH_ROWS = 10_000

Field = tuple[str, int, int]


def parse_layout(text: str) -> tuple[Field, ...]:
    """``"trade_id:1-6,ccy:7-9"`` -> ``(("trade_id", 0, 6), ("ccy", 6, 9))``, as slices."""
    fields: list[Field] = []
    for part in (p.strip() for p in text.replace("\n", ",").split(",")):
        if not part:
            continue
        name, _, span = part.partition(":")
        start, _, end = span.partition("-")
        if not name.strip() or not start.strip().isdigit() or not end.strip().isdigit():
            raise ValueError(f"{part!r} is not name:start-end")
        first, last = int(start), int(end)
        if first < 1 or last < first:
            raise ValueError(f"{part!r}: positions are 1-based and start <= end")
        fields.append((name.strip(), first - 1, last))
    if not fields:
        raise ValueError("the layout names no fields")
    return tuple(fields)


class FixedWidthConnector(Connector):
    """A folder of fixed-width text files, one dataset per file."""

    plugin_key = "fixed_width"
    source_kind = SourceKind.FILESYSTEM

    @classmethod
    def manifest(cls) -> PluginManifest:
        return cls.describe_manifest(
            key="fixed_width",
            display_name="Fixed-width text extract",
            capabilities=CAPABILITIES.to_capabilities(),
            description="A folder of fixed-width files, read with a declared record layout.",
            # Written and tested here, against files the test makes. Nothing has
            # sent it a real mainframe extract, so it says so.
            verification=Verification.CODE_COMPLETE,
        )

    def __init__(self, config: dict[str, Any], **kwargs: Any) -> None:
        super().__init__(config, **kwargs)
        self._root = Path(str(self.config.get("root_path"))).expanduser()
        self._suffix = str(self.config.get("suffix", ".txt"))
        self._encoding = str(self.config.get("encoding", "ascii"))
        # A bad layout is kept as a finding rather than raised here, so that
        # `health` can say "misconfigured" and send the reader back to the form
        # instead of to the network team.
        self._layout: tuple[Field, ...] = ()
        self._layout_error = ""
        try:
            self._layout = parse_layout(str(self.config.get("layout") or ""))
        except ValueError as exc:
            self._layout_error = str(exc)

    # -- the contract ------------------------------------------------------

    async def health(self) -> HealthReport:
        checked = utc_now()
        if self._layout_error:
            return HealthReport(
                state=HealthState.MISCONFIGURED,
                detail=f"the record layout cannot be read: {self._layout_error}",
                checked_at=checked,
            )
        if not self._root.is_dir():
            return HealthReport(
                state=HealthState.UNREACHABLE,
                detail=f"there is no folder at {self._root}",
                checked_at=checked,
            )
        files = await asyncio.to_thread(self._files)
        return HealthReport(
            state=HealthState.HEALTHY,
            detail=f"{len(files)} extract(s), {len(self._layout)} field(s) per record",
            checked_at=checked,
        )

    async def discover(self, path: tuple[str, ...] = ()) -> list[DiscoveredObject]:
        width = max((end for _, _, end in self._layout), default=1)
        found = [
            DiscoveredObject(
                path=(file.name,),
                kind="file",
                estimated_bytes=file.stat().st_size,
                # An estimate from the record width, not a count: discovery
                # must not read every file to rank them.
                estimated_rows=file.stat().st_size // (width + 1),
            )
            for file in await asyncio.to_thread(self._files)
            if self.policy.permits_path((file.name,)) and (not path or file.name == path[0])
        ]
        # Largest first: a person scanning a source looks for the big ones.
        found.sort(key=lambda o: (-(o.estimated_bytes or 0), o.qualified_name))
        return found

    async def describe(self, path: tuple[str, ...]) -> ObjectSchema:
        file = self._file(path)
        rows = await asyncio.to_thread(self._count, file)
        columns = tuple(
            ColumnSchema(name=name, type_name="VARCHAR", nullable=True, ordinal=index)
            for index, (name, _, _) in enumerate(self._layout)
        )
        return ObjectSchema(path=path, columns=columns, estimated_rows=rows)

    async def snapshot(self, path: tuple[str, ...]) -> Snapshot:
        """A digest of the file's bytes: exact, so replaying against it is reproducible."""
        file = self._file(path)
        digest = await asyncio.to_thread(self._digest, file)
        return Snapshot(
            kind=SnapshotKind.FILE_DIGEST,
            identifier=f"{file.stat().st_size}:{digest}",
            captured_at=utc_now(),
            detail={"object": file.name},
        )

    async def read(
        self, path: tuple[str, ...], *, plan: SamplePlan | None = None
    ) -> AsyncIterator[pa.RecordBatch]:
        file = self._file(path)
        plan = plan or SamplePlan()
        # A filtered read this connector cannot filter is refused, never widened.
        self.require_predicate_support(plan)
        if plan.strategy not in (SamplingStrategy.FULL, SamplingStrategy.HEAD):
            raise ConnectorError(
                f"a fixed-width file cannot be sampled by {plan.strategy.value}",
                code="CONNECT.NO_SAMPLING",
                remedy=(
                    "Read it whole, or take a HEAD sample to preview its shape. A "
                    "sample this connector cannot draw honestly is not drawn."
                ),
                context={"object": file.name, "strategy": plan.strategy.value},
            )
        offset = 0
        while True:
            batch = await asyncio.to_thread(self._batch, file, offset, plan.rows)
            if batch is None:
                return
            yield batch
            offset += batch.num_rows
            if plan.rows is not None and offset >= plan.rows:
                return

    def pushdown_capabilities(self) -> tuple[Any, ...]:
        return CAPABILITIES.to_capabilities()

    # -- internals (synchronous, run in a worker thread) -------------------

    def _files(self) -> list[Path]:
        return sorted(p for p in self._root.glob(f"*{self._suffix}") if p.is_file())

    def _file(self, path: tuple[str, ...]) -> Path:
        if self._layout_error:
            raise ConnectorError(
                f"the record layout cannot be read: {self._layout_error}",
                code="CONNECT.MISCONFIGURED",
                remedy="Correct the layout on the connection: name:start-end, comma separated.",
            )
        if not path:
            raise ConnectorError(
                "no file was named", code="CONNECT.OBJECT_MISSING", remedy="Give the file name."
            )
        if not self.policy.permits_path(path):
            raise UnauthorisedError(
                f"the read policy for this connection does not allow {path[0]!r}",
                remedy="Add it to the connection's allowed paths, or read a permitted file.",
                context={"object": path[0]},
            )
        file = self._root / path[0]
        if file.parent != self._root or not file.is_file():
            raise ConnectorError(
                f"no extract named {path[0]!r} in {self._root}",
                code="CONNECT.OBJECT_MISSING",
                remedy="Discovery lists the files this folder holds.",
                context={"object": path[0]},
            )
        return file

    def _lines(self, file: Path) -> list[str]:
        text = file.read_text(encoding=self._encoding)
        return [line for line in text.splitlines() if line.strip()]

    def _count(self, file: Path) -> int:
        return len(self._lines(file))

    @staticmethod
    def _digest(file: Path) -> str:
        sha = hashlib.sha256()
        with file.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                sha.update(chunk)
        return sha.hexdigest()

    def _batch(self, file: Path, offset: int, limit: int | None) -> pa.RecordBatch | None:
        import pyarrow as pa

        size = BATCH_ROWS if limit is None else min(BATCH_ROWS, max(0, limit - offset))
        lines = self._lines(file)[offset : offset + size]
        if not lines:
            return None
        # A blank field is a missing value, not an empty string: the same rule
        # every other connector follows, so a completeness control means one thing.
        columns = {
            name: [line[start:end].strip() or None for line in lines]
            for name, start, end in self._layout
        }
        return pa.RecordBatch.from_pydict(columns)


#: Presentation only. Each key must be a field the connector reads, or
#: `ConnectorRegistry.audit` reports it.
OVERLAY: dict[str, FieldPresentation] = {
    "root_path": FieldPresentation(
        label="Folder",
        help="The directory the extracts land in.",
        input_kind=InputKind.PATH,
        order=10,
    ),
    "layout": FieldPresentation(
        label="Record layout",
        help="name:start-end per field, 1-based and inclusive, as the copybook states it.",
        input_kind=InputKind.MULTILINE,
        order=20,
    ),
    "suffix": FieldPresentation(label="File suffix", order=30),
    "encoding": FieldPresentation(
        label="Encoding",
        help="ascii, latin-1, or cp037 for EBCDIC straight from a mainframe.",
        group="advanced",
        order=110,
    ),
}


def register(registry: ConnectorRegistry) -> ConnectorRegistry:
    """Add the connector, its (empty) capability matrix and its overlay to *registry*."""
    registry.register(FixedWidthConnector, capabilities=CAPABILITIES, overlay=OVERLAY, replace=True)
    return registry
