"""Administering stewards: goals and running one now. Shared by the Agents page and the API.

Both surfaces used to hold these rules in their own handlers; they live here so
that a goal the console refuses is one the API refuses too.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from prama.core.errors import ConflictError, NotFoundError, ValidationError
from prama.steward.runner import interval
from prama.steward.tools import TOOLS


async def steward(uow: Any, tenant_id: str, steward_id: str) -> Any:
    """A steward of this estate, or NotFoundError."""
    found = await uow.stewards.one(tenant_id, steward_id)
    if found is None:
        raise NotFoundError(
            "no such steward",
            remedy="Stewards are listed on the Agents page.",
            context={"steward": steward_id},
        )
    return found


async def add_goal(
    uow: Any,
    tenant_id: str,
    steward_id: str,
    *,
    kind: str,
    by: str,
    statement: str = "",
    schedule: str = "",
    source: str = "",
    remote: bool = False,
    approve_before_run: bool = False,
) -> Any:
    """Give a steward a goal. A server-side goal names a tool the server has; a
    remote one is carried out by the agent's own process, which claims it."""
    await steward(uow, tenant_id, steward_id)
    if kind not in TOOLS and not remote:
        raise NotFoundError(
            f"no goal kind {kind!r}",
            remedy=f"Choose one of {', '.join(TOOLS)}, or mark the goal remote.",
            context={"kind": kind},
        )
    if schedule.strip() and interval(schedule) is None:
        # Refused rather than stored: an unreadable schedule was kept and the
        # goal silently never ran on its own.
        raise ValidationError(
            f"{schedule!r} is not a schedule",
            remedy="Write an interval such as 30m, 6h or 1d, or leave it empty.",
            context={"schedule": schedule},
        )
    statement = statement.strip() or (TOOLS[kind][0] if kind in TOOLS else "")
    if not statement:
        raise ValidationError(
            "a remote goal says what it is for",
            remedy="Give a statement: the agent's process reads it.",
        )
    return await uow.stewards.add_goal(
        tenant_id,
        steward_id,
        statement=statement,
        kind=kind,
        inputs={
            **({"source": source.strip()} if source.strip() else {}),
            **({"remote": True} if remote else {}),
            **({"approve_before_run": True} if approve_before_run else {}),
        },
        schedule=schedule.strip() or None,
        by=by,
    )


async def run_now(uow: Any, config: Any, tenant_id: str, goal_id: str) -> Any:
    """Create and run one task for a goal now, on the server. Returns the task."""
    from prama.steward.runner import run_task

    goal = next((g for g in await uow.stewards.goals(tenant_id) if g.id == goal_id), None)
    if goal is None:
        raise NotFoundError("no such goal", remedy="Goals are listed under each steward.")
    owner = await steward(uow, tenant_id, goal.steward_id)
    if owner.state != "active":
        raise ConflictError(
            f"{owner.name} is {owner.state}",
            remedy="Set the steward active before running its goals.",
            context={"steward": owner.id, "state": owner.state},
        )
    return await run_task(
        uow,
        config,
        tenant_id,
        owner,
        goal,
        key=f"{goal.id}:manual:{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')}",
    )
