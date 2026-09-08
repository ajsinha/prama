"""The wave's demo, executed: run a suite, verify offline, replay, restate.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

import pytest

from prama.backend import example as worked
from prama.backend.fuse import Fuser
from prama.evidence import Ledger, Recorder, SampleStore, compare, verify
from prama.evidence.replay import Cause, ReplayReport
from prama.ir.lower import Lowerer
from prama.ir.model import ControlPlan
from prama.pql.parser import parse


class Snapshot:
    """A source's account of its own state, as a connector would give it."""

    def __init__(self, identifier: str, *, exact: bool = True) -> None:
        self.kind = "file_digest"
        self.identifier = identifier
        self.exact = exact


@pytest.fixture(scope="module")
def plans() -> list[ControlPlan]:
    lowerer = Lowerer(codelists={"iso4217": worked.ISO4217})
    return [lowerer.control(c) for c in parse(worked.SUITE).all_controls]


def runner(rows: tuple) -> Any:
    connection = sqlite3.connect(":memory:")
    connection.execute(worked.create_positions(dialect="sqlite"))
    connection.execute(worked.create_accounts())
    connection.executemany(worked.insert_positions(), [list(r) for r in rows])
    connection.executemany(worked.insert_accounts(), [list(r) for r in worked.ACCOUNTS])
    connection.commit()

    def run(sql: str) -> list[dict[str, Any]]:
        cursor = connection.execute(sql)
        columns = [d[0] for d in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]

    return run


def run_suite(
    plans: list[ControlPlan], rows: tuple, snapshot: Snapshot, recorder: Recorder
) -> list:
    execute = runner(rows)
    fuser = Fuser("sqlite")
    results = []
    for group in fuser.group(plans):
        query = fuser.fuse(group, table=group.dataset)
        results.extend(query.unpack(execute(query.sql)))
    by_plan = {r.plan_id: r for r in results}
    return [
        recorder.record(
            plan,
            by_plan[plan.plan_id],
            snapshot=snapshot,
            parameters={"business_date": "2026-04-02"},
            control_id=f"ctl-{index}",
        )
        for index, plan in enumerate(plans)
    ]


#: The same day's positions with the missing notional supplied — a restatement,
#: which is the ordinary reason a replay differs.
RESTATED = tuple(
    row if row[5] is not None else (*row[:5], 999.0, row[6]) for row in worked.POSITIONS
)


@pytest.fixture
def monday(plans: list[ControlPlan]) -> tuple[Recorder, list]:
    recorder = Recorder(Ledger(), SampleStore(), engine="sqlite", tenant_id="t1")
    written = run_suite(plans, worked.POSITIONS, Snapshot("digest-monday"), recorder)
    return recorder, written


