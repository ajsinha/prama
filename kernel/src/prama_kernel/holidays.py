"""Holiday rules, computed rather than listed.

A calendar shipped as a list of dates is a calendar that expires. It covers the
years somebody typed, and the year after that every settlement control silently
starts treating a holiday as a business day — which is the failure mode that
looks like clean data: the file did not arrive because the market was shut, and
a timeliness control reports it missing.

So the pack ships *rules*. ``Easter`` is computed, "the third Monday in January"
is computed, and a calendar can be materialised for any year range on demand.
The cost is that the rules have to be right; the benefit is that they cannot go
stale, and a rule is something a person can read and disagree with.

**What this cannot know.** Ad-hoc closures — a state funeral, a coronation, an
exchange closing for weather — are not rules and are not here. They are supplied
as explicit extra dates by whoever knows about them, and a calendar says how
many of those it carries so that "we have not been told about any" is
distinguishable from "there were none".

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
from collections.abc import Iterable
from datetime import date, timedelta

from prama_kernel.errors import ValidationError

MONDAY, SATURDAY, SUNDAY = 0, 5, 6


def easter_sunday(year: int) -> date:
    """Western (Gregorian) Easter, by the anonymous Gregorian algorithm.

    Worth computing rather than tabulating: four of the six TARGET2 holidays
    hang off this date, and a table of Easters is the single most likely thing
    in a calendar pack to run out.
    """
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    lam = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * lam) // 451
    month, day = divmod(h + lam - 7 * m + 114, 31)
    return date(year, month, day + 1)


class Observance(enum.Enum):
    """What happens when a fixed-date holiday falls at a weekend.

    Not a detail. A market that moves Christmas to the following Monday and one
    that simply loses it have different business days that week, and a control
    scheduled on the wrong one fires on a day the market is shut.
    """

    #: The holiday is simply lost. Most European fixed dates work this way.
    NONE = "none"
    #: Saturday → Friday before, Sunday → Monday after. US federal *employee*
    #: practice, and the rule the NYSE follows.
    NEAREST_WEEKDAY = "nearest_weekday"
    #: Sunday → Monday after; a Saturday holiday is simply lost. What the
    #: Federal Reserve Banks actually do, and not the same thing as
    #: :attr:`NEAREST_WEEKDAY` — see finding C9. The Fed's published schedule
    #: says "for holidays falling on Saturday, Federal Reserve Bank offices …
    #: will be open the preceding Friday", because the Fed is shut on Saturday
    #: anyway and does not hand back a business day for it. Fedwire is open
    #: that Friday, so a settlement or timeliness control on the Fed calendar
    #: that skips it misses a real business day once or twice a year.
    SUNDAY_TO_MONDAY = "sunday_to_monday"
    #: Both weekend days roll forward, so Christmas on Saturday gives Monday
    #: *and* Tuesday off. UK bank-holiday practice.
    ROLL_FORWARD = "roll_forward"


@dataclasses.dataclass(frozen=True, slots=True)
class Rule:
    """One holiday, as something that can be evaluated for any year."""

    name: str
    #: ``fixed`` · ``easter`` · ``nth_weekday`` · ``last_weekday``
    kind: str
    month: int = 1
    day: int = 1
    #: Days from Easter Sunday, for ``easter``. Good Friday is -2.
    offset: int = 0
    #: For ``nth_weekday``: 1 is the first, 2 the second, and so on.
    nth: int = 1
    weekday: int = MONDAY
    observance: Observance = Observance.NONE
    #: The first year this rule applies. Juneteenth became a US federal holiday
    #: in 2021, and a calendar that back-dated it would report a business day
    #: as closed for every year before that.
    since: int | None = None
    until: int | None = None

    def applies_in(self, year: int) -> bool:
        if self.since is not None and year < self.since:
            return False
        return not (self.until is not None and year > self.until)

    def dates_in(self, year: int) -> tuple[date, ...]:
        """Every date this rule closes the market in *year*.

        A tuple rather than one date, because ``ROLL_FORWARD`` on consecutive
        holidays produces two substitute days from two rules and the caller has
        to see both.
        """
        if not self.applies_in(year):
            return ()
        base = self._base(year)
        return self._observed(base)

    def _base(self, year: int) -> date:
        if self.kind == "fixed":
            return date(year, self.month, self.day)
        if self.kind == "easter":
            return easter_sunday(year) + timedelta(days=self.offset)
        if self.kind == "nth_weekday":
            first = date(year, self.month, 1)
            ahead = (self.weekday - first.weekday()) % 7
            return first + timedelta(days=ahead + 7 * (self.nth - 1))
        if self.kind == "last_weekday":
            # Step back from the first of the next month, which avoids having
            # to know how long this one is.
            nxt = date(year + 1, 1, 1) if self.month == 12 else date(year, self.month + 1, 1)
            back = (nxt.weekday() - self.weekday - 1) % 7
            return nxt - timedelta(days=back + 1)
        raise ValidationError(
            f"unknown holiday rule kind {self.kind!r}",
            remedy="One of: fixed, easter, nth_weekday, last_weekday.",
            context={"rule": self.name, "kind": self.kind},
        )

    def _observed(self, base: date) -> tuple[date, ...]:
        if self.observance is Observance.NONE or base.weekday() < SATURDAY:
            return (base,)
        if self.observance is Observance.SUNDAY_TO_MONDAY:
            # Saturday is lost, Sunday moves to Monday. The asymmetry is the
            # whole point of having this separately from NEAREST_WEEKDAY.
            return (base,) if base.weekday() == SATURDAY else (base + timedelta(days=1),)
        if self.observance is Observance.NEAREST_WEEKDAY:
            # Saturday back to Friday, Sunday forward to Monday. The holiday
            # moves; it does not multiply.
            shift = -1 if base.weekday() == SATURDAY else 1
            return (base + timedelta(days=shift),)
        # ROLL_FORWARD: Saturday gives the following Monday, Sunday the
        # following Monday too — and a second holiday landing on that Monday
        # pushes its own substitute to the Tuesday, which the caller resolves
        # by taking the union of every rule's dates.
        ahead = 2 if base.weekday() == SATURDAY else 1
        return (base + timedelta(days=ahead),)


def observed(rules: Iterable[Rule], years: Iterable[int]) -> frozenset[date]:
    """Every closure the rules produce across *years*.

    Substitutes are resolved against the set as it is built, so two holidays
    whose substitutes collide give two separate days off rather than one. That
    is the Christmas-and-Boxing-Day case in the UK, and getting it wrong loses a
    business day every few years in a way nobody notices until a month-end
    report is a day late.
    """
    closed: set[date] = set()
    for year in sorted(set(years)):
        for rule in rules:
            for day in rule.dates_in(year):
                candidate = day
                if rule.observance is Observance.ROLL_FORWARD:
                    while candidate in closed or candidate.weekday() >= SATURDAY:
                        candidate += timedelta(days=1)
                closed.add(candidate)
    return frozenset(closed)


__all__ = [
    "MONDAY",
    "SATURDAY",
    "SUNDAY",
    "Observance",
    "Rule",
    "easter_sunday",
    "observed",
]
