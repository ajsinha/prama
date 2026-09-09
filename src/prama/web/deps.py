"""Request-scoped dependencies for the UI.

The API takes its caller from headers because its callers are programs. The UI
takes its caller from the session because its callers are people, and a person
does not set a header. Both produce the same ``CallerIdentity``, so every
service below this line is written once.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request

from prama.api.deps import CallerIdentity, get_database
from prama.core.errors import PramaError
from prama.core.log import tenant_id as tenant_context
from prama.db import Database
from prama.db.session import UnitOfWork


class NotSignedIn(PramaError):
    """No session. Translated to a redirect, never to a stack trace."""


def ui_caller(request: Request) -> CallerIdentity:
    """Who is looking at this page.

    Until Wave 10 supplies real authentication, a single-tenant deployment
    falls back to the configured default tenant. The fallback is explicit and
    lives in exactly one place, so removing it later is a one-line change
    rather than a search through every route.
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
    tenant_context.set(tenant)
    return CallerIdentity(
        tenant_id=tenant,
        principal_id=session.get("principal_id"),
        scopes=tuple(session.get("scopes", ())),
    )


async def ui_uow(
    database: Annotated[Database, Depends(get_database)],
) -> AsyncIterator[UnitOfWork]:
    """One transaction per page render, as per request in the API."""
    async with database.unit_of_work() as uow:
        yield uow


Caller = Annotated[CallerIdentity, Depends(ui_caller)]
Uow = Annotated[UnitOfWork, Depends(ui_uow)]
