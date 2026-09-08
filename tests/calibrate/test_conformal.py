"""The guarantee, measured rather than asserted.

Every test here is against a property that either holds or does not. A
calibration module whose tests only check that it returns a number between zero
and one is a calibration module nobody should use.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import random

import pytest

from prama.calibrate.conformal import (
    AdaptiveCalibrator,
    ConformalCalibrator,
    ConformalP,
    Uncalibrated,
    recency_weights,
)


def normal_scores(count: int, seed: int = 11) -> list[float]:
    rng = random.Random(seed)
    return [abs(rng.gauss(0.0, 1.0)) for _ in range(count)]


# -- the guarantee -----------------------------------------------------------


@pytest.mark.parametrize("alpha", [0.01, 0.05, 0.10, 0.20])
def test_a_normal_observation_alerts_at_most_alpha_of_the_time(alpha: float) -> None:
    """The whole claim: under exchangeability the false-alarm rate is bounded
    by the level, in finite samples, with no distributional assumption.

    Measured over two thousand independent calibration sets rather than
    asserted, because this is the property the product is sold on.
    """
    rng = random.Random(7)
    fired = 0
    trials = 2000
    for _ in range(trials):
        calibration = [abs(rng.gauss(0, 1)) for _ in range(100)]
        observation = abs(rng.gauss(0, 1))
        p = ConformalCalibrator(calibration).p_value(observation)
        assert isinstance(p, ConformalP)
        fired += p.value <= alpha
    empirical = fired / trials
    # Bounded above by the level, allowing for the sampling noise of 2000 draws.
    assert empirical <= alpha + 3 * (alpha * (1 - alpha) / trials) ** 0.5


def test_the_guarantee_survives_a_distribution_no_z_score_would() -> None:
    """A row count is not Gaussian and never was. Conformal does not care,
    which is the point of using it rather than three sigma."""
    rng = random.Random(3)
    fired = 0
    trials = 2000
    for _ in range(trials):
        # Heavy-tailed and skewed: a mixture that a normal threshold would
        # misjudge badly in both directions.
        def draw() -> float:
            return rng.expovariate(1 / 50) if rng.random() < 0.8 else rng.expovariate(1 / 500)

        p = ConformalCalibrator([draw() for _ in range(100)]).p_value(draw())
        assert isinstance(p, ConformalP)
        fired += p.value <= 0.05
    assert fired / trials <= 0.05 + 0.015


def test_the_plus_one_is_the_guarantee_and_not_rounding() -> None:
    """Without it the smallest p-value is zero, so a point more extreme than
    everything seen rejects at any level at all and the false-alarm rate
    becomes 1/n rather than alpha. It is right about 95% of the time on twenty
    calibration points, which is exactly the kind of wrong that ships."""
    calibrator = ConformalCalibrator([float(i) for i in range(50)])
    p = calibrator.p_value(1000.0)
    assert isinstance(p, ConformalP)
    assert p.value > 0.0
    assert p.value == pytest.approx(1 / 51)


# -- resolution --------------------------------------------------------------


def test_a_p_value_cannot_be_finer_than_the_history_supports() -> None:
    """Fifty calibration points cannot express 0.001, and printing it anyway is
    the difference between a number and a claim."""
    p = ConformalCalibrator([float(i) for i in range(50)]).p_value(1000.0)
    assert isinstance(p, ConformalP)
    assert p.resolution == pytest.approx(1 / 51)
    assert not p.honours(0.001)
    assert p.honours(0.05)


def test_a_saturated_p_value_says_at_most_rather_than_equals() -> None:
    """Reporting the floor as a point estimate claims precision it does not
    have."""
    p = ConformalCalibrator([float(i) for i in range(100)]).p_value(1e9)
    assert isinstance(p, ConformalP)
    assert p.is_saturated
    assert "p ≤" in p.describe()
    assert "smallest value this much history can express" in p.describe()


def test_an_ordinary_p_value_does_not_claim_to_be_a_bound() -> None:
    p = ConformalCalibrator([float(i) for i in range(100)]).p_value(50.0)
    assert isinstance(p, ConformalP)
    assert not p.is_saturated
    assert p.describe().startswith("p = ")


# -- weighting for drift -----------------------------------------------------


def test_recency_weighting_costs_resolution_and_the_cost_is_reported() -> None:
    """A short half-life tracks a moving regime and leaves few effective points
    to calibrate against. Quoting n instead of the effective n is how a monitor
    with a six-month window claims a precision it has a fortnight's worth of."""
    scores = normal_scores(200)
    plain = ConformalCalibrator(scores)
    weighted = ConformalCalibrator(scores, weights=recency_weights(200, half_life=20))
    assert plain.effective_n == 200
    assert weighted.effective_n < 80
    assert weighted.resolution > plain.resolution


def test_a_weighted_p_value_does_not_claim_to_be_exact() -> None:
    """Weighted conformal trades exactness for robustness, and a number that
    overstates its own rigour is worse than no number."""
    p = ConformalCalibrator(normal_scores(200), weights=recency_weights(200, half_life=20)).p_value(
        2.0
    )
    assert isinstance(p, ConformalP)
    assert not p.exact
    assert p.coverage_gap > 0
    assert "validity is approximate" in p.describe()


