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

from prama.core.clock import utc_now
from prama.core.config import Configuration
from prama.core.errors import UnauthorisedError, ValidationError
from prama.core.ids import new_ulid
from prama.core.log import correlation_id
from prama.core.log import tenant_id as tenant_context
from prama.db import Database
from prama.db.security import ApiKeyIssuer
from prama.db.session import UnitOfWork


@dataclasses.dataclass(frozen=True, slots=True)
class CallerIdentity:
    """Who is making this request, established from an API key.

    The tenant is **not** taken from the request. It is read from the key's own
    record, because a caller who can choose their own tenant is not scoped at
    all — and for several waves this class took it from a header, which meant
    anybody who could reach the port was every tenant at once.
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
    uow: Annotated[UnitOfWork, Depends(get_uow)],
    authorization: Annotated[str | None, Header()] = None,
    x_prama_api_key: Annotated[str | None, Header()] = None,
) -> CallerIdentity:
    """Authenticate the request and derive its scope from the key.

    Every value here comes from the key's stored record. Nothing is taken from
    a header the caller controls except the key itself — which is the whole
    point: the previous version read the tenant from ``X-Prama-Tenant`` and
    verified nothing, so any caller who could reach the port could act as any
    tenant, including one that did not exist.
    """
    presented = x_prama_api_key or _bearer(authorization)
    if not presented:
        raise UnauthorisedError(
            "this request carried no API key",
            remedy=(
                "Send `Authorization: Bearer pk_live_…`, or the X-Prama-API-Key "
                "header. Create one with `prama apikey create`."
            ),
        )

    issuer = ApiKeyIssuer()
    record = await uow.api_keys.by_prefix(issuer.prefix_of(presented))
    # One refusal for every failure below, and deliberately the same one: which
    # part was wrong is useful to an attacker enumerating keys and useless to
    # anybody else, who simply has a key that does not work.
    refusal = UnauthorisedError(
        "that API key is not usable",
        remedy=(
            "Check the key is current and has not been revoked. `prama apikey "
            "list` shows which keys exist for a tenant and their state."
        ),
    )
    if record is None or not issuer.verify(presented, record.key_hash):
        raise refusal
    if record.revoked_at is not None:
        raise refusal
    if record.expires_at is not None and record.expires_at <= utc_now():
        raise refusal

    tenant_context.set(record.tenant_id)
    return CallerIdentity(
        tenant_id=record.tenant_id,
        principal_id=record.principal_id,
        scopes=tuple(record.scopes_json or ()),
    )


def _bearer(header: str | None) -> str:
    if not header:
        return ""
    scheme, _, value = header.partition(" ")
    return value.strip() if scheme.lower() == "bearer" else ""


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
