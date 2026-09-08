"""Business calendars.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time

import pytest

from prama.core.calendars import (
    ALWAYS_OPEN,
    WEEKDAYS,
    BusinessCalendar,
    CalendarRegistry,
)
from prama.core.errors import ValidationError

EASTER_2026 = frozenset({date(2026, 4, 3), date(2026, 4, 6)})
TARGET2 = BusinessCalendar("TARGET2", timezone="Europe/Berlin", holidays=EASTER_2026)


class TestBusinessDays:
    def test_weekends_and_holidays_are_not_business_days(self) -> None:
        assert not TARGET2.is_business_day(date(2026, 4, 4))  # Saturday
        assert not TARGET2.is_business_day(date(2026, 4, 3))  # Good Friday
        assert TARGET2.is_business_day(date(2026, 4, 2))

    def test_a_weekend_rule_is_a_parameter_not_an_assumption(self) -> None:
        # Gulf markets rest Friday and Saturday. Hardcoding Sat/Sun would make
        # the platform quietly wrong in a whole region.
        gulf = BusinessCalendar("Gulf", weekend_days=frozenset({4, 5}))
        assert gulf.is_business_day(date(2026, 4, 5))  # Sunday
        assert not gulf.is_business_day(date(2026, 4, 3))  # Friday

    def test_next_and_previous_skip_the_whole_break(self) -> None:
        assert TARGET2.next_business_day(date(2026, 4, 2)) == date(2026, 4, 7)
        assert TARGET2.previous_business_day(date(2026, 4, 7)) == date(2026, 4, 2)

    def test_shift_settles_t_plus_two_correctly(self) -> None:
        # The reason settlement dates need a calendar at all.
        assert TARGET2.shift(date(2026, 4, 2), 2) == date(2026, 4, 8)
        assert TARGET2.shift(date(2026, 4, 8), -2) == date(2026, 4, 2)

    def test_counting_is_symmetric(self) -> None:
        assert TARGET2.business_days_between(date(2026, 4, 1), date(2026, 4, 8)) == 3
        assert TARGET2.business_days_between(date(2026, 4, 8), date(2026, 4, 1)) == -3

    def test_always_open_counts_every_day(self) -> None:
        assert ALWAYS_OPEN.is_business_day(date(2026, 4, 4))
        assert WEEKDAYS.is_business_day(date(2026, 4, 3))  # no holidays loaded


class TestBusinessDate:
    def test_a_weekend_arrival_belongs_to_the_preceding_business_day(self) -> None:
        # A file landing at 03:00 Saturday belongs to Friday's run, not to a
        # Saturday that never existed.
        assert TARGET2.business_date_of(datetime(2026, 4, 11, 3, 0, tzinfo=UTC)) == date(
            2026, 4, 10
        )

    def test_the_day_boundary_moves_overnight_batch_to_the_day_before(self) -> None:
        overnight = BusinessCalendar("overnight", day_boundary=time(2, 0))
        assert overnight.business_date_of(datetime(2026, 4, 8, 1, 30, tzinfo=UTC)) == date(
            2026, 4, 7
        )
        assert overnight.business_date_of(datetime(2026, 4, 8, 3, 30, tzinfo=UTC)) == date(
            2026, 4, 8
        )

    def test_a_local_deadline_does_not_drift_with_the_clocks(self) -> None:
        # 06:30 written by someone in Berlin must not move by an hour in summer.
        winter = TARGET2.expected_at(date(2026, 1, 15), time(6, 30))
        summer = TARGET2.expected_at(date(2026, 7, 15), time(6, 30))
        assert winter.hour == 5  # CET  = UTC+1
        assert summer.hour == 4  # CEST = UTC+2


class TestRegistry:
    def test_an_unknown_calendar_is_refused_rather_than_assumed(self) -> None:
        # Silently treating it as weekdays would produce controls that look
        # right and fire on the wrong days.
        registry = CalendarRegistry()
        with pytest.raises(ValidationError) as caught:
            registry.get("TARGET2")
        assert "wrong days" in caught.value.remedy

    def test_a_registered_calendar_is_found_case_insensitively(self) -> None:
        registry = CalendarRegistry()
        registry.register(TARGET2)
        assert registry.get("target2").name == "TARGET2"

    def test_no_calendar_named_means_every_day_counts(self) -> None:
        assert CalendarRegistry().get(None) is ALWAYS_OPEN

    def test_a_bad_timezone_is_caught_at_declaration(self) -> None:
        with pytest.raises(ValidationError, match="unknown timezone"):
            BusinessCalendar("nowhere", timezone="Mars/Olympus")
