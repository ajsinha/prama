"""The agent fleet over HTTP, end to end through the SDK.

An administrator issues a token, an agent enrols with it and says hello, the
server hands it work compiled from a real active control, the in-process agent
(`prama.agent.runner.Agent`) runs it against a SQLite file with one planted
defect, and the report lands in the estate's evidence ledger as a ``fail`` whose
chain verifies. Around that, every security property has its counterfactual: a
reused or expired token, a wrong signature, a suspended and a revoked agent, a
replayed and a jumped report, work claimed by one agent and not another, a
claim that expires, evidence about a plan never assigned to the zone, and an
agent of one estate that cannot see another's work.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import prama_sdk as prama
import pytest
from prama_agent.runner import Agent
from prama_kernel.agent.capability import AgentCapabilities
from prama_kernel.agent.protocol import Assignment, Receipt, Report, response_from_dict
from prama_kernel.agent.residency import ResidencyPolicy, SampleDisposition
from prama_kernel.agent.spool import Gap
from prama_kernel.clock import ManualClock
from prama_sdk import AsyncClient
from prama_sdk.signing import sign
from prama_sdk.transport import Call
from tests.api.conftest import issue_key

from prama.db import Database

ZONE = "eu-frankfurt"
PQL = (
    "CHECK trades.notional IS NOT NULL SEVERITY critical DIMENSION completeness "
    "BECAUSE 'every trade has a notional'"
)
CAPABILITIES = AgentCapabilities(engines=("sqlite",))


# -- fixtures and helpers ------------------------------------------------------------


async def _activate(database: Database, tenant_id: str, pql: str = PQL) -> str:
    async with database.unit_of_work() as uow:
        control, _ = await uow.controls.declare(tenant_id=tenant_id, identity=pql[:40], pql=pql)
        await uow.controls.activate(str(control.id), tenant_id=tenant_id, approved_by="bo")
    return str(control.id)


@pytest.fixture
def source(tmp_path: Path) -> Path:
    """The agent's own data: five trades, one of them without a notional."""
    path = tmp_path / "zone.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE trades (id INTEGER PRIMARY KEY, account_id TEXT, notional REAL)")
        db.executemany(
            "INSERT INTO trades VALUES (?, ?, ?)",
            [(1, "A1", 100.0), (2, "A2", 250.5), (3, "A3", None), (4, "A4", 9.75), (5, "A5", 1.0)],
        )
    return path


def _executor(path: Path) -> Any:
    def execute(sql: str) -> list[dict[str, Any]]:
        with sqlite3.connect(path) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute(sql).fetchall()]

    return execute


@pytest.fixture
async def control_id(started_database: Database, tenant_id: str) -> str:
    return await _activate(started_database, tenant_id)


@pytest.fixture
async def anonymous(app: object) -> Any:
    """What an agent holds: a client with no API key at all."""
    agent_client = AsyncClient(app=app)
    yield agent_client
    await agent_client.close()


async def _enrol(client: AsyncClient, anonymous: AsyncClient, name: str, zone: str = ZONE) -> Any:
    issued = await client.fleet.issue_token(zone, name=name)
    return await anonymous.fleet.enrol(
        issued["token"], name=name, version="1.0.0", capabilities=CAPABILITIES.to_dict()
    )


def _agent(enrolled: dict[str, Any], source: Path) -> Agent:
    return Agent(
        enrolled["agent_id"],
        bytes.fromhex(enrolled["key"]),
        executor=_executor(source),
        residency=ResidencyPolicy(
            zone=enrolled["zone"], samples=SampleDisposition.MASK, may_send=("id",)
        ),
        capabilities=CAPABILITIES,
        version="1.0.0",
    )


async def _hello(anonymous: AsyncClient, agent: Agent, key: str) -> dict[str, Any]:
    message, _ = agent.hello()
    return await anonymous.fleet.hello(message.to_dict(), key=bytes.fromhex(key))  # type: ignore[no-any-return]


# -- the loop -----------------------------------------------------------------------


