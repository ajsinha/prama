"""ISO 20022: pacs.008 and camt.053 as named business fields.

Swift completed the migration of cross-border interbank payment instructions to
ISO 20022 in November 2025. Banks now run MT and MX in parallel with translation
layers between them, and docs/corpus/12 §4 names that as the concrete beachhead: the
translation is where the defects are, and neither representation can find them
on its own.

So this parser and ``swift.py`` deliberately produce **the same field names for
the same business facts**. ``reference``, ``amount``, ``currency``,
``debtor_agent_bic``: an MT103 and the pacs.008 it was translated into become
two rows of one shape, and a ``RECONCILES_WITH`` relationship between them is a
translation-fidelity control. Two parsers with two vocabularies would have made
that a mapping exercise, and a mapping maintained by hand is a third thing that
can be wrong.

**Namespaces are not matched.** ISO 20022 documents carry a namespace that
encodes the message version — ``pacs.008.001.08`` against ``.09`` — and a parser
keyed on the full namespace refuses next year's file. Elements are matched on
local name, and the version is *reported* rather than enforced, so a control can
assert on it if the estate cares.

**Nothing is summed that was not stated.** ``control_sum`` is what the message
claims; ``transaction_total`` is what its transactions add up to. Deriving one
from the other would make the most useful check in the file impossible to write.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import re
from decimal import Decimal, InvalidOperation
from typing import Any
from xml.etree import ElementTree

#: ``{urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08}Document`` → the version.
_VERSION = re.compile(r"([a-z]+\.\d{3}\.\d{3}\.\d{2})")


def _local(tag: str) -> str:
    """An element's name without its namespace."""
    return tag.rsplit("}", 1)[-1]


def _find(element: Any, *path: str) -> Any:
    """Walk by local name, ignoring namespaces entirely.

    A parser keyed on the full namespace refuses next year's message, because
    the namespace encodes the version. The version is worth reporting and is not
    worth refusing on: that is a decision for a control, not for a parser.
    """
    if element is None:
        # Absent all the way down. An optional branch that is not there makes
        # every element under it not there, and raising here would turn "this
        # message has no debtor account" into a crash on the whole file.
        return None
    current = element
    for name in path:
        found = None
        for child in list(current):
            if _local(child.tag) == name:
                found = child
                break
        if found is None:
            return None
        current = found
    return current


def _text(element: Any, *path: str) -> str:
    """The text at a path, or "" when anything along it is absent."""
    if element is None:
        return ""
    found = _find(element, *path) if path else element
    if found is None or found.text is None:
        return ""
    text: str = found.text
    return text.strip()


def _decimal(text: str) -> Decimal | None:
    try:
        return Decimal(text) if text else None
    except (InvalidOperation, ValueError):
        return None


def _children(element: Any, name: str) -> list[Any]:
    return [child for child in list(element) if _local(child.tag) == name]


