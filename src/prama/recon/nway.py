"""Three or more sides, and balances that must roll forward.

`FR-REC-005`. Two-sided reconciliation is the common case and not the whole
job. Two shapes turn up constantly and neither reduces to a pair of two-way
runs without losing the thing that mattered.

**N-way.** A trade appears in the front office, the sub-ledger and the GL. Run
as three pairwise reconciliations that is three break populations, and a record
missing from the middle system appears in two of them — so the same problem is
counted twice, and the two entries look like separate items to whoever is
working the queue. Run N-way it is one finding that names *which* side is the
odd one out, which is the whole question.

**Roll-forward.** Opening plus movements equals closing. It is not a comparison
between two systems but between two *periods* of one, and the failure it
catches is invisible to any single-period control: yesterday's closing was
correct, today's closing is correct, and the movements between them do not
account for the difference. Something was restated and nobody said so.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from typing import Any

from prama.recon.classify import Break, BreakKind
from prama.semantic.relationships import Tolerance


@dataclasses.dataclass(frozen=True, slots=True)
class SidePosition:
    """What one system says about one key."""

    side: str
    total: Decimal | None
    rows: int = 0

    @property
    def present(self) -> bool:
        return self.total is not None


@dataclasses.dataclass(frozen=True, slots=True)
class Disagreement:
    """One key, across every side, with the odd one named.

    Naming the odd side is the point. Three pairwise runs produce three break
    populations in which a record missing from the middle system appears twice,
    and the two entries look like separate items to whoever is working the
    queue.
    """

    key: str
    positions: tuple[SidePosition, ...]
    #: The side that disagrees with the others, when exactly one does. Empty
    #: when they all disagree, which is a different and worse situation.
    odd_side: str = ""
    #: The value the majority agree on, when there is a majority.
    consensus: Decimal | None = None

    @property
    def missing_from(self) -> tuple[str, ...]:
        return tuple(item.side for item in self.positions if not item.present)

    @property
    def all_disagree(self) -> bool:
        return not self.odd_side and self.consensus is None

    def describe(self) -> str:
        if self.missing_from:
            return (
                f"{self.key}: present in "
                f"{', '.join(item.side for item in self.positions if item.present)} "
                f"and missing from {', '.join(self.missing_from)}"
            )
        if self.odd_side:
            odd = next(item for item in self.positions if item.side == self.odd_side)
            return (
                f"{self.key}: {self.odd_side} says {odd.total:,.2f} where the others "
                f"agree on {self.consensus:,.2f} — one side is wrong rather than three "
                f"disagreeing"
            )
        return (
            f"{self.key}: every side disagrees ("
            + ", ".join(f"{item.side} {item.total:,.2f}" for item in self.positions if item.present)
            + "), which is not one system being wrong and needs a person"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "positions": [
                {
                    "side": item.side,
                    "total": str(item.total) if item.present else None,
                    "rows": item.rows,
                }
                for item in self.positions
            ],
            "odd_side": self.odd_side,
            "consensus": str(self.consensus) if self.consensus is not None else None,
            "missing_from": list(self.missing_from),
            "all_disagree": self.all_disagree,
            "description": self.describe(),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class NWayResult:
    sides: tuple[str, ...]
    disagreements: tuple[Disagreement, ...] = ()
    keys: int = 0

    def __len__(self) -> int:
        return len(self.disagreements)

    @property
    def by_odd_side(self) -> dict[str, int]:
        """How often each side is the odd one out.

        The number that identifies a broken system rather than a broken record:
        one side being the odd one out four hundred times is that side's
        problem, and no pairwise view makes it visible.
        """
        counts: dict[str, int] = {}
        for item in self.disagreements:
            if item.odd_side:
                counts[item.odd_side] = counts.get(item.odd_side, 0) + 1
        return counts

    def describe(self) -> str:
        if not self.disagreements:
            return f"all {len(self.sides)} sides agree across {self.keys:,} keys"
        head = (
            f"{len(self.disagreements):,} of {self.keys:,} keys disagree across "
            f"{', '.join(self.sides)}"
        )
        odd = self.by_odd_side
        if odd:
            worst = max(odd, key=lambda side: odd[side])
            head += (
                f"; {worst} is the odd one out {odd[worst]:,} times, which points at "
                f"that system rather than at the records"
            )
        return head

    def to_dict(self) -> dict[str, Any]:
        return {
            "sides": list(self.sides),
            "keys": self.keys,
            "disagreements": [item.to_dict() for item in self.disagreements],
            "by_odd_side": self.by_odd_side,
            "summary": self.describe(),
        }


def reconcile_n_way(
    sides: Mapping[str, Mapping[str, Decimal | None]],
    tolerance: Tolerance,
) -> NWayResult:
    """Compare three or more sides on the same keys.

    Takes already-keyed totals rather than rows, because matching and
    normalisation are the two-way engine's job and doing them again here would
    be a second implementation of both — which would drift, and the drift would
    show as N-way and two-way disagreeing about the same data.
    """
    names = tuple(sides)
    keys = sorted({key for side in sides.values() for key in side})
    disagreements: list[Disagreement] = []

    for key in keys:
        positions = tuple(SidePosition(side=name, total=sides[name].get(key)) for name in names)
        present = [item for item in positions if item.present]
        if len(present) < len(positions):
            disagreements.append(Disagreement(key=key, positions=positions))
            continue
        if _all_agree(present, tolerance):
            continue
        odd, consensus = _odd_one_out(present, tolerance)
        disagreements.append(
            Disagreement(key=key, positions=positions, odd_side=odd, consensus=consensus)
        )

    return NWayResult(sides=names, disagreements=tuple(disagreements), keys=len(keys))


def _all_agree(positions: Sequence[SidePosition], tolerance: Tolerance) -> bool:
    first = positions[0].total
    assert first is not None
    return all(
        # The third and last conversion in this module. `_all_agree` decides
        # whether an n-way reconciliation balances at all. `Q-78`.
        tolerance.permits(item.total - first, first)  # type: ignore[operator]
        for item in positions[1:]
    )


def _odd_one_out(
    positions: Sequence[SidePosition], tolerance: Tolerance
) -> tuple[str, Decimal | None]:
    """The side that disagrees with a majority, if exactly one does.

    A majority rather than any two: with three sides two agreeing is a
    majority, and with four sides two agreeing is a tie that names nothing.
    Reporting a tie as an odd-one-out would send somebody to a system chosen
    by iteration order.
    """
    for candidate in positions:
        others = [item for item in positions if item.side != candidate.side]
        if len(others) < 2:
            continue
        reference = others[0].total
        assert reference is not None
        if all(
            # Exact here too. This one decides which side is the odd one out,
            # so a float rounding picks a different side to blame. `Q-78`.
            tolerance.permits(item.total - reference, reference)  # type: ignore[operator]
            for item in others[1:]
        ):
            return candidate.side, reference
    return "", None


# ---------------------------------------------------------------------------
# Roll-forward
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class RollForward:
    """Opening plus movements against closing, for one key and period."""

    key: str
    opening: Decimal
    movements: Decimal
    closing: Decimal
    period: date | None = None

    @property
    def expected(self) -> Decimal:
        return self.opening + self.movements

    @property
    def difference(self) -> Decimal:
        return self.closing - self.expected

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "opening": str(self.opening),
            "movements": str(self.movements),
            "closing": str(self.closing),
            "expected": str(self.expected),
            "difference": str(self.difference),
            "period": self.period.isoformat() if self.period else None,
        }


def check_roll_forward(entries: Sequence[RollForward], tolerance: Tolerance) -> tuple[Break, ...]:
    """Breaks where the movements do not account for the change.

    The failure this catches is invisible to any single-period control:
    yesterday's closing was right, today's closing is right, and the movements
    between them do not explain the difference. Something was restated and
    nobody said so — which is the finding, and it exists only between the
    periods rather than in either of them.
    """
    breaks: list[Break] = []
    for entry in entries:
        # Exact, like the two-sided classifier: this is a verdict boundary too,
        # and n-way differences are sums of Decimals that float rounds. `Q-78`.
        if tolerance.permits(entry.difference, entry.expected or Decimal(1)):
            continue
        breaks.append(
            Break(
                key=entry.key,
                kind=BreakKind.GENUINE,
                left=entry.expected,
                right=entry.closing,
                because=(
                    f"opening {entry.opening:,.2f} plus movements "
                    f"{entry.movements:,.2f} is {entry.expected:,.2f}, and the closing "
                    f"balance is {entry.closing:,.2f}. Both balances may be correct on "
                    f"their own day; what is missing is a movement that explains the "
                    f"difference, which usually means a restatement nobody recorded"
                ),
            )
        )
    return tuple(breaks)


def opening_from(previous_closing: Mapping[str, Decimal]) -> Mapping[str, Decimal]:
    """Yesterday's closing is today's opening. Stated because it is assumed.

    A roll-forward built on an opening balance re-read from the source rather
    than carried from the previous close cannot detect a restatement at all:
    the restated opening agrees with the restated closing, and the check passes
    over exactly the thing it exists to catch.
    """
    return dict(previous_closing)
