"""PostgreSQL as a data source.

The database most likely to be holding the data a bank actually cares about,
and the one where the difference between a careful reader and a careless one is
most visible. Three things this connector does that a naive one does not:

* **It cannot write.** The session is opened read-only at the server, so the
  guarantee survives a bug in our own query construction.
* **It cannot pin the database.** Every statement carries a timeout, and the
  connection declares itself in ``application_name`` so a DBA looking at
  ``pg_stat_activity`` at 3am can see exactly who is asking and kill it.
* **It does not scan to answer cheap questions.** Row counts come from
  ``pg_class.reltuples`` and sizes from ``pg_total_relation_size``, so opening a
  source with ten thousand tables costs one query rather than ten thousand.

Reads use a server-side cursor inside a read-only transaction, so a table larger
than memory streams rather than arriving all at once.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Any

from prama.connect.capability import CapabilityMatrix, PushdownFeature
from prama.connect.sources.sql.base import SqlConnector
from prama.connect.sources.sql.dialect import SqlDialect
from prama.connect.spi import (
    ConnectorError,
    SamplePlan,
    SamplingStrategy,
    SnapshotKind,
)
from prama.core.registry import PluginManifest

CAPABILITIES = CapabilityMatrix.of(
    PushdownFeature.SQL,
    PushdownFeature.FILTER,
    PushdownFeature.AGGREGATION,
    PushdownFeature.PREDICATE_PUSHDOWN,
    PushdownFeature.WINDOW,
    PushdownFeature.REGEX,
    PushdownFeature.SAMPLING,
    PushdownFeature.EXACT_SNAPSHOT,
    PushdownFeature.APPROX_DISTINCT,
    PushdownFeature.QUANTILES,
    PushdownFeature.PARTITION_PRUNING,
    PushdownFeature.CROSS_OBJECT_JOIN,
    PushdownFeature.JSON_PATH,
    regex_flavour="posix",
    max_decimal_precision=1000,
    nulls_sort_first=False,
)

#: Schemas that belong to the server rather than to the business. Surfacing them
#: buries the customer's own tables in catalogue noise.
SYSTEM_SCHEMAS = ("pg_catalog", "information_schema", "pg_toast")


class PostgresDialect(SqlDialect):
    """PostgreSQL's catalogue, sampling clause and point-in-time marker."""

    name = "postgresql"
    capabilities = CAPABILITIES
    snapshot_kind = SnapshotKind.LSN
    has_cheap_row_estimate = True
    has_native_sampling = True
    positional_placeholder = "$"

    def list_objects_sql(self, *, include_views: bool) -> str:
        kinds = "('r', 'p', 'v', 'm', 'f')" if include_views else "('r', 'p', 'f')"
        excluded = ", ".join(f"'{schema}'" for schema in SYSTEM_SCHEMAS)
        return f"""
            SELECT n.nspname,
                   c.relname,
                   CASE c.relkind WHEN 'v' THEN 'view'
                                  WHEN 'm' THEN 'materialized view'
                                  WHEN 'f' THEN 'foreign table'
                                  WHEN 'p' THEN 'partitioned table'
                                  ELSE 'table' END,
                   CASE WHEN c.reltuples < 0 THEN NULL ELSE c.reltuples::bigint END,
                   pg_total_relation_size(c.oid),
                   coalesce(obj_description(c.oid, 'pg_class'), '')
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind IN {kinds}
              AND n.nspname NOT IN ({excluded})
              AND n.nspname NOT LIKE 'pg_temp%'
              AND has_table_privilege(c.oid, 'SELECT')
            ORDER BY n.nspname, c.relname
        """

    def describe_sql(self) -> str:
        # pg_attribute rather than information_schema: it carries the column
        # comment, which is often the only business description that exists
        # anywhere, and picking it up turns a migration into a head start.
        return """
            SELECT a.attname,
                   format_type(a.atttypid, a.atttypmod),
                   NOT a.attnotnull,
                   a.attnum,
                   coalesce(col_description(a.attrelid, a.attnum), ''),
                   information_schema._pg_numeric_precision(a.atttypid, a.atttypmod),
                   information_schema._pg_numeric_scale(a.atttypid, a.atttypmod)
            FROM pg_attribute a
            JOIN pg_class c ON c.oid = a.attrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = $1 AND c.relname = $2
              AND a.attnum > 0 AND NOT a.attisdropped
            ORDER BY a.attnum
        """

    def estimate_rows_sql(self) -> str:
        return """
            SELECT CASE WHEN c.reltuples < 0 THEN NULL ELSE c.reltuples::bigint END
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = $1 AND c.relname = $2
        """

    def snapshot_sql(self) -> str:
        """The WAL position: an exact, monotonic marker of database state.

        On a standby the write position does not advance, so the replay position
        is used instead — otherwise every snapshot taken against a read replica
        would be identical, and evidence would silently stop being replayable.
        """
        return (
            "SELECT CASE WHEN pg_is_in_recovery() "
            "THEN pg_last_wal_replay_lsn()::text ELSE pg_current_wal_lsn()::text END"
        )

    def sample_from(self, path: tuple[str, ...], plan: SamplePlan) -> str:
        """A real sample, taken by the server.

        ``BERNOULLI`` rather than ``SYSTEM``: system sampling picks whole pages,
        so rows that were inserted together are selected together, and any
        column correlated with insertion order — a date, a branch, a batch id —
        comes back badly skewed. Bernoulli costs a scan and is worth it, because
        a profile built on a skewed sample is worse than no profile.
        """
        table = self.qualify(path)
        fraction = plan.fraction if plan.fraction is not None else 0.01
        percent = max(0.000001, min(100.0, fraction * 100))
        repeatable = f" REPEATABLE ({plan.seed})" if plan.seed else ""
        return f"SELECT * FROM {table} TABLESAMPLE BERNOULLI ({percent:g}){repeatable}"

    def session_setup_sql(self, *, statement_timeout_ms: int) -> tuple[str, ...]:
        return (
            # Read-only at the server. Our own care about not writing is not the
            # guarantee a customer should have to rely on.
            "SET default_transaction_read_only = on",
            f"SET statement_timeout = {int(statement_timeout_ms)}",
            # Never wait behind another transaction's lock: Prama observing a
            # table must not be able to block the business using it.
            "SET lock_timeout = 2000",
            # Cheap insurance against a session left open by a crashed reader.
            "SET idle_in_transaction_session_timeout = 300000",
        )