@dataclasses.dataclass(frozen=True, slots=True)
class Transaction:
    """One credit transfer, in the vocabulary ``swift.py`` also uses."""

    reference: str
    end_to_end_id: str
    uetr: str
    amount: Decimal | None
    currency: str
    value_date: str
    debtor_name: str
    debtor_iban: str
    debtor_agent_bic: str
    creditor_name: str
    creditor_iban: str
    creditor_agent_bic: str
    remittance_information: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference": self.reference,
            "end_to_end_id": self.end_to_end_id,
            "uetr": self.uetr,
            "amount": None if self.amount is None else str(self.amount),
            "currency": self.currency,
            "value_date": self.value_date,
            "debtor_name": self.debtor_name,
            "debtor_iban": self.debtor_iban,
            "debtor_agent_bic": self.debtor_agent_bic,
            "creditor_name": self.creditor_name,
            "creditor_iban": self.creditor_iban,
            "creditor_agent_bic": self.creditor_agent_bic,
            "remittance_information": self.remittance_information,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Pacs008:
    """A customer credit transfer file: what it claims, and what it contains."""

    message_id: str
    creation_datetime: str
    version: str
    #: What the group header *says*. Not derived.
    stated_count: int | None
    control_sum: Decimal | None
    settlement_date: str
    settlement_method: str
    transactions: tuple[Transaction, ...] = ()
    defects: tuple[str, ...] = ()

    @property
    def actual_count(self) -> int:
        return len(self.transactions)

    @property
    def transaction_total(self) -> Decimal:
        return sum((t.amount for t in self.transactions if t.amount is not None), Decimal(0))

    @property
    def count_agrees(self) -> bool | None:
        """Stated count against transactions present.

        ``None`` when the header does not state one — which is not the same as
        disagreeing, and goes to a different person: an absent control total is
        a sender problem, a wrong one is a truncation.
        """
        if self.stated_count is None:
            return None
        return self.stated_count == self.actual_count

    @property
    def sum_agrees(self) -> bool | None:
        if self.control_sum is None:
            return None
        return self.control_sum == self.transaction_total

    @property
    def unreadable_amounts(self) -> int:
        """Transactions whose amount could not be read.

        Reported separately because they make the total a lower bound: a file
        whose sum agrees while three amounts were unreadable has not been
        checked, it has been under-counted twice in the same direction.
        """
        return sum(1 for t in self.transactions if t.amount is None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "creation_datetime": self.creation_datetime,
            "version": self.version,
            "stated_count": self.stated_count,
            "actual_count": self.actual_count,
            "control_sum": None if self.control_sum is None else str(self.control_sum),
            "transaction_total": str(self.transaction_total),
            "count_agrees": self.count_agrees,
            "sum_agrees": self.sum_agrees,
            "unreadable_amounts": self.unreadable_amounts,
            "settlement_date": self.settlement_date,
            "settlement_method": self.settlement_method,
            "defect_count": len(self.defects),
        }


def parse_pacs008(xml: str) -> Pacs008:
    """A pacs.008 document. Never raises on malformed XML.

    One bad file must not stop the others being checked; a parse failure comes
    back as a defect on an otherwise-empty result, which a control can assert on
    exactly like any other finding.
    """
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        return Pacs008(
            message_id="",
            creation_datetime="",
            version="",
            stated_count=None,
            control_sum=None,
            settlement_date="",
            settlement_method="",
            defects=(f"the document is not well-formed XML: {exc}",),
        )

    matched = _VERSION.search(root.tag)
    version = matched.group(1) if matched else ""

    # `or` would truth-test an Element, which ElementTree deprecates and
    # which is ambiguous anyway: an element with no children is falsy
    # while being perfectly present.
    body = _find(root, "FIToFICstmrCdtTrf")
    if body is None:
        body = root
    header = _find(body, "GrpHdr")
    defects: list[str] = []
    if header is None:
        defects.append("the group header is absent")

    stated = _decimal(_text(header, "NbOfTxs")) if header is not None else None
    control_sum = _decimal(_text(header, "CtrlSum")) if header is not None else None
    settlement = _find(header, "SttlmInf") if header is not None else None

    group_settlement = _text(header, "IntrBkSttlmDt") if header is not None else ""
    transactions = tuple(
        _transaction(node, group_settlement) for node in _children(body, "CdtTrfTxInf")
    )
    if not transactions:
        defects.append("the document carries no credit transfer transactions")

    return Pacs008(
        message_id=_text(header, "MsgId") if header is not None else "",
        creation_datetime=_text(header, "CreDtTm") if header is not None else "",
        version=version,
        stated_count=None if stated is None else int(stated),
        control_sum=control_sum,
        settlement_date=_text(header, "IntrBkSttlmDt") if header is not None else "",
        settlement_method=_text(settlement, "SttlmMtd") if settlement is not None else "",
        transactions=transactions,
        defects=tuple(defects),
    )


