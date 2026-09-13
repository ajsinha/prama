"""A bundle verifier must be able to say no.

QA round 2, `SEC-142`, `SEC-140` and `SEC-144`. Three ways the offline bundle
check reported "trustworthy" about something it had not established.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path

from prama.security.bundle import Entry, Manifest, verify

KEY = b"a-local-sealing-key"


def _bundle(tmp_path: Path) -> tuple[Path, Manifest]:
    """A small, honest bundle: two files and a manifest that describes them."""
    root = tmp_path / "offline"
    root.mkdir()
    entries = []
    for name, body in (("prama.whl", b"wheel-bytes"), ("chart.tgz", b"chart-bytes")):
        (root / name).write_bytes(body)
        entries.append(Entry(path=name, sha256=hashlib.sha256(body).hexdigest(), bytes=len(body)))
    manifest = Manifest(
        product="prama",
        version="0.1.0",
        created_at="2026-09-13T00:00:00Z",
        entries=tuple(entries),
    )
    # A real bundle carries its manifest on disk, and that file is where the
    # claim being checked has to come from.
    (root / "manifest.json").write_text(json.dumps(manifest.to_dict()))
    return root, manifest


def test_an_honest_bundle_verifies(tmp_path: Path) -> None:
    """The counterfactual for everything below.

    If the verifier refused this, the refusals in the other tests would prove
    nothing — a check that says no to everything is not a check.
    """
    root, manifest = _bundle(tmp_path)
    result = verify(root, manifest, key=KEY, seal=manifest.seal(KEY))
    assert result.is_trustworthy
    assert result.manifest_intact


def test_an_edited_manifest_is_not_intact(tmp_path: Path) -> None:
    """`manifest_intact` compared a computed hash against itself.

    `content_hash` is a property — `sha256(self.content())` — so
    `stored == sha256(content())` is `X == X`. Editing the manifest changes
    both sides together, and the field could never be False. Worse, the loader
    reads every field from `manifest.json` *except* `content_hash`, so the one
    number written down to be checked against was discarded on the way in.
    """
    root, manifest = _bundle(tmp_path)

    # An attacker rewrites the file list to describe what they shipped. The
    # manifest.json on disk still states the honest hash, and that mismatch is
    # the whole signal.
    tampered = dataclasses.replace(
        manifest,
        entries=(Entry(path="prama.whl", sha256="00" * 32, bytes=11),),
    )
    result = verify(root, tampered, key=KEY, seal=manifest.seal(KEY))
    assert not result.manifest_intact
    assert not result.is_trustworthy


def test_a_file_nobody_signed_for_makes_the_bundle_untrustworthy(tmp_path: Path) -> None:
    """An unlisted file is one nobody signed for, and it installs anyway.

    The verifier already detects it and names it in `describe()`. It simply
    was not part of `is_trustworthy`, so an operator reading the exit code
    rather than the prose installed it.
    """
    root, manifest = _bundle(tmp_path)
    (root / "evil.whl").write_bytes(b"not-in-the-manifest")

    result = verify(root, manifest, key=KEY, seal=manifest.seal(KEY))
    assert result.unexpected == ("evil.whl",)
    assert not result.is_trustworthy


def test_a_missing_or_modified_file_still_disqualifies(tmp_path: Path) -> None:
    """Pinned so the fixes above cannot come at the cost of what worked."""
    root, manifest = _bundle(tmp_path)
    (root / "prama.whl").write_bytes(b"different-bytes")
    modified = verify(root, manifest, key=KEY, seal=manifest.seal(KEY))
    assert modified.modified == ("prama.whl",)
    assert not modified.is_trustworthy

    (root / "prama.whl").unlink()
    missing = verify(root, manifest, key=KEY, seal=manifest.seal(KEY))
    assert missing.missing == ("prama.whl",)
    assert not missing.is_trustworthy


class TestAStrippedSignatureIsARemovalNotAnAbsence:
    """Deleting `manifest.ed25519` used to leave a bundle verifying clean.

    The verifier saw no signature offered and reported `signature_holds=None`
    — "none was checked", not "one failed" — then fell through to the local
    HMAC seal, which is produced by the very host that stripped the signature.
    The publisher's guarantee could be removed by anyone who could edit the
    directory, and nothing said so (QA finding SEC-144, and Q-19 before it).

    The fix records `publisher_signed` *inside* the manifest's hashed content,
    so the claim that a signature exists is covered by the seal and the
    signature alike. Retracting it now breaks the manifest.
    """

    def test_a_manifest_that_claims_a_signature_must_be_given_one(self, tmp_path: Path) -> None:
        root, manifest = _bundle(tmp_path)
        signed_manifest = dataclasses.replace(manifest, publisher_signed=True)
        (root / "manifest.json").write_text(json.dumps(signed_manifest.to_dict()))

        # Sealed correctly, files intact — and the signature file removed.
        result = verify(
            root,
            signed_manifest,
            key=KEY,
            seal=signed_manifest.seal(KEY),
            signature="",
        )
        assert result.signature_holds is False, (
            "a missing signature under a manifest that claims one read as "
            "'unsigned bundle' and fell back to the local seal"
        )
        assert not result.is_trustworthy

    def test_a_bundle_that_never_claimed_a_signature_is_unaffected(self, tmp_path: Path) -> None:
        """The counterfactual.

        Most bundles are sealed and not signed. If the fix made every unsigned
        bundle untrustworthy it would pass the test above by breaking the
        ordinary case, which is the air-gapped install this whole mechanism
        exists for.
        """
        root, manifest = _bundle(tmp_path)
        result = verify(root, manifest, key=KEY, seal=manifest.seal(KEY), signature="")
        assert result.signature_holds is None
        assert result.is_trustworthy
