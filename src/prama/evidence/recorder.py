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

import dataclasses
import hashlib
from typing import Any

from prama.backend.execute import ControlResult
from prama.core.clock import Clock, SystemClock
from prama.core.pjson import canonical
from prama.evidence.ledger import Ledger
from prama.evidence.record import EvidenceRecord, SnapshotRef
from prama.ir.model import ControlPlan


@dataclasses.dataclass(frozen=True, slots=True)
class SampleSet:
    """Failing rows, kept apart from the record that refers to them."""

    digest: str
    rows: tuple[dict[str, Any], ...] = ()
    #: Which columns were masked before storage, so a reader knows what they
    #: are not seeing rather than assuming the row is complete.
    masked: tuple[str, ...] = ()

    @property
    def count(self) -> int:
        return len(self.rows)

    def to_dict(self) -> dict[str, Any]:
        return {
            "digest": self.digest,
            "count": self.count,
            "masked": list(self.masked),
            "rows": [dict(r) for r in self.rows],
        }


class SampleStore:
    """Where samples live. In memory here; the seam is deliberately two methods.

    Separate from the ledger because their lifetimes differ by years: an
    evidence record is kept for as long as the regulation requires, and the
    rows behind it are usually kept for as long as somebody might investigate.
    Storing them together forces the shorter retention onto both or the longer
    cost onto both, and neither is right.
    """

    def __init__(self) -> None:
        self._sets: dict[str, SampleSet] = {}

    def put(self, rows: list[dict[str, Any]], *, masked: tuple[str, ...] = ()) -> SampleSet:
        digest = "sha256:" + hashlib.sha256(canonical(rows)).hexdigest()[:32]
        sample = SampleSet(digest=digest, rows=tuple(rows), masked=masked)
        self._sets[digest] = sample
        return sample

    def get(self, digest: str) -> SampleSet | None:
        return self._sets.get(digest)

    def forget(self, digest: str) -> bool:
        """Expire one sample set, leaving the record that names it intact.

        Which is the point of the separation: the evidence still says what was
        found and how many rows, and says honestly that the rows themselves are
        gone.
        """
        return self._sets.pop(digest, None) is not None

    def __len__(self) -> int:
        return len(self._sets)


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
        self.ledger = ledger or Ledger()
        self.samples = samples or SampleStore()
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
                verdict=result.verdict.value,
                metrics=dict(result.metrics),
                samples_digest=sample.digest if sample else "",
                sample_count=sample.count if sample else 0,
                started_at=started.isoformat(),
                finished_at=finished.isoformat(),
                duration_ms=max(0, int((finished - started).total_seconds() * 1000)),
                triggered_by=triggered_by,
                tenant_id=self._tenant,
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
