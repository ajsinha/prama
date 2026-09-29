"""Steward agents.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama.sdk.base import Resource, body, endpoint, namespace, seg


@namespace("agents")
class Agents(Resource):
    """A remote steward agent's side: claim a task, report, ask for approval."""

    @endpoint("POST", "/agents/claim")
    def claim(self, most: int | None = None) -> Any:
        return self._post("/agents/claim", body(most=most))

    @endpoint("POST", "/agents/tasks/{task_id}/heartbeat")
    def heartbeat(self, task_id: str, fencing_token: int) -> Any:
        return self._post(
            f"/agents/tasks/{seg(task_id)}/heartbeat", body(fencing_token=fencing_token)
        )

    @endpoint("POST", "/agents/tasks/{task_id}/result")
    def result(
        self, task_id: str, fencing_token: int, state: str, output: dict[str, Any] | None = None
    ) -> Any:
        return self._post(
            f"/agents/tasks/{seg(task_id)}/result",
            body(fencing_token=fencing_token, state=state, output=output),
        )

    @endpoint("POST", "/agents/tasks/{task_id}/ask")
    def ask(
        self, task_id: str, fencing_token: int, action: str, justification: str | None = None
    ) -> Any:
        return self._post(
            f"/agents/tasks/{seg(task_id)}/ask",
            body(fencing_token=fencing_token, action=action, justification=justification),
        )
