"""``prama lsp`` — a Language Server for PQL, on stdio.

Runs in the foreground and speaks LSP on stdin and stdout, which is how an
editor launches one. Everything Prama would normally print goes to stderr: a
single stray line on stdout desynchronises the framing and the editor reports a
protocol error rather than the banner you meant it to show.

The catalogue is the interesting argument. Without one the server still parses,
type-checks what it can and offers keywords and functions — and says on every
affected control that nothing was checked against a schema, which is a different
statement from "this control is fine". Loading it from a file rather than a
database is deliberate: an editor plugin that needed warehouse credentials to
underline a typo would not be installed.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from prama.cli.base import EXIT_OK, Command, CommandContext, CommandGroup
from prama.core.errors import ValidationError
from prama.pql.types import Catalogue


class LspServeCommand(Command):
    name = "serve"
    help = "run the PQL language server on stdio"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--catalogue",
            default="",
            help=(
                "a JSON file of dataset schemas to check against; without it "
                "nothing is checked against a schema and the server says so"
            ),
        )

    def run(self, ctx: CommandContext) -> int:
        from prama.lsp import serve_stdio

        catalogue = Catalogue()
        source = ""
        if ctx.args.catalogue:
            catalogue = load_catalogue(Path(ctx.args.catalogue))
            source = ctx.args.catalogue
        # To stderr, always. stdout is the protocol stream.
        print(
            f"prama lsp: {len(catalogue.datasets)} dataset(s)"
            + (f" from {source}" if source else " — no catalogue, nothing schema-checked"),
            file=sys.stderr,
        )
        return serve_stdio(catalogue=catalogue, catalogue_source=source)


class LspCatalogueCommand(Command):
    name = "catalogue"
    help = "write the estate's schemas as a file the language server can read"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--tenant", default="", help="defaults to tenancy.default_tenant")
        parser.add_argument("--out", default="prama-catalogue.json", help="where to write it")

    def run(self, ctx: CommandContext) -> int:
        """Export once, edit offline.

        A file rather than a live connection, so an editor keeps working on a
        train and a laptop with no warehouse credentials still underlines a
        typo. The cost is that the file goes stale, which is why it records when
        it was written — a catalogue with no date is one nobody can judge.
        """
        import asyncio

        from prama.core.clock import utc_now
        from prama.db import Database

        tenant = ctx.args.tenant or ctx.config.get_str("tenancy.default_tenant", "")
        if not tenant:
            raise ValidationError(
                "no tenant to export",
                remedy="Pass --tenant, or set tenancy.default_tenant.",
            )
        database = Database.from_config(ctx.config)

        async def go() -> dict[str, dict[str, str]]:
            await database.start()
            try:
                async with database.unit_of_work() as uow:
                    versions = await uow.datasets.list_current(tenant, limit=5000)
                    out: dict[str, dict[str, str]] = {}
                    for version in versions:
                        attributes = await uow.attributes.for_dataset(
                            version.dataset_id, tenant_id=tenant
                        )
                        out[version.slug] = {
                            a.name: (getattr(a, "physical_type", "") or "") for a in attributes
                        }
                    return out
            finally:
                await database.stop()

        datasets = asyncio.run(go())
        payload = {
            "written_at": utc_now().isoformat(),
            "tenant": tenant,
            "datasets": datasets,
        }
        # An --out under a path segment that is a file, or in a directory
        # nobody may write, reached the terminal as NotADirectoryError or
        # PermissionError. The command's whole job is to produce a file, so
        # failing to is the one outcome it must explain. QA round 4, CLI-253.
        out = Path(ctx.args.out)
        try:
            out.write_text(json.dumps(payload, indent=2) + "\n")
        except OSError as exc:
            raise ValidationError(
                f"{out} could not be written: {exc.strerror or exc}",
                remedy=(
                    "Check the directory exists and is writable. --out names the "
                    "file to create, not the directory to create it in."
                ),
                context={"path": str(out)},
            ) from None
        columns = sum(len(v) for v in datasets.values())
        if ctx.json_output:
            ctx.emit_json({"path": ctx.args.out, "datasets": len(datasets), "columns": columns})
            return EXIT_OK
        ctx.emit(f"wrote {ctx.args.out}: {len(datasets)} dataset(s), {columns} column(s)")
        if not datasets:
            ctx.emit(
                "Nothing is declared, so this catalogue checks nothing. That is a "
                "statement about the estate, not about the export."
            )
        return EXIT_OK


def load_catalogue(path: Path) -> Catalogue:
    """Read an exported catalogue.

    A missing or unreadable file is a refusal, never an empty catalogue. An
    empty catalogue silently turns every schema check off, and the editor then
    shows a clean file that has not been checked — the exact confusion the
    ``unchecked`` diagnostic level exists to prevent.
    """
    if not path.exists():
        raise ValidationError(
            f"there is no catalogue at {path}",
            remedy=(
                "Write one with `prama lsp catalogue`, or start the server without "
                "--catalogue and accept that nothing will be schema-checked."
            ),
            context={"path": str(path)},
        )
    if not path.is_file():
        # Separate from the clause above, not folded into it. A path that is
        # missing and a path that is a directory are different mistakes with
        # different fixes, and a single message covering both would name neither
        # — the same argument the empty-codelist refusal makes against reusing
        # "not registered" for "registered but empty".
        #
        # `exists()` was true for a directory, so `read_text` answered
        # `IsADirectoryError`: a stdlib error for a mistake made on a command
        # line. The fifth site of this confusion in QA round 4, after `CLI-139`
        # in `connect/sources/query.py` and three in `cli/contract.py` — and the
        # first one found by a guard rather than by hand.
        raise ValidationError(
            f"{path} is a directory, not a catalogue file",
            remedy=(
                "--catalogue names one file exported by `prama lsp catalogue`, "
                "not a directory of them."
            ),
            context={"path": str(path)},
        )
    try:
        payload = json.loads(path.read_text())
    except ValueError as exc:
        raise ValidationError(
            f"{path} is not readable as a catalogue: {exc}",
            remedy="Rewrite it with `prama lsp catalogue`.",
            context={"path": str(path)},
        ) from None
    from prama.controls.language import catalogue_from_payload

    return catalogue_from_payload(payload, where=str(path))


class LspCommand(CommandGroup):
    name = "lsp"
    help = "language server for PQL, for an editor outside the console"

    def commands(self) -> list[Command]:
        return [LspServeCommand(), LspCatalogueCommand()]


__all__ = ["LspCatalogueCommand", "LspCommand", "LspServeCommand", "load_catalogue"]
