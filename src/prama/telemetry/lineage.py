"""Telling the rest of the estate what ran, in a format it already speaks.

Prama is not the only thing looking at a bank's data, and a platform that can
only be seen through its own console is one more silo. OpenLineage is the
standard every serious lineage and catalogue tool consumes — Marquez, DataHub,
OpenMetadata, Atlan, several warehouses natively — and it has a facet designed
for exactly what Prama produces.

`dataQualityAssertions` carries, per input dataset, a list of assertions with
their outcome and the column they were about. Emitting it means a Prama verdict
appears *inside* whatever catalogue the bank already runs, beside the lineage,
without an integration being written for each. The alternative is a webhook per
tool and a mapping nobody maintains.

Two things this deliberately does not do.

**It does not send the data.** A lineage event names datasets, columns and
outcomes. It never carries a failing row, because a lineage bus is the least
access-controlled pipe in most estates and the fastest way to move personal
data somewhere nobody meant it to be.

**It does not depend on the OpenLineage client library.** The event is
documented JSON, and a bank that will not add a dependency to a control plane
should still be able to publish. The emitter is a seam; where the events go —
HTTP, Kafka, a file — is a deployment decision.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from prama.core.clock import Clock, SystemClock
from prama.core.ids import new_ulid
from prama.evidence.record import EvidenceRecord
from prama.version import VERSION

#: Who produced the event. Part of the spec, and the thing a consumer uses to
#: tell Prama's events from everybody else's.
PRODUCER = f"https://prama.dev/openlineage/{VERSION}"

#: The version of the OpenLineage schema these events conform to.
SCHEMA_URL = "https://openlineage.io/spec/1-0-5/OpenLineage.json#/definitions/RunEvent"

FACET_SCHEMA = "https://openlineage.io/spec/facets/1-0-0/DataQualityAssertionsDatasetFacet.json"


class EventType(enum.Enum):
    START = "START"
    COMPLETE = "COMPLETE"
    FAIL = "FAIL"
    ABORT = "ABORT"

    @classmethod
    def for_verdict(cls, verdict: str) -> EventType:
        """A verdict as OpenLineage sees it.

        A failing control is a COMPLETE run that found something, not a FAILED
        one: the job did exactly what it was asked. FAIL is reserved for a run
        that could not answer, which is a different thing and is what an
        operator's alerting should key on.
        """
        return cls.FAIL if verdict in ("error", "aborted") else cls.COMPLETE


@dataclasses.dataclass(frozen=True, slots=True)
class Assertion:
    """One control's outcome, in the shape the facet expects."""

    assertion: str
    success: bool
    column: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"assertion": self.assertion, "success": self.success}
        if self.column:
            payload["column"] = self.column
        return payload


@dataclasses.dataclass(frozen=True, slots=True)
class RunEvent:
    """One OpenLineage event."""

    event_type: EventType
    event_time: datetime
    run_id: str
    job_namespace: str
    job_name: str
    inputs: tuple[dict[str, Any], ...] = ()
    outputs: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "eventType": self.event_type.value,
            "eventTime": self.event_time.isoformat(),
            "run": {"runId": self.run_id},
            "job": {"namespace": self.job_namespace, "name": self.job_name},
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "producer": PRODUCER,
            "schemaURL": SCHEMA_URL,
        }

    def to_json(self) -> str:
        from prama.core.pjson import dumps

        return dumps(self.to_dict(), sort_keys=True)


class LineageEmitter(ABC):
    """Where lineage events go. One method, because that is the whole seam."""

    @abstractmethod
    def emit(self, event: RunEvent) -> None: ...


class MemoryEmitter(LineageEmitter):
    """Collects events. For tests, and for a deployment that publishes in batches."""

    def __init__(self) -> None:
        self.events: list[RunEvent] = []

    def emit(self, event: RunEvent) -> None:
        self.events.append(event)

    def __len__(self) -> int:
        return len(self.events)


