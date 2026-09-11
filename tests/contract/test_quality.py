"""ODCS quality blocks, and the ones that must not become controls.

The value of this importer is almost entirely in what it refuses. A contract
promising eleven checks that imports as eleven controls, four of which check
nothing, is worse than one that imports six and names the other five.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.contract.quality import LIBRARY_RULES, controls_from
from prama.pql import parse_control
from prama.pql.errors import PqlError


def contract(*, dataset_rules=(), column_rules=None) -> dict:
    properties = [
        {"name": name, "quality": list(rules)} for name, rules in (column_rules or {}).items()
    ]
    return {
        "dataProduct": "orders",
        "schema": [{"name": "orders", "quality": list(dataset_rules), "properties": properties}],
    }


def library(rule: str, **block) -> dict:
    return {"type": "library", "rule": rule, **block}


class TestEveryGeneratedControlParses:
    """The guard this module lives or dies by. A catalogue of templates that do
    not parse is a catalogue of promises — the same lesson the regulatory
    catalogue learned."""

    def test_a_representative_contract_yields_only_valid_pql(self) -> None:
        result = controls_from(
            contract(
                dataset_rules=[library("rowCount", mustBeBetween=[100, 10000])],
                column_rules={
                    "order_id": [
                        library("duplicateCount", mustBeLessThan=10),
                        library("nullCount"),
                    ],
                    "currency": [library("validValues", validValues=["GBP", "USD"])],
                    "status": [library("pattern", pattern="^[A-Z]+$")],
                    "rate": [library("nullPercent", mustBeLessOrEqualTo=2)],
                },
            )
        )
        assert result.controls
        for text in result.controls:
            try:
                parse_control(text)
            except PqlError as exc:  # pragma: no cover - a real failure
                pytest.fail(f"does not parse: {exc}\n{text}")

    @pytest.mark.parametrize("rule", LIBRARY_RULES, ids=lambda r: r.name)
    def test_every_mapped_rule_produces_parseable_pql(self, rule) -> None:
        """No exemption list: a rule added without a working lowering fails
        here rather than at somebody's first import."""
        block = library(rule.name)
        block.update(
            {
                "validValues": ["A", "B"],
                "pattern": "^A",
                "mustBeBetween": [1, 10] if rule.name == "rowCount" else None,
                "window": 1,
            }
        )
        block = {k: v for k, v in block.items() if v is not None}
        result = controls_from(contract(column_rules={"c": [block]}))
        assert result.controls, f"{rule.name} produced nothing: {result.refused}"
        parse_control(result.controls[0])


class TestThresholdsAreTheRule:
    def test_less_than_ten_becomes_at_most_nine(self) -> None:
        """`mustBeLessThan: 10` tolerates nine. PQL's AT MOST is inclusive, so
        importing it as ten makes a contract the producer satisfies fail for
        the consumer who imported it."""
        result = controls_from(
            contract(column_rules={"order_id": [library("duplicateCount", mustBeLessThan=10)]})
        )
        assert "AT MOST 9 ROWS" in result.controls[0]

    def test_less_or_equal_keeps_its_number(self) -> None:
        result = controls_from(
            contract(column_rules={"c": [library("nullCount", mustBeLessOrEqualTo=5)]})
        )
        assert "AT MOST 5 ROWS" in result.controls[0]

    def test_no_threshold_means_none_are_acceptable(self) -> None:
        """The strictest reading, and what a contract without a number means."""
        result = controls_from(contract(column_rules={"c": [library("nullCount")]}))
        assert "AT MOST 0 ROWS" in result.controls[0]

    def test_a_percent_rule_uses_a_rate(self) -> None:
        result = controls_from(
            contract(column_rules={"c": [library("nullPercent", mustBeLessOrEqualTo=2)]})
        )
        assert "BELOW 2%" in result.controls[0]

    def test_a_strict_percentage_bound_is_refused(self) -> None:
        """PQL's BELOW is inclusive and a rate has no representable
        predecessor, so importing it would accept a value the contract
        forbids."""
        result = controls_from(
            contract(column_rules={"c": [library("nullPercent", mustBeLessThan=2)]})
        )
        assert not result.controls
        assert "accept a value the contract forbids" in result.refused[0][1]

    def test_a_lower_bound_on_violations_is_refused(self) -> None:
        """It asks for *at least* that many failures, which is not something a
        control can assert."""
        result = controls_from(
            contract(column_rules={"c": [library("nullCount", mustBeGreaterThan=3)]})
        )
        assert not result.controls
        assert "at least" in result.refused[0][1]

    def test_an_exact_count_other_than_zero_is_refused(self) -> None:
        result = controls_from(contract(column_rules={"c": [library("nullCount", mustBe=4)]}))
        assert not result.controls
        assert "exact count" in result.refused[0][1]

    def test_a_non_numeric_threshold_is_refused(self) -> None:
        result = controls_from(
            contract(column_rules={"c": [library("nullCount", mustBeLessThan="a few")]})
        )
        assert not result.controls
        assert "not a number" in result.refused[0][1]


