"""Shared fixtures for the API tests.

The client authenticates with a real API key, because that is the only way in.
An earlier version sent an ``X-Prama-Tenant`` header, which the API trusted
without checking anything — the tests were the shape that made the hole look
deliberate.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from httpx import ASGITransport

from prama.api import API_PREFIX, create_app
from prama.core.config import Configuration
from prama.db import Database
from prama.db.security import ApiKeyIssuer


async def issue_key(
    database: Database, tenant_id: str, *, principal: str = "alice", scopes: list[str] | None = None
) -> str:
    """Mint a usable key for a tenant and return its plaintext."""
    issued = ApiKeyIssuer().issue(environment="test")
    async with database.unit_of_work() as uow:
        person = uow.principals.create(
            tenant_id=tenant_id, username=principal, display_name=principal
        )
        await uow.flush()
        uow.api_keys.create(
            tenant_id=tenant_id,
            principal_id=str(person.id),
            name="api tests",
            key_prefix=issued.prefix,
            key_hash=issued.hash,
            scopes=scopes if scopes is not None else ["*"],
        )
    return issued.plaintext


@pytest.fixture
async def api_key(started_database: Database, tenant_id: str) -> str:
    return await issue_key(started_database, tenant_id)


@pytest.fixture
async def client(
    sqlite_config: Configuration,
    started_database: Database,
    api_key: str,
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(sqlite_config, database=started_database)
    transport = ASGITransport(app=app)
    async with (
        httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver" + API_PREFIX,
            headers={"Authorization": f"Bearer {api_key}"},
        ) as http,
        app.router.lifespan_context(app),
    ):
        yield http


@pytest.fixture
async def unauthenticated(
    sqlite_config: Configuration, started_database: Database
) -> AsyncIterator[httpx.AsyncClient]:
    """A client with no credential at all, for the refusal tests."""
    app = create_app(sqlite_config, database=started_database)
    async with (
        httpx.AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver" + API_PREFIX,
        ) as http,
        app.router.lifespan_context(app),
    ):
        yield http


@pytest.fixture
async def other_tenant(started_database: Database) -> str:
    """A second estate, so cross-tenant access has somewhere to reach."""
    async with started_database.unit_of_work() as uow:
        tenant = uow.tenants.create(slug="rival-bank", display_name="Rival Bank")
        await uow.flush()
        return str(tenant.id)


@pytest.fixture
async def intruder(
    sqlite_config: Configuration, started_database: Database, other_tenant: str
) -> AsyncIterator[httpx.AsyncClient]:
    """A fully valid caller — of a *different* estate."""
    key = await issue_key(started_database, other_tenant, principal="mallory")
    app = create_app(sqlite_config, database=started_database)
    async with (
        httpx.AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver" + API_PREFIX,
            headers={"Authorization": f"Bearer {key}"},
        ) as http,
        app.router.lifespan_context(app),
    ):
        yield http
