"""The control estate.

Bitemporal, like every other declaration in Prama, and for the same reason.
Editing a threshold is an **amend**: the old threshold really was the rule
until Tuesday, and an evidence record written on Monday must still resolve to
the control that was actually in force when it ran. Discovering that a control
was wrong all along is a **correct**: it supersedes without touching validity,
so the mistaken belief stays visible on the transaction-time axis. Conflating
the two destroys replay, and the destruction is silent.

The PQL text is the authority. ``plan_id``, ``severity``, ``dimensions_json``
and ``criticality`` are derived from it when a version is written and are never
accepted from a caller — they are columns so the estate can be queried without
parsing every control, not a second source of truth. ``ControlDao`` computes
them, and a test re-lowers the stored text and compares.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from prama.db.models.base import Base, CreatedAt, UlidPrimaryKey
from prama.db.temporal import Versioned
from prama.db.types import ULID_WIDTH, JsonText


class CtlControl(UlidPrimaryKey, CreatedAt, Base):
    """Identity of a control. Immutable.

    ``identity`` is derived from what the control is *about* — the declaration,
    the rule, the subject — and deliberately not from its text, so re-running a
    generator after an edit amends this control rather than orphaning it and
    creating another. Without that, the review queue fills with controls that
    already exist and nobody recognises the estate.
    """

    __tablename__ = "ctl_control"

    tenant_id: Mapped[str] = mapped_column(
        String(ULID_WIDTH), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    identity: Mapped[str] = mapped_column(String(64), nullable=False)

    versions: Mapped[list[CtlControlVersion]] = relationship(
        back_populates="control", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (Index("ix_ctl_control_tenant", "tenant_id"),)


class CtlControlVersion(UlidPrimaryKey, Versioned, Base):
    """One version of a control."""

    __tablename__ = "ctl_control_version"

    control_id: Mapped[str] = mapped_column(
        String(ULID_WIDTH), ForeignKey("ctl_control.id", ondelete="CASCADE"), nullable=False
    )

    #: The authority. Everything below it is derived from this text.
    pql: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    dataset: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    #: The content-addressed plan this text lowers to. An evidence record names
    #: it, so a verdict traces to exactly what executed rather than to a row
    #: that happened to point at it.
    plan_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    severity: Mapped[str] = mapped_column(String(32), nullable=False, default="major")
    dimensions_json: Mapped[list[str]] = mapped_column(JsonText, nullable=False, default=list)
    criticality: Mapped[int] = mapped_column(Integer, nullable=False, default=4)

    origin: Mapped[str] = mapped_column(String(32), nullable=False, default="declaration")
    rule: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    source_ref: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    provenance_json: Mapped[dict[str, Any]] = mapped_column(JsonText, nullable=False, default=dict)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="proposed")
    #: Required together with the status. A control silenced with no expiry and
    #: no reason is a control nobody will ever turn back on, and the constraint
    #: is in the schema rather than in a service because that is the failure
    #: that happens at 3am under pressure.
    suppressed_until: Mapped[str | None] = mapped_column(String(32), nullable=True)
    suppressed_because: Mapped[str | None] = mapped_column(Text, nullable=True)
    schedule: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    owner_id: Mapped[str | None] = mapped_column(String(ULID_WIDTH), nullable=True)

    control: Mapped[CtlControl] = relationship(back_populates="versions", lazy="joined")

    @property
    def is_live(self) -> bool:
        """Whether this control will actually run.

        ``proposed`` is not live and neither is ``suppressed``: both are
        states a reader is likely to mistake for running, and a scorecard that
        counted them would report coverage it does not have.
        """
        return self.status == "active"

    @property
    def is_silenced(self) -> bool:
        return self.status == "suppressed"

    __table_args__ = (
        CheckConstraint(
            "status IN ('proposed', 'active', 'suppressed', 'retired')",
            name="ck_ctl_control_status",
        ),
        CheckConstraint(
            "severity IN ('info', 'warning', 'minor', 'major', 'critical')",
            name="ck_ctl_control_severity",
        ),
        CheckConstraint(
            "origin IN ('declaration', 'import', 'document', 'mining', 'example', 'induction')",
            name="ck_ctl_control_origin",
        ),
        CheckConstraint("criticality BETWEEN 1 AND 4", name="ck_ctl_control_criticality"),
        CheckConstraint(
            "status <> 'suppressed' OR "
            "(suppressed_until IS NOT NULL AND suppressed_because IS NOT NULL)",
            name="ck_ctl_control_suppression",
        ),
        Index("ix_ctl_control_version_entity", "control_id", "recorded_at"),
        Index("ix_ctl_control_version_dataset", "dataset", "status"),
        Index("ix_ctl_control_version_plan", "plan_id"),
    )


class CtlRejection(UlidPrimaryKey, Base):
    """A proposal somebody turned down.

    Recorded rather than deleted. A rejection is a training signal, and
    re-proposing something a steward has already refused is the fastest way to
    lose their attention — so the generator consults this table before it
    offers anything.

    Keyed on ``(identity, content_hash)`` rather than identity alone, which is
    the distinction that keeps it useful: rejecting a control does not reject
    every future version of it. A materially different rewrite of the same rule
    is a new question and gets asked again.
    """

    __tablename__ = "ctl_rejection"

    tenant_id: Mapped[str] = mapped_column(
        String(ULID_WIDTH), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    identity: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    reason: Mapped[str] = mapped_column(String(32), nullable=False, default="incorrect")
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    rejected_by: Mapped[str | None] = mapped_column(String(ULID_WIDTH), nullable=True)
    rejected_at: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "reason IN ('incorrect', 'not_material', 'coincidental', 'duplicate', "
            "'too_noisy', 'pending_remediation')",
            name="ck_ctl_rejection_reason",
        ),
    )
