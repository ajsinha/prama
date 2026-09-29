"""People and their keys: the rules the console, the API and the SDK share.

The console's administration and account pages held these rules inside their
route handlers. The HTTP API needs exactly the same ones — an administrator
may not disable themselves, a key may not carry a scope its creator lacks — and
a second copy written for the API would drift from the first, silently, in the
flattering direction. So both call here.

Every function takes a unit of work and returns ORM rows or plain values. None
renders, redirects or flashes; the callers decide how to say what happened.

What an administrator may not do, deliberately:

* **Delete a person.** Evidence and attestations name their actor, and an
  audit trail pointing at a principal that no longer exists answers nothing.
  Disabling is the offboarding verb: it ends every console session, and every
  API key the person holds stops working, because a key acts as its principal.
* **Disable themselves, or remove their own admin role.** An estate whose last
  administrator locked themselves out has to be repaired from a shell.
* **See a password or a key.** A reset sets a new password; a key's plaintext
  exists only in the response that minted it.

**A key can never exceed its holder.** Each scope asked for must be one the
minting credential already holds; a steward cannot mint a key that approves
controls. Only its prefix and hash are stored.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from prama.core.clock import utc_now
from prama.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from prama.core.log import get_logger
from prama.db.security import ApiKeyIssuer
from prama.security.accounts import BUILTIN_ROLES, USERNAME, grant_roles
from prama.security.scopes import SCOPES, WILDCARD, permits

_log = get_logger(__name__)

ADMIN = "admin"
KINDS = ("human", "service")
STATUSES = ("active", "disabled")

#: After Maya: 90 days unless asked otherwise, and never more than a year. A
#: key that never expires is a key nobody remembers to revoke.
DEFAULT_KEY_DAYS = 90
MAX_KEY_DAYS = 365


# -- people ------------------------------------------------------------------


async def find(uow: Any, tenant_id: str, identifier: str) -> Any:
    """A principal in this estate, by id or by username; NotFoundError otherwise."""
    person = await uow.principals.get_for_tenant(tenant_id, identifier)
    if person is None:
        person = await uow.principals.by_username(tenant_id, identifier)
    if person is None:
        raise NotFoundError(
            "no such person in this estate",
            remedy="List the people with client.principals.list(), or /admin/users.",
            context={"principal": identifier},
        )
    return person


def _known_roles(roles: list[str]) -> list[str]:
    wanted = sorted(set(roles))
    unknown = [r for r in wanted if r not in BUILTIN_ROLES]
    if unknown:
        raise ValidationError(
            f"unknown role(s): {', '.join(unknown)}",
            remedy=f"Roles are {', '.join(BUILTIN_ROLES)}.",
            context={"roles": unknown},
        )
    return wanted


async def create(
    uow: Any,
    tenant_id: str,
    *,
    username: str,
    actor_id: str | None,
    display_name: str = "",
    email: str = "",
    password: str = "",
    kind: str = "human",
    roles: list[str] | None = None,
) -> tuple[Any, list[str]]:
    """A new principal with *roles*. No password means they cannot sign in yet."""
    username = username.strip()
    if not USERNAME.match(username):
        raise ValidationError(
            f"{username!r} is not a usable username",
            remedy="Use letters, digits, dot, underscore and hyphen.",
        )
    if kind not in KINDS:
        raise ValidationError(
            "a principal is a human or a service",
            remedy="Choose human or service.",
            context={"kind": kind},
        )
    if await uow.principals.by_username(tenant_id, username) is not None:
        raise ConflictError(
            f"{username!r} already exists in this estate",
            remedy="Choose another username, or edit the existing person.",
            context={"username": username},
        )
    wanted = _known_roles(list(roles or []))
    person = uow.principals.create(
        tenant_id=tenant_id,
        username=username,
        display_name=display_name.strip() or username,
        kind=kind,
        email=email.strip() or None,
    )
    if password:
        uow.principals.set_password(person, password)
    await uow.flush()
    granted = await grant_roles(uow, tenant_id, person, wanted)
    _audit(uow, tenant_id, actor_id, "principal.create", str(person.id), {"roles": granted})
    await uow.flush()
    return person, granted


async def set_roles(
    uow: Any, tenant_id: str, person: Any, roles: list[str], *, actor_id: str | None
) -> list[str]:
    """Replace a principal's built-in roles with exactly *roles*."""
    wanted = _known_roles(roles)
    if str(person.id) == actor_id and ADMIN not in wanted:
        raise ValidationError(
            "you cannot remove your own admin role",
            remedy="Ask another administrator, so an estate cannot lose its last one.",
        )
    held = {r.name: r for r in await uow.principals.roles_of(str(person.id))}
    for name, role in held.items():
        if name not in wanted:
            await uow.roles.revoke(str(person.id), str(role.id))
    await grant_roles(uow, tenant_id, person, [r for r in wanted if r not in held])
    # Any change to the principal ends their console sessions; a role removed
    # must not still be carried by a session minted before.
    person.updated_at = utc_now()
    _audit(uow, tenant_id, actor_id, "principal.roles.set", str(person.id), {"roles": wanted})
    await uow.flush()
    return wanted


