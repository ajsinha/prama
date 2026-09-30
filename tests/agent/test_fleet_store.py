"""The persisted fleet's security properties, below the HTTP layer.

`tests/sdk/test_fleet.py` drives the whole loop over the SDK. These pin the
properties that loop rests on, each beside its counterfactual: a key is bound
to its estate and its agent, a claim is a conditional update that a second
claimant loses, the token is kept only as a digest, and a server with no secret
refuses rather than deriving keys from nothing.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from prama_kernel.agent.capability import AgentCapabilities
from prama_kernel.agent.protocol import Hello
from prama_kernel.agent.signing import sign_payload
from prama_kernel.clock import ManualClock

from prama.agent.fleet import Fleet, FleetSettings, derive_key
from prama.core.errors import SecretMissingError
from prama.db import Database

pytestmark = pytest.mark.anyio

SETTINGS = FleetSettings(secret="fleet-test-secret")
PQL = "CHECK trades.notional IS NOT NULL BECAUSE 'every trade has a notional'"


def test_a_key_is_bound_to_its_estate_and_its_agent() -> None:
    key = derive_key("s", "tenant-a", "agent-1")
    assert key == derive_key("s", "tenant-a", "agent-1") and len(key) == 32
    # The counterfactuals: any one input changed is another key.
    assert key != derive_key("s", "tenant-b", "agent-1")
    assert key != derive_key("s", "tenant-a", "agent-2")
    assert key != derive_key("t", "tenant-a", "agent-1")


def test_no_secret_is_a_refusal_not_a_key_derived_from_nothing() -> None:
    with pytest.raises(SecretMissingError, match="no fleet secret"):
        derive_key("", "tenant-a", "agent-1")


async def test_the_token_is_stored_as_a_digest_only(
    started_database: Database, tenant_id: str
) -> None:
    async with started_database.unit_of_work() as uow:
        issued = await Fleet(uow, SETTINGS).issue_token(tenant_id, "eu")
    async with started_database.unit_of_work() as uow:
        assert await uow.fleet.token_by_digest(issued["token"]) is None
        import hashlib

        stored = await uow.fleet.token_by_digest(
            hashlib.sha256(issued["token"].encode()).hexdigest()
        )
        assert stored is not None and issued["token"] not in repr(stored.to_dict())


async def test_a_signature_under_another_estates_key_is_refused(
    started_database: Database, tenant_id: str
) -> None:
    async with started_database.unit_of_work() as uow:
        fleet = Fleet(uow, SETTINGS)
        issued = await fleet.issue_token(tenant_id, "eu")
        enrolled = await fleet.enrol(issued["token"], name="a", version="1", capabilities={})
    hello = Hello(agent_id=enrolled["agent_id"], capabilities=AgentCapabilities())
    wrong = derive_key(SETTINGS.secret, "01OTHERESTATE0000000000000", enrolled["agent_id"])
    async with started_database.unit_of_work() as uow:
        refused = await Fleet(uow, SETTINGS).hello(
            hello.to_dict(),
            agent_header=enrolled["agent_id"],
            signature=sign_payload(wrong, hello.signable()),
        )
        assert "not signed" in refused["reason"]
        accepted = await Fleet(uow, SETTINGS).hello(
            hello.to_dict(),
            agent_header=enrolled["agent_id"],
            signature=sign_payload(bytes.fromhex(enrolled["key"]), hello.signable()),
        )
        assert "reason" not in accepted
        # A header naming another agent than the message is refused too.
        mismatched = await Fleet(uow, SETTINGS).hello(
            hello.to_dict(),
            agent_header="01SOMEONEELSE0000000000000",
            signature=sign_payload(bytes.fromhex(enrolled["key"]), hello.signable()),
        )
        assert "different agent" in mismatched["reason"]


async def test_a_claim_is_lost_by_the_second_claimant(
    started_database: Database, tenant_id: str
) -> None:
    clock = ManualClock(datetime(2026, 9, 30, 6, 0, tzinfo=UTC))
    async with started_database.unit_of_work() as uow:
        control, _ = await uow.controls.declare(tenant_id=tenant_id, identity="c", pql=PQL)
        await uow.controls.activate(str(control.id), tenant_id=tenant_id, approved_by="bo")
        await Fleet(uow, SETTINGS, clock=clock).dispatch(tenant_id, "eu", engine="sqlite")
    async with started_database.unit_of_work() as uow:
        (row,) = await uow.fleet.queued(tenant_id, "eu")
        stamp, until = "2026-09-30T06:00:00.000+00:00", "2026-09-30T06:15:00.000+00:00"
        assert await uow.fleet.claim(tenant_id, row, agent_id="a", now=stamp, lease_until=until)
        # The same row, as a second agent read it before the first claimed it.
        assert not await uow.fleet.claim(tenant_id, row, agent_id="b", now=stamp, lease_until=until)
        # Another estate cannot claim it either, whoever holds the row object.
        assert not await uow.fleet.claim(
            "01OTHERESTATE0000000000000", row, agent_id="c", now=stamp, lease_until=until
        )
    async with started_database.unit_of_work() as uow:
        (held,) = await uow.fleet.work(tenant_id)
        assert held.state == "claimed" and held.claimed_by == "a" and held.attempts == 1
