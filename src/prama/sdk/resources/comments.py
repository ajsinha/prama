"""Comments on governed objects, and the queue of what waits on a person.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama.sdk.base import Resource, body, endpoint, namespace


@namespace("comments")
class Comments(Resource):
    """Discussion on governed objects, and what is waiting on you."""

    @endpoint("POST", "/comments")
    def post(
        self,
        text: str,
        *,
        object_kind: str | None = None,
        object_ref: str | None = None,
        parent_id: str | None = None,
    ) -> Any:
        return self._post(
            "/comments",
            body(body=text, object_kind=object_kind, object_ref=object_ref, parent_id=parent_id),
        )

    @endpoint("GET", "/comments")
    def list(self, object_kind: str, object_ref: str) -> Any:
        return self._get("/comments", object_kind=object_kind, object_ref=object_ref)

    @endpoint("GET", "/queue")
    def queue(self) -> Any:
        """Mentions, failures, inconsistencies and approvals waiting on you."""
        return self._get("/queue")
