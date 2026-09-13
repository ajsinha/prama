#!/usr/bin/env python3
"""Case study 3 — a mixed estate, and the defects only relationships can see.

Two sources: a warehouse in SQLite holding the masters and the book of record,
and a landing zone of CSV and Parquet holding the daily extracts. Two passes,
one evidence ledger — which is what a real estate looks like.

The point of this study is the third kind of declaration. Studies 1 and 2 plant
orphans and a ledger break and decline to claim them, because neither is
visible from either dataset alone. Here the relationships are declared, and the
same defects are found.

Usage:
    python run.py                 build, run, and serve the console on :8803
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
from prama.semantic.relationships import (  # noqa: E402
    Cardinality,
    MatchKey,
    RelationshipDeclaration,
    RelationshipKind,
    Tolerance,
)

CURRENCIES = ("USD", "EUR", "GBP", "CHF", "JPY")

WAREHOUSE = [
    Dataset(
        name="Instrument Master",
        description="The security master, in the warehouse.",
        grain_statement="one row per instrument, identified by its ISIN",
        grain=("isin",),
        criticality=2,
        attributes=(
            Attribute("isin", "The ISO 6166 identifier.", semantic_type="isin", mandatory=True, is_cde=True),
            Attribute("name", "The instrument's legal name.", mandatory=True),
            Attribute("asset_class", "What kind.", codelist=("EQUITY", "GOVT_BOND", "CORP_BOND"), mandatory=True),
            Attribute("currency", "Denomination.", semantic_type="currency", codelist=CURRENCIES, mandatory=True),
            Attribute("primary_venue", "Where it trades.", semantic_type="mic"),
        ),
    ),
    Dataset(
        name="Counterparty Master",
        description="Legal entities we face, in the warehouse.",
        grain_statement="one row per legal entity, identified by its LEI",
        grain=("lei",),
        criticality=1,
        obligations=("EMIR",),
        attributes=(
            Attribute("lei", "The ISO 17442 identifier.", semantic_type="lei", mandatory=True, is_cde=True),
            Attribute("legal_name", "Registered name.", mandatory=True),
            Attribute("jurisdiction", "Where incorporated.", codelist=("DE", "US", "FR", "CH", "GB", "NL", "JP")),
            Attribute("credit_rating", "Internal rating.", codelist=("AAA", "AA+", "AA", "AA-", "A+", "A", "A-")),
        ),
    ),
    Dataset(
        name="General Ledger",
        description="The book of record, in USD.",
        grain_statement="one balance per book per posting date",
        grain=("book", "posting_date"),
        criticality=1,
        attributes=(
            Attribute("book", "The trading book.", mandatory=True),
            Attribute("posting_date", "The accounting date.", semantic_type="iso_date", mandatory=True),
            Attribute("currency", "Always USD.", codelist=("USD",), mandatory=True),
            Attribute("balance_usd", "The balance in USD.", unit="currency", mandatory=True, is_cde=True),
        ),
    ),
]

LANDING = [
    Dataset(
        name="Trade Feed",
        description="The front office's daily trade extract, as CSV.",
        grain_statement="one row per executed trade",
        grain=("trade_id",),
        criticality=1,
        shape="feed",
        arrival_by="06:30",
        obligations=("MiFID II", "EMIR"),
        attributes=(
            Attribute("trade_id", "The trade's identifier.", mandatory=True, is_cde=True),
            Attribute("book", "The trading book.", mandatory=True),
            Attribute("isin", "The instrument traded.", semantic_type="isin", mandatory=True, is_cde=True),
            Attribute("counterparty_lei", "Who we faced.", semantic_type="lei", mandatory=True, is_cde=True),
            Attribute("side", "Which way.", codelist=("BUY", "SELL"), mandatory=True),
            Attribute("quantity", "Units traded.", minimum=0.0, maximum=100_000_000.0, mandatory=True),
            Attribute("price", "Execution price.", minimum=0.0, maximum=1_000_000.0, mandatory=True),
            Attribute("notional", "Quantity times price.", unit="currency",
                      currency_attribute="currency", mandatory=True, is_cde=True),
            Attribute("currency", "The notional's currency.", semantic_type="currency",
                      codelist=CURRENCIES, mandatory=True),
            Attribute("trade_date", "Execution date.", semantic_type="iso_date", mandatory=True),
            Attribute("settlement_date", "Settlement date.", semantic_type="iso_date"),
            Attribute("venue", "Where it executed.", semantic_type="mic"),
            Attribute("trader", "Who booked it."),
        ),
    ),
    Dataset(
        name="Position Feed",
        description="End-of-day positions from the risk platform, as Parquet.",
        grain_statement="one position per book per instrument per business day",
        grain=("book", "isin", "as_of_date"),
        criticality=1,
        shape="feed",
        arrival_by="19:00",
        obligations=("FRTB",),
        attributes=(
            Attribute("book", "The trading book.", mandatory=True),
            Attribute("isin", "The instrument held.", semantic_type="isin", mandatory=True, is_cde=True),
            Attribute("as_of_date", "The business date.", semantic_type="iso_date", mandatory=True),
            Attribute("quantity", "Net units held."),
            Attribute("market_value", "Value in its own currency.", unit="currency",
                      currency_attribute="currency", mandatory=True, is_cde=True),
            Attribute("currency", "The value's currency.", semantic_type="currency",
                      codelist=CURRENCIES, mandatory=True),
        ),
    ),
]


def relationships(ids: dict[str, str]) -> list[RelationshipDeclaration]:
    """What is true *between* the datasets.

    Written against the physical names because that is what a control has to
    say; the declaration carries the business meaning in its ``description``.
    """
    return [
        RelationshipDeclaration(
            kind=RelationshipKind.REFERENCES,
            from_dataset_id="trade_feed",
            to_dataset_id="instrument_master",
            match_keys=(MatchKey(left="isin", right="isin"),),
            cardinality=Cardinality.MANY_TO_ONE,
            description="Every trade names an instrument the master knows about.",
        ),
        RelationshipDeclaration(
            kind=RelationshipKind.REFERENCES,
            from_dataset_id="trade_feed",
            to_dataset_id="counterparty_master",
            match_keys=(MatchKey(left="counterparty_lei", right="lei"),),
            cardinality=Cardinality.MANY_TO_ONE,
            description="Every trade names a counterparty we have on file.",
        ),
        RelationshipDeclaration(
            kind=RelationshipKind.REFERENCES,
            from_dataset_id="position_feed",
            to_dataset_id="instrument_master",
            match_keys=(MatchKey(left="isin", right="isin"),),
            cardinality=Cardinality.MANY_TO_ONE,
            description="Every position names an instrument the master knows about.",
        ),
        RelationshipDeclaration(
            kind=RelationshipKind.RECONCILES_WITH,
            from_dataset_id="position_feed",
            to_dataset_id="general_ledger",
            match_keys=(MatchKey(left="book", right="book"),),
            compare=("market_value",),
            cardinality=Cardinality.MANY_TO_ONE,
            tolerance=Tolerance(absolute=1.0, currency="USD", relative=0.0001),
            description="Positions must agree with the book of record, within a dollar.",
        ),
    ]


async def main(serve: bool, port: int) -> Any:
    workspace = HERE / "workspace"
    banner(
        "Case study 3 — a mixed estate",
        "A SQLite warehouse and a landing zone of files. Two passes, one ledger.",
    )

    stage(1, "Build both sources", "Masters and ledger in SQLite; extracts as CSV and Parquet.")
    warehouse, landing, catalogue, planted, counts = build(workspace)
    for name, count in counts.items():
        say(f"  {name:<34} {count:>8,} rows")
    say()
    say("  The masters are also published into the analytics zone as Parquet, because")
    say("  a control spanning two datasets has to run somewhere and no single query")
    say("  reaches both a SQLite file and a Parquet directory. That is a copy, and a")
    say("  copy that stops agreeing with its origin is itself a defect — the")
    say("  'mirrors' relationship exists for it, and this estate does not declare one.")
    say()
    say(planted.render())

    harness = Harness(workspace, title="Mixed estate")
    await harness.start(tenant_slug="acme-group", tenant_name="Acme Markets Group")
    try:
        await harness.declare(WAREHOUSE + LANDING)
        await harness.relate(relationships(harness.dataset_ids))
        await harness.derive_and_accept()

        warehouse_execute, warehouse_close = executor_for(warehouse, "sqlite")
        landing_execute, landing_close = executor_for(catalogue, "duckdb")
        try:
            await harness.run(
                [
                    Source(
                        name="warehouse (SQLite)",
                        engine="sqlite",
                        execute=warehouse_execute,
                        close=warehouse_close,
                        # The warehouse holds only its own three datasets. A
                        # control on the landing zone run here would be a
                        # table-not-found error, and forty of those bury the
                        # findings that are real.
                        datasets={"instrument_master", "counterparty_master", "general_ledger"},
                    ),
                    Source(
                        name="landing zone (CSV + Parquet, via DuckDB)",
                        engine="duckdb",
                        execute=landing_execute,
                        close=landing_close,
                        # The feeds *and* the published masters, so the
                        # cross-dataset controls have both sides to hand.
                        datasets={
                            "trade_feed",
                            "position_feed",
                            "instrument_master",
                            "counterparty_master",
                            "general_ledger",
                        },
                    ),
                ]
            )
        finally:
            warehouse_close()
            landing_close()

        await harness.report(planted)
    finally:
        await harness.stop()

    # Returned rather than served here. `harness.serve` calls `uvicorn.run`,
    # which calls `asyncio.run`, and this function is already inside one — so
    # the console never started and the study died on
    # "asyncio.run() cannot be called from a running event loop". Found by a QA
    # pass; nothing under tests/ exercises case-studies/.
    return harness if serve else None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-serve", action="store_true")
    parser.add_argument("--port", type=int, default=8803)
    args = parser.parse_args()
    started = asyncio.run(main(serve=not args.no_serve, port=args.port))
    if started is not None:
        # Outside the loop, where uvicorn can own one of its own.
        started.serve(port=args.port)
