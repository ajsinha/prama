"""Three places where a nearly-right answer was worse than none.

QA round 2, `LIN-030`, `LIN-059`, `PCK-117`. A substring match that read an
ordinary column as an aggregate, a coverage figure that could be negative, and
a statement date that was a year early every January.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.lineage.scan import ScanResult
from prama.lineage.sql import Extraction, Gap


class TestAnAggregateIsMatchedOnItsWholeName:
    """`LIN-030`. `f"{name}(" in expression` is a substring search.

    `discount(price)` contains `count(` and `checksum(x)` contains `sum(`, so
    an ordinary derived column was classified as summed over many rows. Its
    edge was then attenuated to 0.35 and could fall below the impact floor and
    vanish from the graph — and lineage that quietly drops an edge is worse
    than lineage that has none, because an impact analysis run against it comes
    back clean.
    """

    @staticmethod
    def _transform(expression: str):
        from prama.lineage.sql import SqlLineage

        return SqlLineage._transform(expression)

    @pytest.mark.parametrize("expression", ["discount(price)", "checksum(payload)"])
    def test_a_longer_name_ending_in_an_aggregate_is_not_one(self, expression: str) -> None:
        from prama.lineage.sql import Transform

        assert self._transform(expression) is not Transform.AGGREGATED

    @pytest.mark.parametrize("expression", ["count(*)", "SUM(amount)", "max( notional )"])
    def test_a_real_aggregate_is_still_one(self, expression: str) -> None:
        """The counterfactual, including the spacing a formatter may add."""
        from prama.lineage.sql import Transform

        assert self._transform(expression) is Transform.AGGREGATED

    def test_broadcast_is_not_a_cast(self) -> None:
        """`"cast(" in lowered` had the same flaw one line down."""
        from prama.lineage.sql import Transform

        assert self._transform("broadcast(region)") is not Transform.RENAME


class TestCoverageIsAFraction:
    """`LIN-059`. `(found - unread) / found` where the two count different things.

    `units_found` counts units; `units_unread` counts *gaps*, and a gap is
    column-level, so one unreadable mapping produced five. Coverage came out at
    -400% and printed as "read -4 of 1 units".
    """

    @staticmethod
    def _result(units: int, gaps: tuple[Gap, ...]) -> ScanResult:
        return ScanResult(
            scanner="xml_mapping:powercenter",
            source="m.xml",
            extraction=Extraction(edges=(), gaps=gaps, statements=units),
            units_found=units,
            units_unread=len(gaps),
        )

    def test_many_gaps_in_one_unit_do_not_go_negative(self) -> None:
        gaps = tuple(Gap(kind="unresolved", detail=f"c{i}", statement="m1") for i in range(5))
        result = self._result(1, gaps)
        assert 0.0 <= result.coverage <= 1.0
        assert "-" not in result.describe().split("units in")[0]

    def test_a_clean_scan_is_complete(self) -> None:
        assert self._result(4, ()).coverage == 1.0

    def test_a_partial_scan_is_partial(self) -> None:
        """The counterfactual: clamping must not flatten the middle."""
        gaps = (Gap(kind="unresolved", detail="c", statement="m1"),)
        assert self._result(4, gaps).coverage == pytest.approx(0.75)


class TestAnEntryDateKnowsWhichYearItIsIn:
    """`PCK-117`. MT940 field 61 carries MMDD and no year.

    The year was taken from the value date, which is right except across a year
    boundary — and a statement covering the turn of the year is not an edge
    case, it is the first statement every January. A value date of 251231 with
    an entry of 0102 gave 2025-01-02: a year early, and eleven months before
    the value date it sits beside.

    Driven through `swift.parse` and `swift.statement` rather than the private
    helper, so the test means the same thing against the code before the fix.
    A counterfactual that fails on an ImportError has proved nothing.
    """

    @staticmethod
    def _entry_date(value_day: str, entry_day: str) -> str:
        from prama.packs.banking import swift

        message = (
            "{1:F01BANKGB2LAXXX0000000000}{2:O940BANKDEFFXXXXN}{4:\n"
            ":20:STMT-1\n"
            ":25:GB33BUKB20201555555555\n"
            ":28C:00001/001\n"
            f":60F:C{value_day}EUR1000,00\n"
            f":61:{value_day}{entry_day}C100,00NTRFREF-1//BANKREF1\n"
            ":86:a payment\n"
            f":62F:C{value_day}EUR1100,00\n"
            "-}"
        )
        return swift.statement(swift.parse(message)).lines[0].entry_date

    @pytest.mark.parametrize(
        "value_day,entry_day,expected",
        [
            ("251231", "0102", "2026-01-02"),  # December statement, January entry
            ("260102", "1231", "2025-12-31"),  # January statement, December entry
            ("260315", "0316", "2026-03-16"),  # the ordinary case, mid-year
            ("251231", "1231", "2025-12-31"),  # same day
        ],
    )
    def test_the_nearest_year_is_chosen(
        self, value_day: str, entry_day: str, expected: str
    ) -> None:
        assert self._entry_date(value_day, entry_day) == expected

    def test_no_entry_day_gives_no_entry_date(self) -> None:
        """Absent is not a date to guess at."""
        assert self._entry_date("260315", "") == ""