async def test_a_planted_defect_travels_from_the_zone_into_the_verified_ledger(
    client: AsyncClient, anonymous: AsyncClient, control_id: str, source: Path
) -> None:
    enrolled = await _enrol(client, anonymous, "eu-01")
    assert enrolled["zone"] == ZONE and len(bytes.fromhex(enrolled["key"])) == 32

    dispatched = await client.fleet.dispatch(ZONE, engine="sqlite", datasets=["trades"])
    assert [q["control_id"] for q in dispatched["queued"]] == [control_id]
    assert dispatched["unassignable"] == []
    # Dispatching again does not queue the same work twice.
    again = await client.fleet.dispatch(ZONE, engine="sqlite")
    assert again["queued"] == [] and len(again["already_queued"]) == 1

    agent = _agent(enrolled, source)
    receipt = await _hello(anonymous, agent, enrolled["key"])
    assert "reason" not in receipt, receipt
    (sent,) = receipt["assignments"]
    assignment = Assignment.from_dict(sent)
    assert assignment.dataset == "trades" and "trades" in assignment.metric_query

    outcome = agent.run(assignment)
    assert outcome.record is not None and outcome.record.verdict == "fail"
    message, _ = agent.report()
    answer = await anonymous.fleet.report(message.to_dict(), key=bytes.fromhex(enrolled["key"]))
    assert answer["accepted_through"] == 0 and answer["duplicates"] == 0, answer
    assert answer["rejected"] == []
    assert agent.apply(response_from_dict(answer)) is True and len(agent.spool) == 0

    (record,) = (await client.evidence.list())["items"]
    assert record["verdict"] == "fail" and record["control_id"] == control_id
    assert record["dataset"] == "trades" and record["metrics"]["violating_rows"] == 1
    assert record["triggered_by"] == f"agent:{enrolled['agent_id']}"
    verification = await client.evidence.verify()
    assert verification["intact"] is True and verification["records"] == 1

    # The assignment is done, and the fleet shows what the agent last said.
    health = await client.fleet.health()
    assert health["zones"][ZONE]["queued"] == 0 and health["zones"][ZONE]["claimed"] == 0
    (listed,) = await client.fleet.agents()
    assert listed["last_sequence"] == 0 and listed["version"] == "1.0.0"
    assert listed["capabilities"]["engines"] == ["sqlite"]

    # A replay of the same report is counted, not recorded twice.
    replay = await anonymous.fleet.report(message.to_dict(), key=bytes.fromhex(enrolled["key"]))
    assert replay["duplicates"] == 1 and replay["accepted_through"] == 0
    assert len((await client.evidence.list())["items"]) == 1

    # A jump is named with the sequence that was expected, and still kept.
    jumped = Report(
        agent_id=enrolled["agent_id"],
        records=(dataclasses.replace(outcome.record, sequence=5),),
    )
    answer = await anonymous.fleet.report(jumped.to_dict(), key=bytes.fromhex(enrolled["key"]))
    assert answer["accepted_through"] == 5
    assert [r["sequence"] for r in answer["rejected"]] == [5]
    assert "expected sequence 1" in answer["rejected"][0]["reason"]
    assert (await client.evidence.verify())["records"] == 2


async def test_a_claimed_assignment_goes_to_one_agent_only(
    client: AsyncClient, anonymous: AsyncClient, control_id: str, source: Path
) -> None:
    first = await _enrol(client, anonymous, "eu-01")
    second = await _enrol(client, anonymous, "eu-02")
    await client.fleet.dispatch(ZONE, engine="sqlite")

    taken = await _hello(anonymous, _agent(first, source), first["key"])
    assert len(taken["assignments"]) == 1
    # The counterfactual: the second agent, equally able, is given nothing.
    nothing = await _hello(anonymous, _agent(second, source), second["key"])
    assert "reason" not in nothing and nothing["assignments"] == []
    zone = (await client.fleet.health())["zones"][ZONE]
    assert zone["claimed"] == 1 and zone["queued"] == 0


