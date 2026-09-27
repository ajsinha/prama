"""The Code page: receive application code, see what was read, and what was not.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated, Any

from fastapi import File, Form, Request, UploadFile

from prama.codeintake.archive import Limits
from prama.core.errors import PramaError, ValidationError
from prama.web.deps import Caller, Uow
from prama.web.rendering import flash_error_and_log, redirect_to, render
from prama.web.routes.base import UiRoutes


class CodeRoutes(UiRoutes):
    """Application code, received and read for lineage."""

    SUBJECT = "relationship"

    def register(self) -> None:
        self.page("/code", self.index, name="code")
        self.page("/code/zip", self.upload, name="code_zip", methods=["POST"])
        self.page("/code/git", self.fetch, name="code_git", methods=["POST"])

    async def index(self, request: Request, uow: Uow, caller: Caller) -> Any:
        sources = {s.id: s for s in await uow.code.sources(caller.tenant_id)}
        runs = await uow.code.runs(caller.tenant_id)
        return render(request, "code/index.html", sources=sources, runs=runs)

    async def upload(
        self,
        request: Request,
        uow: Uow,
        caller: Caller,
        source: Annotated[str, Form()] = "",
        dialect: Annotated[str, Form()] = "ansi",
        archive: Annotated[UploadFile | None, File()] = None,
    ) -> Any:
        from prama.codeintake.intake import receive_zip

        cap = Limits().max_compressed
        try:
            if archive is None or not source.strip():
                raise ValidationError("choose a ZIP and name the source", remedy="Fill in both.")
            with tempfile.TemporaryDirectory() as scratch:
                target = Path(scratch) / "upload.zip"
                written = 0
                with target.open("wb") as sink:
                    while chunk := await archive.read(1 << 16):
                        written += len(chunk)
                        if written > cap:  # streamed, so a huge upload never lands whole
                            raise ValidationError(
                                "the archive is larger than the intake limit",
                                remedy="Send a smaller archive, or use a git location.",
                            )
                        sink.write(chunk)
                run = await receive_zip(
                    uow,
                    request.app.state.config,
                    caller.tenant_id,
                    source.strip(),
                    target,
                    dialect=dialect,
                    by=caller.principal_id,
                )
        except PramaError as exc:
            flash_error_and_log(request, "That code could not be received", exc)
            return redirect_to(request, "code")
        return redirect_to(request, "code", flash_message=f"Read: {run.status}.")

    async def fetch(
        self,
        request: Request,
        uow: Uow,
        caller: Caller,
        source: Annotated[str, Form()] = "",
        url: Annotated[str, Form()] = "",
        ref: Annotated[str, Form()] = "main",
        credential_ref: Annotated[str, Form()] = "",
        dialect: Annotated[str, Form()] = "ansi",
    ) -> Any:
        from prama.codeintake.intake import receive_git

        try:
            run = await receive_git(
                uow,
                request.app.state.config,
                caller.tenant_id,
                source.strip(),
                url.strip(),
                ref.strip() or "main",
                credential_ref=credential_ref.strip() or None,
                dialect=dialect,
                by=caller.principal_id,
            )
        except PramaError as exc:
            flash_error_and_log(request, "That repository could not be fetched", exc)
            return redirect_to(request, "code")
        return redirect_to(request, "code", flash_message=f"Read: {run.status}.")
