#!/usr/bin/env python3
"""Case study 6 — month-end close: the subledger against the general ledger.

Runs against **your** Prama, through the SDK. Finance closes the month when
the subledger and the general ledger agree. They are two systems: the
subledger books every entry in its own currency, the ledger holds a EUR
balance per account, cost centre and day, and entries booked on the last
evening reach the ledger the next morning. One `RECONCILE` says all of that,
and the server's reconciliation engine does the matching, the currency
conversion, the timing allowance and the classification of every difference.
The breaks it finds are then read, and worked, on the break workbench.

Usage:
    python run.py                          the server config/application.yaml names
    python run.py --config other.yaml      another server
    python run.py --username ada --password …   as somebody else (default: the dev admin)

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary; see LICENSE.
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from _common.defects import DefectLog  # noqa: E402
from _common.estate import Attribute, Dataset  # noqa: E402
from _common.harness import Harness, Source, arguments, banner, say, stage  # noqa: E402

#: To EUR, as the treasury publishes them at the close.
RATES = {"EUR": Decimal("1.0"), "USD": Decimal("0.92"), "GBP": Decimal("1.16")}
ACCOUNTS = [(f"4{n:03d}", ("EUR", "USD", "GBP")[n % 3]) for n in range(1, 21)]
CENTRES = ("CC-LON", "CC-FRA")
DAYS = [date(2026, 9, 24) + timedelta(days=i) for i in range(7)]

RECONCILIATION = (
    "RECONCILE subledger AGAINST general_ledger "
    "ON (account, cost_centre, posting_date) "
    "COMPARING amount = balance_eur WITHIN 0.01 EUR "
    "NORMALISING currency TO 'EUR' USING RATES fx_rates "
    "OFFSET BY 1 DAY "
    "SEVERITY critical DIMENSION accuracy "
    "BECAUSE 'the month does not close until the subledger agrees with the ledger'"
)

ESTATE = [
    Dataset(
        name="Subledger",
        description="Every entry the business booked, in the currency it was booked in.",
        grain_statement="one row per booked entry",
        grain=("entry_id",),
        criticality=1,
        attributes=(
            Attribute("entry_id", "The entry's identifier.", mandatory=True),
            Attribute("account", "General ledger account.", mandatory=True, is_cde=True),
            Attribute("cost_centre", "Where the cost or revenue sits.", mandatory=True),
            Attribute("posting_date", "The day the entry was booked.", mandatory=True),
            Attribute(
                "currency", "The entry's currency.", codelist=("EUR", "USD", "GBP"), mandatory=True
            ),
            Attribute("amount", "Entry amount, in its own currency.", mandatory=True),
        ),
    ),
    Dataset(
        name="General Ledger",
        description="The book of record: a EUR balance per account, cost centre and day.",
        grain_statement="one row per account, cost centre and day",
        grain=("account", "cost_centre", "posting_date"),
        criticality=1,
        attributes=(
            Attribute("account", "General ledger account.", mandatory=True, is_cde=True),
            Attribute("cost_centre", "Where the cost or revenue sits.", mandatory=True),
            Attribute("posting_date", "The ledger day.", mandatory=True),
            Attribute("balance_eur", "The day's movement, in EUR.", mandatory=True, is_cde=True),
        ),
    ),
    Dataset(
        name="Fx Rates",
        description="The treasury's closing rates to EUR.",
        grain_statement="one row per currency",
        grain=("currency",),
        criticality=2,
        attributes=(
            Attribute("currency", "ISO 4217 code.", mandatory=True),
            Attribute("rate", "EUR per unit of the currency.", minimum=0.0, mandatory=True),
        ),
    ),
]


def _eur(amount: Decimal, currency: str) -> Decimal:
    return (amount * RATES[currency]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def build(workspace: Path) -> tuple[Path, DefectLog, dict[str, int]]:
    """The finance system's two books and its rates, as one SQLite file (the ERP's side)."""
    workspace.mkdir(parents=True, exist_ok=True)
    erp = workspace / "finance.db"
    erp.unlink(missing_ok=True)
    entries: list[tuple[Any, ...]] = []
    # The ledger converts each day's total at the closing rate, as the engine
    # does. Converting each entry and summing the rounded amounts is a
    # different convention, and it differs by cents: a real break between two
    # systems, but not the one this study is about.
    native: dict[tuple[str, str, str], Decimal] = {}
    currency_of = dict(ACCOUNTS)
    serial = 0
    for account, currency in ACCOUNTS:
        for centre in CENTRES:
            for day in DAYS:
                for k in range(3):
                    serial += 1
                    amount = Decimal(1000 + (serial * 7919) % 90000) / 100 + k
                    entries.append(
                        (
                            f"E{serial:06d}",
                            account,
                            centre,
                            day.isoformat(),
                            currency,
                            float(amount),
                        )
                    )
                    key = (account, centre, day.isoformat())
                    native[key] = native.get(key, Decimal(0)) + amount
    ledger = {k: _eur(v, currency_of[k[0]]) for k, v in native.items()}
    log = DefectLog()
    keys = sorted(ledger)
    # ------------------------------------------------------------------ 1
    for key in keys[10:13]:
        ledger[key] += Decimal("250.00")
    log.add(
        key="manual_gl_adjustment",
        dataset="general_ledger",
        what="a manual journal of 250.00 EUR posted to the ledger only",
        rows=3,
        dimension="accuracy",
    )
    # ------------------------------------------------------------------ 2
    dropped = keys[40]
    del ledger[dropped]
    log.add(
        key="missing_in_ledger",
        dataset="general_ledger",
        what="a day's entries never reached the ledger",
        rows=1,
        dimension="completeness",
    )
    # ------------------------------------------------------------------ 3
    ledger[("4999", "CC-LON", DAYS[3].isoformat())] = Decimal("1200.00")
    log.add(
        key="ledger_only_account",
        dataset="general_ledger",
        what="a ledger balance on account 4999, which the subledger never booked",
        rows=1,
        dimension="accuracy",
    )
    # ------------------------------------------------------------------ 4
    last = DAYS[-1].isoformat()
    late = [k for k in keys if k[2] == last and k[0] >= "4015"][:2]
    for key in late:
        ledger[(key[0], key[1], (DAYS[-1] + timedelta(days=1)).isoformat())] = ledger.pop(key)
    log.add(
        key="booked_next_morning",
        dataset="general_ledger",
        what="the last evening's entries reached the ledger the next morning: timing, "
        "which clears itself and must not fail the close",
        rows=2,
        dimension="timeliness",
        detectable=False,
        caveat="Matched across OFFSET BY 1 DAY, so no break: by design it does not fail the "
        "close. The run shows what the same reconciliation says without the offset.",
    )

    connection = sqlite3.connect(erp)
    connection.executescript(
        "CREATE TABLE subledger (entry_id TEXT, account TEXT, cost_centre TEXT, "
        "posting_date TEXT, currency TEXT, amount REAL);"
        "CREATE TABLE general_ledger (account TEXT, cost_centre TEXT, posting_date TEXT, "
        "balance_eur REAL);"
        "CREATE TABLE fx_rates (currency TEXT, rate REAL);"
    )
    connection.executemany("INSERT INTO subledger VALUES (?, ?, ?, ?, ?, ?)", entries)
    connection.executemany(
        "INSERT INTO general_ledger VALUES (?, ?, ?, ?)",
        [(*k, float(v)) for k, v in sorted(ledger.items())],
    )
    connection.executemany(
        "INSERT INTO fx_rates VALUES (?, ?)", [(c, float(r)) for c, r in RATES.items()]
    )
    connection.commit()
    connection.close()
    return erp, log, {"subledger": len(entries), "general_ledger": len(ledger), "fx_rates": 3}


def _declare_reconciliation(harness: Harness) -> str:
    stage(4, "Write the reconciliation", "One statement: key, amount, tolerance, FX, timing.")
    checked = harness.sdk.pql.check(RECONCILIATION)
    errors = [f for f in checked.get("findings") or [] if f.get("level") == "error"]
    if checked.get("syntax_error") or errors:
        say(f"  ! the reconciliation does not check: {checked.get('syntax_error') or errors}")
        sys.exit(1)
    for line in RECONCILIATION.split(" SEVERITY")[0].replace(" ON ", "\n    ON ").split("\n"):
        say(f"  {line}")
    for explained in harness.sdk.pql.explain(RECONCILIATION).get("controls") or []:
        say()
        say(f"  {explained['sentence']}")
    control = harness.author(
        RECONCILIATION, identity="close:subledger-ledger", reason="the month-end close"
    )
    return str(control["id"])


def _workbench(harness: Harness, control_id: str) -> None:
    say()
    say("─" * 78)
    say("  THE BREAK WORKBENCH")
    say("─" * 78)
    listed = harness.sdk.reconciliation.list()
    mine = [r for r in listed.get("reconciliations") or [] if r.get("control_id") == control_id]
    if not mine:
        say("  ! the reconciliation is not listed; nothing below can be trusted")
        return
    (reconciliation,) = mine
    definition = str(reconciliation["definition"])
    latest = reconciliation.get("latest") or {}
    match_rate = latest.get("match_rate")
    say(f"  {definition}: {str(latest.get('verdict', 'not run')).upper()}")
    say(
        f"    match rate {'n/a' if match_rate is None else f'{match_rate:.2%}'}, "
        f"{latest.get('breaks_needing_a_person', '?')} break(s) needing a person"
    )
    say()
    bench = harness.sdk.breaks.workbench(definition)
    rows = bench.get("rows") or []
    by_kind: dict[str, int] = {}
    for row in rows:
        by_kind[row["kind"]] = by_kind.get(row["kind"], 0) + 1
        say(f"  {row['kind']:<10} {row['key']:<32} {str(row.get('because', ''))[:60]}")
    say()
    say("  " + ", ".join(f"{n} {k}" for k, n in sorted(by_kind.items())))
    say("  Each break is a piece of work with an owner: explain it, accept it, or fix it.")
    say("  A timing difference is not a failure: it clears when the ledger catches up.")

    # Working the queue, as the ledger's controller would: the manual journals
    # go to the team that posted them, and the ledger-only account is explained.
    # Nothing is accepted here: accepting carries a difference, it does not
    # make the books agree, and the study has no business deciding that.
    say()
    for row in rows:
        if row["kind"] == "genuine":
            harness.sdk.breaks.assign(row["id"], "gl-journals")
        elif row["kind"] == "extra":
            worked = harness.sdk.breaks.explain(
                row["id"], "account 4999 is a suspense account the subledger does not book to"
            )
            say(f"  explained {row['key']}: {len(worked.get('comments') or [])} in its trail")
    assigned = sum(1 for r in rows if r["kind"] == "genuine")
    say(f"  assigned {assigned} genuine break(s) to gl-journals; none accepted")

    certificate = harness.sdk.reconciliation.certify(definition, period_end=DAYS[-1].isoformat())
    say()
    say(f"  Close certificate for {DAYS[-1].isoformat()} (returned, not stored):")
    say(
        f"    outstanding {certificate.get('outstanding_total')}, "
        f"accepted {certificate.get('accepted_total')}, "
        f"unexplained {certificate.get('unexplained_total')}"
    )
    say(f"    content hash {certificate.get('content_hash')}")


def _without_offset(harness: Harness, erp: Path) -> None:
    """The counterfactual: the same reconciliation with no timing allowance.

    Run for real, by the server's reconciliation engine, in an estate of its
    own. In the close's estate it would file its breaks under the same
    definition ("subledger against general_ledger") and leave a failing record
    beside the real one; a separate estate keeps the close's evidence and its
    break queue exactly as the close left them. (`controls.preview`, which
    records nothing, is no substitute: it runs a control's metric query alone,
    and for a RECONCILE that is not the matching engine.)
    """
    pql = RECONCILIATION.replace(" OFFSET BY 1 DAY", "")
    slug = f"{harness.estate.get('slug', 'acme-finance')}-no-offset"
    made = harness.sdk.tenants.create(slug, "Acme Markets — close, without the timing allowance")
    counterfactual = harness.sdk.as_key(made["credentials"]["api_key"])
    try:
        declared = counterfactual.controls.declare(
            pql, identity="close:subledger-ledger-no-offset", criticality=1
        )
        control = declared.get("control", declared)
        counterfactual.controls.activate(control["id"], reason="the counterfactual")
        connection = counterfactual.connections.create(
            "the ERP (SQLite)", "sqlite", config={"path": str(erp)}
        )
        # The estate's only control; nothing else is declared here.
        counterfactual.runs.start(connection["id"])
        listed = counterfactual.reconciliation.list().get("reconciliations") or []
        (reconciliation,) = [r for r in listed if r.get("control_id") == control["id"]]
        latest = reconciliation.get("latest") or {}
        bench = counterfactual.breaks.workbench(str(reconciliation["definition"]))
    finally:
        counterfactual.close()
    kinds: dict[str, int] = {}
    for row in bench.get("rows") or []:
        kinds[row["kind"]] = kinds.get(row["kind"], 0) + 1
    say()
    say(
        f"  Without OFFSET BY 1 DAY the same books show "
        f"{latest.get('breaks_needing_a_person', '?')} breaks needing a person, not 5"
    )
    say(f"  ({', '.join(f'{n} {k}' for k, n in sorted(kinds.items()))}; estate {slug}):")
    say("  each late entry becomes one missing on the last day and one extra the next.")


def main() -> None:
    args = arguments(__doc__ or "")
    workspace = HERE / "workspace"
    banner(
        "Case study 6 — month-end close",
        "The subledger against the general ledger: currency, timing, and breaks.",
    )
    stage(
        1,
        "Build the ERP's books",
        "Twenty accounts, two cost centres, seven days, three currencies.",
    )
    erp, planted, counts = build(workspace)
    for name, count in counts.items():
        say(f"  {name:<16} {count:>8,} rows")
    say()
    say(planted.render())

    harness = Harness(workspace, title="Month-end close", args=args)
    harness.start(tenant_slug="acme-finance", tenant_name="Acme Markets — finance")
    try:
        harness.declare(ESTATE)
        harness.derive_and_accept()
        control_id = _declare_reconciliation(harness)
        erp_source = Source(
            name="the ERP (SQLite)",
            source_type="sqlite",
            path=erp,
            datasets={"subledger", "general_ledger", "fx_rates"},
        )
        harness.run([erp_source])
        harness.report(planted)
        _workbench(harness, control_id)
        _without_offset(harness, erp)
        harness.finish()
    finally:
        harness.close()


if __name__ == "__main__":
    main()
