"""SOC 2 readiness.

Prama's own, not the bank's. An auditor examining a control plane asks what *it*
does about access, change and monitoring, and the answer has to be mechanisms
that exist rather than a policy describing intent.

These tests are mostly about the module not overstating. A readiness matrix is
exactly the artefact somebody would use to mislead an auditor, so the caveats
have to be structural rather than a sentence at the top of a slide.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.security.soc2 import CRITERIA, Readiness, readout


class TestItDoesNotOverstate:
    def test_readiness_is_not_claimed_to_be_compliance(self) -> None:
        """Whether the organisation operates a control consistently over an
        observation window is a Type II question no code can answer."""
        payload = readout().to_dict()
        assert "Readiness is not compliance" in payload["caveat"]
        assert "no code can answer" in payload["caveat"]

    def test_a_partial_criterion_says_what_is_missing(self) -> None:
        """ "Partial" with no explanation is a colour, not a finding."""
        for criterion in CRITERIA:
            if criterion.readiness is Readiness.PARTIAL:
                assert criterion.note, criterion.identity
                assert len(criterion.note) > 40, criterion.identity

    def test_a_half_closed_criterion_says_which_half(self) -> None:
        """CC6.8 — the bundle is sealed and enumerated, and the *image* is
        still unsigned, so provenance stops at the bundle boundary. Moving it
        to evidenceable would be the overstatement this module avoids."""
        criterion = next(c for c in CRITERIA if c.identity == "CC6.8")
        assert criterion.readiness is Readiness.PARTIAL
        assert "still unsigned" in criterion.note
        assert "prama bundle seal" in criterion.mechanism

    def test_every_criterion_says_what_an_auditor_would_ask_for(self) -> None:
        """Including the gaps. A gap without this is a red cell rather than a
        piece of work."""
        for criterion in CRITERIA:
            assert criterion.evidence_request, criterion.identity

    def test_an_evidenceable_criterion_names_its_mechanism(self) -> None:
        """Named so an auditor can be shown it, not described so a reader can
        imagine it."""
        for criterion in CRITERIA:
            if criterion.readiness is Readiness.EVIDENCEABLE:
                assert criterion.mechanism, criterion.identity
                assert len(criterion.mechanism) > 40, criterion.identity


class TestTheGapsComeFirst:
    def test_the_summary_leads_with_what_needs_work(self) -> None:
        """A readiness matrix leading with what is covered is one whose gaps are
        read last or not at all."""
        described = readout().describe()
        assert described.startswith(("5 of", "4 of", "3 of", "2 of", "1 of"))
        assert "need work in the product" in described
        assert described.index("need work") < described.index("evidenceable")

    def test_the_gaps_are_named_in_the_summary(self) -> None:
        described = readout().describe()
        assert "CC6.8" in described
        assert "need work in the product" in described

    def test_organisational_criteria_are_not_counted_as_gaps(self) -> None:
        """They are not gaps, they are somebody else's control — and mixing
        them in makes the product look worse and the list less actionable."""
        result = readout()
        organisational = result.of(Readiness.ORGANISATIONAL)
        assert organisational
        assert not set(organisational) & set(result.gaps)


class TestWhatIsDeliberatelyNotAProductControl:
    def test_backup_is_left_to_the_operator_and_says_why(self) -> None:
        """A product that backed itself up beside the operator's backups would
        produce two recovery points and no statement about which is
        authoritative."""
        criterion = next(c for c in CRITERIA if c.identity == "A1.2")
        assert criterion.readiness is Readiness.ORGANISATIONAL
        assert "two recovery points" in criterion.note

    def test_it_still_says_what_an_auditor_would_ask_for(self) -> None:
        criterion = next(c for c in CRITERIA if c.identity == "A1.2")
        assert "restore test" in criterion.evidence_request


class TestTheMechanismsAreReal:
    @pytest.mark.parametrize(
        "identity,expected",
        [
            ("CC6.1", "PBKDF2"),
            ("CC7.2", "SIEM"),
            ("CC8.1", "bitemporal"),
            ("PI1.1", "indeterminate"),
        ],
    )
    def test_a_named_mechanism_matches_something_built(self, identity: str, expected: str) -> None:
        """Each of these points at code committed in this repository rather than
        at an intention."""
        criterion = next(c for c in CRITERIA if c.identity == identity)
        assert expected in criterion.mechanism

    def test_processing_integrity_rests_on_the_two_stage_design(self) -> None:
        """The claim that most distinguishes this product, and the one an
        auditor can test by replaying a control."""
        criterion = next(c for c in CRITERIA if c.identity == "PI1.1")
        assert "indeterminate rather than passing" in criterion.mechanism
        assert "replay" in criterion.evidence_request.lower()


class TestTheDictionaryForm:
    def test_it_carries_gaps_organisational_and_the_caveat(self) -> None:
        payload = readout().to_dict()
        assert "CC6.8" in payload["gaps"]
        assert "A1.2" in payload["organisational"]
        assert payload["evidenceable"] >= 3
        assert payload["caveat"]

    def test_every_criterion_serialises(self) -> None:
        payload = readout().to_dict()
        assert len(payload["criteria"]) == len(CRITERIA)
        assert all(entry["evidence_request"] for entry in payload["criteria"])
