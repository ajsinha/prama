"""Pairing two sides up, and being honest about how well it went.

`FR-REC-001`. The break population everybody looks at is downstream of the
matching, and **most breaks in a badly-configured reconciliation are matching
failures rather than value differences.** A record that failed to match looks
like a break of one hundred percent of its value, so a reconciliation matching
sixty percent of its rows produces a break list that is mostly noise, in which
the real differences are invisible.

So the match rate is the headline number, not a footnote. A reconciliation
reporting four thousand breaks at a 62% match rate is not a data quality
problem; it is a configuration problem, and saying so before anybody opens the
break list saves the week they would otherwise spend on it.

**Repeated keys are aggregated, never paired arbitrarily.** One GL entry
against twenty sub-ledger postings is the ordinary shape of the work, and
pairing them row by row produces one match and nineteen phantom missing
records. Where a key repeats on either side the comparison is between the two
*totals* for that key — which is what the business means by "these agree" — and
the fact that it aggregated is recorded, because a total matching says less
than twenty rows matching and the difference matters when somebody is chasing
one posting.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

#: Below this match rate the run is reported as a configuration problem rather
#: than a break population. Set where it is because a genuine reconciliation
#: between systems that are meant to agree matches almost everything: a tenth
#: of rows failing to match is a mapping gap, not a data gap.
POOR_MATCH_RATE = 0.9


class Cardinality(enum.Enum):
    """How the two sides line up on a key."""

    ONE_TO_ONE = "one_to_one"
    #: Many rows on the left against one on the right, or the reverse. The
    #: ordinary shape: a GL entry summarising a day of postings.
    MANY_TO_ONE = "many_to_one"
    ONE_TO_MANY = "one_to_many"
    MANY_TO_MANY = "many_to_many"

    @property
    def needs_aggregation(self) -> bool:
        return self is not Cardinality.ONE_TO_ONE


@dataclasses.dataclass(frozen=True, slots=True)
class MatchKey:
    """Which columns identify the same thing on each side."""

    left: tuple[str, ...]
    right: tuple[str, ...]

    def __post_init__(self) -> None:
        if len(self.left) != len(self.right):
            raise ValueError(
                f"{len(self.left)} columns on the left and {len(self.right)} on the "
                "right; a match key pairs columns, so the two must correspond"
            )
        if not self.left:
            raise ValueError(
                "a match key with no columns matches every row against every other, "
                "which is not a reconciliation"
            )

    def of_left(self, row: Mapping[str, Any]) -> tuple[Any, ...]:
        return tuple(_key_part(row.get(column)) for column in self.left)

    def of_right(self, row: Mapping[str, Any]) -> tuple[Any, ...]:
        return tuple(_key_part(row.get(column)) for column in self.right)

    def render(self) -> str:
        return ", ".join(
            left if left == right else f"{left} = {right}"
            for left, right in zip(self.left, self.right, strict=True)
        )

    def to_dict(self) -> dict[str, Any]:
        return {"left": list(self.left), "right": list(self.right)}


@dataclasses.dataclass(frozen=True, slots=True)
class Pair:
    """Two sides of one key, ready to be compared."""

    key: tuple[Any, ...]
    left: tuple[Mapping[str, Any], ...]
    right: tuple[Mapping[str, Any], ...]
    #: The key the right side was found under, when it differed. Set only by a
    #: tolerance match, and it is what makes timing detectable at all: the
    #: comparison sees two amounts and cannot tell whether they were booked on
    #: the same day, where the matcher knows because it had to look next door.
    matched_key: tuple[Any, ...] | None = None

    @property
    def matched_by_tolerance(self) -> bool:
        return self.matched_key is not None and self.matched_key != self.key

    @property
    def cardinality(self) -> Cardinality:
        many_left, many_right = len(self.left) > 1, len(self.right) > 1
        if many_left and many_right:
            return Cardinality.MANY_TO_MANY
        if many_left:
            return Cardinality.MANY_TO_ONE
        if many_right:
            return Cardinality.ONE_TO_MANY
        return Cardinality.ONE_TO_ONE

    @property
    def is_aggregated(self) -> bool:
        return self.cardinality.needs_aggregation

    def render_key(self) -> str:
        return " / ".join(str(part) for part in self.key)


@dataclasses.dataclass(frozen=True, slots=True)
class Unmatched:
    """A key present on one side and not the other."""

    key: tuple[Any, ...]
    side: str
    rows: tuple[Mapping[str, Any], ...]

    def render_key(self) -> str:
        return " / ".join(str(part) for part in self.key)


@dataclasses.dataclass(frozen=True, slots=True)
class MatchReport:
    """How the two sides lined up, before anything is compared."""

    pairs: tuple[Pair, ...] = ()
    unmatched_left: tuple[Unmatched, ...] = ()
    unmatched_right: tuple[Unmatched, ...] = ()
    left_rows: int = 0
    right_rows: int = 0
    key: MatchKey | None = None

    @property
    def matched_rows(self) -> int:
        return sum(len(pair.left) + len(pair.right) for pair in self.pairs)

    @property
    def match_rate(self) -> float:
        total = self.left_rows + self.right_rows
        return self.matched_rows / total if total else 1.0

    @property
    def aggregated_pairs(self) -> int:
        return sum(1 for pair in self.pairs if pair.is_aggregated)

    @property
    def looks_misconfigured(self) -> bool:
        """Whether the match rate says this is a configuration problem.

        The question to answer before anybody opens the break list. A
        reconciliation between two systems that are meant to agree matches
        almost everything; a tenth failing to match is a mapping gap, and the
        breaks it produces are artefacts of that gap rather than findings.
        """
        return self.match_rate < POOR_MATCH_RATE

    def describe(self) -> str:
        head = (
            f"{len(self.pairs):,} keys matched across {self.left_rows:,} and "
            f"{self.right_rows:,} rows ({self.match_rate:.1%})"
        )
        if self.aggregated_pairs:
            head += (
                f"; {self.aggregated_pairs:,} of them compare totals rather than rows, "
                f"because the key repeats on at least one side"
            )
        if self.looks_misconfigured:
            head += (
                f". A match rate this low is a configuration problem rather than a "
                f"break population — {len(self.unmatched_left):,} keys are on the left "
                f"only and {len(self.unmatched_right):,} on the right only, and every "
                f"one of them will look like a break of its whole value"
            )
        return head

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key.to_dict() if self.key else None,
            "pairs": len(self.pairs),
            "aggregated_pairs": self.aggregated_pairs,
            "unmatched_left": len(self.unmatched_left),
            "unmatched_right": len(self.unmatched_right),
            "left_rows": self.left_rows,
            "right_rows": self.right_rows,
            "match_rate": round(self.match_rate, 6),
            "looks_misconfigured": self.looks_misconfigured,
            "summary": self.describe(),
        }


class Matcher:
    """Groups both sides by key and pairs the groups up."""

    def __init__(self, key: MatchKey) -> None:
        self._key = key

    def match(
        self,
        left: Sequence[Mapping[str, Any]],
        right: Sequence[Mapping[str, Any]],
    ) -> MatchReport:
        left_groups = self._group(left, self._key.of_left)
        right_groups = self._group(right, self._key.of_right)

        pairs: list[Pair] = []
        unmatched_left: list[Unmatched] = []
        unmatched_right: list[Unmatched] = []

        for key in sorted(set(left_groups) | set(right_groups), key=repr):
            on_left = left_groups.get(key)
            on_right = right_groups.get(key)
            if on_left and on_right:
                pairs.append(Pair(key=key, left=tuple(on_left), right=tuple(on_right)))
            elif on_left:
                unmatched_left.append(Unmatched(key=key, side="left", rows=tuple(on_left)))
            elif on_right:
                unmatched_right.append(Unmatched(key=key, side="right", rows=tuple(on_right)))

        return MatchReport(
            pairs=tuple(pairs),
            unmatched_left=tuple(unmatched_left),
            unmatched_right=tuple(unmatched_right),
            left_rows=len(left),
            right_rows=len(right),
            key=self._key,
        )

    @staticmethod
    def _group(
        rows: Sequence[Mapping[str, Any]], of: Any
    ) -> dict[tuple[Any, ...], list[Mapping[str, Any]]]:
        groups: dict[tuple[Any, ...], list[Mapping[str, Any]]] = {}
        for row in rows:
            groups.setdefault(of(row), []).append(row)
        return groups


class ToleranceMatcher(Matcher):
    """Matches on a key whose last component is allowed to be near.

    For the case that produces the largest phantom break population in
    practice: a trade date that is one business day apart between two systems.
    Matched exactly, every such row appears twice in the breaks — once as
    missing on the left and once as extra on the right — and the break total is
    double the real difference, which is zero.

    The near component is matched greedily and only when nothing matched it
    exactly, so a system that *does* agree on the date is never quietly paired
    with the wrong day.
    """

    def __init__(self, key: MatchKey, *, window: int = 1) -> None:
        super().__init__(key)
        self._window = window
        self._key_spec = key

    def match(
        self,
        left: Sequence[Mapping[str, Any]],
        right: Sequence[Mapping[str, Any]],
    ) -> MatchReport:
        exact = super().match(left, right)
        if not exact.unmatched_left or not exact.unmatched_right:
            return exact

        remaining_right = {u.key: u for u in exact.unmatched_right}
        pairs = list(exact.pairs)
        still_left: list[Unmatched] = []

        for candidate in exact.unmatched_left:
            partner = self._nearby(candidate.key, remaining_right)
            if partner is None:
                still_left.append(candidate)
                continue
            found = remaining_right.pop(partner)
            pairs.append(
                Pair(
                    key=candidate.key,
                    left=candidate.rows,
                    right=found.rows,
                    matched_key=partner,
                )
            )

        return MatchReport(
            pairs=tuple(pairs),
            unmatched_left=tuple(still_left),
            unmatched_right=tuple(remaining_right.values()),
            left_rows=exact.left_rows,
            right_rows=exact.right_rows,
            key=self._key_spec,
        )

    def _nearby(
        self, key: tuple[Any, ...], candidates: Mapping[tuple[Any, ...], Unmatched]
    ) -> tuple[Any, ...] | None:
        head, tail = key[:-1], key[-1]
        for offset in range(1, self._window + 1):
            for shifted in (_shift(tail, offset), _shift(tail, -offset)):
                if shifted is None:
                    continue
                probe = (*head, shifted)
                if probe in candidates:
                    return probe
        return None


def aggregate(rows: Sequence[Mapping[str, Any]], column: str) -> Decimal:
    """Total one side of a pair, skipping nothing silently.

    A null in an amount column is not zero. Treating it as zero makes the
    aggregate wrong by exactly the missing amount and the break looks like a
    value difference, when the finding is that a row has no amount at all.
    """
    total = Decimal(0)
    for row in rows:
        value = row.get(column)
        if value is None:
            raise ValueError(
                f"a row has no {column}, and treating that as zero would turn a "
                f"missing value into a value difference of exactly the wrong size"
            )
        total += Decimal(str(value))
    return total


def _key_part(value: Any) -> Any:
    """Normalise a key component so 1 and '1' are the same key.

    The most common cause of a zero-match reconciliation: one side reads a
    column as an integer and the other as text, the keys never collide, and
    every row on both sides is reported as unmatched.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int | Decimal | float):
        # `format(d, "f")` and not `str(d.normalize())`. normalize() strips
        # trailing zeros by *raising the exponent*, so 1000 renders as '1E+3'
        # and 250 as '2.5E+2' while the text side of the same key stays
        # '1000' and '250'. The keys then never collide — for round numbers
        # only, so a reconciliation matches most of its rows and reports the
        # rest as breaks on both sides. Positional format has no exponent.
        as_decimal = Decimal(str(value)).normalize()
        return format(as_decimal, "f")
    return str(value).strip()


def _shift(value: Any, offset: int) -> Any:
    """Move a date-like or numeric key component by an offset."""
    from datetime import date, datetime

    if isinstance(value, str):
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            return None
        return date.fromordinal(parsed.toordinal() + offset).isoformat()
    if isinstance(value, datetime):
        return None
    if isinstance(value, date):
        return date.fromordinal(value.toordinal() + offset)
    return None
