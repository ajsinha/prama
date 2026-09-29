"""The evidence ledger, for programs: read it, verify it, compare, anchor, export.

Every read is the estate's own chain; the tenant is the caller's, never the
request's. The export is the same bundle ``prama evidence export`` writes,
zipped, and ``scripts/verify_evidence.py`` checks it unzipped without Prama.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request, Response

from prama.api.deps import EvidenceAnchorer, EvidenceReader, Uow
from prama.core.errors import NotFoundError
from prama.evidence import service

router = APIRouter(prefix="/evidence", tags=["evidence"])


@router.get("")
async def list_records(
    caller: EvidenceReader,
    uow: Uow,
    control_id: str | None = None,
    dataset: str | None = None,
    verdict: str | None = None,
    run_id: str | None = None,
    since: str | None = Query(default=None, description="finished at or after (ISO-8601)"),
    until: str | None = Query(default=None, description="finished at or before (ISO-8601)"),
    limit: int = Query(default=100, ge=1, le=10_000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Records matching every filter given, newest first."""
    records = await uow.evidence.search(
        caller.tenant_id,
        control_id=control_id,
        dataset=dataset,
        verdict=verdict,
        run_id=run_id,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )
    return {
        "items": [service.record_view(r) for r in records],
        "limit": limit,
        "offset": offset,
    }


@router.get("/status")
async def status(caller: EvidenceReader, uow: Uow) -> dict[str, Any]:
    """Whether anything has been observed: ``observed``, ``no_runs``, and unfinished runs."""
    return await service.observation(uow, caller.tenant_id)


@router.get("/latest")
async def latest_per_control(caller: EvidenceReader, uow: Uow) -> dict[str, Any]:
    """Each control's current record, by control id — the basis of incidents and scores."""
    latest = await uow.evidence.latest_per_control(caller.tenant_id)
    return {key: service.record_view(record) for key, record in sorted(latest.items())}


@router.get("/verify")
async def verify(caller: EvidenceReader, uow: Uow) -> dict[str, Any]:
    """Check the chain as stored: record count, intact or not, head, Merkle root, breaches."""
    verification = await uow.evidence.verify(caller.tenant_id)
    return {**verification.to_dict(), "summary": verification.render()}


@router.get("/compare")
async def compare(
    caller: EvidenceReader,
    uow: Uow,
    original: int,
    replayed: int | None = Query(
        default=None, description="omitted: the newest record of the original's control"
    ),
) -> dict[str, Any]:
    """Why two records of a control differ: data, control, engine, parameters, or nothing named."""
    return await service.replay_compare(uow, caller.tenant_id, original, replayed)


@router.get("/runs")
async def runs(
    caller: EvidenceReader, uow: Uow, limit: int = Query(default=50, ge=1, le=1000)
) -> list[dict[str, Any]]:
    """Recent runs, newest first, including any that started and never reported."""
    return [
        service.run_view(r) for r in await uow.evidence_runs.recent(caller.tenant_id, limit=limit)
    ]


@router.get("/runs/{run_id}")
async def run(run_id: str, caller: EvidenceReader, uow: Uow) -> dict[str, Any]:
    """One run and the records it wrote, in chain order."""
    found = await uow.evidence_runs.get(run_id)
    if found is None or found.tenant_id != caller.tenant_id:
        raise NotFoundError(
            f"there is no run {run_id!r}",
            remedy="List runs with GET /evidence/runs.",
            context={"run": run_id},
        )
    records = await uow.evidence.for_run(run_id, tenant_id=caller.tenant_id)
    return {**service.run_view(found), "records": [service.record_view(r) for r in records]}


@router.post("/anchor")
async def anchor(request: Request, caller: EvidenceAnchorer, uow: Uow) -> dict[str, Any]:
    """Anchor the chain head with the configured witness, now. Idempotent per head.

    ``status`` is ``anchored`` or ``failed`` (with the reason in ``detail``); an
    empty chain answers ``{"status": "empty"}``.
    """
    row = await service.anchor_now(uow, caller.tenant_id, request.app.state.config)
    return {"status": "empty"} if row is None else service.anchor_view(row)


@router.get("/anchors")
async def anchors(caller: EvidenceReader, uow: Uow) -> list[dict[str, Any]]:
    """Every anchoring attempt, failures included, in chain order."""
    return [service.anchor_view(a) for a in await uow.anchors.for_tenant(caller.tenant_id)]


@router.get("/export")
async def export(caller: EvidenceReader, uow: Uow) -> Response:
    """The chain as a zip: manifest.json, evidence.ndjson, anchors.json.

    Refused (409) when the stored chain does not verify, because the bundle's
    hashes are recomputed and would hide the breach.
    """
    bundle, receipts = await service.export_bundle(uow, caller.tenant_id)
    return Response(
        content=service.bundle_zip(service.bundle_files(bundle, receipts)),
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f'attachment; filename="evidence-{bundle.manifest.from_sequence}-'
                f'{bundle.manifest.to_sequence}.zip"'
            )
        },
    )


@router.get("/{sequence}")
async def record(sequence: int, caller: EvidenceReader, uow: Uow) -> dict[str, Any]:
    """One record, by its position in the chain."""
    return service.record_view(await service.require(uow, caller.tenant_id, sequence))
