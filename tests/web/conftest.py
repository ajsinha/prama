"""Fixtures for the console tests.

The ``ui`` client fixture lives in tests/conftest.py, because it drives the
whole application and the end-to-end tests need it too. ``stranger``, a
visitor with no session, is here: only the console's tests need one.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from pathlib import Path
from typing import Any

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


def live_console(
    root: Path, seed: Callable[[Any, str], Awaitable[None]] | None = None
) -> Iterator[str]:
    """The console on a real port over a fresh database, for tests driving a browser.

    Single-tenant (``tenancy.default_tenant`` set), so every page renders without
    signing in. *seed* is awaited with a unit of work and the tenant id before the
    server starts, for a test that needs rows to render: an empty table cannot
    overflow a phone's screen.
    """
    import uvicorn

    from prama.core.config import ConfigurationBuilder
    from prama.core.config.defaults import DEFAULTS

    config = (
        ConfigurationBuilder()
        .with_defaults(DEFAULTS)
        .with_mapping(
            {
                "database": {
                    "dialect": "sqlite",
                    "sqlite": {"path": str(root / "console.db")},
                    "schema_dir": str(Path(__file__).resolve().parents[2] / "schema"),
                    "verify_on_start": True,
                },
                "security": {"session_secret": "browser-tests-secret", "cookies_https_only": False},
                "web": {"enabled": True},
            },
            name="browser-tests",
        )
        .build()
    )

    async def _tenant() -> str:
        # Without a tenant every page 303s to the sign-in redirect, and a test
        # would measure that instead of the page.
        database_ = Database.from_config(config)
        database_.initialise(applied_by="browser-tests")
        await database_.start()
        try:
            async with database_.unit_of_work() as uow:
                tenant = uow.tenants.create(slug="test-bank", display_name="Test Bank")
                await uow.flush()
                if seed is not None:
                    await seed(uow, str(tenant.id))
                return str(tenant.id)
        finally:
            await database_.stop()

    tenant_id = asyncio.run(_tenant())
    config = (
        ConfigurationBuilder()
        .with_defaults(config.raw())
        .with_mapping({"tenancy": {"default_tenant": tenant_id}}, name="browser-tenant")
        .build()
    )
    app = create_app(config, database=Database.from_config(config))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        if not thread.is_alive():  # pragma: no cover - the server failed to boot
            raise RuntimeError("the console did not start")
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)
