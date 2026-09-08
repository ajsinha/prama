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
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import URL
from sqlalchemy.pool import NullPool, QueuePool, StaticPool

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
            # asyncpg takes server settings rather than libpq keywords, and it
            # does not understand sslmode; the driver negotiates TLS itself.
            kwargs["connect_args"] = {
                "server_settings": {
                    "application_name": p.application_name,
                    "statement_timeout": str(int(p.statement_timeout_seconds * 1000)),
                    "search_path": p.db_schema,
                }
            }
            kwargs["poolclass"] = QueuePool
        else:
            kwargs["connect_args"] = {
                "application_name": p.application_name,
                "sslmode": p.sslmode,
                "options": (
                    f"-c statement_timeout={int(p.statement_timeout_seconds * 1000)} "
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