async def reset_password(
    uow: Any, tenant_id: str, person: Any, password: str, *, actor_id: str | None
) -> None:
    """Set a new password for somebody else. Their console sessions end."""
    uow.principals.set_password(person, password)
    _audit(uow, tenant_id, actor_id, "principal.password.reset", str(person.id), {})
    await uow.flush()


async def change_own_password(
    uow: Any, tenant_id: str, person: Any, *, current: str, new: str
) -> None:
    """The holder's own change, which needs the current password."""
    checked = await uow.principals.authenticate(tenant_id, person.username, current)
    if checked is None:
        raise ForbiddenError(
            "the current password is not right",
            remedy="Give the password you sign in with now.",
        )
    uow.principals.set_password(person, new)
    _audit(uow, tenant_id, str(person.id), "principal.password.change", str(person.id), {})
    await uow.flush()


async def set_status(
    uow: Any, tenant_id: str, person: Any, status: str, *, actor_id: str | None
) -> None:
    """Enable or disable. Disabled: no sign-in, no session, and no key works."""
    if status not in STATUSES:
        raise ValidationError(
            "status is active or disabled",
            remedy="Use active or disabled.",
            context={"status": status},
        )
    if str(person.id) == actor_id and status != "active":
        raise ValidationError("you cannot disable yourself", remedy="Ask another administrator.")
    person.status = status
    person.updated_at = utc_now()
    _audit(uow, tenant_id, actor_id, f"principal.{status}", str(person.id), {})
    await uow.flush()


async def describe(uow: Any, person: Any) -> dict[str, Any]:
    """A principal as JSON: never the password hash, only whether one is set."""
    roles = await uow.principals.roles_of(str(person.id))
    return {
        "id": str(person.id),
        "username": person.username,
        "display_name": person.display_name,
        "email": person.email,
        "kind": person.kind,
        "status": person.status,
        "roles": [r.name for r in roles],
        "can_sign_in": bool(person.password_hash),
        "last_login_at": _iso(person.last_login_at),
        "created_at": _iso(getattr(person, "created_at", None)),
    }


def roles_catalogue() -> list[dict[str, Any]]:
    """The built-in roles and what each one may do."""
    return [
        {"name": name, "description": description, "permissions": list(permissions)}
        for name, (description, permissions) in BUILTIN_ROLES.items()
    ]


# -- keys --------------------------------------------------------------------


def grantable_scopes(held: tuple[str, ...] | list[str]) -> list[str]:
    """The scopes a credential holding *held* may put on a key it mints."""
    return [scope for scope in SCOPES if permits(held, scope)]


