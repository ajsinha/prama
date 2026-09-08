"""A monitor: one metric, one comparison group, one calibrated verdict.

`FR-MON-001` and `FR-MON-008`. This is where the wave's parts meet. A
monitor takes an observation and the metric's history, asks
:mod:`prama.monitor.season` which past observations are comparable, asks a
detector how unusual this one is against those, asks
:mod:`prama.calibrate.conformal` how surprising that is, and asks
:mod:`prama.calibrate.validity` whether the answer can still be believed.

**The chain has to be able to explain itself at every step**, because "the row
count was low" is not an alert anybody can act on. What a person needs is
"41,200 rows against a typical 62,000 for a month-end, which is more extreme
than 22 of the 23 comparable days — and this monitor's calibration has been
holding". Every clause in that sentence comes from a different component, and
the reason they are composed rather than merged is so each can be replaced
without the sentence losing a clause.

**Segmentation is the difference between a finding and a shrug.** "0.4% of
LEIs are missing" and "every LEI is missing for one legal entity" are the same
number and different incidents. A segmented monitor runs the same test per
segment and then has a multiple-testing problem, which
:mod:`prama.calibrate.select` already knows how to answer — so segments become
a family, and a failure across most of them rolls up into one finding rather
than forty.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from prama.calibrate.conformal import (
    AdaptiveCalibrator,
    ConformalCalibrator,
    ConformalP,
    Uncalibrated,
    recency_weights,
)
from prama.calibrate.select import Hypothesis, Level
from prama.calibrate.validity import Validity, ValidityMonitor, ValidityReport
from prama.monitor.detect import Detector, RobustDeviation, Score
from prama.monitor.season import Grouping, SeasonalModel


class MetricKind(enum.Enum):
    """What is being watched. Chooses defaults, never the verdict."""

    VOLUME = "volume"
    NULL_RATE = "null_rate"
    DISTINCT_COUNT = "distinct_count"
    FRESHNESS = "freshness"
    SCHEMA = "schema"
    DISTRIBUTION = "distribution"
    #: A number the business defined: total exposure, count of open breaks.
    #: The most valuable kind and the one no profiler produces on its own.
    BUSINESS = "business"

    @property
    def is_bounded(self) -> bool:
        """Whether the metric cannot go below zero or above one.

        Decides the default detector: a symmetric measure spends half its
        sensitivity on the impossible side of a null rate.
        """
        return self in (MetricKind.NULL_RATE, MetricKind.DISTRIBUTION)


@dataclasses.dataclass(frozen=True, slots=True)
class Observation:
    """One reading of one metric."""

    value: float
    at: datetime
    #: The segment this reading belongs to, when the monitor is segmented.
    segment: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "at": self.at.isoformat(), "segment": self.segment}


@dataclasses.dataclass(frozen=True, slots=True)
class Verdict:
    """What a monitor concluded, and every step of how."""

    alerted: bool
    observation: Observation
    metric: str
    dataset: str
    score: Score | None = None
    p_value: ConformalP | None = None
    uncalibrated: Uncalibrated | None = None
    grouping: Grouping | None = None
    validity: ValidityReport | None = None
    #: The level actually tested against, after adaptation.
    level: float = 0.0

    @property
    def is_calibrated(self) -> bool:
        return self.validity is not None and self.validity.status.promise_holds

    @property
    def can_be_selected(self) -> bool:
        """Whether this produced a p-value the selector can work with."""
        return self.p_value is not None

    def hypothesis(self, parent: str = "") -> Hypothesis | None:
        """This verdict as something the selection module can rank."""
        if self.p_value is None:
            return None
        return Hypothesis(
            identity=f"{self.dataset}.{self.metric}"
            + (f"[{self.observation.segment}]" if self.observation.segment else ""),
            p_value=self.p_value.value,
            level=Level.CHECK,
            parent=parent or self.dataset,
            label=self.explain(),
        )

    def explain(self) -> str:
        """The sentence a person reads. Assembled, never stored.

        Every clause comes from a different component, which is the reason they
        are composed rather than merged: a detector can be replaced without the
        sentence losing the clause about comparability, and a change to the
        seasonal model cannot silently rewrite what the detector claimed.
        """
        if self.uncalibrated is not None:
            return f"{self.dataset}.{self.metric} could not be judged: {self.uncalibrated.reason}"
        parts = [f"{self.dataset}.{self.metric}"]
        if self.observation.segment:
            parts.append(f"in {self.observation.segment}")
        if self.score is not None:
            parts.append(f"— {self.score.explanation}")
        if self.grouping is not None:
            parts.append(f"({self.grouping.describe()})")
        if self.p_value is not None:
            parts.append(f"{self.p_value.describe()}")
        if self.validity is not None and not self.validity.status.promise_holds:
            # On the alert, not the dashboard. The person reading this at three
            # in the morning is not on the dashboard.
            parts.append(f"⚠ {self.validity.disclosure}")
        return " ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "alerted": self.alerted,
            "dataset": self.dataset,
            "metric": self.metric,
            "observation": self.observation.to_dict(),
            "level": round(self.level, 6),
            "score": self.score.to_dict() if self.score else None,
            "p_value": self.p_value.to_dict() if self.p_value else None,
            "uncalibrated": self.uncalibrated.to_dict() if self.uncalibrated else None,
            "grouping": self.grouping.to_dict() if self.grouping else None,
            "validity": self.validity.to_dict() if self.validity else None,
            "calibrated": self.is_calibrated,
            "explanation": self.explain(),
        }


class Monitor:
    """One metric on one dataset, watched with a declared false-alarm budget."""

    def __init__(
        self,
        dataset: str,
        metric: str,
        *,
        kind: MetricKind = MetricKind.VOLUME,
        detector: Detector | None = None,
        season: SeasonalModel | None = None,
        alpha: float = 0.01,
        half_life: float | None = None,
        adaptive: bool = True,
    ) -> None:
        self.dataset = dataset
        self.metric = metric
        self.kind = kind
        self._detector = detector or _default_detector(kind)
        self._season = season or SeasonalModel()
        self._alpha = alpha
        #: None means no recency weighting, and therefore exact validity. The
        #: default, because paying resolution for drift robustness should be a
        #: decision somebody made rather than one that arrived with the class.
        self._half_life = half_life
        self._adaptive = AdaptiveCalibrator(alpha) if adaptive else None
        self._validity = ValidityMonitor(alpha)

    @property
    def detector(self) -> Detector:
        return self._detector

    @property
    def validity(self) -> ValidityReport:
        return self._validity.report()

    def judge(self, observation: Observation, history: Sequence[Observation]) -> Verdict:
        """Everything, in order: comparable, score, p-value, level, verdict."""
        relevant = [
            item
            for item in history
            if item.segment == observation.segment and item.at < observation.at
        ]
        if not relevant:
            return self._cannot(observation, "no history for this metric yet")

        grouping = self._season.group([item.at for item in relevant], observation.at)
        comparable = [relevant[index].value for index in grouping.members]

        score = self._detector.score(observation.value, comparable)
        if score is None:
            return self._cannot(
                observation,
                f"{len(comparable)} comparable observations is too few for "
                f"{self._detector.name} to compute a score",
                grouping=grouping,
            )

        calibration = self._detector.scores(comparable)
        weights = (
            recency_weights(len(calibration), half_life=self._half_life)
            if self._half_life
            else None
        )
        outcome = ConformalCalibrator(calibration, weights=weights).p_value(score.value)
        if isinstance(outcome, Uncalibrated):
            return self._cannot(observation, outcome.reason, grouping=grouping, score=score)

        level = self._alpha
        if self._adaptive is not None:
            alerted, adaptive_level = self._adaptive.judge(outcome)
            level = adaptive_level.current
        else:
            alerted = outcome.value <= level

        self._validity.observe(outcome.value)
        return Verdict(
            alerted=alerted,
            observation=observation,
            metric=self.metric,
            dataset=self.dataset,
            score=score,
            p_value=outcome,
            grouping=grouping,
            validity=self._validity.report(),
            level=level,
        )

    def _cannot(
        self,
        observation: Observation,
        reason: str,
        *,
        grouping: Grouping | None = None,
        score: Score | None = None,
    ) -> Verdict:
        """A monitor that cannot judge says so and does not alert.

        Not alerting is the right default here and is worth defending: an alert
        that means "I do not know" trains people to ignore alerts, and the
        thing that actually needs attention — that a monitor has been unable to
        judge for a fortnight — is a fleet-level observation rather than a
        per-run one.
        """
        return Verdict(
            alerted=False,
            observation=observation,
            metric=self.metric,
            dataset=self.dataset,
            score=score,
            grouping=grouping,
            uncalibrated=Uncalibrated(reason=reason),
            level=self._alpha,
        )


@dataclasses.dataclass(frozen=True, slots=True)
class FleetReport:
    """What a whole fleet concluded on one run."""

    verdicts: tuple[Verdict, ...] = ()

    def __len__(self) -> int:
        return len(self.verdicts)

    @property
    def alerting(self) -> tuple[Verdict, ...]:
        return tuple(v for v in self.verdicts if v.alerted)

    @property
    def unjudgeable(self) -> tuple[Verdict, ...]:
        """Monitors that could not reach a verdict.

        Surfaced as a fleet number rather than as alerts. A monitor unable to
        judge for a fortnight is a real problem and a bad alert: it has nothing
        to say about the data, only about itself.
        """
        return tuple(v for v in self.verdicts if v.uncalibrated is not None)

    @property
    def degraded(self) -> tuple[Verdict, ...]:
        return tuple(
            v
            for v in self.verdicts
            if v.validity is not None
            and v.validity.status is not Validity.CALIBRATED
            and v.validity.status is not Validity.UNKNOWN
        )

    def hypotheses(self) -> list[Hypothesis]:
        """Everything selectable, for the multiple-testing pass."""
        return [h for h in (v.hypothesis() for v in self.verdicts) if h is not None]

    def describe(self) -> str:
        return (
            f"{len(self.verdicts):,} monitors ran; {len(self.alerting)} exceeded their "
            f"level before selection, {len(self.unjudgeable)} could not be judged, "
            f"{len(self.degraded)} are no longer calibrated"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "monitors": len(self.verdicts),
            "alerting": len(self.alerting),
            "unjudgeable": len(self.unjudgeable),
            "degraded": len(self.degraded),
            "summary": self.describe(),
        }


class SegmentedMonitor:
    """The same metric, watched separately per segment.

    The clause that keeps a finding from being averaged away. "0.4% of LEIs are
    missing" and "every LEI is missing for one legal entity" are the same number
    and different incidents, and only the second is actionable.

    Segmenting multiplies the number of tests, which is a multiple-testing
    problem rather than a reason not to segment — and the selection module
    already answers it. Segments form a family, so a failure across most of
    them rolls up into one finding instead of forty.
    """

    def __init__(
        self,
        dataset: str,
        metric: str,
        segments: Sequence[str],
        **options: Any,
    ) -> None:
        self.dataset = dataset
        self.metric = metric
        self._monitors = {segment: Monitor(dataset, metric, **options) for segment in segments}

    def judge(
        self, observations: Sequence[Observation], history: Sequence[Observation]
    ) -> FleetReport:
        verdicts = [
            self._monitors[observation.segment].judge(observation, history)
            for observation in observations
            if observation.segment in self._monitors
        ]
        return FleetReport(verdicts=tuple(verdicts))

    def hypotheses(self, report: FleetReport) -> list[Hypothesis]:
        """Segments as one family, so a fleet-wide failure is one finding."""
        family = f"{self.dataset}.{self.metric}"
        return [h for h in (v.hypothesis(parent=family) for v in report.verdicts) if h is not None]


def _default_detector(kind: MetricKind) -> Detector:
    """The detector a metric kind implies.

    A default rather than a decision: every one of these is overridable, and
    the choice costs sensitivity rather than validity, so getting it wrong is
    survivable in a way that a wrong threshold would not be.
    """
    if kind.is_bounded:
        from prama.monitor.detect import QuantileDistance

        return QuantileDistance()
    if kind is MetricKind.FRESHNESS:
        from prama.monitor.detect import ForecastResidual

        return ForecastResidual()
    return RobustDeviation()
