"""The dialect abstraction — the ONLY place that branches on the database.

``database.dialect: sqlite | postgres`` switches every behaviour that genuinely
differs between the two engines: URL construction, pooling, connect-time
session setup, introspection, upsert syntax, and the availability of advisory
locks. Everything above this module is written once.

Adding a third engine means adding one class here and one schema file. It does
not mean touching a repository, a service, or a test.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Final

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import URL
from sqlalchemy.pool import AsyncAdaptedQueuePool, NullPool, QueuePool, StaticPool

from prama.core.errors import ConfigError, DatabaseError
from prama.db.settings import DbSettings


class Dialect(ABC):
    """Everything that differs between supported databases."""

    name: str = ""

    def __init__(self, settings: DbSettings) -> None:
        self.settings = settings

    # -- connection --------------------------------------------------------

    @abstractmethod
    def sync_url(self) -> URL:
        """URL for the synchronous engine (DDL, bootstrap, verification, CLI)."""

    @abstractmethod
    def async_url(self) -> URL:
        """URL for the asynchronous engine (all application data access)."""

    @abstractmethod
    def engine_kwargs(self, *, is_async: bool) -> dict[str, Any]:
        """Pool class and parameters for ``create_engine``."""

    @abstractmethod
    def on_connect(self, dbapi_connection: Any) -> None:
        """Per-connection setup: pragmas, timeouts, search path."""

    def prepare_filesystem(self) -> None:
        """Create any directory the engine needs.

        Optional: a networked engine needs nothing, and the default no-op is
        correct for it rather than a gap.
        """
        return

    @property
    def driver_hint(self) -> str:
        """What to install if the driver is missing.

        Lives here so that no caller has to ask *which* dialect it is holding —
        the single rule that keeps engine choice to one module.
        """
        return ""

    # -- capabilities ------------------------------------------------------

    @property
    def supports_advisory_locks(self) -> bool:
        return False

    @property
    def supports_json_indexing(self) -> bool:
        """Whether JSON *columns* can carry an expression index.

        Prama stores JSON as TEXT on both engines (schema/*.sql explains why),
        so this never changes a column type. It only decides whether an
        expression index over a JSON path is available as an optimisation.
        """
        return False

    @property
    def supports_returning(self) -> bool:
        return True

    # -- introspection -----------------------------------------------------

    @abstractmethod
    def list_tables(self, engine: Engine) -> list[str]: ...

    @abstractmethod
    def list_columns(self, engine: Engine, table: str) -> dict[str, dict[str, Any]]:
        """``{column_name: {"type": str, "nullable": bool}}``."""

    @abstractmethod
    def list_indexes(self, engine: Engine, table: str) -> list[str]: ...

    # -- SQL fragments -----------------------------------------------------

    @abstractmethod
    def upsert(self, table: str, columns: list[str], conflict: list[str]) -> str:
        """An INSERT ... ON CONFLICT DO UPDATE statement for *table*."""

    def describe(self) -> str:
        return f"{self.name}"


def _refuse_double_quoted_strings(dbapi_connection: Any) -> None:
    """Turn off SQLite's double-quoted-string fallback.

    SQLite accepts a double-quoted identifier it cannot resolve as a **string
    literal**, for MySQL compatibility. So a control on a column that does not
    exist does not fail — `"no_such_column" IS NOT NULL` is the constant string
    `'no_such_column'`, which is not null on every row, and the control reports
    **pass over the whole table** (QA finding Q-08). The identical control is an
    `error` on DuckDB: two engines, opposite verdicts, and the wrong one is
    silent.

    A typo in a column name is the commonest way a control stops checking
    anything, and this made it the least visible. With the flag off SQLite says
    `no such column: "no_such" - should this be a string literal in
    single-quotes?`, which is both correct and a better error than Prama would
    have written.

    Best-effort here, and only here: this is Prama's own database, reached
    in part through an async driver whose wrapped connection has no `setconfig`, and no
    control runs against it. Every SQLite connection a control runs on is
    strict without exception (`prama_kernel.strict_sqlite`), which is why
    Python 3.12 is the floor.
    """
    import sqlite3

    setconfig = getattr(dbapi_connection, "setconfig", None)
    flag = getattr(sqlite3, "SQLITE_DBCONFIG_DQS_DML", None)
    if setconfig is None or flag is None:  # pragma: no cover - older interpreters
        return
    try:
        setconfig(flag, False)
        ddl = getattr(sqlite3, "SQLITE_DBCONFIG_DQS_DDL", None)
        if ddl is not None:
            setconfig(ddl, False)
    except Exception:  # pragma: no cover - a driver that does not support it
        return


class SqliteDialect(Dialect):
    """SQLite: development, single-node deployments, tests, and the air-gapped
    all-in-one image. Not a scale-out database, and the platform never pretends
    otherwise — but it is a complete one, and being able to run the whole
    product from a single file is worth a great deal in evaluation and support.
    """

    name = "sqlite"

    @property
    def driver_hint(self) -> str:
        return "SQLite needs no driver beyond the standard library and aiosqlite."

    def sync_url(self) -> URL:
        return URL.create("sqlite+pysqlite", database=self._database())

    def async_url(self) -> URL:
        return URL.create("sqlite+aiosqlite", database=self._database())

    def _database(self) -> str:
        s = self.settings.sqlite
        return ":memory:" if s.is_memory else str(s.resolved_path())

    def prepare_filesystem(self) -> None:
        path = self.settings.sqlite.resolved_path()
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)

    def engine_kwargs(self, *, is_async: bool) -> dict[str, Any]:
        s = self.settings.sqlite
        kwargs: dict[str, Any] = {
            "echo": self.settings.echo,
            "connect_args": {"timeout": s.busy_timeout_seconds},
        }
        if s.is_memory:
            # A shared StaticPool keeps every session on the one connection, so
            # an in-memory database is not silently re-created per checkout —
            # the classic reason an in-memory test "loses" its schema.
            kwargs["poolclass"] = StaticPool
            kwargs["connect_args"]["check_same_thread"] = False
        else:
            kwargs["poolclass"] = NullPool if is_async else QueuePool
            if not is_async:
                kwargs["pool_size"] = self.settings.pool.size
                kwargs["max_overflow"] = self.settings.pool.max_overflow
                kwargs["pool_pre_ping"] = self.settings.pool.pre_ping
        return kwargs

    def on_connect(self, dbapi_connection: Any) -> None:
        s = self.settings.sqlite
        _refuse_double_quoted_strings(dbapi_connection)
        cursor = dbapi_connection.cursor()
        try:
            if s.foreign_keys:
                cursor.execute("PRAGMA foreign_keys = ON")
            if not s.is_memory:
                cursor.execute(f"PRAGMA journal_mode = {s.journal_mode}")
            cursor.execute(f"PRAGMA synchronous = {s.synchronous}")
            cursor.execute(f"PRAGMA busy_timeout = {int(s.busy_timeout_seconds * 1000)}")
        finally:
            cursor.close()

    def list_tables(self, engine: Engine) -> list[str]:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                )
            )
            return [row[0] for row in rows]

    def list_columns(self, engine: Engine, table: str) -> dict[str, dict[str, Any]]:
        with engine.connect() as conn:
            rows = conn.execute(text(f'PRAGMA table_info("{table}")'))
            return {
                row[1]: {"type": str(row[2]).upper(), "nullable": not bool(row[3])} for row in rows
            }

    def list_indexes(self, engine: Engine, table: str) -> list[str]:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=:t"),
                {"t": table},
            )
            return sorted(r[0] for r in rows if r[0] and not r[0].startswith("sqlite_"))

    def upsert(self, table: str, columns: list[str], conflict: list[str]) -> str:
        assignments = ", ".join(f"{c} = excluded.{c}" for c in columns if c not in conflict)
        placeholders = ", ".join(f":{c}" for c in columns)
        return (
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON CONFLICT ({', '.join(conflict)}) DO UPDATE SET {assignments}"
        )


#: libpq `sslmode` → what asyncpg needs to mean the same thing. `disable`,
#: `allow` and `prefer` are asyncpg's own default behaviour, so they map to
#: None and nothing is passed; the three that *require* TLS are the ones that
#: have to be stated, because asyncpg's default will connect without it.
_ASYNCPG_SSL: Final[dict[str, str]] = {
    "require": "require",
    "verify-ca": "verify-ca",
    "verify-full": "verify-full",
}


def _asyncpg_ssl(sslmode: str) -> str | None:
    """What to pass asyncpg as ``ssl`` for a libpq ``sslmode``.

    Returns None where asyncpg's default already matches, so the argument is
    omitted rather than set to something meaning "whatever you like".
    """
    return _ASYNCPG_SSL.get(sslmode.strip().lower())


def _statement_timeout_ms(seconds: float) -> int:
    """A PostgreSQL ``statement_timeout``, in whole milliseconds.

    Zero means *unlimited* in PostgreSQL, so it is the one value a rounding
    error must never produce. `int(0.0005 * 1000)` is `0`, which turned
    "half a millisecond" into "no limit at all" — the opposite of what was
    asked for, and in the direction that hides a runaway query rather than
    stopping it (QA finding DB-074).

    Anything above zero therefore floors at one millisecond. A caller who
    genuinely wants no limit configures zero, and gets it.
    """
    if seconds <= 0:
        return 0
    return max(1, int(seconds * 1000))


class PostgresDialect(Dialect):
    """PostgreSQL: the production database. Scale-out, JSONB, advisory locks."""

    name = "postgres"

    @property
    def driver_hint(self) -> str:
        return "Install the driver: pip install 'prama[postgres]'."

    def sync_url(self) -> URL:
        return self._url("postgresql+psycopg")

    def async_url(self) -> URL:
        return self._url("postgresql+asyncpg")

    def _url(self, driver: str) -> URL:
        p = self.settings.postgres
        return URL.create(
            driver,
            username=p.user,
            password=p.password or None,
            host=p.host,
            port=p.port,
            database=p.database,
        )

    def engine_kwargs(self, *, is_async: bool) -> dict[str, Any]:
        pool = self.settings.pool
        p = self.settings.postgres
        kwargs: dict[str, Any] = {
            "echo": self.settings.echo,
            "poolclass": QueuePool,
            "pool_size": pool.size,
            "max_overflow": pool.max_overflow,
            "pool_timeout": pool.timeout_seconds,
            "pool_recycle": int(pool.recycle_seconds),
            "pool_pre_ping": pool.pre_ping,
        }
        if is_async:
            # asyncpg takes server settings rather than libpq keywords, so the
            # libpq spelling of each option has to be translated rather than
            # passed through.
            connect: dict[str, Any] = {
                "server_settings": {
                    "application_name": p.application_name,
                    "statement_timeout": str(_statement_timeout_ms(p.statement_timeout_seconds)),
                    "search_path": p.db_schema,
                }
            }
            # sslmode is the one that was simply dropped. The comment here
            # used to say asyncpg "does not understand sslmode; the driver
            # negotiates TLS itself", which is true of the keyword and not of
            # the requirement: `sslmode: require` asks for a connection that
            # fails rather than falls back to plaintext, and asyncpg's default
            # `ssl=None` will happily connect without TLS. So an operator who
            # asked for TLS got it on the synchronous path and not on the
            # asynchronous one, with nothing said either way (QA finding
            # DB-072).
            ssl = _asyncpg_ssl(p.sslmode)
            if ssl is not None:
                connect["ssl"] = ssl
            kwargs["connect_args"] = connect
            # AsyncAdaptedQueuePool, not QueuePool. SQLAlchemy 2.x refuses the
            # synchronous pool on an asyncio engine outright — "Pool class QueuePool cannot
            # be used with asyncio engine" — so this line made the asynchronous
            # PostgreSQL engine impossible to construct at all (QA finding
            # DB-070, and DB-072, DB-148 and DB-279 behind it, plus the
            # database-backed lease provider).
            #
            # It was also redundant: `poolclass` was already QueuePool from the
            # shared kwargs above, so this re-stated the wrong answer in the
            # one branch that needed a different one. The SQLite dialect gets
            # it right a few lines up — `NullPool if is_async else QueuePool` —
            # so the pattern was known and not applied here.
            #
            # Nothing caught it: `tests/conftest.py` defines `postgres_config`
            # and nothing uses it, and no test constructs an async engine.
            # AsyncAdaptedQueuePool rather than NullPool, which is what SQLite
            # uses. NullPool would construct, and would also open a fresh
            # connection per request against a server where that costs a
            # round trip and a backend process — a correctness fix that
            # quietly became a throughput defect. It also rejects pool_size,
            # max_overflow and pool_timeout, so the configured pool settings
            # would have had to be dropped to make it work, which is the
            # clearest possible sign it was the wrong pool.
            kwargs["poolclass"] = AsyncAdaptedQueuePool
        else:
            kwargs["connect_args"] = {
                "application_name": p.application_name,
                "sslmode": p.sslmode,
                "options": (
                    f"-c statement_timeout={_statement_timeout_ms(p.statement_timeout_seconds)} "
                    f"-c search_path={p.db_schema}"
                ),
            }
        return kwargs

    def on_connect(self, dbapi_connection: Any) -> None:
        """No-op: everything is set through connect_args, which applies to
        pooled connections without a per-checkout round trip."""

    @property
    def supports_advisory_locks(self) -> bool:
        return True

    @property
    def supports_json_indexing(self) -> bool:
        return True

    def list_tables(self, engine: Engine) -> list[str]:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = :s AND table_type = 'BASE TABLE' "
                    "ORDER BY table_name"
                ),
                {"s": self.settings.postgres.db_schema},
            )
            return [row[0] for row in rows]

    def list_columns(self, engine: Engine, table: str) -> dict[str, dict[str, Any]]:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT column_name, data_type, is_nullable "
                    "FROM information_schema.columns "
                    "WHERE table_schema = :s AND table_name = :t"
                ),
                {"s": self.settings.postgres.db_schema, "t": table},
            )
            return {
                row[0]: {"type": str(row[1]).upper(), "nullable": row[2] == "YES"} for row in rows
            }

    def list_indexes(self, engine: Engine, table: str) -> list[str]:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT indexname FROM pg_indexes WHERE schemaname=:s AND tablename=:t"),
                {"s": self.settings.postgres.db_schema, "t": table},
            )
            return sorted(r[0] for r in rows)

    def upsert(self, table: str, columns: list[str], conflict: list[str]) -> str:
        assignments = ", ".join(f"{c} = EXCLUDED.{c}" for c in columns if c not in conflict)
        placeholders = ", ".join(f":{c}" for c in columns)
        return (
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON CONFLICT ({', '.join(conflict)}) DO UPDATE SET {assignments}"
        )


_DIALECTS: dict[str, type[Dialect]] = {
    SqliteDialect.name: SqliteDialect,
    PostgresDialect.name: PostgresDialect,
}


def dialect_for(settings: DbSettings) -> Dialect:
    """Construct the dialect named by configuration."""
    try:
        return _DIALECTS[settings.dialect](settings)
    except KeyError:
        raise ConfigError(
            f"unsupported database.dialect: {settings.dialect!r}",
            code="CONFIG.DIALECT_UNSUPPORTED",
            remedy=f"Set database.dialect to one of: {', '.join(sorted(_DIALECTS))}.",
            context={"dialect": settings.dialect},
        ) from None


def schema_file_for(settings: DbSettings) -> Path:
    """The authoritative schema file, checked to exist.

    There are no migrations: this file *is* the schema. Its absence is a
    packaging failure, not a condition to work around.
    """
    path = settings.schema_file
    if not path.is_file():
        raise DatabaseError(
            f"authoritative schema file not found: {path}",
            code="DB.SCHEMA_FILE_MISSING",
            remedy=(
                f"Prama has no migrations; {path} is the authority for the "
                f"{settings.dialect} dialect. Restore it, or set database.schema_dir."
            ),
            context={"path": str(path), "dialect": settings.dialect},
        )
    return path
