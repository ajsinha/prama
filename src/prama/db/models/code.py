"""Code intake: sources, analysis runs, and the units each run read.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from prama.db.models.base import Base, CreatedAt, UlidPrimaryKey
from prama.db.types import BoolInt, JsonText


class CodeSource(UlidPrimaryKey, CreatedAt, Base):
    """A body of application code: an uploaded ZIP or a git location."""

    __tablename__ = "code_source"

    tenant_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    secret_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sensitivity: Mapped[str] = mapped_column(String(16), nullable=False, default="internal")
    auto_refresh: Mapped[bool] = mapped_column(BoolInt, nullable=False, default=False)
    created_by: Mapped[str | None] = mapped_column(String(26), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_code_source_name"),
        CheckConstraint("kind IN ('zip', 'git')", name="ck_code_source_kind"),
        CheckConstraint("auto_refresh IN (0, 1)", name="ck_code_source_auto"),
    )


class CodeAnalysisRun(UlidPrimaryKey, Base):
    """One reading of a source's snapshot."""

    __tablename__ = "code_analysis_run"

    tenant_id: Mapped[str] = mapped_column(String(26), nullable=False)
    source_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("code_source.id", ondelete="CASCADE"), nullable=False
    )
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    base_run_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[str] = mapped_column(String(32), nullable=False)
    finished_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    inventory_json: Mapped[dict[str, Any]] = mapped_column(JsonText, nullable=False, default=dict)
    coverage_json: Mapped[dict[str, Any]] = mapped_column(JsonText, nullable=False, default=dict)
    llm_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'partial', 'failed', 'cancelled')",
            name="ck_code_run_status",
        ),
        Index("ix_code_run_source", "source_id", "started_at"),
    )


class CodeUnit(UlidPrimaryKey, Base):
    """One file a run read, and what it made of it."""

    __tablename__ = "code_unit"

    tenant_id: Mapped[str] = mapped_column(String(26), nullable=False)
    run_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("code_analysis_run.id", ondelete="CASCADE"), nullable=False
    )
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    blob_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    scanner: Mapped[str] = mapped_column(String(64), nullable=False)
    scanner_version: Mapped[str] = mapped_column(String(32), nullable=False)
    statements: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    gaps_json: Mapped[list[Any]] = mapped_column(JsonText, nullable=False, default=list)

    __table_args__ = (Index("ix_code_unit_run", "run_id"),)
