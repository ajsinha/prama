#!/usr/bin/env python3
"""Build a mixed estate: a warehouse in SQLite and a landing zone of files.

The realistic shape. The book of record and the security master live in a
database somebody queries; the daily extracts land as files. Nothing joins them
except the business's own statement that they are about the same things — which
is exactly what a *relationship* declaration is.

The defects here are the ones that only exist *between* datasets: an orphan, a
break, a copy that has stopped being a copy. None of them is visible from
either side alone, which is why the first two studies plant some of them and
decline to claim them.

Usage:
    python generate.py [workspace]

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import csv
import dataclasses
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import duckdb  # noqa: E402
import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

from _common.bank import FX, Book  # noqa: E402
from _common.defects import DefectLog  # noqa: E402

WAREHOUSE_SCHEMA = """
CREATE TABLE instrument_master (
    isin           TEXT,
    name           TEXT,
    asset_class    TEXT,
    currency       TEXT,
    primary_venue  TEXT
);
CREATE TABLE counterparty_master (
    lei            TEXT,
    legal_name     TEXT,
    jurisdiction   TEXT,
    credit_rating  TEXT
);
CREATE TABLE general_ledger (
    book          TEXT,
    posting_date  TEXT,
    currency      TEXT,
    balance_usd   REAL
);
"""


def build(workspace: Path) -> tuple[Path, Path, Path, DefectLog, dict[str, int]]:
    landing = workspace / "landing"
    if landing.exists():
        shutil.rmtree(landing)
    landing.mkdir(parents=True)

    book = Book(days=10)
    book.generate(trades_per_day=400)
    log = DefectLog()

    trades = [dataclasses.asdict(t) for t in book.trades]
    positions = [dataclasses.asdict(p) for p in book.positions]
    ledger = [dataclasses.asdict(e) for e in book.ledger]
    instruments = book.instrument_rows()
    counterparties = book.counterparty_rows()

    # ---------------------------------------------------------------- 1
    # Orphans: trades against an instrument the master has never heard of.
    # Invisible from the trade side (the value looks like an ISIN) and from
    # the master side (nothing is missing there). Only the *relationship*
    # sees it, and a join would silently drop the rows.
    for trade in trades[400:437]:
        trade["isin"] = "LU9999999999"
    log.add(
        key="orphan_instrument",
        dataset="trade_feed",
        what="instrument not in the master — a join would silently drop these",
        rows=37,
        dimension="integrity",
    )

    # ---------------------------------------------------------------- 2
    # A counterparty that is not in the master either. Same shape, and it
    # matters more: an EMIR report with an unknown LEI is a rejected report.
    for trade in trades[900:914]:
        trade["counterparty_lei"] = "549300XXXXXXXXXXXX00"
    log.add(
        key="orphan_counterparty",
        dataset="trade_feed",
        what="counterparty LEI not in the master — an EMIR report would be rejected",
        rows=14,
        dimension="integrity",
    )

    # ---------------------------------------------------------------- 3
    # The break. The ledger no longer agrees with the positions, because
    # somebody posted a manual adjustment on one side only. Neither dataset
    # is wrong on its own; the relationship between them is.
    broken_book = ledger[0]["book"]
    original = ledger[0]["balance_usd"]
    ledger[0]["balance_usd"] = round(original * 1.006, 2)
    log.add(
        key="ledger_break",
        dataset="general_ledger",
        what=(
            f"{broken_book} adjusted by 0.6% with no matching position move — "
            "neither dataset is wrong alone"
        ),
        rows=1,
        dimension="consistency",
        detectable=False,
        caveat=(
            "The reconciliation *is* declared here, and Γ turns it into a comparison "
            "specification rather than a control — because a reconciliation is "
            "matching, tolerance and break classification, not one SQL predicate. "
            "The matching engine (prama.recon) executes it and is not wired into the "
            "control runner, so the study shows the declaration and does not claim "
            "the finding."
        ),
    )

    # ---------------------------------------------------------------- 4
    # A null in a CDE, so the study still has a single-dataset finding to
    # contrast the relationship ones against.
    for position in positions[:11]:
        position["market_value"] = None
    log.add(
        key="null_market_value",
        dataset="position_feed",
        what="market value missing — a CDE",
        rows=11,
        dimension="completeness",
    )

    # -- write the warehouse ----------------------------------------------

    warehouse = workspace / "warehouse.db"
    if warehouse.exists():
        warehouse.unlink()
    connection = sqlite3.connect(warehouse)
    connection.executescript(WAREHOUSE_SCHEMA)
    _insert(connection, "instrument_master", instruments)
    _insert(connection, "counterparty_master", counterparties)
    _insert(connection, "general_ledger", ledger)
    connection.commit()
    connection.close()

    # -- write the landing zone -------------------------------------------

    (landing / "trades").mkdir(parents=True)
    with (landing / "trades" / "TRADES_20260908_001.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(trades[0]))
        writer.writeheader()
        writer.writerows(trades)
    (landing / "positions").mkdir(parents=True)
    pq.write_table(
        pa.table({c: [p[c] for p in positions] for c in positions[0]}),
        landing / "positions" / "POSITIONS_20260908.parquet",
    )

    # -- the masters, published into the analytics zone -------------------
    #
    # A control that spans two datasets has to run somewhere, and no single
    # query reaches both a SQLite file and a Parquet directory. Banks solve
    # this the same way: the reference data is *published* into the analytics
    # zone daily, and the joins happen there.
    #
    # It is a copy, and this study says so rather than hiding it. A copy that
    # stops agreeing with its origin is itself a defect — the ``mirrors``
    # relationship exists for exactly that, and this estate does not declare
    # it, which is a gap worth noticing.
    (landing / "reference").mkdir(parents=True)
    pq.write_table(
        pa.table({c: [r[c] for r in instruments] for c in instruments[0]}),
        landing / "reference" / "INSTRUMENT_MASTER_20260908.parquet",
    )
    pq.write_table(
        pa.table({c: [r[c] for r in counterparties] for c in counterparties[0]}),
        landing / "reference" / "COUNTERPARTY_MASTER_20260908.parquet",
    )
    pq.write_table(
        pa.table({c: [r[c] for r in ledger] for c in ledger[0]}),
        landing / "reference" / "GENERAL_LEDGER_20260908.parquet",
    )

    # -- one DuckDB catalogue over the files ------------------------------
    #
    # The warehouse stays in SQLite and is queried there. Two sources, two
    # passes, one ledger — which is what a real estate looks like.
    catalogue = workspace / "landing.duckdb"
    if catalogue.exists():
        catalogue.unlink()
    duck = duckdb.connect(str(catalogue))
    duck.execute(
        f"CREATE VIEW trade_feed AS "
        f"SELECT * FROM read_csv_auto('{landing}/trades/*.csv', header=true)"
    )
    duck.execute(
        f"CREATE VIEW position_feed AS "
        f"SELECT * FROM read_parquet('{landing}/positions/*.parquet')"
    )
    for view, stem in (
        ("instrument_master", "INSTRUMENT_MASTER"),
        ("counterparty_master", "COUNTERPARTY_MASTER"),
        ("general_ledger", "GENERAL_LEDGER"),
    ):
        duck.execute(
            f"CREATE VIEW {view} AS "
            f"SELECT * FROM read_parquet('{landing}/reference/{stem}_*.parquet')"
        )
    duck.close()

    counts = {
        "warehouse: instrument_master": len(instruments),
        "warehouse: counterparty_master": len(counterparties),
        "warehouse: general_ledger": len(ledger),
        "landing: trade_feed (CSV)": len(trades),
        "landing: position_feed (Parquet)": len(positions),
    }
    return warehouse, landing, catalogue, log, counts


def _insert(connection: sqlite3.Connection, table: str, rows: list[dict]) -> None:
    columns = list(rows[0])
    connection.executemany(
        f"INSERT INTO {table} ({', '.join(columns)}) "
        f"VALUES ({', '.join('?' for _ in columns)})",
        [tuple(row[c] for c in columns) for row in rows],
    )


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "workspace"
    warehouse, landing, catalogue, log, counts = build(target)
    print(f"warehouse: {warehouse}")
    print(f"landing:   {landing}")
    for name, count in counts.items():
        print(f"  {name:<34} {count:>8,} rows")
    print()
    print(log.render())
