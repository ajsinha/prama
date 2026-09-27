"""Catching a control's mistakes while somebody is still looking at it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.pql.errors import PqlTypeError
from prama.pql.parser import parse_control
from prama.pql.types import Catalogue, TypeChecker

POSITIONS = Catalogue.of(
    positions={
        "account_id": "varchar(20)",
        "instrument_id": "varchar(20)",
        "notional_amount": "numeric(18,2)",
        "as_of_date": "date",
        "trade_status": "varchar(10)",
        "isin": "varchar(12)",
        "is_cleared": "boolean",
    },
    accounts={"account_id": "varchar(20)", "legal_entity_id": "varchar(20)"},
)


def check(source: str, catalogue: Catalogue = POSITIONS) -> list:
    return TypeChecker(catalogue).check(parse_control(source), source=source)


def errors(source: str) -> list:
    return [f for f in check(source) if f.level == "error"]


class TestResolution:
    def test_a_correct_control_has_nothing_to_say(self) -> None:
        assert check("CHECK positions.notional_amount IS NOT NULL") == []

    def test_a_typo_is_caught_before_the_control_ever_runs(self) -> None:
        # Otherwise this is a driver error at three in the morning, against a
        # production warehouse, in a message written for a database engineer.
        found = errors("CHECK positions.notional_amt IS NOT NULL")
        assert len(found) == 1
        assert "no column called notional_amt" in found[0].message

    def test_a_near_miss_gets_a_suggestion(self) -> None:
        assert (
            "Did you mean notional_amount?"
            in errors("CHECK positions.notional_amt IS NOT NULL")[0].remedy
        )

    def test_a_wild_guess_gets_the_column_list_instead(self) -> None:
        remedy = errors("CHECK positions.zzzz IS NOT NULL")[0].remedy
        assert "Columns available" in remedy
        assert "account_id" in remedy

    def test_columns_are_matched_without_regard_to_case(self) -> None:
        # Warehouses fold case differently and a control should not care.
        assert errors("CHECK positions.NOTIONAL_AMOUNT IS NOT NULL") == []

    def test_every_clause_is_resolved_not_only_the_subject(self) -> None:
        assert len(errors("CHECK positions.notional_amount IS NOT NULL WHERE stat = 'A'")) == 1
        assert len(errors("CHECK positions.isin IS NOT NULL FOR EACH entty")) == 1
        assert len(errors("CHECK positions HAS UNIQUE KEY (account_id, instrment_id)")) == 1

    def test_a_column_of_another_dataset_is_questioned(self) -> None:
        # It may be a join nobody declared. Guessing which would be worse than
        # asking.
        found = errors("CHECK positions.notional_amount IS NOT NULL WHERE accounts.x = 1")
        assert any("belongs to accounts" in f.message for f in found)

    def test_all_the_mistakes_are_reported_at_once(self) -> None:
        # Stopping at the first would make somebody fix a control one mistake
        # per attempt, which is the slowest possible way to write anything.
        assert len(errors("CHECK positions HAS UNIQUE KEY (acount_id, instrment_id)")) == 2


class TestTyping:
    def test_a_number_compared_with_text_is_refused(self) -> None:
        # Engines differ on whether they coerce silently, so this control would
        # mean one thing on one database and something else on another.
        found = errors("CHECK positions.notional_amount > 'ACTIVE'")
        assert len(found) == 1
        assert "coerce" in found[0].remedy

    def test_the_same_check_applies_inside_a_where_clause(self) -> None:
        assert len(errors("CHECK positions.isin IS NOT NULL WHERE trade_status = 42")) == 1

    def test_a_date_may_be_compared_with_an_iso_literal(self) -> None:
        # The one cross-family comparison every engine agrees about.
        assert errors("CHECK positions.as_of_date > '2026-01-01'") == []

    def test_a_pattern_needs_text(self) -> None:
        found = errors("CHECK positions.notional_amount MATCHES /^[0-9]+$/")
        assert "pattern cannot be matched against a number" in found[0].message

    def test_a_pattern_on_text_is_fine(self) -> None:
        assert errors("CHECK positions.isin MATCHES /^[A-Z]{2}/") == []

    def test_a_run_parameter_is_not_second_guessed(self) -> None:
        # Its type is not knowable here, and guessing produces errors on
        # correct controls.
        assert errors("CHECK positions.as_of_date = $business_date") == []

    def test_a_set_is_checked_member_by_member(self) -> None:
        assert errors("CHECK positions.trade_status IN ('A', 'B')") == []
        assert len(errors("CHECK positions.trade_status IN ('A', 3)")) == 1

    def test_a_named_thing_is_not_treated_as_a_value(self) -> None:
        # IN CODELIST iso4217 names a list, not a string to compare against.
        assert errors("CHECK positions.trade_status IN CODELIST iso4217") == []
        assert errors("CHECK positions.isin IS VALID ISIN") == []

    def test_an_unrecognised_source_type_suppresses_type_errors(self) -> None:
        # A wrong type error is worse than none: it makes people distrust the
        # checker and then ignore the real ones.
        exotic = Catalogue.of(t={"weird": "geography(point,4326)"})
        assert errors_for("CHECK t.weird > 5", exotic) == []


def errors_for(source: str, catalogue: Catalogue) -> list:
    return [f for f in check(source, catalogue) if f.level == "error"]


class TestUnknownSchemas:
    def test_an_undeclared_dataset_is_not_an_error(self) -> None:
        # Prama is often pointed at something before anyone has declared it.
        # Refusing to check the control at all would be less useful than
        # checking what can be checked.
        findings = check("CHECK mystery.x IS NOT NULL")
        assert [f.level for f in findings] == ["unchecked"]

    def test_but_it_is_recorded_as_unchecked(self) -> None:
        # So nobody later mistakes an unchecked control for a checked one.
        finding = check("CHECK mystery.x IS NOT NULL")[0]
        assert "cannot be verified" in finding.remedy


class TestTheStrictPath:
    def test_require_raises_on_the_first_error(self) -> None:
        with pytest.raises(PqlTypeError) as caught:
            TypeChecker(POSITIONS).require(
                parse_control("CHECK positions.nope IS NOT NULL"), source="x"
            )
        assert "no column called nope" in str(caught.value)

    def test_require_is_silent_on_a_correct_control(self) -> None:
        TypeChecker(POSITIONS).require(parse_control("CHECK positions.isin IS NOT NULL"))

    def test_require_does_not_raise_on_an_unknown_dataset(self) -> None:
        TypeChecker(POSITIONS).require(parse_control("CHECK mystery.x IS NOT NULL"))

    def test_the_error_points_at_the_column(self) -> None:
        source = "CHECK positions.nope IS NOT NULL"
        with pytest.raises(PqlTypeError) as caught:
            TypeChecker(POSITIONS).require(parse_control(source), source=source)
        rendered = caught.value.render()
        caret = next(line for line in rendered.splitlines() if line.strip().startswith("^"))
        text = next(line for line in rendered.splitlines() if "CHECK positions" in line)
        assert text.index("nope") == caret.index("^")


class TestEveryExpressionLocationIsChecked:
    """QA C23 (`PQL-241`, `PQL-242`): type checking covered `WHERE` only, and
    function checking missed `HAVING`. Both now derive from one list of the
    places a condition can appear."""

    def test_a_satisfies_condition_is_type_checked(self) -> None:
        # The surface an Excel formula lands on.
        assert errors("CHECK positions SATISFIES notional_amount > 'ACTIVE'")

    def test_the_same_mistake_in_where_is_still_caught(self) -> None:
        # The control: the path that always worked still works.
        assert errors("CHECK positions.isin IS NOT NULL WHERE notional_amount > 'ACTIVE'")

    def test_a_correct_satisfies_says_nothing(self) -> None:
        assert errors("CHECK positions SATISFIES notional_amount > 0") == []

    def test_an_unknown_function_in_having_is_named(self) -> None:
        found = check(
            "CHECK positions.isin IS NOT NULL FOR EACH account_id HAVING NONSENSE(isin) > 1"
        )
        assert any("NONSENSE" in f.message for f in found)
