"""``prama glossary`` — the business glossary: import it, search it, bind terms.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from prama.cli.base import EXIT_OK, Command, CommandContext, CommandGroup
from prama.cli.llm import _tenant_flag, _with_uow
from prama.core.errors import ValidationError


def _json(path: str) -> Any:
    target = Path(path)
    if not target.is_file():
        raise ValidationError(
            f"there is no file at {path}", remedy="Pass the vendor's JSON export."
        )
    return json.loads(target.read_text(encoding="utf-8"))


def emit_import(ctx: CommandContext, result: dict[str, Any]) -> None:
    if ctx.json_output:
        ctx.emit_json(result)
        return
    ctx.emit(
        f"{result['vendor']}: {result['terms']} term(s), {result['edges']} edge(s); "
        f"{len(result['dropped'])} dropped"
    )
    if result.get("terms"):
        ctx.emit(
            f"  {result['terms_created']} new, {result['terms_updated']} updated, "
            f"{result['bound_to_concepts']} bound to a concept by name"
        )
    for item in result["dropped"]:
        ctx.emit(f"  DROPPED {item['source']}: {item['reason']}")


class ImportCommand(Command):
    name = "import"
    help = "import glossary terms from an Alation or Collibra export"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("export", help="the JSON the vendor's API returned")
        parser.add_argument("--from", dest="vendor", required=True, choices=["alation", "collibra"])
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        from prama.importers.catalog import ingest, read

        imported = read(ctx.args.vendor, "terms", _json(ctx.args.export))

        async def work(uow: Any, tenant: str) -> dict[str, Any]:
            return await ingest(uow, tenant, imported)

        emit_import(ctx, _with_uow(ctx, work))
        return EXIT_OK


class ListCommand(Command):
    name = "list"
    help = "terms, their definitions and what each is bound to"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--search", default="", help="name, synonym or definition text")
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        async def work(uow: Any, tenant: str) -> list[dict[str, Any]]:
            terms = (
                await uow.glossary.search(tenant, ctx.args.search)
                if ctx.args.search
                else await uow.glossary.terms(tenant)
            )
            out = []
            for term in terms:
                bindings = await uow.glossary.bindings(tenant, term_id=term.id)
                out.append(
                    {
                        "name": term.name,
                        "definition": term.definition,
                        "synonyms": json.loads(term.synonyms_json),
                        "source": term.source,
                        "status": term.status,
                        "bound": [f"{b.object_kind}:{b.object_ref}" for b in bindings],
                    }
                )
            return out

        rows = _with_uow(ctx, work)
        if ctx.json_output:
            ctx.emit_json(rows)
            return EXIT_OK
        if not rows:
            ctx.emit("No terms. Import them: prama glossary import terms.json --from alation")
        for r in rows:
            ctx.emit(f"{r['name']}  [{r['status']}, {r['source']}]")
            if r["definition"]:
                ctx.emit(f"  {r['definition'][:160]}")
            if r["synonyms"]:
                ctx.emit(f"  also: {', '.join(r['synonyms'])}")
            ctx.emit(f"  bound: {', '.join(r['bound']) or 'nothing yet'}")
        return EXIT_OK


class BindCommand(Command):
    name = "bind"
    help = "bind a term to a concept, dataset or attribute (dataset.column)"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("term")
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--concept")
        group.add_argument("--dataset")
        group.add_argument("--attribute", help="dataset.column")
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        kind, ref = next(
            (k, v)
            for k, v in (
                ("concept", ctx.args.concept),
                ("dataset", ctx.args.dataset),
                ("attribute", ctx.args.attribute),
            )
            if v
        )

        async def work(uow: Any, tenant: str) -> None:
            from prama.semantic.services.glossary import bind

            await bind(uow, tenant, ctx.args.term, kind, ref)

        _with_uow(ctx, work)
        ctx.emit(f"{ctx.args.term} bound to {kind} {ref}")
        return EXIT_OK


class GlossaryCommand(CommandGroup):
    name = "glossary"
    help = "the business glossary: import, search and bind terms"

    def commands(self) -> list[Command]:
        return [ImportCommand(), ListCommand(), BindCommand()]
