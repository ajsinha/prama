#!/usr/bin/env python3
"""Case study 1 — a trading book in SQLite.

Runs the whole thing: builds the data, declares the estate in business terms,
lets Γ derive the controls, accepts them, runs them against the database, and
prints what was found against what was planted. Then serves the console.

Usage:
    python run.py                 build, run, and serve the console on :8801
    python run.py --no-serve      build and run, then stop
    python run.py --port 9000     serve somewhere else

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from _common.estate import Attribute, Dataset  # noqa: E402
from _common.harness import Harness, banner, say, stage  # noqa: E402
from generate import build  # noqa: E402

from prama.connect.sources.query import executor_for  # noqa: E402

#: The estate, as its owner would describe it. Read this first: everything
#: Prama does afterwards follows from these sentences, and not one of them is
#: SQL.
ESTATE = [
    Dataset(
        name="Instrument Reference",
        description="The security master. Every tradable instrument the firm knows about.",
        grain_statement="one row per instrument, identified by its ISIN",
        grain=("isin",),
        criticality=2,
        arrival_by="05:00",
        attributes=(
            Attribute(
                "isin",
                "The ISO 6166 identifier for the instrument.",
                semantic_type="isin",
                mandatory=True,
                is_cde=True,
            ),
            Attribute("name", "The instrument's legal name.", mandatory=True),
            Attribute(
                "asset_class",
                "What kind of instrument it is.",
                codelist=("EQUITY", "GOVT_BOND", "CORP_BOND"),
                mandatory=True,
            ),
            Attribute(
                "currency",
                "The currency the instrument is denominated in.",
                semantic_type="currency",
                codelist=("USD", "EUR", "GBP", "CHF", "JPY"),
                mandatory=True,
            ),
            Attribute("primary_venue", "Where it principally trades.", semantic_type="mic"),
        ),
    ),
    Dataset(
        name="Counterparties",
        description="Legal entities the firm faces, and what we think of their credit.",
        grain_statement="one row per legal entity, identified by its LEI",
        grain=("lei",),
        criticality=1,
        arrival_by="05:00",
        obligations=("EMIR", "MiFID II"),
        attributes=(
            Attribute(
                "lei",
                "The ISO 17442 Legal Entity Identifier.",
                semantic_type="lei",
                mandatory=True,
                is_cde=True,
                obligations=("EMIR", "MiFID II"),
            ),
            Attribute("legal_name", "The entity's registered name.", mandatory=True),
            Attribute(
                "jurisdiction",
                "Where the entity is incorporated.",
                codelist=("DE", "US", "FR", "CH", "GB", "NL", "JP"),
            ),
            Attribute(
                "credit_rating",
                "Internal credit rating.",
                codelist=("AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB"),
            ),
        ),
    ),
    Dataset(
        name="Trades",
        description="Executed trades from the front office, as booked.",
        grain_statement="one row per executed trade",
        grain=("trade_id",),
        criticality=1,
        arrival_by="06:30",
        obligations=("MiFID II", "FRTB"),
        attributes=(
            Attribute("trade_id", "The firm's identifier for the trade.", mandatory=True, is_cde=True),
            Attribute("book", "The trading book the risk sits in.", mandatory=True),
            Attribute(
                "isin",
                "The instrument traded. Must exist in the security master.",
                semantic_type="isin",
                mandatory=True,
                is_cde=True,
            ),
            Attribute(
                "counterparty_lei",
                "Who we faced.",
                semantic_type="lei",
                mandatory=True,
                is_cde=True,
                obligations=("EMIR",),
            ),
            Attribute("side", "Which way.", codelist=("BUY", "SELL"), mandatory=True),
            Attribute(
                "quantity",
                "Units traded. Always positive; direction is carried by side.",
                minimum=0.0,
                maximum=100_000_000.0,
                mandatory=True,
            ),
            Attribute(
                "price", "Execution price per unit.", minimum=0.0, maximum=1_000_000.0
            ),
            Attribute(
                "notional",
                "Quantity times price. The number every risk and capital figure rests on.",
                unit="currency",
                currency_attribute="currency",
                mandatory=True,
                is_cde=True,
                obligations=("FRTB", "MiFID II"),
            ),
            Attribute(
                "currency",
                "The currency the notional is expressed in.",
                semantic_type="currency",
                codelist=("USD", "EUR", "GBP", "CHF", "JPY"),
                mandatory=True,
            ),
            Attribute("trade_date", "The date of execution.", semantic_type="iso_date", mandatory=True),
            Attribute("settlement_date", "When it is due to settle.", semantic_type="iso_date"),
            Attribute("venue", "Where it executed.", semantic_type="mic"),
            Attribute("trader", "Who booked it."),
        ),
    ),
    Dataset(
        name="Positions EOD",
        description="End-of-day positions per book and instrument.",
        grain_statement="one position per book per instrument per business day",
        grain=("book", "isin", "as_of_date"),
        criticality=1,
        arrival_by="19:00",
        obligations=("FRTB",),
        attributes=(
            Attribute("book", "The trading book.", mandatory=True),
            Attribute("isin", "The instrument held.", semantic_type="isin", mandatory=True, is_cde=True),
            Attribute("as_of_date", "The business date.", semantic_type="iso_date", mandatory=True),
            Attribute("quantity", "Net units held. May be negative — a short is a position."),
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
                "The currency the value is expressed in.",
                semantic_type="currency",
                codelist=("USD", "EUR", "GBP", "CHF", "JPY"),
                mandatory=True,
            ),
        ),
    ),
    Dataset(
        name="General Ledger",
        description="The firm's book of record, in USD.",
        grain_statement="one balance per book per posting date",
        grain=("book", "posting_date"),
        criticality=1,
        arrival_by="21:00",
        attributes=(
            Attribute("book", "The trading book.", mandatory=True),
            Attribute("posting_date", "The accounting date.", semantic_type="iso_date", mandatory=True),
            Attribute("currency", "Always USD in the ledger.", codelist=("USD",), mandatory=True),
            Attribute(
                "balance_usd",
                "The book's balance, converted to USD.",
                unit="currency",
                mandatory=True,
                is_cde=True,
            ),
        ),
    ),
    Dataset(
        name="FX Rates",
        description="End-of-day rates from the market data vendor.",
        grain_statement="one rate per currency pair per rate date",
        grain=("currency_pair", "rate_date"),
        criticality=2,
        arrival_by="18:00",
        attributes=(
            Attribute("currency_pair", "The pair, base then quote.", mandatory=True),
            Attribute("rate_date", "The date the rate is for.", semantic_type="iso_date", mandatory=True),
            Attribute("rate", "Units of quote per unit of base.", minimum=0.0, maximum=10_000.0, mandatory=True),
            Attribute("source", "Which vendor supplied it.", codelist=("VENDOR-A", "VENDOR-B")),
        ),
    ),
]


async def main(serve: bool, port: int) -> None:
    workspace = HERE / "workspace"
    banner(
        "Case study 1 — a trading book, in SQLite",
        "One source. 5,000 trades, ten business days, nine planted defects.",
    )

    stage(1, "Build the data", "Fabricated, seeded, and deliberately imperfect.")
    database_path, planted, counts = build(workspace)
    for table, count in counts.items():
        say(f"  {table:<24} {count:>8,} rows")
    say()
    say(planted.render())

    harness = Harness(workspace, title="Trading book (SQLite)")
    await harness.start(tenant_slug="acme-markets", tenant_name="Acme Markets")
    try:
        await harness.declare(ESTATE)
        await harness.derive_and_accept()

        execute, close = executor_for(database_path, "sqlite")
        try:
            from _common.harness import Source

            await harness.run(
                [
                    Source(
                        name=str(database_path.name),
                        engine="sqlite",
                        execute=execute,
                        close=close,
                        datasets=set(harness.dataset_ids),
                    )
                ]
            )
        finally:
            close()

        await harness.report(planted)
    finally:
        await harness.stop()

    if serve:
        harness.serve(port=port)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-serve", action="store_true", help="do not start the console")
    parser.add_argument("--port", type=int, default=8801)
    args = parser.parse_args()
    asyncio.run(main(serve=not args.no_serve, port=args.port))
