"""A monitor, end to end: comparable, score, p-value, verdict.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from prama.calibrate.select import HierarchicalSelector
from prama.calibrate.validity import Validity
from prama.core.calendars import BusinessCalendar
from prama.monitor.detect import QuantileDistance, RobustDeviation
from prama.monitor.fleet import (
    MetricKind,
    Monitor,
    Observation,
    SegmentedMonitor,
)
from prama.monitor.season import SeasonalModel, month_end_driver

WEEKDAYS = BusinessCalendar(name="wd", weekend_days=frozenset({5, 6}))


def seasonal() -> SeasonalModel:
    return SeasonalModel(calendar=WEEKDAYS, drivers={"month_end": month_end_driver(WEEKDAYS)})


def history(days: int = 730, seed: int = 4) -> list[Observation]:
    """Row counts: 20k on weekdays, 60k at month-end, 500 at weekends."""
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
        out.append(Observation(value=base * rng.uniform(0.9, 1.1), at=when))
    return out


def monitor(**options: object) -> Monitor:
    return Monitor(
        "positions",
        "row_count",
        season=seasonal(),
        alpha=0.05,
        adaptive=False,
        **options,  # type: ignore[arg-type]
    )


# -- the seasonal claim ------------------------------------------------------


def test_an_ordinary_count_on_an_ordinary_day_is_not_an_alert() -> None:
    verdict = monitor().judge(Observation(20_400, datetime(2025, 12, 17, 6, 0)), history())
    assert not verdict.alerted


def test_a_month_end_count_on_an_ordinary_day_is_an_alert() -> None:
    """The case a band wide enough for month-end cannot see."""
    verdict = monitor().judge(Observation(61_000, datetime(2025, 12, 17, 6, 0)), history())
    assert verdict.alerted


def test_a_month_end_count_on_a_month_end_is_not_an_alert() -> None:
    """The case a band narrow enough for ordinary days false-alarms on, every
    month, until somebody widens it into uselessness."""
    verdict = monitor().judge(Observation(59_000, datetime(2025, 12, 31, 6, 0)), history())
    assert not verdict.alerted


def test_a_month_end_that_did_not_happen_is_an_alert() -> None:
    verdict = monitor().judge(Observation(20_400, datetime(2025, 12, 31, 6, 0)), history())
    assert verdict.alerted


# -- the explanation ---------------------------------------------------------


def test_the_alert_says_what_was_expected_and_what_it_was_compared_against() -> None:
    """ "The row count was low" is not an alert anybody can act on."""
    verdict = monitor().judge(Observation(20_400, datetime(2025, 12, 31, 6, 0)), history())
    explanation = verdict.explain()
    assert "20,400" in explanation
    assert "against a typical" in explanation
    assert "compared against" in explanation
    assert "p " in explanation


def test_a_monitor_that_cannot_judge_says_so_and_does_not_alert() -> None:
    """An alert meaning "I do not know" trains people to ignore alerts."""
    verdict = monitor().judge(Observation(20_400, datetime(2024, 1, 2, 6, 0)), [])
    assert not verdict.alerted
    assert verdict.uncalibrated is not None
    assert "no history" in verdict.explain()


def test_a_verdict_becomes_a_hypothesis_the_selector_can_rank() -> None:
    verdict = monitor().judge(Observation(61_000, datetime(2025, 12, 17, 6, 0)), history())
    hypothesis = verdict.hypothesis()
    assert hypothesis is not None
    assert hypothesis.identity == "positions.row_count"
    assert hypothesis.p_value == verdict.p_value.value  # type: ignore[union-attr]


def test_an_unjudgeable_monitor_offers_no_hypothesis() -> None:
    """Rather than a p-value of one, which would be a claim it cannot make."""
    verdict = monitor().judge(Observation(1.0, datetime(2024, 1, 2, 6, 0)), [])
    assert verdict.hypothesis() is None


# -- the budget --------------------------------------------------------------


def test_the_false_alarm_rate_tracks_the_declared_budget() -> None:
    """The differentiator, measured. Normal days, judged against their own
    history, should alert about as often as the level says and no more."""
    days = history(days=900)
    watcher = Monitor("positions", "row_count", season=seasonal(), alpha=0.05, adaptive=False)
    alerts = tested = 0
    for index in range(700, 900):
        observation = days[index]
        verdict = watcher.judge(observation, days[:index])
        if verdict.p_value is None:
            continue
        tested += 1
        alerts += verdict.alerted
    assert tested > 100
    assert alerts / tested <= 0.10


def test_the_validity_monitor_reports_on_the_monitor_itself() -> None:
    days = history(days=900)
    watcher = monitor()
    for index in range(700, 900):
        watcher.judge(days[index], days[:index])
    assert watcher.validity.status in (Validity.CALIBRATED, Validity.DRIFTING)


# -- segmentation ------------------------------------------------------------


def segmented_history(seed: int = 9) -> list[Observation]:
    rng = random.Random(seed)
    start = datetime(2025, 1, 1, 6, 0)
    out = []
    for index in range(400):
        when = start + timedelta(days=index)
        for entity in ("EMEA", "AMER", "APAC"):
            out.append(Observation(value=1000 * rng.uniform(0.95, 1.05), at=when, segment=entity))
    return out


def test_a_failure_in_one_segment_is_not_averaged_away() -> None:
    """ "0.4% of LEIs are missing" and "every LEI is missing for one entity" are
    the same number and different incidents."""
    watcher = SegmentedMonitor(
        "positions",
        "lei_present",
        ("EMEA", "AMER", "APAC"),
        alpha=0.05,
        adaptive=False,
    )
    when = datetime(2026, 2, 5, 6, 0)
    report = watcher.judge(
        [
            Observation(1000, when, "AMER"),
            Observation(1000, when, "APAC"),
            Observation(20, when, "EMEA"),
        ],
        segmented_history(),
    )
    alerting = {v.observation.segment for v in report.alerting}
    assert alerting == {"EMEA"}


def test_segments_form_one_family_so_a_fleet_wide_failure_is_one_finding() -> None:
    watcher = SegmentedMonitor(
        "positions",
        "row_count",
        tuple(f"E{index}" for index in range(10)),
        alpha=0.05,
        adaptive=False,
    )
    rng = random.Random(2)
    start = datetime(2025, 1, 1, 6, 0)
    past = [
        Observation(1000 * rng.uniform(0.95, 1.05), start + timedelta(days=d), f"E{e}")
        for d in range(300)
        for e in range(10)
    ]
    when = datetime(2025, 11, 1, 6, 0)
    report = watcher.judge([Observation(20, when, f"E{index}") for index in range(10)], past)
    selection = HierarchicalSelector().select(watcher.hypotheses(report), alpha=0.05)
    assert selection.raised == 1
    assert selection.findings[0].is_rolled_up


# -- detector choice ---------------------------------------------------------


def test_a_bounded_metric_gets_a_detector_that_does_not_model_it_as_symmetric() -> None:
    """A null rate cannot go below zero, and a symmetric measure spends half
    its sensitivity on the impossible side."""
    assert isinstance(Monitor("t", "nulls", kind=MetricKind.NULL_RATE).detector, QuantileDistance)
    assert isinstance(Monitor("t", "rows", kind=MetricKind.VOLUME).detector, RobustDeviation)


def test_a_fleet_report_separates_alerts_from_monitors_that_could_not_judge() -> None:
    """A monitor unable to judge for a fortnight is a real problem and a bad
    alert: it has nothing to say about the data, only about itself."""
    watcher = SegmentedMonitor("positions", "row_count", ("A", "B"), alpha=0.05, adaptive=False)
    when = datetime(2025, 6, 1, 6, 0)
    report = watcher.judge([Observation(1.0, when, "A"), Observation(1.0, when, "B")], [])
    assert len(report.unjudgeable) == 2
    assert not report.alerting
    assert "could not be judged" in report.describe()
