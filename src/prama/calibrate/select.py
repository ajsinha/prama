"""Which alerts to raise, given a budget for being wrong.

`FR-MON-006` and `FR-MON-012`. A fleet of fifty thousand monitors testing at
alpha = 0.01 produces five hundred false alarms a day and is switched off in a
week. Controlling the *rate* per monitor is not the same as controlling how
many wrong alerts a person sees, and the second is the only one anybody cares
about.

Benjamini-Hochberg fixes the arithmetic: control the expected proportion of
raised alerts that are wrong, rather than the per-test error rate. But applied
flat across an estate it produces something worse than too many alerts — it
produces the *wrong shape* of alerts.

**The failure that makes hierarchy necessary.** A feed does not arrive. Four
hundred controls on that dataset fail at once, every one with a p-value at its
floor. Flat BH rejects all four hundred, and it is right to: they are all real.
The reader gets four hundred alerts describing one incident, and the one alert
that mattered — from a different dataset, about a quietly wrong LEI — is
somewhere on page nine.

So selection runs over the estate's tree. Families are tested first (domain,
then dataset), and a rejected family's children are tested at a level scaled by
how many families survived — Benjamini and Bogomolov's construction, which
controls the average FDR over the selected families rather than pretending the
tree is flat. When a family fails wholesale, the finding is reported at the
family, and the four hundred children are carried as its extent rather than as
four hundred findings.

**On dependence.** BH needs independence or positive regression dependency.
Within a dataset that is a reasonable reading — controls fail together because
the data is bad together. Across an estate it is not: a feed arriving early
makes one monitor fire and another quiet. `BY` is offered for exactly that
case, at the cost of a factor of about ``ln(m)`` in power, and which one ran is
recorded on the result. A procedure whose assumptions nobody can name is a
procedure nobody should trust.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
import math
from collections.abc import Iterable, Sequence
from typing import Any


class Method(enum.Enum):
    """Which multiple-testing procedure to run, and what it assumes."""

    #: Benjamini-Hochberg. Controls FDR under independence or positive
    #: regression dependency. The right default *within* a dataset.
    BH = "bh"
    #: Benjamini-Yekutieli. Controls FDR under arbitrary dependence, at a cost
    #: of about ln(m) in power. The right choice across an estate whose parts
    #: move in different directions.
    BY = "by"

    @property
    def assumes(self) -> str:
        return (
            "independence or positive regression dependency between the tests"
            if self is Method.BH
            else "nothing about the dependence between the tests"
        )


class Level(enum.Enum):
    """Where in the estate a finding sits."""

    DOMAIN = "domain"
    DATASET = "dataset"
    ATTRIBUTE = "attribute"
    CHECK = "check"

    @property
    def depth(self) -> int:
        return list(Level).index(self)


@dataclasses.dataclass(frozen=True, slots=True)
class Hypothesis:
    """One monitor's result, ready to be selected on.

    Named for what it is in the multiple-testing literature rather than for
    what it is in the product. It was ``Test`` first, which is both vaguer and
    a word pytest tries to collect.
    """

    identity: str
    p_value: float
    level: Level
    #: The family this belongs to: the dataset for a check, the domain for a
    #: dataset. Empty for the root.
    parent: str = ""
    label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "p_value": round(self.p_value, 6),
            "level": self.level.value,
            "parent": self.parent,
            "label": self.label,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Finding:
    """An alert that survived selection."""

    test: Hypothesis
    #: The level the test was actually compared against, after the hierarchy
    #: scaled it. Reported because "we rejected at 0.003, not the 0.01 you set"
    #: is the answer to "why did this not alert?".
    threshold: float
    #: Children this finding stands for, when it is a rolled-up family.
    covers: tuple[str, ...] = ()

    @property
    def is_rolled_up(self) -> bool:
        return bool(self.covers)

    def describe(self) -> str:
        if self.is_rolled_up:
            return (
                f"{self.test.label or self.test.identity}: {len(self.covers)} monitors "
                f"failed together, which is one incident rather than "
                f"{len(self.covers)} findings"
            )
        return (
            f"{self.test.label or self.test.identity} (p = {self.test.p_value:.4f}, "
            f"selected at {self.threshold:.4f})"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "test": self.test.to_dict(),
            "threshold": round(self.threshold, 6),
            "covers": list(self.covers),
            "rolled_up": self.is_rolled_up,
            "description": self.describe(),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Selection:
    """What was raised, at what level, under which assumptions."""

    findings: tuple[Finding, ...] = ()
    method: Method = Method.BH
    alpha: float = 0.05
    tested: int = 0
    #: Tests suppressed because their family was reported instead. Counted, so
    #: "one incident covering 400 monitors" is visible rather than looking like
    #: 399 missed alerts.
    rolled_into_parent: int = 0
    #: Families that were not opened at all, because the family test did not
    #: reject. The efficiency of the hierarchy, and also its risk.
    families_unopened: int = 0
    #: ``H(m)`` — how much sensitivity BY gave up against BH. Reported rather
    #: than left implicit, because "we assume nothing about dependence" sounds
    #: free and is not: on a large estate it is a factor of eight, and the
    #: findings it costs are the quiet ones. On the worked example BY loses a
    #: real LEI validity finding that BH raises, which is the trade made
    #: visible rather than discovered later.
    dependence_price: float = 1.0

    def __len__(self) -> int:
        return len(self.findings)

    @property
    def raised(self) -> int:
        return len(self.findings)

    def describe(self) -> str:
        return (
            f"{self.raised} findings from {self.tested:,} monitors at FDR "
            f"{self.alpha:.3f} using {self.method.value.upper()}, which assumes "
            f"{self.method.assumes}"
            + (
                f"; {self.rolled_into_parent:,} monitors rolled into a family finding"
                if self.rolled_into_parent
                else ""
            )
            + (
                f". Assuming nothing about dependence costs about a factor of "
                f"{self.dependence_price:.0f} in sensitivity, and what it costs is "
                f"the quiet findings"
                if self.method is Method.BY and self.dependence_price > 1.5
                else ""
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "findings": [f.to_dict() for f in self.findings],
            "method": self.method.value,
            "assumes": self.method.assumes,
            "alpha": round(self.alpha, 6),
            "tested": self.tested,
            "raised": self.raised,
            "rolled_into_parent": self.rolled_into_parent,
            "families_unopened": self.families_unopened,
            "dependence_price": round(self.dependence_price, 3),
            "summary": self.describe(),
        }


# ---------------------------------------------------------------------------
# The procedures
# ---------------------------------------------------------------------------


def benjamini_hochberg(
    p_values: Sequence[float], alpha: float, *, method: Method = Method.BH
) -> tuple[int, float]:
    """How many of these to reject, and the largest p-value among them.

    Returns ``(count, threshold)``. The step-up form: sort ascending, find the
    largest ``k`` with ``p_(k) <= alpha * k / m``, reject the first ``k``. The
    subtlety that catches people is that it is the *largest* such ``k``, not the
    first failure — a p-value above its line does not stop the procedure, and
    stopping there is uniformly less powerful and quietly wrong.
    """
    total = len(p_values)
    if not total:
        return 0, 0.0
    scale = _harmonic(total) if method is Method.BY else 1.0
    ordered = sorted(p_values)
    best = 0
    threshold = 0.0
    for index, value in enumerate(ordered, start=1):
        line = alpha * index / (total * scale)
        if value <= line:
            best = index
            threshold = line
    return best, threshold


def simes(p_values: Sequence[float]) -> float:
    """A single p-value for a whole family.

    ``min_i (m / i) * p_(i)``. Used to ask "is anything wrong in this dataset?"
    without asking about each control, which is what makes the hierarchy
    cheaper as well as better shaped. Valid under the same dependence
    conditions as BH, which is why the two travel together.
    """
    total = len(p_values)
    if not total:
        return 1.0
    ordered = sorted(p_values)
    return min(1.0, min((total / index) * value for index, value in enumerate(ordered, 1)))


def _harmonic(count: int) -> float:
    """``H(m) = Σ 1/i`` — the price of assuming nothing about dependence."""
    if count <= 0:
        return 1.0
    # Euler-Maclaurin; exact enough well below the point where it matters, and
    # it avoids summing a million reciprocals for a large estate.
    if count < 1000:
        return sum(1.0 / index for index in range(1, count + 1))
    return math.log(count) + 0.5772156649015329 + 1.0 / (2 * count)


# ---------------------------------------------------------------------------
# Hierarchical selection
# ---------------------------------------------------------------------------

#: When at least this fraction of a family's monitors fail, the finding is the
#: family. Set high on purpose: rolling up a partial failure hides which parts
#: are broken, and "most of the dataset" is a different message from "half of
#: it".
ROLLUP_FRACTION = 0.6

#: A family below this size is never rolled up. Three monitors failing is three
#: findings, and calling it an incident is a summary of nothing.
ROLLUP_MINIMUM = 5


class HierarchicalSelector:
    """Selects alerts over the estate tree, under a stated FDR budget."""

    def __init__(
        self,
        *,
        method: Method = Method.BH,
        rollup_fraction: float = ROLLUP_FRACTION,
        rollup_minimum: int = ROLLUP_MINIMUM,
    ) -> None:
        self._method = method
        self._rollup_fraction = rollup_fraction
        self._rollup_minimum = rollup_minimum

    def select(self, tests: Iterable[Hypothesis], alpha: float) -> Selection:
        """Raise the alerts worth raising, and roll up the ones that are one."""
        leaves = list(tests)
        if not leaves:
            return Selection(method=self._method, alpha=alpha)

        families: dict[str, list[Hypothesis]] = {}
        for test in leaves:
            families.setdefault(test.parent, []).append(test)

        # Level one: is anything wrong in each family at all? Testing the
        # family first is what stops a quiet dataset's monitors from spending
        # the estate's error budget.
        family_p = {name: simes([t.p_value for t in members]) for name, members in families.items()}
        names = sorted(family_p)
        rejected_count, _ = benjamini_hochberg(
            [family_p[name] for name in names], alpha, method=self._method
        )
        ordered_families = sorted(names, key=lambda name: family_p[name])
        opened = set(ordered_families[:rejected_count])

        # Level two: within each opened family, at a level scaled by how many
        # families survived. Benjamini and Bogomolov — the scaling is what
        # keeps the average FDR over selected families at alpha rather than
        # inflating it by the number of families examined.
        scaled = alpha * (len(opened) / len(names)) if names else alpha

        findings: list[Finding] = []
        rolled = 0
        for name in ordered_families:
            members = families[name]
            if name not in opened:
                continue
            # Whether to roll up is a question about the *shape* of the
            # family's failure, and it has to be asked before the multiplicity
            # correction rather than after.
            #
            # Asking it afterwards was a real defect: under BY, four hundred
            # controls all with p below 0.001 yielded four survivors after the
            # correction — a hundredth of the family — so no roll-up fired, and
            # the report was four arbitrary members of one incident. The
            # conservatism of the procedure had silently become a statement
            # about the incident's extent, which it is not.
            broken = [t for t in members if t.p_value <= scaled]
            if self._should_roll_up(len(broken), len(members)):
                findings.append(self._roll_up(name, broken, members, scaled))
                rolled += len(broken) - 1
                continue
            count, threshold = benjamini_hochberg(
                [t.p_value for t in members], scaled, method=self._method
            )
            if not count:
                continue
            chosen = sorted(members, key=lambda t: t.p_value)[:count]
            findings.extend(Finding(test=test, threshold=threshold) for test in chosen)

        findings.sort(key=lambda f: (f.test.p_value, f.test.identity))
        return Selection(
            findings=tuple(findings),
            method=self._method,
            alpha=alpha,
            tested=len(leaves),
            rolled_into_parent=rolled,
            families_unopened=len(names) - len(opened),
            dependence_price=(_harmonic(len(leaves)) if self._method is Method.BY else 1.0),
        )

    def _should_roll_up(self, failing: int, total: int) -> bool:
        return total >= self._rollup_minimum and failing / total >= self._rollup_fraction

    @staticmethod
    def _roll_up(
        family: str, chosen: Sequence[Hypothesis], members: Sequence[Hypothesis], threshold: float
    ) -> Finding:
        """One finding standing for a family that failed wholesale.

        The p-value carried is the family's own — Simes over its members —
        rather than the smallest child's. The smallest child's would be the
        most extreme thing that happened, which reads as the severity of the
        incident and is not: an incident in which one control is catastrophic
        and the rest are marginal is a different incident from one in which
        they are uniformly bad.
        """
        return Finding(
            test=Hypothesis(
                identity=family or "estate",
                p_value=simes([t.p_value for t in members]),
                level=_parent_level(chosen[0].level),
                label=family,
            ),
            threshold=threshold,
            covers=tuple(sorted(t.identity for t in chosen)),
        )


def _parent_level(level: Level) -> Level:
    order = list(Level)
    return order[max(0, level.depth - 1)]


# ---------------------------------------------------------------------------
# The dial, and what it means
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class Budget:
    """A false-alarm budget stated the way a business states it.

    "No more than two false alarms a month in this domain" is a sentence
    somebody will actually say. Turning it into a level is arithmetic, and
    doing the arithmetic in the open is the whole differentiator: every
    competitor has a sensitivity slider, and none of them can tell you what
    number it puts on the wall.
    """

    #: False alarms the business will tolerate over the period.
    false_alarms: float
    #: Monitor runs in the same period. The other half of the arithmetic, and
    #: the half that is usually forgotten — the same budget over ten monitors
    #: and ten thousand is two very different levels.
    tests_per_period: int
    period: str = "month"

    @property
    def alpha(self) -> float:
        """The per-test level this budget implies."""
        if self.tests_per_period <= 0:
            return 0.0
        return min(1.0, self.false_alarms / self.tests_per_period)

    def achievable_with(self, resolution: float) -> bool:
        """Whether the calibration history is fine-grained enough for it.

        The question nobody asks, and the one that decides whether the dial is
        honest. A budget of two a month over ten thousand tests needs a level
        of 0.0002, and a monitor with ninety days of history cannot express a
        p-value below about 0.011 — so the budget cannot be honoured, and
        saying so beats printing a threshold that means nothing.
        """
        return self.alpha >= resolution

    def describe(self) -> str:
        return (
            f"{self.false_alarms:g} false alarms per {self.period} across "
            f"{self.tests_per_period:,} monitor runs means testing at "
            f"{self.alpha:.5f}"
        )

    def shortfall(self, resolution: float) -> str:
        """Why the budget cannot be honoured, when it cannot."""
        if self.achievable_with(resolution):
            return ""
        return (
            f"this budget needs a level of {self.alpha:.5f}, and the calibration "
            f"history can express no p-value finer than {resolution:.5f}. Either "
            f"accept about {resolution * self.tests_per_period:.0f} false alarms per "
            f"{self.period}, reduce the number of monitors, or collect "
            f"{math.ceil(1 / self.alpha) - 1:,} comparable observations before "
            f"promising this one"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "false_alarms": self.false_alarms,
            "tests_per_period": self.tests_per_period,
            "period": self.period,
            "alpha": round(self.alpha, 8),
            "summary": self.describe(),
        }


def power_at(alpha: float, effect: float, n: int) -> float:
    """Rough power of a conformal test against a shifted alternative.

    An approximation, and labelled as one wherever it surfaces. It exists so
    the sensitivity dial can answer the other question a person asks — "what
    will I miss?" — with a number rather than a shrug. *effect* is the shift in
    units of the score distribution's spread.
    """
    if n <= 0 or alpha <= 0:
        return 0.0
    # Under a location shift the probability of exceeding the (1-alpha)
    # quantile is approximated by the normal tail at the shifted mean.
    threshold = _normal_quantile(1.0 - alpha)
    return max(0.0, min(1.0, 1.0 - _normal_cdf(threshold - effect)))


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _normal_quantile(probability: float) -> float:
    """Inverse normal CDF by bisection. Slow and obviously correct."""
    if probability <= 0.0:
        return -math.inf
    if probability >= 1.0:
        return math.inf
    low, high = -10.0, 10.0
    for _ in range(200):
        middle = (low + high) / 2
        if _normal_cdf(middle) < probability:
            low = middle
        else:
            high = middle
    return (low + high) / 2
