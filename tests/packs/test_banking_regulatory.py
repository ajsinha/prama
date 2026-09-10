"""The regulatory control catalogue.

An auditor never asks "do you have data quality controls". They ask *"which
controls address principle 4, and did they pass?"* — and these tests are mostly
about the answer having three states rather than two.

A coverage report that collapsed "controls exist and have not run" into either
neighbour is useless in opposite directions: folded into "unaddressed" it
under-reports the estate, folded into "passing" it certifies work nobody did.
The second is the one that gets a bank into trouble.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.core.errors import ValidationError
from prama.packs.banking.obligations import (
    BCBS_239,
    DISCHARGEABLE_PRINCIPLES,
    ISO_20022,
    OBLIGATIONS,
    SUPPORTED_NOT_DISCHARGED,
    catalogue,
)
from prama.packs.banking.regulatory import Standing, Template


@pytest.fixture(scope="module")
def book():
    return catalogue()


class TestTheThreeStates:
    def test_an_obligation_with_no_control_is_unaddressed(self, book) -> None:
        coverage = book.coverage(BCBS_239, controls_by_template={})
        assert all(s.standing is Standing.UNADDRESSED for s in coverage.standings)
        assert len(coverage.unaddressed) == len(coverage.standings)

    def test_controls_that_never_ran_are_unproven_not_passing(self, book) -> None:
        """The state that matters. A control nobody has run has proven nothing,
        and reporting it as coverage certifies work that was never done."""
        coverage = book.coverage(
            BCBS_239, controls_by_template={"cde-not-null": ["C1"]}, verdicts={}
        )
        [addressed] = [s for s in coverage.standings if s.controls]
        assert addressed.standing is Standing.ADDRESSED_UNPROVEN
        assert addressed.never_ran == 1
        assert addressed.standing.is_a_gap

    def test_controls_that_ran_clean_are_proven(self, book) -> None:
        coverage = book.coverage(
            BCBS_239,
            controls_by_template={"cde-not-null": ["C1"]},
            verdicts={"C1": "pass"},
        )
        [addressed] = [s for s in coverage.standings if s.controls]
        assert addressed.standing is Standing.PROVEN_CLEAN
        assert not addressed.standing.is_a_gap

    def test_a_failure_is_proven_with_exceptions(self, book) -> None:
        coverage = book.coverage(
            BCBS_239,
            controls_by_template={"cde-not-null": ["C1"]},
            verdicts={"C1": "fail"},
        )
        [addressed] = [s for s in coverage.standings if s.controls]
        assert addressed.standing is Standing.PROVEN_WITH_EXCEPTIONS
        assert addressed.failed == 1

    @pytest.mark.parametrize("verdict", ["indeterminate", "error"])
    def test_an_unestablished_verdict_is_an_exception_not_a_pass(self, book, verdict: str) -> None:
        """A control that could not establish a pass has not passed. Counting it
        as clean is the same false assurance the two-stage design exists to
        prevent, applied to a regulator."""
        coverage = book.coverage(
            BCBS_239,
            controls_by_template={"cde-not-null": ["C1"]},
            verdicts={"C1": verdict},
        )
        [addressed] = [s for s in coverage.standings if s.controls]
        assert addressed.standing is Standing.PROVEN_WITH_EXCEPTIONS
        assert addressed.not_established == 1

    def test_a_partly_run_obligation_is_not_unproven(self, book) -> None:
        """Two controls, one run. Something has been established, so this is not
        the "nothing has run" state — but the one that did not run is counted."""
        coverage = book.coverage(
            BCBS_239,
            controls_by_template={"cde-not-null": ["C1", "C2"]},
            verdicts={"C1": "pass"},
        )
        [addressed] = [s for s in coverage.standings if s.controls]
        assert addressed.standing is Standing.PROVEN_CLEAN
        assert addressed.never_ran == 1
        assert addressed.passed == 1


class TestTheSummaryNamesGapsFirst:
    def test_it_leads_with_what_is_not_covered(self, book) -> None:
        """A coverage figure quoted alone reads as an achievement. The number
        that matters at an examination is what nothing addresses."""
        described = book.coverage(
            BCBS_239,
            controls_by_template={"cde-not-null": ["C1"]},
            verdicts={"C1": "pass"},
        ).describe()
        assert described.index("have no control at all") < described.index("proven clean")

    def test_it_says_unproven_is_not_passing(self, book) -> None:
        described = book.coverage(
            BCBS_239, controls_by_template={"grain-unique": ["C9"]}
        ).describe()
        assert "not the same as passing" in described

    def test_an_empty_catalogue_says_nothing_is_covered(self) -> None:
        from prama.packs.banking.regulatory import Catalogue

        described = Catalogue().coverage("Anything", controls_by_template={}).describe()
        assert "no obligations are loaded" in described


class TestCitations:
    def test_every_obligation_cites_a_document_and_a_clause(self) -> None:
        """ "Show me where this comes from" is the follow-up to every finding,
        and a control whose provenance is folklore is one the bank cannot
        defend."""
        for obligation in OBLIGATIONS:
            assert obligation.citation.document, obligation.identity
            assert obligation.citation.clause, obligation.identity
            assert obligation.citation.render(), obligation.identity

    def test_every_obligation_states_its_objective_in_business_words(self) -> None:
        """Not the regulation's own words. A control objective nobody can read
        is one nobody checks against."""
        for obligation in OBLIGATIONS:
            assert len(obligation.objective) > 60, obligation.identity

    def test_every_obligation_ships_at_least_one_template(self) -> None:
        for obligation in OBLIGATIONS:
            assert obligation.templates, obligation.identity


class TestTemplatesAreNotControls:
    def test_binding_fills_the_placeholders(self) -> None:
        template = Template(
            identity="t",
            pql="CHECK {dataset}.{attribute} IS NOT NULL",
            requires=("dataset", "attribute"),
        )
        assert (
            template.bind({"dataset": "positions", "attribute": "notional"})
            == "CHECK positions.notional IS NOT NULL"
        )

    def test_an_unbound_placeholder_is_refused(self) -> None:
        """A control naming ``{amount}`` compiles to SQL naming a column called
        ``{amount}``, and the failure surfaces at execution as a database error
        nobody connects back to a template."""
        template = Template(
            identity="t",
            pql="CHECK {dataset}.{attribute} IS NOT NULL",
            requires=("dataset", "attribute"),
        )
        with pytest.raises(ValidationError, match="not bound"):
            template.bind({"dataset": "positions"})

    def test_every_shipped_template_binds_with_its_stated_requirements(self) -> None:
        """The property that makes `requires` trustworthy: a template that
        needed a placeholder it did not declare would raise here."""
        for obligation in OBLIGATIONS:
            for template in obligation.templates:
                bound = template.bind({name: f"col_{name}" for name in template.requires})
                assert "{" not in bound, f"{template.identity} has an undeclared placeholder"

    def test_every_shipped_template_produces_parseable_pql(self) -> None:
        """A catalogue of templates that do not parse is a catalogue of
        promises.

        Every one, with no exemption list. An earlier version of this test
        skipped templates it had no binding for, which is a loophole that grows:
        the next template added without a binding is silently unchecked, and
        nothing says so.
        """
        from prama.pql import parse_control
        from prama.pql.errors import PqlError

        bindings = {
            "cde-not-null": {"dataset": "positions", "attribute": "notional"},
            "grain-unique": {"dataset": "positions", "grain": "account_id, as_of_date"},
            "iban-bic-consistent": {
                "dataset": "payments",
                "iban": "creditor_iban",
                "bic": "creditor_bic",
            },
            "minor-units-ok": {"dataset": "payments", "amount": "amount", "currency": "currency"},
            "control-sum-agrees": {
                "dataset": "batches",
                "control_sum": "control_sum",
                "transaction_total": "transaction_total",
            },
            "references": {
                "dataset": "exposures",
                "attribute": "counterparty_id",
                "target_dataset": "counterparties",
                "target_attribute": "id",
            },
            "row-count-plausible": {"dataset": "positions", "minimum": "1000", "maximum": "5000"},
            "freshness": {"dataset": "positions", "window": "1 day"},
            "reconciles-with": {
                "dataset": "positions",
                "measure": "notional",
                "counterpart_measure": "gl_notional",
            },
        }
        unbound = [
            template.identity
            for obligation in OBLIGATIONS
            for template in obligation.templates
            if template.identity not in bindings
        ]
        assert not unbound, (
            f"no binding here for {unbound}, so they would go unchecked. Add one "
            "rather than letting the exemption grow."
        )
        for obligation in OBLIGATIONS:
            for template in obligation.templates:
                text = template.bind(bindings[template.identity])
                try:
                    parse_control(text)
                except PqlError as exc:  # pragma: no cover - a real failure
                    pytest.fail(f"{template.identity} does not parse: {exc}\n{text}")


class TestWhatThePackDoesNotClaim:
    def test_only_three_principles_are_discharged_by_controls(self) -> None:
        """Three of fourteen, and stating the number is the point. Accuracy,
        completeness and timeliness are testable properties of data; governance
        and architecture are not, and a template that checked nothing would be a
        claim the product cannot defend at an examination."""
        assert DISCHARGEABLE_PRINCIPLES == ("P3", "P4", "P5")
        principles = {o.principle for o in OBLIGATIONS if o.principle}
        assert principles == set(DISCHARGEABLE_PRINCIPLES)

    def test_the_other_principles_are_named_rather_than_omitted(self) -> None:
        """Left out silently, an absence reads as an oversight. Named, it reads
        as a boundary somebody drew."""
        assert "P1" in SUPPORTED_NOT_DISCHARGED
        assert "P2" in SUPPORTED_NOT_DISCHARGED
        assert all(len(reason) > 20 for reason in SUPPORTED_NOT_DISCHARGED.values())

    def test_no_principle_is_both_discharged_and_merely_supported(self) -> None:
        assert not set(DISCHARGEABLE_PRINCIPLES) & set(SUPPORTED_NOT_DISCHARGED)


class TestTheAuditorsQuestion:
    def test_obligations_are_reachable_by_principle(self, book) -> None:
        """The literal form of "which controls address principle 4"."""
        p4 = book.of_principle("P4")
        assert p4
        assert all(o.principle == "P4" for o in p4)

    def test_coverage_is_reportable_per_regime(self, book) -> None:
        assert set(book.regimes()) == {BCBS_239, ISO_20022}
        payments = book.coverage(ISO_20022, controls_by_template={})
        assert len(payments.standings) == len(book.of_regime(ISO_20022))

    def test_a_standing_names_the_controls_behind_it(self, book) -> None:
        """An examiner asked which controls address an obligation needs their
        identifiers, not a count."""
        coverage = book.coverage(
            BCBS_239,
            controls_by_template={"cde-not-null": ["C1", "C2"]},
            verdicts={"C1": "pass", "C2": "fail"},
        )
        [addressed] = [s for s in coverage.standings if s.controls]
        assert addressed.controls == ("C1", "C2")
        assert "2 control(s)" in addressed.describe()

    def test_the_dictionary_form_carries_everything_a_pack_needs(self, book) -> None:
        payload = book.coverage(
            BCBS_239, controls_by_template={"cde-not-null": ["C1"]}, verdicts={"C1": "pass"}
        ).to_dict()
        assert payload["regime"] == BCBS_239
        assert payload["unaddressed"] >= 1
        assert payload["standings"][0]["citation"]
        assert "message" in payload
