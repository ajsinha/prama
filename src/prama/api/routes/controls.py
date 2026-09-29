"""Controls and the language they are written in: author, decide, check, compile.

What the control studio, the controls list and ``prama control …`` do, for a
program. Two rules shape it:

* **Authoring and approving are different scopes.** Declaring a control needs
  ``control:propose``; activating, suppressing and retiring it need
  ``control:approve``. That is maker-checker expressed as a permission, and an
  API that let one scope do both would erase it.
* **Checking a control is reading.** Parsing, type-checking, explaining and
  compiling store nothing, so they need only ``control:read`` — an owner who
  approves controls must be able to read one first. They are POSTs because a
  control's text belongs in a body, not a URL.

Every judgement comes from `prama.controls.language`, which the console and
the CLI call too, so the three surfaces cannot disagree about a control.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query, Request, status
from pydantic import Field

from prama.api.deps import (
    ControlApprover,
    ControlProposer,
    ControlReader,
    Uow,
)
from prama.api.schemas import PramaModel
from prama.controls import language
from prama.controls.runs import open_connection
from prama.core.clock import utc_now
from prama.core.errors import NotFoundError, ValidationError
from prama.core.provenance import content_hash
from prama.db.temporal import Provenance
from prama.schedule import describe as describe_schedule

router = APIRouter(tags=["controls"])

#: How a control may have come to exist, as the schema permits.
ORIGINS = ("declaration", "import", "document", "mining", "example", "induction")
#: The states a control can be in. Only ``active`` runs.
STATUSES = ("proposed", "active", "suppressed", "retired")
#: The longest backtest one request runs; past a quarter the answer is about
#: how the business changed, not about the control (as in the studio).
MAX_PERIODS = 120


# ---------------------------------------------------------------------------
# Bodies
# ---------------------------------------------------------------------------


class ControlIn(PramaModel):
    pql: str = Field(min_length=1, description="One control, in PQL. The text is the authority.")
    identity: str = Field(
        default="",
        max_length=128,
        description=(
            "Stable across edits. Omit for a new control (derived from the text); pass the "
            "existing identity to amend a control rather than create a second one."
        ),
    )
    rule: str = Field(default="authored", max_length=128)
    source_ref: str = Field(default="", max_length=128, description="What it derives from.")
    criticality: int = Field(default=4, ge=1, le=4)
    schedule: str = Field(default="", max_length=64, description="'daily', '06:30', 'manual'…")
    owner_id: str | None = None
    origin: str = "declaration"
    reason: str = ""


class DecisionIn(PramaModel):
    reason: str = ""


class SuppressIn(PramaModel):
    until: str = Field(min_length=1, description="ISO-8601: when it should run again.")
    because: str = Field(min_length=1, description="Why it is being silenced.")


class SourceIn(PramaModel):
    source: str = Field(description="PQL text: one control or a suite.")


class CheckIn(SourceIn):
    catalogue: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Schemas to check against, as `prama lsp catalogue` writes them. Omitted: the "
            "estate's declared datasets."
        ),
    )


class CompileIn(SourceIn):
    dialect: str = "postgresql"
    fuse: bool = Field(default=False, description="Group controls sharing a scope into one scan.")


class PositionIn(SourceIn):
    line: int = Field(default=1, ge=1)
    column: int = Field(default=1, ge=1)


class BuildIn(PramaModel):
    """The rule builder's answers. Which fields a rule needs: GET /rule-builder."""

    dataset: str
    rule: str
    severity: str = "major"
    because: str = ""
    column: str = ""
    columns: str = ""
    values: str = ""
    pattern: str = ""
    lower: str = ""
    upper: str = ""
    minimum: str = ""
    maximum: str = ""
    reference_dataset: str = ""
    reference_column: str = ""
    tolerance_minutes: str = "0"
    due_time: str = ""
    calendar: str = ""
    tolerated_percent: str = ""
    unknown_is_violation: bool = True


class PreviewIn(PramaModel):
    pql: str = Field(min_length=1, max_length=20_000)
    connection_id: str
    max_rows: int = Field(default=0, ge=0, description="A scan ceiling; zero is unbounded.")


class BacktestIn(PreviewIn):
    period_column: str = Field(min_length=1, description="The column carrying the business date.")
    days: int = Field(default=30, ge=1, le=MAX_PERIODS)


