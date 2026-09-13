"""Scores that mean something, and say which arithmetic produced them.

`FR-SCR-001`…`006`. A single number for the quality of a dataset is what every
buyer asks for and the thing most likely to be quietly wrong. Three failures
account for almost all of it:

**An unweighted average is dominated by whatever there is most of.** A dataset
with one Tier 1 CDE and fifty informational columns scores 98% when the CDE is
completely broken, because fifty columns are fine. The number is arithmetically
correct and answers a question nobody asked.

**A composite hides which dimension failed.** "Quality 91%" is not actionable;
"completeness 99%, validity 62%" is. The composite exists to be tracked over
time and compared across datasets, not to be the thing somebody reads before
acting, and a system that offers only the composite has made the wrong trade.

**Different composites disagree, and the disagreement is information.** The
mean says the average column is fine. The minimum says something is badly
broken. The weighted mean says the important things are fine. All three can be
true at once, and publishing one without naming it is how a score becomes
disputed at exactly the moment somebody needs to rely on it.

So: dimensions first, composites named, materiality applied, and an SLO with an
error budget that depletes — because "99.5% complete" is a promise, and a
promise without a budget attached is a wish.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
from collections.abc import Mapping, Sequence
from typing import Any

from prama.pql import ast
from prama.semantic.values import Criticality

#: Weight by criticality. Tier 1 counts sixteen times Tier 4, and the gap is
#: deliberately steep: a regulatory CDE and an informational column are not
#: within a factor of two of each other in anybody's mind, and a gentle weight
#: produces a score that still moves mostly with column count.
CRITICALITY_WEIGHT: dict[Criticality, float] = {
    Criticality.TIER_1: 16.0,
    Criticality.TIER_2: 8.0,
    Criticality.TIER_3: 2.0,
    Criticality.TIER_4: 1.0,
}


class Method(enum.Enum):
    """How dimension scores become one number."""

    #: The arithmetic mean. Says what the average column looks like, and is
    #: dominated by whatever there is most of.
    MEAN = "mean"
    #: The worst dimension. Says whether anything is badly broken, and ignores
    #: how much of the estate is fine.
    MINIMUM = "minimum"
    #: Weighted by materiality. Says whether the things that matter are fine,
    #: which is usually the question — and is the one that can be argued with,
    #: because somebody chose the weights.
    WEIGHTED = "weighted"

    @property
    def answers(self) -> str:
        return {
            Method.MEAN: "what does the average column look like",
            Method.MINIMUM: "is anything badly broken",
            Method.WEIGHTED: "are the things that matter fine",
        }[self]


@dataclasses.dataclass(frozen=True, slots=True)
class Measurement:
    """One control's contribution: rows checked, rows that failed."""

    control: str
    dimension: ast.Dimension
    scanned: int
    violations: int
    criticality: Criticality = Criticality.TIER_4
    #: A control that did not run contributes nothing and is not a pass. The
    #: distinction matters: a dataset scoring 100% because half its controls
    #: were skipped is the most misleading output this module could produce.
    ran: bool = True

    @property
    def measured(self) -> bool:
        """Whether this control produced evidence about anything.

        A control that ran over zero rows did not. It is the same claim as
        ``ran=False`` wearing a different hat, and the commoner one: a delivery
        that did not arrive, a partition filter that matched nothing, an
        extract that failed in a way the connector reported as success.
        """
        return self.ran and self.scanned > 0

    @property
    def rate(self) -> float:
        """Pass rate, and **zero** when nothing was scanned.

        Not 1.0, which is what this returned and what made an empty scan a
        perfect score. Callers that should not be averaging a no-evidence
        control at all use :attr:`measured`; the zero is the safe answer for
        anything that reaches for the rate regardless.
        """
        if not self.scanned:
            return 0.0
        return 1.0 - self.violations / self.scanned

    @property
    def weight(self) -> float:
        return CRITICALITY_WEIGHT[self.criticality]

    def to_dict(self) -> dict[str, Any]:
        return {
            "control": self.control,
            "dimension": self.dimension.value,
            "scanned": self.scanned,
            "violations": self.violations,
            "criticality": int(self.criticality),
            "ran": self.ran,
            "measured": self.measured,
            "rate": round(self.rate, 6),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class DimensionScore:
    dimension: ast.Dimension
    score: float
    controls: int
    scanned: int
    violations: int

    def describe(self) -> str:
        return (
            f"{self.dimension.value} {self.score:.1%} "
            f"({self.violations:,} of {self.scanned:,} rows across "
            f"{self.controls} control{'s' if self.controls != 1 else ''})"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension.value,
            "score": round(self.score, 6),
            "controls": self.controls,
            "scanned": self.scanned,
            "violations": self.violations,
            "description": self.describe(),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Score:
    """A dataset's quality, by dimension and by every composite."""

    dataset: str
    dimensions: tuple[DimensionScore, ...] = ()
    composites: Mapping[Method, float] = dataclasses.field(default_factory=dict)
    #: Controls that did not run. Reported rather than skipped, because a
    #: dataset scoring 100% on half its controls is the most misleading number
    #: this module could produce.
    not_run: int = 0
    #: Controls that ran and scanned nothing. Counted separately from
    #: :attr:`not_run` because the two need different remedies — one is a
    #: scheduling or connectivity problem, the other is a delivery that did not
    #: arrive or a filter that matched no rows — but they make the same claim
    #: about the score, which is that it does not cover this control.
    scanned_nothing: int = 0
    controls: int = 0

    @property
    def coverage(self) -> float:
        """The share of intended controls this score actually describes.

        Both a control that did not run and one that scanned nothing are
        outside it. A score covering half the controls is not a score of the
        dataset, and coverage is the number that says so.
        """
        if not self.controls:
            return 0.0
        return (self.controls - self.not_run - self.scanned_nothing) / self.controls

    @property
    def worst(self) -> DimensionScore | None:
        return min(self.dimensions, key=lambda item: item.score) if self.dimensions else None

    def composite(self, method: Method = Method.WEIGHTED) -> float:
        return self.composites.get(method, 0.0)

    @property
    def methods_disagree(self) -> bool:
        """Whether the composites tell different stories.

        Worth surfacing rather than resolving: the mean saying 98% and the
        minimum saying 62% is not a contradiction, it is the finding — most of
        the dataset is fine and one dimension is not.
        """
        if len(self.composites) < 2:
            return False
        values = list(self.composites.values())
        return max(values) - min(values) > 0.1

    def describe(self) -> str:
        if not self.dimensions:
            if self.scanned_nothing:
                return (
                    f"{self.dataset}: {self.scanned_nothing} control(s) ran and scanned no "
                    "rows, so nothing has been measured — an empty result is not a clean one"
                )
            return f"{self.dataset}: nothing has been measured"
        parts = [f"{self.dataset}: " + ", ".join(item.describe() for item in self.dimensions)]
        if self.methods_disagree:
            parts.append(
                "the composites disagree — "
                + "; ".join(
                    f"{method.value} {value:.1%} ({method.answers})"
                    for method, value in self.composites.items()
                )
                + ", which is the finding rather than a contradiction"
            )
        if self.not_run:
            parts.append(
                f"{self.not_run} of {self.controls} controls did not run, so this "
                f"score describes {self.coverage:.0%} of what was meant to be checked"
            )
        if self.scanned_nothing:
            parts.append(
                f"{self.scanned_nothing} of {self.controls} controls ran and scanned no rows, "
                "so they say nothing about this dataset either way — an empty result is not "
                "a clean one"
            )
        return ". ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "dimensions": [item.to_dict() for item in self.dimensions],
            "composites": {
                method.value: round(value, 6) for method, value in self.composites.items()
            },
            "methods_disagree": self.methods_disagree,
            "not_run": self.not_run,
            "scanned_nothing": self.scanned_nothing,
            "controls": self.controls,
            "coverage": round(self.coverage, 6),
            "summary": self.describe(),
        }


def score(dataset: str, measurements: Sequence[Measurement]) -> Score:
    """Every dimension, and every composite, from one set of measurements.

    A control that scanned no rows is excluded from the arithmetic and counted,
    exactly as one that did not run is. Including it scored it 100% — see
    `tests/score/test_composite.py::TestScanningNothingIsNotPassing`.
    """
    empty = sum(1 for item in measurements if item.ran and not item.scanned)
    ran = [item for item in measurements if item.measured]
    if not ran:
        return Score(
            dataset=dataset,
            not_run=sum(1 for item in measurements if not item.ran),
            scanned_nothing=empty,
            controls=len(measurements),
        )

    by_dimension: dict[ast.Dimension, list[Measurement]] = {}
    for item in ran:
        by_dimension.setdefault(item.dimension, []).append(item)

    dimensions = tuple(
        DimensionScore(
            dimension=dimension,
            score=_weighted_rate(items),
            controls=len(items),
            scanned=sum(item.scanned for item in items),
            violations=sum(item.violations for item in items),
        )
        for dimension, items in sorted(by_dimension.items(), key=lambda pair: pair[0].value)
    )

    scores = [item.score for item in dimensions]
    composites = {
        Method.MEAN: sum(scores) / len(scores),
        Method.MINIMUM: min(scores),
        Method.WEIGHTED: _weighted_rate(ran),
    }
    return Score(
        dataset=dataset,
        dimensions=dimensions,
        composites=composites,
        not_run=sum(1 for item in measurements if not item.ran),
        scanned_nothing=empty,
        controls=len(measurements),
    )


def _weighted_rate(items: Sequence[Measurement]) -> float:
    """Pass rate weighted by materiality.

    **Normalised within each criticality tier before the tiers are combined**,
    and that is the whole point rather than a detail. The obvious
    implementation weights each control by criticality times its row count and
    sums — and it fails at exactly the job it was written for: fifty
    informational controls over fifty million rows outweigh one Tier 1 control
    over one million, sixteen-fold weighting and all, so a completely broken
    regulatory CDE scores 91% and the "materiality-weighted" number comes out
    *higher* than the plain mean.

    Rows are evidence and criticality is importance, and multiplying them
    conflates the two. So rows weight controls *within* a tier, where more rows
    genuinely is more evidence about the same class of thing, and tiers combine
    by criticality alone — where the count of columns cannot drown the
    importance of one.
    """
    by_tier: dict[Criticality, list[Measurement]] = {}
    for item in items:
        by_tier.setdefault(item.criticality, []).append(item)
    if not by_tier:
        return 1.0

    total = 0.0
    passed = 0.0
    for tier, members in by_tier.items():
        weight = CRITICALITY_WEIGHT[tier]
        total += weight
        passed += weight * _rows_weighted(members)
    return passed / total if total else 1.0


def _rows_weighted(items: Sequence[Measurement]) -> float:
    """Pass rate within one tier, weighted by rows.

    Here the row count is the right weight and nothing else is: these are all
    the same class of thing, and a control over four million rows says more
    about the tier than one over four.
    """
    # No `max(1, scanned)` guard: a control that scanned nothing never reaches
    # here, because `score` excludes it. The guard used to give such a control
    # weight 1 and rate 1.0, which is how an empty scan diluted a real failure.
    total = sum(item.scanned for item in items)
    if not total:
        return 0.0
    return sum(item.scanned * item.rate for item in items) / total


# ---------------------------------------------------------------------------
# Service levels
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class ServiceLevel:
    """A promise about a dataset, with a budget attached.

    "99.5% complete" without a budget is a wish: nobody knows how much of the
    month's allowance a bad Tuesday used, so nobody knows whether to react. The
    budget converts the promise into a quantity that depletes, which is the
    only form in which a promise changes anybody's behaviour.
    """

    dataset: str
    dimension: ast.Dimension
    #: The promise: 0.995 for "99.5% of rows pass".
    objective: float
    #: The period the budget is measured over.
    period: str = "month"

    @property
    def budget(self) -> float:
        """The fraction of rows allowed to fail."""
        return 1.0 - self.objective

    def consumed(self, scanned: int, violations: int) -> float:
        """How much of the budget this period's failures used."""
        if not scanned or self.budget <= 0:
            return 1.0 if violations else 0.0
        return (violations / scanned) / self.budget

    def describe(self, scanned: int, violations: int) -> str:
        used = self.consumed(scanned, violations)
        allowed = int(self.budget * scanned)
        if used > 1.0:
            return (
                f"{self.dataset} {self.dimension.value}: the {self.period}'s budget is "
                f"spent and then some — {violations:,} rows failed against an allowance "
                f"of {allowed:,}. The objective of {self.objective:.1%} is missed"
            )
        if used > 0.75:
            return (
                f"{self.dataset} {self.dimension.value}: {used:.0%} of the "
                f"{self.period}'s budget used, {allowed - violations:,} rows of "
                f"allowance left. At this rate the objective is missed before the "
                f"period ends"
            )
        return (
            f"{self.dataset} {self.dimension.value}: {used:.0%} of the {self.period}'s "
            f"budget used, comfortably inside {self.objective:.1%}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "dimension": self.dimension.value,
            "objective": self.objective,
            "budget": round(self.budget, 6),
            "period": self.period,
        }
