"""Many controls, one pass over the data.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

import pytest

from prama.backend.execute import judge, judge_segments
from prama.backend.fuse import Fuser
from prama.backend.sql import SqlCompiler
from prama.ir.lower import Lowerer
from prama.ir.model import ControlPlan
from prama.pql.errors import PqlUnsupportedError
from prama.pql.parser import parse_control

SUITE = (
    "CHECK corpus.isin IS NOT NULL BECAUSE 'a'",
    "CHECK corpus.ccy IN ('GBP','USD','EUR','JPY') BECAUSE 'b'",
    "CHECK corpus.notional > 0 BECAUSE 'c'",
    "CHECK corpus HAS UNIQUE KEY (account_id, instrument_id) BECAUSE 'd'",
    "CHECK corpus.isin HAS LENGTH BETWEEN 12 AND 12 BECAUSE 'e'",
    "CHECK corpus.notional BETWEEN -10 AND 1000 BECAUSE 'f'",
    "CHECK corpus.isin IS NOT NULL WHERE status = 'ACTIVE' BECAUSE 'g'",
    "CHECK corpus.ccy IS NOT NULL WHERE status = 'ACTIVE' BECAUSE 'h'",
    "CHECK corpus.isin IS NOT NULL FOR EACH entity BECAUSE 'i'",
)


def plans(*sources: str) -> list[ControlPlan]:
    return [Lowerer().control(parse_control(s)) for s in (sources or SUITE)]


def separately(plan: ControlPlan, runner: Any) -> Any:
    """The control run on its own, for comparison with the fused answer."""
    compiled = SqlCompiler("duckdb").compile(plan, table="corpus")
    rows = runner(compiled.metric_query)
    names = [m.name for m in plan.metrics]
    if plan.scope.segment_by:
        return judge_segments(
            plan,
            [
                (
                    "|".join(str(row[c]) for c in plan.scope.segment_by),
                    {n: float(row[n]) for n in names},
                )
                for row in rows
            ],
        )
    return judge(plan, {n: float(rows[0][n]) for n in names})


class TestGrouping:
    def test_controls_over_the_same_scope_share_a_scan(self) -> None:
        groups = Fuser("duckdb").group(plans())
        assert len(groups) == 3  # unfiltered, filtered, segmented
        assert sum(g.size for g in groups) == len(SUITE)

    def test_a_different_filter_is_a_different_scan(self) -> None:
        # It reads different rows, so it cannot share the pass.
        assert (
            len(
                Fuser("duckdb").group(
                    plans(
                        "CHECK corpus.isin IS NOT NULL",
                        "CHECK corpus.isin IS NOT NULL WHERE status = 'ACTIVE'",
                    )
                )
            )
            == 2
        )

    def test_a_segmentation_is_a_different_scan(self) -> None:
        assert (
            len(
                Fuser("duckdb").group(
                    plans(
                        "CHECK corpus.isin IS NOT NULL",
                        "CHECK corpus.isin IS NOT NULL FOR EACH entity",
                    )
                )
            )
            == 2
        )

    def test_filters_that_compile_alike_share_a_scan(self) -> None:
        # Two filters that read the same rows however they were written.
        # Grouping on the syntax tree would miss this.
        assert (
            len(
                Fuser("duckdb").group(
                    plans(
                        "CHECK corpus.isin IS NOT NULL WHERE status = 'ACTIVE'",
                        "CHECK corpus.ccy IS NOT NULL WHERE status = 'ACTIVE'",
                    )
                )
            )
            == 1
        )

    def test_different_thresholds_do_not_prevent_sharing(self) -> None:
        # A threshold is applied to numbers the query already produced, so it
        # has no bearing on how the data is read.
        assert (
            len(
                Fuser("duckdb").group(
                    plans(
                        "CHECK corpus.isin IS NOT NULL",
                        "CHECK corpus.isin IS NOT NULL BELOW 5%",
                    )
                )
            )
            == 1
        )


class TestTheFusedQuery:
    def test_it_answers_every_control_identically(self, duckdb_runner: Any) -> None:
        # The property the whole optimisation rests on. If fusing changed an
        # answer it would be a very fast way to be wrong.
        fuser = Fuser("duckdb")
        every = plans()
        fused = []
        for group in fuser.group(every):
            query = fuser.fuse(group, table="corpus")
            fused.extend(query.unpack(duckdb_runner(query.sql)))
        by_id = {result.plan_id: result for result in fused}
        for plan in every:
            alone = separately(plan, duckdb_runner)
            assert by_id[plan.plan_id].comparable() == alone.comparable(), plan.description

    def test_identical_metrics_are_computed_once(self, duckdb_runner: Any) -> None:
        # Twenty controls over one scope all count the rows. An engine asked
        # for the same aggregate twenty times computes it twenty times.
        fuser = Fuser("duckdb")
        group = fuser.group(
            plans(
                "CHECK corpus.isin IS NOT NULL",
                "CHECK corpus.ccy IS NOT NULL",
                "CHECK corpus.entity IS NOT NULL",
            )
        )[0]
        query = fuser.fuse(group, table="corpus")
        assert query.sql.count(" AS ") == 4  # one shared count, three conditions
        assert len(query.unpack(duckdb_runner(query.sql))) == 3

    def test_a_duplicated_control_reuses_its_twins_column(self, duckdb_runner: Any) -> None:
        fuser = Fuser("duckdb")
        group = fuser.group(
            plans(
                "CHECK corpus.isin IS NOT NULL BECAUSE 'one'",
                "CHECK corpus.isin IS NOT NULL BECAUSE 'the other'",
            )
        )[0]
        query = fuser.fuse(group, table="corpus")
        assert query.sql.count(" AS ") == 2
        results = query.unpack(duckdb_runner(query.sql))
        assert len(results) == 2
        assert results[0].comparable() == results[1].comparable()

    def test_a_segmented_group_keeps_its_segments(self, duckdb_runner: Any) -> None:
        fuser = Fuser("duckdb")
        group = fuser.group(
            plans(
                "CHECK corpus.isin IS NOT NULL FOR EACH entity",
                "CHECK corpus.ccy IS NOT NULL FOR EACH entity",
            )
        )[0]
        query = fuser.fuse(group, table="corpus")
        results = query.unpack(duckdb_runner(query.sql))
        assert all(len(r.segments) == 3 for r in results)
        assert [s.key for s in results[0].failing_segments] == ["APAC"]

    def test_a_control_the_engine_cannot_run_stops_that_group(self) -> None:
        """It must not be silently dropped from a group and reported as passing.

        The exemplar is a *sampled* control on SQLite. It used to be a regular
        expression, until SQLite gained regex through the function Prama's
        executor registers — and a test whose refusal quietly stopped happening
        would have gone on passing while testing nothing.
        """
        import dataclasses

        from prama.backend.dialect import APPROX_DISTINCT, dialect
        from prama.ir import Metric, MetricAggregate

        assert APPROX_DISTINCT not in dialect("sqlite").capabilities

        ordinary, approximate = plans(
            "CHECK corpus.isin IS NOT NULL",
            "CHECK corpus.isin IS NOT NULL",
        )
        # An approximate distinct count is a real, reachable construct that
        # SQLite has no function for. Built here rather than parsed because no
        # PQL surface produces one yet — which is itself worth knowing.
        approximate = dataclasses.replace(
            approximate,
            metrics=(
                *approximate.metrics,
                Metric(name="approx_keys", aggregate=MetricAggregate.APPROX_COUNT_DISTINCT),
            ),
        )
        assert APPROX_DISTINCT in approximate.requires

        with pytest.raises(PqlUnsupportedError) as caught:
            fuser = Fuser("sqlite")
            fuser.fuse(fuser.group([ordinary, approximate])[0], table="corpus")
        assert "must not be silently dropped" in caught.value.remedy


class TestCost:
    def test_cost_is_counted_in_scans_not_controls(self) -> None:
        # A scan is what the source pays for; the control count is what a
        # dashboard likes.
        cost = Fuser("duckdb").cost(plans())
        assert cost.controls == len(SUITE)
        assert cost.scans == 3
        assert cost.controls_per_scan == pytest.approx(3.0)

    def test_the_summary_says_what_was_saved(self) -> None:
        rendered = Fuser("duckdb").cost(plans()).render()
        assert "9 control(s) in 3 scan(s)" in rendered
        assert "6 fewer passes" in rendered

    def test_rows_read_counts_every_pass(self) -> None:
        cost = Fuser("duckdb").cost(plans(), rows={"corpus": 100})
        assert cost.rows_read == 300  # three scans of a hundred rows

    def test_an_unmeasured_dataset_gives_no_total(self) -> None:
        # A total that quietly omits the datasets nobody has measured looks
        # precise and is short by however much they hold.
        assert Fuser("duckdb").cost(plans()).rows_read is None

    def test_the_estimate_serialises_for_a_preview(self) -> None:
        payload = Fuser("duckdb").cost(plans(), rows={"corpus": 8}).to_dict()
        assert payload["scans"] == 3
        assert payload["summary"]
