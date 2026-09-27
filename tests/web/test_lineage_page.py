"""The Lineage workbench renders the store, the impact, and a person's decision.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama.db import Database
from prama.lineage.store import scan_sql

ETL = """
INSERT INTO rpt.line_23 (amount) SELECT SUM(a.amt) FROM stg.a a;
INSERT INTO stg.a (amt) SELECT t.notional FROM raw.trades t;
"""


async def _scan(database: Database, tenant: str) -> None:
    async with database.unit_of_work() as uow:
        await scan_sql(uow, tenant, source="warehouse", sql=ETL)


async def test_the_page_shows_edges_from_the_store(
    ui: Any, started_database: Database, tenant_id: str
) -> None:
    empty = await ui.get("/lineage")
    assert "No lineage yet" in empty.text  # the control: nothing before a scan
    await _scan(started_database, tenant_id)
    page = await ui.get("/lineage")
    assert "raw.trades.notional" in page.text and "rpt.line_23.amount" in page.text


async def test_impact_is_drawn_for_a_column(
    ui: Any, started_database: Database, tenant_id: str
) -> None:
    await _scan(started_database, tenant_id)
    page = await ui.get("/lineage", params={"column": "raw.trades.notional"})
    assert "<svg" in page.text and "rpt.line_23.amount" in page.text


async def test_a_rejected_edge_leaves_the_working_graph(
    ui: Any, started_database: Database, tenant_id: str
) -> None:
    await _scan(started_database, tenant_id)
    async with started_database.unit_of_work() as uow:
        edge = (await uow.lineage.edges(tenant_id, dataset="raw.trades"))[0]
    response = await ui.post(f"/lineage/edges/{edge.id}/decide", data={"decision": "rejected"})
    assert response.status_code == 303
    async with started_database.unit_of_work() as uow:
        assert not await uow.lineage.edges(tenant_id, dataset="raw.trades")
