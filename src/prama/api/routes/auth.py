"""Signing in from a program: a username and password exchanged for an API key.

The HTTP API authenticates only by API key. A person scripting against Prama
with the SDK has a username and a password, so this exchanges them for a key:
**expiring**, carrying exactly the scopes the person's roles grant, named for
where it came from, and listed on their account page beside the keys they mint
by hand. Nothing new is trusted: the key is an ordinary key, checked on every
request like any other, and revoking it (``POST /auth/revoke``) ends it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from prama.api.deps import Holder, Uow
from prama.core.clock import utc_now
from prama.core.errors import UnauthorisedError
from prama.core.log import get_logger
from prama.db.security import ApiKeyIssuer

_log = get_logger(__name__)

router = APIRouter(tags=["auth"])

#: A key from a sign-in lives this long unless the caller asks for less. Long
#: enough for a working day of scripting, short enough that a key left in a
#: notebook stops working on its own.
DEFAULT_HOURS = 12
MAXIMUM_HOURS = 24 * 7


class TokenRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=1024)
    #: An estate slug or id. Empty: the configured default, or the only one.
    tenant: str = ""
    #: What the key is for, shown on the account page.
    name: str = Field(default="sdk", max_length=100)
    hours: int = Field(default=DEFAULT_HOURS, ge=1, le=MAXIMUM_HOURS)


async def resolve_tenant(uow: Any, given: str, config: Any) -> str:
    """The estate a sign-in is against: named, configured, or the only one."""
    for candidate in (given.strip(), str(config.get_str("tenancy.default_tenant", "")).strip()):
        if not candidate:
            continue
        if await uow.tenants.get(candidate) is not None:
            return candidate
        by_slug = await uow.tenants.by_slug(candidate)
        if by_slug is not None:
            return str(by_slug.id)
    only = await uow.tenants.list_active(limit=2)
    return str(only[0].id) if len(only) == 1 else ""


async def issue_key(
    uow: Any, principal: Any, *, name: str, hours: int, created_by: str | None = None
) -> dict[str, Any]:
    """An expiring key carrying the scopes the principal's roles grant."""
    scopes = sorted({p for role in await uow.principals.roles_of(str(principal.id))
                     for p in role.permissions_json})  # fmt: skip
    issued = ApiKeyIssuer().issue()
    expires = utc_now() + timedelta(hours=hours)
    uow.api_keys.create(
        tenant_id=str(principal.tenant_id),
        principal_id=str(principal.id),
        name=name,
        key_prefix=issued.prefix,
        key_hash=issued.hash,
        scopes=scopes,
        expires_at=expires,
        created_by=created_by or str(principal.id),
    )
    await uow.flush()
    return {
        "api_key": issued.plaintext,
        "tenant_id": str(principal.tenant_id),
        "principal_id": str(principal.id),
        "username": principal.username,
        "scopes": scopes,
        "expires_at": expires.isoformat(),
    }


@router.post("/auth/token")
async def token(body: TokenRequest, request: Request, uow: Uow) -> dict[str, Any]:
    """Exchange a username and password for an expiring API key.

    One refusal for every failure, as the console's sign-in does: which part
    was wrong helps only somebody guessing.
    """
    tenant_id = await resolve_tenant(uow, body.tenant, request.app.state.config)
    principal = (
        await uow.principals.authenticate(tenant_id, body.username.strip(), body.password)
        if tenant_id
        else None
    )
    if principal is None:
        _log.info("API sign-in refused for %r on tenant %r", body.username, tenant_id)
        raise UnauthorisedError(
            "those credentials were not accepted",
            remedy=(
                "Check the username and password. On an installation with more than one "
                "estate, name it: tenant='acme-bank'."
            ),
        )
    tenant = await uow.tenants.get(tenant_id)
    issued = await issue_key(uow, principal, name=body.name, hours=body.hours)
    issued["tenant_slug"] = tenant.slug if tenant is not None else ""
    return issued


@router.get("/auth/me")
async def me(uow: Uow, caller: Holder) -> dict[str, Any]:
    """Who this key acts as, in which estate, with what scopes."""
    principal = await uow.principals.get(caller.principal_id or "")
    tenant = await uow.tenants.get(caller.tenant_id)
    return {
        "tenant_id": caller.tenant_id,
        "tenant_slug": tenant.slug if tenant is not None else "",
        "tenant_name": tenant.display_name if tenant is not None else "",
        "principal_id": caller.principal_id,
        "username": principal.username if principal is not None else "",
        "display_name": principal.display_name if principal is not None else "",
        "scopes": list(caller.scopes),
        "api_key_id": caller.api_key_id,
    }


@router.post("/auth/revoke")
async def revoke(uow: Uow, caller: Holder) -> Annotated[dict[str, Any], "revoked"]:
    """Revoke the key this request was made with: signing out, for a program."""
    key = await uow.api_keys.get(caller.api_key_id or "")
    if key is not None and key.revoked_at is None:
        key.revoked_at = utc_now()
        await uow.flush()
    return {"revoked": caller.api_key_id}
