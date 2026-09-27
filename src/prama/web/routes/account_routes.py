"""My account: who I am, my password, and my API keys.

Adopted from Maya's ``/account/*`` pages. Every page here needs somebody signed
in and nothing more — a person with no roles at all may still see their own
account and change their own password, which is exactly what they need to do
before asking an administrator for a role.

**A key can never exceed its holder.** Each scope asked for must be one the
signed-in principal already holds; a steward cannot mint a key that approves
controls. The plaintext is rendered once, in the response to the POST that
created it — never put in the session cookie, never redirected through, and
never retrievable afterwards. Only its prefix and hash are stored.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import Form, Request

from prama.core.clock import utc_now
from prama.core.errors import NotFoundError, PramaError, ValidationError
from prama.core.log import get_logger
from prama.db.security import ApiKeyIssuer
from prama.security.scopes import SCOPES, WILDCARD, permits
from prama.web.deps import Caller, NotSignedIn, Uow
from prama.web.rendering import flash_error_and_log, redirect_to, render
from prama.web.routes.base import UiRoutes

_log = get_logger(__name__)

#: After Maya: 90 days unless asked otherwise, and never more than a year. A
#: key that never expires is a key nobody remembers to revoke.
DEFAULT_KEY_DAYS = 90
MAX_KEY_DAYS = 365


def require_principal(caller: Any) -> str:
    """The signed-in principal's id, or a redirect to sign in.

    The single-tenant fallback has a tenant and no principal: there is no
    account to show, so it is treated as not signed in.
    """
    if not caller.principal_id:
        raise NotSignedIn("these pages belong to a signed-in account", remedy="Sign in.")
    return str(caller.principal_id)


def grantable_scopes(held: tuple[str, ...]) -> list[str]:
    """The scopes a principal holding *held* may put on a key of their own."""
    return [scope for scope in SCOPES if permits(held, scope)]


class AccountRoutes(UiRoutes):
    """The signed-in person's own account."""

    def register(self) -> None:
        self.page("/account", self.home, name="account_home", scope=None)
        self.page("/account/password", self.password_form, name="account_password", scope=None)
        self.page(
            "/account/password",
            self.change_password,
            name="account_password_post",
            methods=["POST"],
            scope=None,
        )
        self.page("/account/keys", self.keys, name="account_keys", scope=None)
        self.page(
            "/account/keys", self.create_key, name="account_keys_post", methods=["POST"], scope=None
        )
        self.page(
            "/account/keys/{key_id}/revoke",
            self.revoke_key,
            name="account_key_revoke",
            methods=["POST"],
            scope=None,
        )

    async def home(self, request: Request, uow: Uow, caller: Caller) -> Any:
        principal = await uow.principals.require_for_tenant(
            caller.tenant_id, require_principal(caller)
        )
        roles = await uow.principals.roles_of(str(principal.id))
        return render(
            request,
            "account/home.html",
            principal=principal,
            roles=roles,
            scopes=caller.scopes,
            key_count=len(await uow.api_keys.active_for_principal(str(principal.id))),
        )

    async def password_form(self, request: Request, caller: Caller) -> Any:
        require_principal(caller)
        return render(request, "account/password.html", error="")

    async def change_password(
        self,
        request: Request,
        uow: Uow,
        caller: Caller,
        current: Annotated[str, Form()] = "",
        new: Annotated[str, Form()] = "",
        confirm: Annotated[str, Form()] = "",
    ) -> Any:
        principal = await uow.principals.require_for_tenant(
            caller.tenant_id, require_principal(caller)
        )

        def refuse(message: str) -> Any:
            return render(request, "account/password.html", error=message, status_code=400)

        if new != confirm:
            return refuse("The new password and its confirmation differ.")
        checked = await uow.principals.authenticate(caller.tenant_id, principal.username, current)
        if checked is None:
            return refuse("The current password is not right.")
        try:
            uow.principals.set_password(principal, new)
        except ValidationError as exc:
            return refuse(f"{exc} {exc.remedy or ''}".strip())
        uow.audit.record(
            tenant_id=caller.tenant_id,
            action="principal.password.change",
            object_kind="principal",
            object_id=str(principal.id),
            actor_id=str(principal.id),
        )
        # Changing the password moves `updated_at`, which invalidates every
        # session issued before it — including this one. That is right for the
        # others; this one is re-stamped so the person who just changed their
        # password is not signed out for doing so.
        await uow.flush()
        request.session["issued_at"] = (principal.updated_at or utc_now()).isoformat()
        return redirect_to(
            request,
            "account_home",
            flash_message="Password changed. Every other session of yours has been signed out.",
        )

    async def keys(self, request: Request, uow: Uow, caller: Caller) -> Any:
        principal_id = require_principal(caller)
        return render(
            request,
            "account/keys.html",
            keys=await uow.api_keys.for_principal(caller.tenant_id, principal_id),
            grantable=grantable_scopes(caller.scopes),
            scope_notes=SCOPES,
            default_days=DEFAULT_KEY_DAYS,
            max_days=MAX_KEY_DAYS,
            issued=None,
            now=datetime.now(UTC),
        )

    async def create_key(
        self,
        request: Request,
        uow: Uow,
        caller: Caller,
        name: Annotated[str, Form()] = "",
        scopes: Annotated[list[str] | None, Form()] = None,
        days: Annotated[int, Form()] = DEFAULT_KEY_DAYS,
    ) -> Any:
        principal_id = require_principal(caller)
        wanted = sorted(set(scopes or []))
        try:
            issued = issue_key(
                uow,
                tenant_id=caller.tenant_id,
                principal_id=principal_id,
                created_by=principal_id,
                name=name,
                wanted=wanted,
                days=days,
                ceiling=caller.scopes,
            )
            await uow.flush()
        except PramaError as exc:
            flash_error_and_log(request, "That key could not be created", exc)
            return redirect_to(request, "account_keys")
        return render(
            request,
            "account/keys.html",
            keys=await uow.api_keys.for_principal(caller.tenant_id, principal_id),
            grantable=grantable_scopes(caller.scopes),
            scope_notes=SCOPES,
            default_days=DEFAULT_KEY_DAYS,
            max_days=MAX_KEY_DAYS,
            issued=issued,
            now=datetime.now(UTC),
        )

    async def revoke_key(self, request: Request, uow: Uow, caller: Caller, key_id: str) -> Any:
        principal_id = require_principal(caller)
        key = await uow.api_keys.get_for_tenant(caller.tenant_id, key_id)
        # Somebody else's key is "not found", not "forbidden": the difference
        # would confirm that the id exists.
        if key is None or str(key.principal_id) != principal_id:
            raise NotFoundError(
                "no such key", remedy="Your keys are listed on this page.", context={"key": key_id}
            )
        revoke(uow, key, tenant_id=caller.tenant_id, actor_id=principal_id)
        return redirect_to(request, "account_keys", flash_message=f"Key {key.key_prefix}… revoked.")


