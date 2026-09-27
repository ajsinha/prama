"""Lineage over the API: receive OpenLineage events, and ask what a column reaches.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Query

from prama.api.deps import RelationshipReader, RelationshipWriter, Uow
from prama.lineage.graph import Column
from prama.lineage.ingest import ingest_openlineage

router = APIRouter(tags=["lineage"])


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


@router.get("/lineage/impact")
async def impact(
    caller: RelationshipReader, uow: Uow, column: str = Query(..., description="dataset.column")
) -> dict[str, Any]:
    """Everything a defect in *column* reaches, ranked by how much survives."""
    graph = await uow.lineage.graph(caller.tenant_id)
    radius = graph.blast_radius(Column.parse(column))
    return {
        "column": column,
        "reached": [
            {"column": r.column.qualified, "impact": round(r.impact, 4), "depth": r.depth}
            for r in radius.reached
        ],
    }
