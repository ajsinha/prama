"""Reading PQL into an AST, and writing it back unchanged.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.pql import ast
from prama.pql.errors import PqlSyntaxError
from prama.pql.parser import parse, parse_control


def one(source: str) -> ast.Control:
    return parse_control(source)


class TestTheAssertionCatalogue:
    def test_a_column_check_is_scoped_to_its_dataset(self) -> None:
        # positions.notional is a check *on positions*, about one column. Read
        # the other way round, every column check would have a scope of one
        # column and the row count would mean nothing.
        control = one("CHECK positions.notional IS NOT NULL")
        assert control.target == "positions"
        assert isinstance(control.assertion, ast.PredicateAssertion)
        assert control.assertion.subject.name == "notional"  # type: ignore[union-attr]

    def test_is_not_null_and_is_null_are_distinct(self) -> None:
        assert one("CHECK p.a IS NULL").assertion.operator == "is_null"  # type: ignore[attr-defined]
        assert one("CHECK p.a IS NOT NULL").assertion.operator == "is_not_null"  # type: ignore[attr-defined]

    def test_a_declared_grain_becomes_a_unique_key(self) -> None:
        control = one("CHECK p HAS UNIQUE KEY (account_id, instrument_id, as_of_date)")
        assert isinstance(control.assertion, ast.UniqueKeyAssertion)
        assert [c.name for c in control.assertion.columns] == [
            "account_id",
            "instrument_id",
            "as_of_date",
        ]

    def test_row_count_takes_a_range_or_a_bound(self) -> None:
        both = one("CHECK p HAS ROW COUNT BETWEEN 100 AND 200").assertion
        assert (both.minimum, both.maximum) == (100, 200)  # type: ignore[attr-defined]
        lower = one("CHECK p HAS ROW COUNT AT LEAST 100").assertion
        assert (lower.minimum, lower.maximum) == (100, None)  # type: ignore[attr-defined]

    def test_a_reference_names_both_sides(self) -> None:
        control = one("CHECK p.account_id REFERENCES accounts.account_id")
        assertion = control.assertion
        assert isinstance(assertion, ast.ReferenceAssertion)
        assert (assertion.target_dataset, assertion.target_column) == ("accounts", "account_id")

    def test_freshness_carries_its_calendar(self) -> None:
        control = one("CHECK p IS FRESH WITHIN 4 HOURS OF '06:30' CALENDAR 'TARGET2'")
        assertion = control.assertion
        assert isinstance(assertion, ast.FreshnessAssertion)
        assert assertion.tolerance_minutes == 240
        assert (assertion.due_time, assertion.calendar) == ("06:30", "TARGET2")

    def test_a_functional_dependency_is_not_an_ordinary_expression(self) -> None:
        control = one("CHECK p SATISFIES account_id DETERMINES legal_entity_id")
        assert isinstance(control.assertion, ast.FunctionalDependencyAssertion)

    def test_satisfies_otherwise_takes_any_condition(self) -> None:
        control = one("CHECK trades SATISFIES NOT (side = 'BUY' AND quantity < 0)")
        assert isinstance(control.assertion, ast.ExpressionAssertion)

    def test_a_codelist_is_distinguished_from_a_literal_set(self) -> None:
        assert one("CHECK p.ccy IN CODELIST iso4217").assertion.operator == "in_codelist"  # type: ignore[attr-defined]
        assert one("CHECK p.ccy IN ('GBP','USD')").assertion.operator == "in"  # type: ignore[attr-defined]


class TestModifiers:
    def test_modifiers_may_come_in_any_order(self) -> None:
        # People write them in the order they think of them. A language that
        # insisted otherwise would be rejected by everyone who had to use it.
        first = one("CHECK p.a IS NOT NULL SEVERITY minor WHERE b > 1 BECAUSE 'x'")
        second = one("CHECK p.a IS NOT NULL BECAUSE 'x' WHERE b > 1 SEVERITY minor")
        assert first == second

    def test_a_repeated_modifier_is_refused(self) -> None:
        # Two SEVERITY clauses leave it ambiguous which was meant, and silently
        # taking the last is how a critical control becomes an informational one.
        with pytest.raises(PqlSyntaxError) as caught:
            one("CHECK p.a IS NOT NULL SEVERITY minor SEVERITY critical")
        assert "twice" in str(caught.value)

    def test_severity_and_dimension_are_checked_against_the_catalogue(self) -> None:
        with pytest.raises(PqlSyntaxError) as caught:
            one("CHECK p.a IS NOT NULL SEVERITY urgent")
        assert "critical" in caught.value.remedy

    def test_a_segmentation_keeps_a_finding_from_being_averaged_away(self) -> None:
        control = one("CHECK p.lei IS NOT NULL FOR EACH entity HAVING COUNT(*) > 100")
        assert control.segmentation is not None
        assert [c.name for c in control.segmentation.columns] == ["entity"]
        assert control.segmentation.having is not None

    def test_thresholds_carry_their_unit(self) -> None:
        assert one("CHECK p.a IS NOT NULL BELOW 0.1%").threshold.unit == "rate"
        assert one("CHECK p.a IS NOT NULL AT MOST 5 ROWS").threshold.value == 5
        assert one("CHECK p.a IS NOT NULL WITHIN 1.00 EUR").threshold.currency == "EUR"

    def test_the_default_threshold_allows_no_violations(self) -> None:
        # The only honest default: a declared unique key that tolerated
        # duplicates was not a key.
        assert one("CHECK p HAS UNIQUE KEY (a)").threshold.is_strict


class TestUnknownsAreViolationsByDefault:
    """The inversion of the SQL default, and the reason for it."""

    def test_an_unknown_counts_against_the_control(self) -> None:
        # A rule over a column that is entirely null passes under SQL's default,
        # silently, for years. That is the single most reliable source of false
        # confidence in production data quality suites.
        assert one("CHECK p.a IS NOT NULL").unknown_policy is ast.UnknownPolicy.VIOLATION

    def test_the_sql_behaviour_can_be_restored_deliberately(self) -> None:
        control = one("CHECK p.a IS NOT NULL TREAT UNKNOWN AS PASS BECAUSE 'break workflow'")
        assert control.unknown_policy is ast.UnknownPolicy.PASS

    def test_but_only_with_a_reason(self) -> None:
        # Ignoring unknowns is a decision somebody has to own.
        with pytest.raises(PqlSyntaxError) as caught:
            one("CHECK p.a IS NOT NULL TREAT UNKNOWN AS PASS")
        assert "needs a BECAUSE" in str(caught.value)


class TestDeterminism:
    def test_reading_the_clock_is_refused_at_authoring_time(self) -> None:
        # A control whose verdict depends on when it ran cannot be replayed,
        # and evidence that cannot be replayed is an assertion, not a finding.
        with pytest.raises(PqlSyntaxError) as caught:
            one("CHECK p SATISFIES booked_at < CURRENT_TIMESTAMP()")
        assert "$business_date" in caught.value.remedy

    def test_randomness_is_refused_too(self) -> None:
        with pytest.raises(PqlSyntaxError):
            one("CHECK p SATISFIES RANDOM() > 0.5")

    def test_the_run_supplies_the_date_instead(self) -> None:
        control = one("CHECK p SATISFIES as_of_date = $business_date")
        assert isinstance(control.assertion, ast.ExpressionAssertion)


class TestPrecedence:
    def test_not_binds_looser_than_a_comparison(self) -> None:
        # NOT side = 'BUY' means NOT (side = 'BUY'), as in SQL. Parsed the other
        # way it becomes (NOT side) = 'BUY' — a different control, and a
        # valid-looking one.
        condition = one("CHECK p SATISFIES NOT side = 'BUY'").assertion.condition  # type: ignore[attr-defined]
        assert isinstance(condition, ast.UnaryOp)
        assert isinstance(condition.operand, ast.BinaryOp)

    def test_and_binds_tighter_than_or(self) -> None:
        condition = one("CHECK p SATISFIES a OR b AND c").assertion.condition  # type: ignore[attr-defined]
        assert condition.operator == "OR"
        assert condition.right.operator == "AND"

    def test_between_does_not_swallow_its_own_and(self) -> None:
        # Parsed at full precedence, BETWEEN 1 AND 100 reads as BETWEEN
        # (1 AND 100) and the rest of the control disappears.
        control = one("CHECK p.qty BETWEEN 1 AND 100 AT MOST 5 ROWS")
        assert control.threshold.value == 5

    def test_predicates_work_inside_a_where_clause(self) -> None:
        # A filter that could not say IN would send people to a raw-SQL escape
        # hatch, which is what the language exists to avoid.
        control = one("CHECK p HAS ROW COUNT AT LEAST 1 WHERE ccy IN ('GBP','USD')")
        assert control.where is not None


class TestRoundTrip:
    """A formatter whose output means something else is worse than none."""

    CASES = (
        "CHECK p.a IS NOT NULL",
        "CHECK p SATISFIES NOT (side = 'BUY' AND quantity < 0)",
        "CHECK p SATISFIES NOT side = 'BUY' AND quantity < 0",
        "CHECK p SATISFIES (a + b) * c > 10",
        "CHECK p SATISFIES a - (b - c) = 0",
        "CHECK p SATISFIES a / (b / c) = 1",
        "CHECK p SATISFIES NOT (a OR b) AND c",
        "CHECK p.qty BETWEEN 1 AND 100 AT MOST 5 ROWS",
        "CHECK p HAS UNIQUE KEY (a, b) SEVERITY critical DIMENSION uniqueness",
        "CHECK p.account_id REFERENCES accounts.account_id",
        "CHECK p IS FRESH WITHIN 30 MINUTES OF '06:30' CALENDAR 'TARGET2'",
        "CHECK p HAS ROW COUNT BETWEEN 1 AND 2 WHERE s = 'A' AND r IN ('X','Y')",
        "CHECK p.lei IS NOT NULL FOR EACH entity HAVING COUNT(*) > 100 BELOW 0.1%",
        "CHECK p.a IS NOT NULL EVIDENCE full ON FAIL block OWNER 'risk' BECAUSE 'why'",
        "CHECK p.name HAS LENGTH BETWEEN 1 AND 40",
        "CHECK p.isin MATCHES /^[A-Z]{2}[0-9A-Z]{9}[0-9]$/",
        "CHECK p.a IS NOT NULL TREAT UNKNOWN AS PASS BECAUSE 'owned'",
    )

    @pytest.mark.parametrize("source", CASES)
    def test_rendering_and_reparsing_preserves_meaning(self, source: str) -> None:
        # Compared as trees, not as text. Comparing rendered strings would have
        # missed NOT (a AND b) rendering without its brackets: the text was
        # stable and the meaning was not.
        control = parse_control(source)
        assert parse_control(control.render()) == control

    @pytest.mark.parametrize("source", CASES)
    def test_rendering_is_stable(self, source: str) -> None:
        once = parse_control(source).render()
        assert parse_control(once).render() == once

    def test_every_control_renders_a_description(self) -> None:
        for source in self.CASES:
            described = parse_control(source).describe()
            assert described.endswith((".", "'")) and len(described) > 20


class TestSuites:
    def test_a_suite_groups_controls(self) -> None:
        program = parse("SUITE core {\n  CHECK p.a IS NOT NULL\n  CHECK p HAS UNIQUE KEY (a)\n}")
        assert len(program.suites) == 1
        assert len(program.all_controls) == 2

    def test_an_unclosed_suite_says_so(self) -> None:
        with pytest.raises(PqlSyntaxError) as caught:
            parse("SUITE core { CHECK p.a IS NOT NULL")
        assert "never closed" in str(caught.value)

    def test_a_suite_round_trips(self) -> None:
        source = "SUITE core {\n  CHECK p.a IS NOT NULL\n  CHECK p HAS UNIQUE KEY (a)\n}"
        program = parse(source)
        assert parse(program.render()) == program


class TestErrorsPointAtTheProblem:
    def test_a_missing_assertion_lists_what_is_possible(self) -> None:
        with pytest.raises(PqlSyntaxError) as caught:
            one("CHECK positions")
        assert "IS NOT NULL" in caught.value.remedy

    def test_a_dataset_level_check_written_as_a_column_one_is_explained(self) -> None:
        with pytest.raises(PqlSyntaxError) as caught:
            one("CHECK positions IS NOT NULL")
        assert "HAS ROW COUNT" in caught.value.remedy

    def test_a_column_named_like_a_keyword_is_accepted(self) -> None:
        # Real banking columns are called source, severity and on.
        assert one("CHECK p.source IS NOT NULL").assertion.subject.name == "source"  # type: ignore[attr-defined]

    def test_the_caret_lands_on_the_offending_word(self) -> None:
        with pytest.raises(PqlSyntaxError) as caught:
            one("CHECK p.a IS NOT NULL SEVERITY urgent")
        rendered = caught.value.render()
        caret = next(line for line in rendered.splitlines() if line.strip().startswith("^"))
        source = next(line for line in rendered.splitlines() if "SEVERITY" in line)
        assert source.index("urgent") == caret.index("^")
