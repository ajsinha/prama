"""Metadata templates and their values on datasets and attributes.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from prama.db.models.base import Base, UlidPrimaryKey


class MdTemplate(UlidPrimaryKey, Base):
    __tablename__ = "md_template"

    tenant_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    applies_to: Mapped[str] = mapped_column(String(16), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_md_template_name"),
        CheckConstraint("applies_to IN ('dataset', 'attribute')", name="ck_md_template_applies"),
        CheckConstraint("status IN ('active', 'retired')", name="ck_md_template_status"),
    )


class MdField(UlidPrimaryKey, Base):
    __tablename__ = "md_field"

    template_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("md_template.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    choices_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    required: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    help: Mapped[str] = mapped_column(Text, nullable=False, default="")
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rules_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    __table_args__ = (
        UniqueConstraint("template_id", "name", name="uq_md_field_name"),
        CheckConstraint(
            "kind IN ('text', 'longtext', 'number', 'flag', 'choice', 'list', 'day', 'columns')",
            name="ck_md_field_kind",
        ),
        CheckConstraint("required IN (0, 1)", name="ck_md_field_required"),
    )


class MdValue(UlidPrimaryKey, Base):
    __tablename__ = "md_value"

    tenant_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    field_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("md_field.id", ondelete="CASCADE"), nullable=False
    )
    object_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    object_ref: Mapped[str] = mapped_column(String(26), nullable=False)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)
    valid_from: Mapped[str] = mapped_column(String(32), nullable=False)
    valid_to: Mapped[str | None] = mapped_column(String(32), nullable=True)
    recorded_by: Mapped[str | None] = mapped_column(String(26), nullable=True)

    __table_args__ = (
        CheckConstraint("object_kind IN ('dataset', 'attribute')", name="ck_md_value_kind"),
        Index("ix_md_value_object", "tenant_id", "object_kind", "object_ref"),
    )
