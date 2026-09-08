"""What an agent can actually do, declared rather than discovered.

Agents in a bank upgrade on the bank's schedule, which is measured in quarters.
A control plane that assumed its fleet matched its own version would send a
plan using a construct half of them cannot execute, and would find out when the
runs failed — at night, in a zone nobody can log into.

So an agent declares what it supports and the control plane assigns only work
that fits. The declaration is the same vocabulary the connectors and the
backends already use, so a plan's requirements and an agent's abilities are
compared directly rather than through a translation nobody maintains.

The important case is the negative one. A control an agent cannot run is
**reported as unassignable**, with the reason, and never silently skipped.
Silently skipped work is the failure that makes a coverage report a lie: the
dashboard is green because nothing looked, and the gap is invisible precisely
where it matters most.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from prama.ir.model import IR_VERSION, ControlPlan


@dataclasses.dataclass(frozen=True, slots=True)
class AgentCapabilities:
    """What one agent can execute."""

    #: IR versions this agent understands, oldest first. An agent that
    #: supported only the newest would have to be upgraded in lockstep with the
    #: control plane, which is the thing this design exists to avoid.
    ir_versions: tuple[str, ...] = (IR_VERSION,)
    #: Query engines reachable from where this agent runs.
    engines: tuple[str, ...] = ()
    #: Connector plugin keys installed on this agent.
    connectors: tuple[str, ...] = ()
    #: Backend capabilities, in the vocabulary the dialects publish.
    pushdown: tuple[str, ...] = ()
    #: How much this agent may be given at once. Declared by whoever installed
    #: it, because they know what else the machine is doing.
    max_concurrency: int = 4
    #: What the agent will spend per cycle, in the scheduler's units.
    budget: float = 100.0
    #: Datasets this agent can reach at all. Empty means "anything in my zone",
    #: which is the ordinary case; naming them is for an agent deliberately
    #: confined to part of a zone.
    datasets: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "ir_versions": list(self.ir_versions),
            "engines": list(self.engines),
            "connectors": list(self.connectors),
            "pushdown": list(self.pushdown),
            "max_concurrency": self.max_concurrency,
            "budget": self.budget,
            "datasets": list(self.datasets),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> AgentCapabilities:
        return cls(
            ir_versions=tuple(payload.get("ir_versions") or (IR_VERSION,)),
            engines=tuple(payload.get("engines") or ()),
            connectors=tuple(payload.get("connectors") or ()),
            pushdown=tuple(payload.get("pushdown") or ()),
            max_concurrency=int(payload.get("max_concurrency", 4)),
            budget=float(payload.get("budget", 100.0)),
            datasets=tuple(payload.get("datasets") or ()),
        )


@dataclasses.dataclass(frozen=True, slots=True)
class Fitness:
    """Whether one plan can go to one agent, and why not."""

    assignable: bool
    reasons: tuple[str, ...] = ()
    remedy: str = ""

    def render(self) -> str:
        if self.assignable:
            return "assignable"
        return "; ".join(self.reasons)


def fits(plan: ControlPlan, capabilities: AgentCapabilities, *, engine: str = "") -> Fitness:
    """Whether this agent can run this plan.

    Every reason is collected rather than the first, because an agent short of
    three things needs upgrading once, not three times.
    """
    reasons: list[str] = []
    remedies: list[str] = []

    version = plan.to_dict().get("ir_version", IR_VERSION)
    if version not in capabilities.ir_versions:
        reasons.append(
            f"the plan is IR {version} and this agent understands "
            f"{', '.join(capabilities.ir_versions)}"
        )
        remedies.append("upgrade the agent, or keep the control on a version it knows")

    if engine and capabilities.engines and engine not in capabilities.engines:
        reasons.append(
            f"the control targets {engine} and this agent has "
            f"{', '.join(capabilities.engines) or 'no engine'}"
        )
        remedies.append(f"install {engine} beside the agent, or assign to one that has it")

    missing = sorted(set(plan.requires) - set(capabilities.pushdown))
    if capabilities.pushdown and missing:
        reasons.append(f"the control needs {', '.join(missing)}, which this agent lacks")
        remedies.append("run it where those are available")

    if capabilities.datasets and plan.scope.dataset not in capabilities.datasets:
        reasons.append(
            f"this agent is confined to {', '.join(capabilities.datasets)} and the "
            f"control is about {plan.scope.dataset}"
        )
        remedies.append("widen the agent's datasets, or assign the control elsewhere")

    return Fitness(
        assignable=not reasons,
        reasons=tuple(reasons),
        remedy="; ".join(remedies),
    )


@dataclasses.dataclass(frozen=True, slots=True)
class Unassignable:
    """A control nothing in the fleet can run.

    Kept as its own idea rather than folded into a log line. An estate where
    twelve controls are unassignable has a twelve-control hole in its coverage,
    and a platform that reports coverage without reporting the hole is
    reporting a number it knows to be wrong.
    """

    plan_id: str
    dataset: str
    zone: str
    reasons: tuple[str, ...] = ()
    remedy: str = ""

    def render(self) -> str:
        return (
            f"{self.dataset} ({self.plan_id[:22]}…) cannot run in {self.zone}: "
            f"{'; '.join(self.reasons)}" + (f"\n    → {self.remedy}" if self.remedy else "")
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "dataset": self.dataset,
            "zone": self.zone,
            "reasons": list(self.reasons),
            "remedy": self.remedy,
        }
