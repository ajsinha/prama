"""Semantic types an engine can only half-answer.

The whole design in one file: a check digit is not expressible in SQL, the
screen that is expressible is a *necessary* condition rather than a sufficient
one, and a pass may never be reported from the screen alone.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.backend.execute import judge
from prama.backend.reference import ReferenceEvaluator
from prama.backend.sql import SqlCompiler
from prama.core.errors import ValidationError
from prama.ir.lower import Lowerer
from prama.ir.model import Comparator, Threshold, Verdict
from prama.pql.parser import parse_control


def a_plan(source: str):
    """One control, lowered to its plan."""
    return Lowerer().control(parse_control(source))


REAL = "5493001KJTIIGC8Y1R12"
LEGACY = "HWUPKR0MPOU8FGXBT394"
#: A perfect LEI shape whose check characters do not verify. The value the
#: whole two-stage design exists for.
FABRICATED = "AAAAAAAAAAAAAAAAAA00"
MISSHAPEN = "not-an-lei"


def plan_for(pql: str):  # type: ignore[no-untyped-def]
    return Lowerer().control(parse_control(pql))


def test_a_checksum_type_lowers_to_a_screen_and_a_residual() -> None:
    plan = plan_for("CHECK positions.lei IS VALID 'lei'")
    assert plan.is_two_stage
    assert plan.residual_validators == (("lei", "lei"),)


def test_a_shape_only_type_lowers_complete() -> None:
    """A UUID's regular expression is the whole standard; there is no residual
    and demanding a second pass over the rows would be waste."""
    plan = plan_for("CHECK t.id IS VALID 'uuid'")
    assert not plan.is_two_stage
    assert plan.residual_validators == ()


def test_a_two_stage_plan_hashes_differently_from_a_screen_only_one() -> None:
    """Two plans that check different things must never share an id, or a
    cached result for one answers for the other."""
    assert (
        plan_for("CHECK t.x IS VALID 'lei'").plan_id
        != plan_for("CHECK t.x MATCHES /^[A-Z0-9]{18}[0-9]{2}$/").plan_id
    )


def test_the_compiled_query_declares_that_it_is_not_the_whole_test() -> None:
    """Carried on the artefact rather than left to every call site to
    remember, because remembering is what fails."""
    compiled = SqlCompiler("postgresql").compile(plan_for("CHECK t.lei IS VALID 'lei'"))
    assert not compiled.is_complete
    assert compiled.residual_validators == (("lei", "lei"),)
    assert SqlCompiler("postgresql").compile(plan_for("CHECK t.id IS VALID 'uuid'")).is_complete


def test_the_screen_appears_in_the_sql_and_the_check_digit_does_not() -> None:
    """Not a defect — the arithmetic has no faithful SQL form. The defect
    would be claiming otherwise."""
    query = SqlCompiler("postgresql").compile(plan_for("CHECK t.lei IS VALID 'lei'")).metric_query
    assert "[A-Z0-9]{18}[0-9]{2}" in query


def test_the_exact_check_catches_what_the_screen_cannot() -> None:
    """The row that motivates the whole design: right shape, wrong checksum."""
    plan = plan_for("CHECK t.lei IS VALID 'lei'")
    rows = [{"lei": REAL}, {"lei": LEGACY}, {"lei": FABRICATED}, {"lei": MISSHAPEN}]
    result = ReferenceEvaluator().run(plan, rows)
    assert result.violating_rows == 2  # the fabricated one and the misshapen one


def test_the_screen_alone_would_have_passed_the_fabricated_value() -> None:
    """Stated as a counterfactual, because a control that cannot fail is worth
    nothing and this is the failure it must be able to have."""
    screen_only = plan_for("CHECK t.lei MATCHES /^[A-Z0-9]{18}[0-9]{2}$/")
    result = ReferenceEvaluator().run(screen_only, [{"lei": FABRICATED}])
    assert result.violating_rows == 0

    exact = plan_for("CHECK t.lei IS VALID 'lei'")
    assert ReferenceEvaluator().run(exact, [{"lei": FABRICATED}]).violating_rows == 1


def test_a_valid_value_is_never_rejected_by_the_screen() -> None:
    """The one direction the design cannot tolerate. A legacy LEI carries
    letters where ISO 17442 reserves zeros, and a tighter screen would report a
    violation on live reference data."""
    plan = plan_for("CHECK t.lei IS VALID 'lei'")
    for value in (REAL, LEGACY):
        assert ReferenceEvaluator().run(plan, [{"lei": value}]).violating_rows == 0


def test_a_null_is_a_completeness_question_not_a_format_one() -> None:
    """Under the default unknown policy the null still counts, but it counts as
    an unknown rather than as a malformed value."""
    plan = plan_for("CHECK t.lei IS VALID 'lei' TREAT UNKNOWN AS PASS BECAUSE 'x'")
    assert ReferenceEvaluator().run(plan, [{"lei": None}]).violating_rows == 0


def test_an_unknown_semantic_type_is_refused_at_lowering() -> None:
    """It would otherwise compile to a check that passes everything, which is
    worse than no control because it looks like coverage."""
    with pytest.raises(ValidationError, match="no semantic type called"):
        plan_for("CHECK t.x IS VALID 'not_a_type'")


def test_a_residual_that_cannot_be_located_is_refused() -> None:
    """A residual nobody can apply is a green control over invalid data.

    Built as an AST rather than parsed, because the grammar already refuses to
    write this. That makes the guard defence in depth rather than the first
    line — and it is worth having, since the AST is also what the generator and
    the importers construct, and neither of them goes through the parser.
    """
    from prama.pql import ast

    control = ast.Control(
        target="t",
        assertion=ast.PredicateAssertion(
            subject=ast.FunctionCall(name="UPPER", arguments=(ast.ColumnRef(name="lei"),)),
            operator="is_valid",
            argument=ast.Literal(value="lei"),
        ),
    )
    with pytest.raises(ValidationError, match="can only be applied to a column"):
        Lowerer().control(control)


def test_the_corpus_carries_the_row_no_engine_can_catch() -> None:
    """A conformance corpus without it would let a screen-only implementation
    pass every case."""
    from prama.backend.corpus import COLUMNS, ROWS

    index = [c[0] for c in COLUMNS].index("lei")
    assert FABRICATED in {row[index] for row in ROWS}


def test_conformance_permits_an_engine_to_find_fewer_but_never_more() -> None:
    """The bound, asserted directly. An engine finding more violations than the
    exact check means its screen rejects a value the standard accepts."""
    from prama.backend.conformance import ConformanceRun
    from prama.backend.corpus import CASES, COLUMNS, ROWS

    rows = [dict(zip([c[0] for c in COLUMNS], r, strict=True)) for r in ROWS]
    run = ConformanceRun(rows=rows)
    case = next(c for c in CASES if c.name == "semantic_type_two_stage")
    exact = run.run_case(case, "reference", None)
    assert exact.result is not None
    assert exact.result.violating_rows == 3  # misshapen, null, and fabricated

    compiled = SqlCompiler("duckdb").compile(run.plan_for(case))
    assert not compiled.is_complete


class TestNothingScannedIsNotAPass:
    """QA finding Q-09. The guard existed on one branch of two.

    `Threshold.evaluate` refused an empty scan when the threshold was a
    *percentage* — its comment says "an empty scope is a fact about the scope,
    and calling it a pass is how a broken feed reports green" — and reported
    PASS when the threshold was *absolute*, which is the default every predicate
    control lowers to. Zero rows give zero violations, and `0 <= 0` holds.

    Same scan, same metrics, opposite verdicts, and the one that said PASS was
    the common path. It is finding C5 one layer down: C5 was the scorecard
    turning no evidence into full marks, and this is the engine doing it first —
    so the ledger recorded `pass` for the very records the scorecard described
    as "nothing has been measured".
    """

    def absolute(self) -> Threshold:
        return Threshold(metric="violating_rows", comparator=Comparator.LE, value=0.0)

    def relative(self) -> Threshold:
        return Threshold(
            metric="violating_rows",
            comparator=Comparator.LE,
            value=0.0,
            relative_to="scanned_rows",
        )

    def test_an_absolute_threshold_refuses_an_empty_scan(self) -> None:
        empty = {"scanned_rows": 0.0, "violating_rows": 0.0}
        assert self.absolute().evaluate(empty) is Verdict.INDETERMINATE

    def test_a_relative_threshold_still_refuses_one(self) -> None:
        """The branch that was already right, kept."""
        empty = {"scanned_rows": 0.0, "violating_rows": 0.0}
        assert self.relative().evaluate(empty) is Verdict.INDETERMINATE

    def test_the_two_agree(self) -> None:
        """The property, rather than two separate assertions: how a threshold
        is *spelled* must not change what an empty scan means."""
        empty = {"scanned_rows": 0.0, "violating_rows": 0.0}
        assert self.absolute().evaluate(empty) is self.relative().evaluate(empty)

    def test_a_clean_scan_of_real_rows_is_still_a_pass(self) -> None:
        """The counterfactual. A guard that refused everything would make every
        control indeterminate and pass the tests above."""
        clean = {"scanned_rows": 1_000.0, "violating_rows": 0.0}
        assert self.absolute().evaluate(clean) is Verdict.PASS
        assert self.relative().evaluate(clean) is Verdict.PASS

    def test_a_dirty_scan_still_fails(self) -> None:
        dirty = {"scanned_rows": 1_000.0, "violating_rows": 4.0}
        assert self.absolute().evaluate(dirty) is Verdict.FAIL

    def test_a_row_count_control_still_judges_an_empty_table(self) -> None:
        """`row_count` does not come through `Threshold.evaluate`, and must not:
        an empty table genuinely *is* a row count of zero, and
        `HAS ROW COUNT BETWEEN 1 AND 8` has to fail on it rather than shrug."""
        plan = a_plan("CHECK corpus HAS ROW COUNT BETWEEN 1 AND 8 BECAUSE 'x'")
        result = judge(plan, {"scanned_rows": 0.0})
        assert result.verdict is Verdict.FAIL
