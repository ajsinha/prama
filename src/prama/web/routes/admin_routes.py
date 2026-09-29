"""Administration: people, their roles, and every API key in the estate.

Adopted from Maya's ``/admin/users``. Every page requires the ``admin`` scope,
enforced at registration like every other console page.

What an administrator may not do, deliberately:

* **Delete a person.** Evidence and attestations name their actor, and an
  audit trail pointing at a principal that no longer exists answers nothing.
  Disabling is the offboarding verb — it ends every session at once, because
  ``ui_caller`` refuses a session issued before the account last changed.
* **Disable themselves, or remove their own admin role.** An estate whose last
  administrator locked themselves out has to be repaired from a shell.
* **See a password or a key.** A reset sets a new password; a key's plaintext
  exists only in the response that minted it.

The rules themselves live in `prama.security.people`, which the HTTP API calls
too, so the console and the SDK cannot come to disagree.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Form, Request

from prama.core.clock import utc_now
from prama.core.errors import NotFoundError, PramaError
from prama.security import people
from prama.security.accounts import BUILTIN_ROLES
from prama.web.deps import Caller, Uow
from prama.web.rendering import flash_error_and_log, redirect_to, render
from prama.web.routes.base import UiRoutes

ADMIN = "admin"


class AdminRoutes(UiRoutes):
    """People and keys, for an administrator."""

    SUBJECT = "admin"

    def register(self) -> None:
        post = ["POST"]
        self.page("/admin/users", self.users, name="admin_users", scope=ADMIN)
        self.page(
            "/admin/users", self.create_user, name="admin_users_post", methods=post, scope=ADMIN
        )
        self.page(
            "/admin/users/{pid}/roles",
            self.set_roles,
            name="admin_user_roles",
            methods=post,
            scope=ADMIN,
        )
        self.page(
            "/admin/users/{pid}/password",
            self.reset_password,
            name="admin_user_password",
            methods=post,
            scope=ADMIN,
        )
        self.page(
            "/admin/users/{pid}/status",
            self.set_status,
            name="admin_user_status",
            methods=post,
            scope=ADMIN,
        )
        self.page("/admin/keys", self.keys, name="admin_keys", scope=ADMIN)
        self.page(
            "/admin/keys/{key_id}/revoke",
            self.revoke_key,
            name="admin_key_revoke",
            methods=post,
            scope=ADMIN,
        )

    async def users(self, request: Request, uow: Uow, caller: Caller) -> Any:
        people = await uow.principals.list_for_tenant(caller.tenant_id, limit=1000)
        rows = []
        for person in sorted(people, key=lambda p: p.username):
            roles = await uow.principals.roles_of(str(person.id))
            rows.append({"p": person, "roles": [r.name for r in roles]})
        return render(
            request,
            "admin/users.html",
            rows=rows,
            builtin_roles=BUILTIN_ROLES,
            me=caller.principal_id,
        )

    async def create_user(
        self,
        request: Request,
        uow: Uow,
        caller: Caller,
        username: Annotated[str, Form()] = "",
        display_name: Annotated[str, Form()] = "",
        email: Annotated[str, Form()] = "",
        password: Annotated[str, Form()] = "",
        kind: Annotated[str, Form()] = "human",
        roles: Annotated[list[str] | None, Form()] = None,
    ) -> Any:
        try:
            await people.create(
                uow,
                caller.tenant_id,
                username=username,
                actor_id=caller.principal_id,
                display_name=display_name,
                email=email,
                password=password,
                kind=kind,
                roles=list(roles or []),
            )
        except PramaError as exc:
            flash_error_and_log(request, "That person could not be created", exc)
            return redirect_to(request, "admin_users")
        return redirect_to(request, "admin_users", flash_message=f"Created {username.strip()}.")

    async def set_roles(
        self,
        request: Request,
        uow: Uow,
        caller: Caller,
        pid: str,
        roles: Annotated[list[str] | None, Form()] = None,
    ) -> Any:
        person = await self._person(uow, caller, pid)
        try:
            await people.set_roles(
                uow, caller.tenant_id, person, list(roles or []), actor_id=caller.principal_id
            )
        except PramaError as exc:
            flash_error_and_log(request, "Those roles could not be set", exc)
            return redirect_to(request, "admin_users")
        return redirect_to(
            request, "admin_users", flash_message=f"Roles for {person.username} updated."
        )

    async def reset_password(
        self,
        request: Request,
        uow: Uow,
        caller: Caller,
        pid: str,
        password: Annotated[str, Form()] = "",
    ) -> Any:
        person = await self._person(uow, caller, pid)
        try:
            await people.reset_password(
                uow, caller.tenant_id, person, password, actor_id=caller.principal_id
            )
        except PramaError as exc:
            flash_error_and_log(request, "That password could not be set", exc)
            return redirect_to(request, "admin_users")
        return redirect_to(
            request,
            "admin_users",
            flash_message=f"Password for {person.username} reset; their sessions have ended.",
        )

    async def set_status(
        self,
        request: Request,
        uow: Uow,
        caller: Caller,
        pid: str,
        status: Annotated[str, Form()] = "",
    ) -> Any:
        person = await self._person(uow, caller, pid)
        try:
            await people.set_status(
                uow, caller.tenant_id, person, status, actor_id=caller.principal_id
            )
        except PramaError as exc:
            flash_error_and_log(request, "That status could not be set", exc)
            return redirect_to(request, "admin_users")
        return redirect_to(
            request, "admin_users", flash_message=f"{person.username} is now {status}."
        )

    async def keys(self, request: Request, uow: Uow, caller: Caller) -> Any:
        pairs = await people.estate_keys(uow, caller.tenant_id)
        owners = {str(k.principal_id): owner for k, owner in pairs}
        return render(
            request,
            "admin/keys.html",
            keys=[k for k, _ in pairs],
            owners=owners,
            now=utc_now(),
        )

    async def revoke_key(self, request: Request, uow: Uow, caller: Caller, key_id: str) -> Any:
        key = await uow.api_keys.get_for_tenant(caller.tenant_id, key_id)
        if key is None:
            raise NotFoundError(
                "no such key", remedy="Your keys are listed on this page.", context={"key": key_id}
            )
        people.revoke_key(uow, key, tenant_id=caller.tenant_id, actor_id=caller.principal_id)
        return redirect_to(request, "admin_keys", flash_message=f"Key {key.key_prefix}… revoked.")

    @staticmethod
    async def _person(uow: Any, caller: Any, pid: str) -> Any:
        person = await uow.principals.get_for_tenant(caller.tenant_id, pid)
        if person is None:
            raise NotFoundError(
                "no such person in this estate",
                remedy="People are listed at /admin/users.",
                context={"principal": pid},
            )
        return person
