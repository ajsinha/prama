"""Shared fixtures.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from prama.api import create_app
from prama.core.config import Configuration, ConfigurationBuilder
from prama.core.config.defaults import DEFAULTS
from prama.db import Database

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def sqlite_config(tmp_path: Path) -> Configuration:
    """A configuration pointing at a throwaway SQLite file.

    A file rather than ``:memory:`` so that the synchronous DDL engine and the
    asynchronous data engine genuinely share a database — the exact confusion an
    in-memory default would hide.
    """
    return (
        ConfigurationBuilder()
        .with_defaults(DEFAULTS)
        .with_mapping(
            {
                "database": {
                    "dialect": "sqlite",
                    "sqlite": {"path": str(tmp_path / "prama-test.db")},
                    "schema_dir": str(REPO_ROOT / "schema"),
                    "verify_on_start": True,
                },
                # The console mounts in tests too. A UI that is only ever
                # exercised by hand is a UI whose templates break on a rename
                # and nobody finds out until a demo.
                "security": {
                    "session_secret": "test-only-not-a-secret",
                    "cookies_https_only": False,
                },
            },
            name="test",
        )
        .build()
    )


@pytest.fixture
def postgres_config() -> Configuration:
    """Configuration for a live PostgreSQL, from PRAMA_TEST_PG_* environment."""
    return (
        ConfigurationBuilder()
        .with_defaults(DEFAULTS)
        .with_mapping(
            {
                "database": {
                    "dialect": "postgres",
                    "postgres": {
                        "host": os.environ.get("PRAMA_TEST_PG_HOST", "localhost"),
                        "port": int(os.environ.get("PRAMA_TEST_PG_PORT", "5432")),
                        "database": os.environ.get("PRAMA_TEST_PG_DB", "prama_test"),
                        "user": os.environ.get("PRAMA_TEST_PG_USER", "prama"),
                        "password": os.environ.get("PRAMA_TEST_PG_PASSWORD", ""),
                    },
                    "schema_dir": str(REPO_ROOT / "schema"),
                }
            },
            name="test",
        )
        .build()
    )


@pytest.fixture
def sqlite_database(sqlite_config: Configuration) -> Iterator[Database]:
    database = Database.from_config(sqlite_config)
    database.initialise(applied_by="pytest")
    yield database
    database.sync_engine().dispose()


@pytest.fixture
async def started_database(sqlite_database: Database) -> AsyncIterator[Database]:
    await sqlite_database.start()
    yield sqlite_database
    await sqlite_database.stop()


@pytest.fixture
async def tenant_id(started_database: Database) -> str:
    async with started_database.unit_of_work() as uow:
        tenant = uow.tenants.create(slug="acme-bank", display_name="Acme Bank")
        await uow.flush()
        return str(tenant.id)


@pytest.fixture
async def ui(
    sqlite_config: Configuration, started_database: Database, tenant_id: str
) -> AsyncIterator[httpx.AsyncClient]:
    """A browser-shaped client with a session already carrying the tenant.

    Lives here rather than under tests/web because it is a client for the whole
    application: the end-to-end tests drive the console to check that a run
    they triggered actually appears on it, which is the assertion that makes
    the loop closed rather than merely wired.

    ``follow_redirects`` stays off: several tests are *about* the redirect, and
    a client that quietly follows them cannot tell a working page from a
    redirect loop that happens to terminate.
    """
    config = (
        ConfigurationBuilder()
        .with_defaults(sqlite_config.raw())
        .with_mapping({"tenancy": {"default_tenant": tenant_id}}, name="ui-test")
        .build()
    )
    app = create_app(config, database=started_database)
    transport = ASGITransport(app=app)
    async with (
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as http,
        app.router.lifespan_context(app),
    ):
        yield http
