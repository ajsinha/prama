"""Learning from what people decided, and proving it helped.

`FR-LRN-001`…`010`, and `RQ9`: measured uplift against a frozen-model control
arm. The loop itself is the easy part — every decision a reviewer makes is a
label, and re-ranking on labels is arithmetic. The hard part is knowing whether
it worked.

**Without a control arm, an improving metric proves nothing.** Precision rising
from 0.71 to 0.86 over a quarter is consistent with the loop working, and
equally consistent with the estate maturing, the worst feeds being fixed, a
seasonal quiet period, or reviewers becoming more generous as they get tired.
Every one of those produces the same graph, and a system that shows the graph
and claims the credit is doing marketing.

**The control arm must be a random holdout of the same stream**, not "the old
way, elsewhere". Running the frozen model on different datasets measures the
datasets. Running it on last quarter measures the quarter. The only comparison
that isolates the loop is: the same population, at the same time, split at
random, with one side ranked by a model that stopped learning on a stated date.

**Assignment is deterministic, not sampled.** Hashing the item's identity means
the same item is always on the same side, so a re-run of a period reproduces
the experiment exactly — and an item cannot drift between arms when it is
re-proposed, which would contaminate both.

**The holdout costs something, and the cost is stated.** Ten percent of
proposals ranked by a model that stopped improving is ten percent of reviewers'
time spent worse than it could be. That is the price of knowing, and a system
that hides it is one where somebody eventually turns the experiment off without
understanding what they are giving up.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import math
from collections.abc import Sequence
from typing import Any


class Arm(enum.Enum):
    """Which model ranked this item."""

    #: Ranked by the model that keeps learning.
    TREATMENT = "treatment"
    #: Ranked by a model frozen on a stated date. The only thing that makes
    #: the treatment's numbers mean anything.
    CONTROL = "control"

    @property
    def learns(self) -> bool:
        return self is Arm.TREATMENT


class Outcome(enum.Enum):
    """What the reviewer did, which is the label."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    #: Neither yet. Counted separately, because treating unreviewed items as
    #: rejected understates both arms and treating them as accepted overstates
    #: both, and the bias is not equal between arms when one surfaces more
    #: items than the other.
    PENDING = "pending"


@dataclasses.dataclass(frozen=True, slots=True)
class Decision:
    """One reviewed item: what was proposed, how it ranked, what happened."""

    identity: str
    arm: Arm
    outcome: Outcome
    #: Where it appeared in the queue. The thing the loop is trying to improve:
    #: a model that ranks the accepted things higher is a better model, and
    #: precision alone cannot see that.
    rank: int = 0
    at: str = ""
    rule: str = ""

    @property
    def is_reviewed(self) -> bool:
        return self.outcome is not Outcome.PENDING

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "arm": self.arm.value,
            "outcome": self.outcome.value,
            "rank": self.rank,
            "at": self.at,
            "rule": self.rule,
        }


def assign(identity: str, *, holdout: float = 0.1, salt: str = "prama") -> Arm:
    """Which arm an item belongs to, decided by its identity.

    Deterministic rather than sampled, so a re-run of a period reproduces the
    experiment exactly and an item cannot drift between arms when it is
    re-proposed — which would contaminate both sides at once and in opposite
    directions.
    """
    digest = hashlib.sha256(f"{salt}:{identity}".encode()).hexdigest()
    position = int(digest[:8], 16) / 0xFFFFFFFF
    return Arm.CONTROL if position < holdout else Arm.TREATMENT


