"""The offline bundle: what an air-gapped install receives, and how it is checked.

A bank that will not let a control plane reach the internet still has to install
it, upgrade it, and prove to an auditor that what it installed is what was
shipped. That last part is the whole design here — a bundle is not an archive,
it is *an archive plus a statement about the archive that somebody can check*.

Three properties, and each is a way the obvious implementation is useless:

* **The manifest is hashed, and the hash is what gets signed.** Signing the
  archive means re-hashing gigabytes to verify one file, so nobody does it on a
  restore. Signing a manifest of per-file hashes means verification is cheap and
  can name *which* file is wrong.
* **A missing file and a modified file are different findings.** "Verification
  failed" sends an operator to their network team; "wheel X is present and its
  hash does not match" sends them to whoever built the bundle.
* **An unsigned bundle is not a bundle.** It verifies internally and proves
  nothing about origin, so ``verify`` reports the signature's absence as loudly
  as a mismatch rather than passing on the hashes alone.

**Two signatures, and they say different things.**

The **HMAC seal** establishes that the bundle was sealed by a holder of the
deployment's key, and nothing at all to anybody who does not hold it. It is
fine for a deployment checking its own artefacts and useless as provenance.

The **Ed25519 signature** is the one that matters air-gapped. A customer holding
only Prama's *public* key can verify the bundle came from whoever holds the
private half — which is the entire question an auditor asks about an artefact
that arrived on a disk. Verification needs nothing secret, so the key can be
published, pinned, and checked by somebody with no relationship to the sender.

Both are optional and neither is assumed. ``verify`` reports each separately,
because "sealed by us" and "signed by the publisher" are different claims and a
single boolean would collapse them. What it will not do is treat an absent
signature as a passing one: an unsigned bundle verifies internally and proves
nothing about origin, and in an air-gapped install there is nothing else to
check it against.

**Container image signing is a separate thing and is not done here.** This signs
the offline bundle. Signing the OCI image needs cosign and a registry, neither
of which has been exercised.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import hashlib
import hmac
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from prama.core.errors import ValidationError
from prama.version import PRODUCT_NAME, VERSION

MANIFEST_VERSION = "1.0"
#: Read in blocks so a multi-gigabyte image does not have to fit in memory —
#: which is exactly the file an offline bundle carries.
_BLOCK = 1024 * 1024


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_BLOCK):
            sha.update(chunk)
    return sha.hexdigest()


@dataclasses.dataclass(frozen=True, slots=True)
class Entry:
    """One file in the bundle."""

    path: str
    sha256: str
    bytes: int
    #: ``image`` · ``chart`` · ``wheel`` · ``schema`` · ``model`` · ``other``
    kind: str = "other"

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "bytes": self.bytes,
            "kind": self.kind,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Manifest:
    """What the bundle contains, and what it is for.

    Includes an SBOM of the Python distributions, because "what is in this
    thing" is the first question a bank's security team asks and the answer
    cannot be produced later from an air-gapped host.
    """

    product: str
    version: str
    created_at: str
    entries: tuple[Entry, ...] = ()
    #: name -> version, for everything installed.
    sbom: tuple[tuple[str, str], ...] = ()
    manifest_version: str = MANIFEST_VERSION
    #: Whether a publisher signature was made over this manifest. Set at seal
    #: time and covered by `content_hash`, so it cannot be edited away.
    publisher_signed: bool = False

    @property
    def total_bytes(self) -> int:
        return sum(entry.bytes for entry in self.entries)

    def content(self) -> str:
        """The canonical bytes that get hashed and signed.

        Sorted and separator-fixed, so the same bundle produces the same digest
        on any machine. A manifest whose serialisation varied would make a
        signature depend on the JSON library, and a verification failure would
        then mean nothing.
        """
        return json.dumps(
            {
                "manifest_version": self.manifest_version,
                "product": self.product,
                "version": self.version,
                "created_at": self.created_at,
                "entries": [
                    entry.to_dict() for entry in sorted(self.entries, key=lambda e: e.path)
                ],
                "sbom": [list(item) for item in sorted(self.sbom)],
                # Inside the hashed content on purpose. Without it, deleting
                # `manifest.ed25519` left nothing to notice: the verifier saw
                # no signature offered, reported `signature_holds=None` — "none
                # was checked", not "one failed" — and fell through to the
                # local seal, which the host that stripped it can produce
                # (QA finding SEC-144, and Q-19 before it).
                #
                # A claim not covered by the hash is a claim an attacker can
                # retract. This one is covered, so retracting it breaks the
                # manifest instead of going unnoticed.
                "publisher_signed": self.publisher_signed,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content().encode("utf-8")).hexdigest()

    def seal(self, key: bytes) -> str:
        """An HMAC over the manifest's hash.

        Says the manifest was sealed by a holder of this key, and nothing to
        anybody who does not hold it. Use :meth:`sign` for provenance somebody
        else can check.
        """
        return hmac.new(key, self.content_hash.encode("ascii"), hashlib.sha256).hexdigest()

    def sign(self, private_key: Any) -> str:
        """An Ed25519 signature over the manifest's hash, hex encoded.

        This is the one that survives leaving the building. A customer with only
        the public half can establish that the bundle came from whoever holds
        the private half, which is what an auditor asks about an artefact that
        arrived on a disk.

        Signed over the content hash rather than the bundle, so verification
        stays cheap: re-hashing gigabytes to check one file is a verification
        nobody performs on a restore.
        """
        signature: bytes = private_key.sign(self.content_hash.encode("ascii"))
        return signature.hex()

    def signature_holds(self, public_key: Any, signature: str) -> bool:
        """Whether ``signature`` was made over this manifest by that key."""
        try:
            public_key.verify(bytes.fromhex(signature), self.content_hash.encode("ascii"))
        except Exception:
            # Every failure is one answer: no. Distinguishing a malformed
            # signature from a wrong one tells an attacker which half to vary.
            return False
        return True

    def entry(self, path: str) -> Entry | None:
        return next((e for e in self.entries if e.path == path), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            **json.loads(self.content()),
            "content_hash": self.content_hash,
            "total_bytes": self.total_bytes,
            "files": len(self.entries),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Verification:
    """What checking a bundle found."""

    checked: int = 0
    #: Files the manifest lists and the bundle does not have. A network or
    #: transfer problem.
    missing: tuple[str, ...] = ()
    #: Files present whose hash does not match. A build or tampering problem —
    #: a different person, and a different response.
    modified: tuple[str, ...] = ()
    #: Files present that the manifest does not list. Not automatically wrong,
    #: and worth saying: an unlisted file is one nobody signed for.
    unexpected: tuple[str, ...] = ()
    manifest_intact: bool = True
    #: None when no seal was offered — which is not the same as a bad one.
    seal_holds: bool | None = None
    #: None when no Ed25519 signature was offered. Kept apart from the seal
    #: because "sealed by us" and "signed by the publisher" are different
    #: claims, and one boolean would collapse them.
    signature_holds: bool | None = None

    @property
    def is_trustworthy(self) -> bool:
        """Whether this bundle may be installed.

        A verified signature is required. An unsigned bundle verifies internally
        and proves nothing about origin, and in an air-gapped install there is
        nothing else to check it against.
        """
        if self.signature_holds is False:
            # A signature that was offered and did not verify is disqualifying
            # on its own. Somebody signed this and it was not who the key says,
            # and a holding local seal does not answer that — it says only that
            # whoever put it on this host had this host's key.
            return False
        return (
            self.manifest_intact
            and not self.missing
            and not self.modified
            # An unlisted file is one nobody signed for, and it installs with
            # the rest. The verifier already found it and already said so in
            # `describe()`; it simply was not part of this answer, so anybody
            # reading the exit code rather than the prose installed it anyway
            # (QA finding SEC-140, and finding Q-18 before it).
            and not self.unexpected
            # Either signature suffices. The air-gapped receiver has the
            # publisher's public key and not the sender's HMAC key; requiring
            # both would make the case this exists for impossible.
            and (self.seal_holds is True or self.signature_holds is True)
        )

    def describe(self) -> str:
        if not self.manifest_intact:
            return (
                "The manifest does not hash to its stated value, so nothing else in "
                "this bundle can be trusted — including the file list itself."
            )
        parts: list[str] = []
        # Modified before missing: a modified file is a build or tampering
        # problem and goes to whoever made the bundle, where a missing one is a
        # transfer problem and goes to the network team. Sending an operator to
        # the wrong one costs the first hour.
        if self.modified:
            parts.append(
                f"{len(self.modified)} file(s) present with the wrong hash — this is a "
                f"build or tampering problem, not a transfer one: {', '.join(self.modified[:5])}"
            )
        if self.missing:
            parts.append(
                f"{len(self.missing)} file(s) listed and absent — a transfer problem: "
                f"{', '.join(self.missing[:5])}"
            )
        if self.unexpected:
            parts.append(
                f"{len(self.unexpected)} file(s) present that nobody signed for: "
                f"{', '.join(self.unexpected[:5])}"
            )
        # The two signatures are reported apart, and a failing *seal* alongside
        # a holding *publisher signature* is not a finding at all — it is the
        # normal air-gapped case, where the receiving host has the publisher's
        # public key and was never given the sender's HMAC key. Reporting it as
        # a failure sent an operator to look for tampering that had not
        # happened.
        if self.signature_holds is False:
            parts.append(
                "the publisher signature does not verify against the key given: the "
                "bundle was altered, or signed by somebody else"
            )
        if self.seal_holds is False and self.signature_holds is not True:
            parts.append(
                "the seal does not verify against this deployment's key: the bundle "
                "was altered, or sealed elsewhere"
            )
        if self.seal_holds is None and self.signature_holds is None:
            parts.append(
                "no signature was offered, so this bundle proves nothing about where "
                "it came from — it is internally consistent and could have been built "
                "by anybody"
            )
        if not parts:
            return f"{self.checked} file(s) verified, and {self._who_vouched()}."
        return "; ".join(parts) + f". {self.checked} file(s) checked."

    def _who_vouched(self) -> str:
        """Which signature actually held, said precisely.

        "the signature holds" over two different signatures would let a reader
        take a deployment's own HMAC for publisher provenance, which is the
        stronger claim and the one they came for.
        """
        if self.signature_holds and self.seal_holds:
            return "both the publisher signature and this deployment's seal hold"
        if self.signature_holds:
            return "the publisher signature holds"
        return "this deployment's seal holds — no publisher signature was checked"

    def to_dict(self) -> dict[str, Any]:
        return {
            "checked": self.checked,
            "missing": list(self.missing),
            "modified": list(self.modified),
            "unexpected": list(self.unexpected),
            "manifest_intact": self.manifest_intact,
            "seal_holds": self.seal_holds,
            "trustworthy": self.is_trustworthy,
            "message": self.describe(),
        }


def _kind_of(relative: Path) -> str:
    suffix = relative.suffix.lower()
    if suffix in (".tar", ".tgz") and "image" in relative.parts[0:1]:
        return "image"
    if suffix == ".whl":
        return "wheel"
    if suffix == ".sql":
        return "schema"
    if relative.parts and relative.parts[0] == "chart":
        return "chart"
    if relative.parts and relative.parts[0] == "model":
        return "model"
    if relative.parts and relative.parts[0] == "image":
        return "image"
    return "other"


def build_manifest(
    root: Path, *, created_at: str, sbom: Iterable[tuple[str, str]] = ()
) -> Manifest:
    """Catalogue a directory into a manifest.

    The manifest itself and any signature are excluded: a manifest that listed
    its own hash could never be produced, and one that listed the signature
    would change the thing the signature covers.
    """
    if not root.is_dir():
        raise ValidationError(
            f"there is no bundle directory at {root}",
            remedy="Point at the directory holding the images, chart and wheels.",
            context={"root": str(root)},
        )
    entries: list[Entry] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if relative.name in ("manifest.json", "manifest.sig"):
            continue
        entries.append(
            Entry(
                path=str(relative),
                sha256=digest(path),
                bytes=path.stat().st_size,
                kind=_kind_of(relative),
            )
        )
    return Manifest(
        product=PRODUCT_NAME,
        version=VERSION,
        created_at=created_at,
        entries=tuple(entries),
        sbom=tuple(sorted(sbom)),
    )


def _declared_on_disk(root: Path) -> str:
    """The ``content_hash`` the bundle's own ``manifest.json`` states.

    Read from the file rather than taken from the parsed object, because the
    parsed object hashes to whatever the file says — which is precisely how
    this check became a tautology (QA finding SEC-142). The claim has to come
    from outside the thing being checked or it is not a check.
    """
    path = root / "manifest.json"
    if not path.is_file():
        return ""
    try:
        return str(json.loads(path.read_text(encoding="utf-8")).get("content_hash", ""))
    except (OSError, ValueError):
        # Unreadable or malformed is not "no claim" — it is a bundle that
        # cannot be verified, and the empty string makes `intact` False.
        return ""


def verify(
    root: Path,
    manifest: Manifest,
    *,
    key: bytes | None = None,
    seal: str = "",
    public_key: Any = None,
    signature: str = "",
    declared_hash: str = "",
) -> Verification:
    """Check a bundle against its manifest, naming what is wrong and how.

    ``declared_hash`` is the ``content_hash`` as written in ``manifest.json``,
    read from the file rather than recomputed. When not supplied it is read
    from ``root/manifest.json`` directly, so the check holds even for a caller
    that does not know to pass it — the claim must come from outside the object
    being checked, or it is not a check at all. Without it this check was a
    tautology: ``content_hash`` is a property over the manifest's own content,
    so ``manifest.content_hash == sha256(manifest.content())`` compared a value
    against itself and `manifest_intact` could never be False (QA finding
    SEC-142). The loader compounded it by reading every field from the JSON
    *except* that one — the single number written down in order to be checked
    against was discarded on the way in.
    """
    computed = hashlib.sha256(manifest.content().encode("utf-8")).hexdigest()
    declared = declared_hash or _declared_on_disk(root)
    # Fails closed. A bundle that states no hash cannot have its manifest
    # checked, and "cannot be checked" is not "passes" — that conflation is the
    # family of defect this whole round kept turning up.
    intact = bool(declared) and hmac.compare_digest(declared, computed)

    missing: list[str] = []
    modified: list[str] = []
    checked = 0
    for entry in manifest.entries:
        path = root / entry.path
        if not path.is_file():
            missing.append(entry.path)
            continue
        checked += 1
        if digest(path) != entry.sha256:
            modified.append(entry.path)

    listed = {entry.path for entry in manifest.entries}
    unexpected = sorted(
        str(path.relative_to(root))
        for path in root.rglob("*")
        if path.is_file()
        # The manifest and the signatures over it cannot appear in the file
        # list they sign, so they are not "unsigned for" — listing them as such
        # made a correctly signed bundle read as carrying a stray file.
        and path.name not in ("manifest.json", "manifest.sig", "manifest.ed25519")
        and str(path.relative_to(root)) not in listed
    )

    holds: bool | None = None
    if seal:
        holds = bool(key) and hmac.compare_digest(manifest.seal(key or b""), seal)

    signed: bool | None = None
    if manifest.publisher_signed and not signature:
        # The manifest says it was signed and nothing came with it. That is a
        # removal, not an absence, and it is the one case that must not read as
        # "unsigned bundle, fall back to the local seal".
        signed = False
    elif signature:
        # Offered without a key to check it against is a no, not an absence: a
        # verifier that skipped it would report an unverifiable signature as
        # "unsigned", which reads as a packaging oversight rather than a claim
        # nobody could stand up.
        signed = public_key is not None and manifest.signature_holds(public_key, signature)

    return Verification(
        checked=checked,
        missing=tuple(missing),
        modified=tuple(modified),
        unexpected=tuple(unexpected),
        manifest_intact=intact,
        seal_holds=holds,
        signature_holds=signed,
    )


def installed_distributions() -> list[tuple[str, str]]:
    """The SBOM. What is actually installed, not what was asked for.

    ``pyproject.toml`` states floors; this states what resolved. A bundle whose
    SBOM listed the requirements would be describing a different install from
    the one it carries.
    """
    from importlib.metadata import distributions

    seen: dict[str, str] = {}
    for distribution in distributions():
        name = distribution.metadata["Name"]
        if name:
            seen[name] = distribution.version or ""
    return sorted(seen.items())


__all__ = [
    "MANIFEST_VERSION",
    "Entry",
    "Manifest",
    "Verification",
    "build_manifest",
    "digest",
    "installed_distributions",
    "verify",
]
