"""Lineage from warehouse query history: Snowflake, Databricks and BigQuery exports.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json

import pytest

from prama.core.errors import ValidationError
from prama.db import Database
from prama.lineage import history

SNOWFLAKE = [
    {
        "QUERY_ID": "01a",
        "OBJECTS_MODIFIED": json.dumps(
            [
                {
                    "objectName": "MART.POSITIONS",
                    "columns": [
                        {
                            "columnName": "EXPOSURE_USD",
                            "directSources": [
                                {"objectName": "STG.TRADES", "columnName": "NOTIONAL"},
                                {"objectName": "REF.FX", "columnName": "RATE"},
                            ],
                        },
                        {"columnName": "DESK", "baseSources": [{"objectName": "RAW.D"}]},
                    ],
                }
            ]
        ),
    },
    {"QUERY_ID": "02b", "OBJECTS_MODIFIED": "not json"},
]


def _pairs(edges: list) -> set[tuple[str, str]]:
    return {(e.source.qualified, e.target.qualified) for e in edges}


def test_snowflake_direct_sources_become_edges_and_the_rest_are_gaps() -> None:
    edges, gaps = history.snowflake(SNOWFLAKE)
    assert _pairs(edges) == {
        ("stg.trades.notional", "mart.positions.exposure_usd"),
        ("ref.fx.rate", "mart.positions.exposure_usd"),
    }
    assert {g.kind for g in gaps} == {"unread", "unparsed"}


def test_databricks_rows_are_one_edge_each() -> None:
    rows = [
        {
            "source_table_full_name": "main.stg.trades",
            "source_column_name": "acct",
            "target_table_full_name": "main.mart.positions",
            "target_column_name": "account_id",
            "entity_type": "NOTEBOOK",
        },
        {"source_table_full_name": "main.a", "target_table_full_name": "main.b"},  # table-level
    ]
    edges, _ = history.databricks(rows)
    assert _pairs(edges) == {("main.stg.trades.acct", "main.mart.positions.account_id")}


def test_bigquery_sql_goes_through_the_parser() -> None:
    rows = [{"job_id": "j1", "query": "INSERT INTO mart.p (a) SELECT x FROM stg.t"}]
    edges, _ = history.bigquery(rows)
    assert ("stg.t.x", "mart.p.a") in _pairs(edges)


async def test_an_export_is_recorded_as_a_warehouse_source(
    started_database: Database, tenant_id: str
) -> None:
    async with started_database.unit_of_work() as uow:
        run = await history.ingest_history(uow, tenant_id, "snowflake", SNOWFLAKE, source="sf")
        edges = await uow.lineage.edges(tenant_id)
        with pytest.raises(ValidationError, match="no query-history reader"):
            await history.ingest_history(uow, tenant_id, "oracle", [], source="x")
    assert run.edges == 2 and run.gaps == 2
    assert {e.method for e in edges} == {"history:snowflake"}
