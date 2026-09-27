"""Column lineage from a warehouse's own query history: Snowflake, Databricks, BigQuery.

The warehouse already knows what it ran. These readers turn its history rows
into lineage edges, from an export (JSON or CSV) or from the query below run
through a connector. The query is printed for the operator rather than run by
Prama on its own, because history views need privileges that a quality tool
should be granted deliberately.

* **Snowflake** `ACCESS_HISTORY.OBJECTS_MODIFIED` records, per written column,
  its `directSources`: lineage the warehouse computed itself, taken as
  `parsed`.
* **Databricks** `system.access.column_lineage` rows are one edge each, also
  taken as `parsed`.
* **BigQuery** `INFORMATION_SCHEMA.JOBS` keeps the SQL text; it is read by the
  SQL parser like any other SQL, and its gaps are reported.

Only writes produce edges: a SELECT that wrote nothing moved no value.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

from prama.core.errors import ValidationError
from prama.lineage.graph import Column, Edge, Transform
from prama.lineage.sql import Gap, SqlLineage

#: What to run in each warehouse to export the rows these readers take.
QUERIES: dict[str, str] = {
    "snowflake": (
        "SELECT query_id, query_start_time, objects_modified\n"
        "FROM snowflake.account_usage.access_history\n"
        "WHERE query_start_time >= DATEADD(day, -7, CURRENT_TIMESTAMP())\n"
        "  AND ARRAY_SIZE(objects_modified) > 0"
    ),
    "databricks": (
        "SELECT source_table_full_name, source_column_name,\n"
        "       target_table_full_name, target_column_name, entity_type, entity_id\n"
        "FROM system.access.column_lineage\n"
        "WHERE event_date >= date_sub(current_date(), 7)\n"
        "  AND target_column_name IS NOT NULL"
    ),
    "bigquery": (
        "SELECT job_id, query, destination_table\n"
        "FROM `region-us`.INFORMATION_SCHEMA.JOBS\n"
        "WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)\n"
        "  AND statement_type IN ('INSERT', 'MERGE', 'CREATE_TABLE_AS_SELECT', 'UPDATE')\n"
        "  AND state = 'DONE' AND error_result IS NULL"
    ),
}


def _key(row: Mapping[str, Any], *names: str) -> Any:
    lowered = {str(k).lower(): v for k, v in row.items()}
    for name in names:
        if name in lowered and lowered[name] not in (None, ""):
            return lowered[name]
    return None


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def snowflake(rows: Iterable[Mapping[str, Any]]) -> tuple[list[Edge], list[Gap]]:
    edges: list[Edge] = []
    gaps: list[Gap] = []
    for row in rows:
        query = str(_key(row, "query_id") or "")
        try:
            modified = _json(_key(row, "objects_modified")) or []
        except json.JSONDecodeError:
            gaps.append(Gap("unparsed", f"{query}: OBJECTS_MODIFIED is not JSON", query))
            continue
        for obj in modified:
            target = str(obj.get("objectName", "")).lower()
            for column in obj.get("columns") or []:
                sources = column.get("directSources") or []
                if not sources and column.get("baseSources"):
                    gaps.append(
                        Gap(
                            "unread",
                            f"{target}.{column.get('columnName')}: only "
                            "baseSources recorded; the direct step is not known",
                            query,
                        )
                    )
                for source in sources:
                    edges.append(
                        Edge(
                            Column(
                                str(source.get("objectName", "")).lower(),
                                str(source.get("columnName", "")).lower(),
                            ),
                            Column(target, str(column.get("columnName", "")).lower()),
                            Transform.DERIVED,
                            produced_by=f"snowflake:{query}",
                        )
                    )
    return [e for e in edges if e.source.dataset and e.source.name], gaps


def databricks(rows: Iterable[Mapping[str, Any]]) -> tuple[list[Edge], list[Gap]]:
    edges = []
    for row in rows:
        source = (_key(row, "source_table_full_name"), _key(row, "source_column_name"))
        target = (_key(row, "target_table_full_name"), _key(row, "target_column_name"))
        if all(source) and all(target):
            entity = _key(row, "entity_type", "entity_id") or "unity-catalog"
            edges.append(
                Edge(
                    Column(str(source[0]).lower(), str(source[1]).lower()),
                    Column(str(target[0]).lower(), str(target[1]).lower()),
                    Transform.DERIVED,
                    produced_by=f"databricks:{entity}",
                )
            )
    return edges, []


def bigquery(rows: Iterable[Mapping[str, Any]]) -> tuple[list[Edge], list[Gap]]:
    reader = SqlLineage(dialect="bigquery")
    edges: list[Edge] = []
    gaps: list[Gap] = []
    for row in rows:
        text = str(_key(row, "query") or "")
        job = f"bigquery:{_key(row, 'job_id') or '?'}"
        if not text:
            continue
        extraction = reader.extract(text, job=job)
        edges.extend(extraction.edges)
        gaps.extend(extraction.gaps)
    return edges, gaps


READERS = {"snowflake": snowflake, "databricks": databricks, "bigquery": bigquery}


async def ingest_history(
    uow: Any, tenant_id: str, warehouse: str, rows: list[Mapping[str, Any]], *, source: str
) -> Any:
    """Record one export of *warehouse* history as a run of the named lineage source."""
    reader = READERS.get(warehouse)
    if reader is None:
        raise ValidationError(
            f"no query-history reader for {warehouse!r}",
            remedy=f"Available: {', '.join(sorted(READERS))}.",
        )
    edges, gaps = reader(rows)
    method = "parsed:sqlglot" if warehouse == "bigquery" else f"history:{warehouse}"
    row = await uow.lineage.ensure_source(
        tenant_id, source, kind="warehouse", location=warehouse, dialect=warehouse
    )
    return await uow.lineage.record_run(
        tenant_id,
        row,
        [(edges, method, "parsed", 1.0)],
        gaps,
        statements=len(rows),
        understood=1.0 - (len(gaps) / len(rows)) if rows else 0.0,
    )
