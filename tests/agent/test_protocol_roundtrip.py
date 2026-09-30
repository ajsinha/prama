"""Every agent protocol message survives JSON, byte for byte where it is signed.

A standalone agent and the server exchange these over HTTP. The server checks
an agent's HMAC over a report it has rebuilt from JSON, so the rebuilt report
must serialise exactly as the agent's did: a difference of one float's repr is
a correctly signed report refused.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from prama_kernel.agent.protocol import (
    Assignment,
    Hello,
    Receipt,
    Refusal,
    Report,
    response_from_dict,
)
from prama_kernel.agent.spool import Gap
from tests.agent.test_fleet import AgentRegistry, an_agent, an_assignment


def _through_json(payload: dict) -> dict:  # type: ignore[type-arg]
    return json.loads(json.dumps(payload))


def test_an_assignment_round_trips() -> None:
    _, assignment = an_assignment()
    assignment = Assignment.from_dict(
        {**assignment.to_dict(), "due_at": datetime(2026, 9, 30, 6, 30, tzinfo=UTC).isoformat()}
    )
    again = Assignment.from_dict(_through_json(assignment.to_dict()))
    assert again == assignment


def test_a_signed_report_verifies_after_the_wire() -> None:
    """The case that matters: the agent signs, JSON carries it, the server re-signs."""
    registry = AgentRegistry()
    identity, agent = an_agent(registry)
    _, assignment = an_assignment()
    outcome = agent.run(assignment)
    assert outcome.record is not None
    gap = Gap(3, 5, datetime(2026, 9, 30, tzinfo=UTC), "spool full")
    report = Report(agent_id=identity.agent_id, records=(outcome.record,), gaps=(gap,))
    signature = registry.sign_as(identity.agent_id, report.signable())

    rebuilt = Report.from_dict(_through_json(report.to_dict()))
    assert rebuilt.signable() == report.signable()
    assert registry.verify(identity.agent_id, rebuilt.signable(), signature)


def test_hello_receipt_and_refusal_round_trip() -> None:
    _, assignment = an_assignment()
    hello = Hello(agent_id="ag1", version="0.1.0", pending_findings=4, free_slots=2)
    assert Hello.from_dict(_through_json(hello.to_dict())).signable() == hello.signable()
    receipt = Receipt(
        accepted_through=7, duplicates=1, rejected=((8, "bad"),), assignments=(assignment,)
    )
    assert response_from_dict(_through_json(receipt.to_dict())) == receipt
    refusal = Refusal("revoked", remedy="enrol again", permanent=True)
    assert response_from_dict(_through_json(refusal.to_dict())) == refusal
