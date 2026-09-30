"""Steward agents through the SDK: an administrator's side and the agent's own.

The property that matters most is the one CON-007 names: an agent proposes and
a person decides. So the tests below have a steward ask for approval with its
own key, show that it cannot grant itself — not with its own key, and not with
a wildcard key somebody minted for its principal by hand — and that the record
of the grant names the person who made it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

import prama_sdk as prama
import pytest
from prama_sdk import AsyncClient

from prama.core.config import Configuration
from prama.db import Database
from prama.db.security import ApiKeyIssuer
from prama.steward.runner import tick


async def test_a_steward_is_created_given_a_goal_and_run_now(client: AsyncClient) -> None:
    kinds = {t["kind"] for t in await client.agents.tools()}
    assert "lineage.proposals" in kinds

    made = await client.agents.create("librarian")
    assert made["state"] == "active" and made["api_key"].startswith("pk_")
    me = await client.auth.me()
    assert made["sponsor_id"] == me["principal_id"]

    # The steward's key can work and read; it cannot administer.
    agent = client.as_key(made["api_key"])
    scopes = (await agent.auth.me())["scopes"]
    assert "agent:work" in scopes and "admin" not in scopes
    with pytest.raises(prama.ForbiddenError):
        await agent.agents.list()

    goal = await client.agents.add_goal(made["id"], "lineage.proposals")
    assert goal["statement"] and goal["kind"] == "lineage.proposals"
    with pytest.raises(prama.NotFoundError):
        await client.agents.add_goal(made["id"], "no.such.tool")
    # A schedule the runner cannot read is refused, not stored to never fire.
    with pytest.raises(prama.ValidationError, match="not a schedule"):
        await client.agents.add_goal(made["id"], "lineage.proposals", schedule="every 6h")

    task = await client.agents.run(goal["id"])
    assert task["state"] == "succeeded" and task["goal_id"] == goal["id"]
    assert [t["id"] for t in await client.agents.tasks()] == [task["id"]]
    (listed,) = await client.agents.list()
    assert [g["id"] for g in listed["goals"]] == [goal["id"]]

    # The kill switch: a paused steward's goals do not run; revoked is final
    # and its key stops working.
    await client.agents.set_state(made["id"], "paused")
    with pytest.raises(prama.ConflictError):
        await client.agents.run(goal["id"])
    revoked = await client.agents.set_state(made["id"], "revoked")
    assert revoked["state"] == "revoked"
    with pytest.raises(prama.UnauthorisedError):
        await agent.auth.me()
    with pytest.raises(prama.ValidationError):
        await client.agents.set_state(made["id"], "active")


async def test_an_agent_asks_a_person_decides_and_the_record_names_the_person(
    client: AsyncClient,
    started_database: Database,
    sqlite_config: Configuration,
    tenant_id: str,
) -> None:
    made = await client.agents.create("remote")
    await client.agents.add_goal(
        made["id"], "remote.work", statement="triage breaks", remote=True, schedule="1h"
    )
    await tick(started_database, sqlite_config)  # queues the remote goal's task

    agent = client.as_key(made["api_key"])
    (task,) = (await agent.agents.claim(most=5))["tasks"]
    parked = await agent.agents.ask(
        task["task"], task["fencing_token"], {"tool": "close_break"}, "the break is explained"
    )
    assert parked["state"] == "awaiting_approval"
    (approval,) = await client.agents.approvals()
    assert approval["action"] == {"tool": "close_break"}

    # The agent cannot grant its own request: its key never holds admin...
    with pytest.raises(prama.ForbiddenError):
        await agent.agents.decide(approval["id"], grant=True)
    # ...and even a wildcard key minted for its principal by hand is refused.
    wildcard = await _hand_minted_wildcard(started_database, tenant_id, made["principal_id"])
    with pytest.raises(prama.ForbiddenError, match="person"):
        await client.as_key(wildcard).agents.decide(approval["id"], grant=True)
    assert [a["id"] for a in await client.agents.approvals()] == [approval["id"]]  # still open

    decided = await client.agents.decide(approval["id"], grant=True)
    me = await client.auth.me()
    assert decided["state"] == "granted" and decided["decided_by"] == me["principal_id"]
    assert await client.agents.approvals() == []
    # Granted: the task is back in the queue, carrying what was approved.
    (again,) = (await agent.agents.claim())["tasks"]
    assert again["task"] == task["task"]


async def test_a_person_decides_a_drafted_description_and_is_its_author(
    client: AsyncClient, started_database: Database, tenant_id: str
) -> None:
    trades = await client.datasets.declare("Trades")
    ledger = await client.datasets.declare("Ledger")
    async with started_database.unit_of_work() as uow:
        drafted = []
        for dataset in (trades, ledger):
            row = await uow.stewards.suggest(
                tenant_id,
                object_kind="dataset",
                object_id=dataset["id"],
                object_name=dataset["name"],
                field="description",
                text=f"{dataset['name']}: one row per booked item.",
                model="scripted/qwen",
                fingerprint=None,
                steward_id=None,
            )
            drafted.append(_id(row))

    open_ = await client.agents.suggestions()
    assert {s["id"] for s in open_} == set(drafted)

    me = await client.auth.me()
    accepted = await client.agents.decide_suggestion(drafted[0], accept=True)
    assert accepted["state"] == "accepted" and accepted["decided_by"] == me["principal_id"]
    assert (await client.datasets.get(trades["id"]))["description"] == (
        "Trades: one row per booked item."
    )

    rejected = await client.agents.decide_suggestion(drafted[1], accept=False)
    assert rejected["state"] == "rejected" and rejected["decided_by"] == me["principal_id"]
    assert not (await client.datasets.get(ledger["id"])).get("description")
    assert await client.agents.suggestions() == []
    assert {s["id"] for s in await client.agents.suggestions(state="accepted")} == {drafted[0]}
    # A decided suggestion cannot be decided again.
    with pytest.raises(prama.NotFoundError):
        await client.agents.decide_suggestion(drafted[1], accept=True)


async def _hand_minted_wildcard(database: Database, tenant_id: str, principal_id: str) -> str:
    """What an operator could do with ``prama apikey create --scope '*'``."""
    issued = ApiKeyIssuer().issue()
    async with database.unit_of_work() as uow:
        uow.api_keys.create(
            tenant_id=tenant_id,
            principal_id=principal_id,
            name="by hand",
            key_prefix=issued.prefix,
            key_hash=issued.hash,
            scopes=["*"],
        )
    return issued.plaintext


def _id(row: Any) -> str:
    assert row is not None
    return str(row.id)
