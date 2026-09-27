"""The Schedule page: is anything running controls, and what did it do?

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request

from prama.web.rendering import redirect_to, render
from prama.web.routes.base import UiRoutes


class ScheduleRoutes(UiRoutes):
    """The scheduler's state, and a way to run a tick now."""

    SUBJECT = "control"
    WRITE_SCOPE = "control:approve"

    def register(self) -> None:
        self.page("/schedule", self.index, name="schedule")
        self.page("/schedule/run", self.run_now, name="schedule_run", methods=["POST"])

    async def index(self, request: Request) -> Any:
        return render(
            request, "schedule/index.html", scheduler=getattr(request.app.state, "scheduler", None)
        )

    async def run_now(self, request: Request) -> Any:
        scheduler = getattr(request.app.state, "scheduler", None)
        if scheduler is None:
            return redirect_to(
                request, "schedule", flash_message="The scheduler is off.", flash_category="warning"
            )
        tick = await scheduler.tick()
        return redirect_to(request, "schedule", flash_message=f"Tick {tick.outcome}.")
