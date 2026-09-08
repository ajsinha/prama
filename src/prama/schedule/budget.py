"""Deciding what not to run, and saying so.

A control plane with more work than budget has to shed something. The question
is not whether — a system that never sheds simply queues until it is hours
behind and then sheds everything at once — but how, and how visibly.

The rule this file exists to enforce: **nothing is dropped silently**. A
deferred control is on the report, by name, with the reason and when it will
run instead. The alternative is the failure mode that makes a data quality
platform worthless: the dashboard is green because a third of the estate did not
run, and nobody can tell the difference between a control that passed and one
that never happened.

Shedding is by declared priority, and within a priority by cost, so the estate
gives up the most work for the least loss. Tier-one controls are never shed —
if the budget cannot cover them the budget is wrong, and that is a sentence
somebody needs to read rather than a queue that quietly grows.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
from datetime import datetime, timedelta
from typing import Any


class Priority(enum.Enum):
    """How much it matters that this runs now.

    Declared, not inferred from severity. A critical control on a dataset
    nobody reads until Friday is less urgent than a minor one on the feed that
    blocks the overnight batch, and only a person knows which is which.
    """

    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"

    @property
    def rank(self) -> int:
        return list(Priority).index(self)

    @property
    def may_be_shed(self) -> bool:
        """Whether the scheduler may decline to run this.

        Critical work is never shed. If the budget cannot cover it, the budget
        is wrong — and a scheduler that quietly dropped it would be answering a
        question about money with a decision about risk.
        """
        return self is not Priority.CRITICAL


@dataclasses.dataclass(frozen=True, slots=True)
class Candidate:
    """One piece of work the scheduler is considering."""

    identifier: str
    dataset: str
    priority: Priority = Priority.NORMAL
    #: What running it is expected to cost, in whatever unit the budget counts.
    #: Scans, rows, seconds — the scheduler does not care, as long as the
    #: budget and the estimates agree.
    cost: float = 1.0
    due_at: datetime | None = None
    #: How long it has already waited. A low-priority control deferred five
    #: times running is a different thing from one deferred once.
    deferrals: int = 0

    @property
    def is_starving(self) -> bool:
        """Whether this has been passed over often enough to be a problem.

        Priority scheduling starves the bottom of the queue by construction.
        Noticing is not optional: a control deferred every night for a month is
        a control that does not exist, and the coverage report should not go on
        counting it.
        """
        return self.deferrals >= 3


@dataclasses.dataclass(frozen=True, slots=True)
class Deferral:
    """Something not run, and why."""

    candidate: Candidate
    reason: str
    next_attempt: datetime | None = None

    def render(self) -> str:
        when = (
            f" Next attempt {self.next_attempt.isoformat(timespec='minutes')}."
            if self.next_attempt
            else ""
        )
        starving = (
            f" This is deferral {self.candidate.deferrals + 1} in a row for this control."
            if self.candidate.is_starving
            else ""
        )
        return (
            f"{self.candidate.identifier} on {self.candidate.dataset} "
            f"({self.candidate.priority.value}): {self.reason}.{when}{starving}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "identifier": self.candidate.identifier,
            "dataset": self.candidate.dataset,
            "priority": self.candidate.priority.value,
            "cost": self.candidate.cost,
            "deferrals": self.candidate.deferrals + 1,
            "starving": self.candidate.is_starving,
            "reason": self.reason,
            "next_attempt": self.next_attempt.isoformat() if self.next_attempt else None,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Allocation:
    """What the scheduler decided to run, and what it did not."""

    admitted: tuple[Candidate, ...] = ()
    deferred: tuple[Deferral, ...] = ()
    budget: float = 0.0
    spent: float = 0.0
    #: Set when critical work alone exceeded the budget. Not an error the
    #: scheduler can fix, and not one it may hide.
    over_committed: bool = False

    @property
    def headroom(self) -> float:
        return max(0.0, self.budget - self.spent)

    @property
    def starving(self) -> tuple[Deferral, ...]:
        return tuple(d for d in self.deferred if d.candidate.is_starving)

    def render(self) -> str:
        lines = [
            f"Running {len(self.admitted)} of {len(self.admitted) + len(self.deferred)}, "
            f"spending {self.spent:g} of a {self.budget:g} budget."
        ]
        if self.over_committed:
            lines.append(
                "The critical work alone exceeds the budget. It has been run anyway, "
                "because declining it would answer a question about money with a "
                "decision about risk — but the budget is wrong and somebody has to "
                "change one of the two."
            )
        if self.deferred:
            lines.append("")
            # By name, never as a count. A dashboard that reports "12 deferred"
            # is a dashboard nobody can act on.
            lines.append(f"{len(self.deferred)} deferred:")
            lines.extend(f"  {d.render()}" for d in self.deferred)
        if self.starving:
            lines.append("")
            lines.append(
                f"{len(self.starving)} of those have now been deferred three times or "
                f"more. A control deferred every night is a control that does not "
                f"exist, and the coverage report should stop counting it."
            )
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "admitted": [c.identifier for c in self.admitted],
            "deferred": [d.to_dict() for d in self.deferred],
            "budget": self.budget,
            "spent": self.spent,
            "headroom": self.headroom,
            "over_committed": self.over_committed,
            "starving": len(self.starving),
            "summary": self.render(),
        }


class BudgetPolicy:
    """Admits work up to a budget, and reports everything it does not."""

    def __init__(self, budget: float, *, retry_after_minutes: int = 60) -> None:
        self._budget = max(0.0, budget)
        self._retry = retry_after_minutes

    def allocate(self, candidates: list[Candidate], *, now: datetime) -> Allocation:
        """Choose what runs.

        Critical first and in full; then by priority, and within a priority by
        cost ascending — cheapest first, so the estate keeps the most controls
        for the budget it has. Within equal cost, whatever has been deferred
        longest goes first, which is the only thing standing between priority
        scheduling and permanent starvation at the bottom.
        """
        critical = [c for c in candidates if not c.priority.may_be_shed]
        rest = sorted(
            (c for c in candidates if c.priority.may_be_shed),
            key=lambda c: (c.priority.rank, -c.deferrals, c.cost, c.identifier),
        )
        admitted: list[Candidate] = list(critical)
        spent = sum(c.cost for c in critical)
        over = spent > self._budget

        deferred: list[Deferral] = []
        next_attempt = now + timedelta(minutes=self._retry)
        for candidate in rest:
            if spent + candidate.cost <= self._budget:
                admitted.append(candidate)
                spent += candidate.cost
                continue
            deferred.append(
                Deferral(
                    candidate=candidate,
                    reason=(
                        f"the budget has {max(0.0, self._budget - spent):g} left and this "
                        f"would cost {candidate.cost:g}"
                    ),
                    next_attempt=next_attempt,
                )
            )
        return Allocation(
            admitted=tuple(admitted),
            deferred=tuple(deferred),
            budget=self._budget,
            spent=spent,
            over_committed=over,
        )
