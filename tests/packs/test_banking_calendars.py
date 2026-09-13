"""The banking pack's calendars, against published dates.

A calendar is the one thing in this system that can be checked against an
outside authority, so it is checked against one: every date below is a
published closure, not a value this implementation produced.

The Fed-versus-NYSE cases matter most. A trading calendar and a banking calendar
differ on four days a year, and a settlement control that used one where it
meant the other is wrong on all four — silently, because the file simply does
not arrive and a timeliness control reports it missing.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from prama.core.calendars import CalendarRegistry
from prama.core.errors import ValidationError
from prama.packs.banking.calendars import LAST_YEAR, SPECS, install, spec
from prama.packs.banking.holidays import Observance, Rule, easter_sunday, observed


@pytest.fixture(scope="module")
def calendars() -> CalendarRegistry:
    return install()


class TestEaster:
    @pytest.mark.parametrize(
        "year,expected",
        [
            (1900, "1900-04-15"),
            (2000, "2000-04-23"),
            (2024, "2024-03-31"),
            (2025, "2025-04-20"),
            (2026, "2026-04-05"),
            (2027, "2027-03-28"),
            (2038, "2038-04-25"),
        ],
    )
    def test_it_matches_the_published_dates(self, year: int, expected: str) -> None:
        """Computed rather than tabulated: four of the six TARGET2 closures hang
        off Easter, and a table is the thing most likely to run out."""
        assert easter_sunday(year).isoformat() == expected


class TestTarget2:
    @pytest.mark.parametrize(
        "day",
        [
            date(2026, 1, 1),  # New Year
            date(2026, 4, 3),  # Good Friday
            date(2026, 4, 6),  # Easter Monday
            date(2026, 5, 1),  # Labour Day
            date(2026, 12, 25),
            date(2026, 12, 26) if date(2026, 12, 26).weekday() < 5 else date(2025, 12, 26),
        ],
    )
    def test_the_six_closures(self, calendars: CalendarRegistry, day: date) -> None:
        assert not calendars.get("TARGET2").is_business_day(day)

    @pytest.mark.parametrize(
        "day,what",
        [
            (date(2026, 7, 14), "Bastille Day"),
            (date(2026, 10, 3), "German Unity Day"),
            (date(2026, 8, 15), "Assumption"),
            (date(2026, 11, 1), "All Saints"),
        ],
    )
    def test_national_holidays_do_not_close_it(
        self, calendars: CalendarRegistry, day: date, what: str
    ) -> None:
        """The trap a "European calendar" assembled from national ones falls
        into. TARGET2 settles on Bastille Day."""
        target2 = calendars.get("TARGET2")
        assert target2.is_business_day(day) == (day.weekday() < 5), what

    def test_it_has_exactly_six_rules(self) -> None:
        """Stated as a number because the failure mode is accretion: somebody
        adds their own market's holiday and every euro settlement control moves
        by a day."""
        assert len(spec("TARGET2").rules) == 6


class TestTheFederalReserveIsNotTheExchange:
    def test_good_friday_closes_the_exchange_and_not_the_bank(
        self, calendars: CalendarRegistry
    ) -> None:
        """The single most confused pair in the set."""
        friday = date(2026, 4, 3)
        assert calendars.get("FederalReserve").is_business_day(friday)
        assert not calendars.get("NYSE").is_business_day(friday)

    def test_columbus_day_closes_the_bank_and_not_the_exchange(
        self, calendars: CalendarRegistry
    ) -> None:
        columbus = date(2026, 10, 12)
        assert not calendars.get("FederalReserve").is_business_day(columbus)
        assert calendars.get("NYSE").is_business_day(columbus)

    def test_veterans_day_closes_the_bank_and_not_the_exchange(
        self, calendars: CalendarRegistry
    ) -> None:
        veterans = date(2026, 11, 11)
        assert not calendars.get("FederalReserve").is_business_day(veterans)
        assert calendars.get("NYSE").is_business_day(veterans)


class TestUsObservance:
    """Finding C9. The Fed and the NYSE do *not* observe weekends the same way,
    and the calendar applied the exchange's rule to both.

    The Federal Reserve's published schedule: "For holidays falling on Saturday,
    Federal Reserve Bank offices ... will be open the preceding Friday." The Fed
    is shut on Saturday anyway and does not hand back a business day for it.
    Sunday still rolls to Monday, and that asymmetry is the whole rule.

    The source comment above `FEDERAL_RESERVE_RULES` said exactly this, and
    every rule beneath it carried `NEAREST_WEEKDAY` regardless — while the test
    here asserted the behaviour the comment called wrong. Two files, two
    opposite claims, and a passing suite. The external authority sides with the
    comment.

    NYSE's use of `NEAREST_WEEKDAY` is correct and stays: the exchange does
    close the preceding Friday.
    """

    @pytest.mark.parametrize(
        "holiday,observed_on",
        [
            # 2021-07-04 was a Sunday: observed Monday the 5th.
            (date(2021, 7, 4), date(2021, 7, 5)),
            # 2022-12-25 was a Sunday: observed Monday the 26th.
            (date(2022, 12, 25), date(2022, 12, 26)),
            # 2021-12-25 was a Saturday. Christmas itself is still a closure;
            # what does not happen is the Friday before.
            (date(2021, 12, 25), date(2021, 12, 25)),
        ],
    )
    def test_a_sunday_holiday_moves_to_the_monday(
        self, calendars: CalendarRegistry, holiday: date, observed_on: date
    ) -> None:
        """The holiday moves; it does not multiply.

        `holiday` used to be accepted and never referenced (finding T13), which
        left the second half of that sentence asserted nowhere — the test would
        have passed just as well had the calendar closed the whole week.
        """
        fed = calendars.get("FederalReserve")
        assert not fed.is_business_day(observed_on)
        # Exactly one weekday lost. The Friday before the holiday is a business
        # day: that is the Fed rule, and it is the assertion `holiday` exists
        # to make.
        friday = holiday - timedelta(days=holiday.weekday() - 4 if holiday.weekday() >= 4 else 3)
        while friday.weekday() != 4:
            friday -= timedelta(days=1)
        assert fed.is_business_day(friday), f"the Friday before {holiday} should be open"

    @pytest.mark.parametrize(
        "open_friday,because",
        [
            (date(2021, 12, 24), "Christmas Day 2021 fell on the Saturday"),
            (date(2023, 11, 10), "Veterans Day 2023 fell on the Saturday"),
            (date(2026, 7, 3), "Independence Day 2026 falls on the Saturday"),
            (date(2020, 7, 3), "Independence Day 2020 fell on the Saturday"),
            (date(2021, 6, 18), "Juneteenth 2021 fell on the Saturday"),
        ],
    )
    def test_the_fed_is_open_the_friday_before_a_saturday_holiday(
        self, calendars: CalendarRegistry, open_friday: date, because: str
    ) -> None:
        """Fedwire settles on these days. A timeliness control that treats one
        as a closure gives the feed an extra day it was never owed, and a
        settlement control skips a real business day — once or twice a year,
        silently."""
        fed = calendars.get("FederalReserve")
        assert fed.is_business_day(open_friday), f"{because}, but the Fed is open"

    @pytest.mark.parametrize(
        "closed_friday,because",
        [
            (date(2020, 7, 3), "Independence Day 2020 fell on the Saturday"),
            (date(2021, 12, 24), "Christmas Day 2021 fell on the Saturday"),
        ],
    )
    def test_the_nyse_does_close_that_friday(
        self, calendars: CalendarRegistry, closed_friday: date, because: str
    ) -> None:
        """The counterfactual, and the reason the two calendars are separate.
        A fix that made every US calendar Sunday-only would be as wrong in the
        other direction, and this is the assertion that would catch it."""
        nyse = calendars.get("NYSE")
        assert not nyse.is_business_day(closed_friday), f"{because}, and the NYSE shuts"

    def test_juneteenth_is_absent_before_it_existed(self, calendars: CalendarRegistry) -> None:
        """It became a federal holiday in 2021. A calendar that back-dated it
        would report a business day as closed for every year before that."""
        fed = calendars.get("FederalReserve")
        assert fed.is_business_day(date(2019, 6, 19))
        assert not fed.is_business_day(date(2022, 6, 20))  # 19th was a Sunday


class TestUkSubstitutes:
    def test_christmas_at_a_weekend_gives_two_substitute_days(
        self, calendars: CalendarRegistry
    ) -> None:
        """2021: Christmas fell on Saturday and Boxing Day on Sunday, and the
        substitutes were Monday the 27th *and* Tuesday the 28th. Resolving each
        rule independently would collapse them into one and lose a business day
        — which nobody notices until a month-end report is a day late.
        """
        london = calendars.get("London")
        assert not london.is_business_day(date(2021, 12, 27))
        assert not london.is_business_day(date(2021, 12, 28))

    def test_new_year_on_a_saturday_moves_to_the_monday(self, calendars: CalendarRegistry) -> None:
        # 2022-01-01 was a Saturday; the substitute was Monday the 3rd.
        assert not calendars.get("London").is_business_day(date(2022, 1, 3))

    def test_the_early_may_bank_holiday_is_the_first_monday(
        self, calendars: CalendarRegistry
    ) -> None:
        assert not calendars.get("London").is_business_day(date(2026, 5, 4))


class TestRulesRatherThanLists:
    def test_a_calendar_reaches_the_stated_horizon(self, calendars: CalendarRegistry) -> None:
        """The reason these are rules. A list covers the years somebody typed,
        and the year after that every settlement control silently treats a
        holiday as a business day."""
        assert not calendars.get("TARGET2").is_business_day(date(LAST_YEAR, 12, 25))
        assert not calendars.get("TARGET2").is_business_day(date(LAST_YEAR, 1, 1))

    def test_the_last_weekday_rule_handles_december(self) -> None:
        """It steps back from the first of the *next* month, so December has to
        cross a year boundary."""
        rule = Rule(name="last Monday in December", kind="last_weekday", month=12)
        assert rule.dates_in(2026) == (date(2026, 12, 28),)

    def test_an_unknown_rule_kind_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="unknown holiday rule kind"):
            Rule(name="x", kind="whenever").dates_in(2026)


class TestWhatACalendarCannotKnow:
    def test_ad_hoc_closures_are_supplied_never_inferred(self) -> None:
        """A state funeral is not a rule. 2022-09-19 was a UK bank holiday for
        the Queen's funeral and no algorithm could have produced it."""
        funeral = date(2022, 9, 19)
        assert install().get("London").is_business_day(funeral)

        amended = spec("London").with_closures([funeral]).materialise()
        assert not amended.is_business_day(funeral)

    def test_a_calendar_says_when_it_has_not_been_told_anything(self) -> None:
        """ "No ad-hoc closures supplied" and "there were no ad-hoc closures" are
        different statements, and a calendar that printed its rules and stayed
        silent about closures invites the reader to assume the second."""
        described = spec("TARGET2").describe()
        assert "no ad-hoc closures supplied" in described
        assert "not the same as there having been none" in described

    def test_supplied_closures_are_counted(self) -> None:
        described = spec("London").with_closures([date(2022, 9, 19)]).describe()
        assert "1 ad-hoc closure(s) supplied" in described


