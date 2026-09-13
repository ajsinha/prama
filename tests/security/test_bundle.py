"""The offline bundle.

A bank that will not let a control plane reach the internet still has to install
it and prove to an auditor that what it installed is what was shipped. A bundle
is therefore not an archive — it is an archive plus a statement about the
archive that somebody can check.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from prama.core.errors import ValidationError
from prama.security.bundle import (
    Manifest,
    build_manifest,
    installed_distributions,
    verify,
)

KEY = b"a-deployment-key"
WHEN = "2026-09-10T06:00:00Z"


@pytest.fixture
def bundle(tmp_path: Path) -> Path:
    (tmp_path / "image").mkdir()
    (tmp_path / "chart").mkdir()
    (tmp_path / "wheels").mkdir()
    (tmp_path / "image" / "prama.tar").write_bytes(b"pretend this is an image")
    (tmp_path / "chart" / "prama-0.1.0.tgz").write_bytes(b"pretend this is a chart")
    (tmp_path / "wheels" / "prama-0.1.0-py3-none-any.whl").write_bytes(b"a wheel")
    (tmp_path / "sqlite.sql").write_text("-- schema")
    # A real bundle carries its manifest, and the manifest states the hash it
    # is meant to be checked against. Writing it here means these tests
    # exercise the on-disk path where SEC-142 lived, rather than an in-memory
    # shortcut where the claim and the recomputation came from one object.
    (tmp_path / "manifest.json").write_text(
        json.dumps(build_manifest(tmp_path, created_at=WHEN).to_dict())
    )
    return tmp_path


class TestTheManifest:
    def test_it_catalogues_every_file_with_a_hash(self, bundle: Path) -> None:
        manifest = build_manifest(bundle, created_at=WHEN)
        assert len(manifest.entries) == 4
        assert all(len(entry.sha256) == 64 for entry in manifest.entries)
        assert manifest.total_bytes > 0

    def test_it_classifies_what_it_finds(self, bundle: Path) -> None:
        manifest = build_manifest(bundle, created_at=WHEN)
        kinds = {entry.path: entry.kind for entry in manifest.entries}
        assert kinds["image/prama.tar"] == "image"
        assert kinds["wheels/prama-0.1.0-py3-none-any.whl"] == "wheel"
        assert kinds["sqlite.sql"] == "schema"

    def test_it_excludes_itself_and_its_signature(self, bundle: Path) -> None:
        """A manifest listing its own hash could never be produced, and one
        listing the signature would change the thing the signature covers."""
        (bundle / "manifest.json").write_text("{}")
        (bundle / "manifest.sig").write_text("deadbeef")
        manifest = build_manifest(bundle, created_at=WHEN)
        assert not any("manifest" in entry.path for entry in manifest.entries)

    def test_the_serialisation_is_stable(self, bundle: Path) -> None:
        """A manifest whose serialisation varied would make a signature depend
        on the JSON library, and a verification failure would mean nothing."""
        first = build_manifest(bundle, created_at=WHEN)
        second = build_manifest(bundle, created_at=WHEN)
        assert first.content() == second.content()
        assert first.content_hash == second.content_hash

    def test_a_missing_directory_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(ValidationError, match="no bundle directory"):
            build_manifest(tmp_path / "absent", created_at=WHEN)


class TestVerification:
    def _sealed(self, bundle: Path) -> tuple[Manifest, str]:
        manifest = build_manifest(bundle, created_at=WHEN)
        return manifest, manifest.seal(KEY)

    def test_an_untouched_bundle_verifies(self, bundle: Path) -> None:
        manifest, seal = self._sealed(bundle)
        result = verify(bundle, manifest, key=KEY, seal=seal)
        assert result.is_trustworthy
        assert "seal holds" in result.describe()

    def test_a_modified_file_is_named_as_modified(self, bundle: Path) -> None:
        """A build or tampering problem, and it goes to whoever made the
        bundle."""
        manifest, seal = self._sealed(bundle)
        (bundle / "sqlite.sql").write_text("-- altered")
        result = verify(bundle, manifest, key=KEY, seal=seal)
        assert result.modified == ("sqlite.sql",)
        assert not result.is_trustworthy
        assert "build or tampering problem" in result.describe()

    def test_a_missing_file_is_named_as_missing(self, bundle: Path) -> None:
        """A transfer problem, and it goes to the network team. Sending an
        operator to the wrong one costs the first hour."""
        manifest, seal = self._sealed(bundle)
        (bundle / "sqlite.sql").unlink()
        result = verify(bundle, manifest, key=KEY, seal=seal)
        assert result.missing == ("sqlite.sql",)
        assert "a transfer problem" in result.describe()

    def test_modified_is_reported_before_missing(self, bundle: Path) -> None:
        manifest, seal = self._sealed(bundle)
        (bundle / "sqlite.sql").write_text("-- altered")
        (bundle / "wheels" / "prama-0.1.0-py3-none-any.whl").unlink()
        described = verify(bundle, manifest, key=KEY, seal=seal).describe()
        assert described.index("wrong hash") < described.index("listed and absent")

    def test_an_unlisted_file_is_reported(self, bundle: Path) -> None:
        """Not automatically wrong, and worth saying: an unlisted file is one
        nobody signed for."""
        manifest, seal = self._sealed(bundle)
        (bundle / "extra.bin").write_bytes(b"who put this here")
        result = verify(bundle, manifest, key=KEY, seal=seal)
        assert result.unexpected == ("extra.bin",)
        assert "nobody signed for" in result.describe()


class TestAnUnsignedBundleIsNotABundle:
    def test_no_signature_is_not_trustworthy_even_when_the_hashes_match(self, bundle: Path) -> None:
        """It verifies internally and proves nothing about origin — and in an
        air-gapped install there is nothing else to check it against."""
        manifest = build_manifest(bundle, created_at=WHEN)
        result = verify(bundle, manifest)
        assert not result.missing
        assert not result.modified
        assert not result.is_trustworthy
        assert result.seal_holds is None

    def test_the_absence_is_stated_as_loudly_as_a_mismatch(self, bundle: Path) -> None:
        manifest = build_manifest(bundle, created_at=WHEN)
        described = verify(bundle, manifest).describe()
        assert "proves nothing about where it came from" in described
        assert "could have been built by anybody" in described

    def test_a_wrong_key_is_distinguished_from_no_key(self, bundle: Path) -> None:
        """Altered-or-sealed-elsewhere and never-signed are different
        incidents."""
        manifest = build_manifest(bundle, created_at=WHEN)
        wrong = verify(bundle, manifest, key=b"elsewhere", seal=manifest.seal(KEY))
        absent = verify(bundle, manifest)
        assert wrong.seal_holds is False
        assert absent.seal_holds is None
        assert "sealed elsewhere" in wrong.describe()

    def test_a_tampered_manifest_invalidates_everything(self, bundle: Path) -> None:
        """Including the file list itself, which is why it is said first."""
        manifest = build_manifest(bundle, created_at=WHEN)
        broken = dataclasses.replace(manifest, entries=manifest.entries[:1])
        result = verify(bundle, broken, key=KEY, seal=manifest.seal(KEY))
        assert not result.is_trustworthy
        assert result.seal_holds is False


class TestTheSbom:
    def test_it_records_what_is_installed_not_what_was_asked_for(self) -> None:
        """pyproject.toml states floors; this states what resolved. An SBOM
        listing the requirements describes a different install from the one the
        bundle carries."""
        found = dict(installed_distributions())
        assert "prama" in found
        assert found["prama"]
        # A floor in pyproject would be ">=2.0.30"; this is a resolved version.
        assert not any(version.startswith(">") for version in found.values())

    def test_it_travels_inside_the_signed_manifest(self, bundle: Path) -> None:
        """ "What is in this thing" is the first question a bank's security team
        asks, and it cannot be answered later from an air-gapped host."""
        manifest = build_manifest(
            bundle, created_at=WHEN, sbom=[("prama", "0.1.0"), ("fastapi", "0.141.1")]
        )
        assert ("prama", "0.1.0") in manifest.sbom
        assert "fastapi" in manifest.content()

    def test_changing_the_sbom_changes_the_signature(self, bundle: Path) -> None:
        """Otherwise the dependency list could be swapped after signing."""
        one = build_manifest(bundle, created_at=WHEN, sbom=[("a", "1")])
        two = build_manifest(bundle, created_at=WHEN, sbom=[("a", "2")])
        assert one.seal(KEY) != two.seal(KEY)


class TestAsymmetricSignature:
    """The signature that survives leaving the building.

    An HMAC establishes nothing to anybody who does not hold the key, which is
    exactly the air-gapped customer's position. An Ed25519 signature is
    verifiable with a public key they can be given, pinned and audited.
    """

    def key(self):
        pytest.importorskip("cryptography", reason="needs the 'sso' extra")
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        return Ed25519PrivateKey.generate()

    def test_a_signature_verifies_with_only_the_public_half(self, bundle) -> None:
        """The entire point: verification needs nothing secret, so the key can
        be published and checked by somebody with no relationship to us."""
        manifest = build_manifest(bundle, created_at=WHEN)
        private = self.key()
        signature = manifest.sign(private)
        assert manifest.signature_holds(private.public_key(), signature)

    def test_another_key_does_not_verify(self, bundle) -> None:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        manifest = build_manifest(bundle, created_at=WHEN)
        signature = manifest.sign(self.key())
        assert not manifest.signature_holds(Ed25519PrivateKey.generate().public_key(), signature)

    def test_an_altered_manifest_does_not_verify(self, bundle) -> None:
        manifest = build_manifest(bundle, created_at=WHEN)
        private = self.key()
        signature = manifest.sign(private)
        tampered = dataclasses.replace(manifest, version="9.9.9")
        assert not tampered.signature_holds(private.public_key(), signature)

    def test_a_malformed_signature_is_just_no(self, bundle) -> None:
        """Distinguishing a malformed signature from a wrong one tells an
        attacker which half to vary."""
        manifest = build_manifest(bundle, created_at=WHEN)
        public = self.key().public_key()
        assert not manifest.signature_holds(public, "not-hex")
        assert not manifest.signature_holds(public, "00" * 64)

    def test_verify_reports_the_two_signatures_apart(self, bundle) -> None:
        """ "Sealed by us" and "signed by the publisher" are different claims,
        and one boolean would collapse them."""
        root, manifest = bundle, build_manifest(bundle, created_at=WHEN)
        private = self.key()
        result = verify(
            root,
            manifest,
            public_key=private.public_key(),
            signature=manifest.sign(private),
        )
        assert result.signature_holds is True
        assert result.seal_holds is None
        assert result.is_trustworthy

    def test_a_signature_alone_is_enough_to_install(self, bundle) -> None:
        """An air-gapped customer has the public key and not the deployment's
        HMAC key, which is the whole situation this exists for."""
        root, manifest = bundle, build_manifest(bundle, created_at=WHEN)
        private = self.key()
        result = verify(
            root, manifest, public_key=private.public_key(), signature=manifest.sign(private)
        )
        assert result.is_trustworthy

    def test_a_signature_offered_without_a_key_is_a_no_not_an_absence(self, bundle) -> None:
        """A verifier that skipped it would report an unverifiable signature as
        "unsigned", which reads as a packaging oversight rather than a claim
        nobody could stand up."""
        root, manifest = bundle, build_manifest(bundle, created_at=WHEN)
        result = verify(root, manifest, signature=manifest.sign(self.key()))
        assert result.signature_holds is False
        assert not result.is_trustworthy

    def test_an_unsigned_bundle_is_still_untrustworthy(self, bundle) -> None:
        root, manifest = bundle, build_manifest(bundle, created_at=WHEN)
        result = verify(root, manifest)
        assert result.signature_holds is None
        assert not result.is_trustworthy

    def test_a_signed_bundle_with_a_modified_file_is_untrustworthy(self, bundle) -> None:
        """The signature covers the manifest, so a file changed after sealing
        is caught by the hashes and not by the signature. Both have to hold."""
        root, manifest = bundle, build_manifest(bundle, created_at=WHEN)
        private = self.key()
        signature = manifest.sign(private)
        (root / manifest.entries[0].path).write_text("different", encoding="utf-8")
        result = verify(root, manifest, public_key=private.public_key(), signature=signature)
        assert result.signature_holds is True
        assert result.modified
        assert not result.is_trustworthy

    def test_the_module_says_image_signing_is_not_this(self) -> None:
        """Signing the OCI image needs cosign and a registry, neither of which
        has been exercised."""
        from prama.security import bundle

        assert "Container image signing is a separate thing" in (bundle.__doc__ or "")


class TestTheAirGappedCase:
    """The receiving host has the publisher's public key and was never given
    the sender's HMAC key. That is the normal case, and the first version
    reported it as a signature failure — sending an operator to look for
    tampering that had not happened.
    """

    def key(self):
        pytest.importorskip("cryptography", reason="needs the 'sso' extra")
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        return Ed25519PrivateKey.generate()

    def test_a_holding_signature_with_a_failing_seal_is_not_a_finding(self, bundle) -> None:
        manifest = build_manifest(bundle, created_at=WHEN)
        private = self.key()
        result = verify(
            bundle,
            manifest,
            key=b"the-receiving-host-key",
            seal=manifest.seal(b"the-sending-host-key"),
            public_key=private.public_key(),
            signature=manifest.sign(private),
        )
        assert result.is_trustworthy
        assert "does not verify" not in result.describe()

    def test_it_names_which_signature_vouched(self, bundle) -> None:
        """ "The signature holds" over two different signatures would let a
        reader take a deployment's own HMAC for publisher provenance, which is
        the stronger claim and the one they came for."""
        manifest = build_manifest(bundle, created_at=WHEN)
        private = self.key()
        described = verify(
            bundle,
            manifest,
            public_key=private.public_key(),
            signature=manifest.sign(private),
        ).describe()
        assert "the publisher signature holds" in described

    def test_a_seal_alone_says_no_publisher_signature_was_checked(self, bundle) -> None:
        manifest = build_manifest(bundle, created_at=WHEN)
        described = verify(bundle, manifest, key=KEY, seal=manifest.seal(KEY)).describe()
        assert "no publisher signature was checked" in described

    def test_both_holding_says_both(self, bundle) -> None:
        manifest = build_manifest(bundle, created_at=WHEN)
        private = self.key()
        described = verify(
            bundle,
            manifest,
            key=KEY,
            seal=manifest.seal(KEY),
            public_key=private.public_key(),
            signature=manifest.sign(private),
        ).describe()
        assert "both the publisher signature and this deployment's seal hold" in described

    def test_a_failing_publisher_signature_is_always_reported(self, bundle) -> None:
        """Even when the seal holds: somebody signed this and it was not who
        the key says."""
        manifest = build_manifest(bundle, created_at=WHEN)
        result = verify(
            bundle,
            manifest,
            key=KEY,
            seal=manifest.seal(KEY),
            public_key=self.key().public_key(),
            signature=manifest.sign(self.key()),
        )
        assert not result.is_trustworthy
        assert "signed by somebody else" in result.describe()

    def test_the_signature_files_are_not_unsigned_for(self, bundle) -> None:
        """The manifest and the signatures over it cannot appear in the file
        list they sign. Listing them made a correctly signed bundle read as
        carrying a stray file."""
        manifest = build_manifest(bundle, created_at=WHEN)
        (bundle / "manifest.ed25519").write_text("deadbeef")
        (bundle / "manifest.sig").write_text("deadbeef")
        assert verify(bundle, manifest).unexpected == ()
