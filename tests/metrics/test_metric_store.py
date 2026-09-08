"""The metric history store, and what a profile contributes to it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from prama.connect import SamplePlan, SamplingStrategy
from prama.connect.builtin import register_builtin
from prama.connect.registry import ConnectorRegistry
from prama.db.metrics import (
    MemoryMetricStore,
    MetricPoint,
    ParquetMetricStore,
    retention_cutoff,
)
from prama.profile import Profiler, points_from_profile

BASE = datetime(2026, 3, 1, tzinfo=UTC)


def point(day: int, value: float, **overrides) -> MetricPoint:
    defaults = {
        "tenant_id": "t1",
        "dataset_id": "ds1",
        "metric": "null_rate",
        "value": value,
        "computed_at": BASE + timedelta(days=day),
        "attribute": "isin",
    }
    return MetricPoint(**{**defaults, **overrides})


@pytest.fixture(params=["memory", "parquet"])
def store(request: pytest.FixtureRequest, tmp_path: Path):
    """Both implementations must behave identically."""
    if request.param == "memory":
        return MemoryMetricStore()
    return ParquetMetricStore(tmp_path / "metrics", flush_threshold=10_000)


class TestStore:
    def test_a_series_comes_back_oldest_first(self, store) -> None:
        store.record([point(2, 0.03), point(0, 0.01), point(1, 0.02)])
        series = store.series("t1", "ds1", "null_rate", attribute="isin")
        assert series.values == (0.01, 0.02, 0.03)
        assert series.latest.value == 0.03

    def test_an_empty_history_is_a_normal_state_not_an_error(self, store) -> None:
        # Day one for every dataset. Returning empty is the honest answer.
        assert len(store.series("t1", "never-seen", "row_count")) == 0
        assert store.latest("t1", "never-seen") == []
        assert store.count("t1") == 0

    def test_series_are_separated_by_attribute_and_segment(self, store) -> None:
        store.record(
            [
                point(0, 0.1, attribute="isin"),
                point(0, 0.2, attribute="currency"),
                point(0, 0.3, attribute="isin", segment="EMEA"),
            ]
        )
        assert store.series("t1", "ds1", "null_rate", attribute="isin").values == (0.1,)
        assert store.series("t1", "ds1", "null_rate", attribute="currency").values == (0.2,)
        assert store.series("t1", "ds1", "null_rate", attribute="isin", segment="EMEA").values == (
            0.3,
        )

    def test_a_dataset_level_series_is_not_confused_with_a_column_one(self, store) -> None:
        store.record(
            [
                point(0, 1000, metric="row_count", attribute=None),
                point(0, 0.5, metric="row_count", attribute="isin"),
            ]
        )
        assert store.series("t1", "ds1", "row_count").values == (1000,)

    def test_tenants_do_not_see_each_other(self, store) -> None:
        store.record([point(0, 0.1), point(0, 0.9, tenant_id="t2")])
        assert store.count("t1") == 1
        assert store.series("t2", "ds1", "null_rate", attribute="isin").values == (0.9,)

    def test_since_bounds_the_window(self, store) -> None:
        store.record([point(day, day / 100) for day in range(10)])
        recent = store.series(
            "t1", "ds1", "null_rate", attribute="isin", since=BASE + timedelta(days=7)
        )
        assert len(recent) == 3

    def test_latest_returns_one_point_per_series(self, store) -> None:
        store.record(
            [
                point(0, 0.1, attribute="isin"),
                point(5, 0.4, attribute="isin"),
                point(3, 900, metric="row_count", attribute=None),
            ]
        )
        latest = {(p.metric, p.attribute): p.value for p in store.latest("t1", "ds1")}
        assert latest[("null_rate", "isin")] == 0.4
        assert latest[("row_count", None)] == 900


class TestBaselineTrust:
    def test_a_sampled_observation_is_kept_but_excluded_from_the_baseline(self, store) -> None:
        """The distinction the provenance fields exist for.

        A 1% sample is a real reading and worth showing. It must not silently
        set the expectation a later alert is judged against.
        """
        store.record(
            [
                point(0, 0.01),
                point(1, 0.02, representative=False, sampling="head sample of 1,000 rows"),
                point(2, 0.03, snapshot_exact=False),
            ]
        )
        series = store.series("t1", "ds1", "null_rate", attribute="isin")
        assert len(series) == 3  # all three are readable
        assert len(series.baseline_points()) == 1  # only one may set expectations

    def test_a_full_exact_observation_is_trustworthy(self) -> None:
        assert point(0, 0.01).is_trustworthy_baseline


class TestRetention:
    def test_old_partitions_are_dropped_whole(self, tmp_path: Path) -> None:
        # Retention by partition drop: an append-only store that starts deleting
        # rows is no longer append-only.
        store = ParquetMetricStore(tmp_path / "metrics", flush_threshold=1)
        store.record([point(0, 0.1), point(30, 0.2)])
        store.flush()
        removed = store.purge_before(
            "t1", retention_cutoff(0, clock=_FixedClock(BASE + timedelta(days=20)))
        )
        assert removed >= 1
        assert store.series("t1", "ds1", "null_rate", attribute="isin").values == (0.2,)

    def test_purging_an_unknown_tenant_is_harmless(self, tmp_path: Path) -> None:
        store = ParquetMetricStore(tmp_path / "metrics")
        assert store.purge_before("nobody", BASE) == 0


class _FixedClock:
    def __init__(self, instant: datetime) -> None:
        self._instant = instant

    def now(self) -> datetime:
        return self._instant

    def monotonic(self) -> float:
        return 0.0

    def epoch_millis(self) -> int:
        return int(self._instant.timestamp() * 1000)


class TestRecordingFromProfiles:
    @pytest.fixture
    def source(self, tmp_path: Path) -> Path:
        path = tmp_path / "positions.db"
        connection = sqlite3.connect(path)
        connection.execute("CREATE TABLE positions (id INTEGER NOT NULL, isin TEXT, notional REAL)")
        connection.executemany(
            "INSERT INTO positions VALUES (?,?,?)",
            [(i, f"GB{i:010d}" if i % 5 else None, i * 2.5) for i in range(1, 201)],
        )
        connection.commit()
        connection.close()
        return path

    async def test_a_profile_becomes_a_usable_series(self, source: Path) -> None:
        registry = register_builtin(ConnectorRegistry())
        connector = registry.create("sqlite", {"database_path": str(source)})
        async with connector:
            profile = await Profiler().profile(connector, ("positions",))

        points = points_from_profile(profile, tenant_id="t1", dataset_id="ds1")
        store = MemoryMetricStore()
        store.record(points)

        assert store.series("t1", "ds1", "row_count").values == (200.0,)
        nulls = store.series("t1", "ds1", "null_rate", attribute="isin")
        assert nulls.values[0] == pytest.approx(0.2, abs=0.01)
        assert store.series("t1", "ds1", "max", attribute="notional").values == (500.0,)

    async def test_only_monitorable_statistics_become_history(self, source: Path) -> None:
        # Top values and character masks are findings a person reads, not series
        # a monitor tracks; recording them would fill the store with rows
        # nothing ever queries.
        registry = register_builtin(ConnectorRegistry())
        connector = registry.create("sqlite", {"database_path": str(source)})
        async with connector:
            profile = await Profiler().profile(connector, ("positions",))
        metrics = {p.metric for p in points_from_profile(profile, tenant_id="t1", dataset_id="ds1")}
        assert "null_rate" in metrics
        assert "distinct_count" in metrics
        assert not any(m.startswith("top_") or "mask" in m for m in metrics)

    async def test_every_point_carries_the_profiles_provenance(self, source: Path) -> None:
        registry = register_builtin(ConnectorRegistry())
        connector = registry.create("sqlite", {"database_path": str(source)})
        async with connector:
            profile = await Profiler().profile(
                connector,
                ("positions",),
                plan=SamplePlan(strategy=SamplingStrategy.HEAD, rows=50),
            )
        points = points_from_profile(profile, tenant_id="t1", dataset_id="ds1")
        assert points
        # A head sample must not be able to set a baseline.
        assert all(not p.representative for p in points)
        assert all(not p.is_trustworthy_baseline for p in points)
        assert all(p.snapshot_id for p in points)
