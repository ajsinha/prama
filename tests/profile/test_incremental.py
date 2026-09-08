"""Deciding what a re-examination actually has to read.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from prama.connect.spi import Snapshot, SnapshotKind
from prama.core.clock import Clock
from prama.profile import (
    IncrementalPlanner,
    Segmentation,
    SegmentGrain,
    SegmentLedger,
    SegmentState,
)

TODAY = date(2026, 4, 20)


class FixedClock(Clock):
    def now(self) -> datetime:
        return datetime(2026, 4, 20, 9, 0, tzinfo=UTC)

    def monotonic(self) -> float:
        return 0.0

    def epoch_millis(self) -> int:
        return 0


def exact(identifier: str = "0/1000") -> Snapshot:
    return Snapshot(kind=SnapshotKind.LSN, identifier=identifier, captured_at=FixedClock().now())


def inexact() -> Snapshot:
    return Snapshot(kind=SnapshotKind.WALL_CLOCK, identifier="now", captured_at=FixedClock().now())


def days(start: date, end: date) -> list:
    return Segmentation("booked", SegmentGrain.DAY).over_dates(start, end)


def planner(ledger: SegmentLedger | None = None, **kwargs) -> IncrementalPlanner:
    return IncrementalPlanner(ledger, clock=FixedClock(), **kwargs)


class TestFirstRun:
    def test_everything_is_new(self) -> None:
        plan = planner().plan("risk.positions", days(date(2026, 4, 1), date(2026, 4, 3)))
        assert all(d.state is SegmentState.NEW for d in plan.decisions)
        assert len(plan.to_read) == 3
        assert plan.saved_fraction == 0.0

    def test_the_plan_says_what_it_will_do_before_it_does_it(self) -> None:
        plan = planner().plan("risk.positions", days(date(2026, 4, 1), date(2026, 4, 3)))
        assert "Reading all 3 segments" in plan.render()


class TestSecondRun:
    def test_a_settled_segment_is_not_read_again(self) -> None:
        # The whole point: last March does not change, so a nightly refresh
        # should not keep paying to discover that.
        ledger, snapshot = SegmentLedger(), exact()
        segments = days(date(2026, 4, 1), date(2026, 4, 3))
        for segment in segments:
            ledger.record(
                "risk.positions", segment, snapshot=snapshot, rows=100, at=FixedClock().now()
            )
        plan = planner(ledger).plan("risk.positions", segments, snapshot=snapshot)
        assert plan.to_read == ()
        assert plan.saved_fraction == 1.0
        assert "Reading 0 of 3" in plan.render()

    def test_a_moved_snapshot_forces_a_re_read(self) -> None:
        ledger = SegmentLedger()
        segments = days(date(2026, 4, 1), date(2026, 4, 2))
        for segment in segments:
            ledger.record(
                "risk.positions", segment, snapshot=exact("0/1000"), rows=1, at=FixedClock().now()
            )
        plan = planner(ledger).plan("risk.positions", segments, snapshot=exact("0/2000"))
        assert all(d.state is SegmentState.CHANGED for d in plan.decisions)

    def test_a_newly_added_segment_is_read_and_the_rest_are_not(self) -> None:
        ledger, snapshot = SegmentLedger(), exact()
        known = days(date(2026, 4, 1), date(2026, 4, 2))
        for segment in known:
            ledger.record(
                "risk.positions", segment, snapshot=snapshot, rows=1, at=FixedClock().now()
            )
        plan = planner(ledger).plan(
            "risk.positions", days(date(2026, 4, 1), date(2026, 4, 3)), snapshot=snapshot
        )
        assert [s.key for s in plan.to_read] == ["2026-04-03"]


class TestTheMutableWindow:
    def test_recent_segments_are_re_read_even_when_nothing_moved(self) -> None:
        # A correction booked on Friday and settled on Monday would otherwise
        # never be seen, because the segment was profiled before it arrived.
        ledger, snapshot = SegmentLedger(), exact()
        recent = days(TODAY - timedelta(days=1), TODAY)
        for segment in recent:
            ledger.record(
                "risk.positions", segment, snapshot=snapshot, rows=1, at=FixedClock().now()
            )
        plan = planner(ledger).plan("risk.positions", recent, snapshot=snapshot)
        assert all(d.state is SegmentState.MUTABLE for d in plan.decisions)

    def test_the_window_is_configurable(self) -> None:
        ledger, snapshot = SegmentLedger(), exact()
        segments = days(TODAY - timedelta(days=10), TODAY - timedelta(days=10))
        for segment in segments:
            ledger.record(
                "risk.positions", segment, snapshot=snapshot, rows=1, at=FixedClock().now()
            )
        assert planner(ledger).plan("risk.positions", segments, snapshot=snapshot).to_read == ()
        wide = planner(ledger, mutable_days=30)
        assert len(wide.plan("risk.positions", segments, snapshot=snapshot).to_read) == 1

    def test_a_categorical_segment_never_settles(self) -> None:
        # By entity or by product there is no age, so nothing about it can be
        # called old enough to stop checking.
        ledger, snapshot = SegmentLedger(), exact()
        segments = Segmentation("entity", SegmentGrain.VALUE).over_values(["EMEA", "APAC"])
        for segment in segments:
            ledger.record(
                "risk.positions", segment, snapshot=snapshot, rows=1, at=FixedClock().now()
            )
        plan = planner(ledger).plan("risk.positions", segments, snapshot=snapshot)
        assert all(d.state is SegmentState.MUTABLE for d in plan.decisions)


class TestWhenNothingCanBeVerified:
    def test_an_inexact_snapshot_forces_a_full_re_read(self) -> None:
        # Assuming immutability that cannot be checked is how a number nobody
        # can reproduce turns up six months later.
        ledger = SegmentLedger()
        segments = days(date(2026, 4, 1), date(2026, 4, 3))
        for segment in segments:
            ledger.record(
                "risk.positions", segment, snapshot=exact(), rows=1, at=FixedClock().now()
            )
        plan = planner(ledger).plan("risk.positions", segments, snapshot=inexact())
        assert all(d.state is SegmentState.UNVERIFIABLE for d in plan.decisions)
        assert "no exact snapshot" in plan.decisions[0].state.reason

    def test_no_snapshot_at_all_is_treated_the_same(self) -> None:
        ledger = SegmentLedger()
        segments = days(date(2026, 4, 1), date(2026, 4, 1))
        ledger.record(
            "risk.positions", segments[0], snapshot=exact(), rows=1, at=FixedClock().now()
        )
        plan = planner(ledger).plan("risk.positions", segments, snapshot=None)
        assert plan.decisions[0].state is SegmentState.UNVERIFIABLE

    def test_a_segment_first_profiled_without_an_exact_marker_is_not_trusted(self) -> None:
        ledger = SegmentLedger()
        segments = days(date(2026, 4, 1), date(2026, 4, 1))
        ledger.record(
            "risk.positions", segments[0], snapshot=inexact(), rows=1, at=FixedClock().now()
        )
        plan = planner(ledger).plan("risk.positions", segments, snapshot=exact())
        assert plan.decisions[0].state is SegmentState.CHANGED


class TestTheLedger:
    def test_forgetting_a_dataset_forces_a_full_re_read(self) -> None:
        # Needed when a declaration changes in a way that invalidates earlier
        # profiles — a column reinterpreted, a segmentation redrawn.
        ledger, snapshot = SegmentLedger(), exact()
        segments = days(date(2026, 4, 1), date(2026, 4, 2))
        for segment in segments:
            ledger.record("a", segment, snapshot=snapshot, rows=1, at=FixedClock().now())
            ledger.record("b", segment, snapshot=snapshot, rows=1, at=FixedClock().now())
        ledger.forget("a")
        assert len(planner(ledger).plan("a", segments, snapshot=snapshot).to_read) == 2
        assert planner(ledger).plan("b", segments, snapshot=snapshot).to_read == ()

    def test_the_plan_serialises_with_a_reason_per_segment(self) -> None:
        payload = planner().plan("risk.positions", days(date(2026, 4, 1), date(2026, 4, 2)))
        assert payload.to_dict()["reading"] == 2
        assert payload.to_dict()["decisions"][0]["reason"] == "never profiled"
