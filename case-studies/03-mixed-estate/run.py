#!/usr/bin/env python3
"""Case study 3 — a mixed estate, and the defects only relationships can see.

Two sources: a warehouse in SQLite holding the masters and the book of record,
and a landing zone of CSV and Parquet holding the daily extracts. Two passes,
one evidence ledger — which is what a real estate looks like.

The point of this study is the third kind of declaration. Studies 1 and 2 plant
orphans and a ledger break and decline to claim them, because neither is
visible from either dataset alone. Here the relationships are declared, and the
same defects are found.

Runs against **your** Prama, through the SDK; it starts no server of its own.

Usage:
    python run.py                          the server config/application.yaml names
    python run.py --config other.yaml      another server
    python run.py --username ada --password …   as somebody else (default: the dev admin)

The server reads both sources itself, so this checkout's ``case-studies``
directory must be in its ``runs.roots`` (application.yaml or .local.yaml).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from _common.estate import Attribute, Dataset, Relationship  # noqa: E402
from _common.harness import Harness, Source, arguments, banner, say, stage  # noqa: E402
from generate import build  # noqa: E402

CURRENCIES = ("USD", "EUR", "GBP", "CHF", "JPY")

WAREHOUSE = [
    Dataset(
        name="Instrument Master",
        description="The security master, in the warehouse.",
        grain_statement="one row per instrument, identified by its ISIN",
        grain=("isin",),
        criticality=2,
        attributes=(
            Attribute(
                "isin",
                "The ISO 6166 identifier.",
                semantic_type="isin",
                mandatory=True,
                is_cde=True,
            ),
            Attribute("name", "The instrument's legal name.", mandatory=True),
            Attribute(
                "asset_class",
                "What kind.",
                codelist=("EQUITY", "GOVT_BOND", "CORP_BOND"),
                mandatory=True,
            ),
            Attribute(
                "currency",
                "Denomination.",
                semantic_type="currency",
                codelist=CURRENCIES,
                mandatory=True,
            ),
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
            Attribute(
                "lei", "The ISO 17442 identifier.", semantic_type="lei", mandatory=True, is_cde=True
            ),
            Attribute("legal_name", "Registered name.", mandatory=True),
            Attribute(
                "jurisdiction",
                "Where incorporated.",
                codelist=("DE", "US", "FR", "CH", "GB", "NL", "JP"),
            ),
            Attribute(
                "credit_rating",
                "Internal rating.",
                codelist=("AAA", "AA+", "AA", "AA-", "A+", "A", "A-"),
            ),
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
            Attribute(
                "posting_date", "The accounting date.", semantic_type="iso_date", mandatory=True
            ),
            Attribute("currency", "Always USD.", codelist=("USD",), mandatory=True),
            Attribute(
                "balance_usd", "The balance in USD.", unit="currency", mandatory=True, is_cde=True
            ),
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
            Attribute(
                "isin", "The instrument traded.", semantic_type="isin", mandatory=True, is_cde=True
            ),
            Attribute(
                "counterparty_lei",
                "Who we faced.",
                semantic_type="lei",
                mandatory=True,
                is_cde=True,
            ),
            Attribute("side", "Which way.", codelist=("BUY", "SELL"), mandatory=True),
            Attribute(
                "quantity", "Units traded.", minimum=0.0, maximum=100_000_000.0, mandatory=True
            ),
            Attribute(
                "price", "Execution price.", minimum=0.0, maximum=1_000_000.0, mandatory=True
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
                "The notional's currency.",
                semantic_type="currency",
                codelist=CURRENCIES,
                mandatory=True,
            ),
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
            Attribute(
                "isin", "The instrument held.", semantic_type="isin", mandatory=True, is_cde=True
            ),
            Attribute("as_of_date", "The business date.", semantic_type="iso_date", mandatory=True),
            Attribute("quantity", "Net units held."),
            Attribute(
                "market_value",
                "Value in its own currency.",
                unit="currency",
                currency_attribute="currency",
                mandatory=True,
                is_cde=True,
            ),
            Attribute(
                "currency",
                "The value's currency.",
                semantic_type="currency",
                codelist=CURRENCIES,
                mandatory=True,
            ),
        ),
    ),
]

#: What is true *between* the datasets, named by their slugs. Written against
#: the names a control has to say; the business meaning is in ``description``.
RELATIONSHIPS = [
    Relationship(
        kind="references",
        left="trade_feed",
        right="instrument_master",
        match_keys=(("isin", "isin"),),
        cardinality="many_to_one",
        description="Every trade names an instrument the master knows about.",
    ),
    Relationship(
        kind="references",
        left="trade_feed",
        right="counterparty_master",
        match_keys=(("counterparty_lei", "lei"),),
        cardinality="many_to_one",
        description="Every trade names a counterparty we have on file.",
    ),
    Relationship(
        kind="references",
        left="position_feed",
        right="instrument_master",
        match_keys=(("isin", "isin"),),
        cardinality="many_to_one",
        description="Every position names an instrument the master knows about.",
    ),
    Relationship(
        kind="reconciles_with",
        left="position_feed",
        right="general_ledger",
        match_keys=(("book", "book"),),
        # The ledger states the same amount as balance_usd, one row per book.
        compare=("market_value = balance_usd",),
        cardinality="many_to_one",
        tolerance={"absolute": 1.0, "currency": "USD", "relative": 0.0001},
        description="Positions must agree with the book of record, within a dollar.",
    ),
]

#: The reconciliation, as the finance controller completes Γ's proposal: the
#: positions are in their instruments' currencies and the ledger is in USD, so
#: amounts are normalised with the treasury's rates before they are compared.
RECONCILIATION = (
    "RECONCILE position_feed AGAINST general_ledger ON (book) "
    "COMPARING market_value = balance_usd WITHIN 1 USD OR 0.01% "
    "NORMALISING currency TO 'USD' USING RATES fx_rates "
    "SEVERITY critical DIMENSION consistency "
    "BECAUSE 'positions must agree with the book of record, within a dollar'"
)


def main() -> None:
    args = arguments(__doc__ or "")
    workspace = HERE / "workspace"
    banner(
        "Case study 3 — a mixed estate",
        "A SQLite warehouse and a landing zone of files. Two passes, one ledger.",
    )

    stage(1, "Build both sources", "Masters and ledger in SQLite; extracts as CSV and Parquet.")
    warehouse, _landing, catalogue, planted, counts = build(workspace)
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

    harness = Harness(workspace, title="Mixed estate", args=args)
    harness.start(tenant_slug="acme-group", tenant_name="Acme Markets Group")
    try:
        harness.declare(WAREHOUSE + LANDING)
        harness.relate(RELATIONSHIPS)
        harness.derive_and_accept()
        harness.author(
            RECONCILIATION,
            identity="reconcile:positions-ledger",
            reason="the finance controller completed Γ's proposal with the normalisation",
        )
        say("  authored: " + RECONCILIATION[:96] + "…")
        harness.run(
            [
                Source(
                    name="warehouse (SQLite)",
                    source_type="sqlite",
                    path=warehouse,
                    # The warehouse holds only its own three datasets. A control
                    # on the landing zone run here would be a table-not-found
                    # error, and forty of those bury the findings that are real.
                    datasets={"instrument_master", "counterparty_master", "general_ledger"},
                ),
                Source(
                    # A DuckDB catalogue of views over the files rather than a
                    # ``files`` connection, because the treasury's rates the
                    # reconciliation normalises with are a view, not a file.
                    name="landing zone (CSV + Parquet, via DuckDB)",
                    source_type="duckdb",
                    path=catalogue,
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
        harness.report(planted)
        harness.finish()
    finally:
        harness.close()


if __name__ == "__main__":
    main()
