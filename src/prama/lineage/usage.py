"""How often each dataset is read, from a warehouse's own query history.

A priority signal and nothing more. "Most used, least controlled" says where a
steward's next hour does the most good; it never changes a quality score,
because a popular dataset is not a better one, and a score that rose with
popularity would reward exactly the datasets that most need checking.

Readers take the rows of the export query each warehouse offers:

* **Snowflake** `ACCESS_HISTORY.DIRECT_OBJECTS_ACCESSED` with the user and time.
* **BigQuery** `INFORMATION_SCHEMA.JOBS.referenced_tables` with the user and time.
* **Databricks** `system.access.table_lineage` read events.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

from prama.core.errors import ValidationError

QUERIES: dict[str, str] = {
    "snowflake": (
        "SELECT query_start_time, user_name, direct_objects_accessed\n"
        "FROM snowflake.account_usage.access_history\n"
        "WHERE query_start_time >= DATEADD(day, -30, CURRENT_TIMESTAMP())"
    ),
    "bigquery": (
        "SELECT creation_time, user_email, referenced_tables\n"
        "FROM `region-us`.INFORMATION_SCHEMA.JOBS\n"
        "WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)\n"
        "  AND state = 'DONE'"
    ),
    "databricks": (
        "SELECT event_time, created_by, source_table_full_name\n"
        "FROM system.access.table_lineage\n"
        "WHERE event_date >= date_sub(current_date(), 30)\n"
        "  AND source_table_full_name IS NOT NULL"
    ),
}


def _get(row: Mapping[str, Any], *names: str) -> Any:
    lowered = {str(k).lower(): v for k, v in row.items()}
    return next((lowered[n] for n in names if lowered.get(n) not in (None, "")), None)


def _objects(row: Mapping[str, Any], warehouse: str) -> list[str]:
    if warehouse == "snowflake":
        raw = _get(row, "direct_objects_accessed") or []
        items = json.loads(raw) if isinstance(raw, str) else raw
        return [str(i.get("objectName", "")).lower() for i in items if i.get("objectName")]
    if warehouse == "bigquery":
        raw = _get(row, "referenced_tables") or []
        items = json.loads(raw) if isinstance(raw, str) else raw
        return [
            f"{i.get('dataset_id', '')}.{i.get('table_id', '')}".lower()
            for i in items
            if i.get("table_id")
        ]
    name = _get(row, "source_table_full_name")
    return [str(name).lower()] if name else []


def count(
    warehouse: str, rows: Iterable[Mapping[str, Any]]
) -> dict[tuple[str, str], tuple[int, int]]:
    """(dataset, day) -> (queries, distinct users)."""
    if warehouse not in QUERIES:
        raise ValidationError(
            f"no usage reader for {warehouse!r}", remedy=f"One of: {', '.join(sorted(QUERIES))}."
        )
    queries: dict[tuple[str, str], int] = {}
    users: dict[tuple[str, str], set[str]] = {}
    for row in rows:
        day = str(_get(row, "query_start_time", "creation_time", "event_time") or "")[:10]
        who = str(_get(row, "user_name", "user_email", "created_by") or "")
        if not day:
            continue
        for dataset in set(_objects(row, warehouse)):
            key = (dataset, day)
            queries[key] = queries.get(key, 0) + 1
            if who:
                users.setdefault(key, set()).add(who)
    return {key: (n, len(users.get(key, ()))) for key, n in queries.items()}


def pairs(warehouse: str, rows: Iterable[Mapping[str, Any]]) -> dict[tuple[str, str, str], int]:
    """(dataset, dataset, day) -> queries that read both. Ordered pairs, each once."""
    together: dict[tuple[str, str, str], int] = {}
    for row in rows:
        day = str(_get(row, "query_start_time", "creation_time", "event_time") or "")[:10]
        read = sorted(set(_objects(row, warehouse)))
        if not day or len(read) < 2:
            continue
        for i, first in enumerate(read):
            for second in read[i + 1 :]:
                key = (first, second, day)
                together[key] = together.get(key, 0) + 1
    return together


async def ingest(uow: Any, tenant_id: str, warehouse: str, rows: list[Mapping[str, Any]]) -> int:
    """Record the export; a re-import of the same days replaces them. Returns days recorded."""
    counted = count(warehouse, rows)
    for (dataset, day), (n, who) in counted.items():
        await uow.usage.record(
            tenant_id, dataset=dataset[:255], day=day, source=warehouse, queries=n, users=who
        )
    for (first, second, day), n in pairs(warehouse, rows).items():
        await uow.usage.record_pair(
            tenant_id, pair=(first[:255], second[:255]), day=day, source=warehouse, queries=n
        )
    return len(counted)
