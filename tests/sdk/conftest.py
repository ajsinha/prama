"""An SDK client against a real application, in process.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from prama_sdk import AsyncClient

from prama.api import create_app
from prama.core.config import Configuration
from prama.db import Database
from prama.security.accounts import grant_roles

PASSWORD = "sdk-test-password-1"


@pytest.fixture
async def app(sqlite_config: Configuration, started_database: Database) -> AsyncIterator[object]:
    application = create_app(sqlite_config, database=started_database)
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def admin(started_database: Database, tenant_id: str) -> str:
    """An administrator in the test estate, who signs in with a password."""
    async with started_database.unit_of_work() as uow:
        principal = uow.principals.create(tenant_id=tenant_id, username="ada", display_name="Ada")
        uow.principals.set_password(principal, PASSWORD)
        await uow.flush()
        await grant_roles(uow, tenant_id, principal, ["admin"])
    return "ada"


@pytest.fixture
async def client(app: object, admin: str) -> AsyncIterator[AsyncClient]:
    """Signed in as the administrator, through the SDK's own token exchange."""
    anonymous = AsyncClient(app=app)
    credentials = await anonymous.auth.token(admin, PASSWORD, tenant="acme-bank")
    await anonymous.close()
    signed_in = anonymous.as_key(credentials["api_key"])
    yield signed_in
    await signed_in.close()
