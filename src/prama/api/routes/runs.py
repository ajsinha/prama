"""Runs the server performs, and the schedule that performs them unasked.

``POST /runs`` executes the estate's active controls against a registered
connection and records the evidence — the same `ControlRun` the CLI, the
scheduler and the case studies use. The server reads the source itself; the
caller sends no rows. What the server may read is decided by the operator
(``runs.roots``), never by the connection: see
`prama.connect.sources.confined`.

Running is ``control:approve``, like the Schedule page's "run a tick now": it
writes evidence a regulator may read, so it is the checker's act, not the
author's. Reading runs is ``evidence:read``.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request
from pydantic import Field

from prama.api.deps import ControlApprover, ControlReader, Db, EvidenceReader, Uow
from prama.api.schemas import PramaModel
from prama.controls import runs as service
from prama.core.clock import utc_now
from prama.core.errors import ForbiddenError, NotFoundError, ValidationError
from prama.schedule import Schedule
from prama.schedule import describe as describe_schedule

router = APIRouter(tags=["runs"])


class RunIn(PramaModel):
    connection_id: str = Field(min_length=1, description="A registered connection.")
    datasets: list[str] = Field(
        default_factory=list,
        description=(
            "The datasets this source holds, by slug or id. Controls on other datasets are "
            "reported as on another source rather than run and failed. Empty: every active "
            "control."
        ),
    )
    samples: bool = Field(
        default=False,
        description="Keep failing rows as evidence. They become personal data on a clock.",
    )
    due_only: bool = Field(
        default=False, description="Run only what each control's schedule says is due."
    )


def _delegates(request: Request) -> Any:
    """The host's DQ delegates, built once per application like the console's."""
    host = getattr(request.app.state, "delegate_host", None)
    if host is None:
        from prama.delegates.host import host_from_config

        host = host_from_config(request.app.state.config)
        request.app.state.delegate_host = host
    return host


@router.post("/runs")
async def run_controls(
    body: RunIn, request: Request, caller: ControlApprover, uow: Uow, database: Db
) -> dict[str, Any]:
    """Run the active controls against a connection; return every outcome and its evidence.

    The report names what did not run as well as what did: a control that
    could not be executed is an ``error`` record naming the cause, and a
    control whose data is on another source is listed as not reached.
    """
    config = request.app.state.config
    report = await service.run_connection(
        uow,
        caller.tenant_id,
        connection_id=body.connection_id,
        config=config,
        datasets=body.datasets,
        samples=body.samples,
        due_only=body.due_only,
        actor_id=caller.principal_id,
        delegates=_delegates(request),
    )
    # Committed before the anchor reads the chain head, as the CLI does: the
    # anchor is a receipt for records that exist, not for ones in flight.
    await uow.commit()
    from prama.alert.pipeline import alert_after_run
    from prama.evidence.anchor import anchor_after_run

    await anchor_after_run(database, caller.tenant_id, config)
    # Alerts after the evidence is committed, in their own unit of work; a
    # delivery failure is recorded against the alert and never fails the run.
    await alert_after_run(database, caller.tenant_id, config, run_id=str(report["run_id"]))
    return report


@router.get("/runs")
async def list_runs(
    caller: EvidenceReader,
    uow: Uow,
    limit: int = Query(default=50, ge=1, le=500),
    unfinished: bool = Query(
        default=False, description="Only runs that started and never reported."
    ),
) -> list[dict[str, Any]]:
    """Recent runs, newest first — or the ones that never finished."""
    rows = (
        await uow.evidence_runs.unfinished(caller.tenant_id)
        if unfinished
        else await uow.evidence_runs.recent(caller.tenant_id, limit=limit)
    )
    return [service.run_row_out(run) for run in rows]


@router.get("/runs/{run_id}")
async def get_run(run_id: str, caller: EvidenceReader, uow: Uow) -> dict[str, Any]:
    """One run, and every evidence record it wrote, in sequence."""
    run = await uow.evidence_runs.get(run_id)
    # Scoped by estate: a run in another estate is reported as absent, not as
    # forbidden, so its existence is not disclosed either.
    if run is None or run.tenant_id != caller.tenant_id:
        raise NotFoundError(
            f"run {run_id!r} does not exist in this estate",
            remedy="List the runs with GET /runs.",
            context={"run_id": run_id},
        )
    records = await uow.evidence.for_run(run_id, tenant_id=caller.tenant_id)
    verdicts: dict[str, int] = {}
    for record in records:
        verdicts[record.verdict] = verdicts.get(record.verdict, 0) + 1
    return {
        **service.run_row_out(run),
        "verdicts": verdicts,
        "records": [record.to_dict() for record in records],
    }


# ---------------------------------------------------------------------------
# The schedule
# ---------------------------------------------------------------------------


def _scheduled_here(request: Request, tenant_id: str) -> Any:
    scheduler = getattr(request.app.state, "scheduler", None)
    return scheduler if scheduler is not None and tenant_id in scheduler.tenants else None


@router.get("/schedule")
async def schedule(request: Request, caller: ControlReader, uow: Uow) -> dict[str, Any]:
    """Each active control's schedule, what is due now, and the scheduler's recent ticks.

    The scheduler's state is shown only to an estate it runs for; its source
    path is configuration, not something an estate's reader needs.
    """
    live = await uow.controls.live(caller.tenant_id)
    history = await uow.evidence.last_run_at(caller.tenant_id)
    now = utc_now()
    plan = Schedule().plan(
        live,
        now=now,
        last_run={cid: _instant(stamp) for cid, stamp in history.items()},
    )
    due = {item.control_id for item in plan.due}
    skipped = {item.control_id: item for item in plan.skipped}
    scheduler = _scheduled_here(request, caller.tenant_id)
    return {
        "now": now.isoformat(),
        "summary": plan.describe(),
        "scheduler": None
        if scheduler is None
        else {
            "interval_seconds": scheduler.interval,
            "dialect": scheduler.dialect,
            "ticks": [
                {
                    "started_at": t.started_at,
                    "outcome": t.outcome,
                    "detail": t.detail,
                    "executed": t.executed,
                    "verdicts": dict(t.verdicts),
                }
                for t in scheduler.history
            ],
        },
        "controls": [
            {
                "control_id": str(v.control_id),
                "name": v.name,
                "dataset": v.dataset,
                "schedule": v.schedule,
                "described": describe_schedule(v.schedule),
                "last_run_at": history.get(str(v.control_id)),
                "due": str(v.control_id) in due,
                "skipped_because": getattr(skipped.get(str(v.control_id)), "reason", None),
                "detail": getattr(skipped.get(str(v.control_id)), "detail", ""),
            }
            for v in live
        ],
    }


@router.post("/schedule/run")
async def run_schedule_now(request: Request, caller: ControlApprover) -> dict[str, Any]:
    """Run one scheduler tick now: everything due, against the configured source."""
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is None:
        raise ValidationError(
            "the scheduler is off on this server",
            remedy=(
                "Set scheduler.enabled, scheduler.against and tenancy.default_tenant, or run "
                "the estate with POST /runs against a connection."
            ),
        )
    if caller.tenant_id not in scheduler.tenants:
        # A tick runs every estate the scheduler serves; a caller from another
        # estate would be running somebody else's controls.
        raise ForbiddenError(
            "the scheduler on this server does not run this estate",
            remedy="Run it with POST /runs against a connection instead.",
        )
    tick = await scheduler.tick()
    return {
        "started_at": tick.started_at,
        "outcome": tick.outcome,
        "detail": tick.detail,
        "executed": tick.executed,
        "verdicts": dict(tick.verdicts),
    }


def _instant(stamp: str) -> Any:
    from datetime import UTC, datetime

    parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
