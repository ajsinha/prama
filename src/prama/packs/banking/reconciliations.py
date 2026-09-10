"""Reference reconciliations, as templates a bank points at its own datasets.

docs/12 §6 lists eleven reconciliations every bank runs. They are the same
eleven at every bank, and every bank builds them again — because the *shape* is
standard and the column names never are.

So each entry here is a definition with its keys, its tolerance and its expected
break taxonomy, and an estate instantiates it by naming its datasets. What the
template supplies is the part that is genuinely hard and genuinely portable:

* **The keys, and why those keys.** A cash-book reconciliation keyed on amount
  and date matches the wrong pairs whenever two payments share a value; keyed on
  reference it does not. The key is the design decision and it is stated.
* **The tolerance, and whose convention it follows.** Zero for a count, and for
  a value the materiality the business already uses. A tolerance invented by an
  engineer is one operations will override on the first day.
* **The breaks to expect.** A reconciliation whose breaks are all "genuine" has
  not been classified, and a queue of unexplained differences is one nobody
  works. Naming the expected taxonomy up front is what lets the classifier route
  them.

**A template with no tolerance stated is not the same as a template with zero.**
Zero means the two sides must agree exactly and is right for a count; absent
means nobody has decided, and a reconciliation run on an undecided tolerance
reports either everything or nothing.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from prama.core.errors import ValidationError
from prama.recon.classify import BreakKind
from prama.recon.engine import Definition, Side
from prama.recon.match import MatchKey
from prama.recon.normalise import AmountSpec
from prama.semantic.relationships import Tolerance


@dataclasses.dataclass(frozen=True, slots=True)
class ReconciliationTemplate:
    """One standard reconciliation, before it is pointed at any data."""

    identity: str
    label: str
    #: What the two sides are, in business terms.
    left_role: str
    right_role: str
    #: Attribute roles that identify a pair, in order. Named rather than
    #: column-named: the roles are the same everywhere, the columns never are.
    key_roles: tuple[str, ...]
    #: The role holding the value being compared.
    amount_role: str
    why_these_keys: str
    tolerance: Tolerance
    tolerance_rationale: str
    #: What a well-classified queue looks like. A reconciliation whose breaks
    #: are all "genuine" has not been classified.
    expected_breaks: tuple[BreakKind, ...] = ()
    #: Days either side a timing difference may legitimately span. Zero means
    #: same-day only, which is right for a general ledger and wrong for a
    #: custodian.
    date_window: int = 0
    note: str = ""

    def bind(
        self,
        *,
        left_dataset: str,
        right_dataset: str,
        left_columns: dict[str, str],
        right_columns: dict[str, str],
        left_currency_column: str = "",
        right_currency_column: str = "",
        target_currency: str = "",
    ) -> Definition:
        """A runnable definition, once both sides have been named.

        Refuses on a missing role rather than binding a column called
        ``{amount}``: a reconciliation with a mis-bound key matches nothing and
        reports every row on both sides as unmatched, which reads as a total
        outage rather than as a configuration error.
        """
        needed = (*self.key_roles, self.amount_role)
        for side, columns in (("left", left_columns), ("right", right_columns)):
            missing = [role for role in needed if role not in columns]
            if missing:
                raise ValidationError(
                    f"{self.identity}: the {side} side does not bind {', '.join(missing)}",
                    remedy=(
                        "Map every key role and the amount role to a column. A "
                        "reconciliation with an unbound key matches nothing and "
                        "reports every row on both sides as unmatched, which "
                        "reads as an outage rather than as a mapping error."
                    ),
                    context={"template": self.identity, "side": side, "missing": missing},
                )

        return Definition(
            name=f"{self.identity}: {left_dataset} against {right_dataset}",
            left=Side(
                name=left_dataset,
                amount_column=left_columns[self.amount_role],
                spec=AmountSpec(currency_column=left_currency_column),
            ),
            right=Side(
                name=right_dataset,
                amount_column=right_columns[self.amount_role],
                spec=AmountSpec(currency_column=right_currency_column),
            ),
            key=MatchKey(
                left=tuple(left_columns[role] for role in self.key_roles),
                right=tuple(right_columns[role] for role in self.key_roles),
            ),
            tolerance=self.tolerance,
            target_currency=target_currency,
            date_window=self.date_window,
        )

    def describe(self) -> str:
        kinds = ", ".join(kind.value for kind in self.expected_breaks)
        return (
            f"{self.label}: {self.left_role} against {self.right_role}, keyed on "
            f"{', '.join(self.key_roles)}. {self.tolerance_rationale} "
            f"Expect: {kinds or 'no taxonomy stated'}."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "label": self.label,
            "left_role": self.left_role,
            "right_role": self.right_role,
            "key_roles": list(self.key_roles),
            "amount_role": self.amount_role,
            "why_these_keys": self.why_these_keys,
            "tolerance_rationale": self.tolerance_rationale,
            "expected_breaks": [kind.value for kind in self.expected_breaks],
            "date_window": self.date_window,
            "message": self.describe(),
        }


_EXACT = Tolerance(absolute=0.0)


def _materiality(amount: float, relative: float = 0.0001) -> Tolerance:
    """A penny or a basis point, whichever is larger — operations' own rule.

    Both bounds must be breached for a difference to count, which is the
    convention finance already uses. Encoding it means the generated control
    agrees with the spreadsheet somebody is checking it against.
    """
    return Tolerance(absolute=amount, relative=relative)


TEMPLATES: tuple[ReconciliationTemplate, ...] = (
    ReconciliationTemplate(
        identity="front-office-to-subledger",
        label="Front office to sub-ledger",
        left_role="the trading system's own record",
        right_role="the accounting sub-ledger",
        key_roles=("trade_id", "book", "trade_date"),
        amount_role="notional",
        why_these_keys=(
            "The trade id alone repeats across books after an internal transfer, "
            "and across dates after an amendment. All three together identify the "
            "version of the trade both systems think they are holding."
        ),
        tolerance=_materiality(0.01),
        tolerance_rationale=(
            "Zero on the count and materiality on the value: a missing trade is "
            "never acceptable, a penny of FX rounding usually is."
        ),
        expected_breaks=(
            BreakKind.TIMING,
            BreakKind.FX,
            BreakKind.MISSING,
            BreakKind.GENUINE,
        ),
        date_window=1,
    ),
    ReconciliationTemplate(
        identity="subledger-to-gl",
        label="Sub-ledger to general ledger",
        left_role="the sub-ledger",
        right_role="the general ledger",
        key_roles=("account", "cost_centre", "posting_date"),
        amount_role="balance",
        why_these_keys=(
            "The general ledger holds one line per account and cost centre per "
            "day. Keying on account alone aggregates across cost centres and "
            "nets two errors into an agreement."
        ),
        tolerance=_materiality(0.01),
        tolerance_rationale=(
            "Currency-specific materiality. A yen ledger has no minor unit, so a "
            "tolerance of one hundredth is a tolerance of nothing."
        ),
        expected_breaks=(
            BreakKind.TIMING,
            BreakKind.FX,
            BreakKind.ROUNDING,
            BreakKind.GENUINE,
        ),
    ),
    ReconciliationTemplate(
        identity="position-to-custodian",
        label="Internal position to custodian",
        left_role="the firm's position record",
        right_role="the custodian's statement",
        key_roles=("account", "instrument_id", "as_of_date"),
        amount_role="quantity",
        why_these_keys=(
            "A custodian reports by account and instrument. Adding the date is "
            "what distinguishes a settled difference from a stale file."
        ),
        tolerance=_EXACT,
        tolerance_rationale=(
            "Zero on quantity. A fractional share difference is not rounding; it "
            "is a corporate action nobody applied."
        ),
        expected_breaks=(BreakKind.TIMING, BreakKind.MISSING, BreakKind.GENUINE),
        date_window=2,
        note=(
            "Two days of window, because settlement timing is the commonest "
            "explanation and a same-day comparison reports all of it as genuine."
        ),
    ),
    ReconciliationTemplate(
        identity="cashbook-to-statement",
        label="Cash book to bank statement",
        left_role="the firm's cash book",
        right_role="the bank's statement (camt.053 or MT940)",
        key_roles=("account", "value_date", "reference"),
        amount_role="amount",
        why_these_keys=(
            "The reference is the only field both sides carry unchanged. Keyed on "
            "amount and date instead, two payments of the same value on one day "
            "match each other's counterparts and both look correct."
        ),
        tolerance=_EXACT,
        tolerance_rationale=(
            "Zero. A bank statement is the authority on what moved; a tolerance "
            "here is a decision to ignore the authority."
        ),
        expected_breaks=(BreakKind.TIMING, BreakKind.MISSING, BreakKind.EXTRA),
        date_window=3,
        note=(
            "Three days, for items in transit. Unpresented cheques and in-transit "
            "credits are timing, and classifying them as genuine fills the queue "
            "with differences that clear themselves."
        ),
    ),
    ReconciliationTemplate(
        identity="nostro-vostro",
        label="Nostro to vostro",
        left_role="our record of their account",
        right_role="their record of ours",
        key_roles=("account", "value_date", "reference"),
        amount_role="amount",
        why_these_keys=(
            "Two banks' records of one relationship. The reference travels in the "
            "payment message and is the only thing neither side re-derives."
        ),
        tolerance=_EXACT,
        tolerance_rationale="Zero. Two banks either agree about a movement or do not.",
        expected_breaks=(BreakKind.TIMING, BreakKind.MISSING),
        date_window=2,
    ),
    ReconciliationTemplate(
        identity="repository-to-trade-store",
        label="Trade repository to internal trade store",
        left_role="what the repository acknowledges holding",
        right_role="what we believe we reported",
        key_roles=("uti",),
        amount_role="notional",
        why_these_keys=(
            "The UTI is the identifier the regime exists to make unique. If it "
            "does not identify a pair here, the reporting obligation is already "
            "breached and this reconciliation is how you find out."
        ),
        tolerance=_EXACT,
        tolerance_rationale=(
            "Zero. A reported field either matches what the repository holds or "
            "is a reporting error, and a tolerance would hide the second."
        ),
        expected_breaks=(BreakKind.MISSING, BreakKind.EXTRA, BreakKind.GENUINE),
    ),
    ReconciliationTemplate(
        identity="mt-to-mx",
        label="MT to MX translation fidelity",
        left_role="the MT103 as sent",
        right_role="the pacs.008 it was translated into",
        key_roles=("payment_reference",),
        amount_role="amount",
        why_these_keys=(
            "The end-to-end reference is the only identifier both representations "
            "carry unchanged. Matching on the transaction id fails on every "
            "payment, because MT and MX each assign their own."
        ),
        tolerance=_EXACT,
        tolerance_rationale=(
            "Zero. A translation either preserved the amount or lost it; there is "
            "no materiality argument for a payment being partly translated."
        ),
        expected_breaks=(BreakKind.GENUINE, BreakKind.MISSING),
        note=(
            "The beachhead. Banks have run MT and MX in parallel since November "
            "2025, and the translation layer between them is where the defects "
            "are — neither representation can find them on its own."
        ),
    ),
    ReconciliationTemplate(
        identity="roll-forward",
        label="T to T-1 roll-forward",
        left_role="yesterday's closing plus today's movements",
        right_role="today's closing",
        key_roles=("account", "instrument_id"),
        amount_role="balance",
        why_these_keys=(
            "The identity a balance sheet has to satisfy every day. Keyed without "
            "the instrument it nets a gain on one holding against a loss on "
            "another and balances while both are wrong."
        ),
        tolerance=_EXACT,
        tolerance_rationale=(
            "Zero. Opening plus movements is closing by definition; a tolerance "
            "here is a tolerance on arithmetic."
        ),
        expected_breaks=(BreakKind.MISSING, BreakKind.DUPLICATE, BreakKind.GENUINE),
    ),
    ReconciliationTemplate(
        identity="return-to-feeder",
        label="Regulatory return to its feeder",
        left_role="the submitted return",
        right_role="the data it was built from",
        key_roles=("schedule_line", "reporting_date"),
        amount_role="reported_value",
        why_these_keys=(
            "A return is an aggregation, and the schedule line is the level it "
            "was aggregated to. Comparing at any finer grain compares things the "
            "return never claimed."
        ),
        tolerance=_EXACT,
        tolerance_rationale=(
            "Zero. A submitted figure either derives from the data or does not, "
            "and a regulator's question is about that derivation."
        ),
        expected_breaks=(BreakKind.GENUINE, BreakKind.MISSING),
    ),
)


def template(identity: str) -> ReconciliationTemplate:
    for candidate in TEMPLATES:
        if candidate.identity == identity:
            return candidate
    raise KeyError(identity)


def identities() -> tuple[str, ...]:
    return tuple(candidate.identity for candidate in TEMPLATES)


__all__ = [
    "TEMPLATES",
    "ReconciliationTemplate",
    "identities",
    "template",
]
