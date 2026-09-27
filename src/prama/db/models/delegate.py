"""DQ delegates uploaded through the console, and the decision on each.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from prama.db.models.base import Base, UlidPrimaryKey


class DqDelegateUpload(UlidPrimaryKey, Base):
    """One uploaded delegate file: its source, what vetting found, and who decided."""

    __tablename__ = "dq_delegate_upload"

    tenant_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="proposed")
    described: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    findings: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    submitted_by: Mapped[str] = mapped_column(String(26), nullable=False)
    submitted_at: Mapped[str] = mapped_column(String(32), nullable=False)
    decided_by: Mapped[str | None] = mapped_column(String(26), nullable=True)
    decided_at: Mapped[str | None] = mapped_column(String(32), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", "version", name="uq_dq_delegate_upload"),
        CheckConstraint(
            "state IN ('proposed', 'approved', 'rejected', 'retired')",
            name="ck_dq_delegate_upload_state",
        ),
        Index("ix_dq_delegate_upload_state", "tenant_id", "state"),
    )
