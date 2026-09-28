"""My queue: everything waiting on the signed-in person. And posting comments.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Form, Request

from prama.core.errors import PramaError
from prama.security.scopes import permits
from prama.semantic.services import collaboration
from prama.web.deps import Caller, Uow
from prama.web.rendering import flash_error_and_log, render
from prama.web.routes.base import UiRoutes


class QueueRoutes(UiRoutes):
    SUBJECT = "declaration"

    def register(self) -> None:
        self.page("/queue", self.index, name="my_queue", scope="declaration:read")
        self.page(
            "/comments", self.post, name="comment_post", methods=["POST"], scope="comment:write"
        )
        self.page(
            "/comments/{root_id}/resolve",
            self.resolve,
            name="comment_resolve",
            methods=["POST"],
            scope="comment:write",
        )

    async def index(self, request: Request, uow: Uow, caller: Caller) -> Any:
        waiting = (
            await collaboration.queue(
                uow,
                caller.tenant_id,
                caller.principal_id,
                approver=permits(caller.scopes, "control:approve"),
            )
            if caller.principal_id
            else None
        )
        return render(request, "queue/index.html", q=waiting)

    async def post(
        self,
        request: Request,
        uow: Uow,
        caller: Caller,
        object_kind: Annotated[str, Form()] = "",
        object_ref: Annotated[str, Form()] = "",
        body: Annotated[str, Form()] = "",
        parent_id: Annotated[str, Form()] = "",
        back: Annotated[str, Form()] = "/queue",
    ) -> Any:
        try:
            await collaboration.post(
                uow,
                caller.tenant_id,
                object_kind=object_kind,
                object_ref=object_ref,
                body=body,
                by=caller.principal_id or "",
                parent_id=parent_id or None,
            )
        except PramaError as exc:
            flash_error_and_log(request, "That comment was not posted", exc)
        return _back(back)

    async def resolve(
        self,
        request: Request,
        uow: Uow,
        caller: Caller,
        root_id: str,
        back: Annotated[str, Form()] = "/queue",
    ) -> Any:
        try:
            await collaboration.resolve(
                uow, caller.tenant_id, root_id, by=caller.principal_id or ""
            )
        except PramaError as exc:
            flash_error_and_log(request, "That thread was not resolved", exc)
        return _back(back)


def _back(path: str) -> Any:
    from fastapi.responses import RedirectResponse

    # Only a path on this site: an open redirect is a phishing tool.
    safe = path if path.startswith("/") and not path.startswith("//") else "/queue"
    return RedirectResponse(safe, status_code=303)
