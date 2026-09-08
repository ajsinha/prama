"""Filename patterns, and the business date hidden inside them.

A feed's filename is not decoration — it is usually the only place the business
date is recorded. ``POS_EXTRACT_20260331_001.csv`` says which day it is for and
which delivery of that day it is, and a platform that treats it as an opaque
string cannot tell a late file from a duplicate from a file for the wrong date.

So the pattern is parsed, not globbed. Tokens are written the way an operations
person already writes them in a runbook:

    POS_EXTRACT_{YYYYMMDD}_{SEQ}.csv
    positions.{YYYY}-{MM}-{DD}.parquet
    trades_{YYYYMMDD}_{HH}{mm}.json.gz

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import re
from datetime import date, time
from typing import Any

from prama.core.errors import ValidationError

#: Token -> (regex, group name). Longest tokens first, so ``{YYYYMMDD}`` is not
#: mistaken for ``{YYYY}`` followed by literal ``MMDD``.
TOKENS: tuple[tuple[str, str, str], ...] = (
    ("{YYYYMMDD}", r"(?P<ymd>\d{8})", "ymd"),
    ("{YYYY-MM-DD}", r"(?P<ymd_dashed>\d{4}-\d{2}-\d{2})", "ymd_dashed"),
    ("{DDMMYYYY}", r"(?P<dmy>\d{8})", "dmy"),
    ("{YYYY}", r"(?P<year>\d{4})", "year"),
    ("{YY}", r"(?P<year2>\d{2})", "year2"),
    ("{MM}", r"(?P<month>\d{2})", "month"),
    ("{DD}", r"(?P<day>\d{2})", "day"),
    ("{HH}", r"(?P<hour>\d{2})", "hour"),
    ("{mm}", r"(?P<minute>\d{2})", "minute"),
    ("{SEQ}", r"(?P<seq>\d+)", "seq"),
    ("{ANY}", r"(?P<any>[^/]*)", "any"),
)

#: ``{SEQ:3}`` means a zero-padded sequence. Worth supporting because the
#: padding is how the name is actually written, and an alert that names the
#: missing file as ``..._1.csv`` when it should be ``..._001.csv`` sends the
#: reader looking for the wrong thing.
_PADDED_SEQ = re.compile(r"\{SEQ:(\d+)\}")

_TOKEN_FINDER = re.compile(
    "|".join([_PADDED_SEQ.pattern, *(re.escape(token) for token, _, _ in TOKENS)])
)

#: Anything token-shaped. Used only to catch the ones we do not recognise: a
#: misspelled ``{YYYYMDD}`` left as a literal would match no file ever, and the
#: feed would report a missing delivery every single day with no hint why.
_TOKEN_SHAPED = re.compile(r"\{[A-Za-z][A-Za-z0-9:_-]*\}")


@dataclasses.dataclass(frozen=True, slots=True)
class ParsedName:
    """What a filename told us about itself."""

    filename: str
    business_date: date | None = None
    delivery_time: time | None = None
    sequence: int | None = None

    @property
    def has_date(self) -> bool:
        return self.business_date is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "business_date": self.business_date.isoformat() if self.business_date else None,
            "delivery_time": self.delivery_time.isoformat() if self.delivery_time else None,
            "sequence": self.sequence,
        }


class FilenamePattern:
    """Compiles a feed's naming convention, and reads names back with it.

    Two directions, both needed: *match* an arrived file to learn its business
    date, and *render* the name a file should have so a missing one can be named
    in the alert. "positions_20260331.csv has not arrived" is actionable;
    "a file is missing" is not.
    """

    def __init__(self, pattern: str, *, century: int = 2000) -> None:
        if not pattern.strip():
            raise ValidationError(
                "a feed needs a filename pattern",
                remedy=(
                    "Describe the name, using tokens for the parts that change — "
                    "for example POS_EXTRACT_{YYYYMMDD}_{SEQ}.csv"
                ),
            )
        self.pattern = pattern
        self._century = century
        self._tokens = tuple(m.group(0) for m in _TOKEN_FINDER.finditer(pattern))
        self._reject_unknown_tokens()
        self._reject_incoherent_date()
        self._regex = re.compile(f"^{self._build()}$", re.IGNORECASE)

    def _reject_unknown_tokens(self) -> None:
        known = set(self._tokens)
        unknown = [
            m.group(0) for m in _TOKEN_SHAPED.finditer(self.pattern) if m.group(0) not in known
        ]
        if unknown:
            raise ValidationError(
                f"unrecognised token(s) in the filename pattern: {', '.join(unknown)}",
                remedy=(
                    "Use one of "
                    + ", ".join(token for token, _, _ in TOKENS)
                    + " — or {ANY} for a part of the name nobody controls. "
                    "Left as literal text, this pattern would match no file at all "
                    "and the feed would report a missing delivery every day."
                ),
                context={"pattern": self.pattern, "unknown": unknown},
            )

    def _reject_incoherent_date(self) -> None:
        """A day without a month names no day.

        ``{YYYY}{MM}`` is fine — a monthly feed, read as the first of the month.
        ``{YYYY}{DD}`` is not: every file in the year would land on the same
        handful of dates, and the arrival judge would report them as duplicates.
        """
        if "{DD}" in self._tokens and "{MM}" not in self._tokens:
            raise ValidationError(
                "the filename pattern has a day token but no month token",
                remedy=(
                    "Add {MM}, or use {YYYYMMDD} if the whole date is one field. "
                    "A day without a month cannot identify a business date."
                ),
                context={"pattern": self.pattern},
            )

    def _build(self) -> str:
        """Translate tokens to regex, escaping everything between them."""
        expression: list[str] = []
        position = 0
        for match in _TOKEN_FINDER.finditer(self.pattern):
            literal = self.pattern[position : match.start()]
            expression.append(self._escape_literal(literal))
            token = match.group(0)
            padded = _PADDED_SEQ.fullmatch(token)
            if padded:
                expression.append(rf"(?P<seq>\d{{{int(padded.group(1))}}})")
            else:
                expression.append(next(rx for tok, rx, _ in TOKENS if tok == token))
            position = match.end()
        expression.append(self._escape_literal(self.pattern[position:]))
        return "".join(expression)

    @staticmethod
    def _escape_literal(text: str) -> str:
        """Escape the literal parts, but keep ``*`` and ``?`` as wildcards.

        Operations people write ``POS_*_{YYYYMMDD}.csv`` and mean a wildcard;
        refusing that would make the pattern language a worse version of the
        glob they already know.
        """
        out = []
        for character in text:
            if character == "*":
                out.append(r"[^/]*")
            elif character == "?":
                out.append(r"[^/]")
            else:
                out.append(re.escape(character))
        return "".join(out)

    @property
    def carries_date(self) -> bool:
        """Whether a business date can be read from a name at all.

        When it cannot, arrival has to be judged by modification time — workable,
        but weaker, and the feed's controls should say so rather than imply a
        precision they do not have.
        """
        return any(
            token in self._tokens
            for token in ("{YYYYMMDD}", "{YYYY-MM-DD}", "{DDMMYYYY}", "{YYYY}")
        )

    @property
    def carries_sequence(self) -> bool:
        return any(token.startswith("{SEQ") for token in self._tokens)

    @property
    def _sequence_width(self) -> int:
        for token in self._tokens:
            padded = _PADDED_SEQ.fullmatch(token)
            if padded:
                return int(padded.group(1))
        return 0

    def matches(self, filename: str) -> bool:
        return self._regex.match(filename) is not None

    def parse(self, filename: str) -> ParsedName | None:
        """Read a filename. Returns None when it does not belong to this feed."""
        match = self._regex.match(filename)
        if match is None:
            return None
        groups = {k: v for k, v in match.groupdict().items() if v is not None}
        return ParsedName(
            filename=filename,
            business_date=self._date_from(groups),
            delivery_time=self._time_from(groups),
            sequence=int(groups["seq"]) if "seq" in groups else None,
        )

    def _date_from(self, groups: dict[str, str]) -> date | None:
        try:
            if "ymd" in groups:
                raw = groups["ymd"]
                return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
            if "ymd_dashed" in groups:
                return date.fromisoformat(groups["ymd_dashed"])
            if "dmy" in groups:
                raw = groups["dmy"]
                return date(int(raw[4:8]), int(raw[2:4]), int(raw[:2]))
            year = (
                int(groups["year"])
                if "year" in groups
                else self._century + int(groups["year2"])
                if "year2" in groups
                else None
            )
            if year is None:
                return None
            return date(year, int(groups.get("month", 1)), int(groups.get("day", 1)))
        except ValueError:
            # A name shaped like a date but holding 20261332. Not this feed's
            # file, or a genuinely malformed one — either way, not a date.
            return None

    @staticmethod
    def _time_from(groups: dict[str, str]) -> time | None:
        if "hour" not in groups:
            return None
        try:
            return time(int(groups["hour"]), int(groups.get("minute", 0)))
        except ValueError:
            return None

    def render(self, business_date: date, *, sequence: int = 1) -> str:
        """The name a file for this date *should* have.

        So a missing file can be named in the alert. Wildcards render as ``*``,
        since there is nothing to substitute.
        """
        rendered = self.pattern
        substitutions = {
            "{YYYYMMDD}": business_date.strftime("%Y%m%d"),
            "{YYYY-MM-DD}": business_date.isoformat(),
            "{DDMMYYYY}": business_date.strftime("%d%m%Y"),
            "{YYYY}": business_date.strftime("%Y"),
            "{YY}": business_date.strftime("%y"),
            "{MM}": business_date.strftime("%m"),
            "{DD}": business_date.strftime("%d"),
            "{HH}": "??",
            "{mm}": "??",
            "{SEQ}": str(sequence),
            "{ANY}": "*",
        }
        width = self._sequence_width
        if width:
            rendered = _PADDED_SEQ.sub(str(sequence).zfill(width), rendered)
        for token, value in substitutions.items():
            rendered = rendered.replace(token, value)
        return rendered

    def __repr__(self) -> str:
        return f"FilenamePattern({self.pattern!r})"
