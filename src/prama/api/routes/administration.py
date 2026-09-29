"""The installation's configuration and the estate's audit log, for an administrator.

``GET /config`` is ``prama config show`` over HTTP: the effective merged
configuration as dotted keys, **always redacted**. The CLI's ``--raw`` is not
offered here and never will be — a secret that can be fetched over the network
by anybody holding an admin key is one more place it leaks from, and the
operator who genuinely needs it is on the host already.

``GET /audit`` reads the append-only audit log: who created, disabled or
re-roled a person, who minted or revoked a key.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from prama.api.deps import Administrator, Uow

router = APIRouter(tags=["administration"])


@router.get("/config")
async def config(
    request: Request, caller: Administrator, provenance: bool = False
) -> dict[str, Any]:
    """The effective configuration, secrets masked as ``***``.

    With *provenance*, each key also names the layer that set it.
    """
    configuration = request.app.state.config
    flat = configuration.flatten(redact=True)
    out: dict[str, Any] = {"values": flat}
    if provenance:
        out["provenance"] = {
            key: configuration.provenance(key) or "built-in defaults" for key in flat
        }
    return out


@router.get("/audit")
async def audit(
    uow: Uow,
    caller: Administrator,
    object_kind: str = "",
    object_id: str = "",
    limit: int = Query(100, ge=1, le=1000),
) -> list[dict[str, Any]]:
    """Recent audit events, newest first; or those for one object."""
    if object_kind and object_id:
        rows = await uow.audit.for_object(caller.tenant_id, object_kind, object_id, limit=limit)
    else:
        rows = await uow.audit.recent(caller.tenant_id, limit=limit)
        if object_kind:
            rows = [r for r in rows if r.object_kind == object_kind]
    return [
        {
            "id": str(r.id),
            "occurred_at": r.occurred_at.isoformat() if r.occurred_at else None,
            "actor_id": r.actor_id,
            "actor_kind": r.actor_kind,
            "action": r.action,
            "object_kind": r.object_kind,
            "object_id": r.object_id,
            "outcome": r.outcome,
            "correlation_id": r.correlation_id,
            "detail": dict(r.detail_json or {}),
        }
        for r in rows
    ]
