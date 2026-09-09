#!/usr/bin/env python3
"""Build the trading book, in SQLite, with defects planted on purpose.

Every defect is one somebody has shipped to production. Each is recorded in the
defect log as it is planted, and the run prints that log against what Prama
found — including the ones it did not.

Usage:
    python generate.py [workspace]

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _common.bank import Book  # noqa: E402
from _common.defects import DefectLog  # noqa: E402

SCHEMA = """
CREATE TABLE instrument_reference (
    isin           TEXT,
    name           TEXT,
    asset_class    TEXT,
    currency       TEXT,
    primary_venue  TEXT
);
CREATE TABLE counterparties (
    lei            TEXT,
    legal_name     TEXT,
    jurisdiction   TEXT,
    credit_rating  TEXT
);
CREATE TABLE trades (
    trade_id          TEXT,
    book              TEXT,
    isin              TEXT,
    counterparty_lei  TEXT,
    side              TEXT,
    quantity          REAL,
    price             REAL,
    notional          REAL,
    currency          TEXT,
    trade_date        TEXT,
    settlement_date   TEXT,
    venue             TEXT,
    trader            TEXT
);
CREATE TABLE positions_eod (
    book          TEXT,
    isin          TEXT,
    as_of_date    TEXT,
    quantity      REAL,
    market_value  REAL,
    currency      TEXT
);
CREATE TABLE general_ledger (
    book          TEXT,
    posting_date  TEXT,
    currency      TEXT,
    balance_usd   REAL
);
CREATE TABLE fx_rates (
    currency_pair TEXT,
    rate_date     TEXT,
    rate          REAL,
    source        TEXT
);
"""


def build(workspace: Path) -> tuple[Path, DefectLog, dict[str, int]]:
    workspace.mkdir(parents=True, exist_ok=True)
    path = workspace / "trading_book.db"
    if path.exists():
        path.unlink()

    book = Book(days=10)
    book.generate(trades_per_day=500)
    log = DefectLog()

    # ``slots=True`` dataclasses have no __dict__; asdict is the supported way
    # and it is also the one that copies rather than aliasing.
    trades = [dataclasses.asdict(t) for t in book.trades]
    positions = [dataclasses.asdict(p) for p in book.positions]
    ledger = [dataclasses.asdict(entry) for entry in book.ledger]
    instruments = book.instrument_rows()
    counterparties = book.counterparty_rows()
    fx = book.fx_rows()

    # ---------------------------------------------------------------- 1
    # A duplicated delivery. The commonest incident there is: a feed is
    # replayed after a failure and nobody de-duplicates, so every position
    # in one book is counted twice.
    duplicated = [dict(p) for p in positions if p["book"] == "EQ-CASH-01"]
    positions.extend(duplicated)
    log.add(
        key="duplicate_positions",
        dataset="positions_eod",
        what="one book's positions delivered twice — the declared grain forbids it",
        rows=len(duplicated),
        dimension="uniqueness",
    )

    # ---------------------------------------------------------------- 2
    # A null in a critical data element. Every downstream sum is quietly
    # wrong and nothing about the rows that survived looks unusual.
    for trade in trades[100:160]:
        trade["notional"] = None
    log.add(
        key="null_notional",
        dataset="trades",
        what="notional missing — a CDE for FRTB; every downstream sum is short",
        rows=60,
        dimension="completeness",
    )

    # ---------------------------------------------------------------- 3
    # Identifiers that pass their *shape* and fail their checksum. This is
    # the interesting one: SQL can express the shape and cannot express the
    # checksum, so the control compiles to a screen and Prama reports
    # "indeterminate" rather than a pass.
    for trade in trades[300:312]:
        # A real ISIN with its check digit rotated: twelve characters, right
        # country code, wrong number.
        trade["isin"] = "US0378331006"
    log.add(
        key="bad_isin_checksum",
        dataset="trades",
        what="ISIN checksum wrong — passes the shape, fails ISO 6166",
        rows=12,
        dimension="validity",
        detectable=False,
        caveat=(
            "SQL can express the shape and not the checksum, so the control is a "
            "screen. Prama reports 'not established' rather than a pass — which is "
            "the honest answer and not a detection."
        ),
    )

    # ---------------------------------------------------------------- 4
    # Orphans. A trade against an instrument the security master has never
    # heard of: the join silently drops it and the risk number is short.
    for trade in trades[500:523]:
        trade["isin"] = "LU9999999999"
    log.add(
        key="orphan_instrument",
        dataset="trades",
        what="instrument not in the security master — a join would silently drop these",
        rows=23,
        dimension="integrity",
        detectable=False,
        caveat=(
            "Referential integrity comes from a declared *relationship* between two "
            "datasets, not from either declaration alone. This study declares no "
            "relationships, so no control is generated and none should be. "
            "Case study 3 declares the relationship and finds these."
        ),
    )

    # ---------------------------------------------------------------- 5
    # A negative quantity where the declaration says the range is positive.
    for trade in trades[700:707]:
        trade["quantity"] = -abs(trade["quantity"])
    log.add(
        key="negative_quantity",
        dataset="trades",
        what="negative quantity — outside the declared range",
        rows=7,
        dimension="validity",
    )

    # ---------------------------------------------------------------- 6
    # A settlement date before the trade date. Physically impossible, and
    # invisible to any check that looks at one column at a time.
    for trade in trades[800:804]:
        trade["settlement_date"] = "2020-01-01"
    log.add(
        key="settles_before_trade",
        dataset="trades",
        what="settlement date before the trade date",
        rows=4,
        dimension="consistency",
        detectable=False,
        caveat=(
            "No control is generated for this: the declaration says nothing about "
            "how the two dates relate. It is a gap in the *declaration*, not in "
            "Prama — and the study leaves it in to show the difference."
        ),
    )

    # ---------------------------------------------------------------- 7
    # The ledger no longer ties to the positions. Somebody posted a manual
    # adjustment and nobody told the position keeper.
    ledger[0]["balance_usd"] = round(ledger[0]["balance_usd"] * 1.004, 2)
    log.add(
        key="ledger_break",
        dataset="general_ledger",
        what="book of record adjusted by 0.4% without a matching position move",
        rows=1,
        dimension="consistency",
        detectable=False,
        caveat=(
            "Needs a reconciliation between two datasets, which comes from a "
            "declared relationship rather than from either dataset alone. "
            "Case study 3 declares it."
        ),
    )

    # ---------------------------------------------------------------- 8
    # A stale FX rate. Everything converted through it is wrong by exactly
    # the amount the market moved, and nothing in the data looks odd.
    for row in fx:
        if row["currency_pair"] == "JPYUSD":
            row["rate_date"] = "2026-08-14"
    log.add(
        key="stale_fx",
        dataset="fx_rates",
        what="JPY rate three weeks old — everything converted through it is wrong",
        rows=1,
        dimension="timeliness",
        detectable=False,
        caveat=(
            "The declared rhythm generates a freshness control, and on a plain table "
            "it compiles to a row count — which cannot decide whether anything is "
            "late. It is reported as 'not established' rather than as a pass, which "
            "is the honest outcome and not a detection. A freshness control needs an "
            "arrival timestamp or a feed, which is what case study 2 has."
        ),
    )

    # ---------------------------------------------------------------- 9
    # A currency that is not a currency. Free-text where a codelist belongs.
    for trade in trades[900:915]:
        trade["currency"] = "EURO"
    log.add(
        key="bad_currency_code",
        dataset="trades",
        what="currency 'EURO' — not an ISO 4217 code, and not in the declared list",
        rows=15,
        dimension="validity",
    )

    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA)
    _insert(connection, "instrument_reference", instruments)
    _insert(connection, "counterparties", counterparties)
    _insert(connection, "trades", trades)
    _insert(connection, "positions_eod", positions)
    _insert(connection, "general_ledger", ledger)
    _insert(connection, "fx_rates", fx)
    connection.commit()

    counts = {
        table: connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        for table in (
            "instrument_reference",
            "counterparties",
            "trades",
            "positions_eod",
            "general_ledger",
            "fx_rates",
        )
    }
    connection.close()
    return path, log, counts


def _insert(connection: sqlite3.Connection, table: str, rows: list[dict]) -> None:
    if not rows:
        return
    columns = list(rows[0])
    placeholders = ", ".join("?" for _ in columns)
    connection.executemany(
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
        [tuple(row[c] for c in columns) for row in rows],
    )


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "workspace"
    path, log, counts = build(target)
    print(f"wrote {path}")
    for table, count in counts.items():
        print(f"  {table:<24} {count:>8,} rows")
    print()
    print(log.render())
