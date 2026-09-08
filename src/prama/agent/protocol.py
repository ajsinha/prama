"""What crosses between an agent and the control plane, and in which direction.

**The agent always initiates.** Every exchange is the agent calling out; the
control plane never calls in. This single constraint is what makes the design
installable in a bank, and it is worth more than any feature: no inbound
firewall rule, no port open in a secure zone, no VPN, no jump host, and no
conversation with a network security team that ends in a year of waiting.

It costs something. Work reaches an agent when the agent next asks, so there is
latency between deciding and doing, and the control plane cannot make anything
happen on demand. Both are acceptable and neither is hidden: the poll interval
is declared, and "the control plane cannot reach into your network" is a
property a bank pays for rather than a limitation it tolerates.

Four messages, and no more, because every message is a thing to version, secure
and reason about:

* ``Hello`` — the agent says who it is and what it can do. Answered with the
  work it should take.
* ``Report`` — the agent sends findings and any gaps in them.
* ``Receipt`` — the control plane says what it accepted, so the agent can let
  go of it.
* ``Refusal`` — the control plane declines, and says why, so an agent that has
  been revoked stops rather than retrying forever.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import Any

from prama.agent.capability import AgentCapabilities
from prama.agent.spool import Gap
from prama.core.pjson import dumps
from prama.evidence.record import EvidenceRecord


@dataclasses.dataclass(frozen=True, slots=True)
class Assignment:
    """One piece of work, as it reaches an agent.

    Carries the plan and the compiled query, not a control to be re-derived.
    An agent that compiled its own SQL would be a second compiler in the
    estate, and two compilers is how the same control comes to mean two things.
    """

    plan_id: str
    dataset: str
    binding: str
    engine: str
    #: The SQL, already compiled by the control plane for this engine.
    metric_query: str
    metric_names: tuple[str, ...] = ()
    sample_query: str = ""
    parameters: dict[str, str] = dataclasses.field(default_factory=dict)
    #: The plan, so the agent can judge the metrics with the same threshold the
    #: control plane would have used, and so the evidence names it.
    plan: dict[str, Any] = dataclasses.field(default_factory=dict)
    due_at: datetime | None = None
    priority: str = "normal"

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "dataset": self.dataset,
            "binding": self.binding,
            "engine": self.engine,
            "metric_query": self.metric_query,
            "metric_names": list(self.metric_names),
            "sample_query": self.sample_query,
            "parameters": self.parameters,
            "plan": self.plan,
            "due_at": self.due_at.isoformat() if self.due_at else None,
            "priority": self.priority,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Hello:
    """The agent announcing itself and asking for work."""

    agent_id: str
    version: str = ""
    capabilities: AgentCapabilities = dataclasses.field(default_factory=AgentCapabilities)
    #: How many findings the agent is holding. The control plane needs this to
    #: notice a fleet that has been buffering for a day, which is a different
    #: problem from a fleet that is quiet.
    pending_findings: int = 0
    #: How much work it can take now, given what it is already doing.
    free_slots: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "version": self.version,
            "capabilities": self.capabilities.to_dict(),
            "pending_findings": self.pending_findings,
            "free_slots": self.free_slots,
        }

    def signable(self) -> str:
        return dumps(self.to_dict(), sort_keys=True)


@dataclasses.dataclass(frozen=True, slots=True)
class Report:
    """Findings travelling from the agent to the control plane."""

    agent_id: str
    records: tuple[EvidenceRecord, ...] = ()
    gaps: tuple[Gap, ...] = ()
    #: The zone's residency policy as the agent applied it, so the control
    #: plane records *why* a finding has no samples rather than inferring it.
    residency: dict[str, Any] = dataclasses.field(default_factory=dict)

    @property
    def last_sequence(self) -> int:
        return self.records[-1].sequence if self.records else -1

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "records": [r.to_dict() for r in self.records],
            "gaps": [g.to_dict() for g in self.gaps],
            "residency": self.residency,
        }

    def signable(self) -> str:
        return dumps(self.to_dict(), sort_keys=True)


@dataclasses.dataclass(frozen=True, slots=True)
class Receipt:
    """The control plane confirming what it has, and what it wants next."""

    accepted_through: int = -1
    duplicates: int = 0
    rejected: tuple[tuple[int, str], ...] = ()
    assignments: tuple[Assignment, ...] = ()
    #: Controls nothing in the fleet can run. Sent back rather than dropped,
    #: so an agent's operator sees the hole in coverage that their zone has.
    unassignable: tuple[dict[str, Any], ...] = ()
    #: How long to wait before calling again.
    poll_after_seconds: int = 30

    @property
    def is_refusal(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted_through": self.accepted_through,
            "duplicates": self.duplicates,
            "rejected": [{"sequence": s, "reason": r} for s, r in self.rejected],
            "assignments": [a.to_dict() for a in self.assignments],
            "unassignable": list(self.unassignable),
            "poll_after_seconds": self.poll_after_seconds,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Refusal:
    """The control plane declining to deal with this agent, and why.

    A refusal is terminal for the agent's current identity. It stops rather
    than retrying, because an agent that has been revoked and keeps calling is
    a revoked agent generating load and log noise for as long as it is left
    running.
    """

    reason: str
    remedy: str = ""
    #: Whether the agent should stop entirely or wait and try again. Revocation
    #: is permanent; a control plane that is merely busy is not.
    permanent: bool = True

    @property
    def is_refusal(self) -> bool:
        return True

    def to_dict(self) -> dict[str, Any]:
        return {"reason": self.reason, "remedy": self.remedy, "permanent": self.permanent}


#: What a call returns. Union rather than an optional field on Receipt, so a
#: caller cannot forget to check whether it was refused.
Response = Receipt | Refusal
