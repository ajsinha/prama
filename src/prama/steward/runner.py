"""Running stewards' goals on their schedules, under their own identity.

Each tick finds every active steward's due goals and runs one task per goal.
The kill switch is read from the database before each task, so pausing or
stopping takes effect at the next task, and a revoked steward's principal is
disabled, so its key and gateway access stop at once. Model calls go through
the gateway as the steward's principal: costed, budgeted, redacted and
recorded like anybody's.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from prama.core.log import get_logger
from prama.steward.tools import TOOLS, Context

_log = get_logger(__name__)

_INTERVAL = re.compile(r"^(\d+)\s*([mhd])$")


def interval(schedule: str | None) -> timedelta | None:
    """'30m', '6h', '1d'; None means run only when asked."""
    if not schedule:
        return None
    found = _INTERVAL.match(schedule.strip().lower())
    if not found:
        return None
    amount, unit = int(found.group(1)), found.group(2)
    return timedelta(minutes=amount) * {"m": 1, "h": 60, "d": 1440}[unit]


def _now() -> datetime:
    return datetime.now(UTC)


async def run_task(
    uow: Any, config: Any, tenant_id: str, steward: Any, goal: Any, *, key: str
) -> Any:
    """Create and run one task for *goal*. Returns the task."""
    from prama.llm.wiring import gateway_for, persist

    task = await uow.stewards.add_task(tenant_id, goal, key)
    _, purpose, tool = TOOLS.get(goal.kind, ("", None, None))
    task.started_at, task.state, task.attempts = (
        _now().isoformat(timespec="milliseconds"),
        "running",
        1,
    )
    model = ledger = None
    if purpose and await uow.llm.current(tenant_id, purpose) is not None:
        model, ledger = await gateway_for(
            uow,
            tenant_id,
            surface="steward",
            principal_id=steward.principal_id,
            offline=config.get_bool("llm.offline", False),
        )
    try:
        if tool is None:
            raise ValueError(f"no tool for the goal kind {goal.kind!r}")
        output = await tool(Context(uow, config, tenant_id, steward, task, model))
        task.state, task.output_json = "succeeded", output
    except Exception as exc:
        task.state, task.output_json = "failed", {"error": f"{type(exc).__name__}: {exc}"[:1000]}
    finally:
        if ledger is not None:
            task.tokens_in = sum(r.input_tokens for r in ledger.records)
            task.tokens_out = sum(r.output_tokens for r in ledger.records)
            await persist(uow, tenant_id, ledger)
        task.finished_at = _now().isoformat(timespec="milliseconds")
        steward.last_seen_at = task.finished_at
        await uow.flush()
    return task


async def tick(database: Any, config: Any) -> int:
    """Run every due goal of every active steward, once. Returns tasks run."""
    ran = 0
    async with database.unit_of_work() as uow:
        tenants = [t.id for t in await uow.tenants.list_active(limit=1000)]
    for tenant_id in tenants:
        async with database.unit_of_work() as uow:
            for steward in await uow.stewards.all(tenant_id):
                if steward.state != "active":
                    continue
                for goal in await uow.stewards.goals(tenant_id, steward.id):
                    every = interval(goal.schedule)
                    if goal.state != "active" or every is None:
                        continue
                    last = await uow.stewards.last_task(tenant_id, goal.id)
                    if (
                        last is not None
                        and datetime.fromisoformat(last.created_at) + every > _now()
                    ):
                        continue
                    # The switch is changed from another transaction (the console),
                    # so it is re-read from a fresh one just before acting.
                    async with database.unit_of_work() as fresh:
                        current = await fresh.stewards.one(tenant_id, steward.id)
                    if current is None or current.state != "active":
                        break
                    await run_task(
                        uow,
                        config,
                        tenant_id,
                        steward,
                        goal,
                        key=f"{goal.id}:{_now().strftime('%Y%m%dT%H%M')}",
                    )
                    ran += 1
    return ran


async def loop(database: Any, config: Any) -> None:
    """Tick at the configured interval until the supervisor cancels it."""
    seconds = float(config.get_duration("agents.interval", 60.0))
    while True:
        # Wait first: nothing is due in the first second after boot, and a tick
        # at start-up competes with the application's own startup for the
        # database.
        await asyncio.sleep(seconds)
        try:
            await tick(database, config)
        except Exception as exc:
            _log.warning("steward tick failed: %s", exc)
