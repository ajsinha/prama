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


def _key(ctx: CommandContext) -> bytes:
    secret: str = ctx.config.require_secret("security.session_secret")
    return secret.encode()


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

        if ctx.json_output:
            ctx.emit_json(
                {
                    "root": str(root),
                    "files": len(manifest.entries),
                    "bytes": manifest.total_bytes,
                    "content_hash": manifest.content_hash,
                    "sbom": len(manifest.sbom),
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
        ctx.emit("The signature is an HMAC over the manifest hash. It says the bundle")
        ctx.emit("was sealed by a holder of this deployment's key, and nothing to")
        ctx.emit("anybody who does not hold it.")
        return EXIT_OK


class BundleVerifyCommand(Command):
    name = "verify"
    help = "check a bundle before installing it; non-zero if it must not be"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("root")

    def run(self, ctx: CommandContext) -> int:
        root = Path(ctx.args.root)
        manifest = _load(root)
        signature = root / SIGNATURE
        seal = signature.read_text().strip() if signature.exists() else ""

        result = verify(root, manifest, key=_key(ctx), seal=seal)

        if ctx.json_output:
            ctx.emit_json({**result.to_dict(), "version": manifest.version})
            return EXIT_OK if result.is_trustworthy else EXIT_DRIFT

        ctx.emit(f"{manifest.product} {manifest.version}, sealed {manifest.created_at}")
        ctx.emit(result.describe())
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
