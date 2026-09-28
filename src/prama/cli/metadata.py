"""``prama metadata`` — templates, values, business context, and the rules they imply.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from prama.cli.base import EXIT_OK, Command, CommandContext, CommandGroup
from prama.cli.llm import _tenant_flag, _with_uow
from prama.core.errors import ValidationError


class TemplateInstallCommand(Command):
    name = "install"
    help = "install a starter template (data-quality-attribute, data-quality-dataset)"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("starter")
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        from prama.semantic.services.metadata import install_starter

        result = _with_uow(ctx, lambda uow, t: install_starter(uow, t, ctx.args.starter))
        ctx.emit(f"{result['template']}: {result['added']} added, {result['changed']} changed")
        return EXIT_OK


class TemplateAddCommand(Command):
    name = "add"
    help = "save your own template from a YAML file"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("file")
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        import yaml

        from prama.semantic.services.metadata import save_template

        path = Path(ctx.args.file)
        if not path.is_file():
            raise ValidationError(f"there is no file at {path}", remedy="Pass the YAML file.")
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        result = _with_uow(ctx, lambda uow, t: save_template(uow, t, document))
        ctx.emit(f"{result['template']}: {result['added']} added, {result['changed']} changed")
        return EXIT_OK


class SetCommand(Command):
    name = "set"
    help = "set metadata on a dataset or dataset.attribute: field=value …"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("target", help="dataset slug, or dataset.attribute")
        parser.add_argument("pairs", nargs="+", help="field=value (empty value clears)")
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        from prama.semantic.services.metadata import set_values

        values = {}
        for pair in ctx.args.pairs:
            key, sep, value = pair.partition("=")
            if not sep:
                raise ValidationError(f"{pair!r} is not field=value", remedy="Write field=value.")
            values[key.strip()] = value
        changed = _with_uow(ctx, lambda uow, t: set_values(uow, t, ctx.args.target, values))
        ctx.emit(f"{ctx.args.target}: {', '.join(changed) or 'nothing changed'}")
        return EXIT_OK


class ContextCommand(Command):
    name = "context"
    help = "record the business context of a dataset or dataset.attribute"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("target")
        parser.add_argument("--text", required=True)
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        from prama.semantic.services.metadata import set_context

        _with_uow(ctx, lambda uow, t: set_context(uow, t, ctx.args.target, ctx.args.text))
        ctx.emit(f"{ctx.args.target}: business context recorded (as an amendment)")
        return EXIT_OK


class ShowCommand(Command):
    name = "show"
    help = "a dataset's context, metadata, attributes, rules and implied rules"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("dataset")
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        from prama.semantic.services.metadata import describe

        d: dict[str, Any] = _with_uow(ctx, lambda uow, t: describe(uow, t, ctx.args.dataset))
        if ctx.json_output:
            ctx.emit_json(d)
            return EXIT_OK
        ctx.emit(f"{d['dataset']} ({d['slug']})")
        ctx.emit(f"  context: {d['business_context'] or '-'}")
        for key, value in d["metadata"].items():
            ctx.emit(f"  {key}: {value}")
        for a in d["attributes"]:
            extras = ", ".join(f"{k}={v}" for k, v in a["metadata"].items())
            ctx.emit(f"  .{a['name']}  {a['business_context'] or a['definition']}  {extras}")
        for r in d["rules"]:
            ctx.emit(f"  rule [{r['status']}] {r['pql'].splitlines()[0]}")
        for p in d["proposals"]:
            ctx.emit(f"  implied: {p.get('pql')}")
        return EXIT_OK


class FindCommand(Command):
    name = "find"
    help = "find datasets and attributes by meaning (business context, definitions, metadata)"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("text")
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        from prama.semantic.services.metadata import search

        hits = _with_uow(ctx, lambda uow, t: search(uow, t, ctx.args.text))
        if ctx.json_output:
            ctx.emit_json(hits)
            return EXIT_OK
        for h in hits:
            ctx.emit(f"{h['kind']:<9} {h['name']}  {(h['context'] or '')[:100]}")
        if not hits:
            ctx.emit("Nothing found. Business context is what this searches.")
        return EXIT_OK


class AskCommand(Command):
    name = "ask"
    help = "which datasets are fit for a purpose (embeddings if configured, else BM25)"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("question")
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        from prama.semantic.services.finding import find_data

        answer: dict[str, Any] = _with_uow(
            ctx, lambda uow, t: find_data(uow, t, ctx.args.question, config=ctx.config)
        )
        if ctx.json_output:
            ctx.emit_json(answer)
            return EXIT_OK
        ctx.emit(f"ranked by {answer['ranked_by']}")
        for m in answer["matches"]:
            ctx.emit(f"{m['kind']:<9} {m['name']}  {m['why'] or (m['context'] or '')[:90]}")
        if not answer["matches"]:
            ctx.emit("Nothing found. Business context is what this reads.")
        return EXIT_OK


class CorrelateCommand(Command):
    name = "correlate"
    help = "attributes that mean the same thing across datasets, and where they disagree"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        from prama.semantic.services.metadata import correlation

        result: dict[str, Any] = _with_uow(ctx, lambda uow, t: correlation(uow, t))
        if ctx.json_output:
            ctx.emit_json(result)
            return EXIT_OK
        if not result["groups"]:
            ctx.emit("No shared meanings yet: bind attributes to concepts or glossary terms.")
        for g in result["groups"]:
            ctx.emit(f"{g['meaning']} (same {g['by']}): {', '.join(g['members'])}")
        for f in result["findings"]:
            ctx.emit(f"  INCONSISTENT {f['aspect']}: {f['meaning']}: {f['detail']}")
        for p in result["proposals"]:
            ctx.emit(f"  proposed: {p['pql'].split(' BECAUSE')[0]}")
        return EXIT_OK


class _Template(CommandGroup):
    name = "template"
    help = "metadata templates"

    def commands(self) -> list[Command]:
        return [TemplateInstallCommand(), TemplateAddCommand()]


class MetadataCommand(CommandGroup):
    name = "metadata"
    help = "metadata and business context on datasets and attributes"

    def commands(self) -> list[Command]:
        return [
            _Template(),
            SetCommand(),
            ContextCommand(),
            ShowCommand(),
            FindCommand(),
            AskCommand(),
            CorrelateCommand(),
        ]
