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


async def test_a_failing_upstream_control_lowers_downstream_trust(
    ui: Any, started_database: Database, tenant_id: str
) -> None:
    """E1's acceptance: trust drops through lineage, and removing the edge
    restores it (the counterfactual)."""
    from prama.evidence.record import EvidenceRecord, SnapshotRef

    await _scan(started_database, tenant_id)
    async with started_database.unit_of_work() as uow:
        await uow.evidence.append(
            EvidenceRecord(
                plan_id="ir:sha256:" + "b" * 64,
                control_id="ctl-raw",
                dataset="raw.trades",
                binding="raw.trades",
                engine="duckdb",
                snapshot=SnapshotRef(kind="wall_clock", identifier="t0"),
                verdict="fail",
                metrics={"scanned_rows": 100.0, "violating_rows": 40.0},
                started_at="2026-09-27T06:00:00Z",
                finished_at="2026-09-27T06:00:01Z",
                tenant_id=tenant_id,
            ),
            tenant_id=tenant_id,
        )
    params = {"column": "stg.a.amt"}
    lowered = await ui.get("/lineage", params=params)
    assert "Trust 0.60" in lowered.text
    async with started_database.unit_of_work() as uow:
        edge = (await uow.lineage.edges(tenant_id, dataset="raw.trades"))[0]
        await uow.lineage.decide(tenant_id, edge.id, "rejected", by=None)
    restored = await ui.get("/lineage", params=params)
    assert "Trust 1.00" in restored.text


async def test_an_incident_names_its_upstream_feeders(
    ui: Any, started_database: Database, tenant_id: str
) -> None:
    from prama.evidence.record import EvidenceRecord, SnapshotRef

    await _scan(started_database, tenant_id)
    async with started_database.unit_of_work() as uow:
        for control, dataset in (("ctl-raw", "raw.trades"), ("ctl-stg", "stg.a")):
            await uow.evidence.append(
                EvidenceRecord(
                    plan_id="ir:sha256:" + "c" * 64,
                    control_id=control,
                    dataset=dataset,
                    binding=dataset,
                    engine="duckdb",
                    snapshot=SnapshotRef(kind="wall_clock", identifier="t0"),
                    verdict="fail",
                    metrics={"scanned_rows": 10.0, "violating_rows": 5.0},
                    started_at="2026-09-27T06:00:00Z",
                    finished_at="2026-09-27T06:00:01Z",
                    tenant_id=tenant_id,
                ),
                tenant_id=tenant_id,
            )
    page = await ui.get("/incidents/ctl-stg")
    assert "Upstream, from the lineage store" in page.text
    assert "raw.trades" in page.text and "trust 0.50" in page.text
