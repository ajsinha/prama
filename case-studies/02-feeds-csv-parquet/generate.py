#!/usr/bin/env python3
"""Build a landing zone of daily feeds — CSV and Parquet — with defects planted.

A feed is not a file; it is a contract about arrival. These land in a directory
named the way a real landing zone is, with the business date in the filename,
and the defects are the ones feeds actually suffer: a truncated file, a
duplicate delivery, a day that never arrived, a trailer that disagrees with what
is in the file.

CSV for the front-office extracts and Parquet for the risk and reference feeds,
because that is how these estates are actually shaped: text where a mainframe or
a vendor writes it, columnar where an analytics platform does.

Usage:
    python generate.py [workspace]

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import csv
import dataclasses
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
from _common.bank import Book
from _common.defects import DefectLog


def _write_csv(path: Path, rows: list[dict], *, declared_rows: int | None = None) -> None:
    """Write the data file, and its trailer beside it.

    A sidecar rather than a last line inside the CSV. Both patterns exist in
    the wild; the sidecar is the one that leaves the data file readable by
    anything that reads CSV, and an in-band trailer of a different width is
    what makes half the loaders in a bank need a custom parser.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    if declared_rows is not None:
        path.with_suffix(".trl").write_text(f"TRLR,{declared_rows}\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    """JSON Lines: one record per line, which is what JSON feeds are."""
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def _write_parquet(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = list(rows[0])
    pq.write_table(pa.table({c: [row[c] for row in rows] for c in columns}), path)


def build(workspace: Path) -> tuple[Path, Path, DefectLog, dict[str, int]]:
    landing = workspace / "landing"
    if landing.exists():
        shutil.rmtree(landing)
    landing.mkdir(parents=True)

    book = Book(days=10)
    book.generate(trades_per_day=400)
    log = DefectLog()

    trades = [dataclasses.asdict(t) for t in book.trades]
    positions = [dataclasses.asdict(p) for p in book.positions]
    instruments = book.instrument_rows()
    counterparties = book.counterparty_rows()

    by_day: dict[str, list[dict]] = {}
    for trade in trades:
        by_day.setdefault(trade["trade_date"], []).append(trade)
    days = sorted(by_day)

    # ---------------------------------------------------------------- 1
    # A truncated file. The transfer died halfway; every row that *did*
    # arrive is perfectly valid, so no content check would ever notice —
    # only the trailer count does.
    truncated_day = days[3]
    full = len(by_day[truncated_day])
    by_day[truncated_day] = by_day[truncated_day][: full // 2]
    log.add(
        key="truncated_delivery",
        dataset="trade_feed",
        what=(
            f"the {truncated_day} file was truncated mid-transfer — its trailer "
            f"declares {full} rows and {full - full // 2} are missing"
        ),
        rows=full - full // 2,
        dimension="completeness",
        detectable=False,
        caveat=(
            "The trailer check is a feed control (prama.connect.feed), which runs at "
            "arrival rather than as SQL over the landed rows. It is not wired into "
            "the control runner yet, so this study plants the defect, states it, and "
            "does not claim it."
        ),
    )

    # ---------------------------------------------------------------- 2
    # A day that never arrived at all. The commonest feed incident there
    # is, and the one a content check structurally cannot see: there is
    # nothing wrong with the rows, because there are no rows.
    missing_day = days[6]
    absent = by_day.pop(missing_day)
    log.add(
        key="missing_delivery",
        dataset="trade_feed",
        what=f"the {missing_day} file never arrived",
        rows=len(absent),
        dimension="timeliness",
    )

    # ---------------------------------------------------------------- 3
    # A resend that nobody de-duplicated. Both files land, both are read,
    # and the day is counted twice.
    duplicated_day = days[8]
    log.add(
        key="duplicate_delivery",
        dataset="trade_feed",
        what=f"the {duplicated_day} file was resent and both copies were loaded",
        rows=len(by_day[duplicated_day]),
        dimension="uniqueness",
    )

    # ---------------------------------------------------------------- 4
    # A null in a CDE, in the columnar feed this time.
    for position in positions[:18]:
        position["market_value"] = None
    log.add(
        key="null_market_value",
        dataset="position_feed",
        what="market value missing — a CDE, and every risk number below it is short",
        rows=18,
        dimension="completeness",
    )

    # ---------------------------------------------------------------- 5
    # A currency that is not a currency, in Parquet.
    for position in positions[20:29]:
        position["currency"] = "US$"
    log.add(
        key="bad_currency_code",
        dataset="position_feed",
        what="currency 'US$' — not an ISO 4217 code",
        rows=9,
        dimension="validity",
    )

    # ---------------------------------------------------------------- 6
    # An LEI whose checksum is wrong. Shape-valid, standard-invalid.
    for row in counterparties[:2]:
        row["lei"] = str(row["lei"])[:-2] + "00"
    log.add(
        key="bad_lei_checksum",
        dataset="counterparty_feed",
        what="LEI checksum wrong — passes the shape, fails ISO 17442",
        rows=2,
        dimension="validity",
        detectable=False,
        caveat=(
            "SQL expresses the shape and not the mod-97 checksum, so the control is a "
            "screen and Prama reports 'not established' rather than a pass."
        ),
    )

    # ---------------------------------------------------------------- 7
    # A price outside anything a human would book.
    for trade in by_day[days[0]][:5]:
        trade["price"] = 9_999_999.99
    log.add(
        key="absurd_price",
        dataset="trade_feed",
        what="price above the declared maximum — a fat finger, or a units error",
        rows=5,
        dimension="validity",
    )

    # -- write the landing zone -------------------------------------------

    counts: dict[str, int] = {}
    trade_rows = 0
    for day in sorted(by_day):
        rows = by_day[day]
        stamp = day.replace("-", "")
        _write_csv(
            landing / "trades" / f"TRADES_{stamp}_001.csv",
            rows,
            declared_rows=len(rows) if day != truncated_day else full,
        )
        trade_rows += len(rows)
        if day == duplicated_day:
            # The resend, landed alongside the original under a second
            # sequence number — exactly as a real retry does.
            _write_csv(
                landing / "trades" / f"TRADES_{stamp}_002.csv",
                rows,
                declared_rows=len(rows),
            )
            trade_rows += len(rows)
    counts["trades (CSV)"] = trade_rows

    _write_parquet(landing / "positions" / "POSITIONS_20260908.parquet", positions)
    counts["positions (Parquet)"] = len(positions)
    _write_parquet(landing / "instruments" / "INSTRUMENTS_20260908.parquet", instruments)
    counts["instruments (Parquet)"] = len(instruments)
    _write_csv(landing / "counterparties" / "COUNTERPARTIES_20260908.csv", counterparties)
    counts["counterparties (CSV)"] = len(counterparties)

    # -- settlements, as JSON Lines ------------------------------------------
    statuses = ("PENDING", "SETTLED", "FAILED")
    settlements = [
        {
            "settlement_id": f"SET{i:06d}",
            "amount": round(1_000 + (i * 7919) % 250_000 + 0.25, 2),
            "currency": ("USD", "EUR", "GBP")[i % 3],
            "status": statuses[i % 3],
            "value_date": f"2026-09-{8 + i % 3:02d}",
        }
        for i in range(600)
    ]
    for row in settlements[40:49]:
        row["amount"] = -row["amount"]
    log.add(
        key="negative_settlement_amount",
        dataset="settlement_feed",
        what="settlement amount negative: a direction written into the sign",
        rows=9,
        dimension="validity",
    )
    for row in settlements[300:305]:
        row["status"] = "UNKNOWN"
    log.add(
        key="unknown_settlement_status",
        dataset="settlement_feed",
        what="status UNKNOWN, which the settlement system never sends",
        rows=5,
        dimension="validity",
    )
    _write_jsonl(landing / "settlements" / "SETTLEMENTS_20260908.jsonl", settlements)
    counts["settlements (JSON Lines)"] = len(settlements)

    # -- one DuckDB file with a view over each feed -----------------------
    #
    # DuckDB reads CSV, Parquet and JSON Lines in place, so nothing is copied and the
    # files on disk stay the source of truth. The views are the only thing
    # created, and the database is then opened read-only for the run.
    catalogue = workspace / "landing.duckdb"
    if catalogue.exists():
        catalogue.unlink()
    connection = duckdb.connect(str(catalogue))
    connection.execute(
        f"CREATE VIEW trade_feed AS "
        f"SELECT * FROM read_csv_auto('{landing}/trades/*.csv', header=true)"
    )
    connection.execute(
        f"CREATE VIEW position_feed AS SELECT * FROM read_parquet('{landing}/positions/*.parquet')"
    )
    connection.execute(
        f"CREATE VIEW instrument_feed AS "
        f"SELECT * FROM read_parquet('{landing}/instruments/*.parquet')"
    )
    connection.execute(
        f"CREATE VIEW counterparty_feed AS "
        f"SELECT * FROM read_csv_auto('{landing}/counterparties/*.csv', header=true)"
    )
    connection.execute(
        f"CREATE VIEW settlement_feed AS SELECT * FROM "
        f"read_json('{landing}/settlements/*.jsonl', format='newline_delimited')"
    )
    connection.close()
    return landing, catalogue, log, counts


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "workspace"
    landing, catalogue, log, counts = build(target)
    print(f"landing zone: {landing}")
    for name, count in counts.items():
        print(f"  {name:<26} {count:>8,} rows")
    print(f"views over them: {catalogue}")
    print()
    print(log.render())
