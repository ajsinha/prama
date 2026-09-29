"""The break workbench: two systems side by side, and what people did about it.

The list screen says a reconciliation has four hundred breaks. This one is
where somebody works them, and its whole job is to stop the queue being worked
in the order that feels urgent.

**Sorted by kind, not by size.** A hundred-million-euro timing break is less
urgent than a thousand-euro genuine one — the first clears itself and the
second is somebody's missing trade. Sorting by magnitude puts the queue in
exactly the wrong order and looks authoritative doing it, so the ordering here
is: genuine differences, then everything else that needs a person, then the
configuration faults, then the ones that clear themselves.

**Configuration faults are separated out.** Sign, duplicate and FX breaks are
usually somebody's setup being wrong. Routing them to a data steward wastes the
steward's day and leaves the setup wrong, so they are grouped and labelled as
what they are.

**Accepted breaks stay on the screen.** A carried reconciling item that
disappears once accepted is how a reconciliation quietly stops reconciling.

**The normalisation trail is shown beside every break.** The first question
about any difference is whether it is real or a translation error, and a
workbench that shows the two amounts without showing what was done to them
invites the reader to answer it wrong.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Form, Request

from prama.core.errors import PramaError
from prama.recon import service
from prama.recon.workbench import URGENCY, Row
from prama.web.deps import Caller, Uow
from prama.web.rendering import flash, flash_error_and_log, redirect_to, render
from prama.web.routes.base import UiRoutes


class ReconRoutes(UiRoutes):
    SUBJECT = "break"
    """The workbench and its three dispositions."""

    def register(self) -> None:
        self.page("/reconciliation/{definition}", self.break_workbench, name="break_workbench")
        self.page(
            "/reconciliation/breaks/{break_id}/assign",
            self.break_assign,
            name="break_assign",
            methods=["POST"],
        )
        self.page(
            "/reconciliation/breaks/{break_id}/explain",
            self.break_explain,
            name="break_explain",
            methods=["POST"],
        )
        self.page(
            "/reconciliation/breaks/{break_id}/accept",
            self.break_accept,
            name="break_accept",
            methods=["POST"],
        )

    async def break_workbench(
        self,
        request: Request,
        definition: str,
        caller: Caller,
        uow: Uow,
        show: str = "outstanding",
    ) -> Any:
        """Every break for one reconciliation, in the order it should be worked."""
        rows, cleared_count = await service.workbench_rows(
            uow, caller.tenant_id, definition, show=show
        )
        return render(
            request,
            "reconciliation/workbench.html",
            definition=definition,
            rows=rows,
            show=show,
            # Named rather than left to the reader to notice from an absence:
            # "forty cleared since yesterday" and "nothing changed" produce the
            # same queue length.
            cleared_count=cleared_count,
            # Grouped, because sending a configuration fault to a data steward
            # wastes their day and leaves the setup wrong.
            configuration=[row for row in rows if row.is_configuration],
            stale=[row for row in rows if row.is_stale],
            accepted=[row for row in rows if row.state == "accepted"],
        )

    async def break_assign(
        self,
        request: Request,
        break_id: str,
        caller: Caller,
        uow: Uow,
        definition: Annotated[str, Form()] = "",
        owner: Annotated[str, Form()] = "",
    ) -> Any:
        return await self._act(
            request,
            definition,
            lambda: service.assign(
                uow, caller.tenant_id, break_id, owner=owner, by=caller.principal_id or ""
            ),
            "Assigned.",
        )

    async def break_explain(
        self,
        request: Request,
        break_id: str,
        caller: Caller,
        uow: Uow,
        definition: Annotated[str, Form()] = "",
        text: Annotated[str, Form()] = "",
    ) -> Any:
        return await self._act(
            request,
            definition,
            lambda: service.explain(
                uow, caller.tenant_id, break_id, text=text, by=caller.principal_id or ""
            ),
            "Noted.",
        )

    async def break_accept(
        self,
        request: Request,
        break_id: str,
        caller: Caller,
        uow: Uow,
        definition: Annotated[str, Form()] = "",
        reason: Annotated[str, Form()] = "",
    ) -> Any:
        return await self._act(
            request,
            definition,
            lambda: service.accept(
                uow, caller.tenant_id, break_id, reason=reason, by=caller.principal_id or ""
            ),
            "Accepted as a known reconciling item. It stays on this screen.",
        )

    async def _act(self, request: Request, definition: str, action: Any, said: str) -> Any:
        """One disposition, then back to the workbench.

        The three handlers differ only in which DAO call they make and what
        they say afterwards; writing the redirect and the failure handling
        three times is how two of them end up swallowing an error the third
        reports.
        """
        try:
            await action()
        except PramaError as exc:
            flash_error_and_log(request, "That could not be recorded", exc)
        else:
            flash(request, said)
        return redirect_to(request, "break_workbench", definition=definition)


__all__ = ["URGENCY", "ReconRoutes", "Row"]
