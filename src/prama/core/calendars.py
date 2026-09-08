"""Business calendars.

Financial data is calendar-dominated, and getting the calendar wrong is the
difference between a useful monitor and a noise generator. A feed that arrives
every business day is *missing* on Tuesday and merely *absent* on Sunday, and a
platform that cannot tell those apart will page somebody every weekend until
they turn it off.

Deliberately small. A calendar here is a weekend rule plus a set of holidays;
the real ones — TARGET2, SIFMA, JPX, per-market settlement calendars with their
year-ahead schedules — arrive as versioned domain-pack content (docs/12 §7).
What matters now is that the *abstraction* exists, so nothing downstream has to
invent its own notion of "next business day".

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from prama.core.errors import ValidationError

#: Saturday and Sunday. Not universal — Gulf markets rest Friday and Saturday —
#: which is exactly why it is a parameter rather than an assumption.
WESTERN_WEEKEND: frozenset[int] = frozenset({5, 6})


@dataclasses.dataclass(frozen=True, slots=True)
class BusinessCalendar:
    """Which days count, and in whose timezone.

    The timezone is not decoration. A trade booked at 23:50 in New York is a
    different business date in Tokyo, and a feed's arrival window is stated in
    the calendar's local time, not the server's.
    """

    name: str
    timezone: str = "UTC"
    weekend_days: frozenset[int] = WESTERN_WEEKEND
    holidays: frozenset[date] = frozenset()
    #: Where the business day boundary falls, in local time. A cut-off after
    #: midnight is normal for overnight batch: 02:00 belongs to the day before.
    day_boundary: time = time(0, 0)

    def __post_init__(self) -> None:
        try:
            ZoneInfo(self.timezone)
        except Exception as exc:
            raise ValidationError(
                f"unknown timezone {self.timezone!r} for calendar {self.name!r}",
                remedy="Use an IANA timezone name such as Europe/London or UTC.",
                context={"calendar": self.name, "timezone": self.timezone},
                cause=exc,
            ) from exc

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def is_business_day(self, day: date) -> bool:
        return day.weekday() not in self.weekend_days and day not in self.holidays

    def next_business_day(self, day: date) -> date:
        candidate = day + timedelta(days=1)
        while not self.is_business_day(candidate):
            candidate += timedelta(days=1)
        return candidate

    def previous_business_day(self, day: date) -> date:
        candidate = day - timedelta(days=1)
        while not self.is_business_day(candidate):
            candidate -= timedelta(days=1)
        return candidate

    def shift(self, day: date, business_days: int) -> date:
        """Move *business_days* forward (or back, if negative)."""
        step = self.next_business_day if business_days >= 0 else self.previous_business_day
        for _ in range(abs(business_days)):
            day = step(day)
        return day

    def business_days_between(self, start: date, end: date) -> int:
        """Count business days in ``[start, end)``. Negative if end precedes start."""
        if end < start:
            return -self.business_days_between(end, start)
        count, cursor = 0, start
        while cursor < end:
            if self.is_business_day(cursor):
                count += 1
            cursor += timedelta(days=1)
        return count

    def business_date_of(self, moment: datetime) -> date:
        """Which business date an instant belongs to.

        Converts into the calendar's timezone, applies the day boundary, then
        rolls back to the previous business day if the result is a non-working
        day — because a file that lands at 03:00 on Saturday belongs to Friday's
        run, not to a Saturday that never existed.
        """
        local = moment.astimezone(self.zone)
        candidate = local.date()
        if local.time() < self.day_boundary:
            candidate -= timedelta(days=1)
        if not self.is_business_day(candidate):
            candidate = self.previous_business_day(candidate)
        return candidate

    def expected_at(self, business_date: date, at: time) -> datetime:
        """The instant a thing is due, as an absolute UTC time.

        Local time in, UTC out. An arrival window written as 06:30 by a person
        in London must not drift by an hour twice a year.
        """
        return datetime.combine(business_date, at, tzinfo=self.zone).astimezone(UTC)

    def with_holidays(self, holidays: set[date] | frozenset[date]) -> BusinessCalendar:
        return dataclasses.replace(self, holidays=frozenset(holidays))


#: Every day counts. The right default when nobody has said otherwise, and
#: honest about knowing nothing rather than guessing a market's calendar.
ALWAYS_OPEN = BusinessCalendar(name="always", weekend_days=frozenset())

#: Weekdays only, no holidays. What "business day" means before a real calendar
#: is loaded from a domain pack.
WEEKDAYS = BusinessCalendar(name="weekdays")


class CalendarRegistry:
    """Calendars by name, so a declaration can say ``TARGET2`` and mean it.

    An unknown calendar is refused rather than silently treated as weekdays: a
    rhythm declared against a calendar nobody loaded would produce controls that
    look right and fire on the wrong days.
    """

    def __init__(self) -> None:
        self._calendars: dict[str, BusinessCalendar] = {
            ALWAYS_OPEN.name: ALWAYS_OPEN,
            WEEKDAYS.name: WEEKDAYS,
        }

    def register(self, calendar: BusinessCalendar, *, replace: bool = False) -> None:
        key = calendar.name.lower()
        if key in self._calendars and not replace:
            raise ValidationError(
                f"a calendar named {calendar.name!r} is already registered",
                remedy="Choose a different name, or replace it deliberately.",
                context={"calendar": calendar.name},
            )
        self._calendars[key] = calendar

    def get(self, name: str | None) -> BusinessCalendar:
        if not name:
            return ALWAYS_OPEN
        try:
            return self._calendars[name.lower()]
        except KeyError:
            raise ValidationError(
                f"no calendar named {name!r} is loaded",
                remedy=(
                    f"Loaded: {', '.join(sorted(self._calendars)) or '(none)'}. "
                    f"Install the domain pack that provides it, or correct the name. "
                    f"Treating it as weekdays would produce controls that fire on the "
                    f"wrong days."
                ),
                context={"calendar": name, "loaded": sorted(self._calendars)},
            ) from None

    def names(self) -> list[str]:
        return sorted(self._calendars)


_default = CalendarRegistry()


def default_calendars() -> CalendarRegistry:
    return _default
