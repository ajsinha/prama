"""The Agents page: steward agents, their goals, what they did, and the kill switch.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Form, Request

from prama.core.errors import NotFoundError, PramaError, ValidationError
from prama.steward import identity
from prama.steward.runner import run_task
from prama.steward.tools import TOOLS
from prama.web.deps import Caller, Uow
from prama.web.rendering import flash_error_and_log, redirect_to, render
from prama.web.routes.base import UiRoutes

ADMIN = "admin"


class AgentRoutes(UiRoutes):
    """Steward agents, for an administrator."""

    SUBJECT = "admin"

    def register(self) -> None:
        post = ["POST"]
        self.page("/agents", self.index, name="agents", scope=ADMIN)
        self.page("/agents/new", self.create, name="agents_new", methods=post, scope=ADMIN)
        self.page(
            "/agents/{steward_id}/goals",
            self.add_goal,
            name="agents_goal",
            methods=post,
            scope=ADMIN,
        )
        self.page(
            "/agents/{steward_id}/state",
            self.set_state,
            name="agents_state",
            methods=post,
            scope=ADMIN,
        )
        self.page(
            "/agents/goals/{goal_id}/run",
            self.run_now,
            name="agents_run",
            methods=post,
            scope=ADMIN,
        )

    async def _page(self, request: Request, uow: Any, tenant: str, **extra: Any) -> Any:
        stewards = await uow.stewards.all(tenant)
        goals = await uow.stewards.goals(tenant)
        return render(
            request,
            "agents/index.html",
            stewards=stewards,
            goals={s.id: [g for g in goals if g.steward_id == s.id] for s in stewards},
            tasks=await uow.stewards.tasks(tenant),
            goal_names={g.id: g.statement for g in goals},
            tools=TOOLS,
            **extra,
        )

    async def index(self, request: Request, uow: Uow, caller: Caller) -> Any:
        return await self._page(request, uow, caller.tenant_id, issued=None)

    async def create(
        self, request: Request, uow: Uow, caller: Caller, name: Annotated[str, Form()] = ""
    ) -> Any:
        try:
            if not caller.principal_id:
                # A steward's sponsor is a person who answers for it. The
                # single-tenant fallback has nobody signed in to be that person.
                raise ValidationError(
                    "a steward needs a signed-in sponsor",
                    remedy="Sign in as the person who will answer for this steward.",
                )
            steward, plaintext = await identity.create(
                uow, caller.tenant_id, name.strip(), sponsor_id=caller.principal_id
            )
        except PramaError as exc:
            flash_error_and_log(request, "That steward could not be created", exc)
            return redirect_to(request, "agents")
        # The key, shown once, for a steward that will run elsewhere.
        return await self._page(
            request, uow, caller.tenant_id, issued={"name": steward.name, "key": plaintext}
        )

    async def add_goal(
        self,
        request: Request,
        uow: Uow,
        caller: Caller,
        steward_id: str,
        kind: Annotated[str, Form()] = "",
        statement: Annotated[str, Form()] = "",
        schedule: Annotated[str, Form()] = "",
        source: Annotated[str, Form()] = "",
    ) -> Any:
        try:
            if kind not in TOOLS:
                raise NotFoundError(f"no goal kind {kind!r}", remedy="Choose one from the list.")
            await uow.stewards.add_goal(
                caller.tenant_id,
                steward_id,
                statement=statement.strip() or TOOLS[kind][0],
                kind=kind,
                inputs={"source": source.strip()} if source.strip() else {},
                schedule=schedule.strip() or None,
                by=caller.principal_id or "console",
            )
        except PramaError as exc:
            flash_error_and_log(request, "That goal could not be added", exc)
            return redirect_to(request, "agents")
        return redirect_to(request, "agents", flash_message="Goal added.")

    async def set_state(
        self,
        request: Request,
        uow: Uow,
        caller: Caller,
        steward_id: str,
        state: Annotated[str, Form()] = "",
    ) -> Any:
        try:
            steward = await uow.stewards.one(caller.tenant_id, steward_id)
            if steward is None:
                raise NotFoundError("no such steward", remedy="Stewards are listed on this page.")
            await identity.set_state(uow, caller.tenant_id, steward, state, by=caller.principal_id)
        except PramaError as exc:
            flash_error_and_log(request, "That could not be changed", exc)
            return redirect_to(request, "agents")
        return redirect_to(request, "agents", flash_message=f"{steward.name} is now {state}.")

    async def run_now(self, request: Request, uow: Uow, caller: Caller, goal_id: str) -> Any:
        from datetime import UTC, datetime

        goals = {g.id: g for g in await uow.stewards.goals(caller.tenant_id)}
        goal = goals.get(goal_id)
        steward = await uow.stewards.one(caller.tenant_id, goal.steward_id) if goal else None
        if goal is None or steward is None:
            return redirect_to(
                request, "agents", flash_message="No such goal.", flash_category="warning"
            )
        if steward.state != "active":
            return redirect_to(
                request,
                "agents",
                flash_message=f"{steward.name} is {steward.state}.",
                flash_category="warning",
            )
        task = await run_task(
            uow,
            request.app.state.config,
            caller.tenant_id,
            steward,
            goal,
            key=f"{goal.id}:manual:{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}",
        )
        return redirect_to(request, "agents", flash_message=f"Task {task.state}.")
