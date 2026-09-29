"""How often each dataset is queried: a priority signal, never a quality one.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from prama.db.models.base import Base, UlidPrimaryKey


class UsUsage(UlidPrimaryKey, Base):
    __tablename__ = "us_usage"

    tenant_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    dataset: Mapped[str] = mapped_column(String(255), nullable=False)
    day: Mapped[str] = mapped_column(String(10), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    queries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    users: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("tenant_id", "dataset", "day", "source", name="uq_us_usage"),
        Index("ix_us_usage_day", "tenant_id", "day"),
    )


class UsCoaccess(UlidPrimaryKey, Base):
    """Two datasets read by the same query, counted per day and source."""

    __tablename__ = "us_coaccess"

    tenant_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    dataset_a: Mapped[str] = mapped_column(String(255), nullable=False)
    dataset_b: Mapped[str] = mapped_column(String(255), nullable=False)
    day: Mapped[str] = mapped_column(String(10), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    queries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "dataset_a", "dataset_b", "day", "source", name="uq_us_coaccess"
        ),
        CheckConstraint("dataset_a < dataset_b", name="ck_us_coaccess_order"),
        Index("ix_us_coaccess_day", "tenant_id", "day"),
    )
