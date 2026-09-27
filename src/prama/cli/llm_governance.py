"""``prama llm template|eval|verify`` and ``profile activate`` — governing model use.

Templates are versioned and approved by someone other than their author;
evaluation suites grade a profile or template version deterministically; with
`llm.eval.gate_activation` a version becomes current only after a passing run.
`verify` recomputes the call ledger's chain.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from prama.cli.base import EXIT_ERROR, EXIT_OK, Command, CommandContext, CommandGroup
from prama.cli.llm import _tenant_flag, _with_uow
from prama.core.errors import ValidationError


def _document(path: str) -> dict[str, Any]:
    target = Path(path)
    if not target.is_file():
        raise ValidationError(f"there is no file at {path}", remedy="Pass a YAML or JSON file.")
    text = target.read_text(encoding="utf-8")
    if target.suffix.lower() in (".yaml", ".yml"):
        import yaml

        loaded = yaml.safe_load(text)
    else:
        loaded = json.loads(text)
    if not isinstance(loaded, dict):
        raise ValidationError(f"{path} is not a mapping", remedy="Write the document as a mapping.")
    return loaded


def _gate(ctx: CommandContext) -> bool:
    return bool(ctx.config.get_bool("llm.eval.gate_activation", False))


class TemplateAddCommand(Command):
    name = "add"
    help = "record a template file as a new draft version"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("file", help="YAML: name, system, body, variables, response_schema")
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        from prama.llm.templates import parse

        template = parse(_document(ctx.args.file))

        async def work(uow: Any, tenant: str) -> int:
            row = await uow.llm_governance.add_template_version(tenant, template, by=None)
            return int(row.version)

        version = _with_uow(ctx, work)
        ctx.emit(f"{template.name} v{version} recorded as a draft ({template.content_hash[:12]})")
        return EXIT_OK


class TemplateListCommand(Command):
    name = "list"
    help = "templates and their versions"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        async def work(uow: Any, tenant: str) -> list[dict[str, Any]]:
            out = []
            for row in await uow.llm_governance.templates(tenant):
                for v in await uow.llm_governance.template_versions(tenant, row.name):
                    out.append(
                        {
                            "name": row.name,
                            "version": v.version,
                            "status": v.status,
                            "current": v.version == row.current_version,
                            "hash": v.content_hash[:12],
                        }
                    )
            return out

        rows = _with_uow(ctx, work)
        if ctx.json_output:
            ctx.emit_json(rows)
            return EXIT_OK
        if not rows:
            ctx.emit("No templates. Add one: prama llm template add explain.yaml")
        for r in rows:
            mark = " (current)" if r["current"] else ""
            ctx.emit(f"{r['name']} v{r['version']}  {r['status']}{mark}  {r['hash']}")
        return EXIT_OK


class TemplateApproveCommand(Command):
    name = "approve"
    help = "approve a template version and make it current (not by its author)"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("template")
        parser.add_argument("version", type=int)
        parser.add_argument("--by", required=True, help="the approver's principal id")
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        async def work(uow: Any, tenant: str) -> None:
            await uow.llm_governance.approve_template(
                tenant,
                ctx.args.template,
                ctx.args.version,
                by=ctx.args.by,
                require_eval=_gate(ctx),
            )

        _with_uow(ctx, work)
        ctx.emit(f"{ctx.args.template} v{ctx.args.version} approved and current")
        return EXIT_OK


class EvalRunCommand(Command):
    name = "run"
    help = "run an evaluation suite against a profile (and template) version"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("suite", help="YAML: purpose, optional template, cases with expect")
        parser.add_argument("--profile-version", type=int, default=None)
        parser.add_argument("--template-version", type=int, default=None)
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        from prama.llm.evaluation import run_suite

        document = _document(ctx.args.suite)

        async def work(uow: Any, tenant: str) -> dict[str, Any]:
            row = await run_suite(
                uow,
                tenant,
                document,
                config=ctx.config,
                profile_version=ctx.args.profile_version,
                template_version=ctx.args.template_version,
            )
            return {
                "id": row.id,
                "status": row.status,
                "cases": row.cases,
                "passed": row.passed,
                "profile_version": row.profile_version,
                "template_version": row.template_version,
                "report": json.loads(row.report_json),
            }

        result = _with_uow(ctx, work)
        if ctx.json_output:
            ctx.emit_json(result)
        else:
            ctx.emit(
                f"{result['status']}: {result['passed']} of {result['cases']} case(s) "
                f"(profile v{result['profile_version']}, template v{result['template_version']})"
            )
            for case in result["report"]:
                if not case["passed"]:
                    ctx.emit(f"  FAIL {case['case']}: {'; '.join(case['misses'])}")
        return EXIT_OK if result["status"] == "passed" else EXIT_ERROR


class EvalListCommand(Command):
    name = "list"
    help = "recent evaluation runs"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        async def work(uow: Any, tenant: str) -> list[dict[str, Any]]:
            return [
                {
                    "suite": r.suite,
                    "purpose": r.purpose,
                    "status": r.status,
                    "passed": r.passed,
                    "cases": r.cases,
                    "profile_version": r.profile_version,
                    "template_version": r.template_version,
                    "started_at": r.started_at,
                }
                for r in await uow.llm_governance.eval_runs(tenant)
            ]

        rows = _with_uow(ctx, work)
        if ctx.json_output:
            ctx.emit_json(rows)
        for r in [] if ctx.json_output else rows:
            ctx.emit(
                f"{r['started_at']}  {r['suite']}  {r['purpose']}  {r['status']} "
                f"{r['passed']}/{r['cases']}"
            )
        return EXIT_OK


class ProfileActivateCommand(Command):
    name = "activate"
    help = "make a recorded profile version current (after a passing eval, when gated)"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("purpose")
        parser.add_argument("version", type=int)
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        async def work(uow: Any, tenant: str) -> None:
            await uow.llm_governance.activate_profile(
                tenant, ctx.args.purpose, ctx.args.version, require_eval=_gate(ctx)
            )

        _with_uow(ctx, work)
        ctx.emit(f"{ctx.args.purpose}: version {ctx.args.version} is now current")
        return EXIT_OK


class VerifyCommand(Command):
    name = "verify"
    help = "recompute the model-call ledger's hash chain"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        async def work(uow: Any, tenant: str) -> tuple[bool, int, str]:
            result: tuple[bool, int, str] = await uow.llm.verify_calls(tenant)
            return result

        intact, checked, where = _with_uow(ctx, work)
        if ctx.json_output:
            ctx.emit_json({"intact": intact, "checked": checked, "break": where})
        else:
            ctx.emit(f"{checked} call(s): " + ("intact" if intact else f"BROKEN — {where}"))
        return EXIT_OK if intact else EXIT_ERROR


class TemplateCommand(CommandGroup):
    name = "template"
    help = "versioned prompt templates"

    def commands(self) -> list[Command]:
        return [TemplateAddCommand(), TemplateListCommand(), TemplateApproveCommand()]


class EvalCommand(CommandGroup):
    name = "eval"
    help = "evaluation suites, graded deterministically"

    def commands(self) -> list[Command]:
        return [EvalRunCommand(), EvalListCommand()]
