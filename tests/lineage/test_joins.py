"""Joins in lineage: which rows a dataset holds, and what a lost row reaches.

Case study 8 lost 605,000,000 of notional at an FX join: trades whose currency
had no rate left the mart, nothing failed, and the blast radius, following
values only, stopped at staging. These tests hold the three parts of the fix:
the reader records the join, the blast radius follows it, and a filtered copy
can be reconciled against its source.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import date

import duckdb

from prama.backend import compile_for
from prama.backend.execute import judge
from prama.ir.model import Verdict
from prama.ir.resolve import resolved
from prama.lineage.graph import Column, LineageGraph, Transform
from prama.lineage.sql import SqlLineage
from prama.pql import parse_control
from prama.recon.pql import measure

STAGE = """
INSERT INTO stg.trades (trade_id, account_id, notional, ccy)
SELECT t.id, t.acct, t.notional_amt, t.currency FROM raw.trades t WHERE t.status = 'BOOKED';
"""
MART = """
CREATE VIEW mart.positions AS
WITH fx AS (SELECT r.ccy, r.rate FROM ref.fx_rates r)
SELECT s.account_id AS account_id, SUM(s.notional * fx.rate) AS exposure_usd
FROM stg.trades s JOIN fx ON s.ccy = fx.ccy
GROUP BY s.account_id;
"""


def _edges(sql: str) -> list:
    return list(SqlLineage(dialect="duckdb").extract(sql, job="etl").edges)


def test_a_join_key_is_recorded_through_a_cte_to_the_real_table() -> None:
    joins = [e for e in _edges(MART) if e.transform is Transform.JOIN_KEY]
    assert {e.source.qualified for e in joins} == {"stg.trades.ccy", "ref.fx_rates.ccy"}
    assert {e.target.qualified for e in joins} == {"mart.positions.*"}
    assert {e.expression for e in joins} == {"inner join: stg.trades.ccy = ref.fx_rates.ccy"}


def test_a_cte_is_not_mistaken_for_a_table() -> None:
    """sqlglot 30 keeps WITH under "with_"; reading "with" found no CTEs, and the
    CTE's name `fx` was treated as a real dataset."""
    import sqlglot

    from prama.lineage.parsed import _Scope

    select = sqlglot.parse_one(MART, read="duckdb").expression
    assert _Scope(select).ctes == {"fx"}
    assert "fx" not in _Scope(select).aliases
    assert "fx" not in {e.source.dataset for e in _edges(MART)}


def test_a_filter_edge_carries_its_condition_on_its_own_table() -> None:
    (status,) = [e for e in _edges(STAGE) if e.transform is Transform.FILTER]
    assert status.expression == "WHERE status = 'BOOKED'"


def test_a_cross_or_unkeyed_join_records_no_join_key() -> None:
    sql = "CREATE VIEW v AS SELECT a.x AS x FROM a CROSS JOIN b"
    assert not [e for e in _edges(sql) if e.transform is Transform.JOIN_KEY]


def test_the_blast_radius_follows_a_join_to_the_dashboard() -> None:
    graph = LineageGraph()
    graph.add_all(_edges(STAGE) + _edges(MART))
    from prama.lineage.graph import Edge

    graph.add(
        Edge(
            source=Column("mart.positions", "exposure_usd"),
            target=Column("dashboard", "total_exposure"),
            transform=Transform.AGGREGATED,
            produced_by="bi/model.bim",
        )
    )
    radius = graph.blast_radius(Column("raw.trades", "currency"))
    reached = {r.column.qualified for r in radius.reached}
    # currency -> stg.trades.ccy -> the mart's rows -> every column built from them.
    assert {"stg.trades.ccy", "mart.positions.*", "mart.positions.exposure_usd"} <= reached
    assert "dashboard.total_exposure" in reached


def test_a_filtered_copy_reconciles_against_the_same_rows_of_its_source() -> None:
    """Executed, not just compiled: without the source-side WHERE, every cancelled
    trade is a missing row and the control fails; with it, the copy agrees."""
    db = duckdb.connect()
    db.execute("CREATE TABLE raw_trades (id VARCHAR, notional_amt DOUBLE, status VARCHAR)")
    db.execute(
        "INSERT INTO raw_trades VALUES ('T1', 10, 'BOOKED'), ('T2', 20, 'CANCELLED'), "
        "('T3', 30, 'BOOKED')"
    )
    db.execute(
        "CREATE TABLE stg_trades AS SELECT id AS trade_id, notional_amt AS notional "
        "FROM raw_trades WHERE status = 'BOOKED'"
    )

    def verdict(pql: str) -> Verdict:
        plan = resolved(parse_control(pql))
        compiled = compile_for(plan, "duckdb")

        def rows(sql: str) -> list[dict]:
            cursor = db.execute(sql)
            names = [d[0] for d in cursor.description]
            return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]

        metrics, _ = measure(
            plan,
            rows(compiled.metric_query),
            rows(compiled.counterpart_query),
            business_date=date(2026, 9, 28),
        )
        return judge(plan, metrics).verdict

    head = "RECONCILE stg_trades AGAINST raw_trades"
    tail = " ON (trade_id = id) COMPARING notional = notional_amt WITHIN 0"
    assert verdict(head + tail) is Verdict.FAIL  # T2 looks missing from the copy
    assert verdict(head + " WHERE status = 'BOOKED'" + tail) is Verdict.PASS
