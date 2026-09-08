"""Control commands: read, check, explain, compile and import.

The language is only useful if somebody can run it against a file. These are
the commands that make Wave 4's work reachable from a terminal, and each is
shaped by what a person is actually trying to find out:

* ``check`` — is this control estate sound? Type errors and lint findings
  together, because a suite with a typo and a suite full of controls that
  cannot fire are the same kind of problem to whoever owns it.
* ``explain`` — what do these controls say, in English? The output a data owner
  reads and approves.
* ``compile`` — what SQL will run? The output a DBA asks for before granting
  access, and the one that makes the platform inspectable rather than trusted.
* ``import`` — what happens to what I already have?

``check`` exits non-zero when it finds errors, so it drops into CI without
anything further being written.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from prama.cli.base import EXIT_ERROR, EXIT_OK, EXIT_USAGE, Command, CommandContext, CommandGroup
from prama.importers import IMPORTERS, importer
from prama.pql import parse
from prama.pql.ast import Control
from prama.pql.errors import PqlError
from prama.pql.lint import Linter
from prama.pql.types import Catalogue, TypeChecker


class ControlCheckCommand(Command):
    name = "check"
    help = "parse, type-check and lint a control file"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("file", help="a .pql file")
        parser.add_argument(
            "--strict",
            action="store_true",
            help="treat lint warnings as errors, for a CI gate",
        )

    def run(self, ctx: CommandContext) -> int:
        controls, source, failure = _read(ctx)
        if failure is not None:
            return failure
        checker = TypeChecker(Catalogue())
        problems: list[dict[str, Any]] = []
        # An undeclared dataset is one fact about the estate, not one per
        # control. Reporting it fifty times for a fifty-control suite buries
        # the findings that are actually about a control.
        already_said: set[str] = set()
        for control in controls:
            for finding in checker.check(control, source=source):
                if finding.level == "unchecked":
                    if finding.message in already_said:
                        continue
                    already_said.add(finding.message)
                problems.append({"kind": "type", **finding.to_dict(), "control": _head(control)})
        for lint_finding in Linter().check_all(controls):
            problems.append({"kind": "lint", **lint_finding.to_dict()})

        if ctx.json_output:
            ctx.emit_json({"controls": len(controls), "findings": problems})
        else:
            ctx.emit(f"{len(controls)} control(s) read from {ctx.args.file}.")
            for problem in problems:
                ctx.emit("")
                ctx.emit(
                    f"  [{problem.get('level') or problem.get('severity')}] {problem['message']}"
                )
                ctx.emit(f"      in {problem['control']}")
                ctx.emit(f"      → {problem['remedy']}")
            if not problems:
                ctx.emit("Nothing to report.")
        blocking = [
            p for p in problems if p.get("level") == "error" or p.get("severity") == "error"
        ]
        if ctx.args.strict:
            blocking = [p for p in problems if p.get("level") != "unchecked"]
        return EXIT_ERROR if blocking else EXIT_OK


class ControlExplainCommand(Command):
    name = "explain"
    help = "render each control as a sentence, for the person who owns the data"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("file", help="a .pql file")

    def run(self, ctx: CommandContext) -> int:
        controls, _, failure = _read(ctx)
        if failure is not None:
            return failure
        if ctx.json_output:
            ctx.emit_json([{"control": _head(c), "describes": c.describe()} for c in controls])
            return EXIT_OK
        for control in controls:
            ctx.emit(f"· {control.describe()}")
            ctx.emit("")
        return EXIT_OK


class ControlFormatCommand(Command):
    name = "format"
    help = "rewrite controls in canonical form, so diffs are about meaning"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("file", help="a .pql file")
        parser.add_argument("--write", action="store_true", help="rewrite the file in place")

    def run(self, ctx: CommandContext) -> int:
        controls, source, failure = _read(ctx)
        if failure is not None:
            return failure
        formatted = "\n\n".join(c.render() for c in controls) + "\n"
        if ctx.args.write:
            Path(ctx.args.file).write_text(formatted, encoding="utf-8")
            changed = formatted != source
            ctx.emit(f"{ctx.args.file}: {'rewritten' if changed else 'already canonical'}")
            return EXIT_OK
        ctx.emit(formatted.rstrip())
        return EXIT_OK


class ControlCompileCommand(Command):
    name = "compile"
    help = "show the SQL a control becomes on a given engine"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("file", help="a .pql file")
        parser.add_argument("--dialect", default="postgresql", help="postgresql, duckdb or sqlite")
        parser.add_argument(
            "--fuse",
            action="store_true",
            help="group controls that share a scope into one query each",
        )

    def run(self, ctx: CommandContext) -> int:
        from prama.backend.fuse import Fuser
        from prama.backend.sql import SqlCompiler
        from prama.ir.lower import Lowerer
        from prama.pql.errors import PqlUnsupportedError

        controls, _, failure = _read(ctx)
        if failure is not None:
            return failure
        lowerer = Lowerer()
        plans = []
        for control in controls:
            try:
                plans.append(lowerer.control(control))
            except Exception as exc:  # a control with no plan is reported, not fatal
                ctx.emit(f"-- {_head(control)}")
                ctx.emit(f"--   cannot be compiled: {exc}")
                ctx.emit("")
        if ctx.args.fuse:
            fuser = Fuser(ctx.args.dialect)
            ctx.emit(f"-- {fuser.cost(plans).render()}")
            ctx.emit("")
            for group in fuser.group(plans):
                ctx.emit(f"-- {group.describe()}")
                ctx.emit(fuser.fuse(group, table=group.dataset).sql)
                ctx.emit("")
            return EXIT_OK
        compiler = SqlCompiler(ctx.args.dialect)
        refused = 0
        for plan in plans:
            ctx.emit(f"-- {plan.description}")
            try:
                ctx.emit(compiler.compile(plan, table=plan.scope.dataset).metric_query)
            except PqlUnsupportedError as exc:
                # A refusal is information, not a crash: it is the engine
                # saying which control it cannot run, before anything is
                # scheduled against it.
                refused += 1
                ctx.emit(f"--   refused: {exc.args[0]}")
                ctx.emit(f"--   → {exc.remedy}")
            ctx.emit("")
        if refused:
            ctx.emit(f"-- {refused} control(s) cannot run on {ctx.args.dialect}.")
        return EXIT_OK


class ControlImportCommand(Command):
    name = "import"
    help = "read another tool's tests, and report what did not come across"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("file", help="the source file")
        parser.add_argument(
            "--from",
            dest="source_format",
            required=True,
            choices=sorted(IMPORTERS),
            help="the tool the file belongs to",
        )
        parser.add_argument(
            "--out", help="write the imported controls here instead of to the screen"
        )

    def run(self, ctx: CommandContext) -> int:
        path = Path(ctx.args.file)
        if not path.is_file():
            ctx.emit(f"no such file: {path}")
            return EXIT_USAGE
        result = importer(ctx.args.source_format).read_text(path.read_text(encoding="utf-8"))
        if ctx.json_output:
            ctx.emit_json(result.to_dict())
            return EXIT_OK
        if ctx.args.out:
            Path(ctx.args.out).write_text(
                "\n\n".join(c.render() for c in result.controls) + "\n", encoding="utf-8"
            )
            ctx.emit(f"{result.imported} control(s) written to {ctx.args.out}.")
            ctx.emit("")
        ctx.emit(result.render())
        # Exit non-zero when something was left behind, so a migration script
        # cannot report success while quietly losing coverage.
        return EXIT_OK if result.is_complete else EXIT_ERROR


class ControlCommand(CommandGroup):
    name = "control"
    help = "read, check, explain, compile and import controls"

    def commands(self) -> list[Command]:
        return [
            ControlCheckCommand(),
            ControlExplainCommand(),
            ControlFormatCommand(),
            ControlCompileCommand(),
            ControlImportCommand(),
        ]


def _read(ctx: CommandContext) -> tuple[list[Control], str, int | None]:
    """Read and parse the file, or report why not.

    A parse error is rendered with its caret rather than as a traceback: the
    reader is somebody editing a control, and the position is the whole point.
    """
    path = Path(ctx.args.file)
    if not path.is_file():
        ctx.emit(f"no such file: {path}")
        return [], "", EXIT_USAGE
    source = path.read_text(encoding="utf-8")
    try:
        return list(parse(source).all_controls), source, None
    except PqlError as exc:
        ctx.emit(exc.render())
        return [], source, EXIT_ERROR


def _head(control: Control) -> str:
    return control.render().splitlines()[0]
