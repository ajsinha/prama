"""``prama bundle`` — sealing an offline install, and checking one.

The two commands an air-gapped deployment runs: one on the machine that can
reach the internet, one on the machine that cannot.

    prama bundle seal   ./offline      # where the images and wheels were staged
    prama bundle verify ./offline      # on the air-gapped host, before installing

``verify`` exits 3 on a bundle that must not be installed, distinct from 1 for a
check that could not be made — the same distinction ``prama contract check``
draws, and for the same reason: an operator has to tell "this bundle is wrong"
from "I ran the command wrong", and on an air-gapped host there is nobody to
ask.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from prama.cli.base import EXIT_DRIFT, EXIT_OK, Command, CommandContext, CommandGroup
from prama.core.errors import ValidationError
from prama.security.bundle import (
    Manifest,
    build_manifest,
    installed_distributions,
    verify,
)

MANIFEST = "manifest.json"
SIGNATURE = "manifest.sig"
#: The Ed25519 signature, kept in its own file. Two signatures in one file would
#: make a verifier that reads the wrong line report a valid bundle as forged.
PUBLISHER_SIGNATURE = "manifest.ed25519"


def _key(ctx: CommandContext) -> bytes:
    secret: str = ctx.config.require_secret("security.session_secret")
    return secret.encode()


def _private_key(path: str) -> object:
    """A signing key from a PEM file.

    Read here rather than taken as a hex string on the command line: a private
    key on an argv is a private key in the shell history and in every process
    listing on the machine while the command runs.
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    target = Path(path)
    try:
        data = target.read_bytes()
    except OSError as exc:
        raise ValidationError(
            f"{target} could not be read: {exc.strerror or exc}",
            remedy="--sign-with names a PEM file holding an Ed25519 private key.",
            context={"path": str(target)},
        ) from None

    try:
        key = load_pem_private_key(data, password=None)
    except (ValueError, TypeError) as exc:
        # A malformed PEM, or one that is encrypted, came back as
        # `ValueError: Unable to load PEM file ... MalformedFraming` with a link
        # to somebody else's FAQ. QA round 4, `CLI-198`.
        raise ValidationError(
            f"{target} is not an unencrypted PEM private key: {exc}",
            remedy=(
                "Give an unencrypted Ed25519 private key in PEM form. An "
                "encrypted key cannot be used here, because a bundle is sealed "
                "without anybody present to type a passphrase."
            ),
            context={"path": str(target)},
        ) from None

    if not isinstance(key, Ed25519PrivateKey):
        # The signature this produces is Ed25519 by design — `Manifest.sign`
        # calls `private_key.sign(data)` with no padding or algorithm, which is
        # the Ed25519 interface. An RSA key reached that call and returned
        # `TypeError: sign() missing 2 required positional arguments`, naming a
        # method nobody invoked. QA round 4, `SEC-166`.
        raise ValidationError(
            f"{target} holds a {type(key).__name__.removesuffix('PrivateKey')} key, "
            "and a bundle is signed with Ed25519",
            remedy=(
                "Generate one with `openssl genpkey -algorithm ed25519 -out key.pem`. "
                "The signature format is fixed so that a customer checking a bundle "
                "offline needs no algorithm negotiation."
            ),
            context={"path": str(target), "key_type": type(key).__name__},
        )
    return key


def _public_key(path: str) -> object:
    from cryptography.hazmat.primitives.serialization import load_pem_public_key

    return load_pem_public_key(Path(path).read_bytes())


def _entry_field(entry: object, field: str, path: Path) -> Any:
    """One field of one manifest entry, or a refusal naming what is missing.

    Indexed directly until round 4, so a hand-edited manifest produced a
    `KeyError` with a bare field name and no indication of which file it came
    from. QA `SEC-161`, `CLI-208`, `CLI-209`.
    """
    if not isinstance(entry, dict) or field not in entry:
        raise ValidationError(
            f"an entry in {path} has no {field!r}",
            remedy="Every entry names its path, its sha256 and its size. Reseal the bundle.",
            context={"path": str(path), "field": field},
        )
    return entry[field]


