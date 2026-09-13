"""Every spelling the grammar accepts must run somewhere.

QA round 2, `BE-054`, `PQL-093`, `PQL-331`, `PQL-075`, `PQL-101`, `PQL-186`,
`PQL-187`. Syntax that parses, type-checks, lowers to a plan, receives a
`plan_id` — and then compiles on no engine, or raises a bare `KeyError` in the
reference interpreter, or is refused by a validator lookup the error message
told the author to use.

A language that accepts a control it cannot run has told the author their
control is fine. That is worse than a parse error, which at least arrives
before anybody believes it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import ClassVar

import pytest

from prama.backend.reference import ReferenceEvaluator
from prama.backend.sql import compile_for
from prama.ir.resolve import resolved
from prama.pql.parser import parse

DIALECTS = ("postgresql", "duckdb", "sqlite")


def _plan(assertion: str):
    """A lowered plan for one assertion.

    An assertion beginning with `.` attaches to the dataset — `trades.sedol …`
    — and anything else follows a space, which is the difference between a
    column predicate and a dataset-level one.
    """
    joined = f"trades{assertion}" if assertion.startswith(".") else f"trades {assertion}"
    return resolved(parse(f"CHECK {joined} BECAUSE 'a reason' OWNER 'ops'").all_controls[0])


class TestEveryOperatorTheGrammarAcceptsHasASqlForm:
    """`BE-054`, `PQL-093`. These reached the compiler's final `raise`.

    The keywords are in the lexer, in the parser's binding table and in
    `ast.PRECEDENCE`; only the compilation was missing. So they were real,
    reachable, documented syntax with no SQL form on any of the three engines.
    """

    @pytest.mark.parametrize(
        "assertion",
        [
            "SATISFIES ref LIKE 'GB%'",
            "SATISFIES ref ILIKE 'gb%'",
            "SATISFIES ref NOT LIKE 'X%'",
            "SATISFIES ref NOT ILIKE 'x%'",
            ".sedol HAS FORMAT '9999999'",
        ],
    )
    @pytest.mark.parametrize("dialect", DIALECTS)
    def test_it_compiles(self, assertion: str, dialect: str) -> None:
        query = compile_for(_plan(assertion), dialect).metric_query
        assert "violating_rows" in query

    def test_sqlite_gets_an_ilike_that_works(self) -> None:
        """SQLite has no ILIKE, and refusing would be the wrong answer.

        Its LIKE is already case-insensitive for ASCII, so the two are the same
        operator there. Folding both sides states that explicitly rather than
        relying on a default that is true today.
        """
        query = compile_for(_plan("SATISFIES ref ILIKE 'gb%'"), "sqlite").metric_query
        assert "UPPER(" in query


class TestTheReferenceInterpreterAgrees:
    """`PQL-093`. The same control failed two different ways.

    SQL refused with a well-formed `PqlUnsupportedError`; the reference raised a
    bare, uncaught `KeyError: 'HAS FORMAT'`. The reference is the conformance
    oracle, so it disagreeing is worse than it refusing.
    """

    ROWS: ClassVar[list[dict[str, str | None]]] = [
        {"sedol": "0263494"},
        {"sedol": "ABC1234"},
        {"sedol": None},
    ]

    def test_has_format_is_evaluated_rather_than_crashing(self) -> None:
        result = ReferenceEvaluator().run(_plan(".sedol HAS FORMAT '9999999'"), self.ROWS)
        assert result.metrics["scanned_rows"] == 3
        # '0263494' is seven digits and matches; 'ABC1234' does not; a null is
        # unknown, which the default policy counts as a violation.
        assert result.metrics["violating_rows"] == 2

    def test_like_is_evaluated_rather_than_falling_through_to_a_comparison(self) -> None:
        result = ReferenceEvaluator().run(_plan("SATISFIES sedol LIKE '02%'"), self.ROWS)
        assert result.metrics["violating_rows"] == 2


class TestTheExcelSurfaceProducesOperatorsThatExist:
    """`PQL-331`. `<>` mapped to `!=`, which is in neither operator table.

    The commonest operator in a spreadsheet produced an AST that compiled on no
    engine. The Excel surface exists so a business author can write what they
    already know, and `<>` is what they already know.
    """

    @pytest.mark.parametrize("dialect", DIALECTS)
    def test_an_excel_inequality_compiles(self, dialect: str) -> None:
        plan = _plan("""SATISFIES EXCEL '=[currency] <> "USD"'""")
        assert "violating_rows" in compile_for(plan, dialect).metric_query


class TestASemanticTypeIsNamedNotIdentified:
    """`PQL-075`. `VALIDATORS.find` was a case-sensitive dict lookup.

    PQL is written in upper case and the validators are registered in lower, so
    `IS VALID ISIN` — the spelling in two of the parser's own remedies — did not
    resolve. The error message told an author to type something that does not
    work.
    """

    @pytest.mark.parametrize("spelling", ["ISIN", "isin", "Isin"])
    def test_however_it_is_capitalised(self, spelling: str) -> None:
        assert _plan(f".id IS VALID {spelling}") is not None

    def test_a_name_that_really_is_unknown_is_still_refused(self) -> None:
        """The counterfactual: case-folding must not accept anything."""
        from prama.core.errors import ValidationError

        with pytest.raises(ValidationError, match="no semantic type"):
            _plan(".id IS VALID NOT_A_REAL_TYPE")


class TestACompositeDependencyCanBeWritten:
    """`PQL-101`. `(a, b) DETERMINES (c, d)` could not be parsed at all.

    `_as_columns` handles a list of columns and the assertion node carries
    tuples on both sides, so the feature was built — the grammar path reaching
    it was simply unreachable, because the expression parser met the comma
    first and failed with "expected ')' and found ','".
    """

    def test_the_single_form_still_parses(self) -> None:
        plan = _plan("SATISFIES account_id DETERMINES legal_entity_id")
        assert plan.assertion_kind == "functional_dependency"

    def test_the_composite_form_parses(self) -> None:
        control = parse(
            "CHECK trades SATISFIES (account_id, book) DETERMINES (entity, region) "
            "BECAUSE 'r' OWNER 'ops'"
        ).all_controls[0]
        assert [c.name for c in control.assertion.determinant] == ["account_id", "book"]
        assert [c.name for c in control.assertion.dependent] == ["entity", "region"]

    def test_a_parenthesised_expression_is_still_an_expression(self) -> None:
        """The counterfactual, and the reason this needed backtracking.

        `(` is ambiguous: `(a + b) > 0` is a bracket and `(a, b) DETERMINES` is
        a column list. Reading every `(` as a column list would break every
        parenthesised expression in the language.
        """
        control = parse("CHECK trades SATISFIES (a + b) > 0 BECAUSE 'r' OWNER 'ops'").all_controls[
            0
        ]
        assert type(control.assertion).__name__ == "ExpressionAssertion"


class TestAnAggregateIsNotItsScalarNamesake:
    """`PQL-186`, `PQL-187`. The aggregate table said `MIN_AGG` and `MAX_AGG`.

    Those spellings appeared nowhere else — no parser, lowering or backend ever
    produced them — so a single-argument `MIN(notional)` missed the table and
    was checked against the *scalar* two-argument `MIN`, reporting "MIN takes at
    least 2 argument(s), and was given 1" about a perfectly ordinary aggregate.
    """

    @staticmethod
    def _problems(expression: str):
        from prama.pql.types import check_calls

        control = parse(
            f"CHECK trades SATISFIES {expression} BECAUSE 'r' OWNER 'ops'"
        ).all_controls[0]
        return check_calls(control.assertion.condition)

    def test_a_one_argument_min_is_the_aggregate(self) -> None:
        assert self._problems("MIN(notional) > 0") == []

    def test_a_one_argument_max_is_the_aggregate(self) -> None:
        assert self._problems("MAX(notional) < 1000") == []

    def test_the_two_argument_scalar_still_works(self) -> None:
        """The counterfactual.

        Declaring MIN an aggregate unconditionally would skip arity checking
        for the scalar form, which is the check that stops `MIN()` reaching
        SQL. Arity is the only thing distinguishing them, which is exactly how
        SQL tells them apart too.
        """
        assert self._problems("MIN(a, b) > 0") == []