class TestRunningASuiteLeavesEvidence:
    def test_one_record_per_control(self, monday: tuple, plans: list) -> None:
        recorder, written = monday
        assert len(written) == len(plans)
        assert len(recorder.ledger) == len(plans)

    def test_the_chain_verifies(self, monday: tuple) -> None:
        assert monday[0].ledger.verify().is_intact

    def test_records_stay_under_two_kilobytes(self, monday: tuple) -> None:
        sizes = sorted(r.size_bytes for r in monday[0].ledger)
        assert sizes[len(sizes) // 2] < 2048

    def test_each_record_names_the_plan_and_the_data_state(self, monday: tuple) -> None:
        for record in monday[0].ledger:
            assert record.plan_id.startswith("ir:sha256:")
            assert record.snapshot.identifier == "digest-monday"
            assert record.snapshot.exact

    def test_the_verdicts_are_the_ones_the_suite_found(self, monday: tuple) -> None:
        verdicts = [r.verdict for r in monday[0].ledger]
        assert verdicts == [e.verdict for e in worked.EXPECTED]


class TestVerifyingWithoutPrama:
    def test_an_exported_chain_checks_with_stdlib_alone(self, monday: tuple) -> None:
        # The claim the audit proposition rests on, exercised against real
        # evidence rather than a fixture.
        previous = "0" * 64
        for line in monday[0].ledger.export().splitlines():
            record = json.loads(line)
            content = {
                k: v
                for k, v in record.items()
                if k not in ("previous_hash", "content_hash", "record_hash")
            }
            digest = hashlib.sha256(
                json.dumps(content, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            assert digest == record["content_hash"]
            assert record["previous_hash"] == previous
            previous = record["record_hash"]

    def test_tampering_with_a_verdict_is_caught(self, monday: tuple) -> None:
        payloads = [r.to_dict() for r in monday[0].ledger]
        payloads[0]["verdict"] = "pass"
        assert not verify(payloads).is_intact


class TestReplay:
    def test_the_same_data_replays_identically(self, plans: list, monday: tuple) -> None:
        _, first = monday
        again = run_suite(
            plans,
            worked.POSITIONS,
            Snapshot("digest-monday"),
            Recorder(Ledger(), SampleStore(), engine="sqlite"),
        )
        report = ReplayReport(tuple(compare(a, b) for a, b in zip(first, again, strict=True)))
        assert report.identical == len(first)
        assert report.all_accounted_for

    def test_restated_data_diverges_and_the_report_names_why(
        self, plans: list, monday: tuple
    ) -> None:
        _, first = monday
        third = run_suite(
            plans,
            RESTATED,
            Snapshot("digest-tuesday"),
            Recorder(Ledger(), SampleStore(), engine="sqlite"),
        )
        report = ReplayReport(tuple(compare(a, b) for a, b in zip(first, third, strict=True)))
        assert report.by_cause()["data_changed"] == 2
        assert report.all_accounted_for
        assert not report.escalations
        assert "restatement" in report.render()

    def test_the_controls_whose_answer_held_are_not_reported_as_diverged(
        self, plans: list, monday: tuple
    ) -> None:
        # Only two controls' answers moved. Reporting all seven as diverged
        # because the snapshot identifier changed would bury the two that
        # matter among five that do not.
        _, first = monday
        third = run_suite(
            plans,
            RESTATED,
            Snapshot("digest-tuesday"),
            Recorder(Ledger(), SampleStore(), engine="sqlite"),
        )
        report = ReplayReport(tuple(compare(a, b) for a, b in zip(first, third, strict=True)))
        assert report.held == 5
        assert report.by_cause()["stable"] == 5

    def test_an_engine_disagreement_would_be_escalated(self, plans: list, monday: tuple) -> None:
        # Not reachable through the real path — the conformance suite exists to
        # make it unreachable — so it is constructed, because the escalation
        # rule is worth having a test for whether or not it ever fires.
        import dataclasses

        _, first = monday
        divergent = dataclasses.replace(first[0], engine="duckdb", verdict="pass")
        report = ReplayReport((compare(first[0], divergent),))
        assert report.escalations
        assert report.escalations[0].cause is Cause.ENGINE_CHANGED


class TestSamplesAreKeptApart:
    def test_a_record_names_its_samples_without_carrying_them(self, plans: list) -> None:
        recorder = Recorder(Ledger(), SampleStore(), engine="sqlite")
        execute = runner(worked.POSITIONS)
        fuser = Fuser("sqlite")
        group = fuser.group(plans)[0]
        query = fuser.fuse(group, table=group.dataset)
        result = query.unpack(execute(query.sql))[1]
        record = recorder.record(
            plans[1],
            result,
            snapshot=Snapshot("digest-monday"),
            rows=[{"account_id": "A3", "notional_amount": None}],
            masked=("counterparty",),
        )
        assert record.sample_count == 1
        assert record.samples_digest.startswith("sha256:")
        assert "A3" not in record.to_json()
        assert recorder.samples.get(record.samples_digest) is not None

    def test_expiring_the_samples_leaves_the_record_standing(self, plans: list) -> None:
        # The point of the separation: the evidence still says what was found
        # and how many rows, and says honestly that the rows are gone.
        recorder = Recorder(Ledger(), SampleStore(), engine="sqlite")
        execute = runner(worked.POSITIONS)
        fuser = Fuser("sqlite")
        group = fuser.group(plans)[0]
        query = fuser.fuse(group, table=group.dataset)
        result = query.unpack(execute(query.sql))[1]
        record = recorder.record(plans[1], result, snapshot=Snapshot("d"), rows=[{"a": 1}])
        assert recorder.samples.forget(record.samples_digest)
        assert recorder.ledger.verify().is_intact
        assert record.sample_count == 1
        assert recorder.samples.get(record.samples_digest) is None

    def test_masked_columns_are_declared(self, plans: list) -> None:
        # So a reader knows what they are not seeing rather than assuming the
        # row is complete.
        store = SampleStore()
        sample = store.put([{"lei": "***"}], masked=("lei",))
        assert sample.masked == ("lei",)
        assert store.get(sample.digest) is not None


class TestHonestyAboutWhatWasNotEstablished:
    def test_a_source_with_no_snapshot_is_marked_inexact(self, plans: list) -> None:
        # Filling it in from the clock would make every record look replayable,
        # and the divergence report would then have no way to tell a source
        # that cannot identify its state from one that can and disagreed.
        recorder = Recorder(Ledger(), SampleStore(), engine="sqlite")
        written = run_suite(plans, worked.POSITIONS, None, recorder)  # type: ignore[arg-type]
        assert all(not r.snapshot.exact for r in written)
        assert all(r.snapshot.kind == "none" for r in written)

    def test_an_inexact_snapshot_explains_its_own_divergence(self, plans: list) -> None:
        loose = Snapshot("t", exact=False)
        first = run_suite(
            plans, worked.POSITIONS, loose, Recorder(Ledger(), SampleStore(), engine="sqlite")
        )
        second = run_suite(
            plans, RESTATED, loose, Recorder(Ledger(), SampleStore(), engine="sqlite")
        )
        report = ReplayReport(tuple(compare(a, b) for a, b in zip(first, second, strict=True)))
        assert report.by_cause()["snapshot_not_exact"] == 2
        assert not report.escalations
