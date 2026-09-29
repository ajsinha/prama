"""The steward task protocol: claim, heartbeat, result, and asking for approval.

For stewards that run as their own process, anywhere that can reach the
server over HTTPS; the server never calls out. A claimed task is leased
(`agt-task:<id>` in the lease table), and the lease's fencing token is what a
heartbeat and a result must carry. A result from a stale holder (one whose
lease expired and whose task was handed to another) is refused, so two copies
of an agent cannot both write a task's outcome.

The kill switch binds here too: a paused, stopped or revoked steward is
refused new claims, and a heartbeat answers `cancel`.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from prama.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError

#: Seconds a claim holds a task before it must be renewed by a heartbeat.
LEASE_SECONDS = 300.0

#: Task states a steward may report as its result.
RESULTS = ("succeeded", "failed")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _resource(task_id: str) -> str:
    return f"agt-task:{task_id}"


def _require_active(steward: Any) -> None:
    if steward.state != "active":
        raise ForbiddenError(
            f"this steward is {steward.state}",
            remedy="Its sponsor or an administrator can resume it on the Agents page.",
            context={"steward": steward.name, "state": steward.state},
        )


async def claim(
    uow: Any, database: Any, tenant_id: str, steward: Any, *, most: int = 1
) -> list[dict[str, Any]]:
    """Lease up to *most* pending remote tasks of this steward's goals."""
    _require_active(steward)
    goals = [g for g in await uow.stewards.goals(tenant_id, steward.id) if g.state == "active"]
    leases = database.lease_provider()
    handed: list[dict[str, Any]] = []
    for task in await uow.stewards.tasks_in(tenant_id, [g.id for g in goals], ("pending",)):
        if len(handed) >= max(1, min(most, 20)):
            break
        lease = await leases.acquire(_resource(task.id), steward.id, LEASE_SECONDS)
        if lease is None:
            continue  # held by another instance of this steward
        task.state, task.attempts = "leased", task.attempts + 1
        task.fencing_token, task.started_at = lease.fencing_token, _now()
        handed.append(
            {
                "task": task.id,
                "kind": task.kind,
                "input": task.input_json,
                "fencing_token": lease.fencing_token,
                "lease_seconds": LEASE_SECONDS,
            }
        )
    steward.last_seen_at = _now()
    await uow.flush()
    return handed


async def _held(
    uow: Any, database: Any, tenant_id: str, steward: Any, task_id: str, token: int
) -> tuple[Any, Any]:
    task = await uow.stewards.task(tenant_id, task_id)
    goals = {g.id for g in await uow.stewards.goals(tenant_id, steward.id)}
    if task is None or task.goal_id not in goals:
        raise NotFoundError("no such task for this steward", remedy="Claim tasks first.")
    lease = await database.lease_provider().inspect(_resource(task_id))
    if (
        lease is None
        or lease.holder != steward.id
        or lease.fencing_token != token
        or task.fencing_token != token
    ):
        raise ConflictError(
            "this task's lease has passed to another holder, or expired",
            remedy="Drop the task: its result would be refused. Claim again.",
            context={"task": task_id},
        )
    return task, lease


async def heartbeat(
    uow: Any, database: Any, tenant_id: str, steward: Any, task_id: str, token: int
) -> str:
    """Renew the lease, or tell the agent to stop (`cancel`)."""
    task = await uow.stewards.task(tenant_id, task_id)
    if steward.state != "active" or task is None or task.state == "cancelled":
        return "cancel"
    task, lease = await _held(uow, database, tenant_id, steward, task_id, token)
    if await database.lease_provider().renew(lease, LEASE_SECONDS) is None:
        return "cancel"
    task.state = "running"
    steward.last_seen_at = _now()
    await uow.flush()
    return "continue"


async def result(
    uow: Any,
    database: Any,
    tenant_id: str,
    steward: Any,
    task_id: str,
    token: int,
    *,
    state: str,
    output: dict[str, Any],
) -> Any:
    """Record the task's outcome, if the reporter still holds it."""
    if state not in RESULTS:
        raise ValidationError(f"{state!r} is not a result", remedy="Report succeeded or failed.")
    task, lease = await _held(uow, database, tenant_id, steward, task_id, token)
    task.state, task.output_json, task.finished_at = state, output, _now()
    await database.lease_provider().release(lease)
    await uow.flush()
    return task


async def ask(
    uow: Any,
    database: Any,
    tenant_id: str,
    steward: Any,
    task_id: str,
    token: int,
    *,
    action: dict[str, Any],
    justification: str,
) -> Any:
    """Park the task until a person grants or denies the action."""
    task, lease = await _held(uow, database, tenant_id, steward, task_id, token)
    # Released before the approval is written, as `result` does: the lease is
    # released on a connection of its own, and while this request's unit of
    # work held a write it waited on it — "database is locked" on SQLite's
    # single writer, and the agent's request for approval was a 500. Found by
    # the SDK's first end-to-end test of asking.
    await database.lease_provider().release(lease)
    return await uow.stewards.request_approval(tenant_id, task, action, justification)


async def decide(uow: Any, tenant_id: str, approval_id: str, *, granted: bool, by: str) -> Any:
    """A person's answer. Granted: the task returns to the queue. Denied: it fails."""
    approval = await uow.stewards.approval(tenant_id, approval_id)
    if approval is None or approval.state != "open":
        raise NotFoundError("no open approval with that id", remedy="See the Agents page.")
    task = await uow.stewards.task(tenant_id, approval.task_id)
    approval.state, approval.decided_by, approval.decided_at = (
        "granted" if granted else "denied",
        by,
        _now(),
    )
    if task is not None:
        task.state = "pending" if granted else "failed"
        if granted:
            task.input_json = {**task.input_json, "approved": approval.action_json}
        else:
            task.output_json = {"error": "the requested action was denied"}
            task.finished_at = _now()
    await uow.flush()
    return approval


async def requeue_expired(uow: Any, database: Any, tenant_id: str, goal_ids: list[str]) -> int:
    """Tasks whose holder vanished go back to the queue with a new token to come."""
    leases = database.lease_provider()
    requeued = 0
    for task in await uow.stewards.tasks_in(tenant_id, goal_ids, ("leased", "running")):
        if await leases.inspect(_resource(task.id)) is None:
            task.state, task.fencing_token = "pending", None
            requeued += 1
    await uow.flush()
    return requeued
