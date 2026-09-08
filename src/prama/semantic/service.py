"""Declaration services — the business-facing operations on the semantic layer.

A service takes a ``UnitOfWork``, never a session, so nothing above ``prama.db``
sees SQLAlchemy. What lives here is the logic that is *about the business*
rather than about storage: uniqueness of a name a person will type, the approval
a criticality tier demands, the audit record a change must leave, and the
validation that refuses a declaration at the point it is written.

Every mutation writes an audit event. That is not diligence, it is the
requirement: a declaration nobody can attribute is a declaration an auditor will
not accept.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any

from prama.core.errors import ConflictError, NotFoundError, ValidationError
from prama.db.session import UnitOfWork
from prama.db.temporal import Provenance
from prama.semantic.conflict import ConflictDetector, SemanticConflict
from prama.semantic.maturity import EstateFacts, MaturityAssessor, MaturityScore
from prama.semantic.policy import ApprovalPolicy
from prama.semantic.relationships import RelationshipDeclaration, RelationshipKind
from prama.semantic.values import Grain, Rhythm

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    """A stable, readable identifier derived from a business name.

    Used for URLs, GitOps filenames and cross-references. Derived rather than
    typed, because asking a business user to invent a slug is asking them to do
    a computer's job.
    """
    normalised = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    slug = _SLUG_STRIP.sub("_", normalised.lower()).strip("_")
    if not slug:
        raise ValidationError(
            f"{value!r} contains no characters usable in an identifier",
            remedy="Give the object a name containing letters or digits.",
            context={"name": value},
        )
    return slug[:128]


class SemanticService:
    """Base: a unit of work, an approval policy, and an audit obligation."""

    def __init__(self, uow: UnitOfWork, *, policy: ApprovalPolicy | None = None) -> None:
        self._uow = uow
        self._policy = policy or ApprovalPolicy()

    def _audit(
        self,
        *,
        tenant_id: str,
        action: str,
        object_kind: str,
        object_id: str,
        actor_id: str | None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self._uow.audit.record(
            tenant_id=tenant_id,
            action=action,
            object_kind=object_kind,
            object_id=object_id,
            actor_id=actor_id,
            detail=detail or {},
        )


class DatasetService(SemanticService):
    """Declaring, amending and retiring datasets."""

    async def declare(
        self,
        *,
        tenant_id: str,
        name: str,
        description: str = "",
        purpose: str = "",
        domain_id: str | None = None,
        owner_id: str | None = None,
        criticality: int = 4,
        shape: str = "unbound",
        grain: Grain | None = None,
        rhythm: Rhythm | None = None,
        temporality: str = "snapshot",
        authoritativeness: str = "unknown",
        sensitivity: str = "internal",
        tags: list[str] | None = None,
        authored_by: str | None = None,
        approved_by: str | None = None,
        reason: str = "",
        valid_from: datetime | None = None,
    ) -> Any:
        """Declare a dataset. It may be unbound: that is a first-class state."""
        slug = slugify(name)
        if await self._uow.datasets.by_slug(tenant_id, slug) is not None:
            raise ConflictError(
                f"a dataset named {name!r} already exists in this tenant",
                remedy="Choose a different name, or amend the existing declaration.",
                context={"slug": slug},
            )
        self._policy.check(
            criticality=criticality,
            authored_by=authored_by,
            approved_by=approved_by,
            what="dataset declaration",
        )
        entity, version = await self._uow.datasets.create(
            tenant_id=tenant_id,
            name=name,
            slug=slug,
            description=description,
            purpose=purpose,
            domain_id=domain_id,
            owner_id=owner_id,
            criticality=criticality,
            shape=shape,
            grain_json=grain.to_dict() if grain else None,
            rhythm_json=rhythm.to_dict() if rhythm else None,
            temporality=temporality,
            authoritativeness=authoritativeness,
            sensitivity=sensitivity,
            tags_json=tags or [],
            lifecycle_state="active" if approved_by else "proposed",
            provenance=Provenance(
                authored_by=authored_by,
                approved_by=approved_by,
                reason=reason or "initial declaration",
            ),
            valid_from=valid_from,
        )
        self._audit(
            tenant_id=tenant_id,
            action="dataset.declared",
            object_kind="dataset",
            object_id=str(entity.id),
            actor_id=authored_by,
            detail={"slug": slug, "criticality": criticality, "shape": shape},
        )
        return entity, version

    async def amend(
        self,
        *,
        tenant_id: str,
        dataset_id: str,
        reason: str,
        authored_by: str | None = None,
        approved_by: str | None = None,
        effective_from: datetime | None = None,
        **changes: Any,
    ) -> Any:
        """The world changed: close one validity period and open the next."""
        if not reason.strip():
            raise ValidationError(
                "an amendment must say why",
                remedy=(
                    "State what changed in the world. An unexplained change to a "
                    "declaration is an audit finding."
                ),
            )
        current = await self._uow.datasets.require_current(dataset_id)
        self._policy.check(
            criticality=changes.get("criticality", current.criticality),
            authored_by=authored_by,
            approved_by=approved_by,
            what="dataset amendment",
        )
        version = await self._uow.datasets.amend(
            dataset_id,
            effective_from=effective_from,
            provenance=Provenance(authored_by=authored_by, approved_by=approved_by, reason=reason),
            **changes,
        )
        self._audit(
            tenant_id=tenant_id,
            action="dataset.amended",
            object_kind="dataset",
            object_id=dataset_id,
            actor_id=authored_by,
            detail={"reason": reason, "fields": sorted(changes)},
        )
        return version

    async def correct(
        self,
        *,
        tenant_id: str,
        dataset_id: str,
        reason: str,
        authored_by: str | None = None,
        **changes: Any,
    ) -> Any:
        """We were wrong: supersede the belief, leave validity untouched."""
        if not reason.strip():
            raise ValidationError(
                "a correction must say what was wrong",
                remedy="State the error being corrected; the record is permanent.",
            )
        version = await self._uow.datasets.correct(
            dataset_id,
            provenance=Provenance(authored_by=authored_by, reason=reason),
            **changes,
        )
        self._audit(
            tenant_id=tenant_id,
            action="dataset.corrected",
            object_kind="dataset",
            object_id=dataset_id,
            actor_id=authored_by,
            detail={"reason": reason, "fields": sorted(changes)},
        )
        return version

    async def declare_attribute(
        self,
        *,
        tenant_id: str,
        dataset_id: str,
        name: str,
        definition: str = "",
        interpretation: str = "",
        semantic_type: str | None = None,
        is_cde: bool = False,
        obligations: list[str] | None = None,
        authored_by: str | None = None,
        **extra: Any,
    ) -> Any:
        """Declare an attribute and what it means."""
        if await self._uow.datasets.current(dataset_id) is None:
            raise NotFoundError(
                f"dataset {dataset_id!r} does not exist",
                remedy="Declare the dataset before declaring its attributes.",
                context={"dataset_id": dataset_id},
            )
        existing = await self._uow.attributes.for_dataset(dataset_id)
        if any(a.name == name for a in existing):
            raise ConflictError(
                f"attribute {name!r} is already declared on this dataset",
                remedy="Amend the existing attribute, or choose a different name.",
                context={"attribute": name},
            )
        entity, version = await self._uow.attributes.create(
            tenant_id=tenant_id,
            identity_fields={"dataset_id": dataset_id},
            name=name,
            ordinal=len(existing),
            definition=definition,
            interpretation=interpretation,
            semantic_type=semantic_type,
            is_cde=is_cde,
            obligations_json=obligations or [],
            provenance=Provenance(authored_by=authored_by, reason="attribute declared"),
            **extra,
        )
        self._audit(
            tenant_id=tenant_id,
            action="attribute.declared",
            object_kind="attribute",
            object_id=str(entity.id),
            actor_id=authored_by,
            detail={"dataset_id": dataset_id, "name": name, "is_cde": is_cde},
        )
        return entity, version


class RelationshipService(SemanticService):
    """Declaring and confirming relationships between datasets.

    The most valuable declarations in the product, and the ones that most need a
    human in the loop: a *discovered* relationship remains a proposal, and any
    control derived from it stays a proposal too, until someone confirms it.
    """

    async def declare(
        self,
        *,
        tenant_id: str,
        declaration: RelationshipDeclaration,
        owner_id: str | None = None,
        criticality: int = 4,
        authored_by: str | None = None,
        approved_by: str | None = None,
        reason: str = "",
        confirmed: bool = True,
    ) -> Any:
        """Declare a relationship a human asserts to be true."""
        for side, dataset_id in (
            ("from", declaration.from_dataset_id),
            ("to", declaration.to_dataset_id),
        ):
            if await self._uow.datasets.current(dataset_id) is None:
                raise NotFoundError(
                    f"the {side} dataset {dataset_id!r} does not exist",
                    remedy="Declare both datasets before relating them.",
                    context={"side": side, "dataset_id": dataset_id},
                )
        self._policy.check(
            criticality=criticality,
            authored_by=authored_by,
            approved_by=approved_by,
            what="relationship declaration",
        )
        entity, version = await self._uow.relationships.create(
            tenant_id=tenant_id,
            kind=declaration.kind.value,
            from_dataset_id=declaration.from_dataset_id,
            to_dataset_id=declaration.to_dataset_id,
            name=declaration.name or declaration.render(),
            description=declaration.description,
            match_keys_json=[k.to_dict() for k in declaration.match_keys],
            compare_json=list(declaration.compare),
            cardinality=declaration.cardinality.value,
            tolerance_json=declaration.tolerance.to_dict() if declaration.tolerance else None,
            offset_json=declaration.offset.to_dict() if declaration.offset else None,
            filter_expression=declaration.filter_expression,
            owner_id=owner_id,
            criticality=criticality,
            status="confirmed" if confirmed else "proposed",
            provenance=Provenance(
                authored_by=authored_by,
                approved_by=approved_by,
                reason=reason or "declared on the estate map",
            ),
        )
        self._audit(
            tenant_id=tenant_id,
            action="relationship.declared",
            object_kind="relationship",
            object_id=str(entity.id),
            actor_id=authored_by,
            detail={
                "kind": declaration.kind.value,
                "generates": list(declaration.generates),
                "statement": declaration.render(),
            },
        )
        return entity, version

    async def propose_discovered(
        self,
        *,
        tenant_id: str,
        declaration: RelationshipDeclaration,
        discovered_by: str,
        confidence: float,
        evidence: dict[str, Any],
    ) -> Any:
        """Record a relationship the system believes exists.

        Never confirmed automatically. The evidence is retained so the steward
        confirming it can see *why* it was suggested — which is the difference
        between a suggestion and a guess.
        """
        entity, version = await self._uow.relationships.create(
            tenant_id=tenant_id,
            kind=declaration.kind.value,
            from_dataset_id=declaration.from_dataset_id,
            to_dataset_id=declaration.to_dataset_id,
            name=declaration.render(),
            match_keys_json=[k.to_dict() for k in declaration.match_keys],
            compare_json=list(declaration.compare),
            tolerance_json=declaration.tolerance.to_dict() if declaration.tolerance else None,
            status="proposed",
            confidence=confidence,
            discovered_by=discovered_by,
            evidence_json=evidence,
            provenance=Provenance(reason=f"discovered by {discovered_by}"),
        )
        return entity, version

    async def confirm(
        self, *, tenant_id: str, relationship_id: str, confirmed_by: str, reason: str = ""
    ) -> Any:
        """A human asserts a proposed relationship is true."""
        current = await self._uow.relationships.require_current(relationship_id)
        if current.status == "confirmed":
            return current
        version = await self._uow.relationships.amend(
            relationship_id,
            status="confirmed",
            provenance=Provenance(
                authored_by=confirmed_by,
                approved_by=confirmed_by,
                reason=reason or "confirmed by steward",
            ),
        )
        self._audit(
            tenant_id=tenant_id,
            action="relationship.confirmed",
            object_kind="relationship",
            object_id=relationship_id,
            actor_id=confirmed_by,
            detail={"kind": current.kind, "was_discovered": current.is_discovered},
        )
        return version

    async def reject(
        self, *, tenant_id: str, relationship_id: str, rejected_by: str, reason: str
    ) -> Any:
        """A human asserts a proposed relationship is not true.

        Recorded rather than deleted: a rejection is a training signal, and
        re-proposing something a steward has already rejected is the fastest way
        to lose their trust.
        """
        version = await self._uow.relationships.amend(
            relationship_id,
            status="rejected",
            provenance=Provenance(authored_by=rejected_by, reason=reason),
        )
        self._audit(
            tenant_id=tenant_id,
            action="relationship.rejected",
            object_kind="relationship",
            object_id=relationship_id,
            actor_id=rejected_by,
            detail={"reason": reason},
        )
        return version


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
            attributes.extend(await self._uow.attributes.for_dataset(dataset.dataset_id))

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
            for prop in await self._uow.concept_properties.for_concept(concept.concept_id):
                mapped = await self._uow.attributes.mapped_to_property(prop.property_id)
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


def relationship_kinds() -> list[dict[str, Any]]:
    """The choices offered on the estate map, in business language."""
    return [
        {
            "kind": kind.value,
            "prompt": kind.prompt,
            "generates": list(kind.generates),
            "needs_match_keys": kind.requires_match_keys,
            "needs_tolerance": kind.requires_tolerance,
            "directional": kind.is_directional,
            "carries_trust": kind.carries_trust,
        }
        for kind in RelationshipKind
    ]
