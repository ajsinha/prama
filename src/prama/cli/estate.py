"""Estate commands: export the semantic layer to files, and diff against them.

The half of GitOps that makes the serialiser useful. ``export`` writes the
declared estate as reviewable YAML; ``diff`` compares a directory against the
store and reports disagreement in both directions without resolving it.

Deliberately absent: ``apply``. Writing a directory back into the store is a
mutation of a governed record, and it belongs behind the same approval workflow
as any other change rather than behind a shell command — it arrives with the
CI integration in Wave 4, where a pull request is the approval.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Any

from prama.cli.base import EXIT_DRIFT, EXIT_OK, Command, CommandContext, CommandGroup
from prama.db import Database
from prama.semantic.gitops import DriftDetector, EstateSerialiser


class EstateExportCommand(Command):
    name = "export"
    help = "write the declared estate to a directory of reviewable YAML"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--tenant", required=True, help="tenant id to export")
        parser.add_argument("--out", default="prama", help="output directory")
        parser.add_argument(
            "--dry-run", action="store_true", help="list the files without writing them"
        )

    def run(self, ctx: CommandContext) -> int:
        files = asyncio.run(_collect(ctx, ctx.args.tenant))
        root = Path(ctx.args.out)
        if not ctx.args.dry_run:
            for relative, text in files.items():
                path = root / Path(relative).relative_to("prama")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
        if ctx.json_output:
            ctx.emit_json({"written": not ctx.args.dry_run, "files": sorted(files)})
        else:
            verb = "would write" if ctx.args.dry_run else "wrote"
            for relative in sorted(files):
                ctx.emit(f"  {relative}")
            ctx.emit(f"{verb} {len(files)} file(s) under {root}")
        return EXIT_OK


class EstateDiffCommand(Command):
    name = "diff"
    help = "compare a directory against the store; report drift, never resolve it"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--tenant", required=True)
        parser.add_argument("--dir", default="prama", help="directory to compare against")

    def run(self, ctx: CommandContext) -> int:
        files = asyncio.run(_collect(ctx, ctx.args.tenant))
        serialiser = EstateSerialiser()
        root = Path(ctx.args.dir)

        store: dict[str, dict[str, Any]] = {}
        repository: dict[str, dict[str, Any]] = {}
        for relative, text in files.items():
            key = str(Path(relative).relative_to("prama"))
            store[key] = serialiser.load(text).get("spec", {})
        for path in sorted(root.rglob("*.yaml")):
            key = str(path.relative_to(root))
            repository[key] = serialiser.load(path.read_text(encoding="utf-8")).get("spec", {})

        drifts = DriftDetector().compare(store, repository, kind="Document")
        if ctx.json_output:
            ctx.emit_json({"in_sync": not drifts, "drifts": [d.to_dict() for d in drifts]})
        else:
            ctx.emit(DriftDetector.summarise(drifts))
        return EXIT_OK if not drifts else EXIT_DRIFT


class EstateMaturityCommand(Command):
    name = "maturity"
    help = "score how much of the estate has actually been described"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--tenant", required=True)
        parser.add_argument("--domain", default=None)

    def run(self, ctx: CommandContext) -> int:
        from prama.semantic.services import EstateService

        async def compute() -> Any:
            database = Database.from_config(ctx.config)
            await database.start()
            try:
                async with database.unit_of_work() as uow:
                    return await EstateService(uow).maturity(
                        ctx.args.tenant, domain_id=ctx.args.domain
                    )
            finally:
                await database.stop()

        score = asyncio.run(compute())
        if ctx.json_output:
            ctx.emit_json(score.to_dict())
        else:
            ctx.emit(f"{score.scope}: {score.percent}% — reached stage '{score.stage.value}'")
            for line in score.explain():
                ctx.emit(f"  {line}")
            if score.actions:
                ctx.emit("\nnext, ranked by controls unlocked per item of effort:")
                for action in score.actions[:5]:
                    ctx.emit(f"  {action.headline}  (+{action.estimated_controls} controls)")
        return EXIT_OK


class EstateCommand(CommandGroup):
    name = "estate"
    help = "export, diff and score the declared estate"

    def commands(self) -> list[Command]:
        return [EstateExportCommand(), EstateDiffCommand(), EstateMaturityCommand()]


async def _collect(ctx: CommandContext, tenant_id: str) -> dict[str, str]:
    """Render every declared object to its documented path."""
    serialiser = EstateSerialiser()
    database = Database.from_config(ctx.config)
    await database.start()
    try:
        async with database.unit_of_work() as uow:
            datasets = await uow.datasets.list_current(tenant_id, limit=10_000)
            slugs = {d.dataset_id: d.slug for d in datasets}
            files: dict[str, str] = {}

            for dataset in datasets:
                attributes = await uow.attributes.for_dataset(dataset.dataset_id)
                files[serialiser.path_for("Dataset", dataset.slug)] = serialiser.dump(
                    serialiser.dataset_document(dataset, attributes, slug_of=slugs)
                )
            for relationship in await uow.relationships.list_current(tenant_id, limit=10_000):
                name = f"{relationship.kind}_{relationship.relationship_id[-8:].lower()}"
                files[serialiser.path_for("Relationship", name)] = serialiser.dump(
                    serialiser.relationship_document(relationship, slug_of=slugs)
                )
            for journey in await uow.journeys.list_current(tenant_id, limit=10_000):
                files[serialiser.path_for("Journey", journey.slug)] = serialiser.dump(
                    serialiser.journey_document(journey, slug_of=slugs)
                )
            for connection in await uow.connections.list_current(tenant_id, limit=10_000):
                files[serialiser.path_for("Connection", connection.slug)] = serialiser.dump(
                    serialiser.connection_document(connection)
                )
            return files
    finally:
        await database.stop()
