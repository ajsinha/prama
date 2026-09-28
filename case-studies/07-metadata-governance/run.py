#!/usr/bin/env python3
"""Case study 7 — governance from metadata: rules nobody wrote by hand.

Three datasets are declared with no quality rules at all: names and
descriptions only. Their owners then do what owners do in a catalogue. They
write the business context, fill in metadata fields (mandatory, allowed values,
minimum, key), and bind two columns to the glossary term *LEI*. Every control
that then runs came from that metadata, or from Prama noticing that two
columns mean the same thing. Finally, a question in plain words finds the
dataset fit for a purpose.

Usage:
    python run.py                 build, run, and serve the console on :8807
    python run.py --no-serve      build and run, then stop

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary; see LICENSE.
"""

from __future__ import annotations

import argparse
import asyncio
import sqlite3
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from _common.defects import DefectLog  # noqa: E402
from _common.estate import Attribute, Dataset  # noqa: E402
from _common.harness import Harness, Source, banner, say, stage, use_config  # noqa: E402

from prama.connect.sources.query import executor_for  # noqa: E402

LEIS = [f"5493000{n:03d}ABCDEF{n % 97:02d}" for n in range(1, 41)]

#: Declared with meaning only: not one quality rule among them.
ESTATE = [
    Dataset(
        name="Customers",
        description="The bank's customers, one row each.",
        grain_statement="one row per customer",
        grain=("customer_id",),
        criticality=3,
        attributes=(
            Attribute("customer_id", "The customer's identifier."),
            Attribute("lei", "The customer's Legal Entity Identifier."),
            Attribute("legal_name", "Registered name."),
            Attribute("country", "Country of registration."),
            Attribute("segment", "Commercial segment."),
        ),
    ),
    Dataset(
        name="Accounts",
        description="Accounts the customers hold.",
        grain_statement="one row per account",
        grain=("account_id",),
        criticality=3,
        attributes=(
            Attribute("account_id", "The account's identifier."),
            Attribute("customer_lei", "Whose account it is."),
            Attribute("currency", "Account currency."),
        ),
    ),
    Dataset(
        name="Payments",
        description="Payments out of those accounts.",
        grain_statement="one row per payment",
        grain=("payment_id",),
        criticality=3,
        attributes=(
            Attribute("payment_id", "The payment's identifier."),
            Attribute("account_id", "The paying account."),
            Attribute("amount", "Amount paid."),
        ),
    ),
]

#: What the owners write, and what the metadata says. This is the whole of the
#: governance input: no PQL is written by hand in this study.
CONTEXT = {
    "customers": "Every legal entity we bank: who they are, where they are registered and "
    "which segment serves them. Used for onboarding, sanctions screening and KYC refresh.",
    "accounts": "The accounts our customers hold, keyed to the customer by LEI.",
    "payments": "Outgoing payments; the direction is never in the sign of the amount.",
}
METADATA = {
    "customers.segment": {"allowed_values": "RETAIL, SME, CORPORATE", "mandatory": "yes"},
    "customers.lei": {"mandatory": "yes", "unique": "yes", "pii": "no"},
    "accounts.customer_lei": {"mandatory": "yes", "pii": "yes"},
    "payments.amount": {"minimum": "0", "mandatory": "yes"},
    "customers": {"key": "customer_id", "source_system": "CRM"},
    "accounts": {"key": "account_id", "source_system": "Core banking"},
}


def build(workspace: Path) -> tuple[Path, DefectLog, dict[str, int]]:
    workspace.mkdir(parents=True, exist_ok=True)
    warehouse = workspace / "warehouse.db"
    warehouse.unlink(missing_ok=True)
    segments = ("RETAIL", "SME", "CORPORATE")
    customers = [
        (f"C{i:04d}", LEIS[i], f"Entity {i}", ("GB", "DE", "FR", "US")[i % 4], segments[i % 3])
        for i in range(40)
    ]
    accounts = [(f"A{i:05d}", LEIS[i % 40], ("EUR", "USD", "GBP")[i % 3]) for i in range(200)]
    payments = [
        (f"P{i:06d}", f"A{i % 200:05d}", round(100 + (i * 37) % 9000 + 0.5, 2)) for i in range(1200)
    ]
    log = DefectLog()
    for i in range(3, 9):
        customers[i] = (*customers[i][:4], "SME ")  # a trailing space from a spreadsheet
    log.add(
        key="segment_not_allowed",
        dataset="customers",
        what="segment 'SME ' with a trailing space: not one of the allowed values",
        rows=6,
        dimension="validity",
    )
    for i in range(10, 14):
        accounts[i] = (accounts[i][0], None, accounts[i][2])
    log.add(
        key="account_without_owner",
        dataset="accounts",
        what="account with no customer LEI",
        rows=4,
        dimension="completeness",
    )
    for i in range(100, 103):
        accounts[i] = (accounts[i][0], "549300ZZZORPHAN00001", accounts[i][2])
    log.add(
        key="orphan_customer_lei",
        dataset="accounts",
        what="account owned by an LEI no customer has",
        rows=3,
        dimension="integrity",
    )
    for i in range(500, 505):
        payments[i] = (payments[i][0], payments[i][1], -payments[i][2])
    log.add(
        key="negative_payment",
        dataset="payments",
        what="payment amount negative, the direction written into the sign",
        rows=5,
        dimension="validity",
    )
    connection = sqlite3.connect(warehouse)
    connection.executescript(
        "CREATE TABLE customers (customer_id TEXT, lei TEXT, legal_name TEXT, country TEXT, "
        "segment TEXT);"
        "CREATE TABLE accounts (account_id TEXT, customer_lei TEXT, currency TEXT);"
        "CREATE TABLE payments (payment_id TEXT, account_id TEXT, amount REAL);"
    )
    connection.executemany("INSERT INTO customers VALUES (?, ?, ?, ?, ?)", customers)
    connection.executemany("INSERT INTO accounts VALUES (?, ?, ?)", accounts)
    connection.executemany("INSERT INTO payments VALUES (?, ?, ?)", payments)
    connection.commit()
    connection.close()
    return warehouse, log, {"customers": 40, "accounts": 200, "payments": 1200}


