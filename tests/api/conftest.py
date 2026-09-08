"""Shared fixtures for the API tests.

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

TENANT_HEADER = "X-Prama-Tenant"


@pytest.fixture
async def client(
    sqlite_config: Configuration, started_database: Database, tenant_id: str
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(sqlite_config, database=started_database)
    transport = ASGITransport(app=app)
    async with (
        httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver" + API_PREFIX,
            headers={TENANT_HEADER: tenant_id, "X-Prama-Principal": "alice"},
        ) as http,
        app.router.lifespan_context(app),
    ):
        yield http
