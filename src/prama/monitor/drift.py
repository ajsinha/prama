"""Distributions that moved, and deciding whether the move is the new normal.

`FR-MON-003` and `FR-MON-004`. A drift measure answers a different question
from a monitor: not "is today unusual?" but "has the shape of normal changed?".
The distinction matters operationally, because the two have opposite responses.
An unusual day is an incident to investigate. A changed distribution is either
an incident *or* a business change, and the second is resolved by telling the
system so — after which the old normal must stop being the standard, or every
day for the next six months is an alert.

**"Accept the new normal" is annotated permanently, and that is the whole
feature.** A system that lets somebody silence a drift and forgets they did it
has a hole in its audit trail exactly where the interesting question lives: the
next person to ask "when did this change and who agreed?" gets nothing. So an
acceptance is a record with a name, a date and a reason, it stays attached to
the metric, and a report six months later still shows the step and who signed
for it.

Five measures because they disagree usefully. PSI is what risk teams already
read and is unstable on small samples; KS is distribution-free and insensitive
to the tails, which is where money lives; Wasserstein is in the units of the
data, which makes it the one a person understands; Jensen-Shannon is bounded
and symmetric; chi-square is the right one for categories. Reporting several
and their disagreement is more honest than picking one and calling it the
answer.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Sequence
from typing import Any

#: Bins for the histogram measures. Ten is what risk teams use for PSI, and
#: matching the convention matters more here than an optimal choice would:
#: a PSI that disagrees with the one in somebody's spreadsheet is a PSI nobody
#: will act on.
DEFAULT_BINS = 10

#: PSI above this is the industry's "significant shift". Quoted rather than
#: invented, for the same reason.
PSI_SHIFT = 0.2

#: Below this many observations on either side, no drift measure is reported.
#: PSI in particular is wildly unstable on small samples and will report a
#: shift between two draws from the same distribution.
MINIMUM_SAMPLE = 50


@dataclasses.dataclass(frozen=True, slots=True)
class DriftMeasure:
    name: str
    value: float
    #: Whether this measure considers the shift material, by its own
    #: convention. Deliberately per-measure: they disagree, and averaging their
    #: verdicts into one would hide the disagreement that is the useful signal.
    material: bool
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "measure": self.name,
            "value": round(self.value, 6),
            "material": self.material,
            "explanation": self.explanation,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class DriftReport:
    """How far a distribution has moved, by several measures that disagree."""

    measures: tuple[DriftMeasure, ...] = ()
    reference_size: int = 0
    current_size: int = 0
    refusal: str = ""

    @property
    def material(self) -> tuple[str, ...]:
        return tuple(m.name for m in self.measures if m.material)

    @property
    def is_material(self) -> bool:
        """Material when a majority of the measures say so.

        A majority rather than any, because each has a failure mode the others
        do not share, and a single measure firing alone is more often that
        measure's weakness than a real shift.
        """
        return len(self.material) * 2 > len(self.measures)

    @property
    def disagreement(self) -> str:
        """What the measures disagree about, when they do. The useful part."""
        if not self.measures or len(self.material) in (0, len(self.measures)):
            return ""
        quiet = [m.name for m in self.measures if not m.material]
        return (
            f"{', '.join(self.material)} see a shift and {', '.join(quiet)} do not, "
            f"which usually means the change is in a part of the distribution only "
            f"some of them look at"
        )

    def describe(self) -> str:
        if self.refusal:
            return self.refusal
        head = "; ".join(m.explanation for m in self.measures)
        return head + (f". {self.disagreement}" if self.disagreement else "")

    def to_dict(self) -> dict[str, Any]:
        return {
            "measures": [m.to_dict() for m in self.measures],
            "material": list(self.material),
            "is_material": self.is_material,
            "disagreement": self.disagreement,
            "reference_size": self.reference_size,
            "current_size": self.current_size,
            "refusal": self.refusal,
            "summary": self.describe(),
        }


def compare(
    reference: Sequence[float],
    current: Sequence[float],
    *,
    bins: int = DEFAULT_BINS,
    minimum: int = MINIMUM_SAMPLE,
) -> DriftReport:
    """Every measure, over the same two samples."""
    if len(reference) < minimum or len(current) < minimum:
        return DriftReport(
            reference_size=len(reference),
            current_size=len(current),
            refusal=(
                f"no drift measure is reported below {minimum} observations a side "
                f"({len(reference)} against {len(current)}); PSI in particular will "
                f"report a shift between two draws from the same distribution"
            ),
        )
    edges = _edges(reference, bins)
    expected = _histogram(reference, edges)
    observed = _histogram(current, edges)
    return DriftReport(
        measures=(
            _psi(expected, observed),
            _kolmogorov_smirnov(reference, current),
            _wasserstein(reference, current),
            _jensen_shannon(expected, observed),
            _chi_square(expected, observed, len(current)),
        ),
        reference_size=len(reference),
        current_size=len(current),
    )


# ---------------------------------------------------------------------------
# Accepting a new normal
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class Changepoint:
    """Where a series changed level, and by how much."""

    index: int
    before: float
    after: float
    #: How strong the evidence is, in units of the series' own variability.
    strength: float

    @property
    def ratio(self) -> float:
        return self.after / self.before if self.before else math.inf

    def describe(self) -> str:
        direction = "rose" if self.after > self.before else "fell"
        return (
            f"the level {direction} from about {self.before:,.0f} to {self.after:,.0f} "
            f"at observation {self.index}, a {abs(self.ratio - 1):.0%} change"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "before": round(self.before, 4),
            "after": round(self.after, 4),
            "ratio": round(self.ratio, 4) if math.isfinite(self.ratio) else None,
            "strength": round(self.strength, 4),
            "description": self.describe(),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Acceptance:
    """A person deciding that a shift is the new normal, recorded for good.

    The whole feature. A system that lets somebody silence a drift and then
    forgets they did it has a hole in its audit trail exactly where the
    interesting question lives — "when did this change, and who agreed?" — and
    the answer six months later is nothing.
    """

    metric: str
    #: The observation index, and the date it corresponds to.
    at_index: int
    at: str
    accepted_by: str
    accepted_at: str
    #: Why. Free text, and required: an acceptance with no reason is a
    #: silencing, and the difference is exactly what the record exists to
    #: preserve.
    reason: str
    before: float = 0.0
    after: float = 0.0

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError(
                "accepting a new normal requires a reason. Without one the record "
                "cannot distinguish a business change from somebody silencing an "
                "alert, which is the only question anybody asks about it later"
            )

    def annotation(self) -> str:
        """What a chart shows at this point, for as long as the chart exists."""
        return (
            f"{self.at}: new normal accepted by {self.accepted_by} "
            f"({self.before:,.0f} → {self.after:,.0f}) — {self.reason}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "at_index": self.at_index,
            "at": self.at,
            "accepted_by": self.accepted_by,
            "accepted_at": self.accepted_at,
            "reason": self.reason,
            "before": self.before,
            "after": self.after,
            "annotation": self.annotation(),
        }


def find_changepoint(values: Sequence[float], *, minimum_segment: int = 20) -> Changepoint | None:
    """The single most likely place the level changed.

    A one-break search rather than a full segmentation, because that is the
    operational question: "did something change, and when?" is answerable and
    actionable, where "here are seven candidate breaks" is a research output.
    """
    if len(values) < 2 * minimum_segment:
        return None
    best: Changepoint | None = None
    total_spread = _spread(values) or 1.0
    for split in range(minimum_segment, len(values) - minimum_segment):
        left, right = values[:split], values[split:]
        before = sum(left) / len(left)
        after = sum(right) / len(right)
        # The gap in means, in units of the pooled variability. Larger is a
        # cleaner break; the strongest one wins.
        strength = abs(after - before) / total_spread
        if best is None or strength > best.strength:
            best = Changepoint(index=split, before=before, after=after, strength=strength)
    return best


def history_after(values: Sequence[float], acceptances: Sequence[Acceptance]) -> Sequence[float]:
    """The history a monitor should calibrate against, given what was accepted.

    Everything before the most recent accepted changepoint is discarded — not
    hidden, discarded, and only from *this* calculation. The chart still shows
    it and the annotation still explains it; what stops is treating the old
    regime as evidence about the new one, which is the thing that makes a
    monitor alert every day for six months after a business change.
    """
    if not acceptances:
        return values
    latest = max(acceptance.at_index for acceptance in acceptances)
    return values[latest:] if latest < len(values) else values


# ---------------------------------------------------------------------------
# The measures
# ---------------------------------------------------------------------------


def _edges(values: Sequence[float], bins: int) -> list[float]:
    ordered = sorted(values)
    return [
        ordered[min(len(ordered) - 1, index * len(ordered) // bins)] for index in range(1, bins)
    ]


def _histogram(values: Sequence[float], edges: Sequence[float]) -> list[float]:
    counts = [0.0] * (len(edges) + 1)
    for value in values:
        index = 0
        while index < len(edges) and value > edges[index]:
            index += 1
        counts[index] += 1
    total = sum(counts) or 1.0
    return [count / total for count in counts]


def _psi(expected: Sequence[float], observed: Sequence[float]) -> DriftMeasure:
    """Population stability index — what risk teams already read.

    The epsilon is not a nicety: an empty bin gives a logarithm of zero, and
    without it PSI is infinite whenever the current sample misses a bin the
    reference had, which happens constantly on small samples and makes the
    number useless exactly when it is most quoted.
    """
    epsilon = 1e-6
    value = sum(
        (o - e) * math.log(max(o, epsilon) / max(e, epsilon))
        for e, o in zip(expected, observed, strict=True)
    )
    return DriftMeasure(
        name="psi",
        value=value,
        material=value >= PSI_SHIFT,
        explanation=(
            f"PSI {value:.3f}"
            + (" — a significant shift by the usual convention" if value >= PSI_SHIFT else "")
        ),
    )


def _kolmogorov_smirnov(reference: Sequence[float], current: Sequence[float]) -> DriftMeasure:
    combined = sorted({*reference, *current})
    statistic = 0.0
    for point in combined:
        left = sum(1 for value in reference if value <= point) / len(reference)
        right = sum(1 for value in current if value <= point) / len(current)
        statistic = max(statistic, abs(left - right))
    # The 5% critical value for the two-sample test.
    critical = 1.36 * math.sqrt((len(reference) + len(current)) / (len(reference) * len(current)))
    return DriftMeasure(
        name="ks",
        value=statistic,
        material=statistic > critical,
        explanation=(
            f"the distributions differ by at most {statistic:.3f} at any point "
            f"(5% critical value {critical:.3f})"
        ),
    )


def _wasserstein(reference: Sequence[float], current: Sequence[float]) -> DriftMeasure:
    """Earth mover's distance — the one in the units of the data.

    Which makes it the one a person understands: "the typical row count moved
    by 4,100" is a sentence, where "PSI 0.31" is a number somebody has to be
    trained to read.
    """
    left, right = sorted(reference), sorted(current)
    size = max(len(left), len(right))
    total = 0.0
    for index in range(size):
        a = left[min(index * len(left) // size, len(left) - 1)]
        b = right[min(index * len(right) // size, len(right) - 1)]
        total += abs(a - b)
    distance = total / size
    scale = _spread(reference) or 1.0
    return DriftMeasure(
        name="wasserstein",
        value=distance,
        material=distance > scale,
        explanation=f"the distribution moved by about {distance:,.1f} in its own units",
    )


def _jensen_shannon(expected: Sequence[float], observed: Sequence[float]) -> DriftMeasure:
    middle = [(e + o) / 2 for e, o in zip(expected, observed, strict=True)]
    divergence = 0.5 * _kl(expected, middle) + 0.5 * _kl(observed, middle)
    value = math.sqrt(max(0.0, divergence))
    return DriftMeasure(
        name="jensen_shannon",
        value=value,
        material=value > 0.1,
        explanation=f"Jensen-Shannon distance {value:.3f} (bounded 0 to 1)",
    )


def _chi_square(expected: Sequence[float], observed: Sequence[float], size: int) -> DriftMeasure:
    statistic = (
        sum(((o - e) ** 2) / max(e, 1e-9) for e, o in zip(expected, observed, strict=True)) * size
    )
    degrees = max(1, len(expected) - 1)
    # Wilson-Hilferty: a chi-square with d degrees of freedom is roughly normal
    # after a cube root, which avoids needing the full distribution here.
    normalised = ((statistic / degrees) ** (1 / 3) - (1 - 2 / (9 * degrees))) / math.sqrt(
        2 / (9 * degrees)
    )
    return DriftMeasure(
        name="chi_square",
        value=statistic,
        material=normalised > 1.96,
        explanation=f"chi-square {statistic:,.1f} on {degrees} degrees of freedom",
    )


def _kl(left: Sequence[float], right: Sequence[float]) -> float:
    epsilon = 1e-12
    return sum(
        a * math.log(max(a, epsilon) / max(b, epsilon))
        for a, b in zip(left, right, strict=True)
        if a > 0
    )


def _spread(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))
