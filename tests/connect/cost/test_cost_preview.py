"""What a scan will cost, said before it runs.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from prama.connect.cost import (
    ASSUMED_BYTES_PER_ROW,
    CostEstimator,
    EstimateBasis,
    Throughput,
    ThroughputRegistry,
)
from prama.connect.spi import (
    DiscoveredObject,
    ObjectSchema,
    ReadPolicy,
    SamplePlan,
    SamplingStrategy,
)

ORDERS = DiscoveredObject(
    path=("sales", "orders"),
    estimated_rows=1_000_000,
    estimated_bytes=4 * 1024**3,
)

FAST = Throughput(
    bytes_per_second=100 * 1024**2,
    rows_per_second=50_000,
    samples=3,
    measured_at=datetime(2026, 4, 2, tzinfo=UTC),
)


class TestTheNumbers:
    def test_a_full_scan_is_the_whole_object(self) -> None:
        estimate = CostEstimator().estimate(path=("sales", "orders"), discovered=ORDERS)
        assert estimate.rows == 1_000_000
        assert estimate.byte_count == 4 * 1024**3
        assert estimate.fraction == 1.0
        assert estimate.rows_basis is EstimateBasis.CATALOGUE

    def test_a_sample_costs_its_fraction(self) -> None:
        estimate = CostEstimator().estimate(
            path=("sales", "orders"),
            discovered=ORDERS,
            plan=SamplePlan(strategy=SamplingStrategy.SYSTEMATIC, fraction=0.01),
        )
        assert estimate.rows == 10_000
        assert estimate.byte_count == int(0.01 * 4 * 1024**3)

    def test_a_row_limit_caps_both_rows_and_bytes(self) -> None:
        estimate = CostEstimator().estimate(
            path=("sales", "orders"), discovered=ORDERS, plan=SamplePlan(rows=1_000)
        )
        assert estimate.rows == 1_000
        # Not the whole four gigabytes: the bytes must follow the rows, or the
        # preview frightens somebody out of a read that costs almost nothing.
        assert estimate.byte_count is not None
        assert estimate.byte_count < 10 * 1024**2

    def test_a_schema_supplies_the_count_when_discovery_did_not(self) -> None:
        estimate = CostEstimator().estimate(
            path=("s", "t"),
            schema=ObjectSchema(path=("s", "t"), columns=(), estimated_rows=500),
        )
        assert estimate.rows == 500
        assert estimate.rows_basis is EstimateBasis.CATALOGUE


class TestHonestyAboutWhereNumbersCameFrom:
    def test_a_size_inferred_from_rows_is_marked_as_inferred(self) -> None:
        # A preview that presented this as a catalogue figure would be quietly
        # lying about a number somebody is using to decide whether to proceed.
        estimate = CostEstimator().estimate(
            path=("s", "t"),
            discovered=DiscoveredObject(path=("s", "t"), estimated_rows=1_000),
        )
        assert estimate.byte_count == 1_000 * ASSUMED_BYTES_PER_ROW
        assert estimate.bytes_basis is EstimateBasis.DERIVED
        assert not estimate.is_confident
        assert any("bytes per row" in w for w in estimate.warnings)

    def test_a_source_that_reports_nothing_says_so(self) -> None:
        estimate = CostEstimator().estimate(
            path=("s", "t"), discovered=DiscoveredObject(path=("s", "t"))
        )
        assert estimate.rows is None
        assert estimate.rows_basis is EstimateBasis.UNKNOWN
        assert any("unknown until it runs" in w for w in estimate.warnings)

    def test_duration_is_absent_until_something_has_been_measured(self) -> None:
        # Inventing one from a default throughput constant would be a
        # fabrication, and a confident wrong number costs more trust than an
        # admitted absence.
        estimate = CostEstimator().estimate(path=("sales", "orders"), discovered=ORDERS)
        assert estimate.duration_seconds is None
        assert estimate.duration_basis is EstimateBasis.UNKNOWN
        assert "nothing has been read through this connection yet" in estimate.render()

    def test_a_measured_connection_gives_a_real_duration(self) -> None:
        estimate = CostEstimator().estimate(
            path=("sales", "orders"), discovered=ORDERS, throughput=FAST
        )
        assert estimate.duration_basis is EstimateBasis.MEASURED
        assert estimate.duration_seconds is not None

    def test_duration_comes_from_rows_because_the_units_match(self) -> None:
        # The catalogue's byte figure is size on disk — indexes, TOAST and page
        # padding included — while measured throughput is bytes delivered.
        # Dividing one by the other is a unit error that looks like arithmetic,
        # and on an index-heavy table it overstates the wait severalfold.
        indexed = DiscoveredObject(
            path=("s", "t"), estimated_rows=1_000_000, estimated_bytes=100 * 1024**3
        )
        estimate = CostEstimator().estimate(path=("s", "t"), discovered=indexed, throughput=FAST)
        assert estimate.duration_seconds == 1_000_000 / FAST.rows_per_second
        assert estimate.duration_basis is EstimateBasis.MEASURED

    def test_without_a_row_count_bytes_are_used_and_marked_derived(self) -> None:
        estimate = CostEstimator().estimate(
            path=("s", "t"),
            discovered=DiscoveredObject(path=("s", "t"), estimated_bytes=10 * 1024**2),
            throughput=FAST,
        )
        assert estimate.duration_basis is EstimateBasis.DERIVED


class TestBudget:
    def test_an_oversized_scan_is_flagged_before_it_runs(self) -> None:
        policy = ReadPolicy(max_bytes_scanned=1024**3)
        estimate = CostEstimator(policy).estimate(path=("sales", "orders"), discovered=ORDERS)
        assert not estimate.within_budget
        assert "exceeds" in estimate.render()

    def test_a_row_ceiling_is_reported_in_its_own_words(self) -> None:
        policy = ReadPolicy(max_rows_read=1_000)
        estimate = CostEstimator(policy).estimate(path=("sales", "orders"), discovered=ORDERS)
        assert any("1,000 rows" in reason for reason in estimate.exceeds)

    def test_a_refusal_comes_with_the_plan_that_would_work(self) -> None:
        # "You cannot do that" is a dead end; "you cannot do that, but this
        # would" is an answer.
        estimator = CostEstimator(ReadPolicy(max_rows_read=50_000))
        estimate = estimator.estimate(path=("sales", "orders"), discovered=ORDERS)
        suggested = estimator.plan_that_fits(estimate)
        assert suggested is not None
        assert suggested.rows == 50_000
        assert suggested.strategy is SamplingStrategy.SYSTEMATIC

    def test_a_byte_ceiling_is_translated_into_rows(self) -> None:
        estimator = CostEstimator(ReadPolicy(max_bytes_scanned=4 * 1024**2))
        suggested = estimator.plan_that_fits(
            estimator.estimate(path=("sales", "orders"), discovered=ORDERS)
        )
        assert suggested is not None
        assert 0 < (suggested.rows or 0) < 10_000

    def test_a_scan_inside_the_budget_needs_no_alternative(self) -> None:
        estimator = CostEstimator(ReadPolicy(max_rows_read=10_000_000))
        estimate = estimator.estimate(path=("sales", "orders"), discovered=ORDERS)
        assert estimate.within_budget
        assert estimator.plan_that_fits(estimate) is None


class TestPacedDuration:
    def test_a_load_ceiling_lengthens_the_wall_clock(self) -> None:
        # The number somebody actually waits for. Quoting the unpaced duration
        # while a 5% ceiling is in force would understate it twentyfold.
        policy = ReadPolicy(load_ceiling=0.05)
        estimate = CostEstimator(policy).estimate(
            path=("sales", "orders"), discovered=ORDERS, throughput=FAST
        )
        assert estimate.paced_duration_seconds is not None
        assert estimate.duration_seconds is not None
        assert estimate.paced_duration_seconds == pytest.approx(estimate.duration_seconds * 20)

    def test_no_ceiling_means_the_two_agree(self) -> None:
        estimate = CostEstimator(ReadPolicy(load_ceiling=1.0)).estimate(
            path=("sales", "orders"), discovered=ORDERS, throughput=FAST
        )
        assert estimate.paced_duration_seconds == estimate.duration_seconds


class TestRendering:
    def test_the_summary_is_one_sentence_somebody_can_act_on(self) -> None:
        estimate = CostEstimator().estimate(
            path=("sales", "orders"), discovered=ORDERS, throughput=FAST
        )
        rendered = estimate.render()
        assert rendered.startswith("Reading sales.orders will scan 4.0 GB")
        assert "1,000,000 rows" in rendered
        assert rendered.endswith(".")

    def test_a_sample_says_it_is_a_sample(self) -> None:
        estimate = CostEstimator().estimate(
            path=("sales", "orders"),
            discovered=ORDERS,
            plan=SamplePlan(strategy=SamplingStrategy.SYSTEMATIC, fraction=0.01),
        )
        assert "sample 1.00% of the table" in estimate.render()

    def test_the_dictionary_carries_the_basis_of_every_number(self) -> None:
        payload = CostEstimator().estimate(path=("sales", "orders"), discovered=ORDERS).to_dict()
        assert payload["rows_basis"] == "catalogue"
        assert payload["duration_basis"] == "unknown"
        assert payload["summary"]


class TestLearningFromExperience:
    def test_the_first_read_teaches_the_second_preview(self) -> None:
        registry = ThroughputRegistry()
        assert registry.of("c1") is None
        registry.record(
            "c1", Throughput.from_read(rows=100_000, byte_count=50 * 1024**2, seconds=2.0)
        )
        assert registry.of("c1") is not None
        assert (
            CostEstimator()
            .estimate(path=("sales", "orders"), discovered=ORDERS, throughput=registry.of("c1"))
            .duration_basis
            is EstimateBasis.MEASURED
        )

    def test_a_read_too_short_to_time_is_not_learned_from(self) -> None:
        # Letting it into the average makes the next estimate worse, not better.
        assert Throughput.from_read(rows=5, byte_count=100, seconds=0.001) is None
        assert Throughput.from_read(rows=0, byte_count=0, seconds=10.0) is None

    def test_samples_are_weighted_so_one_slow_morning_does_not_dominate(self) -> None:
        registry = ThroughputRegistry()
        for _ in range(9):
            registry.record(
                "c1", Throughput.from_read(rows=100_000, byte_count=1024**2, seconds=1.0)
            )
        registry.record("c1", Throughput.from_read(rows=1_000, byte_count=1024**2, seconds=10.0))
        observed = registry.of("c1")
        assert observed is not None
        assert observed.samples == 10
        assert observed.rows_per_second > 80_000
