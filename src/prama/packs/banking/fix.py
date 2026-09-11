"""FIX: tag-value messages, and the three things that make them not a dictionary.

A FIX message looks like a flat map of ``tag=value`` pairs and is not one. The
differences are where the defects live, and a parser that flattens loses exactly
the structure a control needs to assert on.

* **The delimiter is SOH (0x01), not a pipe.** Pipes are what a log viewer shows
  and what every example in a specification prints. A parser that accepts only
  pipes works on documentation and fails on the wire; one that accepts only SOH
  fails on every captured log somebody pastes in. Both are accepted, and which
  was found is reported — because a message that arrived pipe-delimited on a
  session is itself a finding.
* **Repeating groups are not repeated keys.** ``NoLegs=2`` introduces two legs,
  each with its own tags, and flattening keeps the last one. A two-leg swap
  parsed flat is a one-leg swap that balances.
* **BodyLength and CheckSum are computed over bytes, not fields.** Both are
  stated by the sender and both are checkable, and a parser that reads them as
  ordinary tags has thrown away the only integrity check the protocol has.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from typing import Any

SOH = "\x01"
#: What a pasted log uses instead. Accepted, and reported when found.
DISPLAY_DELIMITERS = ("|", "^")

#: Tags that introduce a repeating group, and the tag that starts each entry.
#: A group flattened into a dictionary keeps its last entry, and a two-leg swap
#: read that way is a one-leg swap that balances.
GROUPS: dict[int, int] = {
    555: 600,  # NoLegs -> LegSymbol
    268: 269,  # NoMDEntries -> MDEntryType
    453: 448,  # NoPartyIDs -> PartyID
    382: 375,  # NoContraBrokers -> ContraBroker
    78: 79,  # NoAllocs -> AllocAccount
}

#: The business names a control asserts on. A control written against tag 55 is
#: a control nobody can review.
NAMES: dict[int, str] = {
    8: "begin_string",
    9: "body_length",
    10: "checksum",
    11: "cl_ord_id",
    15: "currency",
    17: "exec_id",
    31: "last_price",
    32: "last_quantity",
    35: "msg_type",
    37: "order_id",
    38: "order_quantity",
    39: "ord_status",
    44: "price",
    48: "security_id",
    49: "sender_comp_id",
    52: "sending_time",
    54: "side",
    55: "symbol",
    56: "target_comp_id",
    60: "transact_time",
    75: "trade_date",
    150: "exec_type",
    151: "leaves_quantity",
    14: "cumulative_quantity",
    22: "security_id_source",
    167: "security_type",
    453: "no_party_ids",
    555: "no_legs",
}

#: Required tags by message type, from the FIX 4.4 specification. Only the ones
#: whose absence is a defect rather than a convention.
REQUIRED: dict[str, tuple[int, ...]] = {
    "D": (11, 55, 54, 38, 40),  # NewOrderSingle
    "8": (37, 17, 150, 39, 55, 54),  # ExecutionReport
    "F": (11, 41, 55, 54),  # OrderCancelRequest
    "AE": (571, 55, 32, 31),  # TradeCaptureReport
}


@dataclasses.dataclass(frozen=True, slots=True)
class Group:
    """One entry in a repeating group."""

    tags: dict[int, str]

    def get(self, tag: int) -> str | None:
        return self.tags.get(tag)


@dataclasses.dataclass(frozen=True, slots=True)
class Defect:
    """Something wrong with a message, named where it is."""

    tag: int | None
    problem: str

    def render(self) -> str:
        where = f"tag {self.tag}" if self.tag is not None else "the message"
        return f"{where}: {self.problem}"


@dataclasses.dataclass(frozen=True, slots=True)
class Message:
    """One FIX message, with its groups intact."""

    tags: dict[int, str] = dataclasses.field(default_factory=dict)
    groups: dict[int, tuple[Group, ...]] = dataclasses.field(default_factory=dict)
    defects: tuple[Defect, ...] = ()
    #: Which delimiter the message actually used. A session message that
    #: arrived pipe-delimited is itself a finding.
    delimiter: str = SOH

    @property
    def msg_type(self) -> str:
        return self.tags.get(35, "")

    @property
    def is_well_formed(self) -> bool:
        return not self.defects

    @property
    def arrived_display_delimited(self) -> bool:
        return self.delimiter != SOH

    def get(self, tag: int) -> str | None:
        return self.tags.get(tag)

    def named(self) -> dict[str, Any]:
        """The message as business fields, with groups counted and kept.

        A control written against ``tag 55`` is a control nobody can review, so
        the row a control asserts on carries names.
        """
        out: dict[str, Any] = {
            NAMES.get(tag, f"tag_{tag}"): value for tag, value in self.tags.items()
        }
        for tag, entries in self.groups.items():
            name = NAMES.get(tag, f"tag_{tag}")
            out[f"{name}_entries"] = len(entries)
        out["defect_count"] = len(self.defects)
        out["display_delimited"] = self.arrived_display_delimited
        return out


def _split(text: str) -> tuple[list[str], str]:
    """Fields and the delimiter that separated them."""
    if SOH in text:
        return [part for part in text.split(SOH) if part], SOH
    for candidate in DISPLAY_DELIMITERS:
        if candidate in text:
            return [part for part in text.split(candidate) if part], candidate
    return ([text] if text else []), SOH


def body_length(text: str, delimiter: str = SOH) -> int | None:
    """The length the protocol defines: after tag 9's delimiter, to before tag 10.

    Computed rather than read, so the stated value has something to be checked
    against. ``None`` when the message has no recognisable envelope.
    """
    marker = f"{delimiter}35="
    start = text.find(marker)
    end = text.find(f"{delimiter}10=")
    if start < 0 or end < 0 or end <= start:
        return None
    return len(text[start + 1 : end + 1])


def checksum(text: str, delimiter: str = SOH) -> str | None:
    """The sum of every byte up to and including the delimiter before tag 10.

    Three digits, zero-padded, modulo 256 — the protocol's only integrity check,
    and the one a parser that reads tag 10 as an ordinary field throws away.
    """
    end = text.find(f"{delimiter}10=")
    if end < 0:
        return None
    return f"{sum(text[: end + 1].encode('latin-1')) % 256:03d}"


def parse(text: str) -> Message:
    """One FIX message. Never raises: a malformed message is a finding.

    One bad message in a session must not stop the rest being checked — that
    turns a data defect into an outage, and the outage is what gets the control
    disabled.
    """
    fields, delimiter = _split(text)
    defects: list[Defect] = []
    tags: dict[int, str] = {}
    groups: dict[int, tuple[Group, ...]] = {}

    pairs: list[tuple[int, str]] = []
    for field in fields:
        tag_text, separator, value = field.partition("=")
        if not separator or not tag_text.isdigit():
            defects.append(Defect(None, f"not a tag=value field: {field[:32]!r}"))
            continue
        pairs.append((int(tag_text), value))

    index = 0
    while index < len(pairs):
        tag, value = pairs[index]
        if tag in GROUPS:
            count = int(value) if value.isdigit() else 0
            starter = GROUPS[tag]
            entries: list[Group] = []
            index += 1
            current: dict[int, str] = {}
            while index < len(pairs) and len(entries) < count:
                inner_tag, inner_value = pairs[index]
                if inner_tag == starter and current:
                    entries.append(Group(tags=current))
                    current = {}
                if inner_tag == starter or current:
                    current[inner_tag] = inner_value
                    index += 1
                    continue
                break
            if current:
                entries.append(Group(tags=current))
            if len(entries) != count:
                # The count is a statement by the sender and the entries are
                # what arrived. A parser that trusted the count would report a
                # truncated group as complete.
                defects.append(
                    Defect(tag, f"declares {count} entr(ies) and carries {len(entries)}")
                )
            groups[tag] = tuple(entries)
            tags[tag] = value
            continue
        tags[tag] = value
        index += 1

    stated_length = tags.get(9)
    actual_length = body_length(text, delimiter)
    if (
        stated_length is not None
        and actual_length is not None
        and (not stated_length.isdigit() or int(stated_length) != actual_length)
    ):
        defects.append(Defect(9, f"states {stated_length} and the body is {actual_length}"))

    stated_sum = tags.get(10)
    actual_sum = checksum(text, delimiter)
    if stated_sum is not None and actual_sum is not None and stated_sum != actual_sum:
        defects.append(Defect(10, f"states {stated_sum} and the bytes give {actual_sum}"))

    for required in REQUIRED.get(tags.get(35, ""), ()):
        if required not in tags:
            defects.append(Defect(required, f"required for message type {tags.get(35)} and absent"))

    return Message(tags=tags, groups=groups, defects=tuple(defects), delimiter=delimiter)


def split(text: str) -> list[str]:
    """A session log into messages, on the ``8=FIX`` boundary."""
    import re

    pieces = re.split(r"(?=8=FIX)", text)
    return [piece for piece in pieces if piece.strip()]


__all__ = [
    "DISPLAY_DELIMITERS",
    "GROUPS",
    "NAMES",
    "REQUIRED",
    "SOH",
    "Defect",
    "Group",
    "Message",
    "body_length",
    "checksum",
    "parse",
    "split",
]
