"""The reference interpreter, and the logic it exists to get right.

These test the interpreter directly rather than by comparison, because the
comparison only tells you two implementations disagree — not which is wrong.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.backend.reference import (
    UNKNOWN,
    Bindings,
    ReferenceEvaluator,
    _and,
    _membership,
    _not,
    _or,
)
from prama.ir.lower import Lowerer
from prama.ir.model import Verdict
from prama.pql.parser import parse_control

ROWS = [
    {"a": 1, "b": "x", "c": 10.0},
    {"a": 2, "b": "y", "c": None},
    {"a": None, "b": "x", "c": 30.0},
    {"a": 4, "b": None, "c": -5.0},
]


def run(source: str, rows: list[dict] | None = None, **bindings: object):
    # `rows if rows is not None`, not `rows or ROWS`: an empty scope is a case
    # worth testing, and treating it as "not supplied" would silently run the
    # default rows instead.
    plan = Lowerer().control(parse_control(source))
    return ReferenceEvaluator(Bindings(dict(bindings))).run(plan, ROWS if rows is None else rows)


class TestKleeneLogic:
    """Python's and/or are two-valued and its None is falsy. Neither will do."""

    def test_false_dominates_a_conjunction(self) -> None:
        assert _and(False, UNKNOWN) is False
        assert _and(UNKNOWN, False) is False

    def test_an_unknown_survives_a_conjunction_of_truths(self) -> None:
        assert _and(True, UNKNOWN) is UNKNOWN

    def test_true_dominates_a_disjunction(self) -> None:
        assert _or(True, UNKNOWN) is True
        assert _or(UNKNOWN, True) is True

    def test_an_unknown_survives_a_disjunction_of_falsehoods(self) -> None:
        assert _or(False, UNKNOWN) is UNKNOWN

    def test_not_unknown_is_unknown(self) -> None:
        # The one that a two-valued implementation gets wrong, and the reason
        # a NOT around a null-bearing predicate silently changes a verdict.
        assert _not(UNKNOWN) is UNKNOWN
        assert _not(True) is False


class TestMembership:
    """SQL's IN, including the part everybody forgets."""

    def test_a_present_value_is_in(self) -> None:
        assert _membership(1, [1, 2], negated=False) is True

    def test_an_absent_value_is_not_in(self) -> None:
        assert _membership(3, [1, 2], negated=False) is False

    def test_a_null_in_the_list_makes_absence_unknown(self) -> None:
        # x NOT IN (1, 2, NULL) is never true: x might equal the null. Getting
        # this wrong is the classic SQL bug, and an engine that got it right
        # while the interpreter did not would show up as a conformance failure
        # — which is exactly what the interpreter is for.
        assert _membership(3, [1, 2, UNKNOWN], negated=False) is UNKNOWN
        assert _membership(3, [1, 2, UNKNOWN], negated=True) is UNKNOWN

    def test_but_a_match_is_still_decisive(self) -> None:
        assert _membership(1, [1, UNKNOWN], negated=False) is True
        assert _membership(1, [1, UNKNOWN], negated=True) is False

    def test_an_unknown_value_is_never_in_anything(self) -> None:
        assert _membership(UNKNOWN, [1, 2], negated=False) is UNKNOWN


class TestUnknownsAreViolations:
    def test_a_null_counts_against_the_control(self) -> None:
        # Row 2 has c = NULL. Under SQL's own default it would vanish.
        result = run("CHECK t.c > 0")
        assert result.metrics["violating_rows"] == 2  # the null and the -5.0

    def test_unless_the_control_says_otherwise(self) -> None:
        result = run("CHECK t.c > 0 TREAT UNKNOWN AS PASS BECAUSE 'declared'")
        assert result.metrics["violating_rows"] == 1

    def test_a_function_of_an_unknown_is_unknown(self) -> None:
        # LENGTH(NULL) returning 0 would make a length check silently pass on
        # every null.
        result = run("CHECK t.b HAS LENGTH BETWEEN 1 AND 1")
        assert result.metrics["violating_rows"] == 1  # the null b