# ---------------------------------------------------------------------------
# Shapes
# ---------------------------------------------------------------------------


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def control_out(version: Any) -> dict[str, Any]:
    """A control's current (or historical) version, as JSON."""
    return {
        "id": str(version.control_id),
        "identity": version.control.identity,
        "version": version.version,
        "name": version.name,
        "dataset": version.dataset,
        "pql": version.pql,
        "plan_id": version.plan_id,
        "content_hash": version.content_hash,
        "severity": version.severity,
        "dimensions": list(version.dimensions_json or []),
        "criticality": version.criticality,
        "origin": version.origin,
        "rule": version.rule,
        "source_ref": version.source_ref,
        "status": version.status,
        "suppressed_until": version.suppressed_until,
        "suppressed_because": version.suppressed_because,
        "schedule": version.schedule,
        # Through the parser rather than echoed, so a schedule that cannot be
        # read shows as unreadable instead of looking fine and never firing.
        "schedule_described": describe_schedule(version.schedule),
        "owner_id": version.owner_id,
        "valid_from": _iso(version.valid_from),
        "valid_to": _iso(version.valid_to),
        "recorded_at": _iso(version.recorded_at),
        "superseded_at": _iso(version.superseded_at),
        "authored_by": version.authored_by,
        "approved_by": version.approved_by,
        "change_reason": version.change_reason,
        "is_current": version.is_current,
    }


async def stored_out(uow: Any, tenant_id: str, control_id: Any) -> dict[str, Any]:
    """A control as stored now, read back after a write.

    Read back rather than rendered from the object the write returned: that
    object's control row is not loaded, and loading it lazily inside an async
    session is not something the ORM will do.
    """
    return control_out(await _require(uow, tenant_id, str(control_id)))


async def _require(uow: Any, tenant_id: str, control_id: str) -> Any:
    version = await uow.controls.by_control_id(tenant_id, control_id)
    if version is None:
        raise NotFoundError(
            f"control {control_id!r} does not exist in this estate",
            remedy="Check the identifier, or list the controls.",
            context={"control_id": control_id},
        )
    return version


# ---------------------------------------------------------------------------
# The estate of controls
# ---------------------------------------------------------------------------


