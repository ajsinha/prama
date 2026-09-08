"""When a control runs, and what caused it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time

import pytest

from prama.core.calendars import ALWAYS_OPEN, BusinessCalendar
from prama.core.errors import ValidationError
from prama.schedule import (
    ArrivalTrigger,
    CalendarTrigger,
    DependencyTrigger,
    IntervalTrigger,
    ManualTrigger,
    TriggerKind,
    next_due,
)

TARGET2 = BusinessCalendar(
    "TARGET2",
    timezone="Europe/Berlin",
    holidays=frozenset({date(2026, 4, 3), date(2026, 4, 6)}),
)


class TestInterval:
    def test_it_fires_on_the_grid(self) -> None:
        trigger = IntervalTrigger(minutes=60)
        assert trigger.next_after(datetime(2026, 4, 2, 6, 15, tzinfo=UTC)) == datetime(
            2026, 4, 2, 7, 0, tzinfo=UTC
        )

    def test_an_offset_staggers_two_datasets_apart(self) -> None:
        # Two hourly datasets both firing at the top of the hour collide on the
        # same source. Staggering is a property of the schedule, not a hack in
        # a worker.
        moment = datetime(2026, 4, 2, 6, 5, tzinfo=UTC)
        plain = IntervalTrigger(minutes=60).next_after(moment)
        offset = IntervalTrigger(minutes=60, offset_minutes=20).next_after(moment)
        assert plain != offset
        assert offset.minute == 20

    def test_a_non_positive_interval_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="positive interval"):
            IntervalTrigger(minutes=0)

    def test_it_describes_itself_in_the_largest_sensible_unit(self) -> None:
        assert IntervalTrigger(minutes=1440).describe() == "every 1 day(s)"
        assert IntervalTrigger(minutes=120).describe() == "every 2 hour(s)"
        assert IntervalTrigger(minutes=45).describe() == "every 45 minutes"


class TestCalendar:
    def test_it_fires_at_the_declared_local_time(self) -> None:
        trigger = CalendarTrigger(at=time(6, 30), calendar=TARGET2)
        # 06:30 in Berlin is 04:30 UTC in April.
        assert trigger.next_after(datetime(2026, 4, 2, 3, 0, tzinfo=UTC)).hour == 4

    def test_it_skips_a_holiday(self) -> None:
        # A cron expression would fire on Good Friday and report a missing file
        # that was never coming — which is a morning of false alarms that
        # teaches somebody to stop reading them.
        trigger = CalendarTrigger(at=time(6, 30), calendar=TARGET2)
        after_thursday = trigger.next_after(datetime(2026, 4, 2, 12, 0, tzinfo=UTC))
        assert after_thursday.date() == date(2026, 4, 7)

    def test_the_local_time_holds_across_a_clock_change(self) -> None:
        trigger = CalendarTrigger(at=time(6, 30), calendar=TARGET2)
        winter = trigger.next_after(datetime(2026, 1, 14, 12, 0, tzinfo=UTC))
        summer = trigger.next_after(datetime(2026, 7, 14, 12, 0, tzinfo=UTC))
        assert winter.hour == 5  # CET
        assert summer.hour == 4  # CEST

    def test_a_calendar_with_no_business_days_is_refused_loudly(self) -> None:
        closed = BusinessCalendar("closed", weekend_days=frozenset(range(7)))
        with pytest.raises(ValidationError, match="no business day"):
            CalendarTrigger(at=time(6, 30), calendar=closed).next_after(
                datetime(2026, 4, 2, tzinfo=UTC)
            )


class TestArrival:
    def test_without_a_deadline_it_waits_indefinitely(self) -> None:
        trigger = ArrivalTrigger(feed="positions")
        assert trigger.next_after(datetime(2026, 4, 2, tzinfo=UTC)) is None
        assert "when positions arrives" in trigger.describe()

    def test_a_deadline_is_when_absence_becomes_a_finding(self) -> None:
        # A trigger that only fires on arrival can never report that nothing
        # arrived, and a feed that silently stops is the failure the platform
        # exists to catch.
        trigger = ArrivalTrigger(feed="positions", due_by=time(6, 30), calendar=TARGET2)
        due = trigger.next_after(datetime(2026, 4, 2, 3, 0, tzinfo=UTC))
        assert due is not None
        assert "whether it has or not" in trigger.describe()


class TestDependencyAndManual:
    def test_a_dependency_never_fires_on_a_clock(self) -> None:
        trigger = DependencyTrigger(after=("general_ledger",), require_pass=True)
        assert trigger.next_after(datetime(2026, 4, 2, tzinfo=UTC)) is None
        assert "after general_ledger pass" in trigger.describe()

    def test_running_versus_passing_are_different_declarations(self) -> None:
        # A reconciliation needs its inputs sound; a coverage report wants to
        # run regardless of what it finds.
        assert "run" in DependencyTrigger(after=("x",)).describe()
        assert "pass" in DependencyTrigger(after=("x",), require_pass=True).describe()

    def test_a_manual_trigger_records_who_asked(self) -> None:
        # "The schedule" and "the head of market risk, at 4pm, during an
        # investigation" are different answers to the same question.
        trigger = ManualTrigger(requested_by="a.roy")
        assert trigger.kind is TriggerKind.MANUAL
        assert "a.roy" in trigger.describe()


class TestSeveralTriggers:
    def test_the_earliest_wins(self) -> None:
        # A dataset may have an arrival trigger for promptness and a calendar
        # trigger for the day the arrival never comes.
        moment = datetime(2026, 4, 2, 3, 0, tzinfo=UTC)
        soon = IntervalTrigger(minutes=30)
        later = CalendarTrigger(at=time(23, 0), calendar=ALWAYS_OPEN)
        assert next_due([soon, later], moment) == soon.next_after(moment)

    def test_event_only_triggers_contribute_nothing_to_a_due_time(self) -> None:
        moment = datetime(2026, 4, 2, 3, 0, tzinfo=UTC)
        assert next_due([DependencyTrigger(after=("x",)), ManualTrigger()], moment) is None

    def test_no_triggers_means_nothing_is_due(self) -> None:
        assert next_due([], datetime(2026, 4, 2, tzinfo=UTC)) is None
