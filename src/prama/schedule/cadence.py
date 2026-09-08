"""How often to look, decided from what looking has found.

A fixed schedule is wrong in both directions at once. Checking a static
reference table every hour spends a year of scans to learn nothing; checking a
volatile ledger daily means a break is eight hours old before anybody hears.
Neither is a configuration mistake — the right cadence is a property of the
data, and the data is the only thing that knows it.

So the cadence adapts. Three rules govern it, and the third is the one that
makes the other two safe to have.

**Back off on stability.** A dataset that has passed many consecutive runs is
telling us we are looking too often. The interval widens, geometrically but
slowly, because a dataset that has been quiet for a month can still break
tomorrow.

**Return immediately on a failure.** Not gradually. A single failure resets the
interval to the floor, because the period just after a break is when the next
one is most likely and when somebody is most likely to be watching.

**Never past the declared bounds.** A tier-one dataset carrying a CDE has a
floor that no amount of quiet can widen, because the cost of finding out late
is not paid by the scheduler. The bounds are declared by a person; the cadence
moves between them.

And one property that is not a rule but decides whether any of this is
acceptable: **every change explains itself.** An adaptive system that cannot
say why it now checks something every four hours instead of every one is a
system nobody trusts, and the first time it is blamed for a late detection it
will be turned off. Each decision carries the sentence.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from typing import Any

#: How much wider the interval gets after a run of clean results. Slow on
#: purpose: doubling would take a daily check to fortnightly in four quiet
#: weeks, which is a different control from the one somebody approved.
BACKOFF_FACTOR = 1.5

#: Consecutive passes before the interval widens at all. Below this, a quiet
#: patch is not evidence of stability — it is a small sample.
PASSES_BEFORE_BACKOFF = 10

#: How many recent runs the policy looks at. Long enough to see a pattern,
#: short enough that a dataset which has changed character is not judged on how
#: it behaved last quarter.
WINDOW = 50


@dataclasses.dataclass(frozen=True, slots=True)
class CadenceBounds:
    """What a person declared, and what the policy may not cross.

    Both bounds are required rather than defaulted. A floor invented by the
    platform would be the platform deciding how late a bank may learn about a
    break, which is not the platform's decision to make.
    """

    floor_minutes: int
    ceiling_minutes: int
    #: Where a dataset starts before anything is known about it.
    initial_minutes: int = 0

    def __post_init__(self) -> None:
        from prama.core.errors import ValidationError

        if self.floor_minutes <= 0 or self.ceiling_minutes < self.floor_minutes:
            raise ValidationError(
                "the cadence bounds are impossible",
                remedy=(
                    "The floor must be positive and the ceiling at least the floor. "
                    "A dataset checked at most every hour and at least every ten "
                    "minutes has no schedule."
                ),
                context={"floor": self.floor_minutes, "ceiling": self.ceiling_minutes},
            )

    @property
    def start(self) -> int:
        return self.initial_minutes or self.floor_minutes

    def clamp(self, minutes: float) -> int:
        return int(max(self.floor_minutes, min(self.ceiling_minutes, _round_interval(minutes))))


@dataclasses.dataclass(frozen=True, slots=True)
class Observation:
    """What the recent runs found. The only input the policy has."""

    #: Most recent last, so a reader of a stored history sees it in time order.
    verdicts: tuple[str, ...] = ()

    @property
    def consecutive_passes(self) -> int:
        count = 0
        for verdict in reversed(self.verdicts):
            if verdict != "pass":
                break
            count += 1
        return count

    @property
    def recent_failures(self) -> int:
        return sum(1 for v in self.verdicts[-WINDOW:] if v in ("fail", "error"))

    @property
    def last_failed(self) -> bool:
        return bool(self.verdicts) and self.verdicts[-1] in ("fail", "error")

    @property
    def has_run(self) -> bool:
        return bool(self.verdicts)

    @property
    def indeterminate_streak(self) -> int:
        count = 0
        for verdict in reversed(self.verdicts):
            if verdict != "indeterminate":
                break
            count += 1
        return count


@dataclasses.dataclass(frozen=True, slots=True)
class Decision:
    """A cadence, and the sentence explaining it."""

    minutes: int
    reason: str
    #: What it was before, so a change is visible as a change.
    previous_minutes: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.previous_minutes) and self.minutes != self.previous_minutes

    @property
    def direction(self) -> str:
        if not self.changed:
            return "unchanged"
        return "widened" if self.minutes > self.previous_minutes else "narrowed"

    def render(self) -> str:
        if not self.changed:
            return f"Checking every {_period(self.minutes)}: {self.reason}."
        return (
            f"Checking every {_period(self.minutes)} instead of every "
            f"{_period(self.previous_minutes)}: {self.reason}."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "minutes": self.minutes,
            "previous_minutes": self.previous_minutes,
            "changed": self.changed,
            "direction": self.direction,
            "reason": self.reason,
            "summary": self.render(),
        }


class AdaptiveCadence:
    """Decides how often to look, and says why."""

    def __init__(
        self,
        bounds: CadenceBounds,
        *,
        backoff: float = BACKOFF_FACTOR,
        passes_before_backoff: int = PASSES_BEFORE_BACKOFF,
    ) -> None:
        self._bounds = bounds
        self._backoff = max(1.0, backoff)
        self._patience = max(1, passes_before_backoff)

    @property
    def bounds(self) -> CadenceBounds:
        return self._bounds

    def decide(self, observed: Observation, *, current_minutes: int = 0) -> Decision:
        current = current_minutes or self._bounds.start
        floor, ceiling = self._bounds.floor_minutes, self._bounds.ceiling_minutes

        if not observed.has_run:
            return Decision(
                minutes=self._bounds.start,
                reason="nothing has been observed yet, so this is the declared starting cadence",
                previous_minutes=current_minutes,
            )

        if observed.last_failed:
            # Immediately, not gradually. The period just after a break is when
            # the next one is most likely and when somebody is watching.
            return Decision(
                minutes=floor,
                reason=(
                    f"the last run failed, so the cadence returns to its floor — every "
                    f"{_period(floor)} — rather than easing back"
                ),
                previous_minutes=current,
            )

        if observed.indeterminate_streak >= 3:
            # Repeated indeterminates mean we are not learning anything by
            # looking. Widening would be the wrong lesson: the answer is that
            # somebody should fix the scope, and checking harder will not.
            return Decision(
                minutes=current,
                reason=(
                    f"the last {observed.indeterminate_streak} runs were indeterminate, so "
                    f"the cadence is held while the scope is investigated — looking more "
                    f"often would not make an empty scope informative"
                ),
                previous_minutes=current,
            )

        passes = observed.consecutive_passes
        if passes < self._patience:
            return Decision(
                minutes=current,
                reason=(
                    f"{passes} consecutive clean run(s) is too small a sample to widen on; "
                    f"{self._patience} are needed"
                ),
                previous_minutes=current,
            )

        widened = self._bounds.clamp(current * self._backoff)
        if widened == current and current >= ceiling:
            return Decision(
                minutes=ceiling,
                reason=(
                    f"{passes} consecutive clean runs, and the cadence is already at its "
                    f"declared ceiling — every {_period(ceiling)}"
                ),
                previous_minutes=current,
            )
        return Decision(
            minutes=widened,
            reason=(
                f"{passes} consecutive clean runs, so the interval widens; it returns to "
                f"every {_period(floor)} the moment anything fails"
            ),
            previous_minutes=current,
        )

    def explain_bounds(self) -> str:
        """Why the cadence can never leave its range, in one sentence."""
        return (
            f"This dataset is checked at least once every "
            f"{_period(self._bounds.ceiling_minutes)}, and no more often than once every "
            f"{_period(self._bounds.floor_minutes)}, whatever the data does. Both bounds "
            f"were declared, not inferred."
        )


def _round_interval(minutes: float) -> int:
    """A cadence on a grid a person would have chosen.

    Geometric backoff produces intervals like 202 minutes, which are correct
    and awkward: harder to reason about, harder to stagger against other
    datasets, and they churn — 202 becomes 303 becomes 454, and none of those
    numbers means anything. Rounding to a sensible step keeps the schedule
    legible and stops the interval moving on every run.
    """
    if minutes < 60:
        step = 5
    elif minutes < 1440:
        step = 15
    else:
        step = 60
    return max(step, int(round(minutes / step) * step))


def _period(minutes: int) -> str:
    if minutes % 1440 == 0 and minutes >= 1440:
        days = minutes // 1440
        return "day" if days == 1 else f"{days} days"
    if minutes >= 60:
        hours, remainder = divmod(minutes, 60)
        head = "hour" if hours == 1 else f"{hours} hours"
        return head if not remainder else f"{head} {remainder} minutes"
    return f"{minutes} minutes"
