"""The shared rule for turning values into Arrow.

Every connector reached this and each was solving a piece of it, so the rule
lives in one place: a value that does not fit the column's natural type must
not be dropped, truncated, or silently made into a different number.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from decimal import Decimal

from prama.connect.arrow import to_array


class TestOrdinaryColumns:
    def test_integers_infer(self) -> None:
        assert to_array([1, 2, 3]).to_pylist() == [1, 2, 3]

    def test_strings_infer(self) -> None:
        assert to_array(["a", None, "b"]).to_pylist() == ["a", None, "b"]

    def test_decimals_survive(self) -> None:
        values = [Decimal("1953193.464900000000")]
        assert to_array(values).to_pylist() == values


class TestValuesThatDoNotFit:
    def test_an_unsigned_bigint_becomes_uint64(self) -> None:
        """MySQL's unsigned BIGINT goes past int64, and 18446744073709551615 is
        a real identifier. Inference raised rather than producing anything."""
        assert to_array([18446744073709551615, 1]).to_pylist() == [18446744073709551615, 1]

    def test_a_mixed_type_column_becomes_strings(self) -> None:
        """In MongoDB a field is 100 in one document and "one hundred" in the
        next, because nothing stopped it. That is the finding the estate is
        being examined for, and it has to survive into a control."""
        assert to_array([100, "one hundred"]).to_pylist() == ["100", "one hundred"]

    def test_a_value_beyond_every_integer_type_becomes_a_string(self) -> None:
        enormous = 10**40
        array = to_array([enormous])
        assert array.to_pylist() == [str(enormous)]
        assert str(array.type) == "string"

    def test_nulls_survive_every_fallback(self) -> None:
        assert to_array([10**40, None]).to_pylist() == [str(10**40), None]
        assert to_array([100, "text", None]).to_pylist() == ["100", "text", None]


class TestItNeverReachesForAFloat:
    def test_a_large_integer_does_not_become_a_float(self) -> None:
        """A float makes the read succeed and the number wrong, which is the
        failure this whole tree is built to avoid. A string is visibly a
        string, and a control asserting a numeric property of it fails loudly
        rather than passing on a value that was quietly reinterpreted."""
        array = to_array([10**40])
        assert "float" not in str(array.type)
        assert "double" not in str(array.type)

    def test_a_mixed_column_does_not_become_a_float(self) -> None:
        array = to_array([1.5, "x"])
        assert str(array.type) == "string"
