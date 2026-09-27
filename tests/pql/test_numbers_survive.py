"""A number means the same thing on every path through Prama.

QA C1 (`PQL-300`, `BE-078`, `BE-079`, `BE-080`): the reference interpreter
did operator arithmetic in `float` while its functions used `Decimal`, so
`0.1 + 0.2` was `0.30000000000000004` on one path and `0.3` on the other.
QA C22 (`PQL-141`, `PQL-209`): `render()` used `:g`, six significant figures,
so `AT MOST 1234567 ROWS` re-read as 1234570.

The same family as Q-115: a number quietly changing on the way through.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from prama.backend.reference import UNKNOWN, _arithmetic, _compare
from prama.pql.parser import parse_control


class TestOperatorArithmeticIsExact:
    def test_a_tenth_plus_two_tenths_is_three_tenths(self) -> None:
        total = _arithmetic("+", [0.1, 0.2])
        assert total == Decimal("0.3")
        assert _compare("=", total, 0.3) is True  # a float column value

    def test_it_agrees_with_the_function_path(self) -> None:
        from prama.pql.library import _number

        assert _arithmetic("+", [0.1, 0.2]) == _number(0.1) + _number(0.2)

    def test_whole_numbers_still_add(self) -> None:
        # The control: ordinary arithmetic is unchanged in value.
        assert _arithmetic("*", [6, 7]) == 42
        assert _arithmetic("%", [-10, 3]) == -1  # SQL truncation, as before

    @pytest.mark.parametrize("bad", [True, "abc"])
    def test_a_non_number_is_unknown_not_a_crash_or_a_one(self, bad: object) -> None:
        assert _arithmetic("+", [bad, 1]) is UNKNOWN

    def test_division_by_zero_is_still_unknown(self) -> None:
        assert _arithmetic("/", [1, 0]) is UNKNOWN


class TestRenderingKeepsEveryDigit:
    @pytest.mark.parametrize(
        "source",
        [
            "CHECK p.a IS NOT NULL AT MOST 1234567 ROWS",
            "CHECK p.a IS NOT NULL BELOW 0.1234567%",
            "CHECK p.a IS NOT NULL AT MOST 5 ROWS",
        ],
    )
    def test_a_threshold_survives_a_round_trip(self, source: str) -> None:
        first = parse_control(source)
        again = parse_control(first.render())
        assert again.threshold.value == first.threshold.value, first.render()


class TestQualifiedDatasetsSurviveRendering:
    """Q-124: a quoted, schema-qualified dataset lost its quotes on render."""

    def test_a_dotted_dataset_round_trips(self) -> None:
        for source in (
            'CHECK "stg.trades".notional IS NOT NULL',
            'CHECK "stg.trades".account_id REFERENCES "raw.trades".account_id',
            'CHECK "stg.trades" HAS UNIQUE KEY (a, b)',
        ):
            control = parse_control(source)
            assert parse_control(control.render()) == control, control.render()

    def test_a_plain_dataset_is_still_written_bare(self) -> None:
        # The control: ordinary names do not start acquiring quotes.
        assert parse_control("CHECK p.a IS NOT NULL").render().startswith("CHECK p.a ")
