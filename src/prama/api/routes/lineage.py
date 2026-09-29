"""Lineage over the API: read SQL and exports into the store, and ask it questions.

Every edge says how it is known: `parsed` by the SQL parser, `inferred` by the
fallback reader or a model (waiting for a person), `confirmed` or `rejected` by
one. Scans report their gaps beside their edges, because a partial graph whose
gaps are visible is worth more than a complete-looking one whose gaps are not.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from fastapi import APIRouter, Body, File, Form, Query, UploadFile
from pydantic import BaseModel, Field

from prama.api.deps import RelationshipReader, RelationshipWriter, Uow
from prama.api.routes._knowledge import read_json, read_text
from prama.core.errors import ValidationError
from prama.lineage.graph import Column
from prama.lineage.ingest import ingest_openlineage

router = APIRouter(tags=["lineage"])


def _edge(r: Any, sources: dict[str, str] | None = None) -> dict[str, Any]:
    return {
        "id": r.id,
        "from": f"{r.source_dataset}.{r.source_column}",
        "to": f"{r.target_dataset}.{r.target_column}",
        "transform": r.transform,
        "status": r.status,
        "method": r.method,
        "confidence": r.confidence,
        "expression": r.expression,
        "produced_by": r.produced_by,
        "source": (sources or {}).get(r.source_id, r.source_id),
        "decided_by": r.decided_by,
        "decided_at": r.decided_at,
    }


def _run(run: Any) -> dict[str, Any]:
    return {
        "run": run.id,
        "statements": run.statements,
        "edges": run.edges,
        "gaps": run.gaps,
        "understood": round(run.understood, 3),
        "outcome": run.outcome,
        "detail": run.detail,
    }


@router.post("/lineage/openlineage")
async def receive_openlineage(
    caller: RelationshipWriter, uow: Uow, event: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    """Accept one OpenLineage RunEvent; store its column lineage.

    Point an OpenLineage transport (Airflow, Spark, Marquez) at this URL with
    an API key holding `relationship:write`. Replaying an event is safe: its
    edges are refreshed, never duplicated.
    """
    run = await ingest_openlineage(uow, caller.tenant_id, event)
    return {"run": run.id, "edges": run.edges}


@router.post("/lineage/scan")
async def scan(
    caller: RelationshipWriter,
    uow: Uow,
    source: str = Form(..., min_length=1, max_length=128),
    dialect: str = Form("ansi"),
    files: list[UploadFile] = File(...),
) -> dict[str, Any]:
    """Read uploaded SQL files into the store as one run of the named source.

    sqlglot reads what it can; a regex fallback reads what it cannot, and its
    edges are `inferred` until a person confirms them. Never executed.
    """
    from prama.lineage.store import scan_sql

    texts = [await read_text(f, what=f.filename or "a SQL file") for f in files]
    if not any(t.strip() for t in texts):
        raise ValidationError("nothing to scan", remedy="Upload at least one non-empty .sql file.")
    run = await scan_sql(
        uow,
        caller.tenant_id,
        source=source.strip(),
        sql=";\n".join(texts),
        location=", ".join(f.filename or "?" for f in files)[:500],
        dialect=dialect,
        by=caller.principal_id,
    )
    return {"source": source.strip(), **_run(run)}


@router.post("/lineage/dbt")
async def ingest_dbt(
    caller: RelationshipWriter,
    uow: Uow,
    manifest: UploadFile = File(...),
    source: str = Form("dbt"),
    dialect: str = Form("ansi"),
) -> dict[str, Any]:
    """A dbt project's column lineage, from its `target/manifest.json`."""
    from prama.lineage.ingest import ingest_dbt as ingest

    document = await read_json(manifest, what="the manifest")
    run = await ingest(uow, caller.tenant_id, document, source=source, dialect=dialect)
    return {"source": source, "models": run.statements, "edges": run.edges, "gaps": run.gaps}


