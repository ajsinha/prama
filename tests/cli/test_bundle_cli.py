"""``prama bundle`` — the two commands an air-gapped install runs.

One on the machine that can reach the internet, one on the machine that cannot.
The exit code is the interface on the second, because there is nobody to ask.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from prama.cli.base import EXIT_DRIFT, EXIT_ERROR, EXIT_OK, Application
from prama.cli.commands import all_commands
from prama.core import pjson


def run(argv: list[str], secret: str = "a-deployment-key") -> tuple[int, str]:
    out = io.StringIO()
    argv = ["--set", f"security.session_secret={secret}", *argv]
    return Application(all_commands()).run(argv, out=out), out.getvalue()


@pytest.fixture
def staged(tmp_path: Path) -> Path:
    (tmp_path / "image").mkdir()
    (tmp_path / "wheels").mkdir()
    (tmp_path / "image" / "prama.tar").write_bytes(b"an image")
    (tmp_path / "wheels" / "prama.whl").write_bytes(b"a wheel")
    (tmp_path / "sqlite.sql").write_text("-- schema")
    return tmp_path


class TestSeal:
    def test_it_writes_a_manifest_and_a_signature(self, staged: Path) -> None:
        code, text = run(["bundle", "seal", str(staged)])
        assert code == EXIT_OK
        assert (staged / "manifest.json").exists()
        assert (staged / "manifest.sig").exists()
        assert "sealed 3 file(s)" in text

    def test_it_says_what_the_signature_is_worth(self, staged: Path) -> None:
        """This is the moment somebody decides how much to trust it."""
        _, text = run(["bundle", "seal", str(staged)])
        assert "HMAC over the manifest hash" in text
        assert "nothing to" in text and "does not hold it" in text

    def test_the_sbom_travels_by_default(self, staged: Path) -> None:
        _, text = run(["bundle", "seal", str(staged)])
        assert "distribution(s)" in text
        assert "sbom" in (staged / "manifest.json").read_text()

    def test_a_missing_directory_is_refused(self, tmp_path: Path) -> None:
        code, _ = run(["bundle", "seal", str(tmp_path / "absent")])
        assert code == EXIT_ERROR


class TestVerify:
    def test_a_sealed_bundle_verifies(self, staged: Path) -> None:
        run(["bundle", "seal", str(staged)])
        code, text = run(["bundle", "verify", str(staged)])
        assert code == EXIT_OK
        # Deliberately precise: "the signature holds" over two different
        # signatures would let a reader take a deployment's own HMAC for
        # publisher provenance, which is the stronger claim.
        assert "this deployment's seal holds" in text

    def test_a_tampered_file_exits_three(self, staged: Path) -> None:
        """Three, not one: an operator has to tell "this bundle is wrong" from
        "I ran the command wrong", and on an air-gapped host there is nobody to
        ask."""
        run(["bundle", "seal", str(staged)])
        (staged / "sqlite.sql").write_text("-- altered")
        code, text = run(["bundle", "verify", str(staged)])
        assert code == EXIT_DRIFT
        assert "Do not install this bundle." in text
        assert "build or tampering problem" in text

    def test_an_unsigned_bundle_exits_three(self, staged: Path) -> None:
        """It verifies internally and proves nothing about origin."""
        run(["bundle", "seal", str(staged)])
        (staged / "manifest.sig").unlink()
        code, text = run(["bundle", "verify", str(staged)])
        assert code == EXIT_DRIFT
        assert "could have been built by anybody" in text

    def test_a_bundle_sealed_with_another_key_exits_three(self, staged: Path) -> None:
        run(["bundle", "seal", str(staged)], secret="the-real-key")
        code, text = run(["bundle", "verify", str(staged)], secret="somebody-elses-key")
        assert code == EXIT_DRIFT
        assert "sealed elsewhere" in text

    def test_a_directory_with_no_manifest_is_refused(self, staged: Path) -> None:
        """A directory of files is not a bundle: without a manifest there is
        nothing to check the files against."""
        code, _ = run(["bundle", "verify", str(staged)])
        assert code == EXIT_ERROR

    def test_json_output_carries_the_verdict(self, staged: Path) -> None:
        run(["bundle", "seal", str(staged)])
        (staged / "sqlite.sql").write_text("-- altered")
        code, text = run(["--json", "bundle", "verify", str(staged)])
        payload = pjson.loads(text)
        assert code == EXIT_DRIFT
        assert payload["trustworthy"] is False
        assert payload["modified"] == ["sqlite.sql"]


class TestSbom:
    def test_it_lists_resolved_versions(self) -> None:
        """pyproject.toml states floors. A security review asking "what is in
        this" wants what resolved, and a floor is not an answer."""
        code, text = run(["bundle", "sbom"])
        assert code == EXIT_OK
        assert "prama==" in text
        assert ">=" not in text
        assert "as resolved rather than as requested" in text

    def test_json_output_is_machine_readable(self) -> None:
        code, text = run(["--json", "bundle", "sbom"])
        payload = pjson.loads(text)
        assert code == EXIT_OK
        assert any(item["name"] == "prama" for item in payload["distributions"])


