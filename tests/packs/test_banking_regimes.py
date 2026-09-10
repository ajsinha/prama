"""The reporting regimes, and what they admit to.

The value of a regulatory catalogue is not its size. It is whether a reader can
tell, without reading the code, which entries rest on a reference nobody has
checked and which obligations are only partly discharged.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.packs.banking import regimes
from prama.packs.banking.obligations import ALL_OBLIGATIONS
from prama.packs.banking.regulatory import (
    Citation,
    Obligation,
    RelationshipRequirement,
    Template,
)
from prama.semantic.relationships import RelationshipKind


class TestCitationsSayWhetherAnybodyCheckedThem:
    def test_a_citation_is_unconfirmed_until_somebody_confirms_it(self) -> None:
        """ "Show me where this comes from" is the follow-up to every finding an
        examiner makes, and a wrong article number costs more credibility than
        an absent one."""
        assert Citation(document="X", clause="Art 1").confirmed is False

    def test_an_unconfirmed_citation_says_so_when_rendered(self) -> None:
        rendered = Citation(document="X", clause="Art 1").render_with_standing()
        assert "unconfirmed against the published text" in rendered

    def test_a_confirmation_must_name_somebody(self) -> None:
        """An unattributable confirmation is not one."""
        with pytest.raises(ValueError, match="nobody named"):
            Citation(document="X", clause="Art 1", confirmed=True)

    def test_a_confirmed_citation_names_the_confirmer(self) -> None:
        rendered = Citation(
            document="X", clause="Art 1", confirmed=True, confirmed_by="compliance"
        ).render_with_standing()
        assert "confirmed by compliance" in rendered

    def test_every_shipped_regime_citation_is_honestly_marked(self) -> None:
        """Nobody has checked these against the published texts, and the
        catalogue must not imply otherwise."""
        for obligation in regimes.REGIME_OBLIGATIONS:
            assert obligation.citation.confirmed is False
            assert obligation.citation.document
            assert obligation.citation.clause
            assert obligation.citation.authority

    def test_the_confirmation_standing_reaches_the_dict_form(self) -> None:
        """Whatever consumes the catalogue programmatically must be able to
        report which obligations rest on unverified references."""
        payload = regimes.REGIME_OBLIGATIONS[0].to_dict()
        assert payload["citation_confirmed"] is False


class TestAnObligationCannotLookCovered:
    def test_one_with_nothing_behind_it_is_refused(self) -> None:
        with pytest.raises(ValueError, match="looks covered"):
            Obligation(
                identity="EMPTY",
                regime="X",
                citation=Citation(document="X", clause="1"),
                objective="something",
            )

    def test_a_stated_gap_is_enough_on_its_own(self) -> None:
        """An obligation nothing discharges can still be catalogued, provided
        it says so. That is more useful than omitting it, which leaves a reader
        to conclude the regime does not require it."""
        entry = Obligation(
            identity="HONEST",
            regime="X",
            citation=Citation(document="X", clause="1"),
            objective="something",
            not_discharged="no control addresses this",
        )
        assert not entry.is_fully_discharged

    def test_a_relationship_alone_is_enough(self) -> None:
        entry = Obligation(
            identity="DECLARED",
            regime="X",
            citation=Citation(document="X", clause="1"),
            objective="something",
            relationships=(
                RelationshipRequirement(
                    kind=RelationshipKind.TOGETHER_COMPLETE, between="{a} and {b}"
                ),
            ),
        )
        assert entry.is_fully_discharged

    def test_the_regimes_that_are_partly_discharged_say_which_part(self) -> None:
        partial = [o for o in regimes.REGIME_OBLIGATIONS if not o.is_fully_discharged]
        assert partial
        for obligation in partial:
            assert len(obligation.not_discharged) > 30


class TestSetLevelObligationsAreDeclaredNotFaked:
    def test_population_completeness_is_a_relationship(self) -> None:
        """Whether a set of feeds covers the book is a statement about the set,
        not a check on any one of them. Written as PQL it would be syntax the
        language does not have."""
        entry = next(
            o for o in regimes.REGIME_OBLIGATIONS if o.identity == "CRR-ART394-EXPOSURE-COMPLETE"
        )
        kinds = [r.kind for r in entry.relationships]
        assert RelationshipKind.TOGETHER_COMPLETE in kinds

    def test_subledger_to_gl_is_a_relationship(self) -> None:
        entry = next(o for o in regimes.REGIME_OBLIGATIONS if o.identity == "SOX-404-SUBLEDGER-GL")
        assert RelationshipKind.RECONCILES_WITH in [r.kind for r in entry.relationships]

    def test_the_relationship_kinds_are_ones_the_platform_has(self) -> None:
        """Naming the enum rather than a string is what stops this catalogue
        drifting from the generator that dispatches on it."""
        for obligation in ALL_OBLIGATIONS:
            for requirement in obligation.relationships:
                assert isinstance(requirement.kind, RelationshipKind)


class TestTheDirectionOfAPopulationCheck:
    def test_under_reporting_is_checked_from_the_trade_store(self) -> None:
        """Checking that every reported trade exists in the store finds
        over-reporting and cannot find under-reporting — and under-reporting is
        the breach."""
        entry = next(
            o for o in regimes.REGIME_OBLIGATIONS if o.identity == "MIFIR-ART26-T1-COMPLETE"
        )
        template = next(t for t in entry.templates if t.identity == "mifir-t1-every-trade-reported")
        bound = template.bind(
            {
                "trade_store": "trades",
                "trade_id": "trade_id",
                "dataset": "tx_report",
                "report_trade_id": "trade_id",
            }
        )
        assert bound.startswith("CHECK trades.trade_id REFERENCES tx_report")

    def test_the_template_says_why_the_direction_matters(self) -> None:
        entry = next(
            o for o in regimes.REGIME_OBLIGATIONS if o.identity == "MIFIR-ART26-T1-COMPLETE"
        )
        template = next(t for t in entry.templates if t.identity == "mifir-t1-every-trade-reported")
        assert "direction is the control" in template.note


class TestScope:
    def test_every_regime_says_what_it_leaves_alone(self) -> None:
        """A regime named in a catalogue reads as a regime handled, and for
        every one of these that is false."""
        shipped = {o.regime for o in regimes.REGIME_OBLIGATIONS}
        assert shipped == set(regimes.REGIME_SCOPE)
        for regime, scope in regimes.REGIME_SCOPE.items():
            assert "Not " in scope or "not " in scope, regime

    def test_aml_does_not_claim_to_judge_an_alert(self) -> None:
        """CON-007: whether an alert should have been raised is an
        adjudication."""
        assert "CON-007" in regimes.REGIME_SCOPE[regimes.AML]

    def test_large_exposures_does_not_claim_the_calculation(self) -> None:
        assert "not a data quality control" in regimes.REGIME_SCOPE[regimes.LARGE_EXPOSURES]

    def test_gdpr_does_not_claim_lawfulness(self) -> None:
        assert "lawfulness" in regimes.REGIME_SCOPE[regimes.GDPR]


class TestTemplatesThatCouldMislead:
    def test_the_lei_template_says_a_person_has_no_lei(self) -> None:
        """Applying it to a retail book turns every borrower into a defect."""
        entry = next(
            o
            for o in regimes.REGIME_OBLIGATIONS
            if o.identity == "ANACREDIT-COUNTERPARTY-REFERENCE"
        )
        template = next(t for t in entry.templates if t.identity == "anacredit-counterparty-lei")
        assert "natural person has no LEI" in template.note

    def test_the_email_template_says_well_formed_is_not_accurate(self) -> None:
        entry = next(o for o in regimes.REGIME_OBLIGATIONS if o.identity == "GDPR-ART5-ACCURACY")
        template = next(t for t in entry.templates if t.identity == "gdpr-contact-well-formed")
        assert "Well-formed is not accurate" in template.note

    def test_binding_still_refuses_a_hole(self) -> None:
        """Inherited, and worth re-asserting for the new templates: a control
        naming {amount} compiles to SQL naming a column called {amount}."""
        from prama.core.errors import ValidationError

        template = Template(identity="t", pql="CHECK {a} IS NOT NULL", requires=("a",))
        with pytest.raises(ValidationError):
            template.bind({})