Warehouse = Literal["snowflake", "databricks", "bigquery"]


class HistoryIn(BaseModel):
    warehouse: Warehouse
    rows: list[dict[str, Any]]
    source: str = ""


@router.get("/lineage/history/query")
async def history_query(caller: RelationshipReader, warehouse: Warehouse) -> dict[str, str]:
    """The query that exports a warehouse's history in the shape `history` reads."""
    from prama.lineage.history import QUERIES

    return {"warehouse": warehouse, "query": QUERIES[warehouse]}


@router.post("/lineage/history")
async def ingest_history(body: HistoryIn, caller: RelationshipWriter, uow: Uow) -> dict[str, Any]:
    """Column lineage from an export of a warehouse's query history."""
    from prama.lineage.history import ingest_history as ingest

    source = body.source or f"{body.warehouse}-history"
    rows: list[Mapping[str, Any]] = list(body.rows)
    run = await ingest(uow, caller.tenant_id, body.warehouse, rows, source=source)
    return {"source": source, "rows": len(body.rows), "edges": run.edges, "gaps": run.gaps}


@router.post("/lineage/import")
async def import_catalog(
    caller: RelationshipWriter,
    uow: Uow,
    vendor: Literal["manta", "alation"] = Form(...),
    export: UploadFile = File(...),
    source: str = Form(""),
) -> dict[str, Any]:
    """Lineage from a Manta or Alation export, kept beside Prama's own parse.

    What did not come across is returned under `dropped`, each with why.
    """
    from prama.importers.catalog import ingest, read

    imported = read(vendor, "lineage", await read_json(export))
    return await ingest(uow, caller.tenant_id, imported, source=source)


@router.get("/lineage/conflicts")
async def conflicts(caller: RelationshipReader, uow: Uow) -> list[dict[str, Any]]:
    """Columns where an imported catalog and Prama's own parse name different sources."""
    from prama.importers.catalog import disagreements

    return await disagreements(uow, caller.tenant_id)


@router.get("/lineage/edges")
async def edges(
    caller: RelationshipReader,
    uow: Uow,
    dataset: str = "",
    status: str = "",
    limit: int = Query(1000, ge=1, le=20000),
) -> dict[str, Any]:
    """Current edges, optionally only those touching one dataset, or in one status."""
    sources = {s.id: s.name for s in await uow.lineage.sources(caller.tenant_id)}
    rows = await uow.lineage.edges(caller.tenant_id, dataset=dataset.strip())
    if status:
        rows = [r for r in rows if r.status == status]
    return {"total": len(rows), "edges": [_edge(r, sources) for r in rows[:limit]]}


class DecisionIn(BaseModel):
    decision: Literal["confirmed", "rejected"]
    note: str = Field("", max_length=2000)


@router.post("/lineage/edges/{edge_id}/decide")
async def decide(
    edge_id: str, body: DecisionIn, caller: RelationshipWriter, uow: Uow
) -> dict[str, Any]:
    """Confirm or reject an edge. The decision outlives re-scans."""
    row = await uow.lineage.decide(
        caller.tenant_id, edge_id, body.decision, by=caller.principal_id, note=body.note
    )
    return _edge(row)


@router.get("/lineage/proposals")
async def proposals(caller: RelationshipReader, uow: Uow) -> dict[str, Any]:
    """What waits on a person: inferred edges to decide, and the controls lineage implies.

    A control resting on an inferred edge is held (`deferred_because`) until
    the edge is confirmed. The implied controls are accepted where every
    proposal is, on the proposals queue.
    """
    from prama.derive.lineage_controls import propose

    rows = await uow.lineage.edges(caller.tenant_id)
    sources = {s.id: s.name for s in await uow.lineage.sources(caller.tenant_id)}
    implied = propose(rows, await uow.controls.live(caller.tenant_id))
    # What waits on a person, so not what is already in the estate: a control
    # accepted under this identity is not offered again, as the proposals
    # queue does. It was, and invited somebody to accept it twice.
    waiting = [
        p for p in implied if await uow.controls.by_identity(caller.tenant_id, p.identity) is None
    ]
    return {
        "edges": [_edge(r, sources) for r in rows if r.status == "inferred"],
        "controls": [
            {
                "identity": p.identity,
                "rule": p.rule,
                "dataset": p.dataset,
                "pql": p.pql,
                "sentence": p.sentence,
                "deferred_because": p.deferred_because,
            }
            for p in waiting
        ],
    }