def _transaction(node: Any, group_settlement: str = "") -> Transaction:
    """One transaction, inheriting the group's settlement date when it has none.

    ISO 20022 allows the interbank settlement date on the group header or on
    each transaction, and most senders put it on the header. A parser that read
    only the transaction returns nothing for the majority of real files, and a
    control then reports every payment as missing a value date.
    """
    identifiers = _find(node, "PmtId")
    amount_node = _find(node, "IntrBkSttlmAmt")
    amount = _decimal(_text(amount_node)) if amount_node is not None else None
    currency = amount_node.get("Ccy", "") if amount_node is not None else ""

    return Transaction(
        reference=_text(identifiers, "TxId") if identifiers is not None else "",
        end_to_end_id=_text(identifiers, "EndToEndId") if identifiers is not None else "",
        uetr=_text(identifiers, "UETR") if identifiers is not None else "",
        amount=amount,
        currency=currency,
        value_date=_text(node, "IntrBkSttlmDt") or group_settlement,
        debtor_name=_text(_find(node, "Dbtr"), "Nm"),
        debtor_iban=_text(_find(node, "DbtrAcct", "Id"), "IBAN"),
        debtor_agent_bic=_agent(node, "DbtrAgt"),
        creditor_name=_text(_find(node, "Cdtr"), "Nm"),
        creditor_iban=_text(_find(node, "CdtrAcct", "Id"), "IBAN"),
        creditor_agent_bic=_agent(node, "CdtrAgt"),
        remittance_information=_text(_find(node, "RmtInf"), "Ustrd"),
    )


def _agent(node: Any, name: str) -> str:
    """An agent's BIC, under either of the two names the standard has used.

    ``BICFI`` since version .03 and ``BIC`` before it. Reading only one silently
    returns nothing for the other, and "no BIC" is a finding a control will
    report as a missing field rather than as a parser that did not look.
    """
    institution = _find(node, name, "FinInstnId")
    if institution is None:
        return ""
    return _text(institution, "BICFI") or _text(institution, "BIC")


