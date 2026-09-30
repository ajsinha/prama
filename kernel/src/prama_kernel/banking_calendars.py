"""Financial calendars, as rules.

``CalendarRegistry`` shipped with two calendars — always-open and weekdays — and
an error message telling you to "install the domain pack that provides it".
This is that pack.

Four to begin with, chosen because they are the ones a settlement control
actually names: **TARGET2** for the euro, **Federal Reserve** for the dollar,
**London** for sterling, and **NYSE** because a trading calendar is not a
banking calendar and conflating them is a real defect — the US bond market
closes for Good Friday and the Federal Reserve does not.

Each is a set of rules plus a year range, materialised into the frozen
``BusinessCalendar`` the core expects. The range is stated rather than infinite
because a calendar has to be able to say when it stops knowing: a control
scheduled beyond the horizon must fail loudly rather than quietly treat an
unknown year as all-weekdays.

**Not authoritative.** These are the published rules, and published rules are
not the same as a market's own calendar file: an ad-hoc closure is not a rule.
``with_closures`` takes the extra dates, and every calendar reports how many it
carries so "nobody told us about any" reads differently from "there were none".

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable
from datetime import date

from prama_kernel.calendars import BusinessCalendar, CalendarRegistry
from prama_kernel.holidays import Observance as Obs
from prama_kernel.holidays import Rule, observed

#: How far the shipped calendars are materialised. Wide enough for a control
#: written today to cover a decade of backtests and a decade of scheduling, and
#: narrow enough that the set stays small.
FIRST_YEAR = 2015
LAST_YEAR = 2040

MON, THU = 0, 3


def _fixed(name: str, month: int, day: int, observance: Obs = Obs.NONE, **kw: object) -> Rule:
    return Rule(name=name, kind="fixed", month=month, day=day, observance=observance, **kw)  # type: ignore[arg-type]


def _easter(name: str, offset: int) -> Rule:
    return Rule(name=name, kind="easter", offset=offset)


def _nth(name: str, month: int, nth: int, weekday: int = MON, **kw: object) -> Rule:
    return Rule(name=name, kind="nth_weekday", month=month, nth=nth, weekday=weekday, **kw)  # type: ignore[arg-type]


def _last(name: str, month: int, weekday: int = MON) -> Rule:
    return Rule(name=name, kind="last_weekday", month=month, weekday=weekday)


#: TARGET2 — the euro RTGS system. Exactly six closures, and deliberately no
#: national holidays: TARGET2 stays open on Bastille Day and on German Unity
#: Day, which is precisely the trap a "European calendar" assembled from
#: national ones falls into.
TARGET2_RULES: tuple[Rule, ...] = (
    _fixed("New Year's Day", 1, 1),
    _easter("Good Friday", -2),
    _easter("Easter Monday", 1),
    _fixed("Labour Day", 5, 1),
    _fixed("Christmas Day", 12, 25),
    _fixed("Christmas Holiday", 12, 26),
)

#: US Federal Reserve. Saturday holidays are *not* observed — the Fed is shut on
#: Saturday anyway and does not grant the Friday — while Sunday rolls to Monday.
#: That asymmetry is why NEAREST_WEEKDAY is wrong here, and for four releases
#: this comment said so while every rule below carried NEAREST_WEEKDAY anyway
#: (finding C9). The calendar closed 2021-12-24, 2023-11-10 and 2026-07-03 —
#: Fridays on which Fedwire was open.
FEDERAL_RESERVE_RULES: tuple[Rule, ...] = (
    _fixed("New Year's Day", 1, 1, Obs.SUNDAY_TO_MONDAY),
    _nth("Martin Luther King Jr. Day", 1, 3),
    _nth("Washington's Birthday", 2, 3),
    _last("Memorial Day", 5),
    _fixed("Juneteenth", 6, 19, Obs.SUNDAY_TO_MONDAY, since=2021),
    _fixed("Independence Day", 7, 4, Obs.SUNDAY_TO_MONDAY),
    _nth("Labor Day", 9, 1),
    _nth("Columbus Day", 10, 2),
    _fixed("Veterans Day", 11, 11, Obs.SUNDAY_TO_MONDAY),
    _nth("Thanksgiving", 11, 4, THU),
    _fixed("Christmas Day", 12, 25, Obs.SUNDAY_TO_MONDAY),
)

#: England and Wales bank holidays. ROLL_FORWARD throughout, which is what
#: produces two days off when Christmas falls at a weekend — and the reason
#: ``observed`` resolves substitutes against the accumulating set rather than
#: rule by rule.
LONDON_RULES: tuple[Rule, ...] = (
    _fixed("New Year's Day", 1, 1, Obs.ROLL_FORWARD),
    _easter("Good Friday", -2),
    _easter("Easter Monday", 1),
    _nth("Early May Bank Holiday", 5, 1),
    _last("Spring Bank Holiday", 5),
    _last("Summer Bank Holiday", 8),
    _fixed("Christmas Day", 12, 25, Obs.ROLL_FORWARD),
    _fixed("Boxing Day", 12, 26, Obs.ROLL_FORWARD),
)

#: NYSE. A *trading* calendar, not a banking one, and the difference is the
#: point: the exchange closes for Good Friday while the Federal Reserve does
#: not, and Columbus Day and Veterans Day are the other way round. A settlement
#: control that used one where it meant the other is wrong four days a year.
NYSE_RULES: tuple[Rule, ...] = (
    _fixed("New Year's Day", 1, 1, Obs.NEAREST_WEEKDAY),
    _nth("Martin Luther King Jr. Day", 1, 3),
    _nth("Washington's Birthday", 2, 3),
    _easter("Good Friday", -2),
    _last("Memorial Day", 5),
    _fixed("Juneteenth", 6, 19, Obs.NEAREST_WEEKDAY, since=2022),
    _fixed("Independence Day", 7, 4, Obs.NEAREST_WEEKDAY),
    _nth("Labor Day", 9, 1),
    _nth("Thanksgiving", 11, 4, THU),
    _fixed("Christmas Day", 12, 25, Obs.NEAREST_WEEKDAY),
)


@dataclasses.dataclass(frozen=True, slots=True)
class CalendarSpec:
    """A calendar before it is materialised for a range of years."""

    name: str
    timezone: str
    rules: tuple[Rule, ...]
    description: str = ""
    #: Closures nobody could have derived: a state funeral, an exchange shut
    #: for weather. Supplied, never inferred.
    closures: frozenset[date] = frozenset()

    def with_closures(self, extra: Iterable[date]) -> CalendarSpec:
        return dataclasses.replace(self, closures=self.closures | frozenset(extra))

    def materialise(
        self, first_year: int = FIRST_YEAR, last_year: int = LAST_YEAR
    ) -> BusinessCalendar:
        return BusinessCalendar(
            name=self.name,
            timezone=self.timezone,
            holidays=observed(self.rules, range(first_year, last_year + 1)) | self.closures,
        )

    def describe(self) -> str:
        """What this calendar knows, and what it cannot.

        The second half is the part worth printing. A calendar that lists its
        rules and says nothing about ad-hoc closures invites a reader to assume
        it has them.
        """
        carried = (
            f"{len(self.closures)} ad-hoc closure(s) supplied"
            if self.closures
            else "no ad-hoc closures supplied — none have been provided, which is "
            "not the same as there having been none"
        )
        return f"{self.name}: {len(self.rules)} rule(s), {FIRST_YEAR} to {LAST_YEAR}; {carried}"


SPECS: tuple[CalendarSpec, ...] = (
    CalendarSpec(
        name="TARGET2",
        timezone="Europe/Brussels",
        rules=TARGET2_RULES,
        description="Euro RTGS. Six closures; no national holidays.",
    ),
    CalendarSpec(
        name="FederalReserve",
        timezone="America/New_York",
        rules=FEDERAL_RESERVE_RULES,
        description="US banking. Open on Good Friday, unlike the exchanges.",
    ),
    CalendarSpec(
        name="London",
        timezone="Europe/London",
        rules=LONDON_RULES,
        description="England and Wales bank holidays, with rolled substitutes.",
    ),
    CalendarSpec(
        name="NYSE",
        timezone="America/New_York",
        rules=NYSE_RULES,
        description="US equities trading. Closed Good Friday; open Columbus Day.",
    ),
)


def install(
    registry: CalendarRegistry | None = None,
    *,
    first_year: int = FIRST_YEAR,
    last_year: int = LAST_YEAR,
    replace: bool = False,
) -> CalendarRegistry:
    """Materialise every shipped calendar into a registry.

    Explicit rather than on import. A calendar appearing because a module was
    imported somewhere is a calendar whose presence depends on import order,
    and the first symptom is a control that resolves in one process and refuses
    in another.
    """
    target = registry or CalendarRegistry()
    for spec in SPECS:
        target.register(spec.materialise(first_year, last_year), replace=replace)
    return target


def spec(name: str) -> CalendarSpec:
    for candidate in SPECS:
        if candidate.name.lower() == name.lower():
            return candidate
    raise KeyError(name)


__all__ = [
    "FEDERAL_RESERVE_RULES",
    "FIRST_YEAR",
    "LAST_YEAR",
    "LONDON_RULES",
    "NYSE_RULES",
    "SPECS",
    "TARGET2_RULES",
    "CalendarSpec",
    "install",
    "spec",
]