class NullEmitter(LineageEmitter):
    """Publishes nothing.

    The default. A platform that emitted to a bus nobody configured would fail
    on every run in an air-gapped deployment, and lineage is an integration
    rather than a requirement.
    """

    def emit(self, event: RunEvent) -> None:  # noqa: ARG002 - discarding is the point
        return None


class Lineage:
    """Turns evidence into events the rest of the estate understands."""

    def __init__(
        self,
        emitter: LineageEmitter | None = None,
        *,
        namespace: str = "prama",
        clock: Clock | None = None,
    ) -> None:
        self._emitter = NullEmitter() if emitter is None else emitter
        self._namespace = namespace
        self._clock = clock or SystemClock()

    def started(self, *, job: str, run_id: str = "", datasets: tuple[str, ...] = ()) -> str:
        """Announce a run beginning, and return its id.

        A START event before the work matters more than it looks: a consumer
        that only ever sees COMPLETE cannot tell a run that is slow from one
        that never happened.
        """
        identifier = run_id or f"run:{new_ulid()}"
        self._emitter.emit(
            RunEvent(
                event_type=EventType.START,
                event_time=self._clock.now(),
                run_id=identifier,
                job_namespace=self._namespace,
                job_name=job,
                inputs=tuple(self._dataset(d) for d in datasets),
            )
        )
        return identifier

    def finished(
        self,
        records: list[EvidenceRecord],
        *,
        job: str,
        run_id: str,
        source_namespace: str = "",
    ) -> RunEvent:
        """Publish what a run found, grouped by the dataset it was about."""
        by_dataset: dict[str, list[EvidenceRecord]] = {}
        for record in records:
            by_dataset.setdefault(record.dataset or "unknown", []).append(record)
        worst = _worst_verdict([r.verdict for r in records])
        event = RunEvent(
            event_type=EventType.for_verdict(worst),
            event_time=self._clock.now(),
            run_id=run_id,
            job_namespace=self._namespace,
            job_name=job,
            inputs=tuple(
                self._dataset(
                    dataset,
                    namespace=source_namespace or self._namespace,
                    assertions=[_assertion(r) for r in found],
                )
                for dataset, found in sorted(by_dataset.items())
            ),
        )
        self._emitter.emit(event)
        return event

    def _dataset(
        self,
        name: str,
        *,
        namespace: str = "",
        assertions: list[Assertion] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"namespace": namespace or self._namespace, "name": name}
        if assertions:
            payload["facets"] = {
                "dataQualityAssertions": {
                    "_producer": PRODUCER,
                    "_schemaURL": FACET_SCHEMA,
                    "assertions": [a.to_dict() for a in assertions],
                }
            }
        return payload


def _assertion(record: EvidenceRecord) -> Assertion:
    """One evidence record as a lineage assertion.

    The plan id is the assertion's name rather than a prose description: a
    consumer correlating two runs needs a stable identifier, and the sentence
    is available from Prama for anybody who wants it.
    """
    return Assertion(
        assertion=record.plan_id or record.control_id or "control",
        success=record.verdict == "pass",
    )


def _worst_verdict(verdicts: list[str]) -> str:
    """The least reassuring verdict in the list.

    An unrecognised string ranks *worst*, not best. The key used to be
    `order.index(v) if v in order else 0`, and `order[0]` is `"pass"` — so a
    verdict nobody recognised was given the rank of the best possible outcome,
    and a new verdict added anywhere, or a typo, silently improved the lineage
    event it appeared in (QA finding OPS-063).

    Ranking it worst is the only safe direction. A verdict this function does
    not understand is one it cannot vouch for, and a lineage consumer reading
    "pass" would take a claim nobody made.
    """
    order = ["pass", "skipped", "indeterminate", "fail", "error"]
    return max(verdicts, key=lambda v: order.index(v) if v in order else len(order), default="pass")
