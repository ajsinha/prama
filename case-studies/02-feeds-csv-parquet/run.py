#!/usr/bin/env python3
"""Case study 2 — daily feeds: CSV, Parquet and JSON Lines.

Runs against **your** Prama, through the SDK: builds a landing zone of files,
declares five feeds in business terms, lets Γ derive the controls, accepts
them, registers the landing zone as a ``files`` connection, has the server read
the files itself and run the controls, and prints what was found against what
was planted. It starts no server of its own.

Usage:
    python run.py                          the server config/application.yaml names
    python run.py --config other.yaml      another server
    python run.py --username ada --password …   as somebody else (default: the dev admin)

The server reads the landing zone itself, so this checkout's ``case-studies``
directory must be in its ``runs.roots`` (application.yaml or .local.yaml).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from _common.estate import Attribute, Dataset  # noqa: E402
from _common.harness import Harness, Source, arguments, banner, say, stage  # noqa: E402
from generate import build  # noqa: E402

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
            Attribute(
                "trade_id", "The firm's identifier for the trade.", mandatory=True, is_cde=True
            ),
            Attribute("book", "The trading book the risk sits in.", mandatory=True),
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
            Attribute(
                "trade_date", "The date of execution.", semantic_type="iso_date", mandatory=True
            ),
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
            Attribute(
                "isin", "The instrument held.", semantic_type="isin", mandatory=True, is_cde=True
            ),
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
    Dataset(
        name="Settlement Feed",
        description="The settlement system's daily instructions, as JSON Lines.",
        grain_statement="one row per settlement instruction",
        grain=("settlement_id",),
        criticality=2,
        shape="feed",
        frequency="daily",
        attributes=(
            Attribute("settlement_id", "The instruction's identifier.", mandatory=True),
            Attribute(
                "amount",
                "Amount to settle; the direction is not in the sign.",
                minimum=0.0,
                mandatory=True,
            ),
            Attribute("currency", "Settlement currency.", codelist=("USD", "EUR", "GBP")),
            Attribute(
                "status",
                "Where the instruction stands.",
                codelist=("PENDING", "SETTLED", "FAILED"),
                mandatory=True,
            ),
            Attribute("value_date", "The intended settlement date.", mandatory=True),
        ),
    ),
]

#: Each feed as the table a control names, and the files in the landing zone
#: that make it up. A ``files`` connection reads them in place, on the server,
#: with DuckDB: nothing is copied or loaded, and a glob is how a feed that
#: lands one file a day becomes one table.
TABLES = {
    "trade_feed": "trades/*.csv",
    "position_feed": "positions/*.parquet",
    "instrument_feed": "instruments/*.parquet",
    "counterparty_feed": "counterparties/*.csv",
    "settlement_feed": "settlements/*.jsonl",
}


def main() -> None:
    args = arguments(__doc__ or "")
    workspace = HERE / "workspace"
    banner(
        "Case study 2 — daily feeds: CSV, Parquet and JSON Lines",
        "A landing zone. Ten business days, five feeds, nine planted defects.",
    )

    stage(
        1, "Build the landing zone", "CSV where a vendor writes it, Parquet where a platform does."
    )
    landing, _catalogue, planted, counts = build(workspace)
    say(f"  {landing}")
    for name, count in counts.items():
        say(f"    {name:<26} {count:>8,} rows")
    say()
    say("  The server reads CSV, Parquet and JSON Lines in place — nothing is copied,")
    say("  and the files on disk stay the source of truth.")
    say()
    say(planted.render())

    harness = Harness(workspace, title="Feeds (CSV + Parquet + JSON Lines)", args=args)
    harness.start(tenant_slug="acme-feeds", tenant_name="Acme Markets — landing zone")
    try:
        harness.declare(ESTATE)
        harness.derive_and_accept()
        harness.run(
            [
                Source(
                    name="landing zone (CSV + Parquet + JSON Lines)",
                    source_type="files",
                    path=landing,
                    datasets=set(harness.dataset_ids),
                    config={"tables": TABLES},
                )
            ]
        )
        harness.report(planted)
        _arrival(harness)
        harness.finish()
    finally:
        harness.close()


def _arrival(harness: Harness) -> None:
    """What arrived, and what did not — and why this run does not say.

    Content controls cannot see a missing file: there is nothing wrong with the
    rows, because there are no rows. Arrival is a property of the *feed*, judged
    from the filenames against a filename pattern and a business calendar.
    Prama has that judgement (``prama.connect.feed``), and before this study
    drove the server through the SDK it ran it in-process and reported the
    missing 2026-09-03 file and the duplicated 2026-09-07 delivery from the
    filenames. The server exposes no arrival judgement over its API, so a
    client cannot ask for one, and this study does not compute one itself: a
    verdict worked out by the study would be the study's, not Prama's.
    """
    say()
    say("─" * 78)
    say("  WHAT ARRIVED, AND WHAT DID NOT")
    say("  A missing file is invisible to every content check: there are no rows to be wrong.")
    say("─" * 78)
    derived = [u for u in harness.unsatisfiable if "arrives" in u["reason"]]
    say("  NOT CLAIMED IN THIS RUN — the missing 2026-09-03 delivery.")
    say()
    say("  Arrival is judged from the filenames, against the feed's filename pattern")
    say("  (TRADES_{YYYYMMDD}_{SEQ:3}.csv) and its business calendar, and that")
    say("  judgement is not reachable through the SDK: the server has no endpoint")
    say("  that says which expected deliveries arrived. A report worked out here,")
    say("  in the study, would be the study's finding and not Prama's, so there is")
    say("  none. The planted list above still counts it, and nothing above found it.")
    say()
    say("  The duplicated 2026-09-07 delivery IS found above, by content: the")
    say("  declared grain (one row per trade_id) sees every trade twice.")
    if derived:
        say()
        say(f"  Nor could Γ derive a freshness control for {len(derived)} feed(s): each")
        say("  declares when it arrives, but no column records the arrival.")


if __name__ == "__main__":
    main()
