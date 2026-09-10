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
        ]
        regimes = sorted({o.regime for o in obligations.OBLIGATIONS})
        payload: dict[str, Any] = {
            "calendars": [spec.name for spec in calendars.SPECS],
            "cross_field_functions": [fn.name for fn in BANKING_FUNCTIONS],
            "obligations": len(obligations.OBLIGATIONS),
            "regimes": regimes,
            "reconciliations": list(reconciliations.identities()),
            "message_formats": [
                "SWIFT MT (MT940, MT103)",
                "ISO 20022 (pacs.008, camt.053)",
                "COBOL copybook over EBCDIC",
            ],
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
        ]


__all__: list[str] = ["PackCommand"]
