"""The proposal queue: what Γ derived, and what it could not.

Two lists, and the second one is the reason this screen is worth building.
Every tool of this kind shows what it generated; almost none shows what it
declined to generate and why. An ``Unsatisfiable`` — "the grain names
``settlement_date``, which this dataset does not have" — is a finding about
the declaration, and burying it makes the generated set look complete when it
is not.

Nothing here adjudicates. Γ is deterministic and versioned; a model may rank
and explain these, and no model output decides whether a control passes
(CON-007, NFR-AI-002).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Form, Request

from prama.controls import proposals
from prama.core.errors import PramaError
from prama.propose.proposal import RejectionReason
from prama.web.deps import Caller, Uow
from prama.web.rendering import flash_error_and_log, redirect_to, render
from prama.web.routes.base import UiRoutes

#: Offered when turning a proposal down. Derived from the enum rather than
#: written out, so a new reason appears in the form the moment it exists — and
#: so the form can never offer one the schema will refuse.
REJECTION_REASONS: list[tuple[str, str]] = [
    (reason.value, reason.value.replace("_", " ")) for reason in RejectionReason
]


class ProposalRoutes(UiRoutes):
    """What the declarations imply, ready to be accepted."""

    def register(self) -> None:
        self.page("/proposals", self.proposal_queue, name="proposal_queue")
        self.page("/proposals/accept", self.accept, name="proposal_accept", methods=["POST"])
        self.page("/proposals/reject", self.reject, name="proposal_reject", methods=["POST"])
        self.page("/proposals/{dataset_id}", self.proposals_for, name="proposals_for")

    async def _generate(self, caller: Caller, uow: Uow, dataset_id: str | None = None) -> Any:
        """The queue (`prama.controls.proposals.queue`), with the form's reasons."""
        return {
            **await proposals.queue(uow, caller.tenant_id, dataset_id),
            "reasons": REJECTION_REASONS,
        }

    async def proposal_queue(self, request: Request, caller: Caller, uow: Uow) -> Any:
        return render(
            request,
            "proposals/queue.html",
            dataset=None,
            **await self._generate(caller, uow),
        )

    async def proposals_for(
        self, request: Request, dataset_id: str, caller: Caller, uow: Uow
    ) -> Any:
        version = await uow.datasets.require_current(dataset_id, tenant_id=caller.tenant_id)
        return render(
            request,
            "proposals/queue.html",
            dataset={"id": dataset_id, "name": version.name},
            **await self._generate(caller, uow, dataset_id),
        )

    async def accept(
        self,
        request: Request,
        caller: Caller,
        uow: Uow,
        identity: Annotated[str, Form()],
        pql: Annotated[str, Form()],
        rule: Annotated[str, Form()] = "",
        dataset_id: Annotated[str, Form()] = "",
    ) -> Any:
        """Accept a proposal: the control enters the estate and begins to run.

        The PQL is re-derived on the way in — parsed, lowered, hashed — so what
        is stored is what was reviewed, and a form field cannot introduce a
        severity the text does not carry.
        """
        try:
            await proposals.accept(
                uow,
                caller.tenant_id,
                identity=identity,
                pql=pql,
                rule=rule,
                dataset_id=dataset_id,
                by=caller.principal_id,
            )
        except PramaError as exc:
            flash_error_and_log(request, "That control could not be accepted", exc)
            return redirect_to(request, "proposal_queue")
        return redirect_to(
            request,
            "control_list",
            flash_message="Accepted. The control is now part of the estate.",
        )

    async def reject(
        self,
        request: Request,
        caller: Caller,
        uow: Uow,
        identity: Annotated[str, Form()],
        content_hash: Annotated[str, Form()],
        reason: Annotated[str, Form()] = "incorrect",
        note: Annotated[str, Form()] = "",
    ) -> Any:
        """Turn a proposal down, and record that it was turned down.

        Recorded rather than dismissed. The reason matters to the learning
        loop — "too noisy" is a threshold problem and "incorrect" is a rule
        that should never have been proposed — and without the record the same
        proposal returns tomorrow night.
        """
        try:
            await proposals.reject(
                uow,
                caller.tenant_id,
                identity=identity,
                content_hash=content_hash,
                reason=reason,
                note=note,
                by=caller.principal_id,
            )
        except PramaError as exc:
            flash_error_and_log(request, "That proposal could not be rejected", exc)
            return redirect_to(request, "proposal_queue")
        return redirect_to(
            request,
            "proposal_queue",
            flash_message="Rejected, and recorded so it is not proposed again.",
            flash_category="info",
        )