@dataclasses.dataclass(frozen=True, slots=True)
class ArmResult:
    """One arm's performance over a period."""

    arm: Arm
    surfaced: int = 0
    reviewed: int = 0
    accepted: int = 0
    #: Mean rank of the accepted items. Lower is better, and it is the measure
    #: that sees an improvement precision cannot: a model that surfaces the
    #: same things in a better order has helped, and its precision is
    #: unchanged.
    mean_accepted_rank: float = 0.0

    @property
    def precision(self) -> float | None:
        return self.accepted / self.reviewed if self.reviewed else None

    @property
    def pending(self) -> int:
        return self.surfaced - self.reviewed

    def describe(self) -> str:
        if self.precision is None:
            return f"{self.arm.value}: {self.surfaced} surfaced, none reviewed yet"
        return (
            f"{self.arm.value}: {self.accepted} of {self.reviewed} reviewed were "
            f"accepted ({self.precision:.0%}), mean accepted rank "
            f"{self.mean_accepted_rank:.1f}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "arm": self.arm.value,
            "surfaced": self.surfaced,
            "reviewed": self.reviewed,
            "accepted": self.accepted,
            "pending": self.pending,
            "precision": round(self.precision, 4) if self.precision is not None else None,
            "mean_accepted_rank": round(self.mean_accepted_rank, 2),
            "summary": self.describe(),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Uplift:
    """Whether the loop helped, and whether the answer is trustworthy yet."""

    treatment: ArmResult
    control: ArmResult
    #: Difference in precision. The headline, and meaningless without the
    #: interval below it.
    difference: float = 0.0
    #: A two-proportion interval on that difference. Reported because a
    #: difference of five points on ninety reviews is noise, and publishing it
    #: as a result is how a learning loop acquires a reputation for claiming
    #: things.
    low: float = 0.0
    high: float = 0.0
    #: What the holdout cost: reviews spent on the frozen arm.
    holdout_cost: int = 0

    @property
    def is_significant(self) -> bool:
        """Whether the interval excludes zero.

        The only form in which "the loop is working" is a claim rather than a
        hope.
        """
        return self.low > 0 or self.high < 0

    @property
    def is_measurable(self) -> bool:
        return self.treatment.reviewed >= 30 and self.control.reviewed >= 30

    def describe(self) -> str:
        if not self.is_measurable:
            return (
                f"not measurable yet: {self.treatment.reviewed} treatment and "
                f"{self.control.reviewed} control reviews, and an interval on this "
                f"much data is wider than any effect worth claiming"
            )
        direction = "better" if self.difference > 0 else "worse"
        head = (
            f"the learning arm is {abs(self.difference):.1%} {direction} on precision "
            f"({self.low:+.1%} to {self.high:+.1%})"
        )
        if not self.is_significant:
            head += (
                ", and the interval covers zero — which is not evidence the loop is "
                "working, however encouraging the point estimate looks"
            )
        rank_gain = self.control.mean_accepted_rank - self.treatment.mean_accepted_rank
        if abs(rank_gain) > 0.5:
            head += (
                f". It also puts accepted items {abs(rank_gain):.1f} places "
                f"{'higher' if rank_gain > 0 else 'lower'} in the queue, which "
                f"precision alone cannot see"
            )
        head += (
            f". The holdout cost {self.holdout_cost} reviews ranked by a model that "
            f"stopped learning, which is the price of knowing any of this"
        )
        return head

    def to_dict(self) -> dict[str, Any]:
        return {
            "treatment": self.treatment.to_dict(),
            "control": self.control.to_dict(),
            "difference": round(self.difference, 6),
            "low": round(self.low, 6),
            "high": round(self.high, 6),
            "significant": self.is_significant,
            "measurable": self.is_measurable,
            "holdout_cost": self.holdout_cost,
            "summary": self.describe(),
        }


def measure(decisions: Sequence[Decision]) -> Uplift:
    """Compare the two arms over the same period, with an interval."""
    treatment = _summarise(Arm.TREATMENT, decisions)
    control = _summarise(Arm.CONTROL, decisions)

    if treatment.precision is None or control.precision is None:
        return Uplift(treatment=treatment, control=control, holdout_cost=control.reviewed)

    difference = treatment.precision - control.precision
    low, high = _difference_interval(
        treatment.accepted, treatment.reviewed, control.accepted, control.reviewed
    )
    return Uplift(
        treatment=treatment,
        control=control,
        difference=difference,
        low=low,
        high=high,
        holdout_cost=control.reviewed,
    )


def _summarise(arm: Arm, decisions: Sequence[Decision]) -> ArmResult:
    members = [item for item in decisions if item.arm is arm]
    reviewed = [item for item in members if item.is_reviewed]
    accepted = [item for item in reviewed if item.outcome is Outcome.ACCEPTED]
    return ArmResult(
        arm=arm,
        surfaced=len(members),
        reviewed=len(reviewed),
        accepted=len(accepted),
        mean_accepted_rank=(
            sum(item.rank for item in accepted) / len(accepted) if accepted else 0.0
        ),
    )


def _difference_interval(
    accepted_a: int, reviewed_a: int, accepted_b: int, reviewed_b: int
) -> tuple[float, float]:
    """A 95% interval on the difference between two proportions.

    Normal approximation, which is adequate here and stated as such: both arms
    carry dozens of reviews by the time anybody looks, and a method that is
    exact at n=3 would not change a decision anybody makes at n=300.
    """
    if not reviewed_a or not reviewed_b:
        return 0.0, 0.0
    p_a = accepted_a / reviewed_a
    p_b = accepted_b / reviewed_b
    variance = p_a * (1 - p_a) / reviewed_a + p_b * (1 - p_b) / reviewed_b
    spread = 1.959963984540054 * math.sqrt(max(variance, 0.0))
    difference = p_a - p_b
    return difference - spread, difference + spread


# ---------------------------------------------------------------------------
# Promotion
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class Promotion:
    """Whether to move the frozen model forward, and why."""

    should_promote: bool
    reason: str
    uplift: Uplift

    def to_dict(self) -> dict[str, Any]:
        return {
            "should_promote": self.should_promote,
            "reason": self.reason,
            "uplift": self.uplift.to_dict(),
        }


def consider(uplift: Uplift, *, minimum_gain: float = 0.03) -> Promotion:
    """Decide whether the learning arm has earned the control's place.

    Promotion here means refreezing: the control becomes the current model, and
    the experiment starts again from a higher baseline. Doing it on a point
    estimate rather than an interval is how a loop that is doing nothing
    accumulates a series of promotions and a story about continuous
    improvement.
    """
    if not uplift.is_measurable:
        return Promotion(
            should_promote=False,
            reason=(
                "not enough reviews on both arms; an interval on this much data is "
                "wider than any effect worth acting on"
            ),
            uplift=uplift,
        )
    if not uplift.is_significant:
        return Promotion(
            should_promote=False,
            reason=(
                f"the difference is {uplift.difference:+.1%} and the interval covers "
                f"zero. Promoting on a point estimate is how a loop that is doing "
                f"nothing accumulates a series of promotions"
            ),
            uplift=uplift,
        )
    if uplift.difference < 0:
        # Checked *before* the small-gain branch. The other order reported a
        # significant -22% regression as "a real but small gain", which is
        # exactly backwards and would hide a feedback loop teaching the model
        # the wrong thing.
        return Promotion(
            should_promote=False,
            reason=(
                f"the learning arm is significantly *worse* ({uplift.difference:+.1%}). "
                f"Something in the feedback is teaching it the wrong thing, and the "
                f"labels are the place to look"
            ),
            uplift=uplift,
        )
    if uplift.difference < minimum_gain:
        return Promotion(
            should_promote=False,
            reason=(
                f"the gain is real but small ({uplift.difference:+.1%}), below the "
                f"{minimum_gain:.0%} that makes refreezing worth restarting the "
                f"experiment for"
            ),
            uplift=uplift,
        )
    return Promotion(
        should_promote=True,
        reason=(
            f"{uplift.difference:+.1%} precision, interval {uplift.low:+.1%} to "
            f"{uplift.high:+.1%}, on {uplift.treatment.reviewed} and "
            f"{uplift.control.reviewed} reviews"
        ),
        uplift=uplift,
    )
