"""Calibration across five ways for data to be difficult.

The wave's headline acceptance criterion, measured. The default size keeps the
suite fast; the full grid the roadmap quotes is one environment variable away:

    PRAMA_BENCH_OBSERVATIONS=700 pytest tests/monitor/test_benchmark.py -s

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import os

import pytest

from prama.monitor.benchmark import LEVELS, REGIMES, Mechanism, measure, run

#: The smallest size at which the criterion is a real test rather than a
#: measurement of noise. Below about five hundred observations the warm-up
#: leaves too few measured points for a 0.01 level to be distinguishable from
#: zero, so every mechanism looks conservative and the benchmark stops
#: discriminating. Raise it to reproduce the number the roadmap quotes; the
#: calibration is quadratic, so it costs.
COUNT = int(os.environ.get("PRAMA_BENCH_OBSERVATIONS", "500"))


@pytest.fixture(scope="module")
def report():  # type: ignore[no-untyped-def]
    return run(count=COUNT)


# -- the acceptance criterion ------------------------------------------------


def test_every_regime_has_a_mechanism_that_holds_the_promise(report) -> None:  # type: ignore[no-untyped-def]
    """The claim the wave actually makes.

    Not that one mechanism handles everything — none does, and a benchmark
    reporting a single number would hide that — but that for every way data can
    be difficult there is a mechanism whose realised false-alarm rate matches
    what it promised.
    """
    print("\n" + report.render())
    for regime in REGIMES:
        best = report.best_for(regime.name)
        assert best is not None, regime.name
        assert best.meets_target, f"{regime.name}: best is {best.describe()}"
    assert report.every_regime_has_a_mechanism


def test_the_stationary_case_is_calibrated_by_every_mechanism(report) -> None:  # type: ignore[no-untyped-def]
    """A monitor miscalibrated here is wrong, not challenged."""
    for cell in report.cells:
        if cell.regime == "stationary":
            assert cell.meets_target, cell.describe()


# -- what each regime breaks -------------------------------------------------


def test_plain_conformal_fails_on_seasonal_data() -> None:
    """Not a defect — the honest consequence of an assumption.

    And it fails in the direction people do not expect. Pooling weekdays with
    weekends does not make the monitor noisy; it makes it *insensitive*. The
    calibration set contains the weekend scores, so a weekend observation looks
    ordinary against them, and the band is wide enough to admit almost
    anything. That is the same failure as a threshold wide enough for
    month-end being blind on ordinary days, measured as calibration error
    rather than described.
    """
    cell = measure(REGIMES[1], Mechanism.PLAIN, count=COUNT)
    assert not cell.meets_target
    assert not cell.is_liberal
    # Conservative at every level: it alerts far less than it promised.
    assert all(empirical <= nominal for nominal, empirical in cell.empirical)


def test_forgetting_does_not_repair_seasonality() -> None:
    """Recency weighting makes it worse, and the reason is worth stating: the
    recent past is Friday and today is Monday. Seasonality is repaired by
    conditioning, never by forgetting."""
    weighted = measure(REGIMES[1], Mechanism.WEIGHTED, count=COUNT)
    grouped = measure(REGIMES[1], Mechanism.SEASONAL, count=COUNT)
    assert grouped.calibration_error < weighted.calibration_error


def test_a_level_shift_is_not_repaired_by_conditioning() -> None:
    """The mirror image: grouping by calendar cannot help when the whole series
    stepped, because every group stepped with it."""
    grouped = measure(REGIMES[2], Mechanism.SEASONAL, count=COUNT)
    assert not grouped.meets_target


def test_adaptation_handles_the_regime_that_switches_back() -> None:
    """Where adaptation earns its place over forgetting: a monitor that has
    forgotten the old regime is wrong again the moment it returns."""
    cell = measure(REGIMES[3], Mechanism.ADAPTIVE, count=COUNT)
    assert cell.meets_target


def test_the_bursty_regime_has_no_shift_at_all() -> None:
    """The one most often missing from an evaluation and most common in a real
    feed: the mean never moves and the variance does, so a quiet observation
    and a volatile one are not exchangeable."""
    regime = REGIMES[4]
    series = regime.series(600, seed=3)
    quiet = [value for index, value in enumerate(series) if (index // 50) % 3 != 0]
    loud = [value for index, value in enumerate(series) if (index // 50) % 3 == 0]
    assert abs(sum(quiet) / len(quiet) - sum(loud) / len(loud)) < 60
    assert _spread(loud) > 3 * _spread(quiet)


# -- how the error is measured ----------------------------------------------


def test_the_error_is_absolute_so_it_cannot_be_cancelled() -> None:
    """A signed deviation would average a monitor firing twice as often as
    promised against one firing half as often and call the pair perfect."""
    cell = measure(REGIMES[0], Mechanism.PLAIN, count=COUNT)
    assert cell.calibration_error >= 0
    assert cell.calibration_error == sum(abs(e - n) for n, e in cell.empirical) / len(
        cell.empirical
    )


def test_firing_more_often_than_promised_is_distinguished_from_firing_less() -> None:
    """Wasting sensitivity and breaking the promise are not the same failure."""
    liberal = measure(REGIMES[2], Mechanism.PLAIN, count=COUNT)
    assert liberal.is_liberal


def test_the_benchmark_measures_at_levels_spanning_the_budget_range(report) -> None:  # type: ignore[no-untyped-def]
    for cell in report.cells:
        assert tuple(n for n, _ in cell.empirical) == LEVELS


def test_every_observation_in_the_benchmark_is_normal_by_construction() -> None:
    """Which is what makes the realised rate directly comparable with the
    nominal level: anything that alerts is a false alarm."""
    for regime in REGIMES:
        series = regime.series(200, seed=1)
        assert len(series) == 200
        assert all(isinstance(value, float) for value in series)


def _spread(values: list[float]) -> float:
    mean = sum(values) / len(values)
    return (sum((value - mean) ** 2 for value in values) / len(values)) ** 0.5
