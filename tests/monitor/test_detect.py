"""Detectors: how far from normal, on a scale the calibrator can use.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import random

import pytest

from prama.calibrate.conformal import ConformalCalibrator, ConformalP
from prama.monitor.detect import (
    ForecastResidual,
    LocalOutlierFactor,
    QuantileDistance,
    RobustDeviation,
    ShapeDistance,
    default_ensemble,
)

DETECTORS = [
    RobustDeviation(),
    QuantileDistance(),
    LocalOutlierFactor(),
    ForecastResidual(),
]


def steady(count: int = 200, seed: int = 3) -> list[float]:
    rng = random.Random(seed)
    return [1000 + rng.gauss(0, 20) for _ in range(count)]


# -- the contract ------------------------------------------------------------


@pytest.mark.parametrize("detector", DETECTORS, ids=lambda d: d.name)
def test_a_stranger_point_scores_higher(detector: object) -> None:
    """The only contract a detector has. Everything else about it is a matter
    of sensitivity, which is why a badly chosen one costs findings and never
    validity."""
    history = steady()
    ordinary = detector.score(1005.0, history)  # type: ignore[attr-defined]
    strange = detector.score(4000.0, history)  # type: ignore[attr-defined]
    assert ordinary is not None and strange is not None
    assert strange.value > ordinary.value


@pytest.mark.parametrize("detector", DETECTORS, ids=lambda d: d.name)
def test_a_badly_chosen_detector_costs_sensitivity_and_never_validity(
    detector: object,
) -> None:
    """The inversion that makes this architecture worth having: a detector
    that scores noise still produces exchangeable scores, so the false-alarm
    rate is bounded and the monitor merely finds nothing."""
    rng = random.Random(11)
    fired = 0
    trials = 400
    for _ in range(trials):
        history = [rng.gauss(0, 1) for _ in range(120)]
        calibration = detector.scores(history)  # type: ignore[attr-defined]
        score = detector.score(rng.gauss(0, 1), history)  # type: ignore[attr-defined]
        assert score is not None
        p = ConformalCalibrator(calibration).p_value(score.value)
        if isinstance(p, ConformalP):
            fired += p.value <= 0.10
    assert fired / trials <= 0.16


@pytest.mark.parametrize("detector", DETECTORS, ids=lambda d: d.name)
def test_no_detector_speaks_on_a_history_too_short(detector: object) -> None:
    assert detector.score(1.0, [1.0, 2.0]) is None  # type: ignore[attr-defined]


@pytest.mark.parametrize("detector", DETECTORS, ids=lambda d: d.name)
def test_every_detector_names_what_it_is_blind_to(detector: object) -> None:
    """A suite that only advertises strengths is a suite whose gaps are
    discovered in production."""
    assert detector.good_at  # type: ignore[attr-defined]
    assert detector.blind_to  # type: ignore[attr-defined]


@pytest.mark.parametrize("detector", DETECTORS, ids=lambda d: d.name)
def test_calibration_scores_are_leave_one_out(detector: object) -> None:
    """Scoring a point against a history containing it makes every calibration
    score slightly too small, so the observation looks stranger than it is and
    the monitor over-alerts — by a little, consistently, in the direction that
    breaks the promise."""
    history = steady(60)
    scores = detector.scores(history)  # type: ignore[attr-defined]
    assert len(scores) == len(history)
    # An outlier planted in the history must score highly in its own
    # leave-one-out score, which it could not if it were compared against
    # itself.
    with_outlier = [*history, 9999.0]
    outlier_scores = detector.scores(with_outlier)  # type: ignore[attr-defined]
    assert outlier_scores[-1] == max(outlier_scores)


# -- what each one is for ----------------------------------------------------


def test_robust_deviation_is_not_blinded_by_one_bad_day_in_the_window() -> None:
    """A mean moves and a standard deviation inflates, so the monitor is least
    sensitive exactly after something went wrong."""
    clean = steady(100)
    contaminated = [*clean, 50_000.0]
    detector = RobustDeviation()
    from_clean = detector.score(1400.0, clean)
    from_contaminated = detector.score(1400.0, contaminated)
    assert from_clean is not None and from_contaminated is not None
    assert from_contaminated.value > from_clean.value * 0.5


def test_quantile_distance_treats_both_tails_as_unusual() -> None:
    history = steady()
    detector = QuantileDistance()
    high = detector.score(5000.0, history)
    low = detector.score(-5000.0, history)
    assert high is not None and low is not None
    assert high.value == pytest.approx(low.value, abs=0.05)


def test_local_outlier_factor_finds_the_point_between_two_clusters() -> None:
    """Ordinary by distance from the centre, and in a place nothing has ever
    been. A count that is normally 20,000 on weekdays or 500 at weekends is not
    reassured by an observation of 10,000."""
    rng = random.Random(7)
    bimodal = [500 + rng.gauss(0, 20) for _ in range(60)] + [
        20_000 + rng.gauss(0, 200) for _ in range(60)
    ]
    detector = LocalOutlierFactor()
    between = detector.score(10_000.0, bimodal)
    inside = detector.score(20_050.0, bimodal)
    assert between is not None and inside is not None
    assert between.value > inside.value


def test_forecast_residual_does_not_alert_on_a_steady_trend() -> None:
    """A count growing 2% a month is always far from the median of its own
    year, and a monitor built on that alerts continuously until somebody widens
    it into uselessness."""
    trending = [1000 * (1.02**index) for index in range(120)]
    forecast = ForecastResidual()
    robust = RobustDeviation()
    next_value = 1000 * (1.02**120)
    from_forecast = forecast.score(next_value, trending)
    from_robust = robust.score(next_value, trending)
    assert from_forecast is not None and from_robust is not None
    assert from_forecast.value < from_robust.value


def test_forecast_scores_stay_exchangeable_on_a_growing_series() -> None:
    """The property that broke, and the reason it mattered.

    Absolute residuals grow with the level, so on a series doubling over a year
    the calibration scores from January are systematically smaller than the
    score computed in December. That is not a sensitivity problem — it breaks
    exchangeability, which is the assumption the conformal guarantee rests on,
    so the false-alarm rate drifts upward over the life of the monitor and
    nothing says why.
    """
    rng = random.Random(21)
    growing = [1000 * (1.02**index) * rng.uniform(0.98, 1.02) for index in range(200)]
    scores = ForecastResidual().scores(growing)
    early = sorted(scores[:80])[len(scores[:80]) // 2]
    late = sorted(scores[-80:])[len(scores[-80:]) // 2]
    # The two halves must describe the same distribution, or the guarantee is
    # being spent by the passage of time.
    assert 0.5 < late / max(early, 1e-9) < 2.0


def test_shape_distance_sees_a_changed_profile_with_an_unchanged_total() -> None:
    """A feed that arrived all at once instead of throughout the day, which
    every level-based detector calls normal."""
    rng = random.Random(5)
    normal_day = [10.0, 30.0, 60.0, 60.0, 30.0, 10.0]
    history: list[float] = []
    for _ in range(30):
        history.extend(value * rng.uniform(0.95, 1.05) for value in normal_day)
    detector = ShapeDistance(window=6)
    ordinary = detector.score_window(normal_day, history)
    burst = detector.score_window([0.0, 0.0, 0.0, 0.0, 0.0, 200.0], history)
    assert ordinary is not None and burst is not None
    assert burst.value > ordinary.value


# -- the ensemble ------------------------------------------------------------


def test_the_ensemble_scores_each_detector_separately() -> None:
    """Combining scores before calibration would be the obvious move and is
    wrong: they are on different scales with different distributions, and any
    weighting silently changes the false-alarm rate."""
    scores = default_ensemble().score_all(4000.0, steady())
    assert len(scores) == 4
    assert len({round(score.value, 6) for score in scores.values()}) > 1


def test_the_ensemble_can_say_what_each_member_is_for() -> None:
    described = default_ensemble().describe()
    assert "blind to" in described
    assert described.count("good at") == 4


def test_every_score_explains_itself_in_a_sentence() -> None:
    for score in default_ensemble().score_all(4000.0, steady()).values():
        assert score.explanation
        assert score.detector
