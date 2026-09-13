"""The worker: claim, run, record, release.

Stateless on purpose. A worker holds nothing between units of work, so adding
one is a deployment and losing one is a lease expiring. There is no worker
identity that matters beyond the life of a claim, no state to migrate, and
nothing to drain before a restart — which is what makes a fleet operable by
people who did not build it.

The loop is four steps and the order of the last two is the whole design:

1. **Claim** a unit, or move on. Another worker holding it is the ordinary case
   in a fleet, not an error.
2. **Run** the assignments in it, sharing one scan where the fuser said they
   could.
3. **Check the claim, then record.** In that order. Recording first and
   checking after would put a stale verdict on the ledger and then discover it.
4. **Release**, requeueing only if the work did not finish.

A worker never decides *what* to check, only *whether it is its turn*. Every
question about correctness — the plan, the threshold, the compiled query — was
settled before the work reached here, which is why a worker can be restarted,
duplicated or replaced without anybody thinking about it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import Any

from prama.backend.execute import ControlResult
from prama.core.clock import Clock, SystemClock
from prama.core.errors import LeaseLostError
from prama.core.ids import new_ulid
from prama.core.log import get_logger
from prama.evidence.record import EvidenceRecord
from prama.evidence.recorder import Recorder
from prama.execute.claim import (
    Claim,
    FencedWriter,
    StaleWriteError,
    WorkQueue,
    WorkUnit,
    claim_unit,
    release_claim,
)

_log = get_logger(__name__)

#: Runs one unit's work and returns a result per plan. Injected rather than
#: built here: a worker in the control plane runs SQL, a worker in an agent
#: runs the same thing against a source only it can reach, and neither belongs
#: in the loop that claims and records.
Runner = Callable[[WorkUnit], list[tuple[str, ControlResult, Any]]]


@dataclasses.dataclass(frozen=True, slots=True)
class WorkOutcome:
    """What one claimed unit produced."""

    unit: WorkUnit
    records: tuple[EvidenceRecord, ...] = ()
    #: ``done``, ``skipped``, ``lost``, ``failed`` or ``stranded``. Five,
    #: because they lead to five different next actions and collapsing them
    #: would hide which.
    status: str = "done"
    detail: str = ""

    @property
    def should_requeue(self) -> bool:
        """Whether the work still needs doing.

        A lost claim requeues: the work was not recorded, so somebody must do
        it. A failure does not: it produced an error verdict, which is a
        finding, and rerunning it immediately would produce the same one.

        ``stranded`` is the third case and it requeues. The unit ran and the
        *recording* failed — a ledger briefly unreachable — so there is no
        verdict anywhere and nobody knows the work was done. That is not a
        finding about the data, it is a finding about Prama, and the work still
        needs doing. Kept distinct from ``failed`` because an operator triaging
        a queue needs to tell "this control errored" from "we could not write
        down what it said".
        """
        return self.status in ("lost", "stranded")

    def render(self) -> str:
        return (
            f"{self.unit.resource}: {self.status}"
            + (f" — {self.detail}" if self.detail else "")
            + (f" ({len(self.records)} record(s))" if self.records else "")
        )


class Worker:
    """One executor. Stateless between units."""

    def __init__(
        self,
        queue: WorkQueue,
        recorder: Recorder,
        *,
        lease_provider: Any,
        runner: Runner,
        writer: FencedWriter | None = None,
        worker_id: str = "",
        zone: str = "",
        lease_seconds: float = 60.0,
        clock: Clock | None = None,
    ) -> None:
        self.worker_id = worker_id or f"worker:{new_ulid()}"
        self.zone = zone
        self._queue = queue
        self._recorder = recorder
        self._leases = lease_provider
        self._runner = runner
        self._writer = FencedWriter() if writer is None else writer
        self._lease_seconds = lease_seconds
        self._clock = clock or SystemClock()

    @property
    def writer(self) -> FencedWriter:
        return self._writer

    # -- one unit ----------------------------------------------------------

    async def take_one(self) -> WorkOutcome | None:
        """Claim and run the next unit this worker can have.

        None means there was nothing to take — either the queue is empty or
        every unit in it is held by somebody else. Both are ordinary.
        """
        for unit in self._queue.pending(self.zone):
            claim = await claim_unit(
                self._leases, unit, worker_id=self.worker_id, ttl_seconds=self._lease_seconds
            )
            if claim is None:
                continue
            self._queue.take(unit, claim)
            # try/finally, and not because `_run` is expected to raise: it
            # catches a failing runner and a lost lease and turns both into an
            # outcome. What it does *not* guard is the recorder, and finding X4
            # is what that costs. A transiently unreachable evidence ledger
            # raised out of `_run`, so `queue.release` never ran and the unit
            # stayed claimed, `release_claim` never ran and the lease renewed
            # itself for ever, and the unit was invisible to every worker in
            # the fleet — not lost, not failed, absent from the report
            # entirely. The one path that strands work permanently was the one
            # path with no cleanup.
            outcome: WorkOutcome | None = None
            try:
                outcome = await self._run(claim)
                return outcome
            except Exception as exc:
                _log.exception(
                    "%s could not complete %s; requeuing: %s",
                    self.worker_id,
                    claim.resource,
                    exc,
                )
                # Requeued rather than dropped. The unit was claimed, so
                # something meant to run it; a failure to record is a reason to
                # try again, not a reason for the work to vanish.
                return WorkOutcome(
                    unit=claim.unit,
                    status="stranded",
                    detail=f"{type(exc).__name__}: {exc}",
                )
            finally:
                self._queue.release(
                    claim, requeue=outcome.should_requeue if outcome is not None else True
                )
                await release_claim(claim)
        return None

    async def drain(self, limit: int = 0) -> list[WorkOutcome]:
        """Keep taking work until there is none, or until *limit* units."""
        outcomes: list[WorkOutcome] = []
        while limit <= 0 or len(outcomes) < limit:
            outcome = await self.take_one()
            if outcome is None:
                break
            outcomes.append(outcome)
        return outcomes

    # -- the work ----------------------------------------------------------

    async def _run(self, claim: Claim) -> WorkOutcome:
        started = self._clock.now()
        try:
            results = self._runner(claim.unit)
        except Exception as exc:  # a unit that will not run is a finding
            _log.warning("%s failed on %s: %s", self.worker_id, claim.resource, exc)
            return WorkOutcome(
                unit=claim.unit,
                status="failed",
                detail=f"{type(exc).__name__}: {exc}",
            )

        try:
            # Checked before anything is written, not after. Recording first
            # would put a stale verdict on the ledger and discover it later,
            # which is the failure the fencing token exists to prevent.
            claim.check()
            self._writer.accept(claim)
        except (LeaseLostError, StaleWriteError) as exc:
            _log.error(
                "%s finished %s but no longer holds it; the result is discarded: %s",
                self.worker_id,
                claim.resource,
                exc.args[0],
            )
            return WorkOutcome(unit=claim.unit, status="lost", detail=str(exc.args[0]))

        written = [
            self._recorder.record(
                plan,
                result,
                snapshot=snapshot,
                started_at=started,
                triggered_by=f"worker:{self.worker_id}",
            )
            for plan, result, snapshot in _as_triples(results)
        ]
        return WorkOutcome(unit=claim.unit, records=tuple(written), status="done")


def _as_triples(results: Any) -> list[tuple[Any, ControlResult, Any]]:
    """Normalise a runner's return into (plan, result, snapshot).

    Runners differ — one has a snapshot, another does not — and a worker that
    branched on the shape of what it was handed would encode every runner's
    quirks into the loop that is supposed to be independent of them.
    """
    triples: list[tuple[Any, ControlResult, Any]] = []
    for entry in results:
        if len(entry) == 3:
            triples.append((entry[0], entry[1], entry[2]))
        else:
            triples.append((entry[0], entry[1], None))
    return triples


@dataclasses.dataclass(frozen=True, slots=True)
class FleetReport:
    """What a pool of workers got through, and what it could not."""

    outcomes: tuple[WorkOutcome, ...] = ()
    remaining: int = 0

    @property
    def done(self) -> int:
        return sum(1 for o in self.outcomes if o.status == "done")

    @property
    def lost(self) -> tuple[WorkOutcome, ...]:
        return tuple(o for o in self.outcomes if o.status == "lost")

    @property
    def failed(self) -> tuple[WorkOutcome, ...]:
        return tuple(o for o in self.outcomes if o.status == "failed")

    @property
    def records(self) -> int:
        return sum(len(o.records) for o in self.outcomes)

    def render(self) -> str:
        lines = [
            f"{self.done} unit(s) completed, {self.records} record(s) written, "
            f"{self.remaining} still queued."
        ]
        if self.lost:
            # Named, because a lost claim means work was done and thrown away.
            # A fleet losing claims regularly has a lease shorter than its work.
            lines.append(f"{len(self.lost)} claim(s) were lost mid-run:")
            lines.extend(f"  {o.render()}" for o in self.lost)
        if self.failed:
            lines.append(f"{len(self.failed)} unit(s) failed:")
            lines.extend(f"  {o.render()}" for o in self.failed)
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "done": self.done,
            "records": self.records,
            "lost": [o.render() for o in self.lost],
            "failed": [o.render() for o in self.failed],
            "remaining": self.remaining,
            "summary": self.render(),
        }


async def run_fleet(workers: list[Worker], queue: WorkQueue) -> FleetReport:
    """Run several workers against one queue until it is empty.

    Concurrently, because the point of a fleet is that two workers racing for
    the same unit is the normal case and exactly one of them wins it.
    """
    import asyncio

    results = await asyncio.gather(*(w.drain() for w in workers))
    return FleetReport(outcomes=tuple(o for batch in results for o in batch), remaining=len(queue))
