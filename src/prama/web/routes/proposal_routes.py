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

from prama.core.clock import utc_now
from prama.core.errors import PramaError
from prama.derive import ControlGenerator
from prama.derive.persisted import dataset_declaration_of
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
        generator = ControlGenerator()
        versions = await uow.datasets.list_current(caller.tenant_id, limit=5000)
        if dataset_id:
            versions = [v for v in versions if v.dataset_id == dataset_id]

        proposals: list[dict[str, Any]] = []
        unsatisfiable: list[dict[str, Any]] = []
        deferred: list[dict[str, Any]] = []
        accepted_already = 0
        rejected_already = 0
        for version in versions:
            attributes = await uow.attributes.for_dataset(
                version.dataset_id, tenant_id=caller.tenant_id
            )
            declaration = dataset_declaration_of(version, attributes)
            try:
                generation = generator.generate(declaration)
            except PramaError as exc:
                # One bad declaration must not empty the queue for the estate.
                unsatisfiable.append(
                    {
                        "dataset": version.name,
                        "dataset_id": version.dataset_id,
                        "rule": "generation",
                        "declared": version.slug,
                        "reason": str(exc),
                    }
                )
                continue

            for control in generation.controls:
                # Two reasons a proposal is not offered, and they are different
                # answers. Already accepted: it is in the estate, and showing
                # it again would invite somebody to accept it twice. Already
                # rejected: a person said no to this exact text, and asking
                # nightly is the fastest way to lose their attention.
                if await uow.rejections.was_rejected(
                    caller.tenant_id, control.identity, control.content_hash
                ):
                    rejected_already += 1
                    continue
                stored = await uow.controls.by_identity(caller.tenant_id, control.identity)
                if stored is not None and stored.content_hash == control.content_hash:
                    accepted_already += 1
                    continue
                proposals.append(
                    {
                        "dataset": version.name,
                        "dataset_id": version.dataset_id,
                        "identity": control.identity,
                        "rule": control.rule,
                        "sentence": control.describe(),
                        "pql": control.content,
                        "content_hash": control.content_hash,
                        "criticality": version.criticality,
                        # A proposal that changes an existing control is a
                        # different decision from one that adds a new control,
                        # and a queue that renders them identically gets the
                        # first waved through.
                        "amends": stored is not None,
                    }
                )
            for item in generation.unsatisfiable:
                unsatisfiable.append(
                    {
                        "dataset": version.name,
                        "dataset_id": version.dataset_id,
                        "rule": item.rule,
                        "declared": item.declared,
                        "reason": item.reason,
                    }
                )
            for postponed in generation.deferred:
                deferred.append(
                    {
                        "dataset": version.name,
                        "dataset_id": version.dataset_id,
                        "rule": getattr(postponed, "rule", ""),
                        "reason": getattr(postponed, "reason", ""),
                    }
                )
        # Proposals derived from lineage: controls carried downstream, and keys
        # checked against where they were copied from. Held while the edge
        # they rest on is only inferred.
        import hashlib

        from prama.derive.lineage_controls import propose as from_lineage

        for mined in from_lineage(
            await uow.lineage.edges(caller.tenant_id), await uow.controls.live(caller.tenant_id)
        ):
            if dataset_id:
                continue  # a per-dataset view lists what that dataset's declaration implies
            content_hash = hashlib.sha256(mined.pql.encode("utf-8")).hexdigest()
            if await uow.rejections.was_rejected(caller.tenant_id, mined.identity, content_hash):
                rejected_already += 1
                continue
            if await uow.controls.by_identity(caller.tenant_id, mined.identity) is not None:
                accepted_already += 1
                continue
            if mined.deferred_because:
                deferred.append(
                    {
                        "dataset": mined.dataset,
                        "dataset_id": "",
                        "rule": mined.rule,
                        "reason": mined.deferred_because,
                    }
                )
                continue
            proposals.append(
                {
                    "dataset": mined.dataset,
                    "dataset_id": "",
                    "identity": mined.identity,
                    "rule": mined.rule,
                    "sentence": mined.sentence,
                    "pql": mined.pql,
                    "content_hash": content_hash,
                    "criticality": 3,
                    "amends": False,
                }
            )
        # Tier 1 first, then by rule so a systematically bad rule is visible as
        # a block rather than scattered through the list.
        proposals.sort(key=lambda p: (p["criticality"], p["rule"], p["dataset"]))
        return {
            "proposals": proposals,
            "unsatisfiable": unsatisfiable,
            "deferred": deferred,
            # Counted and shown. An empty queue after a generator run means
            # either "everything is already decided" or "nothing was
            # generated", and those are opposite facts.
            "accepted_already": accepted_already,
            "rejected_already": rejected_already,
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
            control, _ = await uow.controls.declare(
                tenant_id=caller.tenant_id,
                identity=identity,
                pql=pql,
                # Lineage-derived proposals are mined from the estate; the rule
                # (lineage_propagated, lineage_referential) says which way.
                origin="mining" if rule.startswith("lineage_") else "declaration",
                rule=rule,
                source_ref=dataset_id,
                status="proposed",
                authored_by=caller.principal_id,
                reason="accepted from the proposal queue",
            )
            await uow.controls.activate(
                str(control.id),
                tenant_id=caller.tenant_id,
                approved_by=caller.principal_id or "console",
                reason="accepted from the proposal queue",
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
        await uow.rejections.record(
            tenant_id=caller.tenant_id,
            identity=identity,
            content_hash=content_hash,
            reason=reason,
            note=note,
            rejected_by=caller.principal_id,
            rejected_at=utc_now().isoformat(),
        )
        return redirect_to(
            request,
            "proposal_queue",
            flash_message="Rejected, and recorded so it is not proposed again.",
            flash_category="info",
        )
