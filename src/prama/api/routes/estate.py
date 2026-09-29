"""Estate-level routes: maturity, conflicts, coverage gaps.

The questions a CDO asks, rather than the ones an engineer asks. Each answer is
decomposed rather than asserted: a score that cannot be explained is a score
nobody will act on.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from prama.api.deps import Reader, Uow
from prama.api.schemas import ConflictOut, MaturityOut
from prama.semantic.services import EstateService, estate_files

router = APIRouter(prefix="/estate", tags=["estate"])


@router.get("/maturity", response_model=MaturityOut)
async def estate_maturity(
    caller: Reader,
    uow: Uow,
    domain_id: str | None = Query(default=None),
    scope: str = Query(default="estate"),
) -> MaturityOut:
    """How much of the estate the business has actually described.

    Returns the components as well as the number, because the point of the score
    is the action it implies, not the score itself.
    """
    score = await EstateService(uow).maturity(caller.tenant_id, domain_id=domain_id, scope=scope)
    return MaturityOut(**score.to_dict())


@router.get("/conflicts", response_model=list[ConflictOut])
async def semantic_conflicts(caller: Reader, uow: Uow) -> list[ConflictOut]:
    """Attributes claiming one canonical meaning while disagreeing about it.

    Reported, never resolved: which definition is right is a business decision.
    """
    conflicts = await EstateService(uow).conflicts(caller.tenant_id)
    return [ConflictOut(**c.to_dict()) for c in conflicts]


@router.get("/coverage-gaps", response_model=dict[str, list[str]])
async def coverage_gaps(caller: Reader, uow: Uow) -> dict[str, list[str]]:
    """What is declared but unreachable, unowned, or unshaped.

    The honest list. A physical-first tool cannot produce it at all, because it
    only knows about things it managed to crawl.
    """
    return await EstateService(uow).coverage_gaps(caller.tenant_id)


# -- export and diff (evidence and assurance area) -------------------------------


class EstateFilesIn(BaseModel):
    #: Path (relative to the export directory) -> YAML text, as `export` returns them.
    files: dict[str, str]


@router.get("/export")
async def export_estate(caller: Reader, uow: Uow) -> dict[str, Any]:
    """The declared estate as reviewable YAML, by path — what `prama estate export` writes."""
    files = await estate_files.export(uow, caller.tenant_id)
    return {"files": dict(sorted(files.items()))}


@router.post("/diff")
async def diff_estate(body: EstateFilesIn, caller: Reader, uow: Uow) -> dict[str, Any]:
    """Where a set of files disagrees with the store, in both directions. Never resolved.

    Changes nothing: a POST only because it carries the files, so it asks for
    the read scope, and is listed as a read-only POST, with its reason, in
    `tests/architecture/test_scopes.py`. An auditor may compare a repository
    with the estate.
    """
    return await estate_files.diff_against(uow, caller.tenant_id, body.files)
