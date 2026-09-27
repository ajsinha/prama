"""No new regression test proves only an absence.

QA round 4's second-largest cluster was checks that pass because they reach
nothing (`Q-109`: a fixture that typed every column `unknown`; `Q-98`: a set
of one answer counted as unanimous). A regression whose only assertions are
"empty", "none", "false" or "not" passes just as well against code that does
nothing at all, unless something in the same test shows the check can see a
non-empty case.

A ratchet, deliberately. The 33 existing tests of that shape are
listed in `BASELINE` to be reviewed, not waved through. A new one fails the
build until it asserts something positive too: the control the working
method in `qa/HANDOVER.md` already asks for. Scoped to `qa/regression-suite`
because a lint that fired on every unit test would be switched off (`Q-114`).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import ast
from pathlib import Path

SUITE = Path(__file__).resolve().parents[2] / "qa" / "regression-suite"

#: Existing absence-only regressions, awaiting review. Remove an entry when its
#: test gains a positive control; never add one.
BASELINE: frozenset[str] = frozenset(
    {
        "data/test_one_bad_input_does_not_stop_the_work.py::test_a_recognised_scheme_is_not_refused_before_it_is_tried",
        "domain/test_empty_is_not_agreement.py::test_the_rate_is_unknown_rather_than_perfect",
        "domain/test_empty_is_not_agreement.py::test_the_json_keeps_the_distinction",
        "domain/test_empty_is_not_agreement.py::test_no_legs_gives_no_answer",
        "domain/test_empty_is_not_agreement.py::test_an_empty_publish_is_not_complete",
        "domain/test_empty_is_not_agreement.py::test_a_partial_publish_is_still_incomplete",
        "domain/test_lineage_and_dates.py::test_no_entry_day_gives_no_entry_date",
        "domain/test_shipped_templates_resolve.py::test_every_function_a_template_names_is_registered",
        "domain/test_shipped_templates_resolve.py::test_every_template_compiles_once_its_placeholders_are_filled",
        "domain/test_thresholds_and_purity.py::test_a_strict_rate_is_refused_rather_than_widened",
        "domain/test_thresholds_and_purity.py::test_an_ordinary_regex_is_not_refused",
        "domain/test_tolerance_is_decimal.py::test_a_difference_exactly_on_the_relative_allowance_is_not_a_break",
        "domain/test_tolerance_is_decimal.py::test_the_ordinary_case_is_still_not_a_break",
        "interfaces/test_operations_screens_declare_their_subject.py::test_no_operations_screen_still_falls_back_to_the_declaration_default",
        "language/test_a_length_check_is_about_length.py::test_a_length_check_on_a_text_column_is_clean",
        "language/test_a_length_check_is_about_length.py::test_the_other_exemptions_are_untouched",
        "language/test_a_money_literal_stays_a_number.py::test_the_ordering_it_was_getting_wrong",
        "language/test_a_selector_says_when_it_cannot_answer.py::test_a_selector_that_genuinely_matches_nothing_is_still_allowed",
        "language/test_conformance_needs_two_answers.py::test_a_run_nobody_compared_is_not_conforming",
        "language/test_nothing_to_report.py::test_a_pass_over_no_messages_reports_no_rate",
        "language/test_precedence_and_binding_agree.py::test_every_operator_the_parser_reads_can_be_rendered",
        "language/test_syntax_that_can_run.py::test_a_one_argument_min_is_the_aggregate",
        "language/test_syntax_that_can_run.py::test_a_one_argument_max_is_the_aggregate",
        "language/test_syntax_that_can_run.py::test_the_two_argument_scalar_still_works",
        "language/test_the_package_exports_what_it_lists.py::test_every_name_prama_pql_advertises_resolves",
        "language/test_the_package_exports_what_it_lists.py::test_no_module_advertises_a_name_it_does_not_have",
        "platform/test_plugins_disabled_in_the_cli.py::test_packs_are_not_installed_before_the_configuration_is_known",
        "trust/test_bundle_range_matches_payload.py::test_a_manifest_claiming_a_narrower_range_is_also_refused",
        "trust/test_bundle_verification.py::test_an_edited_manifest_is_not_intact",
        "trust/test_bundle_verification.py::test_a_manifest_that_claims_a_signature_must_be_given_one",
        "trust/test_ledger_concurrency.py::test_the_chain_those_writers_produced_still_verifies",
        "trust/test_windowed_chain.py::test_the_whole_chain_verifies",
        "trust/test_windowed_chain.py::test_a_window_of_it_also_verifies",
    }
)


def _absence(test: ast.expr) -> bool:
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        return True
    if isinstance(test, ast.Compare) and len(test.ops) == 1:
        right = test.comparators[0]
        if isinstance(test.ops[0], ast.Eq | ast.Is):
            if isinstance(right, ast.List | ast.Tuple | ast.Set) and not right.elts:
                return True
            if isinstance(right, ast.Dict) and not right.keys:
                return True
            if isinstance(right, ast.Constant) and right.value in (None, 0, "", False):
                return True
    return False


def absence_only(source: str) -> list[str]:
    """Test functions in *source* whose every assertion is an absence."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith(
            "test"
        ):
            asserts = [n for n in ast.walk(node) if isinstance(n, ast.Assert)]
            raises = any(isinstance(n, ast.With | ast.AsyncWith) for n in ast.walk(node))
            if asserts and not raises and all(_absence(a.test) for a in asserts):
                found.append(node.name)
    return found


def test_no_new_regression_proves_only_an_absence() -> None:
    found = {
        f"{path.relative_to(SUITE)}::{name}"
        for path in sorted(SUITE.rglob("test_*.py"))
        for name in absence_only(path.read_text(encoding="utf-8"))
    }
    new = sorted(found - BASELINE)
    assert not new, (
        f"these regressions assert only that something is empty or false: {new}. "
        "Add an assertion that the same check sees a non-empty case, so the test "
        "cannot pass against code that does nothing."
    )
    stale = sorted(BASELINE - found)
    assert not stale, f"these baseline entries were fixed or removed; delete them: {stale}"


def test_the_lint_can_fail() -> None:
    """The counterfactual, and the control."""
    assert absence_only("def test_x():\n    assert found == []\n") == ["test_x"]
    assert absence_only("def test_x():\n    assert thing\n    assert found == []\n") == []
