"""SQLite files as a data source.

Useful far beyond development: SQLite extracts are a real delivery format in
regulated estates, and being able to point Prama at one without provisioning
anything is what makes an evaluation take an afternoon rather than a quarter.

Reads run in a worker thread. The driver is synchronous, and blocking the event
loop to read a table would stall every other control in the process — a failure
that appears as unexplained latency somewhere else entirely.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import AsyncIterator
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
    UnauthorisedError,
)
from prama.core.clock import utc_now
from prama.core.registry import PluginManifest

if TYPE_CHECKING:  # pragma: no cover
    import pyarrow as pa

CAPABILITIES = CapabilityMatrix.of(
    PushdownFeature.SQL,
    PushdownFeature.FILTER,
    PushdownFeature.AGGREGATION,
    PushdownFeature.PREDICATE_PUSHDOWN,
    PushdownFeature.WINDOW,
    PushdownFeature.EXACT_SNAPSHOT,
    # Deliberately absent: SQLite's REGEXP is not built in, its approximate
    # aggregates do not exist, and claiming either would produce a control that
    # compiles and then fails at the source.
    regex_flavour="none",
    max_decimal_precision=None,
    nulls_sort_first=True,
)

BATCH_ROWS = 10_000


class SqliteConnector(Connector):
    """A SQLite database file."""

    plugin_key = "sqlite"
    source_kind = SourceKind.RELATIONAL

    @classmethod
    def manifest(cls) -> PluginManifest:
        return cls.describe_manifest(
            key="sqlite",
            display_name="SQLite database file",
            capabilities=CAPABILITIES.to_capabilities(),
            description=(
                "A SQLite file. Opened read-only, so pointing Prama at a production "
                "extract cannot alter it."
            ),
        )

    def __init__(self, config: dict[str, Any], **kwargs: Any) -> None:
        super().__init__(config, **kwargs)
        self._path = Path(str(self.config.get("database_path"))).expanduser()
        self._timeout = float(self.config.get("busy_timeout_seconds", 5.0))
        self._include_views = bool(self.config.get("include_views", True))

    # -- contract ----------------------------------------------------------

    async def health(self) -> HealthReport:
        checked = utc_now()
        if not self._path.is_file():
            return HealthReport(
                state=HealthState.UNREACHABLE,
                detail=f"no database file at {self._path}.",
                checked_at=checked,
            )
        try:
            tables = await asyncio.to_thread(self._list_objects)
        except sqlite3.OperationalError as exc:
            return HealthReport(
                state=HealthState.UNAUTHORISED
                if "permission" in str(exc).lower()
                else HealthState.UNREACHABLE,
                detail=f"the file exists but could not be opened: {exc}",
                checked_at=checked,
            )
        return HealthReport(
            state=HealthState.HEALTHY,
            detail=f"{len(tables)} readable table(s)",
            checked_at=checked,
        )

    async def discover(self, path: tuple[str, ...] = ()) -> list[DiscoveredObject]:
        rows = await asyncio.to_thread(self._list_objects)
        found = [
            DiscoveredObject(path=(name,), kind=kind, estimated_rows=rows_estimate)
            for name, kind, rows_estimate in rows
            if self.policy.permits_path((name,)) and (not path or name == path[0])
        ]
        # Largest first: a person scanning a source looks for the big tables.
        found.sort(key=lambda o: (-(o.estimated_rows or 0), o.qualified_name))
        return found

    async def describe(self, path: tuple[str, ...]) -> ObjectSchema:
        self._check_permitted(path)
        return await asyncio.to_thread(self._describe, path[0])

    async def snapshot(self, path: tuple[str, ...]) -> Snapshot:
        """The file's state: size, modification time and page count.

        Not ``PRAGMA data_version``, which is the obvious candidate and is
        wrong. It reports changes made by *other* connections during the life
        of the current one, so a fresh connection always reads 1 no matter what
        has happened to the file. Used as a change marker it never moves, and
        anything built on it — incremental profiling above all — would trust a
        stale profile forever while believing it had checked.

        Size, nanosecond mtime and page count together do move, and a change
        that preserved all three is not something that happens by accident.
        """
        self._check_permitted(path)
        identity, page_count = await asyncio.to_thread(self._file_identity)
        return Snapshot(
            kind=SnapshotKind.FILE_DIGEST,
            identifier=identity,
            captured_at=utc_now(),
            detail={"page_count": page_count, "object": path[0]},
        )

    async def read(
        self, path: tuple[str, ...], *, plan: SamplePlan | None = None
    ) -> AsyncIterator[pa.RecordBatch]:
        self._check_permitted(path)
        plan = plan or SamplePlan()
        self.require_predicate_support(plan)
        offset = 0
        while True:
            batch = await asyncio.to_thread(self._read_batch, path[0], plan, offset)
            if batch is None or batch.num_rows == 0:
                return
            yield batch
            offset += batch.num_rows
            if plan.rows is not None and offset >= plan.rows:
                return

    def pushdown_capabilities(self) -> tuple[Any, ...]:
        return CAPABILITIES.to_capabilities()

    # -- internals (all synchronous, all run in a worker thread) -----------

    # -- running a control -------------------------------------------------

    @property
    def can_run_controls(self) -> bool:
        """SQLite is a query engine, so a control can be pushed down to it.

        Worth claiming rather than leaving to the relational base class, which
        this connector does not inherit: a SQLite file is read here through the
        stdlib driver, and a source that could evaluate a control locally and
        did not would drag every row across for no reason.
        """
        return True

    async def run_metric_query(self, sql: str) -> list[dict[str, Any]]:
        """Evaluate a compiled control's metric query."""
        import asyncio

        from prama.connect.sources.query import sole_read_statement

        statement = sole_read_statement(sql)
        return await asyncio.to_thread(self._query, statement)

    def _query(self, statement: str) -> list[dict[str, Any]]:
        from prama.connect.sources.query import register_regexp

        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            # The SQLite dialect declares the regex capability on the strength
            # of this registration. Without it every validity control compiled
            # for SQLite fails with "no such function: REGEXP".
            register_regexp(connection)
            return [dict(row) for row in connection.execute(statement).fetchall()]

    def _connect(self) -> sqlite3.Connection:
        # Read-only URI: pointing at a production extract cannot alter it, and
        # the guarantee is enforced by the driver rather than by our discipline.
        uri = f"file:{self._path}?mode=ro"
        return sqlite3.connect(uri, uri=True, timeout=self._timeout)

    def _list_objects(self) -> list[tuple[str, str, int | None]]:
        kinds = ("table", "view") if self._include_views else ("table",)
        placeholders = ", ".join("?" for _ in kinds)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT name, type FROM sqlite_master WHERE type IN ({placeholders}) "
                f"AND name NOT LIKE 'sqlite_%' ORDER BY name",
                kinds,
            ).fetchall()
            out: list[tuple[str, str, int | None]] = []
            for name, kind in rows:
                try:
                    count = connection.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0]
                except sqlite3.Error:  # a view that cannot be evaluated
                    count = None
                out.append((name, kind, count))
            return out

    def _describe(self, name: str) -> ObjectSchema:
        with self._connect() as connection:
            info = connection.execute(f'PRAGMA table_info("{name}")').fetchall()
            if not info:
                raise ConnectorError(
                    f"no table or view named {name!r}",
                    code="CONNECT.OBJECT_MISSING",
                    remedy="Discovery lists what this database contains.",
                    context={"object": name},
                )
            columns = tuple(
                ColumnSchema(
                    name=row[1],
                    type_name=(row[2] or "TEXT").upper(),
                    nullable=not row[3],
                    ordinal=row[0],
                )
                for row in info
            )
            count = connection.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0]
        return ObjectSchema(path=(name,), columns=columns, estimated_rows=count)

    def _file_identity(self) -> tuple[str, int]:
        stat = self._path.stat()
        with self._connect() as connection:
            pages = int(connection.execute("PRAGMA page_count").fetchone()[0])
        return f"{stat.st_size}:{stat.st_mtime_ns}:{pages}", pages

    def _read_batch(self, name: str, plan: SamplePlan, offset: int) -> pa.RecordBatch | None:
        import pyarrow as pa

        limit = BATCH_ROWS
        if plan.rows is not None:
            limit = min(limit, max(0, plan.rows - offset))
            if limit == 0:
                return None
        query = self._select(name, plan, limit, offset)
        with self._connect() as connection:
            cursor = connection.execute(query)
            names = [d[0] for d in cursor.description]
            rows = cursor.fetchall()
        if not rows:
            return None
        columns = list(zip(*rows, strict=True))
        return pa.RecordBatch.from_arrays(
            [pa.array(list(column)) for column in columns], names=names
        )

    def _select(self, name: str, plan: SamplePlan, limit: int, offset: int) -> str:
        where = f" WHERE {plan.predicate}" if plan.predicate else ""
        if plan.strategy in (SamplingStrategy.FULL, SamplingStrategy.HEAD):
            return f'SELECT * FROM "{name}"{where} LIMIT {limit} OFFSET {offset}'
        # SQLite has no sampling clause. A seeded ordering is deterministic and
        # honest about being a sample rather than pretending to be a scan.
        return (
            f'SELECT * FROM "{name}"{where} ORDER BY (rowid * {plan.seed or 1} % 1000003) '
            f"LIMIT {limit} OFFSET {offset}"
        )

    def _check_permitted(self, path: tuple[str, ...]) -> None:
        if not path:
            raise ConnectorError(
                "no object was named",
                code="CONNECT.OBJECT_MISSING",
                remedy="Give the table or view name.",
            )
        if not self.policy.permits_path(path):
            raise UnauthorisedError(
                f"the read policy for this connection does not allow {path[0]!r}",
                remedy="Add it to the connection's allowed paths, or read a permitted object.",
                context={"object": path[0]},
            )
