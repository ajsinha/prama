"""``prama pack`` — what a domain pack ships, and what it does not claim.

A pack that cannot be inspected from a terminal is a pack nobody audits. The
questions this answers are the ones asked before a pack is trusted rather than
after: which calendars, whose rules, which obligations, citing what — and, the
question that matters most at an examination, *what does this pack not claim to
discharge?*

Every command here is answerable without a database, so it can be run from a
change ticket by somebody who has not installed anything.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import argparse
from datetime import date
from typing import Any

from prama.cli.base import EXIT_OK, Command, CommandContext, CommandGroup
from prama.core.errors import ValidationError

#: The message formats `pack parse` reads, from the one list the API reads too.
from prama.packs.banking.readout import PARSERS as _PARSERS


class PackListCommand(Command):
    name = "list"
    help = "what the banking pack ships"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        pass

    def run(self, ctx: CommandContext) -> int:
        from prama.packs.banking import calendars, obligations, reconciliations
        from prama.packs.banking.crossfield import BANKING_FUNCTIONS
        from prama.packs.banking.readout import inventory

        payload = inventory()
        formats, regimes = payload["message_formats"], payload["regimes"]
        if ctx.json_output:
            ctx.emit_json(payload)
            return EXIT_OK

        ctx.emit("Calendars")
        for spec in calendars.SPECS:
            ctx.emit(f"  {spec.name:16} {spec.description}")
        ctx.emit()
        ctx.emit("Cross-field checks (usable from PQL as SATISFIES ...)")
        for function in BANKING_FUNCTIONS:
            ctx.emit(f"  {function.name}")
        ctx.emit()
        ctx.emit("Message formats")
        for entry in formats:
            ctx.emit(f"  {entry}")
        ctx.emit()
        ctx.emit(f"Obligations: {len(obligations.ALL_OBLIGATIONS)} across {len(regimes)} regimes")
        for regime in regimes:
            ctx.emit(f"  {regime}")
        ctx.emit(f"Reconciliation templates: {len(reconciliations.TEMPLATES)}")
        ctx.emit()
        ctx.emit("`prama pack claims` says what this pack does NOT discharge.")
        return EXIT_OK


class PackClaimsCommand(Command):
    name = "claims"
    help = "what the pack discharges with controls, and what it only supports"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        pass

    def run(self, ctx: CommandContext) -> int:
        """The question asked at an examination, answerable before one.

        A pack that listed only what it covers invites a reader to assume the
        rest. Naming the boundary is what makes the covered part believable.
        """
        from prama.packs.banking.obligations import (
            ALL_OBLIGATIONS,
            DISCHARGEABLE_PRINCIPLES,
            SUPPORTED_NOT_DISCHARGED,
        )
        from prama.packs.banking.readout import claims
        from prama.packs.banking.regimes import REGIME_SCOPE

        partial = [o for o in ALL_OBLIGATIONS if not o.is_fully_discharged]
        unconfirmed = [o for o in ALL_OBLIGATIONS if not o.citation.confirmed]

        if ctx.json_output:
            ctx.emit_json(claims())
            return EXIT_OK

        ctx.emit("Discharged by controls — testable properties of data:")
        for principle in DISCHARGEABLE_PRINCIPLES:
            covered = [o for o in ALL_OBLIGATIONS if o.principle == principle]
            ctx.emit(f"  {principle}  {len(covered)} obligation(s)")
            for obligation in covered:
                ctx.emit(f"        {obligation.identity}")
                for line in _wrap(obligation.citation.render_with_standing(), 60):
                    ctx.emit(f"            {line}")
        ctx.emit()
        ctx.emit("Supported but NOT discharged by a control:")
        for principle, how in sorted(SUPPORTED_NOT_DISCHARGED.items()):
            ctx.emit(f"  {principle}  {how}")
        ctx.emit()
        ctx.emit("Each reporting regime, and what it leaves alone:")
        for regime, scope in sorted(REGIME_SCOPE.items()):
            ctx.emit(f"  {regime}")
            for line in _wrap(scope, 68):
                ctx.emit(f"      {line}")
        ctx.emit()
        if partial:
            # Printed even when the list is short. An obligation catalogued but
            # only partly discharged reads as handled, and the reader who
            # assumes that finds out in the examination room.
            ctx.emit("Catalogued but only partly discharged:")
            for obligation in partial:
                ctx.emit(f"  {obligation.identity}")
                for line in _wrap(obligation.not_discharged, 68):
                    ctx.emit(f"      {line}")
            ctx.emit()
        ctx.emit(
            f"Citations checked against the published text: "
            f"{len(ALL_OBLIGATIONS) - len(unconfirmed)} of {len(ALL_OBLIGATIONS)}."
        )
        if unconfirmed:
            ctx.emit("The rest are cited at article or section level and are unverified.")
            ctx.emit("Your compliance function confirms them; `--json` lists which.")
        ctx.emit()
        ctx.emit("Shipping templates for the second group that checked nothing would")
        ctx.emit("be a claim this product cannot defend at an examination.")
        return EXIT_OK


class PackCalendarCommand(Command):
    name = "calendar"
    help = "the closures a calendar computes for a year"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("name", help="TARGET2, FederalReserve, London or NYSE")
        parser.add_argument("--year", type=int, default=date.today().year)

    def run(self, ctx: CommandContext) -> int:
        from prama.packs.banking.readout import calendar, calendar_spec

        wanted = calendar_spec(ctx.args.name)
        computed = calendar(ctx.args.name, ctx.args.year)
        rows = computed["closures"]
        closures = rows
        if ctx.json_output:
            ctx.emit_json({"calendar": wanted.name, "year": ctx.args.year, "closures": rows})
            return EXIT_OK

        ctx.emit(f"{wanted.name} — {wanted.description}")
        ctx.emit(
            f"{len(closures)} closure(s) in {ctx.args.year}, computed from "
            f"{len(wanted.rules)} rule(s):"
        )
        for row in rows:
            ctx.emit(f"  {row['date']}  {row['weekday']}")
        ctx.emit()
        # The limit, stated. A calendar that listed its closures and stopped
        # invites the reader to believe it knows about all of them.
        ctx.emit(wanted.describe())
        return EXIT_OK


class PackReconciliationCommand(Command):
    name = "reconciliation"
    help = "a reference reconciliation's keys, tolerance and expected breaks"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("identity", nargs="?", default="", help="omit to list them all")

    def run(self, ctx: CommandContext) -> int:
        from prama.packs.banking.reconciliations import TEMPLATES, identities, template

        if not ctx.args.identity:
            if ctx.json_output:
                ctx.emit_json({"reconciliations": [t.to_dict() for t in TEMPLATES]})
                return EXIT_OK
            for entry in TEMPLATES:
                ctx.emit(f"  {entry.identity:28} {entry.label}")
            return EXIT_OK

        try:
            entry = template(ctx.args.identity)
        except KeyError:
            raise ValidationError(
                f"no reconciliation template called {ctx.args.identity!r}",
                remedy=f"One of: {', '.join(identities())}.",
                context={"template": ctx.args.identity},
            ) from None

        if ctx.json_output:
            ctx.emit_json(entry.to_dict())
            return EXIT_OK

        ctx.emit(entry.label)
        ctx.emit(f"  {entry.left_role}")
        ctx.emit(f"  against {entry.right_role}")
        ctx.emit()
        ctx.emit(f"  keys      {', '.join(entry.key_roles)}")
        ctx.emit(f"  amount    {entry.amount_role}")
        ctx.emit(f"  window    {entry.date_window} day(s) either side")
        ctx.emit()
        # The reasoning, not just the choice. A key supplied without it is one
        # somebody changes on a hunch.
        ctx.emit(f"  why these keys: {entry.why_these_keys}")
        ctx.emit(f"  tolerance:      {entry.tolerance_rationale}")
        ctx.emit(f"  expect breaks:  {', '.join(k.value for k in entry.expected_breaks)}")
        if entry.note:
            ctx.emit(f"  note:           {entry.note}")
        return EXIT_OK


class PackSoc2Command(Command):
    name = "soc2"
    help = "which Trust Services Criteria this product itself can evidence"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        pass

    def run(self, ctx: CommandContext) -> int:
        """Prama's own readiness, not the bank's.

        Answerable before an audit rather than during, and leading with the
        gaps: a readiness matrix that led with what is covered is one whose
        gaps are read last or not at all.
        """
        from prama.security.soc2 import Readiness, readout

        result = readout()
        if ctx.json_output:
            ctx.emit_json(result.to_dict())
            return EXIT_OK

        ctx.emit(result.describe())
        ctx.emit()
        for group, heading in (
            (Readiness.GAP, "Gaps in the product"),
            (Readiness.PARTIAL, "Partial — a mechanism exists, its evidence is incomplete"),
            (Readiness.EVIDENCEABLE, "Evidenceable today"),
            (Readiness.ORGANISATIONAL, "Not a product control"),
        ):
            found = result.of(group)
            if not found:
                if group is Readiness.GAP:
                    # Said rather than omitted. A section that silently vanishes
                    # reads as "nothing needs work", and the partial ones below
                    # still do.
                    ctx.emit("Gaps in the product")
                    ctx.emit("  none outright — see the partial criteria below, which")
                    ctx.emit("  are not the same as covered")
                    ctx.emit()
                continue
            ctx.emit(heading)
            for criterion in found:
                ctx.emit(f"  {criterion.identity:<8} {criterion.statement}")
                if criterion.mechanism:
                    ctx.emit(f"           via: {criterion.mechanism}")
                ctx.emit(f"           auditor asks for: {criterion.evidence_request}")
                if criterion.note:
                    ctx.emit(f"           note: {criterion.note}")
            ctx.emit()
        ctx.emit(result.to_dict()["caveat"])
        return EXIT_OK


class PackParseCommand(Command):
    name = "parse"
    help = "parse one financial message and report what is wrong with it"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("path", help="file holding a single message")
        parser.add_argument(
            "--format",
            choices=sorted(_PARSERS),
            help="format; inferred from the content when omitted",
        )

    def run(self, ctx: CommandContext) -> int:
        from pathlib import Path

        source = Path(ctx.args.path)
        if not source.is_file():
            raise ValidationError(
                f"no such file: {source}",
                remedy="Pass the path to a file holding one message.",
            )
        raw = source.read_text(encoding="utf-8", errors="replace")

        from prama.packs.banking.readout import infer, parse_message

        if not ctx.args.format and infer(raw) is None:
            raise ValidationError(
                "could not tell which format this is",
                remedy=(f"Pass --format explicitly; one of {', '.join(sorted(_PARSERS))}."),
            )
        parsed = parse_message(raw, ctx.args.format)
        chosen = parsed.pop("format")
        parsed.pop("inferred")
        summary = parsed
        if ctx.json_output:
            ctx.emit_json({"format": chosen, **summary})
            return EXIT_OK

        # Width from the labels themselves: a fixed one silently runs the
        # longest label into its value, which reads as a different label.
        labels = ["Format", *(k for k in summary if k != "defects")]
        width = max(len(label) for label in labels) + 2
        ctx.emit(f"{'Format':{width}}{chosen}{'' if ctx.args.format else ' (inferred)'}")
        for label, value in summary.items():
            if label == "defects":
                continue
            ctx.emit(f"{label:{width}}{value}")
        defects = summary["defects"]
        ctx.emit()
        if not defects:
            # Deliberately not "valid": these parsers check structure and
            # self-consistency, not whether the trade should have been booked.
            ctx.emit("No structural defects found.")
        else:
            ctx.emit(f"{len(defects)} defect(s):")
            for defect in defects:
                ctx.emit(f"  {defect}")
        return EXIT_OK


def _wrap(text: str, width: int) -> list[str]:
    """Wrap a caveat to the terminal.

    Caveats are sentences, and a sentence printed as one long line is a
    sentence a reader skips — which for this command defeats the point of it.
    """
    import textwrap

    return textwrap.wrap(text, width=width) or [""]


class PackConceptsCommand(Command):
    name = "concepts"
    help = "the business concept model, and where each concept ends"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("concept", nargs="?", help="one concept, in full")

    def run(self, ctx: CommandContext) -> int:
        from prama.packs.banking import concepts

        if ctx.args.concept:
            return self._one(ctx, concepts.concept(ctx.args.concept))

        if ctx.json_output:
            from prama.packs.banking.readout import concepts as listed

            ctx.emit_json({"concepts": listed()})
            return EXIT_OK

        ctx.emit(f"{len(concepts.CONCEPTS)} concepts. A starter ontology; a tenant's own wins.")
        ctx.emit()
        for entry in concepts.CONCEPTS:
            identifying = ", ".join(p.name for p in entry.identifying)
            ctx.emit(f"  {entry.name:20} {entry.description}")
            ctx.emit(f"  {'':20} identified by: {identifying}")
        ctx.emit()
        ctx.emit("`prama pack concepts <name>` says where a concept ends.")
        return EXIT_OK

    def _one(self, ctx: CommandContext, entry: Any) -> int:
        if ctx.json_output:
            from prama.packs.banking.readout import concept

            ctx.emit_json(concept(entry.name))
            return EXIT_OK

        ctx.emit(f"{entry.name} — {entry.description}")
        ctx.emit()
        for prop in entry.properties:
            marker = {"identifying": "!", "defining": "*", "descriptive": " "}[prop.role.value]
            kind = f" [{prop.semantic_type}]" if prop.semantic_type else ""
            ctx.emit(f"  {marker} {prop.name}{kind}")
            if prop.aliases:
                ctx.emit(f"      also: {', '.join(prop.aliases)}")
        ctx.emit()
        ctx.emit("  ! without it, the table is not this concept")
        ctx.emit("  * carries the concept's meaning; absence is a finding")
        if entry.boundary:
            ctx.emit()
            ctx.emit(f"What it is not: {entry.boundary}")
        if entry.relevance:
            ctx.emit(f"Why it matters: {entry.relevance}")
        return EXIT_OK


class PackRecogniseCommand(Command):
    name = "recognise"
    help = "which concept a set of columns is, or why that cannot be said"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("columns", nargs="+", help="column names")
        parser.add_argument("--as", dest="expected", help="test against one concept")

    def run(self, ctx: CommandContext) -> int:
        from prama.packs.banking import concepts

        columns = list(ctx.args.columns)
        if ctx.args.expected:
            results = [concepts.recognise(ctx.args.expected, columns)]
        else:
            results = list(concepts.identify(columns))

        if ctx.json_output:
            ctx.emit_json({"columns": columns, "candidates": [r.to_dict() for r in results]})
            return EXIT_OK

        if not results:
            # Deliberately not the closest match. Position, Balance and
            # Exposure share a shape, and naming one of them here would be a
            # guess wearing the tool's authority.
            ctx.emit("No concept recognised.")
            ctx.emit()
            ctx.emit("These columns carry no concept's identifying properties. That is")
            ctx.emit("usually a table that references business objects rather than being")
            ctx.emit("one — a fact table, a log, an extract. `prama pack concepts` lists")
            ctx.emit("what identifies each concept.")
            return EXIT_OK

        for result in results:
            ctx.emit(f"{result.concept} — {result.standing.value}")
            ctx.emit(f"  {result.reason}")
            for column, prop in result.matched:
                ctx.emit(f"    {column} -> {prop}")
            if result.expected_types:
                pairs = ", ".join(f"{c} is {t}" for c, t in result.expected_types)
                ctx.emit(f"  expect: {pairs}")
            if result.unmatched_columns:
                ctx.emit(f"  unplaced: {', '.join(result.unmatched_columns)}")
            ctx.emit()
        ctx.emit("A recognition is a proposal. A steward confirms it.")
        return EXIT_OK


class PackCommand(CommandGroup):
    name = "pack"
    help = "what a domain pack ships, and what it does not claim"

    def commands(self) -> list[Command]:
        return [
            PackListCommand(),
            PackClaimsCommand(),
            PackCalendarCommand(),
            PackReconciliationCommand(),
            PackSoc2Command(),
            PackParseCommand(),
            PackConceptsCommand(),
            PackRecogniseCommand(),
        ]


__all__: list[str] = ["PackCommand"]