@router.get("/lineage/impact")
async def impact(
    caller: RelationshipReader, uow: Uow, column: str = Query(..., description="dataset.column")
) -> dict[str, Any]:
    """Everything a defect in *column* reaches, ranked by how much survives; and how far
    its own value can be trusted, from the controls upstream of it."""
    from prama.lineage.trust import trust_of

    try:
        origin = Column.parse(column)
    except ValueError as exc:
        raise ValidationError(str(exc), remedy="Name a column as dataset.column.") from exc
    graph = await uow.lineage.graph(caller.tenant_id)
    radius = graph.blast_radius(origin)
    latest = (await uow.evidence.latest_per_control(caller.tenant_id)).values()
    trust = trust_of(origin, graph, latest)
    return {
        "column": column,
        "reached": [
            {"column": r.column.qualified, "impact": round(r.impact, 4), "depth": r.depth}
            for r in radius.reached
        ],
        "upstream": [e.source.qualified for e in graph.upstream(origin)],
        "trust": trust.score,
        "trust_explained": trust.explain(),
    }


class ChangeIn(BaseModel):
    before: str
    after: str
    dialect: str = "ansi"


@router.post("/lineage/change")
async def change(body: ChangeIn, caller: RelationshipWriter, uow: Uow) -> dict[str, Any]:
    """What a change between two versions of a SQL file puts at risk.

    `at_risk` is true when a control or attestation sits downstream — what
    `prama lineage impact --diff` exits 3 on. Nothing is stored; it asks for
    `relationship:write` because it reads submitted SQL, as a scan does.
    """
    from prama.lineage.change import assess, changed_columns

    changed = changed_columns(body.before, body.after, dialect=body.dialect)
    result = await assess(uow, caller.tenant_id, changed)
    return result.to_dict()


@router.get("/lineage/gaps")
async def gaps(
    caller: RelationshipReader, uow: Uow, runs: int = Query(5, ge=1, le=100)
) -> list[dict[str, Any]]:
    """What the latest scans could not read."""
    out = []
    for run in await uow.lineage.runs(caller.tenant_id, limit=runs):
        for gap in await uow.lineage.gaps(caller.tenant_id, run.id):
            out.append(
                {
                    "run": run.id,
                    "kind": gap.kind,
                    "detail": gap.detail,
                    "statement": gap.statement,
                    "unit": gap.unit_ref,
                }
            )
    return out


@router.get("/lineage/runs")
async def runs(
    caller: RelationshipReader, uow: Uow, limit: int = Query(20, ge=1, le=500)
) -> list[dict[str, Any]]:
    """Recent scans and imports, newest first."""
    sources = {s.id: s.name for s in await uow.lineage.sources(caller.tenant_id)}
    return [
        {**_run(r), "source": sources.get(r.source_id, r.source_id), "started_at": r.started_at}
        for r in await uow.lineage.runs(caller.tenant_id, limit=limit)
    ]


@router.get("/lineage/sources")
async def sources(caller: RelationshipReader, uow: Uow) -> list[dict[str, Any]]:
    """The bodies of SQL, projects, warehouses and exports lineage has been read from."""
    return [
        {
            "id": s.id,
            "name": s.name,
            "kind": s.kind,
            "location": s.location,
            "dialect": s.dialect,
            "last_run_id": s.last_run_id,
        }
        for s in await uow.lineage.sources(caller.tenant_id)
    ]