@router.get("/controls")
async def list_controls(
    caller: ControlReader,
    uow: Uow,
    state: str | None = Query(
        default=None, alias="status", description="proposed | active | suppressed | retired"
    ),
    dataset: str | None = Query(default=None, description="The dataset a control checks."),
    overdue: bool = Query(
        default=False, description="Only controls silenced past their expiry and not re-enabled."
    ),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    """The controls, filtered. Only ``active`` controls run."""
    if state is not None and state not in STATUSES:
        raise ValidationError(
            f"{state!r} is not a control status",
            remedy=f"One of: {', '.join(STATUSES)}.",
            context={"status": state},
        )
    if overdue:
        versions = await uow.controls.silenced_past_expiry(caller.tenant_id, utc_now().isoformat())
    elif state is not None:
        versions = await uow.controls.of_status(caller.tenant_id, state)
    elif dataset:
        versions = await uow.controls.for_dataset(caller.tenant_id, dataset)
    else:
        versions = await uow.controls.list_current(caller.tenant_id, limit=limit, offset=offset)
    if dataset:
        versions = [v for v in versions if v.dataset == dataset]
    if state is not None:
        versions = [v for v in versions if v.status == state]
    return [control_out(v) for v in versions]


@router.post("/controls", status_code=status.HTTP_201_CREATED)
async def declare_control(body: ControlIn, caller: ControlProposer, uow: Uow) -> dict[str, Any]:
    """Author a control. It is a proposal until somebody with ``control:approve`` activates it.

    Declaring the same identity again amends that control; declaring identical
    text again changes nothing.
    """
    if body.origin not in ORIGINS:
        raise ValidationError(
            f"{body.origin!r} is not a way a control comes to exist",
            remedy=f"One of: {', '.join(ORIGINS)}.",
            context={"origin": body.origin},
        )
    if body.schedule.strip():
        from prama.schedule import parse as parse_schedule

        # Refused here rather than stored: an unreadable schedule is a control
        # that will never run and has no verdict to say so.
        parse_schedule(body.schedule)
    _, version = await uow.controls.declare(
        tenant_id=caller.tenant_id,
        identity=body.identity or content_hash(body.pql),
        pql=body.pql,
        origin=body.origin,
        rule=body.rule,
        source_ref=body.source_ref,
        status="proposed",
        criticality=body.criticality,
        schedule=body.schedule,
        owner_id=body.owner_id,
        authored_by=caller.principal_id,
        reason=body.reason or "declared over the API",
    )
    return await stored_out(uow, caller.tenant_id, version.control_id)


@router.get("/controls/{control_id}")
async def get_control(control_id: str, caller: ControlReader, uow: Uow) -> dict[str, Any]:
    return control_out(await _require(uow, caller.tenant_id, control_id))


@router.get("/controls/{control_id}/history")
async def control_history(control_id: str, caller: ControlReader, uow: Uow) -> list[dict[str, Any]]:
    """Every version, oldest first: what the control said, and who agreed, when."""
    await _require(uow, caller.tenant_id, control_id)
    return [
        control_out(v) for v in await uow.controls.history(control_id, tenant_id=caller.tenant_id)
    ]


@router.post("/controls/{control_id}/activate")
async def activate_control(
    control_id: str, body: DecisionIn, caller: ControlApprover, uow: Uow
) -> dict[str, Any]:
    """Approve: the control begins to run. Recorded with who approved it and why."""
    current = await _require(uow, caller.tenant_id, control_id)
    if current.status == "retired":
        raise ValidationError(
            "a retired control cannot be activated",
            remedy="Declare it again; a retirement is kept so its evidence stays attributable.",
            context={"control_id": control_id},
        )
    version = await uow.controls.activate(
        control_id,
        tenant_id=caller.tenant_id,
        approved_by=caller.require_principal(),
        reason=body.reason or "accepted",
    )
    return await stored_out(uow, caller.tenant_id, version.control_id)


@router.post("/controls/{control_id}/suppress")
async def suppress_control(
    control_id: str, body: SuppressIn, caller: ControlApprover, uow: Uow
) -> dict[str, Any]:
    """Silence a running control, with an expiry and a reason — both required."""
    await _require(uow, caller.tenant_id, control_id)
    version = await uow.controls.suppress(
        control_id,
        tenant_id=caller.tenant_id,
        until=body.until,
        because=body.because,
        by=caller.principal_id,
    )
    return await stored_out(uow, caller.tenant_id, version.control_id)


@router.post("/controls/{control_id}/retire")
async def retire_control(
    control_id: str, body: DecisionIn, caller: ControlApprover, uow: Uow
) -> dict[str, Any]:
    """Stop running a control. Never deleted: its evidence stays attributable."""
    await _require(uow, caller.tenant_id, control_id)
    version = await uow.controls.retire(
        control_id,
        tenant_id=caller.tenant_id,
        provenance=Provenance(
            authored_by=caller.principal_id,
            approved_by=caller.principal_id,
            reason=body.reason or "retired",
        ),
    )
    return await stored_out(uow, caller.tenant_id, version.control_id)


# ---------------------------------------------------------------------------
# Trying a control against data, without recording anything
# ---------------------------------------------------------------------------


@router.post("/controls/preview")
async def preview_control(
    body: PreviewIn, request: Request, caller: ControlProposer, uow: Uow
) -> dict[str, Any]:
    """Run a control once against a registered connection. Writes no evidence.

    A preview runs an unapproved control, often over a bounded scan, and
    evidence a regulator may read has to be the record of a control the estate
    agreed to, run in full.
    """
    from prama.execute.preview import Preview

    _, opened = await open_connection(
        uow, caller.tenant_id, body.connection_id, request.app.state.config
    )
    try:
        preview = Preview(execute=opened.execute, engine=opened.engine, max_rows=body.max_rows)
        trial = await asyncio.to_thread(preview.once, body.pql)
    finally:
        opened.close()
    return {"engine": opened.engine, **trial.to_dict()}


@router.post("/controls/backtest")
async def backtest_control(
    body: BacktestIn, request: Request, caller: ControlProposer, uow: Uow
) -> dict[str, Any]:
    """Run a control once per business day over the last *days*. Writes no evidence.

    How often it would have fired, which decides whether it gets approved — and,
    three weeks later, whether it gets muted.
    """
    from prama.execute.preview import Backtest, Preview, business_dates

    _, opened = await open_connection(
        uow, caller.tenant_id, body.connection_id, request.app.state.config
    )
    dates = business_dates(utc_now().date(), days=body.days)
    try:
        preview = Preview(execute=opened.execute, engine=opened.engine, max_rows=body.max_rows)

        def trials() -> list[Any]:
            return list(preview.over(body.pql, period_column=body.period_column, periods=dates))

        found = await asyncio.to_thread(trials)
    finally:
        opened.close()
    return {
        "engine": opened.engine,
        "first": dates[0].isoformat() if dates else None,
        "last": dates[-1].isoformat() if dates else None,
        "trials": [t.to_dict() for t in found],
        "summary": Backtest(trials=tuple(found)).to_dict(),
    }


# ---------------------------------------------------------------------------
# The rule builder
# ---------------------------------------------------------------------------


@router.get("/rule-builder")
async def builder_questions(caller: ControlReader, uow: Uow) -> dict[str, Any]:
    """The questions the builder asks, and the estate's datasets and columns."""
    from prama.pql.builder import QUESTIONS

    versions = await uow.datasets.list_current(caller.tenant_id, limit=5000)
    return {
        "questions": [
            {
                "key": q.key,
                "label": q.label,
                "needs": list(q.needs),
                "dimension": q.dimension.value,
                "rationale": q.rationale,
            }
            for q in QUESTIONS
        ],
        "datasets": {
            v.slug: [
                a.name
                for a in await uow.attributes.for_dataset(v.dataset_id, tenant_id=caller.tenant_id)
            ]
            for v in versions
        },
    }


@router.post("/rule-builder")
async def build_control(body: BuildIn, caller: ControlReader) -> dict[str, Any]:
    """Assemble a control from the builder's answers, and show its PQL. Stores nothing.

    The PQL is always shown: a builder that hides its output produces controls
    nobody reviews. Declare it with POST /controls to keep it.
    """
    from prama.ir.resolve import resolved
    from prama.pql.builder import build, render_and_verify

    control = build(**body.model_dump())
    return {"pql": render_and_verify(control), "sentence": resolved(control).description}


# ---------------------------------------------------------------------------
# PQL tooling
# ---------------------------------------------------------------------------


@router.post("/pql/check")
async def check_pql(body: CheckIn, caller: ControlReader, uow: Uow) -> dict[str, Any]:
    """Parse, type-check and lint; explain what parsed. ``errors`` counts what blocks."""
    catalogue = (
        language.catalogue_from_payload(body.catalogue, where="the catalogue in this request")
        if body.catalogue is not None
        else await language.catalogue_of(uow, caller.tenant_id)
    )
    return language.check(body.source, catalogue)


@router.post("/pql/explain")
async def explain_pql(body: SourceIn, caller: ControlReader) -> dict[str, Any]:
    """Each control as the sentence a data owner approves, with spreadsheet divergences."""
    return language.explain(body.source)


@router.post("/pql/compile")
async def compile_pql(body: CompileIn, caller: ControlReader) -> dict[str, Any]:
    """The SQL each control becomes, and what it does not test; fused into scans on request."""
    return language.compile_source(body.source, body.dialect, fuse=body.fuse)


@router.post("/pql/format")
async def format_pql(body: SourceIn, caller: ControlReader) -> dict[str, Any]:
    """The controls in canonical form, so a diff is about meaning."""
    return {"source": language.format_source(body.source)}


@router.post("/pql/completions")
async def pql_completions(body: PositionIn, caller: ControlReader, uow: Uow) -> dict[str, Any]:
    """What may legitimately be typed at a position. Never a name the estate cannot satisfy."""
    from prama.pql.analysis import LanguageService

    service = LanguageService(await language.catalogue_of(uow, caller.tenant_id))
    return {
        "items": [c.to_dict() for c in service.completions(body.source, body.line, body.column)]
    }


@router.post("/pql/hover")
async def pql_hover(body: PositionIn, caller: ControlReader, uow: Uow) -> dict[str, Any]:
    """What the name at a position means, from the estate's own words."""
    from prama.pql.analysis import LanguageService

    service = LanguageService(await language.catalogue_of(uow, caller.tenant_id))
    return dict(service.hover(body.source, body.line, body.column).to_dict())


@router.get("/pql/functions")
async def pql_functions(
    caller: ControlReader, engine: str = Query(default="", description="One engine, or all.")
) -> dict[str, Any]:
    """The function catalogue, and what share of it each engine runs where the data is."""
    names, rows = language.function_coverage(engine)
    return {"functions": list(names), "coverage": [row.to_dict() for row in rows]}


# ---------------------------------------------------------------------------
# Importing another tool's tests
# ---------------------------------------------------------------------------


class ImportIn(PramaModel):
    source_format: str = Field(description="dbt | great_expectations | soda")
    text: str = Field(min_length=1, description="The file's contents.")
    declare: bool = Field(
        default=False,
        description=(
            "Also declare what came across as proposals (origin 'import'). They run only "
            "once somebody activates them."
        ),
    )


@router.post("/controls/import")
async def import_controls(body: ImportIn, caller: ControlProposer, uow: Uow) -> dict[str, Any]:
    """Translate another tool's tests to PQL, and report what did not come across.

    What was left behind is listed one by one and never as a count: those are
    the ones somebody has to decide about, and a number hides them.
    """
    from prama.importers import importer

    result = importer(body.source_format).read_text(body.text)
    report = result.to_dict()
    report["declared"] = []
    if body.declare:
        for control in result.controls:
            pql = control.render()
            _, version = await uow.controls.declare(
                tenant_id=caller.tenant_id,
                identity=content_hash(pql),
                pql=pql,
                origin="import",
                rule=f"import.{result.source_format or body.source_format}",
                status="proposed",
                authored_by=caller.principal_id,
                reason=f"imported from {result.source_format or body.source_format}",
            )
            report["declared"].append(await stored_out(uow, caller.tenant_id, version.control_id))
    return report
