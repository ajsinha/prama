"""Stewards, goals, tasks, approvals and memory. Every read takes the tenant.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from prama.core.errors import ConflictError
from prama.db.dao.base import Dao
from prama.db.models.steward import (
    AgtApproval,
    AgtGoal,
    AgtMemory,
    AgtSteward,
    AgtTask,
    CurSuggestion,
)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class StewardDao(Dao[AgtSteward]):
    model = AgtSteward

    async def create(
        self, tenant_id: str, *, name: str, principal_id: str, sponsor_id: str
    ) -> AgtSteward:
        await self._session.flush()
        exists = await self._session.execute(
            select(AgtSteward.id).where(AgtSteward.tenant_id == tenant_id, AgtSteward.name == name)
        )
        if exists.first() is not None:
            raise ConflictError(
                f"a steward called {name!r} already exists", remedy="Choose another name."
            )
        row = AgtSteward(
            tenant_id=tenant_id, name=name, principal_id=principal_id, sponsor_id=sponsor_id
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def all(self, tenant_id: str) -> list[AgtSteward]:
        await self._session.flush()
        result = await self._session.execute(
            select(AgtSteward).where(AgtSteward.tenant_id == tenant_id).order_by(AgtSteward.name)
        )
        return list(result.scalars().all())

    async def one(self, tenant_id: str, steward_id: str) -> AgtSteward | None:
        row = await self._session.get(AgtSteward, steward_id)
        return row if row is not None and row.tenant_id == tenant_id else None

    async def by_principal(self, tenant_id: str, principal_id: str) -> AgtSteward | None:
        await self._session.flush()
        result = await self._session.execute(
            select(AgtSteward).where(
                AgtSteward.tenant_id == tenant_id, AgtSteward.principal_id == principal_id
            )
        )
        return result.scalars().first()

    async def task(self, tenant_id: str, task_id: str) -> AgtTask | None:
        row = await self._session.get(AgtTask, task_id)
        return row if row is not None and row.tenant_id == tenant_id else None

    async def tasks_in(
        self, tenant_id: str, goal_ids: list[str], states: tuple[str, ...]
    ) -> list[AgtTask]:
        if not goal_ids:
            return []
        result = await self._session.execute(
            select(AgtTask)
            .where(
                AgtTask.tenant_id == tenant_id,
                AgtTask.goal_id.in_(goal_ids),
                AgtTask.state.in_(states),
            )
            .order_by(AgtTask.created_at)
        )
        return list(result.scalars().all())

    async def open_approvals(self, tenant_id: str) -> list[AgtApproval]:
        result = await self._session.execute(
            select(AgtApproval)
            .where(AgtApproval.tenant_id == tenant_id, AgtApproval.state == "open")
            .order_by(AgtApproval.created_at)
        )
        return list(result.scalars().all())

    async def approval(self, tenant_id: str, approval_id: str) -> AgtApproval | None:
        row = await self._session.get(AgtApproval, approval_id)
        return row if row is not None and row.tenant_id == tenant_id else None

    async def request_approval(
        self, tenant_id: str, task: AgtTask, action: dict[str, Any], justification: str
    ) -> AgtApproval:
        row = AgtApproval(
            tenant_id=tenant_id,
            task_id=task.id,
            action_json=action,
            justification=justification[:4000],
            created_at=_now(),
        )
        task.state = "awaiting_approval"
        self._session.add(row)
        await self._session.flush()
        return row

    async def add_goal(
        self,
        tenant_id: str,
        steward_id: str,
        *,
        statement: str,
        kind: str,
        inputs: dict[str, Any],
        schedule: str | None,
        by: str,
    ) -> AgtGoal:
        goal = AgtGoal(
            tenant_id=tenant_id,
            steward_id=steward_id,
            statement=statement,
            kind=kind,
            input_json=inputs,
            schedule=schedule,
            created_by=by,
            created_at=_now(),
        )
        self._session.add(goal)
        await self._session.flush()
        return goal

    async def goals(self, tenant_id: str, steward_id: str | None = None) -> list[AgtGoal]:
        statement = select(AgtGoal).where(AgtGoal.tenant_id == tenant_id)
        if steward_id:
            statement = statement.where(AgtGoal.steward_id == steward_id)
        result = await self._session.execute(statement.order_by(AgtGoal.created_at))
        return list(result.scalars().all())

    async def last_task(self, tenant_id: str, goal_id: str) -> AgtTask | None:
        result = await self._session.execute(
            select(AgtTask)
            .where(AgtTask.tenant_id == tenant_id, AgtTask.goal_id == goal_id)
            .order_by(AgtTask.created_at.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def add_task(self, tenant_id: str, goal: AgtGoal, task_key: str) -> AgtTask:
        task = AgtTask(
            tenant_id=tenant_id,
            goal_id=goal.id,
            task_key=task_key,
            kind=goal.kind,
            input_json=goal.input_json,
            created_at=_now(),
        )
        self._session.add(task)
        await self._session.flush()
        return task

    async def tasks(self, tenant_id: str, *, limit: int = 50) -> list[AgtTask]:
        result = await self._session.execute(
            select(AgtTask)
            .where(AgtTask.tenant_id == tenant_id)
            .order_by(AgtTask.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def cancel_open_tasks(self, tenant_id: str, steward_id: str) -> int:
        goal_ids = [g.id for g in await self.goals(tenant_id, steward_id)]
        if not goal_ids:
            return 0
        result = await self._session.execute(
            select(AgtTask).where(
                AgtTask.tenant_id == tenant_id,
                AgtTask.goal_id.in_(goal_ids),
                AgtTask.state.in_(("pending", "leased", "running", "awaiting_approval")),
            )
        )
        cancelled = 0
        for task in result.scalars():
            task.state, task.finished_at = "cancelled", _now()
            cancelled += 1
        await self._session.flush()
        return cancelled

    async def remember(
        self, tenant_id: str, steward_id: str, key: str, body: str, *, task_id: str | None
    ) -> None:
        """A note the steward keeps for its next task, replacing any earlier one."""
        existing = (
            (
                await self._session.execute(
                    select(AgtMemory).where(
                        AgtMemory.steward_id == steward_id,
                        AgtMemory.kind == "note",
                        AgtMemory.mkey == key,
                    )
                )
            )
            .scalars()
            .first()
        )
        if existing is None:
            self._session.add(
                AgtMemory(
                    tenant_id=tenant_id,
                    steward_id=steward_id,
                    kind="note",
                    mkey=key,
                    body=body[:20000],
                    source_task_id=task_id,
                    created_at=_now(),
                )
            )
        else:
            existing.body, existing.source_task_id = body[:20000], task_id
        await self._session.flush()

    # -- curation suggestions ------------------------------------------------

    async def suggest(
        self,
        tenant_id: str,
        *,
        object_kind: str,
        object_id: str,
        object_name: str,
        field: str,
        text: str,
        model: str,
        fingerprint: str | None,
        steward_id: str | None,
    ) -> CurSuggestion | None:
        """Record a draft, unless one is already open for the same field."""
        await self._session.flush()
        open_already = await self._session.execute(
            select(CurSuggestion.id).where(
                CurSuggestion.tenant_id == tenant_id,
                CurSuggestion.object_id == object_id,
                CurSuggestion.field == field,
                CurSuggestion.state == "open",
            )
        )
        if open_already.first() is not None:
            return None
        row = CurSuggestion(
            tenant_id=tenant_id,
            object_kind=object_kind,
            object_id=object_id,
            object_name=object_name,
            field=field,
            suggested=text[:4000],
            model=model,
            request_fingerprint=fingerprint,
            steward_id=steward_id,
            created_at=_now(),
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def suggestions(self, tenant_id: str, *, state: str = "open") -> list[CurSuggestion]:
        await self._session.flush()
        result = await self._session.execute(
            select(CurSuggestion)
            .where(CurSuggestion.tenant_id == tenant_id, CurSuggestion.state == state)
            .order_by(CurSuggestion.created_at)
        )
        return list(result.scalars().all())

    async def suggestion(self, tenant_id: str, suggestion_id: str) -> CurSuggestion | None:
        row = await self._session.get(CurSuggestion, suggestion_id)
        return row if row is not None and row.tenant_id == tenant_id else None
