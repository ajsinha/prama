"""Comments on governed objects, and the queue of what waits on a person.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama_sdk.base import Resource, body, endpoint, namespace, seg


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
        """A comment on an object, or a reply to a thread (*parent_id*). ``@name`` mentions."""
        return self._post(
            "/comments",
            body(body=text, object_kind=object_kind, object_ref=object_ref, parent_id=parent_id),
        )

    def reply(self, thread_id: str, text: str) -> Any:
        return self.post(text, parent_id=thread_id)

    @endpoint("GET", "/comments")
    def list(self, object_kind: str, object_ref: str) -> Any:
        return self._get("/comments", object_kind=object_kind, object_ref=object_ref)

    @endpoint("GET", "/comments/threads")
    def threads(self, object_kind: str, object_ref: str) -> Any:
        """The object's threads, each with its replies."""
        return self._get("/comments/threads", object_kind=object_kind, object_ref=object_ref)

    @endpoint("POST", "/comments/{root_id}/resolve")
    def resolve(self, thread_id: str) -> Any:
        """Resolve a thread: it leaves everybody's queue, and the discussion is kept."""
        return self._post(f"/comments/{seg(thread_id)}/resolve")

    @endpoint("GET", "/queue")
    def queue(
        self,
        *,
        person: str = "",
        approver: bool | None = None,
        section: str | None = None,
    ) -> Any:
        """Mentions, failures, inconsistencies and approvals waiting on you.

        *person* reads somebody else's (needs ``admin``); *approver* includes or
        leaves out approvals; *section* keeps one list.
        """
        return self._get(
            "/queue",
            person=person or None,
            approver=None if approver is None else str(approver).lower(),
            section=section,
        )
