"""Steward agents: identity, goals, the kill switch, and the propose-only boundary.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

from prama.core.errors import ValidationError
from prama.db import Database
from prama.steward import identity
from prama.steward.runner import tick

SPONSOR = "01SPONSOR0000000000000000A"


async def _sponsor(uow: Any, tenant: str) -> str:
    person = uow.principals.create(tenant_id=tenant, username="ada", display_name="Ada")
    await uow.flush()
    return str(person.id)


def test_a_steward_may_never_hold_a_deciding_scope() -> None:
    for scope in ("control:approve", "attestation:sign", "admin", "relationship:write", "*"):
        with pytest.raises(ValidationError, match="may not hold"):
            identity.check_scopes(["llm:use", scope])
    assert identity.check_scopes(["llm:use", "control:read"])  # the control


async def test_a_steward_is_a_service_principal_with_a_propose_only_key(
    started_database: Database, tenant_id: str
) -> None:
    async with started_database.unit_of_work() as uow:
        sponsor = await _sponsor(uow, tenant_id)
        steward, plaintext = await identity.create(uow, tenant_id, "keeper", sponsor_id=sponsor)
        principal = await uow.principals.get(steward.principal_id)
        (key,) = await uow.api_keys.active_for_principal(steward.principal_id)
    assert principal.kind == "service" and steward.sponsor_id == sponsor
    assert plaintext.startswith("pk_agent_")
    assert not set(key.scopes_json) & identity.FORBIDDEN


async def test_a_scheduled_goal_runs_and_leaves_a_note(
    started_database: Database, tenant_id: str, sqlite_config: Any
) -> None:
    async with started_database.unit_of_work() as uow:
        sponsor = await _sponsor(uow, tenant_id)
        steward, _ = await identity.create(uow, tenant_id, "keeper", sponsor_id=sponsor)
        await uow.stewards.add_goal(
            tenant_id,
            steward.id,
            statement="watch",
            kind="lineage.proposals",
            inputs={},
            schedule="1h",
            by=sponsor,
        )
    assert await tick(started_database, sqlite_config) == 1
    assert await tick(started_database, sqlite_config) == 0  # not due again for an hour
    async with started_database.unit_of_work() as uow:
        (task,) = await uow.stewards.tasks(tenant_id)
    assert task.state == "succeeded" and "note" in task.output_json


async def test_a_model_call_is_made_as_the_steward_and_recorded(
    started_database: Database, tenant_id: str, sqlite_config: Any
) -> None:
    from prama.evidence.record import EvidenceRecord, SnapshotRef
    from prama.steward.runner import run_task

    async with started_database.unit_of_work() as uow:
        sponsor = await _sponsor(uow, tenant_id)
        await uow.llm.add_provider(
            tenant_id,
            name="local",
            kind="scripted",
            hosting="self_hosted",
            settings={"answers": ["Positions are failing completeness; start with raw.trades."]},
        )
        await uow.llm.set_profile(tenant_id, "summarise", [("local", "qwen")])
        await uow.evidence.append(
            EvidenceRecord(
                plan_id="ir:sha256:" + "d" * 64,
                control_id="c1",
                dataset="raw.trades",
                binding="raw.trades",
                engine="duckdb",
                snapshot=SnapshotRef(kind="wall_clock", identifier="t0"),
                verdict="fail",
                metrics={"scanned_rows": 10.0, "violating_rows": 2.0},
                started_at="2026-09-27T06:00:00Z",
                finished_at="2026-09-27T06:00:01Z",
                tenant_id=tenant_id,
            ),
            tenant_id=tenant_id,
        )
        steward, _ = await identity.create(uow, tenant_id, "briefer", sponsor_id=sponsor)
        goal = await uow.stewards.add_goal(
            tenant_id,
            steward.id,
            statement="brief",
            kind="incidents.summarise",
            inputs={},
            schedule=None,
            by=sponsor,
        )
        task = await run_task(uow, sqlite_config, tenant_id, steward, goal, key="k1")
        (call,) = await uow.llm.calls(tenant_id)
    assert task.state == "succeeded" and "raw.trades" in task.output_json["summary"]
    assert call.surface == "steward" and call.principal_id == steward.principal_id


async def test_pause_stops_new_work_and_revoke_ends_the_identity(
    started_database: Database, tenant_id: str, sqlite_config: Any
) -> None:
    async with started_database.unit_of_work() as uow:
        sponsor = await _sponsor(uow, tenant_id)
        steward, _ = await identity.create(uow, tenant_id, "keeper", sponsor_id=sponsor)
        await uow.stewards.add_goal(
            tenant_id,
            steward.id,
            statement="watch",
            kind="lineage.proposals",
            inputs={},
            schedule="1m",
            by=sponsor,
        )
        await identity.set_state(uow, tenant_id, steward, "paused", by=sponsor)
    assert await tick(started_database, sqlite_config) == 0
    async with started_database.unit_of_work() as uow:
        steward = (await uow.stewards.all(tenant_id))[0]
        await identity.set_state(uow, tenant_id, steward, "revoked", by=sponsor)
        principal = await uow.principals.get(steward.principal_id)
        assert principal.status == "disabled"
        assert not await uow.api_keys.active_for_principal(steward.principal_id)
        with pytest.raises(ValidationError, match="stays revoked"):
            await identity.set_state(uow, tenant_id, steward, "active", by=sponsor)


def test_the_steward_package_never_calls_a_deciding_function() -> None:
    """CON-007 for agents: nothing in prama.steward approves, confirms, signs or
    activates. Proposals go to the queue; people decide."""
    forbidden = {"activate", "accept", "sign", "decide", "approve", "confirm", "suppress"}
    root = Path(__file__).resolve().parents[2] / "src" / "prama" / "steward"
    called: set[str] = set()
    for path in root.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                called.add(node.func.attr)
    assert not called & forbidden, sorted(called & forbidden)
    assert "remember" in called  # the control: the scan does see calls
