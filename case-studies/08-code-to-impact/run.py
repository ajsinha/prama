#!/usr/bin/env python3
"""Case study 8 — from code to impact: lineage read from the ETL, not drawn by hand.

A risk team's ETL repository (two SQL scripts and a Power BI model) is handed
to Prama's code intake, as a ZIP. Nothing in it is executed: it is parsed, and
the parse becomes column lineage. Two controls are written on the raw feed; the
lineage carries them downstream as proposals, a reviewer accepts them, and
they all run: carried controls, keys checked against their sources, a filtered
reconciliation, and a check at the FX join. Two defects planted in the raw
feed are then traced, through the lineage, to the dashboard measure a risk
committee reads.

It all happens in **your** Prama, through the SDK: the code is received, the
proposals accepted, the controls run and the blast radius read from the server
the configuration names. It starts no server of its own.

Usage:
    python run.py                          the server config/application.yaml names
    python run.py --config other.yaml      another server
    python run.py --username ada --password …   as somebody else (default: the dev admin)

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary; see LICENSE.
"""

from __future__ import annotations

import io
import json
import shutil
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from _common.defects import DefectLog  # noqa: E402
from _common.harness import Harness, Source, arguments, banner, say, stage  # noqa: E402

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


def _archive(code: Path) -> bytes:
    """The repository as the ZIP a CI job would upload: every file, relative paths."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(code.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(code).as_posix())
    return buffer.getvalue()


def _intake(harness: Harness, code: Path) -> None:
    sdk = harness.sdk
    stage(2, "Read the ETL repository", "Parsed, never executed. The parse becomes lineage.")
    run = sdk.code.add_zip("risk-etl", _archive(code))
    units = sdk.code.units(run["run"])
    edges = sdk.lineage.edges()["edges"]
    say(f"  run {run['status']}: {len(units)} file(s) read, {len(edges)} column edge(s)")
    if run.get("error"):
        say(f"  ! {run['error']}")
    for unit in sorted(units, key=lambda u: u["path"]):
        say(f"    {unit['path']:<28} {unit['kind']:<8} read by {unit['scanner']}")
        for gap in unit.get("gaps") or []:
            say(f"      ! not read: {gap}")
    for edge in sorted(edges, key=lambda e: (e["to"], e["from"])):
        say(f"    {edge['from']:<30} → {edge['to']:<48} {edge['transform']:<10} {edge['status']}")


def _controls(harness: Harness) -> None:
    sdk = harness.sdk
    stage(
        3,
        "Write two controls on the raw feed; lineage proposes the rest",
        "A control on a column is owed by every faithful copy of it.",
    )
    for identity, pql in AUTHORED.items():
        harness.author(pql, identity=identity, reason="written by the feed's owner")
        say(f"  written   {pql.split(' SEVERITY')[0]}")
    for proposal in sdk.lineage.proposals()["controls"]:
        if proposal["deferred_because"]:
            say(
                f"  held      {proposal['pql'].split(' BECAUSE')[0]}\n"
                f"            ({proposal['deferred_because']})"
            )
            continue
        # A reviewer accepts it on the proposal queue: declared, then activated.
        sdk.proposals.accept(
            proposal["identity"],
            proposal["pql"],
            rule=proposal["rule"],
            reason="accepted for the study",
        )
        harness.accepted += 1
        say(f"  proposed  {proposal['pql'].split(' BECAUSE')[0]}   ({proposal['rule']})")
    # Read the queue back rather than assume it emptied.
    active = {c["identity"] for c in sdk.controls.list(status="active")}
    waiting = sdk.lineage.proposals()["controls"]
    stale = [p for p in waiting if p["identity"] in active]
    fresh = [p for p in waiting if p["identity"] not in active]
    queue = sdk.proposals.list()["proposals"]
    queued = [p for p in queue if p["identity"] in active]
    say()
    say(
        f"  {harness.accepted} control(s) active. Asked again, lineage lists {len(waiting)}: "
        f"{len(stale)} already active, {len(fresh)} new."
    )
    say(
        f"  The proposal queue lists {len(queue)}, of which {len(queued)} are already "
        "active controls."
    )
    for proposal in fresh:
        # Implied by the controls just accepted. Left for a reviewer, not run here.
        say(f"  next      {proposal['pql'].split(' BECAUSE')[0]}   ({proposal['rule']})")


def _dataset(column: str) -> str:
    """The dataset of a qualified column: everything before the last dot."""
    return column.rsplit(".", 1)[0]


def _impact(harness: Harness) -> None:
    stage(6, "Where do the defects go?", "The blast radius of each failing raw column.")
    for column in ("notional_amt", "currency"):
        answer = harness.sdk.lineage.impact(f"raw.trades.{column}")
        reached = answer["reached"]
        datasets = list(dict.fromkeys(_dataset(r["column"]) for r in reached))
        say(f"  raw.trades.{column}: reaches {len(reached)} column(s) in {', '.join(datasets)}")
        for item in sorted(reached, key=lambda r: (-r["impact"], r["column"]))[:8]:
            hops = f"{item['depth']} hop{'s' if item['depth'] != 1 else ''}"
            say(f"    → {item['column']} at {item['impact']:.0%} of the defect, {hops} away")


def _vanished(warehouse: Path) -> None:
    """What the currency defect costs, measured on the bank's own warehouse.

    This is the customer's side, queried directly: Prama is not asked. It is
    the number the check at the FX join exists to catch.
    """
    import duckdb

    connection = duckdb.connect(str(warehouse), read_only=True)
    try:
        count, amount = connection.execute(
            "SELECT COUNT(*), SUM(s.notional) FROM stg.trades s "
            "LEFT JOIN ref.fx_rates r ON s.ccy = r.ccy WHERE r.ccy IS NULL"
        ).fetchone()
    finally:
        connection.close()
    say()
    say(
        f"  {int(count)} staged trade(s), {amount or 0:,.0f} in notional, have no FX "
        "rate and are missing from mart.positions."
    )
    say("  No row error and no null at the mart. The join key's lineage proposed the check")
    say("  that catches it where it happens: every staged currency must have a rate.")


def main() -> None:
    args = arguments(__doc__ or "")
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
    harness = Harness(workspace, title="From code to impact", args=args)
    harness.start(tenant_slug="acme-risk", tenant_name="Acme Markets — risk")
    try:
        _intake(harness, code)
        _controls(harness)
        harness.run(
            [
                Source(
                    name="warehouse (DuckDB)",
                    source_type="duckdb",
                    path=warehouse,
                    datasets={"raw.trades", "stg.trades", "mart.positions", "ref.fx_rates"},
                ),
            ]
        )
        harness.report(planted)
        _impact(harness)
        _vanished(warehouse)
        harness.finish()
    finally:
        harness.close()


if __name__ == "__main__":
    main()
