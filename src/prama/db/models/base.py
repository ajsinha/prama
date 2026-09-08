"""The declarative base and the mixins every table shares.

The ORM models here must agree with schema/*.sql, which is the authority.
Agreement is not assumed: ``tests/db/test_model_schema_agreement.py`` reflects
the schema file into a scratch database and compares it with this metadata, so
a column added in one place and forgotten in the other fails the build.

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


class Base(DeclarativeBase):
    """Root of Prama's ORM metadata."""

    def to_dict(self) -> dict[str, Any]:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

    def __repr__(self) -> str:
        names = [c.name for c in self.__table__.primary_key]
        rendered = ", ".join(f"{n}={getattr(self, n)!r}" for n in names)
        return f"<{type(self).__name__} {rendered}>"


class UlidPrimaryKey:
    """A ULID primary key, minted client-side so a retry can reuse it."""

    id: Mapped[str] = mapped_column(String(ULID_WIDTH), primary_key=True, default=new_ulid)


class TenantScoped:
    """Belongs to exactly one tenant.

    Every tenant-scoped query filters on this column, and an architecture test
    will grow to assert that no repository method omits it. Multi-tenancy is
    the one property that cannot be retrofitted.
    """

    tenant_id: Mapped[str] = mapped_column(String(ULID_WIDTH), nullable=False, index=True)


class CreatedAt:
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, default=utc_now)


class Timestamped(CreatedAt):
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, nullable=False, default=utc_now, onupdate=utc_now
    )
