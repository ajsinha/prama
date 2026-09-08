"""Platform tables: tenancy, identity, audit, coordination, settings.

Column types are restricted to ``TEXT``, ``INTEGER`` and ``REAL`` (through the
portable decorators in ``prama.db.types``) so that the ORM, schema/sqlite.sql
and schema/postgres.sql describe one schema rather than three.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from prama.db.models.base import Base, CreatedAt, Timestamped, UlidPrimaryKey
from prama.db.types import BoolInt, JsonText, UtcDateTime


class SchemaState(Base):
    """What this database believes it is.

    Deliberately *not* a migration table. It records the digest of the schema
    file that was applied so that drift between the file and the live database
    is detectable, and it holds exactly one row.
    """

    __tablename__ = "schema_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    dialect: Mapped[str] = mapped_column(String(16), nullable=False)
    file_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    applied_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    applied_by: Mapped[str] = mapped_column(String(255), nullable=False)
    product_version: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (CheckConstraint("id = 1", name="ck_schema_state_singleton"),)


class Tenant(UlidPrimaryKey, Timestamped, Base):
    """The isolation boundary."""

    __tablename__ = "tenant"

    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    residency: Mapped[str | None] = mapped_column(String(64), nullable=True)
    settings_json: Mapped[dict[str, Any]] = mapped_column(JsonText, nullable=False, default=dict)

    #: selectin loading throughout: one extra query per collection rather than
    #: one per parent row, which is the difference between a list screen that
    #: renders and one that melts under an N+1.
    principals: Mapped[list[Principal]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan", lazy="selectin"
    )
    roles: Mapped[list[Role]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        UniqueConstraint("slug", name="uq_tenant_slug"),
        CheckConstraint("status IN ('active', 'suspended', 'retired')", name="ck_tenant_status"),
    )


class Principal(UlidPrimaryKey, Timestamped, Base):
    """A human or a service account."""

    __tablename__ = "principal"

    tenant_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    username: Mapped[str] = mapped_column(String(128), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="human")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_idp: Mapped[str | None] = mapped_column(String(64), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(512), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)

    tenant: Mapped[Tenant] = relationship(back_populates="principals", lazy="joined")
    roles: Mapped[list[Role]] = relationship(
        secondary="principal_role", back_populates="principals", lazy="selectin", viewonly=True
    )
    api_keys: Mapped[list[ApiKey]] = relationship(
        back_populates="principal", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def role_names(self) -> list[str]:
        """Role names, sorted, for stable output in APIs and logs."""
        return sorted(role.name for role in self.roles)

    def has_permission(self, permission: str) -> bool:
        """True if any granted role carries *permission*.

        Wildcards are supported one level deep: a role holding ``control:*``
        satisfies ``control:approve``. Deeper globbing is deliberately absent —
        a permission model nobody can hold in their head is one nobody audits.
        """
        for role in self.roles:
            for granted in role.permissions_json:
                if granted in ("*", permission):
                    return True
                if granted.endswith(":*") and permission.startswith(granted[:-1]):
                    return True
        return False

    __table_args__ = (
        UniqueConstraint("tenant_id", "username", name="uq_principal_tenant_username"),
        Index("ix_principal_tenant_status", "tenant_id", "status"),
        CheckConstraint("kind IN ('human', 'service')", name="ck_principal_kind"),
        CheckConstraint("status IN ('active', 'disabled', 'locked')", name="ck_principal_status"),
    )


class Role(UlidPrimaryKey, Timestamped, Base):
    """A named bundle of permissions."""

    __tablename__ = "role"

    tenant_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    permissions_json: Mapped[list[str]] = mapped_column(JsonText, nullable=False, default=list)
    is_builtin: Mapped[bool] = mapped_column(BoolInt, nullable=False, default=False)

    tenant: Mapped[Tenant] = relationship(back_populates="roles", lazy="joined")
    principals: Mapped[list[Principal]] = relationship(
        secondary="principal_role", back_populates="roles", lazy="selectin", viewonly=True
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_role_tenant_name"),
        CheckConstraint("is_builtin IN (0, 1)", name="ck_role_is_builtin"),
    )


class PrincipalRole(Base):
    """Grant of a role to a principal."""

    __tablename__ = "principal_role"

    principal_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("principal.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("role.id", ondelete="CASCADE"), primary_key=True
    )
    granted_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    granted_by: Mapped[str | None] = mapped_column(String(26), nullable=True)

    __table_args__ = (Index("ix_principal_role_role", "role_id"),)


class ApiKey(UlidPrimaryKey, CreatedAt, Base):
    """An API credential. Only the hash is stored; the plaintext is shown once."""

    __tablename__ = "api_key"

    tenant_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    principal_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("principal.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(32), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    scopes_json: Mapped[list[str]] = mapped_column(JsonText, nullable=False, default=list)
    expires_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(26), nullable=True)

    principal: Mapped[Principal] = relationship(back_populates="api_keys", lazy="joined")

    def is_valid_at(self, moment: datetime) -> bool:
        """Usable at *moment*: neither revoked nor expired."""
        if self.revoked_at is not None:
            return False
        return not (self.expires_at is not None and self.expires_at <= moment)

    __table_args__ = (
        UniqueConstraint("key_prefix", name="uq_api_key_prefix"),
        Index("ix_api_key_principal", "principal_id"),
    )


class AuditEvent(UlidPrimaryKey, Base):
    """Append-only record of who did what.

    No code path in Prama issues UPDATE or DELETE against this table. Retention
    is enforced by archival, never by mutation.
    """

    __tablename__ = "audit_event"

    tenant_id: Mapped[str] = mapped_column(String(26), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    actor_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="human")
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    object_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    object_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False, default="success")
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail_json: Mapped[dict[str, Any]] = mapped_column(JsonText, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_audit_tenant_time", "tenant_id", "occurred_at"),
        Index("ix_audit_object", "object_kind", "object_id"),
        Index("ix_audit_actor", "actor_id", "occurred_at"),
        CheckConstraint(
            "actor_kind IN ('human', 'service', 'system', 'agent')", name="ck_audit_actor_kind"
        ),
        CheckConstraint("outcome IN ('success', 'failure', 'denied')", name="ck_audit_outcome"),
    )


class LeaseRow(Base):
    """A held lease. One row per resource, fleet-wide."""

    __tablename__ = "lease"

    resource: Mapped[str] = mapped_column(String(255), primary_key=True)
    holder: Mapped[str] = mapped_column(String(255), nullable=False)
    token: Mapped[str] = mapped_column(String(26), nullable=False)
    fencing_token: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    acquired_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JsonText, nullable=False, default=dict)

    __table_args__ = (Index("ix_lease_expires", "expires_at"),)


class Setting(Base):
    """Runtime configuration owned by a tenant.

    Never a substitute for ``config/application.yaml``, which holds the
    deployment's own settings; this is for values a user changes in the product.
    """

    __tablename__ = "setting"

    tenant_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    scope: Mapped[str] = mapped_column(String(128), primary_key=True, default="global")
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value_json: Mapped[Any] = mapped_column(JsonText, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String(26), nullable=True)
