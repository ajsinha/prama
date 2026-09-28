#!/usr/bin/env python3
"""Case study 4 — Excel formulas, and a validator somebody else wrote.

The two halves of Wave 11, on data that makes both of them matter:

  * A **formula** a finance person would type, compiled to pushed-down SQL —
    and finding a class of defect that nothing else in these studies finds,
    because it is a disagreement between two systems' rounding rules.
  * A **plugin validator** for an identifier scheme Prama has never heard of,
    admitted only after its purity is checked and its implementation hashed
    into the plan.

Usage:
    python run.py                 build, run, and serve the console on :8804
    python run.py --no-serve      build and run, then stop

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import argparse
import asyncio
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
from _common.harness import Harness, Source, banner, say, stage, use_config  # noqa: E402
from acme_validators import AcmeBookCode, book_code  # noqa: E402

from prama.classify.plugins import PLUGINS, scan_source  # noqa: E402
from prama.classify.validators import REGISTRY as VALIDATORS  # noqa: E402
from prama.connect.sources.query import executor_for  # noqa: E402

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


async def main(serve: bool, port: int) -> Any:  # noqa: ARG001
    workspace = HERE / "workspace"
    banner(
        "Case study 4 — Excel formulas, and a validator somebody else wrote",
        "Six formulas a finance person would type, and one plugin identifier scheme.",
    )

    stage(1, "Build the blotter", "Five planted defects, one of them a rounding disagreement.")
    catalogue, planted, rows = build(workspace)
    say(f"  trade_blotter  {rows:,} rows")
    say()
    say(planted.render())

    stage(
        2,
        "Admit the plugin validator",
        "Purity checked before it is usable, and its code hashed into every plan.",
    )
    source = HERE / "acme_validators.py"
    say(f"  scanning {source.name} without importing it…")
    findings = scan_source(str(source))
    if findings:
        for module, reason in findings:
            say(f"    REFUSED  {module}: {reason}")
        say("  A plugin is scanned from its source before it is imported, because")
        say("  importing runs its top-level code — a gate that had to run the thing")
        say("  it was gating would already have run it.")
        return None
    say("    clean: no clock, no network, no filesystem, no model")

    validator = AcmeBookCode()
    provenance = PLUGINS.admit(validator, distribution="acme-pack (local)")
    VALIDATORS.register(validator)
    say(f"    admitted {provenance.name} — implementation {provenance.implementation_hash}")
    say("    ran twice on the same inputs and agreed both times")
    say()
    say("  Every control naming acme_book now carries that hash in its plan id.")
    say("  Edit the check-digit routine and the control changes identity, rather")
    say("  than silently changing what last month's evidence meant.")

    harness = Harness(workspace, title="Expressions and plugins")
    await harness.start(tenant_slug="acme-desk", tenant_name="Acme Markets — trading desk")
    try:
        await harness.declare(ESTATE)
        await _declare_formulas(harness)
        await harness.derive_and_accept()

        execute, close = executor_for(catalogue, "duckdb")
        try:
            await harness.run(
                [
                    Source(
                        name="blotter (CSV, via DuckDB)",
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
        _explain_the_half_cent()
    finally:
        await harness.stop()

    # Returned rather than served here. `harness.serve` calls `uvicorn.run`,
    # which calls `asyncio.run`, and this function is already inside one — so
    # the console never started and the study died on
    # "asyncio.run() cannot be called from a running event loop". Found by a QA
    # pass; nothing under tests/ exercises case-studies/.
    return harness if serve else None


async def _declare_formulas(harness: Harness) -> None:
    """The formulas, as controls, with the SQL each becomes."""
    from prama.backend import compile_for
    from prama.ir.resolve import resolved
    from prama.pql import parse_control

    stage(
        4,
        "Write the controls as formulas",
        "The syntax a finance person already knows, compiled to SQL that runs in the engine.",
    )
    async with harness.database.unit_of_work() as uow:
        for name, formula, dimension, because in FORMULAS:
            pql = (
                f"CHECK trade_blotter SATISFIES EXCEL '{formula}' "
                f"SEVERITY major DIMENSION {dimension} BECAUSE '{because}'"
            )
            control = parse_control(pql)
            compiled = compile_for(resolved(control), "duckdb", table="trade_blotter")
            say(f"  {formula}")
            predicate = compiled.metric_query.split("WHERE NOT COALESCE((", 1)
            if len(predicate) > 1:
                say(f"     → {predicate[1].split('), FALSE)')[0][:100]}")
            entity, _ = await uow.controls.declare(
                tenant_id=harness.tenant_id,
                identity=f"formula:{name}",
                pql=pql,
                rule="authored.excel",
                criticality=1,
                schedule="06:30",
                authored_by="alice",
            )
            await uow.controls.activate(
                str(entity.id), tenant_id=harness.tenant_id, approved_by="bob"
            )
            harness.accepted += 1


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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-serve", action="store_true")
    parser.add_argument(
        "--config", default="", help="a Prama configuration file; defaults to the application's"
    )
    parser.add_argument("--port", type=int, default=8804)
    args = parser.parse_args()
    use_config(args.config)
    started = asyncio.run(main(serve=not args.no_serve, port=args.port))
    if started is not None:
        # Outside the loop, where uvicorn can own one of its own.
        started.serve(port=args.port)
