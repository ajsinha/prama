"""Printing a rate without rounding towards good news.

Written against one observed failure: a dataset with 412 failing rows in
1,284,301 scored 99.968%, and one decimal place rendered it as **100.0%** on
the scorecard. Technically correct, and exactly what this product exists not to
do — the number a business owner reads said the data was perfect.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.report.rate import MAX_DECIMALS, plain


class TestItNeverPrintsPerfectionThatIsNotThere:
    def test_the_observed_failure(self) -> None:
        assert plain(1 - 412 / 1_284_301) == "99.97%"

    @pytest.mark.parametrize("value", [0.9999, 0.99999, 0.999999, 1 - 1e-9, 1 - 1e-12])
    def test_no_value_below_one_prints_as_a_hundred(self, value: float) -> None:
        rendered = plain(value)
        assert rendered != "100%"
        assert rendered != "100.0%"

    def test_exactly_one_does_print_as_a_hundred(self) -> None:
        """The counterfactual. A formatter that could never say 100% would be
        useless, and a clean dataset deserves to be called clean."""
        assert plain(1.0) == "100%"

    def test_precision_grows_only_as_far_as_it_helps(self) -> None:
        """Past a basis point nobody acts on the difference, so it degrades to
        'close to' rather than to a wall of digits — or to 100%."""
        assert plain(1 - 1e-12) == ">99.99%"
        assert len(plain(0.9)) <= len("99.9999%")


class TestItNeverPrintsZeroThatIsNotThere:
    def test_a_tiny_positive_rate_is_not_zero(self) -> None:
        """ "Nothing passed" and "almost nothing passed" are different facts
        about a remediation that is underway."""
        assert plain(1e-7) == "<0.0001%"

    def test_exactly_zero_does_print_as_zero(self) -> None:
        assert plain(0.0) == "0%"


class TestOrdinaryValuesStayReadable:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [(0.5, "50.0%"), (0.9, "90.0%"), (0.333333, "33.3%"), (0.125, "12.5%")],
    )
    def test_it_does_not_add_precision_it_does_not_need(self, value: float, expected: str) -> None:
        assert plain(value) == expected

    def test_the_preferred_precision_is_respected(self) -> None:
        assert plain(0.123456, decimals=2) == "12.35%"

    def test_the_cap_is_a_basis_point(self) -> None:
        """The smallest difference anyone in this domain acts on."""
        assert MAX_DECIMALS == 4
