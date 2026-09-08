"""Request-scoped dependencies.

The application holds one configuration and one ``Database``; a request borrows
a unit of work from it and returns it when the response is written. Nothing here
constructs a session: that stays inside ``prama.db``.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header, Request

from prama.core.config import Configuration
from prama.core.errors import ValidationError
from prama.core.ids import new_ulid
from prama.core.log import correlation_id
from prama.core.log import tenant_id as tenant_context
from prama.db import Database
from prama.db.session import UnitOfWork


@dataclasses.dataclass(frozen=True, slots=True)
class CallerIdentity:
    """Who is making this request.

    Wave 2 trusts headers because there is no authentication subsystem yet; the
    shape is fixed now so that Wave 10 replaces the *source* of these values
    without touching a single route. Every route already takes the caller
    explicitly rather than reaching for an ambient user, which is what makes
    that substitution safe.
    """

    tenant_id: str
    principal_id: str | None = None
    scopes: tuple[str, ...] = ()

    def require_principal(self) -> str:
        if not self.principal_id:
            raise ValidationError(
                "this operation records an author and none was supplied",
                remedy="Send the X-Prama-Principal header identifying the acting user.",
            )
        return self.principal_id


def get_config(request: Request) -> Configuration:
    return request.app.state.config  # type: ignore[no-any-return]


def get_database(request: Request) -> Database:
    return request.app.state.database  # type: ignore[no-any-return]


async def get_caller(
    x_prama_tenant: Annotated[str | None, Header()] = None,
    x_prama_principal: Annotated[str | None, Header()] = None,
) -> CallerIdentity:
    if not x_prama_tenant:
        raise ValidationError(
            "no tenant was supplied with the request",
            remedy="Send the X-Prama-Tenant header. Every operation is tenant-scoped.",
        )
    tenant_context.set(x_prama_tenant)
    return CallerIdentity(tenant_id=x_prama_tenant, principal_id=x_prama_principal)


async def get_uow(
    database: Annotated[Database, Depends(get_database)],
) -> AsyncIterator[UnitOfWork]:
    """One transaction per request: committed on success, rolled back on failure.

    A request that raises leaves no partial write, which is the only sane
    default for an API whose callers retry.
    """
    async with database.unit_of_work() as uow:
        yield uow


def new_correlation_id(request: Request) -> str:
    """Reuse the caller's correlation id if they sent one; otherwise mint one."""
    supplied = request.headers.get("X-Correlation-Id")
    cid = supplied or new_ulid()
    correlation_id.set(cid)
    return cid


Caller = Annotated[CallerIdentity, Depends(get_caller)]
Uow = Annotated[UnitOfWork, Depends(get_uow)]
Config = Annotated[Configuration, Depends(get_config)]
Db = Annotated[Database, Depends(get_database)]
