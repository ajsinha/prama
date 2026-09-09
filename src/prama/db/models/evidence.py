"""The evidence ledger's tables.

Owned by ``EvidenceBase`` rather than ``Base``, which is not organisation but
enforcement: nothing that operates on the platform's metadata — a create_all, a
drop, a tenant cascade — can reach these. The ledger outlives the semantic
layer it describes and is retained for years after it.

Two absences here are deliberate and worth stating, because both look like
omissions:

* **No foreign key to any semantic table.** ``dataset``, ``control_id`` and
  ``plan_id`` are carried as plain values. A referential link would let a
  tenant deletion take the evidence of what was checked along with it, and that
  is exactly the record somebody would later need. It also means a record
  survives the retirement of the declaration it refers to, which is the normal
  case over a seven-year retention.
* **No mutable columns and no ``updated_at``.** There is no update path. The
  one exception is erasure, and it is not an update in the ordinary sense:
  content columns are blanked and the *original content hash* is preserved in
  ``tombstone_json``, so the chain still verifies across the gap and the
  erasure is visible rather than being a hole nobody can account for.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import CheckConstraint, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from prama.db.models.base import EvidenceBase, UlidPrimaryKey
from prama.db.types import ULID_WIDTH, JsonText


class EvRun(EvidenceBase, UlidPrimaryKey):
    """One execution: a batch of records produced together.

    Exists so "last night's run" is a thing that can be named. Without it, the
    only way to group records is by timestamp proximity, which silently merges
    two runs that overlapped and splits one that was slow.
    """

    __tablename__ = "ev_run"

    tenant_id: Mapped[str] = mapped_column(String(ULID_WIDTH), nullable=False)
    triggered_by: Mapped[str] = mapped_column(String(32), nullable=False, default="schedule")
    actor_id: Mapped[str | None] = mapped_column(String(ULID_WIDTH), nullable=True)
    engine: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    started_at: Mapped[str] = mapped_column(String(32), nullable=False)
    finished_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: A run that never finished is a fact about the estate, not a row to tidy
    #: away: its controls have no verdict, and a scorecard that silently
    #: omitted them would report the controls that did run as though they were
    #: all of them.
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")

    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'complete', 'failed', 'abandoned')",
            name="ck_ev_run_status",
        ),
        Index("ix_ev_run_tenant", "tenant_id", "started_at"),
    )


class EvRecord(EvidenceBase, UlidPrimaryKey):
    """One control, one scope, one moment. Append-only and hash-linked.

    The columns mirror :class:`prama.evidence.record.EvidenceRecord` field for
    field, and the DAO converts between them rather than either side reaching
    into the other. The hashes are stored rather than recomputed on read: a
    reader has to be able to detect that the stored content no longer hashes to
    the stored hash, and recomputing both would make that impossible.
    """

    __tablename__ = "ev_record"

    tenant_id: Mapped[str] = mapped_column(String(ULID_WIDTH), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    run_id: Mapped[str | None] = mapped_column(String(ULID_WIDTH), nullable=True)

    plan_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    control_id: Mapped[str] = mapped_column(String(ULID_WIDTH), nullable=False, default="")
    control_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    dataset: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    binding: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(JsonText, nullable=False, default=dict)
    parameters_json: Mapped[dict[str, Any]] = mapped_column(JsonText, nullable=False, default=dict)
    engine: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    coverage: Mapped[str] = mapped_column(String(32), nullable=False, default="full")
    verdict: Mapped[str] = mapped_column(String(32), nullable=False, default="error")
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JsonText, nullable=False, default=dict)
    samples_digest: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    finished_at: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    triggered_by: Mapped[str] = mapped_column(String(32), nullable=False, default="schedule")
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tombstone_json: Mapped[dict[str, Any] | None] = mapped_column(JsonText, nullable=True)

    previous_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    record_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1.0")

    __table_args__ = (
        CheckConstraint(
            "verdict IN ('pass', 'fail', 'warn', 'error', 'skipped', 'unknown')",
            name="ck_ev_record_verdict",
        ),
        CheckConstraint(
            "coverage IN ('full', 'incremental', 'forward_only')",
            name="ck_ev_record_coverage",
        ),
        # The constraint that makes a concurrent second writer fail loudly
        # instead of forking the chain.
        UniqueConstraint("tenant_id", "sequence", name="uq_ev_record_sequence"),
        UniqueConstraint("record_hash", name="uq_ev_record_hash"),
        Index("ix_ev_record_dataset", "tenant_id", "dataset", "finished_at"),
        Index("ix_ev_record_control", "control_id", "finished_at"),
        Index("ix_ev_record_run", "run_id"),
        Index("ix_ev_record_verdict", "tenant_id", "verdict", "finished_at"),
    )


class EvSample(EvidenceBase):
    """Failing rows, kept apart from the record that names them.

    Keyed by digest rather than by a ULID: the same failing rows recorded twice
    are one sample set, and a record refers to it by hash rather than owning
    it. That also means erasing one sample set erases it everywhere it is
    referenced, which is what a right-to-erasure request actually asks for.
    """

    __tablename__ = "ev_sample"

    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(ULID_WIDTH), nullable=False)
    rows_json: Mapped[list[dict[str, Any]]] = mapped_column(JsonText, nullable=False, default=list)
    masked_json: Mapped[list[str]] = mapped_column(JsonText, nullable=False, default=list)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    #: Samples expire on their own schedule, years before the records that name
    #: them: the rows are the personal data, the record is the audit trail, and
    #: putting the two on one clock means either discarding evidence early or
    #: holding personal data for seven years.
    expires_at: Mapped[str | None] = mapped_column(String(32), nullable=True)

    __table_args__ = (
        Index("ix_ev_sample_expiry", "expires_at"),
        Index("ix_ev_sample_tenant", "tenant_id"),
    )
