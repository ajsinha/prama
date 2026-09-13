"""Signing an attestation, and reading the ones already signed.

The screen deliberately does not let the attester type the numbers. Coverage,
exceptions and the evidence root are derived from the ledger and shown; the
only things the person supplies are their sentence, their name, and a word
about each exception.

An attestation whose figures were typed is a statement about what the attester
believed. One whose figures were derived is a statement about what happened,
which is what a regulator is asking for.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Form, Request
from fastapi.responses import HTMLResponse

from prama.core.clock import utc_now
from prama.core.errors import PramaError
from prama.report import attest
from prama.report.render import Coverage as PackCoverage
from prama.report.render import Provenance, attestation_pack
from prama.web.deps import Caller, Uow
from prama.web.rendering import flash_error_and_log, redirect_to, render
from prama.web.routes.base import UiRoutes


class AttestationRoutes(UiRoutes):
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
        """The sealing key.

        The session secret, which a deployment must set and which is refused
        empty. A dedicated signing key belongs to Wave 10's key management; the
        distinction matters and is stated on the screen rather than implied by
        the word "signed".
        """
        secret: str = request.app.state.config.require_secret("security.session_secret")
        return secret.encode()

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
        now = utc_now()
        period_start = start or now.replace(day=1).date().isoformat()
        period_end = end or now.date().isoformat()
        draft = await attest.build(
            uow,
            caller.tenant_id,
            scope=scope,
            period_start=period_start,
            period_end=period_end,
            attester_id=caller.principal_id or "",
            attester_name="",
            statement="",
            signed_at="",
        )
        return render(
            request,
            "attestations/form.html",
            draft=draft,
            scope=scope,
            period_start=period_start,
            period_end=period_end,
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
        """Derive it again, seal it, and record it.

        Rebuilt from the ledger rather than from the form, so what is signed is
        what the evidence says at the moment of signing — not what a page
        rendered some minutes earlier and a browser posted back.
        """
        form = dict(await request.form())
        dispositions = {
            key[len("disposition:") :]: str(value)
            for key, value in form.items()
            if key.startswith("disposition:")
        }
        try:
            if not attester_name.strip():
                raise PramaError(
                    "an attestation needs the name of the person signing it",
                    remedy=(
                        "A control attested by 'the team' is a control nobody "
                        "attested. Give the name of the person accountable."
                    ),
                )
            if not statement.strip():
                raise PramaError(
                    "an attestation needs a statement",
                    remedy=(
                        "Say what you are attesting to, in your own words. It is "
                        "printed on the artefact and quoted back at review."
                    ),
                )
            attestation = await attest.build(
                uow,
                caller.tenant_id,
                scope=scope,
                period_start=period_start,
                period_end=period_end,
                attester_id=caller.principal_id or "console",
                attester_name=attester_name.strip(),
                statement=statement.strip(),
                signed_at=utc_now().isoformat(),
                dispositions=dispositions,
            )
            import dataclasses

            if supersedes:
                # Checked against the caller's own estate before it is
                # recorded. The id arrives in a form field, and this used to be
                # applied verbatim: signing from one estate while naming
                # another estate's attestation id succeeded, and the record
                # then claimed to supersede an attestation its signer had no
                # standing over (QA finding UI-122). `in_tenant` raises a
                # not-found for an id outside the estate, which is the right
                # answer twice over — it refuses, and it does not confirm that
                # the id exists somewhere else.
                await uow.attestations.in_tenant(supersedes, caller.tenant_id)
                attestation = dataclasses.replace(
                    attestation, supersedes=supersedes, supersedes_because=supersedes_because
                )
            row = await uow.attestations.sign(
                attestation,
                seal=attestation.seal(self._key(request)),
                supersedes=supersedes or None,
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
        row = await uow.attestations.in_tenant(attestation_id, caller.tenant_id)
        attestation = await uow.attestations.value(attestation_id)
        intact, sealed = await uow.attestations.verify(attestation_id, self._key(request))
        artefact = attestation_pack(
            provenance=Provenance(
                tenant_id=caller.tenant_id, generated_by=caller.principal_id or ""
            ),
            attestation=attestation,
            seal=row.seal,
            intact=intact,
            sealed=sealed,
            coverage=PackCoverage(
                included=attestation.coverage.controls_run,
                excluded=attestation.coverage.controls_in_scope - attestation.coverage.controls_run,
                exclusion_reason="in scope and produced no verdict in the period",
            ),
        )
        return HTMLResponse(artefact.html)
