"""Attestation: a named person's statement, and everything it may not omit.

An attestation is the easiest artefact in this product to make dishonest, so
most of these tests are about what it is not allowed to leave out — and about
the fact that a *qualified* attestation is a valid one, so the format must
never make the honest answer the hard one to give.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses

import pytest

from prama.report.attestation import Attestation, Coverage, Exception_


def _coverage(**overrides: int) -> Coverage:
    base = {
        "controls_in_scope": 40,
        "controls_run": 40,
        "passed": 40,
        "failed": 0,
        "not_established": 0,
        "errored": 0,
        "never_ran": 0,
    }
    base.update(overrides)
    return Coverage(**base)  # type: ignore[arg-type]


def _attestation(**overrides: object) -> Attestation:
    base: dict[str, object] = {
        "attester_id": "01ALICE",
        "attester_name": "Alice Chen",
        "statement": "I have reviewed the controls on the trading book for September.",
        "scope": "Trading book",
        "period_start": "2026-09-01",
        "period_end": "2026-09-30",
        "coverage": _coverage(),
        "evidence_root": "ab" * 32,
        "evidence_records": 340,
        "signed_at": "2026-10-02T09:14:00Z",
        "tenant_id": "01TENANT",
    }
    base.update(overrides)
    return Attestation(**base)  # type: ignore[arg-type]


class TestQualifiedIsStillValid:
    """The distinction an auditor uses. A qualified attestation is an
    attestation; presenting one as unqualified is the fraud, and refusing to
    allow one would simply mean nobody attests."""

    def test_a_clean_period_is_unqualified(self) -> None:
        assert not _attestation().is_qualified
        assert "without exception" in _attestation().describe()

    def test_a_failure_qualifies_it(self) -> None:
        attestation = _attestation(
            coverage=_coverage(passed=38, failed=2),
            exceptions=(Exception_("c1", "trades", "fail", "412 rows"),),
        )
        assert attestation.is_qualified
        assert "with exceptions" in attestation.describe()

    def test_incomplete_coverage_qualifies_it_even_with_no_failures(self) -> None:
        """Everything that ran passed, and half of it never ran. That is not a
        clean sign-off, and a format that called it one would be the problem."""
        attestation = _attestation(coverage=_coverage(controls_run=20, passed=20, never_ran=20))
        assert attestation.coverage.is_clean
        assert attestation.is_qualified


class TestItCannotOmitTheNumbers:
    def test_coverage_states_the_share_when_incomplete(self) -> None:
        """An attestation over 40% coverage that does not say 40% converts an
        unexamined estate into a signed one."""
        described = _coverage(controls_run=16, passed=16, never_ran=24).describe()
        assert "16 of 40" in described
        assert "40%" in described

    def test_a_complete_period_does_not_belabour_it(self) -> None:
        assert "%" not in _coverage().describe()

    @pytest.mark.parametrize(
        ("field", "word"),
        [
            ("failed", "failed"),
            ("not_established", "could not be established"),
            ("errored", "could not be executed"),
            ("never_ran", "never ran at all"),
        ],
    )
    def test_every_unhappy_number_appears(self, field: str, word: str) -> None:
        assert word in _coverage(**{field: 3}).describe()

    def test_an_empty_scope_does_not_divide_by_zero(self) -> None:
        assert _coverage(controls_in_scope=0, controls_run=0, passed=0).rate == 0.0

    def test_never_ran_is_not_an_exception_but_is_counted(self) -> None:
        """There is no verdict to except from — and it is the number that
        decides how much the attestation covers."""
        attestation = _attestation(coverage=_coverage(controls_run=30, passed=30, never_ran=10))
        assert attestation.exceptions == ()
        assert attestation.coverage.never_ran == 10
        assert attestation.is_qualified


class TestTheSealCoversEverything:
    def test_the_hash_changes_with_the_statement(self) -> None:
        assert _attestation().content_hash != _attestation(statement="Different.").content_hash

    def test_the_hash_changes_with_the_coverage(self) -> None:
        """A field outside the hash is a field somebody can change after the
        signature, which is the only thing a signature is for."""
        assert (
            _attestation().content_hash
            != _attestation(coverage=_coverage(failed=1, passed=39)).content_hash
        )

    def test_the_hash_changes_with_an_exception_disposition(self) -> None:
        first = _attestation(exceptions=(Exception_("c1", "t", "fail", "d", "raised"),))
        second = _attestation(exceptions=(Exception_("c1", "t", "fail", "d", "accepted"),))
        assert first.content_hash != second.content_hash

    def test_the_hash_changes_with_the_evidence_root(self) -> None:
        """Without this the signature would survive the evidence being
        swapped, which is the whole thing it exists to prevent."""
        assert _attestation().content_hash != _attestation(evidence_root="cd" * 32).content_hash

    def test_the_seal_verifies_with_the_key_and_not_without(self) -> None:
        attestation = _attestation()
        seal = attestation.seal(b"the-key")
        assert attestation.verify(b"the-key", seal)
        assert not attestation.verify(b"another-key", seal)

    def test_a_tampered_attestation_fails_its_own_seal(self) -> None:
        original = _attestation()
        seal = original.seal(b"k")
        tampered = dataclasses.replace(original, coverage=_coverage(failed=0, passed=40))
        edited = dataclasses.replace(original, statement="Everything was perfect.")
        assert tampered.verify(b"k", seal)  # unchanged content, same seal
        assert not edited.verify(b"k", seal)


class TestItNamesAPerson:
    def test_the_description_names_the_attester(self) -> None:
        """A control attested by "the team" is a control nobody attested."""
        assert "Alice Chen" in _attestation().describe()

    def test_the_description_names_the_scope_and_period(self) -> None:
        described = _attestation().describe()
        assert "Trading book" in described
        assert "2026-09-01" in described and "2026-09-30" in described


class TestSupersession:
    def test_a_correction_carries_what_it_replaces_and_why(self) -> None:
        """A signed attestation is never edited: the fact that somebody signed
        the first one is part of the record."""
        correction = _attestation(
            supersedes="01EARLIER",
            supersedes_because="the September evidence was re-run after a source fix",
        )
        assert correction.content()["supersedes"] == "01EARLIER"
        assert "re-run" in correction.content()["supersedes_because"]

    def test_the_supersession_is_inside_the_hash(self) -> None:
        assert _attestation().content_hash != _attestation(supersedes="01X").content_hash
