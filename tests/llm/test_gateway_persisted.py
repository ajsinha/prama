"""Profiles and the call ledger, through the real database.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.core.errors import ValidationError
from prama.db import Database
from prama.llm.gateway import GENESIS, seal
from prama.llm.spi import Request
from prama.llm.wiring import gateway_for, persist


async def _setup(database: Database, tenant: str) -> None:
    async with database.unit_of_work() as uow:
        await uow.llm.add_provider(
            tenant,
            name="local",
            kind="scripted",
            hosting="self_hosted",
            settings={"answers": ["CHECK t.a IS NOT NULL", "CHECK t.b IS NOT NULL"]},
        )
        await uow.llm.set_profile(tenant, "author", [("local", "qwen2.5-coder")])


async def test_a_call_is_routed_and_chained(started_database: Database, tenant_id: str) -> None:
    await _setup(started_database, tenant_id)
    async with started_database.unit_of_work() as uow:
        gateway, ledger = await gateway_for(uow, tenant_id, surface="test")
        assert gateway.run("author", Request(system="s", prompt="p")).text
        assert gateway.run("author", Request(system="s", prompt="q")).text
        assert await persist(uow, tenant_id, ledger) == 2
    async with started_database.unit_of_work() as uow:
        second, first = await uow.llm.calls(tenant_id)
    assert (first.sequence, second.sequence) == (0, 1)
    assert first.previous_hash == GENESIS and second.previous_hash == first.record_hash
    assert first.model_requested == "qwen2.5-coder" and first.outcome == "ok"


async def test_changing_a_profile_keeps_its_history(
    started_database: Database, tenant_id: str
) -> None:
    await _setup(started_database, tenant_id)
    async with started_database.unit_of_work() as uow:
        await uow.llm.add_provider(tenant_id, name="other", kind="none", hosting="self_hosted")
        await uow.llm.set_profile(tenant_id, "author", [("other", "m2"), ("local", "m1")])
        profile, version = await uow.llm.current(tenant_id, "author")
    assert version.version == 2 and len(profile.versions) == 2
    assert [r.model for r in version.routes] == ["m2", "m1"]


async def test_offline_refuses_a_remote_provider(
    started_database: Database, tenant_id: str
) -> None:
    async with started_database.unit_of_work() as uow:
        await uow.llm.add_provider(
            tenant_id,
            name="vendor",
            kind="openai_compatible",
            hosting="hosted",
            endpoint="https://api.openai.com",
        )
        await uow.llm.set_profile(tenant_id, "author", [("vendor", "gpt")])
        await gateway_for(uow, tenant_id, surface="test")  # the control: online it builds
        with pytest.raises(ValidationError, match="not usable offline"):
            await gateway_for(uow, tenant_id, surface="test", offline=True)


async def test_a_profile_naming_a_missing_provider_is_refused(
    started_database: Database, tenant_id: str
) -> None:
    async with started_database.unit_of_work() as uow:
        with pytest.raises(Exception, match="no provider called ghost"):
            await uow.llm.set_profile(tenant_id, "author", [("ghost", "m")])


def test_the_seal_is_what_the_dao_stores() -> None:
    # One function computes the chain wherever it is written or checked.
    from prama.db.dao.llm import seal as dao_seal

    assert dao_seal is seal
