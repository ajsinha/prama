"""Every model call is held to the budgets, not only the chat API's.

``POST /llm/chat`` checked budgets before calling; a steward's task, code
intake, fitness search, the CLI and the console's model pages built their own
gateway and spent freely. The guard now lives in the gateway ``gateway_for``
builds, so no path can skip it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.db import Database
from prama.llm.budget import BudgetExhausted
from prama.llm.spi import Request
from prama.llm.wiring import gateway_for
from prama.semantic.values import Sensitivity


async def _configure(database: Database, tenant: str, answers: list[str]) -> None:
    async with database.unit_of_work() as uow:
        await uow.llm.add_provider(
            tenant,
            name="local",
            kind="scripted",
            hosting="self_hosted",
            settings={"answers": answers},
        )
        await uow.llm.set_profile(tenant, "author", [("local", "qwen")])


def _ask() -> Request:
    return Request(system="", prompt="write one", sensitivity=Sensitivity.INTERNAL)


async def test_a_steward_is_refused_when_the_budget_is_spent(
    started_database: Database, tenant_id: str
) -> None:
    await _configure(started_database, tenant_id, ["CHECK t.a IS NOT NULL"])
    async with started_database.unit_of_work() as uow:
        await uow.llm.set_budget(tenant_id, scope_kind="tenant", limit_tokens=0)
        gateway, ledger = await gateway_for(
            uow, tenant_id, surface="steward", principal_id="steward-1"
        )
    with pytest.raises(BudgetExhausted):
        gateway.run("author", _ask())
    (record,) = ledger.records
    assert record.outcome == "refused_budget" and record.surface == "steward"


async def test_a_gateways_own_calls_count_against_the_budget(
    started_database: Database, tenant_id: str
) -> None:
    # Four words out spends four tokens: under a limit of three, the first call
    # is made (nothing was spent) and the second is refused.
    await _configure(started_database, tenant_id, ["one two three four", "again"])
    async with started_database.unit_of_work() as uow:
        await uow.llm.set_budget(tenant_id, scope_kind="tenant", limit_tokens=3)
        gateway, ledger = await gateway_for(uow, tenant_id, surface="cli")
    assert gateway.run("author", _ask()).text == "one two three four"
    with pytest.raises(BudgetExhausted):
        gateway.run("author", _ask())
    assert [r.outcome for r in ledger.records] == ["ok", "refused_budget"]


async def test_a_principals_budget_binds_only_that_principal(
    started_database: Database, tenant_id: str
) -> None:
    await _configure(started_database, tenant_id, ["a", "b"])
    async with started_database.unit_of_work() as uow:
        await uow.llm.set_budget(
            tenant_id, scope_kind="principal", scope_id="steward-1", limit_tokens=0
        )
        bound, _ = await gateway_for(uow, tenant_id, surface="steward", principal_id="steward-1")
        free, _ = await gateway_for(uow, tenant_id, surface="steward", principal_id="steward-2")
    with pytest.raises(BudgetExhausted):
        bound.run("author", _ask())
    assert free.run("author", _ask()).text == "a"


async def test_with_no_budget_nothing_is_refused(
    started_database: Database, tenant_id: str
) -> None:
    await _configure(started_database, tenant_id, ["a"])
    async with started_database.unit_of_work() as uow:
        gateway, _ = await gateway_for(uow, tenant_id, surface="steward")
    assert gateway.run("author", _ask()).text == "a"
