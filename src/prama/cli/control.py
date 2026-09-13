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
import dataclasses
from pathlib import Path
from typing import Any

from prama.cli.base import EXIT_ERROR, EXIT_OK, EXIT_USAGE, Command, CommandContext, CommandGroup
from prama.core.errors import PramaError, ValidationError
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
            ctx.emit_json(
                [
                    {
                        "control": _head(c),
                        "describes": c.describe(),
                        "divergences": _divergences(c),
                    }
                    for c in controls
                ]
            )
            return EXIT_OK
        for control in controls:
            ctx.emit(f"· {control.describe()}")
            # Every way this control's functions differ from what a spreadsheet
            # would do. Printed here rather than left in the catalogue, because
            # a divergence discovered in production is worth less than one
            # stated on the control the day it is written — and the author of an
            # Excel formula has a spreadsheet open beside them.
            for note in _divergences(control):
                ctx.emit(f"    {note}")
            ctx.emit("")
        return EXIT_OK


def _divergences(control: Any) -> list[str]:
    """How this control's functions differ from a spreadsheet, and where.

    Both kinds are reported: a function whose *semantics* differ from Excel, and
    one an engine cannot run at all. The second matters as much as the first —
    an author writing a formula that will be refused on the estate's own engine
    should learn it now rather than at the first execution.
    """
    from prama.pql.library import FUNCTIONS

    notes: list[str] = []
    for name in sorted(_function_names(control)):
        function = FUNCTIONS.find(name)
        if function is None:
            continue
        if function.excel_divergence:
            notes.append(f"{name} differs from Excel: {function.excel_divergence}")
        if function.unsupported_on:
            notes.append(
                f"{name} cannot run on "
                + ", ".join(sorted(function.unsupported_on))
                + " — the control will be refused there rather than approximated"
            )
    return notes


def _function_names(node: Any) -> set[str]:
    """Every function called anywhere in a control, however deeply nested."""
    from prama.pql import ast as pql_ast

    found: set[str] = set()
    stack: list[Any] = [node]
    seen: set[int] = set()
    while stack:
        current = stack.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, pql_ast.FunctionCall):
            found.add(current.name.upper())
        for value in getattr(current, "__slots__", ()) or ():
            child = getattr(current, value, None)
            if isinstance(child, pql_ast.Node):
                stack.append(child)
            elif isinstance(child, (tuple, list)):
                stack.extend(item for item in child if isinstance(item, pql_ast.Node))
    return found


@dataclasses.dataclass(frozen=True, slots=True)
class _Coverage:
    """One engine's share of the function catalogue."""

    engine: str
    total: int
    refused: tuple[str, ...] = ()

    @property
    def pushes_down(self) -> int:
        return self.total - len(self.refused)

    @property
    def share(self) -> float:
        return self.pushes_down / self.total if self.total else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "total": self.total,
            "pushes_down": self.pushes_down,
            "share": self.share,
            "refused": list(self.refused),
        }


