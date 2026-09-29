"""My account: who I am, my password, and my API keys.

Adopted from Maya's ``/account/*`` pages. Every page here needs somebody signed
in and nothing more — a person with no roles at all may still see their own
account and change their own password, which is exactly what they need to do
before asking an administrator for a role.

**A key can never exceed its holder.** Each scope asked for must be one the
signed-in principal already holds; a steward cannot mint a key that approves
controls. The plaintext is rendered once, in the response to the POST that
created it — never put in the session cookie, never redirected through, and
never retrievable afterwards. Only its prefix and hash are stored. The rules
live in `prama.security.people`, which the HTTP API calls too.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Form, Request

from prama.core.clock import utc_now
from prama.core.errors import ForbiddenError, NotFoundError, PramaError, ValidationError
from prama.security.people import (
    DEFAULT_KEY_DAYS,
    MAX_KEY_DAYS,
    change_own_password,
    grantable_scopes,
    issue_key,
)
from prama.security.people import revoke_key as revoke
from prama.security.scopes import SCOPES
from prama.web.deps import Caller, NotSignedIn, Uow
from prama.web.rendering import flash_error_and_log, redirect_to, render
from prama.web.routes.base import UiRoutes


def require_principal(caller: Any) -> str:
    """The signed-in principal's id, or a redirect to sign in.

    The single-tenant fallback has a tenant and no principal: there is no
    account to show, so it is treated as not signed in.
    """
    if not caller.principal_id:
        raise NotSignedIn("these pages belong to a signed-in account", remedy="Sign in.")
    return str(caller.principal_id)


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
        try:
            await change_own_password(uow, caller.tenant_id, principal, current=current, new=new)
        except ForbiddenError:
            return refuse("The current password is not right.")
        except ValidationError as exc:
            return refuse(f"{exc} {exc.remedy or ''}".strip())
        # Changing the password moves `updated_at`, which invalidates every
        # session issued before it — including this one. That is right for the
        # others; this one is re-stamped so the person who just changed their
        # password is not signed out for doing so.
        request.session["issued_at"] = (principal.updated_at or utc_now()).isoformat()
        request.session.pop("default_password", None)
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
            issued = await issue_key(
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


__all__ = [
    "DEFAULT_KEY_DAYS",
    "MAX_KEY_DAYS",
    "AccountRoutes",
    "grantable_scopes",
    "issue_key",
    "require_principal",
    "revoke",
]
