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


class PackListCommand(Command):
    name = "list"
    help = "what the banking pack ships"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        pass

    def run(self, ctx: CommandContext) -> int:
        from prama.packs.banking import calendars, obligations, reconciliations
        from prama.packs.banking.crossfield import BANKING_FUNCTIONS

        formats = [
            "SWIFT MT (MT940, MT103)",
            "ISO 20022 (pacs.008, camt.053)",
            "COBOL copybook over EBCDIC",
            "FIX 4.2-4.4 (tag=value, repeating groups kept)",
            "ISO 8583 (bitmap-driven, PAN masked)",
            "FpML 5 (both legs, direction kept)",
        ]
        regimes = sorted({o.regime for o in obligations.OBLIGATIONS})
        payload: dict[str, Any] = {
            "calendars": [spec.name for spec in calendars.SPECS],
            "cross_field_functions": [fn.name for fn in BANKING_FUNCTIONS],
            "obligations": len(obligations.OBLIGATIONS),
            "regimes": regimes,
            "reconciliations": list(reconciliations.identities()),
            "message_formats": formats,
        }
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
        ctx.emit(
            f"Obligations: {len(obligations.OBLIGATIONS)} across {', '.join(payload['regimes'])}"
        )
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
            DISCHARGEABLE_PRINCIPLES,
            OBLIGATIONS,
            SUPPORTED_NOT_DISCHARGED,
        )

        if ctx.json_output:
            ctx.emit_json(
                {
                    "discharged": list(DISCHARGEABLE_PRINCIPLES),
                    "supported_not_discharged": SUPPORTED_NOT_DISCHARGED,
                    "obligations": [o.to_dict() for o in OBLIGATIONS],
                }
            )
            return EXIT_OK

        ctx.emit("Discharged by controls — testable properties of data:")
        for principle in DISCHARGEABLE_PRINCIPLES:
            covered = [o for o in OBLIGATIONS if o.principle == principle]
            ctx.emit(f"  {principle}  {len(covered)} obligation(s)")
            for obligation in covered:
                ctx.emit(f"        {obligation.identity}  ({obligation.citation.render()})")
        ctx.emit()
        ctx.emit("Supported but NOT discharged by a control:")
        for principle, how in sorted(SUPPORTED_NOT_DISCHARGED.items()):
            ctx.emit(f"  {principle}  {how}")
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
        from prama.packs.banking.calendars import spec
        from prama.packs.banking.holidays import observed

        try:
            wanted = spec(ctx.args.name)
        except KeyError:
            raise ValidationError(
                f"no calendar called {ctx.args.name!r} is in this pack",
                remedy="TARGET2, FederalReserve, London or NYSE.",
                context={"calendar": ctx.args.name},
            ) from None

        closures = sorted(observed(wanted.rules, [ctx.args.year]))
        rows = [{"date": day.isoformat(), "weekday": day.strftime("%A")} for day in closures]
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

        chosen = ctx.args.format or _infer(raw)
        if chosen is None:
            raise ValidationError(
                "could not tell which format this is",
                remedy=(f"Pass --format explicitly; one of {', '.join(sorted(_PARSERS))}."),
            )

        summary = _PARSERS[chosen](raw)
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


def _infer(raw: str) -> str | None:
    """Which format this is, or nothing.

    Guessing wrong is worse than declining: every one of these parsers reports
    defects, so a misidentified message comes back as a page of findings about
    a file that was never in that format.
    """
    stripped = raw.lstrip()
    if stripped.startswith("<") and "fpml" in raw[:400].lower():
        return "fpml"
    if stripped.startswith("8=FIX"):
        return "fix"
    if stripped[:4].isdigit() and len(stripped) > 20:
        return "iso8583"
    return None


def _fix_summary(raw: str) -> dict[str, Any]:
    from prama.packs.banking import fix

    message = fix.parse(raw)
    return {
        "type": message.msg_type,
        "fields": len(message.tags),
        "groups": len(message.groups),
        "delimiter": "display" if message.arrived_display_delimited else "SOH",
        "defects": [d.render() for d in message.defects],
    }


def _iso8583_summary(raw: str) -> dict[str, Any]:
    from prama.packs.banking import iso8583

    message = iso8583.parse(raw.strip())
    return {
        "mti": message.mti,
        "fields": len(message.present),
        "amount": str(message.amount()) if message.amount() is not None else "-",
        "defects": [d.problem for d in message.defects],
    }


def _fpml_summary(raw: str) -> dict[str, Any]:
    from prama.packs.banking import fpml

    trade = fpml.parse(raw)
    return {
        "trade": trade.trade_id or "-",
        "version": trade.version or "-",
        "legs": len(trade.legs),
        "legs directed": trade.is_two_sided,
        "defects": list(trade.defects),
    }


_PARSERS = {
    "fix": _fix_summary,
    "iso8583": _iso8583_summary,
    "fpml": _fpml_summary,
}


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
            ctx.emit_json(
                {
                    "concepts": [
                        {
                            "name": c.name,
                            "description": c.description,
                            "identifying": [p.name for p in c.identifying],
                            "properties": len(c.properties),
                            "semantic_types": list(c.semantic_types),
                            "boundary": c.boundary,
                        }
                        for c in concepts.CONCEPTS
                    ]
                }
            )
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
            ctx.emit_json(
                {
                    "name": entry.name,
                    "description": entry.description,
                    "boundary": entry.boundary,
                    "relevance": entry.relevance,
                    "properties": [
                        {
                            "name": p.name,
                            "role": p.role.value,
                            "semantic_type": p.semantic_type,
                            "aliases": list(p.aliases),
                        }
                        for p in entry.properties
                    ],
                }
            )
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
