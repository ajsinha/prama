"""The database package — the ONLY package in Prama that imports SQLAlchemy.

Everything above this boundary works with DAOs and a unit of work, never with a
session, a query or a dialect. ``tests/architecture/test_layering.py``
enforces that by import scanning, so the rule is a property of the build rather
than a convention people remember.

    from prama.db import Database

    database = Database.from_config(config)
    await database.start()                       # verifies the schema, or fails loudly

    async with database.unit_of_work() as uow:
        tenant = await uow.tenants.by_slug("acme-bank")

There are no migrations. ``schema/sqlite.sql`` and ``schema/postgres.sql`` are
the authority for their engines; ``initialise()`` applies one idempotently and
``verify()`` reports drift rather than repairing it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from prama.core.clock import Clock
from prama.core.concurrency.leases import LeaseProvider
from prama.core.config import Configuration
from prama.core.log import get_logger
from prama.db.dialects import Dialect, dialect_for
from prama.db.engine import EngineFactory
from prama.db.lease_provider import DatabaseLeaseProvider
from prama.db.schema import (
    BootstrapResult,
    SchemaBootstrapper,
    SchemaVerifier,
    VerificationReport,
)
from prama.db.security import ApiKeyIssuer, IssuedApiKey, PasswordHasher
from prama.db.session import SessionManager, UnitOfWork
from prama.db.settings import DbSettings

if TYPE_CHECKING:
    from sqlalchemy import Engine

_log = get_logger(__name__)

__all__ = [
    "ApiKeyIssuer",
    "BootstrapResult",
    "Database",
    "DbSettings",
    "Dialect",
    "IssuedApiKey",
    "PasswordHasher",
    "SchemaBootstrapper",
    "SchemaVerifier",
    "UnitOfWork",
    "VerificationReport",
]


class Database:
    """The façade: one object, one configuration, one database.

    Held by the application and passed to services, so nothing has to reach for
    a module-level global — which is also what allows a test to run two
    databases side by side, and what would allow one process to serve more than
    one tenant estate.
    """

    def __init__(self, settings: DbSettings, *, clock: Clock | None = None) -> None:
        settings.validate()
        self._settings = settings
        self._dialect = dialect_for(settings)
        self._engines = EngineFactory(settings, self._dialect)
        self._sessions = SessionManager(self._engines)
        self._clock = clock
        self._started = False

    # -- construction ------------------------------------------------------

    @classmethod
    def from_config(cls, config: Configuration, *, clock: Clock | None = None) -> Database:
        return cls(DbSettings.from_config(config), clock=clock)

    # -- properties --------------------------------------------------------

    @property
    def settings(self) -> DbSettings:
        return self._settings

    @property
    def dialect(self) -> Dialect:
        return self._dialect

    def sync_engine(self) -> Engine:
        """The synchronous engine. DDL, verification and the CLI only."""
        return self._engines.sync_engine()

    # -- lifecycle ---------------------------------------------------------

    def initialise(self, *, applied_by: str | None = None) -> BootstrapResult:
        """Apply the authoritative schema file. Idempotent; never alters."""
        result = SchemaBootstrapper(self._dialect).apply(
            self._engines.sync_engine(), applied_by=applied_by
        )
        _log.info("%s", result.summary())
        return result

    def verify(self) -> VerificationReport:
        """Compare the live database with the schema file. Reports; never repairs."""
        return SchemaVerifier(self._dialect).verify(self._engines.sync_engine())

    async def start(self) -> None:
        """Prepare for use, verifying the schema if configuration asks.

        Verification at start-up is on by default because a mismatched schema
        produces failures that look like application bugs, hours later, in
        unrelated code. Failing here names the actual problem.
        """
        if self._settings.verify_on_start:
            self.verify().raise_if_blocking()
        self._engines.async_engine()
        self._started = True

    async def stop(self) -> None:
        await self._engines.dispose()
        self._started = False

    # -- work --------------------------------------------------------------

    def unit_of_work(self) -> UnitOfWork:
        """A transaction boundary with its DAOs."""
        return UnitOfWork(self._sessions.session(), self._engines)

    def lease_provider(self) -> LeaseProvider:
        """Durable, fleet-wide leases backed by this database."""
        return DatabaseLeaseProvider(self._engines.async_engine(), clock=self._clock)

    async def health(self) -> dict[str, object]:
        """A liveness probe that actually touches the database."""
        from sqlalchemy import text

        engine = self._engines.async_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {
            "dialect": self._dialect.name,
            "schema_file": str(self._settings.schema_file),
            "started": self._started,
        }
