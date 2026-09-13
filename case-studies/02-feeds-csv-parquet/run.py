#!/usr/bin/env python3
"""Case study 2 — daily feeds, CSV and Parquet.

Usage:
    python run.py                 build, run, and serve the console on :8802
    python run.py --no-serve      build and run, then stop

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from _common.estate import Attribute, Dataset  # noqa: E402
from _common.harness import Harness, Source, banner, say, stage  # noqa: E402
from generate import build  # noqa: E402

from prama.connect.sources.query import executor_for  # noqa: E402

#: Feeds, not tables. The difference is in the declaration: a feed has a
#: *rhythm* — it arrives daily, by a time — and that is what turns "the file
#: never came" from an absence nobody notices into a control.
ESTATE = [
    Dataset(
        name="Trade Feed",
        description="The front office's daily trade extract, one CSV per business day.",
        grain_statement="one row per executed trade, and one file per business day",
        grain=("trade_id",),
        criticality=1,
        shape="feed",
        frequency="daily",
        arrival_by="06:30",
        obligations=("MiFID II",),
        attributes=(
            Attribute("trade_id", "The firm's identifier for the trade.", mandatory=True, is_cde=True),
            Attribute("book", "The trading book the risk sits in.", mandatory=True),
            Attribute("isin", "The instrument traded.", semantic_type="isin", mandatory=True, is_cde=True),
            Attribute("counterparty_lei", "Who we faced.", semantic_type="lei", mandatory=True, is_cde=True),
            Attribute("side", "Which way.", codelist=("BUY", "SELL"), mandatory=True),
            Attribute("quantity", "Units traded.", minimum=0.0, maximum=100_000_000.0, mandatory=True),
            Attribute(
                "price",
                "Execution price per unit. A price above the cap is a fat finger or a units error.",
                minimum=0.0,
                maximum=1_000_000.0,
                mandatory=True,
            ),
            Attribute(
                "notional",
                "Quantity times price.",
                unit="currency",
                currency_attribute="currency",
                mandatory=True,
                is_cde=True,
            ),
            Attribute(
                "currency",
                "The currency of the notional.",
                semantic_type="currency",
                codelist=("USD", "EUR", "GBP", "CHF", "JPY"),
                mandatory=True,
            ),
            Attribute("trade_date", "The date of execution.", semantic_type="iso_date", mandatory=True),
            Attribute("settlement_date", "When it settles.", semantic_type="iso_date"),
            Attribute("venue", "Where it executed.", semantic_type="mic"),
            Attribute("trader", "Who booked it."),
        ),
    ),
    Dataset(
        name="Position Feed",
        description="End-of-day positions from the risk platform, in Parquet.",
        grain_statement="one position per book per instrument per business day",
        grain=("book", "isin", "as_of_date"),
        criticality=1,
        shape="feed",
        frequency="daily",
        arrival_by="19:00",
        obligations=("FRTB",),
        attributes=(
            Attribute("book", "The trading book.", mandatory=True),
            Attribute("isin", "The instrument held.", semantic_type="isin", mandatory=True, is_cde=True),
            Attribute("as_of_date", "The business date.", semantic_type="iso_date", mandatory=True),
            Attribute("quantity", "Net units held; a short is a position."),
            Attribute(
                "market_value",
                "The position's value in its own currency.",
                unit="currency",
                currency_attribute="currency",
                mandatory=True,
                is_cde=True,
            ),
            Attribute(
                "currency",
                "The currency of the value.",
                semantic_type="currency",
                codelist=("USD", "EUR", "GBP", "CHF", "JPY"),
                mandatory=True,
            ),
        ),
    ),
    Dataset(
        name="Instrument Feed",
        description="The vendor's security master, in Parquet.",
        grain_statement="one row per instrument, identified by its ISIN",
        grain=("isin",),
        criticality=2,
        shape="feed",
        frequency="daily",
        arrival_by="05:00",
        attributes=(
            Attribute("isin", "The ISO 6166 identifier.", semantic_type="isin", mandatory=True, is_cde=True),
            Attribute("name", "The instrument's legal name.", mandatory=True),
            Attribute(
                "asset_class",
                "What kind of instrument it is.",
                codelist=("EQUITY", "GOVT_BOND", "CORP_BOND"),
                mandatory=True,
            ),
            Attribute(
                "currency",
                "Denomination currency.",
                semantic_type="currency",
                codelist=("USD", "EUR", "GBP", "CHF", "JPY"),
                mandatory=True,
            ),
            Attribute("primary_venue", "Where it principally trades.", semantic_type="mic"),
        ),
    ),
    Dataset(
        name="Counterparty Feed",
        description="The reference data team's counterparty extract, one CSV a day.",
        grain_statement="one row per legal entity, identified by its LEI",
        grain=("lei",),
        criticality=1,
        shape="feed",
        frequency="daily",
        arrival_by="05:00",
        obligations=("EMIR",),
        attributes=(
            Attribute(
                "lei",
                "The ISO 17442 Legal Entity Identifier.",
                semantic_type="lei",
                mandatory=True,
                is_cde=True,
                obligations=("EMIR",),
            ),
            Attribute("legal_name", "The entity's registered name.", mandatory=True),
            Attribute(
                "jurisdiction",
                "Where it is incorporated.",
                codelist=("DE", "US", "FR", "CH", "GB", "NL", "JP"),
            ),
            Attribute(
                "credit_rating",
                "Internal credit rating.",
                codelist=("AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB"),
            ),
        ),
    ),
]


async def main(serve: bool, port: int) -> Any:
    workspace = HERE / "workspace"
    banner(
        "Case study 2 — daily feeds, CSV and Parquet",
        "A landing zone. Ten business days, four feeds, seven planted defects.",
    )

    stage(1, "Build the landing zone", "CSV where a vendor writes it, Parquet where a platform does.")
    landing, catalogue, planted, counts = build(workspace)
    say(f"  {landing}")
    for name, count in counts.items():
        say(f"    {name:<26} {count:>8,} rows")
    say()
    say("  DuckDB reads both formats in place — nothing is copied, and the files")
    say("  on disk stay the source of truth. Only the views are created.")
    say()
    say(planted.render())

    harness = Harness(workspace, title="Feeds (CSV + Parquet)")
    await harness.start(tenant_slug="acme-feeds", tenant_name="Acme Markets — landing zone")
    try:
        await harness.declare(ESTATE)
        await harness.derive_and_accept()

        execute, close = executor_for(catalogue, "duckdb")
        try:
            await harness.run(
                [
                    Source(
                        name="landing zone (CSV + Parquet, via DuckDB)",
                        engine="duckdb",
                        execute=execute,
                        close=close,
                        datasets=set(harness.dataset_ids),
                    )
                ]
            )
        finally:
            close()

        await harness.report(planted)
        await _arrival_report(harness, landing)
    finally:
        await harness.stop()

    # Returned rather than served here. `harness.serve` calls `uvicorn.run`,
    # which calls `asyncio.run`, and this function is already inside one — so
    # the console never started and the study died on
    # "asyncio.run() cannot be called from a running event loop". Found by a QA
    # pass; nothing under tests/ exercises case-studies/.
    return harness if serve else None


async def _arrival_report(harness: Harness, landing: Path) -> None:
    """What arrived, and what did not.

    Content controls cannot see a missing file: there is nothing wrong with the
    rows, because there are no rows. Arrival is a property of the *feed*, and
    Prama's feed machinery reads it from the filenames — which is why a feed
    declaration names its filename pattern.
    """
    from datetime import date

    from prama.connect.feed import FeedDefinition, FilenamePattern
    from prama.core.calendars import WEEKDAYS

    stage(
        6,
        "What arrived, and what did not",
        "A missing file is invisible to every content check: there are no rows to be wrong.",
    )
    # The calendar is the whole point. Without it every Saturday is a missing
    # delivery, and a report that cries wolf twice a week is a report nobody
    # reads by the third week. Weekdays here rather than TARGET2 because these
    # studies ship no holiday file, and pretending otherwise would make this
    # lie on Good Friday.
    feed = FeedDefinition(
        name="trade_feed",
        landing_path=str(landing / "trades"),
        filename_pattern=FilenamePattern("TRADES_{YYYYMMDD}_{SEQ:3}.csv"),
        calendar=WEEKDAYS,
        files_per_day=1,
    )
    landed: dict[str, list[str]] = {}
    for path in sorted((landing / "trades").glob("*.csv")):
        parsed = feed.filename_pattern.parse(path.name)
        if parsed and parsed.business_date:
            landed.setdefault(parsed.business_date.isoformat(), []).append(path.name)

    if not landed:
        say("  nothing parsed")
        return
    days = sorted(landed)
    expected = feed.expected_dates(
        date.fromisoformat(days[0]), date.fromisoformat(days[-1])
    )
    for day in expected:
        key = day.isoformat()
        files = landed.get(key, [])
        if not files:
            say(f"    MISSING    {key}  nothing arrived")
        elif len(files) > 1:
            say(f"    DUPLICATE  {key}  {len(files)} files: {', '.join(files)}")
        else:
            say(f"    ok         {key}  {files[0]}")
    say()
    say("  Read from the filenames, which is why a feed declaration carries a")
    say("  filename pattern: the business date lives there and nowhere else.")
    say("  Weekends are not expected, because the feed declares a calendar — a")
    say("  report that cried wolf every Saturday would not be read by week three.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-serve", action="store_true")
    parser.add_argument("--port", type=int, default=8802)
    args = parser.parse_args()
    started = asyncio.run(main(serve=not args.no_serve, port=args.port))
    if started is not None:
        # Outside the loop, where uvicorn can own one of its own.
        started.serve(port=args.port)