# -- camt.053: bank-to-customer statement ----------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class Entry:
    """One statement entry, with its sign resolved.

    ``CRDT``/``DBIT`` in ISO 20022 is what ``C``/``D`` is in field 61, and the
    amount is positive in both. Resolving it here rather than carrying the
    indicator means no consumer can forget to apply it — and the consumer that
    forgets produces a statement whose entries only ever add up.
    """

    amount: Decimal | None
    currency: str
    is_credit: bool
    booking_date: str
    value_date: str
    reference: str = ""
    additional_information: str = ""

    @property
    def signed(self) -> Decimal | None:
        if self.amount is None:
            return None
        return self.amount if self.is_credit else -self.amount

    def to_dict(self) -> dict[str, Any]:
        return {
            "amount": None if self.amount is None else str(self.amount),
            "signed_amount": None if self.signed is None else str(self.signed),
            "currency": self.currency,
            "is_credit": self.is_credit,
            "booking_date": self.booking_date,
            "value_date": self.value_date,
            "reference": self.reference,
            "additional_information": self.additional_information,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Camt053:
    """A bank-to-customer statement, in the vocabulary ``swift.Statement`` uses.

    Same field names as MT940 for the same facts, so a bank running both can
    reconcile the two representations of one account-day rather than mapping
    between them by hand.
    """

    message_id: str
    version: str
    account: str
    currency: str
    statement_number: str
    opening_balance: Decimal | None
    closing_balance: Decimal | None
    opening_date: str
    closing_date: str
    entries: tuple[Entry, ...] = ()
    defects: tuple[str, ...] = ()

    @property
    def movement(self) -> Decimal:
        return sum(
            (entry.signed for entry in self.entries if entry.signed is not None),
            Decimal(0),
        )

    @property
    def balances(self) -> bool | None:
        """Opening plus movement against closing, or ``None`` when unstated."""
        if self.opening_balance is None or self.closing_balance is None:
            return None
        return self.opening_balance + self.movement == self.closing_balance

    @property
    def discrepancy(self) -> Decimal | None:
        if self.opening_balance is None or self.closing_balance is None:
            return None
        return self.closing_balance - (self.opening_balance + self.movement)

    @property
    def unreadable_entries(self) -> int:
        return sum(1 for entry in self.entries if entry.amount is None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "version": self.version,
            "account": self.account,
            "currency": self.currency,
            "statement_number": self.statement_number,
            "opening_balance": None if self.opening_balance is None else str(self.opening_balance),
            "closing_balance": None if self.closing_balance is None else str(self.closing_balance),
            "opening_date": self.opening_date,
            "closing_date": self.closing_date,
            "entry_count": len(self.entries),
            "movement": str(self.movement),
            "balances": self.balances,
            "discrepancy": None if self.discrepancy is None else str(self.discrepancy),
            "unreadable_entries": self.unreadable_entries,
            "defect_count": len(self.defects),
        }


#: Balance type codes. OPBD/PRCD open a statement and CLBD closes it; ITBD is
#: an interim figure and CLAV is *available* rather than booked, which is a
#: different number and the one a naive reader picks up by accident.
_OPENING_CODES = ("OPBD", "PRCD")
_CLOSING_CODES = ("CLBD",)


def parse_camt053(xml: str) -> Camt053:
    """A camt.053 statement. Never raises on malformed XML."""
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        return Camt053(
            message_id="",
            version="",
            account="",
            currency="",
            statement_number="",
            opening_balance=None,
            closing_balance=None,
            opening_date="",
            closing_date="",
            defects=(f"the document is not well-formed XML: {exc}",),
        )

    matched = _VERSION.search(root.tag)
    version = matched.group(1) if matched else ""

    body = _find(root, "BkToCstmrStmt")
    if body is None:
        body = root
    header = _find(body, "GrpHdr")
    statement_node = _find(body, "Stmt")
    defects: list[str] = []
    if statement_node is None:
        return Camt053(
            message_id=_text(header, "MsgId"),
            version=version,
            account="",
            currency="",
            statement_number="",
            opening_balance=None,
            closing_balance=None,
            opening_date="",
            closing_date="",
            defects=("the document carries no statement",),
        )

    opening, opening_date, opening_ccy = _balance_of(statement_node, _OPENING_CODES)
    closing, closing_date, closing_ccy = _balance_of(statement_node, _CLOSING_CODES)
    if opening is None:
        defects.append("no opening balance (OPBD or PRCD) is stated")
    if closing is None:
        defects.append("no closing balance (CLBD) is stated")
    if opening_ccy and closing_ccy and opening_ccy != closing_ccy:
        defects.append(f"opens in {opening_ccy} and closes in {closing_ccy}")

    entries = tuple(_entry(node) for node in _children(statement_node, "Ntry"))

    return Camt053(
        message_id=_text(header, "MsgId"),
        version=version,
        account=_text(_find(statement_node, "Acct", "Id"), "IBAN")
        or _text(_find(statement_node, "Acct", "Id", "Othr"), "Id"),
        currency=opening_ccy or closing_ccy,
        statement_number=_text(statement_node, "LglSeqNb") or _text(statement_node, "ElctrncSeqNb"),
        opening_balance=opening,
        closing_balance=closing,
        opening_date=opening_date,
        closing_date=closing_date,
        entries=entries,
        defects=tuple(defects),
    )


def _balance_of(statement_node: Any, codes: tuple[str, ...]) -> tuple[Decimal | None, str, str]:
    """The balance carrying one of *codes*, signed by its indicator.

    Matched on code rather than on position. A statement may carry five
    balances, and taking the first is how a reader ends up reporting the
    *available* balance as the closing one — a different number that usually
    happens to be close.
    """
    for node in _children(statement_node, "Bal"):
        code = _text(_find(node, "Tp", "CdOrPrtry"), "Cd")
        if code not in codes:
            continue
        amount_node = _find(node, "Amt")
        value = _decimal(_text(amount_node)) if amount_node is not None else None
        currency = amount_node.get("Ccy", "") if amount_node is not None else ""
        indicator = _text(node, "CdtDbtInd")
        date_text = _text(_find(node, "Dt"), "Dt") or _text(_find(node, "Dt"), "DtTm")
        if value is not None and indicator == "DBIT":
            value = -value
        return value, date_text[:10], currency
    return None, "", ""


def _entry(node: Any) -> Entry:
    amount_node = _find(node, "Amt")
    return Entry(
        amount=_decimal(_text(amount_node)) if amount_node is not None else None,
        currency=amount_node.get("Ccy", "") if amount_node is not None else "",
        is_credit=_text(node, "CdtDbtInd") == "CRDT",
        booking_date=_text(_find(node, "BookgDt"), "Dt")[:10],
        value_date=_text(_find(node, "ValDt"), "Dt")[:10],
        reference=_text(node, "AcctSvcrRef")
        or _text(_find(node, "NtryDtls", "TxDtls", "Refs"), "EndToEndId"),
        additional_information=_text(node, "AddtlNtryInf"),
    )


__all__ = [
    "Camt053",
    "Entry",
    "Pacs008",
    "Transaction",
    "parse_camt053",
    "parse_pacs008",
]
