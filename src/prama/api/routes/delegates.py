"""Python DQ delegates over the API: upload, vet, decide with four eyes, and try one.

The path from a file to a control that runs it is the console's
(`prama.delegates.uploads`): vetted in a sandbox (the server never imports
uploaded code), proposed with what vetting found, and approved by somebody
holding `control:approve` who is **not** the uploader.

`/delegates/uploads` and its `source` are what a remote agent pulls: the
approved uploads only, with the SHA-256 to check them against.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import tempfile
from typing import Any, Literal

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from prama.api.deps import ControlApprover, ControlProposer, ControlReader, Uow
from prama.api.routes._knowledge import read_capped
from prama.core.errors import NotFoundError, ValidationError
from prama.delegates import uploads

router = APIRouter(tags=["delegates"])

#: Rows accepted by one try-out. A try is for a sample; a dataset runs as a control.
MAX_TRY_ROWS = 100_000


def _upload(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "version": row.version,
        "filename": row.filename,
        "state": row.state,
        "source_hash": row.source_hash,
        "described": json.loads(row.described),
        "findings": json.loads(row.findings),
        "submitted_by": row.submitted_by,
        "submitted_at": row.submitted_at,
        "decided_by": row.decided_by,
        "decided_at": row.decided_at,
        "note": row.note,
    }


@router.get("/delegates")
async def delegates(request: Request, uow: Uow, caller: ControlReader) -> dict[str, Any]:
    """What may run here: the server's configured delegates (and those it refused, with
    why), and this estate's uploads in every state."""
    from prama.delegates.host import server_host

    host = server_host(request.app.state, request.app.state.config)
    return {
        "configured": [a.describe() for a in host.registry.all() if not a.sandbox_only],
        "refused": dict(host.registry.refused),
        "uploads": [_upload(r) for r in await uow.delegate_uploads.all(caller.tenant_id)],
    }


@router.get("/delegates/uploads")
async def approved_uploads(uow: Uow, caller: ControlReader) -> list[dict[str, Any]]:
    """The approved uploads, for a remote agent's `delegates.paths`."""
    return [
        {
            "id": row.id,
            "name": row.name,
            "version": row.version,
            "filename": row.filename,
            "source_hash": row.source_hash,
            "described": json.loads(row.described),
        }
        for row in await uow.delegate_uploads.approved(caller.tenant_id)
    ]


@router.get("/delegates/uploads/{upload_id}/source", response_class=PlainTextResponse)
async def upload_source(upload_id: str, uow: Uow, caller: ControlReader) -> PlainTextResponse:
    row = await uow.delegate_uploads.one(caller.tenant_id, upload_id)
    if row is None or row.state != "approved":
        raise NotFoundError(
            "no approved delegate upload with that id",
            remedy="List them at /api/v1/delegates/uploads.",
        )
    return PlainTextResponse(
        row.source,
        media_type="text/x-python",
        headers={"X-Prama-Source-Hash": row.source_hash},
    )


@router.post("/delegates/submissions", status_code=201)
async def submit(
    uow: Uow, caller: ControlProposer, delegate: UploadFile = File(...)
) -> dict[str, Any]:
    """Upload one `.py` delegate. It is vetted in the sandbox and, if it conforms,
    proposed for somebody else to approve. A refusal is not stored; it says why."""
    body = await read_capped(delegate, uploads.MAX_BYTES + 1, what=delegate.filename or "the file")
    row = await uploads.submit(
        uow, caller.tenant_id, delegate.filename or "", body, by=caller.principal_id or ""
    )
    return _upload(row)


@router.get("/delegates/submissions/{upload_id}")
async def submission(upload_id: str, uow: Uow, caller: ControlReader) -> dict[str, Any]:
    """One upload: what it declares, what vetting found, and who decided it."""
    row = await uow.delegate_uploads.one(caller.tenant_id, upload_id)
    if row is None:
        raise NotFoundError("no such upload", remedy="List them at /api/v1/delegates.")
    return {**_upload(row), "source": row.source}


class DecisionIn(BaseModel):
    action: Literal["approve", "reject", "retire"]
    note: str = Field("", max_length=2000)


@router.post("/delegates/submissions/{upload_id}/decide")
async def decide(
    upload_id: str, body: DecisionIn, uow: Uow, caller: ControlApprover
) -> dict[str, Any]:
    """Approve or reject a proposal, or retire an approved delegate.

    Four eyes: the uploader cannot approve their own delegate.
    """
    row = await uploads.decide(
        uow,
        caller.tenant_id,
        upload_id,
        action=body.action,
        by=caller.principal_id or "",
        note=body.note.strip(),
    )
    return _upload(row)


@router.post("/delegates/vet")
async def vet(caller: ControlProposer, delegate: UploadFile = File(...)) -> dict[str, Any]:
    """Run the conformance kit over a file in the sandbox, and store nothing."""
    body = await read_capped(delegate, uploads.MAX_BYTES, what=delegate.filename or "the file")
    name = (delegate.filename or "delegate.py").rsplit("/", 1)[-1]
    if not name.endswith(".py"):
        raise ValidationError(f"{name} is not a .py file", remedy="Upload one .py file.")
    return await asyncio.to_thread(uploads.vet, name, body)


class TryIn(BaseModel):
    delegate: str = Field(..., description="its registered name, optionally @version")
    rows: list[dict[str, Any]]
    params: dict[str, Any] = Field(default_factory=dict)


@router.post("/delegates/try")
async def try_delegate(
    body: TryIn, request: Request, uow: Uow, caller: ControlProposer
) -> dict[str, Any]:
    """Run one delegate over supplied rows exactly as a control would: sandboxed, with
    canonical JSON rows, judged by the deterministic engine at the default threshold.

    The delegates it can name are the server's configured ones and this estate's
    approved uploads.
    """
    from prama.backend.execute import judge
    from prama.delegates.host import host_from_config
    from prama.delegates.testkit import control_for
    from prama.ir.resolve import resolved
    from prama.pql import parse_control

    if len(body.rows) > MAX_TRY_ROWS:
        raise ValidationError(
            f"{len(body.rows)} rows is more than a try-out takes ({MAX_TRY_ROWS})",
            remedy="Try it on a sample; run it over the dataset as a control.",
        )
    source = control_for(body.delegate, body.params)
    plan = resolved(parse_control(source))
    host = host_from_config(request.app.state.config)
    with tempfile.TemporaryDirectory(prefix="prama-try-") as scratch:
        host = dataclasses.replace(host, upload_dir=scratch)
        from prama.delegates.uploads import adopt

        await adopt(uow, caller.tenant_id, host)
        result = await asyncio.to_thread(host.measure_plan, plan, body.rows)
    return {
        "control": source,
        "verdict": judge(plan, result.metrics).verdict.value,
        "metrics": result.metrics,
        "note": result.note,
        "samples": result.samples,
        "delegate": result.parameters,
    }
