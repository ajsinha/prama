"""``prama evidence`` — anchor the chain outside Prama, and hand it to an auditor.

    prama evidence anchor              the chain head, to the configured witness, now
    prama evidence anchors             every attempt, failures included
    prama evidence export OUT          a bundle the offline verifier checks, receipts included

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from prama.cli.base import EXIT_OK, Command, CommandContext, CommandGroup
from prama.cli.llm import _tenant_flag, _with_uow

EXIT_NOT_ANCHORED = 3


def _row(anchor: Any) -> dict[str, Any]:
    from prama.evidence.service import anchor_view

    return anchor_view(anchor)


class AnchorCommand(Command):
    name = "anchor"
    help = "anchor the chain head with the configured witness (evidence.anchor)"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        from prama.evidence.service import anchor_now

        row = _with_uow(ctx, lambda uow, tenant_id: anchor_now(uow, tenant_id, ctx.config))
        if row is None:
            ctx.emit("The chain is empty: nothing to anchor.")
            return EXIT_OK
        if ctx.json_output:
            ctx.emit_json(_row(row))
        elif row.status == "anchored":
            ctx.emit(
                f"Anchored sequence {row.sequence} ({row.digest[:16]}…) at {row.authority}, "
                f"witnessed {row.witnessed_at}"
            )
        else:
            ctx.emit(f"NOT anchored: sequence {row.sequence}: {row.detail}")
        return EXIT_OK if row.status == "anchored" else EXIT_NOT_ANCHORED


class AnchorsCommand(Command):
    name = "anchors"
    help = "every anchoring attempt, failures included"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        rows = _with_uow(ctx, lambda uow, t: uow.anchors.for_tenant(t))
        if ctx.json_output:
            ctx.emit_json([_row(r) for r in rows])
            return EXIT_OK
        if not rows:
            ctx.emit("No anchors. Turn them on with evidence.anchor in the configuration.")
        for r in rows:
            when = r.witnessed_at or r.requested_at
            ctx.emit(f"{r.sequence:>8}  {r.status:<9} {r.digest[:16]}…  {when}  {r.detail[:60]}")
        return EXIT_OK


class ExportCommand(Command):
    name = "export"
    help = "write a bundle (manifest, records, anchor receipts) for scripts/verify_evidence.py"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("out", help="a directory, created if absent")
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        from prama.evidence.service import bundle_files, export_bundle

        bundle, receipts = _with_uow(ctx, export_bundle)
        out = Path(ctx.args.out)
        out.mkdir(parents=True, exist_ok=True)
        for name, content in bundle_files(bundle, receipts).items():
            (out / name).write_text(content, encoding="utf-8")
        ctx.emit(
            f"{bundle.manifest.records} record(s) and {len(receipts)} anchor receipt(s) -> {out}"
        )
        ctx.emit(f"Verify without Prama: python3 scripts/verify_evidence.py {out}")
        return EXIT_OK


class EvidenceCommand(CommandGroup):
    name = "evidence"
    help = "anchor the evidence chain outside Prama, and export it for an auditor"

    def commands(self) -> list[Command]:
        return [AnchorCommand(), AnchorsCommand(), ExportCommand()]
