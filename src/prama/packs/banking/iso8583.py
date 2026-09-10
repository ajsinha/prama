"""ISO 8583: card messages, where the bitmap is the whole problem.

An ISO 8583 message says which fields it carries in a bitmap, then concatenates
them with no separators. Everything about reading one depends on getting that
bitmap right, and getting it wrong does not raise — it shifts every subsequent
field and produces a message full of its neighbours' digits.

Three specific traps:

* **Bit 1 is not a field.** It says a second bitmap follows. A reader that
  treats it as data loses sixteen bytes off the front of field 2 and reports a
  PAN that is somebody else's.
* **A field's length is not fixed.** LLVAR and LLLVAR carry their own length in
  the first two or three digits, and those digits are *not* part of the value. A
  reader that includes them turns a 16-digit PAN into ``1655...``, which is a
  perfectly plausible 18-digit card number.
* **Field 4 is an amount in minor units with no decimal point.** ``000000012345``
  is 123.45, and a reader that treats it as an integer reports a payment ten
  thousand times too large — which is exactly the failure that gets noticed at
  settlement rather than at parse time.

**The PAN is never returned whole.** Field 2 comes back masked, with the length
and the last four preserved, because a parser that hands a full card number to
whatever called it has put it in that caller's logs. The unmasked value is
available only through an explicit call whose name says what it does.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal
from typing import Any

#: ``(name, kind, length)``. ``kind`` is ``n``/``an``/``ans`` for fixed, or
#: ``LLVAR``/``LLLVAR`` for length-prefixed.
FIELDS: dict[int, tuple[str, str, int]] = {
    2: ("primary_account_number", "LLVAR", 19),
    3: ("processing_code", "n", 6),
    4: ("amount_transaction", "n", 12),
    7: ("transmission_datetime", "n", 10),
    11: ("system_trace_audit_number", "n", 6),
    12: ("local_time", "n", 6),
    13: ("local_date", "n", 4),
    14: ("expiry_date", "n", 4),
    18: ("merchant_type", "n", 4),
    22: ("point_of_service_entry_mode", "n", 3),
    32: ("acquiring_institution_id", "LLVAR", 11),
    35: ("track_2_data", "LLVAR", 37),
    37: ("retrieval_reference_number", "an", 12),
    38: ("authorisation_id_response", "an", 6),
    39: ("response_code", "an", 2),
    41: ("card_acceptor_terminal_id", "ans", 8),
    42: ("card_acceptor_id", "ans", 15),
    43: ("card_acceptor_name_location", "ans", 40),
    49: ("currency_code_transaction", "n", 3),
    52: ("pin_data", "b", 16),
    55: ("icc_data", "LLLVAR", 999),
}

#: Fields whose content must never be returned in full by an ordinary read.
SENSITIVE = frozenset({2, 35, 52})


@dataclasses.dataclass(frozen=True, slots=True)
class Defect:
    field: int | None
    problem: str

    def render(self) -> str:
        where = f"field {self.field}" if self.field is not None else "the message"
        return f"{where}: {self.problem}"


def mask_pan(value: str) -> str:
    """A card number as it may safely travel: length preserved, last four kept.

    Length is preserved because it is the part a control asserts on — a
    thirteen-digit Visa and a sixteen-digit one are different findings — and
    the last four because that is what a person uses to identify a card without
    holding it.
    """
    digits = "".join(character for character in value if character.isdigit())
    if len(digits) <= 4:
        return "*" * len(digits)
    return "*" * (len(digits) - 4) + digits[-4:]


@dataclasses.dataclass(frozen=True, slots=True)
class Message:
    """One ISO 8583 message, read through its bitmap."""

    mti: str = ""
    #: Present field numbers, in order.
    present: tuple[int, ...] = ()
    #: Field number to value. Sensitive fields hold their masked form.
    values: dict[int, str] = dataclasses.field(default_factory=dict)
    defects: tuple[Defect, ...] = ()
    #: The raw, unmasked values. Deliberately separate and deliberately awkward
    #: to reach, so a caller that wants a PAN has to say so.
    _raw: dict[int, str] = dataclasses.field(default_factory=dict, repr=False)

    @property
    def is_well_formed(self) -> bool:
        return not self.defects

    @property
    def has_secondary_bitmap(self) -> bool:
        return any(field > 64 for field in self.present)

    def amount(self) -> Decimal | None:
        """Field 4, as a number with its decimal point restored.

        Minor units with no separator: 000000012345 is 123.45. Read as an
        integer it is ten thousand times too large, which is the failure noticed
        at settlement rather than at parse time.
        """
        raw = self.values.get(4)
        if raw is None or not raw.isdigit():
            return None
        return Decimal(raw).scaleb(-2)

    def unmasked(self, field: int) -> str | None:
        """A sensitive field in full.

        Named so it appears in a code review. A parser that returned these by
        default would have put a card number in whatever log its caller keeps.
        """
        return self._raw.get(field)

    def named(self) -> dict[str, Any]:
        out: dict[str, Any] = {"mti": self.mti}
        for field in self.present:
            name, _, _ = FIELDS.get(field, (f"field_{field}", "ans", 0))
            out[name] = self.values.get(field)
        amount = self.amount()
        if amount is not None:
            out["amount"] = str(amount)
        out["defect_count"] = len(self.defects)
        return out


def _bits(bitmap: str) -> list[int]:
    """Field numbers a hex bitmap declares present."""
    present: list[int] = []
    for index, character in enumerate(bitmap):
        try:
            nibble = int(character, 16)
        except ValueError:
            return present
        for offset in range(4):
            if nibble & (0b1000 >> offset):
                present.append(index * 4 + offset + 1)
    return present


def parse(text: str) -> Message:
    """One ISO 8583 message in its hex/ASCII form. Never raises."""
    defects: list[Defect] = []
    if len(text) < 4 + 16:
        return Message(defects=(Defect(None, "too short to carry an MTI and a bitmap"),))

    mti = text[:4]
    cursor = 4
    primary = text[cursor : cursor + 16]
    cursor += 16
    present = _bits(primary)

    # Bit 1 is not a field: it says a second bitmap follows. Treating it as data
    # loses sixteen bytes off the front of field 2 and reports somebody else's
    # PAN.
    if 1 in present:
        present.remove(1)
        secondary = text[cursor : cursor + 16]
        cursor += 16
        present += [field + 64 for field in _bits(secondary)]

    values: dict[int, str] = {}
    raw: dict[int, str] = {}
    for field in sorted(present):
        definition = FIELDS.get(field)
        if definition is None:
            defects.append(Defect(field, "declared present and not defined in this dialect"))
            # Cannot continue: an unknown length means every field after this
            # one is at the wrong offset, and guessing would produce a message
            # of plausible rubbish.
            break
        _, kind, size = definition
        if kind in ("LLVAR", "LLLVAR"):
            width = 2 if kind == "LLVAR" else 3
            header = text[cursor : cursor + width]
            if not header.isdigit():
                defects.append(Defect(field, f"length prefix is not numeric: {header!r}"))
                break
            length = int(header)
            cursor += width
        else:
            length = size
        value = text[cursor : cursor + length]
        if len(value) < length:
            defects.append(Defect(field, f"declares {length} characters and {len(value)} remain"))
            break
        cursor += length
        raw[field] = value
        values[field] = mask_pan(value) if field in SENSITIVE else value

    return Message(
        mti=mti,
        present=tuple(sorted(values)),
        values=values,
        defects=tuple(defects),
        _raw=raw,
    )


__all__ = ["FIELDS", "SENSITIVE", "Defect", "Message", "mask_pan", "parse"]