class ControlFunctionsCommand(Command):
    name = "functions"
    help = "the function catalogue, and how much of it each engine can run"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--engine", default="", help="one engine, or omit for the coverage table"
        )

    def run(self, ctx: CommandContext) -> int:
        """W11.13 — pushdown coverage, per engine.

        The number a deployment needs before it picks a warehouse: what
        *fraction* of the language runs where the data is. A function that
        cannot be pushed down is not merely slower — it is refused, because
        approximating it would make the same control mean two things on two
        engines, and nothing would notice.
        """
        from prama.backend import DIALECTS
        from prama.pql.library import FUNCTIONS

        names = FUNCTIONS.names()
        engines = sorted(DIALECTS) if not ctx.args.engine else [ctx.args.engine]
        if ctx.args.engine and ctx.args.engine not in DIALECTS:
            raise ValidationError(
                f"no engine called {ctx.args.engine!r}",
                remedy=f"One of: {', '.join(sorted(DIALECTS))}.",
                context={"engine": ctx.args.engine},
            )

        rows: list[_Coverage] = []
        for engine in engines:
            refused = sorted(
                name
                for name in names
                if (found := FUNCTIONS.find(name)) is not None and not found.supports(engine)
            )
            rows.append(_Coverage(engine=engine, total=len(names), refused=tuple(refused)))

        if ctx.json_output:
            ctx.emit_json({"functions": list(names), "coverage": [row.to_dict() for row in rows]})
            return EXIT_OK

        ctx.emit(f"{len(names)} function(s) in the catalogue.")
        ctx.emit()
        for row in rows:
            ctx.emit(f"  {row.engine:<12} {row.pushes_down}/{row.total} ({row.share:.0%})")
            for name in row.refused:
                # Named, not counted. "24 of 25" tells a reader something is
                # missing and not whether it is the one they need.
                ctx.emit(f"      refused: {name}")
        ctx.emit()
        ctx.emit("A refused function is refused, never approximated: the same control")
        ctx.emit("meaning two things on two engines is the failure this prevents.")
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
            _write_source(Path(ctx.args.file), formatted)
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
        from prama.ir.resolve import resolved
        from prama.pql.errors import PqlUnsupportedError

        controls, _, failure = _read(ctx)
        if failure is not None:
            return failure
        plans = []
        for control in controls:
            try:
                # `resolved`, not a bare `Lowerer`. Its module says why: it is
                # the one function that lowers a control properly, and every
                # call site uses it. This one did not, so every
                # `IN CODELIST` control was refused as "not registered" against
                # lists the product ships (QA finding Q-14).
                plans.append(resolved(control))
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
        result = importer(ctx.args.source_format).read_text(_read_source(path))
        if ctx.json_output:
            ctx.emit_json(result.to_dict())
            return EXIT_OK
        if ctx.args.out:
            _write_source(
                Path(ctx.args.out),
                "\n\n".join(c.render() for c in result.controls) + "\n",
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
            ControlFunctionsCommand(),
            ControlCompileCommand(),
            ControlRunCommand(),
            ControlImportCommand(),
        ]


def _write_source(path: Path, text: str) -> None:
    """Write, or refuse in a way that says which file and why.

    A path under an unwritable or non-existent directory raised
    `FileNotFoundError` or `PermissionError` straight out of `io.open`, so the
    person who mistyped `--out` got a stack trace through pathlib rather than
    the path they mistyped. QA round 3, Q-68.
    """
    try:
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise ValidationError(
            f"{path} could not be written: {exc.strerror or exc}",
            remedy=(
                "Check the directory exists and is writable. `--out` names the "
                "file to create, not the directory to create it in."
            ),
            context={"file": str(path)},
        ) from None


def _read_source(path: Path) -> str:
    """The file's text, or a typed refusal naming why it could not be read.

    `read_text(encoding="utf-8")` raises `UnicodeDecodeError` on a file saved as
    latin-1 — which is what an editor on a Windows desktop produces by default —
    and that reached the terminal as a stack trace ending in a codec frame.
    Nothing in it said "your file is not UTF-8", and nothing said which byte.
    QA round 3, Q-68.
    """
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError(
            f"{path} is not valid UTF-8: byte 0x{exc.object[exc.start]:02x} at position "
            f"{exc.start} is not part of a UTF-8 character",
            remedy=(
                "Save the file as UTF-8. An editor defaulting to latin-1 or "
                "cp1252 produces this whenever a control quotes an accented "
                "word in its BECAUSE clause."
            ),
            context={"file": str(path), "position": exc.start},
        ) from None
    except OSError as exc:
        raise ValidationError(
            f"{path} could not be read: {exc.strerror or exc}",
            remedy="Check the path exists and that you have permission to read it.",
            context={"file": str(path)},
        ) from None


