"""Request-scoped dependencies.

The application holds one configuration and one ``Database``; a request borrows
a unit of work from it and returns it when the response is written. Nothing here
constructs a session: that stays inside ``prama.db``.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import Depends, Header, Request

from prama.core.clock import utc_now
from prama.core.config import Configuration
from prama.core.errors import ForbiddenError, UnauthorisedError, ValidationError
from prama.core.ids import new_ulid
from prama.core.log import correlation_id
from prama.core.log import tenant_id as tenant_context
from prama.db import Database
from prama.db.security import ApiKeyIssuer
from prama.db.session import UnitOfWork
from prama.security.scopes import SCOPES, permits


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
    #: The key that authenticated the request, for per-key budgets and the
    #: model-call ledger. None for a console session.
    api_key_id: str | None = None

    def require_scope(self, scope: str) -> None:
        """Refuse unless this credential carries *scope*.

        Separate from authentication: S1 established *who* is calling, and this
        establishes *what they may do*. Before it existed, the scopes on a key
        were recorded, carried on this object and consulted nowhere, so a
        read-only key could retire a declaration.
        """
        if not permits(self.scopes, scope):
            raise ForbiddenError(
                f"this credential does not carry the {scope!r} scope",
                remedy=(
                    f"Issue a key with {scope!r} — it may {SCOPES.get(scope, 'do this')}. "
                    "An empty scope list permits nothing, deliberately: a credential "
                    "created before scopes existed must not become a superuser the day "
                    "they are enforced."
                ),
                context={"scope": scope, "held": ",".join(self.scopes) or "(none)"},
            )

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
    # A key acts as its principal, so it is no more usable than they are.
    # Disabling somebody used to end their console sessions and leave every
    # key they had minted working — offboarding that stopped at the browser.
    holder = await uow.principals.get(record.principal_id)
    if holder is None or holder.status != "active":
        raise refusal

    tenant_context.set(record.tenant_id)
    return CallerIdentity(
        tenant_id=record.tenant_id,
        principal_id=record.principal_id,
        scopes=tuple(record.scopes_json or ()),
        api_key_id=str(record.id),
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


def scoped(scope: str) -> Any:
    """A caller who additionally holds *scope*.

    Used as a route's `caller` annotation, so the permission a route needs is
    stated in its signature rather than in its body — which means it is visible
    in the generated OpenAPI document and, more usefully, checkable by a test
    that walks the routing table. See
    `tests/architecture/test_scopes.py::TestEveryMutatingRouteDeclaresAScope`.
    """
    if scope not in SCOPES:
        raise ValueError(f"{scope!r} is not a declared scope; add it to SCOPES first")

    async def guard(caller: Caller) -> CallerIdentity:
        caller.require_scope(scope)
        return caller

    guard.__name__ = f"requires_{scope.replace(':', '_')}"
    #: Read by the architecture test to tell a guarded route from a bare one.
    guard.prama_scope = scope  # type: ignore[attr-defined]
    return Annotated[CallerIdentity, Depends(guard)]


Caller = Annotated[CallerIdentity, Depends(get_caller)]
#: An authenticated caller, with no authorisation check. Reserved for the
#: routes that genuinely need none; a route using this instead of one of the
#: annotations below is what `tests/architecture/test_scopes.py` looks for.
#:
#: The names come from `prama.security.scopes.SCOPES`, which is the same list
#: `BUILTIN_ROLES` grants from — see finding H5. An annotation naming a scope no
#: role can hold is a route nobody can call.
Reader = scoped("declaration:read")
Writer = scoped("declaration:write")
RelationshipReader = scoped("relationship:read")
RelationshipWriter = scoped("relationship:write")
LlmUser = scoped("llm:use")
AgentWorker = scoped("agent:work")
ControlReader = scoped("control:read")
Commenter = scoped("comment:write")


async def _holder(caller: Caller) -> CallerIdentity:
    return caller


#: A question a credential asks about **itself** — who am I, which estate, end
#: this key — which any holder may ask and which reads nothing else. Marked so
#: the architecture test sees a decision rather than a missing scope.
HOLDER = "self"
_holder.prama_scope = HOLDER  # type: ignore[attr-defined]
Holder = Annotated[CallerIdentity, Depends(_holder)]
TenantAdmin = scoped("tenant:admin")
Uow = Annotated[UnitOfWork, Depends(get_uow)]
Config = Annotated[Configuration, Depends(get_config)]
Db = Annotated[Database, Depends(get_database)]

# -- reconciliation, data contracts and usage ----------------------------------
BreakReader = scoped("break:read")
BreakWriter = scoped("break:write")
#: A period-end reconciliation certificate is a signed statement, so issuing
#: one takes the scope that signs statements.
AttestationSigner = scoped("attestation:sign")
ReportReader = scoped("report:read")
ContractChecker = scoped("contract:check")
