"""Usage from query history: a priority signal, and never a quality one.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import ast
import json
from datetime import UTC, datetime
from pathlib import Path

from prama.db import Database
from prama.lineage import usage
from prama.semantic.services.datasets import DatasetService
from prama.semantic.services.priorities import priorities

TODAY = datetime.now(UTC).date().isoformat()
SNOWFLAKE = [
    {
        "QUERY_START_TIME": f"{TODAY} 09:00:00",
        "USER_NAME": "ANA",
        "DIRECT_OBJECTS_ACCESSED": json.dumps([{"objectName": "PROD.MART.TRADES"}]),
    },
    {
        "QUERY_START_TIME": f"{TODAY} 09:05:00",
        "USER_NAME": "BEN",
        "DIRECT_OBJECTS_ACCESSED": json.dumps(
            [{"objectName": "PROD.MART.TRADES"}, {"objectName": "PROD.RAW.SHADOW_BOOK"}]
        ),
    },
    {
        "QUERY_START_TIME": f"{TODAY} 10:00:00",
        "USER_NAME": "ANA",
        "DIRECT_OBJECTS_ACCESSED": json.dumps([{"objectName": "PROD.MART.POSITIONS"}]),
    },
]


def test_counts_are_queries_and_distinct_readers_per_day() -> None:
    counted = usage.count("snowflake", SNOWFLAKE)
    assert counted[("prod.mart.trades", TODAY)] == (2, 2)
    assert counted[("prod.raw.shadow_book", TODAY)] == (1, 1)


def test_bigquery_and_databricks_read_their_own_shapes() -> None:
    bq = usage.count(
        "bigquery",
        [
            {
                "creation_time": f"{TODAY}T01:00:00",
                "user_email": "a@x",
                "referenced_tables": [{"dataset_id": "mart", "table_id": "trades"}],
            }
        ],
    )
    db = usage.count(
        "databricks",
        [
            {
                "event_time": f"{TODAY}T01:00:00",
                "created_by": "a",
                "source_table_full_name": "main.mart.trades",
            }
        ],
    )
    assert bq == {("mart.trades", TODAY): (1, 1)}
    assert db == {("main.mart.trades", TODAY): (1, 1)}


async def test_the_busiest_least_controlled_dataset_comes_first(
    started_database: Database, tenant_id: str
) -> None:
    async with started_database.unit_of_work() as uow:
        service = DatasetService(uow)
        await service.declare(tenant_id=tenant_id, name="Trades", criticality=4)
        await service.declare(tenant_id=tenant_id, name="Positions", criticality=4)
        control, _ = await uow.controls.declare(
            tenant_id=tenant_id, identity="p", pql="CHECK positions.a IS NOT NULL"
        )
        await uow.controls.activate(str(control.id), tenant_id=tenant_id, approved_by="bo")
        await usage.ingest(uow, tenant_id, "snowflake", SNOWFLAKE)
        again = await usage.ingest(uow, tenant_id, "snowflake", SNOWFLAKE)
        result = await priorities(uow, tenant_id)
    assert again == 3  # a re-import replaces the same days rather than doubling them
    first = result["datasets"][0]
    assert (first["slug"], first["queries"], first["readers"], first["controls"]) == (
        "trades",
        2,
        2,
        0,
    )
    assert [u["dataset"] for u in result["undeclared"]] == ["prod.raw.shadow_book"]


def test_no_score_can_read_usage() -> None:
    """The counterfactual the roadmap asked for, made structural: nothing under
    `prama.score` imports usage, so popularity cannot move a quality score."""
    root = Path(__file__).resolve().parents[2] / "src" / "prama" / "score"
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            assert not any("usage" in n or "priorities" in n for n in names), path
