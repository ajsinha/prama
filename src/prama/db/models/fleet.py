"""The agent fleet: agents, enrolment tokens, assignments and reported gaps.

The authority is ``schema/*.sql``; these mappings agree with it and
``tests/db/test_schema.py`` checks that they do.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from prama.db.models.base import Base, UlidPrimaryKey
from prama.db.types import JsonText


class FlAgent(UlidPrimaryKey, Base):
    """An enrolled agent. Its key is derived, never stored."""

    __tablename__ = "fl_agent"

    tenant_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    zone: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    capabilities_json: Mapped[dict[str, Any]] = mapped_column(
        JsonText, nullable=False, default=dict
    )
    pending_findings: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=-1)
    enrolled_at: Mapped[str] = mapped_column(String(32), nullable=False)
    last_seen_at: Mapped[str | None] = mapped_column(String(32), nullable=True)

    __table_args__ = (
        CheckConstraint("state IN ('active', 'suspended', 'revoked')", name="ck_fl_agent_state"),
        Index("ix_fl_agent_zone", "tenant_id", "zone"),
    )


class FlToken(UlidPrimaryKey, Base):
    """A one-use enrolment token, as its digest."""

    __tablename__ = "fl_token"

    tenant_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    zone: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    issued_by: Mapped[str | None] = mapped_column(String(26), nullable=True)
    issued_at: Mapped[str] = mapped_column(String(32), nullable=False)
    expires_at: Mapped[str] = mapped_column(String(32), nullable=False)
    redeemed_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String(26), nullable=True)

    __table_args__ = (UniqueConstraint("digest", name="uq_fl_token_digest"),)


class FlAssignment(UlidPrimaryKey, Base):
    """One control's work for one zone, queued or claimed under a lease."""

    __tablename__ = "fl_assignment"

    tenant_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    zone: Mapped[str] = mapped_column(String(128), nullable=False)
    control_id: Mapped[str] = mapped_column(String(26), nullable=False)
    control_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    plan_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    dataset: Mapped[str] = mapped_column(String(255), nullable=False)
    engine: Mapped[str] = mapped_column(String(32), nullable=False)
    pql: Mapped[str] = mapped_column(Text, nullable=False)
    assignment_json: Mapped[dict[str, Any]] = mapped_column(JsonText, nullable=False, default=dict)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    reasons_json: Mapped[list[Any]] = mapped_column(JsonText, nullable=False, default=list)
    queued_by: Mapped[str | None] = mapped_column(String(26), nullable=True)
    queued_at: Mapped[str] = mapped_column(String(32), nullable=False)
    claimed_by: Mapped[str | None] = mapped_column(String(26), nullable=True)
    claimed_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    lease_until: Mapped[str | None] = mapped_column(String(32), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    done_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    evidence_sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "state IN ('queued', 'claimed', 'done', 'unassignable')",
            name="ck_fl_assignment_state",
        ),
        Index("ix_fl_assignment_queue", "tenant_id", "zone", "state"),
    )


class FlGap(UlidPrimaryKey, Base):
    """Findings an agent's spool dropped, as the agent reported them."""

    __tablename__ = "fl_gap"

    tenant_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("fl_agent.id", ondelete="CASCADE"), nullable=False
    )
    first_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    last_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    dropped_at: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    reported_at: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        UniqueConstraint("agent_id", "first_sequence", "last_sequence", name="uq_fl_gap"),
    )
