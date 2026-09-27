"""Lineage from what the bank already runs: OpenLineage events and dbt manifests.

Zero scanning: an orchestrator emitting OpenLineage (Airflow, Spark, Marquez)
and a dbt project both already know their column lineage. These readers turn
it into the lineage store's edges and gaps, labelled with where they came from.

* **OpenLineage.** One source per job (`openlineage:<namespace>/<name>`), because
  an event carries only its own job's edges; a run records them, and a replayed
  event refreshes the same edges rather than duplicating them.
* **dbt.** Column lineage comes from each model's *compiled* SQL, read by the
  SQL parser. A model with only its Jinja source is reported as a gap: Prama
  never renders a project's Jinja itself (docs/design/code-lineage §A1).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from prama.core.errors import ValidationError
from prama.lineage.graph import Column, Edge, Transform
from prama.lineage.sql import Gap, SqlLineage

#: OpenLineage transformation subtypes to Prama's transforms.
_SUBTYPES: dict[str, Transform] = {
    "IDENTITY": Transform.IDENTITY,
    "TRANSFORMATION": Transform.DERIVED,
    "AGGREGATION": Transform.AGGREGATED,
    "FILTER": Transform.FILTER,
    "JOIN": Transform.JOIN_KEY,
    "GROUP_BY": Transform.FILTER,
    "SORT": Transform.FILTER,
    "WINDOW": Transform.DERIVED,
    "CONDITIONAL": Transform.DERIVED,
}


def _transform(field: Mapping[str, Any]) -> Transform:
    steps = field.get("transformations") or []
    if not steps:
        return Transform.DERIVED  # no claim made: the least specific honest answer
    subtype = str(steps[0].get("subtype", "")).upper()
    return _SUBTYPES.get(subtype, Transform.DERIVED)


def openlineage_job(event: Mapping[str, Any]) -> str:
    job = event.get("job") or {}
    namespace, name = str(job.get("namespace", "")), str(job.get("name", ""))
    if not name:
        raise ValidationError(
            "an OpenLineage event without a job name",
            remedy="Send a RunEvent with job.namespace and job.name.",
        )
    return f"{namespace}/{name}" if namespace else name


def openlineage_edges(event: Mapping[str, Any]) -> list[Edge]:
    """Column edges from a RunEvent's `columnLineage` facets."""
    job = openlineage_job(event)
    edges: list[Edge] = []
    for output in event.get("outputs") or []:
        target = str(output.get("name", ""))
        facet = ((output.get("facets") or {}).get("columnLineage") or {}).get("fields") or {}
        for column, detail in facet.items():
            for field in detail.get("inputFields") or []:
                edges.append(
                    Edge(
                        source=Column(
                            dataset=str(field.get("name", "")),
                            name=str(field.get("field", "")).lower(),
                        ),
                        target=Column(dataset=target, name=str(column).lower()),
                        transform=_transform(field),
                        produced_by=job,
                    )
                )
    return [e for e in edges if e.source.dataset and e.source.name and e.target.dataset]


def _relation(node: Mapping[str, Any]) -> str:
    relation = str(node.get("relation_name") or "")
    if relation:
        return relation.replace('"', "").replace("`", "")
    parts = (node.get("database"), node.get("schema"), node.get("alias") or node.get("name"))
    return ".".join(str(p) for p in parts if p)


def dbt_lineage(
    manifest: Mapping[str, Any], *, dialect: str = "ansi"
) -> tuple[list[Edge], list[Gap], int]:
    """Edges, gaps and the number of models, from a dbt `manifest.json`."""
    reader = SqlLineage(dialect=dialect)
    edges: list[Edge] = []
    gaps: list[Gap] = []
    models = 0
    for unique_id, node in (manifest.get("nodes") or {}).items():
        if node.get("resource_type") not in ("model", "snapshot"):
            continue
        models += 1
        target = _relation(node)
        compiled = node.get("compiled_code") or node.get("compiled_sql")
        if not compiled:
            gaps.append(
                Gap(
                    kind="uncompiled",
                    detail=(
                        f"{unique_id} has no compiled SQL; run `dbt compile` first. Prama "
                        f"does not render a project's Jinja itself"
                    ),
                    statement=unique_id,
                )
            )
            continue
        extraction = reader.extract(f"CREATE VIEW {target} AS {compiled}", job=unique_id)
        edges.extend(extraction.edges)
        gaps.extend(extraction.gaps)
    return edges, gaps, models


async def ingest_openlineage(uow: Any, tenant_id: str, event: Mapping[str, Any]) -> Any:
    """Record one OpenLineage event as a run of its job's source."""
    job = openlineage_job(event)
    source = await uow.lineage.ensure_source(
        tenant_id, f"openlineage:{job}"[:128], kind="openlineage", location=job[:512]
    )
    edges = openlineage_edges(event)
    return await uow.lineage.record_run(
        tenant_id,
        source,
        [(edges, "ingested:openlineage", "parsed", 1.0)],
        [],
        statements=1,
        understood=1.0 if edges else 0.0,
    )


async def ingest_dbt(
    uow: Any, tenant_id: str, manifest: Mapping[str, Any], *, source: str, dialect: str = "ansi"
) -> Any:
    """Record a dbt project's column lineage as a run of the named source."""
    edges, gaps, models = dbt_lineage(manifest, dialect=dialect)
    row = await uow.lineage.ensure_source(tenant_id, source, kind="dbt", dialect=dialect)
    uncompiled = sum(1 for g in gaps if g.kind == "uncompiled")
    return await uow.lineage.record_run(
        tenant_id,
        row,
        [(edges, "parsed:dbt", "parsed", 1.0)],
        gaps,
        statements=models,
        understood=1.0 - uncompiled / models if models else 0.0,
    )
