"""The worked example from the specification, as runnable data and controls.

Section 10 of the rule-language spec shows one screen of business declarations
becoming a production control suite. Keeping it here rather than only in prose
means it is executed on every build: the example in the document and the
example that runs cannot drift apart, because they are the same text.

It is also the honest record of what the language does and does not do yet.
The suite below is the part of §10 that compiles today. MONITOR and RECONCILE
are declared in the spec and are not implemented, and this module says so
rather than quietly shipping an example trimmed to what happens to work.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from typing import Any

#: The declarations a business owner makes, in their own words. Every control
#: below traces back to one of these lines, which is what makes the suite
#: reviewable by the person who owns the data rather than only by its author.
DECLARATIONS: tuple[str, ...] = (
    "Daily Positions EOD, owned by the Head of Market Risk Data, Tier 1.",
    "One row per account per instrument per business day.",
    "Arrives by 06:30 on TARGET2 business days.",
    "notional_amount is a CDE for FRTB, denominated in the trade currency.",
    "account_id refers to an account in the accounts master.",
    "One account belongs to exactly one legal entity.",
    "Volume tracks trading days, roughly 3x at month-end.",
)

#: The suite Prama generates from them. Written out rather than generated here,
#: so this file is a fixture and not a second implementation of the generator.
SUITE = """
SUITE positions_eod_core {
  CHECK positions_eod HAS UNIQUE KEY (account_id, instrument_id, as_of_date)
    SEVERITY critical DIMENSION uniqueness
    BECAUSE 'Declared grain: one row per account per instrument per business day'

  CHECK positions_eod.notional_amount IS NOT NULL
    SEVERITY critical DIMENSION completeness
    BECAUSE 'CDE for the FRTB return'

  CHECK positions_eod.currency IN CODELIST iso4217
    SEVERITY major DIMENSION validity
    BECAUSE 'notional_amount is declared as denominated in currency'

  CHECK positions_eod.account_id REFERENCES accounts.account_id
    SEVERITY major DIMENSION consistency
    BECAUSE 'Relationship R-4471: positions_eod REFERENCES accounts'

  CHECK positions_eod SATISFIES account_id DETERMINES legal_entity_id
    SEVERITY major DIMENSION consistency
    BECAUSE 'Relationship R-4472: one account belongs to one legal entity'

  CHECK positions_eod HAS ROW COUNT BETWEEN 1 AND 2000000
    WHERE trade_status = 'ACTIVE'
    SEVERITY minor DIMENSION completeness
    BECAUSE 'Declared volume driver: trading days, 3x at month-end'

  CHECK positions_eod.notional_amount BETWEEN -1000000000 AND 1000000000
    SEVERITY major DIMENSION accuracy
    BECAUSE 'A notional outside this range is a units error, not a trade'
}
"""

#: What §10 declares and the language cannot yet express. Listed so that a
#: reader of the example is never left to infer the gap from its absence.
NOT_YET_IMPLEMENTED: tuple[tuple[str, str], ...] = (
    (
        "MONITOR row_count ON positions_eod SEASONALITY daily, weekly, month_end",
        "calibrated monitors need the baseline and false-alarm budgeting of Wave 6",
    ),
    (
        "RECONCILE positions_eod AGAINST general_ledger ON (account_code, cost_centre)",
        "reconciliation needs cross-dataset joins, currency normalisation and "
        "break classification, none of which the IR carries yet",
    ),
    (
        "CHECK positions_eod DERIVES FROM murex_trades PRESERVING SUM(notional_amount)",
        "a preservation check compares an aggregate across two datasets, which is "
        "the same missing machinery as reconciliation",
    ),
)

COLUMNS: tuple[tuple[str, str], ...] = (
    ("account_id", "VARCHAR(20)"),
    ("instrument_id", "VARCHAR(20)"),
    ("as_of_date", "VARCHAR(10)"),
    ("legal_entity_id", "VARCHAR(20)"),
    ("currency", "VARCHAR(3)"),
    ("notional_amount", "DOUBLE PRECISION"),
    ("trade_status", "VARCHAR(10)"),
)

#: A day's positions with four planted faults, one per failing control, so the
#: example demonstrates detection rather than merely completing.
POSITIONS: tuple[tuple[Any, ...], ...] = (
    ("A1", "I1", "2026-04-02", "LE1", "GBP", 1000.00, "ACTIVE"),
    ("A1", "I2", "2026-04-02", "LE1", "USD", 2500.00, "ACTIVE"),
    ("A2", "I1", "2026-04-02", "LE2", "EUR", 3300.75, "ACTIVE"),
    # The declared grain says one row per account per instrument per day.
    ("A2", "I1", "2026-04-02", "LE2", "EUR", 3300.75, "ACTIVE"),
    # A CDE with no value.
    ("A3", "I1", "2026-04-02", "LE1", "GBP", None, "ACTIVE"),
    # A currency that is not in ISO 4217.
    ("A3", "I2", "2026-04-02", "LE1", "XYZ", 120.00, "ACTIVE"),
    # An account the master does not know.
    ("A9", "I1", "2026-04-02", "LE3", "JPY", 50000.00, "ACTIVE"),
    # The same account under a second legal entity.
    ("A1", "I3", "2026-04-02", "LE9", "GBP", 10.00, "CANCELLED"),
)

ACCOUNTS: tuple[tuple[str, str], ...] = (
    ("A1", "LE1"),
    ("A2", "LE2"),
    ("A3", "LE1"),
)

#: ISO 4217 codes the example uses. The real codelist is registered data; this
#: is enough to show the control working.
ISO4217: tuple[str, ...] = ("GBP", "USD", "EUR", "JPY", "CHF")


@dataclasses.dataclass(frozen=True, slots=True)
class Expectation:
    """What each control should find, and which planted fault it catches."""

    control: str
    verdict: str
    catches: str


EXPECTED: tuple[Expectation, ...] = (
    Expectation("unique key", "fail", "the duplicate A2/I1 row breaks the declared grain"),
    Expectation("notional not null", "fail", "A3/I1 has no notional, and it is a CDE"),
    Expectation("currency codelist", "fail", "XYZ is not an ISO 4217 code"),
    Expectation("account reference", "fail", "A9 is not in the accounts master"),
    Expectation("account determines entity", "fail", "A1 appears under LE1 and LE9"),
    Expectation("row count", "pass", "the volume is within the declared band"),
    Expectation(
        "notional range",
        "fail",
        "the missing notional again — an unknown violates a range check too, so "
        "one row fires two controls and the linter flags the pair as subsumed",
    ),
)


def create_positions(*, dialect: str = "postgresql") -> str:
    from prama.backend.dialect import dialect as resolve

    double = resolve(dialect).double_type
    columns = ", ".join(
        f'"{name}" {double if "DOUBLE" in kind else kind}' for name, kind in COLUMNS
    )
    return f'CREATE TABLE "positions_eod" ({columns})'


def create_accounts() -> str:
    return 'CREATE TABLE "accounts" ("account_id" VARCHAR(20), "legal_entity_id" VARCHAR(20))'


def insert_positions(*, placeholder: str = "?") -> str:
    marks = ", ".join(
        placeholder if placeholder != "$" else f"${i + 1}" for i in range(len(COLUMNS))
    )
    names = ", ".join(f'"{name}"' for name, _ in COLUMNS)
    return f'INSERT INTO "positions_eod" ({names}) VALUES ({marks})'


def insert_accounts(*, placeholder: str = "?") -> str:
    marks = "?, ?" if placeholder != "$" else "$1, $2"
    return f'INSERT INTO "accounts" ("account_id", "legal_entity_id") VALUES ({marks})'
