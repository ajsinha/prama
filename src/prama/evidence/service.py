"""The evidence ledger as the console, the CLI and the API all read it.

One module so that each question has one answer. The console's evidence
screen, ``prama evidence`` and ``/api/v1/evidence`` used to be three places a
record could be rendered, a bundle assembled or an anchor taken — and a rule
restated in a second place drifts, silently, in the flattering direction.

Nothing here decides a verdict. It reads what the executor recorded, checks
that the chain still holds, and packages it for somebody outside Prama.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any

from prama.core.errors import ConflictError, NotFoundError, ValidationError
from prama.evidence.record import EvidenceRecord
from prama.evidence.replay import compare
from prama.evidence.retention import Archivist, Bundle


def record_view(record: EvidenceRecord) -> dict[str, Any]:
    """One record as JSON: its content, its hashes, and the claim it supports.

    ``claim`` is carried beside ``verdict`` because a pass over an incremental
    window is a statement about the rows examined, not about the dataset.
    """
    return {**record.to_dict(), "claim": record.claim, "erased": record.is_erased}


def run_view(run: Any) -> dict[str, Any]:
    return {
        "id": str(run.id),
        "triggered_by": run.triggered_by,
        "actor_id": run.actor_id,
        "engine": run.engine,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "status": run.status,
        "record_count": run.record_count,
        "detail": run.detail,
    }


def anchor_view(anchor: Any) -> dict[str, Any]:
    """One anchoring attempt; also the shape of a receipt in ``anchors.json``."""
    return {
        "sequence": anchor.sequence,
        "digest": anchor.digest,
        "kind": anchor.kind,
        "authority": anchor.authority,
        "status": anchor.status,
        "requested_at": anchor.requested_at,
        "witnessed_at": anchor.witnessed_at,
        "token": anchor.token,
        "detail": anchor.detail,
    }


async def observation(uow: Any, tenant_id: str) -> dict[str, Any]:
    """What, if anything, has been observed for this tenant.

    Three states, not two. ``no_runs`` means nothing has been examined;
    ``observed`` means it has; and a run that started and never reported is
    reported alongside either, because its controls have no verdict and every
    number built on "the latest evidence" is silently missing them.
    """
    records = await uow.evidence.count_for(tenant_id)
    unfinished = await uow.evidence_runs.unfinished(tenant_id)
    return {
        "state": "observed" if records else "no_runs",
        "records": records,
        "declared_datasets": await uow.datasets.count_current(tenant_id),
        "unfinished_runs": len(unfinished),
        "reason": (
            "No control has executed against this estate. Nothing on this page "
            "is a statement about data quality — it is a statement that nothing "
            "has been examined yet."
        )
        if not records
        else "",
    }


async def require(uow: Any, tenant_id: str, sequence: int) -> EvidenceRecord:
    """The record at *sequence* in this estate's chain, or a not-found."""
    record: EvidenceRecord | None = await uow.evidence.at(tenant_id, sequence)
    if record is None:
        raise NotFoundError(
            f"there is no evidence record at sequence {sequence}",
            remedy="List the chain (GET /evidence) to see which positions exist.",
            context={"sequence": sequence},
        )
    return record


async def replay_compare(
    uow: Any, tenant_id: str, original: int, replayed: int | None = None
) -> dict[str, Any]:
    """Why two records of the same control differ, or that they do not.

    ``replayed`` defaults to the newest record of the original's control, which
    is the everyday question: has this control's answer moved since then, and
    if so is it the data, the control, the engine, or nothing we can name.
    """
    first = await require(uow, tenant_id, original)
    if replayed is None:
        key = first.control_id
        newer = await uow.evidence.search(tenant_id, control_id=key, limit=1) if key else []
        if not newer or newer[0].sequence == first.sequence:
            raise ValidationError(
                f"there is no later record of this control to compare sequence {original} with",
                remedy="Run the control again, or name the record to compare with (replayed=).",
                context={"sequence": original, "control": key},
            )
        second = newer[0]
    else:
        second = await require(uow, tenant_id, replayed)
    return compare(first, second).to_dict()


async def anchor_now(uow: Any, tenant_id: str, config: Any) -> Any:
    """Anchor the chain head with the configured witness; None when the chain is empty."""
    from prama.evidence.anchor import anchor_from, anchor_head

    tenant = await uow.tenants.get(tenant_id)
    anchor = anchor_from(config, residency=getattr(tenant, "residency", None))
    if anchor is None:
        raise ValidationError(
            "evidence anchoring is off",
            remedy="Set evidence.anchor.kind to rfc3161 and evidence.anchor.url.",
        )
    return await anchor_head(uow, tenant_id, anchor)


async def export_bundle(uow: Any, tenant_id: str) -> tuple[Bundle, list[dict[str, Any]]]:
    """The whole chain as a bundle, and the anchor receipts that witness it.

    Refused when the stored chain does not verify. The bundle is built from the
    records' content, whose hashes are recomputed on the way out, so exporting a
    tampered chain would hand the auditor a bundle that verifies clean — the
    tampering laundered by the export. Better that the export fail and say why.
    """
    verification = await uow.evidence.verify(tenant_id)
    if not verification.is_intact:
        raise ConflictError(
            "the evidence chain does not verify, so it will not be exported",
            remedy=(
                "Investigate the breaches first (GET /evidence/verify, or the Evidence "
                "screen). An export would recompute the hashes and hide them."
            ),
            context={"breaches": len(verification.breaches)},
        )
    records = await uow.evidence.chain(tenant_id, limit=10_000_000)
    if not records:
        raise NotFoundError(
            "there is no evidence to export",
            code="EVIDENCE.EMPTY",
            remedy="Run some controls first: prama control run.",
        )
    bundle = Archivist().bundle(records, tenant_id=tenant_id)
    anchors = await uow.anchors.for_tenant(
        tenant_id, first=records[0].sequence, last=records[-1].sequence
    )
    return bundle, [anchor_view(a) for a in anchors if a.status == "anchored"]


def bundle_files(bundle: Bundle, receipts: list[dict[str, Any]]) -> dict[str, str]:
    """What an exported bundle directory holds, by file name."""
    return {**bundle.files(), "anchors.json": json.dumps(receipts, indent=2)}


def bundle_zip(files: dict[str, str]) -> bytes:
    """The bundle as one zip, for a download; unzipped, it is the CLI's directory."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            archive.writestr(name, content)
    return buffer.getvalue()


__all__ = [
    "anchor_now",
    "anchor_view",
    "bundle_files",
    "bundle_zip",
    "export_bundle",
    "observation",
    "record_view",
    "replay_compare",
    "require",
    "run_view",
]