async def test_an_expired_claim_returns_to_the_queue(
    app: Any, client: AsyncClient, anonymous: AsyncClient, control_id: str, source: Path
) -> None:
    clock = ManualClock(datetime(2026, 9, 30, 6, 0, tzinfo=UTC))
    app.state.clock = clock
    first = await _enrol(client, anonymous, "eu-01")
    second = await _enrol(client, anonymous, "eu-02")
    await client.fleet.dispatch(ZONE, engine="sqlite")
    assert len((await _hello(anonymous, _agent(first, source), first["key"]))["assignments"]) == 1

    clock.advance(899)  # within the lease (fleet.lease_seconds = 900): still claimed
    assert (await _hello(anonymous, _agent(second, source), second["key"]))["assignments"] == []
    clock.advance(2)
    assert (await client.fleet.health())["zones"][ZONE]["expired_claims"] == 1
    reclaimed = await _hello(anonymous, _agent(second, source), second["key"])
    assert len(reclaimed["assignments"]) == 1


# -- enrolment -----------------------------------------------------------------------


async def test_a_token_is_redeemed_once_and_the_zone_is_the_tokens(
    client: AsyncClient, anonymous: AsyncClient
) -> None:
    issued = await client.fleet.issue_token(ZONE, name="eu-01")
    assert issued["token"].startswith("pft_") and issued["zone"] == ZONE
    enrolled = await anonymous.fleet.enrol(
        issued["token"], name="eu-01", version="1", capabilities={"engines": ["sqlite"]}
    )
    assert enrolled["zone"] == ZONE
    with pytest.raises(prama.UnauthorisedError, match="already been used"):
        await anonymous.fleet.enrol(issued["token"], name="again", version="1", capabilities={})
    with pytest.raises(prama.UnauthorisedError, match="not one this server issued"):
        await anonymous.fleet.enrol("pft_made-up", name="x", version="1", capabilities={})
    # One agent came of it, not two.
    assert [a["name"] for a in await client.fleet.agents()] == ["eu-01"]


async def test_an_expired_token_is_refused_and_a_fresh_one_is_not(
    app: Any, client: AsyncClient, anonymous: AsyncClient
) -> None:
    clock = ManualClock(datetime(2026, 9, 30, 6, 0, tzinfo=UTC))
    app.state.clock = clock
    stale = await client.fleet.issue_token(ZONE, hours=1)
    fresh = await client.fleet.issue_token(ZONE, hours=3)
    clock.advance(2 * 3600)
    with pytest.raises(prama.UnauthorisedError, match="expired"):
        await anonymous.fleet.enrol(stale["token"], name="late", version="1", capabilities={})
    assert (await anonymous.fleet.enrol(fresh["token"], name="ok", version="1", capabilities={}))[
        "agent_id"
    ]


async def test_issuing_a_token_takes_the_admin_scope(
    client: AsyncClient, started_database: Database, tenant_id: str
) -> None:
    reader = client.as_key(
        await issue_key(started_database, tenant_id, principal="rita", scopes=["control:read"])
    )
    with pytest.raises(prama.ForbiddenError):
        await reader.fleet.issue_token(ZONE)
    with pytest.raises(prama.ForbiddenError):
        await reader.fleet.dispatch(ZONE, engine="sqlite")
    await reader.close()


# -- trust ---------------------------------------------------------------------------


async def test_a_wrong_signature_is_refused_and_the_right_one_is_not(
    client: AsyncClient, anonymous: AsyncClient, source: Path
) -> None:
    enrolled = await _enrol(client, anonymous, "eu-01")
    message, _ = _agent(enrolled, source).hello()
    refused = await anonymous.fleet.hello(message.to_dict(), key=b"\x00" * 32)
    assert "not signed by that agent's key" in refused["reason"]
    # A signature over something else is as wrong as a wrong key.
    tampered = {**message.to_dict(), "free_slots": 99}
    signed_original = await anonymous.fleet.hello(
        message.to_dict(), key=bytes.fromhex(enrolled["key"])
    )
    assert "reason" not in signed_original
    forged = await anonymous._transport.call(  # one message's signature on another
        Call(
            "POST",
            "/fleet/hello",
            json_body=tampered,
            headers={
                "X-Prama-Agent": enrolled["agent_id"],
                "X-Prama-Signature": sign(bytes.fromhex(enrolled["key"]), message.to_dict()),
            },
        )
    )
    assert "not signed" in forged["reason"]
    unknown = await anonymous.fleet.hello(
        {**message.to_dict(), "agent_id": "01NOSUCHAGENT0000000000000"}, key=b"k"
    )
    assert "does not know that agent" in unknown["reason"]


