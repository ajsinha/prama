"""Comment threads on governed objects.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from prama.db.models.base import Base, UlidPrimaryKey


class CmComment(UlidPrimaryKey, Base):
    __tablename__ = "cm_comment"

    tenant_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    object_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    object_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("cm_comment.id", ondelete="CASCADE"), nullable=True
    )
    author_id: Mapped[str] = mapped_column(String(26), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    mentions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    resolved_by: Mapped[str | None] = mapped_column(String(26), nullable=True)
    resolved_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "object_kind IN ('dataset', 'attribute', 'control', 'term', 'incident')",
            name="ck_cm_comment_kind",
        ),
        CheckConstraint("state IN ('open', 'resolved')", name="ck_cm_comment_state"),
        Index("ix_cm_comment_object", "tenant_id", "object_kind", "object_ref"),
        Index("ix_cm_comment_open", "tenant_id", "state"),
    )
