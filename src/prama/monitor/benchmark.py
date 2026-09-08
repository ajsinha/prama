"""Does the guarantee hold on data that behaves like real data?

`W7.13`, and the wave's headline acceptance criterion: calibration error at or
below 0.02 across stationary, seasonal, level-shift, regime-switch and bursty
regimes.

**The point of five regimes is that no single mechanism handles all of them**,
and a benchmark reporting one number would hide that. Each regime breaks a
different assumption:

*Stationary* breaks nothing. If a monitor is miscalibrated here, it is wrong.

*Seasonal* breaks exchangeability by structure — Monday is not Sunday — and is
repaired by conditioning rather than by any amount of forgetting. Recency
weighting makes it *worse*, because the recent past is Friday and today is
Monday.

*Level shift* breaks exchangeability by time. Conditioning cannot help; the
repair is to forget, which costs resolution.

*Regime switch* breaks it repeatedly and in both directions, so a monitor that
has adapted to the new regime is wrong again when it switches back. This is
where adaptation earns its place over weighting.

*Bursty* has no shift at all — the variance is not constant, so an observation
drawn from a quiet stretch and one from a volatile stretch are not
exchangeable even though the mean never moves. It is the regime most likely to
be missing from somebody's evaluation and the most common in real feeds.

So the benchmark runs each regime against each mechanism and reports the grid.
A row that is green everywhere would mean the regimes are not hard enough.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import random
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from typing import Any

from prama.calibrate.conformal import (
    AdaptiveCalibrator,
    ConformalCalibrator,
    ConformalP,
    recency_weights,
)
from prama.calibrate.validity import TARGET_CALIBRATION_ERROR
from prama.core.calendars import BusinessCalendar
from prama.monitor.detect import RobustDeviation
from prama.monitor.season import SeasonalModel

#: Levels the benchmark measures at. The same grid the calibration curve uses,
#: because the two answer the same question and reporting them at different
#: levels would make them impossible to compare.
LEVELS: tuple[float, ...] = (0.01, 0.02, 0.05, 0.10, 0.20)

WEEKDAYS = BusinessCalendar(name="benchmark", weekend_days=frozenset({5, 6}))


@dataclasses.dataclass(frozen=True, slots=True)
class Regime:
    """A way for data to be difficult, and what it breaks."""

    name: str
    breaks: str
    generate: Callable[[int, random.Random], list[float]]
    #: Whether the seasonal grouping is expected to be needed here.
    seasonal: bool = False

    def series(self, count: int, seed: int) -> list[float]:
        return self.generate(count, random.Random(seed))


def _stationary(count: int, rng: random.Random) -> list[float]:
    return [1000 + rng.gauss(0, 50) for _ in range(count)]


def _seasonal(count: int, rng: random.Random) -> list[float]:
    """Weekday and weekend volumes an order of magnitude apart.

    The structure that makes a pooled band useless: a threshold wide enough to
    admit a Monday admits anything that could happen on a Sunday.
    """
    start = datetime(2024, 1, 1)
    out = []
    for index in range(count):
        day = (start + timedelta(days=index)).date()
        base = 1000.0 if WEEKDAYS.is_business_day(day) else 80.0
        out.append(base * rng.uniform(0.9, 1.1))
    return out


def _level_shift(count: int, rng: random.Random) -> list[float]:
    """One permanent step, halfway through."""
    return [(1000 if index < count // 2 else 1600) + rng.gauss(0, 50) for index in range(count)]


def _regime_switch(count: int, rng: random.Random) -> list[float]:
    """Back and forth between two levels, every hundred observations.

    The case that separates adaptation from forgetting: a monitor that has
    forgotten the old regime is wrong again the moment it returns.
    """
    return [
        (1000 if (index // 100) % 2 == 0 else 1600) + rng.gauss(0, 50) for index in range(count)
    ]


def _bursty(count: int, rng: random.Random) -> list[float]:
    """A constant mean and a variance that is not.

    No shift at all, and still not exchangeable: an observation from a quiet
    stretch and one from a volatile stretch are drawn from different
    distributions. The regime most often missing from an evaluation and most
    common in a real feed.
    """
    out = []
    for index in range(count):
        volatile = (index // 50) % 3 == 0
        out.append(1000 + rng.gauss(0, 300 if volatile else 30))
    return out


REGIMES: tuple[Regime, ...] = (
    Regime("stationary", "nothing — a monitor wrong here is wrong", _stationary),
    Regime(
        "seasonal",
        "exchangeability, by structure: Monday is not Sunday",
        _seasonal,
        seasonal=True,
    ),
    Regime("level_shift", "exchangeability, by time: one permanent step", _level_shift),
    Regime(
        "regime_switch",
        "exchangeability repeatedly and in both directions",
        _regime_switch,
    ),
    Regime(
        "bursty",
        "exchangeability without any shift: the variance moves, the mean does not",
        _bursty,
    ),
)


class Mechanism:
    """A way of calibrating, so the benchmark can compare them."""

    PLAIN = "plain"
    SEASONAL = "seasonal"
    WEIGHTED = "weighted"
    ADAPTIVE = "adaptive"
    #: Detect that the level moved and calibrate from after the move.
    #:
    #: The mechanism the other three cannot substitute for. A twelve-sigma step
    #: makes every subsequent observation more extreme than the whole
    #: pre-shift calibration set, so every p-value sits at its floor —
    #: forgetting is too slow and no threshold exists between alerting on
    #: everything and nothing. What is needed is to stop treating the old
    #: regime as evidence about the new one, which is a different action
    #: rather than a smaller number.
    CHANGEPOINT = "changepoint"


@dataclasses.dataclass(frozen=True, slots=True)
class Cell:
    """One regime against one mechanism."""

    regime: str
    mechanism: str
    #: Realised alert rate at each nominal level.
    empirical: tuple[tuple[float, float], ...]
    observations: int

    @property
    def calibration_error(self) -> float:
        """Mean absolute deviation between nominal and empirical.

        Signed deviation would average a monitor that fires twice as often as
        promised against one that fires half as often and call the pair
        perfect. Absolute is the only reading that cannot be gamed by
        cancelling.
        """
        if not self.empirical:
            return 1.0
        return sum(abs(e - n) for n, e in self.empirical) / len(self.empirical)

    @property
    def meets_target(self) -> bool:
        return self.calibration_error <= TARGET_CALIBRATION_ERROR

    @property
    def is_liberal(self) -> bool:
        """Firing more often than promised at any level — the direction that
        breaks the promise rather than merely wasting sensitivity."""
        return any(e > n + TARGET_CALIBRATION_ERROR for n, e in self.empirical)

    def describe(self) -> str:
        mark = "✓" if self.meets_target else ("!" if self.is_liberal else "~")
        return f"{mark} {self.regime:14} {self.mechanism:9} error {self.calibration_error:.4f}" + (
            "  (fires more often than promised)" if self.is_liberal else ""
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "regime": self.regime,
            "mechanism": self.mechanism,
            "empirical": [[n, round(e, 6)] for n, e in self.empirical],
            "observations": self.observations,
            "calibration_error": round(self.calibration_error, 6),
            "meets_target": self.meets_target,
            "liberal": self.is_liberal,
            "summary": self.describe(),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class BenchmarkReport:
    cells: tuple[Cell, ...]

    def best_for(self, regime: str) -> Cell | None:
        candidates = [c for c in self.cells if c.regime == regime]
        return min(candidates, key=lambda c: c.calibration_error) if candidates else None

    @property
    def every_regime_has_a_mechanism(self) -> bool:
        """The claim the wave actually makes.

        Not that one mechanism handles everything — none does, and a benchmark
        reporting a single number would hide that — but that for every regime
        there is a mechanism that holds the promise.
        """
        regimes = {c.regime for c in self.cells}
        return all(
            (best := self.best_for(regime)) is not None and best.meets_target for regime in regimes
        )

    def render(self) -> str:
        lines = ["calibration error by regime and mechanism (target ≤ 0.02)", ""]
        lines.extend(cell.describe() for cell in self.cells)
        lines.append("")
        for regime in sorted({c.regime for c in self.cells}):
            best = self.best_for(regime)
            if best is not None:
                lines.append(f"  {regime:14} best: {best.mechanism} ({best.calibration_error:.4f})")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cells": [cell.to_dict() for cell in self.cells],
            "every_regime_has_a_mechanism": self.every_regime_has_a_mechanism,
            "report": self.render(),
        }


def measure(
    regime: Regime,
    mechanism: str,
    *,
    count: int = 700,
    warmup: int = 250,
    seed: int = 17,
    half_life: float = 40.0,
) -> Cell:
    """Run one regime through one mechanism and measure the realised rates.

    Every observation is drawn from the regime's own distribution — there are
    no injected anomalies. Anything that alerts is therefore a false alarm by
    construction, which is what makes the realised rate directly comparable
    with the nominal level.
    """
    series = regime.series(count, seed)
    detector = RobustDeviation()
    season = SeasonalModel(calendar=WEEKDAYS)
    start = datetime(2024, 1, 1, 6, 0)
    stamps = [start + timedelta(days=index) for index in range(count)]

    p_values: list[float] = []
    adaptives = {level: AdaptiveCalibrator(level, step=0.02) for level in LEVELS}
    adaptive_hits = dict.fromkeys(LEVELS, 0)

    for index in range(warmup, count):
        history = series[:index]
        if mechanism == Mechanism.CHANGEPOINT:
            history = list(_after_changepoint(history))
        if mechanism == Mechanism.SEASONAL:
            grouping = season.group(stamps[:index], stamps[index])
            comparable = [history[position] for position in grouping.members]
        else:
            comparable = history

        score = detector.score(series[index], comparable)
        if score is None:
            continue
        calibration = detector.scores(comparable)
        weights = (
            recency_weights(len(calibration), half_life=half_life)
            if mechanism == Mechanism.WEIGHTED
            else None
        )
        outcome = ConformalCalibrator(calibration, weights=weights).p_value(score.value)
        if not isinstance(outcome, ConformalP):
            continue
        p_values.append(outcome.value)
        if mechanism == Mechanism.ADAPTIVE:
            for level in LEVELS:
                alerted, _ = adaptives[level].judge(outcome)
                adaptive_hits[level] += alerted

    if mechanism == Mechanism.ADAPTIVE:
        total = len(p_values) or 1
        empirical = tuple((level, adaptive_hits[level] / total) for level in LEVELS)
    else:
        total = len(p_values) or 1
        empirical = tuple(
            (level, sum(1 for p in p_values if p <= level) / total) for level in LEVELS
        )
    return Cell(
        regime=regime.name,
        mechanism=mechanism,
        empirical=empirical,
        observations=len(p_values),
    )


def _after_changepoint(history: Sequence[float]) -> Sequence[float]:
    """The history since the level last moved, if it moved convincingly.

    Strength is in units of the series' own variability, and the threshold is
    high on purpose: recalibrating on noise throws away the history a monitor
    needs, and a monitor that keeps discarding its past never accumulates
    enough to promise anything.
    """
    from prama.monitor.drift import find_changepoint

    point = find_changepoint(history)
    if point is None or point.strength < 1.5:
        return history
    remainder = history[point.index :]
    # Only if what remains can still calibrate. A shift detected ten
    # observations ago leaves nothing to compare against, and the old regime is
    # a poor reference but a better one than none.
    return remainder if len(remainder) >= 40 else history


def run(
    *,
    regimes: Sequence[Regime] = REGIMES,
    mechanisms: Sequence[str] = (
        Mechanism.PLAIN,
        Mechanism.SEASONAL,
        Mechanism.WEIGHTED,
        Mechanism.ADAPTIVE,
        Mechanism.CHANGEPOINT,
    ),
    count: int = 700,
    seed: int = 17,
) -> BenchmarkReport:
    """The whole grid."""
    return BenchmarkReport(
        cells=tuple(
            measure(regime, mechanism, count=count, seed=seed)
            for regime in regimes
            for mechanism in mechanisms
        )
    )
