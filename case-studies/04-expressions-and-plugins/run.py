#!/usr/bin/env python3
"""Case study 4 — Excel formulas, and a validator somebody else wrote.

The two halves of Wave 11, on data that makes both of them matter:

  * A **formula** a finance person would type, compiled to pushed-down SQL —
    and finding a class of defect that nothing else in these studies finds,
    because it is a disagreement between two systems' rounding rules.
  * A **plugin validator** for an identifier scheme Prama has never heard of,
    admitted by the server only after its purity is checked and its
    implementation hashed into the plan.

Runs against **your** Prama, through the SDK; it starts no server of its own.
The validator is admitted where controls run, which is the server, so install
it into the server's environment first and restart the server:

    uv pip install --no-deps -e case-studies/04-expressions-and-plugins

Usage:
    python run.py                          the server config/application.yaml names
    python run.py --config other.yaml      another server
    python run.py --username ada --password …   as somebody else (default: the dev admin)

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import csv
import dataclasses
import shutil
import sys
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import duckdb  # noqa: E402
from _common.bank import Book  # noqa: E402
from _common.defects import DefectLog  # noqa: E402
from _common.estate import Attribute, Dataset  # noqa: E402
from _common.harness import Harness, Source, arguments, banner, say, stage  # noqa: E402
from acme_validators import book_code  # noqa: E402

import prama.sdk as prama  # noqa: E402

#: The controls a business owner writes, in the syntax they already know.
#: Every one of these compiles to SQL that runs inside the engine — which is
#: the performance decision that matters, and the reason the catalogue exists.
FORMULAS: list[tuple[str, str, str, str]] = [
    (
        "notional_ties_out",
        "=ROUND([quantity] * [price], 2) = [notional]",
        "accuracy",
        "the notional must be the quantity times the price, to the cent",
    ),
    (
        "notional_within_materiality",
        "=ABS(ROUND([quantity] * [price], 2) - [notional]) <= 0.005",
        "accuracy",
        "the notional agrees with the recomputation within half a cent",
    ),
    (
        "positive_economics",
        "=AND([quantity] > 0, [price] > 0)",
        "validity",
        "a trade with a non-positive quantity or price is a booking error",
    ),
    (
        "settles_after_trading",
        "=[settlement_date] >= [trade_date]",
        "consistency",
        "a trade cannot settle before it is executed",
    ),
    (
        "identified_counterparty",
        "=NOT(ISBLANK([counterparty_lei]))",
        "completeness",
        "an EMIR report with no counterparty is a rejected report",
    ),
    (
        "venue_is_a_mic",
        "=IF(ISBLANK([venue]), FALSE, LEN([venue]) = 4)",
        "validity",
        "a market identifier code is four characters",
    ),
    (
        "codes_are_upper_case",
        "=UPPER([currency]) = [currency]",
        "conformity",
        "codes are stored upper case so a join does not miss on case",
    ),
]

ESTATE = [
    Dataset(
        name="Trade Blotter",
        description="The desk's daily blotter, as the front office writes it.",
        grain_statement="one row per executed trade",
        grain=("trade_id",),
        criticality=1,
        shape="feed",
        arrival_by="06:30",
        obligations=("MiFID II", "EMIR"),
        attributes=(
            Attribute("trade_id", "The trade's identifier.", mandatory=True, is_cde=True),
            Attribute(
                "book_code",
                "Acme's internal trading-book code.",
                # A semantic type Prama does not ship. The plugin supplies it,
                # and the control that follows is two-stage like any other.
                semantic_type="acme_book",
                mandatory=True,
                is_cde=True,
            ),
            Attribute("isin", "The instrument traded.", semantic_type="isin", mandatory=True),
            Attribute("counterparty_lei", "Who we faced.", semantic_type="lei", is_cde=True),
            Attribute("side", "Which way.", codelist=("BUY", "SELL"), mandatory=True),
            Attribute("quantity", "Units traded.", minimum=0.0, maximum=100_000_000.0),
            Attribute("price", "Execution price.", minimum=0.0, maximum=1_000_000.0),
            Attribute(
                "notional",
                "Quantity times price, to the cent.",
                unit="currency",
                currency_attribute="currency",
                mandatory=True,
                is_cde=True,
            ),
            Attribute(
                "currency",
                "The notional's currency.",
                semantic_type="currency",
                codelist=("USD", "EUR", "GBP", "CHF", "JPY"),
                mandatory=True,
            ),
            Attribute("trade_date", "Execution date.", semantic_type="iso_date", mandatory=True),
            Attribute("settlement_date", "Settlement date.", semantic_type="iso_date"),
            Attribute("venue", "Where it executed.", semantic_type="mic"),
        ),
    ),
]


def build(workspace: Path) -> tuple[Path, DefectLog, int]:
    landing = workspace / "landing"
    if landing.exists():
        shutil.rmtree(landing)
    (landing / "blotter").mkdir(parents=True)

    book = Book(days=6)
    book.generate(trades_per_day=500)
    log = DefectLog()
    rows = [dataclasses.asdict(t) for t in book.trades]

    desks = ("EQ", "FX", "CR", "RT")
    half_cent = 0
    for index, row in enumerate(rows):
        row["book_code"] = book_code(desks[index % len(desks)], 1000 + (index % 40))
        # ---------------------------------------------------------------- 1
        # The upstream system rounds half to *even*. Prama's ROUND is half away
        # from zero, which is what a settlement system does. On the ties — and
        # an integer quantity times a four-decimal price lands on a tie often —
        # the two disagree by exactly one cent.
        exact = Decimal(str(row["quantity"])) * Decimal(str(row["price"]))
        upstream = exact.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        settlement = exact.quantize(Decimal("0.01"), rounding="ROUND_HALF_UP")
        row["notional"] = float(upstream)
        if upstream != settlement:
            half_cent += 1

    log.add(
        key="half_cent",
        dataset="trade_blotter",
        what=(
            "the blotter rounds half-to-even and settlement rounds half-up — one "
            "cent apart on every tie, and nothing about either number looks wrong"
        ),
        rows=half_cent,
        dimension="accuracy",
    )

    # ---------------------------------------------------------------- 2
    for row in rows[100:118]:
        row["settlement_date"] = "2020-01-01"
    log.add(
        key="settles_before_trade",
        dataset="trade_blotter",
        what="settlement date before the trade date — physically impossible",
        rows=18,
        dimension="consistency",
    )

    # ---------------------------------------------------------------- 3
    for row in rows[300:311]:
        row["counterparty_lei"] = ""
    log.add(
        key="missing_counterparty",
        dataset="trade_blotter",
        what="no counterparty LEI — an EMIR report would be rejected",
        rows=11,
        dimension="completeness",
    )

    # ---------------------------------------------------------------- 4
    for row in rows[500:507]:
        code = row["book_code"]
        wrong = "A" if code[-1] != "A" else "B"
        row["book_code"] = code[:-1] + wrong
    log.add(
        key="bad_book_check_character",
        dataset="trade_blotter",
        what="book code check character wrong — right shape, wrong code",
        rows=7,
        dimension="validity",
    )

    # ---------------------------------------------------------------- 5
    for row in rows[700:709]:
        row["currency"] = row["currency"].lower()
    log.add(
        key="lower_case_currency",
        dataset="trade_blotter",
        what="currency in lower case — a join on it silently misses",
        rows=9,
        dimension="conformity",
    )

    path = landing / "blotter" / "BLOTTER_20260908.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    catalogue = workspace / "blotter.duckdb"
    if catalogue.exists():
        catalogue.unlink()
    connection = duckdb.connect(str(catalogue))
    connection.execute(
        f"CREATE VIEW trade_blotter AS "
        f"SELECT * FROM read_csv_auto('{landing}/blotter/*.csv', header=true)"
    )
    connection.close()
    return catalogue, log, len(rows)


#: What the server is asked to compile, to learn whether it admitted the plugin.
#: A server that does not know ``acme_book`` refuses the control outright rather
#: than compiling a check that passes everything.
PLUGIN_PROBE = (
    "CHECK trade_blotter.book_code IS VALID acme_book "
    "SEVERITY major DIMENSION validity BECAUSE 'the book code is Acme standard BK-4'"
)


def main() -> None:
    args = arguments(__doc__ or "")
    workspace = HERE / "workspace"
    banner(
        "Case study 4 — Excel formulas, and a validator somebody else wrote",
        "Seven formulas a finance person would type, and one plugin identifier scheme.",
    )

    stage(1, "Build the blotter", "Five planted defects, one of them a rounding disagreement.")
    _catalogue, planted, rows = build(workspace)
    say(f"  trade_blotter  {rows:,} rows")
    say()
    say(planted.render())

    harness = Harness(workspace, title="Expressions and plugins", args=args)
    harness.start(tenant_slug="acme-desk", tenant_name="Acme Markets — trading desk")
    try:
        admitted = _plugin(harness.sdk)
        harness.declare(ESTATE)
        harness.derive_and_accept()
        _declare_formulas(harness)
        harness.run(
            [
                Source(
                    name="blotter (CSV)",
                    source_type="files",
                    path=workspace / "landing",
                    datasets=set(harness.dataset_ids),
                    config={"tables": {"trade_blotter": "blotter/*.csv"}},
                )
            ]
        )
        harness.report(planted)
        if not admitted:
            say()
            say("  ! acme_book was not admitted on this server, so the book-code defect")
            say("    above had no control at all. Install the plugin and rerun.")
        _explain_the_half_cent()
        harness.finish()
    finally:
        harness.close()


def _plugin(sdk: prama.Client) -> bool:
    """Ask the server whether it admitted the plugin, by compiling a control naming it.

    The validator is admitted where controls run: the server loads every
    ``prama.validators`` entry point when it starts, scans the module's source
    for a clock, a socket, the filesystem or a model client, runs it twice on
    the same probes, and folds a hash of its implementation into the plan of
    every control that names it. That happens in the server's process, so the
    study cannot do it for the server, and it does not pretend to by admitting a
    copy in its own.
    """
    stage(
        2,
        "Is the plugin validator admitted?",
        "Purity checked before it is usable, and its code hashed into every plan.",
    )
    compiled = sdk.pql.compile(PLUGIN_PROBE, dialect="duckdb")
    plan = (compiled.get("plans") or [{}])[0]
    if plan.get("error"):
        say("  NOT ADMITTED. The server refused a control naming acme_book:")
        say(f"    {str(plan['error']).split(' | ')[0]}")
        say()
        say("  A plugin is admitted by the server that runs the controls, at start-up,")
        say("  from the `prama.validators` entry point. Install it into the server's")
        say("  environment and restart the server:")
        say("      uv pip install --no-deps -e case-studies/04-expressions-and-plugins")
        say("  The study goes on without it: the book-code declaration is then one")
        say("  Γ cannot satisfy, and says so below.")
        return False
    residuals = [r for r in plan.get("residual_validators") or [] if isinstance(r, dict)]
    say("  admitted by the server: a control naming acme_book compiles.")
    say(f"    plan            {plan.get('plan_id', '?')}")
    for residual in residuals:
        say(
            f"    residual        {residual.get('validator', '?')} on "
            f"{residual.get('column', '?')}, after the SQL screen"
        )
    say()
    say("  When it started, the server loaded acme_validators through its entry point,")
    say("  scanned its source and any sibling module it imports (no clock, no network,")
    say("  no filesystem, no model), ran it twice on the same probes, and hashed its")
    say("  implementation into the plan of every control naming acme_book. Edit the")
    say("  check-character routine, restart the server, and the plan id changes: the")
    say("  control changes identity rather than silently changing what last month's")
    say("  evidence meant.")
    say()
    say("  The plan id above is what the API returns. The implementation hash inside")
    say("  it is not returned on its own, and no endpoint lists the plugins a server")
    say("  admitted, so this study cannot print the hash the way it once did.")
    return True


def _declare_formulas(harness: Harness) -> None:
    """The formulas, as controls, with the SQL the server compiles each to."""
    stage(
        3,
        "Write the controls as formulas",
        "The syntax a finance person already knows, compiled to SQL that runs in the engine.",
    )
    for name, formula, dimension, because in FORMULAS:
        pql = (
            f"CHECK trade_blotter SATISFIES EXCEL '{formula}' "
            f"SEVERITY major DIMENSION {dimension} BECAUSE '{because}'"
        )
        compiled: dict[str, Any] = harness.sdk.pql.compile(pql, dialect="duckdb")
        plan = (compiled.get("plans") or [{}])[0]
        say(f"  {formula}")
        predicate = str(plan.get("metric_query", "")).split("WHERE NOT COALESCE((", 1)
        if len(predicate) > 1:
            say(f"     → {predicate[1].split('), FALSE)')[0][:100]}")
        harness.author(
            pql, identity=f"formula:{name}", reason="the desk's formula, reviewed for the study"
        )
    say()
    say(f"  {len(FORMULAS)} formula control(s) declared and activated.")


def _explain_the_half_cent() -> None:
    say()
    say("─" * 78)
    say("  THE HALF-CENT")
    say("─" * 78)
    say("  The formula =ROUND([quantity] * [price], 2) = [notional] finds a class of")
    say("  defect nothing else in these studies finds, and it is not a bug in either")
    say("  system:")
    say()
    say("    the blotter rounds half to EVEN     2.675 → 2.67")
    say("    settlement rounds half AWAY FROM 0  2.675 → 2.68")
    say()
    say("  One cent, on every tie, and an integer quantity times a four-decimal price")
    say("  lands on a tie often. Nothing about either number looks wrong in isolation;")
    say("  the disagreement only exists between them.")
    say()
    say("  Prama's ROUND is half away from zero, which is what a settlement system")
    say("  does. It says so on the function — printed by `control explain` rather than")
    say("  discovered in a reconciliation six months later — and it refuses to run on")
    say("  SQLite, which has no exact numeric type and would give a third answer.")
    say()
    say("  WHAT BUILDING THIS FOUND")
    say("  The first version of the ROUND lowering emitted CAST(x AS NUMERIC), which")
    say("  is arbitrary precision in PostgreSQL and DECIMAL(18,3) in DuckDB. Rounding")
    say("  through three decimals and then to two is a *double* rounding:")
    say()
    say("    1953193.4649  →  .465  →  .47        two roundings")
    say("    1953193.4649  →  .46                 one rounding")
    say()
    say("  It reported 131 extra rows as a cent out when they were not — a false alarm")
    say("  on the control people trust most, in the direction that makes a clean book")
    say("  look broken. The lowering now states its scale, the corpus pins it, and")
    say("  this study finds exactly the 31 rows it planted.")


if __name__ == "__main__":
    main()
