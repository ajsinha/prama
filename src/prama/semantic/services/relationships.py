"""Declaring and confirming relationships between datasets.

The most valuable declarations in the product, and the ones that most need a
human in the loop: a *discovered* relationship stays a proposal, and any control
derived from it stays a proposal too, until someone confirms it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama.core.errors import NotFoundError
from prama.db.temporal import Provenance
from prama.semantic.relationships import RelationshipDeclaration, RelationshipKind
from prama.semantic.services.base import SemanticService


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
