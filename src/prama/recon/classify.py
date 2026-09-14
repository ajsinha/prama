"""What kind of break this is, before anybody spends a day on it.

`FR-REC-003`. A reconciliation that reports four thousand breaks has told
somebody almost nothing. Four thousand breaks of which three thousand nine
hundred are timing differences that clear tomorrow is a completely different
situation from four thousand genuine ones, and the two demand opposite
responses — the first is a settled process working normally, the second is an
incident.

**The cheap explanations are checked before a break is called genuine**, and
each one has a signature that is nearly free to test:

*Sign convention* is the single most common configuration mistake and the
easiest to spot: the two sides sum to approximately zero rather than
differing by approximately zero. A break of exactly twice the value is not a
data problem, and reporting it as one sends somebody to the wrong system.

*Duplication* shows as one side being an exact multiple of the other. Two is
overwhelmingly the common case, and a break that is exactly double is a posting
counted twice rather than an amount that is wrong.

*Rounding* is a difference smaller than the precision one side is stated at.

*Timing* is the record appearing on the other side on an adjacent day, which
the matcher can see and a comparison alone cannot.

*Foreign exchange* is a difference proportional to the value and consistent
across a population — one break explained by a rate is a coincidence, four
hundred with the same ratio is a rate.

Only what survives all of them is genuine, and the classification is stated
with the evidence rather than as a label, because a steward who disagrees needs
something to disagree with.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from prama.semantic.relationships import Tolerance

#: A ratio within this of a round multiple counts as that multiple. Loose
#: enough to survive a rounding difference on top of a duplication, tight
#: enough that an ordinary break is not mistaken for one.
MULTIPLE_TOLERANCE = Decimal("0.0001")

#: Breaks needed before a shared ratio is called a rate rather than a
#: coincidence. One break explained by an FX move is arithmetic; four hundred
#: with the same ratio is a missing conversion.
FX_POPULATION = 20


class BreakKind(enum.Enum):
    """Why the two sides differ."""

    TIMING = "timing"
    FX = "fx"
    ROUNDING = "rounding"
    MISSING = "missing"
    EXTRA = "extra"
    DUPLICATE = "duplicate"
    SIGN = "sign"
    GENUINE = "genuine"

    @property
    def clears_itself(self) -> bool:
        """Whether this resolves without anybody doing anything.

        Only timing. Everything else needs a person or a fix, and the
        distinction is what stops a break queue being triaged by size — a
        hundred-million-euro timing break is less urgent than a thousand-euro
        genuine one.
        """
        return self is BreakKind.TIMING

    @property
    def is_configuration(self) -> bool:
        """Whether the fault is in the reconciliation rather than the data.

        Sign, duplicate and FX breaks are usually somebody's setup being wrong.
        Routing them to a data steward wastes the steward's day and leaves the
        setup wrong.
        """
        return self in (BreakKind.SIGN, BreakKind.DUPLICATE, BreakKind.FX)

    @property
    def label(self) -> str:
        return {
            BreakKind.TIMING: "timing — expected to clear",
            BreakKind.FX: "currency conversion",
            BreakKind.ROUNDING: "rounding",
            BreakKind.MISSING: "missing from the right",
            BreakKind.EXTRA: "present only on the right",
            BreakKind.DUPLICATE: "duplicated on one side",
            BreakKind.SIGN: "sign convention",
            BreakKind.GENUINE: "genuine difference",
        }[self]


@dataclasses.dataclass(frozen=True, slots=True)
class Break:
    """One difference, classified, with the evidence for the classification."""

    key: str
    kind: BreakKind
    left: Decimal | None
    right: Decimal | None
    #: Why it was classified this way, in a sentence somebody can argue with.
    because: str
    #: What normalisation did to get here. The first question about any break
    #: is whether it is real or a translation error, and this answers it.
    normalisation: tuple[str, ...] = ()
    #: Set when the two sides had to be aggregated to be comparable.
    aggregated: bool = False

    @property
    def difference(self) -> Decimal:
        return (self.right or Decimal(0)) - (self.left or Decimal(0))

    @property
    def magnitude(self) -> Decimal:
        return abs(self.difference)

    def describe(self) -> str:
        sides = (
            f"{self.left:,.2f} against {self.right:,.2f}"
            if self.left is not None and self.right is not None
            else (
                f"{self.left:,.2f} on the left and nothing on the right"
                if self.left is not None
                else f"nothing on the left and {self.right:,.2f} on the right"
            )
        )
        head = f"{self.key}: {sides} — {self.kind.label}. {self.because}"
        if self.aggregated:
            head += (
                " These are totals: the key repeats, so the comparison is between "
                "sums rather than rows"
            )
        return head

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "kind": self.kind.value,
            "label": self.kind.label,
            "left": str(self.left) if self.left is not None else None,
            "right": str(self.right) if self.right is not None else None,
            "difference": str(self.difference),
            "because": self.because,
            "normalisation": list(self.normalisation),
            "aggregated": self.aggregated,
            "clears_itself": self.kind.clears_itself,
            "is_configuration": self.kind.is_configuration,
            "description": self.describe(),
        }


class Classifier:
    """Explains a difference with the cheapest sufficient reason."""

    def __init__(
        self,
        tolerance: Tolerance,
        *,
        rounding_places: int | None = None,
    ) -> None:
        self._tolerance = tolerance
        self._rounding_places = rounding_places

    def classify(
        self,
        key: str,
        left: Decimal | None,
        right: Decimal | None,
        *,
        normalisation: Sequence[str] = (),
        aggregated: bool = False,
        timing: bool = False,
    ) -> Break | None:
        """One difference, or None when the two sides agree."""
        common = {
            "key": key,
            "left": left,
            "right": right,
            "normalisation": tuple(normalisation),
            "aggregated": aggregated,
        }

        if left is None or right is None:
            present, missing = ("right", "left") if left is None else ("left", "right")
            # A side can have no total for two different reasons, and they are
            # different findings: the record is not there, or the record is
            # there and carries no amount. Saying "not on the left" about a row
            # that is plainly on the left sends somebody to look for a missing
            # feed instead of at the posting in front of them.
            unvalued = next((s for s in normalisation if "carry no" in s), "")
            return Break(
                kind=BreakKind.GENUINE
                if unvalued
                else (BreakKind.EXTRA if left is None else BreakKind.MISSING),
                because=(
                    unvalued
                    or (
                        f"the record is on the {present} and not the {missing}. Until "
                        f"it is known whether it is late or absent, its whole value is "
                        f"the break"
                    )
                ),
                **common,  # type: ignore[arg-type]
            )

        difference = right - left
        if self._within_tolerance(difference, left):
            return None

        if timing:
            return Break(
                kind=BreakKind.TIMING,
                because=(
                    "a matching record was found on an adjacent day, so this is the "
                    "same item recognised on different dates and is expected to clear"
                ),
                **common,  # type: ignore[arg-type]
            )

        # Sign convention first. It is the cheapest test, the most common
        # configuration error, and the one whose break is most misleading:
        # exactly twice the value, which reads as a large data problem.
        if self._within_tolerance(left + right, left):
            return Break(
                kind=BreakKind.SIGN,
                because=(
                    "the two sides sum to approximately zero rather than differing by "
                    "approximately zero, which is one side stating the opposite sign "
                    "convention. The break is twice the value and none of it is real"
                ),
                **common,  # type: ignore[arg-type]
            )

        multiple = self._exact_multiple(left, right)
        if multiple is not None:
            larger, smaller = ("right", "left") if abs(right) > abs(left) else ("left", "right")
            return Break(
                kind=BreakKind.DUPLICATE,
                because=(
                    f"the {larger} is exactly {multiple}x the {smaller}, which is a "
                    f"posting counted {multiple} times rather than an amount that is "
                    f"wrong"
                ),
                **common,  # type: ignore[arg-type]
            )

        if self._is_rounding(difference):
            return Break(
                kind=BreakKind.ROUNDING,
                because=(
                    f"the difference is smaller than the precision one side is stated "
                    f"at ({self._rounding_places} decimal places)"
                ),
                **common,  # type: ignore[arg-type]
            )

        return Break(
            kind=BreakKind.GENUINE,
            because=(
                "no sign, duplication, rounding or timing explanation fits, so the "
                "two systems disagree about this amount"
            ),
            **common,  # type: ignore[arg-type]
        )

    def _within_tolerance(self, difference: Decimal, magnitude: Decimal) -> bool:
        # No `float()`. Every amount reaching here is exact, and the tolerance
        # holds `Decimal` bounds; converting at the instant the break verdict is
        # decided is what made a difference of exactly one basis point, against a
        # one-basis-point bound, a break. QA round 4, `Q-78`.
        return self._tolerance.permits(difference, magnitude)

    @staticmethod
    def _exact_multiple(left: Decimal, right: Decimal) -> int | None:
        """Whether one side is a small whole multiple of the other."""
        if left == 0 or right == 0:
            return None
        larger, smaller = (right, left) if abs(right) > abs(left) else (left, right)
        ratio = larger / smaller
        for candidate in (2, 3, 4):
            if abs(ratio - candidate) <= MULTIPLE_TOLERANCE:
                return candidate
        return None

    def _is_rounding(self, difference: Decimal) -> bool:
        if self._rounding_places is None:
            return False
        unit = Decimal(1).scaleb(-self._rounding_places)
        return abs(difference) <= unit


def attribute_to_fx(breaks: Sequence[Break]) -> tuple[Break, ...]:
    """Reclassify a population whose differences share one ratio.

    One break explained by an exchange rate is arithmetic and could be anything.
    Four hundred breaks whose right side is 1.0873 times the left is a missing
    conversion, and calling them four hundred genuine differences sends a team
    to investigate a rate.

    Applied to the population rather than the break, because that is the level
    the evidence exists at — no individual break carries it.
    """
    candidates = [
        item
        for item in breaks
        if item.kind is BreakKind.GENUINE and item.left and item.right and item.left != 0
    ]
    if len(candidates) < FX_POPULATION:
        return tuple(breaks)

    ratios = [item.right / item.left for item in candidates]  # type: ignore[operator]
    ordered = sorted(ratios)
    median = ordered[len(ordered) // 2]
    if abs(median - 1) < Decimal("0.001"):
        return tuple(breaks)
    close = [r for r in ratios if abs(r - median) <= abs(median) * Decimal("0.001")]
    if len(close) * 2 <= len(ratios):
        return tuple(breaks)

    explained = {
        id(item)
        for item, ratio in zip(candidates, ratios, strict=True)
        if abs(ratio - median) <= abs(median) * Decimal("0.001")
    }
    return tuple(
        dataclasses.replace(
            item,
            kind=BreakKind.FX,
            because=(
                f"{len(close)} of {len(ratios)} unexplained differences share a ratio "
                f"of about {median:.6f}, which is an exchange rate rather than a "
                f"population of coincidences. The two sides are almost certainly in "
                f"different currencies"
            ),
        )
        if id(item) in explained
        else item
        for item in breaks
    )


@dataclasses.dataclass(frozen=True, slots=True)
class Population:
    """A classified break population, summarised the way it is worked."""

    breaks: tuple[Break, ...] = ()

    def __len__(self) -> int:
        return len(self.breaks)

    def of_kind(self, kind: BreakKind) -> tuple[Break, ...]:
        return tuple(item for item in self.breaks if item.kind is kind)

    @property
    def by_kind(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.breaks:
            counts[item.kind.value] = counts.get(item.kind.value, 0) + 1
        return counts

    @property
    def genuine(self) -> tuple[Break, ...]:
        return self.of_kind(BreakKind.GENUINE)

    @property
    def needs_a_person(self) -> tuple[Break, ...]:
        """Everything that will not clear itself, worst first by value."""
        return tuple(
            sorted(
                (item for item in self.breaks if not item.kind.clears_itself),
                key=lambda item: -item.magnitude,
            )
        )

    @property
    def configuration_faults(self) -> tuple[Break, ...]:
        """Breaks whose fault is the setup rather than the data.

        Routed separately, because sending them to a data steward wastes the
        steward's day and leaves the setup wrong — and because a reconciliation
        with a sign error in it is producing a break population that means
        nothing until the error is fixed.
        """
        return tuple(item for item in self.breaks if item.kind.is_configuration)

    @property
    def total_difference(self) -> Decimal:
        return sum((item.difference for item in self.breaks), Decimal(0))

    @property
    def genuine_difference(self) -> Decimal:
        return sum((item.difference for item in self.genuine), Decimal(0))

    def describe(self) -> str:
        if not self.breaks:
            return "the two sides agree"
        parts = [f"{len(self.breaks):,} breaks totalling {self.total_difference:,.2f}"]
        counts = self.by_kind
        parts.append(
            "by cause: " + ", ".join(f"{count:,} {kind}" for kind, count in sorted(counts.items()))
        )
        genuine = self.genuine
        if genuine:
            parts.append(
                f"{len(genuine):,} {'is' if len(genuine) == 1 else 'are'} genuine, "
                f"totalling {self.genuine_difference:,.2f}"
            )
        else:
            parts.append("none of them is a genuine difference")
        faults = self.configuration_faults
        if faults:
            parts.append(
                f"{len(faults):,} {'points' if len(faults) == 1 else 'point'} at the "
                f"reconciliation's own setup rather than at the data, and should be "
                f"fixed before the rest are worked"
            )
        return ". ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "breaks": len(self.breaks),
            "by_kind": self.by_kind,
            "genuine": len(self.genuine),
            "total_difference": str(self.total_difference),
            "genuine_difference": str(self.genuine_difference),
            "configuration_faults": len(self.configuration_faults),
            "summary": self.describe(),
        }
