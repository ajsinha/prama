"""Filename patterns.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import date

import pytest

from prama.connect.feed import FilenamePattern
from prama.core.errors import ValidationError


class TestParsing:
    def test_a_business_date_is_recovered_from_the_name(self) -> None:
        pattern = FilenamePattern("POS_EXTRACT_{YYYYMMDD}.csv")
        parsed = pattern.parse("POS_EXTRACT_20260402.csv")
        assert parsed is not None
        assert parsed.business_date == date(2026, 4, 2)

    def test_a_name_from_a_different_feed_does_not_match(self) -> None:
        pattern = FilenamePattern("POS_EXTRACT_{YYYYMMDD}.csv")
        assert pattern.parse("TRADES_20260402.csv") is None
        assert pattern.parse("POS_EXTRACT_20260402.csv.gz") is None

    def test_literal_text_is_escaped_not_interpreted(self) -> None:
        # A dot in the literal must not match any character, or POS_EXTRACTX
        # would look like a valid delivery.
        pattern = FilenamePattern("POS.{YYYYMMDD}.csv")
        assert pattern.parse("POSX20260402Xcsv") is None
        assert pattern.parse("POS.20260402.csv") is not None

    @pytest.mark.parametrize(
        ("template", "name", "expected"),
        [
            ("f_{YYYY-MM-DD}.csv", "f_2026-04-02.csv", date(2026, 4, 2)),
            ("f_{DDMMYYYY}.csv", "f_02042026.csv", date(2026, 4, 2)),
            ("f_{YYYY}{MM}{DD}.csv", "f_20260402.csv", date(2026, 4, 2)),
            ("{YY}{MM}{DD}_f.csv", "260402_f.csv", date(2026, 4, 2)),
        ],
    )
    def test_the_date_conventions_senders_actually_use(
        self, template: str, name: str, expected: date
    ) -> None:
        parsed = FilenamePattern(template).parse(name)
        assert parsed is not None
        assert parsed.business_date == expected

    def test_a_delivery_time_is_taken_from_the_name_when_present(self) -> None:
        parsed = FilenamePattern("f_{YYYYMMDD}_{HH}{mm}.csv").parse("f_20260402_0615.csv")
        assert parsed is not None
        assert parsed.delivery_time is not None
        assert (parsed.delivery_time.hour, parsed.delivery_time.minute) == (6, 15)

    def test_an_impossible_date_leaves_the_name_dateless_not_wrong(self) -> None:
        # 30 February parses structurally. Coercing it to 1 March would attribute
        # the file to a day it was never for; discarding the match entirely would
        # hide the file from the feed it plainly belongs to. So it matches, and
        # carries no date — which the arrival judge reports as an unreadable name.
        parsed = FilenamePattern("f_{YYYYMMDD}.csv").parse("f_20260230.csv")
        assert parsed is not None
        assert not parsed.has_date

    def test_a_sequence_orders_intraday_deliveries(self) -> None:
        pattern = FilenamePattern("f_{YYYYMMDD}_{SEQ:3}.csv")
        first = pattern.parse("f_20260402_001.csv")
        second = pattern.parse("f_20260402_002.csv")
        assert first is not None and second is not None
        assert first.sequence == 1
        assert second.sequence == 2
        assert pattern.parse("f_20260402_02.csv") is None  # width is fixed

    def test_a_wildcard_absorbs_the_part_nobody_controls(self) -> None:
        pattern = FilenamePattern("f_{YYYYMMDD}_{ANY}.csv")
        assert pattern.parse("f_20260402_batch7of9.csv") is not None


class TestRendering:
    def test_rendering_names_the_file_that_should_have_arrived(self) -> None:
        # The whole point: a missing-file alert has to say what to go and look for.
        pattern = FilenamePattern("POS_EXTRACT_{YYYYMMDD}.csv")
        assert pattern.render(date(2026, 4, 2)) == "POS_EXTRACT_20260402.csv"

    def test_a_sequence_renders_at_its_declared_width(self) -> None:
        pattern = FilenamePattern("f_{YYYYMMDD}_{SEQ:4}.csv")
        assert pattern.render(date(2026, 4, 2), sequence=7) == "f_20260402_0007.csv"

    def test_an_uncontrolled_part_renders_as_a_glob_to_search_with(self) -> None:
        # The alert cannot name the file exactly, but "go look for this" still
        # beats "something is missing".
        pattern = FilenamePattern("f_{YYYYMMDD}_{ANY}.csv")
        assert pattern.render(date(2026, 4, 2)) == "f_20260402_*.csv"

    def test_round_trip_holds_for_every_renderable_pattern(self) -> None:
        for template in (
            "f_{YYYYMMDD}.csv",
            "f_{YYYY-MM-DD}.csv",
            "f_{DDMMYYYY}.csv",
            "{YY}{MM}{DD}.dat",
        ):
            pattern = FilenamePattern(template)
            day = date(2026, 4, 2)
            parsed = pattern.parse(pattern.render(day))
            assert parsed is not None and parsed.business_date == day


class TestDeclaration:
    def test_a_dateless_pattern_is_allowed_but_declares_its_weakness(self) -> None:
        # Plenty of real feeds overwrite one fixed name. Refusing them would
        # exclude the feeds most in need of monitoring; instead the pattern says
        # it carries no date, and FeedDefinition declines to claim it can detect
        # a missing delivery.
        pattern = FilenamePattern("positions.csv")
        assert not pattern.carries_date

    def test_an_unknown_token_is_named_in_the_error(self) -> None:
        with pytest.raises(ValidationError) as caught:
            FilenamePattern("f_{YYYYMMDD}_{REGION}.csv")
        assert "{REGION}" in str(caught.value)
        assert "{ANY}" in caught.value.remedy

    def test_a_month_without_a_day_is_a_monthly_feed_not_an_error(self) -> None:
        # Regulatory extracts are named RWA_202604.csv. The first of the month
        # is the right reading.
        parsed = FilenamePattern("RWA_{YYYY}{MM}.csv").parse("RWA_202604.csv")
        assert parsed is not None
        assert parsed.business_date == date(2026, 4, 1)

    def test_a_day_without_a_month_is_refused(self) -> None:
        # Unlike the month case there is no sane reading: every file in the year
        # would collapse onto the same 31 dates and be reported as duplicates.
        with pytest.raises(ValidationError, match="day token but no month"):
            FilenamePattern("f_{YYYY}{DD}.csv")