def _load(root: Path) -> tuple[Manifest, str]:
    from prama.security.bundle import Entry

    path = root / MANIFEST
    if not path.exists():
        raise ValidationError(
            f"there is no {MANIFEST} in {root}",
            remedy=(
                "This is a directory of files, not a bundle. A bundle carries a "
                "manifest, because without one there is nothing to check the "
                "files against."
            ),
            context={"root": str(root)},
        )
    # A manifest that is not JSON, or is JSON missing a field this indexes
    # directly below, used to reach the terminal as a json.decoder or KeyError
    # traceback. The person holding the bundle is deciding whether to install
    # it; a stack trace is not an answer to that question. QA round 4, B13.
    try:
        payload = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise ValidationError(
            f"{path} is not readable as a manifest: {exc}",
            remedy=(
                "A bundle's manifest is JSON written by `prama bundle seal`. "
                "If this was edited by hand, reseal it."
            ),
            context={"path": str(path)},
        ) from None
    if not isinstance(payload, dict):
        raise ValidationError(
            f"{path} does not hold a manifest object",
            remedy="A manifest is a JSON object. Reseal the bundle.",
            context={"path": str(path)},
        )
    missing = [key for key in ("product", "version", "created_at", "entries") if key not in payload]
    if missing:
        raise ValidationError(
            f"{path} is missing {', '.join(missing)}",
            remedy=(
                "Every manifest names the product, its version, when it was "
                "sealed and what it contains. Reseal the bundle."
            ),
            context={"path": str(path), "missing": ", ".join(missing)},
        )
    # The declared hash is returned beside the manifest rather than folded into
    # it. It is what the *file* claims, and verification exists to compare that
    # claim against a recomputation — a Manifest rebuilt from this same JSON
    # hashes to whatever the JSON says, which is exactly how the check became a
    # tautology (QA finding SEC-142).
    declared = str(payload.get("content_hash", ""))
    return Manifest(
        product=payload["product"],
        version=payload["version"],
        created_at=payload["created_at"],
        entries=tuple(
            Entry(
                path=_entry_field(entry, "path", path),
                sha256=_entry_field(entry, "sha256", path),
                bytes=_entry_field(entry, "bytes", path),
                kind=entry.get("kind", "other") if isinstance(entry, dict) else "other",
            )
            for entry in payload["entries"]
        ),
        sbom=tuple((name, version) for name, version in payload.get("sbom", [])),
        manifest_version=payload.get("manifest_version", "1.0"),
        publisher_signed=bool(payload.get("publisher_signed", False)),
    ), declared


class BundleSealCommand(Command):
    name = "seal"
    help = "catalogue a staged directory and sign its manifest"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("root", help="the directory holding images, chart and wheels")
        parser.add_argument(
            "--sign-with",
            metavar="KEY.pem",
            help=(
                "an Ed25519 private key in PEM. Produces a signature an "
                "air-gapped customer can check with the public half alone"
            ),
        )
        parser.add_argument(
            "--no-sbom",
            action="store_true",
            help="omit the dependency list. Rarely right: it is the first thing a "
            "bank's security team asks for and cannot be produced later from an "
            "air-gapped host",
        )

    def run(self, ctx: CommandContext) -> int:
        from prama.core.clock import utc_now

        root = Path(ctx.args.root)
        import dataclasses

        manifest = build_manifest(
            root,
            created_at=utc_now().isoformat(),
            sbom=() if ctx.args.no_sbom else installed_distributions(),
        )
        # Decided before anything is hashed. `publisher_signed` is part of the
        # manifest's content, so the seal and the signature both cover the
        # claim that a signature exists — which is what makes deleting the
        # signature file detectable rather than silent.
        manifest = dataclasses.replace(manifest, publisher_signed=bool(ctx.args.sign_with))
        seal = manifest.seal(_key(ctx))

        (root / MANIFEST).write_text(json.dumps(manifest.to_dict(), indent=2) + "\n")
        (root / SIGNATURE).write_text(seal + "\n")

        signed = ""
        if ctx.args.sign_with:
            signed = manifest.sign(_private_key(ctx.args.sign_with))
            (root / PUBLISHER_SIGNATURE).write_text(signed + "\n")

        if ctx.json_output:
            ctx.emit_json(
                {
                    "root": str(root),
                    "files": len(manifest.entries),
                    "bytes": manifest.total_bytes,
                    "content_hash": manifest.content_hash,
                    "sbom": len(manifest.sbom),
                    "publisher_signature": bool(signed),
                }
            )
            return EXIT_OK
        ctx.emit(
            f"sealed {len(manifest.entries)} file(s), {manifest.total_bytes / 1_048_576:.1f} MiB"
        )
        ctx.emit(f"  manifest: {manifest.content_hash}")
        ctx.emit(f"  sbom:     {len(manifest.sbom)} distribution(s)")
        ctx.emit()
        # Said here rather than left to a README, because this is the moment
        # somebody decides how much the signature is worth.
        ctx.emit("The seal is an HMAC over the manifest hash. It says the bundle was")
        ctx.emit("sealed by a holder of this deployment's key, and nothing to anybody")
        ctx.emit("who does not hold it.")
        if signed:
            ctx.emit()
            ctx.emit("An Ed25519 signature is also written. That one a customer can check")
            ctx.emit("with the public half alone, which is what an auditor asks about an")
            ctx.emit("artefact that arrived on a disk.")
        else:
            # Said on the success path, because this is the moment somebody
            # decides how much the signature is worth.
            ctx.emit()
            ctx.emit("No publisher signature: --sign-with was not given. An air-gapped")
            ctx.emit("customer cannot check an HMAC without the key, so this bundle")
            ctx.emit("carries no provenance they can verify.")
        return EXIT_OK


