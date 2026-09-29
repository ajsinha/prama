"""Estates: the one you are in, the ones there are, and making a new one.

A tenant is Prama's estate: every declaration, control and evidence record
belongs to exactly one, and an API key is bound to one. Creating an estate
provisions the caller there as its first administrator — the same username,
the same password — and returns a key for it, so a script (a case study, a
test estate, a new business line) can create an estate and start working in it
without a second, separate sign-in.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from prama.api.deps import Holder, TenantAdmin, Uow
from prama.api.routes.auth import DEFAULT_HOURS, MAXIMUM_HOURS, issue_key
from prama.core.errors import ConflictError, NotFoundError, ValidationError
from prama.security.accounts import grant_roles

router = APIRouter(tags=["tenants"])

_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$")


def _view(tenant: Any) -> dict[str, Any]:
    return {
        "id": str(tenant.id),
        "slug": tenant.slug,
        "display_name": tenant.display_name,
        "status": tenant.status,
        "residency": tenant.residency,
        "created_at": tenant.created_at.isoformat() if tenant.created_at else None,
    }


class TenantCreate(BaseModel):
    slug: str = Field(min_length=3, max_length=64)
    display_name: str = Field(min_length=1, max_length=255)
    residency: str | None = Field(default=None, max_length=64)
    hours: int = Field(default=DEFAULT_HOURS, ge=1, le=MAXIMUM_HOURS)


@router.get("/tenants/current")
async def current(uow: Uow, caller: Holder) -> dict[str, Any]:
    """The estate this key is bound to."""
    tenant = await uow.tenants.get(caller.tenant_id)
    if tenant is None:
        raise NotFoundError(
            "this key's estate no longer exists",
            remedy="Sign in again; the estate may have been retired.",
        )
    return _view(tenant)


@router.get("/tenants")
async def list_tenants(uow: Uow, caller: TenantAdmin) -> list[dict[str, Any]]:
    """Every active estate on this installation. Administrators only."""
    return [_view(t) for t in await uow.tenants.list_active(limit=1000)]


@router.post("/tenants", status_code=201)
async def create(body: TenantCreate, uow: Uow, caller: TenantAdmin) -> dict[str, Any]:
    """Create an estate, with the caller as its first administrator.

    Returns the estate and an expiring key for it. The caller's password is
    carried over as its hash — never as plaintext — so the same person signs
    in to the new estate with what they already know.
    """
    slug = body.slug.strip().lower()
    if not _SLUG.match(slug):
        raise ValidationError(
            f"{body.slug!r} is not a usable estate name",
            remedy="Lower-case letters, digits and hyphens, 3 to 64 characters: acme-markets.",
        )
    if await uow.tenants.by_slug(slug) is not None:
        raise ConflictError(
            f"an estate called {slug!r} already exists",
            remedy="Sign in to it (the SDK's connect(tenant=...)), or choose another name.",
            context={"slug": slug},
        )
    me = await uow.principals.get(caller.principal_id or "")
    if me is None:
        raise NotFoundError(
            "the calling principal no longer exists",
            remedy="Sign in again as somebody who exists in this estate.",
        )

    tenant = uow.tenants.create(
        slug=slug, display_name=body.display_name.strip(), residency=body.residency
    )
    await uow.flush()
    admin = uow.principals.create(
        tenant_id=str(tenant.id),
        username=me.username,
        display_name=me.display_name,
        email=me.email,
    )
    admin.password_hash = me.password_hash
    await uow.flush()
    await grant_roles(uow, str(tenant.id), admin, ["admin"])
    issued = await issue_key(
        uow, admin, name=f"created {slug}", hours=body.hours, created_by=caller.principal_id
    )
    issued["tenant_slug"] = slug
    return {"tenant": _view(tenant), "credentials": issued}
