#!/usr/bin/env python3
"""Case study 5 — DQ delegates: Python checks the bank writes, under Prama's rules.

Two checks PQL cannot say, written as delegates by Acme's own engineers, named
from PQL, and run in two places:

  * **acme.settlement_cycle**, on the control plane. Every trade settles its
    market's cycle of *business days* after trading: US T+1 since May 2024,
    EU T+2, each on its own holiday calendar.
  * **acme.benford_first_digit**, on a remote agent in the payments zone,
    configured with its own `delegates:` section. The payment rows never leave
    the zone; the finding does.

And one delegate that must be refused, because it fetches FX rates from the
internet: it is refused from its source, before it is imported.

Usage:
    python run.py                 build, run, and serve the console on :8805
    python run.py --no-serve      build and run, then stop

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary; see LICENSE.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import random
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
from _common.harness import Harness, Source, banner, say, stage  # noqa: E402

from prama.connect.sources.query import executor_for  # noqa: E402
from prama.delegates.host import host_from_config  # noqa: E402

DELEGATES = HERE / "acme_delegates"
#: Control ids by the identity they were declared under, for the comparison.
DECLARED: dict[str, str] = {}
REJECTED = HERE / "rejected"

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


def _admit() -> Any:
    """The control plane's delegates, from its own configuration."""
    stage(
        2,
        "Admit the delegates",
        "Scanned before import, run twice on probe rows, and hashed.",
    )
    say("  delegates:                      # the control plane's application.yaml")
    say(f"    paths: [{DELEGATES.name}, {REJECTED.name}]")
    say("    sandbox: true")
    host = host_from_config(
        {"delegates": {"paths": [str(DELEGATES), str(REJECTED)], "entry_points": False}}
    )
    say()
    for admitted in host.registry.all():
        say(f"  admitted  {admitted.name}@{admitted.version}  counts {admitted.delegate.unit}")
        say(f"            reads {', '.join(admitted.delegate.requires)}")
        say(f"            source {admitted.implementation_hash}")
    for name, why in sorted(host.registry.refused.items()):
        say(f"  REFUSED   {name}")
        say(f"            {why}")
    say()
    say("  live_fx.py was refused from its source. It was never imported, so its")
    say("  top-level urlopen() never ran: a gate that had to run the thing it was")
    say("  gating would already have let it out.")
    return host


async def _declare(harness: Harness) -> None:
    from prama.backend import compile_for
    from prama.ir.resolve import resolved
    from prama.pql import parse_control

    say()
    say("  The controls, as written:")
    written = [
        ("delegate:settlement_cycle", SETTLEMENT),
        ("naive:settles_after_trading", NAIVE),
        ("delegate:benford_payments", BENFORD.format(dataset="payments_ledger")),
        ("delegate:benford_receipts", BENFORD.format(dataset="receipts_ledger")),
    ]
    async with harness.database.unit_of_work() as uow:
        for identity, pql in written:
            control = parse_control(pql)
            say(f"    {control.describe()}")
            if identity.startswith("delegate:settlement"):
                query = compile_for(
                    resolved(control),
                    "duckdb",
                    table="trade_blotter",
                    columns=("trade_id", "market", "trade_date", "settlement_date"),
                ).metric_query
                say(f"      the engine's part: {' '.join(query.split())}")
            entity, _ = await uow.controls.declare(
                tenant_id=harness.tenant_id,
                identity=identity,
                pql=pql,
                rule="authored.delegate" if identity.startswith("delegate") else "authored.excel",
                criticality=1,
                schedule="06:30",
                authored_by="alice",
            )
            await uow.controls.activate(
                str(entity.id), tenant_id=harness.tenant_id, approved_by="bob"
            )
            DECLARED[identity] = str(entity.id)
            harness.accepted += 1


