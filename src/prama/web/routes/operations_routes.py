"""Incidents, reconciliation and scorecards.

Each of these reads *runs*, and runs are recorded in the evidence ledger.
Wave 9 mounts the console on a platform whose ledger is not yet persistent, so
these pages have one job that matters more than the tables they will eventually
draw: to say, without ambiguity, that nothing has been observed.

An empty incident list rendered as a clean incident list is the single most
dangerous screen a data quality product can ship. Every one of these pages
distinguishes "we looked and found nothing" from "nothing has run" and refuses
to render the first when it means the second.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request

from prama.web.deps import Caller, Uow
from prama.web.rendering import render
from prama.web.routes.base import UiRoutes


class OperationsRoutes(UiRoutes):
    """The run-backed screens."""

    def register(self) -> None:
        self.page("/incidents", self.incident_list, name="incident_list")
        self.page("/reconciliation", self.reconciliation_list, name="reconciliation_list")
        self.page("/scorecards", self.scorecard_list, name="scorecard_list")

    async def _observation(self, caller: Caller, uow: Uow) -> dict[str, Any]:
        """What, if anything, has been observed for this tenant.

        Reported as a state rather than as a count. ``no_runs`` and ``clean``
        are different answers to the same question and must never render the
        same way — a score of 100% derived from zero measurements is the
        flattering direction, and it is exactly what an unqualified count
        produces.
        """
        ledger = getattr(uow, "evidence", None)
        declared = await uow.datasets.count_current(caller.tenant_id)
        return {
            "state": "no_runs" if ledger is None else "observed",
            "declared_datasets": declared,
            "reason": (
                "No control has executed against this estate. Nothing on this page "
                "is a statement about data quality — it is a statement that nothing "
                "has been examined yet."
            )
            if ledger is None
            else "",
        }

    async def incident_list(self, request: Request, caller: Caller, uow: Uow) -> Any:
        return render(
            request,
            "incidents/list.html",
            observation=await self._observation(caller, uow),
            incidents=[],
        )

    async def reconciliation_list(self, request: Request, caller: Caller, uow: Uow) -> Any:
        return render(
            request,
            "reconciliation/list.html",
            observation=await self._observation(caller, uow),
            reconciliations=[],
        )

    async def scorecard_list(self, request: Request, caller: Caller, uow: Uow) -> Any:
        return render(
            request,
            "scorecards/list.html",
            observation=await self._observation(caller, uow),
            scores=[],
        )
