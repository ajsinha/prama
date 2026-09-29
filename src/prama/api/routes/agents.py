"""Steward agents over HTTPS: the agent's own protocol, and their administration.

Two sides, with different callers:

* **The agent's side** (``/agents/claim``, ``/agents/tasks/…``) needs
  ``agent:work``, which only a steward's key holds. The agent calls out; the
  server never does.
* **The administrator's side** (``/agents/stewards``, goals, runs, approvals,
  suggestions) needs ``admin``, as the console's Agents page does. Approving an
  agent's requested action and accepting a model's drafted description are
  decisions a person makes: a steward's key can never hold ``admin``
  (`prama.steward.identity.FORBIDDEN`), and a steward's principal is refused
  here even if somebody minted it a wildcard key by hand. An agent never
  approves; the record names the person who did.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from prama.api.deps import Administrator, AgentWorker, Uow
from prama.core.errors import ForbiddenError, ValidationError
from prama.steward import admin, identity, protocol
from prama.steward.tools import TOOLS

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


# -- the administrator's side -----------------------------------------------


async def _person(uow: Any, caller: Any) -> str:
    """The deciding person: signed in, and not a steward acting for itself."""
    if not caller.principal_id:
        raise ValidationError(
            "a decision names the person who made it", remedy="Sign in as a person."
        )
    if await uow.stewards.by_principal(caller.tenant_id, caller.principal_id) is not None:
        raise ForbiddenError(
            "a steward agent cannot decide; a person does",
            remedy="Ask the steward's sponsor, or another administrator, to decide.",
        )
    return str(caller.principal_id)


def _iso(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _goal(g: Any) -> dict[str, Any]:
    return {
        "id": g.id,
        "steward_id": g.steward_id,
        "statement": g.statement,
        "kind": g.kind,
        "inputs": dict(g.input_json or {}),
        "schedule": g.schedule,
        "state": g.state,
        "created_by": g.created_by,
        "created_at": g.created_at,
    }


def _task(t: Any) -> dict[str, Any]:
    return {
        "id": t.id,
        "goal_id": t.goal_id,
        "kind": t.kind,
        "state": t.state,
        "attempts": t.attempts,
        "output": t.output_json,
        "tokens_in": t.tokens_in,
        "tokens_out": t.tokens_out,
        "created_at": t.created_at,
        "started_at": t.started_at,
        "finished_at": t.finished_at,
    }


async def _steward_view(uow: Any, tenant: str, s: Any) -> dict[str, Any]:
    return {
        "id": s.id,
        "name": s.name,
        "state": s.state,
        "principal_id": s.principal_id,
        "sponsor_id": s.sponsor_id,
        "last_seen_at": s.last_seen_at,
        "created_at": _iso(getattr(s, "created_at", None)),
        "goals": [_goal(g) for g in await uow.stewards.goals(tenant, s.id)],
    }


class StewardIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    #: Narrower than the default; never admin, approve, sign or write.
    scopes: list[str] | None = None


class StateIn(BaseModel):
    state: str = Field(..., description="active | paused | stopped | revoked")


class GoalIn(BaseModel):
    kind: str = Field(..., max_length=64)
    statement: str = Field("", max_length=4000)
    #: "30m", "6h" or "1d"; empty means run only when asked.
    schedule: str = Field("", max_length=128)
    source: str = Field("", max_length=255)
    #: Carried out by the agent's own process rather than on the server.
    remote: bool = False
    approve_before_run: bool = False


class DecisionIn(BaseModel):
    #: Approvals: grant the requested action, or deny it.
    grant: bool


class CurationIn(BaseModel):
    #: Suggestions: accept the draft (amending the declaration as you), or reject it.
    accept: bool


@router.get("/agents/tools")
async def tools(caller: Administrator) -> list[dict[str, Any]]:
    """The goal kinds a steward can pursue on the server, and the model purpose each uses."""
    return [
        {"kind": kind, "description": description, "purpose": purpose}
        for kind, (description, purpose, _) in TOOLS.items()
    ]


@router.get("/agents/stewards")
async def stewards(uow: Uow, caller: Administrator) -> list[dict[str, Any]]:
    """Every steward, its state and its goals."""
    return [
        await _steward_view(uow, caller.tenant_id, s)
        for s in await uow.stewards.all(caller.tenant_id)
    ]


@router.post("/agents/stewards", status_code=201)
async def create_steward(body: StewardIn, uow: Uow, caller: Administrator) -> dict[str, Any]:
    """Create a steward sponsored by you. Its key is in this response only."""
    sponsor = await _person(uow, caller)
    created, plaintext = await identity.create(
        uow, caller.tenant_id, body.name.strip(), sponsor_id=sponsor, scopes=body.scopes
    )
    view = await _steward_view(uow, caller.tenant_id, created)
    return {**view, "api_key": plaintext}


@router.get("/agents/stewards/{steward_id}")
async def get_steward(steward_id: str, uow: Uow, caller: Administrator) -> dict[str, Any]:
    """One steward and its goals."""
    found = await admin.steward(uow, caller.tenant_id, steward_id)
    return await _steward_view(uow, caller.tenant_id, found)


@router.post("/agents/stewards/{steward_id}/state")
async def set_state(
    steward_id: str, body: StateIn, uow: Uow, caller: Administrator
) -> dict[str, Any]:
    """The kill switch: pause, stop (open tasks cancelled) or revoke (key revoked,
    principal disabled). A revoked steward stays revoked."""
    found = await admin.steward(uow, caller.tenant_id, steward_id)
    await identity.set_state(uow, caller.tenant_id, found, body.state, by=caller.principal_id)
    return await _steward_view(uow, caller.tenant_id, found)


@router.post("/agents/stewards/{steward_id}/goals", status_code=201)
async def add_goal(
    steward_id: str, body: GoalIn, uow: Uow, caller: Administrator
) -> dict[str, Any]:
    """Give a steward a goal."""
    goal = await admin.add_goal(
        uow,
        caller.tenant_id,
        steward_id,
        kind=body.kind,
        by=caller.principal_id or "api",
        statement=body.statement,
        schedule=body.schedule,
        source=body.source,
        remote=body.remote,
        approve_before_run=body.approve_before_run,
    )
    return _goal(goal)


@router.post("/agents/goals/{goal_id}/run")
async def run_goal(
    goal_id: str, uow: Uow, caller: Administrator, request: Request
) -> dict[str, Any]:
    """Run a goal now, on the server, as its steward. Returns the finished task."""
    task = await admin.run_now(uow, request.app.state.config, caller.tenant_id, goal_id)
    return _task(task)


@router.get("/agents/tasks")
async def tasks(
    uow: Uow, caller: Administrator, limit: int = Query(50, ge=1, le=500)
) -> list[dict[str, Any]]:
    """The most recent tasks, newest first, with what each produced."""
    return [_task(t) for t in await uow.stewards.tasks(caller.tenant_id, limit=limit)]


@router.get("/agents/approvals")
async def approvals(uow: Uow, caller: Administrator) -> list[dict[str, Any]]:
    """Actions agents have asked a person to approve, still open."""
    return [
        {
            "id": a.id,
            "task_id": a.task_id,
            "action": a.action_json,
            "justification": a.justification,
            "state": a.state,
            "created_at": a.created_at,
        }
        for a in await uow.stewards.open_approvals(caller.tenant_id)
    ]


@router.post("/agents/approvals/{approval_id}")
async def decide_approval(
    approval_id: str, body: DecisionIn, uow: Uow, caller: Administrator
) -> dict[str, Any]:
    """Grant (the task returns to the queue) or deny (it fails). A person decides."""
    by = await _person(uow, caller)
    approval = await protocol.decide(uow, caller.tenant_id, approval_id, granted=body.grant, by=by)
    return {
        "id": approval.id,
        "task_id": approval.task_id,
        "state": approval.state,
        "decided_by": approval.decided_by,
        "decided_at": approval.decided_at,
    }


def _suggestion(r: Any) -> dict[str, Any]:
    return {
        "id": r.id,
        "object_kind": r.object_kind,
        "object_id": r.object_id,
        "object_name": r.object_name,
        "field": r.field,
        "suggested": r.suggested,
        "model": r.model,
        "steward_id": r.steward_id,
        "state": r.state,
        "decided_by": r.decided_by,
        "decided_at": r.decided_at,
        "created_at": r.created_at,
    }


@router.get("/agents/suggestions")
async def suggestions(uow: Uow, caller: Administrator, state: str = "open") -> list[dict[str, Any]]:
    """Model-drafted descriptions waiting for a person (or, by state, decided ones)."""
    if state not in ("open", "accepted", "rejected", "stale"):
        raise ValidationError(
            f"{state!r} is not a suggestion state",
            remedy="Use open, accepted, rejected or stale.",
        )
    return [_suggestion(r) for r in await uow.stewards.suggestions(caller.tenant_id, state=state)]


@router.post("/agents/suggestions/{suggestion_id}")
async def decide_suggestion(
    suggestion_id: str, body: CurationIn, uow: Uow, caller: Administrator
) -> dict[str, Any]:
    """Accept (the declaration is amended with you as its author) or reject."""
    from prama.curation.suggestions import decide

    by = await _person(uow, caller)
    row = await decide(uow, caller.tenant_id, suggestion_id, accept=body.accept, by=by)
    return _suggestion(row)