async def test_suspension_waits_and_revocation_is_permanent(
    client: AsyncClient, anonymous: AsyncClient, source: Path
) -> None:
    enrolled = await _enrol(client, anonymous, "eu-01")
    agent = _agent(enrolled, source)

    assert (await client.fleet.suspend(enrolled["agent_id"]))["state"] == "suspended"
    waiting = response_from_dict(await _hello(anonymous, agent, enrolled["key"]))
    assert waiting.is_refusal and waiting.permanent is False  # type: ignore[union-attr]
    assert agent.apply(waiting) is True  # keep running, keep spooling

    await client.fleet.resume(enrolled["agent_id"])
    assert isinstance(response_from_dict(await _hello(anonymous, agent, enrolled["key"])), Receipt)

    assert (await client.fleet.revoke(enrolled["agent_id"]))["state"] == "revoked"
    stopped = response_from_dict(await _hello(anonymous, agent, enrolled["key"]))
    assert stopped.is_refusal and stopped.permanent is True  # type: ignore[union-attr]
    assert agent.apply(stopped) is False
    report, _ = agent.report()
    refused = await anonymous.fleet.report(report.to_dict(), key=bytes.fromhex(enrolled["key"]))
    assert refused["permanent"] is True and "revoked" in refused["reason"]
    with pytest.raises(prama.ConflictError, match="not reinstated"):
        await client.fleet.resume(enrolled["agent_id"])


# -- the zone boundary ---------------------------------------------------------------


async def test_evidence_about_work_never_assigned_to_the_zone_is_not_recorded(
    client: AsyncClient,
    anonymous: AsyncClient,
    started_database: Database,
    tenant_id: str,
    source: Path,
) -> None:
    await _activate(started_database, tenant_id)
    enrolled = await _enrol(client, anonymous, "eu-01")
    await client.fleet.dispatch(ZONE, engine="sqlite")
    agent = _agent(enrolled, source)
    (sent,) = (await _hello(anonymous, agent, enrolled["key"]))["assignments"]
    record = agent.run(Assignment.from_dict(sent)).record
    assert record is not None

    stray = dataclasses.replace(record, plan_id="ir:sha256:" + "0" * 64, sequence=0)
    counted = dataclasses.replace(record, sequence=1)
    answer = await anonymous.fleet.report(
        Report(agent_id=enrolled["agent_id"], records=(stray, counted)).to_dict(),
        key=bytes.fromhex(enrolled["key"]),
    )
    assert answer["accepted_through"] == 1
    assert [r["sequence"] for r in answer["rejected"]] == [0]
    assert "never assigned" in answer["rejected"][0]["reason"]
    # The counterfactual beside it: the record about assigned work is recorded.
    (only,) = (await client.evidence.list())["items"]
    assert only["plan_id"] == record.plan_id


