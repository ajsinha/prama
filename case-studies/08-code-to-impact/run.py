#!/usr/bin/env python3
"""Case study 8 — from code to impact: lineage read from the ETL, not drawn by hand.

A risk team's ETL repository (two SQL scripts and a Power BI model) is handed
to Prama's code intake. Nothing in it is executed: it is parsed, and the
parse becomes column lineage. Two controls are written on the raw feed; the
lineage carries them downstream as proposals, a reviewer accepts them, and
they all run. Two defects planted in the raw feed are then traced, through
the lineage, to the dashboard measure a risk committee reads.

Usage:
    python run.py                 build, run, and serve the console on :8808
    python run.py --no-serve      build and run, then stop

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary; see LICENSE.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from _common.defects import DefectLog  # noqa: E402
from _common.harness import Harness, Source, banner, say, stage, use_config  # noqa: E402

from prama.connect.sources.query import executor_for  # noqa: E402

NOTICE = "Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved."

#: The repository, as the risk team keeps it. The SQL is run to build the
#: warehouse; the same files are what code intake reads.
STAGE_SQL = f"""-- {NOTICE}
-- Stage booked trades from the raw feed.
INSERT INTO stg.trades (trade_id, account_id, notional, ccy, trade_date)
SELECT t.id, t.acct, t.notional_amt, t.currency, t.trade_dt
FROM raw.trades t
WHERE t.status = 'BOOKED';
"""
MART_SQL = f"""-- {NOTICE}
-- Positions in USD, by account.
CREATE VIEW mart.positions AS
WITH fx AS (SELECT r.ccy, r.rate FROM ref.fx_rates r)
SELECT s.account_id AS account_id,
       SUM(s.notional * fx.rate) AS exposure_usd