async def issue_key(
    uow: Any,
    *,
    tenant_id: str,
    principal_id: str,
    created_by: str,
    name: str,
    wanted: list[str],
    days: int,
    ceiling: tuple[str, ...] | list[str],
) -> dict[str, Any]:
    """Mint a key, record it, and return the one copy of its plaintext.

    *ceiling* is what the minting credential holds; no scope beyond it is
    granted, and the wildcard is never granted this way.
    """
    name = name.strip()
    if not name:
        raise ValidationError("a key needs a name", remedy="Say what program will use it.")
    wanted = sorted(set(wanted))
    if not wanted:
        raise ValidationError(
            "a key with no scopes can do nothing",
            remedy="Ask for at least one scope. An empty list means nothing, not everything.",
        )
    beyond = [s for s in wanted if s == WILDCARD or s not in SCOPES or not permits(ceiling, s)]
    if beyond:
        raise ValidationError(
            f"you cannot grant {', '.join(beyond)}",
            remedy="A key can only carry scopes its creator already holds.",
            context={"scopes": beyond},
        )
    if not 1 <= days <= MAX_KEY_DAYS:
        raise ValidationError(
            f"a key lives between 1 and {MAX_KEY_DAYS} days",
            remedy=f"Choose an expiry up to {MAX_KEY_DAYS} days; renew it by minting another.",
            context={"days": str(days)},
        )
    issued = ApiKeyIssuer().issue()
    expires = datetime.now(UTC) + timedelta(days=days)
    row = uow.api_keys.create(
        tenant_id=tenant_id,
        principal_id=principal_id,
        name=name,
        key_prefix=issued.prefix,
        key_hash=issued.hash,
        scopes=wanted,
        expires_at=expires,
        created_by=created_by,
    )
    # The id is minted on flush. Before this was moved up, the console's audit
    # record of every key it minted named the object "None".
    await uow.flush()
    uow.audit.record(
        tenant_id=tenant_id,
        action="api_key.create",
        object_kind="api_key",
        object_id=str(row.id),
        actor_id=created_by,
        detail={"prefix": issued.prefix, "scopes": wanted, "days": days},
    )
    await uow.flush()
    _log.info("api key %s issued to %s", issued.prefix, principal_id)
    return {
        "id": str(row.id),
        "plaintext": issued.plaintext,
        "prefix": issued.prefix,
        "name": name,
        "scopes": wanted,
        "expires_at": expires.isoformat(),
    }


def revoke_key(uow: Any, key: Any, *, tenant_id: str, actor_id: str | None) -> None:
    """Revoke a key. Idempotent: revoking twice keeps the first time."""
    if key.revoked_at is None:
        key.revoked_at = utc_now()
        uow.audit.record(
            tenant_id=tenant_id,
            action="api_key.revoke",
            object_kind="api_key",
            object_id=str(key.id),
            actor_id=actor_id,
            detail={"prefix": key.key_prefix},
        )


def describe_key(key: Any, *, owner: str = "") -> dict[str, Any]:
    """A key as JSON: its prefix and state, never its hash."""
    now = utc_now()
    state = "active"
    if key.revoked_at is not None:
        state = "revoked"
    elif key.expires_at is not None and key.expires_at <= now:
        state = "expired"
    return {
        "id": str(key.id),
        "name": key.name,
        "prefix": key.key_prefix,
        "principal_id": str(key.principal_id),
        "owner": owner,
        "scopes": list(key.scopes_json or ()),
        "state": state,
        "created_at": _iso(getattr(key, "created_at", None)),
        "expires_at": _iso(key.expires_at),
        "last_used_at": _iso(key.last_used_at),
        "revoked_at": _iso(key.revoked_at),
        "created_by": key.created_by,
    }


async def estate_keys(uow: Any, tenant_id: str) -> list[tuple[Any, str]]:
    """Every key in the estate with its owner's username, newest first."""
    people = {
        str(p.id): p.username for p in await uow.principals.list_for_tenant(tenant_id, limit=1000)
    }
    keys = []
    for pid in people:
        keys.extend(await uow.api_keys.for_principal(tenant_id, pid))
    keys.sort(key=lambda k: k.created_at, reverse=True)
    return [(k, people.get(str(k.principal_id), "")) for k in keys]


def _audit(
    uow: Any,
    tenant_id: str,
    actor_id: str | None,
    action: str,
    object_id: str,
    detail: dict[str, Any],
) -> None:
    uow.audit.record(
        tenant_id=tenant_id,
        action=action,
        object_kind="principal",
        object_id=object_id,
        actor_id=actor_id,
        detail=detail,
    )


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)