async def _govern(harness: Harness) -> None:
    from prama.semantic.services import metadata

    stage(
        4,
        "The owners describe their data",
        "Business context, metadata fields, a glossary term. No PQL is written.",
    )
    async with harness.database.unit_of_work() as uow:
        tenant = harness.tenant_id
        await metadata.install_starter(uow, tenant, "data-quality-attribute")
        await metadata.install_starter(uow, tenant, "data-quality-dataset")
        for slug, text in CONTEXT.items():
            await metadata.set_context(uow, tenant, slug, text, by="alice")
            say(f"  {slug}: {text[:84]}…")
        for target, values in METADATA.items():
            await metadata.set_values(uow, tenant, target, values, by="alice")
            say(f"  {target:<24} " + ", ".join(f"{k}={v}" for k, v in values.items()))
        await uow.glossary.upsert(
            tenant, name="LEI", definition="ISO 17442 Legal Entity Identifier"
        )
        await uow.glossary.bind(tenant, "LEI", "attribute", "customers.lei")
        await uow.glossary.bind(tenant, "LEI", "attribute", "accounts.customer_lei")
        say("  glossary: customers.lei and accounts.customer_lei are both the term LEI")

        stage(5, "What the metadata implies", "Proposed, then accepted by a reviewer.")
        implied = await metadata.proposals(uow, tenant)
        correlated = await metadata.correlation(uow, tenant)
        for item in [*implied, *correlated["proposals"]]:
            say(f"  + {item['pql'].split(' BECAUSE')[0]}   ({item['rule']})")
            entity, _ = await uow.controls.declare(
                tenant_id=tenant,
                identity=item["identity"],
                pql=item["pql"],
                rule=item["rule"],
                status="proposed",
                authored_by="gamma",
                criticality=2,
            )
            await uow.controls.activate(str(entity.id), tenant_id=tenant, approved_by="bob")
            harness.accepted += 1
        for finding in correlated["findings"]:
            say(f"  ! held inconsistently ({finding['aspect']}): {finding['detail']}")


async def _find(harness: Harness) -> None:
    from prama.semantic.services.fitness import rank

    stage(7, "Which dataset is fit for a purpose?", "A question in plain words, over the metadata.")
    async with harness.database.unit_of_work() as uow:
        for question in (
            "who is the customer and where are they registered, for sanctions screening",
            "outgoing payment amounts",
        ):
            answer = await rank(uow, harness.tenant_id, question, config=harness.config)
            best = answer["matches"][0] if answer["matches"] else None
            say(f"  “{question}”")
            if best:
                say(
                    f"    → {best['name']} (ranked by {answer['ranked_by']}; "
                    f"matching {', '.join(best['evidence']) or '-'})"
                )


async def main(serve: bool) -> Any:
    workspace = HERE / "workspace"
    banner(
        "Case study 7 — governance from metadata",
        "No rule written by hand: every check comes from what the owners said.",
    )
    stage(1, "Build the warehouse", "Customers, accounts and payments, with four planted defects.")
    warehouse, planted, counts = build(workspace)
    for name, count in counts.items():
        say(f"  {name:<12} {count:>6,} rows")
    say()
    say(planted.render())
    harness = Harness(workspace, title="Governance from metadata")
    await harness.start(tenant_slug="acme-retail", tenant_name="Acme Bank — retail")
    try:
        await harness.declare(ESTATE)
        await _govern(harness)
        execute, close = executor_for(warehouse, "sqlite")
        try:
            await harness.run(
                [
                    Source(
                        name="warehouse (SQLite)",
                        engine="sqlite",
                        execute=execute,
                        close=close,
                        datasets={"customers", "accounts", "payments"},
                    ),
                ]
            )
        finally:
            close()
        await harness.report(planted)
        await _find(harness)
    finally:
        await harness.stop()
    return harness if serve else None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-serve", action="store_true")
    parser.add_argument(
        "--config", default="", help="a Prama configuration file; defaults to the application's"
    )
    parser.add_argument("--port", type=int, default=8807)
    args = parser.parse_args()
    use_config(args.config)
    started = asyncio.run(main(serve=not args.no_serve))
    if started is not None:
        started.serve(port=args.port)
