"""People, roles and API keys over the API: what the Administration and Account
pages do, for a program.

Two kinds of route live here, and the difference is who may call them:

* ``/principals``, ``/roles`` and ``/api-keys`` are administration: they need
  the ``admin`` scope, exactly as the console's pages do.
* ``/account`` is the holder's own account — who am I, change my password,
  my keys — which any signed-in key may use, as any signed-in person may use
  the console's Account page. A key minted here can carry only scopes the
  minting key already holds, so a holder can narrow their authority but never
  widen it.

The rules are in `prama.security.people`, shared with the console.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from prama.api.deps import Administrator, Holder, Uow
from prama.core.errors import NotFoundError, ValidationError
from prama.security import people
from prama.security.scopes import SCOPES

router = APIRouter(tags=["people"])


def _principal_of(caller: Any) -> str:
    if not caller.principal_id:
        raise ValidationError(
            "this key does not belong to a person",
            remedy="Sign in with client.auth.token(username, password).",
        )
    return str(caller.principal_id)


# -- administration: people ------------------------------------------------


class PrincipalIn(BaseModel):
    username: str = Field(..., min_length=1, max_length=128)
    display_name: str = Field("", max_length=255)
    email: str = Field("", max_length=320)
    #: Empty: the principal exists but cannot sign in until a password is set.
    password: str = Field("", max_length=1024)
    kind: str = Field("human", description="human | service")
    roles: list[str] = Field(default_factory=list)


class RolesIn(BaseModel):
    roles: list[str] = Field(default_factory=list)


class PasswordIn(BaseModel):
    password: str = Field(..., min_length=1, max_length=1024)


class StatusIn(BaseModel):
    status: str = Field(..., description="active | disabled")


@router.get("/principals")
async def list_principals(uow: Uow, caller: Administrator) -> list[dict[str, Any]]:
    """Everybody in this estate, with their roles and whether they can sign in."""
    rows = await uow.principals.list_for_tenant(caller.tenant_id, limit=1000)
    return [await people.describe(uow, p) for p in sorted(rows, key=lambda p: p.username)]


@router.post("/principals", status_code=201)
async def create_principal(body: PrincipalIn, uow: Uow, caller: Administrator) -> dict[str, Any]:
    """Create a person or a service principal, with built-in roles."""
    person, _ = await people.create(
        uow,
        caller.tenant_id,
        username=body.username,
        actor_id=caller.principal_id,
        display_name=body.display_name,
        email=body.email,
        password=body.password,
        kind=body.kind,
        roles=body.roles,
    )
    return await people.describe(uow, person)


@router.get("/principals/{principal}")
async def get_principal(principal: str, uow: Uow, caller: Administrator) -> dict[str, Any]:
    """One person, by id or username."""
    return await people.describe(uow, await people.find(uow, caller.tenant_id, principal))


@router.put("/principals/{principal}/roles")
async def set_roles(
    principal: str, body: RolesIn, uow: Uow, caller: Administrator
) -> dict[str, Any]:
    """Replace a person's roles. You cannot remove your own admin role."""
    person = await people.find(uow, caller.tenant_id, principal)
    await people.set_roles(uow, caller.tenant_id, person, body.roles, actor_id=caller.principal_id)
    return await people.describe(uow, person)


@router.post("/principals/{principal}/password")
async def reset_password(
    principal: str, body: PasswordIn, uow: Uow, caller: Administrator
) -> dict[str, Any]:
    """Set somebody else's password. Their console sessions end."""
    person = await people.find(uow, caller.tenant_id, principal)
    await people.reset_password(
        uow, caller.tenant_id, person, body.password, actor_id=caller.principal_id
    )
    return await people.describe(uow, person)


@router.post("/principals/{principal}/status")
async def set_status(
    principal: str, body: StatusIn, uow: Uow, caller: Administrator
) -> dict[str, Any]:
    """Enable or disable. A disabled person's keys stop working at once."""
    person = await people.find(uow, caller.tenant_id, principal)
    await people.set_status(
        uow, caller.tenant_id, person, body.status, actor_id=caller.principal_id
    )
    return await people.describe(uow, person)


@router.get("/roles")
async def roles(caller: Administrator) -> dict[str, Any]:
    """The built-in roles, what each grants, and every scope with its meaning."""
    return {"roles": people.roles_catalogue(), "scopes": dict(SCOPES)}


# -- administration: every key in the estate -------------------------------


class IssueIn(BaseModel):
    #: The username or id the key acts as.
    principal: str = Field(..., min_length=1, max_length=128)
    name: str = Field(..., min_length=1, max_length=128)
    scopes: list[str] = Field(..., min_length=1)
    days: int = Field(people.DEFAULT_KEY_DAYS, ge=1, le=people.MAX_KEY_DAYS)


