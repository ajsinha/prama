"""Fixtures for the QA regression suite.

Deliberately self-contained rather than importing `tests/conftest.py`. The two
suites answer to different pressures — `tests/` follows the code, this one
follows what QA found — and a shared fixture is a shared assumption. Several of
the defects recorded here exist *because* every console fixture set
`tenancy.default_tenant`, a pre-auth wildcard, so 4,666 tests passed over a
sign-in door that did not work. Fixtures are not neutral.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from prama.core.config import Configuration, ConfigurationBuilder
from prama.core.config.defaults import DEFAULTS
from prama.db import Database

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def qa_config(tmp_path: Path) -> Configuration:
    """A throwaway SQLite estate.

    A file rather than `:memory:`, so the synchronous DDL engine and the
    asynchronous data engine share one database instead of quietly disagreeing.
    """
    return (
        ConfigurationBuilder()
        .with_defaults(DEFAULTS)
        .with_mapping(
            {
                "database": {
                    "dialect": "sqlite",
                    "sqlite": {"path": str(tmp_path / "prama-qa.db")},
                    "schema_dir": str(REPO_ROOT / "schema"),
                    "verify_on_start": True,
                },
                "security": {
                    "session_secret": "test-only-not-a-secret",
                    "cookies_https_only": False,
                },
            },
            name="qa-regression",
        )
        .build()
    )


@pytest.fixture
def qa_database(qa_config: Configuration) -> Iterator[Database]:
    database = Database.from_config(qa_config)
    database.initialise(applied_by="qa-regression")
    yield database
    database.sync_engine().dispose()


@pytest.fixture
async def estate(qa_database: Database) -> AsyncIterator[Database]:
    await qa_database.start()
    yield qa_database
    await qa_database.stop()


@pytest.fixture
async def two_tenants(estate: Database) -> tuple[str, str]:
    """Two estates that must not be able to see each other.

    Returned as a pair because almost every isolation defect needs both: one
    to hold the data and one to try to read it. A single-tenant fixture cannot
    express the failure at all, which is part of why these went unnoticed.
    """
    async with estate.unit_of_work() as uow:
        ours = uow.tenants.create(slug="acme-bank", display_name="Acme Bank")
        theirs = uow.tenants.create(slug="rival-bank", display_name="Rival Bank")
        await uow.flush()
        return str(ours.id), str(theirs.id)


@pytest.fixture
async def console_for_ours(
    qa_config: Configuration, estate: Database, two_tenants: tuple[str, str]
) -> AsyncIterator[httpx.AsyncClient]:
    """A browser bound to the *first* of the two estates.

    Bound to one deliberately. The console fixture under `tests/` sets
    `tenancy.default_tenant` too, but with a single tenant in the database —
    which makes every cross-estate question unaskable, and is a large part of
    why round 1 passed 4,666 tests over a sign-in door that did not work. Two
    estates exist here, and this client can only be one of them.

    `follow_redirects` stays off: a 303 is the success signal on these forms,
    and a client that quietly follows it cannot tell a completed post from a
    redirect loop.
    """
    from prama.api import create_app

    ours, _ = two_tenants
    config = (
        ConfigurationBuilder()
        .with_defaults(qa_config.raw())
        .with_mapping({"tenancy": {"default_tenant": ours}}, name="qa-console")
        .build()
    )
    app = create_app(config, database=estate)
    transport = ASGITransport(app=app)
    async with (
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as http,
        app.router.lifespan_context(app),
    ):
        yield http
