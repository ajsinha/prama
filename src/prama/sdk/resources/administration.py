"""The installation's configuration and the estate's audit log. Needs ``admin``.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama.sdk.base import Resource, endpoint, namespace


@namespace("config")
class Config(Resource):
    """``prama config show``, over the API. Always redacted."""

    @endpoint("GET", "/config")
    def show(self, *, provenance: bool = False) -> Any:
        """``{"values": {dotted.key: value}}``, secrets as ``***``; with
        *provenance*, also which layer set each key."""
        return self._get("/config", provenance=provenance)


@namespace("audit")
class Audit(Resource):
    """The append-only audit log."""

    @endpoint("GET", "/audit")
    def list(
        self, *, object_kind: str | None = None, object_id: str | None = None, limit: int = 100
    ) -> Any:
        """Recent events, newest first; or those for one object."""
        params: dict[str, Any] = {"limit": limit}
        if object_kind:
            params["object_kind"] = object_kind
        if object_id:
            params["object_id"] = object_id
        return self._get("/audit", **params)
