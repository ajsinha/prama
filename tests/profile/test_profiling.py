"""Sketches, column statistics and end-to-end profiling.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import random
import sqlite3
from pathlib import Path

import pytest

from prama.connect import SamplePlan, SamplingStrategy
from prama.connect.builtin import register_builtin
from prama.connect.registry import ConnectorRegistry
from prama.profile import (
    ColumnAccumulator,
    CountMin,
    HyperLogLog,
    Profiler,
    TDigest,
    TopK,
    character_classes,
    detectable_rate,
    suggest_sample_plan,
)


class TestHyperLogLog:
    def test_estimates_within_its_stated_error(self) -> None:
        sketch = HyperLogLog()
        for i in range(200_000):
            sketch.add(f"value-{i % 60_000}")
        error = abs(sketch.estimate() - 60_000) / 60_000
        # The bound is one standard error; allow three, as statistics requires.
        assert error < sketch.standard_error * 3

    def test_is_exact_for_small_cardinalities(self) -> None:
        # Where a key-candidate decision is actually made, so vagueness here
        # would be worst exactly where it matters most.
        sketch = HyperLogLog()
        sketch.update(f"v{i}" for i in range(50))
        assert sketch.estimate() == 50

    def test_nulls_are_not_distinct_values(self) -> None:
        sketch = HyperLogLog()
        sketch.update([None] * 100)
        assert sketch.estimate() == 0

    def test_merging_partial_sketches_matches_the_whole(self) -> None:
        whole = HyperLogLog()
        left, right = HyperLogLog(), HyperLogLog()
        for i in range(20_000):
            whole.add(i)
            (left if i % 2 else right).add(i)
        merged = left.merge(right)
        assert abs(merged.estimate() - whole.estimate()) / whole.estimate() < 0.02

    def test_hashing_is_stable_across_instances(self) -> None:
        # Python's hash() is salted per process; two workers would disagree and
        # a merged sketch would be silently wrong.
        a, b = HyperLogLog(), HyperLogLog()
        a.update(["x", "y", "z"])
        b.update(["x", "y", "z"])
        assert a.estimate() == b.estimate() == 3


class TestTDigest:
    def test_quantiles_are_accurate_at_the_tails(self) -> None:
        random.seed(11)
        values = [random.gauss(100, 15) for _ in range(50_000)]
        digest = TDigest()
        digest.update(values)
        values.sort()
        for q in (0.01, 0.5, 0.99):
            exact = values[int(q * len(values))]
            assert abs(digest.quantile(q) - exact) < 3.0

    def test_an_empty_digest_returns_nothing_rather_than_zero(self) -> None:
        # Zero would be a plausible, wrong number; None is an honest absence.
        assert TDigest().quantile(0.5) is None
        assert TDigest().minimum is None

    def test_non_finite_values_are_ignored(self) -> None:
        digest = TDigest()
        digest.update([1.0, float("nan"), float("inf"), 3.0])
        assert digest.count == 2
        assert digest.minimum == 1.0

    def test_merging_preserves_the_extremes(self) -> None:
        left, right = TDigest(), TDigest()
        left.update(range(0, 500))
        right.update(range(500, 1000))
        merged = left.merge(right)
        assert merged.minimum == 0
        assert merged.maximum == 999
        assert merged.count == 1000


class TestCountMinAndTopK:
    def test_countmin_never_underestimates(self) -> None:
        # One-sided error: over-counting a rare value is harmless, missing a
        # frequent one is not.
        sketch = CountMin()
        for i in range(20_000):
            sketch.add("frequent" if i % 4 == 0 else f"rare-{i}")
        assert sketch.estimate("frequent") >= 5_000

    def test_topk_finds_a_dominant_default_exactly(self) -> None:
        top = TopK(3)
        top.update(["N"] * 9_700 + ["Y"] * 250 + ["?"] * 50)
        assert top.most_common()[0] == ("N", 9_700)

    def test_topk_stays_bounded_on_a_high_cardinality_column(self) -> None:
        # The leak this module exists to prevent.
        top = TopK(10, capacity_multiple=5)
        top.update(f"unique-{i}" for i in range(100_000))
        assert top.tracked <= 50


class TestColumnStatistics:
    def _accumulate(self, values: list, type_name: str = "TEXT") -> ColumnAccumulator:
        accumulator = ColumnAccumulator("column", type_name)
        accumulator.add_values(values)
        return accumulator

    def test_null_rate_drives_a_completeness_threshold(self) -> None:
        profile = self._accumulate(["a", None, "b", None]).profile()
        assert profile.nulls == 2
        assert profile.null_rate == 0.5

    def test_a_unique_never_null_column_is_a_key_candidate(self) -> None:
        profile = self._accumulate([f"id-{i}" for i in range(500)]).profile()
        assert profile.is_key_candidate

    def test_a_genuine_key_is_not_missed_because_the_sketch_under_counted(self) -> None:
        """The asymmetry that matters.

        A missed key costs the grain declaration, which generates more controls
        than anything else a business owner can state. A false candidate costs
        one verification query. The threshold is three sigma for that reason.
        """
        for size in (2_000, 20_000, 200_000):
            profile = self._accumulate([f"id-{i}" for i in range(size)]).profile()
            assert profile.is_key_candidate, f"missed a genuine key at {size:,} rows"

    def test_a_column_with_real_duplicates_is_not_a_candidate(self) -> None:
        # Generous, but not credulous: 10% duplicates is not a key.
        values = [f"id-{i // 10}" for i in range(2_000)]
        assert not self._accumulate(values).profile().is_key_candidate

    def test_a_nullable_column_is_never_a_key_candidate(self) -> None:
        values = [f"id-{i}" for i in range(500)] + [None]
        assert not self._accumulate(values).profile().is_key_candidate

    def test_a_constant_column_is_reported_as_such(self) -> None:
        profile = self._accumulate(["ACTIVE"] * 1_000).profile()
        assert profile.is_constant
        assert not profile.is_key_candidate

    def test_a_dominant_default_is_surfaced(self) -> None:
        # "97% of this column is 'N'" is a finding a person acts on.
        profile = self._accumulate(["N"] * 970 + ["Y"] * 30).profile()
        value, share = profile.dominant_value
        assert value == "N"
        assert share == 0.97

    def test_a_balanced_column_has_no_dominant_value(self) -> None:
        assert self._accumulate(["N"] * 500 + ["Y"] * 500).profile().dominant_value is None

    def test_numeric_summary_carries_the_tails(self) -> None:
        profile = self._accumulate([float(i) for i in range(1, 1001)], "REAL").profile()
        assert profile.numeric.minimum == 1.0
        assert profile.numeric.maximum == 1000.0
        assert 495 < profile.numeric.mean < 506
        assert "p99" in profile.numeric.quantiles

    def test_booleans_are_not_averaged(self) -> None:
        # Averaging a flag produces a number that looks meaningful and is not.
        assert self._accumulate([True, False, True], "BOOLEAN").profile().numeric is None

    def test_string_masks_reveal_a_format(self) -> None:
        profile = self._accumulate([f"GB{i:010d}" for i in range(100)] + ["not-an-isin"]).profile()
        assert profile.strings.top_masks[0][0] == "AA9999999999"
        assert profile.strings.is_fixed_length is False  # the odd one out shows up

    def test_blank_strings_are_counted_separately_from_nulls(self) -> None:
        profile = self._accumulate(["a", "", "   ", None]).profile()
        assert profile.nulls == 1
        assert profile.strings.blank_count == 2

    def test_accumulators_merge(self) -> None:
        left = self._accumulate([f"v{i}" for i in range(0, 500)])
        right = self._accumulate([f"v{i}" for i in range(500, 1000)])
        merged = left.merge(right).profile()
        assert merged.rows == 1000
        assert abs(merged.distinct_estimate - 1000) < 40

    def test_character_classes_feed_semantic_typing(self) -> None:
        assert character_classes("GB0002634946") == {"upper", "digit"}
        assert "punctuation" in character_classes("a-b")


class TestSamplePlanning:
    def test_small_tables_are_read_completely(self) -> None:
        # An exact rate is worth more than the compute saved.
        assert suggest_sample_plan(100_000).is_complete

    def test_large_tables_are_sampled_to_a_target(self) -> None:
        plan = suggest_sample_plan(100_000_000, target_rows=1_000_000)
        assert not plan.is_complete
        assert plan.fraction == pytest.approx(0.01)
        assert plan.seed  # seeded, so the result is reproducible

    def test_an_unknown_size_is_read_completely(self) -> None:
        assert suggest_sample_plan(None).is_complete

    def test_detectable_rate_turns_a_sample_size_into_a_sentence(self) -> None:
        # "We would have caught anything above 0.03%" is actionable;
        # "we sampled 1%" is not.
        assert detectable_rate(10_000) == pytest.approx(0.0003)
        assert detectable_rate(0) == 1.0


class TestEndToEndProfiling:
    @pytest.fixture
    def source(self, tmp_path: Path) -> Path:
        path = tmp_path / "positions.db"
        connection = sqlite3.connect(path)
        connection.execute(
            "CREATE TABLE positions (position_id INTEGER NOT NULL, isin TEXT, "
            "currency TEXT NOT NULL, notional REAL, status TEXT, unused TEXT)"
        )
        rows = [
            (
                i,
                f"GB{i:010d}" if i % 10 else None,
                "GBP" if i % 3 else "EUR",
                float(i) * 1.5,
                "ACTIVE",
                None,
            )
            for i in range(1, 2001)
        ]
        connection.executemany("INSERT INTO positions VALUES (?,?,?,?,?,?)", rows)
        connection.commit()
        connection.close()
        return path

    async def test_a_first_profile_answers_what_a_person_asks(self, source: Path) -> None:
        registry = register_builtin(ConnectorRegistry())
        connector = registry.create("sqlite", {"database_path": str(source)})
        async with connector:
            profile = await Profiler().profile(connector, ("positions",))

        assert profile.rows == 2000
        # notional is genuinely unique in this fixture, so it is a candidate too;
        # a candidate is a proposal to verify, not a declared key.
        assert "position_id" in profile.key_candidates
        assert profile.constant_columns == ("status", "unused")
        assert profile.empty_columns == ("unused",)
        assert profile.column("isin").null_rate == pytest.approx(0.1, abs=0.001)
        assert profile.column("notional").numeric.maximum == pytest.approx(3000.0)
        assert "2,000 rows" in profile.summary()

    async def test_the_profile_records_how_it_was_computed(self, source: Path) -> None:
        registry = register_builtin(ConnectorRegistry())
        connector = registry.create("sqlite", {"database_path": str(source)})
        async with connector:
            profile = await Profiler().profile(connector, ("positions",))
        provenance = profile.provenance
        assert provenance.is_complete
        assert provenance.snapshot.exact
        assert "all 2,000 rows" in provenance.confidence_note

    async def test_a_sampled_profile_says_so_rather_than_implying_exactness(
        self, source: Path
    ) -> None:
        registry = register_builtin(ConnectorRegistry())
        connector = registry.create("sqlite", {"database_path": str(source)})
        async with connector:
            profile = await Profiler().profile(
                connector,
                ("positions",),
                plan=SamplePlan(strategy=SamplingStrategy.HEAD, rows=100),
            )
        assert not profile.provenance.is_complete
        assert "not of any rate" in profile.provenance.confidence_note

    async def test_a_row_budget_truncates_visibly(self, source: Path) -> None:
        # Stopping is honest and recorded; silently reading everything because
        # nobody set a limit is not.
        registry = register_builtin(ConnectorRegistry())
        connector = registry.create("sqlite", {"database_path": str(source)})
        async with connector:
            profile = await Profiler(max_rows=500).profile(connector, ("positions",))
        assert profile.provenance.truncated
        assert not profile.provenance.is_complete

    async def test_profiling_a_whole_source_survives_one_bad_object(self, source: Path) -> None:
        connection = sqlite3.connect(source)
        connection.execute("CREATE VIEW broken AS SELECT * FROM missing_table")
        connection.commit()
        connection.close()

        registry = register_builtin(ConnectorRegistry())
        connector = registry.create("sqlite", {"database_path": str(source)})
        async with connector:
            profiles = await Profiler().profile_source(connector)
        # One unreadable view must not stop the sweep.
        assert "positions" in [p.qualified_name for p in profiles]

    async def test_a_csv_feed_profiles_the_same_way(self, tmp_path: Path) -> None:
        root = tmp_path / "landing"
        root.mkdir()
        lines = ["trade_id,ccy,amount"] + [
            f"{i},{'GBP' if i % 2 else 'USD'},{i * 10}" for i in range(1, 501)
        ]
        (root / "trades_20260331.csv").write_text("\n".join(lines) + "\n")

        registry = register_builtin(ConnectorRegistry())
        connector = registry.create("filesystem", {"root_path": str(root)})
        async with connector:
            profile = await Profiler().profile(connector, ("trades_20260331.csv",))
        assert profile.rows == 500
        assert "trade_id" in profile.key_candidates
        assert profile.column("ccy").distinct_estimate == 2
