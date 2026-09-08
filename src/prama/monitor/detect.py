"""Detectors: how far from normal, on a scale the calibrator can use.

`FR-MON-001`. A detector's job here is narrower than usual and the narrowing is
the point: it produces a **nonconformity score**, not a verdict. How unusual
that score is, and whether it is unusual enough to alert, is
:mod:`prama.calibrate.conformal`'s question — and keeping the two apart is what
lets a detector be swapped, tuned or replaced without touching the guarantee.

The consequence is worth stating plainly, because it inverts the usual
arrangement: **a badly-chosen detector here costs sensitivity, never validity.**
A detector that scores noise produces scores that are exchangeable with the
calibration scores, so the false-alarm rate is still at most alpha — the
monitor simply never finds anything. That is a much better failure than the
conventional one, where a mis-specified model produces a threshold that is
wrong in a direction nobody can see.

Five detectors, chosen because they fail differently:

*Deviation from a robust centre* — median and MAD rather than mean and standard
deviation, because one bad day in the calibration window moves a mean and
inflates a standard deviation, and the monitor then cannot see the next bad day.

*Quantile distance* — where in the empirical distribution the point sits.
Assumes nothing about shape, and is the right default for a bounded quantity
like a null rate.

*Local outlier factor* — density rather than distance, which is what finds a
point sitting between two clusters rather than beyond both.

*Forecast residual* — for a series with trend or autocorrelation, where "far
from the middle" is the wrong question and "far from what yesterday implied" is
the right one.

*Matrix profile distance* — for shape rather than level: a day whose intraday
curve is unlike any day before it, even though its total is ordinary.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import abc
import dataclasses
import math
from collections.abc import Sequence
from typing import Any, ClassVar

#: Below this, no detector says anything: the statistics it would compute are
#: dominated by the points used to compute them.
MINIMUM_HISTORY = 10

#: Calibration points a detector will score, most recent first.
#:
#: Leave-one-out scoring is quadratic — each of n points is scored against the
#: other n-1 — so an unbounded window makes a monitor slower every day it runs,
#: which is the kind of cost that is invisible in a test and fatal in a fleet.
#:
#: The cap is not only a performance concession. Three hundred points express a
#: p-value down to 0.0033, finer than any budget a real estate can honour once
#: it is divided across the number of monitors it runs; the points beyond that
#: buy resolution nobody spends and are the ones most likely to predate a
#: change in the data.
MAXIMUM_CALIBRATION = 300


@dataclasses.dataclass(frozen=True, slots=True)
class Score:
    """How unusual an observation is, before anybody decides whether to care.

    Deliberately not a probability, not a severity and not a verdict. It is a
    number that is larger when a point is stranger, and its only contract is
    that it is computed the same way for the calibration set and for the
    observation — which is the assumption conformal validity actually rests on.
    """

    value: float
    detector: str
    #: Enough to put in front of a person without them reading the code.
    explanation: str = ""
    #: What the detector thought normal looked like, for the chart.
    expected: float | None = None
    observed: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.value, 6),
            "detector": self.detector,
            "explanation": self.explanation,
            "expected": self.expected,
            "observed": self.observed,
        }


class Detector(abc.ABC):
    """Turns an observation and its history into a nonconformity score."""

    name: ClassVar[str] = ""
    #: What this detector is good at, for the model card and for the person
    #: choosing between them.
    good_at: ClassVar[str] = ""
    #: What it is blind to. Stated because every detector is blind to
    #: something, and a suite that only advertises strengths is a suite whose
    #: gaps are discovered in production.
    blind_to: ClassVar[str] = ""

    def score(self, observation: float, history: Sequence[float]) -> Score | None:
        """The nonconformity score, or None when the history cannot support one.

        A template method rather than the thing subclasses override, and the
        reason is a bug this shape makes impossible. The window is capped here,
        once, so the observation is scored against exactly the reference set the
        calibration points are scored against.

        Scoring the observation against the full history while calibrating
        against the last three hundred points is the kind of mistake that looks
        like an optimisation and is a silent violation of exchangeability: the
        two sets of scores come from different reference distributions, so
        comparing them means nothing and the false-alarm rate drifts with no
        symptom anybody can see.
        """
        return self.compute(observation, list(history[-MAXIMUM_CALIBRATION:]))

    @abc.abstractmethod
    def compute(self, observation: float, history: Sequence[float]) -> Score | None:
        """Score against an already-windowed history. Subclasses override this."""

    def scores(self, history: Sequence[float]) -> list[float]:
        """Calibration scores: each historical point against the others.

        Leave-one-out, and that is not fussiness. Scoring a point against a
        history that includes it makes every calibration score slightly too
        small, so the observation looks relatively stranger than it is and the
        monitor over-alerts — by a little, consistently, in the direction that
        breaks the promise.
        """
        window = list(history[-MAXIMUM_CALIBRATION:])
        out = []
        for index in range(len(window)):
            others = [*window[:index], *window[index + 1 :]]
            score = self.compute(window[index], others)
            if score is not None:
                out.append(score.value)
        return out


class RobustDeviation(Detector):
    """Distance from the median, in units of the median absolute deviation.

    Median and MAD rather than mean and standard deviation, because one bad day
    in the window moves a mean and inflates a standard deviation — so the
    monitor is least sensitive exactly after something has gone wrong, which is
    when it is most needed.
    """

    name: ClassVar[str] = "robust_deviation"
    good_at: ClassVar[str] = "a level that has shifted, on a series without trend"
    blind_to: ClassVar[str] = (
        "a series with trend or autocorrelation, where yesterday predicts today "
        "and the middle of the window predicts nothing"
    )

    def compute(self, observation: float, history: Sequence[float]) -> Score | None:
        if len(history) < MINIMUM_HISTORY:
            return None
        centre = _median(history)
        spread = _median([abs(value - centre) for value in history])
        if spread <= 0:
            # A constant history. Any departure is infinitely surprising by
            # this measure, which is useless — so the score is the raw
            # distance, and the calibrator's own floor handles the rest.
            spread = 1.0
        # 1.4826 makes MAD comparable with a standard deviation for Gaussian
        # data, so the number reads the way people expect. It has no effect on
        # the ordering, and therefore none on the guarantee.
        deviation = abs(observation - centre) / (spread * 1.4826)
        return Score(
            value=deviation,
            detector=self.name,
            expected=centre,
            observed=observation,
            explanation=(
                f"{observation:,.0f} against a typical {centre:,.0f}, which is "
                f"{deviation:.1f} robust deviations away"
            ),
        )


class QuantileDistance(Detector):
    """How far outside the observed range the point sits.

    Assumes nothing about the shape of the distribution, which makes it the
    right default for a bounded quantity — a null rate cannot go below zero,
    and a detector that models it as symmetric will spend half its sensitivity
    on the impossible side.
    """

    name: ClassVar[str] = "quantile_distance"
    good_at: ClassVar[str] = "bounded or skewed quantities, like a null rate"
    blind_to: ClassVar[str] = (
        "a point inside the observed range that is nonetheless in the wrong "
        "place — between two clusters, say"
    )

    def compute(self, observation: float, history: Sequence[float]) -> Score | None:
        if len(history) < MINIMUM_HISTORY:
            return None
        ordered = sorted(history)
        below = sum(1 for value in ordered if value <= observation)
        fraction = below / len(ordered)
        # Distance from the middle of the distribution, so both tails score
        # highly. A one-sided monitor is a different declaration and gets a
        # different detector rather than a flag on this one.
        value = abs(fraction - 0.5) * 2
        return Score(
            value=value,
            detector=self.name,
            expected=_median(ordered),
            observed=observation,
            explanation=(
                f"{observation:,.0f} sits at the {fraction:.0%} point of what has been seen before"
            ),
        )


class LocalOutlierFactor(Detector):
    """Density rather than distance.

    Finds the point sitting between two clusters — ordinary by any measure of
    distance from the centre, and in a place nothing has ever been. A row count
    that is normally either 20,000 on weekdays or 500 at weekends is not
    reassured by an observation of 10,000.
    """

    name: ClassVar[str] = "local_outlier_factor"
    good_at: ClassVar[str] = "multi-modal series, where the middle is empty"
    blind_to: ClassVar[str] = "gradual drift, which moves every point together"

    def __init__(self, neighbours: int = 5) -> None:
        self._k = neighbours

    def compute(self, observation: float, history: Sequence[float]) -> Score | None:
        if len(history) < max(MINIMUM_HISTORY, self._k + 1):
            return None
        own = self._local_density(observation, history)
        if own <= 0:
            return Score(
                value=float(len(history)),
                detector=self.name,
                observed=observation,
                explanation=f"{observation:,.0f} is nowhere near anything seen before",
            )
        neighbours = self._nearest(observation, history)
        ratios = []
        for neighbour in neighbours:
            density = self._local_density(neighbour, [v for v in history if v != neighbour])
            ratios.append(density / own if own > 0 else 0.0)
        factor = sum(ratios) / len(ratios) if ratios else 1.0
        return Score(
            value=factor,
            detector=self.name,
            observed=observation,
            explanation=(
                f"the neighbourhood around {observation:,.0f} is {factor:.1f} times "
                f"sparser than the neighbourhoods of its nearest comparable days"
            ),
        )

    def _nearest(self, point: float, history: Sequence[float]) -> list[float]:
        return sorted(history, key=lambda value: abs(value - point))[: self._k]

    def _local_density(self, point: float, history: Sequence[float]) -> float:
        neighbours = self._nearest(point, history)
        if not neighbours:
            return 0.0
        distance = sum(abs(value - point) for value in neighbours) / len(neighbours)
        return 1.0 / distance if distance > 0 else math.inf


class ForecastResidual(Detector):
    """Distance from what the recent past implied, rather than from the middle.

    For a series with trend or autocorrelation, "far from the median" is the
    wrong question: a row count growing 2% a month is always far from the
    median of its own year, and a monitor built on that alerts continuously
    until somebody widens it into uselessness.
    """

    name: ClassVar[str] = "forecast_residual"
    good_at: ClassVar[str] = "series with trend or momentum"
    blind_to: ClassVar[str] = (
        "a change that arrives gradually enough for the forecast to follow it, "
        "which is exactly what a slow leak looks like"
    )

    def __init__(self, span: int = 7) -> None:
        self._span = span

    def compute(self, observation: float, history: Sequence[float]) -> Score | None:
        if len(history) < max(MINIMUM_HISTORY, self._span + 1):
            return None
        forecast = _exponential_mean(history, self._span)
        # Residuals are taken *relative* to the forecast, not absolute.
        #
        # On a series growing multiplicatively — which is what a healthy
        # business looks like — absolute residuals grow with the level, so the
        # calibration scores computed early in the window are systematically
        # smaller than the one computed for today. That is not a sensitivity
        # problem: it breaks exchangeability, which is the assumption the
        # conformal guarantee rests on, so the false-alarm rate drifts upward
        # over the life of the monitor and nothing says why.
        #
        # A relative residual is scale-free, so a series doubling over a year
        # produces the same score distribution in January and December.
        residuals = [
            _relative(history[index], _exponential_mean(history[:index], self._span))
            for index in range(self._span, len(history))
        ]
        spread = _median(residuals) if residuals else 0.0
        if spread <= 0:
            spread = 1e-9
        value = _relative(observation, forecast) / spread
        return Score(
            value=value,
            detector=self.name,
            expected=forecast,
            observed=observation,
            explanation=(
                f"the recent trend implied about {forecast:,.0f} and {observation:,.0f} "
                f"arrived, which is {value:.1f} typical residuals away"
            ),
        )


class ShapeDistance(Detector):
    """How unlike every previous window this window's shape is.

    The matrix-profile idea, reduced to what a monitor actually needs: the
    distance to the nearest previous window of the same length. Catches a day
    whose intraday curve is unlike any day before it even though its total is
    perfectly ordinary — a feed that arrived all at once instead of throughout
    the day, which every level-based detector calls normal.
    """

    name: ClassVar[str] = "shape_distance"
    good_at: ClassVar[str] = "a changed profile with an unchanged total"
    blind_to: ClassVar[str] = "a level change that preserves the shape"

    def __init__(self, window: int = 6) -> None:
        self._window = window

    def compute(self, observation: float, history: Sequence[float]) -> Score | None:
        return self.score_window([*history[-(self._window - 1) :], observation], history)

    def score_window(self, window: Sequence[float], history: Sequence[float]) -> Score | None:
        size = len(window)
        if len(history) < max(MINIMUM_HISTORY, 2 * size):
            return None
        best = math.inf
        for start in range(len(history) - size):
            candidate = history[start : start + size]
            distance = _shape_distance(window, candidate)
            best = min(best, distance)
        return Score(
            value=best,
            detector=self.name,
            observed=window[-1] if window else None,
            explanation=(
                f"the most recent {size} observations form a pattern whose closest "
                f"match in the history is {best:.2f} away"
            ),
        )


# ---------------------------------------------------------------------------
# The suite
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class Ensemble:
    """Several detectors over one series, each scored and calibrated apart.

    Combining scores before calibration would be the obvious move and is wrong:
    the scores are on different scales with different distributions, and any
    weighting is a modelling choice that would silently change the false-alarm
    rate. Calibrating each and combining the *p-values* keeps every detector's
    guarantee intact and makes the combination a multiple-testing question,
    which the selection module already answers.
    """

    detectors: tuple[Detector, ...]

    def score_all(self, observation: float, history: Sequence[float]) -> dict[str, Score]:
        out: dict[str, Score] = {}
        for detector in self.detectors:
            score = detector.score(observation, history)
            if score is not None:
                out[detector.name] = score
        return out

    def calibration_for(self, name: str, history: Sequence[float]) -> list[float]:
        for detector in self.detectors:
            if detector.name == name:
                return detector.scores(history)
        return []

    def describe(self) -> str:
        return "; ".join(
            f"{d.name} (good at {d.good_at}; blind to {d.blind_to})" for d in self.detectors
        )


def default_ensemble() -> Ensemble:
    """The detectors that fail differently enough to be worth running together."""
    return Ensemble(
        detectors=(
            RobustDeviation(),
            QuantileDistance(),
            LocalOutlierFactor(),
            ForecastResidual(),
        )
    )


# ---------------------------------------------------------------------------
# Arithmetic
# ---------------------------------------------------------------------------


def _median(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _relative(observed: float, expected: float) -> float:
    """Residual as a fraction of what was expected.

    Falls back to the absolute difference when the expectation is at zero,
    where a ratio has no meaning and the absolute number is the only honest
    one available.
    """
    scale = abs(expected)
    if scale < 1e-12:
        return abs(observed - expected)
    return abs(observed - expected) / scale


def _exponential_mean(values: Sequence[float], span: int) -> float:
    if not values:
        return 0.0
    alpha = 2.0 / (span + 1.0)
    result = values[0]
    for value in values[1:]:
        result = alpha * value + (1 - alpha) * result
    return result


def _shape_distance(left: Sequence[float], right: Sequence[float]) -> float:
    """Euclidean distance between two windows, each normalised to itself.

    Normalising each window separately is what makes this about *shape*: two
    days with the same intraday profile at different volumes score as
    identical, which is the question this detector exists to ask and the
    opposite of what a level detector asks.
    """
    left_z = _standardise(left)
    right_z = _standardise(right)
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left_z, right_z, strict=True)))


def _standardise(values: Sequence[float]) -> list[float]:
    if not values:
        return []
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    spread = math.sqrt(variance)
    if spread <= 0:
        return [0.0] * len(values)
    return [(value - mean) / spread for value in values]
