"""Signing an attestation, and reading the ones already signed.

The screen deliberately does not let the attester type the numbers. Coverage,
exceptions and the evidence root are derived from the ledger and shown; the
only things the person supplies are their sentence, their name, and a word
about each exception.

An attestation whose figures were typed is a statement about what the attester
believed. One whose figures were derived is a statement about what happened,
which is what a regulator is asking for.

The drafting, sealing and pack assembly live in `prama.report.attest` and
`prama.report.packs`, which ``/api/v1/attestations`` uses too.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Form, Request
from fastapi.responses import HTMLResponse

from prama.core.errors import PramaError
from prama.report import attest, packs
from prama.web.deps import Caller, Uow
from prama.web.rendering import flash_error_and_log, redirect_to, render
from prama.web.routes.base import UiRoutes


class AttestationRoutes(UiRoutes):
    SUBJECT = "attestation"
    WRITE_SCOPE = "attestation:sign"
    """The sign-off screen, the register, and the pack."""

    def register(self) -> None:
        self.page("/attestations", self.attestation_list, name="attestation_list")
        self.page("/attestations/new", self.attestation_form, name="attestation_form")
        self.page(
            "/attestations/new", self.attestation_sign, name="attestation_sign", methods=["POST"]
        )
        self.page(
            "/attestations/{attestation_id}", self.attestation_detail, name="attestation_detail"
        )
        self.page(
            "/attestations/{attestation_id}/pack",
            self.attestation_pack,
            name="attestation_pack",
        )

    def _key(self, request: Request) -> bytes:
        return attest.sealing_key(request.app.state.config)

    async def attestation_list(self, request: Request, caller: Caller, uow: Uow) -> Any:
        return render(
            request,
            "attestations/list.html",
            attestations=await uow.attestations.current(caller.tenant_id),
        )

    async def attestation_form(
        self,
        request: Request,
        caller: Caller,
        uow: Uow,
        scope: str = "the estate",
        start: str = "",
        end: str = "",
    ) -> Any:
        """Show what would be attested to, before anybody signs it."""
        draft = await attest.draft(
            uow,
            caller.tenant_id,
            attester_id=caller.principal_id or "",
            scope=scope,
            start=start,
            end=end,
        )
        return render(
            request,
            "attestations/form.html",
            draft=draft,
            scope=scope,
            period_start=draft.period_start,
            period_end=draft.period_end,
        )

    async def attestation_sign(
        self,
        request: Request,
        caller: Caller,
        uow: Uow,
        attester_name: Annotated[str, Form()],
        statement: Annotated[str, Form()],
        scope: Annotated[str, Form()],
        period_start: Annotated[str, Form()],
        period_end: Annotated[str, Form()],
        supersedes: Annotated[str, Form()] = "",
        supersedes_because: Annotated[str, Form()] = "",
    ) -> Any:
        """Derive it again, seal it, and record it (`prama.report.attest.sign`)."""
        form = dict(await request.form())
        dispositions = {
            key[len("disposition:") :]: str(value)
            for key, value in form.items()
            if key.startswith("disposition:")
        }
        try:
            row = await attest.sign(
                uow,
                caller.tenant_id,
                key=self._key(request),
                attester_id=caller.principal_id or "console",
                attester_name=attester_name,
                statement=statement,
                scope=scope,
                period_start=period_start,
                period_end=period_end,
                dispositions=dispositions,
                supersedes=supersedes,
                supersedes_because=supersedes_because,
            )
        except PramaError as exc:
            flash_error_and_log(request, "That attestation could not be signed", exc)
            return redirect_to(request, "attestation_form", scope=scope)
        return redirect_to(
            request,
            "attestation_detail",
            attestation_id=str(row.id),
            flash_message="Signed. It cannot be edited; a correction supersedes it.",
        )

    async def attestation_detail(
        self, request: Request, attestation_id: str, caller: Caller, uow: Uow
    ) -> Any:
        row = await uow.attestations.in_tenant(attestation_id, caller.tenant_id)
        intact, sealed = await uow.attestations.verify(attestation_id, self._key(request))
        return render(
            request,
            "attestations/detail.html",
            row=row,
            attestation=await uow.attestations.value(attestation_id),
            intact=intact,
            sealed=sealed,
        )

    async def attestation_pack(
        self, request: Request, attestation_id: str, caller: Caller, uow: Uow
    ) -> HTMLResponse:
        """The artefact that leaves the building."""
        artefact = await packs.attestation(
            uow,
            caller.tenant_id,
            attestation_id,
            self._key(request),
            generated_by=caller.principal_id or "",
        )
        return HTMLResponse(artefact.html)
