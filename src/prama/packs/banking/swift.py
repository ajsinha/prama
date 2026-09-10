"""SWIFT MT: block structure, tagged fields, and named business fields.

The point of parsing a message is not to read it. It is to turn it into rows
whose columns have business names, so a control can say

    CHECK mt103.value_date ... CHECK mt103.currency IS IN CODELIST 'iso4217'

instead of asserting on ``:32A:``. A tool that can only see the raw text can
check that a file is well-formed and nothing about whether the payment in it is
right.

Four things this parser does that a naive one does not, each of which is a
defect class in its own right:

* **Amounts use a comma.** SWIFT writes ``1234,56``. ``float("1234,56")`` raises
  and ``float("1234.56")`` is a different parse of a different string; the
  common shortcut — strip non-digits — turns ``1234,56`` into ``123456``. Every
  amount here is a ``Decimal`` parsed from the SWIFT form, because these are
  money and binary floating point manufactures exactly the small discrepancies
  a reconciliation exists to find.
* **The debit/credit mark carries the sign.** Field 61 states ``C`` or ``D`` and
  the amount is always positive. A parser that ignores the mark produces a
  statement whose entries only ever add up, and the continuity check then passes
  on a statement that does not balance.
* **A malformed message is a finding, not an exception.** One bad message in a
  file of four thousand must not stop the other 3,999 being checked — that turns
  a data defect into an outage, and the outage is what gets the control
  disabled.
* **Nothing is inferred.** An absent optional field is absent, not empty string
  and not zero. A missing closing balance is a different fact from a closing
  balance of nothing, and only one of them balances.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import re
from decimal import Decimal, InvalidOperation
from typing import Any

#: ``{n:content}`` at the top level. Block 4 ends with ``-}`` and may contain
#: newlines and colons, so it cannot be matched by the same simple rule.
_BLOCK = re.compile(r"\{(\d):((?:[^{}]|\{[^{}]*\})*)\}", re.DOTALL)
_BLOCK4 = re.compile(r"\{4:\r?\n?(.*?)\r?\n?-\}", re.DOTALL)

#: ``:20:`` or ``:32A:`` at the start of a line.
_TAG = re.compile(r"^:(\d{2}[A-Z]?):(.*)$")

#: A balance field: mark, YYMMDD, three-letter currency, comma amount.
_BALANCE = re.compile(r"^([CD])(\d{6})([A-Z]{3})([\d,]+)$")

#: Field 61: value date, optional entry date, mark (with optional reversal),
#: amount, a four-character transaction type beginning with a letter, then
#: references.
_LINE = re.compile(r"^(\d{6})(\d{4})?([A-Z]?[CD])([\d,]+)([A-Z]\w{3})([^/]*)(?://(.*))?$")


def _amount(text: str) -> Decimal | None:
    """A SWIFT amount, which uses a comma for the decimal point.

    ``None`` rather than zero when it cannot be read: an unparseable amount is
    a finding, and zero is a number that balances.
    """
    try:
        return Decimal(text.replace(",", ".").strip() or "0")
    except (InvalidOperation, ValueError):
        return None


def _date(text: str) -> str:
    """``YYMMDD`` as ISO-8601, or "" if it is not six digits.

    The century is inferred as 20xx, which is correct for every message this
    will ever see and wrong for archives from the 1990s — stated here rather
    than buried, because a two-digit year is a decision somebody made in 1977.
    """
    if len(text) != 6 or not text.isdigit():
        return ""
    return f"20{text[0:2]}-{text[2:4]}-{text[4:6]}"


@dataclasses.dataclass(frozen=True, slots=True)
class Defect:
    """Something wrong with a message, named where it is."""

    message_reference: str
    field: str
    problem: str

    def render(self) -> str:
        return f"{self.message_reference or '(unreferenced)'} {self.field}: {self.problem}"


@dataclasses.dataclass(frozen=True, slots=True)
class Message:
    """One parsed MT message: its blocks, its fields, and what was wrong."""

    kind: str
    blocks: dict[str, str] = dataclasses.field(default_factory=dict)
    #: Tag to value, in the order the message carried them. A repeated tag —
    #: field 61 in a statement — keeps every occurrence.
    fields: tuple[tuple[str, str], ...] = ()
    defects: tuple[Defect, ...] = ()
    raw: str = ""

    @property
    def is_well_formed(self) -> bool:
        return not self.defects

    def first(self, tag: str) -> str | None:
        """The first occurrence of a tag, or ``None`` if absent.

        ``None``, never "". An absent optional field and a present empty one are
        different facts, and a caller that cannot tell them apart will report
        one as the other.
        """
        for name, value in self.fields:
            if name == tag:
                return value
        return None

    def all_of(self, tag: str) -> tuple[str, ...]:
        return tuple(value for name, value in self.fields if name == tag)

    @property
    def sender_bic(self) -> str:
        """From block 1, characters 4 to 15 of the application header."""
        block = self.blocks.get("1", "")
        return block[3:15].strip() if len(block) >= 15 else ""


def parse(text: str) -> Message:
    """One MT message into blocks and tagged fields.

    Never raises on malformed input. A file of four thousand messages must not
    lose 3,999 of them because one is bad — that turns a data defect into an
    outage, and the outage is what gets the control switched off.
    """
    defects: list[Defect] = []
    blocks = dict(_BLOCK.findall(text))

    body = _BLOCK4.search(text)
    if body is None:
        return Message(
            kind="",
            blocks=blocks,
            defects=(Defect("", "block 4", "the text block is missing or unterminated"),),
            raw=text,
        )

    fields: list[tuple[str, str]] = []
    current_tag = ""
    current: list[str] = []
    for line in body.group(1).splitlines():
        matched = _TAG.match(line)
        if matched:
            if current_tag:
                fields.append((current_tag, "\n".join(current).rstrip()))
            current_tag, current = matched.group(1), [matched.group(2)]
        elif current_tag:
            # A continuation line. Field 86 and field 50K are multi-line by
            # design, and joining them onto the previous tag is the only way to
            # keep an address together.
            current.append(line)
        elif line.strip():
            defects.append(Defect("", "block 4", f"content before the first tag: {line[:40]!r}"))
    if current_tag:
        fields.append((current_tag, "\n".join(current).rstrip()))

    kind = ""
    header = blocks.get("2", "")
    if len(header) >= 4:
        kind = header[1:4]

    return Message(kind=kind, blocks=blocks, fields=tuple(fields), defects=tuple(defects), raw=text)


def split(text: str) -> list[str]:
    """A file of concatenated messages into individual ones.

    Split on the ``$`` separator or on a block-1 boundary. Deliberately not on a
    blank line: a field 86 narrative may contain one, and splitting there cuts a
    message in half and reports two malformed messages instead of one good one.
    """
    if not text.strip():
        return []
    parts = [part for part in text.split("$") if part.strip()]
    if len(parts) > 1:
        return parts
    pieces = re.split(r"(?=\{1:)", text)
    return [piece for piece in pieces if piece.strip()]


# -- MT940: customer statement ---------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class StatementLine:
    """One entry on a statement, with its sign resolved."""

    value_date: str
    entry_date: str
    #: Signed. Field 61 states a mark and a positive amount; carrying the mark
    #: separately means every consumer has to remember to apply it, and the one
    #: that forgets produces a statement that only ever adds up.
    amount: Decimal
    is_credit: bool
    transaction_type: str
    customer_reference: str
    bank_reference: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "value_date": self.value_date,
            "entry_date": self.entry_date,
            "amount": str(self.amount),
            "is_credit": self.is_credit,
            "transaction_type": self.transaction_type,
            "customer_reference": self.customer_reference,
            "bank_reference": self.bank_reference,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Statement:
    """An MT940 as named business fields."""

    reference: str
    account: str
    statement_number: str
    opening_balance: Decimal | None
    closing_balance: Decimal | None
    currency: str
    opening_date: str
    closing_date: str
    lines: tuple[StatementLine, ...] = ()
    defects: tuple[Defect, ...] = ()

    @property
    def movement(self) -> Decimal:
        return sum((line.amount for line in self.lines), Decimal(0))

    @property
    def balances(self) -> bool | None:
        """Whether opening + movement equals closing.

        ``None`` when either balance is missing, which is not the same as not
        balancing: a statement with no closing balance has not failed
        continuity, it has failed to state it, and the two go to different
        people.
        """
        if self.opening_balance is None or self.closing_balance is None:
            return None
        return self.opening_balance + self.movement == self.closing_balance

    @property
    def discrepancy(self) -> Decimal | None:
        if self.opening_balance is None or self.closing_balance is None:
            return None
        return self.closing_balance - (self.opening_balance + self.movement)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference": self.reference,
            "account": self.account,
            "statement_number": self.statement_number,
            "currency": self.currency,
            "opening_balance": _maybe(self.opening_balance),
            "closing_balance": _maybe(self.closing_balance),
            "opening_date": self.opening_date,
            "closing_date": self.closing_date,
            "entry_count": len(self.lines),
            "movement": str(self.movement),
            "balances": self.balances,
            "discrepancy": _maybe(self.discrepancy),
            "defect_count": len(self.defects),
        }


def _maybe(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def statement(message: Message) -> Statement:
    """An MT940 message as a statement.

    Everything that cannot be read becomes a defect on the statement rather
    than an exception, so a file's worth of statements can be checked in one
    pass and the bad ones named.
    """
    defects = list(message.defects)
    reference = (message.first("20") or "").strip()

    opening_raw = message.first("60F") or message.first("60M")
    closing_raw = message.first("62F") or message.first("62M")
    opening, opening_date, opening_ccy = _balance(opening_raw, "60F", reference, defects)
    closing, closing_date, closing_ccy = _balance(closing_raw, "62F", reference, defects)

    if opening_ccy and closing_ccy and opening_ccy != closing_ccy:
        # A statement that opens in euros and closes in dollars is not a
        # statement; the arithmetic below would be meaningless and the check
        # has to name that rather than produce a number.
        defects.append(
            Defect(
                reference,
                "60F/62F",
                f"opens in {opening_ccy} and closes in {closing_ccy}",
            )
        )

    lines: list[StatementLine] = []
    for raw in message.all_of("61"):
        parsed = _line(raw, reference, defects)
        if parsed is not None:
            lines.append(parsed)

    return Statement(
        reference=reference,
        account=(message.first("25") or "").strip(),
        statement_number=(message.first("28C") or message.first("28") or "").strip(),
        opening_balance=opening,
        closing_balance=closing,
        currency=opening_ccy or closing_ccy,
        opening_date=opening_date,
        closing_date=closing_date,
        lines=tuple(lines),
        defects=tuple(defects),
    )


def _balance(
    raw: str | None, tag: str, reference: str, defects: list[Defect]
) -> tuple[Decimal | None, str, str]:
    if raw is None:
        defects.append(Defect(reference, tag, "the balance field is absent"))
        return None, "", ""
    matched = _BALANCE.match(raw.strip())
    if matched is None:
        defects.append(Defect(reference, tag, f"cannot be read: {raw.strip()[:40]!r}"))
        return None, "", ""
    mark, day, currency, amount = matched.groups()
    value = _amount(amount)
    if value is None:
        defects.append(Defect(reference, tag, f"the amount cannot be read: {amount!r}"))
        return None, _date(day), currency
    # A debit balance is negative. Storing the mark separately and the amount
    # positive is how a statement comes to look overdrawn by the same figure it
    # is in credit by.
    return (value if mark == "C" else -value), _date(day), currency


def _line(raw: str, reference: str, defects: list[Defect]) -> StatementLine | None:
    head = raw.splitlines()[0].strip()
    matched = _LINE.match(head)
    if matched is None:
        defects.append(Defect(reference, "61", f"cannot be read: {head[:48]!r}"))
        return None
    value_day, entry_day, mark, amount, kind, customer, bank = matched.groups()
    value = _amount(amount)
    if value is None:
        defects.append(Defect(reference, "61", f"the amount cannot be read: {amount!r}"))
        return None
    # 'RC' and 'RD' are reversals: a reversal of a credit is a debit.
    credit = mark.endswith("C")
    if mark.startswith("R"):
        credit = not credit
    return StatementLine(
        value_date=_date(value_day),
        entry_date=_date(f"{value_day[:2]}{entry_day}") if entry_day else "",
        amount=value if credit else -value,
        is_credit=credit,
        transaction_type=kind,
        customer_reference=customer.strip(),
        bank_reference=(bank or "").strip(),
    )


# -- MT103: single customer credit transfer --------------------------------


def payment(message: Message) -> dict[str, Any]:
    """An MT103 as named business fields.

    Returns a plain dictionary because this is a row: it goes into a dataset, a
    control asserts on its columns, and a dataclass would have to be unpacked
    again at the first use.
    """
    reference = (message.first("20") or "").strip()
    value_date, currency, amount = "", "", None
    raw = message.first("32A")
    if raw is None:
        currency = ""
    else:
        stripped = raw.strip()
        if len(stripped) > 9 and stripped[:6].isdigit():
            value_date = _date(stripped[:6])
            currency = stripped[6:9]
            amount = _amount(stripped[9:])

    return {
        "reference": reference,
        "bank_operation_code": (message.first("23B") or "").strip(),
        "value_date": value_date,
        "currency": currency,
        "amount": None if amount is None else str(amount),
        "ordering_customer": (message.first("50K") or message.first("50A") or "").strip(),
        "ordering_institution": (message.first("52A") or "").strip(),
        "account_with_institution": (message.first("57A") or "").strip(),
        "beneficiary": (message.first("59") or message.first("59A") or "").strip(),
        "remittance_information": (message.first("70") or "").strip(),
        "details_of_charges": (message.first("71A") or "").strip(),
        "sender_bic": message.sender_bic,
        "defect_count": len(message.defects),
    }


__all__ = [
    "Defect",
    "Message",
    "Statement",
    "StatementLine",
    "parse",
    "payment",
    "split",
    "statement",
]
