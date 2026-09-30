"""The agent fleet over HTTP (docs/design/agent-fleet-http.md).

Two sides, with different callers:

* **An administrator's** (``admin``): issue enrolment tokens, list the fleet,
  suspend, resume and revoke agents, read fleet health. Dispatching work to a
  zone runs the estate's controls, so it takes ``control:approve``, the scope
  that runs the estate elsewhere.
* **An agent's** (``/fleet/enrol``, ``/fleet/hello``, ``/fleet/report``). An
  agent holds no API key and never sees a scope: enrolment is authenticated by
  the one-use token, every later message by its signature
  (``X-Prama-Agent``, ``X-Prama-Signature``). These routes therefore see no
  caller, and are listed with that reason in ``tests/architecture/test_scopes.py``.

The protocol's answer is the body: a ``Receipt``, or a ``Refusal`` (which has a
``reason``). A refusal is a 200, never an HTTP error, so an agent reads one
thing to know whether to carry on.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Header, Request
from pydantic import BaseModel, Field

from prama.agent.fleet import Fleet, FleetSettings
from prama.api.deps import Administrator, Config, ControlApprover, Uow
from prama.core.clock import Clock, SystemClock

router = APIRouter(tags=["fleet"])


def _fleet(uow: Any, config: Any, request: Request) -> Fleet:
    # `app.state.clock` when a test has set one, so leases and token expiry can
    # be exercised without waiting; the system clock otherwise.
    clock: Clock = getattr(request.app.state, "clock", None) or SystemClock()
    return Fleet(uow, FleetSettings.from_config(config), clock=clock)


class TokenIn(BaseModel):
    zone: str = Field(..., min_length=1, max_length=128)
    name: str | None = Field(None, max_length=128)
    hours: float | None = Field(None, gt=0, description="default: fleet.token_hours")


class DispatchIn(BaseModel):
    zone: str = Field(..., min_length=1, max_length=128)
    engine: str = Field(..., min_length=1, max_length=32)
    datasets: list[str] | None = Field(None, description="default: every active control")


class EnrolIn(BaseModel):
    token: str = Field(..., min_length=1, max_length=256)
    name: str = Field("", max_length=128)
    version: str = Field("", max_length=64)
    capabilities: dict[str, Any] = Field(default_factory=dict)


AgentHeader = Annotated[str | None, Header(alias="X-Prama-Agent")]
SignatureHeader = Annotated[str | None, Header(alias="X-Prama-Signature")]
#: A protocol message, taken whole: the kernel rebuilds it with `from_dict`.
MessageBody = Annotated[dict[str, Any], Body()]


# -- the administrator's side -------------------------------------------------


@router.post("/fleet/tokens")
async def issue_token(
    body: TokenIn, caller: Administrator, uow: Uow, config: Config, request: Request
) -> dict[str, Any]:
    """A one-use enrolment token for a zone. The plaintext is shown this once."""
    return await _fleet(uow, config, request).issue_token(
        caller.tenant_id,
        body.zone,
        name=body.name or "",
        hours=body.hours,
        issued_by=caller.principal_id,
    )


@router.get("/fleet/agents")
async def agents(
    caller: Administrator, uow: Uow, config: Config, request: Request
) -> list[dict[str, Any]]:
    """Every agent in this estate, whatever its state."""
    return await _fleet(uow, config, request).agents(caller.tenant_id)


@router.post("/fleet/agents/{agent_id}/suspend")
async def suspend(
    agent_id: str, caller: Administrator, uow: Uow, config: Config, request: Request
) -> dict[str, Any]:
    """Refuse the agent's messages until resumed; its claims return to the queue."""
    return await _fleet(uow, config, request).suspend(caller.tenant_id, agent_id)


@router.post("/fleet/agents/{agent_id}/resume")
async def resume(
    agent_id: str, caller: Administrator, uow: Uow, config: Config, request: Request
) -> dict[str, Any]:
    """Trust a suspended agent again. A revoked one is not reinstated."""
    return await _fleet(uow, config, request).resume(caller.tenant_id, agent_id)


@router.post("/fleet/agents/{agent_id}/revoke")
async def revoke(
    agent_id: str, caller: Administrator, uow: Uow, config: Config, request: Request
) -> dict[str, Any]:
    """Stop trusting the agent for good; its next message gets a permanent refusal."""
    return await _fleet(uow, config, request).revoke(caller.tenant_id, agent_id)


@router.get("/fleet/health")
async def health(
    caller: Administrator, uow: Uow, config: Config, request: Request
) -> dict[str, Any]:
    """Stale agents, work per zone, what nothing can run, and reported gaps."""
    return await _fleet(uow, config, request).health(caller.tenant_id)


@router.post("/fleet/dispatch")
async def dispatch(
    body: DispatchIn, caller: ControlApprover, uow: Uow, config: Config, request: Request
) -> dict[str, Any]:
    """Queue the active controls on these datasets for the zone, compiled here."""
    return await _fleet(uow, config, request).dispatch(
        caller.tenant_id,
        body.zone,
        engine=body.engine,
        datasets=body.datasets,
        by=caller.principal_id,
    )


# -- the agent's side -----------------------------------------------------------


@router.post("/fleet/enrol")
async def enrol(body: EnrolIn, uow: Uow, config: Config, request: Request) -> dict[str, Any]:
    """Redeem a token for an agent id and its key. The key is shown this once."""
    return await _fleet(uow, config, request).enrol(
        body.token, name=body.name, version=body.version, capabilities=body.capabilities
    )


@router.post("/fleet/hello")
async def hello(
    body: MessageBody,
    uow: Uow,
    config: Config,
    request: Request,
    agent: AgentHeader = None,
    signature: SignatureHeader = None,
) -> dict[str, Any]:
    """A signed Hello; answered with a Receipt carrying work, or a Refusal."""
    return await _fleet(uow, config, request).hello(body, agent_header=agent, signature=signature)


@router.post("/fleet/report")
async def report(
    body: MessageBody,
    uow: Uow,
    config: Config,
    request: Request,
    agent: AgentHeader = None,
    signature: SignatureHeader = None,
) -> dict[str, Any]:
    """A signed Report; answered with a Receipt of what was accepted, or a Refusal."""
    return await _fleet(uow, config, request).report(body, agent_header=agent, signature=signature)
