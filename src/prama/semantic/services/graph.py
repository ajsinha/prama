"""Services for the objects that connect datasets to each other and the world.

Concepts and their properties give the estate a shared vocabulary; journeys give
it business lineage where no scanner can reach; connections and bindings give it
a route to the physical world — and a way to notice when that world moves
beneath a declaration.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama.core.errors import ConflictError, NotFoundError, ValidationError
from prama.db.temporal import Provenance
from prama.semantic.services.base import SemanticService, slugify


class ConceptService(SemanticService):
    """The canonical vocabulary attributes across the estate map onto."""

    async def declare_concept(
        self,
        *,
        tenant_id: str,
        name: str,
        description: str = "",
        domain_id: str | None = None,
        pack_ref: str | None = None,
        authored_by: str | None = None,
    ) -> Any:
        if await self._uow.concepts.by_name(tenant_id, name) is not None:
            raise ConflictError(
                f"a concept named {name!r} already exists",
                remedy="Amend the existing concept, or choose a different name.",
                context={"name": name},
            )
        entity, version = await self._uow.concepts.create(
            tenant_id=tenant_id,
            name=name,
            description=description,
            domain_id=domain_id,
            pack_ref=pack_ref,
            provenance=Provenance(authored_by=authored_by, reason="concept declared"),
        )
        self._audit(
            tenant_id=tenant_id,
            action="concept.declared",
            object_kind="concept",
            object_id=str(entity.id),
            actor_id=authored_by,
            detail={"name": name, "from_pack": pack_ref},
        )
        return entity, version

    async def declare_property(
        self,
        *,
        tenant_id: str,
        concept_id: str,
        name: str,
        definition: str = "",
        semantic_type: str | None = None,
        unit: str | None = None,
        value_domain: dict[str, Any] | None = None,
        is_identifier: bool = False,
        authored_by: str | None = None,
    ) -> Any:
        """Declare a property of a concept, e.g. ``Instrument.ISIN``.

        A control authored against this property applies to every attribute
        mapped to it — which is what "author once, enforce everywhere" means in
        practice, and why the mapping is worth asking for.
        """
        if await self._uow.concepts.current(concept_id) is None:
            raise NotFoundError(
                f"concept {concept_id!r} does not exist",
                remedy="Declare the concept before declaring its properties.",
                context={"concept_id": concept_id},
            )
        existing = await self._uow.concept_properties.for_concept(concept_id)
        if any(p.name == name for p in existing):
            raise ConflictError(
                f"property {name!r} is already declared on this concept",
                remedy="Amend the existing property, or choose a different name.",
                context={"property": name},
            )
        entity, version = await self._uow.concept_properties.create(
            tenant_id=tenant_id,
            identity_fields={"concept_id": concept_id},
            name=name,
            definition=definition,
            semantic_type=semantic_type,
            unit=unit,
            value_domain_json=value_domain,
            is_identifier=is_identifier,
            provenance=Provenance(authored_by=authored_by, reason="property declared"),
        )
        self._audit(
            tenant_id=tenant_id,
            action="concept_property.declared",
            object_kind="concept_property",
            object_id=str(entity.id),
            actor_id=authored_by,
            detail={"concept_id": concept_id, "name": name, "identifier": is_identifier},
        )
        return entity, version

    async def map_attribute(
        self,
        *,
        tenant_id: str,
        attribute_id: str,
        property_id: str,
        mapped_by: str | None = None,
    ) -> Any:
        """Claim that an attribute *is* a canonical property.

        The claim is what makes conflict detection possible: two attributes
        asserting the same meaning while disagreeing about units become visible
        rather than silently coexisting.
        """
        if await self._uow.concept_properties.current(property_id) is None:
            raise NotFoundError(
                f"concept property {property_id!r} does not exist",
                remedy="Declare the property before mapping attributes to it.",
                context={"property_id": property_id},
            )
        version = await self._uow.attributes.amend(
            attribute_id,
            concept_property_id=property_id,
            provenance=Provenance(
                authored_by=mapped_by, reason="mapped to a canonical concept property"
            ),
        )
        self._audit(
            tenant_id=tenant_id,
            action="attribute.mapped",
            object_kind="attribute",
            object_id=attribute_id,
            actor_id=mapped_by,
            detail={"property_id": property_id},
        )
        return version


class JourneyService(SemanticService):
    """Business processes as ordered chains of datasets.

    A journey is business lineage a human declared, so it crosses the boundaries
    a scanner cannot: a mainframe job, a vendor package, a manual upload.
    """

    STEP_KINDS = ("dataset", "black_box", "manual")

    async def declare(
        self,
        *,
        tenant_id: str,
        name: str,
        description: str = "",
        domain_id: str | None = None,
        owner_id: str | None = None,
        criticality: int = 4,
        sla: dict[str, Any] | None = None,
        steps: list[dict[str, Any]] | None = None,
        authored_by: str | None = None,
        approved_by: str | None = None,
    ) -> Any:
        slug = slugify(name)
        if await self._uow.journeys.by_slug(tenant_id, slug) is not None:
            raise ConflictError(
                f"a journey named {name!r} already exists",
                remedy="Choose a different name, or amend the existing journey.",
                context={"slug": slug},
            )
        self._policy.check(
            criticality=criticality,
            authored_by=authored_by,
            approved_by=approved_by,
            what="journey declaration",
        )
        normalised = await self._validate_steps(steps or [])
        entity, version = await self._uow.journeys.create(
            tenant_id=tenant_id,
            name=name,
            slug=slug,
            description=description,
            domain_id=domain_id,
            owner_id=owner_id,
            criticality=criticality,
            sla_json=sla,
            steps_json=normalised,
            provenance=Provenance(
                authored_by=authored_by, approved_by=approved_by, reason="journey declared"
            ),
        )
        self._audit(
            tenant_id=tenant_id,
            action="journey.declared",
            object_kind="journey",
            object_id=str(entity.id),
            actor_id=authored_by,
            detail={"slug": slug, "steps": len(normalised)},
        )
        return entity, version

    async def set_steps(
        self,
        *,
        tenant_id: str,
        journey_id: str,
        steps: list[dict[str, Any]],
        reason: str,
        authored_by: str | None = None,
    ) -> Any:
        """Replace the chain wholesale.

        Steps are edited as a whole because reordering touches every one of
        them; a per-step API would make the common operation the awkward one.
        """
        normalised = await self._validate_steps(steps)
        version = await self._uow.journeys.amend(
            journey_id,
            steps_json=normalised,
            provenance=Provenance(authored_by=authored_by, reason=reason),
        )
        self._audit(
            tenant_id=tenant_id,
            action="journey.steps_changed",
            object_kind="journey",
            object_id=journey_id,
            actor_id=authored_by,
            detail={"steps": len(normalised), "reason": reason},
        )
        return version

    async def _validate_steps(self, steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Check every step and renumber, so ordinals always match position."""
        normalised: list[dict[str, Any]] = []
        for position, step in enumerate(steps):
            kind = step.get("kind", "dataset")
            if kind not in self.STEP_KINDS:
                raise ValidationError(
                    f"step {position} has unknown kind {kind!r}",
                    remedy=f"Use one of: {', '.join(self.STEP_KINDS)}.",
                    context={"position": position, "kind": kind},
                )
            if kind == "dataset":
                dataset_id = step.get("dataset_id")
                if not dataset_id:
                    raise ValidationError(
                        f"step {position} is a dataset step with no dataset",
                        remedy=(
                            "Name the dataset, or declare the step as a black_box if it is "
                            "a system Prama cannot read."
                        ),
                        context={"position": position},
                    )
                if await self._uow.datasets.current(dataset_id) is None:
                    raise NotFoundError(
                        f"step {position} references dataset {dataset_id!r}, which does not exist",
                        remedy="Declare the dataset first, or correct the reference.",
                        context={"position": position, "dataset_id": dataset_id},
                    )
            elif not (step.get("description") or "").strip():
                raise ValidationError(
                    f"step {position} is a {kind} step with no description",
                    remedy=(
                        "Describe what happens there. A black box Prama cannot read is "
                        "exactly the step that most needs a sentence explaining it."
                    ),
                    context={"position": position},
                )
            normalised.append({**step, "ordinal": position, "kind": kind})
        return normalised


