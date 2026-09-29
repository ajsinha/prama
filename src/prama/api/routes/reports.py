"""The print packs, for programs: an index, and each pack as HTML or as JSON.

The HTML is the document the console serves at ``/reports/...`` — standalone,
styles inlined, ready to print to PDF. The JSON is the content it was rendered
from. There is no server-side PDF (see `prama.report.render`).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Query, Response

from prama.api.deps import ReportReader, Uow
from prama.report import packs

router = APIRouter(prefix="/reports", tags=["reports"])

Format = Literal["html", "json"]


def _html(artefact: Any) -> Response:
    return Response(
        content=artefact.html,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{artefact.filename}"'},
    )


@router.get("")
async def index(caller: ReportReader, uow: Uow) -> dict[str, Any]:
    """Which packs this estate can produce, and in which formats."""
    return await packs.index(uow, caller.tenant_id)


@router.get("/declarations", response_model=None)
async def declarations(
    caller: ReportReader, uow: Uow, fmt: Format = Query(default="html", alias="format")
) -> Response | dict[str, Any]:
    """What the business says its data is — including what nobody has connected."""
    if fmt == "json":
        return packs.as_json(await packs.declaration_contents(uow, caller.tenant_id))
    return _html(
        await packs.declarations(uow, caller.tenant_id, generated_by=caller.principal_id or "")
    )


@router.get("/controls", response_model=None)
async def controls(
    caller: ReportReader, uow: Uow, fmt: Format = Query(default="html", alias="format")
) -> Response | dict[str, Any]:
    """Every generated control, its reason, and the SQL it becomes."""
    if fmt == "json":
        return packs.as_json(await packs.control_contents(uow, caller.tenant_id))
    return _html(
        await packs.controls(uow, caller.tenant_id, generated_by=caller.principal_id or "")
    )
