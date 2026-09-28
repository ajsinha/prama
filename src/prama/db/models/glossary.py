"""The business glossary: terms, and what each term names in the estate.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from prama.db.models.base import Base, UlidPrimaryKey


class GlTerm(UlidPrimaryKey, Base):
    __tablename__ = "gl_term"

    tenant_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False, default="")
    synonyms_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    domain: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    steward: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="accepted")
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="prama")
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_gl_term_name"),
        CheckConstraint(
            "status IN ('candidate', 'accepted', 'deprecated')", name="ck_gl_term_status"
        ),
        Index("ix_gl_term_external", "tenant_id", "source", "external_id"),
    )


class GlBinding(UlidPrimaryKey, Base):
    __tablename__ = "gl_binding"

    tenant_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    term_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("gl_term.id", ondelete="CASCADE"), nullable=False
    )
    object_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    object_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    how: Mapped[str] = mapped_column(String(16), nullable=False, default="person")
    created_by: Mapped[str | None] = mapped_column(String(26), nullable=True)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        UniqueConstraint("term_id", "object_kind", "object_ref", name="uq_gl_binding"),
        CheckConstraint(
            "object_kind IN ('concept', 'dataset', 'attribute')", name="ck_gl_binding_kind"
        ),
        CheckConstraint("how IN ('person', 'name_match', 'imported')", name="ck_gl_binding_how"),
        Index("ix_gl_binding_object", "tenant_id", "object_kind", "object_ref"),
    )
