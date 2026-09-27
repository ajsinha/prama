"""The Models page: providers, profiles, a prompt tester, the call ledger.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama.db import Database


async def test_an_administrator_configures_and_runs_a_model(
    ui: Any, started_database: Database, tenant_id: str
) -> None:
    # The `ui` fixture runs on the single-tenant fallback, which holds every scope.
    assert (await ui.get("/models")).status_code == 200
    added = await ui.post(
        "/models/providers",
        data={"name": "local", "kind": "scripted", "hosting": "self_hosted"},
    )
    assert added.status_code == 303
    async with started_database.unit_of_work() as uow:
        provider = await uow.llm.provider(tenant_id, "local")
        assert provider is not None
        provider.settings_json = {"answers": ["CHECK trades.notional IS NOT NULL"]}
    saved = await ui.post("/models/profiles", data={"purpose": "author", "route": "local:qwen"})
    assert saved.status_code == 303
    page = await ui.post("/models/try", data={"purpose": "author", "prompt": "write one"})
    assert "CHECK trades.notional IS NOT NULL" in page.text
    async with started_database.unit_of_work() as uow:
        (call,) = await uow.llm.calls(tenant_id)
    assert call.surface == "console" and call.outcome == "ok"


async def test_a_vendor_declared_self_hosted_is_refused_on_the_page(
    ui: Any, started_database: Database, tenant_id: str
) -> None:
    await ui.post(
        "/models/providers",
        data={
            "name": "sneaky",
            "kind": "openai_compatible",
            "hosting": "self_hosted",
            "endpoint": "https://api.openai.com",
        },
    )
    async with started_database.unit_of_work() as uow:
        assert await uow.llm.provider(tenant_id, "sneaky") is None


async def test_the_page_is_for_administrators(
    ui: Any, started_database: Database, tenant_id: str
) -> None:
    from prama.security.accounts import BUILTIN_ROLES

    async with started_database.unit_of_work() as uow:
        person = uow.principals.create(tenant_id=tenant_id, username="sam", display_name="Sam")
        uow.principals.set_password(person, "correct horse battery staple")
        _, permissions = BUILTIN_ROLES["steward"]
        role = uow.roles.create(tenant_id=tenant_id, name="steward", permissions=permissions)
        await uow.flush()
        await uow.roles.grant(str(person.id), str(role.id))
    await ui.post("/sign-in", data={"username": "sam", "password": "correct horse battery staple"})
    assert (await ui.get("/models")).status_code == 403


async def test_the_schedule_page_says_when_the_scheduler_is_off(ui: Any) -> None:
    page = await ui.get("/schedule")
    assert page.status_code == 200 and "The scheduler is off" in page.text
    assert "scheduler:" in page.text  # it shows how to turn it on


async def test_a_budget_and_a_price_are_managed_on_the_page(
    ui: Any, started_database: Database, tenant_id: str
) -> None:
    await ui.post(
        "/models/providers", data={"name": "local", "kind": "scripted", "hosting": "self_hosted"}
    )
    assert (
        await ui.post("/models/budgets", data={"period": "month", "limit": "250.00"})
    ).status_code == 303
    assert (
        await ui.post(
            "/models/prices",
            data={
                "provider": "local",
                "model": "qwen",
                "input_per_million": "2.50",
                "output_per_million": "10",
            },
        )
    ).status_code == 303
    async with started_database.unit_of_work() as uow:
        (budget,) = await uow.llm.budgets(tenant_id)
        assert budget.limit_micros == 250_000_000
    page = await ui.get("/models")
    assert "250.00" in page.text and "This month" in page.text
