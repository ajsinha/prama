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

**The signature is an HMAC and says so.** It establishes that the bundle was
sealed by a holder of the deployment's key and nothing to anybody else — the
same limit the attestation seal carries. An asymmetric signature would say more;
this does not, and pretending otherwise in an air-gapped install is worse than
in a connected one, because there is nothing else to check against.

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
        anybody who does not hold it. An asymmetric signature would say more;
        this does not, and the readout says so.
        """
        return hmac.new(key, self.content_hash.encode("ascii"), hashlib.sha256).hexdigest()

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
    #: None when no signature was offered — which is not the same as a bad one.
    seal_holds: bool | None = None

    @property
    def is_trustworthy(self) -> bool:
        """Whether this bundle may be installed.

        A verified signature is required. An unsigned bundle verifies internally
        and proves nothing about origin, and in an air-gapped install there is
        nothing else to check it against.
        """
        return (
            self.manifest_intact
            and not self.missing
            and not self.modified
            and self.seal_holds is True
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
        if self.seal_holds is None:
            parts.append(
                "no signature was offered, so this bundle proves nothing about where "
                "it came from — it is internally consistent and could have been built "
                "by anybody"
            )
        elif not self.seal_holds:
            parts.append(
                "the signature does not verify against this deployment's key: the "
                "bundle was altered, or sealed elsewhere"
            )
        if not parts:
            return f"{self.checked} file(s) verified, and the signature holds."
        return "; ".join(parts) + f". {self.checked} file(s) checked."

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


def verify(
    root: Path, manifest: Manifest, *, key: bytes | None = None, seal: str = ""
) -> Verification:
    """Check a bundle against its manifest, naming what is wrong and how."""
    stored_hash = manifest.content_hash
    intact = stored_hash == hashlib.sha256(manifest.content().encode("utf-8")).hexdigest()

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
        and path.name not in ("manifest.json", "manifest.sig")
        and str(path.relative_to(root)) not in listed
    )

    holds: bool | None = None
    if seal:
        holds = bool(key) and hmac.compare_digest(manifest.seal(key or b""), seal)

    return Verification(
        checked=checked,
        missing=tuple(missing),
        modified=tuple(modified),
        unexpected=tuple(unexpected),
        manifest_intact=intact,
        seal_holds=holds,
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
