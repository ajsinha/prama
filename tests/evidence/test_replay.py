"""Replaying a run, and saying precisely why the answer moved.

Replaying identically proves little on its own — a system that never re-reads
anything replays identically too. The value is in the other case: when the
answer differs, the report has to name the cause.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from prama.evidence.record import EvidenceRecord, SnapshotRef
from prama.evidence.replay import Cause, ReplayReport, compare

ORIGINAL = EvidenceRecord(
    sequence=7,
    plan_id="ir:sha256:" + "a" * 64,
    control_id="ctl-1",
    control_version=3,
    dataset="positions_eod",
    engine="postgresql",
    snapshot=SnapshotRef(kind="lsn", identifier="0/1A2B3C", exact=True),
    parameters={"business_date": "2026-04-02"},
    verdict="fail",
    metrics={"scanned_rows": 50000.0, "violating_rows": 12.0},
)


def replayed(**changes: Any) -> EvidenceRecord:
    """The same run again, with whatever moved."""
    return dataclasses.replace(ORIGINAL, sequence=99, **changes)


class TestAnIdenticalReplay:
    def test_the_same_answer_is_reported_as_identical(self) -> None:
        assert compare(ORIGINAL, replayed()).cause is Cause.IDENTICAL

    def test_timing_and_sequence_are_not_divergences(self) -> None:
        # A replay happens later and takes a different length of time.
        # Reporting that would bury the difference that matters under two that
        # never do.
        later = replayed(
            started_at="2026-05-01T09:00:00Z",
            finished_at="2026-05-01T09:00:09Z",
            duration_ms=9000,
        )
        assert compare(ORIGINAL, later).is_identical

    def test_it_says_so_plainly(self) -> None:
        assert "reproduced the original exactly" in compare(ORIGINAL, replayed()).render()


class TestNamingTheCause:
    def test_moved_data_is_the_ordinary_case(self) -> None:
        # A restatement, a late arrival, a correction. Not a defect, and the
        # case an investigation most often wants.
        divergence = compare(
            ORIGINAL,
            replayed(
                snapshot=SnapshotRef(kind="lsn", identifier="0/1A2B99", exact=True),
                verdict="pass",
                metrics={"scanned_rows": 50000.0, "violating_rows": 0.0},
            ),
        )
        assert divergence.cause is Cause.DATA_CHANGED
        assert not divergence.cause.needs_escalation
        assert "restatement" in divergence.render()

    def test_an_edited_control_makes_the_answers_incomparable(self) -> None:
        divergence = compare(ORIGINAL, replayed(plan_id="ir:sha256:" + "b" * 64, verdict="pass"))
        assert divergence.cause is Cause.CONTROL_CHANGED
        assert "different questions" in divergence.render()

    def test_the_control_wins_when_both_the_control_and_the_data_moved(self) -> None:
        # If the control moved, the answers were never comparable, and no
        # amount of looking at the data will explain the difference.
        divergence = compare(
            ORIGINAL,
            replayed(
                plan_id="ir:sha256:" + "b" * 64,
                snapshot=SnapshotRef(kind="lsn", identifier="0/999", exact=True),
                verdict="pass",
            ),
        )
        assert divergence.cause is Cause.CONTROL_CHANGED

    def test_different_parameters_mean_a_different_scope(self) -> None:
        divergence = compare(
            ORIGINAL, replayed(parameters={"business_date": "2026-04-03"}, verdict="pass")
        )
        assert divergence.cause is Cause.PARAMETERS_CHANGED

    def test_an_engine_disagreement_is_escalated(self) -> None:
        # Same plan, same data, different backend, different answer. This is a
        # portability failure and the conformance suite should have caught it.
        divergence = compare(ORIGINAL, replayed(engine="duckdb", verdict="pass"))
        assert divergence.cause is Cause.ENGINE_CHANGED
        assert divergence.cause.needs_escalation
        assert "should be escalated" in divergence.render()

    def test_an_inexact_snapshot_explains_itself(self) -> None:
        # The source admitted its identifier does not pin the data, so this run
        # was never replayable and the original record said so. Without
        # carrying that flag, this would look identical to an unexplained
        # divergence, and an estate of file-digest sources would generate
        # unexplained divergences nightly until nobody read them.
        loose = dataclasses.replace(
            ORIGINAL, snapshot=SnapshotRef(kind="wall_clock", identifier="t", exact=False)
        )
        divergence = compare(loose, dataclasses.replace(loose, sequence=99, verdict="pass"))
        assert divergence.cause is Cause.SNAPSHOT_NOT_EXACT
        assert not divergence.cause.needs_escalation

    def test_an_unexplained_divergence_is_reported_as_alarming(self) -> None:
        # Same plan, same exact snapshot, same engine, different answer. This
        # should not be possible, and smoothing it into one of the other causes
        # would hide the only case that means something is actually broken.
        divergence = compare(ORIGINAL, replayed(verdict="pass"))
        assert divergence.cause is Cause.UNEXPLAINED
        assert divergence.cause.needs_escalation
        assert "should not be possible" in divergence.render()


class TestWhatIsReported:
    def test_the_differing_metrics_are_listed(self) -> None:
        divergence = compare(
            ORIGINAL,
            replayed(metrics={"scanned_rows": 50000.0, "violating_rows": 3.0}),
        )
        fields = {field for field, _, _ in divergence.differences}
        assert "metrics.violating_rows" in fields
        assert "metrics.scanned_rows" not in fields

    def test_a_metric_that_appeared_or_vanished_is_reported(self) -> None:
        divergence = compare(ORIGINAL, replayed(metrics={"scanned_rows": 50000.0}))
        assert any(f == "metrics.violating_rows" for f, _, _ in divergence.differences)

    def test_a_verdict_change_is_distinguished_from_moved_numbers(self) -> None:
        same_verdict = compare(
            ORIGINAL, replayed(metrics={"scanned_rows": 50000.0, "violating_rows": 3.0})
        )
        assert not same_verdict.verdict_changed
        assert "with different numbers" in same_verdict.render()

    def test_it_serialises_for_an_investigation(self) -> None:
        payload = compare(ORIGINAL, replayed(engine="duckdb", verdict="pass")).to_dict()
        assert payload["cause"] == "engine_changed"
        assert payload["escalate"] is True
        assert payload["differences"]


class TestTheReport:
    def test_it_counts_by_cause(self) -> None:
        report = ReplayReport(
            divergences=(
                compare(ORIGINAL, replayed()),
                compare(
                    ORIGINAL,
                    replayed(snapshot=SnapshotRef("lsn", "0/999", True), verdict="pass"),
                ),
                compare(
                    ORIGINAL,
                    replayed(snapshot=SnapshotRef("lsn", "0/888", True), verdict="pass"),
                ),
            )
        )
        assert report.replayed == 3
        assert report.identical == 1
        assert report.by_cause()["data_changed"] == 2

    def test_the_gate_is_that_nothing_is_unexplained(self) -> None:
        # Not that everything replays identically — data legitimately changes —
        # but that nothing diverges without the report being able to say why.
        accounted = ReplayReport(
            divergences=(
                compare(
                    ORIGINAL,
                    replayed(snapshot=SnapshotRef("lsn", "0/999", True), verdict="pass"),
                ),
            )
        )
        assert accounted.all_accounted_for

        unexplained = ReplayReport(divergences=(compare(ORIGINAL, replayed(verdict="pass")),))
        assert not unexplained.all_accounted_for

    def test_escalations_are_surfaced_in_the_summary(self) -> None:
        report = ReplayReport(
            divergences=(compare(ORIGINAL, replayed(engine="duckdb", verdict="pass")),)
        )
        assert report.escalations
        assert "need escalation" in report.render()

    def test_an_empty_report_is_not_an_error(self) -> None:
        report = ReplayReport()
        assert report.all_accounted_for
        assert "Replayed 0 record(s)" in report.render()
