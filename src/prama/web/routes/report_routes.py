"""The print artefacts, served from the console.

Rendered as standalone documents rather than as pages inside the shell: a pack
that leaves the building must not depend on the console's stylesheet, its
navigation, or the reader's theme. Everything it needs is inlined, so the file
that is saved is the file that is read.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse

from prama.report import packs
from prama.web.deps import Caller, Uow
from prama.web.rendering import render
from prama.web.routes.base import UiRoutes

#: Re-exported from `prama.report.packs`, where the packs are assembled.
REPORTED_STATES = packs.REPORTED_STATES


class ReportRoutes(UiRoutes):
    SUBJECT = "report"
    """The pack index and the two packs. Assembled in `prama.report.packs`,
    which ``/api/v1/reports`` reads too."""

    def register(self) -> None:
        self.page("/reports", self.report_index, name="report_index")
        self.page("/reports/declarations", self.declaration_pack, name="report_declarations")
        self.page("/reports/controls", self.control_pack, name="report_controls")

    async def report_index(self, request: Request, caller: Caller, uow: Uow) -> Any:
        return render(
            request,
            "reports/index.html",
            declared=await uow.datasets.count_current(caller.tenant_id),
        )

    async def declaration_pack(self, caller: Caller, uow: Uow) -> HTMLResponse:
        """What the business says its data is."""
        artefact = await packs.declarations(
            uow, caller.tenant_id, generated_by=caller.principal_id or ""
        )
        return HTMLResponse(artefact.html)

    async def control_pack(self, caller: Caller, uow: Uow) -> HTMLResponse:
        """Every control, its reason, and the SQL it becomes."""
        artefact = await packs.controls(
            uow, caller.tenant_id, generated_by=caller.principal_id or ""
        )
        return HTMLResponse(artefact.html)
