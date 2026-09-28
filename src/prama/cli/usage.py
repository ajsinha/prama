"""``prama usage`` — how often datasets are read, and what that says to work on first.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path
from typing import Any

from prama.cli.base import EXIT_OK, Command, CommandContext, CommandGroup
from prama.cli.llm import _tenant_flag, _with_uow
from prama.core.errors import ValidationError


class ImportCommand(Command):
    name = "import"
    help = "read a warehouse's query-history export into daily usage (--query prints it)"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("warehouse", choices=["snowflake", "bigquery", "databricks"])
        parser.add_argument("rows", nargs="?", default="", help="JSON list or CSV")
        parser.add_argument("--query", action="store_true", help="print the export query")
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        from prama.lineage.usage import QUERIES, ingest

        if ctx.args.query or not ctx.args.rows:
            ctx.emit(QUERIES[ctx.args.warehouse])
            return EXIT_OK
        path = Path(ctx.args.rows)
        if not path.is_file():
            raise ValidationError(f"there is no file at {path}", remedy="Pass the export.")
        text = path.read_text(encoding="utf-8")
        rows = (
            list(csv.DictReader(io.StringIO(text)))
            if path.suffix.lower() == ".csv"
            else json.loads(text)
        )
        days = _with_uow(ctx, lambda uow, t: ingest(uow, t, ctx.args.warehouse, rows))
        ctx.emit(f"{len(rows)} history row(s) -> {days} dataset-day(s) of usage")
        return EXIT_OK


class PrioritiesCommand(Command):
    name = "priorities"
    help = "most used, least controlled: where to work first"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--days", type=int, default=30)
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        from prama.semantic.services.priorities import priorities

        result: dict[str, Any] = _with_uow(
            ctx, lambda uow, t: priorities(uow, t, days=ctx.args.days)
        )
        if ctx.json_output:
            ctx.emit_json(result)
            return EXIT_OK
        if not result["has_usage"]:
            ctx.emit("No usage recorded. Import it: prama usage import snowflake rows.json")
        for r in result["datasets"]:
            ctx.emit(
                f"{r['slug']:<30} {r['queries']:>7} queries  {r['readers']:>4} readers  "
                f"{r['controls']:>3} controls  {r['failing']} failing"
            )
        for r in result["undeclared"]:
            ctx.emit(f"UNDECLARED {r['dataset']:<30} {r['queries']:>7} queries")
        return EXIT_OK


class UsageCommand(CommandGroup):
    name = "usage"
    help = "dataset usage from query history, as a priority signal"

    def commands(self) -> list[Command]:
        return [ImportCommand(), PrioritiesCommand()]
