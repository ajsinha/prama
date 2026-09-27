"""The Delegates page: configured and uploaded DQ delegates, and the approval queue.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import File, Form, Request, UploadFile

from prama.core.errors import PramaError, ValidationError
from prama.delegates import uploads
from prama.web.deps import Caller, Uow
from prama.web.rendering import flash_error_and_log, redirect_to, render
from prama.web.routes.base import UiRoutes


class DelegateRoutes(UiRoutes):
    """Upload a delegate, see what vetting found, and approve with four eyes."""

    SUBJECT = "control"

    def register(self) -> None:
        post = ["POST"]
        self.page("/delegates", self.index, name="delegates", scope="control:read")
        self.page(
            "/delegates/upload",
            self.upload,
            name="delegates_upload",
            methods=post,
            scope="control:propose",
        )
        self.page(
            "/delegates/{upload_id}/decide",
            self.decide,
            name="delegates_decide",
            methods=post,
            scope="control:approve",
        )

    async def index(self, request: Request, uow: Uow, caller: Caller) -> Any:
        host = _configured(request)
        rows = await uow.delegate_uploads.all(caller.tenant_id)
        return render(
            request,
            "delegates/index.html",
            configured=[a.describe() for a in host.registry.all() if not a.sandbox_only],
            refused=host.registry.refused,
            uploads=[(row, json.loads(row.described), json.loads(row.findings)) for row in rows],
            me=caller.principal_id,
        )

    async def upload(
        self,
        request: Request,
        uow: Uow,
        caller: Caller,
        delegate: Annotated[UploadFile | None, File()] = None,
    ) -> Any:
        try:
            if delegate is None:
                raise ValidationError("choose a .py file", remedy="Pick the delegate's file.")
            body = await delegate.read(uploads.MAX_BYTES + 1)
            row = await uploads.submit(
                uow, caller.tenant_id, delegate.filename or "", body, by=caller.principal_id or ""
            )
        except PramaError as exc:
            flash_error_and_log(request, "That delegate was not accepted", exc)
            return redirect_to(request, "delegates")
        return redirect_to(
            request,
            "delegates",
            flash_message=f"{row.name}@{row.version} passed vetting and waits for approval.",
        )

    async def decide(
        self,
        request: Request,
        uow: Uow,
        caller: Caller,
        upload_id: str,
        action: Annotated[str, Form()] = "",
        note: Annotated[str, Form()] = "",
    ) -> Any:
        try:
            row = await uploads.decide(
                uow,
                caller.tenant_id,
                upload_id,
                action=action,
                by=caller.principal_id or "",
                note=note.strip(),
            )
        except PramaError as exc:
            flash_error_and_log(request, "That could not be recorded", exc)
            return redirect_to(request, "delegates")
        return redirect_to(
            request, "delegates", flash_message=f"{row.name}@{row.version} is {row.state}."
        )


def _configured(request: Request) -> Any:
    """The server's configured delegates, loaded once per process."""
    host = getattr(request.app.state, "delegate_host", None)
    if host is None:
        from prama.delegates.host import host_from_config

        host = host_from_config(request.app.state.config)
        request.app.state.delegate_host = host
    return host
