"""Semantic-layer models: domain, dataset, attribute.

The business estate as the business describes it. Each object is an **identity**
row that never changes and a chain of **version** rows carrying the declaration
(``prama.db.temporal``). Foreign keys point at identities, so a reference does
not need rewriting every time a declaration changes.

Value objects — grain, rhythm, value domain — are stored as JSON text and
reconstituted by the DAO into the types in ``prama.semantic.values``. They are
JSON rather than columns because they are *the business's words*: they gain
fields as the vocabulary grows, and a schema change per field would make the
vocabulary expensive to extend, which is the opposite of what we want.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from prama.db.models.base import Base, CreatedAt, UlidPrimaryKey
from prama.db.temporal import Versioned
from prama.db.types import BoolInt, JsonText

# ---------------------------------------------------------------------------
# Domain
# ---------------------------------------------------------------------------


class SemDomain(UlidPrimaryKey, CreatedAt, Base):
    """Identity of a business domain. Immutable."""

    __tablename__ = "sem_domain"

    tenant_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )

    versions: Mapped[list[SemDomainVersion]] = relationship(
        back_populates="domain", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (Index("ix_sem_domain_tenant", "tenant_id"),)


class SemDomainVersion(UlidPrimaryKey, Versioned, Base):
    """A domain declaration as it stood over some period."""

    __tablename__ = "sem_domain_version"

    domain_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("sem_domain.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    owner_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    parent_domain_id: Mapped[str | None] = mapped_column(String(26), nullable=True)

    domain: Mapped[SemDomain] = relationship(back_populates="versions", lazy="joined")

    __table_args__ = (Index("ix_sem_domain_version_entity", "domain_id", "recorded_at"),)


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------


class SemDataset(UlidPrimaryKey, CreatedAt, Base):
    """Identity of a dataset. Immutable, and creatable before anything is bound."""

    __tablename__ = "sem_dataset"

    tenant_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )

    versions: Mapped[list[SemDatasetVersion]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan", lazy="selectin"
    )
    attributes: Mapped[list[SemAttribute]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (Index("ix_sem_dataset_tenant", "tenant_id"),)


class SemDatasetVersion(UlidPrimaryKey, Versioned, Base):
    """A dataset declaration.

    Every column here answers a question a business owner can answer, and every
    one of them generates a control (docs/03 §5). ``shape`` records what kind of
    thing this is — a table, a feed, a set of feeds, a return, or nothing yet —
    because a feed's controls are not a table's.
    """

    __tablename__ = "sem_dataset_version"

    dataset_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("sem_dataset.id", ondelete="CASCADE"), nullable=False
    )

    # -- identity and ownership
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    purpose: Mapped[str] = mapped_column(Text, nullable=False, default="")
    domain_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    shape: Mapped[str] = mapped_column(String(32), nullable=False, default="unbound")
    owner_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    steward_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    custodian_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    criticality: Mapped[int] = mapped_column(Integer, nullable=False, default=4)

    # -- the declarations that generate controls
    grain_json: Mapped[dict[str, Any] | None] = mapped_column(JsonText, nullable=True)
    business_key_json: Mapped[list[str] | None] = mapped_column(JsonText, nullable=True)
    temporality: Mapped[str] = mapped_column(String(32), nullable=False, default="snapshot")
    rhythm_json: Mapped[dict[str, Any] | None] = mapped_column(JsonText, nullable=True)
    authoritativeness: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    source_of_truth_id: Mapped[str | None] = mapped_column(String(26), nullable=True)

    # -- governance
    retention_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    jurisdiction: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sensitivity: Mapped[str] = mapped_column(String(32), nullable=False, default="internal")
    lifecycle_state: Mapped[str] = mapped_column(String(32), nullable=False, default="proposed")
    tags_json: Mapped[list[str]] = mapped_column(JsonText, nullable=False, default=list)

    dataset: Mapped[SemDataset] = relationship(back_populates="versions", lazy="joined")

    # -- derived views used by the estate map and the maturity score

    @property
    def is_bound(self) -> bool:
        """A dataset with no physical shape is declared but not yet connected."""
        return self.shape != "unbound"

    @property
    def has_grain(self) -> bool:
        return bool(self.grain_json and self.grain_json.get("attributes"))

    @property
    def has_rhythm(self) -> bool:
        return bool(self.rhythm_json)

    @property
    def is_tier_one(self) -> bool:
        return self.criticality == 1

    __table_args__ = (
        Index("ix_sem_dataset_version_entity", "dataset_id", "recorded_at"),
        Index("ix_sem_dataset_version_domain", "domain_id", "criticality"),
        Index("ix_sem_dataset_version_slug", "slug"),
        CheckConstraint("criticality BETWEEN 1 AND 4", name="ck_sem_dataset_criticality"),
        CheckConstraint(
            "shape IN ('unbound', 'table', 'table_set', 'schema', 'feed', 'feed_set', "
            "'stream', 'api', 'report', 'query')",
            name="ck_sem_dataset_shape",
        ),
        CheckConstraint(
            "lifecycle_state IN ('proposed', 'active', 'deprecated', 'retired')",
            name="ck_sem_dataset_lifecycle",
        ),
    )


# ---------------------------------------------------------------------------
# Attribute
# ---------------------------------------------------------------------------


class SemAttribute(UlidPrimaryKey, CreatedAt, Base):
    """Identity of a business attribute. Immutable."""

    __tablename__ = "sem_attribute"

    tenant_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    dataset_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("sem_dataset.id", ondelete="CASCADE"), nullable=False
    )

    dataset: Mapped[SemDataset] = relationship(back_populates="attributes", lazy="joined")
    versions: Mapped[list[SemAttributeVersion]] = relationship(
        back_populates="attribute", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (Index("ix_sem_attribute_dataset", "dataset_id"),)


class SemAttributeVersion(UlidPrimaryKey, Versioned, Base):
    """An attribute declaration: what the field means, not what it is called.

    ``interpretation`` is separate from ``definition`` on purpose. A definition
    says what the value is; an interpretation says how to read it — sign
    conventions, inclusions and exclusions, the calculation basis. Almost every
    cross-team disagreement about a number is an interpretation disagreement,
    and there has never been a field to write it in.
    """

    __tablename__ = "sem_attribute_version"

    attribute_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("sem_attribute.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    definition: Mapped[str] = mapped_column(Text, nullable=False, default="")
    interpretation: Mapped[str] = mapped_column(Text, nullable=False, default="")

    semantic_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    currency_attribute: Mapped[str | None] = mapped_column(String(128), nullable=True)
    numeric_scale: Mapped[int | None] = mapped_column(Integer, nullable=True)
    numeric_precision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    value_domain_json: Mapped[dict[str, Any] | None] = mapped_column(JsonText, nullable=True)

    optionality: Mapped[str] = mapped_column(String(32), nullable=False, default="optional")
    optionality_condition: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_cde: Mapped[bool] = mapped_column(BoolInt, nullable=False, default=False)
    obligations_json: Mapped[list[str]] = mapped_column(JsonText, nullable=False, default=list)
    sensitivity: Mapped[str] = mapped_column(String(32), nullable=False, default="internal")
    masking_policy: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expected_behaviour: Mapped[str | None] = mapped_column(String(32), nullable=True)
    concept_property_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    glossary_term: Mapped[str | None] = mapped_column(String(255), nullable=True)
    owner_id: Mapped[str | None] = mapped_column(String(26), nullable=True)

    attribute: Mapped[SemAttribute] = relationship(back_populates="versions", lazy="joined")

    @property
    def is_constrained(self) -> bool:
        """Whether this attribute can generate a domain-membership control."""
        if self.semantic_type:
            return True
        domain = self.value_domain_json or {}
        return bool(domain) and domain.get("kind") != "free_text"

    __table_args__ = (
        Index("ix_sem_attribute_version_entity", "attribute_id", "recorded_at"),
        Index("ix_sem_attribute_version_cde", "is_cde", "semantic_type"),
        CheckConstraint("is_cde IN (0, 1)", name="ck_sem_attribute_is_cde"),
        CheckConstraint(
            "optionality IN ('mandatory', 'conditional', 'optional')",
            name="ck_sem_attribute_optionality",
        ),
    )
