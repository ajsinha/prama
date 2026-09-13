"""Reading a control's schedule.

A control carries its cadence as one short string, because that is what a
person types and what a generated control renders. This module is the only
place that string becomes a :class:`Trigger`, so "every 15 minutes" and
"06:30 TARGET2" mean the same thing to the scheduler, the console and the
explain output.

**Not cron.** ``30 6 * * 1-5`` is wrong on Good Friday, wrong in a market that
rests on Friday and Saturday, and wrong twice a year when the clocks move —
and each of those is a morning of false alarms that teaches somebody to stop
reading them. The forms accepted here name a calendar instead.

Accepted, and deliberately few:

    ``every 15 minutes`` · ``every 4 hours`` · ``daily``
    ``06:30``                     — daily at that time, every day
    ``06:30 TARGET2``             — at that time, on that calendar's business days
    ``on arrival``                — when the feed lands
    ``manual``                    — only when somebody asks

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import re
from datetime import time

from prama.core.calendars import CalendarRegistry, default_calendars
from prama.core.errors import ValidationError
from prama.schedule.trigger import (
    ArrivalTrigger,
    CalendarTrigger,
    IntervalTrigger,
    ManualTrigger,
    Trigger,
)

#: What a control gets when it says nothing. Daily rather than hourly, because
#: an unstated cadence is an unconsidered one, and the cost of guessing too
#: often is a bill and a load the owner never agreed to.
DEFAULT = "daily"

_EVERY = re.compile(r"^every\s+(\d+)\s*(minute|minutes|min|hour|hours|h|day|days|d)$")
_AT = re.compile(r"^(\d{1,2}):(\d{2})(?:\s+(\S+))?$")

_UNIT_MINUTES = {
    "minute": 1,
    "minutes": 1,
    "min": 1,
    "hour": 60,
    "hours": 60,
    "h": 60,
    "day": 1440,
    "days": 1440,
    "d": 1440,
}

#: Below this, a control is running often enough that its own cost becomes the
#: dominant load on the source. Refused rather than clamped: silently running
#: something five times less often than it says is worse than saying no.
MINIMUM_MINUTES = 5


def parse(
    text: str, *, calendars: CalendarRegistry | None = None, offset_minutes: int = 0
) -> Trigger:
    """One schedule string as a trigger.

    ``offset_minutes`` staggers triggers so that two datasets on an
    hourly cadence do not both fire at the top of the hour and collide on the
    same source. It belongs to the schedule rather than to a worker, which is
    why it is a parameter here.
    """
    raw = (text or DEFAULT).strip().lower()
    registry = calendars or default_calendars()

    if raw in ("manual", "never", "on demand"):
        return ManualTrigger()
    if raw in ("on arrival", "arrival", "on-arrival"):
        return ArrivalTrigger()
    if raw in ("daily", "every day"):
        return IntervalTrigger(minutes=1440, offset_minutes=offset_minutes)
    if raw in ("hourly", "every hour"):
        return IntervalTrigger(minutes=60, offset_minutes=offset_minutes)

    every = _EVERY.match(raw)
    if every:
        minutes = int(every.group(1)) * _UNIT_MINUTES[every.group(2)]
        if minutes < MINIMUM_MINUTES:
            raise ValidationError(
                f"a cadence of {minutes} minute(s) is below the {MINIMUM_MINUTES}-minute floor",
                remedy=(
                    "Run it less often, or use an arrival trigger so it runs when the "
                    "data changes rather than on a timer. Below this the control's own "
                    "cost is the dominant load on the source."
                ),
                context={"schedule": text},
            )
        return IntervalTrigger(minutes=minutes, offset_minutes=offset_minutes)

    at = _AT.match(raw)
    if at:
        hour, minute = int(at.group(1)), int(at.group(2))
        if hour > 23 or minute > 59:
            raise ValidationError(
                f"{at.group(1)}:{at.group(2)} is not a time of day",
                remedy="Use a 24-hour time, for example 06:30.",
                context={"schedule": text},
            )
        # An unknown calendar is refused by the registry rather than treated as
        # weekdays: a control declared against a calendar nobody loaded would
        # look right and fire on the wrong days.
        return CalendarTrigger(
            at=time(hour, minute),
            calendar=registry.get(at.group(3)),
            offset_minutes=offset_minutes,
        )

    raise ValidationError(
        f"{text!r} is not a schedule Prama understands",
        remedy=(
            "Use one of: 'every 15 minutes', 'every 4 hours', 'daily', '06:30', "
            "'06:30 TARGET2', 'on arrival', 'manual'. Cron is deliberately not "
            "accepted — it cannot express a business calendar, and a schedule that "
            "is wrong on a holiday is a morning of false alarms."
        ),
        context={"schedule": text},
    )


def describe(text: str, *, calendars: CalendarRegistry | None = None) -> str:
    """The schedule as a sentence, or the reason it is not one.

    Never raises. This is what a list of controls prints beside each row, and
    one unparseable schedule must not take the page down — it has to be
    *visible* as broken instead.
    """
    try:
        return parse(text, calendars=calendars).describe()
    except ValidationError as exc:
        return f"unreadable schedule: {exc}"
