"""Application code over the API: receive it, read its lineage, and review a change.

Code is received as a ZIP or fetched from a git location, and read by the
sandboxed reader intake uses: parsed, **never executed**. A git location is
checked before anything is fetched (`prama.codeintake.git.check_location`): no
loopback, private or link-local address, no `file://`, and only the hosts in
`codeintake.git.allowed_hosts` when that list is set.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from pydantic import BaseModel, Field

from prama.api.deps import RelationshipReader, RelationshipWriter, Uow
from prama.api.routes._knowledge import spool
from prama.codeintake.archive import Limits

router = APIRouter(tags=["code"])


def _run(run: Any, names: dict[str, str] | None = None) -> dict[str, Any]:
    return {
        "run": run.id,
        "source": (names or {}).get(run.source_id, run.source_id),
        "status": run.status,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "commit": run.commit_sha,
        "snapshot": run.snapshot_hash,
        "coverage": run.coverage_json or {},
        "inventory": run.inventory_json or {},
        "error": run.error,
    }


@router.post("/code/zip")
async def receive_zip(
    request: Request,
    caller: RelationshipWriter,
    uow: Uow,
    source: str = Form(..., min_length=1, max_length=128),
    dialect: str = Form("ansi"),
    archive: UploadFile = File(...),
) -> dict[str, Any]:
    """Receive a ZIP of application code and read its lineage. Never executed.

    A path that climbs out, a link, a bomb or an oversized entry is refused
    with its reason before anything is read.
    """
    from prama.codeintake.intake import receive_zip as receive

    with tempfile.TemporaryDirectory() as scratch:
        target = await spool(
            archive, Path(scratch) / "upload.zip", Limits().max_compressed, what="the archive"
        )
        run = await receive(
            uow,
            request.app.state.config,
            caller.tenant_id,
            source.strip(),
            target,
            dialect=dialect,
            by=caller.principal_id,
        )
    return _run(run, {run.source_id: source.strip()})


class GitIn(BaseModel):
    source: str = Field(..., min_length=1, max_length=128)
    url: str = Field(..., description="https:// or ssh:// (git@host:org/repo.git)")
    ref: str = "main"
    credential_ref: str | None = Field(None, description="a secret reference, e.g. env://TOKEN")
    dialect: str = "ansi"


@router.post("/code/git")
async def receive_git(
    body: GitIn, request: Request, caller: RelationshipWriter, uow: Uow
) -> dict[str, Any]:
    """Fetch one ref of a repository and read its lineage. Never executed.

    The location is refused before anything is stored if it names a private,
    loopback or link-local address, or a host outside the allowed list.
    """
    from prama.codeintake.intake import receive_git as receive

    run = await receive(
        uow,
        request.app.state.config,
        caller.tenant_id,
        body.source.strip(),
        body.url.strip(),
        body.ref.strip() or "main",
        credential_ref=body.credential_ref or None,
        dialect=body.dialect,
        by=caller.principal_id,
    )
    return _run(run, {run.source_id: body.source.strip()})


@router.get("/code/sources")
async def sources(caller: RelationshipReader, uow: Uow) -> list[dict[str, Any]]:
    """Where code has come from. A credential is a reference, never a value."""
    return [
        {
            "id": s.id,
            "name": s.name,
            "kind": s.kind,
            "url": s.url,
            "ref": s.ref,
            "credential_ref": s.secret_ref,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in await uow.code.sources(caller.tenant_id)
    ]


@router.get("/code/runs")
async def runs(
    caller: RelationshipReader, uow: Uow, limit: int = Query(20, ge=1, le=500)
) -> list[dict[str, Any]]:
    """Recent readings, newest first, with what each covered and what it could not read."""
    names = {s.id: s.name for s in await uow.code.sources(caller.tenant_id)}
    return [_run(r, names) for r in await uow.code.runs(caller.tenant_id, limit=limit)]


@router.get("/code/runs/{run_id}/units")
async def units(run_id: str, caller: RelationshipReader, uow: Uow) -> list[dict[str, Any]]:
    """Each file one reading looked at, how, and the gaps it left."""
    return [
        {
            "path": u.path,
            "kind": u.kind,
            "scanner": u.scanner,
            "scanner_version": u.scanner_version,
            "statements": u.statements,
            "gaps": u.gaps_json or [],
        }
        for u in await uow.code.units(caller.tenant_id, run_id)
    ]


async def _live(uow: Any, tenant_id: str, offline: bool) -> list[Any]:
    return [] if offline else list(await uow.controls.live(tenant_id))


@router.post("/code/review")
async def review_archives(
    request: Request,
    caller: RelationshipReader,
    uow: Uow,
    base: UploadFile = File(..., description="the code before the change, as a ZIP"),
    head: UploadFile = File(..., description="the code with the change, as a ZIP"),
    dialect: str = Form("ansi"),
    offline: bool = Form(False),
    base_label: str = Form("base"),
    head_label: str = Form("head"),
) -> dict[str, Any]:
    """What a change does to lineage and to the controls resting on it.

    `fails` is true when a live control loses its basis — the change removes
    the edge it rests on — which `prama code review` exits 3 on. `markdown` is
    the same review as a pull-request comment. Deterministic; no model is asked.

    It stores nothing, but it reads submitted code in the sandbox, so it asks
    for `relationship:write` — the scope that may submit code at all.
    """
    from prama.codeintake.intake import review_zips

    cap = Limits().max_compressed
    live = await _live(uow, caller.tenant_id, offline)
    with tempfile.TemporaryDirectory() as scratch:
        before = await spool(base, Path(scratch) / "base.zip", cap, what="the base archive")
        after = await spool(head, Path(scratch) / "head.zip", cap, what="the head archive")
        result = await review_zips(
            request.app.state.config,
            before,
            after,
            dialect=dialect,
            live=live,
            base_label=base_label,
            head_label=head_label,
        )
    return {**result.to_dict(), "markdown": result.to_markdown()}


class ReviewRefsIn(BaseModel):
    url: str
    base: str
    head: str
    credential_ref: str | None = None
    dialect: str = "ansi"
    offline: bool = False


@router.post("/code/review/git")
async def review_refs(
    body: ReviewRefsIn, request: Request, caller: RelationshipReader, uow: Uow
) -> dict[str, Any]:
    """The same review over two refs of a repository, fetched with intake's protections."""
    from prama.codeintake.intake import review_refs as review

    result = await review(
        request.app.state.config,
        body.url.strip(),
        body.base.strip(),
        body.head.strip(),
        credential_ref=body.credential_ref or None,
        dialect=body.dialect,
        live=await _live(uow, caller.tenant_id, body.offline),
    )
    return {**result.to_dict(), "markdown": result.to_markdown()}
