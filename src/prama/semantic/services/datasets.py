"""Declaring, amending and retiring datasets and their attributes.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from prama.core.errors import ConflictError, NotFoundError, ValidationError
from prama.db.temporal import Provenance
from prama.semantic.services.base import SemanticService, slugify
from prama.semantic.values import Grain, Rhythm


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
        current = await self._uow.datasets.require_current(dataset_id, tenant_id=tenant_id)
        self._policy.check(
            criticality=changes.get("criticality", current.criticality),
            authored_by=authored_by,
            approved_by=approved_by,
            what="dataset amendment",
        )
        version = await self._uow.datasets.amend(
            dataset_id,
            tenant_id=tenant_id,
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
            tenant_id=tenant_id,
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
        if await self._uow.datasets.current(dataset_id, tenant_id=tenant_id) is None:
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
