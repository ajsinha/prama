"""Signing in, who you are, and the estates on this installation.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama_sdk.base import Resource, body, endpoint, namespace


@namespace("auth")
class Auth(Resource):
    """Credentials: exchange a password for a key, see who a key is, end it."""

    @endpoint("POST", "/auth/token")
    def token(
        self,
        username: str,
        password: str,
        *,
        tenant: str = "",
        name: str = "sdk",
        hours: int | None = None,
    ) -> Any:
        """An expiring API key for this person, carrying their roles' scopes."""
        return self._post(
            "/auth/token",
            body(username=username, password=password, tenant=tenant, name=name, hours=hours),
        )

    @endpoint("GET", "/auth/me")
    def me(self) -> Any:
        """Who this client acts as: estate, person and scopes."""
        return self._get("/auth/me")

    @endpoint("POST", "/auth/revoke")
    def revoke(self) -> Any:
        """Revoke the key this client uses. It stops working at once."""
        return self._post("/auth/revoke")


@namespace("tenants")
class Tenants(Resource):
    """Estates. Creating one makes you its first administrator."""

    @endpoint("GET", "/tenants/current")
    def current(self) -> Any:
        return self._get("/tenants/current")

    @endpoint("GET", "/tenants")
    def list(self) -> Any:
        """Every active estate. Needs ``tenant:admin``."""
        return self._get("/tenants")

    @endpoint("POST", "/tenants")
    def create(
        self,
        slug: str,
        display_name: str,
        *,
        residency: str | None = None,
        hours: int | None = None,
    ) -> Any:
        """Create an estate. Returns ``{"tenant": …, "credentials": {"api_key": …}}``;
        ``client.as_key(result["credentials"]["api_key"])`` works in it."""
        return self._post(
            "/tenants",
            body(slug=slug, display_name=display_name, residency=residency, hours=hours),
        )


@namespace("system")
class System(Resource):
    """The server itself: health and what it can do."""

    @endpoint("GET", "/health")
    def health(self) -> Any:
        return self._get("/health")

    @endpoint("GET", "/capabilities")
    def capabilities(self) -> Any:
        return self._get("/capabilities")
