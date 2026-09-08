"""Conformal p-values: an alert level that means what it says.

`FR-MON-005`. Every monitoring product has a sensitivity dial. Almost none of
them can tell you what the number on it means, because the threshold is a
z-score or a percentile of a distribution nobody checked the data against. Turn
it to "high" and you get more alerts; that is the whole contract.

Conformal prediction gives the dial a meaning that survives contact with real
data: **under exchangeability, the probability that a normal point produces a
p-value at or below alpha is at most alpha, exactly, in finite samples, with no
distributional assumption at all.** Not asymptotically, not approximately, and
not conditional on the residuals being Gaussian — which they never are for a
row count.

The construction is three lines and one of them is easy to get wrong::

    p = (1 + #{i : s_i >= s}) / (n + 1)

**That ``1 +`` and ``n + 1`` are the guarantee, not rounding.** Compute
``#{s_i >= s} / n`` instead and the smallest p-value becomes 0, so a point more
extreme than everything seen produces a p-value of zero and the test rejects at
any level at all — the false-alarm rate becomes 1/n rather than alpha. It is right
about 95% of the time on 20 calibration points, which is exactly the kind of
wrong that ships.

**What this cannot do, said out loud.** The guarantee is marginal, not
conditional: it holds over the whole stream, not within every segment. It
assumes exchangeability, which drift breaks — hence the weighted and adaptive
variants below, both of which trade exactness for robustness and *say by how
much*. And it cannot express a p-value smaller than ``1/(n+1)``: with fifty
calibration points the smallest number this construction can produce is 0.0196,
so a monitor asked for alpha = 0.001 on fifty points cannot honour it. Reporting
that ceiling is the difference between a system that prints ``p = 0.0002`` from
fifty points and one that says what it actually knows.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import bisect
import dataclasses
import math
from collections.abc import Sequence
from typing import Any

#: Below this many calibration points, no p-value is worth reporting: the
#: coarsest it can be is 1/(n+1), and a monitor whose finest distinction is
#: "one in eleven" is a monitor that cannot honour any useful budget.
MINIMUM_CALIBRATION = 20

#: Default half-life for recency weighting, in observations. Roughly a quarter
#: of a year of daily data — long enough that a month of unusual weather does
#: not dominate, short enough that last year's regime does not.
DEFAULT_HALF_LIFE = 60.0


@dataclasses.dataclass(frozen=True, slots=True)
class ConformalP:
    """A p-value, and everything needed to know what it is worth."""

    value: float
    #: Calibration points behind it.
    n: int
    #: Effective sample size after weighting: ``(Σw)² / Σw²``. Equal to ``n``
    #: when unweighted. This, not ``n``, is what bounds the resolution.
    effective_n: float
    #: The smallest p-value this much calibration data can express.
    resolution: float
    #: Whether exchangeability was assumed to hold. False once weighting is in
    #: play, which is the honest reading of a weighted conformal p-value: it is
    #: approximately valid, and the approximation is not free.
    exact: bool = True
    #: An upper bound on how far coverage may depart from nominal, when that
    #: can be bounded. Zero for the exact case.
    coverage_gap: float = 0.0

    @property
    def is_saturated(self) -> bool:
        """Whether the observation is more extreme than everything in memory.

        The p-value is then at its floor, and the honest statement is "at most
        this", not "equal to this". A monitor that reports a saturated p-value
        as a point estimate is claiming precision it does not have.
        """
        return self.value <= self.resolution + 1e-12

    def honours(self, alpha: float) -> bool:
        """Whether a budget of *alpha* is expressible with this much history."""
        return alpha >= self.resolution

    def describe(self) -> str:
        if self.is_saturated:
            head = (
                f"p ≤ {self.value:.4f} — more extreme than every one of the "
                f"{self.n:,} comparable observations, so this is the smallest "
                f"value this much history can express"
            )
        else:
            head = f"p = {self.value:.4f} against {self.n:,} comparable observations"
        if not self.exact:
            head += (
                f"; weighted for recency, so validity is approximate — coverage may "
                f"depart from nominal by up to {self.coverage_gap:.3f}"
            )
        return head

    def to_dict(self) -> dict[str, Any]:
        return {
            "p_value": round(self.value, 6),
            "n": self.n,
            "effective_n": round(self.effective_n, 2),
            "resolution": round(self.resolution, 6),
            "exact": self.exact,
            "coverage_gap": round(self.coverage_gap, 6),
            "saturated": self.is_saturated,
            "summary": self.describe(),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Uncalibrated:
    """No p-value, and the reason.

    A distinct type rather than ``None`` because "not enough history" and "the
    calibration set is degenerate" lead to different actions, and because a
    monitor that silently returns nothing is a monitor that silently stops
    working.
    """

    reason: str
    n: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"p_value": None, "reason": self.reason, "n": self.n}


class ConformalCalibrator:
    """Turns a nonconformity score into a p-value with a stated meaning.

    Holds the calibration scores sorted, so each p-value is a binary search
    rather than a scan. That matters: this is called once per monitor per run,
    and a fleet is tens of thousands of monitors.
    """

    def __init__(
        self,
        scores: Sequence[float],
        *,
        weights: Sequence[float] | None = None,
        minimum: int = MINIMUM_CALIBRATION,
    ) -> None:
        if weights is not None and len(weights) != len(scores):
            raise ValueError(
                f"{len(weights)} weights for {len(scores)} scores; a weighted "
                "calibration set needs one weight per point"
            )
        self._minimum = minimum
        finite = [
            (score, 1.0 if weights is None else weights[index])
            for index, score in enumerate(scores)
            if math.isfinite(score)
        ]
        finite.sort(key=lambda pair: pair[0])
        self._scores = [score for score, _ in finite]
        self._weights = [weight for _, weight in finite]
        self._weighted = weights is not None
        #: Suffix sums of weight, so ``#{s_i >= s}`` is O(log n) weighted too.
        self._suffix: list[float] = [0.0] * (len(self._weights) + 1)
        for index in range(len(self._weights) - 1, -1, -1):
            self._suffix[index] = self._suffix[index + 1] + self._weights[index]

    @property
    def n(self) -> int:
        return len(self._scores)

    @property
    def effective_n(self) -> float:
        """``(Σw)² / Σw²`` — how many points the weighting is really using.

        Equal to ``n`` when unweighted, and much smaller when the decay is
        aggressive. This is the number that bounds resolution, and quoting
        ``n`` instead is how a monitor with a six-month window and a two-week
        half-life claims a precision it has about fourteen points' worth of.
        """
        total = self._suffix[0]
        if total <= 0:
            return 0.0
        square = sum(weight * weight for weight in self._weights)
        return (total * total) / square if square else 0.0

    @property
    def resolution(self) -> float:
        """The smallest p-value this calibration set can express."""
        effective = self.effective_n
        return 1.0 / (effective + 1.0) if effective > 0 else 1.0

    def p_value(self, score: float) -> ConformalP | Uncalibrated:
        """The conformal p-value for one observation."""
        if self.n < self._minimum:
            return Uncalibrated(
                reason=(
                    f"{self.n} calibration points is below the minimum of "
                    f"{self._minimum}; the coarsest p-value available would be "
                    f"{1 / (self.n + 1):.3f}, which cannot honour any useful budget"
                ),
                n=self.n,
            )
        if not math.isfinite(score):
            return Uncalibrated(reason="the observed score is not a finite number", n=self.n)
        if self._suffix[0] <= 0:
            return Uncalibrated(
                reason=(
                    "every calibration point has zero weight, which happens when the "
                    "whole window is older than the decay allows for. Widen the window "
                    "or lengthen the half-life"
                ),
                n=self.n,
            )

        # Weight of points at least as extreme as the observation. The test
        # point contributes its own weight of 1 to both parts of the ratio —
        # the "+1" that makes the bound hold in finite samples.
        index = bisect.bisect_left(self._scores, score)
        at_least = self._suffix[index]
        total = self._suffix[0]
        value = (at_least + 1.0) / (total + 1.0)

        return ConformalP(
            value=value,
            n=self.n,
            effective_n=self.effective_n,
            resolution=self.resolution,
            exact=not self._weighted,
            coverage_gap=self._coverage_gap(),
        )

    def quantile(self, alpha: float) -> float | None:
        """The score threshold at which a p-value would equal *alpha*.

        For a UI that wants to show "this monitor fires above 41,200 rows"
        rather than a p-value. Returns None when *alpha* is finer than the
        calibration set can express, which is the honest answer rather than the
        largest score seen.
        """
        if self.n < self._minimum or alpha < self.resolution:
            return None
        total = self._suffix[0]
        target = alpha * (total + 1.0) - 1.0
        for index, score in enumerate(self._scores):
            if self._suffix[index] <= target:
                return score
        return self._scores[-1] if self._scores else None

    def _coverage_gap(self) -> float:
        """How far weighting may push coverage from nominal.

        The exact bound from the non-exchangeable conformal literature involves
        total-variation distances between the true distributions, which are not
        observable. What *is* observable is how much of the calibration mass
        the weighting discards, and that is reported instead — under the
        reading that a weighting which effectively ignores most of its window
        has departed from the exchangeable case by about as much.

        Deliberately an indicative bound rather than a proof, and labelled as
        one everywhere it surfaces. A number that overstates its own rigour is
        worse than no number, because it is the one that ends up in a slide.
        """
        if not self._weighted or self.n == 0:
            return 0.0
        return max(0.0, 1.0 - self.effective_n / self.n)


def recency_weights(count: int, *, half_life: float = DEFAULT_HALF_LIFE) -> tuple[float, ...]:
    """Exponentially decaying weights, oldest first.

    The standard answer to drift, and it buys robustness with resolution: a
    short half-life tracks a moving regime and leaves few effective points to
    calibrate against. :attr:`ConformalCalibrator.effective_n` is where that
    trade shows up, and it is why the number is reported rather than assumed.
    """
    if count <= 0:
        return ()
    decay = math.log(2.0) / max(half_life, 1e-9)
    # Oldest first, so the most recent observation carries weight 1.
    return tuple(math.exp(-decay * (count - 1 - index)) for index in range(count))


@dataclasses.dataclass(frozen=True, slots=True)
class AdaptiveLevel:
    """The level an adaptive monitor is currently testing at.

    Gibbs and Candès' adaptive conformal inference: when recent alerts have
    exceeded the budget, tighten; when they have fallen short, loosen. The
    long-run rate converges to the target whatever the drift does, which is a
    weaker and much more robust guarantee than exact marginal validity — and it
    is the right one for a monitor that has to keep running through a regime
    change rather than be recalibrated by hand.
    """

    target: float
    current: float
    #: How fast it adapts. Larger tracks faster and oscillates more.
    step: float
    #: Observations since the level was last at target, for the UI.
    updates: int = 0
    #: Realised alert rate over the observed window.
    realised: float = 0.0
    #: Fraction of recent p-values sitting at their resolution floor.
    saturated: float = 0.0

    @property
    def is_powerless(self) -> bool:
        """Whether adapting the level can do anything at all.

        When nearly every observation is more extreme than the whole
        calibration set, every p-value equals ``1/(n+1)`` and there is no level
        between "everything alerts" and "nothing alerts". The level then
        oscillates between the two and the realised rate has nothing to do with
        the budget — which a rate alone does not reveal, because the number
        looks like an ordinary overshoot.

        This is the resolution limit again, at the other end: the calibration
        set no longer describes the data, and no amount of moving a threshold
        fixes that. Recalibrate, or say the monitor is uncalibrated. Adapting
        harder is the one thing that cannot work.
        """
        return self.saturated >= 0.5

    @property
    def is_tightened(self) -> bool:
        return self.current < self.target - 1e-9

    @property
    def is_loosened(self) -> bool:
        return self.current > self.target + 1e-9

    def describe(self) -> str:
        if self.is_powerless:
            return (
                f"the level cannot be held to budget: {self.saturated:.0%} of recent "
                f"observations were more extreme than the entire calibration set, so "
                f"every p-value is at its floor and there is no threshold between "
                f"alerting on all of them and none. The calibration set no longer "
                f"describes this data"
            )
        if self.is_tightened:
            return (
                f"testing at {self.current:.4f} rather than the declared "
                f"{self.target:.4f}, because {self.realised:.1%} of recent "
                f"observations alerted — the data has moved and the level is being "
                f"held to the budget"
            )
        if self.is_loosened:
            return (
                f"testing at {self.current:.4f} rather than the declared "
                f"{self.target:.4f}: recent alerting has run below budget, so the "
                f"monitor is being allowed to be more sensitive"
            )
        return f"testing at the declared level of {self.target:.4f}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": round(self.target, 6),
            "current": round(self.current, 6),
            "step": self.step,
            "updates": self.updates,
            "realised": round(self.realised, 6),
            "saturated": round(self.saturated, 6),
            "powerless": self.is_powerless,
            "summary": self.describe(),
        }


class AdaptiveCalibrator:
    """Holds the level to the budget when exchangeability fails.

    Weighted conformal handles gradual drift by forgetting; this handles the
    case weighting cannot, where the *shape* of normal has changed and the
    monitor would otherwise alert on every observation until somebody notices.
    The two compose: weighting decides what to compare against, this decides
    what level to compare at.
    """

    def __init__(
        self,
        target: float,
        *,
        step: float = 0.02,
        window: int = 100,
        floor: float = 1e-4,
        ceiling: float = 0.5,
    ) -> None:
        if not 0.0 < target < 1.0:
            raise ValueError(
                f"a target alert rate of {target} is not a probability; the budget "
                "dial expresses how often a normal observation may alert"
            )
        self._target = target
        self._step = step
        self._window = window
        self._floor = floor
        self._ceiling = ceiling
        self._current = target
        self._recent: list[bool] = []
        self._saturated: list[bool] = []
        self._updates = 0

    @property
    def level(self) -> AdaptiveLevel:
        return AdaptiveLevel(
            target=self._target,
            current=self._current,
            step=self._step,
            updates=self._updates,
            realised=self.realised,
            saturated=(sum(self._saturated) / len(self._saturated) if self._saturated else 0.0),
        )

    @property
    def realised(self) -> float:
        return sum(self._recent) / len(self._recent) if self._recent else 0.0

    def observe(self, alerted: bool, *, saturated: bool = False) -> AdaptiveLevel:
        """Record one outcome and move the level toward the budget.

        The update is on the *error indicator* rather than on the p-value, so
        it is unaffected by how extreme an alert was — which is what makes the
        long-run guarantee hold without assuming anything about the score
        distribution.
        """
        self._recent.append(alerted)
        self._saturated.append(saturated)
        if len(self._recent) > self._window:
            self._recent.pop(0)
            self._saturated.pop(0)
        self._current += self._step * (self._target - (1.0 if alerted else 0.0))
        self._current = min(self._ceiling, max(self._floor, self._current))
        self._updates += 1
        return self.level

    def test(self, p: ConformalP) -> bool:
        """Whether this p-value alerts at the current adaptive level."""
        return p.value <= self._current

    def judge(self, p: ConformalP) -> tuple[bool, AdaptiveLevel]:
        """Test and record in one step, carrying the saturation through.

        The convenience that makes the saturation signal hard to lose: a caller
        using :meth:`test` and :meth:`observe` separately has to remember to
        pass it, and the whole point of the signal is that it appears when
        nobody is watching for it.
        """
        alerted = self.test(p)
        return alerted, self.observe(alerted, saturated=p.is_saturated)
