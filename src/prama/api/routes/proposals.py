"""Γ and the proposal queue: what the declarations imply, and deciding on it.

Derivation is where Prama's thesis is tested — the controls come from what the
business declared, not from somebody who already knew what to check — so every
answer carries the other half too: what Γ could *not* derive, and why. A
response listing only generated controls would make the set look complete when
it is not.

Scopes follow the decision being made. Seeing the queue or a derivation reads
(``control:read``); declaring derived controls as proposals authors them
(``control:propose``); accepting — which makes a control run — approves
(``control:approve``), and a derivation asked to accept checks that scope too.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import Field

from prama.api.deps import ControlApprover, ControlProposer, ControlReader, Uow
from prama.api.routes.controls import stored_out
from prama.api.schemas import PramaModel
from prama.controls import proposals as service
from prama.core.errors import ValidationError

router = APIRouter(tags=["proposals"])


class AcceptIn(PramaModel):
    identity: str = Field(min_length=1, max_length=128)
    pql: str = Field(min_length=1, description="Exactly the text that was reviewed.")
    rule: str = Field(default="", max_length=128)
    dataset_id: str = Field(default="", max_length=128)
    reason: str = "accepted from the proposal queue"


class RejectIn(PramaModel):
    identity: str = Field(min_length=1, max_length=128)
    content_hash: str = Field(
        min_length=1, description="The proposal's hash: a rewrite is a new question."
    )
    reason: str = Field(default="incorrect", description=", ".join(service.REJECTION_REASONS))
    note: str = ""


class DeriveIn(PramaModel):
    declare: bool = Field(
        default=False, description="Declare the derived controls as proposals in the estate."
    )
    accept: bool = Field(
        default=False,
        description="Also activate them, so they run. Needs control:approve; implies declare.",
    )
    schedule: str = Field(default="daily", max_length=64)
    reason: str = "derived from the declaration"


# ---------------------------------------------------------------------------
# The queue
# ---------------------------------------------------------------------------


@router.get("/proposals")
async def proposal_queue(
    caller: ControlReader,
    uow: Uow,
    dataset_id: str | None = Query(default=None, description="Only what one dataset implies."),
) -> dict[str, Any]:
    """Proposals awaiting a decision, and what could not be proposed, with counts of both."""
    if dataset_id:
        await uow.datasets.require_current(dataset_id, tenant_id=caller.tenant_id)
    return await service.queue(uow, caller.tenant_id, dataset_id)


@router.post("/proposals/accept")
async def accept_proposal(body: AcceptIn, caller: ControlApprover, uow: Uow) -> dict[str, Any]:
    """Accept a proposal: the control enters the estate, active, and begins to run."""
    version = await service.accept(
        uow,
        caller.tenant_id,
        identity=body.identity,
        pql=body.pql,
        rule=body.rule,
        dataset_id=body.dataset_id,
        by=caller.require_principal(),
        reason=body.reason,
    )
    return await stored_out(uow, caller.tenant_id, version.control_id)


@router.post("/proposals/reject")
async def reject_proposal(body: RejectIn, caller: ControlApprover, uow: Uow) -> dict[str, Any]:
    """Turn a proposal down. Recorded, so the same text is not proposed again."""
    rejection = await service.reject(
        uow,
        caller.tenant_id,
        identity=body.identity,
        content_hash=body.content_hash,
        reason=body.reason,
        note=body.note,
        by=caller.principal_id,
    )
    return _rejection_out(rejection)


@router.get("/proposals/rejections")
async def rejections(
    caller: ControlReader, uow: Uow, limit: int = Query(default=500, ge=1, le=5000)
) -> list[dict[str, Any]]:
    """Proposals somebody turned down, newest first, with the reason."""
    return [
        _rejection_out(r) for r in await uow.rejections.for_tenant(caller.tenant_id, limit=limit)
    ]


def _rejection_out(rejection: Any) -> dict[str, Any]:
    return {
        "identity": rejection.identity,
        "content_hash": rejection.content_hash,
        "reason": rejection.reason,
        "note": rejection.note,
        "rejected_by": rejection.rejected_by,
        "rejected_at": rejection.rejected_at,
    }


# ---------------------------------------------------------------------------
# Derivation (Γ)
# ---------------------------------------------------------------------------


@router.get("/datasets/{dataset_id}/derivation")
async def derivation_of_dataset(dataset_id: str, caller: ControlReader, uow: Uow) -> dict[str, Any]:
    """What Γ derives from one declared dataset. Stores nothing."""
    version, generation = await service.derive_dataset(uow, caller.tenant_id, dataset_id)
    return _dataset_generation_out(version, generation)


@router.post("/datasets/{dataset_id}/derive")
async def derive_from_dataset(
    dataset_id: str, body: DeriveIn, caller: ControlProposer, uow: Uow
) -> dict[str, Any]:
    """Γ over one declared dataset; optionally declare the result, and accept it.

    Each control is declared at the dataset's criticality, with its source
    recorded, so it can be traced back to the declaration that implied it.
    """
    if body.accept:
        caller.require_scope("control:approve")
    version, generation = await service.derive_dataset(uow, caller.tenant_id, dataset_id)
    out = _dataset_generation_out(version, generation)
    if body.declare or body.accept:
        await _adopt(out, generation.controls, uow, caller, body, dataset_id, version.criticality)
    return out


@router.get("/relationships/{relationship_id}/derivation")
async def derivation_of_relationship(
    relationship_id: str, caller: ControlReader, uow: Uow
) -> dict[str, Any]:
    """What Γ derives from one declared relationship. Stores nothing."""
    version, generation = await service.derive_relationship(uow, caller.tenant_id, relationship_id)
    return _relationship_generation_out(version, generation)


@router.post("/relationships/{relationship_id}/derive")
async def derive_from_relationship(
    relationship_id: str, body: DeriveIn, caller: ControlProposer, uow: Uow
) -> dict[str, Any]:
    """Γ over one declared relationship; optionally declare its controls, and accept them.

    Comparison specs are returned and never declared: a reconciliation comes as
    runnable RECONCILE PQL (``pql``) for a reviewer to complete — how amounts in
    different currencies are normalised is not in the declaration — and the
    other kinds are specifications PQL cannot say yet.
    """
    if body.accept:
        caller.require_scope("control:approve")
    version, generation = await service.derive_relationship(uow, caller.tenant_id, relationship_id)
    if body.accept and version.status != "confirmed":
        # A control derived from a relationship nobody confirmed is itself only
        # a proposal, and never activates before a person confirms the fact it
        # rests on (RelationshipStatus).
        raise ValidationError(
            f"relationship {relationship_id!r} is {version.status}, not confirmed",
            remedy=(
                "Confirm it (POST /relationships/{id}/confirm) before accepting what it implies."
            ),
            context={"relationship_id": relationship_id, "status": version.status},
        )
    out = _relationship_generation_out(version, generation)
    if body.declare or body.accept:
        await _adopt(
            out, generation.controls, uow, caller, body, relationship_id, version.criticality
        )
    return out


async def _adopt(
    out: dict[str, Any],
    controls: Any,
    uow: Any,
    caller: Any,
    body: DeriveIn,
    source_ref: str,
    criticality: int,
) -> None:
    if body.schedule.strip():
        from prama.schedule import parse as parse_schedule

        parse_schedule(body.schedule)
    adopted = await service.adopt(
        uow,
        caller.tenant_id,
        controls,
        source_ref=source_ref,
        criticality=criticality,
        schedule=body.schedule,
        by=caller.require_principal(),
        activate=body.accept,
        reason=body.reason,
    )
    stored = {
        item["identity"]: await stored_out(uow, caller.tenant_id, item["version"].control_id)
        for item in adopted
    }
    for control in out["controls"]:
        control["control"] = stored.get(control["identity"])
    out["declared"] = len(stored)
    out["active"] = sum(1 for c in stored.values() if c["status"] == "active")


def _dataset_generation_out(version: Any, generation: Any) -> dict[str, Any]:
    return {
        "dataset_id": str(version.dataset_id),
        "dataset": version.slug,
        "criticality": version.criticality,
        "complete": generation.is_complete,
        "controls": [c.to_dict() for c in generation.controls],
        "unsatisfiable": [u.to_dict() for u in generation.unsatisfiable],
        "deferred": [d.to_dict() for d in generation.deferred],
        "comparisons": [],
    }


def _relationship_generation_out(version: Any, generation: Any) -> dict[str, Any]:
    return {
        "relationship_id": str(version.relationship_id),
        "kind": version.kind,
        "criticality": version.criticality,
        "complete": generation.is_complete,
        "controls": [c.to_dict() for c in generation.controls],
        "unsatisfiable": [u.to_dict() for u in generation.unsatisfiable],
        "deferred": [],
        "comparisons": [
            {**spec.to_dict(), "pql": spec.to_pql()} for spec in generation.comparisons
        ],
    }