class TestFilters:
    def test_an_unknown_filter_excludes_the_row(self) -> None:
        # SQL's rule for WHERE, and the right one: a row we cannot tell is in
        # scope is not in scope, and counting it would put rows in the
        # denominator the engine never looked at.
        result = run("CHECK t.b IS NOT NULL WHERE c > 0")
        assert result.metrics["scanned_rows"] == 2  # c = 10.0 and c = 30.0

    def test_the_denominator_follows_the_filter(self) -> None:
        result = run("CHECK t.b IS NOT NULL WHERE a IS NOT NULL")
        assert result.metrics["scanned_rows"] == 3


class TestArithmetic:
    def test_a_sign_is_not_a_subtraction(self) -> None:
        # A unary minus reaching an implementation that expects two operands
        # drops the sign — and every engine agrees on the wrong answer, so
        # nothing notices. This is the bug the interpreter found.
        result = run("CHECK t.c BETWEEN -10 AND 100")
        assert result.metrics["violating_rows"] == 1  # only the null

    def test_division_by_zero_is_unknown_not_an_error(self) -> None:
        # An error would abort a control over one bad row; zero would silently
        # change the answer.
        rows = [{"a": 1, "b": 0}, {"a": 1, "b": 1}]
        result = run("CHECK t SATISFIES a / b > 0", rows)
        assert result.metrics["violating_rows"] == 1


class TestKeys:
    def test_a_null_key_is_not_a_duplicate(self) -> None:
        # It is a different failure: a null key identifies nothing, so it
        # cannot be one row per anything. Counting it as a duplicate would
        # misattribute the problem and misdirect whoever investigates.
        result = run("CHECK t HAS UNIQUE KEY (a)")
        assert result.metrics["null_key_rows"] == 1
        assert result.metrics["duplicate_rows"] == 0
        assert result.metrics["violating_rows"] == 1

    def test_a_real_duplicate_is_counted_once(self) -> None:
        result = run("CHECK t HAS UNIQUE KEY (b)")
        assert result.metrics["duplicate_rows"] == 1  # two rows share 'x'
        assert result.metrics["null_key_rows"] == 1

    def test_a_clean_key_passes(self) -> None:
        result = run("CHECK t HAS UNIQUE KEY (c)", [{"c": 1}, {"c": 2}, {"c": 3}])
        assert result.verdict is Verdict.PASS


class TestScopes:
    def test_an_empty_scope_is_indeterminate_not_a_pass(self) -> None:
        # An empty scope has demonstrated nothing. Reporting green is how a
        # broken feed goes unnoticed.
        assert run("CHECK t HAS UNIQUE KEY (a)", []).verdict is Verdict.INDETERMINATE

    def test_a_segment_is_judged_on_its_own_rows(self) -> None:
        result = run("CHECK t.c IS NOT NULL FOR EACH b")
        assert result.verdict is Verdict.FAIL
        assert {s.key for s in result.failing_segments} == {"y"}

    def test_a_run_parameter_is_bound_at_execution(self) -> None:
        result = run("CHECK t SATISFIES a = $expected", expected=1)
        assert result.metrics["violating_rows"] == 3


class TestItSharesNothingWithTheCompiler:
    def test_it_never_asks_for_sql(self) -> None:
        # If it did, it would be a fourth opinion from the same compiler rather
        # than an independent check.
        import inspect

        from prama.backend import reference

        source = inspect.getsource(reference)
        assert "SELECT" not in source
        assert "prama.backend.sql" not in source
        assert "dialect" not in source

    @pytest.mark.parametrize(
        "source",
        [
            "CHECK t.a IS NOT NULL",
            "CHECK t.c BETWEEN -10 AND 30",
            "CHECK t.b IN ('x', 'y')",
            "CHECK t SATISFIES NOT (a = 1 AND c > 0)",
            "CHECK t HAS ROW COUNT BETWEEN 1 AND 10",
            "CHECK t HAS UNIQUE KEY (a, b)",
        ],
    )
    def test_it_answers_for_every_shape_of_control(self, source: str) -> None:
        result = run(source)
        assert result.verdict in (Verdict.PASS, Verdict.FAIL)
        assert result.engine == "reference"
