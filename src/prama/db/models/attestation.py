"""The attestation table.

Under ``Base`` rather than ``EvidenceBase``: an attestation is a governance
artefact *about* evidence, made by a person, and it references principals and
scopes that live in the platform schema. What it borrows from the ledger is the
discipline — it is never updated, and a correction is a new row.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from prama.db.models.base import Base, UlidPrimaryKey
from prama.db.types import ULID_WIDTH, JsonText


class AttAttestation(UlidPrimaryKey, Base):
    """One person's signed statement about one scope for one period."""

    __tablename__ = "att_attestation"

    tenant_id: Mapped[str] = mapped_column(
        String(ULID_WIDTH), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    attester_id: Mapped[str] = mapped_column(String(ULID_WIDTH), nullable=False)
    #: The name as it was at signing. Denormalised deliberately: an attestation
    #: reprinted years later must say who signed it, not who happens to hold
    #: that principal id now.
    attester_name: Mapped[str] = mapped_column(String(255), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(String(255), nullable=False)
    period_start: Mapped[str] = mapped_column(String(32), nullable=False)
    period_end: Mapped[str] = mapped_column(String(32), nullable=False)
    coverage_json: Mapped[dict[str, Any]] = mapped_column(JsonText, nullable=False, default=dict)
    exceptions_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JsonText, nullable=False, default=list
    )
    #: Ties the statement to the facts. Without it an attestation floats free
    #: of the records, and evidence written afterwards is indistinguishable
    #: from evidence written before.
    evidence_root: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    #: Named ``seal`` rather than ``signature``, because an HMAC proves the
    #: content was sealed by a holder of the key and proves nothing to anybody
    #: else. The column name is where that distinction is least likely to be
    #: lost.
    seal: Mapped[str] = mapped_column(String(64), nullable=False)
    signed_at: Mapped[str] = mapped_column(String(32), nullable=False)
    superseded_by: Mapped[str | None] = mapped_column(String(ULID_WIDTH), nullable=True)
    supersedes: Mapped[str | None] = mapped_column(String(ULID_WIDTH), nullable=True)
    supersedes_because: Mapped[str] = mapped_column(Text, nullable=False, default="")
    version: Mapped[str] = mapped_column(String(16), nullable=False, default="1.0")

    @property
    def is_current(self) -> bool:
        return self.superseded_by is None

    __table_args__ = (
        CheckConstraint("period_end >= period_start", name="ck_att_period"),
        Index("uq_att_content", "content_hash", unique=True),
        Index("ix_att_tenant", "tenant_id", "period_end"),
        Index("ix_att_scope", "tenant_id", "scope", "period_end"),
        Index("ix_att_attester", "attester_id"),
    )
