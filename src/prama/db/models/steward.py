"""Steward agents: who they are, what they pursue, what they did.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from prama.db.models.base import Base, CreatedAt, UlidPrimaryKey
from prama.db.types import JsonText


class AgtSteward(UlidPrimaryKey, CreatedAt, Base):
    __tablename__ = "agt_steward"

    tenant_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    principal_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("principal.id", ondelete="CASCADE"), nullable=False
    )
    sponsor_id: Mapped[str] = mapped_column(String(26), ForeignKey("principal.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    budget_json: Mapped[dict[str, Any]] = mapped_column(JsonText, nullable=False, default=dict)
    approvals_json: Mapped[list[Any]] = mapped_column(JsonText, nullable=False, default=list)
    last_seen_at: Mapped[str | None] = mapped_column(String(32), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_agt_steward_name"),
        CheckConstraint(
            "state IN ('active', 'paused', 'stopped', 'revoked')", name="ck_agt_steward_state"
        ),
    )


class AgtGoal(UlidPrimaryKey, Base):
    __tablename__ = "agt_goal"

    tenant_id: Mapped[str] = mapped_column(String(26), nullable=False)
    steward_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("agt_steward.id", ondelete="CASCADE"), nullable=False
    )
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    input_json: Mapped[dict[str, Any]] = mapped_column(JsonText, nullable=False, default=dict)
    schedule: Mapped[str | None] = mapped_column(String(128), nullable=True)
    trigger_json: Mapped[list[Any]] = mapped_column(JsonText, nullable=False, default=list)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_by: Mapped[str] = mapped_column(String(26), nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "state IN ('active', 'paused', 'done', 'cancelled')", name="ck_agt_goal_state"
        ),
    )


class AgtTask(UlidPrimaryKey, Base):
    __tablename__ = "agt_task"

    tenant_id: Mapped[str] = mapped_column(String(26), nullable=False)
    goal_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("agt_goal.id", ondelete="CASCADE"), nullable=False
    )
    task_key: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    input_json: Mapped[dict[str, Any]] = mapped_column(JsonText, nullable=False, default=dict)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fencing_token: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_json: Mapped[dict[str, Any] | None] = mapped_column(JsonText, nullable=True)
    trace_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    finished_at: Mapped[str | None] = mapped_column(String(32), nullable=True)

    __table_args__ = (
        UniqueConstraint("goal_id", "task_key", name="uq_agt_task_key"),
        CheckConstraint(
            "state IN ('pending', 'leased', 'running', 'awaiting_approval', 'succeeded', "
            "'failed', 'cancelled', 'expired')",
            name="ck_agt_task_state",
        ),
        Index("ix_agt_task_state", "state", "created_at"),
    )


class AgtApproval(UlidPrimaryKey, Base):
    __tablename__ = "agt_approval"

    tenant_id: Mapped[str] = mapped_column(String(26), nullable=False)
    task_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("agt_task.id", ondelete="CASCADE"), nullable=False
    )
    action_json: Mapped[dict[str, Any]] = mapped_column(JsonText, nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False, default="")
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    decided_by: Mapped[str | None] = mapped_column(String(26), nullable=True)
    decided_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "state IN ('open', 'granted', 'denied', 'expired')", name="ck_agt_approval_state"
        ),
    )


class AgtMemory(UlidPrimaryKey, Base):
    __tablename__ = "agt_memory"

    tenant_id: Mapped[str] = mapped_column(String(26), nullable=False)
    steward_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("agt_steward.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    mkey: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    source_task_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    expires_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        UniqueConstraint("steward_id", "kind", "mkey", name="uq_agt_memory_key"),
        CheckConstraint("kind IN ('episodic', 'note')", name="ck_agt_memory_kind"),
    )
