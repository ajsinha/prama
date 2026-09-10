"""COBOL copybooks and EBCDIC: reading what the mainframe actually sends.

A bank's most important data usually arrives as a fixed-width EBCDIC file with a
copybook describing it, and every generic data quality tool treats that file as
binary and gives up. The extract is then converted by a script somebody wrote in
2009, and the conversion is where the defects are — which makes it exactly the
place a control belongs and exactly the place nothing is looking.

Three things here that a naive reader gets wrong, each of which silently
produces plausible numbers:

* **COMP-3 is not a string of digits.** Packed decimal stores two digits per
  byte with a sign nibble at the end. Read as text it is mojibake; read as an
  integer it is a number roughly ten thousand times too large. And the sign
  nibble distinguishes ``C`` and ``F`` (positive) from ``D`` (negative), so a
  reader that ignores it turns every credit into a debit.
* **The implied decimal point is not in the data.** ``PIC S9(7)V99`` stores
  ``123456789`` and means ``1234567.89``. There is no separator in the bytes; a
  reader that does not apply ``V`` reports every amount a hundred times too big,
  and the figure looks entirely reasonable.
* **OCCURS changes the record length.** A group that repeats twelve times is
  twelve times its own size, and getting it wrong shifts every field after it —
  producing not an error but a record full of neighbouring fields' bytes.

**Codepage matters and is stated.** EBCDIC is not one encoding: cp037 is US,
cp273 is German, cp500 is international. The difference falls on exactly the
characters an identifier uses — ``@``, ``#``, ``$`` and the accented letters —
so the codepage is a required argument rather than a default that works in
testing and corrupts one field in production.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import re
from decimal import Decimal
from typing import Any

from prama.core.errors import ValidationError

#: A copybook line: level number, name, and the rest of the clause.
_LINE = re.compile(r"^\s*(\d{2})\s+([A-Z0-9][A-Z0-9-]*)\s*(.*?)\.?\s*$", re.IGNORECASE)
_PIC = re.compile(r"\bPIC(?:TURE)?\s+(?:IS\s+)?(\S+)", re.IGNORECASE)
_OCCURS = re.compile(r"\bOCCURS\s+(\d+)", re.IGNORECASE)
_USAGE = re.compile(
    r"\b(COMP-3|COMPUTATIONAL-3|PACKED-DECIMAL|COMP|BINARY|DISPLAY)\b", re.IGNORECASE
)
_REDEFINES = re.compile(r"\bREDEFINES\s+([A-Z0-9-]+)", re.IGNORECASE)

#: ``S9(7)V99`` → sign, integer digits, decimal digits.
_PICTURE = re.compile(r"^(S)?(?:9\((\d+)\)|(9+))?(?:V(?:9\((\d+)\)|(9+)))?$", re.IGNORECASE)
_ALPHA = re.compile(r"^X\((\d+)\)$|^(X+)$", re.IGNORECASE)

#: Codepages this reader will accept without argument. Deliberately none — see
#: the module docstring. Listed here so the error can name the usual ones.
COMMON_CODEPAGES = ("cp037", "cp273", "cp500", "cp1047", "cp285", "cp297")


@dataclasses.dataclass(frozen=True, slots=True)
class Field:
    """One elementary item in a copybook."""

    name: str
    level: int
    offset: int
    length: int
    #: ``text`` · ``number``
    kind: str = "text"
    #: Digits after the implied decimal point, from ``V``.
    scale: int = 0
    signed: bool = False
    #: ``display`` · ``comp3`` · ``binary``
    usage: str = "display"
    occurs: int = 1
    #: Set when this field redefines another: it shares the earlier field's
    #: bytes and must not advance the offset.
    redefines: str = ""

    @property
    def end(self) -> int:
        return self.offset + self.length

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "offset": self.offset,
            "length": self.length,
            "kind": self.kind,
            "scale": self.scale,
            "signed": self.signed,
            "usage": self.usage,
            "occurs": self.occurs,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Copybook:
    """A parsed copybook: its fields, and how long a record is."""

    fields: tuple[Field, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def record_length(self) -> int:
        return max((field.end for field in self.fields), default=0)

    def field(self, name: str) -> Field | None:
        wanted = name.upper()
        return next((f for f in self.fields if f.name.upper() == wanted), None)

    def describe(self) -> str:
        return f"{len(self.fields)} field(s), record length {self.record_length} byte(s)" + (
            f"; {len(self.warnings)} warning(s)" if self.warnings else ""
        )


def _picture(text: str) -> tuple[str, int, int, bool]:
    """A PICTURE clause as (kind, digits, scale, signed).

    Raises rather than guessing. A picture this cannot read means every field
    after it is at the wrong offset, so continuing would produce a whole file of
    plausible rubbish — which is worse than refusing the copybook.
    """
    picture = text.strip().upper()
    alpha = _ALPHA.match(picture)
    if alpha:
        return "text", int(alpha.group(1) or len(alpha.group(2) or "")), 0, False

    matched = _PICTURE.match(picture)
    if matched and (matched.group(2) or matched.group(3) or matched.group(4) or matched.group(5)):
        signed = bool(matched.group(1))
        whole = int(matched.group(2) or 0) or len(matched.group(3) or "")
        scale = int(matched.group(4) or 0) or len(matched.group(5) or "")
        return "number", whole + scale, scale, signed

    raise ValidationError(
        f"cannot read the PICTURE clause {text.strip()!r}",
        remedy=(
            "Supported: X(n), 9(n), S9(n)V9(m) and their repeated forms. A "
            "picture this cannot read would put every field after it at the "
            "wrong offset, so the copybook is refused rather than guessed at."
        ),
        context={"picture": text.strip()},
    )


def _stored_length(digits: int, usage: str) -> int:
    if usage == "comp3":
        # Two digits per byte plus a sign nibble, rounded up.
        return digits // 2 + 1
    if usage == "binary":
        # COBOL's own table: up to 4 digits is a halfword, up to 9 a fullword.
        return 2 if digits <= 4 else (4 if digits <= 9 else 8)
    return digits


def parse_copybook(text: str) -> Copybook:
    """A copybook into fields with byte offsets.

    Group items contribute no bytes of their own; only elementary items do, and
    an ``OCCURS`` on a group multiplies everything inside it. Getting that wrong
    shifts every subsequent field and produces records full of their
    neighbours' bytes.
    """
    fields: list[Field] = []
    warnings: list[str] = []
    offset = 0
    #: (level, repeats, where the children start, where the cursor resumes).
    #:
    #: The two offsets differ only for a redefining group, and that is exactly
    #: why both are needed: its children are laid out over an *earlier* field's
    #: bytes, while the cursor must resume after whatever came before the group.
    #: Carrying one offset gets one of those two right.
    pending: list[tuple[int, int, int, int | None]] = []

    for raw in text.splitlines():
        line = raw.split("*", 1)[0] if raw.lstrip().startswith("*") else raw
        if not line.strip():
            continue
        matched = _LINE.match(line)
        if matched is None:
            warnings.append(f"ignored, not a copybook line: {line.strip()[:48]!r}")
            continue

        level, name, rest = int(matched.group(1)), matched.group(2), matched.group(3)
        if level == 88:
            # A condition name: a named value of the field above it, not a
            # field of its own and contributing no bytes.
            continue

        while pending and level <= pending[-1][0]:
            offset = _close(pending.pop(), offset)

        picture = _PIC.search(rest)
        occurs = _OCCURS.search(rest)
        repeats = int(occurs.group(1)) if occurs else 1
        redefines = _REDEFINES.search(rest)

        if picture is None:
            # A group item. It occupies whatever its children occupy — unless
            # it redefines an earlier field, in which case it occupies that
            # field's bytes and contributes none of its own.
            start, resume = offset, None
            if redefines:
                earlier = next(
                    (f for f in fields if f.name.upper() == redefines.group(1).upper()),
                    None,
                )
                if earlier is None:
                    warnings.append(
                        f"{name} redefines {redefines.group(1)}, which is not a field above it"
                    )
                else:
                    start = earlier.offset
                resume = offset
                offset = start
            pending.append((level, repeats, start, resume))
            continue

        usage_match = _USAGE.search(rest)
        usage = "display"
        if usage_match:
            token = usage_match.group(1).upper()
            if token in ("COMP-3", "COMPUTATIONAL-3", "PACKED-DECIMAL"):
                usage = "comp3"
            elif token in ("COMP", "BINARY"):
                usage = "binary"

        kind, digits, scale, signed = _picture(picture.group(1))
        length = _stored_length(digits, usage)

        if redefines:
            earlier = next(
                (f for f in fields if f.name.upper() == redefines.group(1).upper()), None
            )
            if earlier is None:
                warnings.append(
                    f"{name} redefines {redefines.group(1)}, which is not a field above it"
                )
            start = earlier.offset if earlier else offset
            fields.append(
                Field(
                    name=name,
                    level=level,
                    offset=start,
                    length=length,
                    kind=kind,
                    scale=scale,
                    signed=signed,
                    usage=usage,
                    occurs=repeats,
                    redefines=redefines.group(1),
                )
            )
            # A redefinition shares bytes; it must not advance the cursor.
            continue

        fields.append(
            Field(
                name=name,
                level=level,
                offset=offset,
                length=length,
                kind=kind,
                scale=scale,
                signed=signed,
                usage=usage,
                occurs=repeats,
            )
        )
        offset += length * repeats

    while pending:
        offset = _close(pending.pop(), offset)

    return Copybook(fields=tuple(fields), warnings=tuple(warnings))


def _close(group: tuple[int, int, int, int | None], offset: int) -> int:
    """Where the cursor goes when a group ends.

    A redefining group returns the cursor to where it was *before* the group —
    not to where its children started, which is an earlier field's offset. It
    borrowed those bytes and consumed none of its own. An OCCURS group
    multiplies the span its children took.
    """
    _, repeats, started, resume = group
    if resume is not None:
        return resume
    if repeats > 1:
        return started + (offset - started) * repeats
    return offset


def unpack_comp3(data: bytes, scale: int = 0) -> Decimal | None:
    """Packed decimal to a number, sign included.

    Two digits per byte, the last nibble being the sign: ``C`` and ``F`` are
    positive, ``D`` is negative. A reader that ignores the nibble turns every
    credit into a debit — and the figures still look entirely reasonable.

    ``None`` when a nibble is not a digit, which is what a mis-offset field
    looks like: it is a finding, not a zero.
    """
    if not data:
        return None
    nibbles: list[int] = []
    for byte in data[:-1]:
        nibbles.append(byte >> 4)
        nibbles.append(byte & 0x0F)
    last = data[-1]
    nibbles.append(last >> 4)
    sign_nibble = last & 0x0F

    # Compared as numbers. Rendering first and comparing the strings is the
    # bug this replaced: str(0xA) is "10", and "10" > "9" is False, so every
    # invalid nibble passed and produced a plausible number from rubbish.
    if any(nibble > 9 for nibble in nibbles):
        return None
    if sign_nibble not in (0x0C, 0x0D, 0x0F):
        return None

    text = "".join(str(nibble) for nibble in nibbles) or "0"
    value = Decimal(text)
    if scale:
        value = value.scaleb(-scale)
    return -value if sign_nibble == 0x0D else value


def _display_number(text: str, scale: int, signed: bool) -> Decimal | None:
    """Zoned decimal: digits as characters, with the sign overpunched.

    A trailing ``}`` or ``J`` to ``R`` in EBCDIC-derived text is a negative sign
    stamped onto the last digit. A reader that strips non-digits loses it, and
    the amount changes sign without changing magnitude — which reconciles to
    exactly twice the error and is routinely misread as a duplicate.
    """
    stripped = text.strip()
    if not stripped:
        return None
    negative = False
    if signed and stripped:
        last = stripped[-1]
        if last in "}JKLMNOPQR":
            negative = True
            stripped = stripped[:-1] + ("0" if last == "}" else str("JKLMNOPQR".index(last) + 1))
        elif last in "{ABCDEFGHI":
            stripped = stripped[:-1] + ("0" if last == "{" else str("ABCDEFGHI".index(last) + 1))
        elif last == "-":
            negative, stripped = True, stripped[:-1]
        elif last == "+":
            stripped = stripped[:-1]
    if not stripped.isdigit():
        return None
    value = Decimal(stripped)
    if scale:
        value = value.scaleb(-scale)
    return -value if negative else value


def read_record(record: bytes, copybook: Copybook, *, codepage: str) -> dict[str, Any]:
    """One fixed-width record into named values.

    ``codepage`` is required. EBCDIC is not one encoding — cp037 is US, cp273
    German, cp500 international — and they differ on exactly the characters an
    identifier uses. A default here would work in testing and corrupt one field
    in production.
    """
    if not codepage:
        raise ValidationError(
            "no EBCDIC codepage was given",
            remedy=(
                "State it: " + ", ".join(COMMON_CODEPAGES) + ". They differ on "
                "@, #, $ and the accented letters, which is exactly where an "
                "identifier lives."
            ),
        )

    out: dict[str, Any] = {}
    for field in copybook.fields:
        chunk = record[field.offset : field.end]
        if len(chunk) < field.length:
            # Short record. Named rather than padded: a padded field is a value
            # that was never sent, and it will be checked as though it were.
            out[field.name] = None
            continue
        if field.usage == "comp3":
            out[field.name] = _maybe_str(unpack_comp3(chunk, field.scale))
        elif field.usage == "binary":
            value = Decimal(int.from_bytes(chunk, "big", signed=field.signed))
            out[field.name] = str(value.scaleb(-field.scale) if field.scale else value)
        else:
            try:
                text = chunk.decode(codepage)
            except (UnicodeDecodeError, LookupError) as exc:
                raise ValidationError(
                    f"{field.name} cannot be decoded as {codepage}",
                    remedy="Check the codepage against the sending system's.",
                    context={"field": field.name, "codepage": codepage},
                    cause=exc,
                ) from exc
            if field.kind == "number":
                out[field.name] = _maybe_str(_display_number(text, field.scale, field.signed))
            else:
                out[field.name] = text.rstrip()
    return out


def _maybe_str(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def read_records(
    data: bytes, copybook: Copybook, *, codepage: str
) -> tuple[list[dict[str, Any]], list[str]]:
    """A whole fixed-width file, and what was wrong with it.

    Returns the rows *and* the complaints rather than raising, so a file with
    one short record still yields the rest — and the short record is a finding
    a control can assert on rather than an exception that lost the batch.
    """
    length = copybook.record_length
    if length <= 0:
        raise ValidationError(
            "the copybook describes no fields, so a record has no length",
            remedy="Check that the copybook text reached this call.",
        )
    rows: list[dict[str, Any]] = []
    complaints: list[str] = []
    for index in range(0, len(data), length):
        chunk = data[index : index + length]
        if len(chunk) < length:
            complaints.append(
                f"record {index // length + 1} is {len(chunk)} bytes, not {length}: "
                "the file does not divide into whole records"
            )
            continue
        rows.append(read_record(chunk, copybook, codepage=codepage))
    return rows, complaints


__all__ = [
    "COMMON_CODEPAGES",
    "Copybook",
    "Field",
    "parse_copybook",
    "read_record",
    "read_records",
    "unpack_comp3",
]
