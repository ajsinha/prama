"""Finding the controls that are not doing anything.

A control estate rots quietly: nothing breaks, the suite stays green, and
confidence in it falls until people stop reading the alerts.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.pql.errors import PqlSyntaxError
from prama.pql.lint import Linter, lint
from prama.pql.parser import parse, parse_control


def findings(*sources: str) -> list:
    return lint([parse_control(s) for s in sources])


def rules(*sources: str) -> set[str]:
    return {f.rule for f in findings(*sources)}


class TestControlsThatCannotFire:
    def test_a_hundred_percent_threshold_can_never_be_exceeded(self) -> None:
        # Worse than no control: it appears on the coverage report and covers
        # nothing.
        found = findings("CHECK p.a IS NOT NULL BELOW 100% BECAUSE 'x'")
        assert [f.rule for f in found] == ["never-fires"]
        assert found[0].severity == "error"

    def test_at_least_zero_rows_asserts_nothing(self) -> None:
        assert "never-fires" in rules("CHECK p HAS ROW COUNT AT LEAST 0 BECAUSE 'x'")

    def test_a_realistic_threshold_is_left_alone(self) -> None:
        assert "never-fires" not in rules("CHECK p.a IS NOT NULL BELOW 1% BECAUSE 'x'")


class TestControlsThatAlwaysFire:
    def test_reversed_bounds_are_caught(self) -> None:
        found = findings("CHECK p.qty BETWEEN 100 AND 1 BECAUSE 'x'")
        assert [f.rule for f in found] == ["always-fires"]
        assert "wrong way round" in found[0].remedy

    def test_a_reversed_row_count_range_is_caught(self) -> None:
        assert "always-fires" in rules("CHECK p HAS ROW COUNT BETWEEN 1000 AND 10 BECAUSE 'x'")

    def test_an_empty_set_is_a_syntax_error_not_a_lint_finding(self) -> None:
        # It fails every row, so it is a mistake rather than a style — and the
        # caret can point at the brackets while somebody is still typing.
        with pytest.raises(PqlSyntaxError) as caught:
            parse_control("CHECK p.status IN ()")
        assert "IS NULL" in caught.value.remedy


class TestDuplicates:
    def test_an_exact_duplicate_is_found(self) -> None:
        found = findings(
            "CHECK p.a IS NOT NULL BECAUSE 'one'",
            "CHECK p.a IS NOT NULL BECAUSE 'the other'",
        )
        assert [f.rule for f in found] == ["duplicate"]
        assert found[0].related

    def test_duplicates_are_found_by_meaning_not_by_text(self) -> None:
        # Content addressing makes this exact: a suite copied and its clauses
        # reordered is still the same control.
        found = findings(
            "CHECK p.a IS NOT NULL SEVERITY minor WHERE b > 1 BECAUSE 'one'",
            "CHECK p.a IS NOT NULL BECAUSE 'two' WHERE b > 1 SEVERITY critical",
        )
        assert [f.rule for f in found] == ["duplicate"]

    def test_two_genuinely_different_controls_are_not_duplicates(self) -> None:
        assert "duplicate" not in rules(
            "CHECK p.a IS NOT NULL BECAUSE 'x'",
            "CHECK p.b IS NOT NULL BECAUSE 'y'",
        )


class TestSubsumption:
    def test_a_null_check_beside_a_range_check_adds_nothing(self) -> None:
        # The non-obvious one, and a direct consequence of the language's
        # central decision: an unknown counts as a violation, so the range
        # check already fails on a null.
        found = findings(
            "CHECK p.notional BETWEEN 0 AND 1000 BECAUSE 'range'",
            "CHECK p.notional IS NOT NULL BECAUSE 'CDE'",
        )
        assert [f.rule for f in found] == ["subsumed"]
        assert "unknown counts as a violation" in found[0].message

    def test_but_not_when_the_unknown_policy_was_changed(self) -> None:
        # With TREAT UNKNOWN AS PASS the range check no longer catches nulls,
        # so the null check is doing real work.
        assert "subsumed" not in rules(
            "CHECK p.notional BETWEEN 0 AND 1000 BECAUSE 'range'",
            "CHECK p.notional IS NOT NULL TREAT UNKNOWN AS PASS BECAUSE 'declared'",
        )

    def test_a_narrower_set_subsumes_a_wider_one(self) -> None:
        found = findings(
            "CHECK p.ccy IN ('GBP','USD') BECAUSE 'traded'",
            "CHECK p.ccy IN ('GBP','USD','EUR') BECAUSE 'permitted'",
        )
        assert [f.rule for f in found] == ["subsumed"]

    def test_identical_sets_are_a_duplicate_not_a_subsumption(self) -> None:
        assert rules(
            "CHECK p.ccy IN ('GBP','USD') BECAUSE 'a'",
            "CHECK p.ccy IN ('GBP','USD') BECAUSE 'b'",
        ) == {"duplicate"}

    def test_different_scopes_are_not_compared(self) -> None:
        # Deciding this needs reasoning about the filters, which is where a
        # solver would be required and a wrong answer would be expensive.
        assert "subsumed" not in rules(
            "CHECK p.notional BETWEEN 0 AND 1000 WHERE status = 'A' BECAUSE 'x'",
            "CHECK p.notional IS NOT NULL BECAUSE 'y'",
        )

    def test_a_tolerance_stops_the_inference(self) -> None:
        # A stricter predicate under a looser tolerance implies nothing.
        assert "subsumed" not in rules(
            "CHECK p.notional BETWEEN 0 AND 1000 BELOW 5% BECAUSE 'x'",
            "CHECK p.notional IS NOT NULL BECAUSE 'y'",
        )

    def test_different_columns_are_never_subsumed(self) -> None:
        assert "subsumed" not in rules(
            "CHECK p.a BETWEEN 0 AND 1 BECAUSE 'x'",
            "CHECK p.b IS NOT NULL BECAUSE 'y'",
        )


class TestJustification:
    def test_a_control_with_no_reason_is_noted(self) -> None:
        found = findings("CHECK p.a IS NOT NULL")
        assert [f.rule for f in found] == ["no-justification"]
        assert found[0].severity == "info"

    def test_a_justified_control_says_nothing(self) -> None:
        assert findings("CHECK p.a IS NOT NULL BECAUSE 'CDE for FRTB'") == []


class TestASuiteThatHasRotted:
    SUITE = """
    SUITE positions_core {
      CHECK positions.notional IS NOT NULL BECAUSE 'CDE'
      CHECK positions.notional BETWEEN 0 AND 1000000 BECAUSE 'plausible range'
      CHECK positions.ccy IN ('GBP','USD') BECAUSE 'traded currencies'
      CHECK positions.ccy IN ('GBP','USD','EUR','JPY') BECAUSE 'permitted'
      CHECK positions.isin IS NOT NULL BELOW 100% BECAUSE 'nice to have'
      CHECK positions HAS ROW COUNT BETWEEN 1000 AND 10 BECAUSE 'volume'
      CHECK positions.account_id IS NOT NULL BECAUSE 'key part'
      CHECK positions.account_id IS NOT NULL BECAUSE 'copied'
      CHECK positions.settled IS NOT NULL
    }
    """

    def test_every_kind_of_rot_is_found_at_once(self) -> None:
        found = Linter().check_all(list(parse(self.SUITE).all_controls))
        assert {f.rule for f in found} == {
            "never-fires",
            "always-fires",
            "duplicate",
            "subsumed",
            "no-justification",
        }

    def test_every_finding_names_a_control(self) -> None:
        for finding in Linter().check_all(list(parse(self.SUITE).all_controls)):
            assert finding.control.startswith("CHECK ")

    def test_findings_that_involve_two_controls_name_both(self) -> None:
        # "This is redundant" is not actionable. "This is already covered by
        # the control on line 12" is.
        found = Linter().check_all(list(parse(self.SUITE).all_controls))
        for finding in found:
            if finding.rule in ("duplicate", "subsumed"):
                assert finding.related.startswith("CHECK ")

    def test_a_healthy_suite_produces_nothing(self) -> None:
        healthy = """
        SUITE clean {
          CHECK positions.notional BETWEEN 0 AND 1000000 BECAUSE 'plausible'
          CHECK positions.ccy IN ('GBP','USD') BECAUSE 'traded'
          CHECK positions HAS UNIQUE KEY (account_id, as_of_date) BECAUSE 'grain'
          CHECK positions HAS ROW COUNT BETWEEN 100 AND 100000 BECAUSE 'volume'
        }
        """
        assert Linter().check_all(list(parse(healthy).all_controls)) == []
