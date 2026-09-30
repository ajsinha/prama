"""Connectors: what is installed and what each needs; and using a configured connection.

Configure a connection with ``client.connections.create(...)``; test, browse and
profile it here.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama_sdk.base import Resource, endpoint, namespace, seg


@namespace("connectors")
class Connectors(Resource):
    """Installed connectors, and test / browse / profile through a connection."""

    @endpoint("GET", "/connectors")
    def list(self) -> Any:
        """Every installed connector with its kind, capabilities and configuration form."""
        return self._get("/connectors")

    @endpoint("GET", "/connectors/{key}")
    def form(self, key: str) -> Any:
        """One connector's form: each field, whether required, its default and help."""
        return self._get(f"/connectors/{seg(key)}")

    @endpoint("POST", "/connections/{connection_id}/test")
    def test(self, connection_id: str) -> Any:
        """Reachable, and permitted? ``needs_access_request`` separates the two."""
        return self._post(f"/connections/{seg(connection_id)}/test")

    @endpoint("GET", "/connections/{connection_id}/objects")
    def browse(self, connection_id: str, *, path: str = "", limit: int | None = None) -> Any:
        """What the source holds, largest first; *path* looks inside a schema."""
        return self._call(
            "GET",
            f"/connections/{seg(connection_id)}/objects",
            params={"path": path or None, "limit": limit},
        )

    @endpoint("GET", "/connections/{connection_id}/cost")
    def cost(self, connection_id: str, target: str) -> Any:
        """What reading *target* (``schema.table``) would cost, without reading it."""
        return self._get(f"/connections/{seg(connection_id)}/cost", object=target)

    @endpoint("POST", "/connections/{connection_id}/profile")
    def profile(self, connection_id: str, target: str = "", *, limit: int | None = None) -> Any:
        """Profile one object (``schema.table``), or sweep the source when none is named."""
        payload: dict[str, Any] = {"object": target}
        if limit is not None:
            payload["limit"] = limit
        return self._post(f"/connections/{seg(connection_id)}/profile", payload)
