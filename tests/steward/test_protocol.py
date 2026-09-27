"""The remote steward protocol, through the real API with a steward's own key.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from httpx import ASGITransport

from prama.api import create_app
from prama.api.app import API_PREFIX
from prama.db import Database
from prama.steward import identity, protocol
from prama.steward.runner import tick


@pytest.fixture
async def agent(
    sqlite_config: Any, started_database: Database, tenant_id: str
) -> AsyncIterator[tuple[httpx.AsyncClient, Any]]:
    async with started_database.unit_of_work() as uow:
        sponsor = uow.principals.create(tenant_id=tenant_id, username="ada", display_name="Ada")
        await uow.flush()
        steward, key = await identity.create(uow, tenant_id, "remote", sponsor_id=str(sponsor.id))
        await uow.stewards.add_goal(
            tenant_id,
            steward.id,
            statement="triage",
            kind="remote.work",
            inputs={"remote": True},
            schedule="1h",
            by=str(sponsor.id),
        )
    app = create_app(sqlite_config, database=started_database)
    async with (
        httpx.AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver" + API_PREFIX,
            headers={"Authorization": f"Bearer {key}"},
        ) as http,
        app.router.lifespan_context(app),
    ):
        yield http, steward


async def test_claim_heartbeat_result_and_a_stale_token_refused(
    agent: Any, started_database: Database, sqlite_config: Any
) -> None:
    http, _ = agent
    await tick(started_database, sqlite_config)  # queues the remote goal's task
    (task,) = (await http.post("/agents/claim", json={"most": 5})).json()["tasks"]
    token = task["fencing_token"]
    beat = await http.post(f"/agents/tasks/{task['task']}/heartbeat", json={"fencing_token": token})
    assert beat.json() == {"instruction": "continue"}
    stale = await http.post(
        f"/agents/tasks/{task['task']}/result",
        json={"fencing_token": token + 99, "state": "succeeded", "output": {}},
    )
    assert stale.status_code == 409
    done = await http.post(
        f"/agents/tasks/{task['task']}/result",
        json={"fencing_token": token, "state": "succeeded", "output": {"note": "done"}},
    )
    assert done.status_code == 200 and done.json()["state"] == "succeeded"


async def test_an_abandoned_task_is_requeued_and_the_old_holder_refused(
    agent: Any, started_database: Database, sqlite_config: Any, tenant_id: str
) -> None:
    http, steward = agent
    await tick(started_database, sqlite_config)
    (first,) = (await http.post("/agents/claim", json={})).json()["tasks"]
    # The holder vanishes: its lease is gone.
    leases = started_database.lease_provider()
    held = await leases.inspect(f"agt-task:{first['task']}")
    await leases.release(held)
    async with started_database.unit_of_work() as uow:
        goals = [g.id for g in await uow.stewards.goals(tenant_id, steward.id)]
        assert await protocol.requeue_expired(uow, started_database, tenant_id, goals) == 1
    (second,) = (await http.post("/agents/claim", json={})).json()["tasks"]
    assert second["task"] == first["task"] and second["fencing_token"] > first["fencing_token"]
    late = await http.post(
        f"/agents/tasks/{first['task']}/result",
        json={"fencing_token": first["fencing_token"], "state": "succeeded", "output": {}},
    )
    assert late.status_code == 409


async def test_a_paused_steward_is_refused_and_told_to_cancel(
    agent: Any, started_database: Database, sqlite_config: Any, tenant_id: str
) -> None:
    http, steward = agent
    await tick(started_database, sqlite_config)
    (task,) = (await http.post("/agents/claim", json={})).json()["tasks"]
    async with started_database.unit_of_work() as uow:
        row = await uow.stewards.one(tenant_id, steward.id)
        await identity.set_state(uow, tenant_id, row, "paused", by=None)
    assert (await http.post("/agents/claim", json={})).status_code == 403
    beat = await http.post(
        f"/agents/tasks/{task['task']}/heartbeat", json={"fencing_token": task["fencing_token"]}
    )
    assert beat.json() == {"instruction": "cancel"}


async def test_an_ordinary_key_cannot_act_as_an_agent(
    sqlite_config: Any, started_database: Database, tenant_id: str
) -> None:
    from tests.api.conftest import issue_key

    key = await issue_key(started_database, tenant_id, principal="bob", scopes=["agent:work"])
    app = create_app(sqlite_config, database=started_database)
    async with (
        httpx.AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver" + API_PREFIX,
            headers={"Authorization": f"Bearer {key}"},
        ) as http,
        app.router.lifespan_context(app),
    ):
        assert (await http.post("/agents/claim", json={})).status_code == 403


async def test_an_approval_gate_parks_then_runs_or_fails(
    started_database: Database, sqlite_config: Any, tenant_id: str
) -> None:
    async with started_database.unit_of_work() as uow:
        sponsor = uow.principals.create(tenant_id=tenant_id, username="eve", display_name="Eve")
        await uow.flush()
        steward, _ = await identity.create(uow, tenant_id, "careful", sponsor_id=str(sponsor.id))
        for statement in ("first", "second"):
            await uow.stewards.add_goal(
                tenant_id,
                steward.id,
                statement=statement,
                kind="lineage.proposals",
                inputs={"approve_before_run": True},
                schedule="1h",
                by=str(sponsor.id),
            )
    assert await tick(started_database, sqlite_config) == 0  # parked, not run
    async with started_database.unit_of_work() as uow:
        granted, denied = await uow.stewards.open_approvals(tenant_id)
        await protocol.decide(uow, tenant_id, granted.id, granted=True, by="eve")
        await protocol.decide(uow, tenant_id, denied.id, granted=False, by="eve")
    assert await tick(started_database, sqlite_config) == 1  # the granted one runs
    async with started_database.unit_of_work() as uow:
        states = sorted(t.state for t in await uow.stewards.tasks(tenant_id))
    assert states == ["failed", "succeeded"]