def test_weighting_tracks_a_shifted_regime_that_unweighted_calibration_misses() -> None:
    """The reason to pay the resolution cost: after a level shift, the old
    calibration set says every new observation is extreme, and the weighted one
    has mostly forgotten it."""
    rng = random.Random(5)
    old = [abs(rng.gauss(0, 1)) for _ in range(150)]
    new = [abs(rng.gauss(3, 1)) for _ in range(150)]
    scores = old + new
    observation = abs(rng.gauss(3, 1))

    unweighted = ConformalCalibrator(scores).p_value(observation)
    weighted = ConformalCalibrator(
        scores, weights=recency_weights(len(scores), half_life=25)
    ).p_value(observation)
    assert isinstance(unweighted, ConformalP) and isinstance(weighted, ConformalP)
    # The new normal is unremarkable to the weighted calibrator and alarming to
    # the one still remembering the old regime.
    assert weighted.value > unweighted.value


def test_mismatched_weights_are_refused() -> None:
    with pytest.raises(ValueError, match="one weight per point"):
        ConformalCalibrator([1.0, 2.0], weights=[1.0])


# -- honest refusals ---------------------------------------------------------


def test_too_little_history_produces_no_p_value_and_says_why() -> None:
    """A monitor that silently returns nothing is a monitor that silently stops
    working."""
    result = ConformalCalibrator([1.0, 2.0, 3.0]).p_value(9.0)
    assert isinstance(result, Uncalibrated)
    assert "below the minimum" in result.reason
    assert "cannot honour any useful budget" in result.reason


def test_a_non_finite_observation_is_refused_rather_than_ranked() -> None:
    result = ConformalCalibrator(normal_scores(100)).p_value(float("nan"))
    assert isinstance(result, Uncalibrated)


def test_a_window_older_than_its_decay_says_so() -> None:
    """Rather than dividing by zero or returning a p-value of one."""
    result = ConformalCalibrator(normal_scores(100), weights=[0.0] * 100).p_value(1.0)
    assert isinstance(result, Uncalibrated)
    assert "widen the window" in result.reason.lower()


# -- the threshold, for a UI that wants a number ----------------------------


def test_a_threshold_can_be_shown_instead_of_a_p_value() -> None:
    calibrator = ConformalCalibrator([float(i) for i in range(100)])
    threshold = calibrator.quantile(0.05)
    assert threshold is not None
    p = calibrator.p_value(threshold)
    assert isinstance(p, ConformalP)
    assert p.value <= 0.05 + 1e-9


def test_no_threshold_is_offered_for_a_level_the_history_cannot_express() -> None:
    """Returning the largest score seen would be a threshold that means
    nothing."""
    assert ConformalCalibrator([float(i) for i in range(50)]).quantile(0.001) is None


# -- adaptive ----------------------------------------------------------------


def test_the_adaptive_level_tightens_when_alerts_exceed_the_budget() -> None:
    """The case weighting cannot handle: the shape of normal has changed and
    the monitor would otherwise alert on every observation until somebody
    notices."""
    adaptive = AdaptiveCalibrator(0.05, step=0.01)
    for _ in range(50):
        adaptive.observe(alerted=True)
    level = adaptive.level
    assert level.is_tightened
    assert "the data has moved" in level.describe()


def test_the_adaptive_level_loosens_when_nothing_has_alerted_in_a_long_time() -> None:
    adaptive = AdaptiveCalibrator(0.05, step=0.01)
    for _ in range(50):
        adaptive.observe(alerted=False)
    assert adaptive.level.is_loosened


def test_the_long_run_alert_rate_converges_to_the_budget_under_drift() -> None:
    """The guarantee adaptive conformal actually offers: not exact marginal
    validity, but a realised rate that tracks the target whatever the data
    does. Measured against a stream whose distribution shifts underneath it.
    """
    rng = random.Random(13)
    adaptive = AdaptiveCalibrator(0.10, step=0.05, window=400)
    alerts = 0
    for step in range(2000):
        # A stream that shifts every 500 observations, so a fixed level would
        # spend long stretches far from budget in both directions. The shifts
        # are within a standard deviation or so: large enough that a fixed
        # level drifts badly, small enough that the p-values still discriminate
        # — beyond that no level can help, which the next test covers.
        centre = [0.0, 0.8, 0.3, 1.2][step // 500]
        calibration = [abs(rng.gauss(0, 1)) for _ in range(200)]
        observation = abs(rng.gauss(centre, 1))
        p = ConformalCalibrator(calibration).p_value(observation)
        assert isinstance(p, ConformalP)
        alerted, _ = adaptive.judge(p)
        alerts += alerted
    assert 0.05 <= alerts / 2000 <= 0.18


def test_adapting_cannot_help_when_every_p_value_is_at_its_floor() -> None:
    """The limit, found by a test that assumed otherwise.

    Shift the data far enough and every observation is more extreme than the
    whole calibration set, so every p-value equals 1/(n+1) and there is no
    threshold between alerting on all of them and none. The level oscillates
    and the realised rate has nothing to do with the budget — which the rate
    alone does not reveal, because it looks like an ordinary overshoot. The
    honest response is to say the calibration set no longer describes the data,
    not to adapt harder.
    """
    rng = random.Random(13)
    adaptive = AdaptiveCalibrator(0.10, step=0.05, window=200)
    for _ in range(400):
        calibration = [abs(rng.gauss(0, 1)) for _ in range(200)]
        p = ConformalCalibrator(calibration).p_value(abs(rng.gauss(8, 1)))
        assert isinstance(p, ConformalP)
        adaptive.judge(p)
    level = adaptive.level
    assert level.is_powerless
    assert "no longer describes this data" in level.describe()
    assert not adaptive.level.is_powerless or level.saturated > 0.9


def test_a_target_that_is_not_a_probability_is_refused() -> None:
    with pytest.raises(ValueError, match="not a probability"):
        AdaptiveCalibrator(1.5)
