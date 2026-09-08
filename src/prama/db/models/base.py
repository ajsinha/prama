"""Declarative bases and the mixins every table shares.

**One base per logical database.** ``Base`` owns the platform and semantic-layer
schema; ``EvidenceBase`` will own the evidence ledger, which lives in its own
store with its own retention, its own immutability guarantees and its own
lifecycle. Keeping the metadata separate is not tidiness — it is what stops the
platform database's bootstrap from ever creating an evidence table, and what
lets the two be backed by different engines. DishtaYantra separates ``Base``
from ``FlowBase`` for exactly this reason, and the reason holds here.

The ORM models must agree with schema/*.sql, which is the authority. Agreement
is not assumed: ``tests/db/test_schema.py`` compares the two, including the
declared VARCHAR widths, so a column added in one place and forgotten in the
other fails the build.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from prama.core.clock import utc_now
from prama.core.ids import new_ulid
from prama.db.types import ULID_WIDTH, UtcDateTime


class ModelMixin:
    """Behaviour shared by every model, whichever base it belongs to."""

    def to_dict(self) -> dict[str, Any]:
        """Serialise the mapped columns. Relationships are deliberately not
        traversed: a ``to_dict`` that lazily loads is a latency bug waiting to
        be discovered in production."""
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}  # type: ignore[attr-defined]

    def __repr__(self) -> str:
        names = [c.name for c in self.__table__.primary_key]  # type: ignore[attr-defined]
        rendered = ", ".join(f"{n}={getattr(self, n)!r}" for n in names)
        return f"<{type(self).__name__} {rendered}>"


class Base(DeclarativeBase, ModelMixin):
    """The platform and semantic-layer database.

    Created from schema/sqlite.sql or schema/postgres.sql — never from this
    metadata. ``metadata.create_all`` is forbidden by an architecture test,
    because a second source of schema truth is how the two silently diverge.
    """


class EvidenceBase(DeclarativeBase, ModelMixin):
    """The evidence ledger, in its own database.

    Append-only, hash-linked, WORM-exportable, and retained for years after the
    platform data it describes has been archived. It is kept out of ``Base`` so
    that it can never be created, migrated or truncated by a platform operation.
    Populated in Wave 5.
    """


class UlidPrimaryKey:
    """A ULID primary key, minted client-side so a retry can reuse it."""

    id: Mapped[str] = mapped_column(String(ULID_WIDTH), primary_key=True, default=new_ulid)


class TenantScoped:
    """Belongs to exactly one tenant.

    Every tenant-scoped query filters on this column. Multi-tenancy enforced by
    discipline is multi-tenancy that leaks, so the scoping lives in the DAO
    signature rather than in the caller's memory.
    """

    tenant_id: Mapped[str] = mapped_column(String(ULID_WIDTH), nullable=False, index=True)


class CreatedAt:
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, default=utc_now)


class Timestamped(CreatedAt):
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, nullable=False, default=utc_now, onupdate=utc_now
    )