class TestInstallation:
    def test_it_is_explicit_rather_than_on_import(self) -> None:
        """A calendar that appears because a module was imported somewhere is
        one whose presence depends on import order, and the first symptom is a
        control that resolves in one process and refuses in another.

        Checked in a **subprocess**. This used to assert that `target2` is
        absent from the default registry, full stop — which held only because
        nothing in `src/` installed it, and stopped holding the moment
        `prama.packs.install_shipped()` did (finding H7). That is not a
        regression: the property was never "nobody installs these", it was
        "importing does not". In this process another test has almost certainly
        run the bootstrap already, so asking here measures test order rather
        than the code.
        """
        import subprocess
        import sys

        probe = (
            "import prama.packs.banking.calendars\n"
            "from prama.core.calendars import default_calendars\n"
            "print('target2' in default_calendars().names())\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", probe], capture_output=True, text=True, check=True
        )
        assert result.stdout.strip() == "False", (
            "importing the calendars module installed them; presence now depends on import order"
        )

    def test_the_bootstrap_does_install_them(self) -> None:
        """The other half. A module that installs nothing on import and nothing
        anywhere else is a module whose calendars never exist — which is what
        finding H7 was."""
        import subprocess
        import sys

        probe = (
            "from prama.packs import install_shipped\n"
            "install_shipped()\n"
            "from prama.core.calendars import default_calendars\n"
            "print('target2' in default_calendars().names())\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", probe], capture_output=True, text=True, check=True
        )
        assert result.stdout.strip() == "True", result.stdout + result.stderr

    def test_installing_twice_is_refused_unless_asked(self) -> None:
        registry = install()
        with pytest.raises(ValidationError, match="already registered"):
            install(registry)
        assert install(registry, replace=True) is registry

    def test_every_spec_materialises(self) -> None:
        for candidate in SPECS:
            calendar = candidate.materialise()
            assert calendar.holidays
            assert calendar.name == candidate.name

    def test_an_unknown_calendar_still_refuses_loudly(self, calendars: CalendarRegistry) -> None:
        """Installing a pack must not make an unknown name silently fall back to
        weekdays."""
        with pytest.raises(ValidationError, match="no calendar named"):
            calendars.get("TOKYO")


