"""Detection scoring: what a benchmark result actually means.

docs/corpus/15 §3.1 sets a rule most data quality benchmarks quietly break:

    Detection is credited only if the alert identifies the correct dataset
    **and** column **and** time window; a generic "something is wrong with this
    table" scores zero.

That rule is the whole difference between a benchmark and a demonstration. A
tool that alerts on every table every day has perfect recall under a loose
match, and is useless. So a match here is exact on all three axes, and a
partial match is scored as what it is — a *miss*, with the near-miss reported
separately so the number is arguable rather than merely low.

Two further rules, both from the same instinct:

* **Per-family before aggregate.** An overall F1 hides the semantic family,
  which is where the argument lives: everybody catches a null, and almost
  nobody catches a code that is valid and wrong. Reporting one number lets a
  tool average its way past the thing it is bad at.
* **A family with no planted defects scores nothing, not one.** Precision over
  zero predictions is undefined, and a benchmark that reports 1.0 for a family
  it never tested is a benchmark that rewards not being tested.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable
from typing import Any


@dataclasses.dataclass(frozen=True, slots=True)
class Defect:
    """A planted defect, and where it is."""

    dataset: str
    column: str
    #: The window it lives in, as an ISO date or a period label. Compared
    #: exactly: a detection in the wrong window is a detection of something
    #: else that happens to look similar.
    window: str
    family: str = "unclassified"
    #: ``easy`` · ``moderate`` · ``hard``. Reported separately, because a tool
    #: that only finds the easy ones has a different problem from one that
    #: finds few of everything.
    difficulty: str = "moderate"
    note: str = ""

    @property
    def locus(self) -> tuple[str, str, str]:
        return (self.dataset, self.column, self.window)


@dataclasses.dataclass(frozen=True, slots=True)
class Alert:
    """Something a tool said, and where it said it."""

    dataset: str
    column: str
    window: str
    detail: str = ""

    @property
    def locus(self) -> tuple[str, str, str]:
        return (self.dataset, self.column, self.window)


@dataclasses.dataclass(frozen=True, slots=True)
class FamilyScore:
    """One defect family's numbers."""

    family: str
    planted: int
    found: int
    false_alarms: int

    @property
    def missed(self) -> int:
        return self.planted - self.found

    @property
    def precision(self) -> float | None:
        """``None`` at family level, always — and that is the finding.

        A false alarm corresponds to *no planted defect*, so it belongs to no
        family. Attributing it to one is a guess; spreading it across all of
        them makes every family look slightly better than it is. Precision is
        computable at the aggregate, where the denominator is real, and a
        family score reports recall.

        ``false_alarms`` is still carried so the run total is visible beside
        each family; it is simply not turned into a ratio nobody can defend.
        """
        return None

    @property
    def recall(self) -> float | None:
        """``None`` when nothing was planted.

        A family the benchmark never tested must not score, or a tool is
        rewarded for the gaps in its evaluation.
        """
        return None if self.planted == 0 else self.found / self.planted

    @property
    def f1(self) -> float | None:
        precision, recall = self.precision, self.recall
        if precision is None or recall is None or precision + recall == 0:
            return None
        return 2 * precision * recall / (precision + recall)

    def describe(self) -> str:
        if self.planted == 0:
            return (
                f"{self.family}: nothing was planted, so nothing is scored — "
                f"{self.false_alarms} alert(s) here are all false"
            )
        recall = self.recall
        assert recall is not None
        return (
            f"{self.family}: found {self.found} of {self.planted} (recall {recall:.0%}); "
            "precision is an aggregate figure, because a false alarm belongs to no family"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "planted": self.planted,
            "found": self.found,
            "missed": self.missed,
            "false_alarms": self.false_alarms,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "message": self.describe(),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Score:
    """A whole benchmark run."""

    families: tuple[FamilyScore, ...] = ()
    #: Alerts naming a real defect's dataset and column but the wrong window,
    #: or the right dataset and the wrong column. Not credited — reported, so
    #: the score is arguable rather than merely low.
    near_misses: tuple[tuple[Alert, Defect], ...] = ()
    by_difficulty: dict[str, tuple[int, int]] = dataclasses.field(default_factory=dict)

    @property
    def planted(self) -> int:
        return sum(family.planted for family in self.families)

    @property
    def found(self) -> int:
        return sum(family.found for family in self.families)

    @property
    def false_alarms(self) -> int:
        """Alerts crediting no planted defect.

        Read from any family rather than summed: every family carries the same
        run total, because a false alarm belongs to none of them.
        """
        return self.families[0].false_alarms if self.families else 0

    @property
    def recall(self) -> float | None:
        return None if self.planted == 0 else self.found / self.planted

    @property
    def precision(self) -> float | None:
        predicted = self.found + self.false_alarms
        return None if predicted == 0 else self.found / predicted

    @property
    def f1(self) -> float | None:
        precision, recall = self.precision, self.recall
        if precision is None or recall is None or precision + recall == 0:
            return None
        return 2 * precision * recall / (precision + recall)

    @property
    def weakest_family(self) -> FamilyScore | None:
        """The family with the worst recall, which is the honest headline.

        An aggregate F1 lets a tool average its way past the thing it is bad
        at, and the thing it is bad at is what a buyer will hit in week two.
        """
        scored = [f for f in self.families if f.recall is not None]
        return min(scored, key=lambda f: f.recall or 0.0) if scored else None

    def describe(self) -> str:
        if not self.planted:
            return "nothing was planted, so this run scores nothing"
        recall = self.recall
        assert recall is not None
        parts = [f"found {self.found} of {self.planted} planted defect(s) ({recall:.0%})"]
        weakest = self.weakest_family
        if weakest is not None and weakest.recall is not None and weakest.recall < 1.0:
            # Named before the aggregate. The weakest family is what a buyer
            # hits in week two, and an average hides it by construction.
            parts.insert(0, f"weakest family {weakest.family} at {weakest.recall:.0%} recall")
        if self.false_alarms:
            parts.append(f"{self.false_alarms} false alarm(s)")
        if self.near_misses:
            parts.append(
                f"{len(self.near_misses)} near miss(es) — right table, wrong column or "
                "window, credited as misses"
            )
        return "; ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "planted": self.planted,
            "found": self.found,
            "false_alarms": self.false_alarms,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "families": [family.to_dict() for family in self.families],
            "near_misses": [
                {"alert": alert.locus, "defect": defect.locus} for alert, defect in self.near_misses
            ],
            "by_difficulty": {
                key: {"found": found, "planted": planted}
                for key, (found, planted) in sorted(self.by_difficulty.items())
            },
            "message": self.describe(),
        }


