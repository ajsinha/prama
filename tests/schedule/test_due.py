"""What is due, and why the rest is not.

"Which controls should run now?" invites a list. What an operator needs is a
list *and* an account of everything left out, because a control that silently
stops being scheduled is indistinguishable from one that is passing. These
tests are mostly about the second half.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta

import pytest

from prama.core.errors import ValidationError
from prama.schedule import Schedule
from prama.schedule.spec import DEFAULT, MINIMUM_MINUTES, describe, parse

NOW = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)


@dataclasses.dataclass(frozen=True)
class FakeControl:
    control_id: str
    dataset: str = "positions_eod"
    schedule: str = "daily"


def _plan(*controls: FakeControl, last_run: dict[str, datetime] | None = None) -> object:
    return Schedule().plan(list(controls), now=NOW, last_run=last_run or {})


class TestParsing:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("daily", "every 1 day(s)"),
            ("hourly", "every 1 hour(s)"),
            ("every 15 minutes", "every 15 minutes"),
            ("every 4 hours", "every 4 hour(s)"),
            ("manual", "when somebody asks"),
        ],
    )
    def test_the_forms_people_write(self, text: str, expected: str) -> None:
        assert parse(text).describe() == expected

    def test_a_time_of_day_becomes_a_calendar_trigger(self) -> None:
        assert "06:30" in parse("06:30").describe()

    def test_an_unknown_calendar_is_refused_rather_than_assumed(self) -> None:
        """A control declared against a calendar nobody loaded would look right
        and fire on the wrong days."""
        with pytest.raises(ValidationError, match="no calendar named"):
            parse("06:30 TARGET2")

    def test_cron_is_refused_with_the_reason(self) -> None:
        """It cannot express a business calendar, and a schedule that is wrong
        on a holiday is a morning of false alarms."""
        with pytest.raises(ValidationError, match="not a schedule"):
            parse("30 6 * * 1-5")

    def test_a_cadence_below_the_floor_is_refused_not_clamped(self) -> None:
        """Silently running something less often than it says is worse than
        saying no."""
        with pytest.raises(ValidationError, match="below the"):
            parse(f"every {MINIMUM_MINUTES - 1} minutes")

    def test_an_empty_schedule_is_the_stated_default(self) -> None:
        assert parse("").describe() == parse(DEFAULT).describe()

    def test_a_nonsense_time_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="not a time of day"):
            parse("99:99")

    def test_describe_never_raises(self) -> None:
        """It is what a list of controls prints beside each row, and one
        unparseable schedule must not take the page down — it has to be
        visible as broken instead."""
        assert "unreadable" in describe("30 6 * * 1-5")


class TestWhatIsDue:
    def test_a_control_that_has_never_run_is_due_now(self) -> None:
        """So a control accepted this afternoon is checked tonight rather than
        at whatever boundary its cadence would next reach."""
        plan = _plan(FakeControl("c1"))
        assert [item.control_id for item in plan.due] == ["c1"]
        assert plan.due[0].has_never_run

    def test_a_control_run_recently_is_not_due(self) -> None:
        plan = _plan(
            FakeControl("c1", schedule="daily"),
            last_run={"c1": NOW - timedelta(minutes=5)},
        )
        assert plan.due == ()
        assert [item.reason for item in plan.skipped] == ["not_due"]

    def test_a_control_past_its_interval_is_due(self) -> None:
        plan = _plan(
            FakeControl("c1", schedule="every 15 minutes"),
            last_run={"c1": NOW - timedelta(hours=3)},
        )
        assert len(plan.due) == 1

    def test_the_skip_says_when_it_will_next_run(self) -> None:
        plan = _plan(
            FakeControl("c1", schedule="daily"), last_run={"c1": NOW - timedelta(minutes=1)}
        )
        assert "next at" in plan.skipped[0].detail


class TestSkipsThatAreNotDefects:
    def test_a_manual_control_is_left_alone(self) -> None:
        plan = _plan(FakeControl("c1", schedule="manual"))
        assert plan.due == ()
        assert plan.skipped[0].reason == "manual"
        assert not plan.skipped[0].is_a_defect

    def test_an_arrival_trigger_is_not_run_on_a_timer(self) -> None:
        """It fires on a feed landing. A timer-driven pass must leave it alone
        rather than guess a cadence for it."""
        plan = _plan(FakeControl("c1", schedule="on arrival"))
        assert plan.due == ()
        assert plan.skipped[0].reason == "waits_for_arrival"
        assert not plan.skipped[0].is_a_defect


class TestAnUnreadableScheduleIsADefect:
    def test_it_is_not_silently_defaulted_to_daily(self) -> None:
        """Quietly running it on a cadence nobody chose would hide the problem
        for as long as it kept passing."""
        plan = _plan(FakeControl("c1", schedule="30 6 * * 1-5"))
        assert plan.due == ()
        assert plan.skipped[0].reason == "unreadable"

    def test_it_is_reported_apart_from_the_ordinary_skips(self) -> None:
        """A control that will never run again and has no verdict to say so is
        a different fact from one that is simply not due yet."""
        plan = _plan(
            FakeControl("c1", schedule="30 6 * * 1-5"),
            FakeControl("c2", schedule="manual"),
        )
        assert [item.control_id for item in plan.defects] == ["c1"]
        assert len(plan.skipped) == 2

    def test_the_summary_says_it_will_never_run(self) -> None:
        plan = _plan(FakeControl("c1", schedule="nonsense"))
        assert "never run until it is fixed" in plan.describe()

    def test_one_bad_schedule_does_not_stop_the_others(self) -> None:
        plan = _plan(
            FakeControl("c1", schedule="nonsense"),
            FakeControl("c2", schedule="daily"),
        )
        assert [item.control_id for item in plan.due] == ["c2"]


class TestStaggering:
    def test_two_controls_do_not_share_an_offset_by_construction(self) -> None:
        """Without it, every hourly control in the estate fires at the top of
        the hour and lands on the source together."""
        from prama.schedule.due import _stagger

        offsets = {_stagger(f"control-{index}") for index in range(50)}
        assert len(offsets) > 20

    def test_the_offset_is_stable_across_restarts(self) -> None:
        """A random offset would re-stagger the estate on every deploy and make
        load unpredictable."""
        from prama.schedule.due import _stagger

        assert _stagger("c1") == _stagger("c1")