class TestObservanceItself:
    def test_none_loses_a_weekend_holiday(self) -> None:
        # 2027-12-25 is a Saturday.
        rule = Rule(name="Christmas", kind="fixed", month=12, day=25)
        assert observed([rule], [2027]) == frozenset({date(2027, 12, 25)})

    def test_roll_forward_moves_past_an_occupied_monday(self) -> None:
        first = Rule(name="a", kind="fixed", month=12, day=25, observance=Observance.ROLL_FORWARD)
        second = Rule(name="b", kind="fixed", month=12, day=26, observance=Observance.ROLL_FORWARD)
        # 2021-12-25 Saturday, 26th Sunday -> Monday 27th and Tuesday 28th.
        assert observed([first, second], [2021]) == frozenset(
            {date(2021, 12, 27), date(2021, 12, 28)}
        )


class TestTheRemedysOwnExampleParses:
    """Finding H7. `prama.schedule.spec` refuses `'06:30 TARGET2'` — an example
    its own error message tells the reader to copy.

        "Use one of: 'every 15 minutes', 'every 4 hours', 'daily', '06:30',
         '06:30 TARGET2', 'on arrival', 'manual'."

    Every listed form parsed except the one naming a calendar. `parse()`
    resolves through `default_calendars()`, seeded with `always` and `weekdays`
    alone, and `packs.banking.calendars.install()` — deliberately not called on
    import — was called from nowhere in `src/`. A user following the message
    exactly is told they are wrong, which is worse than no message.

    Two things had to be true, and only the first was obvious: the bootstrap
    has to run, *and* it has to install into the default registry. `install()`
    defaults to a fresh one and returns it, so calling it bare materialises
    every calendar into an object nobody holds — indistinguishable from not
    calling it.
    """

    def test_every_form_the_remedy_names_is_accepted(self) -> None:
        from prama.packs import install_shipped
        from prama.schedule.spec import parse

        install_shipped()
        for form in (
            "every 15 minutes",
            "every 4 hours",
            "daily",
            "06:30",
            "06:30 TARGET2",
            "on arrival",
            "manual",
        ):
            parse(form)  # raises if the remedy is lying

    def test_every_shipped_calendar_can_be_named_in_a_schedule(self) -> None:
        from prama.packs import install_shipped
        from prama.packs.banking.calendars import SPECS
        from prama.schedule.spec import parse

        install_shipped()
        for shipped in SPECS:
            parse(f"06:30 {shipped.name}")

    def test_a_calendar_nobody_ships_is_still_refused(self) -> None:
        """The counterfactual. Installing everything must not turn the check
        into a formality — a typo in a calendar name is a control that fires on
        the wrong days, silently."""
        from prama.core.errors import ValidationError
        from prama.packs import install_shipped
        from prama.schedule.spec import parse

        install_shipped()
        with pytest.raises(ValidationError, match="no calendar named"):
            parse("06:30 TARGET3")