def score(defects: Iterable[Defect], alerts: Iterable[Alert]) -> Score:
    """Score a run under docs/corpus/15 §3.1's exact-match rule.

    An alert credits a defect only when dataset, column and window all agree. A
    tool alerting on every table every day would otherwise score perfect recall
    while being useless.
    """
    planted = list(defects)
    raised = list(alerts)

    by_locus: dict[tuple[str, str, str], list[Defect]] = {}
    for defect in planted:
        by_locus.setdefault(defect.locus, []).append(defect)

    matched: set[int] = set()
    credited_alerts: set[int] = set()
    for alert_index, alert in enumerate(raised):
        candidates = by_locus.get(alert.locus, [])
        for defect in candidates:
            identity = planted.index(defect)
            if identity in matched:
                continue
            # One alert credits one defect. Crediting a repeated alert again
            # would let a tool improve its recall by shouting.
            matched.add(identity)
            credited_alerts.add(alert_index)
            break

    near: list[tuple[Alert, Defect]] = []
    for alert_index, alert in enumerate(raised):
        if alert_index in credited_alerts:
            continue
        for defect in planted:
            if alert.dataset == defect.dataset and (
                alert.column == defect.column or alert.window == defect.window
            ):
                near.append((alert, defect))
                break

    uncredited = len(raised) - len(credited_alerts)
    scored: list[FamilyScore] = [
        FamilyScore(
            family=family,
            planted=sum(1 for defect in planted if defect.family == family),
            found=sum(
                1
                for index, defect in enumerate(planted)
                if defect.family == family and index in matched
            ),
            # The run total, carried on every family rather than attributed to
            # one. A false alarm corresponds to no planted defect, so no family
            # owns it — and the number is worth seeing beside each of them.
            false_alarms=uncredited,
        )
        for family in sorted({defect.family for defect in planted})
    ]

    difficulty: dict[str, tuple[int, int]] = {}
    for index, defect in enumerate(planted):
        found, total = difficulty.get(defect.difficulty, (0, 0))
        difficulty[defect.difficulty] = (found + (1 if index in matched else 0), total + 1)

    return Score(
        families=tuple(scored),
        near_misses=tuple(near),
        by_difficulty=difficulty,
    )


__all__ = ["Alert", "Defect", "FamilyScore", "Score", "score"]
