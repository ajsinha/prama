"""Probes and metrics for the platform that runs Prama.

* ``GET /livez`` — the process answers. Touches nothing else, so a slow
  database never gets a healthy pod restarted.
* ``GET /readyz`` — the process can do its job: the database answers and its
  schema is the one the code was built for. A pod that is not ready is taken
  out of the load balancer, not killed.
* ``GET /metrics`` — Prama's own operational metrics in the Prometheus text
  format (`prama.telemetry.metrics`). Off with
  ``observability.metrics.enabled: false``; when
  ``observability.metrics.token`` is set (in the untracked local
  configuration, like every secret) a scraper must send it as a bearer token.

At the root rather than under ``/api/v1``: they are for the platform, not for
API clients, and every orchestrator looks for them there.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse

from prama.telemetry import metrics
from prama.version import VERSION

router = APIRouter(tags=["probes"], include_in_schema=False)

PROMETHEUS = "text/plain; version=0.0.4; charset=utf-8"


@router.get("/livez")
async def livez() -> JSONResponse:
    return JSONResponse({"status": "alive", "version": VERSION})


@router.get("/readyz")
async def readyz(request: Request) -> JSONResponse:
    database = getattr(request.app.state, "database", None)
    if database is None:
        return JSONResponse({"status": "starting"}, status_code=503)
    try:
        state = await database.health()
    except Exception as exc:  # reported, not raised: the answer is the point
        return JSONResponse(
            {"status": "unready", "reason": f"the database did not answer: {exc}"[:300]},
            status_code=503,
        )
    scheduler = getattr(request.app.state, "scheduler", None)
    return JSONResponse(
        {
            "status": "ready",
            "version": VERSION,
            "dialect": str(state.get("dialect", "")),
            "scheduler": "on" if scheduler is not None else "off",
        }
    )


@router.get("/metrics")
async def prometheus(request: Request) -> Response:
    config = request.app.state.config
    if not config.get_bool("observability.metrics.enabled", True):
        return PlainTextResponse("metrics are off here\n", status_code=404)
    token = str(config.get("observability.metrics.token", "") or "")
    if token:
        sent = request.headers.get("authorization", "")
        if not hmac.compare_digest(sent.encode(), f"Bearer {token}".encode()):
            return PlainTextResponse(
                "a bearer token is required\n",
                status_code=401,
                headers={"WWW-Authenticate": 'Bearer realm="metrics"'},
            )
    return Response(metrics.REGISTRY.render(), media_type=PROMETHEUS)
