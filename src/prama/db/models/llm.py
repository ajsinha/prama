"""The LLM gateway's tables: providers, profiles, and the call ledger.

Under ``Base``: providers and profiles are managed configuration, and the call
ledger, although hash-chained, records what the *model layer* did rather than
what a control concluded, so it keeps the platform's retention rather than the
evidence store's.

Every column the later gateway phases use is declared now, because Prama has no
migrations and a column added in Wave 13 would be drift on every deployed
database (docs/23 §4, Wave 12).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import datetime
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from prama.core.clock import utc_now
from prama.db.models.base import Base, CreatedAt, UlidPrimaryKey
from prama.db.types import BoolInt, JsonText, UtcDateTime


class LlmProvider(UlidPrimaryKey, CreatedAt, Base):
    """A configured model endpoint. Holds a secret *reference*, never a secret."""

    __tablename__ = "llm_provider"

    tenant_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    dialect: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    hosting: Mapped[str] = mapped_column(String(16), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    region: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    credential_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    settings_json: Mapped[dict[str, Any]] = mapped_column(JsonText, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(BoolInt, nullable=False, default=True)
    created_by: Mapped[str | None] = mapped_column(String(26), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, nullable=False, default=utc_now, onupdate=utc_now
    )
    updated_by: Mapped[str | None] = mapped_column(String(26), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_llm_provider_name"),
        CheckConstraint(
            "hosting IN ('hosted', 'tenant', 'self_hosted')", name="ck_llm_provider_hosting"
        ),
        CheckConstraint("enabled IN (0, 1)", name="ck_llm_provider_enabled"),
    )


class LlmProfile(UlidPrimaryKey, CreatedAt, Base):
    """A purpose, and which of its versions is current."""

    __tablename__ = "llm_profile"

    tenant_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    purpose: Mapped[str] = mapped_column(String(64), nullable=False)
    current_version: Mapped[int | None] = mapped_column(Integer, nullable=True)

    versions: Mapped[list[LlmProfileVersion]] = relationship(
        back_populates="profile", lazy="selectin", order_by="LlmProfileVersion.version"
    )

    __table_args__ = (UniqueConstraint("tenant_id", "purpose", name="uq_llm_profile_purpose"),)


class LlmProfileVersion(UlidPrimaryKey, Base):
    """One immutable version of a profile: its parameters and its route."""

    __tablename__ = "llm_profile_version"

    profile_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("llm_profile.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    purpose_class: Mapped[str] = mapped_column(String(16), nullable=False, default="author")
    params_json: Mapped[dict[str, Any]] = mapped_column(JsonText, nullable=False, default=dict)
    overridable_json: Mapped[list[str]] = mapped_column(JsonText, nullable=False, default=list)
    max_sensitivity: Mapped[str] = mapped_column(String(16), nullable=False, default="internal")
    redactors_json: Mapped[list[str]] = mapped_column(JsonText, nullable=False, default=list)
    template_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    template_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timeout_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=60000)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    schema_repairs: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    cache_ttl_s: Mapped[int] = mapped_column(Integer, nullable=False, default=86400)
    fallback_across_hosting: Mapped[bool] = mapped_column(BoolInt, nullable=False, default=False)
    eval_run_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    recorded_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, default=utc_now)
    recorded_by: Mapped[str | None] = mapped_column(String(26), nullable=True)

    profile: Mapped[LlmProfile] = relationship(back_populates="versions")
    routes: Mapped[list[LlmProfileRoute]] = relationship(
        lazy="selectin", order_by="LlmProfileRoute.position"
    )

    __table_args__ = (
        UniqueConstraint("profile_id", "version", name="uq_llm_profile_version"),
        CheckConstraint(
            "purpose_class IN ('author', 'explain', 'summarise', 'embed')",
            name="ck_llm_profile_class",
        ),
        CheckConstraint("fallback_across_hosting IN (0, 1)", name="ck_llm_profile_fallback"),
    )


class LlmProfileRoute(Base):
    """One step of a profile version's route: try this provider and model."""

    __tablename__ = "llm_profile_route"

    profile_version_id: Mapped[str] = mapped_column(
        String(26),
        ForeignKey("llm_profile_version.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    provider_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("llm_provider.id"), nullable=False
    )
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    params_json: Mapped[dict[str, Any]] = mapped_column(JsonText, nullable=False, default=dict)


class LlmCall(UlidPrimaryKey, Base):
    """One model call, hash-chained per tenant. Hashes, never the text."""

    __tablename__ = "llm_call"

    tenant_id: Mapped[str] = mapped_column(String(26), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[str] = mapped_column(String(32), nullable=False)
    finished_at: Mapped[str] = mapped_column(String(32), nullable=False)
    principal_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    api_key_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    surface: Mapped[str] = mapped_column(String(32), nullable=False)
    purpose: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    profile_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    profile_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    template_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    template_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    provider_kind: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    hosting: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    destination_region: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    jurisdiction: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    sensitivity: Mapped[str] = mapped_column(String(16), nullable=False)
    model_requested: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    model_reported: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    model_version: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    price_model_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    payload_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    redactions_json: Mapped[dict[str, Any]] = mapped_column(JsonText, nullable=False, default=dict)
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cached_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_estimated: Mapped[bool] = mapped_column(BoolInt, nullable=False, default=False)
    cost_micros: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    fallback_from: Mapped[str | None] = mapped_column(String(26), nullable=True)
    served_from: Mapped[str] = mapped_column(String(16), nullable=False, default="provider")
    schema_valid: Mapped[bool | None] = mapped_column(BoolInt, nullable=True)
    grammar_enforced: Mapped[bool] = mapped_column(BoolInt, nullable=False, default=False)
    outcome: Mapped[str] = mapped_column(String(24), nullable=False)
    outcome_detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    previous_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    record_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "sequence", name="uq_llm_call_sequence"),
        CheckConstraint(
            "served_from IN ('provider', 'cache', 'replay')", name="ck_llm_call_served"
        ),
        CheckConstraint(
            "outcome IN ('ok', 'incomplete', 'refused_policy', 'refused_budget', "
            "'refused_rate', 'error', 'cancelled')",
            name="ck_llm_call_outcome",
        ),
        CheckConstraint(
            "tokens_estimated IN (0, 1) AND grammar_enforced IN (0, 1) "
            "AND (schema_valid IS NULL OR schema_valid IN (0, 1))",
            name="ck_llm_call_flags",
        ),
        Index("ix_llm_call_started", "tenant_id", "started_at"),
    )
