#!/usr/bin/env python3
"""Case study 7 — governance from metadata: rules nobody wrote by hand.

Three datasets are declared with no quality rules at all: names and
descriptions only. Their owners then do what owners do in a catalogue. They
write the business context, fill in metadata fields (mandatory, allowed values,
minimum, key), and bind two columns to the glossary term *LEI*. Every control
that then runs came from that metadata, or from Prama noticing that two
columns mean the same thing. Finally, a question in plain words finds the
dataset fit for a purpose.

It all happens in **your** Prama, through the SDK: the metadata is set, the
glossary term imported and bound, the proposals accepted and the controls run
by the server the configuration names. It starts no server of its own.

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
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from _common.defects import DefectLog  # noqa: E402
from _common.estate import Attribute, Dataset  # noqa: E402
from _common.harness import Harness, Source, arguments, banner, say, stage  # noqa: E402

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

#: The bank's catalogue already defines *LEI*: its Alation export is where the
#: term comes from, and the owners bind their columns to it.
CATALOGUE = {
    "results": [
        {
            "id": 1742,
            "title": "LEI",
            "description": "ISO 17442 Legal Entity Identifier",
            "custom_fields": [{"field_name": "synonyms", "value": "Legal Entity Identifier"}],
        }
    ]
}
LEI_COLUMNS = ("customers.lei", "accounts.customer_lei")


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


def _govern(harness: Harness) -> None:
    sdk = harness.sdk
    stage(
        4,
        "The owners describe their data",
        "Business context, metadata fields, a glossary term. No PQL is written.",
    )
    sdk.metadata.install_starter("data-quality-attribute")
    sdk.metadata.install_starter("data-quality-dataset")
    for slug, text in CONTEXT.items():
        sdk.metadata.set_context(slug, text)
        say(f"  {slug}: {text[:84]}…")
    for target, values in METADATA.items():
        sdk.metadata.set(target, **values)
        say(f"  {target:<24} " + ", ".join(f"{k}={v}" for k, v in values.items()))
    imported = sdk.glossary.import_export("alation", CATALOGUE)
    for dropped in imported.get("dropped", []):
        say(f"  ! the catalogue import dropped {dropped['source']}: {dropped['reason']}")
    for column in LEI_COLUMNS:
        sdk.glossary.bind("LEI", "attribute", column)
    term = sdk.glossary.get("LEI")
    bound = sorted(b["ref"] for b in term["bound"] if b["kind"] == "attribute")
    say(f"  glossary: LEI ({term['definition']}), imported from the catalogue")
    say(f"            bound to {' and '.join(bound)}")

    stage(5, "What the metadata implies", "Proposed, then accepted by a reviewer.")
    implied = sdk.metadata.proposals()
    correlated = sdk.metadata.correlation()
    for item in [*implied, *correlated["proposals"]]:
        if item.get("error"):
            # A rule the metadata implies but that does not parse: shown, never run.
            say(f"  ! {item['pql']}   (not a control: {item['error']})")
            continue
        say(f"  + {item['pql'].split(' BECAUSE')[0]}   ({item['rule']})")
        # A reviewer accepts it on the proposal queue: it is declared and activated.
        sdk.proposals.accept(
            item["identity"],
            item["pql"],
            rule=item["rule"],
            dataset_id=item.get("dataset_id") or None,
            reason="accepted for the study",
        )
        harness.accepted += 1
    for finding in correlated["findings"]:
        say(f"  ! held inconsistently ({finding['aspect']}): {finding['detail']}")
    # Read the queue back rather than assume it emptied. A proposal still listed
    # after it was accepted is one a reviewer would be asked to decide twice.
    active = {c["identity"] for c in sdk.controls.list(status="active")}
    waiting = sdk.metadata.proposals()
    stale = [item for item in waiting if item.get("identity") in active]
    queue = sdk.proposals.list()["proposals"]
    queued = [item for item in queue if item.get("identity") in active]
    say()
    say(
        f"  {harness.accepted} accepted and active; the metadata queue still lists "
        f"{len(waiting)}, of which {len(stale)} are already active controls."
    )
    say(
        f"  The proposal queue lists {len(queue)}, of which {len(queued)} are already "
        "active controls."
    )
    # The rest is what the declarations themselves imply (Γ). This study runs
    # only what the metadata implies, so they are left for a reviewer, and shown.
    for item in queue:
        if item.get("identity") not in active:
            say(f"    waiting  {item['pql'].splitlines()[0]}   ({item['rule']})")
    if stale or queued:
        say("  ! The queue re-offers accepted proposals: it compares a hash of the proposed")
        say("    text with the stored control's hash of its rendered form, and they never match.")


def _find(harness: Harness) -> None:
    stage(7, "Which dataset is fit for a purpose?", "A question in plain words, over the metadata.")
    for question in (
        "who is the customer and where are they registered, for sanctions screening",
        "outgoing payment amounts",
    ):
        answer = harness.sdk.metadata.ask(question)
        best = answer["matches"][0] if answer["matches"] else None
        say(f"  “{question}”")
        if best:
            say(
                f"    → {best['name']} (ranked by {answer['ranked_by']}; "
                f"matching {', '.join(best['evidence']) or '-'})"
            )
        else:
            say("    → nothing in the estate answers it")


def main() -> None:
    args = arguments(__doc__ or "")
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
    harness = Harness(workspace, title="Governance from metadata", args=args)
    harness.start(tenant_slug="acme-retail", tenant_name="Acme Bank — retail")
    try:
        harness.declare(ESTATE)
        _govern(harness)
        harness.run(
            [
                Source(
                    name="warehouse (SQLite)",
                    source_type="sqlite",
                    path=warehouse,
                    datasets={"customers", "accounts", "payments"},
                ),
            ]
        )
        harness.report(planted)
        _find(harness)
        harness.finish()
    finally:
        harness.close()


if __name__ == "__main__":
    main()
