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

from typing import Any

from fastapi import Request

from prama.core.errors import PramaError
from prama.derive import ControlGenerator
from prama.derive.persisted import dataset_declaration_of
from prama.web.deps import Caller, Uow
from prama.web.rendering import render
from prama.web.routes.base import UiRoutes


class ProposalRoutes(UiRoutes):
    """What the declarations imply, ready to be accepted."""

    def register(self) -> None:
        self.page("/proposals", self.proposal_queue, name="proposal_queue")
        self.page("/proposals/{dataset_id}", self.proposals_for, name="proposals_for")

    async def _generate(self, caller: Caller, uow: Uow, dataset_id: str | None = None) -> Any:
        generator = ControlGenerator()
        versions = await uow.datasets.list_current(caller.tenant_id, limit=5000)
        if dataset_id:
            versions = [v for v in versions if v.dataset_id == dataset_id]

        proposals: list[dict[str, Any]] = []
        unsatisfiable: list[dict[str, Any]] = []
        deferred: list[dict[str, Any]] = []
        for version in versions:
            attributes = await uow.attributes.for_dataset(version.dataset_id)
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
        # Tier 1 first, then by rule so a systematically bad rule is visible as
        # a block rather than scattered through the list.
        proposals.sort(key=lambda p: (p["criticality"], p["rule"], p["dataset"]))
        return proposals, unsatisfiable, deferred

    async def proposal_queue(self, request: Request, caller: Caller, uow: Uow) -> Any:
        proposals, unsatisfiable, deferred = await self._generate(caller, uow)
        return render(
            request,
            "proposals/queue.html",
            proposals=proposals,
            unsatisfiable=unsatisfiable,
            deferred=deferred,
            dataset=None,
        )

    async def proposals_for(
        self, request: Request, dataset_id: str, caller: Caller, uow: Uow
    ) -> Any:
        version = await uow.datasets.require_current(dataset_id)
        proposals, unsatisfiable, deferred = await self._generate(caller, uow, dataset_id)
        return render(
            request,
            "proposals/queue.html",
            proposals=proposals,
            unsatisfiable=unsatisfiable,
            deferred=deferred,
            dataset={"id": dataset_id, "name": version.name},
        )
