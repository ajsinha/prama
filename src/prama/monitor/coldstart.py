"""Monitoring an asset on day one, from what is already known about it.

`FR-MON-011`. A monitor with no history has nothing to calibrate against and
so, honestly applied, says nothing — which means a new dataset is unmonitored
for the three months it takes to accumulate a window. That is the period when a
new feed is most likely to be wrong, and the gap is the reason "we'll monitor it
once we have history" is the wrong answer.

**Priors, labelled as priors.** Four sources, in order of how much they are
worth: what the semantic type implies (an ISIN column's null rate is not a
free parameter), what the declared rhythm implies (a daily feed with a declared
volume range starts with a range), what sibling datasets in the same domain do,
and finally the estate's own defaults.

**The labelling is not a footnote.** A prior-based monitor produces a verdict
with no calibration behind it, so it cannot promise a false-alarm rate — and
saying "0.01" next to it would be a lie of exactly the kind this wave exists to
stop telling. Every prior-based verdict carries the source of its prior and the
fact that it is one, and the monitor switches to real calibration the moment
there is enough history, announcing that too.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
from collections.abc import Sequence
from typing import Any

from prama.derive.declaration import AttributeDeclaration, DatasetDeclaration
from prama.monitor.fleet import MetricKind


class PriorSource(enum.Enum):
    """Where an expectation came from, before there was any history."""

    #: The attribute's semantic type. The strongest, because it is a fact about
    #: the world rather than about this estate: an ISIN column with a 40% null
    #: rate is wrong wherever it appears.
    SEMANTIC_TYPE = "semantic_type"
    #: The declared rhythm — a volume range somebody stated.
    DECLARATION = "declaration"
    #: What comparable datasets in the same domain do.
    SIBLINGS = "siblings"
    #: The estate's own defaults. The weakest, and better than nothing only
    #: because "nothing" means unmonitored.
    DEFAULT = "default"

    @property
    def strength(self) -> float:
        return {
            PriorSource.SEMANTIC_TYPE: 0.8,
            PriorSource.DECLARATION: 0.7,
            PriorSource.SIBLINGS: 0.5,
            PriorSource.DEFAULT: 0.2,
        }[self]


@dataclasses.dataclass(frozen=True, slots=True)
class Prior:
    """An expectation with no history behind it, and the fact stated."""

    metric: str
    kind: MetricKind
    source: PriorSource
    low: float
    high: float
    explanation: str

    @property
    def is_calibrated(self) -> bool:
        """Always false. A prior is not a calibration and never becomes one.

        Present as a property rather than left implicit so that any code path
        asking "can I promise a false-alarm rate here?" gets the same answer
        from a prior as it would from an uncalibrated monitor, without having
        to know which it is holding.
        """
        return False

    def admits(self, value: float) -> bool:
        return self.low <= value <= self.high

    def disclosure(self) -> str:
        return (
            f"this is a prior, not a measurement: {self.explanation}. No false-alarm "
            f"rate is promised until this monitor has its own history"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "kind": self.kind.value,
            "source": self.source.value,
            "strength": self.source.strength,
            "low": self.low,
            "high": self.high,
            "explanation": self.explanation,
            "calibrated": self.is_calibrated,
            "disclosure": self.disclosure(),
        }


#: Null rates a semantic type implies. A fact about the world rather than about
#: an estate: an ISIN column that is 40% empty is wrong wherever it appears,
#: and a monitor can say so on day one without having seen the column before.
SEMANTIC_NULL_RATES: dict[str, tuple[float, float]] = {
    "isin": (0.0, 0.02),
    "lei": (0.0, 0.05),
    "cusip": (0.0, 0.02),
    "sedol": (0.0, 0.05),
    "iban": (0.0, 0.02),
    "iso4217": (0.0, 0.001),
    "iso3166": (0.0, 0.02),
    "uuid": (0.0, 0.0),
    "iso_date": (0.0, 0.01),
}


class ColdStart:
    """Builds the expectations a new monitor starts with."""

    def __init__(self, *, defaults: dict[MetricKind, tuple[float, float]] | None = None) -> None:
        self._defaults = defaults or {
            MetricKind.NULL_RATE: (0.0, 0.2),
            MetricKind.VOLUME: (0.0, float("inf")),
            MetricKind.FRESHNESS: (0.0, 3600.0),
        }

    def for_attribute(
        self,
        declaration: DatasetDeclaration,
        attribute: AttributeDeclaration,
        *,
        siblings: Sequence[float] = (),
    ) -> Prior:
        """The null-rate expectation for one attribute on day one."""
        metric = f"{attribute.name}.null_rate"

        if attribute.optionality.value == "mandatory":
            return Prior(
                metric=metric,
                kind=MetricKind.NULL_RATE,
                source=PriorSource.DECLARATION,
                low=0.0,
                high=0.0,
                explanation=(
                    f"{attribute.name} was declared mandatory, so any missing value at "
                    f"all is a departure from what was declared"
                ),
            )

        bounds = SEMANTIC_NULL_RATES.get(attribute.semantic_type)
        if bounds is not None:
            return Prior(
                metric=metric,
                kind=MetricKind.NULL_RATE,
                source=PriorSource.SEMANTIC_TYPE,
                low=bounds[0],
                high=bounds[1],
                explanation=(
                    f"{attribute.name} holds {attribute.semantic_type} values, and a "
                    f"column of those is typically no more than {bounds[1]:.1%} empty "
                    f"wherever it appears"
                ),
            )

        if len(siblings) >= 3:
            low, high = min(siblings), max(siblings)
            return Prior(
                metric=metric,
                kind=MetricKind.NULL_RATE,
                source=PriorSource.SIBLINGS,
                low=max(0.0, low * 0.5),
                high=min(1.0, high * 2.0),
                explanation=(
                    f"{len(siblings)} comparable attributes in "
                    f"{declaration.domain_id or 'this domain'} run between {low:.1%} "
                    f"and {high:.1%} empty"
                ),
            )

        low, high = self._defaults[MetricKind.NULL_RATE]
        return Prior(
            metric=metric,
            kind=MetricKind.NULL_RATE,
            source=PriorSource.DEFAULT,
            low=low,
            high=high,
            explanation=(
                "nothing is known about this attribute yet, so the estate default "
                "applies — this is the weakest kind of expectation and is here only "
                "because the alternative is no monitoring at all"
            ),
        )

    def for_volume(self, declaration: DatasetDeclaration) -> Prior | None:
        """The row-count expectation, when the rhythm declared one."""
        rhythm = declaration.rhythm
        if rhythm is None:
            return None
        if rhythm.expected_volume_min is None and rhythm.expected_volume_max is None:
            return None
        low = float(rhythm.expected_volume_min or 0)
        high = float(
            rhythm.expected_volume_max if rhythm.expected_volume_max is not None else float("inf")
        )
        return Prior(
            metric="row_count",
            kind=MetricKind.VOLUME,
            source=PriorSource.DECLARATION,
            low=low,
            high=high,
            explanation=(
                f"the declared rhythm says a {rhythm.frequency.value} delivery carries "
                f"between {low:,.0f} and {high:,.0f} records"
            ),
        )

    def for_dataset(
        self, declaration: DatasetDeclaration, *, siblings: Sequence[float] = ()
    ) -> tuple[Prior, ...]:
        """Everything a new dataset can be monitored on before it has history."""
        priors = [
            self.for_attribute(declaration, attribute, siblings=siblings)
            for attribute in declaration.attributes
        ]
        volume = self.for_volume(declaration)
        if volume is not None:
            priors.insert(0, volume)
        return tuple(priors)


@dataclasses.dataclass(frozen=True, slots=True)
class Handover:
    """The moment a monitor stops guessing and starts measuring.

    Announced rather than silent. A monitor whose basis changes without saying
    so has, from the reader's point of view, started behaving differently for
    no reason — and the first time that happens on a real alert it costs more
    trust than the whole feature was worth.
    """

    metric: str
    from_prior: Prior
    observations: int
    at: str = ""

    def describe(self) -> str:
        return (
            f"{self.metric} now has {self.observations} of its own observations and is "
            f"calibrated against them. Until now it was judged against a prior: "
            f"{self.from_prior.explanation}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "observations": self.observations,
            "at": self.at,
            "from_prior": self.from_prior.to_dict(),
            "description": self.describe(),
        }
