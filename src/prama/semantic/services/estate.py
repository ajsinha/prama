"""Questions about the estate as a whole.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama.db.session import UnitOfWork
from prama.semantic.conflict import ConflictDetector, SemanticConflict
from prama.semantic.maturity import EstateFacts, MaturityAssessor, MaturityScore
from prama.semantic.policy import ApprovalPolicy
from prama.semantic.services.base import SemanticService


class EstateService(SemanticService):
    """Questions about the estate as a whole."""

    def __init__(
        self,
        uow: UnitOfWork,
        *,
        policy: ApprovalPolicy | None = None,
        assessor: MaturityAssessor | None = None,
        detector: ConflictDetector | None = None,
    ) -> None:
        super().__init__(uow, policy=policy)
        self._assessor = assessor or MaturityAssessor()
        self._detector = detector or ConflictDetector()

    async def gather_facts(self, tenant_id: str, *, domain_id: str | None = None) -> EstateFacts:
        """Count what has and has not been declared."""
        datasets = (
            await self._uow.datasets.in_domain(tenant_id, domain_id)
            if domain_id
            else await self._uow.datasets.list_current(tenant_id, limit=10_000)
        )
        dataset_ids = {d.dataset_id for d in datasets}

        attributes: list[Any] = []
        for dataset in datasets:
            attributes.extend(
                await self._uow.attributes.for_dataset(dataset.dataset_id, tenant_id=tenant_id)
            )

        relationships = [
            r
            for r in await self._uow.relationships.confirmed(tenant_id)
            if not dataset_ids or r.from_dataset_id in dataset_ids or r.to_dataset_id in dataset_ids
        ]
        journeys = await self._uow.journeys.list_current(tenant_id, limit=10_000)
        journey_datasets = {d for j in journeys for d in j.dataset_ids} & dataset_ids

        tier_one = [d for d in datasets if d.criticality == 1]
        return EstateFacts(
            datasets=len(datasets),
            datasets_owned=sum(1 for d in datasets if d.owner_id),
            datasets_with_grain=sum(1 for d in datasets if d.has_grain),
            datasets_with_rhythm=sum(1 for d in datasets if d.has_rhythm),
            datasets_bound=sum(1 for d in datasets if d.is_bound),
            attributes=len(attributes),
            attributes_defined=sum(1 for a in attributes if (a.definition or "").strip()),
            attributes_mapped_to_concepts=sum(1 for a in attributes if a.concept_property_id),
            critical_data_elements=sum(1 for a in attributes if a.is_cde),
            tier_one_datasets=len(tier_one),
            tier_one_datasets_with_grain=sum(1 for d in tier_one if d.has_grain),
            relationships_confirmed=len(relationships),
            journeys=len(journeys),
            journey_datasets=len(journey_datasets),
        )

    async def maturity(
        self, tenant_id: str, *, domain_id: str | None = None, scope: str = "estate"
    ) -> MaturityScore:
        return self._assessor.assess(scope, await self.gather_facts(tenant_id, domain_id=domain_id))

    async def conflicts(self, tenant_id: str) -> list[SemanticConflict]:
        """Every disagreement between attributes claiming one canonical meaning."""
        found: list[SemanticConflict] = []
        for concept in await self._uow.concepts.list_current(tenant_id, limit=10_000):
            for prop in await self._uow.concept_properties.for_concept(
                concept.concept_id, tenant_id=tenant_id
            ):
                mapped = await self._uow.attributes.mapped_to_property(
                    prop.property_id, tenant_id=tenant_id
                )
                found.extend(
                    self._detector.detect(prop.property_id, f"{concept.name}.{prop.name}", mapped)
                )
        return found

    async def coverage_gaps(self, tenant_id: str) -> dict[str, list[str]]:
        """The honest list of what is declared but unreachable, or unowned."""
        datasets = await self._uow.datasets.list_current(tenant_id, limit=10_000)
        return {
            "unbound": [d.name for d in datasets if not d.is_bound],
            "unowned": [d.name for d in datasets if not d.owner_id],
            "no_grain": [d.name for d in datasets if not d.has_grain],
            "no_rhythm": [d.name for d in datasets if not d.has_rhythm],
            "tier_one_without_grain": [
                d.name for d in datasets if d.criticality == 1 and not d.has_grain
            ],
            "drifted_bindings": [b.dataset_id for b in await self._uow.bindings.drifted(tenant_id)],
        }
