"""What the banking pack ships, as data: the one answer `prama pack` and the API both give.

The CLI prints these and the API returns them. They were first written inside
the CLI commands, which meant a second surface would have had to restate them;
a restated inventory drifts, and in a pack the drift is always towards claiming
more than it does. Nothing here needs a database.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import MAXYEAR, MINYEAR
from typing import Any

from prama.core.errors import ValidationError

MESSAGE_FORMATS = (
    "SWIFT MT (MT940, MT103)",
    "ISO 20022 (pacs.008, camt.053)",
    "COBOL copybook over EBCDIC",
    "FIX 4.2-4.4 (tag=value, repeating groups kept)",
    "ISO 8583 (bitmap-driven, PAN masked)",
    "FpML 5 (both legs, direction kept)",
)


def inventory() -> dict[str, Any]:
    """Calendars, cross-field checks, obligations, reconciliations and message formats."""
    from prama.packs.banking import calendars, obligations, reconciliations
    from prama.packs.banking.crossfield import BANKING_FUNCTIONS

    return {
        "calendars": [spec.name for spec in calendars.SPECS],
        "cross_field_functions": [fn.name for fn in BANKING_FUNCTIONS],
        "obligations": len(obligations.ALL_OBLIGATIONS),
        "regimes": sorted({o.regime for o in obligations.ALL_OBLIGATIONS}),
        "reconciliations": list(reconciliations.identities()),
        "message_formats": list(MESSAGE_FORMATS),
    }


def claims() -> dict[str, Any]:
    """What the pack discharges with controls, and — the point — what it does not."""
    from prama.packs.banking.obligations import (
        ALL_OBLIGATIONS,
        DISCHARGEABLE_PRINCIPLES,
        SUPPORTED_NOT_DISCHARGED,
    )
    from prama.packs.banking.regimes import REGIME_SCOPE

    return {
        "discharged": list(DISCHARGEABLE_PRINCIPLES),
        "supported_not_discharged": SUPPORTED_NOT_DISCHARGED,
        "regime_scope": REGIME_SCOPE,
        "partly_discharged": [o.identity for o in ALL_OBLIGATIONS if not o.is_fully_discharged],
        "unconfirmed_citations": [o.identity for o in ALL_OBLIGATIONS if not o.citation.confirmed],
        "obligations": [o.to_dict() for o in ALL_OBLIGATIONS],
    }


def calendar_spec(name: str) -> Any:
    from prama.packs.banking.calendars import spec

    try:
        return spec(name)
    except KeyError:
        raise ValidationError(
            f"no calendar called {name!r} is in this pack",
            remedy="TARGET2, FederalReserve, London or NYSE.",
            context={"calendar": name},
        ) from None


def calendar(name: str, year: int) -> dict[str, Any]:
    """The closures a calendar computes for *year*, and the limit of what it knows."""
    from prama.packs.banking.holidays import observed

    wanted = calendar_spec(name)
    # A year outside `datetime`'s range reaches `date(year, ...)` deep in the
    # rule evaluation and raises a bare ValueError. QA round 3, Q-68.
    if not MINYEAR <= year <= MAXYEAR:
        raise ValidationError(
            f"year {year} is outside the range a calendar can be computed for",
            remedy=(
                f"Pass a year between {MINYEAR} and {MAXYEAR}. "
                "A closure calendar is only meaningful for years the regime existed."
            ),
            context={"year": year},
        )
    closures = sorted(observed(wanted.rules, [year]))
    return {
        "calendar": wanted.name,
        "description": wanted.description,
        "year": year,
        "rules": len(wanted.rules),
        "closures": [{"date": d.isoformat(), "weekday": d.strftime("%A")} for d in closures],
        "limits": wanted.describe(),
    }


def reconciliations() -> list[dict[str, Any]]:
    from prama.packs.banking.reconciliations import TEMPLATES

    return [t.to_dict() for t in TEMPLATES]


def reconciliation_template(identity: str) -> Any:
    from prama.packs.banking.reconciliations import identities, template

    try:
        return template(identity)
    except KeyError:
        raise ValidationError(
            f"no reconciliation template called {identity!r}",
            remedy=f"One of: {', '.join(identities())}.",
            context={"template": identity},
        ) from None


# -- messages -----------------------------------------------------------------


def _fix(raw: str) -> dict[str, Any]:
    from prama.packs.banking import fix

    message = fix.parse(raw)
    return {
        "type": message.msg_type,
        "fields": len(message.tags),
        "groups": len(message.groups),
        "delimiter": "display" if message.arrived_display_delimited else "SOH",
        "defects": [d.render() for d in message.defects],
    }


def _iso8583(raw: str) -> dict[str, Any]:
    from prama.packs.banking import iso8583

    message = iso8583.parse(raw.strip())
    return {
        "mti": message.mti,
        "fields": len(message.present),
        "amount": str(message.amount()) if message.amount() is not None else "-",
        "defects": [d.problem for d in message.defects],
    }


def _fpml(raw: str) -> dict[str, Any]:
    from prama.packs.banking import fpml

    trade = fpml.parse(raw)
    return {
        "trade": trade.trade_id or "-",
        "version": trade.version or "-",
        "legs": len(trade.legs),
        "legs directed": trade.is_two_sided,
        "defects": list(trade.defects),
    }


def _swift(raw: str) -> dict[str, Any]:
    from prama.packs.banking import swift

    message = swift.parse(raw)
    defects = [d.render() for d in message.defects]
    summary: dict[str, Any] = {
        "type": f"MT{message.kind}" if message.kind else "-",
        "sender": message.sender_bic or "-",
        "fields": len(message.fields),
    }
    if message.kind == "940" and message.is_well_formed:
        statement = swift.statement(message)
        summary.update(statement.to_dict())
        defects += [d.render() for d in statement.defects]
    return {**summary, "defects": defects}


def _pacs008(raw: str) -> dict[str, Any]:
    from prama.packs.banking import iso20022

    document = iso20022.parse_pacs008(raw)
    return {**document.to_dict(), "defects": list(document.defects)}


def _camt053(raw: str) -> dict[str, Any]:
    from prama.packs.banking import iso20022

    document = iso20022.parse_camt053(raw)
    return {**document.to_dict(), "defects": list(document.defects)}


PARSERS: dict[str, Callable[[str], dict[str, Any]]] = {
    "fix": _fix,
    "iso8583": _iso8583,
    "fpml": _fpml,
    "swift": _swift,
    "pacs008": _pacs008,
    "camt053": _camt053,
}


def infer(raw: str) -> str | None:
    """Which format this is, or nothing.

    Guessing wrong is worse than declining: every one of these parsers reports
    defects, so a misidentified message comes back as a page of findings about
    a file that was never in that format.
    """
    stripped = raw.lstrip()
    head = raw[:600].lower()
    if stripped.startswith("<"):
        if "fpml" in head:
            return "fpml"
        if "pacs.008" in head:
            return "pacs008"
        if "camt.053" in head:
            return "camt053"
        return None
    if stripped.startswith("{1:"):
        return "swift"
    if stripped.startswith("8=FIX"):
        return "fix"
    if stripped[:4].isdigit() and len(stripped) > 20:
        return "iso8583"
    return None


def parse_message(raw: str, fmt: str | None = None) -> dict[str, Any]:
    """Parse one message; say which format and every structural defect found.

    No defects is not "valid": these parsers check structure and
    self-consistency, not whether the trade should have been booked.
    """
    chosen = fmt or infer(raw)
    if chosen is None:
        raise ValidationError(
            "could not tell which format this is",
            remedy=f"Name the format explicitly; one of {', '.join(sorted(PARSERS))}.",
        )
    if chosen not in PARSERS:
        raise ValidationError(
            f"{chosen!r} is not a message format this pack reads",
            remedy=f"One of {', '.join(sorted(PARSERS))}.",
        )
    return {"format": chosen, "inferred": fmt is None, **PARSERS[chosen](raw)}


# -- concepts -----------------------------------------------------------------


def concepts() -> list[dict[str, Any]]:
    from prama.packs.banking import concepts as model

    return [
        {
            "name": c.name,
            "description": c.description,
            "identifying": [p.name for p in c.identifying],
            "properties": len(c.properties),
            "semantic_types": list(c.semantic_types),
            "boundary": c.boundary,
        }
        for c in model.CONCEPTS
    ]


def concept(name: str) -> dict[str, Any]:
    from prama.packs.banking import concepts as model

    entry = model.concept(name)
    return {
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


def recognise(columns: Iterable[str], expected: str = "") -> dict[str, Any]:
    """Which concept these columns are — every candidate, never a guessed winner."""
    from prama.packs.banking import concepts as model

    seen = [c for c in columns if c]
    results = [model.recognise(expected, seen)] if expected else list(model.identify(seen))
    return {"columns": seen, "candidates": [r.to_dict() for r in results]}


def soc2() -> Any:
    """Prama's own SOC 2 readiness (`prama.security.soc2.readout`), gaps first."""
    from prama.security.soc2 import readout

    return readout()