class BundleVerifyCommand(Command):
    name = "verify"
    help = "check a bundle before installing it; non-zero if it must not be"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("root")
        parser.add_argument(
            "--publisher-key",
            metavar="KEY.pem",
            help="the publisher's Ed25519 public key, to check provenance",
        )

    def run(self, ctx: CommandContext) -> int:
        root = Path(ctx.args.root)
        manifest, declared = _load(root)
        signature = root / SIGNATURE
        seal = signature.read_text().strip() if signature.exists() else ""
        publisher = root / PUBLISHER_SIGNATURE
        signed = publisher.read_text().strip() if publisher.exists() else ""

        result = verify(
            root,
            manifest,
            key=_key(ctx),
            seal=seal,
            public_key=_public_key(ctx.args.publisher_key) if ctx.args.publisher_key else None,
            signature=signed,
            declared_hash=declared,
        )

        if ctx.json_output:
            ctx.emit_json({**result.to_dict(), "version": manifest.version})
            return EXIT_OK if result.is_trustworthy else EXIT_DRIFT

        ctx.emit(f"{manifest.product} {manifest.version}, sealed {manifest.created_at}")
        ctx.emit(result.describe())
        if signed and not ctx.args.publisher_key:
            # Not silence: an unverifiable signature reported as nothing reads
            # as an unsigned bundle, which is a different and lesser problem.
            ctx.emit()
            ctx.emit("This bundle carries a publisher signature and no key was given to")
            ctx.emit("check it against. Pass --publisher-key to establish where it came")
            ctx.emit("from; the hashes alone say only that it is internally consistent.")
        if not result.is_trustworthy:
            ctx.emit()
            ctx.emit("Do not install this bundle.")
        return EXIT_OK if result.is_trustworthy else EXIT_DRIFT


class BundleSbomCommand(Command):
    name = "sbom"
    help = "the dependency list this installation would ship"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        pass

    def run(self, ctx: CommandContext) -> int:
        """What is installed, not what was asked for.

        pyproject.toml states floors. A security review asking "what is in
        this" wants the resolved versions, and a floor is not an answer.
        """
        found = installed_distributions()
        if ctx.json_output:
            ctx.emit_json({"distributions": [{"name": n, "version": v} for n, v in found]})
            return EXIT_OK
        for name, version in found:
            ctx.emit(f"  {name}=={version}")
        ctx.emit()
        ctx.emit(f"{len(found)} distribution(s), as resolved rather than as requested.")
        return EXIT_OK


class BundleCommand(CommandGroup):
    name = "bundle"
    help = "seal and verify an offline install"

    def commands(self) -> list[Command]:
        return [BundleSealCommand(), BundleVerifyCommand(), BundleSbomCommand()]


__all__ = ["BundleCommand"]
