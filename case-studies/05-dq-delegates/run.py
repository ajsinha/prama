#!/usr/bin/env python3
"""Case study 5 — DQ delegates: Python checks the bank writes, under Prama's rules.

Runs against **your** Prama, through the SDK. Two checks PQL cannot say,
written as delegates by Acme's own engineers, uploaded to Prama, approved by a
second administrator (four eyes), named from PQL, and run by the server:

  * **acme.settlement_cycle**. Every trade settles its market's cycle of
    *business days* after trading: US T+1 since May 2024, EU T+2, each on its
    own holiday calendar.
  * **acme.benford_first_digit**. Whether amounts' first digits follow
    Benford's law, on the receipts ledger the server can read; the payments
    ledger lives in a PCI zone the control plane cannot reach.

And one delegate that must be refused, because it fetches FX rates from the
internet: the upload is refused from its source, before it is imported.

Usage:
    python run.py                          the server config/application.yaml names
    python run.py --config other.yaml      another server
    python run.py --username ada --password …   as somebody else (default: the dev admin)

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary; see LICENSE.
"""

from __future__ import annotations

import csv
import random
import secrets
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import duckdb  # noqa: E402
from _common.defects import DefectLog  # noqa: E402
from _common.estate import Attribute, Dataset  # noqa: E402
from _common.harness import Harness, Source, arguments, banner, say, stage  # noqa: E402

import prama.sdk as prama  # noqa: E402

DELEGATES = HERE / "acme_delegates"
REJECTED = HERE / "rejected"
#: Control ids by the identity they were declared under, for the comparison.
DECLARED: dict[str, str] = {}

#: The generator's own calendar, written independently of the delegate's so
#: the study does not grade the delegate against itself.
_HOLIDAYS = {
    "US": {"2026-04-03", "2026-05-25"},
    "EU": {"2026-04-03", "2026-04-06", "2026-05-01"},
    "UK": {"2026-04-03", "2026-04-06", "2026-05-04", "2026-05-25"},
}
_CYCLE = {"US": 1, "EU": 2, "UK": 2}

#: The controls, as the data owners write them.
SETTLEMENT = (
    "CHECK trade_blotter USING DELEGATE 'acme.settlement_cycle@1' "
    "(us_cycle = 1, eu_cycle = 2, uk_cycle = 2) "
    "SEVERITY critical DIMENSION timeliness, consistency "
    "BECAUSE 'a trade that settles off-cycle is a failed or mis-booked settlement'"
)
NAIVE = (
    "CHECK trade_blotter SATISFIES EXCEL '=[settlement_date] >= [trade_date]' "
    "SEVERITY major DIMENSION consistency BECAUSE 'the column-comparison way to say it'"
)
BENFORD = (
    "CHECK {dataset} USING DELEGATE 'acme.benford_first_digit' (min_rows = 300) "
    "SEVERITY major DIMENSION accuracy "
    "BECAUSE 'invented amounts do not follow the first-digit law that real ones do'"
)

ESTATE = [
    Dataset(
        name="Trade Blotter",
        description="Executed trades across the US, EU and UK desks.",
        grain_statement="one row per executed trade",
        grain=("trade_id",),
        criticality=1,
        attributes=(
            Attribute("trade_id", "The trade's identifier.", mandatory=True, is_cde=True),
            Attribute("market", "Where it settles.", codelist=("US", "EU", "UK"), mandatory=True),
            Attribute("trade_date", "Execution date.", mandatory=True),
            Attribute("settlement_date", "Contractual settlement date.", mandatory=True),
            Attribute("notional", "Trade value.", minimum=0.0),
        ),
    ),
    Dataset(
        name="Payments Ledger",
        description="Supplier payments released by accounts payable.",
        grain_statement="one row per payment released",
        grain=("payment_id",),
        criticality=1,
        attributes=(
            Attribute("payment_id", "The payment.", mandatory=True, is_cde=True),
            Attribute("amount", "Amount paid.", minimum=0.0, mandatory=True),
            Attribute("approver", "Who approved it.", mandatory=True),
        ),
    ),
    Dataset(
        name="Receipts Ledger",
        description="Customer receipts, for contrast: nobody invents these.",
        grain_statement="one row per receipt",
        grain=("payment_id",),
        criticality=2,
        attributes=(
            Attribute("payment_id", "The receipt.", mandatory=True),
            Attribute("amount", "Amount received.", minimum=0.0, mandatory=True),
        ),
    ),
]


def _settle(traded: date, market: str) -> date:
    days, current = _CYCLE[market], traded
    while days:
        current += timedelta(days=1)
        if current.weekday() < 5 and current.isoformat() not in _HOLIDAYS[market]:
            days -= 1
    return current


