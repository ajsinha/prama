"""The lineage store: scan, re-scan, decide, and ask what a defect reaches.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.db import Database
from prama.lineage.graph import Column
from prama.lineage.store import scan_sql

PROC = """
INSERT INTO rpt.finrep_line_23 (amount)
SELECT SUM(a.amt) FROM stg.a a WHERE a.status = 'BOOKED';
CREATE VIEW v AS SELECT x.k AS k FROM x UNION ALL SELECT y.k AS k FROM y;
"""


async def test_a_scan_persists_edges_that_survive_a_restart(
    started_database: Database, tenant_id: str
) -> None:
    async with started_database.unit_of_work() as uow:
        run = await scan_sql(uow, tenant_id, source="finrep", sql=PROC)
        assert run.statements == 2 and run.outcome == "partial"
    # A new unit of work: what is shown comes from the database.
    async with started_database.unit_of_work() as uow:
        rows = await uow.lineage.edges(tenant_id, dataset="rpt.finrep_line_23")
        assert any(
            (r.source_dataset, r.source_column, r.target_column) == ("stg.a", "amt", "amount")
            and r.status == "parsed"
            and r.method == "parsed:sqlglot"
            for r in rows
        )
        (latest,) = await uow.lineage.runs(tenant_id)
        gaps = await uow.lineage.gaps(tenant_id, latest.id)
        # The UNION went to the fallback, and the store says so.
        assert any(g.kind == "regex_fallback" for g in gaps)
        fallback = await uow.lineage.edges(tenant_id, dataset="v")
        assert fallback and all(r.status == "inferred" and r.confidence < 1 for r in fallback)


async def test_a_rescan_refreshes_and_closes_rather_than_duplicating(
    started_database: Database, tenant_id: str
) -> None:
    async with started_database.unit_of_work() as uow:
        await scan_sql(uow, tenant_id, source="finrep", sql=PROC)
        first = len(await uow.lineage.edges(tenant_id))
        await scan_sql(uow, tenant_id, source="finrep", sql=PROC)
        assert len(await uow.lineage.edges(tenant_id)) == first  # the control
        # The proc stops reading stg.a: its edges close, and are kept.
        await scan_sql(uow, tenant_id, source="finrep", sql="SELECT 1;")
        assert not await uow.lineage.edges(tenant_id, dataset="stg.a")


async def test_a_rejection_outlives_the_next_scan(
    started_database: Database, tenant_id: str
) -> None:
    async with started_database.unit_of_work() as uow:
        await scan_sql(uow, tenant_id, source="finrep", sql=PROC)
        edge = (await uow.lineage.edges(tenant_id, dataset="v"))[0]
        await uow.lineage.decide(tenant_id, edge.id, "rejected", by=None)
        await scan_sql(uow, tenant_id, source="finrep", sql=PROC)
        ids = {r.id for r in await uow.lineage.edges(tenant_id, dataset="v")}
        assert edge.id not in ids


async def test_impact_is_computed_from_the_persisted_graph(
    started_database: Database, tenant_id: str
) -> None:
    async with started_database.unit_of_work() as uow:
        await scan_sql(uow, tenant_id, source="finrep", sql=PROC)
        graph = await uow.lineage.graph(tenant_id)
    radius = graph.blast_radius(Column(dataset="stg.a", name="amt"))
    assert "rpt.finrep_line_23.amount" in {r.column.qualified for r in radius.reached}
