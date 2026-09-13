"""Claiming work so exactly one worker does it, and nothing stale is recorded.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

import pytest

from prama.backend.execute import judge
from prama.core.concurrency.leases import MemoryLeaseProvider
from prama.core.errors import LeaseLostError
from prama.evidence import Ledger, Recorder, SampleStore
from prama.execute import (
    Claim,
    FencedWriter,
    StaleWriteError,
    Worker,
    WorkQueue,
    WorkUnit,
    claim_unit,
    run_fleet,
)
from prama.ir.lower import Lowerer
from prama.pql.parser import parse_control

PLAN = Lowerer().control(parse_control("CHECK t.a IS NOT NULL BECAUSE 'x'"))


def a_unit(resource: str = "scan:t", **changes: Any) -> WorkUnit:
    options: dict[str, Any] = {"resource": resource, "dataset": "t", "plan_ids": (PLAN.plan_id,)}
    options.update(changes)
    return WorkUnit(**options)


def a_runner(violating: float = 1.0):
    def run(unit: WorkUnit) -> list[tuple[Any, Any, Any]]:
        result = judge(PLAN, {"scanned_rows": 8.0, "violating_rows": violating})
        return [(PLAN, result, None)]

    return run


def a_worker(queue: WorkQueue, **changes: Any) -> tuple[Worker, Recorder]:
    recorder = Recorder(Ledger(), SampleStore(), engine="sqlite")
    options: dict[str, Any] = {
        "lease_provider": MemoryLeaseProvider(),
        "runner": a_runner(),
    }
    options.update(changes)
    return Worker(queue, recorder, **options), recorder


class TestOneUnitAtATime:
    async def test_a_worker_claims_runs_and_records(self) -> None:
        queue = WorkQueue()
        queue.offer(a_unit())
        worker, recorder = a_worker(queue)
        outcome = await worker.take_one()
        assert outcome is not None
        assert outcome.status == "done"
        assert len(recorder.ledger) == 1
        assert len(queue) == 0

    async def test_an_empty_queue_gives_nothing_rather_than_an_error(self) -> None:
        worker, _ = a_worker(WorkQueue())
        assert await worker.take_one() is None

    async def test_a_worker_only_takes_work_for_its_zone(self) -> None:
        queue = WorkQueue()
        queue.offer(a_unit("scan:a", zone="frankfurt"))
        queue.offer(a_unit("scan:b", zone="london"))
        worker, _ = a_worker(queue, zone="london")
        outcome = await worker.take_one()
        assert outcome is not None
        assert outcome.unit.resource == "scan:b"

    async def test_a_unit_held_by_another_worker_is_skipped_not_failed(self) -> None:
        # Losing a race is the ordinary case in a fleet. A worker that logged
        # an exception each time would drown its own useful output.
        provider = MemoryLeaseProvider()
        queue = WorkQueue()
        unit = a_unit()
        queue.offer(unit)
        held = await claim_unit(provider, unit, worker_id="other")
        assert held is not None

        worker, recorder = a_worker(queue, lease_provider=provider)
        assert await worker.take_one() is None
        assert len(recorder.ledger) == 0


class TestAFleet:
    async def test_two_workers_never_run_the_same_unit(self) -> None:
        # The obvious failure: two evidence records for one run.
        provider = MemoryLeaseProvider()
        queue = WorkQueue()
        for n in range(20):
            queue.offer(a_unit(f"scan:{n}"))
        workers = []
        recorders = []
        for n in range(4):
            worker, recorder = a_worker(queue, lease_provider=provider, worker_id=f"w{n}")
            workers.append(worker)
            recorders.append(recorder)

        report = await run_fleet(workers, queue)
        assert report.done == 20
        assert report.records == 20
        assert sum(len(r.ledger) for r in recorders) == 20

    async def test_the_report_names_what_did_not_finish(self) -> None:
        def explode(unit: WorkUnit) -> list:
            raise RuntimeError("source unreachable")

        queue = WorkQueue()
        queue.offer(a_unit())
        worker, _ = a_worker(queue, runner=explode)
        report = await run_fleet([worker], queue)
        assert report.failed
        assert "source unreachable" in report.render()

    async def test_a_failed_unit_is_not_requeued(self) -> None:
        # It produced an error verdict, which is a finding. Rerunning it
        # immediately would produce the same one.
        def explode(unit: WorkUnit) -> list:
            raise RuntimeError("nope")

        queue = WorkQueue()
        queue.offer(a_unit())
        worker, _ = a_worker(queue, runner=explode)
        await worker.take_one()
        assert len(queue) == 0


class TestFencing:
    """The failure a lease alone does not cover."""

    def test_a_newer_holder_shuts_out_an_older_one(self) -> None:
        # A worker stalls — a long GC, a stalled disk, a paused VM — its lease
        # expires, a second worker does the work properly, and then the first
        # wakes up and writes a result computed from data it read a minute ago.
        writer = FencedWriter()
        unit = a_unit()
        stalled = Claim(unit=unit, worker_id="slow", fencing_token=1)
        took_over = Claim(unit=unit, worker_id="fast", fencing_token=2)

        writer.accept(took_over)
        with pytest.raises(StaleWriteError) as caught:
            writer.accept(stalled)
        assert "already written" in str(caught.value)
        assert "older data" in caught.value.remedy

    def test_the_same_token_may_write_again(self) -> None:
        # A retry within one claim is not a stale write.
        writer = FencedWriter()
        claim = Claim(unit=a_unit(), worker_id="w", fencing_token=3)
        writer.accept(claim)
        writer.accept(claim)

    def test_different_resources_do_not_fence_each_other(self) -> None:
        writer = FencedWriter()
        writer.accept(Claim(unit=a_unit("scan:a"), worker_id="w", fencing_token=9))
        writer.accept(Claim(unit=a_unit("scan:b"), worker_id="w", fencing_token=1))

    def test_a_token_can_be_checked_without_committing_to_it(self) -> None:
        writer = FencedWriter()
        writer.accept(Claim(unit=a_unit(), worker_id="w", fencing_token=5))
        assert not writer.would_accept(Claim(unit=a_unit(), worker_id="x", fencing_token=4))
        assert writer.would_accept(Claim(unit=a_unit(), worker_id="x", fencing_token=6))

    async def test_a_worker_that_lost_its_claim_records_nothing(self) -> None:
        # The whole point: the check happens before the write, so a stale
        # verdict never reaches the ledger.
        queue = WorkQueue()
        queue.offer(a_unit())
        writer = FencedWriter()
        # Somebody newer has already written to this resource.
        writer.accept(Claim(unit=a_unit(), worker_id="newer", fencing_token=99))
        worker, recorder = a_worker(queue, writer=writer)

        outcome = await worker.take_one()
        assert outcome is not None
        assert outcome.status == "lost"
        assert len(recorder.ledger) == 0

    async def test_lost_work_is_requeued_for_somebody_else(self) -> None:
        # It was never recorded, so somebody must still do it.
        queue = WorkQueue()
        queue.offer(a_unit())
        writer = FencedWriter()
        writer.accept(Claim(unit=a_unit(), worker_id="newer", fencing_token=99))
        worker, _ = a_worker(queue, writer=writer)
        await worker.take_one()
        assert len(queue) == 1

    async def test_a_lost_lease_is_caught_before_recording(self) -> None:
        class Expired:
            fencing_token = 1

            def raise_if_lost(self) -> None:
                raise LeaseLostError("lease expired", remedy="Abandon the work.", context={})

        queue = WorkQueue()
        unit = a_unit()
        queue.offer(unit)
        worker, recorder = a_worker(queue)
        claim = Claim(unit=unit, worker_id="w", fencing_token=1, holder=Expired())
        outcome = await worker._run(claim)
        assert outcome.status == "lost"
        assert len(recorder.ledger) == 0


class TestTheQueue:
    def test_releasing_without_requeue_removes_the_work(self) -> None:
        queue = WorkQueue()
        unit = a_unit()
        queue.offer(unit)
        claim = Claim(unit=unit, worker_id="w", fencing_token=1)
        queue.take(unit, claim)
        queue.release(claim)
        assert len(queue) == 0

    def test_releasing_with_requeue_puts_it_back(self) -> None:
        queue = WorkQueue()
        unit = a_unit()
        queue.offer(unit)
        claim = Claim(unit=unit, worker_id="w", fencing_token=1)
        queue.take(unit, claim)
        queue.release(claim, requeue=True)
        assert len(queue) == 1

    def test_a_superseded_claim_cannot_release_the_current_one(self) -> None:
        # An old holder waking up must not free work somebody else is doing.
        queue = WorkQueue()
        unit = a_unit()
        queue.offer(unit)
        current = Claim(unit=unit, worker_id="new", fencing_token=2)
        queue.take(unit, current)
        queue.release(Claim(unit=unit, worker_id="old", fencing_token=1))
        assert queue.claimed_by("new")


class TestALedgerFailureDoesNotStrandTheWork:
    """Finding X4. The one path that stranded work permanently had no cleanup.

    `_run` carefully wraps the runner, and the claim check, and turns each into
    an outcome. It does not wrap the recorder — and `take_one` had no
    `try/finally` around `_run`, so a transiently unreachable evidence ledger
    raised straight out of both.

    The unit had already been removed from `_pending` by `queue.take()` and was
    never returned. `queue.release()` never ran, so the queue still recorded it
    as claimed. `release_claim()` never ran, so the lease holder's background
    task renewed the lease indefinitely. The unit was invisible to every worker
    in the fleet, nobody could ever claim its resource again, and `drain()`
    returned no outcome for it — so the fleet report did not mention it either.
    Not lost, not failed: gone.

    The existing coverage exercises a *runner* that explodes, which `_run`
    already handled. A recorder that explodes was never written.
    """

    def exploding_recorder(self) -> Recorder:
        class Unreachable(Recorder):
            def record(self, *arguments: Any, **keywords: Any) -> Any:
                raise RuntimeError("the ledger is unreachable")

        return Unreachable(Ledger(), SampleStore(), engine="sqlite")

    async def test_the_unit_comes_back_to_the_queue(self) -> None:
        queue = WorkQueue()
        queue.offer(a_unit())
        worker = Worker(
            queue,
            self.exploding_recorder(),
            lease_provider=MemoryLeaseProvider(),
            runner=a_runner(),
        )
        outcome = await worker.take_one()
        assert outcome is not None
        assert outcome.status == "stranded"
        assert outcome.should_requeue
        assert len(queue) == 1, "the unit was claimed and never returned"

    async def test_the_resource_can_be_claimed_again(self) -> None:
        """The part that makes it permanent. A held lease nobody releases is a
        resource no worker in the fleet can ever take."""
        queue = WorkQueue()
        queue.offer(a_unit())
        leases = MemoryLeaseProvider()
        failing = Worker(queue, self.exploding_recorder(), lease_provider=leases, runner=a_runner())
        await failing.take_one()

        healthy = Worker(
            queue,
            Recorder(Ledger(), SampleStore(), engine="sqlite"),
            lease_provider=leases,
            runner=a_runner(),
        )
        outcome = await healthy.take_one()
        assert outcome is not None, "no worker could claim the resource afterwards"
        assert outcome.status == "done"

    async def test_the_fleet_report_names_it(self) -> None:
        """It used to appear in no category at all."""
        queue = WorkQueue()
        queue.offer(a_unit())
        worker = Worker(
            queue,
            self.exploding_recorder(),
            lease_provider=MemoryLeaseProvider(),
            runner=a_runner(),
        )
        outcome = await worker.take_one()
        assert outcome is not None
        assert "the ledger is unreachable" in outcome.render()

    async def test_an_ordinary_unit_is_unaffected(self) -> None:
        """The counterfactual: a try/finally that requeued everything would
        make every unit run for ever."""
        queue = WorkQueue()
        queue.offer(a_unit())
        worker, _ = a_worker(queue)
        outcome = await worker.take_one()
        assert outcome is not None and outcome.status == "done"
        assert not outcome.should_requeue
        assert len(queue) == 0
