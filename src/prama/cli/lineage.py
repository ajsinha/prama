"""``prama lineage`` — scan SQL into the lineage store, and ask it questions.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from prama.cli.base import EXIT_OK, Command, CommandContext, CommandGroup
from prama.cli.llm import _tenant_flag, _with_uow
from prama.core.errors import ValidationError


class ScanCommand(Command):
    name = "scan"
    help = "read SQL files into the lineage store as a run of a named source"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("paths", nargs="+", help=".sql files, or directories of them")
        parser.add_argument("--source", required=True, help="a name for this body of SQL")
        parser.add_argument("--dialect", default="ansi", help="e.g. tsql, snowflake, postgres")
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        from prama.lineage.store import scan_sql

        files: list[Path] = []
        for raw in ctx.args.paths:
            path = Path(raw)
            files.extend(sorted(path.rglob("*.sql")) if path.is_dir() else [path])
        missing = [str(f) for f in files if not f.is_file()]
        if missing or not files:
            raise ValidationError(
                f"nothing to scan: {', '.join(missing) or 'no .sql files found'}",
                remedy="Pass .sql files or a directory that contains them.",
            )
        sql = ";\n".join(f.read_text(encoding="utf-8", errors="replace") for f in files)

        async def work(uow: Any, tenant: str) -> dict[str, Any]:
            run = await scan_sql(
                uow,
                tenant,
                source=ctx.args.source,
                sql=sql,
                location=", ".join(str(f) for f in files)[:500],
                dialect=ctx.args.dialect,
            )
            return {
                "run": run.id,
                "statements": run.statements,
                "edges": run.edges,
                "gaps": run.gaps,
                "understood": round(run.understood, 3),
                "outcome": run.outcome,
                "detail": run.detail,
            }

        result = _with_uow(ctx, work)
        if ctx.json_output:
            ctx.emit_json(result)
        else:
            ctx.emit(
                f"{ctx.args.source}: {result['statements']} statements, {result['edges']} edges, "
                f"{result['gaps']} gaps ({result['understood']:.0%} understood)"
            )
            if result["detail"]:
                ctx.emit(f"  {result['detail']}")
            if result["gaps"]:
                ctx.emit("  See what was not understood: prama lineage gaps")
        return EXIT_OK


class ShowCommand(Command):
    name = "show"
    help = "current edges, optionally those touching one dataset"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("dataset", nargs="?", default="")
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        async def work(uow: Any, tenant: str) -> list[dict[str, Any]]:
            return [
                {
                    "from": f"{r.source_dataset}.{r.source_column}",
                    "to": f"{r.target_dataset}.{r.target_column}",
                    "transform": r.transform,
                    "status": r.status,
                    "method": r.method,
                    "confidence": r.confidence,
                }
                for r in await uow.lineage.edges(tenant, dataset=ctx.args.dataset)
            ]

        rows = _with_uow(ctx, work)
        if ctx.json_output:
            ctx.emit_json(rows)
        elif not rows:
            ctx.emit("No lineage yet. Scan some SQL: prama lineage scan etl/ --source warehouse")
        for r in [] if ctx.json_output else rows:
            ctx.emit(f"{r['from']} -> {r['to']}  [{r['transform']}, {r['status']}]")
        return EXIT_OK


class ImpactCommand(Command):
    name = "impact"
    help = "everything a defect in one column reaches, ranked"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("column", help="dataset.column, e.g. stg.trades.notional")
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        from prama.lineage.graph import Column

        origin = Column.parse(ctx.args.column)

        async def work(uow: Any, tenant: str) -> Any:
            return (await uow.lineage.graph(tenant)).blast_radius(origin)

        radius = _with_uow(ctx, work)
        rows = [
            {"column": r.column.qualified, "impact": round(r.impact, 3), "depth": r.depth}
            for r in radius.reached
        ]
        if ctx.json_output:
            ctx.emit_json(rows)
        elif not rows:
            ctx.emit(f"Nothing downstream of {origin.qualified} in the lineage store.")
        for r in [] if ctx.json_output else rows:
            ctx.emit(f"{r['impact']:>6.0%}  {r['column']}  (depth {r['depth']})")
        return EXIT_OK


class GapsCommand(Command):
    name = "gaps"
    help = "what the latest scans could not read"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        async def work(uow: Any, tenant: str) -> list[dict[str, str]]:
            out = []
            for run in await uow.lineage.runs(tenant, limit=5):
                for gap in await uow.lineage.gaps(tenant, run.id):
                    out.append({"run": run.id, "kind": gap.kind, "detail": gap.detail})
            return out

        rows = _with_uow(ctx, work)
        if ctx.json_output:
            ctx.emit_json(rows)
        elif not rows:
            ctx.emit("No gaps in the latest scans.")
        for r in [] if ctx.json_output else rows:
            ctx.emit(f"[{r['kind']}] {r['detail']}")
        return EXIT_OK


class LineageCommand(CommandGroup):
    name = "lineage"
    help = "column lineage: scan SQL, show edges, impact, gaps"

    def commands(self) -> list[Command]:
        return [ScanCommand(), ShowCommand(), ImpactCommand(), GapsCommand()]
