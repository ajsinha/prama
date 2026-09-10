"""The offline bundle.

A bank that will not let a control plane reach the internet still has to install
it and prove to an auditor that what it installed is what was shipped. A bundle
is therefore not an archive — it is an archive plus a statement about the
archive that somebody can check.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
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
        assert "the signature holds" in result.describe()

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
