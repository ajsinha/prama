"""The agent fleet: its administration, and the calls an agent makes.

An administrator (``admin``) issues enrolment tokens, lists the fleet, suspends,
resumes and revokes agents and reads fleet health; somebody holding
``control:approve`` dispatches a zone's work.

An agent holds no API key. It enrols with a one-use token (`enrol`), and signs
every later message with the key enrolment returned (`hello`, `report`): pass
the message's ``to_dict()`` and the key as bytes (``bytes.fromhex(key)``), and
the SDK computes ``X-Prama-Signature`` exactly as the server checks it
(`prama_sdk.signing`). The answer is a Receipt, or a Refusal (it has a
``reason``); a refusal is a normal answer, not an exception.

See docs/design/agent-fleet-http.md for the contract.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama_sdk.base import Resource, body, endpoint, namespace, seg
from prama_sdk.signing import sign

#: Named at module level: inside a resource class, ``list`` would be a method.
Strings = list[str]


@namespace("fleet")
class Fleet(Resource):
    """Agents beside the data: administration, and the agent's own protocol."""

    # -- administration ------------------------------------------------------

    @endpoint("POST", "/fleet/tokens")
    def issue_token(self, zone: str, *, name: str | None = None, hours: float | None = None) -> Any:
        """A one-use enrolment token for *zone*: ``{token, zone, expires_at}``.
        The token is shown this once."""
        return self._post("/fleet/tokens", body(zone=zone, name=name, hours=hours))

    @endpoint("GET", "/fleet/agents")
    def agents(self) -> Any:
        """Every agent: id, name, zone, state, version, capabilities, last seen,
        pending findings and last accepted sequence."""
        return self._get("/fleet/agents")

    @endpoint("POST", "/fleet/agents/{agent_id}/suspend")
    def suspend(self, agent_id: str) -> Any:
        """Refuse the agent's messages until resumed; its claims return to the queue."""
        return self._post(f"/fleet/agents/{seg(agent_id)}/suspend")

    @endpoint("POST", "/fleet/agents/{agent_id}/resume")
    def resume(self, agent_id: str) -> Any:
        """Trust a suspended agent again. A revoked agent is not reinstated."""
        return self._post(f"/fleet/agents/{seg(agent_id)}/resume")

    @endpoint("POST", "/fleet/agents/{agent_id}/revoke")
    def revoke(self, agent_id: str) -> Any:
        """Stop trusting the agent for good."""
        return self._post(f"/fleet/agents/{seg(agent_id)}/revoke")

    @endpoint("GET", "/fleet/health")
    def health(self) -> Any:
        """Stale agents, queued and claimed work per zone, unassignable work, gaps."""
        return self._get("/fleet/health")

    @endpoint("POST", "/fleet/dispatch")
    def dispatch(self, zone: str, *, engine: str, datasets: Strings | None = None) -> Any:
        """Queue the active controls on *datasets* (every one, if None) for *zone*,
        compiled by the server for *engine*: ``{queued, already_queued, unassignable}``."""
        return self._post("/fleet/dispatch", body(zone=zone, engine=engine, datasets=datasets))

    # -- the agent's side ----------------------------------------------------

    @endpoint("POST", "/fleet/enrol")
    def enrol(self, token: str, *, name: str, version: str, capabilities: dict[str, Any]) -> Any:
        """Redeem *token*: ``{agent_id, key, zone, poll_after_seconds}``. The key is
        hex and shown this once; sign with ``bytes.fromhex(key)``."""
        return self._post(
            "/fleet/enrol",
            {"token": token, "name": name, "version": version, "capabilities": capabilities},
        )

    @endpoint("POST", "/fleet/hello")
    def hello(self, hello: dict[str, Any], *, key: bytes) -> Any:
        """Send a signed ``Hello.to_dict()``; a Receipt with work, or a Refusal."""
        return self._signed("/fleet/hello", hello, key)

    @endpoint("POST", "/fleet/report")
    def report(self, report: dict[str, Any], *, key: bytes) -> Any:
        """Send a signed ``Report.to_dict()``; a Receipt of what was accepted, or a
        Refusal."""
        return self._signed("/fleet/report", report, key)

    def _signed(self, path: str, message: dict[str, Any], key: bytes) -> Any:
        return self._call(
            "POST",
            path,
            json_body=message,
            headers={
                "X-Prama-Agent": str(message.get("agent_id", "")),
                "X-Prama-Signature": sign(key, message),
            },
        )
