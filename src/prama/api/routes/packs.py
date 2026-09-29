"""Domain packs over the API: what the banking pack ships, and what it does not claim.

The same answers `prama pack` prints (`prama.packs.banking.readout`). None of
them reads the estate; they need a caller who may read declarations only so
that no route on this API is unguarded.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from prama.api.deps import Reader, Writer
from prama.packs.banking import readout

router = APIRouter(tags=["packs"])


@router.get("/packs/banking")
async def inventory(caller: Reader) -> dict[str, Any]:
    """Calendars, cross-field checks, obligations, reconciliations and message formats."""
    return readout.inventory()


@router.get("/packs/banking/claims")
async def claims(caller: Reader) -> dict[str, Any]:
    """What the pack discharges with controls, what it only supports, and what it leaves
    alone — the question asked at an examination, answerable before one."""
    return readout.claims()


@router.get("/packs/banking/calendars/{name}")
async def calendar(
    name: str, caller: Reader, year: int = Query(default_factory=lambda: date.today().year)
) -> dict[str, Any]:
    """The closures a calendar computes for a year, and the limit of what it knows."""
    return readout.calendar(name, year)


@router.get("/packs/banking/reconciliations")
async def reconciliations(caller: Reader) -> list[dict[str, Any]]:
    return readout.reconciliations()


@router.get("/packs/banking/reconciliations/{identity}")
async def reconciliation(identity: str, caller: Reader) -> dict[str, Any]:
    """A reference reconciliation's keys, tolerance and expected breaks, with the reasons."""
    return dict(readout.reconciliation_template(identity).to_dict())


class MessageIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=4 * 1024 * 1024)
    format: str | None = Field(
        None, description="fix, iso8583, fpml, swift, pacs008 or camt053; inferred when omitted"
    )


@router.post("/packs/banking/parse")
async def parse(body: MessageIn, caller: Writer) -> dict[str, Any]:
    """Parse one financial message and list what is structurally wrong with it.

    A defect is a finding about the message, not a failure of the call. An empty
    `defects` means no structural defect, which is not the same as "valid".
    Nothing is stored; a message is a body, so this is a POST, and a POST asks
    for a write scope (`declaration:write`).
    """
    return readout.parse_message(body.message, body.format)


@router.get("/packs/banking/concepts")
async def concepts(caller: Reader) -> list[dict[str, Any]]:
    """The business concept model: what identifies each concept, and where it ends."""
    return readout.concepts()


@router.get("/packs/banking/concepts/{name}")
async def concept(name: str, caller: Reader) -> dict[str, Any]:
    return readout.concept(name)


@router.get("/packs/banking/recognise")
async def recognise(
    caller: Reader,
    columns: list[str] = Query(..., min_length=1),
    concept: str = Query("", description="test against this one concept only"),
) -> dict[str, Any]:
    """Which concept a set of columns is — every candidate, or none with why.

    A recognition is a proposal; a steward confirms it.
    """
    return readout.recognise(columns, concept)


@router.get("/packs/soc2")
async def soc2(caller: Reader) -> dict[str, Any]:
    """Prama's own SOC 2 readiness — not the bank's — gaps first."""
    return dict(readout.soc2().to_dict())
