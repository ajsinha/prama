"""The lineage store: sources, runs, column edges, and the gaps.

Lineage was a tested library that nothing persisted (docs/23 §1); these tables
make it a product. One store for every origin, so the workbench shows parsed
SQL, ingested OpenLineage and a declared journey side by side, each labelled
with where it came from.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from prama.db.models.base import Base, CreatedAt, UlidPrimaryKey
from prama.db.types import JsonText


class LinSource(UlidPrimaryKey, CreatedAt, Base):
    """Where lineage comes from."""

    __tablename__ = "lin_source"

    tenant_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    location: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    dialect: Mapped[str] = mapped_column(String(32), nullable=False, default="ansi")
    settings_json: Mapped[dict[str, Any]] = mapped_column(JsonText, nullable=False, default=dict)
    created_by: Mapped[str | None] = mapped_column(String(26), nullable=True)
    last_run_id: Mapped[str | None] = mapped_column(String(26), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_lin_source_name"),
        CheckConstraint(
            "kind IN ('sql', 'code', 'openlineage', 'dbt', 'warehouse', 'declared', 'import')",
            name="ck_lin_source_kind",
        ),
    )


class LinRun(UlidPrimaryKey, Base):
    """One scan of a source."""

    __tablename__ = "lin_run"

    tenant_id: Mapped[str] = mapped_column(String(26), nullable=False)
    source_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("lin_source.id", ondelete="CASCADE"), nullable=False
    )
    started_at: Mapped[str] = mapped_column(String(32), nullable=False)
    finished_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    statements: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    edges: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    gaps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    understood: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    started_by: Mapped[str | None] = mapped_column(String(26), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "outcome IN ('running', 'ok', 'partial', 'failed')", name="ck_lin_run_outcome"
        ),
        CheckConstraint("understood >= 0 AND understood <= 1", name="ck_lin_run_understood"),
        Index("ix_lin_run_source", "source_id", "started_at"),
    )


class LinEdge(UlidPrimaryKey, Base):
    """One column feeding another, with where the claim came from."""

    __tablename__ = "lin_edge"

    tenant_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("lin_source.id", ondelete="CASCADE"), nullable=False
    )
    identity: Mapped[str] = mapped_column(String(64), nullable=False)
    source_dataset: Mapped[str] = mapped_column(String(255), nullable=False)
    source_column: Mapped[str] = mapped_column(String(255), nullable=False)
    target_dataset: Mapped[str] = mapped_column(String(255), nullable=False)
    target_column: Mapped[str] = mapped_column(String(255), nullable=False)
    transform: Mapped[str] = mapped_column(String(16), nullable=False)
    produced_by: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    expression: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="parsed")
    method: Mapped[str] = mapped_column(String(128), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    unit_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    line_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    line_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    llm_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(26), nullable=True)
    decided_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    valid_from: Mapped[str] = mapped_column(String(32), nullable=False)
    valid_to: Mapped[str | None] = mapped_column(String(32), nullable=True)
    first_seen_run: Mapped[str] = mapped_column(String(26), nullable=False)
    last_seen_run: Mapped[str] = mapped_column(String(26), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "identity", name="uq_lin_edge_identity"),
        CheckConstraint(
            "status IN ('parsed', 'inferred', 'confirmed', 'rejected', 'retired')",
            name="ck_lin_edge_status",
        ),
        CheckConstraint(
            "transform IN ('identity', 'rename', 'derived', 'aggregated', 'filter', 'join_key')",
            name="ck_lin_edge_transform",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_lin_edge_confidence"),
        Index("ix_lin_edge_source_col", "tenant_id", "source_dataset", "source_column"),
        Index("ix_lin_edge_target_col", "tenant_id", "target_dataset", "target_column"),
    )


class LinGap(UlidPrimaryKey, Base):
    """Something one run could not read."""

    __tablename__ = "lin_gap"

    tenant_id: Mapped[str] = mapped_column(String(26), nullable=False)
    run_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("lin_run.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False, default="")
    unit_ref: Mapped[str] = mapped_column(String(512), nullable=False, default="")

    __table_args__ = (Index("ix_lin_gap_run", "run_id"),)