class ConnectionService(SemanticService):
    """Configured routes to source systems.

    A business user configures a connection they cannot read the credential for:
    ``credential_ref`` names a vault entry, and no secret is ever stored here.
    Separation of duties expressed in the data model rather than in a procedure.
    """

    async def configure(
        self,
        *,
        tenant_id: str,
        name: str,
        source_type: str,
        description: str = "",
        config: dict[str, Any] | None = None,
        credential_ref: str | None = None,
        read_policy: dict[str, Any] | None = None,
        budget: dict[str, Any] | None = None,
        owner_id: str | None = None,
        authored_by: str | None = None,
    ) -> Any:
        slug = slugify(name)
        if await self._uow.connections.by_slug(tenant_id, slug) is not None:
            raise ConflictError(
                f"a connection named {name!r} already exists",
                remedy="Choose a different name, or amend the existing connection.",
                context={"slug": slug},
            )
        self._reject_inline_secrets(config or {})
        entity, version = await self._uow.connections.create(
            tenant_id=tenant_id,
            name=name,
            slug=slug,
            source_type=source_type,
            description=description,
            config_json=config or {},
            credential_ref=credential_ref,
            read_policy_json=read_policy or {},
            budget_json=budget or {},
            owner_id=owner_id,
            provenance=Provenance(authored_by=authored_by, reason="connection configured"),
        )
        self._audit(
            tenant_id=tenant_id,
            action="connection.configured",
            object_kind="connection",
            object_id=str(entity.id),
            actor_id=authored_by,
            detail={"slug": slug, "source_type": source_type},
        )
        return entity, version

    async def record_health(
        self,
        *,
        tenant_id: str,
        connection_id: str,
        state: str,
        detail: str | None = None,
        checked_at: Any = None,
    ) -> Any:
        """Record the outcome of a connectivity check.

        An amendment rather than a correction: the connection really was healthy
        yesterday and really is unreachable now, and both facts matter when
        explaining why a control did not run.
        """
        version = await self._uow.connections.amend(
            connection_id,
            health_state=state,
            health_detail=detail,
            health_checked_at=checked_at,
            provenance=Provenance(reason=f"health check: {state}"),
        )
        self._audit(
            tenant_id=tenant_id,
            action="connection.health_recorded",
            object_kind="connection",
            object_id=connection_id,
            actor_id=None,
            actor_kind="system",
            detail={"state": state, "detail": detail},
        )
        return version

    #: Keys that must never appear inline in a tracked configuration.
    SECRET_KEYS = frozenset(
        {
            "password",
            "passwd",
            "secret",
            "token",
            "api_key",
            "apikey",
            "private_key",
            "client_secret",
            "access_key",
            "sas_token",
        }
    )

    def _reject_inline_secrets(self, config: dict[str, Any]) -> None:
        """Refuse a secret written into the connection's configuration.

        The vault reference exists so this never has to be stored; accepting it
        "just this once" is how a credential ends up in a GitOps export.
        """
        found = sorted(
            key
            for key, value in config.items()
            if key.lower() in self.SECRET_KEYS and value not in (None, "")
        )
        if found:
            raise ValidationError(
                f"a connection's configuration may not contain a secret: {', '.join(found)}",
                remedy=(
                    "Store it in the vault and reference it with credential_ref. "
                    "Connection configuration is exported to Git and shown in the UI."
                ),
                context={"keys": found},
            )


