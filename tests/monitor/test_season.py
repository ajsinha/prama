"""Which past observations today is comparable with.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from prama.core.calendars import BusinessCalendar
from prama.monitor.season import (
    COMFORTABLE_GROUP,
    Facet,
    SeasonalModel,
    month_end_driver,
    nth_weekday_driver,
)

WEEKDAYS = BusinessCalendar(name="wd", weekend_days=frozenset({5, 6}))


def two_years() -> list[datetime]:
    start = datetime(2024, 1, 1)
    return [start + timedelta(days=index) for index in range(730)]


def model(**options: object) -> SeasonalModel:
    return SeasonalModel(calendar=WEEKDAYS, **options)  # type: ignore[arg-type]


# -- what makes a day the kind of day it is ---------------------------------


def test_period_end_is_the_last_business_day_not_the_calendar_last() -> None:
    """A month ending on a Sunday has its month-end volume on the Friday. A
    monitor keyed on the calendar date compares that Friday against ordinary
    Fridays and alerts every quarter."""
    seasonal = model()
    # 30 June 2024 is a Sunday; the month-end work lands on Friday the 28th.
    assert seasonal.period_end(datetime(2024, 6, 28).date()) == "quarter"
    assert seasonal.period_end(datetime(2024, 6, 30).date()) == "none"


def test_year_end_outranks_quarter_end_outranks_month_end() -> None:
    seasonal = model()
    assert seasonal.period_end(datetime(2024, 12, 31).date()) == "year"
    assert seasonal.period_end(datetime(2024, 9, 30).date()) == "quarter"
    assert seasonal.period_end(datetime(2024, 7, 31).date()) == "month"


def test_an_ordinary_day_is_compared_against_ordinary_days_of_the_same_weekday() -> None:
    grouping = model().group(two_years(), datetime(2025, 12, 17))
    assert grouping.is_specific
    assert grouping.size > 90
    assert grouping.key.to_dict()["day_of_week"] == "2"
    assert grouping.key.to_dict()["period_end"] == "none"


def test_a_weekend_is_never_compared_against_a_business_day() -> None:
    grouping = model().group(two_years(), datetime(2025, 12, 21))
    assert grouping.key.to_dict()["business_day"] == "False"


# -- the relaxation, and what it must not do ---------------------------------


def test_a_year_end_is_compared_against_period_ends_not_ordinary_days() -> None:
    """Two years of history hold two year-ends, so the specific group is
    unusable — and dropping the facet outright lands on "any business day",
    which is the pooled band this module exists to avoid. In between sits "any
    period end", which keeps the distinction that matters."""
    grouping = model().group(two_years(), datetime(2025, 12, 31))
    assert grouping.key.to_dict()["period_end"] == "any"
    assert 20 <= grouping.size <= 40
    assert Facet.PERIOD_END not in grouping.relaxed


def test_specificity_is_never_traded_for_a_bigger_sample() -> None:
    """An earlier version relaxed until it found a *comfortable* group, which
    walked straight past twenty-four comparable period-ends and landed on five
    hundred ordinary business days."""
    grouping = model().group(two_years(), datetime(2025, 12, 31))
    assert grouping.size < 100
    assert "period_end=any" in grouping.key.render()


def test_the_least_important_facet_is_given_up_first() -> None:
    """Dropping period-end first would be easier and would produce exactly the
    pooled band."""
    grouping = model().group(two_years(), datetime(2025, 12, 31))
    assert Facet.DAY_OF_WEEK in grouping.relaxed


def test_a_thin_group_reports_the_p_value_it_can_support() -> None:
    """Comparing a year-end against 23 period-ends means no budget below 0.04
    can be honoured that day, and that is a consequence of the calendar rather
    than of the history's length."""
    grouping = model().group(two_years(), datetime(2025, 12, 31))
    assert grouping.size < COMFORTABLE_GROUP
    assert grouping.resolution > 0.02
    assert "no finer than" in grouping.describe()


def test_a_comfortable_group_does_not_apologise() -> None:
    grouping = model().group(two_years(), datetime(2025, 12, 17))
    assert "no finer than" not in grouping.describe()


# -- declared drivers --------------------------------------------------------


def test_a_declared_driver_is_used_rather_than_rediscovered() -> None:
    """ "Three times normal at month-end" is prior knowledge available on day
    one, and worth more than a year of history."""
    declared = model(drivers={"month_end": month_end_driver(WEEKDAYS)})
    grouping = declared.group(two_years(), datetime(2025, 12, 31))
    assert grouping.key.to_dict()["declared:month_end"] == "True"


def test_a_declared_driver_survives_relaxation_longest() -> None:
    """The business said it matters, and discarding a declaration to make a
    sample bigger is exactly the trade this system exists not to make
    silently."""
    declared = model(drivers={"rebalance": nth_weekday_driver(4, 3)})
    grouping = declared.group(two_years(), datetime(2025, 12, 19))
    assert "declared:rebalance" in grouping.key.to_dict()


def test_a_driver_contributes_the_days_and_the_history_contributes_the_number() -> None:
    """A multiplier would have to be right, and "about three times" is a
    recollection. A predicate only has to identify the days."""
    applies = month_end_driver(WEEKDAYS)
    assert applies(datetime(2024, 6, 28).date())
    assert not applies(datetime(2024, 6, 27).date())


def test_nth_weekday_finds_the_third_friday() -> None:
    """Index rebalances, futures expiry, payroll."""
    third_friday = nth_weekday_driver(4, 3)
    assert third_friday(datetime(2025, 12, 19).date())
    assert not third_friday(datetime(2025, 12, 12).date())


# -- honest limits -----------------------------------------------------------


def test_no_history_at_all_still_returns_a_group_rather_than_nothing() -> None:
    grouping = model().group([], datetime(2025, 12, 17))
    assert grouping.size == 0
    assert grouping.relaxed


def test_a_short_history_falls_back_and_says_it_did() -> None:
    short = [datetime(2025, 12, 1) + timedelta(days=index) for index in range(25)]
    grouping = model().group(short, datetime(2025, 12, 31))
    assert grouping.relaxed
    assert "less specific" in grouping.describe()
