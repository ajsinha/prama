"""What a metric observation is.

Every number Prama ever computes about data lands here: a null rate from a
profile, a row count from a control, a distinct estimate from a sketch. The
monitors in Wave 7 read nothing else, which is why the shape matters more than
it looks.

Three fields exist purely so an observation can be *trusted later*:

    snapshot_id   what data state produced it
    sampling      whether it is exact or estimated, and how
    rows_examined how much was actually read

A baseline built from observations that silently mixed full scans with 1%
samples would be wrong in a way nobody could detect afterwards. Recording the
provenance is what lets a monitor exclude, weight, or flag them.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import Any

#: The metric names the platform itself computes. A tenant may record others;
#: these are the ones monitors and derived controls know how to interpret.
CORE_METRICS = (
    "row_count",
    "null_count",
    "null_rate",
    "distinct_count",
    "distinct_ratio",
    "blank_count",
    "min",
    "max",
    "mean",
    "stddev",
    "min_length",
    "max_length",
    "mean_length",
    "bytes_scanned",
    "duration_seconds",
    "arrival_lateness_seconds",
    "violation_count",
    "violation_rate",
)


@dataclasses.dataclass(frozen=True, slots=True)
class MetricPoint:
    """One observation of one metric, at one moment, of one thing.

    ``segment`` is what makes per-entity monitoring possible without a table per
    entity: the same metric, sliced by legal entity or currency or source
    system, recorded as ordinary rows.
    """

    tenant_id: str
    dataset_id: str
    metric: str
    value: float
    computed_at: datetime
    attribute: str | None = None
    segment: str | None = None
    #: How the observation was produced, so a baseline can weigh it.
    snapshot_id: str | None = None
    snapshot_exact: bool = True
    sampling: str = "full"
    representative: bool = True
    rows_examined: int = 0
    run_id: str | None = None
    connection_id: str | None = None

    @property
    def key(self) -> tuple[str, str, str | None, str | None]:
        """What makes a series: one dataset, attribute, segment and metric."""
        return (self.dataset_id, self.metric, self.attribute, self.segment)

    @property
    def is_trustworthy_baseline(self) -> bool:
        """Whether this observation may contribute to a monitor's baseline.

        An unrepresentative sample or an inexact snapshot can still be *shown* —
        it is a real reading — but it must not silently set the expectation a
        later alert is judged against.
        """
        return self.representative and self.snapshot_exact

    def to_row(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "dataset_id": self.dataset_id,
            "attribute": self.attribute,
            "segment": self.segment,
            "metric": self.metric,
            "value": float(self.value),
            "computed_at": self.computed_at,
            "snapshot_id": self.snapshot_id,
            "snapshot_exact": self.snapshot_exact,
            "sampling": self.sampling,
            "representative": self.representative,
            "rows_examined": int(self.rows_examined),
            "run_id": self.run_id,
            "connection_id": self.connection_id,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class MetricSeries:
    """One metric's history, ordered oldest first."""

    dataset_id: str
    metric: str
    attribute: str | None
    segment: str | None
    points: tuple[MetricPoint, ...]

    def __len__(self) -> int:
        return len(self.points)

    @property
    def values(self) -> tuple[float, ...]:
        return tuple(p.value for p in self.points)

    @property
    def latest(self) -> MetricPoint | None:
        return self.points[-1] if self.points else None

    def baseline_points(self) -> tuple[MetricPoint, ...]:
        """Only the observations fit to set an expectation."""
        return tuple(p for p in self.points if p.is_trustworthy_baseline)

    @property
    def name(self) -> str:
        parts = [self.dataset_id, self.metric]
        if self.attribute:
            parts.insert(1, self.attribute)
        if self.segment:
            parts.append(f"[{self.segment}]")
        return ".".join(parts)
