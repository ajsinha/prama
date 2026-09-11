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
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    data = Path(path).read_bytes()
    return load_pem_private_key(data, password=None)


def _public_key(path: str) -> object:
    from cryptography.hazmat.primitives.serialization import load_pem_public_key

    return load_pem_public_key(Path(path).read_bytes())


def _load(root: Path) -> Manifest:
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
    payload = json.loads(path.read_text())
    return Manifest(
        product=payload["product"],
        version=payload["version"],
        created_at=payload["created_at"],
        entries=tuple(
            Entry(
                path=entry["path"],
                sha256=entry["sha256"],
                bytes=entry["bytes"],
                kind=entry.get("kind", "other"),
            )
            for entry in payload["entries"]
        ),
        sbom=tuple((name, version) for name, version in payload.get("sbom", [])),
        manifest_version=payload.get("manifest_version", "1.0"),
    )


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
        manifest = build_manifest(
            root,
            created_at=utc_now().isoformat(),
            sbom=() if ctx.args.no_sbom else installed_distributions(),
        )
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
        manifest = _load(root)
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
