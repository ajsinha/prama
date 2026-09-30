"""People, roles, API keys, and your own account.

``client.principals``, ``client.roles`` and ``client.api_keys.list_all()`` /
``issue()`` / ``revoke_any()`` are administration and need the ``admin``
scope. ``client.account`` and ``client.api_keys.list()`` / ``create()`` /
``revoke()`` act on the signed-in holder's own account and need nothing more.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama_sdk.base import Resource, body, endpoint, namespace, seg

#: Named at module level: inside a resource class, ``list`` is the method.
Strings = list[str]


@namespace("principals")
class Principals(Resource):
    """The people (and service principals) of this estate. Needs ``admin``."""

    @endpoint("GET", "/principals")
    def list(self) -> Any:
        """Everybody, with roles, status and whether they can sign in."""
        return self._get("/principals")

    @endpoint("POST", "/principals")
    def create(
        self,
        username: str,
        *,
        roles: Strings | None = None,
        password: str | None = None,
        display_name: str | None = None,
        email: str | None = None,
        kind: str | None = None,
    ) -> Any:
        """Create somebody. Without a password they exist but cannot sign in yet."""
        return self._post(
            "/principals",
            body(
                username=username,
                roles=roles,
                password=password,
                display_name=display_name,
                email=email,
                kind=kind,
            ),
        )

    @endpoint("GET", "/principals/{principal}")
    def get(self, principal: str) -> Any:
        """One person, by id or username."""
        return self._get(f"/principals/{seg(principal)}")

    @endpoint("PUT", "/principals/{principal}/roles")
    def set_roles(self, principal: str, roles: Strings) -> Any:
        """Replace a person's roles with exactly *roles*."""
        return self._put(f"/principals/{seg(principal)}/roles", {"roles": list(roles)})

    @endpoint("POST", "/principals/{principal}/password")
    def reset_password(self, principal: str, password: str) -> Any:
        """Set somebody else's password; their console sessions end."""
        return self._post(f"/principals/{seg(principal)}/password", {"password": password})

    @endpoint("POST", "/principals/{principal}/status")
    def set_status(self, principal: str, status: str) -> Any:
        """``"active"`` or ``"disabled"``. Disabling stops every key they hold."""
        return self._post(f"/principals/{seg(principal)}/status", {"status": status})

    def disable(self, principal: str) -> Any:
        """Offboard somebody: no sign-in, no session, no working key."""
        return self.set_status(principal, "disabled")

    def enable(self, principal: str) -> Any:
        """Undo `disable`."""
        return self.set_status(principal, "active")


@namespace("roles")
class Roles(Resource):
    """The built-in roles and the scopes they grant. Needs ``admin``."""

    @endpoint("GET", "/roles")
    def list(self) -> Any:
        """``{"roles": [{name, description, permissions}], "scopes": {scope: meaning}}``."""
        return self._get("/roles")


@namespace("api_keys")
class ApiKeys(Resource):
    """API keys: your own, and (for an administrator) every key in the estate."""

    @endpoint("GET", "/account/keys")
    def list(self) -> Any:
        """Your keys, revoked and expired ones included, newest first."""
        return self._get("/account/keys")

    @endpoint("POST", "/account/keys")
    def create(self, name: str, scopes: Strings, *, days: int | None = None) -> Any:
        """Mint a key of your own. ``result["plaintext"]`` is the only copy.

        Each scope must be one the key you are using already holds.
        """
        return self._post("/account/keys", body(name=name, scopes=list(scopes), days=days))

    @endpoint("POST", "/account/keys/{key_id}/revoke")
    def revoke(self, key_id: str) -> Any:
        """Revoke one of your own keys."""
        return self._post(f"/account/keys/{seg(key_id)}/revoke")

    @endpoint("GET", "/api-keys")
    def list_all(self) -> Any:
        """Every key in the estate, with its owner. Needs ``admin``."""
        return self._get("/api-keys")

    @endpoint("POST", "/api-keys")
    def issue(self, principal: str, name: str, scopes: Strings, *, days: int | None = None) -> Any:
        """Mint a key acting as *principal* (username or id), with explicit scopes.
        Needs ``admin``; ``result["plaintext"]`` is the only copy."""
        return self._post(
            "/api-keys", body(principal=principal, name=name, scopes=list(scopes), days=days)
        )

    @endpoint("POST", "/api-keys/{key_id}/revoke")
    def revoke_any(self, key_id: str) -> Any:
        """Revoke any key in the estate. Needs ``admin``."""
        return self._post(f"/api-keys/{seg(key_id)}/revoke")


@namespace("account")
class Account(Resource):
    """Your own account: who you are, and your password."""

    @endpoint("GET", "/account")
    def get(self) -> Any:
        """You, your roles, this key's scopes and those it may grant."""
        return self._get("/account")

    @endpoint("POST", "/account/password")
    def change_password(self, current: str, new: str) -> Any:
        """Change your password; the current one is required."""
        return self._post("/account/password", {"current": current, "new": new})
