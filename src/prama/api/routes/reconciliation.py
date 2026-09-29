"""Reconciliations, their break queues, and the period-end certificate, for programs.

Everything here reads what a control run recorded. A reconciliation is a
RECONCILE control and runs the way every control runs; this module adds no
second way to run one, so there is one place a reconciliation's breaks come
from.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from prama.api.deps import AttestationSigner, BreakReader, BreakWriter, Uow
from prama.recon import service

router = APIRouter(tags=["reconciliation"])


class AssignIn(BaseModel):
    owner: str = Field(min_length=1, max_length=128, description="the person or team taking it")


class ExplainIn(BaseModel):
    text: str = Field(min_length=1, description="what was found, even if it is 'still looking'")


class AcceptIn(BaseModel):
    reason: str = Field(min_length=1, description="why this difference is expected to persist")


class CertificateIn(BaseModel):
    definition: str = Field(min_length=1, description="the reconciliation, as its queue names it")
    period_end: date | None = Field(default=None, description="defaults to today (UTC)")


@router.get("/reconciliations")
async def list_reconciliations(caller: BreakReader, uow: Uow) -> dict[str, Any]:
    """Every RECONCILE control with its latest result, and every break queue."""
    return await service.reconciliations(uow, caller.tenant_id)


@router.post("/reconciliations/certificate")
async def certify(body: CertificateIn, caller: AttestationSigner, uow: Uow) -> dict[str, Any]:
    """A certificate of what is outstanding, signed by the caller. Not stored."""
    issued = await service.certificate(
        uow,
        caller.tenant_id,
        body.definition,
        signed_by=caller.require_principal(),
        period_end=body.period_end,
    )
    return issued.to_dict()


@router.get("/reconciliations/{control_id}")
async def get_reconciliation(
    control_id: str, caller: BreakReader, uow: Uow, history: int = Query(20, ge=1, le=500)
) -> dict[str, Any]:
    """One reconciliation: the control, its latest result and its recent runs."""
    return await service.reconciliation(uow, caller.tenant_id, control_id, history=history)


@router.get("/breaks")
async def workbench(
    caller: BreakReader,
    uow: Uow,
    definition: str = Query(min_length=1),
    show: str = Query("outstanding", pattern="^(outstanding|all)$"),
) -> dict[str, Any]:
    """One reconciliation's breaks, in the order they should be worked."""
    return await service.workbench(uow, caller.tenant_id, definition, show=show)


@router.get("/breaks/{break_id}")
async def get_break(break_id: str, caller: BreakReader, uow: Uow) -> dict[str, Any]:
    return (await service.get_break(uow, caller.tenant_id, break_id)).to_dict()


@router.post("/breaks/{break_id}/assign")
async def assign(break_id: str, body: AssignIn, caller: BreakWriter, uow: Uow) -> dict[str, Any]:
    row = await service.assign(
        uow, caller.tenant_id, break_id, owner=body.owner, by=caller.principal_id or ""
    )
    return row.to_dict()


@router.post("/breaks/{break_id}/explain")
async def explain(break_id: str, body: ExplainIn, caller: BreakWriter, uow: Uow) -> dict[str, Any]:
    row = await service.explain(
        uow, caller.tenant_id, break_id, text=body.text, by=caller.principal_id or ""
    )
    return row.to_dict()


@router.post("/breaks/{break_id}/accept")
async def accept(break_id: str, body: AcceptIn, caller: BreakWriter, uow: Uow) -> dict[str, Any]:
    row = await service.accept(
        uow, caller.tenant_id, break_id, reason=body.reason, by=caller.principal_id or ""
    )
    return row.to_dict()
