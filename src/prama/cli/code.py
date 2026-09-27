"""``prama code`` — receive application code and read its lineage.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from prama.cli.base import EXIT_OK, Command, CommandContext, CommandGroup
from prama.cli.llm import _tenant_flag, _with_uow


def _report(ctx: CommandContext, run: Any) -> int:
    summary = {
        "run": run.id,
        "status": run.status,
        "coverage": run.coverage_json,
        "error": run.error,
    }
    if ctx.json_output:
        ctx.emit_json(summary)
        return EXIT_OK
    ctx.emit(f"run {run.id}: {run.status}")
    if run.error:
        ctx.emit(f"  {run.error}")
    cov = run.coverage_json or {}
    if cov:
        ctx.emit(
            f"  {cov.get('read', 0)} of {cov.get('units', 0)} files read, {cov.get('edges', 0)} "
            f"lineage edges, {cov.get('gaps', 0)} gaps"
        )
        if cov.get("unread_kinds"):
            ctx.emit(f"  not yet read by this build: {', '.join(cov['unread_kinds'])}")
    return EXIT_OK


class AddZipCommand(Command):
    name = "add-zip"
    help = "receive a ZIP of application code and read its lineage (never executed)"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("archive")
        parser.add_argument("--source", required=True, help="a name for this code")
        parser.add_argument("--dialect", default="ansi")
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        from prama.codeintake.intake import receive_zip

        async def work(uow: Any, tenant: str) -> Any:
            return await receive_zip(
                uow,
                ctx.config,
                tenant,
                ctx.args.source,
                Path(ctx.args.archive),
                dialect=ctx.args.dialect,
            )

        return _report(ctx, _with_uow(ctx, work))


class AddGitCommand(Command):
    name = "add-git"
    help = "fetch one ref of a git repository and read its lineage (never executed)"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("url", help="https:// or ssh:// (git@host:org/repo.git)")
        parser.add_argument("--ref", default="main")
        parser.add_argument("--source", required=True)
        parser.add_argument("--credential-ref", default="", help="e.g. env://GIT_TOKEN")
        parser.add_argument("--dialect", default="ansi")
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        from prama.codeintake.intake import receive_git

        async def work(uow: Any, tenant: str) -> Any:
            return await receive_git(
                uow,
                ctx.config,
                tenant,
                ctx.args.source,
                ctx.args.url,
                ctx.args.ref,
                credential_ref=ctx.args.credential_ref or None,
                dialect=ctx.args.dialect,
            )

        return _report(ctx, _with_uow(ctx, work))


class RunsCommand(Command):
    name = "runs"
    help = "recent analysis runs"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        async def work(uow: Any, tenant: str) -> list[dict[str, Any]]:
            names = {s.id: s.name for s in await uow.code.sources(tenant)}
            return [
                {
                    "run": r.id,
                    "source": names.get(r.source_id, "?"),
                    "status": r.status,
                    "started_at": r.started_at,
                    "coverage": r.coverage_json,
                }
                for r in await uow.code.runs(tenant)
            ]

        rows = _with_uow(ctx, work)
        if ctx.json_output:
            ctx.emit_json(rows)
        elif not rows:
            ctx.emit("No code received yet: prama code add-zip app.zip --source app")
        for r in [] if ctx.json_output else rows:
            cov = r["coverage"] or {}
            ctx.emit(
                f"{r['started_at'][:19]}  {r['source']}  {r['status']}  "
                f"{cov.get('read', 0)}/{cov.get('units', 0)} read"
            )
        return EXIT_OK


class CodeCommand(CommandGroup):
    name = "code"
    help = "application code: receive a ZIP or a git ref, read its lineage"

    def commands(self) -> list[Command]:
        return [AddZipCommand(), AddGitCommand(), RunsCommand()]
