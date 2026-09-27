"""``prama lineage`` — scan SQL into the lineage store, and ask it questions.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from prama.cli.base import EXIT_DRIFT, EXIT_OK, Command, CommandContext, CommandGroup
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
        parser.add_argument("column", nargs="?", default="", help="dataset.column")
        parser.add_argument(
            "--diff",
            nargs=2,
            metavar=("BEFORE", "AFTER"),
            help="two versions of a SQL file: what does the change put at risk? exits 3 if "
            "any control or attestation is affected",
        )
        parser.add_argument("--dialect", default="ansi")
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        from prama.lineage.graph import Column

        if ctx.args.diff:
            return self._diff(ctx)
        if not ctx.args.column:
            raise ValidationError(
                "name a column, or pass --diff BEFORE AFTER",
                remedy="prama lineage impact raw.trades.notional",
            )
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

    def _diff(self, ctx: CommandContext) -> int:
        """What a change between two SQL files puts at risk. Exit 3 if anything."""
        from prama.lineage.change import assess, changed_columns

        before, after = (_read(p) for p in ctx.args.diff)
        changed = changed_columns(before, after, dialect=ctx.args.dialect)

        async def work(uow: Any, tenant: str) -> Any:
            return await assess(uow, tenant, changed)

        impact = _with_uow(ctx, work)
        if ctx.json_output:
            ctx.emit_json(impact.to_dict())
        elif not impact.changed:
            ctx.emit("The change alters no column lineage.")
        else:
            ctx.emit(f"Changed: {', '.join(impact.changed)}")
            for column, share in impact.reached:
                ctx.emit(f"  {share:>6.0%}  {column}")
            for c in impact.controls:
                label = c["name"] or c["control"]
                ctx.emit(f"  control at risk: {label} on {c['dataset']} [{c['severity']}]")
            for a in impact.attestations:
                ctx.emit(f"  attestation at risk: {a['scope']}, signed by {a['attester']}")
            if not impact.at_risk:
                ctx.emit("  Nothing downstream is controlled or attested.")
        # Exit 3 is the code `prama contract check` uses for a breach, so one
        # CI rule stops either.
        return EXIT_DRIFT if impact.at_risk else EXIT_OK


def _read(path: str) -> str:
    target = Path(path)
    if not target.is_file():
        raise ValidationError(f"there is no file at {path}", remedy="Pass two SQL files.")
    return target.read_text(encoding="utf-8", errors="replace")


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


class IngestDbtCommand(Command):
    name = "ingest-dbt"
    help = "read a dbt project's column lineage from its manifest.json"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("manifest", help="target/manifest.json, after `dbt compile`")
        parser.add_argument("--source", default="dbt", help="a name for this project")
        parser.add_argument("--dialect", default="ansi")
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        import json

        from prama.lineage.ingest import ingest_dbt

        manifest = json.loads(_read(ctx.args.manifest))

        async def work(uow: Any, tenant: str) -> dict[str, Any]:
            run = await ingest_dbt(
                uow, tenant, manifest, source=ctx.args.source, dialect=ctx.args.dialect
            )
            return {"models": run.statements, "edges": run.edges, "gaps": run.gaps}

        result = _with_uow(ctx, work)
        if ctx.json_output:
            ctx.emit_json(result)
        else:
            ctx.emit(
                f"{ctx.args.source}: {result['models']} models, {result['edges']} edges, "
                f"{result['gaps']} gaps"
            )
        return EXIT_OK


class HistoryCommand(Command):
    name = "history"
    help = "column lineage from a warehouse's query history (Snowflake, Databricks, BigQuery)"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("warehouse", choices=["snowflake", "databricks", "bigquery"])
        parser.add_argument("rows", nargs="?", default="", help="an export: JSON list or CSV")
        parser.add_argument("--source", default="", help="a name; defaults to <warehouse>-history")
        parser.add_argument("--query", action="store_true", help="print the export query and stop")
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        import csv
        import io
        import json

        from prama.lineage.history import QUERIES, ingest_history

        if ctx.args.query or not ctx.args.rows:
            ctx.emit(QUERIES[ctx.args.warehouse])
            return EXIT_OK
        text = _read(ctx.args.rows)
        rows = (
            list(csv.DictReader(io.StringIO(text)))
            if ctx.args.rows.lower().endswith(".csv")
            else json.loads(text)
        )
        source = ctx.args.source or f"{ctx.args.warehouse}-history"

        async def work(uow: Any, tenant: str) -> dict[str, Any]:
            run = await ingest_history(uow, tenant, ctx.args.warehouse, rows, source=source)
            return {"rows": len(rows), "edges": run.edges, "gaps": run.gaps}

        result = _with_uow(ctx, work)
        if ctx.json_output:
            ctx.emit_json(result)
        else:
            ctx.emit(
                f"{source}: {result['rows']} rows, {result['edges']} edges, {result['gaps']} gaps"
            )
        return EXIT_OK


class LineageCommand(CommandGroup):
    name = "lineage"
    help = "column lineage: scan SQL, show edges, impact, gaps"

    def commands(self) -> list[Command]:
        return [
            ScanCommand(),
            IngestDbtCommand(),
            HistoryCommand(),
            ShowCommand(),
            ImpactCommand(),
            GapsCommand(),
        ]
