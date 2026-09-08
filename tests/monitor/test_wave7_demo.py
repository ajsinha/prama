"""Wave 7's demo, as a test.

"Set 'no more than two false alarms a month in this domain'; show the resulting
thresholds, the calibration curve, and what happens to the guarantee when a
regime shift is injected."

Written as a test rather than a script for the same reason as Wave 6's: a demo
not executed on every commit is a demo that works on the day it was recorded.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from prama.calibrate.conformal import ConformalCalibrator
from prama.calibrate.select import Budget, HierarchicalSelector, Level, Method
from prama.calibrate.validity import Validity, ValidityMonitor
from prama.core.calendars import BusinessCalendar
from prama.monitor.cards import PrecisionHistory, card_for
from prama.monitor.detect import RobustDeviation
from prama.monitor.fleet import Monitor, Observation
from prama.monitor.season import SeasonalModel, month_end_driver

WEEKDAYS = BusinessCalendar(name="wd", weekend_days=frozenset({5, 6}))

#: A domain of forty datasets, each watched on five metrics, running daily.
DATASETS = 40
METRICS = 5
RUNS_PER_MONTH = DATASETS * METRICS * 22


def seasonal() -> SeasonalModel:
    return SeasonalModel(calendar=WEEKDAYS, drivers={"month_end": month_end_driver(WEEKDAYS)})


def series(days: int, *, shift_at: int | None = None, seed: int = 4) -> list[Observation]:
    rng = random.Random(seed)
    season = seasonal()
    start = datetime(2024, 1, 1, 6, 0)
    out = []
    for index in range(days):
        when = start + timedelta(days=index)
        day = when.date()
        if not WEEKDAYS.is_business_day(day):
            base = 500.0
        elif season.period_end(day) != "none":
            base = 60_000.0
        else:
            base = 20_000.0
        if shift_at is not None and index >= shift_at:
            base *= 1.9
        out.append(Observation(value=base * rng.uniform(0.92, 1.08), at=when))
    return out


# -- the dial ----------------------------------------------------------------


def test_the_business_states_a_budget_and_gets_a_level() -> None:
    """ "No more than two false alarms a month in this domain" is a sentence
    somebody will actually say. Every competitor has a sensitivity slider and
    none can say what number it puts on the wall."""
    budget = Budget(false_alarms=2, tests_per_period=RUNS_PER_MONTH)
    assert budget.alpha < 0.001
    assert "4,400 monitor runs" in budget.describe()


def test_the_budget_is_refused_when_the_history_cannot_express_it() -> None:
    """Two a month across 4,400 runs needs a level of 0.00045, and a monitor
    with two years of daily history for one weekday has about a hundred
    comparable observations — which cannot express a p-value below 0.01.
    Printing a threshold anyway would be the lie this wave exists to stop."""
    budget = Budget(false_alarms=2, tests_per_period=RUNS_PER_MONTH)
    history = series(730)
    grouping = seasonal().group([item.at for item in history], datetime(2025, 12, 17, 6, 0))
    assert not budget.achievable_with(grouping.resolution)
    shortfall = budget.shortfall(grouping.resolution)
    assert "comparable observations before promising this one" in shortfall


def test_an_achievable_budget_produces_a_threshold_a_person_can_read() -> None:
    """For a UI that wants "this monitor fires below 17,400 rows" rather than a
    p-value."""
    history = [item.value for item in series(730)]
    detector = RobustDeviation()
    ordinary = [
        value
        for value, item in zip(history, series(730), strict=True)
        if WEEKDAYS.is_business_day(item.at.date())
        and seasonal().period_end(item.at.date()) == "none"
    ]
    calibrator = ConformalCalibrator(detector.scores(ordinary))
    threshold = calibrator.quantile(0.05)
    assert threshold is not None
    assert calibrator.quantile(0.0001) is None


# -- the realised volume -----------------------------------------------------


def test_the_alert_volume_tracks_the_declared_budget() -> None:
    """The criterion, measured end to end. Every observation here is normal, so
    every alert is a false alarm and the realised rate is directly comparable
    with what was promised."""
    history = series(900)
    watcher = Monitor("positions", "row_count", season=seasonal(), alpha=0.05, adaptive=True)
    alerts = judged = 0
    for index in range(600, 900):
        verdict = watcher.judge(history[index], history[:index])
        if verdict.p_value is None:
            continue
        judged += 1
        alerts += verdict.alerted
    realised = alerts / judged
    print(f"\n  declared 0.05, realised {realised:.4f} over {judged} judged days")
    assert judged > 200
    assert realised <= 0.05 + 0.03


def test_the_calibration_curve_can_be_plotted_for_this_monitor() -> None:
    """The artefact the acceptance criterion asks for, and the one no
    competitor can produce because none has a nominal level to compare
    against."""
    history = series(900)
    watcher = Monitor("positions", "row_count", season=seasonal(), alpha=0.05, adaptive=False)
    validity = ValidityMonitor(0.05, window=400)
    for index in range(600, 900):
        verdict = watcher.judge(history[index], history[:index])
        if verdict.p_value is not None:
            validity.observe(verdict.p_value.value)
    curve = validity.curve()
    points = curve.plot_points()
    assert len(points) == 7
    print(f"  calibration error {curve.calibration_error:.4f}")
    for nominal, empirical, low, high in points:
        assert low <= empirical <= high
        assert 0.0 < nominal < 1.0


# -- what happens when the regime shifts -------------------------------------


def test_a_regime_shift_is_detected_and_the_guarantee_degrades_visibly() -> None:
    """The last third of the demo, and the part that matters most.

    A monitor whose data has moved does not quietly go on printing its level.
    It keeps running, it stops claiming the level means what it says, and the
    disclosure travels on every alert — because the person reading one at three
    in the morning is not on the status page.
    """
    history = series(900, shift_at=700)
    watcher = Monitor("positions", "row_count", season=seasonal(), alpha=0.05, adaptive=False)
    verdicts = []
    for index in range(600, 900):
        verdict = watcher.judge(history[index], history[:index])
        if verdict.p_value is not None:
            verdicts.append(verdict)

    after_shift = [v for v in verdicts if v.observation.at >= history[700].at]
    assert after_shift
    report = watcher.validity
    print(f"  after the shift: {report.status.value}")
    assert report.status in (Validity.UNCALIBRATED, Validity.DRIFTING)
    assert not report.status.promise_holds

    # Every alert carries it, not only the dashboard.
    alerting = [v for v in after_shift if v.alerted]
    assert alerting
    assert "⚠" in alerting[-1].explain()
    assert "promised at most" in alerting[-1].explain()


def test_the_degraded_monitor_keeps_working_rather_than_stopping() -> None:
    """It goes on producing scores and p-values. What it stops doing is
    claiming a false-alarm rate."""
    history = series(900, shift_at=700)
    watcher = Monitor("positions", "row_count", season=seasonal(), alpha=0.05, adaptive=False)
    for index in range(600, 900):
        watcher.judge(history[index], history[:index])
    final = watcher.judge(Observation(1_000_000.0, history[-1].at + timedelta(days=1)), history)
    assert final.p_value is not None
    assert final.alerted


# -- the whole domain --------------------------------------------------------


def test_the_domain_wide_selection_honours_the_budget_across_the_fleet() -> None:
    """Per-monitor levels are not the same as how many wrong alerts a person
    sees, and the second is the only one anybody cares about."""
    rng = random.Random(21)
    hypotheses = []
    from prama.calibrate.select import Hypothesis

    for dataset in range(DATASETS):
        for metric in range(METRICS):
            hypotheses.append(
                Hypothesis(
                    identity=f"d{dataset}.m{metric}",
                    p_value=rng.random(),
                    level=Level.CHECK,
                    parent=f"d{dataset}",
                )
            )
    selection = HierarchicalSelector(method=Method.BY).select(hypotheses, alpha=0.05)
    # Nothing is genuinely wrong, so almost nothing should be raised.
    assert selection.raised <= 2
    assert "assumes nothing about the dependence" in selection.describe()


def test_every_monitor_can_produce_its_card() -> None:
    """Including, honestly, the fact that its declared budget is finer than its
    history can express."""
    history = series(730)
    watcher = Monitor("positions", "row_count", season=seasonal(), alpha=0.0005, adaptive=False)
    verdict = watcher.judge(history[-1], history[:-1])
    built = card_for(
        "positions",
        "row_count",
        watcher.detector,
        alpha=0.0005,
        validity=watcher.validity,
        grouping=verdict.grouping,
        precision=PrecisionHistory(raised=12, confirmed=9, unreviewed=0),
        version="0.7.0",
    )
    rendered = built.render()
    assert "Blind to" in rendered
    assert "The promise cannot currently be kept" in rendered
    assert "12 alerts raised" in rendered
