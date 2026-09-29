"""Incidents, for programs: what is currently wrong, one in full, and its discussion.

An incident is a control whose latest evidence is not a pass (see
`prama.incident.triage`). There is no separate incident record to open, assign
or close: when the control passes again, the incident is gone, and the ledger
keeps the history. Working one is done by discussion — a comment, with
mentions reaching colleagues' queues.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from prama.api.deps import Commenter, IncidentReader, Uow
from prama.core.errors import ValidationError
from prama.evidence.service import observation, record_view
from prama.incident import triage
from prama.semantic.services import collaboration

router = APIRouter(prefix="/incidents", tags=["incidents"])


class IncidentCommentIn(BaseModel):
    body: str
    parent_id: str | None = None


def _comment(r: Any) -> dict[str, Any]:
    return {
        "id": r.id,
        "object_kind": r.object_kind,
        "object_ref": r.object_ref,
        "parent_id": r.parent_id,
        "author_id": r.author_id,
        "body": r.body,
        "state": r.state,
        "created_at": r.created_at,
    }


def _version(version: Any) -> dict[str, Any] | None:
    if version is None:
        return None
    return {
        "control_id": str(version.control_id),
        "name": version.name,
        "dataset": version.dataset,
        "status": version.status,
        "severity": version.severity,
        "criticality": version.criticality,
        "dimensions": list(version.dimensions_json or ()),
        "plan_id": version.plan_id,
        "pql": version.pql,
    }


def _sample(sample: triage.Sample) -> dict[str, Any]:
    return {
        **dataclasses.asdict(sample),
        "is_complete": sample.is_complete,
        "withheld": sample.withheld,
        "description": sample.describe(),
    }


@router.get("")
async def list_incidents(
    caller: IncidentReader,
    uow: Uow,
    verdict: str | None = None,
    dataset: str | None = None,
    criticality: int | None = None,
) -> dict[str, Any]:
    """What is currently wrong, failures first, one row per control.

    ``observation`` says whether anything has been examined at all: an empty
    list with ``state: no_runs`` means nothing has run, not that nothing is wrong.
    """
    items, passing = await triage.current(uow, caller.tenant_id)
    items = [
        item
        for item in items
        if (verdict is None or item["verdict"] == verdict)
        and (dataset is None or item["dataset"] == dataset)
        and (criticality is None or item["criticality"] == criticality)
    ]
    return {
        "items": items,
        "passing": passing,
        "observation": await observation(uow, caller.tenant_id),
    }


@router.get("/{control_id}")
async def incident(control_id: str, caller: IncidentReader, uow: Uow) -> dict[str, Any]:
    """One control's incident: what it says, its history, since when, its rows, its feeders."""
    found = await triage.detail(uow, caller.tenant_id, control_id)
    latest = found["latest"]
    return {
        "control_id": control_id,
        "control": _version(found["version"]),
        "sentence": found["sentence"],
        "latest": record_view(latest) if latest else None,
        "open": bool(latest) and latest.verdict in triage.UNRESOLVED,
        "history": [record_view(r) for r in found["history"]],
        "began": found["began"],
        "history_is_truncated": found["history_is_truncated"],
        "sample": _sample(found["sample"]),
        "upstream": found["upstream"],
    }


@router.get("/{control_id}/comments")
async def comments(control_id: str, caller: IncidentReader, uow: Uow) -> list[dict[str, Any]]:
    """The discussion on this incident, oldest first."""
    return [_comment(r) for r in await uow.comments.on(caller.tenant_id, "incident", control_id)]


@router.post("/{control_id}/comments", status_code=201)
async def comment(
    control_id: str, body: IncidentCommentIn, caller: Commenter, uow: Uow
) -> dict[str, Any]:
    """Comment on this incident; ``@username`` mentions reach that person's queue."""
    if not caller.principal_id:
        raise ValidationError("a comment needs a person", remedy="Use a key issued to a person.")
    row = await collaboration.post(
        uow,
        caller.tenant_id,
        object_kind="incident",
        object_ref=control_id,
        body=body.body,
        by=caller.principal_id,
        parent_id=body.parent_id,
    )
    return _comment(row)
