"""Attestations, for programs: the register, a draft, signing, and the pack.

As on the console, the caller cannot supply the numbers. Coverage, exceptions
and the evidence root are derived from the ledger at the moment of signing; the
signer supplies their name, their statement and a word about each exception.
The signer's identity is the key's principal, never a field in the request.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

from prama.api.deps import AttestationReader, AttestationSigner, Uow
from prama.core.errors import ValidationError
from prama.report import attest, packs

router = APIRouter(prefix="/attestations", tags=["attestations"])


class SignIn(BaseModel):
    attester_name: str
    statement: str
    scope: str = "the estate"
    period_start: str
    period_end: str
    #: The signer's word about each exception, by control id.
    dispositions: dict[str, str] = Field(default_factory=dict)
    supersedes: str = ""
    supersedes_because: str = ""


async def _signed(uow: Any, row: Any, key: bytes) -> dict[str, Any]:
    intact, sealed = await uow.attestations.verify(str(row.id), key)
    value = await uow.attestations.value(str(row.id))
    return {
        **attest.row_view(row),
        "summary": value.describe(),
        "is_qualified": value.is_qualified,
        "intact": intact,
        "sealed": sealed,
    }


@router.get("")
async def register(caller: AttestationReader, uow: Uow) -> list[dict[str, Any]]:
    """Attestations nothing has replaced, most recent period first."""
    return [attest.row_view(r) for r in await uow.attestations.current(caller.tenant_id)]


@router.get("/history")
async def history(scope: str, caller: AttestationReader, uow: Uow) -> list[dict[str, Any]]:
    """Everything ever signed for one scope, superseded ones included, oldest first."""
    return [attest.row_view(r) for r in await uow.attestations.history(caller.tenant_id, scope)]


@router.get("/draft")
async def draft(
    caller: AttestationReader,
    uow: Uow,
    scope: str = "the estate",
    start: str = "",
    end: str = "",
) -> dict[str, Any]:
    """What would be attested to for a scope and period, before anybody signs it.

    The period defaults to this month so far.
    """
    value = await attest.draft(
        uow,
        caller.tenant_id,
        attester_id=caller.principal_id or "",
        scope=scope,
        start=start,
        end=end,
    )
    return value.to_dict()


@router.post("", status_code=201)
async def sign(
    body: SignIn, request: Request, caller: AttestationSigner, uow: Uow
) -> dict[str, Any]:
    """Derive the attestation from the ledger now, seal it, and record it."""
    if not caller.principal_id:
        raise ValidationError(
            "an attestation is signed by a person",
            remedy="Use a key issued to the person signing.",
        )
    key = attest.sealing_key(request.app.state.config)
    row = await attest.sign(
        uow,
        caller.tenant_id,
        key=key,
        attester_id=caller.principal_id,
        attester_name=body.attester_name,
        statement=body.statement,
        scope=body.scope,
        period_start=body.period_start,
        period_end=body.period_end,
        dispositions=body.dispositions,
        supersedes=body.supersedes,
        supersedes_because=body.supersedes_because,
    )
    return await _signed(uow, row, key)


@router.get("/{attestation_id}")
async def get(
    attestation_id: str, request: Request, caller: AttestationReader, uow: Uow
) -> dict[str, Any]:
    """One attestation, and whether its content and seal still verify."""
    row = await uow.attestations.in_tenant(attestation_id, caller.tenant_id)
    return await _signed(uow, row, attest.sealing_key(request.app.state.config))


@router.get("/{attestation_id}/pack")
async def pack(
    attestation_id: str, request: Request, caller: AttestationReader, uow: Uow
) -> Response:
    """The attestation pack: the HTML document an auditor is handed."""
    artefact = await packs.attestation(
        uow,
        caller.tenant_id,
        attestation_id,
        attest.sealing_key(request.app.state.config),
        generated_by=caller.principal_id or "",
    )
    return Response(
        content=artefact.html,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{artefact.filename}"'},
    )
