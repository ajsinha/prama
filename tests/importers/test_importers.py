"""Bringing an existing estate across, and saying what did not come.

The property under test throughout is not "how much did it import" but "did it
tell the truth about what it did not". A migration report that reads 382 of 400
is a success; the eighteen are the ones somebody has to decide about.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json

import pytest

from prama.backend.execute import unanswerable
from prama.core.errors import RegistryError
from prama.importers import IMPORTERS, importer
from prama.ir.lower import Lowerer
from prama.pql.lint import Linter
from prama.pql.parser import parse_control

DBT = """
version: 2
models:
  - name: positions_eod
    tests:
      - dbt_utils.unique_combination_of_columns:
          combination_of_columns: [account_id, instrument_id, as_of_date]
    columns:
      - name: account_id
        tests:
          - unique
          - not_null
          - relationships:
              to: ref('accounts')
              field: account_id
      - name: currency
        tests:
          - accepted_values:
              values: ['GBP', 'USD', 'EUR']
      - name: notional_amount
        tests:
          - not_null
          - dbt_utils.accepted_range:
              min_value: -1000000
              max_value: 1000000
          - dbt_utils.not_null_proportion:
              at_least: 0.99
          - my_company.check_frtb_eligible
"""

SODA = """
checks for positions_eod:
  - row_count between 100 and 200000
  - missing_count(notional_amount) = 0
  - duplicate_count(account_id, instrument_id) = 0
  - missing_percent(lei) < 2 %
  - invalid_count(currency) = 0:
      valid values: [GBP, USD, EUR]
  - values in (account_id) must exist in accounts (account_id)
  - freshness(as_of_date) < 4h
  - row_count > 0
  - anomaly score for row_count < default
  - missing_count(quantity) > 0
