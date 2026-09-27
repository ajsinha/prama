"""Approved DQ delegate uploads, for remote agents to fetch into their own delegates.paths.

An agent beside the data runs only what its own configuration admits. These
two endpoints let an operator (or `prama delegate pull`) copy the estate's
approved uploads there, with the SHA-256 to check them against.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from prama.api.deps import ControlReader, Uow
from prama.core.errors import NotFoundError

router = APIRouter(tags=["delegates"])


@router.get("/delegates/uploads")
async def approved_uploads(uow: Uow, caller: ControlReader) -> list[dict[str, Any]]:
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
