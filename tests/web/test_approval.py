"""A held declaration, approved in the console by somebody other than its author.

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

PASSWORD = "approval-test-password-1"


async def _person(database: Database, tenant_id: str, username: str, role: str) -> None:
    async with database.unit_of_work() as uow:
        person = uow.principals.create(
            tenant_id=tenant_id, username=username, display_name=username
        )
        uow.principals.set_password(person, PASSWORD)
        await uow.flush()
        await grant_roles(uow, tenant_id, person, [role])


@pytest.fixture
async def browser(
    sqlite_config: Configuration, started_database: Database, tenant_id: str
) -> AsyncIterator[httpx.AsyncClient]:
    await _person(started_database, tenant_id, "alice", "admin")
    await _person(started_database, tenant_id, "olu", "owner")
    app = create_app(sqlite_config, database=started_database)
    async with (
        httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as http,
        app.router.lifespan_context(app),
    ):
        yield http


async def _sign_in(browser: httpx.AsyncClient, username: str) -> None:
    await browser.post("/sign-out")
    signed = await browser.post("/sign-in", data={"username": username, "password": PASSWORD})
    assert signed.status_code == 303


async def test_a_tier_one_declaration_is_held_then_approved_by_somebody_else(
    browser: httpx.AsyncClient,
) -> None:
    await _sign_in(browser, "alice")
    made = await browser.post(
        "/declarations/new",
        data={"name": "FRTB Feeder", "criticality": "1", "shape": "table"},
    )
    assert made.status_code == 303, made.text
    page = await browser.get(made.headers["location"])
    assert "Awaiting approval" in page.text
    # The author is not offered the approval, and is refused it if they try.
    assert 'name="reason"' not in page.text
    dataset_url = made.headers["location"]
    await browser.post(f"{dataset_url}/approve", data={"reason": "mine"})
    assert "Awaiting approval" in (await browser.get(dataset_url)).text

    await _sign_in(browser, "olu")
    assert 'name="reason"' in (await browser.get(dataset_url)).text
    approved = await browser.post(f"{dataset_url}/approve", data={"reason": "reviewed"})
    assert approved.status_code == 303
    assert "Awaiting approval" not in (await browser.get(dataset_url)).text
