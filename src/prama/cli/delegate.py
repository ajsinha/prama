"""``prama delegate`` — the Python checks this host may run, vetted and tried out.

``list`` shows what `delegates:` in configuration admitted, and what it refused
and why. ``scan`` vets a file or directory *without importing it*. ``test`` runs
one delegate over rows from a JSON or CSV file, exactly as a control would —
sandboxed, with canonical JSON rows — and prints the measurement.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from prama.cli.base import EXIT_ERROR, EXIT_OK, Command, CommandContext, CommandGroup
from prama.core.errors import ValidationError


def _paths_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--path",
        action="append",
        default=[],
        help="a directory of delegate files, in addition to delegates.paths",
    )


def _host(ctx: CommandContext) -> Any:
    from prama.delegates.host import host_from_config

    host = host_from_config(ctx.config)
    extra = list(getattr(ctx.args, "path", []) or [])
    if extra:
        host.registry.load_paths(extra)
    return host


class ListCommand(Command):
    name = "list"
    help = "the delegates this host admitted, and those it refused"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        _paths_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        host = _host(ctx)
        admitted = [a.describe() for a in host.registry.all()]
        if ctx.json_output:
            ctx.emit_json({"admitted": admitted, "refused": host.registry.refused})
            return EXIT_OK
        if not admitted and not host.registry.refused:
            ctx.emit("No delegates. Point delegates.paths at a directory, or install a")
            ctx.emit("distribution advertising the prama.delegates entry point.")
        for a in admitted:
            params = ", ".join(p["name"] for p in a["parameters"]) or "no parameters"
            ctx.emit(f"{a['name']}@{a['version']}  counts {a['unit']}  ({params})")
            ctx.emit(f"  {a['summary']}")
            ctx.emit(f"  reads: {', '.join(a['requires']) or 'every column'}")
            ctx.emit(f"  from {a['origin']}  source {a['implementation_hash'][:12]}")
        for name, why in sorted(host.registry.refused.items()):
            ctx.emit(f"REFUSED {name}: {why}")
        return EXIT_OK


class ScanCommand(Command):
    name = "scan"
    help = "vet delegate files without importing them"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("target", help="a .py file or a directory of them")

    def run(self, ctx: CommandContext) -> int:
        from prama.classify.plugins import scan_source

        target = Path(ctx.args.target)
        files = sorted(target.glob("*.py")) if target.is_dir() else [target]
        failed = 0
        for path in files:
            found = sorted(set(scan_source(str(path))))
            failed += bool(found)
            ctx.emit(f"{path.name}: {'refused' if found else 'clean'}")
            for module, why in found:
                ctx.emit(f"  {module} — {why}")
        return EXIT_ERROR if failed else EXIT_OK


def _rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, list):
        raise ValidationError(
            f"{path} is not a JSON list of rows", remedy="Give a list of objects, or a CSV."
        )
    return loaded


def _value(text: str) -> Any:
    lowered = text.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


class TestCommand(Command):
    name = "test"
    help = "run one delegate over rows from a file, exactly as a control would"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("delegate", help="its registered name, optionally @version")
        parser.add_argument("--rows", required=True, help="a JSON list of objects, or a CSV")
        parser.add_argument("--param", action="append", default=[], help="name=value, repeatable")
        _paths_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        from prama.backend.execute import judge
        from prama.delegates.testkit import control_for
        from prama.pql import parse_control

        params = {}
        for item in ctx.args.param:
            key, _, raw = item.partition("=")
            params[key.strip()] = _value(raw.strip())
        source = control_for(ctx.args.delegate, params)
        from prama.ir.resolve import resolved

        plan = resolved(parse_control(source))
        host = _host(ctx)
        result = host.measure_plan(plan, _rows(Path(ctx.args.rows)))
        verdict = judge(plan, result.metrics).verdict.value
        if ctx.json_output:
            ctx.emit_json(
                {
                    "control": source,
                    "verdict": verdict,
                    "metrics": result.metrics,
                    "note": result.note,
                    "samples": result.samples,
                    "delegate": result.parameters,
                }
            )
            return EXIT_OK
        ctx.emit(source)
        for name, value in result.metrics.items():
            ctx.emit(f"  {name}: {value:g}")
        if result.note:
            ctx.emit(f"  {result.note}")
        ctx.emit(f"  verdict at the default threshold (no violations): {verdict}")
        ran = result.parameters
        ctx.emit(f"  ran {ran['delegate']}, source {ran['delegate_hash'][:12]}")
        return EXIT_OK


class CheckCommand(Command):
    name = "check"
    help = "conformance: everything Prama checks, plus your own cases (for CI)"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("target", help="a delegate .py file or a directory of them")
        parser.add_argument("--cases", default="", help="JSON list of cases with expectations")
        parser.add_argument("--large", type=int, default=50_000, help="rows for the stream test")
        parser.add_argument("--no-sandbox", action="store_true", help="run in-process")

    def run(self, ctx: CommandContext) -> int:
        from prama.delegates.testkit import Case, check_delegate

        cases = []
        if ctx.args.cases:
            loaded = json.loads(Path(ctx.args.cases).read_text(encoding="utf-8"))
            cases = [Case.from_dict(item) for item in loaded]
        report = check_delegate(
            ctx.args.target,
            cases=cases,
            sandbox=not ctx.args.no_sandbox,
            large_rows=ctx.args.large,
        )
        if ctx.json_output:
            ctx.emit_json(report.to_dict())
        else:
            ctx.emit(report.render())
        return EXIT_OK if report.ok else EXIT_ERROR


class DelegateCommand(CommandGroup):
    name = "delegate"
    help = "Python DQ checks: list, vet and try them"

    def commands(self) -> list[Command]:
        return [ListCommand(), ScanCommand(), TestCommand(), CheckCommand()]