@router.get("/api-keys")
async def all_keys(uow: Uow, caller: Administrator) -> list[dict[str, Any]]:
    """Every key in the estate, revoked and expired ones included, newest first."""
    return [
        people.describe_key(key, owner=owner)
        for key, owner in await people.estate_keys(uow, caller.tenant_id)
    ]


@router.post("/api-keys", status_code=201)
async def issue_for(body: IssueIn, uow: Uow, caller: Administrator) -> dict[str, Any]:
    """Mint a key that acts as somebody else, for a service or a pipeline.

    The scopes are explicit, not inherited from the person's roles, and still
    bounded by what the administrator's own key holds.
    """
    person = await people.find(uow, caller.tenant_id, body.principal)
    issued = await people.issue_key(
        uow,
        tenant_id=caller.tenant_id,
        principal_id=str(person.id),
        created_by=_principal_of(caller),
        name=body.name,
        wanted=body.scopes,
        days=body.days,
        ceiling=caller.scopes,
    )
    await uow.flush()
    return {**issued, "principal_id": str(person.id), "username": person.username}


@router.post("/api-keys/{key_id}/revoke")
async def revoke_any(key_id: str, uow: Uow, caller: Administrator) -> dict[str, Any]:
    """Revoke any key in the estate. Idempotent."""
    key = await uow.api_keys.get_for_tenant(caller.tenant_id, key_id)
    if key is None:
        raise NotFoundError(
            "no such key in this estate",
            remedy="List them with client.api_keys.list_all().",
            context={"key": key_id},
        )
    people.revoke_key(uow, key, tenant_id=caller.tenant_id, actor_id=caller.principal_id)
    await uow.flush()
    return people.describe_key(key)


# -- the holder's own account ----------------------------------------------


class ChangePasswordIn(BaseModel):
    current: str = Field(..., min_length=1, max_length=1024)
    new: str = Field(..., min_length=1, max_length=1024)


class KeyIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    scopes: list[str] = Field(..., min_length=1)
    days: int = Field(people.DEFAULT_KEY_DAYS, ge=1, le=people.MAX_KEY_DAYS)


@router.get("/account")
async def account(uow: Uow, caller: Holder) -> dict[str, Any]:
    """Who I am, my roles, the scopes this key holds and those it may grant."""
    person = await uow.principals.require_for_tenant(caller.tenant_id, _principal_of(caller))
    return {
        **await people.describe(uow, person),
        "scopes": list(caller.scopes),
        "grantable": people.grantable_scopes(caller.scopes),
        "active_keys": len(await uow.api_keys.active_for_principal(str(person.id))),
    }


@router.post("/account/password")
async def change_password(body: ChangePasswordIn, uow: Uow, caller: Holder) -> dict[str, Any]:
    """Change my own password; the current one is required. My console sessions end."""
    person = await uow.principals.require_for_tenant(caller.tenant_id, _principal_of(caller))
    await people.change_own_password(
        uow, caller.tenant_id, person, current=body.current, new=body.new
    )
    return {"changed": True, "principal_id": str(person.id)}


@router.get("/account/keys")
async def my_keys(uow: Uow, caller: Holder) -> list[dict[str, Any]]:
    """My keys, revoked ones included, newest first."""
    principal_id = _principal_of(caller)
    return [
        people.describe_key(k)
        for k in await uow.api_keys.for_principal(caller.tenant_id, principal_id)
    ]


@router.post("/account/keys", status_code=201)
async def mint(body: KeyIn, uow: Uow, caller: Holder) -> dict[str, Any]:
    """Mint a key of my own. The plaintext is in this response and nowhere else.

    Each scope must be one this request's key already holds: a key can narrow
    its holder's authority, never widen it.
    """
    principal_id = _principal_of(caller)
    issued = await people.issue_key(
        uow,
        tenant_id=caller.tenant_id,
        principal_id=principal_id,
        created_by=principal_id,
        name=body.name,
        wanted=body.scopes,
        days=body.days,
        ceiling=caller.scopes,
    )
    await uow.flush()
    return issued


@router.post("/account/keys/{key_id}/revoke")
async def revoke_mine(key_id: str, uow: Uow, caller: Holder) -> dict[str, Any]:
    """Revoke one of my keys. Somebody else's is "not found", not "forbidden"."""
    principal_id = _principal_of(caller)
    key = await uow.api_keys.get_for_tenant(caller.tenant_id, key_id)
    if key is None or str(key.principal_id) != principal_id:
        raise NotFoundError(
            "no such key", remedy="Your keys: client.api_keys.list().", context={"key": key_id}
        )
    people.revoke_key(uow, key, tenant_id=caller.tenant_id, actor_id=principal_id)
    await uow.flush()
    return people.describe_key(key)