FROM stg.trades s
JOIN fx ON s.ccy = fx.ccy
GROUP BY s.account_id;
"""
DASHBOARD = {
    "_comment": NOTICE,
    "name": "Risk Dashboard",
    "compatibilityLevel": 1550,
    "model": {
        "tables": [
            {
                "name": "Positions",
                "columns": [
                    {"name": "account_id", "sourceColumn": "account_id", "dataType": "string"},
                    {"name": "Exposure", "sourceColumn": "Exposure", "dataType": "double"},
                ],
                "partitions": [
                    {
                        "name": "p",
                        "source": {
                            "type": "m",
                            "expression": [
                                "let",
                                '    Source = Sql.Database("warehouse", "bank"),',
                                "    mart_positions = "
                                'Source{[Schema="mart",Item="positions"]}[Data],',
                                "    Renamed = Table.RenameColumns(mart_positions, "
                                '{{"exposure_usd", "Exposure"}})',
                                "in",
                                "    Renamed",
                            ],
                        },
                    }
                ],
                "measures": [{"name": "Total Exposure", "expression": "SUM(Positions[Exposure])"}],
            }
        ]
    },
}

#: What the feed's owner writes. Everything downstream is proposed from lineage.
AUTHORED = {
    "raw:notional-non-negative": 'CHECK "raw.trades".notional_amt >= 0 SEVERITY critical '
    "DIMENSION validity BECAUSE 'a notional is a size; the direction is in the side'",
    "raw:currency-iso": "CHECK \"raw.trades\".currency IN ('USD', 'EUR', 'GBP', 'JPY') "
    "SEVERITY critical DIMENSION validity BECAUSE 'only rated currencies can be converted'",
}
RATES = {"USD": 1.0, "EUR": 1.08, "GBP": 1.27, "JPY": 0.0067}


def write_code(code: Path) -> None:
    shutil.rmtree(code, ignore_errors=True)
    (code / "sql").mkdir(parents=True)
    (code / "bi").mkdir()
    (code / "sql" / "01_stage_trades.sql").write_text(STAGE_SQL)
    (code / "sql" / "02_mart_positions.sql").write_text(MART_SQL)
    (code / "bi" / "model.bim").write_text(json.dumps(DASHBOARD, indent=2))


def build(workspace: Path) -> tuple[Path, Path, DefectLog, dict[str, int]]:
    """The code repository, and a DuckDB warehouse built by running that code."""
    import duckdb

    workspace.mkdir(parents=True, exist_ok=True)
    code = workspace / "risk-etl"
    write_code(code)
    warehouse = workspace / "warehouse.duckdb"
    warehouse.unlink(missing_ok=True)
    currencies = ("USD", "EUR", "GBP", "JPY")
    trades = [
        (
            f"T{i:06d}",
            f"ACC{i % 60:03d}",
            float(1_000_000 * (1 + i % 9) if i % 4 != 3 else 150_000_000 * (1 + i % 5)),
            currencies[i % 4],
            f"2026-09-{1 + i % 25:02d}",
            "BOOKED" if i % 17 else "CANCELLED",
        )
        for i in range(2000)
    ]
    log = DefectLog()
    for i in range(40, 45):
        trades[i] = (*trades[i][:2], -trades[i][2], *trades[i][3:])
    log.add(
        key="negative_notional",
        dataset="raw.trades",
        what="notional written with the sign of the side",
        rows=5,
        dimension="validity",
    )
    for i in (100, 101, 102, 103):
        trades[i] = (*trades[i][:3], "usd", *trades[i][4:])
    log.add(
        key="lowercase_currency",
        dataset="raw.trades",
        what="currency 'usd' in lower case: the FX join drops these trades silently",
        rows=4,
        dimension="validity",
    )
    booked = sum(1 for t in trades if t[5] == "BOOKED")
    connection = duckdb.connect(str(warehouse))
    connection.execute(
        "CREATE SCHEMA raw; CREATE SCHEMA ref; CREATE SCHEMA stg; CREATE SCHEMA mart"
    )
    connection.execute(
        "CREATE TABLE raw.trades (id VARCHAR, acct VARCHAR, notional_amt DOUBLE, "
        "currency VARCHAR, trade_dt VARCHAR, status VARCHAR)"
    )
    connection.executemany("INSERT INTO raw.trades VALUES (?, ?, ?, ?, ?, ?)", trades)
    connection.execute("CREATE TABLE ref.fx_rates (ccy VARCHAR, rate DOUBLE)")
    connection.executemany("INSERT INTO ref.fx_rates VALUES (?, ?)", list(RATES.items()))
    connection.execute(
        "CREATE TABLE stg.trades (trade_id VARCHAR, account_id VARCHAR, notional DOUBLE, "
        "ccy VARCHAR, trade_date VARCHAR)"
    )
    connection.execute(STAGE_SQL)  # the pipeline, run as written
    connection.execute(MART_SQL)
    connection.close()
    return code, warehouse, log, {"raw.trades": len(trades), "stg.trades": booked}


async def _intake(harness: Harness, code: Path) -> None:
    from prama.codeintake.archive import Limits
    from prama.codeintake.git import snapshot_of
    from prama.codeintake.service import analyse

    stage(2, "Read the ETL repository", "Parsed, never executed. The parse becomes lineage.")
    # Intake deletes the tree it read, so it reads a copy.
    received = code.parent / "received"
    shutil.rmtree(received, ignore_errors=True)
    shutil.copytree(code, received)
    snapshot = snapshot_of(received, Limits())
    async with harness.database.unit_of_work() as uow:
        source = await uow.code.ensure_source(harness.tenant_id, "risk-etl", kind="zip")
        run = await analyse(uow, harness.tenant_id, source, snapshot)
        units = await uow.code.units(harness.tenant_id, run.id)
        edges = await uow.lineage.edges(harness.tenant_id)
    say(f"  run {run.status}: {len(units)} file(s) read, {len(edges)} column edge(s)")
    for unit in sorted(units, key=lambda u: u.path):
        say(f"    {unit.path:<28} {unit.kind:<8} read by {unit.scanner}")
    for edge in sorted(edges, key=lambda e: (e.target_dataset, e.target_column)):
        say(
            f"    {edge.source_dataset}.{edge.source_column:<14} → "
            f"{edge.target_dataset}.{edge.target_column:<16} {edge.transform:<10} {edge.status}"
        )


async def _controls(harness: Harness) -> None:
    from prama.derive.lineage_controls import propose

    stage(
        3,
        "Write two controls on the raw feed; lineage proposes the rest",
        "A control on a column is owed by every faithful copy of it.",
    )
    tenant = harness.tenant_id
    async with harness.database.unit_of_work() as uow:
        for identity, pql in AUTHORED.items():
            entity, _ = await uow.controls.declare(
                tenant_id=tenant,
                identity=identity,
                pql=pql,
                rule="authored",
                criticality=1,
                authored_by="alice",
            )
            await uow.controls.activate(str(entity.id), tenant_id=tenant, approved_by="bob")
            harness.accepted += 1
            say(f"  written   {pql.split(' SEVERITY')[0]}")
    async with harness.database.unit_of_work() as uow:
        proposals = propose(await uow.lineage.edges(tenant), await uow.controls.live(tenant))
        for proposal in proposals:
            if proposal.deferred_because:
                say(
                    f"  held      {proposal.pql.split(' BECAUSE')[0]}\n"
                    f"            ({proposal.deferred_because})"
                )
                continue
            entity, _ = await uow.controls.declare(
                tenant_id=tenant,
                identity=proposal.identity,
                pql=proposal.pql,
                rule=proposal.rule,
                status="proposed",
                authored_by="gamma",
                criticality=2,
            )
            await uow.controls.activate(str(entity.id), tenant_id=tenant, approved_by="bob")
            harness.accepted += 1
            say(f"  proposed  {proposal.pql.split(' BECAUSE')[0]}   ({proposal.rule})")


async def _impact(harness: Harness) -> None:
    from prama.lineage.graph import Column

    stage(6, "Where do the defects go?", "The blast radius of each failing raw column.")
    async with harness.database.unit_of_work() as uow:
        graph = await uow.lineage.graph(harness.tenant_id)
    for column in ("notional_amt", "currency"):
        radius = graph.blast_radius(Column(dataset="raw.trades", name=column))
        say(
            f"  raw.trades.{column}: reaches {len(radius)} column(s) in "
            f"{', '.join(radius.datasets)}"
        )
        for reached in radius.worst(8):
            say(f"    → {reached.describe()}")


def _vanished(warehouse: Path) -> None:
    execute, close = executor_for(warehouse, "duckdb")
    try:
        lost = execute(
            "SELECT COUNT(*) AS n, SUM(s.notional) AS amount FROM stg.trades s "
            "LEFT JOIN ref.fx_rates r ON s.ccy = r.ccy WHERE r.ccy IS NULL"
        )[0]
    finally:
        close()
    say()
    say(
        f"  {int(lost['n'])} staged trade(s), {lost['amount'] or 0:,.0f} in notional, have no FX "
        "rate and are missing from mart.positions."
    )
    say("  No row errors and no count changes at the mart: only the raw column's control saw it.")


async def main(serve: bool) -> Any:
    workspace = HERE / "workspace"
    banner(
        "Case study 8 — from code to impact",
        "Lineage read from the ETL code, and a defect traced to the dashboard.",
    )
    stage(1, "Build the warehouse by running the ETL", "Raw feed, staging, mart; two defects.")
    code, warehouse, planted, counts = build(workspace)
    for name, count in counts.items():
        say(f"  {name:<12} {count:>6,} rows")
    say()
    say(planted.render())
    harness = Harness(workspace, title="From code to impact")
    await harness.start(tenant_slug="acme-risk", tenant_name="Acme Markets — risk")
    try:
        await _intake(harness, code)
        await _controls(harness)
        execute, close = executor_for(warehouse, "duckdb")
        try:
            await harness.run(
                [
                    Source(
                        name="warehouse (DuckDB)",
                        engine="duckdb",
                        execute=execute,
                        close=close,
                        datasets={"raw.trades", "stg.trades", "mart.positions"},
                    ),
                ]
            )
        finally:
            close()
        await harness.report(planted)
        await _impact(harness)
        _vanished(warehouse)
    finally:
        await harness.stop()
    return harness if serve else None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-serve", action="store_true")
    parser.add_argument(
        "--config", default="", help="a Prama configuration file; defaults to the application's"
    )
    parser.add_argument("--port", type=int, default=8808)
    args = parser.parse_args()
    use_config(args.config)
    started = asyncio.run(main(serve=not args.no_serve))
    if started is not None:
        started.serve(port=args.port)
