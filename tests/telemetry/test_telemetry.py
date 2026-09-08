"""Telling the rest of the estate what ran, and timing it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json

import pytest

from prama.evidence.record import EvidenceRecord
from prama.telemetry import (
    EXECUTE,
    Lineage,
    MemoryEmitter,
    MemoryTracer,
    NullEmitter,
    NullTracer,
)
from prama.telemetry.lineage import EventType

RECORDS = [
    EvidenceRecord(plan_id="ir:sha256:aaa", dataset="positions_eod", verdict="pass"),
    EvidenceRecord(plan_id="ir:sha256:bbb", dataset="positions_eod", verdict="fail"),
    EvidenceRecord(plan_id="ir:sha256:ccc", dataset="accounts", verdict="pass"),
]


class TestLineageEvents:
    def test_a_run_is_announced_before_it_finishes(self) -> None:
        # A consumer that only ever sees COMPLETE cannot tell a run that is
        # slow from one that never happened.
        emitter = MemoryEmitter()
        lineage = Lineage(emitter)
        run_id = lineage.started(job="positions_eod_core", datasets=("positions_eod",))
        assert emitter.events[0].event_type is EventType.START
        assert run_id.startswith("run:")

    def test_findings_are_grouped_by_the_dataset_they_are_about(self) -> None:
        emitter = MemoryEmitter()
        Lineage(emitter).finished(RECORDS, job="suite", run_id="run:1")
        event = emitter.events[0]
        assert [i["name"] for i in event.inputs] == ["accounts", "positions_eod"]

    def test_the_assertions_facet_carries_each_outcome(self) -> None:
        # Which is what makes a Prama verdict appear inside whatever catalogue
        # the bank already runs.
        emitter = MemoryEmitter()
        Lineage(emitter).finished(RECORDS, job="suite", run_id="run:1")
        positions = next(i for i in emitter.events[0].inputs if i["name"] == "positions_eod")
        facet = positions["facets"]["dataQualityAssertions"]
        assert facet["_schemaURL"].endswith("DataQualityAssertionsDatasetFacet.json")
        assert [a["success"] for a in facet["assertions"]] == [True, False]

    def test_a_failing_control_is_a_completed_run(self) -> None:
        # The job did exactly what it was asked. FAIL is reserved for a run
        # that could not answer, which is what an operator's alerting keys on.
        emitter = MemoryEmitter()
        Lineage(emitter).finished(RECORDS, job="suite", run_id="run:1")
        assert emitter.events[0].event_type is EventType.COMPLETE

    def test_a_control_that_could_not_answer_is_a_failed_run(self) -> None:
        emitter = MemoryEmitter()
        Lineage(emitter).finished(
            [EvidenceRecord(plan_id="p", dataset="d", verdict="error")],
            job="suite",
            run_id="run:1",
        )
        assert emitter.events[0].event_type is EventType.FAIL

    def test_the_event_conforms_to_the_spec_shape(self) -> None:
        emitter = MemoryEmitter()
        Lineage(emitter).finished(RECORDS, job="suite", run_id="run:1")
        payload = json.loads(emitter.events[0].to_json())
        assert set(payload) >= {
            "eventType",
            "eventTime",
            "run",
            "job",
            "inputs",
            "producer",
            "schemaURL",
        }
        assert payload["run"]["runId"] == "run:1"
        assert payload["producer"].startswith("https://prama.dev/openlineage/")

    def test_no_row_data_ever_reaches_the_lineage_bus(self) -> None:
        # A lineage bus is the least access-controlled pipe in most estates and
        # the fastest way to move personal data somewhere nobody meant it to be.
        emitter = MemoryEmitter()
        Lineage(emitter).finished(
            [
                EvidenceRecord(
                    plan_id="p",
                    dataset="positions_eod",
                    verdict="fail",
                    parameters={"subject": "person-42"},
                    samples_digest="sha256:abc",
                )
            ],
            job="suite",
            run_id="run:1",
        )
        published = emitter.events[0].to_json()
        assert "person-42" not in published
        assert "sha256:abc" not in published

    def test_the_default_publishes_nothing(self) -> None:
        # A platform emitting to a bus nobody configured would fail on every
        # run in an air-gapped deployment.
        lineage = Lineage()
        lineage.finished(RECORDS, job="suite", run_id="run:1")  # does not raise
        assert isinstance(Lineage()._emitter, NullEmitter)

    def test_a_source_namespace_can_be_declared(self) -> None:
        # So a dataset in the lineage graph is the *warehouse's* dataset rather
        # than one Prama invented, and the two halves of the graph join up.
        emitter = MemoryEmitter()
        Lineage(emitter).finished(
            RECORDS, job="suite", run_id="run:1", source_namespace="snowflake://risk"
        )
        assert emitter.events[0].inputs[0]["namespace"] == "snowflake://risk"


class TestTracing:
    def test_a_span_is_recorded_with_its_duration(self) -> None:
        tracer = MemoryTracer()
        with tracer.span(EXECUTE, dataset="positions_eod") as span:
            span.set(rows=8)
        assert len(tracer) == 1
        assert tracer.spans[0].attributes == {"dataset": "positions_eod", "rows": 8}
        assert tracer.spans[0].duration_ms >= 0

    def test_attributes_can_be_added_during_the_span(self) -> None:
        # A span describable only before it ran would have to guess the row
        # count, and a trace whose attributes are guesses is one nobody can
        # reason from.
        tracer = MemoryTracer()
        with tracer.span(EXECUTE) as span:
            span.set(rows=50_000)
        assert tracer.spans[0].attributes["rows"] == 50_000

    def test_a_span_that_raised_is_still_recorded(self) -> None:
        # It is the four-minute query that failed, and losing it leaves a gap
        # exactly where the investigation starts.
        tracer = MemoryTracer()
        with pytest.raises(RuntimeError), tracer.span(EXECUTE):
            raise RuntimeError("connection reset")
        assert len(tracer) == 1
        assert "connection reset" in tracer.spans[0].error

    def test_the_slowest_spans_are_findable(self) -> None:
        tracer = MemoryTracer()
        for name in ("a", "b", "c"):
            with tracer.span(name):
                pass
        assert len(tracer.slowest(2)) == 2

    def test_the_default_tracer_costs_a_function_call(self) -> None:
        tracer = NullTracer()
        with tracer.span(EXECUTE, dataset="d") as span:
            span.set(rows=1)
        # Nothing to assert but that it did not raise, which is the point: a
        # bank evaluating on a laptop and a bank on a fleet run the same code.

    def test_span_names_are_declared_once(self) -> None:
        # So a dashboard built against one deployment works against the next.
        from prama.telemetry import CLAIM, COMPILE, DELIVER, JUDGE, RECORD

        assert {CLAIM, COMPILE, EXECUTE, JUDGE, RECORD, DELIVER} == {
            "prama.claim",
            "prama.compile",
            "prama.execute",
            "prama.judge",
            "prama.record",
            "prama.deliver",
        }
