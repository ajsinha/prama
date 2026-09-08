"""Turning a profile into metric observations.

The join between Wave 3 and Wave 7: a profile is a snapshot of what a dataset
looks like now, and a *series* of profiles is what a monitor learns a baseline
from. This module is the one place that decides which numbers become history.

Not every statistic does. A top-value list and a set of character masks are
findings a person reads; a null rate and a distinct count are numbers a monitor
tracks. Recording the former as time series would fill the store with rows
nothing ever queries.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.db.metrics import MetricPoint
from prama.profile.profiler import DatasetProfile

#: Column statistics worth a time series, and the metric name each becomes.
COLUMN_METRICS: tuple[tuple[str, str], ...] = (
    ("nulls", "null_count"),
    ("null_rate", "null_rate"),
    ("distinct_estimate", "distinct_count"),
    ("distinct_ratio", "distinct_ratio"),
)

#: Named explicitly rather than derived: "minimum" becomes "min" because that
#: is what a monitor and a threshold call it, and inferring the name by slicing
#: the attribute would be clever and unreadable.
NUMERIC_METRICS: tuple[tuple[str, str], ...] = (
    ("minimum", "min"),
    ("maximum", "max"),
    ("mean", "mean"),
    ("stddev", "stddev"),
)
STRING_METRICS: tuple[tuple[str, str], ...] = (
    ("min_length", "min_length"),
    ("max_length", "max_length"),
    ("mean_length", "mean_length"),
    ("blank_count", "blank_count"),
)


def points_from_profile(
    profile: DatasetProfile,
    *,
    tenant_id: str,
    dataset_id: str,
    run_id: str | None = None,
    connection_id: str | None = None,
    segment: str | None = None,
) -> list[MetricPoint]:
    """Every number in a profile that a monitor could learn from.

    Each point carries the profile's provenance — snapshot, sampling, rows read
    — because a baseline that silently mixed full scans with 1% samples would be
    wrong in a way nobody could detect afterwards.
    """
    provenance = profile.provenance
    snapshot = provenance.snapshot
    points: list[MetricPoint] = []

    def add(metric: str, value: float, attribute: str | None = None) -> None:
        points.append(
            MetricPoint(
                tenant_id=tenant_id,
                dataset_id=dataset_id,
                metric=metric,
                value=float(value),
                computed_at=provenance.computed_at,
                attribute=attribute,
                segment=segment,
                snapshot_id=snapshot.identifier if snapshot else None,
                snapshot_exact=snapshot.exact if snapshot else False,
                sampling=provenance.plan.describe(),
                representative=provenance.plan.strategy.is_representative,
                rows_examined=provenance.rows_examined,
                run_id=run_id,
                connection_id=connection_id,
            )
        )

    add("row_count", profile.rows)
    add("duration_seconds", provenance.duration_seconds)

    for column in profile.columns:
        for attribute_name, metric in COLUMN_METRICS:
            add(metric, getattr(column, attribute_name), column.name)
        if column.numeric is not None:
            for attribute_name, metric in NUMERIC_METRICS:
                value = getattr(column.numeric, attribute_name)
                if value is not None:
                    add(metric, value, column.name)
            for label, value in column.numeric.quantiles.items():
                add(f"quantile_{label}", value, column.name)
        if column.strings is not None:
            for attribute_name, metric in STRING_METRICS:
                value = getattr(column.strings, attribute_name)
                if value is not None:
                    add(metric, value, column.name)
    return points
