"""The control plane's side of the conversation with a fleet of agents.

Its job is narrow and its refusals matter more than its acceptances.

**It assigns by zone, never by request.** An agent asks for work; it does not
ask for particular work. A compromised agent in the reporting zone cannot
obtain the trading estate's controls, because what it gets is decided here from
its enrolled zone rather than from anything it said.

**It verifies before it believes.** Every report is signed and every signature
is checked against a registry that knows which agents are still trusted. A
revoked agent's correctly-signed findings are rejected, because verifying a
signature and then accepting the finding anyway is how a revocation list
becomes decorative.

**It deduplicates rather than promising exactly-once.** Delivery over an
unreliable network is at-least-once; an agent that sent a batch and heard
nothing must send it again. The same finding therefore arrives twice, and the
second is recognised by its sequence and dropped. Claiming exactly-once would
mean an agent somewhere quietly losing evidence to preserve the claim.

**It reports what nothing can run.** A control no agent in its zone can execute
is a hole in the estate's coverage, and it is returned to the agent's operator
and kept for the coverage report. A platform that reports coverage while
knowing part of it never ran is reporting a number it knows to be wrong.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from prama.agent.capability import Unassignable, fits
from prama.agent.identity import AgentRegistry, AgentState
from prama.agent.protocol import Assignment, Hello, Receipt, Refusal, Report, Response
from prama.core.clock import Clock, SystemClock
from prama.core.log import get_logger
from prama.evidence.ledger import Ledger
from prama.ir.model import ControlPlan

_log = get_logger(__name__)


@dataclasses.dataclass(slots=True)
class ZoneWork:
    """The queue of assignments waiting for a zone.

    Held per zone rather than per agent so an agent that dies does not take its
    work with it: whatever it had not started is still here for whichever agent
    asks next.
    """

    zone: str
    queue: list[tuple[ControlPlan, Assignment]] = dataclasses.field(default_factory=list)
    unassignable: list[Unassignable] = dataclasses.field(default_factory=list)


class Coordinator:
    """Accepts findings from agents and hands out work."""

    def __init__(
        self,
        registry: AgentRegistry,
        *,
        ledger: Ledger | None = None,
        clock: Clock | None = None,
        poll_seconds: int = 30,
    ) -> None:
        self._registry = registry
        # `if None`, not `or`: a Ledger defines __len__, so an empty one
        # passed in is falsy and would be silently replaced — the caller would
        # hold a ledger that never fills.
        self._ledger = Ledger() if ledger is None else ledger
        self._clock = clock or SystemClock()
        self._poll = poll_seconds
        self._work: dict[str, ZoneWork] = {}
        #: The highest sequence accepted from each agent, so a redelivery is
        #: recognised rather than duplicated.
        self._accepted: dict[str, int] = {}

    @property
    def ledger(self) -> Ledger:
        return self._ledger

    # -- work in --------------------------------------------------------

    def enqueue(self, zone: str, plan: ControlPlan, assignment: Assignment) -> None:
        self._work.setdefault(zone, ZoneWork(zone=zone)).queue.append((plan, assignment))

    def unassignable(self, zone: str) -> list[Unassignable]:
        work = self._work.get(zone)
        return list(work.unassignable) if work else []

    # -- the conversation --------------------------------------------------

    def hello(self, message: Hello, signature: str) -> Response:
        """An agent announcing itself and asking for work."""
        refusal = self._authenticate(message.agent_id, message.signable(), signature)
        if refusal is not None:
            return refusal
        agent = self._registry.seen(message.agent_id)
        assert agent is not None
        assignments, unassignable = self._assign(agent.zone, message)
        return Receipt(
            accepted_through=self._accepted.get(message.agent_id, -1),
            assignments=tuple(assignments),
            unassignable=tuple(u.to_dict() for u in unassignable),
            poll_after_seconds=self._poll,
        )

    def report(self, message: Report, signature: str) -> Response:
        """Findings arriving from an agent."""
        refusal = self._authenticate(message.agent_id, message.signable(), signature)
        if refusal is not None:
            return refusal
        self._registry.seen(message.agent_id)

        highest = self._accepted.get(message.agent_id, -1)
        duplicates = 0
        rejected: list[tuple[int, str]] = []
        for record in message.records:
            if record.sequence <= highest:
                # Already have it. At-least-once delivery means this is the
                # ordinary case after a lost acknowledgement, not an anomaly.
                duplicates += 1
                continue
            if record.sequence != highest + 1 and highest >= 0:
                # A hole. Recorded and the record still kept: refusing it would
                # lose evidence that did arrive to punish evidence that did not.
                rejected.append(
                    (
                        record.sequence,
                        f"expected sequence {highest + 1}; {record.sequence - highest - 1} "
                        f"finding(s) from this agent are missing",
                    )
                )
            self._ledger.append(record)
            highest = record.sequence
        self._accepted[message.agent_id] = highest

        for gap in message.gaps:
            # A gap the agent already knows about — its spool overflowed. It
            # belongs in the same channel as the evidence, not only in a log.
            _log.warning("agent %s reported a gap: %s", message.agent_id, gap.render())

        return Receipt(
            accepted_through=highest,
            duplicates=duplicates,
            rejected=tuple(rejected),
            poll_after_seconds=self._poll,
        )

    # -- internals ---------------------------------------------------------

    def _authenticate(self, agent_id: str, payload: str, signature: str) -> Refusal | None:
        agent = self._registry.get(agent_id)
        if agent is None:
            return Refusal(
                reason="this control plane does not know that agent",
                remedy="Enrol the agent again with a fresh token.",
            )
        if agent.state is AgentState.REVOKED:
            return Refusal(
                reason="this agent has been revoked",
                remedy=(
                    "Stop the agent. If it should be running, enrol it again — a "
                    "revoked identity is not reinstated."
                ),
            )
        if agent.state is AgentState.SUSPENDED:
            # Before the signature check, and deliberately. The registry
            # refuses to verify for a suspended agent, so checking the
            # signature first would tell its operator their credential is
            # wrong — sending them to reissue a key that was never the problem.
            return Refusal(
                reason="this agent is suspended",
                remedy=(
                    "Resume it when whatever caused the suspension is resolved. Keep it "
                    "running meanwhile: it will spool its findings and deliver them."
                ),
                permanent=False,
            )
        if not self._registry.verify(agent_id, payload, signature):
            return Refusal(
                reason="the message was not signed by that agent's key",
                remedy="Check the agent's credential, or enrol the agent again.",
            )
        return None

    def _assign(self, zone: str, message: Hello) -> tuple[list[Assignment], list[Unassignable]]:
        work = self._work.get(zone)
        if work is None or not work.queue:
            return [], []
        taken: list[Assignment] = []
        remaining: list[tuple[ControlPlan, Assignment]] = []
        slots = max(0, min(message.free_slots, message.capabilities.max_concurrency))
        for plan, assignment in work.queue:
            fitness = fits(plan, message.capabilities, engine=assignment.engine)
            if not fitness.assignable:
                work.unassignable.append(
                    Unassignable(
                        plan_id=plan.plan_id,
                        dataset=plan.scope.dataset,
                        zone=zone,
                        reasons=fitness.reasons,
                        remedy=fitness.remedy,
                    )
                )
                continue
            if len(taken) < slots:
                taken.append(assignment)
            else:
                remaining.append((plan, assignment))
        work.queue = remaining
        return taken, list(work.unassignable)


def fleet_health(registry: AgentRegistry, *, after_minutes: int = 15) -> dict[str, Any]:
    """Which agents are talking, and which have gone quiet.

    Silence is reported rather than inferred from missing evidence. An agent
    that has died and an agent whose datasets are all clean produce the same
    absence of findings, and only one of them is a problem.
    """
    stale = registry.stale(after_minutes=after_minutes)
    agents = registry.all()
    return {
        "agents": len(agents),
        "active": sum(1 for a in agents if a.state is AgentState.ACTIVE),
        "suspended": sum(1 for a in agents if a.state is AgentState.SUSPENDED),
        "revoked": sum(1 for a in agents if a.state is AgentState.REVOKED),
        "silent": [a.to_dict() for a in stale],
        "summary": (
            f"{len(agents)} agent(s), {len(stale)} of them silent for more than "
            f"{after_minutes} minutes."
            if stale
            else f"{len(agents)} agent(s), all reporting."
        ),
    }
