"""Platform data access: tenancy, identity, audit and settings.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select, text

from prama.core import pjson
from prama.core.clock import utc_now
from prama.core.errors import ConflictError, ValidationError
from prama.db.dao.base import Dao, TenantScopedDao
from prama.db.models import (
    ApiKey,
    AuditEvent,
    Principal,
    PrincipalRole,
    Role,
    Setting,
    Tenant,
)
from prama.db.security import PasswordHasher


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


#: Below this, a password is not worth hashing. Length is the only property
#: that reliably helps; character-class rules demonstrably push people towards
#: Password1! and away from anything longer.
MINIMUM_PASSWORD = 12

#: A well-formed hash of nothing anybody knows, verified against when the
#: username does not exist so that both paths cost the same. Computed once at
#: import rather than per call, because deriving it on every failed sign-in
#: would double the cost of exactly the request an attacker floods.
_DUMMY_HASH = PasswordHasher().hash(secrets.token_urlsafe(32))


class PrincipalDao(TenantScopedDao[Principal]):
    model = Principal

    async def by_username(self, tenant_id: str, username: str) -> Principal | None:
        return await self._one_or_none(
            select(Principal).where(
                Principal.tenant_id == tenant_id, Principal.username == username
            )
        )

    async def by_external_id(
        self, idp: str, external_id: str, *, tenant_id: str | None = None
    ) -> Principal | None:
        """The principal an identity provider's subject maps to.

        The tenant is optional here, and deliberately so: this is a step in
        authentication, which runs *before* a tenant is known. Requiring one
        would need the answer before the question — the same reason
        `ApiKeyDao.by_prefix` is unscoped.

        What was wrong was the ambiguous case. `(external_idp, external_id)` has
        no uniqueness constraint, and two estates federating with the same
        provider will legitimately see the same subject — a contractor at two
        banks is not an error. `_one_or_none` met that with a raw, untranslated
        `MultipleResultsFound`, so the sign-in path would have crashed rather
        than refusing (QA finding DB-142).

        Now it refuses, and says what to do: pass the tenant when the caller
        knows it. Guessing which of two principals was meant is the one thing
        an authentication path must never do.
        """
        stmt = select(Principal).where(
            Principal.external_idp == idp, Principal.external_id == external_id
        )
        if tenant_id is not None:
            stmt = stmt.where(Principal.tenant_id == tenant_id)
        matches = list((await self._session.execute(stmt)).scalars().all())
        if len(matches) > 1:
            raise ConflictError(
                "that identity matches a principal in more than one estate",
                remedy=(
                    "Pass the tenant this sign-in is for. The identity provider's "
                    "subject is unique within an estate, not across them."
                ),
                context={"idp": idp, "estates": str(len(matches))},
            )
        return matches[0] if matches else None

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

    def set_password(self, principal: Principal, password: str, *, hasher: Any = None) -> None:
        """Store a password, hashed. The plaintext is never persisted.

        Beside the column that holds it, per the DAO convention: the algorithm
        and the storage format are one decision, and separating them is how a
        system ends up with a hasher that has moved on and a column that has
        not.
        """
        if len(password) < MINIMUM_PASSWORD:
            raise ValidationError(
                f"a password must be at least {MINIMUM_PASSWORD} characters",
                remedy=(
                    "Length is the only property that reliably helps. Prama does not "
                    "impose character-class rules: they demonstrably push people "
                    "towards Password1! and away from anything longer."
                ),
                context={"principal": principal.username},
            )
        principal.password_hash = (hasher or PasswordHasher()).hash(password)
        principal.updated_at = utc_now()

    async def authenticate(
        self, tenant_id: str, username: str, password: str, *, hasher: Any = None
    ) -> Principal | None:
        """The principal, if the credentials are right. ``None`` otherwise.

        One answer for every kind of failure — unknown user, wrong password,
        disabled account, an account with no password set at all. A caller that
        could tell them apart could enumerate usernames, and "that account is
        disabled" tells an attacker the account exists.

        The work is done even when the username is unknown. Skipping the hash
        for a missing user makes the *absence* measurable: an unknown username
        would return in microseconds and a known one in a tenth of a second,
        which is an enumeration oracle built out of timing rather than wording.
        """
        hasher = hasher or PasswordHasher()
        principal = await self.by_username(tenant_id, username)
        stored = principal.password_hash if principal is not None else ""

        # Against a fixed hash when there is nothing real to check, so the two
        # paths cost the same.
        matched = hasher.verify(password, stored or _DUMMY_HASH)

        if principal is None or not stored or not matched:
            return None
        if principal.status != "active":
            return None

        principal.last_login_at = utc_now()
        if hasher.needs_rehash(stored):
            # Raised cost applied on the one occasion the plaintext is legibly
            # in hand. A rehash scheduled for "later" is one that never runs.
            principal.password_hash = hasher.hash(password)
        principal.updated_at = utc_now()
        return principal

    async def any_for(self, tenant_id: str) -> bool:
        """Whether this tenant has a principal who could sign in.

        Exists so a sign-in page can say "nobody has been created here yet"
        rather than letting somebody try their password four more times before
        suspecting the installation.
        """
        await self._session.flush()
        found = await self._session.execute(
            select(Principal.id)
            .where(Principal.tenant_id == tenant_id, Principal.status == "active")
            .limit(1)
        )
        return found.first() is not None

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

    async def for_principal(self, tenant_id: str, principal_id: str) -> list[ApiKey]:
        """Every key a principal holds, revoked ones included, newest first.

        Revoked keys are listed rather than hidden: "which keys has this person
        ever had" is the question an access review asks.
        """
        return await self._all(
            select(ApiKey)
            .where(ApiKey.tenant_id == tenant_id, ApiKey.principal_id == principal_id)
            .order_by(ApiKey.created_at.desc())
        )

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
