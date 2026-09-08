"""What a monitor is, written down where somebody can read it.

`FR-MON-017` and `NFR-CMP-005`. A model card for a data quality monitor is not
a compliance artefact borrowed from machine learning; it is the answer to the
question every audit asks and no monitoring product can answer: *what does this
alert mean, what was it built from, and how often has it been right?*

Three things distinguish this from a card that is filled in once and rots:

**It is derived, not written.** Every field comes from the monitor's own
configuration and its measured history, so it cannot describe a monitor that no
longer exists. A hand-written card is accurate on the day it is written.

**It states what the monitor is blind to.** Every detector has a failure mode
and the suite documents them; a card that lists only strengths is the kind of
document that gets quoted back after an incident nobody caught.

**It carries the measured precision, not a claim.** "This monitor has raised 34
alerts, 29 of which a steward confirmed" is a fact. "High accuracy" is
marketing, and an audit can tell the difference.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from prama.calibrate.validity import ValidityReport
from prama.monitor.detect import Detector
from prama.monitor.season import Grouping


@dataclasses.dataclass(frozen=True, slots=True)
class Outcome:
    """What happened to one alert after a person looked at it."""

    #: True when a steward confirmed the alert found something real.
    confirmed: bool
    at: str = ""
    note: str = ""


@dataclasses.dataclass(frozen=True, slots=True)
class PrecisionHistory:
    """How often this monitor has been right, measured.

    Precision rather than accuracy, deliberately. Accuracy on a monitor that
    alerts twice a year is 99.5% whatever it does, because it is dominated by
    the days nothing happened — a number that flatters every monitor equally
    and distinguishes none of them.
    """

    raised: int = 0
    confirmed: int = 0
    #: Alerts nobody has judged yet. Counted separately, because treating them
    #: as wrong understates the monitor and treating them as right overstates
    #: it, and the honest thing is to say how much of the record is unknown.
    unreviewed: int = 0

    @property
    def reviewed(self) -> int:
        return self.raised - self.unreviewed

    @property
    def precision(self) -> float | None:
        return self.confirmed / self.reviewed if self.reviewed else None

    def describe(self) -> str:
        if not self.raised:
            return "this monitor has not raised an alert yet"
        if not self.reviewed:
            return f"{self.raised} alerts raised, none of them reviewed yet"
        head = (
            f"{self.raised} alerts raised, {self.confirmed} of the {self.reviewed} "
            f"reviewed were confirmed ({self.precision:.0%})"
        )
        if self.unreviewed:
            head += f"; {self.unreviewed} still unreviewed"
        return head

    def with_outcome(self, outcome: Outcome) -> PrecisionHistory:
        return PrecisionHistory(
            raised=self.raised,
            confirmed=self.confirmed + (1 if outcome.confirmed else 0),
            unreviewed=max(0, self.unreviewed - 1),
        )

    def with_alert(self) -> PrecisionHistory:
        return PrecisionHistory(
            raised=self.raised + 1,
            confirmed=self.confirmed,
            unreviewed=self.unreviewed + 1,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "raised": self.raised,
            "confirmed": self.confirmed,
            "reviewed": self.reviewed,
            "unreviewed": self.unreviewed,
            "precision": round(self.precision, 4) if self.precision is not None else None,
            "summary": self.describe(),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class ModelCard:
    """Everything about a monitor, derived from the monitor.

    Reproducibility metadata included, because "which version of what, against
    which calibration window" is the first question when two runs disagree and
    the one nobody records until after the first time it matters.
    """

    dataset: str
    metric: str
    detector: str
    good_at: str
    blind_to: str
    #: The declared budget, and whether it is currently being honoured.
    alpha: float
    validity: str
    calibration_size: int
    #: The finest p-value the current calibration can express. The honest
    #: bound on what the budget dial can promise.
    resolution: float
    comparison_group: str
    precision: PrecisionHistory
    #: For reproducibility: which code, which window, which seasonal rules.
    version: str = ""
    seasonal_facets: tuple[str, ...] = ()
    generated_at: str = ""

    @property
    def budget_is_expressible(self) -> bool:
        return self.alpha >= self.resolution

    def render(self) -> str:
        """The card as prose, for the person the audit sent."""
        lines = [
            f"# {self.dataset}.{self.metric}",
            "",
            f"**What it watches.** {self.metric} on {self.dataset}, compared against "
            f"{self.comparison_group}.",
            "",
            f"**How it decides.** {self.detector}, calibrated against "
            f"{self.calibration_size} comparable observations. Good at "
            f"{self.good_at}. Blind to {self.blind_to}.",
            "",
            f"**What it promises.** At most {self.alpha:.2%} of normal observations "
            f"raise an alert. {self.validity}",
        ]
        if not self.budget_is_expressible:
            lines.extend(
                [
                    "",
                    f"**The promise cannot currently be kept.** This much history "
                    f"can express no p-value finer than {self.resolution:.4f}, and the "
                    f"declared budget needs {self.alpha:.4f}.",
                ]
            )
        lines.extend(
            [
                "",
                f"**How often it has been right.** {self.precision.describe()}.",
                "",
                f"**Reproducibility.** Prama {self.version}; seasonal grouping on "
                + (", ".join(self.seasonal_facets) or "nothing")
                + f"; card generated {self.generated_at or 'on demand'}.",
            ]
        )
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "metric": self.metric,
            "detector": self.detector,
            "good_at": self.good_at,
            "blind_to": self.blind_to,
            "alpha": self.alpha,
            "validity": self.validity,
            "calibration_size": self.calibration_size,
            "resolution": round(self.resolution, 6),
            "budget_expressible": self.budget_is_expressible,
            "comparison_group": self.comparison_group,
            "precision": self.precision.to_dict(),
            "version": self.version,
            "seasonal_facets": list(self.seasonal_facets),
            "generated_at": self.generated_at,
            "markdown": self.render(),
        }


def card_for(
    dataset: str,
    metric: str,
    detector: Detector,
    *,
    alpha: float,
    validity: ValidityReport,
    grouping: Grouping | None,
    precision: PrecisionHistory | None = None,
    version: str = "",
    generated_at: str = "",
) -> ModelCard:
    """Build a card from the monitor rather than about it.

    Everything here is read off the running monitor, so a card cannot describe
    a configuration that has been changed since — which is the failure mode of
    every hand-written model card in every catalogue.
    """
    size = grouping.size if grouping else 0
    return ModelCard(
        dataset=dataset,
        metric=metric,
        detector=detector.name,
        good_at=detector.good_at,
        blind_to=detector.blind_to,
        alpha=alpha,
        validity=validity.disclosure,
        calibration_size=size,
        resolution=grouping.resolution if grouping else 1.0,
        comparison_group=grouping.key.render() if grouping else "nothing yet",
        precision=precision or PrecisionHistory(),
        version=version,
        seasonal_facets=tuple(grouping.key.to_dict()) if grouping else (),
        generated_at=generated_at,
    )
