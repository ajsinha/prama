"""When a control runs, and what caused it to.

Five kinds, because data arrives in five ways and a scheduler that offered only
cron would make four of them somebody's cron expression — which is how a
platform ends up unable to say *why* something ran.

* **Interval** — every so often. The simple case, and the one that is right for
  a table nobody can tell you the arrival time of.
* **Calendar** — at a time, on business days, in a named calendar. What a feed
  with a declared 06:30 arrival actually needs, and wrong as a cron expression
  the moment a holiday lands on a Monday.
* **Arrival** — when the data lands. The only trigger that gets the answer as
  early as it can be got, and the only one that does not waste a scan on a day
  the file is late.
* **Dependency** — after another dataset's controls have run. So a
  reconciliation does not fire against half a ledger.
* **Manual** — somebody asked. Recorded distinctly because "who caused this
  run" is a question the evidence has to answer, and "the schedule" and "the
  head of market risk, at 4pm, during an investigation" are different answers.

Every trigger answers the same two questions: when is the next run due, and what
should the evidence say caused it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
from abc import ABC, abstractmethod
from datetime import date, datetime, time, timedelta
from typing import Any

from prama.core.calendars import ALWAYS_OPEN, BusinessCalendar
from prama.core.errors import ValidationError


class TriggerKind(enum.Enum):
    INTERVAL = "interval"
    CALENDAR = "calendar"
    ARRIVAL = "arrival"
    DEPENDENCY = "dependency"
    MANUAL = "manual"

    @property
    def is_time_based(self) -> bool:
        """Whether a due time can be computed without waiting for something."""
        return self in (TriggerKind.INTERVAL, TriggerKind.CALENDAR)


class Trigger(ABC):
    """Something that decides a control should run."""

    kind: TriggerKind = TriggerKind.MANUAL

    @abstractmethod
    def next_after(self, moment: datetime) -> datetime | None:
        """When this trigger next fires, or None if it waits on an event."""

    @abstractmethod
    def describe(self) -> str:
        """In the words somebody would use to declare it."""

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "describes": self.describe()}


@dataclasses.dataclass(frozen=True, slots=True)
class IntervalTrigger(Trigger):
    """Every *n* minutes, from a fixed origin."""

    minutes: int = 60
    #: The point the interval is measured from, so two datasets on an hourly
    #: cadence do not both fire at the top of the hour and collide on the same
    #: source. Staggering is a property of the schedule, not a hack in a worker.
    offset_minutes: int = 0
    kind: TriggerKind = dataclasses.field(default=TriggerKind.INTERVAL, init=False)

    def __post_init__(self) -> None:
        if self.minutes <= 0:
            raise ValidationError(
                "an interval trigger needs a positive interval",
                remedy="Give the number of minutes between runs, for example 60.",
                context={"minutes": self.minutes},
            )

    def next_after(self, moment: datetime) -> datetime:
        anchor = moment.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
            minutes=self.offset_minutes
        )
        elapsed = (moment - anchor).total_seconds() / 60
        steps = int(elapsed // self.minutes) + 1
        return anchor + timedelta(minutes=self.minutes * steps)

    def describe(self) -> str:
        if self.minutes % 1440 == 0:
            return f"every {self.minutes // 1440} day(s)"
        if self.minutes % 60 == 0:
            return f"every {self.minutes // 60} hour(s)"
        return f"every {self.minutes} minutes"


@dataclasses.dataclass(frozen=True, slots=True)
class CalendarTrigger(Trigger):
    """At a local time, on business days, in a named calendar.

    Not a cron expression. ``30 6 * * 1-5`` is wrong on Good Friday, wrong in a
    market that rests on Friday and Saturday, and wrong twice a year when the
    clocks move — and each of those is a morning of false alarms that teaches
    somebody to stop reading them.
    """

    at: time = time(6, 30)
    calendar: BusinessCalendar = ALWAYS_OPEN
    kind: TriggerKind = dataclasses.field(default=TriggerKind.CALENDAR, init=False)

    def next_after(self, moment: datetime) -> datetime:
        day = moment.date()
        for _ in range(400):  # a year of holidays is the practical bound
            if self.calendar.is_business_day(day):
                due = self.calendar.expected_at(day, self.at)
                if due > moment:
                    return due
            day = day + timedelta(days=1)
        raise ValidationError(
            f"the {self.calendar.name} calendar has no business day in the next year",
            remedy="Check the calendar's weekend days and holidays.",
            context={"calendar": self.calendar.name},
        )

    def describe(self) -> str:
        where = f" on {self.calendar.name} business days" if self.calendar.name else ""
        return f"at {self.at.strftime('%H:%M')}{where}"


@dataclasses.dataclass(frozen=True, slots=True)
class ArrivalTrigger(Trigger):
    """When the data lands.

    Carries a deadline as well, because a trigger that only fires on arrival
    can never report that nothing arrived — and a feed that silently stops is
    the failure this platform exists to catch.
    """

    feed: str = ""
    due_by: time | None = None
    calendar: BusinessCalendar = ALWAYS_OPEN

    kind: TriggerKind = dataclasses.field(default=TriggerKind.ARRIVAL, init=False)

    def next_after(self, moment: datetime) -> datetime | None:
        """The deadline, which is when absence becomes a finding.

        None when no deadline is declared: the trigger then waits indefinitely,
        and the platform says so rather than inventing a time by which the data
        was supposed to have appeared.
        """
        if self.due_by is None:
            return None
        return CalendarTrigger(at=self.due_by, calendar=self.calendar).next_after(moment)

    def describe(self) -> str:
        if self.due_by is None:
            return f"when {self.feed} arrives"
        return (
            f"when {self.feed} arrives, and by {self.due_by.strftime('%H:%M')} "
            f"whether it has or not"
        )


@dataclasses.dataclass(frozen=True, slots=True)
class DependencyTrigger(Trigger):
    """After another dataset's controls have finished.

    So a reconciliation does not fire against half a ledger, and a derived
    dataset is not judged before the thing it derives from has been.
    """

    after: tuple[str, ...] = ()
    #: Whether the upstream must have passed, or merely have run. Both are
    #: legitimate: a reconciliation needs its inputs sound, while a coverage
    #: report wants to run regardless of what it finds.
    require_pass: bool = False
    kind: TriggerKind = dataclasses.field(default=TriggerKind.DEPENDENCY, init=False)

    def next_after(self, moment: datetime) -> datetime | None:  # noqa: ARG002
        """Never on its own. This trigger waits on an upstream, not a clock."""
        return None

    def describe(self) -> str:
        condition = "pass" if self.require_pass else "run"
        return f"after {', '.join(self.after)} {condition}"


@dataclasses.dataclass(frozen=True, slots=True)
class ManualTrigger(Trigger):
    """Somebody asked."""

    requested_by: str = ""
    kind: TriggerKind = dataclasses.field(default=TriggerKind.MANUAL, init=False)

    def next_after(self, moment: datetime) -> datetime | None:  # noqa: ARG002
        """Never. Somebody has to ask."""
        return None

    def describe(self) -> str:
        return f"when {self.requested_by or 'somebody'} asks"


def next_due(triggers: list[Trigger], moment: datetime) -> datetime | None:
    """The earliest of several triggers.

    A dataset may have more than one — an arrival trigger for promptness and a
    calendar trigger for the day the arrival never comes — and the schedule is
    whichever fires first.
    """
    times = [t for t in (trigger.next_after(moment) for trigger in triggers) if t is not None]
    return min(times) if times else None


def business_days_between(calendar: BusinessCalendar, start: date, end: date) -> int:
    return calendar.business_days_between(start, end)
