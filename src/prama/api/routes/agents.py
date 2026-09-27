"""The steward task protocol over HTTPS. The agent calls out; the server never does.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from prama.api.deps import AgentWorker, Uow
from prama.core.errors import ForbiddenError
from prama.steward import protocol

router = APIRouter(tags=["agents"])


async def _steward(uow: Any, caller: Any) -> Any:
    steward = await uow.stewards.by_principal(caller.tenant_id, caller.principal_id or "")
    if steward is None:
        raise ForbiddenError(
            "this key does not belong to a steward agent",
            remedy="Use the key shown when the steward was created on the Agents page.",
        )
    return steward


class ClaimIn(BaseModel):
    most: int = Field(1, ge=1, le=20)


class Held(BaseModel):
    fencing_token: int


class ResultIn(Held):
    state: str = Field(..., description="succeeded | failed")
    output: dict[str, Any] = Field(default_factory=dict)


class AskIn(Held):
    action: dict[str, Any]
    justification: str = Field("", max_length=4000)


@router.post("/agents/claim")
async def claim(body: ClaimIn, caller: AgentWorker, uow: Uow, request: Request) -> dict[str, Any]:
    """Lease up to `most` pending tasks. Each carries the fencing token to report with."""
    steward = await _steward(uow, caller)
    tasks = await protocol.claim(
        uow, request.app.state.database, caller.tenant_id, steward, most=body.most
    )
    return {"tasks": tasks}


@router.post("/agents/tasks/{task_id}/heartbeat")
async def heartbeat(
    task_id: str, body: Held, caller: AgentWorker, uow: Uow, request: Request
) -> dict[str, str]:
    """Renew the lease. `cancel` means stop now: the steward was paused or stopped."""
    steward = await _steward(uow, caller)
    answer = await protocol.heartbeat(
        uow, request.app.state.database, caller.tenant_id, steward, task_id, body.fencing_token
    )
    return {"instruction": answer}


@router.post("/agents/tasks/{task_id}/result")
async def result(
    task_id: str, body: ResultIn, caller: AgentWorker, uow: Uow, request: Request
) -> dict[str, str]:
    """Report the outcome. A stale fencing token is refused with 409."""
    steward = await _steward(uow, caller)
    task = await protocol.result(
        uow,
        request.app.state.database,
        caller.tenant_id,
        steward,
        task_id,
        body.fencing_token,
        state=body.state,
        output=body.output,
    )
    return {"task": task.id, "state": task.state}


@router.post("/agents/tasks/{task_id}/ask")
async def ask(
    task_id: str, body: AskIn, caller: AgentWorker, uow: Uow, request: Request
) -> dict[str, str]:
    """Park the task until a person approves the action on the Agents page."""
    steward = await _steward(uow, caller)
    approval = await protocol.ask(
        uow,
        request.app.state.database,
        caller.tenant_id,
        steward,
        task_id,
        body.fencing_token,
        action=body.action,
        justification=body.justification,
    )
    return {"approval": approval.id, "state": "awaiting_approval"}
