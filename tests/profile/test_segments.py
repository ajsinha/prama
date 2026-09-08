"""Cutting a dataset up the way a business person would describe it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import date

import pytest

from prama.core.errors import ValidationError
from prama.profile import MAX_SEGMENTS, Segmentation, SegmentGrain


def quote(identifier: str) -> str:
    return f'"{identifier}"'


class TestDailySegments:
    def test_a_range_becomes_one_segment_per_day(self) -> None:
        segments = Segmentation("booked").over_dates(date(2026, 4, 1), date(2026, 4, 3))
        assert [s.key for s in segments] == ["2026-04-01", "2026-04-02", "2026-04-03"]

    def test_the_bounds_are_half_open_so_days_cannot_overlap(self) -> None:
        # Inclusive upper bounds would count every midnight row twice, and the
        # double-count would show up as an inflated row total nobody can explain.
        first, second = Segmentation("booked").over_dates(date(2026, 4, 1), date(2026, 4, 2))
        assert first.upper == second.lower == date(2026, 4, 2)

    def test_a_single_day_is_a_single_segment(self) -> None:
        assert len(Segmentation("booked").over_dates(date(2026, 4, 1), date(2026, 4, 1))) == 1

    def test_a_backwards_range_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="ends before it begins"):
            Segmentation("booked").over_dates(date(2026, 4, 3), date(2026, 4, 1))


class TestMonthlySegments:
    def test_months_are_whole_and_cross_a_year_boundary(self) -> None:
        segments = Segmentation("booked", SegmentGrain.MONTH).over_dates(
            date(2025, 11, 15), date(2026, 2, 3)
        )
        assert [s.key for s in segments] == ["2025-11", "2025-12", "2026-01", "2026-02"]
        assert segments[1].lower == date(2025, 12, 1)
        assert segments[1].upper == date(2026, 1, 1)

    def test_a_partial_month_is_still_that_month(self) -> None:
        # The 15th belongs to November, not to a fortnight of its own.
        segments = Segmentation("booked", SegmentGrain.MONTH).over_dates(
            date(2026, 4, 15), date(2026, 4, 20)
        )
        assert [s.key for s in segments] == ["2026-04"]


class TestValueSegments:
    def test_one_segment_per_distinct_value(self) -> None:
        segments = Segmentation("entity", SegmentGrain.VALUE).over_values(
            ["EMEA", "APAC", "EMEA", "AMER"]
        )
        assert [s.key for s in segments] == ["AMER", "APAC", "EMEA"]

    def test_nulls_do_not_become_a_segment(self) -> None:
        # A null segmentation key means the row cannot be attributed anywhere;
        # inventing a "None" segment would make that look deliberate.
        segments = Segmentation("entity", SegmentGrain.VALUE).over_values(["EMEA", None])
        assert [s.key for s in segments] == ["EMEA"]

    def test_a_date_grain_cannot_be_built_from_values(self) -> None:
        with pytest.raises(ValidationError, match="cannot be built from a date range"):
            Segmentation("entity", SegmentGrain.VALUE).over_dates(
                date(2026, 4, 1), date(2026, 4, 2)
            )


class TestPredicates:
    def test_a_day_reads_as_a_half_open_range(self) -> None:
        segment = Segmentation("booked").over_dates(date(2026, 4, 1), date(2026, 4, 1))[0]
        assert segment.predicate(quote) == (
            "\"booked\" >= '2026-04-01' AND \"booked\" < '2026-04-02'"
        )

    def test_a_value_reads_as_equality(self) -> None:
        segment = Segmentation("entity", SegmentGrain.VALUE).over_values(["EMEA"])[0]
        assert segment.predicate(quote) == "\"entity\" = 'EMEA'"

    def test_the_column_is_quoted_by_the_dialect(self) -> None:
        # Segment columns come from a customer's catalogue and end up in a
        # query string.
        segment = Segmentation("odd name").over_dates(date(2026, 4, 1), date(2026, 4, 1))[0]
        assert '"odd name"' in segment.predicate(quote)

    def test_a_quote_inside_a_value_cannot_end_the_literal(self) -> None:
        segment = Segmentation("entity", SegmentGrain.VALUE).over_values(["O'Brien Ltd"])[0]
        assert segment.predicate(quote) == "\"entity\" = 'O''Brien Ltd'"


class TestLimits:
    def test_too_many_segments_is_refused_not_truncated(self) -> None:
        # Silently truncating would report "all segments healthy" while never
        # having looked at most of them.
        with pytest.raises(ValidationError) as caught:
            Segmentation("booked").over_dates(date(2020, 1, 1), date(2030, 1, 1))
        assert "coarser grain" in caught.value.remedy
        assert caught.value.context["maximum"] == MAX_SEGMENTS

    def test_a_segmentation_needs_a_column(self) -> None:
        with pytest.raises(ValidationError, match="needs the column"):
            Segmentation("")
