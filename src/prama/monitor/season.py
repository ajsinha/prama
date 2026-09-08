"""Which past observations are comparable with today's.

`FR-MON-002`. A row count is not one distribution. Monday is not Sunday,
month-end is not the fourteenth, and a settlement date that falls after a bank
holiday carries two days of activity. A monitor that pools them and computes a
band gets a band wide enough to accommodate month-end, which means it is blind
on every ordinary day — the failure that makes volume monitoring a byword for
noise.

**Seasonality and conformal validity turn out to be the same mechanism.**
Conformal p-values need exchangeability, and a row count over a year is
emphatically not exchangeable. Grouped by *comparable day*, it is: month-end
Fridays are exchangeable with other month-end Fridays. So this module does not
model a seasonal effect and subtract it — it answers "which past observations
is today comparable with?", and hands that group to the calibrator. The
seasonal structure becomes a conditioning set rather than a fitted curve, and
the guarantee survives.

**The cost is the same one everything else in this wave pays.** Condition
finely enough and the group is empty: day-of-week by month-end by hour leaves one
observation a year. So a grouping that is too thin falls back to a coarser one,
and **says which it used** — because "compared against 240 ordinary weekdays"
and "compared against 11 month-ends" support very different claims, and a
monitor that silently switches between them is a monitor whose alerts mean
different things on different days without saying so.

**A declared driver beats a year of history.** A business owner saying "three
times normal at month-end" is prior knowledge available on day one, and
`FR-MON-002` asks for it to be used rather than rediscovered. A declared driver
adds a dimension to the grouping immediately; a discovered one has to earn its
place by being visible in the data.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

from prama.core.calendars import ALWAYS_OPEN, BusinessCalendar

#: How a facet blurs before it is dropped. Only period-end has a middle
#: setting, and it is the one that needs it: month, quarter and year ends
#: resemble each other far more than any of them resembles an ordinary day.
_COARSER: dict[tuple[str, str], str] = {
    ("period_end", "year"): "any",
    ("period_end", "quarter"): "any",
    ("period_end", "month"): "any",
}

#: Values a coarsened facet accepts.
_COARSE_MATCHES: dict[tuple[str, str], frozenset[str]] = {
    ("period_end", "any"): frozenset({"month", "quarter", "year"}),
}

#: A group thinner than this cannot calibrate anything: the finest p-value it
#: could express would be coarser than any budget worth setting.
MINIMUM_GROUP = 20

#: A group at or above this supports a p-value fine enough for most budgets.
#: Reported rather than pursued: a group of 24 month-ends distinguishes
#: month-end from an ordinary day *and* can express a p-value of 0.04, which is
#: a better monitor than 500 mixed days that can express 0.002 about nothing in
#: particular. Relaxing to reach this number is how a seasonal monitor becomes
#: a pooled one.
COMFORTABLE_GROUP = 40


class Facet(enum.Enum):
    """One way two days can be alike, in order of how much it usually matters."""

    #: Whether the calendar says it is a business day at all.
    BUSINESS_DAY = "business_day"
    #: Month-end, quarter-end, year-end. The largest single effect in most
    #: financial data, and the one a pooled band is always accommodating.
    PERIOD_END = "period_end"
    #: Monday through Sunday. Second largest, and the one people expect.
    DAY_OF_WEEK = "day_of_week"
    #: Hour, for intraday series.
    HOUR = "hour"
    #: A named driver the business declared: "month_end", "payroll",
    #: "index_rebalance". Prior knowledge, used rather than rediscovered.
    DECLARED = "declared"

    @property
    def rank(self) -> int:
        return list(Facet).index(self)


@dataclasses.dataclass(frozen=True, slots=True)
class SeasonKey:
    """What makes an observation comparable with another."""

    facets: tuple[tuple[str, str], ...] = ()

    def render(self) -> str:
        if not self.facets:
            return "every observation"
        return ", ".join(f"{name}={value}" for name, value in self.facets)

    def without(self, facet: Facet) -> SeasonKey:
        return SeasonKey(facets=tuple(f for f in self.facets if f[0] != facet.value))

    def coarsened(self, facet: Facet) -> SeasonKey | None:
        """The same key with one facet blurred rather than removed.

        The step that stops a year-end being compared against ordinary
        Wednesdays. Two years of history contain two year-ends, so the specific
        group is unusable — and dropping the facet outright lands on "any
        business day", which is the pooled band this module exists to avoid. In
        between sits "any period end": twenty-odd members, and it keeps the
        distinction that actually matters.

        Returns None when there is nothing coarser than the current value.
        """
        current = dict(self.facets).get(facet.value)
        if current is None:
            return None
        blurred = _COARSER.get((facet.value, current))
        if blurred is None:
            return None
        return SeasonKey(
            facets=tuple(
                (name, blurred if name == facet.value else value) for name, value in self.facets
            )
        )

    def to_dict(self) -> dict[str, str]:
        return dict(self.facets)


@dataclasses.dataclass(frozen=True, slots=True)
class Grouping:
    """The comparison group chosen, and what had to be given up for it."""

    key: SeasonKey
    #: Indices into the history, oldest first.
    members: tuple[int, ...]
    #: Facets dropped to reach a usable group size, most specific first.
    relaxed: tuple[Facet, ...] = ()

    @property
    def size(self) -> int:
        return len(self.members)

    @property
    def is_specific(self) -> bool:
        return not self.relaxed

    @property
    def resolution(self) -> float:
        """The finest p-value this comparison group can express.

        Carried on the grouping because it is a property of the *seasonal
        choice*, not of the calibrator: comparing a year-end against 24
        period-ends means no budget below 0.04 can be honoured that day, and
        that is a consequence of the calendar rather than of the history's
        length.
        """
        return 1.0 / (self.size + 1) if self.size else 1.0

    def describe(self) -> str:
        head = f"compared against {self.size} observations where {self.key.render()}"
        if self.size < COMFORTABLE_GROUP:
            head += f", which is enough for a p-value no finer than {self.resolution:.3f}"
        if not self.relaxed:
            return head
        dropped = ", ".join(f.value for f in self.relaxed)
        return (
            f"{head}. {dropped} had to be ignored to find enough comparable days — "
            f"this monitor is less specific today than it would be with more history"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key.to_dict(),
            "size": self.size,
            "relaxed": [f.value for f in self.relaxed],
            "specific": self.is_specific,
            "resolution": round(self.resolution, 6),
            "description": self.describe(),
        }


class SeasonalModel:
    """Decides which past observations today should be judged against."""

    def __init__(
        self,
        *,
        calendar: BusinessCalendar = ALWAYS_OPEN,
        intraday: bool = False,
        #: Named drivers the business declared, with the days they apply to.
        #: A callable rather than a set, because "the third Friday" and "two
        #: business days before month-end" are rules, not enumerations.
        drivers: dict[str, Any] | None = None,
        minimum: int = MINIMUM_GROUP,
        comfortable: int = COMFORTABLE_GROUP,
    ) -> None:
        self._calendar = calendar
        self._intraday = intraday
        self._drivers = drivers or {}
        self._minimum = minimum
        self._comfortable = comfortable

    def key(self, moment: datetime) -> SeasonKey:
        """Everything that makes this moment the kind of moment it is."""
        day = moment.date()
        facets: list[tuple[str, str]] = [
            (Facet.BUSINESS_DAY.value, str(self._calendar.is_business_day(day))),
            (Facet.PERIOD_END.value, self.period_end(day)),
            (Facet.DAY_OF_WEEK.value, str(day.weekday())),
        ]
        if self._intraday:
            facets.append((Facet.HOUR.value, str(moment.hour)))
        for name, rule in sorted(self._drivers.items()):
            facets.append((f"{Facet.DECLARED.value}:{name}", str(bool(rule(day)))))
        return SeasonKey(facets=tuple(facets))

    def period_end(self, day: date) -> str:
        """The strongest seasonal signal in financial data, named.

        Reported as the *last business day* of the period rather than the
        calendar last day, because that is when the work happens: a month
        ending on a Sunday has its month-end volume on the Friday, and a
        monitor keyed on the calendar date compares that Friday against
        ordinary Fridays and alerts every quarter.
        """
        if not self._calendar.is_business_day(day):
            return "none"
        following = self._calendar.next_business_day(day)
        if following.year != day.year:
            return "year"
        if (following.month - 1) // 3 != (day.month - 1) // 3:
            return "quarter"
        if following.month != day.month:
            return "month"
        return "none"

    def group(self, history: Sequence[datetime], moment: datetime) -> Grouping:
        """The comparable observations, relaxing specificity until there are enough.

        Facets are dropped from the *least* important upward — hour, then
        day-of-week, then period-end — so what survives longest is the
        distinction that matters most. Dropping period-end first would be
        easier and would produce exactly the pooled band this module exists to
        avoid.
        """
        target = self.key(moment)
        keys = [self.key(when) for when in history]
        order = self._relaxation_order(target)

        relaxed: list[Facet] = []
        current = target

        # Stop at the first grouping with enough members, most specific first.
        #
        # An earlier version kept going until it found a *comfortable* group,
        # and that was wrong in the way this module exists to prevent: a
        # year-end has one comparable year-end in two years of history and
        # twenty-four comparable period-ends, and continuing past the
        # twenty-four landed on five hundred ordinary business days. The
        # monitor then compares a year-end against ordinary Wednesdays and
        # alerts every December.
        #
        # Specificity is worth more than sample size down to the point where
        # the sample stops meaning anything, and that point is `minimum`. Below
        # it there is no p-value at all; above it there is a coarser p-value,
        # and the coarseness is reported rather than traded away silently.
        for step in self._steps(order):
            if step is not None:
                current, dropped = self._relax_one(current, step)
                if dropped and step not in relaxed:
                    relaxed.append(step)
            members = tuple(index for index, key in enumerate(keys) if self._matches(key, current))
            if len(members) >= self._minimum:
                return Grouping(key=current, members=members, relaxed=tuple(relaxed))

        # Nothing was specific enough to be usable: compare against everything
        # and say so, rather than returning an empty group and no p-value.
        return Grouping(
            key=SeasonKey(),
            members=tuple(range(len(history))),
            relaxed=tuple(order),
        )

    @staticmethod
    def _steps(order: Sequence[Facet]) -> list[Facet | None]:
        """The specific key, then each facet blurred, then each one dropped.

        Each facet appears twice: the first visit blurs it if it has a coarser
        setting, the second removes it. That ordering is what stops a year-end
        landing on "any business day" — it stops at "any period end" on the
        way, which has twenty-odd members and preserves the distinction that
        matters.
        """
        steps: list[Facet | None] = [None]
        for facet in order:
            steps.extend([facet, facet])
        return steps

    @staticmethod
    def _relax_one(current: SeasonKey, facet: Facet) -> tuple[SeasonKey, bool]:
        """Blur the facet if it can be blurred, otherwise drop it.

        Returns the new key and whether the facet was dropped outright, since
        only a drop is worth reporting as lost specificity — a blurred facet is
        still doing work.
        """
        blurred = current.coarsened(facet)
        if blurred is not None:
            return blurred, False
        return current.without(facet), True

    def _relaxation_order(self, key: SeasonKey) -> tuple[Facet, ...]:
        """Least important first, so the meaningful distinction survives."""
        present = {name.split(":", 1)[0] for name, _ in key.facets}
        order = [Facet.HOUR, Facet.DAY_OF_WEEK, Facet.PERIOD_END, Facet.BUSINESS_DAY]
        # A declared driver is dropped last of all: the business said it
        # matters, and discarding a declaration to make a sample bigger is
        # exactly the trade this system exists not to make silently.
        return tuple(f for f in order if f.value in present)

    @staticmethod
    def _matches(candidate: SeasonKey, target: SeasonKey) -> bool:
        have = dict(candidate.facets)
        for name, value in target.facets:
            accepted = _COARSE_MATCHES.get((name, value))
            if accepted is not None:
                if have.get(name) not in accepted:
                    return False
            elif have.get(name) != value:
                return False
        return True


# ---------------------------------------------------------------------------
# Declared drivers
# ---------------------------------------------------------------------------


def month_end_driver(calendar: BusinessCalendar = ALWAYS_OPEN) -> Any:
    """ "Volume is three times normal at month-end", as a rule.

    Returned as a predicate rather than a multiplier on purpose. A multiplier
    would have to be right, and the business's "about three times" is a
    recollection; a predicate only has to identify the days, and the history
    then says how much they differ by. The declaration contributes the thing a
    person actually knows and the data contributes the number.
    """
    model = SeasonalModel(calendar=calendar)

    def applies(day: date) -> bool:
        return model.period_end(day) in ("month", "quarter", "year")

    return applies


def weekday_driver(weekday: int) -> Any:
    def applies(day: date) -> bool:
        return day.weekday() == weekday

    return applies


def nth_weekday_driver(weekday: int, occurrence: int) -> Any:
    """ "The third Friday" — index rebalances, futures expiry, payroll."""

    def applies(day: date) -> bool:
        return day.weekday() == weekday and (day.day - 1) // 7 == occurrence - 1

    return applies


def day_of_month_driver(day_of_month: int) -> Any:
    def applies(day: date) -> bool:
        return day.day == day_of_month

    return applies
