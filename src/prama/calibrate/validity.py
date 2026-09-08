"""Checking that the guarantee still holds, and saying so when it does not.

`FR-MON-007`. A calibrated monitor makes a promise: at level alpha, at most a
fraction alpha of normal observations will alert. The promise rests on
exchangeability, and exchangeability is a property of the world rather than of
the code — so it fails silently, and a monitor that has quietly stopped being
calibrated looks exactly like one that has not.

That is the failure mode this module exists for, and the response is not to
hide it. When the assumptions break the monitor **degrades visibly**: it keeps
running, it keeps producing scores, and it stamps every alert with the fact
that its level no longer means what it says. A monitor that silently becomes
approximate is worse than one that stops, because the number on the dial goes
on being quoted.

**The test has to allow for noise, or it becomes the thing it is testing for.**
At alpha = 0.05 over a hundred observations the realised rate has a standard
deviation of about 0.022, so seeing 0.09 is a bit over two standard errors and
is not evidence of anything much. A validity monitor that flags on any
departure flags constantly and is switched off — the same death as any other
noisy control, and a particularly embarrassing one for the component whose job
is calibration. So the comparison is against a binomial interval, and the
width of that interval is reported alongside the verdict.

**The calibration curve is the artefact.** Nominal against empirical across a
grid of levels, with intervals. It is the plot that shows whether the promise
is being kept, and the acceptance criterion for this wave notes — correctly —
that no deployed competitor can produce it at all, because none of them has a
nominal level that means anything to compare against.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
import math
from collections.abc import Sequence
from typing import Any

#: Levels the calibration curve is evaluated at. Spread over three orders of
#: magnitude because that is the range a budget dial actually spans, and a
#: curve that only checks 0.05 says nothing about a monitor asked for 0.001.
CURVE_LEVELS: tuple[float, ...] = (0.001, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2)

#: Observations below which no validity claim is made either way. Under this,
#: the interval is wider than the thing being measured.
MINIMUM_OBSERVATIONS = 50

#: Confidence for the degradation decision. Much tighter than the 95% a single
#: comparison would use, and deliberately: this runs against every monitor in
#: the fleet, so a 5% false-degradation rate means one monitor in twenty is
#: wrongly labelled uncalibrated at any moment. The component whose job is
#: calibration cannot be the one crying wolf.
DEGRADATION_CONFIDENCE = 0.999

#: The wave's target: mean absolute deviation between nominal and empirical
#: coverage, across regimes.
TARGET_CALIBRATION_ERROR = 0.02


class Validity(enum.Enum):
    """How much the level on the dial can currently be believed."""

    #: The realised rate is consistent with the nominal level.
    CALIBRATED = "calibrated"
    #: Departing, but within what could still be sampling noise at this volume.
    #: Reported rather than smoothed, because it is the early warning.
    DRIFTING = "drifting"
    #: The realised rate is inconsistent with the nominal level. The monitor
    #: keeps working; its level no longer means what it says.
    UNCALIBRATED = "uncalibrated"
    #: Not enough observations to say. Distinct from calibrated, and the
    #: distinction matters: a new monitor has not earned the promise yet.
    UNKNOWN = "unknown"

    @property
    def promise_holds(self) -> bool:
        return self is Validity.CALIBRATED

    @property
    def label(self) -> str:
        return {
            Validity.CALIBRATED: "calibrated",
            Validity.DRIFTING: "calibration drifting",
            Validity.UNCALIBRATED: "uncalibrated — best effort",
            Validity.UNKNOWN: "not yet calibrated — best effort",
        }[self]


@dataclasses.dataclass(frozen=True, slots=True)
class Point:
    """One point on the calibration curve."""

    nominal: float
    empirical: float
    observations: int
    #: Wilson interval on the empirical rate. Wilson rather than normal because
    #: at alpha = 0.001 the normal interval reaches below zero and stops being
    #: an interval.
    low: float
    high: float

    @property
    def error(self) -> float:
        return abs(self.empirical - self.nominal)

    @property
    def covers_nominal(self) -> bool:
        return self.low <= self.nominal <= self.high

    @property
    def is_liberal(self) -> bool:
        """Firing more often than promised — the direction that matters.

        A conservative monitor wastes sensitivity; a liberal one breaks the
        promise. They are not equally bad and are not reported as though they
        were.

        The comparison is *nominal against the interval*, not the empirical
        rate against its own upper bound. The first version did the latter, and
        an estimate is always inside its own interval, so the flag could never
        fire — a check that could not fail, on the module whose job is checking
        that things can.
        """
        return self.low > self.nominal

    def to_dict(self) -> dict[str, Any]:
        return {
            "nominal": self.nominal,
            "empirical": round(self.empirical, 6),
            "observations": self.observations,
            "low": round(self.low, 6),
            "high": round(self.high, 6),
            "error": round(self.error, 6),
            "covers_nominal": self.covers_nominal,
            "liberal": self.is_liberal,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class CalibrationCurve:
    """Nominal against empirical, with intervals. The artefact."""

    points: tuple[Point, ...]
    observations: int

    @property
    def calibration_error(self) -> float:
        """Mean absolute deviation across levels — the wave's headline number."""
        if not self.points:
            return 0.0
        return sum(point.error for point in self.points) / len(self.points)

    @property
    def meets_target(self) -> bool:
        return self.calibration_error <= TARGET_CALIBRATION_ERROR

    @property
    def liberal_levels(self) -> tuple[float, ...]:
        return tuple(point.nominal for point in self.points if point.is_liberal)

    def describe(self) -> str:
        head = (
            f"calibration error {self.calibration_error:.4f} across "
            f"{len(self.points)} levels on {self.observations:,} observations"
        )
        liberal = self.liberal_levels
        if liberal:
            return (
                f"{head}; fires more often than promised at "
                + ", ".join(f"{level:g}" for level in liberal)
                + " — the direction that breaks the promise"
            )
        return head

    def plot_points(self) -> tuple[tuple[float, float, float, float], ...]:
        """``(nominal, empirical, low, high)`` per level, ready to draw."""
        return tuple((p.nominal, p.empirical, p.low, p.high) for p in self.points)

    def to_dict(self) -> dict[str, Any]:
        return {
            "points": [p.to_dict() for p in self.points],
            "observations": self.observations,
            "calibration_error": round(self.calibration_error, 6),
            "meets_target": self.meets_target,
            "liberal_levels": list(self.liberal_levels),
            "summary": self.describe(),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class ValidityReport:
    """What a monitor may currently claim, and what it must disclose."""

    status: Validity
    curve: CalibrationCurve
    nominal: float
    empirical: float
    reason: str = ""

    @property
    def disclosure(self) -> str:
        """The sentence that goes on every alert this monitor raises.

        Every alert, not the dashboard. A degradation visible only on a status
        page is a degradation nobody sees, because the person reading the alert
        at three in the morning is not on the status page.
        """
        if self.status.promise_holds:
            return (
                f"calibrated: at most {self.nominal:.1%} of normal observations alert, "
                f"and {self.empirical:.1%} did over the checked window"
            )
        if self.status is Validity.UNKNOWN:
            return (
                f"not yet calibrated — this monitor has seen too little history to "
                f"promise a false-alarm rate, so {self.nominal:.1%} is an intention "
                f"rather than a measurement"
            )
        return (
            f"{self.status.label}: this monitor promised at most {self.nominal:.1%} "
            f"false alarms and is running at {self.empirical:.1%}. {self.reason}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "label": self.status.label,
            "promise_holds": self.status.promise_holds,
            "nominal": self.nominal,
            "empirical": round(self.empirical, 6),
            "reason": self.reason,
            "disclosure": self.disclosure,
            "curve": self.curve.to_dict(),
        }


class ValidityMonitor:
    """Watches a monitor's own false-alarm rate against what it promised.

    Fed the p-values of observations *believed to be normal*. That belief is
    the weak point and is worth naming: on live data nobody knows which
    observations were normal, so in practice this is fed the whole stream and
    reads as "how often does this monitor fire", which equals the false-alarm
    rate only when genuine incidents are rare. When they are not, the monitor
    reports as liberal and a person should look — which is the right outcome
    either way, because a monitor firing on a fifth of all days is worth
    looking at whichever explanation is true.
    """

    def __init__(
        self,
        nominal: float,
        *,
        window: int = 500,
        minimum: int = MINIMUM_OBSERVATIONS,
        levels: Sequence[float] = CURVE_LEVELS,
    ) -> None:
        self._nominal = nominal
        self._window = window
        self._minimum = minimum
        self._levels = tuple(levels)
        self._p_values: list[float] = []

    def observe(self, p_value: float) -> None:
        self._p_values.append(p_value)
        if len(self._p_values) > self._window:
            self._p_values.pop(0)

    def observe_all(self, p_values: Sequence[float]) -> None:
        for value in p_values:
            self.observe(value)

    @property
    def observations(self) -> int:
        return len(self._p_values)

    def curve(self) -> CalibrationCurve:
        """The plot: what fraction fell below each level, with intervals."""
        total = len(self._p_values)
        points = []
        for level in self._levels:
            hits = sum(1 for value in self._p_values if value <= level)
            rate = hits / total if total else 0.0
            low, high = wilson_interval(hits, total, confidence=DEGRADATION_CONFIDENCE)
            points.append(
                Point(
                    nominal=level,
                    empirical=rate,
                    observations=total,
                    low=low,
                    high=high,
                )
            )
        return CalibrationCurve(points=tuple(points), observations=total)

    def report(self) -> ValidityReport:
        """The current verdict, and the sentence every alert must carry."""
        curve = self.curve()
        total = len(self._p_values)
        hits = sum(1 for value in self._p_values if value <= self._nominal)
        empirical = hits / total if total else 0.0

        if total < self._minimum:
            return ValidityReport(
                status=Validity.UNKNOWN,
                curve=curve,
                nominal=self._nominal,
                empirical=empirical,
                reason=(
                    f"{total} observations is below the {self._minimum} needed for the "
                    f"interval to be narrower than the effect being measured"
                ),
            )

        low, high = wilson_interval(hits, total, confidence=DEGRADATION_CONFIDENCE)
        if low <= self._nominal <= high:
            # Consistent with the promise. Not proof of it — an interval that
            # covers the nominal level also covers a range of others — but the
            # honest reading is that nothing here contradicts it.
            return ValidityReport(
                status=Validity.CALIBRATED,
                curve=curve,
                nominal=self._nominal,
                empirical=empirical,
            )

        if empirical <= self._nominal:
            # Firing less than promised. Wasteful, not dishonest, so it is not
            # a degradation — a conservative monitor keeps its promise and
            # spends sensitivity doing it.
            return ValidityReport(
                status=Validity.DRIFTING,
                curve=curve,
                nominal=self._nominal,
                empirical=empirical,
                reason=(
                    f"firing less often than the budget allows ({empirical:.2%} against "
                    f"{self._nominal:.2%}), so the promise holds and sensitivity is "
                    f"being wasted"
                ),
            )

        severity = (empirical - self._nominal) / max(self._nominal, 1e-9)
        if severity < 1.0:
            return ValidityReport(
                status=Validity.DRIFTING,
                curve=curve,
                nominal=self._nominal,
                empirical=empirical,
                reason=(
                    f"firing {severity:.0%} more often than promised, which is outside "
                    f"the interval but not yet by a factor that makes the level "
                    f"meaningless"
                ),
            )
        return ValidityReport(
            status=Validity.UNCALIBRATED,
            curve=curve,
            nominal=self._nominal,
            empirical=empirical,
            reason=(
                f"that is {1 + severity:.1f} times the promised rate, and outside the "
                f"{low:.2%} to {high:.2%} interval this many observations supports. The "
                f"data has moved and the calibration set no longer describes it; "
                f"treat this monitor's level as an intention until it recovers"
            ),
        )


def wilson_interval(
    successes: int, trials: int, *, confidence: float = 0.95
) -> tuple[float, float]:
    """A binomial interval that behaves at the ends of the range.

    Wilson rather than the normal approximation because the normal one reaches
    below zero for small rates — and small rates are the entire subject here.
    An interval of [-0.01, 0.03] on a monitor promising 0.001 is not an
    interval, and code that clamps it to zero has produced a number that looks
    like a bound and is not one.
    """
    if trials <= 0:
        return 0.0, 1.0
    z = 1.959963984540054 if abs(confidence - 0.95) < 1e-9 else _z_for(confidence)
    rate = successes / trials
    denominator = 1.0 + z * z / trials
    centre = (rate + z * z / (2 * trials)) / denominator
    spread = z * math.sqrt(rate * (1 - rate) / trials + z * z / (4 * trials * trials)) / denominator
    return max(0.0, centre - spread), min(1.0, centre + spread)


def _z_for(confidence: float) -> float:
    """Two-sided normal quantile, by bisection."""
    target = 1.0 - (1.0 - confidence) / 2.0
    low, high = 0.0, 10.0
    for _ in range(200):
        middle = (low + high) / 2
        if 0.5 * (1.0 + math.erf(middle / math.sqrt(2.0))) < target:
            low = middle
        else:
            high = middle
    return (low + high) / 2
