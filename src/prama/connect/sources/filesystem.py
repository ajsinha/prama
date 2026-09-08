"""Files on a local or mounted filesystem: CSV, Parquet, JSON, NDJSON.

Reading is delegated to DuckDB, which brings CSV dialect inference, Parquet and
JSON readers, glob expansion and predicate pushdown for free, and returns Arrow
directly. Writing those by hand would be months of work to arrive somewhere
worse.

A file source is where the *feed* controls live — arrival, completeness,
trailer totals, duplicate delivery — so this connector reports a file's
modification time and digest as first-class facts rather than incidental ones.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from prama.connect.capability import CapabilityMatrix, PushdownFeature
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
)
from prama.core.clock import utc_now
from prama.core.registry import PluginManifest

if TYPE_CHECKING:  # pragma: no cover
    import pyarrow as pa

#: Extensions DuckDB can read without help, mapped to its reader function.
READERS: dict[str, str] = {
    ".csv": "read_csv_auto",
    ".tsv": "read_csv_auto",
    ".txt": "read_csv_auto",
    ".parquet": "read_parquet",
    ".pq": "read_parquet",
    ".json": "read_json_auto",
    ".ndjson": "read_json_auto",
    ".jsonl": "read_json_auto",
}

CAPABILITIES = CapabilityMatrix.of(
    PushdownFeature.SQL,
    PushdownFeature.FILTER,
    PushdownFeature.AGGREGATION,
    PushdownFeature.PREDICATE_PUSHDOWN,
    PushdownFeature.PARTITION_PRUNING,
    PushdownFeature.APPROX_DISTINCT,
    PushdownFeature.QUANTILES,
    PushdownFeature.REGEX,
    PushdownFeature.WINDOW,
    PushdownFeature.QUALIFY,
    PushdownFeature.SAMPLING,
    PushdownFeature.JSON_PATH,
    PushdownFeature.EXACT_SNAPSHOT,
    regex_flavour="re2",
    max_decimal_precision=38,
    nulls_sort_first=False,
)


class FilesystemConnector(Connector):
    """A directory of data files, read through DuckDB."""

    plugin_key = "filesystem"
    source_kind = SourceKind.FILESYSTEM

    @classmethod
    def manifest(cls) -> PluginManifest:
        return cls.describe_manifest(
            key="filesystem",
            display_name="Files (CSV, Parquet, JSON)",
            capabilities=CAPABILITIES.to_capabilities(),
            description=(
                "A local or mounted directory of data files. Reads CSV with dialect "
                "inference, Parquet, and JSON, and reports arrival time and content "
                "digest so feed controls have something to check."
            ),
        )

    def __init__(self, config: dict[str, Any], **kwargs: Any) -> None:
        super().__init__(config, **kwargs)
        self._root = Path(str(self.config.get("root_path"))).expanduser()
        self._pattern = str(self.config.get("file_pattern", "**/*"))
        self._max_bytes = int(self.config.get("max_file_bytes", 0))
        self._sample_rows = int(self.config.get("schema_sample_rows", 20000))
        self._connection: Any = None

    # -- lifecycle ---------------------------------------------------------

    async def open(self) -> None:
        import duckdb

        self._connection = duckdb.connect(":memory:")

    async def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def _duck(self) -> Any:
        if self._connection is None:
            raise ConnectorError(
                "the filesystem connector was used before it was opened",
                code="CONNECT.NOT_OPEN",
                remedy="Use the connector as an async context manager, or call open() first.",
            )
        return self._connection

    # -- contract ----------------------------------------------------------

    async def health(self) -> HealthReport:
        checked = utc_now()
        if not self._root.exists():
            return HealthReport(
                state=HealthState.UNREACHABLE,
                detail=(
                    f"the directory {self._root} does not exist. Check the path, or the "
                    f"mount if it is a network share."
                ),
                checked_at=checked,
            )
        if not self._root.is_dir():
            return HealthReport(
                state=HealthState.UNREACHABLE,
                detail=f"{self._root} is a file, not a directory. Point at the folder above it.",
                checked_at=checked,
            )
        try:
            next(self._root.iterdir(), None)
        except PermissionError:
            return HealthReport(
                state=HealthState.UNAUTHORISED,
                detail=f"the directory {self._root} exists but cannot be listed.",
                missing_permissions=(f"read:{self._root}",),
                checked_at=checked,
            )
        readable = len(self._candidates())
        return HealthReport(
            state=HealthState.HEALTHY,
            detail=f"{readable} readable file(s) matching {self._pattern}",
            checked_at=checked,
        )

    async def discover(self, path: tuple[str, ...] = ()) -> list[DiscoveredObject]:
        """Files, largest and most recent first — the order a person scans in."""
        found = []
        for file in self._candidates(path):
            stat = file.stat()
            found.append(
                DiscoveredObject(
                    path=self._relative(file),
                    kind=file.suffix.lstrip(".") or "file",
                    estimated_bytes=stat.st_size,
                    last_modified=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
                )
            )
        found.sort(key=lambda o: (-(o.estimated_bytes or 0), o.qualified_name))
        return found

    async def describe(self, path: tuple[str, ...]) -> ObjectSchema:
        file = self._resolve(path)
        relation = self._duck().sql(f"SELECT * FROM {self._reader(file)} LIMIT 0")
        columns = tuple(
            ColumnSchema(name=name, type_name=str(dtype), ordinal=index)
            for index, (name, dtype) in enumerate(
                zip(relation.columns, relation.types, strict=True)
            )
        )
        rows = self._duck().sql(f"SELECT count(*) FROM {self._reader(file)}").fetchone()
        return ObjectSchema(
            path=path, columns=columns, estimated_rows=int(rows[0]) if rows else None
        )

    async def snapshot(self, path: tuple[str, ...]) -> Snapshot:
        """A content digest: exact, and stable across a re-read of the same bytes.

        Cheap because it hashes in blocks and stops at a configured ceiling —
        an exact identifier for a 40 GB extract is not worth 40 GB of reading,
        and the size and mtime carried alongside make a collision implausible.
        """
        file = self._resolve(path)
        stat = file.stat()
        digest = hashlib.sha256()
        limit = self._max_bytes or 64 * 1024 * 1024
        read = 0
        with file.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
                read += len(chunk)
                if read >= limit:
                    break
        digest.update(str(stat.st_size).encode())
        digest.update(str(stat.st_mtime_ns).encode())
        return Snapshot(
            kind=SnapshotKind.FILE_DIGEST,
            identifier=digest.hexdigest(),
            captured_at=utc_now(),
            detail={
                "bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
                "hashed_bytes": min(read, stat.st_size),
            },
        )

    async def read(
        self, path: tuple[str, ...], *, plan: SamplePlan | None = None
    ) -> AsyncIterator[pa.RecordBatch]:
        file = self._resolve(path)
        query = self._select(file, plan or SamplePlan())
        # A table, explicitly. `arrow()` returns a reader in some DuckDB
        # versions and a table in others, and the difference would surface as an
        # AttributeError on somebody else's machine rather than on ours.
        relation = self._duck().sql(query)
        to_table = getattr(relation, "to_arrow_table", None) or relation.fetch_arrow_table
        table = to_table()
        for batch in table.to_batches():
            yield batch

    def pushdown_capabilities(self) -> tuple[Any, ...]:
        return CAPABILITIES.to_capabilities()

    # -- internals ---------------------------------------------------------

    def _candidates(self, path: tuple[str, ...] = ()) -> list[Path]:
        root = self._root.joinpath(*path) if path else self._root
        if not root.exists():
            return []
        if root.is_file():
            return [root]
        return sorted(
            file
            for file in root.glob(self._pattern)
            if file.is_file()
            and file.suffix.lower() in READERS
            and self.policy.permits_path(self._relative(file))
        )

    def _relative(self, file: Path) -> tuple[str, ...]:
        try:
            return file.relative_to(self._root).parts
        except ValueError:  # pragma: no cover - defensive
            return (file.name,)

    def _resolve(self, path: tuple[str, ...]) -> Path:
        if not self.policy.permits_path(path):
            from prama.connect.spi import UnauthorisedError

            raise UnauthorisedError(
                f"the read policy for this connection does not allow {'/'.join(path)}",
                remedy=(
                    "Add the path to the connection's allowed paths, or read something "
                    "already permitted."
                ),
                context={"path": "/".join(path)},
            )
        file = self._root.joinpath(*path)
        if not file.is_file():
            raise ConnectorError(
                f"no such file: {'/'.join(path)}",
                code="CONNECT.OBJECT_MISSING",
                remedy=(
                    "The file may not have arrived yet, or may have been archived. "
                    "Discovery lists what is present."
                ),
                context={"path": "/".join(path), "root": str(self._root)},
            )
        return file

    def _reader(self, file: Path) -> str:
        reader = READERS.get(file.suffix.lower())
        if reader is None:
            raise ConnectorError(
                f"cannot read {file.suffix or 'a file with no extension'}",
                code="CONNECT.FORMAT_UNSUPPORTED",
                remedy=f"Supported here: {', '.join(sorted(READERS))}.",
                context={"file": file.name},
            )
        escaped = str(file).replace("'", "''")
        return f"{reader}('{escaped}')"

    def _select(self, file: Path, plan: SamplePlan) -> str:
        source = self._reader(file)
        if plan.strategy is SamplingStrategy.FULL:
            return f"SELECT * FROM {source}"
        if plan.strategy is SamplingStrategy.HEAD:
            return f"SELECT * FROM {source} LIMIT {int(plan.rows or 1000)}"
        if plan.fraction is not None:
            # Seeded so a sampled result is reproducible, which is what lets a
            # sampled verdict carry an honest confidence rather than a guess.
            percent = max(0.0, min(100.0, plan.fraction * 100))
            return f"SELECT * FROM {source} USING SAMPLE {percent} PERCENT (bernoulli, {plan.seed})"
        return (
            f"SELECT * FROM {source} USING SAMPLE {int(plan.rows or 1000)} ROWS "
            f"(reservoir, {plan.seed})"
        )