async def test_one_estate_never_sees_anothers_fleet(
    client: AsyncClient,
    anonymous: AsyncClient,
    started_database: Database,
    tenant_id: str,
    source: Path,
) -> None:
    async with started_database.unit_of_work() as uow:
        rival = uow.tenants.create(slug="rival-bank", display_name="Rival Bank")
        await uow.flush()
        rival_id = str(rival.id)
    theirs = client.as_key(await issue_key(started_database, rival_id, principal="mallory"))
    their_control = await _activate(started_database, rival_id)

    ours = await _enrol(client, anonymous, "eu-01")
    their_agent = await _enrol(theirs, anonymous, "their-01")  # the same zone name
    await theirs.fleet.dispatch(ZONE, engine="sqlite")

    # Our agent, in a zone of the same name, is given none of their work.
    receipt = await _hello(anonymous, _agent(ours, source), ours["key"])
    assert receipt["assignments"] == []
    # Theirs is, which is the counterfactual that makes the line above mean something.
    got = await _hello(anonymous, _agent(their_agent, source), their_agent["key"])
    assert [Assignment.from_dict(a).plan["control_id"] for a in got["assignments"]] == [
        their_control
    ]

    assert [a["name"] for a in await client.fleet.agents()] == ["eu-01"]
    assert [a["name"] for a in await theirs.fleet.agents()] == ["their-01"]
    with pytest.raises(prama.NotFoundError):
        await theirs.fleet.revoke(ours["agent_id"])
    assert (await client.fleet.health())["zones"] == {
        ZONE: {"queued": 0, "claimed": 0, "expired_claims": 0, "unassignable": 0}
    }

    # Our agent reporting on their plan records nothing in either ledger.
    their_record = _agent(their_agent, source).run(Assignment.from_dict(got["assignments"][0]))
    assert their_record.record is not None
    answer = await anonymous.fleet.report(
        Report(
            agent_id=ours["agent_id"],
            records=(dataclasses.replace(their_record.record, sequence=0),),
        ).to_dict(),
        key=bytes.fromhex(ours["key"]),
    )
    assert "never assigned" in answer["rejected"][0]["reason"]
    assert (await client.evidence.list())["items"] == []
    assert (await theirs.evidence.list())["items"] == []
    await theirs.close()


# -- health --------------------------------------------------------------------------


async def test_health_names_what_nothing_can_run_and_the_gaps_agents_report(
    client: AsyncClient, anonymous: AsyncClient, control_id: str, source: Path
) -> None:
    # No agent in the zone yet: queued, and said to be unassignable at once.
    dispatched = await client.fleet.dispatch(ZONE, engine="sqlite")
    (hole,) = dispatched["unassignable"]
    assert hole["queued"] is True and "no active agent" in hole["reasons"][0]

    # An agent that has only duckdb is told why it gets nothing.
    issued = await client.fleet.issue_token(ZONE)
    duck = await anonymous.fleet.enrol(
        issued["token"], name="duck", version="1", capabilities={"engines": ["duckdb"]}
    )
    agent = Agent(
        duck["agent_id"],
        bytes.fromhex(duck["key"]),
        executor=_executor(source),
        residency=ResidencyPolicy(zone=ZONE, samples=SampleDisposition.MASK, may_send=("id",)),
        capabilities=AgentCapabilities(engines=("duckdb",)),
    )
    receipt = await _hello(anonymous, agent, duck["key"])
    assert receipt["assignments"] == []
    assert "targets sqlite" in receipt["unassignable"][0]["reasons"][0]
    health = await client.fleet.health()
    assert health["zones"][ZONE]["unassignable"] == 1
    assert "duck: " in health["unassignable"][0]["reasons"][0]

    gap = Gap(
        first_sequence=0,
        last_sequence=2,
        dropped_at=datetime(2026, 9, 30, 5, 0, tzinfo=UTC),
        reason="spool full",
    )
    message = Report(agent_id=duck["agent_id"], gaps=(gap,))
    for _ in range(2):  # delivered twice, kept once
        await anonymous.fleet.report(message.to_dict(), key=bytes.fromhex(duck["key"]))
    (kept,) = (await client.fleet.health())["gaps"]
    assert kept["count"] == 3 and kept["reason"] == "spool full"
    assert "3 finding(s) lost" in (await client.fleet.health())["summary"]


async def test_health_names_an_agent_that_has_gone_quiet(
    app: Any, client: AsyncClient, anonymous: AsyncClient
) -> None:
    clock = ManualClock(datetime(2026, 9, 30, 6, 0, tzinfo=UTC))
    app.state.clock = clock
    enrolled = await _enrol(client, anonymous, "eu-01")
    assert (await client.fleet.health())["stale"] == []
    clock.advance(16 * 60)
    (quiet,) = (await client.fleet.health())["stale"]
    assert quiet["agent_id"] == enrolled["agent_id"]