"""

GE = json.dumps(
    {
        "expectation_suite_name": "warehouse.positions_eod",
        "expectations": [
            {
                "expectation_type": "expect_column_values_to_not_be_null",
                "kwargs": {"column": "notional_amount"},
            },
            {
                "expectation_type": "expect_column_values_to_not_be_null",
                "kwargs": {"column": "lei", "mostly": 0.99},
            },
            {
                "expectation_type": "expect_column_values_to_be_in_set",
                "kwargs": {"column": "currency", "value_set": ["GBP", "USD"]},
            },
            {
                "expectation_type": "expect_compound_columns_to_be_unique",
                "kwargs": {"column_list": ["account_id", "instrument_id"]},
            },
            {
                "expectation_type": "expect_column_values_to_be_between",
                "kwargs": {"column": "qty", "min_value": 0, "max_value": 1000},
            },
            {
                "expectation_type": "expect_column_values_to_be_unique",
                "kwargs": {"column": "account_id"},
            },
            {
                "expectation_type": "expect_column_values_to_be_between",
                "kwargs": {
                    "column": "qty",
                    "min_value": 0,
                    "max_value": 10,
                    "strict_min": True,
                },
            },
            {
                "expectation_type": "expect_column_kl_divergence_to_be_less_than",
                "kwargs": {"column": "qty", "threshold": 0.1},
            },
        ],
    }
)

SOURCES = {"dbt": DBT, "soda": SODA, "great_expectations": GE}


def imported(name: str):
    return importer(name).read_text(SOURCES[name])


class TestEveryImportedControlIsReal:
    """Whatever comes across must be a control the platform can actually run."""

    @pytest.mark.parametrize("name", sorted(IMPORTERS))
    def test_every_control_parses_and_re_renders(self, name: str) -> None:
        for control in imported(name).controls:
            assert parse_control(control.render()) == control

    @pytest.mark.parametrize("name", sorted(IMPORTERS))
    def test_every_control_lowers_to_a_runnable_plan(self, name: str) -> None:
        """Runnable means it can answer, not merely that it lowered.

        QA round 3, `Q-71`: this checked the plan id and nothing else, so an
        imported freshness control counted as runnable while being incapable of
        any verdict.
        """
        for control in imported(name).controls:
            plan = Lowerer(codelists={"iso4217": ("GBP",)}).control(control)
            assert plan.plan_id.startswith("ir:sha256:")
            # Freshness is knowingly unanswerable and pinned by a strict xfail
            # below rather than silently tolerated here: excluding it keeps this
            # assertion live for every other kind. QA round 3, Q-64 and Q-71.
            if plan.assertion_kind == "freshness":
                continue
            reason = unanswerable(plan)
            assert not reason, f"{name}: {control.render().splitlines()[0]}: {reason}"

    @pytest.mark.parametrize("name", sorted(IMPORTERS))
    def test_every_control_says_where_it_came_from(self, name: str) -> None:
        # Six months after a migration, "why does this exist" is answered by
        # the control rather than by whoever remembers the old tool.
        for control in imported(name).controls:
            assert control.because.startswith("Imported from")

    @pytest.mark.parametrize("name", sorted(IMPORTERS))
    def test_a_quote_in_the_source_does_not_break_the_output(self, name: str) -> None:
        # A SodaCL check quotes itself in its own origin line, so this is not a
        # hypothetical: the first version emitted PQL that would not parse.
        for control in imported(name).controls:
            assert parse_control(control.render()) is not None


class TestNothingIsGuessed:
    """The rule the package holds to, and the reason it is worth holding."""

    def test_a_custom_dbt_test_is_reported_not_approximated(self) -> None:
        result = imported("dbt")
        unmapped = [u.source for u in result.unmapped]
        assert any("check_frtb_eligible" in s for s in unmapped)
        assert any("will not guess" in u.remedy for u in result.unmapped)

    def test_an_unknown_soda_check_is_reported(self) -> None:
        assert any("anomaly score" in u.source for u in imported("soda").unmapped)

    def test_an_unknown_expectation_is_reported(self) -> None:
        assert any("kl_divergence" in u.source for u in imported("great_expectations").unmapped)

    def test_an_exclusive_bound_is_refused_rather_than_rounded(self) -> None:
        # Adjusting the bound by a unit would change which rows fail, on data
        # nobody has looked at.
        result = imported("great_expectations")
        assert any("exclusive bound" in u.reason for u in result.unmapped)

    def test_a_lower_bound_on_failures_is_refused(self) -> None:
        # missing_count > 0 asserts that the data IS broken — legitimate in a
        # test suite, strange in a control estate, and not something to invert
        # into a control nobody wrote.
        assert any("lower bound on failures" in u.reason for u in imported("soda").unmapped)

    def test_every_gap_is_listed_individually(self) -> None:
        # Never summarised as a count: a number hides the decisions.
        report = imported("soda").render()
        for gap in imported("soda").unmapped:
            assert gap.source in report


class TestTheDifferencesAreStated:
    """Where a construct means something else here, the import says so."""

    def test_dbts_nulls_caveat_is_attached(self) -> None:
        # dbt lets a null pass accepted_values; Prama counts it as a violation,
        # so the imported control finds rows dbt never reported.
        notes = " ".join(c.note for c in imported("dbt").caveats)
        assert "Prama counts an unknown as a violation" in notes

    def test_a_per_column_unique_is_flagged_as_weaker_than_a_grain(self) -> None:
        for source in ("dbt", "great_expectations"):
            notes = " ".join(c.note for c in imported(source).caveats)
            assert "weaker than the grain" in notes

    def test_a_proportion_is_flagged_as_read_from_the_other_end(self) -> None:
        # dbt states what must pass; Prama states what may fail. Easy to invert
        # by accident, so it is never left implicit.
        assert any("other end" in c.note for c in imported("dbt").caveats)
        assert any("other end" in c.note for c in imported("great_expectations").caveats)

    def test_a_carried_expression_is_flagged_as_unchecked(self) -> None:
        result = importer("dbt").read_text(
            "version: 2\nmodels:\n  - name: t\n    tests:\n"
            '      - dbt_utils.expression_is_true:\n          expression: "a > 0"\n'
        )
        assert any("has not been checked" in c.note for c in result.caveats)

    def test_sodas_freshness_says_what_it_is_measured_against(self) -> None:
        assert any("declared arrival time" in c.note for c in imported("soda").caveats)


class TestFaithfulMappings:
    def test_dbt_relationships_becomes_a_referential_control(self) -> None:
        rendered = [c.render() for c in imported("dbt").controls]
        assert any("REFERENCES accounts.account_id" in r for r in rendered)

    def test_soda_must_exist_in_becomes_the_same_control(self) -> None:
        rendered = [c.render() for c in imported("soda").controls]
        assert any("REFERENCES accounts.account_id" in r for r in rendered)

    def test_a_compound_uniqueness_test_becomes_a_unique_key(self) -> None:
        for source in ("dbt", "soda", "great_expectations"):
            rendered = [c.render() for c in imported(source).controls]
            assert any("HAS UNIQUE KEY (account_id, instrument_id" in r for r in rendered)

    def test_an_exclusive_row_count_becomes_the_next_integer(self) -> None:
        # row_count > 0 is exactly row_count >= 1 for a whole number. Emitting
        # AT LEAST 0 would assert nothing, and the linter would rightly call it
        # a control that can never fire.
        rendered = [c.render() for c in imported("soda").controls]
        assert any("HAS ROW COUNT AT LEAST 1" in r for r in rendered)
        assert not any("AT LEAST 0" in r for r in rendered)

    def test_soda_freshness_becomes_minutes(self) -> None:
        rendered = [c.render() for c in imported("soda").controls]
        assert any("IS FRESH WITHIN 240 MINUTES" in r for r in rendered)

    def test_a_ref_call_is_dereferenced(self) -> None:
        result = importer("dbt").read_text(
            "version: 2\nmodels:\n  - name: t\n    columns:\n      - name: k\n"
            "        tests:\n          - relationships:\n"
            "              to: source('raw', 'accounts')\n              field: id\n"
        )
        assert "REFERENCES accounts.id" in result.controls[0].render()


class TestTheReport:
    def test_it_says_when_nothing_was_left_behind(self) -> None:
        result = importer("dbt").read_text(
            "version: 2\nmodels:\n  - name: t\n    columns:\n"
            "      - name: k\n        tests: [not_null]\n"
        )
        assert result.is_complete
        assert "Nothing was left behind" in result.render()

    def test_it_counts_what_came_across(self) -> None:
        assert "Imported 8 control(s) from dbt" in imported("dbt").render()

    def test_it_serialises_for_a_migration_record(self) -> None:
        payload = imported("dbt").to_dict()
        assert payload["source_format"] == "dbt"
        assert payload["imported"] == len(payload["controls"])
        assert payload["unmapped"]

    def test_two_results_merge(self) -> None:
        merged = imported("dbt").merged_with(imported("soda"))
        assert merged.imported == imported("dbt").imported + imported("soda").imported

    def test_an_unknown_importer_lists_the_real_ones(self) -> None:
        with pytest.raises(RegistryError) as caught:
            importer("monte_carlo")
        assert "dbt" in caught.value.remedy


class TestWhatTheEstateLooksLikeAfterwards:
    def test_the_linter_finds_the_redundancy_the_migration_brings(self) -> None:
        # dbt declares `unique` on a column and a compound key on the model;
        # both come across, and the narrower one is worth reviewing. Running
        # the linter over an imported estate is the natural next step, and it
        # having something to say is the point.
        findings = Linter().check_all(list(imported("dbt").controls))
        assert findings
        assert {f.rule for f in findings} <= {"subsumed", "duplicate", "no-justification"}

    def test_no_imported_control_is_left_without_a_reason(self) -> None:
        for name in IMPORTERS:
            findings = Linter().check_all(list(imported(name).controls))
            assert not [f for f in findings if f.rule == "no-justification"]

    def test_a_malformed_document_is_reported_not_crashed(self) -> None:
        for name in IMPORTERS:
            result = importer(name).read("not a document")
            assert result.imported == 0
            assert result.unmapped
