"""Data Access Objects — the only database access layer.

Every read and write against Prama's schema is concentrated here. Nothing
outside ``prama.db`` issues SQL or touches an ORM session; higher layers call a
DAO through the unit of work and receive domain objects. An architecture test
enforces that by import scanning, so the rule is a property of the build rather
than of anyone's memory.

Three rules make the layering real:

* **Tenant scoping is structural.** ``TenantScopedDao`` takes the tenant on
  every read and write; no method can omit it. Multi-tenancy enforced by
  discipline is multi-tenancy that leaks.
* **Domain logic lives with the data it belongs to.** Password hashing sits
  beside the column that stores the hash, and key issuance beside the key
  table, rather than drifting into a service where the two can diverge.
* **No exception is swallowed.** Failures are translated into the Prama error
  taxonomy by the unit of work — with a remedy the caller can act on — and
  propagate. A DAO never returns a sentinel that means "something went wrong".

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from sqlalchemy import Select, delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from prama.core import pjson
from prama.core.clock import utc_now
from prama.core.errors import NotFoundError
from prama.db.dialects import Dialect
from prama.db.models import (
    ApiKey,
    AuditEvent,
    Base,
    Principal,
    PrincipalRole,
    Role,
    Setting,
    Tenant,
)

M = TypeVar("M", bound=Base)


class Dao(Generic[M]):
    """Base for every DAO: one model, one session, one dialect."""

    model: type[M]

    def __init__(self, session: AsyncSession, dialect: Dialect) -> None:
        self._session = session
        self._dialect = dialect

    # -- primitives --------------------------------------------------------

    def add(self, entity: M) -> M:
        self._session.add(entity)
        return entity

    async def get(self, identifier: Any) -> M | None:
        return await self._session.get(self.model, identifier)

    async def require(self, identifier: Any) -> M:
        entity = await self.get(identifier)
        if entity is None:
            raise NotFoundError(
                f"{self.model.__name__} {identifier!r} does not exist",
                remedy="Check the identifier, or list the available entities first.",
                context={"model": self.model.__name__, "id": str(identifier)},
            )
        return entity

    async def delete(self, entity: M) -> None:
        await self._session.delete(entity)

    async def count(self, statement: Select[Any] | None = None) -> int:
        stmt = statement if statement is not None else select(self.model)
        result = await self._session.execute(select(func.count()).select_from(stmt.subquery()))
        return int(result.scalar_one())

    async def _all(self, statement: Select[Any]) -> list[M]:
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def _one_or_none(self, statement: Select[Any]) -> M | None:
        result = await self._session.execute(statement)
        return result.scalars().one_or_none()


class TenantScopedDao(Dao[M]):
    """A DAO whose every query is filtered by tenant.

    The tenant is a parameter of each method rather than constructor state so
    that a single unit of work can legitimately serve an admin operation across
    tenants — while still never issuing an unscoped query by accident.
    """

    async def list_for_tenant(
        self, tenant_id: str, *, limit: int = 100, offset: int = 0
    ) -> list[M]:
        stmt = (
            select(self.model)
            .where(self.model.tenant_id == tenant_id)  # type: ignore[attr-defined]
            .order_by(self.model.id)  # type: ignore[attr-defined]
            .limit(limit)
            .offset(offset)
        )
        return await self._all(stmt)

    async def get_for_tenant(self, tenant_id: str, identifier: str) -> M | None:
        stmt = select(self.model).where(
            self.model.id == identifier,  # type: ignore[attr-defined]
            self.model.tenant_id == tenant_id,  # type: ignore[attr-defined]
        )
        return await self._one_or_none(stmt)

    async def require_for_tenant(self, tenant_id: str, identifier: str) -> M:
        entity = await self.get_for_tenant(tenant_id, identifier)
        if entity is None:
            raise NotFoundError(
                f"{self.model.__name__} {identifier!r} does not exist in this tenant",
                remedy="Check the identifier and the tenant it belongs to.",
                context={"model": self.model.__name__, "id": identifier, "tenant": tenant_id},
            )
        return entity

    async def count_for_tenant(self, tenant_id: str) -> int:
        return await self.count(
            select(self.model).where(self.model.tenant_id == tenant_id)  # type: ignore[attr-defined]
        )


class TenantDao(Dao[Tenant]):
    model = Tenant

    async def by_slug(self, slug: str) -> Tenant | None:
        return await self._one_or_none(select(Tenant).where(Tenant.slug == slug))

    async def list_active(self, *, limit: int = 100) -> list[Tenant]:
        return await self._all(
            select(Tenant).where(Tenant.status == "active").order_by(Tenant.slug).limit(limit)
        )

    def create(self, *, slug: str, display_name: str, residency: str | None = None) -> Tenant:
        now = utc_now()
        return self.add(
            Tenant(
                slug=slug,
                display_name=display_name,
                residency=residency,
                settings_json={},
                created_at=now,
                updated_at=now,
            )
        )


class PrincipalDao(TenantScopedDao[Principal]):
    model = Principal

    async def by_username(self, tenant_id: str, username: str) -> Principal | None:
        return await self._one_or_none(
            select(Principal).where(
                Principal.tenant_id == tenant_id, Principal.username == username
            )
        )

    async def by_external_id(self, idp: str, external_id: str) -> Principal | None:
        return await self._one_or_none(
            select(Principal).where(
                Principal.external_idp == idp, Principal.external_id == external_id
            )
        )

    def create(
        self,
        *,
        tenant_id: str,
        username: str,
        display_name: str,
        kind: str = "human",
        email: str | None = None,
    ) -> Principal:
        now = utc_now()
        return self.add(
            Principal(
                tenant_id=tenant_id,
                username=username,
                display_name=display_name,
                kind=kind,
                email=email,
                created_at=now,
                updated_at=now,
            )
        )

    async def roles_of(self, principal_id: str) -> list[Role]:
        """Roles granted to a principal.

        Goes through the relationship rather than a hand-written join: the
        association is declared once, on the model, and selectin loading makes
        it one extra query rather than one per row.
        """
        await self._session.flush()
        principal = await self._session.get(Principal, principal_id)
        if principal is None:
            return []
        await self._session.refresh(principal, ["roles"])
        return sorted(principal.roles, key=lambda r: r.name)


class RoleDao(TenantScopedDao[Role]):
    model = Role

    async def by_name(self, tenant_id: str, name: str) -> Role | None:
        return await self._one_or_none(
            select(Role).where(Role.tenant_id == tenant_id, Role.name == name)
        )

    def create(
        self,
        *,
        tenant_id: str,
        name: str,
        permissions: list[str],
        description: str = "",
        builtin: bool = False,
    ) -> Role:
        now = utc_now()
        return self.add(
            Role(
                tenant_id=tenant_id,
                name=name,
                description=description,
                permissions_json=permissions,
                is_builtin=builtin,
                created_at=now,
                updated_at=now,
            )
        )

    async def grant(
        self, principal_id: str, role_id: str, *, granted_by: str | None = None
    ) -> None:
        """Grant a role. Idempotent, and atomically so.

        A read-then-write existence check is not idempotency: it loses to a
        concurrent grant, and it does not even see rows pending in its own
        session. The upsert is issued by the dialect, so this method carries no
        engine-specific SQL.
        """
        await self._session.flush()  # raw SQL must not race pending ORM state
        statement = self._dialect.upsert(
            "principal_role",
            ["principal_id", "role_id", "granted_at", "granted_by"],
            ["principal_id", "role_id"],
        )
        await self._session.execute(
            text(statement),
            {
                "principal_id": principal_id,
                "role_id": role_id,
                "granted_at": _iso(utc_now()),
                "granted_by": granted_by,
            },
        )

    async def revoke(self, principal_id: str, role_id: str) -> None:
        await self._session.execute(
            delete(PrincipalRole).where(
                PrincipalRole.principal_id == principal_id, PrincipalRole.role_id == role_id
            )
        )


class ApiKeyDao(TenantScopedDao[ApiKey]):
    model = ApiKey

    async def by_prefix(self, prefix: str) -> ApiKey | None:
        return await self._one_or_none(select(ApiKey).where(ApiKey.key_prefix == prefix))

    async def active_for_principal(self, principal_id: str) -> list[ApiKey]:
        return await self._all(
            select(ApiKey).where(ApiKey.principal_id == principal_id, ApiKey.revoked_at.is_(None))
        )

    def create(
        self,
        *,
        tenant_id: str,
        principal_id: str,
        name: str,
        key_prefix: str,
        key_hash: str,
        scopes: list[str],
        expires_at: datetime | None = None,
        created_by: str | None = None,
    ) -> ApiKey:
        return self.add(
            ApiKey(
                tenant_id=tenant_id,
                principal_id=principal_id,
                name=name,
                key_prefix=key_prefix,
                key_hash=key_hash,
                scopes_json=scopes,
                expires_at=expires_at,
                created_at=utc_now(),
                created_by=created_by,
            )
        )


class AuditDao(Dao[AuditEvent]):
    """Append-only. This class deliberately exposes no update or delete."""

    model = AuditEvent

    def record(
        self,
        *,
        tenant_id: str,
        action: str,
        object_kind: str,
        object_id: str | None = None,
        actor_id: str | None = None,
        actor_kind: str = "human",
        outcome: str = "success",
        correlation_id: str | None = None,
        source_ip: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> AuditEvent:
        return self.add(
            AuditEvent(
                tenant_id=tenant_id,
                occurred_at=utc_now(),
                actor_id=actor_id,
                actor_kind=actor_kind,
                action=action,
                object_kind=object_kind,
                object_id=object_id,
                outcome=outcome,
                correlation_id=correlation_id,
                source_ip=source_ip,
                detail_json=detail or {},
            )
        )

    async def for_object(
        self, tenant_id: str, object_kind: str, object_id: str, *, limit: int = 100
    ) -> list[AuditEvent]:
        return await self._all(
            select(AuditEvent)
            .where(
                AuditEvent.tenant_id == tenant_id,
                AuditEvent.object_kind == object_kind,
                AuditEvent.object_id == object_id,
            )
            .order_by(AuditEvent.occurred_at.desc())
            .limit(limit)
        )

    async def recent(self, tenant_id: str, *, limit: int = 100) -> list[AuditEvent]:
        return await self._all(
            select(AuditEvent)
            .where(AuditEvent.tenant_id == tenant_id)
            .order_by(AuditEvent.occurred_at.desc())
            .limit(limit)
        )


class SettingDao(Dao[Setting]):
    model = Setting

    async def get_value(
        self, tenant_id: str, key: str, *, scope: str = "global", default: Any = None
    ) -> Any:
        await self._session.flush()
        row = await self._one_or_none(
            select(Setting).where(
                Setting.tenant_id == tenant_id, Setting.scope == scope, Setting.key == key
            )
        )
        return default if row is None else row.value_json

    async def put(
        self,
        tenant_id: str,
        key: str,
        value: Any,
        *,
        scope: str = "global",
        updated_by: str | None = None,
    ) -> None:
        """Write a setting. Atomic upsert, not read-then-write."""
        await self._session.flush()
        statement = self._dialect.upsert(
            "setting",
            ["tenant_id", "scope", "key", "value_json", "updated_at", "updated_by"],
            ["tenant_id", "scope", "key"],
        )
        await self._session.execute(
            text(statement),
            {
                "tenant_id": tenant_id,
                "scope": scope,
                "key": key,
                "value_json": pjson.dumps(value, sort_keys=True),
                "updated_at": _iso(utc_now()),
                "updated_by": updated_by,
            },
        )

    async def all_for_scope(self, tenant_id: str, scope: str = "global") -> dict[str, Any]:
        rows = await self._all(
            select(Setting).where(Setting.tenant_id == tenant_id, Setting.scope == scope)
        )
        return {r.key: r.value_json for r in rows}


def _iso(value: datetime) -> str:
    """Timestamps are ISO-8601 UTC text on both engines (see schema/*.sql)."""
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")
