"""Signing in when the installation has more than one estate.

A case study creates an estate per run, so an installation with several is
ordinary. The form must then ask which, or every correct password is refused.

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
from prama.security.accounts import grant_roles

PASSWORD = "estate-sign-in-pw-1"


@pytest.fixture
async def browser(
    sqlite_config: Configuration, started_database: Database
) -> AsyncIterator[httpx.AsyncClient]:
    async with started_database.unit_of_work() as uow:
        for slug in ("first-estate", "second-estate"):
            tenant = uow.tenants.create(slug=slug, display_name=slug.replace("-", " ").title())
            await uow.flush()
            ada = uow.principals.create(
                tenant_id=str(tenant.id), username="ada", display_name="Ada"
            )
            uow.principals.set_password(ada, PASSWORD)
            await uow.flush()
            await grant_roles(uow, str(tenant.id), ada, ["admin"])
    app = create_app(sqlite_config, database=started_database)
    async with (
        httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as http,
        app.router.lifespan_context(app),
    ):
        yield http


async def test_the_form_asks_for_the_estate(browser: httpx.AsyncClient) -> None:
    page = (await browser.get("/sign-in")).text
    assert 'name="tenant"' in page
    # A text field, never a list of the estates on the installation.
    assert "second-estate" not in page and "first-estate" not in page


async def test_naming_the_estate_signs_you_in_to_it(browser: httpx.AsyncClient) -> None:
    signed = await browser.post(
        "/sign-in", data={"username": "ada", "password": PASSWORD, "tenant": "second-estate"}
    )
    assert signed.status_code == 303
    menu = (await browser.get("/estate")).text
    assert "Second Estate" in menu and "Switch estate" in menu


async def test_without_the_estate_a_right_password_is_refused(browser: httpx.AsyncClient) -> None:
    refused = await browser.post("/sign-in", data={"username": "ada", "password": PASSWORD})
    assert refused.status_code == 401
