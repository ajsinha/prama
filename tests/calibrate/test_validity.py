"""Saying so when the guarantee stops holding.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import random

import pytest

from prama.calibrate.validity import (
    TARGET_CALIBRATION_ERROR,
    Validity,
    ValidityMonitor,
    wilson_interval,
)


def uniform(count: int, seed: int = 3) -> list[float]:
    """P-values from a correctly calibrated monitor on normal data."""
    rng = random.Random(seed)
    return [rng.random() for _ in range(count)]


# -- the verdict -------------------------------------------------------------


def test_a_calibrated_monitor_reports_that_it_is() -> None:
    monitor = ValidityMonitor(0.05)
    monitor.observe_all(uniform(500))
    report = monitor.report()
    assert report.status is Validity.CALIBRATED
    assert report.status.promise_holds


def test_a_monitor_whose_data_moved_reports_uncalibrated_and_keeps_running() -> None:
    """It keeps producing scores; what it stops claiming is the level."""
    monitor = ValidityMonitor(0.05)
    monitor.observe_all([value * 0.25 for value in uniform(500)])
    report = monitor.report()
    assert report.status is Validity.UNCALIBRATED
    assert not report.status.promise_holds
    assert "uncalibrated — best effort" in report.status.label


def test_the_degradation_appears_on_every_alert_not_only_a_status_page() -> None:
    """A degradation visible only on a dashboard is a degradation nobody sees,
    because the person reading the alert at three in the morning is not on the
    dashboard."""
    monitor = ValidityMonitor(0.05)
    monitor.observe_all([value * 0.25 for value in uniform(500)])
    disclosure = monitor.report().disclosure
    assert "promised at most 5.0%" in disclosure
    assert "running at" in disclosure
    assert "no longer describes it" in disclosure


def test_sampling_noise_does_not_trip_the_validity_monitor() -> None:
    """At 0.05 over a hundred observations the realised rate has a standard
    deviation of about 0.022. A validity monitor that flags on any departure
    flags constantly and is switched off — a particularly embarrassing death
    for the component whose job is calibration."""
    for seed in range(20):
        monitor = ValidityMonitor(0.05, minimum=50)
        monitor.observe_all(uniform(100, seed=seed))
        assert monitor.report().status is not Validity.UNCALIBRATED, seed


def test_a_new_monitor_has_not_earned_the_promise_yet() -> None:
    """Distinct from calibrated, and the distinction matters."""
    monitor = ValidityMonitor(0.05)
    monitor.observe_all(uniform(10))
    report = monitor.report()
    assert report.status is Validity.UNKNOWN
    assert "intention rather than a measurement" in report.disclosure


def test_firing_less_often_than_promised_is_not_a_broken_promise() -> None:
    """A conservative monitor keeps its promise and spends sensitivity doing
    it. Wasteful, not dishonest, and not reported as though they were the
    same."""
    monitor = ValidityMonitor(0.20)
    monitor.observe_all([0.5 + 0.5 * value for value in uniform(500)])
    report = monitor.report()
    assert report.status is Validity.DRIFTING
    assert "sensitivity is being wasted" in report.reason


def test_a_departure_that_is_not_yet_meaningless_is_called_drifting() -> None:
    """The early warning, reported rather than smoothed."""
    monitor = ValidityMonitor(0.05, window=2000)
    # Exactly 8% at or below the level, the rest spread above it. Outside the
    # interval on two thousand observations, and well short of the factor of
    # two that makes a level meaningless.
    monitor.observe_all([0.01] * 160 + [0.05 + 0.95 * (index / 1840) for index in range(1840)])
    report = monitor.report()
    assert report.status is Validity.DRIFTING
    assert "not yet by a factor that makes the level meaningless" in report.reason


# -- the curve ---------------------------------------------------------------


def test_the_calibration_curve_can_be_plotted() -> None:
    """The acceptance criterion, and the artefact: no competitor can produce
    this plot at all, because none has a nominal level to compare against."""
    monitor = ValidityMonitor(0.05)
    monitor.observe_all(uniform(2000))
    curve = monitor.curve()
    points = curve.plot_points()
    assert len(points) == 7
    for nominal, empirical, low, high in points:
        assert 0.0 <= low <= high <= 1.0
        assert low <= empirical <= high
        assert 0.0 < nominal < 1.0


def test_the_calibration_error_meets_the_wave_target_on_honest_data() -> None:
    monitor = ValidityMonitor(0.05)
    monitor.observe_all(uniform(2000))
    curve = monitor.curve()
    assert curve.calibration_error <= TARGET_CALIBRATION_ERROR
    assert curve.meets_target


def test_firing_more_often_than_promised_is_flagged_as_the_direction_that_matters() -> None:
    """A conservative monitor wastes sensitivity; a liberal one breaks the
    promise. Not equally bad, and not reported as though they were."""
    monitor = ValidityMonitor(0.05)
    monitor.observe_all([value * 0.2 for value in uniform(1000)])
    curve = monitor.curve()
    assert curve.liberal_levels
    assert "the direction that breaks the promise" in curve.describe()


def test_the_curve_covers_three_orders_of_magnitude() -> None:
    """A curve that only checks 0.05 says nothing about a monitor asked for
    0.001, which is the range a budget dial actually spans."""
    monitor = ValidityMonitor(0.05)
    monitor.observe_all(uniform(200))
    levels = [point.nominal for point in monitor.curve().points]
    assert min(levels) <= 0.001
    assert max(levels) >= 0.2


# -- the interval ------------------------------------------------------------


def test_the_interval_stays_an_interval_at_small_rates() -> None:
    """The normal approximation reaches below zero for small rates, and small
    rates are the entire subject here. Clamping it to zero produces a number
    that looks like a bound and is not one."""
    low, high = wilson_interval(1, 1000)
    assert low > 0.0
    assert high > 0.001
    assert low <= 0.001 <= high


def test_the_interval_narrows_with_evidence() -> None:
    narrow = wilson_interval(50, 1000)
    wide = wilson_interval(5, 100)
    assert (narrow[1] - narrow[0]) < (wide[1] - wide[0])


def test_no_observations_admits_everything() -> None:
    assert wilson_interval(0, 0) == (0.0, 1.0)


def test_the_interval_covers_the_truth_about_as_often_as_it_claims() -> None:
    """A confidence interval that does not is not one."""
    rng = random.Random(17)
    truth = 0.05
    covered = 0
    trials = 2000
    for _ in range(trials):
        hits = sum(1 for _ in range(200) if rng.random() < truth)
        low, high = wilson_interval(hits, 200)
        covered += low <= truth <= high
    assert covered / trials == pytest.approx(0.95, abs=0.03)
