"""Usage through the SDK: import query history, read it back, and rank by it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from tests.sdk.test_reconciliation import _signed_in_as

import prama.sdk as prama
from prama.db import Database
from prama.sdk import AsyncClient

TODAY = datetime.now(UTC).date().isoformat()


def _read(minute: int, user: str, *objects: str) -> dict[str, str]:
    return {
        "QUERY_START_TIME": f"{TODAY} 09:{minute:02d}:00",
        "USER_NAME": user,
        "DIRECT_OBJECTS_ACCESSED": json.dumps([{"objectName": o} for o in objects]),
    }


#: Trades and Positions are each read three times; Positions has a control and
#: Trades none. Ledger is read once.
HISTORY = [
    _read(0, "ANA", "PROD.MART.TRADES"),
    _read(1, "BEN", "PROD.MART.TRADES", "PROD.MART.POSITIONS"),
    _read(2, "CAL", "PROD.MART.TRADES"),
    _read(3, "ANA", "PROD.MART.POSITIONS"),
    _read(4, "ANA", "PROD.MART.POSITIONS"),
    _read(5, "BEN", "PROD.MART.LEDGER"),
]


@pytest.fixture
async def estate(client: AsyncClient, started_database: Database, tenant_id: str) -> None:
    for name in ("Trades", "Positions", "Ledger"):
        await client.datasets.declare(name, criticality=4)
    async with started_database.unit_of_work() as uow:
        control, _ = await uow.controls.declare(
            tenant_id=tenant_id, identity="p", pql="CHECK positions.a IS NOT NULL"
        )
        await uow.controls.activate(str(control.id), tenant_id=tenant_id, approved_by="bo")


async def test_the_export_query_is_the_one_the_cli_prints(client: AsyncClient) -> None:
    from prama.lineage.usage import QUERIES

    for warehouse in ("snowflake", "bigquery", "databricks"):
        assert (await client.usage.export_query(warehouse))["query"] == QUERIES[warehouse]
    with pytest.raises(prama.NotFoundError):
        await client.usage.export_query("oracle")


async def test_import_then_priorities_puts_the_busy_uncontrolled_dataset_first(
    client: AsyncClient, estate: None
) -> None:
    before = await client.usage.priorities()
    assert not before["has_usage"]

    imported = await client.usage.import_history("snowflake", HISTORY)
    assert imported == {"warehouse": "snowflake", "rows": 6, "dataset_days": 3}

    ranked = await client.usage.priorities()
    order = [(r["slug"], r["queries"], r["controls"]) for r in ranked["datasets"]]
    # Equal use; the one nobody controls comes first. The ledger, barely used, last.
    assert order == [("trades", 3, 0), ("positions", 3, 1), ("ledger", 1, 0)]
    assert ranked["datasets"][0]["readers"] == 3


async def test_a_reimport_replaces_the_day_rather_than_adding_to_it(
    client: AsyncClient, estate: None
) -> None:
    await client.usage.import_history("snowflake", HISTORY)
    await client.usage.import_history("snowflake", HISTORY)
    days = (await client.usage.daily(dataset="prod.mart.trades"))["days"]
    assert days == [
        {
            "dataset": "prod.mart.trades",
            "day": TODAY,
            "source": "snowflake",
            "queries": 3,
            "users": 3,
        }
    ]
    everything = (await client.usage.daily(days=7))["days"]
    assert {row["dataset"] for row in everything} == {
        "prod.mart.trades",
        "prod.mart.positions",
        "prod.mart.ledger",
    }


async def test_coaccess_counts_queries_that_read_both(client: AsyncClient, estate: None) -> None:
    await client.usage.import_history("snowflake", HISTORY)
    pairs = (await client.usage.coaccess())["pairs"]
    assert pairs == [{"datasets": ["prod.mart.positions", "prod.mart.trades"], "queries": 1}]


async def test_a_csv_export_is_read_by_its_suffix(
    client: AsyncClient, estate: None, tmp_path: Path
) -> None:
    export = tmp_path / "history.csv"
    export.write_text(
        "event_time,created_by,source_table_full_name\n"
        f"{TODAY}T01:00:00,a,main.mart.trades\n"
        f"{TODAY}T02:00:00,b,main.mart.trades\n"
    )
    assert (await client.usage.import_history("databricks", export))["dataset_days"] == 1
    assert (await client.usage.daily(dataset="main.mart.trades"))["days"][0]["queries"] == 2


async def test_refusals(
    client: AsyncClient, estate: None, started_database: Database, tenant_id: str
) -> None:
    with pytest.raises(prama.NotFoundError):
        await client.usage.import_history("oracle", HISTORY)
    with pytest.raises(prama.ValidationError, match="not valid JSON"):
        await client.usage.import_history("snowflake", ("history.json", b"{nope"))
    with pytest.raises(prama.ValidationError):
        await client.usage.daily(days=0)
    # An auditor reads reports but records nothing.
    auditor = await _signed_in_as(client, started_database, tenant_id, "aud", "auditor")
    with pytest.raises(prama.ForbiddenError):
        await auditor.usage.import_history("snowflake", HISTORY)
    assert not (await auditor.usage.priorities())["has_usage"]
    await auditor.close()
