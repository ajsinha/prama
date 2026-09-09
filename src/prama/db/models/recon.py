"""The reconciliation break queue.

Under ``Base``, not ``EvidenceBase``, and the distinction is the whole design.
The ledger records what a reconciliation *concluded*; this records what people
are *doing about it*. Working state is mutable — a break gets assigned,
explained, accepted — where evidence is not, and putting the two in one store
would either make the ledger writable or make the queue unusable.

Three things must not move, and the columns rather than the callers are what
keep them still:

* ``first_seen`` is set once. A break re-detected for forty days is forty days
  old, and a queue that stamps each sighting with today reports every break as
  new every morning.
* ``cleared_at`` is set by absence, not by an announcement. No reconciliation
  tells you a break has gone; it simply stops reporting it.
* Nothing is deleted. "We had four hundred breaks and they cleared" and "we had
  four hundred breaks" are the same sentence in a system that forgets.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from prama.db.models.base import Base, UlidPrimaryKey
from prama.db.types import ULID_WIDTH, JsonText


class RecBreak(UlidPrimaryKey, Base):
    """One difference between two systems, tracked across the runs it appears in."""

    __tablename__ = "rec_break"

    tenant_id: Mapped[str] = mapped_column(
        String(ULID_WIDTH), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    #: Which reconciliation produced it. A break key is unique only within its
    #: own definition; two reconciliations over the same accounts would collide
    #: and each would clear the other's breaks.
    definition: Mapped[str] = mapped_column(String(255), nullable=False)
    break_key: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    #: Text, not REAL. These are money, and binary floating point manufactures
    #: exactly the small discrepancies a reconciliation exists to find.
    left_value: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    right_value: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    difference: Mapped[str] = mapped_column(String(64), nullable=False, default="0")
    because: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: What normalisation did to get here. The first question about any break is
    #: whether it is real or a translation error, and this answers it.
    normalisation_json: Mapped[list[str]] = mapped_column(JsonText, nullable=False, default=list)
    aggregated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_seen: Mapped[str] = mapped_column(String(32), nullable=False)
    last_seen: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    owner: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    accepted_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: Appended to, never rewritten. The disposition history is the reason a
    #: carried break is defensible years later.
    comments_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JsonText, nullable=False, default=list
    )
    cleared_at: Mapped[str | None] = mapped_column(String(32), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "kind IN ('timing', 'fx', 'rounding', 'missing', 'extra', "
            "'duplicate', 'sign', 'genuine')",
            name="ck_rec_break_kind",
        ),
        CheckConstraint(
            "state IN ('open', 'assigned', 'explained', 'cleared', 'accepted')",
            name="ck_rec_break_state",
        ),
        CheckConstraint("aggregated IN (0, 1)", name="ck_rec_break_aggregated"),
        CheckConstraint("last_seen >= first_seen", name="ck_rec_break_seen"),
        Index("uq_rec_break_key", "tenant_id", "definition", "break_key", unique=True),
        Index("ix_rec_break_open", "tenant_id", "definition", "state", "first_seen"),
        Index("ix_rec_break_owner", "tenant_id", "owner"),
    )


__all__ = ["RecBreak"]
