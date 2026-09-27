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

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Form, Request

from prama.core.clock import utc_now
from prama.core.errors import NotFoundError, PramaError, ValidationError
from prama.security.accounts import BUILTIN_ROLES, USERNAME, grant_roles
from prama.web.deps import Caller, Uow
from prama.web.rendering import flash_error_and_log, redirect_to, render
from prama.web.routes.account_routes import revoke
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
            username = username.strip()
            if not USERNAME.match(username):
                raise ValidationError(
                    f"{username!r} is not a usable username",
                    remedy="Use letters, digits, dot, underscore and hyphen.",
                )
            if kind not in ("human", "service"):
                raise ValidationError(
                    "a principal is a human or a service",
                    remedy="Choose human or service.",
                    context={"kind": kind},
                )
            if await uow.principals.by_username(caller.tenant_id, username) is not None:
                raise ValidationError(
                    f"{username!r} already exists in this estate",
                    remedy="Choose another username, or edit the existing person.",
                )
            unknown = [r for r in roles or [] if r not in BUILTIN_ROLES]
            if unknown:
                raise ValidationError(
                    f"unknown role(s): {', '.join(unknown)}",
                    remedy=f"Roles are {', '.join(BUILTIN_ROLES)}.",
                )
            person = uow.principals.create(
                tenant_id=caller.tenant_id,
                username=username,
                display_name=display_name.strip() or username,
                kind=kind,
                email=email.strip() or None,
            )
            if password:
                uow.principals.set_password(person, password)
            await uow.flush()
            granted = await grant_roles(uow, caller.tenant_id, person, list(roles or []))
            self._audit(uow, caller, "principal.create", str(person.id), {"roles": granted})
            await uow.flush()
        except PramaError as exc:
            flash_error_and_log(request, "That person could not be created", exc)
            return redirect_to(request, "admin_users")
        return redirect_to(request, "admin_users", flash_message=f"Created {username}.")

    async def set_roles(
        self,
        request: Request,
        uow: Uow,
        caller: Caller,
        pid: str,
        roles: Annotated[list[str] | None, Form()] = None,
    ) -> Any:
        person = await self._person(uow, caller, pid)
        wanted = sorted(set(roles or []))
        try:
            if [r for r in wanted if r not in BUILTIN_ROLES]:
                raise ValidationError(
                    "only the built-in roles can be granted here",
                    remedy=f"Roles are {', '.join(BUILTIN_ROLES)}.",
                )
            if str(person.id) == caller.principal_id and ADMIN not in wanted:
                raise ValidationError(
                    "you cannot remove your own admin role",
                    remedy="Ask another administrator, so an estate cannot lose its last one.",
                )
            held = {r.name: r for r in await uow.principals.roles_of(str(person.id))}
            for name, role in held.items():
                if name not in wanted:
                    await uow.roles.revoke(str(person.id), str(role.id))
            await grant_roles(uow, caller.tenant_id, person, [r for r in wanted if r not in held])
            # Any change to the principal ends their sessions; a role removed
            # must not still be carried by a session minted before.
            person.updated_at = utc_now()
            self._audit(uow, caller, "principal.roles.set", str(person.id), {"roles": wanted})
            await uow.flush()
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
            uow.principals.set_password(person, password)
            self._audit(uow, caller, "principal.password.reset", str(person.id), {})
            await uow.flush()
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
            if status not in ("active", "disabled"):
                raise ValidationError(
                    "status is active or disabled",
                    remedy="Use the Enable or Disable button.",
                    context={"status": status},
                )
            if str(person.id) == caller.principal_id and status != "active":
                raise ValidationError(
                    "you cannot disable yourself",
                    remedy="Ask another administrator.",
                )
            person.status = status
            person.updated_at = utc_now()
            self._audit(uow, caller, f"principal.{status}", str(person.id), {})
            await uow.flush()
        except PramaError as exc:
            flash_error_and_log(request, "That status could not be set", exc)
            return redirect_to(request, "admin_users")
        return redirect_to(
            request, "admin_users", flash_message=f"{person.username} is now {status}."
        )

    async def keys(self, request: Request, uow: Uow, caller: Caller) -> Any:
        people = {
            str(p.id): p.username
            for p in await uow.principals.list_for_tenant(caller.tenant_id, limit=1000)
        }
        keys = []
        for pid in people:
            keys.extend(await uow.api_keys.for_principal(caller.tenant_id, pid))
        keys.sort(key=lambda k: k.created_at, reverse=True)
        return render(request, "admin/keys.html", keys=keys, owners=people, now=utc_now())

    async def revoke_key(self, request: Request, uow: Uow, caller: Caller, key_id: str) -> Any:
        key = await uow.api_keys.get_for_tenant(caller.tenant_id, key_id)
        if key is None:
            raise NotFoundError(
                "no such key", remedy="Your keys are listed on this page.", context={"key": key_id}
            )
        revoke(uow, key, tenant_id=caller.tenant_id, actor_id=caller.principal_id)
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

    @staticmethod
    def _audit(uow: Any, caller: Any, action: str, object_id: str, detail: dict[str, Any]) -> None:
        uow.audit.record(
            tenant_id=caller.tenant_id,
            action=action,
            object_kind="principal",
            object_id=object_id,
            actor_id=caller.principal_id,
            detail=detail,
        )
