"""Datasets the warehouse reads together: a hint for a steward, never a proposal.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from prama.db import Database
from prama.lineage import usage
from prama.semantic.services.datasets import DatasetService
from prama.semantic.services.metadata import correlation
from prama.semantic.values import Grain

TODAY = datetime.now(UTC).date().isoformat()


def _history(times: int) -> list[dict[str, str]]:
    both = json.dumps([{"objectName": "PROD.MART.TRADES"}, {"objectName": "PROD.MART.ACCOUNTS"}])
    return [
        {"QUERY_START_TIME": f"{TODAY} 09:{i:02d}:00", "USER_NAME": "ANA",
         "DIRECT_OBJECTS_ACCESSED": both}
        for i in range(times)
    ]  # fmt: skip


def test_a_query_reading_two_tables_is_one_pair() -> None:
    together = usage.pairs("snowflake", _history(2))
    assert together == {("prod.mart.accounts", "prod.mart.trades", TODAY): 2}
    # Databricks records one table per event, so it has no pairs to give.
    one = [{"event_time": f"{TODAY}T01:00:00", "source_table_full_name": "a.b"}]
    assert usage.pairs("databricks", one) == {}


async def _estate(database: Database, tenant_id: str, queries: int) -> dict:
    async with database.unit_of_work() as uow:
        service = DatasetService(uow)
        _, trades = await service.declare(tenant_id=tenant_id, name="Trades", criticality=4)
        _, accounts = await service.declare(
            tenant_id=tenant_id,
            name="Accounts",
            criticality=4,
            grain=Grain(attributes=("account_id",), statement="one row per account"),
        )
        for version, names in ((trades, ("trade_id", "account_id")), (accounts, ("account_id",))):
            for name in names:
                await service.declare_attribute(
                    tenant_id=tenant_id, dataset_id=str(version.dataset_id), name=name
                )
        await usage.ingest(uow, tenant_id, "snowflake", _history(queries))
        return await correlation(uow, tenant_id)


async def test_datasets_read_together_suggest_the_relationship(
    started_database: Database, tenant_id: str
) -> None:
    result = await _estate(started_database, tenant_id, queries=4)
    (hint,) = result["queried_together"]
    assert hint["datasets"] == ["accounts", "trades"] and hint["queries"] == 4
    assert hint["shared"] == ["account_id"]
    assert hint["suggested"] == ["CHECK trades.account_id REFERENCES accounts.account_id"]
    # A hint, not a proposal: nothing enters the review queue on a shared name.
    assert not [p for p in result["proposals"] if "REFERENCES accounts" in p["pql"]]


async def test_below_the_threshold_nothing_is_said(
    started_database: Database, tenant_id: str
) -> None:
    result = await _estate(started_database, tenant_id, queries=2)
    assert result["queried_together"] == []
