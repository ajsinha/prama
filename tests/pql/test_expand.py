"""Selectors: a control estate declared rather than typed.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses

import pytest

from prama.core.errors import ValidationError
from prama.ir.lower import Lowerer
from prama.pql.expand import Attribute, AttributeCatalogue, Expander, Expansion
from prama.pql.parser import parse_control

ESTATE = AttributeCatalogue(
    attributes=(
        Attribute(
            "positions",
            "notional_amount",
            concept="Position",
            concept_property="Notional",
            domain="Credit Risk",
            is_cde=True,
            criticality="tier1",
        ),
        Attribute(
            "positions",
            "isin",
            concept="Instrument",
            concept_property="ISIN",
            domain="Credit Risk",
            is_cde=True,
            semantic_type="ISIN",
        ),
        Attribute(
            "trades",
            "isin",
            concept="Instrument",
            concept_property="ISIN",
            domain="Market Risk",
            is_cde=True,
            semantic_type="ISIN",
        ),
        Attribute("trades", "comment", domain="Market Risk"),
        Attribute("accounts", "lei", domain="Credit Risk", is_cde=True, tags=("pii",)),
    )
)

CDES_IN_CREDIT = (
    "CHECK EVERY ATTRIBUTE WHERE is_cde AND domain = 'Credit Risk' "
    "IS NOT NULL SEVERITY critical BECAUSE 'CDEs must be complete'"
)


def expand(source: str, catalogue: AttributeCatalogue = ESTATE) -> list:
    return Expander(catalogue).expand(parse_control(source))


class TestSelectingByMetadata:
    def test_a_selector_covers_what_the_sentence_says(self) -> None:
        assert {c.target + "." + _column(c) for c in expand(CDES_IN_CREDIT)} == {
            "positions.notional_amount",
            "positions.isin",
            "accounts.lei",
        }

    def test_an_attribute_outside_the_domain_is_not_covered(self) -> None:
        assert "trades.isin" not in {c.target + "." + _column(c) for c in expand(CDES_IN_CREDIT)}

    def test_a_concept_selector_reaches_across_datasets(self) -> None:
        # The point of a semantic layer: ISO 6166 applies wherever an
        # instrument is identified, whatever the column is called locally.
        covered = expand("CHECK CONCEPT Instrument.ISIN IS VALID ISIN BECAUSE 'ISO 6166'")
        assert {c.target for c in covered} == {"positions", "trades"}

    def test_a_tag_matches_when_it_is_among_the_tags(self) -> None:
        covered = expand("CHECK EVERY ATTRIBUTE WHERE tags IN ('pii') IS NOT NULL BECAUSE 'x'")
        assert [c.target for c in covered] == ["accounts"]

    def test_a_bare_selector_covers_everything_declared(self) -> None:
        assert len(expand("CHECK EVERY ATTRIBUTE IS NOT NULL BECAUSE 'x'")) == 5

    def test_a_selector_matching_nothing_expands_to_nothing(self) -> None:
        # Not an error — a domain may genuinely have no CDEs yet — but an empty
        # expansion must not look like a covered estate.
        assert expand("CHECK EVERY ATTRIBUTE WHERE domain = 'Nowhere' IS NOT NULL") == []

    def test_missing_metadata_does_not_match(self) -> None:
        # Two-valued deliberately: an attribute nobody classified is not
        # thereby in scope, and quietly including it would put a control on
        # something nobody declared.
        assert expand("CHECK EVERY ATTRIBUTE WHERE criticality = 'tier1' IS NOT NULL") != []
        assert len(expand("CHECK EVERY ATTRIBUTE WHERE criticality = 'tier1' IS NOT NULL")) == 1


class TestWhatExpansionProduces:
    def test_an_expanded_control_is_an_ordinary_control(self) -> None:
        # It must render and re-parse as one, or the estate cannot be exported,
        # diffed or reviewed.
        for control in expand(CDES_IN_CREDIT):
            assert not control.is_template
            assert parse_control(control.render()) == control

    def test_it_remembers_the_declaration_it_came_from(self) -> None:
        # The difference between a generated estate somebody owns and one
        # nobody recognises.
        for control in expand(CDES_IN_CREDIT):
            assert control.derived_from.startswith("EVERY ATTRIBUTE WHERE")

    def test_it_keeps_the_severity_and_the_reason(self) -> None:
        control = expand(CDES_IN_CREDIT)[0]
        assert control.severity.value == "critical"
        assert control.because == "CDEs must be complete"

    def test_an_unjustified_selector_gives_its_controls_a_reason(self) -> None:
        control = expand("CHECK EVERY ATTRIBUTE WHERE is_cde IS NOT NULL")[0]
        assert control.because.startswith("Selected by EVERY ATTRIBUTE")

    def test_expanded_controls_lower_to_runnable_plans(self) -> None:
        for control in expand(CDES_IN_CREDIT):
            plan = Lowerer().control(control)
            assert plan.columns()
            assert plan.scope.dataset == control.target

    def test_two_attributes_produce_two_different_plans(self) -> None:
        plans = {Lowerer().control(c).plan_id for c in expand(CDES_IN_CREDIT)}
        assert len(plans) == 3


class TestExpansionIsMaterialised:
    """The whole design: a selector is resolved once, and changes are shown."""

    def test_a_preview_says_exactly_what_will_be_covered(self) -> None:
        # An author sees the assets before approving, not afterwards.
        preview = Expander(ESTATE).preview(parse_control(CDES_IN_CREDIT))
        assert preview.attributes == (
            "accounts.lei",
            "positions.isin",
            "positions.notional_amount",
        )
        assert preview.digest

    def test_the_same_coverage_gives_the_same_digest(self) -> None:
        first = Expander(ESTATE).preview(parse_control(CDES_IN_CREDIT))
        second = Expander(ESTATE).preview(parse_control(CDES_IN_CREDIT))
        assert first.digest == second.digest

    def test_a_newly_tagged_attribute_shows_as_drift(self) -> None:
        # Re-evaluating a selector on every run sounds like a feature and is
        # not: nobody approved the new control, nobody was told, and the first
        # anybody hears of it is an alert about a dataset they did not know was
        # in scope.
        control = parse_control(CDES_IN_CREDIT)
        approved = Expander(ESTATE).preview(control)
        wider = Expander(
            AttributeCatalogue(
                (
                    *ESTATE.attributes,
                    Attribute("collateral", "market_value", domain="Credit Risk", is_cde=True),
                )
            )
        )
        drift = wider.drift(control, approved)
        assert drift.has_changed
        assert drift.added == ("collateral.market_value",)
        assert "now covers 1 more" in drift.render()

    def test_a_de_tagged_attribute_shows_as_drift_too(self) -> None:
        # The dangerous direction: an attribute quietly loses its control while
        # the coverage report still says it is covered.
        control = parse_control(CDES_IN_CREDIT)
        approved = Expander(ESTATE).preview(control)
        narrower = Expander(
            AttributeCatalogue(tuple(a for a in ESTATE.attributes if a.name != "lei"))
        )
        drift = narrower.drift(control, approved)
        assert drift.removed == ("accounts.lei",)
        assert "no longer covers 1" in drift.render()

    def test_no_change_says_so_plainly(self) -> None:
        control = parse_control(CDES_IN_CREDIT)
        approved = Expander(ESTATE).preview(control)
        assert not Expander(ESTATE).drift(control, approved).has_changed

    def test_an_expansion_serialises_for_the_approval_record(self) -> None:
        payload = Expander(ESTATE).preview(parse_control(CDES_IN_CREDIT)).to_dict()
        assert payload["count"] == 3
        assert payload["selector"].startswith("EVERY ATTRIBUTE")
        assert payload["expanded_at"]


class TestRefusals:
    def test_expanding_a_concrete_control_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="nothing to expand"):
            Expander(ESTATE).expand(parse_control("CHECK positions.isin IS NOT NULL"))

    def test_a_reference_cannot_be_written_against_a_selector(self) -> None:
        # A reference names one column on each side; under a selector the left
        # side is different for every match, so there is no single
        # relationship to declare.
        from prama.pql.errors import PqlSyntaxError

        with pytest.raises(PqlSyntaxError) as caught:
            parse_control("CHECK EVERY ATTRIBUTE WHERE is_cde REFERENCES accounts.id")
        assert "one column on each side" in str(caught.value)

    def test_expand_all_leaves_concrete_controls_alone(self) -> None:
        mixed = [
            parse_control("CHECK positions.isin IS NOT NULL BECAUSE 'x'"),
            parse_control(CDES_IN_CREDIT),
        ]
        expanded = Expander(ESTATE).expand_all(mixed)
        assert len(expanded) == 4
        assert not any(c.is_template for c in expanded)


class TestReadability:
    def test_a_selector_control_describes_itself_in_business_terms(self) -> None:
        described = parse_control(CDES_IN_CREDIT).describe()
        assert described.startswith("For every attribute where is_cde AND domain")
        assert "ATTRIBUTE" not in described  # the placeholder must not shout

    def test_a_concept_selector_describes_the_concept(self) -> None:
        described = parse_control(
            "CHECK CONCEPT Instrument.ISIN IS VALID ISIN BECAUSE 'x'"
        ).describe()
        assert "every attribute mapped to Instrument.ISIN" in described


def _column(control) -> str:
    subject = control.assertion.subject
    return subject.name


def _replace(expansion: Expansion, **changes) -> Expansion:
    return dataclasses.replace(expansion, **changes)


class TestTheSelectorGrammar:
    """Where a selector's condition ends and its assertion begins."""

    def test_is_always_begins_the_assertion(self) -> None:
        # EVERY ATTRIBUTE WHERE is_cde IS NOT NULL is ambiguous to a parser
        # and, read carefully, to a person. The rule is that IS begins the
        # assertion, so this checks that CDEs are not null rather than
        # selecting attributes whose is_cde is not null.
        control = parse_control("CHECK EVERY ATTRIBUTE WHERE is_cde IS NOT NULL")
        assert control.selector is not None
        assert control.selector.where is not None
        assert control.selector.where.render() == "is_cde"
        assert control.assertion.operator == "is_not_null"  # type: ignore[attr-defined]

    def test_a_compound_condition_still_ends_at_is(self) -> None:
        control = parse_control(
            "CHECK EVERY ATTRIBUTE WHERE is_cde AND domain = 'Credit Risk' IS NOT NULL"
        )
        assert control.selector is not None
        assert control.selector.where is not None
        assert "domain = 'Credit Risk'" in control.selector.where.render()

    def test_in_is_still_available_inside_a_condition(self) -> None:
        # It cannot begin an assertion about a matched attribute on its own,
        # so there is no ambiguity to resolve.
        control = parse_control(
            "CHECK EVERY ATTRIBUTE WHERE criticality IN ('tier1','tier2') IS NOT NULL"
        )
        assert control.selector is not None
        assert control.selector.where is not None
        assert "IN ('tier1', 'tier2')" in control.selector.where.render()

    def test_a_selector_control_round_trips(self) -> None:
        for source in (
            "CHECK EVERY ATTRIBUTE WHERE is_cde IS NOT NULL",
            "CHECK EVERY ATTRIBUTE WHERE domain = 'Credit Risk' AND is_cde IS NOT NULL",
            "CHECK EVERY ATTRIBUTE IS NOT NULL",
            "CHECK CONCEPT Instrument.ISIN IS VALID ISIN",
        ):
            control = parse_control(source)
            assert parse_control(control.render()) == control