class PostgresConnector(SqlConnector):
    """A PostgreSQL database, read over asyncpg."""

    plugin_key = "postgresql"
    dialect = PostgresDialect()

    @classmethod
    def manifest(cls) -> PluginManifest:
        return cls.describe_manifest(
            key="postgresql",
            display_name="PostgreSQL",
            capabilities=CAPABILITIES.to_capabilities(),
            description=(
                "A PostgreSQL database. The session is opened read-only at the server "
                "and every statement carries a timeout, so pointing Prama at production "
                "cannot alter it and cannot pin it."
            ),
        )

    def __init__(self, config: dict[str, Any], **kwargs: Any) -> None:
        super().__init__(config, **kwargs)
        self._dsn = str(self.config.get("dsn") or "")
        self._host = str(self.config.get("host", "localhost"))
        self._port = int(self.config.get("port", 5432))
        self._database = str(self.config.get("database", "postgres"))
        self._user = str(self.config.get("user", ""))
        self._password = str(self.config.get("password", ""))
        self._ssl_mode = str(self.config.get("ssl_mode", "prefer"))
        self._connect_timeout = float(self.config.get("connect_timeout_seconds", 10.0))
        self._application_name = str(self.config.get("application_name", "prama"))
        self._pool: Any = None
        self._stream_columns: tuple[str, ...] = ()

    # -- lifecycle ---------------------------------------------------------

    async def open(self) -> None:
        asyncpg = self._driver()
        try:
            self._pool = await asyncpg.create_pool(
                **self._connection_arguments(),
                min_size=1,
                max_size=max(1, self.policy.max_concurrency),
                command_timeout=self._statement_timeout_ms / 1000,
                setup=self._prepare_session,
            )
        except Exception as exc:
            state, detail = self.classify_failure(exc)
            raise ConnectorError(
                f"could not connect to PostgreSQL at {self._host}:{self._port}: {detail}",
                code="CONNECT.UNREACHABLE",
                remedy=(
                    "Check the host, port and credentials, and that this database "
                    "accepts connections from wherever Prama runs."
                ),
                context={"host": self._host, "database": self._database, "state": state.value},
            ) from exc

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def _prepare_session(self, connection: Any) -> None:
        for statement in self.dialect.session_setup_sql(
            statement_timeout_ms=self._statement_timeout_ms
        ):
            await connection.execute(statement)

    def _connection_arguments(self) -> dict[str, Any]:
        if self._dsn:
            return {
                "dsn": self._dsn,
                "timeout": self._connect_timeout,
                "server_settings": {"application_name": self._application_name},
            }
        return {
            "host": self._host,
            "port": self._port,
            "database": self._database,
            "user": self._user or None,
            "password": self._password or None,
            "ssl": None if self._ssl_mode in ("disable", "") else self._ssl_mode,
            "timeout": self._connect_timeout,
            # Visible in pg_stat_activity. A DBA who finds an unfamiliar query
            # eating a production box at 3am should be able to see whose it is
            # without asking anyone.
            "server_settings": {"application_name": self._application_name},
        }

    # -- driver primitives -------------------------------------------------

    async def _fetch(self, sql: str, *params: Any) -> list[tuple[Any, ...]]:
        async with self._acquire() as connection:
            records = await connection.fetch(sql, *params)
        return [tuple(record.values()) for record in records]

    async def _stream(self, sql: str, batch_rows: int) -> AsyncIterator[list[tuple[Any, ...]]]:
        """Page through a server-side cursor.

        The cursor lives inside a transaction, which is why the read-only
        session setting matters: the transaction is genuinely read-only at the
        server for its whole life, not merely by convention.
        """
        async with self._acquire() as connection, connection.transaction():
            cursor = await connection.cursor(sql)
            first = True
            while True:
                records = await cursor.fetch(batch_rows)
                if not records:
                    return
                if first:
                    self._stream_columns = tuple(records[0].keys())
                    first = False
                yield [tuple(record.values()) for record in records]

    def _column_names(self) -> tuple[str, ...]:
        return self._stream_columns

    @contextlib.asynccontextmanager
    async def _acquire(self) -> AsyncIterator[Any]:
        if self._pool is None:
            await self.open()
        assert self._pool is not None
        async with self._pool.acquire() as connection:
            yield connection

    @staticmethod
    def _driver() -> Any:
        try:
            import asyncpg
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise ConnectorError(
                "the PostgreSQL driver is not installed",
                code="CONNECT.DRIVER_MISSING",
                remedy="Install Prama's postgres extra: pip install 'prama[postgres]'",
            ) from exc
        return asyncpg


def sample_plan_is_supported(plan: SamplePlan) -> bool:
    """Whether TABLESAMPLE can serve this plan.

    Stratified sampling cannot be expressed as a table sample, so asking for it
    here would silently return an unstratified one — the kind of quiet
    substitution that makes a profile untrustworthy without making it look
    wrong.
    """
    return plan.strategy is not SamplingStrategy.STRATIFIED
