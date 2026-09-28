"""``prama evidence`` — anchor the chain outside Prama, and hand it to an auditor.

    prama evidence anchor              the chain head, to the configured witness, now
    prama evidence anchors             every attempt, failures included
    prama evidence export OUT          a bundle the offline verifier checks, receipts included

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from prama.cli.base import EXIT_OK, Command, CommandContext, CommandGroup
from prama.cli.llm import _tenant_flag, _with_uow
from prama.core.errors import PramaError, ValidationError

EXIT_NOT_ANCHORED = 3


def _row(anchor: Any) -> dict[str, Any]:
    return {
        "sequence": anchor.sequence,
        "digest": anchor.digest,
        "kind": anchor.kind,
        "authority": anchor.authority,
        "status": anchor.status,
        "requested_at": anchor.requested_at,
        "witnessed_at": anchor.witnessed_at,
        "token": anchor.token,
        "detail": anchor.detail,
    }


class AnchorCommand(Command):
    name = "anchor"
    help = "anchor the chain head with the configured witness (evidence.anchor)"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        from prama.evidence.anchor import anchor_from, anchor_head

        async def work(uow: Any, tenant_id: str) -> Any:
            tenant = await uow.tenants.get(tenant_id)
            anchor = anchor_from(ctx.config, residency=getattr(tenant, "residency", None))
            if anchor is None:
                raise ValidationError(
                    "evidence anchoring is off",
                    remedy="Set evidence.anchor.kind to rfc3161 and evidence.anchor.url.",
                )
            return await anchor_head(uow, tenant_id, anchor)

        row = _with_uow(ctx, work)
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
        from prama.evidence.retention import Archivist

        async def work(uow: Any, tenant_id: str) -> tuple[Any, list[Any]]:
            records = await uow.evidence.chain(tenant_id, limit=10_000_000)
            if not records:
                raise PramaError(
                    "there is no evidence to export",
                    code="EVIDENCE.EMPTY",
                    remedy="Run some controls first: prama control run.",
                )
            bundle = Archivist().bundle(records, tenant_id=tenant_id)
            anchors = await uow.anchors.for_tenant(
                tenant_id, first=records[0].sequence, last=records[-1].sequence
            )
            return bundle, anchors

        bundle, anchors = _with_uow(ctx, work)
        out = Path(ctx.args.out)
        out.mkdir(parents=True, exist_ok=True)
        for name, content in bundle.files().items():
            (out / name).write_text(content, encoding="utf-8")
        receipts = [_row(a) for a in anchors if a.status == "anchored"]
        (out / "anchors.json").write_text(json.dumps(receipts, indent=2), encoding="utf-8")
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
