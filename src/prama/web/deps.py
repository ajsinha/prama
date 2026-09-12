"""Request-scoped dependencies for the UI.

The API takes its caller from headers because its callers are programs. The UI
takes its caller from the session because its callers are people, and a person
does not set a header. Both produce the same ``CallerIdentity``, so every
service below this line is written once.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Depends, Request

from prama.api.deps import CallerIdentity, get_database
from prama.core.errors import PramaError
from prama.core.log import tenant_id as tenant_context
from prama.db import Database
from prama.db.session import UnitOfWork
from prama.security.scopes import WILDCARD


class NotSignedIn(PramaError):
    """No session. Translated to a redirect, never to a stack trace."""


async def ui_uow(
    database: Annotated[Database, Depends(get_database)],
) -> AsyncIterator[UnitOfWork]:
    """One transaction per page render, as per request in the API."""
    async with database.unit_of_work() as uow:
        yield uow


async def ui_caller(
    request: Request,
    uow: Annotated[UnitOfWork, Depends(ui_uow)],
) -> CallerIdentity:
    """Who is looking at this page, checked against the database.

    Until Wave 10 supplies real authentication, a single-tenant deployment
    falls back to the configured default tenant. The fallback is explicit and
    lives in exactly one place, so removing it later is a one-line change
    rather than a search through every route.

    **The session is revalidated on every request** — finding S8. It used to be
    built from the cookie alone: no principal was loaded, no status was read, no
    role was re-checked. A self-contained signed cookie with no server-side
    state has two consequences that matter more than the round trip it saves.

    Disabling or deleting a principal had *no effect on their existing session*,
    so offboarding was not enforceable: `PrincipalDao.authenticate` refuses them
    at the door and the door was already open. And `sign_out` cleared the
    client's cookie only, so a cookie captured beforehand stayed valid for
    Starlette's default fourteen days. The module docstring presented the
    absence of a revocation flag as a security property — "the flag is one bug
    away from being ignored" — which is true of a flag and is not an argument
    for having nothing.

    Revocation is keyed on the principal's own `updated_at` rather than a new
    column: a session issued before the row last changed is refused. That gives
    sign-out something real to do, and it means *any* change to the principal —
    disabling them, removing a role — invalidates their sessions as a side
    effect. Over-invalidation is the safe direction: the cost is signing in
    again.
    """
    session = request.session
    tenant = session.get("tenant_id") or request.app.state.config.get_str(
        "tenancy.default_tenant", ""
    )
    if not tenant:
        raise NotSignedIn(
            "no tenant for this session",
            remedy="Sign in, or set tenancy.default_tenant for a single-tenant deployment.",
        )

    principal_id = session.get("principal_id")
    # No principal means the `tenancy.default_tenant` fallback: a deployment
    # that has not turned authentication on. There is no authorisation to apply
    # to a caller nobody authenticated, and pretending otherwise would lock such
    # a deployment out of its own console. Spelled out rather than implied,
    # because it is the one path where "everything" is the right answer, and it
    # stops being right the moment somebody signs in.
    scopes: tuple[str, ...] = (WILDCARD,)
    if principal_id:
        principal = await uow.principals.get(principal_id)
        if principal is None or principal.status != "active" or principal.tenant_id != tenant:
            raise NotSignedIn(
                "this session's account is no longer usable",
                remedy="Sign in again. If you have been disabled, ask an administrator.",
                context={"principal": str(principal_id)},
            )
        if _issued_before(session.get("issued_at"), principal.updated_at):
            raise NotSignedIn(
                "this session was issued before the account last changed",
                remedy="Sign in again.",
                context={"principal": str(principal_id)},
            )
        # Re-read rather than trusted from the cookie: a role removed an hour
        # ago must not still be carried by a session minted before it was. A
        # principal with no roles holds nothing, which is the same rule the API
        # applies to a key with no scopes — "none recorded" is not "no limit".
        scopes = tuple(
            sorted({grant for role in principal.roles for grant in role.permissions_json})
        )

    tenant_context.set(tenant)
    return CallerIdentity(tenant_id=tenant, principal_id=principal_id, scopes=scopes)


def _issued_before(issued_at: Any, changed_at: datetime | None) -> bool:
    """Whether this session predates the last change to the account.

    An unparsable or absent stamp counts as *before*: a session that cannot say
    when it was issued is one minted by an older build, and refusing it costs a
    sign-in.
    """
    if changed_at is None:
        return False
    if not isinstance(issued_at, str) or not issued_at:
        return True
    try:
        issued = datetime.fromisoformat(issued_at)
    except ValueError:
        return True
    if issued.tzinfo is None:
        issued = issued.replace(tzinfo=UTC)
    reference = changed_at if changed_at.tzinfo else changed_at.replace(tzinfo=UTC)
    # Strict, and no slack. A tolerance here is a window in which a revoked
    # session still works, and sign-out is the case that most needs it not to:
    # signing in and out within the same second is ordinary, and a one-second
    # grace made the revocation test pass a cookie captured beforehand. The
    # stamp is taken from the principal's own `updated_at` after the sign-in
    # flush, so the two are comparable without fudge.
    return issued < reference


Caller = Annotated[CallerIdentity, Depends(ui_caller)]


def ui_scope(scope: str) -> Any:
    """A dependency that refuses a console request lacking *scope*.

    The console was out of scope for finding S4: it authenticates a session
    rather than a key, and a route was authorised by the caller merely being
    signed in. `ui_caller` had been putting the principal's permissions on the
    identity for waves, and nothing read them — an auditor could post to
    `/controls/{id}/activate` exactly as an owner could.

    Applied in `UiRoutes.page` rather than on each handler, because the console
    has forty-eight routes registered through one helper and annotating them
    individually is forty-eight chances to forget.
    """
    from prama.security.scopes import SCOPES

    if scope not in SCOPES:
        raise ValueError(f"{scope!r} is not a declared scope; add it to SCOPES first")

    async def guard(caller: Caller) -> None:
        caller.require_scope(scope)

    guard.__name__ = f"ui_requires_{scope.replace(':', '_')}"
    guard.prama_scope = scope  # type: ignore[attr-defined]
    return guard


Uow = Annotated[UnitOfWork, Depends(ui_uow)]
