"""``prama contract`` — data contracts at the point a change is proposed.

The whole value of a contract is that breaking it is *noticed before it ships*.
A contract checked nightly tells you what broke yesterday; a contract checked in
a pull request tells you what is about to.

So these commands are built for a build system rather than for a person, and the
exit code is the interface:

* ``0`` — the contract holds.
* ``3`` — the contract is breached. Distinct from 1, because a build wants to
  tell "your change broke the contract" apart from "the checker fell over", and
  a single non-zero code makes a broken checker look like a broken change.
* ``1`` — the check could not be made.

**A breach and a warning are different exits.** A removed column breaks every
consumer; an added one breaks none. Treating them alike either blocks harmless
changes — after which the gate is disabled — or lets through the one change that
matters.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from prama.cli.base import EXIT_DRIFT, EXIT_OK, Command, CommandContext, CommandGroup
from prama.contract import odcs, quality
from prama.contract.diff import compare, compare_schema
from prama.core.errors import ValidationError


def _load(path: str, what: str) -> Any:
    target = Path(path)
    if not target.exists():
        raise ValidationError(
            f"there is no {what} at {target}",
            remedy="Check the path.",
            context={"path": str(target)},
        )
    text = target.read_text()
    try:
        if target.suffix in (".yaml", ".yml"):
            import yaml

            return yaml.safe_load(text)
        return json.loads(text)
    except Exception as exc:
        syntax = "YAML" if target.suffix in (".yaml", ".yml") else "JSON"
        raise ValidationError(
            f"{target} could not be read as {syntax}",
            remedy="Check the syntax.",
            context={"path": str(target)},
            cause=exc,
        ) from exc


def _rows(path: str) -> list[dict[str, Any]]:
    """Rows from JSON, JSON Lines or CSV, chosen by suffix."""
    target = Path(path)
    if not target.exists():
        raise ValidationError(
            f"there is no data file at {target}",
            remedy="Check the path.",
            context={"path": str(target)},
        )
    if target.suffix == ".csv":
        import csv

        with target.open(newline="") as handle:
            return list(csv.DictReader(handle))
    if target.suffix in (".jsonl", ".ndjson"):
        return [json.loads(line) for line in target.read_text().splitlines() if line.strip()]
    payload = json.loads(target.read_text())
    if isinstance(payload, dict):
        payload = payload.get("rows", [])
    if not isinstance(payload, list):
        raise ValidationError(
            f"{target} does not hold a list of rows",
            remedy="Give a JSON array, a .jsonl file, or a .csv.",
            context={"path": str(target)},
        )
    return payload


class ContractImportCommand(Command):
    name = "import"
    help = "read an ODCS contract as a Prama declaration, and say what did not come across"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("path", help="an ODCS contract, .yaml or .json")
        parser.add_argument(
            "--controls",
            action="store_true",
            help="also print the controls its quality blocks become, and the ones they do not",
        )

    def run(self, ctx: CommandContext) -> int:
        document = _load(ctx.args.path, "contract")
        result = odcs.load(document)
        checks = quality.controls_from(document)
        if ctx.json_output:
            ctx.emit_json({**result.to_dict(), "quality": checks.to_dict()})
            return EXIT_OK if result.declaration else EXIT_DRIFT
        ctx.emit(result.describe())
        if result.declaration is None:
            return EXIT_DRIFT
        # Listed rather than summarised. A count of ignored fields tells a
        # reader something was lost and not what, which is the half that
        # decides whether it matters.
        for note in result.defaulted:
            ctx.emit(f"  default: {note}")
        for note in result.ignored:
            ctx.emit(f"  ignored: {note}")

        if checks.offered:
            # Always, not only under --controls. A contract's quality blocks are
            # the part a consumer is relying on, and importing the schema while
            # silently taking on none of the checks is the failure this whole
            # module is about.
            ctx.emit()
            ctx.emit(checks.describe())
            if ctx.args.controls:
                for control in checks.controls:
                    ctx.emit(f"  {control}")
        return EXIT_OK


class ContractExportCommand(Command):
    name = "export"
    help = "write a declared dataset as an ODCS contract"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("dataset", help="the declared dataset's slug")
        parser.add_argument("--tenant", default="", help="defaults to tenancy.default_tenant")
        parser.add_argument("--out", default="", help="where to write; stdout if omitted")

    def run(self, ctx: CommandContext) -> int:
        import asyncio

        from prama.db import Database
        from prama.derive.persisted import dataset_declaration_of

        tenant = ctx.args.tenant or ctx.config.get_str("tenancy.default_tenant", "")
        if not tenant:
            raise ValidationError(
                "no tenant to export from",
                remedy="Pass --tenant, or set tenancy.default_tenant.",
            )
        database = Database.from_config(ctx.config)

        async def go() -> Any:
            await database.start()
            try:
                async with database.unit_of_work() as uow:
                    versions = await uow.datasets.list_current(tenant, limit=5000)
                    version = next((v for v in versions if v.slug == ctx.args.dataset), None)
                    if version is None:
                        return None
                    attributes = await uow.attributes.for_dataset(
                        version.dataset_id, tenant_id=tenant
                    )
                    return dataset_declaration_of(version, attributes)
            finally:
                await database.stop()

        declaration = asyncio.run(go())
        if declaration is None:
            raise ValidationError(
                f"no dataset called {ctx.args.dataset!r} is declared",
                remedy="Check the slug against `prama estate export`.",
                context={"dataset": ctx.args.dataset},
            )
        document = odcs.dump(declaration)
        rendered = json.dumps(document, indent=2) + "\n"
        if ctx.args.out:
            Path(ctx.args.out).write_text(rendered)
            ctx.emit(f"wrote {ctx.args.out}")
        else:
            ctx.emit(rendered.rstrip())
        return EXIT_OK


class ContractDiffCommand(Command):
    name = "diff"
    help = "what changed between two versions of a dataset"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("before")
        parser.add_argument("after")
        parser.add_argument(
            "--key",
            default="",
            help=(
                "comma-separated columns identifying a row. Without it this is a "
                "membership comparison and says so, because nothing tells one row "
                "from another"
            ),
        )
        parser.add_argument(
            "--ignore", default="", help="comma-separated columns to leave out of the comparison"
        )

    def run(self, ctx: CommandContext) -> int:
        """Non-zero when anything differs, so a build can gate on it."""
        diff = compare(
            _rows(ctx.args.before),
            _rows(ctx.args.after),
            key=[part.strip() for part in ctx.args.key.split(",") if part.strip()],
            ignore=[part.strip() for part in ctx.args.ignore.split(",") if part.strip()],
        )
        if ctx.json_output:
            ctx.emit_json(diff.to_dict())
            return EXIT_OK if diff.is_identical else EXIT_DRIFT

        ctx.emit(diff.describe())
        for change in diff.changed_examples[:10]:
            ctx.emit(f"  {change.render()}")
        if diff.added_examples:
            ctx.emit(f"  added: {', '.join(str(k) for k in diff.added_examples[:10])}")
        if diff.removed_examples:
            ctx.emit(f"  removed: {', '.join(str(k) for k in diff.removed_examples[:10])}")
        return EXIT_OK if diff.is_identical else EXIT_DRIFT


class ContractCheckCommand(Command):
    name = "check"
    help = "fail a build when a change breaches a contract's schema"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("contract", help="the ODCS contract the data must satisfy")
        parser.add_argument("--data", required=True, help="rows to check it against")
        parser.add_argument(
            "--allow-additions",
            action="store_true",
            help=(
                "treat a new column as acceptable. A removed column breaks every "
                "consumer; an added one breaks none, and blocking both is how a "
                "gate gets switched off"
            ),
        )

    def run(self, ctx: CommandContext) -> int:
        result = odcs.load(_load(ctx.args.contract, "contract"))
        if result.declaration is None:
            raise ValidationError(
                "that contract declares no schema, so there is nothing to check against",
                remedy="Check the file.",
                context={"contract": ctx.args.contract},
            )

        promised = {a.name: a for a in result.declaration.attributes}
        rows = _rows(ctx.args.data)
        present = {column for row in rows for column in row}

        schema = compare_schema(list(promised), present)
        # Missing is a breach; extra is a warning unless the contract is closed.
        missing = schema.removed
        extra = schema.added

        # A promised-mandatory column that is null anywhere is a breach too: the
        # contract's `required` is a promise about values, not only about the
        # column existing, and checking only the header would pass a table of
        # nulls.
        empty_mandatory = tuple(
            sorted(
                name
                for name, attribute in promised.items()
                if attribute.optionality.name == "MANDATORY"
                and name in present
                and any(row.get(name) in (None, "") for row in rows)
            )
        )

        # An empty file establishes nothing, so it is never a pass. This has to
        # be decided before the output branches: the check used to live after
        # the `--json` early return, so `prama contract check` refused an empty
        # file and `prama --json contract check` — the spelling a build uses —
        # let it through with exit 0. The gate was open on exactly the path it
        # exists to guard. It is also reported as its own field, because a
        # caller parsing the JSON cannot otherwise tell "nothing was checked"
        # from "checked, and every promise held".
        checked = bool(rows)
        breached = (
            not checked
            or bool(missing or empty_mandatory)
            or (bool(extra) and not ctx.args.allow_additions)
        )

        payload = {
            "contract": ctx.args.contract,
            "rows": len(rows),
            # With no rows the column comparison is vacuous — every promised
            # column looks absent because there is nothing for it to be in — so
            # reporting it as a schema breach would name the wrong cause.
            "missing_columns": list(missing) if checked else [],
            "unexpected_columns": list(extra) if checked else [],
            "mandatory_with_nulls": list(empty_mandatory) if checked else [],
            "checked": checked,
            "breached": breached,
        }
        if ctx.json_output:
            ctx.emit_json(payload)
            return EXIT_DRIFT if breached else EXIT_OK

        if not checked:
            # Loud, because a contract check over no rows passes every test it
            # can run and has established nothing.
            ctx.emit("The data file holds no rows, so nothing was checked.")
            return EXIT_DRIFT

        if missing:
            ctx.emit(f"BREACH — promised column(s) absent: {', '.join(missing)}")
        if empty_mandatory:
            ctx.emit(
                "BREACH — column(s) promised as required hold empty values: "
                + ", ".join(empty_mandatory)
            )
        if extra:
            label = "note" if ctx.args.allow_additions else "BREACH"
            ctx.emit(f"{label} — column(s) not in the contract: {', '.join(extra)}")
        if not breached:
            ctx.emit(
                f"The contract holds over {len(rows):,} row(s): every promised column "
                "is present and every required one is populated."
            )
        return EXIT_DRIFT if breached else EXIT_OK


class ContractCommand(CommandGroup):
    name = "contract"
    help = "data contracts: import, export, diff, and gate a build on them"

    def commands(self) -> list[Command]:
        return [
            ContractImportCommand(),
            ContractExportCommand(),
            ContractDiffCommand(),
            ContractCheckCommand(),
        ]


__all__ = [
    "ContractCheckCommand",
    "ContractCommand",
    "ContractDiffCommand",
    "ContractExportCommand",
    "ContractImportCommand",
]