@pytest.fixture
def keypair(tmp_path: Path) -> tuple[Path, Path]:
    pytest.importorskip("cryptography", reason="needs the 'sso' extra")
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = Ed25519PrivateKey.generate()
    private = tmp_path / "publisher.pem"
    public = tmp_path / "publisher.pub"
    private.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    public.write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    return private, public


class TestPublisherSigning:
    """The whole point: a host with only the public key can establish where a
    bundle came from."""

    def test_an_unsigned_seal_says_the_bundle_carries_no_provenance(self, staged) -> None:
        """Said on the success path, because that is the moment somebody
        decides how much the signature is worth."""
        code, text = run(["bundle", "seal", str(staged), "--no-sbom"])
        assert code == EXIT_OK
        assert "No publisher signature" in text
        assert "cannot check an HMAC without the key" in text

    def test_signing_writes_a_separate_file(self, staged, keypair) -> None:
        """Two signatures in one file would make a verifier that reads the
        wrong line report a valid bundle as forged."""
        private, _ = keypair
        run(["bundle", "seal", str(staged), "--no-sbom", "--sign-with", str(private)])
        assert (staged / "manifest.ed25519").is_file()
        assert (staged / "manifest.sig").is_file()

    def test_a_different_host_verifies_with_the_public_key_alone(self, staged, keypair) -> None:
        """The air-gapped case: a different session secret, so the HMAC seal
        legitimately fails while the publisher signature holds."""
        private, public = keypair
        run(
            ["bundle", "seal", str(staged), "--no-sbom", "--sign-with", str(private)],
            secret="the-build-machine-key",
        )
        code, text = run(
            ["bundle", "verify", str(staged), "--publisher-key", str(public)],
            secret="a-completely-different-host-key",
        )
        assert code == EXIT_OK
        assert "the publisher signature holds" in text
        assert "does not verify" not in text

    def test_a_signature_with_no_key_given_refuses(self, staged, keypair) -> None:
        """An unverifiable signature reported as nothing reads as an unsigned
        bundle, which is a different and lesser problem."""
        private, _ = keypair
        run(["bundle", "seal", str(staged), "--no-sbom", "--sign-with", str(private)])
        code, text = run(["bundle", "verify", str(staged)], secret="another-host")
        assert code == EXIT_DRIFT
        assert "no key was given to" in text

    def test_a_wrong_publisher_key_refuses(self, staged, keypair, tmp_path) -> None:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        private, _ = keypair
        run(["bundle", "seal", str(staged), "--no-sbom", "--sign-with", str(private)])
        impostor = tmp_path / "impostor.pub"
        impostor.write_bytes(
            Ed25519PrivateKey.generate()
            .public_key()
            .public_bytes(
                serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
            )
        )
        code, text = run(["bundle", "verify", str(staged), "--publisher-key", str(impostor)])
        assert code == EXIT_DRIFT
        assert "signed by somebody else" in text

    def test_tampering_after_signing_is_caught(self, staged, keypair) -> None:
        private, public = keypair
        run(["bundle", "seal", str(staged), "--no-sbom", "--sign-with", str(private)])
        (staged / "wheels" / "prama.whl").write_bytes(b"malicious")
        code, text = run(["bundle", "verify", str(staged), "--publisher-key", str(public)])
        assert code == EXIT_DRIFT
        assert "wrong hash" in text
        assert "Do not install" in text

    def test_json_says_whether_a_publisher_signature_was_written(self, staged, keypair) -> None:
        private, _ = keypair
        _, text = run(["--json", "bundle", "seal", str(staged), "--no-sbom"])
        assert pjson.loads(text)["publisher_signature"] is False
        _, text = run(
            ["--json", "bundle", "seal", str(staged), "--no-sbom", "--sign-with", str(private)]
        )
        assert pjson.loads(text)["publisher_signature"] is True
