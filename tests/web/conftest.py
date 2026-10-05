"""Fixtures for the console tests.

The ``ui`` client fixture lives in tests/conftest.py, because it drives the
whole application and the end-to-end tests need it too. ``stranger``, a
visitor with no session, is here: only the console's tests need one.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from httpx import ASGITransport

from prama.api import create_app
from prama.core.config import Configuration
from prama.db import Database


@pytest.fixture
async def stranger(
    sqlite_config: Configuration, started_database: Database, tenant_id: str
) -> AsyncIterator[httpx.AsyncClient]:
    """No session and no default tenant: somebody arriving from outside."""
    app = create_app(sqlite_config, database=started_database)
    async with (
        httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as http,
        app.router.lifespan_context(app),
    ):
        yield http