class TestWhatMustNotBecomeAControl:
    def test_a_text_rule_is_refused(self) -> None:
        """Prose with no executable content. A control built from it checks
        nothing while appearing on a coverage report as though it did."""
        result = controls_from(
            contract(dataset_rules=[{"type": "text", "description": "should look sensible"}])
        )
        assert not result.controls
        assert "checks nothing" in result.refused[0][1] or "check nothing" in result.refused[0][1]

    def test_a_sql_rule_is_refused_and_the_query_is_kept(self) -> None:
        """Raw SQL bypasses the IR, so the reference interpreter cannot check
        it and it cannot be replayed. The query is preserved so somebody can
        rewrite it rather than hunt for it."""
        query = "SELECT COUNT(*) FROM orders WHERE total < 0"
        result = controls_from(contract(dataset_rules=[{"type": "sql", "query": query}]))
        assert not result.controls
        assert "bypasses the IR" in result.refused[0][1]
        assert "total < 0" in result.refused[0][1]

    def test_an_unmapped_library_rule_lists_the_mapped_ones(self) -> None:
        result = controls_from(contract(column_rules={"c": [library("sortedness")]}))
        assert not result.controls
        assert "nullCount" in result.refused[0][1]

    def test_a_column_rule_with_no_column_is_refused(self) -> None:
        result = controls_from(contract(dataset_rules=[library("nullCount")]))
        assert not result.controls
        assert "names none" in result.refused[0][1]

    def test_valid_values_without_a_list_is_refused(self) -> None:
        """Nothing is invented: an empty IN () is not a check."""
        result = controls_from(contract(column_rules={"c": [library("validValues")]}))
        assert not result.controls
        assert "carries none" in result.refused[0][1]

    def test_a_pattern_containing_the_delimiter_is_refused(self) -> None:
        """PQL delimits a pattern with slashes, and escaping is a decision
        somebody should make deliberately."""
        result = controls_from(contract(column_rules={"c": [library("pattern", pattern="^a/b$")]}))
        assert not result.controls
        assert "delimiter" in result.refused[0][1]

    def test_a_row_count_without_both_bounds_is_refused(self) -> None:
        result = controls_from(contract(dataset_rules=[library("rowCount", mustBeGreaterThan=100)]))
        assert not result.controls
        assert "both a minimum and a maximum" in result.refused[0][1]


class TestRouting:
    def test_a_soda_block_is_routed_not_refused(self) -> None:
        """Prama already imports SodaCL. Reimplementing it here would be a
        second mapping to drift from the first."""
        result = controls_from(
            contract(dataset_rules=[{"type": "custom", "engine": "soda", "implementation": "x"}])
        )
        assert result.routed
        assert "control import --from soda" in result.routed[0][1]

    def test_great_expectations_is_routed(self) -> None:
        result = controls_from(
            contract(dataset_rules=[{"type": "custom", "engine": "greatExpectations", "x": 1}])
        )
        assert result.routed

    def test_an_unknown_engine_is_refused_by_name(self) -> None:
        result = controls_from(contract(dataset_rules=[{"type": "custom", "engine": "montecarlo"}]))
        assert not result.routed
        assert "montecarlo" in result.refused[0][0]
        assert "cannot explain or replay" in result.refused[0][1]


class TestTheReport:
    def test_it_counts_what_was_offered_not_what_landed(self) -> None:
        """A contract promising eleven checks and yielding four is a
        conversation with the producer."""
        result = controls_from(
            contract(
                dataset_rules=[{"type": "text"}, {"type": "sql", "query": "SELECT 1"}],
                column_rules={"c": [library("nullCount")]},
            )
        )
        assert result.offered == 3
        assert len(result.controls) == 1
        assert not result.is_complete

    def test_a_contract_with_no_quality_says_so(self) -> None:
        assert controls_from(contract()).describe() == "the contract states no quality rules"

    def test_the_dict_form_names_every_refusal(self) -> None:
        payload = controls_from(
            contract(dataset_rules=[{"type": "text", "description": "x"}])
        ).to_dict()
        assert payload["refused"][0]["why"]
        assert payload["complete"] is False

    def test_a_contract_with_no_schema_imports_nothing(self) -> None:
        assert controls_from({"dataProduct": "x"}).offered == 0
