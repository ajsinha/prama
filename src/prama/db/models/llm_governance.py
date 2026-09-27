"""Prompt templates, stored payloads and evaluation runs: the governance of model use.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from prama.db.models.base import Base, UlidPrimaryKey


class LlmTemplate(UlidPrimaryKey, Base):
    __tablename__ = "llm_template"

    tenant_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    current_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_llm_template_name"),)


class LlmTemplateVersion(UlidPrimaryKey, Base):
    __tablename__ = "llm_template_version"

    template_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("llm_template.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    system_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False)
    variables_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    response_schema_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    eval_run_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    recorded_at: Mapped[str] = mapped_column(String(32), nullable=False)
    recorded_by: Mapped[str | None] = mapped_column(String(26), nullable=True)
    approved_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(26), nullable=True)

    __table_args__ = (
        UniqueConstraint("template_id", "version", name="uq_llm_template_version"),
        CheckConstraint(
            "status IN ('draft', 'approved', 'retired')", name="ck_llm_template_status"
        ),
    )


class LlmPayload(Base):
    __tablename__ = "llm_payload"

    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    request_json: Mapped[str] = mapped_column(Text, nullable=False)
    response_json: Mapped[str] = mapped_column(Text, nullable=False, default="")
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    expires_at: Mapped[str | None] = mapped_column(String(32), nullable=True)

    __table_args__ = (
        CheckConstraint("mode IN ('redacted', 'full', 'expired')", name="ck_llm_payload_mode"),
        Index("ix_llm_payload_expiry", "expires_at"),
    )


class LlmEvalRun(UlidPrimaryKey, Base):
    __tablename__ = "llm_eval_run"

    tenant_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    suite: Mapped[str] = mapped_column(String(128), nullable=False)
    suite_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    purpose: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    profile_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    profile_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    template_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    template_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    passed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    report_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    started_at: Mapped[str] = mapped_column(String(32), nullable=False)
    finished_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    started_by: Mapped[str | None] = mapped_column(String(26), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'passed', 'failed', 'error')", name="ck_llm_eval_status"
        ),
        Index("ix_llm_eval_run_subject", "tenant_id", "profile_id", "template_id"),
    )
