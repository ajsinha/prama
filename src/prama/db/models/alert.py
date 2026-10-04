"""Alert delivery: what has been sent, and what waits for the digest.

The authority is ``schema/*.sql``; these mappings agree with it and
``tests/db/test_schema.py`` checks that they do.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from prama.db.models.base import Base, UlidPrimaryKey
from prama.db.types import JsonText

_FAULTS = "'arrival', 'schema', 'value', 'definition', 'reconciliation', 'calibration'"
_CHANGES = "'opened', 'unchanged', 'worsened', 'improved', 'resolved'"


class AlrState(UlidPrimaryKey, Base):
    """One open alert the router has sent, keyed by its fingerprint."""

    __tablename__ = "alr_state"

    tenant_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    identity: Mapped[str] = mapped_column(String(128), nullable=False)
    dataset: Mapped[str] = mapped_column(String(255), nullable=False)
    fault: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[float] = mapped_column(Float, nullable=False)
    last_sent_at: Mapped[str] = mapped_column(String(32), nullable=False)
    alert_json: Mapped[dict[str, Any]] = mapped_column(JsonText, nullable=False, default=dict)
    last_error: Mapped[str] = mapped_column(Text, nullable=False, default="")

    __table_args__ = (
        UniqueConstraint("tenant_id", "fingerprint", name="uq_alr_state_fingerprint"),
        CheckConstraint(f"fault IN ({_FAULTS})", name="ck_alr_state_fault"),
        Index("ix_alr_state_identity", "tenant_id", "identity"),
    )


class AlrDigest(UlidPrimaryKey, Base):
    """One finding queued for the daily digest."""

    __tablename__ = "alr_digest"

    tenant_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset: Mapped[str] = mapped_column(String(255), nullable=False)
    change: Mapped[str] = mapped_column(String(16), nullable=False)
    dispatch_json: Mapped[dict[str, Any]] = mapped_column(JsonText, nullable=False, default=dict)
    queued_at: Mapped[str] = mapped_column(String(32), nullable=False)
    sent_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error: Mapped[str] = mapped_column(Text, nullable=False, default="")

    __table_args__ = (
        CheckConstraint(f"change IN ({_CHANGES})", name="ck_alr_digest_change"),
        Index("ix_alr_digest_pending", "tenant_id", "sent_at"),
    )
