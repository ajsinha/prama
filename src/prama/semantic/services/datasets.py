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

#: Fields only the approval step sets. Accepted in ``changes`` they would let an
#: amendment or a correction declare itself approved, which is the whole of what
#: maker-checker exists to prevent.
PROTECTED = frozenset({"lifecycle_state", "approved_by", "approved_at", "authored_by"})


def refuse_protected(changes: dict[str, Any]) -> None:
    named = sorted(PROTECTED & set(changes))
    if named:
        raise ValidationError(
            f"{', '.join(named)} cannot be changed directly",
            remedy=(
                "A held declaration takes effect when somebody else approves it "
                "(POST /datasets/{id}/approve); authorship is recorded, not edited."
            ),
            context={"fields": ",".join(named)},
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
        business_context: str = "",
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
            business_context=business_context,
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
        refuse_protected(changes)
        current = await self._uow.datasets.require_current(dataset_id, tenant_id=tenant_id)
        self._policy.check(
            criticality=changes.get("criticality", current.criticality),
            authored_by=authored_by,
            approved_by=approved_by,
            what="dataset amendment",
        )
        if self._policy.held(changes.get("criticality", current.criticality), approved_by):
            # Recorded, and held until somebody approves it (`approve`).
            changes["lifecycle_state"] = "proposed"
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

    async def approve(
        self, *, tenant_id: str, dataset_id: str, approved_by: str, reason: str = ""
    ) -> Any:
        """Approve a held declaration or amendment: it takes effect.

        The approval is a correction, not an amendment: what the declaration
        says, and when it is true of the world, do not change; what is now
        known is that somebody signed it off. The author is kept as the author,
        so the version says both who wrote it and who agreed, and a Tier-1
        author cannot be their own approver.
        """
        from prama.core.clock import utc_now

        current = await self._uow.datasets.require_current(dataset_id, tenant_id=tenant_id)
        if current.lifecycle_state != "proposed":
            raise ConflictError(
                f"{current.name} is {current.lifecycle_state}, not awaiting approval",
                remedy="Only a declaration or amendment that is held (proposed) is approved.",
                context={"dataset_id": dataset_id, "state": current.lifecycle_state},
            )
        self._policy.check_approver(
            criticality=current.criticality,
            authored_by=current.authored_by,
            approver=approved_by,
            what="dataset declaration",
        )
        version = await self._uow.datasets.correct(
            dataset_id,
            tenant_id=tenant_id,
            provenance=Provenance(
                authored_by=current.authored_by,
                approved_by=approved_by,
                approved_at=utc_now(),
                reason=reason or "approved",
            ),
            lifecycle_state="active",
        )
        self._audit(
            tenant_id=tenant_id,
            action="dataset.approved",
            object_kind="dataset",
            object_id=dataset_id,
            actor_id=approved_by,
            detail={"author": current.authored_by, "criticality": current.criticality},
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
        refuse_protected(changes)
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

    async def amend_attribute(
        self,
        *,
        tenant_id: str,
        attribute_id: str,
        reason: str,
        authored_by: str | None = None,
        effective_from: datetime | None = None,
        **changes: Any,
    ) -> Any:
        """An attribute's meaning changed: its definition, business context, CDE mark."""
        if not reason.strip():
            raise ValidationError(
                "an amendment must say why",
                remedy="State what changed. An unexplained change to a declaration is a finding.",
            )
        version = await self._uow.attributes.amend(
            attribute_id,
            tenant_id=tenant_id,
            effective_from=effective_from,
            provenance=Provenance(authored_by=authored_by, reason=reason),
            **changes,
        )
        self._audit(
            tenant_id=tenant_id,
            action="attribute.amended",
            object_kind="attribute",
            object_id=attribute_id,
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
        existing = await self._uow.attributes.for_dataset(dataset_id, tenant_id=tenant_id)
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
