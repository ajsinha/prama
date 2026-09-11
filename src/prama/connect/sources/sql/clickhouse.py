"""ClickHouse.

A column store, which changes what a connector should ask for rather than only
how it asks. Three decisions follow from that and none of them is syntax.

**`system.parts` knows the row count and it is free.** ClickHouse keeps per-part
statistics, so discovery across a large estate costs nothing. A `count(*)` here
is cheap by warehouse standards and still pointless when the answer is already
recorded.

**Sampling needs a sampling key and usually there is not one.** `SAMPLE 0.1` is
only valid on a MergeTree declared with `SAMPLE BY`, and on a table without one
it is a syntax error rather than a slower read. So this dialect does **not**
claim native sampling: the base connector then reads ordinarily and reports the
result as approximate, which is true, where claiming sampling would produce a
control that compiles and fails at the source.

**A snapshot is wall-clock and says so.** ClickHouse has no cheap
statement-level marker a reader can name and return to — parts merge in the
background, and a query id does not pin them. Reporting anything exact would
make deterministic replay claim something the engine cannot honour.

Decimals arrive as :class:`decimal.Decimal` from the driver, which is one fewer
thing to fix than JDBC needed.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from prama.connect.capability import CapabilityMatrix, PushdownFeature
from prama.connect.sources.sql.base import SqlConnector
from prama.connect.sources.sql.dialect import SqlDialect
from prama.connect.spi import (
    ConnectorError,
    SamplePlan,
    SnapshotKind,
    UnreachableError,
    Verification,
)
from prama.core.concurrency import DedicatedThread
from prama.core.registry import PluginManifest

__all__ = ["CAPABILITIES", "ClickHouseConnector", "ClickHouseDialect"]

CAPABILITIES = CapabilityMatrix.of(
    PushdownFeature.SQL,
    PushdownFeature.FILTER,
    PushdownFeature.AGGREGATION,
    PushdownFeature.PREDICATE_PUSHDOWN,
    PushdownFeature.APPROX_DISTINCT,
    PushdownFeature.QUANTILES,
    PushdownFeature.REGEX,
    PushdownFeature.WINDOW,
    PushdownFeature.PARTITION_PRUNING,
)


class ClickHouseDialect(SqlDialect):
    """ClickHouse SQL."""

    name = "clickhouse"
    capabilities = CAPABILITIES
    positional_placeholder = "?"
    has_cheap_row_estimate = True
    #: No statement-level marker a reader can return to: parts merge in the
    #: background and a query id does not pin them.
    snapshot_kind = SnapshotKind.WALL_CLOCK
    #: SAMPLE needs a sampling key the table may not have, where it is a syntax
    #: error rather than a slower read.
    has_native_sampling = False

    def quote(self, identifier: str) -> str:
        return "`" + identifier.replace("`", "\\`") + "`"

    def list_objects_sql(self, *, include_views: bool) -> str:
        kinds = "" if include_views else " AND engine NOT LIKE '%View'"
        return f"""
            SELECT database, name,
                   if(engine LIKE '%View', 'view', 'table'),
                   total_rows, total_bytes, comment
            FROM system.tables
            WHERE database NOT IN ('system', 'INFORMATION_SCHEMA', 'information_schema')
            {kinds}
            ORDER BY total_bytes DESC
        """

    def describe_sql(self) -> str:
        return f"""
            SELECT name, lower(type),
                   type LIKE 'Nullable(%',
                   position, comment,
                   NULL, NULL
            FROM system.columns
            WHERE database = {self.placeholder(1)} AND table = {self.placeholder(2)}
            ORDER BY position
        """

    def estimate_rows_sql(self) -> str | None:
        """From the table's own recorded total, which costs nothing."""
        return f"""
            SELECT total_rows FROM system.tables
            WHERE database = {self.placeholder(1)} AND name = {self.placeholder(2)}
        """

    def select_sql(self, path: tuple[str, ...], plan: SamplePlan, limit: int, offset: int) -> str:  # noqa: ARG002
        """The plan is deliberately ignored for sampling.

        `has_native_sampling` is False, so the base connector already knows this
        read is an ordinary one and reports the result as approximate. Emitting
        `SAMPLE` here anyway would be a syntax error on any table without a
        sampling key — which is most of them.
        """
        return f"SELECT * FROM {self.qualify(path)} LIMIT {limit} OFFSET {offset}"

    def session_setup_sql(self, *, statement_timeout_ms: int) -> tuple[str, ...]:
        """Bounded by time and by memory.

        `max_execution_time` alone is not enough on a column store: a query that
        finishes inside its time limit can still take the server down by
        allocating, and `max_memory_usage` is the ceiling that stops a
        discovery scan becoming everybody's outage.
        """
        seconds = max(1, statement_timeout_ms // 1000)
        return (
            f"SET max_execution_time = {seconds}",
            "SET max_memory_usage = 4000000000",
            "SET readonly = 1",
        )


class ClickHouseConnector(SqlConnector):
    """A ClickHouse cluster, read over its HTTP interface."""

    plugin_key = "clickhouse"
    dialect = ClickHouseDialect()
    credential_field = "password"

    @classmethod
    def manifest(cls) -> PluginManifest:
        return cls.describe_manifest(
            key="clickhouse",
            display_name="ClickHouse",
            capabilities=CAPABILITIES.to_capabilities(),
            description=(
                "A ClickHouse cluster. Row counts come from the table's own recorded "
                "totals rather than a scan, and the session is capped by time and by "
                "memory — on a column store a query can finish in time and still take "
                "the server down by allocating."
            ),
            verification=Verification.VERIFIED,
        )

    def __init__(self, config: dict[str, Any], **kwargs: Any) -> None:
        super().__init__(config, **kwargs)
        self._host = str(self.config.get("host", "localhost"))
        self._port = int(self.config.get("port", 8123))
        self._database = str(self.config.get("database", "default"))
        self._user = str(self.config.get("user", "default"))
        self._password = str(self.config.get("password", ""))
        self._secure = bool(self.config.get("secure", False))
        self._client: Any = None
        self._stream_columns: tuple[str, ...] = ()
        #: The driver is synchronous. One thread per connector rather than the
        #: shared pool, for the same reason every other synchronous source here
        #: gets one.
        self._worker: DedicatedThread | None = None

    async def open(self) -> None:
        driver = self._driver()
        self._worker = DedicatedThread(name="clickhouse")
        try:
            self._client = await self._call(
                driver.get_client,
                host=self._host,
                port=self._port,
                username=self._user,
                password=self._password,
                database=self._database,
                secure=self._secure,
            )
        except Exception as exc:
            # The driver's own exception type means nothing to a caller and
            # carries no remedy. Translating it here keeps `health()` able to
            # report a state rather than propagating something nobody expected.
            await self.close()
            raise UnreachableError(
                f"could not reach ClickHouse at {self._host}:{self._port}",
                remedy=(
                    "Check the host and port, and that the HTTP interface is the "
                    "one exposed — 8123 plain, 8443 with TLS. The native protocol "
                    "port (9000) will not answer this."
                ),
                context={"host": self._host, "port": str(self._port)},
            ) from exc

    async def close(self) -> None:
        if self._client is not None:
            client, self._client = self._client, None
            await self._call(client.close)
        if self._worker is not None:
            worker, self._worker = self._worker, None
            await worker.close()

    async def _call(self, function: Any, *arguments: Any, **keywords: Any) -> Any:
        if self._worker is None:
            raise ConnectorError(
                "the ClickHouse connector was used before it was opened",
                code="CONNECT.NOT_OPEN",
                remedy="Use the connector as an async context manager, or call open() first.",
            )
        return await self._worker.call(function, *arguments, **keywords)

    async def _fetch(self, sql: str, *params: Any) -> list[tuple[Any, ...]]:
        statement, arguments = _bind(sql, params)

        def run() -> list[tuple[Any, ...]]:
            result = self._require().query(statement, parameters=arguments or None)
            return [tuple(row) for row in result.result_rows]

        rows: list[tuple[Any, ...]] = await self._call(run)
        return rows

    async def _stream(self, sql: str, batch_rows: int) -> AsyncIterator[list[tuple[Any, ...]]]:
        """Paged with LIMIT/OFFSET rather than a server cursor.

        ClickHouse's HTTP interface streams, but the driver materialises a
        result; paging keeps the ceiling on what one batch can cost in memory,
        which is the property the budget in the base class depends on.
        """

        def run(offset: int) -> tuple[list[tuple[Any, ...]], tuple[str, ...]]:
            result = self._require().query(f"{sql} LIMIT {batch_rows} OFFSET {offset}")
            return [tuple(row) for row in result.result_rows], tuple(result.column_names)

        offset = 0
        while True:
            rows, names = await self._call(run, offset)
            if names:
                self._stream_columns = names
            if not rows:
                return
            yield rows
            if len(rows) < batch_rows:
                return
            offset += batch_rows

    def _column_names(self) -> tuple[str, ...]:
        return self._stream_columns

    def _require(self) -> Any:
        if self._client is None:
            raise ConnectorError(
                "the ClickHouse connector was used before it was opened",
                code="CONNECT.NOT_OPEN",
                remedy="Use the connector as an async context manager, or call open() first.",
            )
        return self._client

    @staticmethod
    def _driver() -> Any:
        try:
            import clickhouse_connect
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise ConnectorError(
                "the ClickHouse driver is not installed",
                code="CONNECT.DRIVER_MISSING",
                remedy='Install Prama\'s clickhouse extra: pip install "prama[clickhouse]"',
            ) from exc
        return clickhouse_connect


def _bind(sql: str, params: tuple[Any, ...]) -> tuple[str, dict[str, Any]]:
    """Turn `?` placeholders into ClickHouse's named parameters.

    The dialect writes `?` because that is what most drivers want; this driver
    wants `{name:Type}`. Converting here rather than giving ClickHouse its own
    placeholder style keeps every dialect's SQL written one way — and the
    alternative, interpolating the values into the string, is how a catalogue
    name a customer controls becomes a query.
    """
    if not params:
        return sql, {}
    arguments: dict[str, Any] = {}
    out = []
    index = 0
    for character in sql:
        if character == "?":
            name = f"p{index}"
            arguments[name] = params[index]
            out.append(f"{{{name}:String}}")
            index += 1
        else:
            out.append(character)
    return "".join(out), arguments
