"""Checking only what changed, and being honest about the rest.

The trap: an incremental run makes a *narrower claim* than a full one, and a
platform that renders the two identically is misrepresenting its own evidence.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from prama.core.errors import ValidationError
from prama.execute.watermark import (
    Coverage,
    LatenessPolicy,
    Watermark,
    WatermarkPlanner,
)

NOW = datetime(2026, 4, 10, 6, 0, tzinfo=UTC)
MARK = Watermark(column="as_of_date", value=date(2026, 4, 9), observed_at=NOW, rows_seen=1000)


def planner(**changes: object) -> WatermarkPlanner:
    return WatermarkPlanner(LatenessPolicy(**changes))  # type: ignore[arg-type]


class TestTheNarrowerClaim:
    def test_a_full_run_says_what_it_means(self) -> None:
        assert Coverage.FULL.qualify("passed") == "passed"
        assert Coverage.FULL.supports_a_claim_about_the_whole_dataset

    def test_an_incremental_run_qualifies_its_verdict(self) -> None:
        # "positions_eod passed" after a full scan means the table is sound.
        # The same words after an incremental run mean today's rows are sound.
        assert Coverage.INCREMENTAL.qualify("passed") == "passed over the rows examined"
        assert not Coverage.INCREMENTAL.supports_a_claim_about_the_whole_dataset

    def test_a_forward_only_run_cannot_see_a_restatement(self) -> None:
        assert not Coverage.FORWARD_ONLY.sees_restatements
        assert Coverage.INCREMENTAL.sees_restatements


class TestWatermarks:
    def test_it_advances(self) -> None:
        moved = MARK.advanced_to(date(2026, 4, 10), at=NOW, rows=50)
        assert moved.value == date(2026, 4, 10)
        assert moved.rows_seen == 1050

    def test_it_never_moves_backwards(self) -> None:
        # A watermark that could move back would silently re-admit rows already
        # judged, and the same failing row would be reported every night until
        # somebody noticed the count was wrong rather than the data.
        assert MARK.advanced_to(date(2026, 4, 1), at=NOW).value == date(2026, 4, 9)

    def test_incomparable_values_do_not_move_it(self) -> None:
        # At worst a row is examined twice; the alternative is a mark set to
        # something nobody can order and a scope nobody can predict.
        assert MARK.advanced_to("not a date", at=NOW).value == date(2026, 4, 9)

    def test_when_it_was_observed_is_kept_apart_from_its_value(self) -> None:
        # A watermark of 1 April recorded a week late means a week of data
        # arrived at once, and that is worth being able to see.
        assert MARK.observed_at == NOW
        assert MARK.value != MARK.observed_at


class TestScope:
    def test_a_dataset_never_examined_reads_everything(self) -> None:
        scope = planner().scope(Watermark(column="as_of_date"), now=NOW)
        assert scope.coverage is Coverage.FULL
        assert "nothing has been examined before" in scope.reason

    def test_an_ordinary_run_reads_forward_plus_the_lookback(self) -> None:
        scope = planner(lookback=timedelta(days=3), full_sweep_every=None).scope(
            MARK, now=NOW, last_full_sweep=NOW
        )
        assert scope.coverage is Coverage.INCREMENTAL
        assert scope.lower_bound == date(2026, 4, 6)
        assert "as_of_date >= '2026-04-06'" in scope.predicate

    def test_a_change_column_finds_an_old_row_that_moved(self) -> None:
        # The only way a restatement outside the lookback is visible without
        # reading everything.
        scope = planner(
            lookback=timedelta(days=1), full_sweep_every=None, change_column="updated_at"
        ).scope(MARK, now=NOW, last_full_sweep=NOW)
        assert "updated_at >=" in scope.predicate
        assert " OR " in scope.predicate

    def test_a_full_sweep_comes_round_and_says_why(self) -> None:
        # The evidence should be able to explain why last Tuesday's run took an
        # hour when the others took a second.
        scope = planner(full_sweep_every=timedelta(days=7)).scope(
            MARK, now=NOW, last_full_sweep=NOW - timedelta(days=8)
        )
        assert scope.coverage is Coverage.FULL
        assert "full sweep is due" in scope.reason

    def test_a_sweep_that_has_never_run_is_due(self) -> None:
        scope = planner(full_sweep_every=timedelta(days=7)).scope(MARK, now=NOW)
        assert scope.coverage is Coverage.FULL
        assert "never run" in scope.reason

    def test_a_numeric_watermark_has_no_lookback_to_apply(self) -> None:
        # A sequence or an offset has no notion of days, so the mark itself is
        # the bound.
        mark = Watermark(column="row_id", value=100_000)
        scope = planner(full_sweep_every=None).scope(mark, now=NOW, last_full_sweep=NOW)
        assert scope.lower_bound == 100_000
        assert "row_id >= 100000" in scope.predicate

    def test_the_scope_describes_itself(self) -> None:
        scope = planner(full_sweep_every=None).scope(MARK, now=NOW, last_full_sweep=NOW)
        assert "rows where as_of_date is at or after 2026-04-06" in scope.describe()


class TestTheGapIsReported:
    def test_a_policy_with_no_lookback_and_no_sweep_is_flagged(self) -> None:
        # Otherwise it is discovered when a restatement from three months ago
        # turns up in a regulatory return.
        audit = planner(lookback=timedelta(0), full_sweep_every=None).audit()
        assert not audit["covers_the_past"]
        assert "would never be seen" in audit["gap"]

    def test_a_sweep_closes_the_gap(self) -> None:
        assert planner(full_sweep_every=timedelta(days=7)).audit()["gap"] == ""

    def test_a_change_column_closes_it_too(self) -> None:
        audit = planner(full_sweep_every=None, change_column="updated_at").audit()
        assert audit["covers_the_past"]
        assert audit["gap"] == ""

    def test_the_policy_says_what_it_examines(self) -> None:
        described = planner(
            lookback=timedelta(days=3),
            change_column="updated_at",
            full_sweep_every=timedelta(days=7),
        ).policy.describe()
        assert "last 3 days" in described
        assert "updated_at has moved" in described
        assert "everything every 7 days" in described

    def test_a_negative_lookback_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="cannot be negative"):
            LatenessPolicy(lookback=timedelta(days=-1))


class TestSerialisation:
    def test_a_scope_serialises_into_the_evidence(self) -> None:
        # So a verdict's width travels with it rather than being inferred.
        payload = planner(full_sweep_every=None).scope(MARK, now=NOW, last_full_sweep=NOW).to_dict()
        assert payload["coverage"] == "incremental"
        assert payload["lower_bound"] == "2026-04-06"
        assert payload["watermark"]["column"] == "as_of_date"
        assert payload["describes"]


class TestTheWidthTravelsWithTheVerdict:
    """A record that omitted coverage would let the narrower claim read as the wider."""

    def test_a_record_qualifies_its_own_verdict(self) -> None:
        from prama.evidence.record import EvidenceRecord

        full = EvidenceRecord(verdict="pass", coverage="full")
        narrow = EvidenceRecord(verdict="pass", coverage="incremental")
        assert full.claim == "pass"
        assert narrow.claim == "pass over the rows examined"

    def test_coverage_is_part_of_what_is_hashed(self) -> None:
        # Two runs differing only in how much they read are different facts,
        # and a chain that hashed them the same would let one be substituted
        # for the other.
        from prama.evidence.record import EvidenceRecord

        full = EvidenceRecord(verdict="pass", coverage="full")
        narrow = EvidenceRecord(verdict="pass", coverage="incremental")
        assert full.content_hash != narrow.content_hash

    def test_a_replay_at_a_different_width_is_not_blamed_on_the_data(self) -> None:
        # Two runs that read different amounts of the table were never
        # comparable, and blaming the data would send somebody looking for a
        # restatement that did not happen.
        import dataclasses

        from prama.evidence.record import EvidenceRecord, SnapshotRef
        from prama.evidence.replay import Cause, compare

        original = EvidenceRecord(
            plan_id="p",
            verdict="pass",
            coverage="full",
            snapshot=SnapshotRef("lsn", "0/1", True),
            metrics={"violating_rows": 0.0},
        )
        narrower = dataclasses.replace(
            original, coverage="incremental", metrics={"violating_rows": 3.0}
        )
        assert compare(original, narrower).cause is Cause.COVERAGE_CHANGED