def issue_key(
    uow: Any,
    *,
    tenant_id: str,
    principal_id: str,
    created_by: str,
    name: str,
    wanted: list[str],
    days: int,
    ceiling: tuple[str, ...],
) -> dict[str, Any]:
    """Mint a key, record it, and return the one copy of its plaintext.

    *ceiling* is what the minting caller holds; no scope beyond it is granted.
    """
    name = name.strip()
    if not name:
        raise ValidationError("a key needs a name", remedy="Say what program will use it.")
    if not wanted:
        raise ValidationError(
            "a key with no scopes can do nothing",
            remedy="Tick at least one scope. An empty list means nothing, not everything.",
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
    row = uow.api_keys.create(
        tenant_id=tenant_id,
        principal_id=principal_id,
        name=name,
        key_prefix=issued.prefix,
        key_hash=issued.hash,
        scopes=wanted,
        expires_at=datetime.now(UTC) + timedelta(days=days),
        created_by=created_by,
    )
    uow.audit.record(
        tenant_id=tenant_id,
        action="api_key.create",
        object_kind="api_key",
        object_id=str(row.id),
        actor_id=created_by,
        detail={"prefix": issued.prefix, "scopes": wanted, "days": days},
    )
    _log.info("api key %s issued to %s", issued.prefix, principal_id)
    return {"plaintext": issued.plaintext, "prefix": issued.prefix, "name": name}


def revoke(uow: Any, key: Any, *, tenant_id: str, actor_id: str | None) -> None:
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