def _business_days(start: date, end: date) -> list[date]:
    days, current = [], start
    while current <= end:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def _natural_amount(rng: random.Random) -> float:
    # Log-uniform over five orders of magnitude: what naturally occurring
    # amounts look like, and why their first digits follow Benford's law.
    return round(10 ** rng.uniform(1, 6), 2)


def build(workspace: Path) -> tuple[Path, DefectLog, dict[str, int]]:
    landing = workspace / "landing"
    if landing.exists():
        shutil.rmtree(landing)
    landing.mkdir(parents=True)
    rng = random.Random(42)
    log = DefectLog()

    # -- trades ------------------------------------------------------------
    trades: list[dict[str, Any]] = []
    for index, traded in enumerate(
        d for d in _business_days(date(2026, 4, 1), date(2026, 5, 29)) for _ in range(40)
    ):
        market = ("US", "EU", "UK")[index % 3]
        if traded.isoformat() in _HOLIDAYS[market]:
            continue
        trades.append(
            {
                "trade_id": f"T{index:05d}",
                "market": market,
                "trade_date": traded.isoformat(),
                "settlement_date": _settle(traded, market).isoformat(),
                "notional": round(rng.uniform(1e4, 5e6), 2),
            }
        )
    us = [t for t in trades if t["market"] == "US" and t["trade_date"] >= "2026-05-04"]
    for trade in us[:23]:
        traded = date.fromisoformat(trade["trade_date"])
        legacy = _settle(_settle(traded, "US"), "US")  # T+2: the pre-2024 cycle
        trade["settlement_date"] = legacy.isoformat()
    log.add(
        key="us_still_t_plus_2",
        dataset="trade_blotter",
        what="US trades booked T+2 by a desk system never moved to T+1",
        rows=23,
        dimension="timeliness",
    )
    eu = [t for t in trades if t["market"] == "EU" and t["trade_date"] == "2026-04-29"]
    for trade in eu[:9]:
        trade["settlement_date"] = "2026-05-01"
    log.add(
        key="eu_settles_on_target2_holiday",
        dataset="trade_blotter",
        what="EU trades set to settle on 1 May, a TARGET2 closing day (weekday-only calendar)",
        rows=9,
        dimension="consistency",
    )
    for trade in trades[500:504]:
        trade["settlement_date"] = "31/04/2026"
    log.add(
        key="unreadable_settlement_date",
        dataset="trade_blotter",
        what="settlement date in DD/MM/YYYY, and 31 April does not exist",
        rows=4,
        dimension="validity",
    )
    _write(landing / "trades.csv", trades)

    # -- payments: fabricated invoices just under a 5,000 approval limit -----
    payments = [
        {
            "payment_id": f"P{i:05d}",
            "amount": _natural_amount(rng),
            "approver": f"u{rng.randint(1, 40):03d}",
        }
        for i in range(4000)
    ]
    payments += [
        {
            "payment_id": f"P{4000 + i:05d}",
            "amount": round(rng.uniform(4000, 4990), 2),
            "approver": "u117",
        }
        for i in range(350)
    ]
    rng.shuffle(payments)
    log.add(
        key="split_under_approval_limit",
        dataset="payments_ledger",
        what="350 invented invoices between 4,000 and 4,990, under a 5,000 approval limit",
        rows=350,
        dimension="accuracy",
    )
    _write(landing / "payments.csv", payments)
    receipts = [{"payment_id": f"R{i:05d}", "amount": _natural_amount(rng)} for i in range(4000)]
    _write(landing / "receipts.csv", receipts)

    catalogue = workspace / "acme.duckdb"
    if catalogue.exists():
        catalogue.unlink()
    connection = duckdb.connect(str(catalogue))
    # Dates arrive as text, as they do in most feeds: the unreadable ones are
    # part of the point, and a typed column would have rejected them upstream.
    as_text = "types={'trade_date': 'VARCHAR', 'settlement_date': 'VARCHAR'}, "
    for view, name, options in (
        ("trade_blotter", "trades", as_text),
        ("payments_ledger", "payments", ""),
        ("receipts_ledger", "receipts", ""),
    ):
        connection.execute(
            f"CREATE VIEW {view} AS SELECT * FROM "
            f"read_csv('{landing}/{name}.csv', header=true, {options}auto_detect=true)"
        )
    connection.close()
    return (
        catalogue,
        log,
        {"trades": len(trades), "payments": len(payments), "receipts": len(receipts)},
    )


