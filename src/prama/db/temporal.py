"""Bitemporal versioning.

Every declaration in the semantic layer is held as an **identity row** plus a
chain of **version rows**, along two independent time axes:

* **valid time** (``valid_from`` / ``valid_to``) — when the declaration was true
  of the world. Changing a fact closes one validity period and opens the next.
* **transaction time** (``recorded_at`` / ``superseded_at``) — when we believed
  it. Correcting a mistake supersedes a version without touching validity.

The two are separable because the questions differ, and after a correction they
have different answers:

    "What was the grain on 31 March?"                  -> valid time
    "What did we believe the grain was, on 31 March?"  -> transaction time

The second is the one an evidence record from March must resolve against, which
is why a single "updated_at" column is not enough for a system whose whole claim
is that its past can be reconstructed.

**Nothing is ever updated in place.** A partial unique index in the schema
enforces exactly one current version per entity, on both engines.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import Any, TypeVar

from sqlalchemy import Integer, Select, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from prama.core.clock import utc_now
from prama.db.types import UtcDateTime

V = TypeVar("V", bound="Versioned")


class Versioned:
    """The bitemporal columns shared by every version table."""

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    #: Business time. ``valid_to IS NULL`` means "still true".
    valid_from: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, default=utc_now)
    valid_to: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)

    #: System time. ``superseded_at IS NULL`` means "still believed".
    recorded_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, default=utc_now)
    superseded_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)

    authored_by: Mapped[str | None] = mapped_column(String(26), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(26), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    change_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # -- state -------------------------------------------------------------

    @property
    def is_current(self) -> bool:
        """The one version that is both still true and still believed."""
        return self.valid_to is None and self.superseded_at is None

    @property
    def is_superseded(self) -> bool:
        """Corrected: we no longer believe this version was ever right."""
        return self.superseded_at is not None

    @property
    def is_approved(self) -> bool:
        return self.approved_by is not None

    def was_valid_at(self, moment: datetime) -> bool:
        """Whether this version described the world at *moment*."""
        if moment < self.valid_from:
            return False
        return self.valid_to is None or moment < self.valid_to

    def was_believed_at(self, moment: datetime) -> bool:
        """Whether we held this version to be true at *moment*."""
        if moment < self.recorded_at:
            return False
        return self.superseded_at is None or moment < self.superseded_at

    def held_at(self, valid_at: datetime, known_at: datetime) -> bool:
        """The full bitemporal predicate: true then, and believed then."""
        return self.was_valid_at(valid_at) and self.was_believed_at(known_at)


@dataclasses.dataclass(frozen=True, slots=True)
class Provenance:
    """Who changed a declaration, when, and why.

    ``reason`` is required by the service layer rather than by the column,
    because an unexplained change to a Tier-1 declaration is an audit finding
    and the cheapest place to prevent it is at the point of authorship.
    """

    authored_by: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    reason: str = ""

    def apply_to(self, version: Versioned) -> None:
        version.authored_by = self.authored_by
        version.approved_by = self.approved_by
        version.approved_at = self.approved_at
        version.change_reason = self.reason


class TemporalQuery:
    """Builds the temporal predicates. One place, so they cannot drift.

    Hand-written ``WHERE superseded_at IS NULL`` clauses scattered through a
    codebase are how a bitemporal store quietly starts returning superseded
    rows in one query out of forty.
    """

    @staticmethod
    def current(statement: Select[Any], model: type[Any]) -> Select[Any]:
        """The present: still true, still believed."""
        return statement.where(model.valid_to.is_(None), model.superseded_at.is_(None))

    @staticmethod
    def believed_now_valid_at(
        statement: Select[Any], model: type[Any], valid_at: datetime
    ) -> Select[Any]:
        """What we believe *today* was true at *valid_at*.

        The usual historical question — "what was the grain in March?" — asked
        with the benefit of any corrections made since.
        """
        return statement.where(
            model.superseded_at.is_(None),
            model.valid_from <= valid_at,
            (model.valid_to.is_(None)) | (model.valid_to > valid_at),
        )

    @staticmethod
    def as_of(
        statement: Select[Any], model: type[Any], valid_at: datetime, known_at: datetime
    ) -> Select[Any]:
        """The full bitemporal question: true at *valid_at*, as believed at
        *known_at*.

        This is what an evidence record replays against. A control that ran in
        March must resolve the declaration March believed in, not the one a
        correction in June produced — otherwise the replay silently answers a
        different question and the divergence goes unnoticed.
        """
        return statement.where(
            model.recorded_at <= known_at,
            (model.superseded_at.is_(None)) | (model.superseded_at > known_at),
            model.valid_from <= valid_at,
            (model.valid_to.is_(None)) | (model.valid_to > valid_at),
        )

    @staticmethod
    def all_versions(statement: Select[Any], model: type[Any]) -> Select[Any]:
        """Everything, oldest first. For a history view or an audit export."""
        return statement.order_by(model.recorded_at, model.version)
