"""Steward agents: the agent's own side, and their administration.

``claim``, ``heartbeat``, ``result`` and ``ask`` are what a remote steward's
process calls with its own key (``agent:work``). Everything else is for an
administrator (``admin``): create a steward, give it goals, run one now, pull
the kill switch, and decide what agents have asked for — a person decides; an
agent never approves.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama.sdk.base import Resource, body, endpoint, namespace, seg

#: Named at module level: inside a resource class, ``list`` is the method.
Strings = list[str]


@namespace("agents")
class Agents(Resource):
    """Steward agents: a remote agent's protocol, and their administration."""

    # -- the agent's side ----------------------------------------------------

    @endpoint("POST", "/agents/claim")
    def claim(self, most: int | None = None) -> Any:
        """Lease up to *most* pending tasks, each with its fencing token."""
        return self._post("/agents/claim", body(most=most))

    @endpoint("POST", "/agents/tasks/{task_id}/heartbeat")
    def heartbeat(self, task_id: str, fencing_token: int) -> Any:
        """Renew a task's lease; ``cancel`` means stop now."""
        return self._post(
            f"/agents/tasks/{seg(task_id)}/heartbeat", body(fencing_token=fencing_token)
        )

    @endpoint("POST", "/agents/tasks/{task_id}/result")
    def result(
        self, task_id: str, fencing_token: int, state: str, output: dict[str, Any] | None = None
    ) -> Any:
        """Report a task ``succeeded`` or ``failed``."""
        return self._post(
            f"/agents/tasks/{seg(task_id)}/result",
            body(fencing_token=fencing_token, state=state, output=output),
        )

    @endpoint("POST", "/agents/tasks/{task_id}/ask")
    def ask(
        self,
        task_id: str,
        fencing_token: int,
        action: dict[str, Any],
        justification: str | None = None,
    ) -> Any:
        """Park a task until a person approves *action*."""
        return self._post(
            f"/agents/tasks/{seg(task_id)}/ask",
            body(fencing_token=fencing_token, action=action, justification=justification),
        )

    # -- administration --------------------------------------------------------

    @endpoint("GET", "/agents/tools")
    def tools(self) -> Any:
        """The goal kinds a steward can pursue on the server."""
        return self._get("/agents/tools")

    @endpoint("GET", "/agents/stewards")
    def list(self) -> Any:
        """Every steward, its state and its goals."""
        return self._get("/agents/stewards")

    @endpoint("POST", "/agents/stewards")
    def create(self, name: str, *, scopes: Strings | None = None) -> Any:
        """Create a steward you sponsor. ``result["api_key"]`` is its key, shown once."""
        return self._post("/agents/stewards", body(name=name, scopes=scopes))

    @endpoint("GET", "/agents/stewards/{steward_id}")
    def get(self, steward_id: str) -> Any:
        """One steward and its goals."""
        return self._get(f"/agents/stewards/{seg(steward_id)}")

    @endpoint("POST", "/agents/stewards/{steward_id}/state")
    def set_state(self, steward_id: str, state: str) -> Any:
        """``active``, ``paused``, ``stopped`` or ``revoked`` (final)."""
        return self._post(f"/agents/stewards/{seg(steward_id)}/state", {"state": state})

    @endpoint("POST", "/agents/stewards/{steward_id}/goals")
    def add_goal(
        self,
        steward_id: str,
        kind: str,
        *,
        statement: str | None = None,
        schedule: str | None = None,
        source: str | None = None,
        remote: bool | None = None,
        approve_before_run: bool | None = None,
    ) -> Any:
        """Give a steward a goal (see `tools` for the kinds)."""
        return self._post(
            f"/agents/stewards/{seg(steward_id)}/goals",
            body(
                kind=kind,
                statement=statement,
                schedule=schedule,
                source=source,
                remote=remote,
                approve_before_run=approve_before_run,
            ),
        )

    @endpoint("POST", "/agents/goals/{goal_id}/run")
    def run(self, goal_id: str) -> Any:
        """Run a goal now, on the server; returns the finished task."""
        return self._post(f"/agents/goals/{seg(goal_id)}/run")

    @endpoint("GET", "/agents/tasks")
    def tasks(self, *, limit: int = 50) -> Any:
        """Recent tasks, newest first, with what each produced."""
        return self._get("/agents/tasks", limit=limit)

    @endpoint("GET", "/agents/approvals")
    def approvals(self) -> Any:
        """Actions agents are waiting for a person to approve."""
        return self._get("/agents/approvals")

    @endpoint("POST", "/agents/approvals/{approval_id}")
    def decide(self, approval_id: str, *, grant: bool) -> Any:
        """Grant or deny an agent's requested action, as yourself."""
        return self._post(f"/agents/approvals/{seg(approval_id)}", {"grant": grant})

    @endpoint("GET", "/agents/suggestions")
    def suggestions(self, *, state: str = "open") -> Any:
        """Model-drafted descriptions waiting for a person (or decided ones, by state)."""
        return self._get("/agents/suggestions", state=state)

    @endpoint("POST", "/agents/suggestions/{suggestion_id}")
    def decide_suggestion(self, suggestion_id: str, *, accept: bool) -> Any:
        """Accept (amending the declaration with you as author) or reject a draft."""
        return self._post(f"/agents/suggestions/{seg(suggestion_id)}", {"accept": accept})