def _write(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _reviewer(harness: Harness) -> prama.Client:
    """A second administrator, signed in as themselves: the delegate's four eyes.

    Code that will run against the estate's data is approved by somebody other
    than the person who uploaded it. The server enforces that; this is the
    second person it asks for.
    """
    password = secrets.token_urlsafe(18)
    harness.sdk.principals.create(
        "reviewer",
        roles=["admin"],
        password=password,
        display_name="Rui Costa (reviews delegate code)",
    )
    return prama.connect(
        harness.sdk.base_url,
        username="reviewer",
        password=password,
        tenant=str(harness.estate.get("slug", "")),
    )


def _admit(harness: Harness, reviewer: prama.Client) -> None:
    """Upload each delegate, have the second administrator approve it, and try the bad one."""
    stage(
        "3b",
        "Upload the delegates, and approve them with four eyes",
        "Vetted in the server's sandbox before import; approved by somebody else.",
    )
    for path in sorted(DELEGATES.glob("*.py")):
        upload = harness.sdk.delegates.upload(path)
        described = upload.get("described") or {}
        checks = upload.get("findings") or []
        passed = sum(1 for c in checks if c.get("passed"))
        say(f"  uploaded  {upload['name']}@{upload['version']}  ({path.name}) — {upload['state']}")
        reads = ", ".join(described.get("requires") or [])
        say(f"            counts {described.get('unit', '?')}; reads {reads}")
        say(f"            vetting: {passed} of {len(checks)} conformance check(s) passed")
        say(f"            source {str(described.get('implementation_hash', ''))[:32]}")
        try:
            harness.sdk.delegates.approve(upload["id"])
            say("            ! the uploader approved their own delegate: four eyes did not hold")
        except prama.ForbiddenError as error:
            say(f"            the uploader cannot approve it: {error.message}")
        decided = reviewer.delegates.approve(upload["id"], note="read the source; approved")
        say(f"            approved by the reviewer — {decided['state']}")
    say()
    for path in sorted(REJECTED.glob("*.py")):
        try:
            upload = harness.sdk.delegates.upload(path)
        except prama.ValidationError as error:
            say(f"  REFUSED   {path.name}")
            say(f"            {error.message}")
            continue
        say(f"  ! {path.name} was accepted for review ({upload['state']}); it should not have been")
    say()
    say("  live_fx.py was refused from its source. It was never imported, so its")
    say("  top-level urlopen() never ran: a gate that had to run the thing it was")
    say("  gating would already have let it out.")
    say()
    say("  The server needs no configuration for this: an approved upload is written")
    say("  to its delegates.upload_dir (default data/delegates) when a run starts, and")
    say("  runs only in the sandbox, which re-hashes the file before importing it.")


def _declare(harness: Harness) -> None:
    say()
    say("  The controls, as written, checked and explained by the server:")
    written = [
        ("delegate:settlement_cycle", SETTLEMENT),
        ("naive:settles_after_trading", NAIVE),
        ("delegate:benford_payments", BENFORD.format(dataset="payments_ledger")),
        ("delegate:benford_receipts", BENFORD.format(dataset="receipts_ledger")),
    ]
    for identity, pql in written:
        checked = harness.sdk.pql.check(pql)
        errors = [f for f in checked.get("findings") or [] if f.get("level") == "error"]
        if checked.get("syntax_error") or errors:
            say(f"    ! {identity} does not check: {checked.get('syntax_error') or errors}")
            sys.exit(1)
        for explained in harness.sdk.pql.explain(pql).get("controls") or []:
            say(f"    {explained['sentence']}")
        if identity.startswith("delegate:settlement"):
            (plan,) = harness.sdk.pql.compile(pql, dialect="duckdb").get("plans") or [{}]
            say(f"      the engine's part: {' '.join(str(plan.get('metric_query', '')).split())}")
            say("      (a run narrows it to the columns the delegate declares it reads)")
        control = harness.author(pql, identity=identity, reason="written by the data owner")
        DECLARED[identity] = str(control["id"])


def _payments(harness: Harness, landing: Path) -> None:
    """The payments ledger's check: what an agent in the zone would run, and what the SDK can."""
    stage(
        "4b",
        "The payments ledger, in the PCI zone",
        "The control plane cannot read it, so the server's run did not reach it.",
    )
    say("  The check belongs on an agent inside the zone, configured with its own")
    say("  delegates: section, so the rows never leave and only the finding does.")
    say("  That agent is not something the SDK drives: Prama's data-plane agent")
    say("  protocol (prama.agent) has no HTTP endpoint, so this study, a client of")
    say("  the server, cannot enrol one or hand it the control. Its evidence would")
    say("  be the agent's, and none is claimed below.")
    say()
    say("  What the SDK can do is try the approved delegate on rows, in the server's")
    say("  sandbox, exactly as a control would measure them. A try-out records no")
    say("  evidence, and it sends the rows to the control plane: acceptable for a")
    say("  study's synthetic payments, and the very thing a real PCI zone forbids.")
    with (landing / "payments.csv").open(newline="", encoding="utf-8") as handle:
        rows = [
            {"payment_id": r["payment_id"], "amount": float(r["amount"])}
            for r in csv.DictReader(handle)
        ]
    tried = harness.sdk.delegates.test("acme.benford_first_digit@1", rows, min_rows=300)
    metrics = tried.get("metrics") or {}
    say()
    say(f"  try-out over {len(rows):,} payments")
    say(
        f"    verdict   {str(tried.get('verdict', '?')).upper()}  "
        f"({int(metrics.get('violating_rows', 0))} finding(s))"
    )
    say(
        f"    MAD {metrics.get('mad', 0):.4f}   χ² {metrics.get('chi_square', 0):.1f}   "
        f"share of 4s {metrics.get('share_digit_4', 0):.1%} (Benford: 9.7%)"
    )
    if tried.get("note"):
        say(f"    {tried['note']}")
    delegate = tried.get("delegate") or {}
    say(
        f"    ran {delegate.get('delegate', '?')}, source "
        f"{str(delegate.get('delegate_hash', ''))[:16]}, {delegate.get('delegate_isolation', '')}"
    )
    TRIED["payments"] = tried


#: What the payments try-out returned, for the comparison.
TRIED: dict[str, Any] = {}


def main() -> None:
    args = arguments(__doc__ or "")
    workspace = HERE / "workspace"
    banner(
        "Case study 5 — DQ delegates",
        "Python checks the bank writes, named from PQL, judged by Prama.",
    )
    stage(1, "Build the data", "Trades on three calendars; payments with invented invoices.")
    catalogue, planted, counts = build(workspace)
    for name, count in counts.items():
        say(f"  {name:<10} {count:,} rows")
    say()
    say(planted.render())

    harness = Harness(workspace, title="DQ delegates", args=args)
    harness.start(tenant_slug="acme-ops", tenant_name="Acme Markets — operations")
    reviewer = _reviewer(harness)
    try:
        harness.declare(ESTATE)
        harness.derive_and_accept()
        _admit(harness, reviewer)
        _declare(harness)
        harness.run(
            [
                Source(
                    name="control plane (DuckDB)",
                    source_type="duckdb",
                    path=catalogue,
                    # The payments ledger lives in the PCI zone; the control
                    # plane cannot reach it, and the run says so.
                    datasets={"trade_blotter", "receipts_ledger"},
                )
            ]
        )
        _payments(harness, workspace / "landing")
        harness.report(planted)
        _compare(harness)
        harness.finish()
    finally:
        reviewer.close()
        harness.close()


def _latest(harness: Harness) -> dict[str, dict[str, Any]]:
    """The latest evidence record per control id."""
    latest = harness.sdk.evidence.latest()
    if isinstance(latest, dict):
        records = next(
            (latest[k] for k in ("records", "items", "latest") if isinstance(latest.get(k), list)),
            [v for v in latest.values() if isinstance(v, dict)],
        )
    else:
        records = list(latest or [])
    return {str(r.get("control_id")): r for r in records}


def _compare(harness: Harness) -> None:
    latest = _latest(harness)
    by_identity = {
        identity: latest[control_id]
        for identity, control_id in DECLARED.items()
        if control_id in latest
    }
    say()
    say("─" * 78)
    say("  THE SAME QUESTION, ASKED TWO WAYS")
    say("─" * 78)
    naive = by_identity.get("naive:settles_after_trading")
    cycle = by_identity.get("delegate:settlement_cycle")
    if naive is not None and cycle is not None:
        say(
            f"  settlement_date >= trade_date      {str(naive['verdict']).upper():<5} "
            f"{int((naive.get('metrics') or {}).get('violating_rows', 0))} violation(s)"
        )
        say(
            f"  acme.settlement_cycle              {str(cycle['verdict']).upper():<5} "
            f"{int((cycle.get('metrics') or {}).get('violating_rows', 0))} violation(s)"
        )
        if cycle.get("detail"):
            say(f"    {cycle['detail']}")
    receipts = by_identity.get("delegate:benford_receipts")
    if receipts is not None:
        say(
            f"  benford on receipts (clean)        {str(receipts['verdict']).upper():<5} "
            f"MAD {(receipts.get('metrics') or {}).get('mad', 0):.4f}"
        )
    payments = TRIED.get("payments")
    if payments is not None:
        say(
            f"  benford on payments (try-out)      {str(payments.get('verdict')).upper():<5} "
            f"MAD {(payments.get('metrics') or {}).get('mad', 0):.4f}   no evidence recorded"
        )
    say()
    say("  Every trade planted here settles after it trades, so the column")
    say("  comparison passes all of them. Only a check that knows each market's")
    say("  cycle and calendar sees them, and that check is Python the bank owns.")
    say("  Prama still judges it: the delegate returned counts, the control's")
    say("  threshold decided, and the evidence names the delegate's source hash.")


if __name__ == "__main__":
    main()
