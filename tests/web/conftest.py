"""Fixtures for the console tests.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from httpx import ASGITransport

from prama.api import create_app
from prama.core.config import Configuration, ConfigurationBuilder
from prama.db import Database


@pytest.fixture
async def ui(
    sqlite_config: Configuration, started_database: Database, tenant_id: str
) -> AsyncIterator[httpx.AsyncClient]:
    """A browser-shaped client with a session already carrying the tenant.

    ``follow_redirects`` stays off: several of these tests are *about* the
    redirect, and a client that quietly follows them cannot tell a working
    page from a redirect loop that happens to terminate.
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
