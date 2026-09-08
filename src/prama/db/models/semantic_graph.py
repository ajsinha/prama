"""Semantic-layer models: concept, relationship, journey, connection, binding.

The objects that connect datasets to each other and to the physical world.
Split from ``semantic.py`` so neither file grows past the point where it can be
read in one sitting.

Every one is bitemporal (``prama.db.temporal``): identity rows that never
change, and version chains carrying the declaration along valid time and
transaction time.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    REAL,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from prama.db.models.base import Base, CreatedAt, UlidPrimaryKey
from prama.db.temporal import Versioned
from prama.db.types import BoolInt, JsonText, UtcDateTime

# ---------------------------------------------------------------------------
# Concept and Concept Property
# ---------------------------------------------------------------------------


class SemConcept(UlidPrimaryKey, CreatedAt, Base):
    """Identity of a canonical business concept: Party, Instrument, Position."""

    __tablename__ = "sem_concept"

    tenant_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )

    versions: Mapped[list[SemConceptVersion]] = relationship(
        back_populates="concept", cascade="all, delete-orphan", lazy="selectin"
    )
    properties: Mapped[list[SemConceptProperty]] = relationship(
        back_populates="concept", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (Index("ix_sem_concept_tenant", "tenant_id"),)


class SemConceptVersion(UlidPrimaryKey, Versioned, Base):
    __tablename__ = "sem_concept_version"

    concept_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("sem_concept.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    domain_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    #: Set when the concept came from a domain pack rather than the tenant.
    pack_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)

    concept: Mapped[SemConcept] = relationship(back_populates="versions", lazy="joined")

    __table_args__ = (Index("ix_sem_concept_version_entity", "concept_id", "recorded_at"),)


class SemConceptProperty(UlidPrimaryKey, CreatedAt, Base):
    """Identity of a property of a concept, e.g. ``Instrument.ISIN``."""

    __tablename__ = "sem_concept_property"

    tenant_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    concept_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("sem_concept.id", ondelete="CASCADE"), nullable=False
    )

    concept: Mapped[SemConcept] = relationship(back_populates="properties", lazy="joined")
    versions: Mapped[list[SemConceptPropertyVersion]] = relationship(
        back_populates="property", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (Index("ix_sem_concept_property_concept", "concept_id"),)


class SemConceptPropertyVersion(UlidPrimaryKey, Versioned, Base):
    """The canonical definition attributes across the estate map onto.

    When twenty-three datasets map an attribute to ``Party.LEI``, one control
    authored here applies to all of them — and two incompatible definitions of
    the same property become detectable instead of silently coexisting.
    """

    __tablename__ = "sem_concept_property_version"

    property_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("sem_concept_property.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False, default="")
    semantic_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    value_domain_json: Mapped[dict[str, Any] | None] = mapped_column(JsonText, nullable=True)
    #: True when this property identifies the concept, e.g. Party.LEI.
    is_identifier: Mapped[bool] = mapped_column(BoolInt, nullable=False, default=False)

    property: Mapped[SemConceptProperty] = relationship(back_populates="versions", lazy="joined")

    __table_args__ = (
        Index("ix_sem_concept_property_version_entity", "property_id", "recorded_at"),
        CheckConstraint("is_identifier IN (0, 1)", name="ck_sem_concept_property_identifier"),
    )


# ---------------------------------------------------------------------------
# Relationship
# ---------------------------------------------------------------------------


class SemRelationship(UlidPrimaryKey, CreatedAt, Base):
    """Identity of a business relationship between two datasets."""

    __tablename__ = "sem_relationship"

    tenant_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )

    versions: Mapped[list[SemRelationshipVersion]] = relationship(
        back_populates="entity", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (Index("ix_sem_relationship_tenant", "tenant_id"),)


class SemRelationshipVersion(UlidPrimaryKey, Versioned, Base):
    """A declared relationship, and everything a generator needs from it.

    ``status`` separates *discovered* from *declared*. A control derived from a
    merely proposed relationship is itself only a proposal, and can never
    activate until a human confirms the relationship — which is what stops
    automated discovery from quietly creating production controls.
    """

    __tablename__ = "sem_relationship_version"

    relationship_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("sem_relationship.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    from_dataset_id: Mapped[str] = mapped_column(String(26), nullable=False)
    to_dataset_id: Mapped[str] = mapped_column(String(26), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    match_keys_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JsonText, nullable=False, default=list
    )
    compare_json: Mapped[list[str]] = mapped_column(JsonText, nullable=False, default=list)
    cardinality: Mapped[str] = mapped_column(String(32), nullable=False, default="many_to_many")
    tolerance_json: Mapped[dict[str, Any] | None] = mapped_column(JsonText, nullable=True)
    offset_json: Mapped[dict[str, Any] | None] = mapped_column(JsonText, nullable=True)
    filter_expression: Mapped[str | None] = mapped_column(Text, nullable=True)

    owner_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    criticality: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="proposed")
    #: Present when discovered rather than declared; the evidence is retained
    #: so a steward confirming it can see *why* it was suggested.
    confidence: Mapped[float | None] = mapped_column(REAL, nullable=True)
    discovered_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    evidence_json: Mapped[dict[str, Any] | None] = mapped_column(JsonText, nullable=True)

    entity: Mapped[SemRelationship] = relationship(back_populates="versions", lazy="joined")

    @property
    def is_confirmed(self) -> bool:
        """Only a confirmed relationship may generate an activatable control."""
        return self.status == "confirmed"

    @property
    def is_discovered(self) -> bool:
        return self.discovered_by is not None

    __table_args__ = (
        Index("ix_sem_relationship_version_from", "from_dataset_id", "kind"),
        Index("ix_sem_relationship_version_to", "to_dataset_id", "kind"),
        Index("ix_sem_relationship_version_entity", "relationship_id", "recorded_at"),
        CheckConstraint(
            "kind IN ('references', 'reconciles_with', 'derives_from', 'feeds', 'mirrors', "
            "'aggregates', 'enriches', 'supersedes', 'same_entity_as', "
            "'temporal_successor', 'parent_of', 'mutually_exclusive', 'together_complete')",
            name="ck_sem_relationship_kind",
        ),
        CheckConstraint(
            "cardinality IN ('one_to_one', 'one_to_many', 'many_to_one', 'many_to_many')",
            name="ck_sem_relationship_cardinality",
        ),
        CheckConstraint(
            "status IN ('proposed', 'confirmed', 'rejected', 'retired')",
            name="ck_sem_relationship_status",
        ),
        CheckConstraint("criticality BETWEEN 1 AND 4", name="ck_sem_relationship_criticality"),
    )


# ---------------------------------------------------------------------------
# Journey
# ---------------------------------------------------------------------------


class SemJourney(UlidPrimaryKey, CreatedAt, Base):
    """Identity of a business process expressed as a chain of datasets."""

    __tablename__ = "sem_journey"

    tenant_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )

    versions: Mapped[list[SemJourneyVersion]] = relationship(
        back_populates="journey", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (Index("ix_sem_journey_tenant", "tenant_id"),)


class SemJourneyVersion(UlidPrimaryKey, Versioned, Base):
    """An ordered chain of steps: datasets, relationships, and black boxes.

    Steps are JSON rather than rows because a journey is edited as a whole — a
    reorder touches every step — and because a step may be a *declared* black
    box (a mainframe job, a vendor system, a manual upload) that has no dataset
    to point at. That is precisely the case a lineage scanner cannot reach and a
    human can describe in one sentence.
    """

    __tablename__ = "sem_journey_version"

    journey_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("sem_journey.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    domain_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    owner_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    criticality: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    sla_json: Mapped[dict[str, Any] | None] = mapped_column(JsonText, nullable=True)
    steps_json: Mapped[list[dict[str, Any]]] = mapped_column(JsonText, nullable=False, default=list)

    journey: Mapped[SemJourney] = relationship(back_populates="versions", lazy="joined")

    @property
    def step_count(self) -> int:
        return len(self.steps_json or [])

    @property
    def dataset_ids(self) -> list[str]:
        return [s["dataset_id"] for s in (self.steps_json or []) if s.get("dataset_id")]

    __table_args__ = (
        Index("ix_sem_journey_version_entity", "journey_id", "recorded_at"),
        CheckConstraint("criticality BETWEEN 1 AND 4", name="ck_sem_journey_criticality"),
    )


# ---------------------------------------------------------------------------
# Connection and Binding
# ---------------------------------------------------------------------------


class SemConnection(UlidPrimaryKey, CreatedAt, Base):
    """Identity of a configured route to a source system."""

    __tablename__ = "sem_connection"

    tenant_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )

    versions: Mapped[list[SemConnectionVersion]] = relationship(
        back_populates="connection", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (Index("ix_sem_connection_tenant", "tenant_id"),)


class SemConnectionVersion(UlidPrimaryKey, Versioned, Base):
    """How Prama reaches a source, and what it is permitted to do there.

    ``credential_ref`` names a vault entry; no secret is ever stored here. A
    business user can configure a connection they cannot read the password for,
    which is separation of duties expressed in the data model rather than in a
    policy document.
    """

    __tablename__ = "sem_connection_version"

    connection_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("sem_connection.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    config_json: Mapped[dict[str, Any]] = mapped_column(JsonText, nullable=False, default=dict)
    credential_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    read_policy_json: Mapped[dict[str, Any]] = mapped_column(JsonText, nullable=False, default=dict)
    budget_json: Mapped[dict[str, Any]] = mapped_column(JsonText, nullable=False, default=dict)
    owner_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    health_state: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    health_checked_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    health_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    connection: Mapped[SemConnection] = relationship(back_populates="versions", lazy="joined")

    @property
    def is_usable(self) -> bool:
        return self.health_state in ("healthy", "degraded")

    __table_args__ = (
        Index("ix_sem_connection_version_entity", "connection_id", "recorded_at"),
        CheckConstraint(
            "health_state IN ('unknown', 'healthy', 'degraded', 'unreachable', 'unauthorised')",
            name="ck_sem_connection_health",
        ),
    )


class SemBinding(UlidPrimaryKey, CreatedAt, Base):
    """Identity of a link from a business object to a physical one."""

    __tablename__ = "sem_binding"

    tenant_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )

    versions: Mapped[list[SemBindingVersion]] = relationship(
        back_populates="binding", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (Index("ix_sem_binding_tenant", "tenant_id"),)


class SemBindingVersion(UlidPrimaryKey, Versioned, Base):
    """Where a declared object actually lives.

    ``drift_state`` is what makes metadata drift detectable: the physical world
    is re-checked on cadence, and a binding whose column has vanished becomes an
    incident routed to the **business owner of the declaration**, not to an
    engineer. No physical-first tool can do this, because it has no declaration
    to compare reality against.
    """

    __tablename__ = "sem_binding_version"

    binding_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("sem_binding.id", ondelete="CASCADE"), nullable=False
    )
    target_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    dataset_id: Mapped[str] = mapped_column(String(26), nullable=False)
    attribute_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    connection_id: Mapped[str] = mapped_column(String(26), nullable=False)
    physical_ref_json: Mapped[dict[str, Any]] = mapped_column(
        JsonText, nullable=False, default=dict
    )
    transform: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="proposed")
    confidence: Mapped[float | None] = mapped_column(REAL, nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    drift_state: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")

    binding: Mapped[SemBinding] = relationship(back_populates="versions", lazy="joined")

    @property
    def is_intact(self) -> bool:
        return self.status == "confirmed" and self.drift_state in ("intact", "unknown")

    @property
    def has_drifted(self) -> bool:
        return self.drift_state in ("missing", "retyped", "renamed")

    __table_args__ = (
        Index("ix_sem_binding_version_dataset", "dataset_id", "target_kind"),
        Index("ix_sem_binding_version_connection", "connection_id"),
        Index("ix_sem_binding_version_entity", "binding_id", "recorded_at"),
        CheckConstraint("target_kind IN ('dataset', 'attribute')", name="ck_sem_binding_target"),
        CheckConstraint(
            "status IN ('proposed', 'confirmed', 'rejected', 'broken')",
            name="ck_sem_binding_status",
        ),
        CheckConstraint(
            "drift_state IN ('unknown', 'intact', 'missing', 'retyped', 'renamed')",
            name="ck_sem_binding_drift",
        ),
    )
