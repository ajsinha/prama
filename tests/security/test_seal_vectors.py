"""Every HMAC seal, pinned to a known answer rather than to itself.

Finding T6. `verify_signature(head, key, sig)` is
`compare_digest(sign(head, key), sig)`, and every test of it was `sign`
agreeing with `sign`. The same shape held for `Manifest.seal` and
`Attestation.seal`. The string ``hmac`` appeared in exactly one test file in the
whole suite, and in none of the evidence, bundle or attestation tests.

Replacing all three with ``sha256(key || message)`` — the textbook
length-extension-vulnerable prefix MAC — and swapping ``hmac.compare_digest``
for ``==`` produced **zero** new failures. The word "sealed" in those docstrings
was carrying a claim nothing checked.

**The oracle here is independent.** `_hmac_sha256` below is HMAC written out
from RFC 2104 over `hashlib` alone; it does not import `hmac`. That is the same
move `scripts/verify_evidence.py` makes for the hash chain — a second
implementation that would have to be wrong in the same way to agree — and it is
what makes these vectors worth more than a round trip.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest

from prama.evidence.ledger import sign, verify_signature
from prama.report.attestation import Attestation, Coverage
from prama.report.attestation import Exception_ as AttestationException
from prama.security.bundle import Manifest

#: A fixed key. Not a secret: the point of a known-answer vector is that the
#: answer is known.
KEY = b"prama-known-answer-key"

BLOCK = 64


def _hmac_sha256(key: bytes, message: bytes) -> str:
    """HMAC-SHA256 from RFC 2104, using only `hashlib`.

    Deliberately not `hmac.new`: a test that reaches for the same library the
    code does cannot tell HMAC from anything else that library would produce.
    """
    if len(key) > BLOCK:
        key = hashlib.sha256(key).digest()
    key = key.ljust(BLOCK, b"\0")
    inner = bytes(byte ^ 0x36 for byte in key)
    outer = bytes(byte ^ 0x5C for byte in key)
    return hashlib.sha256(outer + hashlib.sha256(inner + message).digest()).hexdigest()


class TestTheOracleItself:
    """Before trusting the oracle, pin it to the published vectors.

    An independent implementation that is independently *wrong* is worse than
    no oracle at all. These two constants are RFC 4231 §4.2 and §4.3, and they
    are not something this repository gets to have an opinion about.
    """

    def test_rfc_4231_case_1(self) -> None:
        assert _hmac_sha256(bytes.fromhex("0b" * 20), b"Hi There") == (
            "b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7"
        )

    def test_rfc_4231_case_2(self) -> None:
        assert _hmac_sha256(b"Jefe", b"what do ya want for nothing?") == (
            "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843"
        )

    def test_it_is_not_a_prefix_mac(self) -> None:
        """The substitution that used to go unnoticed, shown to be different."""
        message = b"a" * 64
        assert _hmac_sha256(KEY, message) != hashlib.sha256(KEY + message).hexdigest()


def attestation() -> Attestation:
    return Attestation(
        attester_id="01ALICE",
        attester_name="Alice Chen",
        statement="I have reviewed the controls for September.",
        scope="Trading book",
        period_start="2026-09-01",
        period_end="2026-09-30",
        coverage=Coverage(controls_in_scope=12, controls_run=11, passed=9, failed=2, never_ran=1),
        exceptions=(
            AttestationException(
                control_id="01C1", dataset="positions_eod", verdict="fail", detail="12 of 1,000"
            ),
        ),
        evidence_root="ab" * 32,
        evidence_records=431,
        signed_at="2026-10-01T09:15:00Z",
        tenant_id="01TENANT",
    )


class TestEverySealIsHmacSha256:
    """One test per seal, each against the independent oracle."""

    def test_the_ledger_head_signature(self) -> None:
        head = "cd" * 32
        assert sign(head, KEY) == _hmac_sha256(KEY, head.encode("ascii"))

    def test_the_attestation_seal(self) -> None:
        subject = attestation()
        assert subject.seal(KEY) == _hmac_sha256(KEY, subject.content_hash.encode("ascii"))

    def test_the_manifest_seal(self, tmp_path: Path) -> None:
        from prama.security.bundle import build_manifest

        (tmp_path / "a.txt").write_text("contents", encoding="utf-8")
        manifest: Manifest = build_manifest(tmp_path, created_at="2026-10-01T09:15:00Z")
        assert manifest.seal(KEY) == _hmac_sha256(KEY, manifest.content_hash.encode("ascii"))

    def test_a_prefix_mac_would_be_caught(self) -> None:
        """The counterfactual for the three tests above.

        Each would be satisfied by any function that agrees with itself; this
        shows the oracle disagrees with the specific wrong answer the reviewer
        substituted without breaking a single test.
        """
        head = "cd" * 32
        assert sign(head, KEY) != hashlib.sha256(KEY + head.encode("ascii")).hexdigest()


class TestVerificationIsConstantTime:
    """A seal compared with `==` leaks its prefix a byte at a time.

    Nothing asserted this, and swapping `compare_digest` for `==` broke no test.
    Checked by reading the code rather than by timing: a timing test on a laptop
    measures the laptop.
    """

    SOURCES = (
        "src/prama/evidence/ledger.py",
        "src/prama/report/attestation.py",
        "src/prama/security/bundle.py",
        "src/prama/db/security.py",
    )

    @pytest.mark.parametrize("relative", SOURCES)
    def test_the_module_compares_digests_constant_time(self, relative: str) -> None:
        root = Path(__file__).resolve().parents[2]
        tree = ast.parse((root / relative).read_text(encoding="utf-8"))
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "compare_digest"
        ]
        assert calls, f"{relative} seals or verifies and never calls hmac.compare_digest"

    def test_a_wrong_signature_is_rejected(self) -> None:
        """The behaviour, alongside the shape."""
        head = "cd" * 32
        assert verify_signature(head, KEY, sign(head, KEY))
        assert not verify_signature(head, KEY, sign(head, b"another key"))
        assert not verify_signature(head, KEY, "00" * 32)
