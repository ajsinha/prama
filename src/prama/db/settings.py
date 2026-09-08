"""Database settings, bound once from configuration.

Nothing downstream reads raw configuration keys: a component receives a typed
settings object whose values were validated at startup. A typo in a key name is
therefore a boot failure naming the key, not a 3am ``KeyError`` inside a
transaction.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from prama.core.config import Configuration
from prama.core.errors import ConfigError


@dataclasses.dataclass(frozen=True, slots=True)
class PoolSettings:
    """Connection-pool shape. Applies to PostgreSQL; SQLite ignores most of it."""

    size: int = 10
    max_overflow: int = 20
    timeout_seconds: float = 30.0
    recycle_seconds: float = 1800.0
    pre_ping: bool = True

    def validate(self) -> None:
        if self.size <= 0:
            raise ConfigError(
                "database.pool.size must be positive",
                code="CONFIG.POOL_INVALID",
                remedy="Set database.pool.size to at least 1.",
                context={"size": self.size},
            )


@dataclasses.dataclass(frozen=True, slots=True)
class SqliteSettings:
    """SQLite specifics.

    WAL is the default because it lets readers proceed during a write, which is
    the difference between a usable single-node deployment and one that stalls
    whenever the scheduler commits.
    """

    path: str = "data/prama.db"
    journal_mode: str = "WAL"
    synchronous: str = "NORMAL"
    busy_timeout_seconds: float = 5.0
    foreign_keys: bool = True

    @property
    def is_memory(self) -> bool:
        return self.path in (":memory:", "") or self.path.startswith("file::memory:")

    def resolved_path(self) -> Path | None:
        return None if self.is_memory else Path(self.path).expanduser()


@dataclasses.dataclass(frozen=True, slots=True)
class PostgresSettings:
    """PostgreSQL connection parameters."""

    host: str = "localhost"
    port: int = 5432
    database: str = "prama"
    user: str = "prama"
    password: str = ""
    sslmode: str = "prefer"
    application_name: str = "prama"
    db_schema: str = "public"
    statement_timeout_seconds: float = 60.0


@dataclasses.dataclass(frozen=True, slots=True)
class DbSettings:
    """The complete database configuration.

    ``dialect`` is the single switch that chooses an engine. No code outside
    ``prama.db.dialects`` branches on it.
    """

    dialect: str = "sqlite"
    sqlite: SqliteSettings = dataclasses.field(default_factory=SqliteSettings)
    postgres: PostgresSettings = dataclasses.field(default_factory=PostgresSettings)
    pool: PoolSettings = dataclasses.field(default_factory=PoolSettings)
    schema_dir: str = "schema"
    verify_on_start: bool = True
    echo: bool = False

    SUPPORTED: tuple[str, ...] = ("sqlite", "postgres")

    def validate(self) -> None:
        if self.dialect not in self.SUPPORTED:
            raise ConfigError(
                f"unsupported database.dialect: {self.dialect!r}",
                code="CONFIG.DIALECT_UNSUPPORTED",
                remedy=f"Set database.dialect to one of: {', '.join(self.SUPPORTED)}.",
                context={"dialect": self.dialect, "supported": list(self.SUPPORTED)},
            )
        self.pool.validate()

    @property
    def schema_file(self) -> Path:
        """The authoritative schema file for the selected dialect."""
        return Path(self.schema_dir) / f"{self.dialect}.sql"

    @classmethod
    def from_config(cls, config: Configuration) -> DbSettings:
        section = config.section("database")
        settings = cls(
            dialect=section.get_str("dialect", "sqlite").lower(),
            sqlite=SqliteSettings(
                path=section.get_str("sqlite.path", "data/prama.db"),
                journal_mode=section.get_str("sqlite.journal_mode", "WAL"),
                synchronous=section.get_str("sqlite.synchronous", "NORMAL"),
                busy_timeout_seconds=section.get_duration("sqlite.busy_timeout", "5s"),
                foreign_keys=section.get_bool("sqlite.foreign_keys", True),
            ),
            postgres=PostgresSettings(
                host=section.get_str("postgres.host", "localhost"),
                port=section.get_int("postgres.port", 5432),
                database=section.get_str("postgres.database", "prama"),
                user=section.get_str("postgres.user", "prama"),
                password=section.get_str("postgres.password", ""),
                sslmode=section.get_str("postgres.sslmode", "prefer"),
                application_name=section.get_str("postgres.application_name", "prama"),
                db_schema=section.get_str("postgres.schema", "public"),
                statement_timeout_seconds=section.get_duration("postgres.statement_timeout", "60s"),
            ),
            pool=PoolSettings(
                size=section.get_int("pool.size", 10),
                max_overflow=section.get_int("pool.max_overflow", 20),
                timeout_seconds=section.get_duration("pool.timeout", "30s"),
                recycle_seconds=section.get_duration("pool.recycle", "30m"),
                pre_ping=section.get_bool("pool.pre_ping", True),
            ),
            schema_dir=section.get_str("schema_dir", "schema"),
            verify_on_start=section.get_bool("verify_on_start", True),
            echo=section.get_bool("echo", False),
        )
        settings.validate()
        return settings