def _remote_agent(catalogue: Path) -> None:
    """The payments ledger's check, run by an agent inside the payments zone."""
    from prama.agent import Agent, AgentCapabilities, Assignment, ResidencyPolicy, fits
    from prama.agent.residency import SampleDisposition
    from prama.ir.resolve import resolved
    from prama.pql import parse_control

    stage(
        "4b",
        "Run the payments check on a remote agent",
        "Configured with its own delegates: section; rows stay in the zone.",
    )
    plan = resolved(parse_control(BENFORD.format(dataset="payments_ledger")))
    bare = AgentCapabilities(engines=("duckdb",))
    verdict = fits(plan, bare, engine="duckdb")
    say("  an agent in eu-frankfurt, with no delegates configured:")
    say(f"    {verdict.render()}")
    say(f"    → {verdict.remedy}")
    say()

    say("  the agent in pci-zone, whose own application.yaml says:")
    say("    delegates:")
    say(f"      paths: [/opt/acme/{DELEGATES.name}]")
    say("      sandbox: true")
    host = host_from_config({"delegates": {"paths": [str(DELEGATES)], "entry_points": False}})
    execute, close = executor_for(catalogue, "duckdb")
    try:
        agent = Agent(
            "agent-pci-01",
            b"k" * 32,
            executor=lambda sql: list(execute(sql)),
            residency=ResidencyPolicy(
                zone="pci-zone",
                samples=SampleDisposition.WITHHOLD,
                investigate_at="the AP investigations workstation in pci-zone",
            ),
            capabilities=bare,
            delegates=host,
        )
        hello, _ = agent.hello()
        say(f"    advertises: {', '.join(hello.capabilities.delegates)}")
        say(f"    fits: {fits(plan, hello.capabilities, engine='duckdb').render()}")
        outcome = agent.run(Assignment.for_plan(plan, "duckdb", control_id="benford_payments"))
    finally:
        close()
    record = outcome.record
    assert record is not None
    metrics = record.metrics
    say()
    findings = int(metrics.get("violating_rows", 0))
    say(f"    verdict   {record.verdict.upper()}  ({findings} finding(s))")
    say(
        f"    MAD {metrics.get('mad', 0):.4f}   χ² {metrics.get('chi_square', 0):.1f}   "
        f"share of 4s {metrics.get('share_digit_4', 0):.1%} (Benford: 9.7%)"
    )
    say(f"    {record.detail}")
    say(
        f"    ran {record.parameters['delegate']}, source {record.parameters['delegate_hash'][:16]}"
    )
    say(
        f"    {record.sample_count} example payments kept in the zone; "
        f"{'none' if not record.samples_digest else 'masked copies'} sent to the control plane"
    )


async def main(serve: bool) -> Any:
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

    host = _admit()

    harness = Harness(workspace, title="DQ delegates")
    await harness.start(tenant_slug="acme-ops", tenant_name="Acme Markets — operations")
    try:
        await harness.declare(ESTATE)
        await harness.derive_and_accept()
        await _declare(harness)
        execute, close = executor_for(catalogue, "duckdb")
        try:
            await harness.run(
                [
                    Source(
                        name="control plane (DuckDB)",
                        engine="duckdb",
                        execute=execute,
                        close=close,
                        # The payments ledger lives in the PCI zone; the
                        # control plane cannot reach it, and says so.
                        datasets={"trade_blotter", "receipts_ledger"},
                        delegates=host,
                    )
                ]
            )
        finally:
            close()
        _remote_agent(catalogue)
        await harness.report(planted)
        await _compare(harness)
    finally:
        await harness.stop()
    return harness if serve else None


async def _compare(harness: Harness) -> None:
    async with harness.database.unit_of_work() as uow:
        latest = await uow.evidence.latest_per_control(harness.tenant_id)
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
            f"  settlement_date >= trade_date      {naive.verdict.upper():<5} "
            f"{int(naive.metrics.get('violating_rows', 0))} violation(s)"
        )
        say(
            f"  acme.settlement_cycle              {cycle.verdict.upper():<5} "
            f"{int(cycle.metrics.get('violating_rows', 0))} violation(s)"
        )
        say(f"    {cycle.detail}")
    receipts = by_identity.get("delegate:benford_receipts")
    if receipts is not None:
        say(
            f"  benford on receipts (clean)        {receipts.verdict.upper():<5} "
            f"MAD {receipts.metrics.get('mad', 0):.4f}"
        )
    say()
    say("  Every trade planted here settles after it trades, so the column")
    say("  comparison passes all of them. Only a check that knows each market's")
    say("  cycle and calendar sees them, and that check is Python the bank owns.")
    say("  Prama still judges it: the delegate returned counts, the control's")
    say("  threshold decided, and the evidence names the delegate's source hash.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-serve", action="store_true")
    parser.add_argument("--port", type=int, default=8805)
    args = parser.parse_args()
    started = asyncio.run(main(serve=not args.no_serve))
    if started is not None:
        started.serve(port=args.port)
