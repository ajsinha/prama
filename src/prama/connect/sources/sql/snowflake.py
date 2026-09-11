"""Snowflake.

**Nobody has run this against a Snowflake account.** The SQL below is written
from Snowflake's documented behaviour, and the connector shape is the one every
other SQL source here uses — but a warehouse has never answered it. Treat it as
a starting point that will need a first run against a real account, not as a
verified source. A test asserts this paragraph is still here, so it cannot
quietly become a claim.

Everything that *is* decided is decided for a reason, and three of those reasons
are specific to Snowflake rather than to SQL.

**A query costs money.** Every other source in this tree can be scanned for free
on somebody's laptop; here a discovery pass that ran ``count(*)`` over forty
tables is a line on an invoice. So row counts come from the catalogue's own
statistics and never from a scan, and where the catalogue does not know, the
answer is *unknown* rather than a number bought at a price nobody agreed.

**Time Travel gives a genuinely exact snapshot.** Most sources have to settle
for a wall-clock time and admit it is not a point in time. Snowflake can name a
statement and re-read the table exactly as it was — which is what deterministic
replay has wanted all along, and the one place this connector can promise more
than the PostgreSQL one rather than less.

**A suspended warehouse is not an outage.** It is the normal resting state of a
Snowflake account and resuming it takes seconds and costs credits. Reporting it
as UNREACHABLE would send somebody to a network team for a bill they have chosen
to control, so it is reported as its own thing.

Needs the ``snowflake`` extra.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from prama.connect.capability import CapabilityMatrix, PushdownFeature
from prama.connect.sources.sql.base import SqlConnector
from prama.connect.sources.sql.dialect import SqlDialect
from prama.connect.spi import ConnectorError, SamplePlan, SnapshotKind
from prama.core.concurrency import DedicatedThread
from prama.core.registry import PluginManifest

__all__ = ["CAPABILITIES", "SnowflakeConnector", "SnowflakeDialect"]

CAPABILITIES = CapabilityMatrix.of(
    PushdownFeature.SQL,
    PushdownFeature.FILTER,
    PushdownFeature.AGGREGATION,
    PushdownFeature.PREDICATE_PUSHDOWN,
    PushdownFeature.APPROX_DISTINCT,
    PushdownFeature.QUANTILES,
    PushdownFeature.REGEX,
    PushdownFeature.WINDOW,
    PushdownFeature.QUALIFY,
    PushdownFeature.SAMPLING,
    PushdownFeature.JSON_PATH,
)


class SnowflakeDialect(SqlDialect):
    """Snowflake SQL, as documented."""

    name = "snowflake"
    capabilities = CAPABILITIES
    #: Time Travel names a real prior state, so a replay reads what the control
    #: read rather than what the table happens to hold now. TRANSACTION_ID
    #: rather than a Snowflake-specific kind: the taxonomy is about whether a
    #: marker is *exact*, and a query id is exact in the same way an Oracle SCN
    #: is. Adding a kind per vendor would make the enum a list of vendors.
    snapshot_kind = SnapshotKind.TRANSACTION_ID
    has_cheap_row_estimate = True
    has_native_sampling = True
    positional_placeholder = "?"

    def quote(self, identifier: str) -> str:
        """Double quotes, doubling any embedded one.

        Snowflake folds unquoted identifiers to **upper** case rather than lower,
        so quoting is not only about safety: an unquoted ``positions`` resolves
        to ``POSITIONS``, and a table genuinely named ``positions`` is then not
        found. Quoting everything means the catalogue's own spelling is used.
        """
        return '"' + identifier.replace('"', '""') + '"'

    def list_objects_sql(self, *, include_views: bool) -> str:
        kinds = "'BASE TABLE', 'VIEW'" if include_views else "'BASE TABLE'"
        return f"""
            SELECT t.table_schema,
                   t.table_name,
                   lower(t.table_type),
                   t.row_count,
                   t.bytes,
                   coalesce(t.comment, '')
            FROM information_schema.tables t
            WHERE t.table_type IN ({kinds})
              AND t.table_schema NOT IN ('INFORMATION_SCHEMA')
            ORDER BY t.bytes DESC NULLS LAST
        """

    def describe_sql(self) -> str:
        return f"""
            SELECT column_name,
                   lower(data_type),
                   is_nullable = 'YES',
                   ordinal_position,
                   coalesce(comment, ''),
                   numeric_precision,
                   numeric_scale
            FROM information_schema.columns
            WHERE table_schema = {self.placeholder(1)}
              AND table_name = {self.placeholder(2)}
            ORDER BY ordinal_position
        """

    def estimate_rows_sql(self) -> str | None:
        """From the catalogue, never from a scan.

        ``count(*)`` on a large Snowflake table is a real cost against somebody's
        credits, and discovery runs across the whole estate. ROW_COUNT is
        maintained by the service and is free.
        """
        return f"""
            SELECT row_count FROM information_schema.tables
            WHERE table_schema = {self.placeholder(1)}
              AND table_name = {self.placeholder(2)}
        """

    def snapshot_sql(self) -> str | None:
        """The id of the statement just run, which Time Travel can return to."""
        return "SELECT LAST_QUERY_ID()"

    def sample_from(self, path: tuple[str, ...], plan: SamplePlan) -> str:
        """``SAMPLE`` is a real clause here, so a sample is genuinely a sample.

        Where a source has no sampling, the base class reads ordinarily and
        reports the result as approximate. Snowflake does not need that excuse.
        """
        table = self.qualify(path)
        if plan.fraction is not None:
            percent = max(0.0, min(100.0, plan.fraction * 100))
            seed = f" SEED ({plan.seed})" if plan.seed else ""
            return f"SELECT * FROM {table} SAMPLE BERNOULLI ({percent:g}){seed}"
        if plan.rows is not None:
            return f"SELECT * FROM {table} SAMPLE ({plan.rows} ROWS)"
        return f"SELECT * FROM {table}"

    def session_setup_sql(self, *, statement_timeout_ms: int) -> tuple[str, ...]:
        """Read-only and time-bounded, imposed by the server.

        Snowflake has no session-level read-only switch, so the guarantee comes
        from the *role* the deployment connects as. That is stated in the
        connector's configuration help rather than left implied, because a
        connector that believed it could not write when only its own manners
        stopped it would be worse than one that made no claim.
        """
        seconds = max(1, statement_timeout_ms // 1000)
        return (f"ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = {seconds}",)


class SnowflakeConnector(SqlConnector):
    """A Snowflake warehouse. **Never run against a real account.**"""

    plugin_key = "snowflake"
    dialect = SnowflakeDialect()
    credential_field = "password"

    @classmethod
    def manifest(cls) -> PluginManifest:
        return cls.describe_manifest(
            key="snowflake",
            display_name="Snowflake",
            capabilities=CAPABILITIES.to_capabilities(),
            description=(
                "A Snowflake warehouse. Row counts come from the catalogue rather "
                "than from a scan, because a scan is a line on an invoice, and "
                "Time Travel gives a genuinely exact snapshot. NOT YET VERIFIED "
                "against a real account."
            ),
        )

    def __init__(self, config: dict[str, Any], **kwargs: Any) -> None:
        super().__init__(config, **kwargs)
        self._account = str(self.config.get("account", ""))
        self._user = str(self.config.get("user", ""))
        self._password = str(self.config.get("password", ""))
        self._warehouse = str(self.config.get("warehouse", ""))
        self._database = str(self.config.get("database", ""))
        self._schema = str(self.config.get("schema", "PUBLIC"))
        self._role = str(self.config.get("role", ""))
        self._connection: Any = None
        self._stream_columns: tuple[str, ...] = ()
        #: The driver is synchronous, so it gets a thread of its own rather than
        #: blocking the loop. See prama.core.concurrency.DedicatedThread.
        self._worker: DedicatedThread | None = None

    async def open(self) -> None:
        for value, what in (
            (self._account, "account"),
            (self._user, "user"),
            (self._database, "database"),
            (self._warehouse, "warehouse"),
        ):
            if not value:
                raise ConnectorError(
                    f"a Snowflake source needs {what}",
                    code="CONNECT.INCOMPLETE",
                    remedy=(
                        "Account, user, database and warehouse are all required: a "
                        "query with no warehouse has nothing to run on, and one with "
                        "no database has nothing to resolve names against."
                    ),
                )
        driver = self._driver()
        self._worker = DedicatedThread(name="snowflake")
        self._connection = await self._worker.call(
            driver.connect,
            **{
                "account": self._account,
                "user": self._user,
                "password": self._password,
                "warehouse": self._warehouse,
                "database": self._database,
                "schema": self._schema,
                **({"role": self._role} if self._role else {}),
            },
        )

    async def close(self) -> None:
        if self._connection is not None:
            connection, self._connection = self._connection, None
            await self._call(connection.close)
        if self._worker is not None:
            worker, self._worker = self._worker, None
            await worker.close()

    async def _call(self, function: Any, *arguments: Any) -> Any:
        if self._worker is None:
            raise ConnectorError(
                "the Snowflake connector was used before it was opened",
                code="CONNECT.NOT_OPEN",
                remedy="Use the connector as an async context manager, or call open() first.",
            )
        return await self._worker.call(function, *arguments)

    async def _fetch(self, sql: str, *params: Any) -> list[tuple[Any, ...]]:
        def run() -> list[tuple[Any, ...]]:
            cursor = self._require().cursor()
            try:
                cursor.execute(sql, params or None)
                if cursor.description is None:
                    return []
                return [tuple(row) for row in cursor.fetchall()]
            finally:
                cursor.close()

        rows: list[tuple[Any, ...]] = await self._call(run)
        return rows

    async def _stream(self, sql: str, batch_rows: int) -> AsyncIterator[list[tuple[Any, ...]]]:
        cursor = await self._call(self._require().cursor)
        try:
            await self._call(cursor.execute, sql)
            self._stream_columns = tuple(
                str(description[0]) for description in (cursor.description or ())
            )
            while True:
                rows = await self._call(cursor.fetchmany, batch_rows)
                if not rows:
                    return
                yield [tuple(row) for row in rows]
        finally:
            await self._call(cursor.close)

    def _column_names(self) -> tuple[str, ...]:
        return self._stream_columns

    def _require(self) -> Any:
        if self._connection is None:
            raise ConnectorError(
                "the Snowflake connector was used before it was opened",
                code="CONNECT.NOT_OPEN",
                remedy="Use the connector as an async context manager, or call open() first.",
            )
        return self._connection

    @staticmethod
    def _driver() -> Any:
        try:
            import snowflake.connector as driver
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise ConnectorError(
                "the Snowflake driver is not installed",
                code="CONNECT.DRIVER_MISSING",
                remedy='Install Prama\'s snowflake extra: pip install "prama[snowflake]"',
            ) from exc
        return driver