def _read(ctx: CommandContext) -> tuple[list[Control], str, int | None]:
    """Read and parse the file, or report why not.

    A parse error is rendered with its caret rather than as a traceback: the
    reader is somebody editing a control, and the position is the whole point.
    """
    path = Path(ctx.args.file)
    if not path.is_file():
        ctx.emit(f"no such file: {path}")
        return [], "", EXIT_USAGE
    source = _read_source(path)
    try:
        return list(parse(source).all_controls), source, None
    except PqlError as exc:
        ctx.emit(exc.render())
        return [], source, EXIT_ERROR


def _head(control: Control) -> str:
    return control.render().splitlines()[0]


class ControlRunCommand(Command):
    name = "run"
    help = "execute the estate's live controls and record the evidence"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--tenant", default="", help="the estate to run")
        parser.add_argument(
            "--against",
            required=True,
            help="path to the DuckDB or SQLite file holding the data to check",
        )
        parser.add_argument(
            "--dialect",
            default="duckdb",
            choices=["duckdb", "sqlite"],
            help="which engine the SQL is compiled for",
        )
        parser.add_argument(
            "--samples",
            action="store_true",
            help="keep failing rows as evidence (they become personal data on a clock)",
        )
        parser.add_argument(
            "--due-only",
            action="store_true",
            help=(
                "run only what each control's schedule says is due; without it "
                "everything live runs, which is what typing this means"
            ),
        )

    def run(self, ctx: CommandContext) -> int:
        """Run every live control and write the results into the ledger.

        Deliberately narrow: it takes a file, not a connection. The runner's
        whole interface to a source is a callable that takes SQL and returns
        rows, so pointing it at a warehouse is a matter of supplying a
        different callable — and until the connector SPI exposes a query path,
        pretending otherwise here would mean reaching into a connector's
        private methods from the CLI.
        """
        import asyncio

        from prama.connect.sources.query import executor_for
        from prama.db import Database
        from prama.execute import ControlRun

        tenant = ctx.args.tenant or ctx.config.get_str("tenancy.default_tenant", "")
        if not tenant:
            raise PramaError(
                "no tenant to run",
                code="CLI.NO_TENANT",
                remedy="Pass --tenant, or set tenancy.default_tenant.",
            )
        execute, close = executor_for(ctx.args.against, ctx.args.dialect)
        database = Database.from_config(ctx.config)

        async def go() -> Any:
            await database.start()
            try:
                async with database.unit_of_work() as uow:
                    return await ControlRun(
                        uow,
                        tenant,
                        execute=execute,
                        sample=execute if ctx.args.samples else None,
                        engine=ctx.args.dialect,
                        triggered_by="schedule" if ctx.args.due_only else "manual",
                        respect_schedule=ctx.args.due_only,
                    ).execute_all()
            finally:
                await database.stop()
                close()

        report = asyncio.run(go())
        if ctx.json_output:
            ctx.emit_json(
                {
                    "run_id": report.run_id,
                    "controls": len(report.outcomes),
                    "executed": report.executed,
                    "failed_to_run": report.failed_to_run,
                    "verdicts": report.verdicts,
                    "skipped": len(report.skipped),
                    "unschedulable": [
                        {"control_id": s.control_id, "dataset": s.dataset, "detail": s.detail}
                        for s in report.unschedulable
                    ],
                    "summary": report.describe(),
                }
            )
            return EXIT_OK

        ctx.emit(f"run {report.run_id}")
        ctx.emit(f"  {report.describe()}")
        for outcome in report.outcomes:
            if not outcome.ran:
                ctx.emit(f"  ! {outcome.record.dataset}: {outcome.error}")
        for skipped in report.unschedulable:
            # Listed even though nothing failed: these will never run again,
            # and no verdict anywhere will say so.
            ctx.emit(f"  ! {skipped.dataset}: {skipped.detail}")
        # Non-zero when something did not run *or* can never run. A schedule
        # nobody can read is as much a gap in coverage as a source that is
        # down, and it is the quieter of the two.
        return EXIT_ERROR if (report.failed_to_run or report.unschedulable) else EXIT_OK
