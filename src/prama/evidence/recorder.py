"""Turning a control run into an evidence record.

The seam between execution and the ledger, and the place where two decisions
are made that decide whether the record is worth keeping.

**Samples are separated from the record.** The failing rows are the most useful
thing on the screen when somebody investigates and the most expensive thing to
keep for seven years. They live in their own store, addressed by hash, with
their own retention; the record carries the hash and the count. So the record is
permanent and small, the samples expire, and the record still says exactly what
it was that expired.

**Nothing is recorded that the run did not establish.** A metric the engine did
not return is absent rather than zero, and a snapshot the source could not
provide is marked inexact rather than filled in with the clock. Both are
temptations because both make the record look more complete, and both would
make it a worse record.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama_kernel.samples import SampleSet, SampleStore

#: SampleSet and SampleStore moved to the kernel; re-exported here for the server.
__all__ = ["Recorder", "SampleSet", "SampleStore"]

from prama.backend.execute import ControlResult
from prama.core.clock import Clock, SystemClock
from prama.evidence.ledger import Ledger
from prama.evidence.record import EvidenceRecord, SnapshotRef
from prama.ir.model import ControlPlan


class Recorder:
    """Writes a run into the ledger."""

    def __init__(
        self,
        ledger: Ledger | None = None,
        samples: SampleStore | None = None,
        *,
        clock: Clock | None = None,
        engine: str = "",
        tenant_id: str = "",
    ) -> None:
        # `if None`, not `or`: both define __len__, so an empty one passed in
        # is falsy and `or` would silently replace it with a different object.
        # The caller would then hold a ledger that never fills.
        self.ledger = Ledger() if ledger is None else ledger
        self.samples = SampleStore() if samples is None else samples
        self._clock = clock or SystemClock()
        self._engine = engine
        self._tenant = tenant_id

    def record(
        self,
        plan: ControlPlan,
        result: ControlResult,
        *,
        snapshot: Any = None,
        parameters: dict[str, str] | None = None,
        started_at: Any = None,
        rows: list[dict[str, Any]] | None = None,
        masked: tuple[str, ...] = (),
        triggered_by: str = "schedule",
        control_id: str = "",
        control_version: int = 1,
        coverage: str = "full",
        criticality: int = 4,
    ) -> EvidenceRecord:
        finished = self._clock.now()
        started = started_at or finished
        sample = self.samples.put(rows, masked=masked) if rows else None
        return self.ledger.append(
            EvidenceRecord(
                plan_id=plan.plan_id,
                control_id=control_id or plan.provenance.pql_hash,
                control_version=control_version,
                dataset=plan.scope.dataset,
                binding=plan.scope.binding,
                snapshot=_snapshot_ref(snapshot),
                parameters=dict(sorted((parameters or {}).items())),
                engine=result.engine or self._engine,
                coverage=coverage,
                verdict=result.verdict.value,
                metrics=dict(result.metrics),
                samples_digest=sample.digest if sample else "",
                sample_count=sample.count if sample else 0,
                started_at=started.isoformat(),
                finished_at=finished.isoformat(),
                duration_ms=max(0, int((finished - started).total_seconds() * 1000)),
                triggered_by=triggered_by,
                tenant_id=self._tenant,
                # From the plan, not from the caller: the dimensions are a
                # property of the control that ran, and a run that could label
                # its own results would let two records of the same control
                # score against different dimensions.
                dimensions=tuple(plan.dimensions),
                # The tier the control ran *under*. Carried rather than looked
                # up later, because re-tiering a dataset next year must not
                # silently re-weight last year's score.
                criticality=criticality,
            )
        )


def _snapshot_ref(snapshot: Any) -> SnapshotRef:
    """The source's own account of what state was read.

    A source with no snapshot gets one marked inexact rather than one filled in
    from the clock. Filling it in would make every record look replayable, and
    the divergence report would then have no way to tell a source that cannot
    identify its state from one that can and disagreed.
    """
    if snapshot is None:
        return SnapshotRef(kind="none", identifier="", exact=False)
    return SnapshotRef(
        kind=getattr(snapshot.kind, "value", str(snapshot.kind)),
        identifier=str(snapshot.identifier),
        exact=bool(snapshot.exact),
    )