class BindingService(SemanticService):
    """The link between a declared object and its physical realisation."""

    async def bind_dataset(
        self,
        *,
        tenant_id: str,
        dataset_id: str,
        connection_id: str,
        physical_ref: dict[str, Any],
        shape: str = "table",
        confidence: float | None = None,
        confirmed: bool = True,
        authored_by: str | None = None,
    ) -> Any:
        """Bind a dataset, and record the shape it turned out to have."""
        if await self._uow.datasets.current(dataset_id) is None:
            raise NotFoundError(
                f"dataset {dataset_id!r} does not exist",
                remedy="Declare the dataset before binding it.",
                context={"dataset_id": dataset_id},
            )
        if await self._uow.connections.current(connection_id) is None:
            raise NotFoundError(
                f"connection {connection_id!r} does not exist",
                remedy="Configure the connection before binding through it.",
                context={"connection_id": connection_id},
            )
        entity, version = await self._uow.bindings.create(
            tenant_id=tenant_id,
            target_kind="dataset",
            dataset_id=dataset_id,
            connection_id=connection_id,
            physical_ref_json=physical_ref,
            status="confirmed" if confirmed else "proposed",
            confidence=confidence,
            drift_state="intact" if confirmed else "unknown",
            provenance=Provenance(authored_by=authored_by, reason="dataset bound"),
        )
        # A bound dataset is no longer unbound: the declaration and the shape
        # must agree, or the coverage report lies.
        await self._uow.datasets.amend(
            dataset_id,
            shape=shape,
            provenance=Provenance(authored_by=authored_by, reason="bound to a source"),
        )
        self._audit(
            tenant_id=tenant_id,
            action="dataset.bound",
            object_kind="dataset",
            object_id=dataset_id,
            actor_id=authored_by,
            detail={"connection_id": connection_id, "shape": shape, "ref": physical_ref},
        )
        return entity, version

    async def bind_attribute(
        self,
        *,
        tenant_id: str,
        dataset_id: str,
        attribute_id: str,
        connection_id: str,
        physical_ref: dict[str, Any],
        transform: str | None = None,
        confidence: float | None = None,
        authored_by: str | None = None,
    ) -> Any:
        entity, version = await self._uow.bindings.create(
            tenant_id=tenant_id,
            target_kind="attribute",
            dataset_id=dataset_id,
            attribute_id=attribute_id,
            connection_id=connection_id,
            physical_ref_json=physical_ref,
            transform=transform,
            status="confirmed",
            confidence=confidence,
            drift_state="intact",
            provenance=Provenance(authored_by=authored_by, reason="attribute bound"),
        )
        return entity, version

    async def record_drift(
        self,
        *,
        tenant_id: str,
        binding_id: str,
        drift_state: str,
        detail: str = "",
    ) -> Any:
        """Record that the physical world has moved beneath a declaration.

        Routed to the **business owner of the declaration**, not to an engineer:
        the declaration is theirs, and only a platform holding a declared model
        can detect this at all.
        """
        binding = await self._uow.bindings.require_current(binding_id)
        version = await self._uow.bindings.amend(
            binding_id,
            drift_state=drift_state,
            status="broken" if drift_state == "missing" else binding.status,
            provenance=Provenance(reason=detail or f"re-examination found: {drift_state}"),
        )
        self._audit(
            tenant_id=tenant_id,
            action="binding.drifted",
            object_kind="dataset",
            object_id=binding.dataset_id,
            actor_id=None,
            actor_kind="system",
            detail={"binding_id": binding_id, "drift_state": drift_state, "detail": detail},
        )
        return version
