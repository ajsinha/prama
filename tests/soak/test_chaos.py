"""What survives when things go wrong, asserted as invariants.

Individually, each failure here has a unit test. This runs them together and at
random, because the failures that reach production are combinations — a worker
stalls *while* the control plane is unreachable *while* a source is refusing
connections — and a system tested one failure at a time is tested for the easy
half.

Four invariants, and they are the ones that decide whether the evidence can be
trusted after a bad night:

1. **Nothing is lost.** Work that completed produced exactly one record.
2. **Nothing is duplicated.** Redelivery and retries do not create a second.
3. **The chain always verifies.** Whatever happened, the ledger is intact.
4. **Progress is made.** A system that survives by doing nothing has not
   survived.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import random
from typing import Any

import pytest

from prama.agent import (
    Agent,
    AgentCapabilities,
    AgentRegistry,
    Assignment,
    Coordinator,
    Receipt,
    ResidencyPolicy,
    SampleDisposition,
    Spool,
)
from prama.backend.execute import judge
from prama.core.concurrency.leases import MemoryLeaseProvider
from prama.evidence import Ledger, Recorder, SampleStore
from prama.execute import Claim, FencedWriter, Worker, WorkQueue, WorkUnit, run_fleet
from prama.ir.lower import Lowerer
from prama.pql.parser import parse_control

PLAN = Lowerer().control(parse_control("CHECK t.a IS NOT NULL BECAUSE 'x'"))


def a_unit(n: int) -> WorkUnit:
    return WorkUnit(resource=f"scan:{n}", dataset="t", plan_ids=(PLAN.plan_id,))


def a_runner(rng: random.Random, failure_rate: float = 0.0):
    """A source that sometimes will not answer."""

    def run(unit: WorkUnit) -> list[tuple[Any, Any, Any]]:
        if rng.random() < failure_rate:
            raise ConnectionError(f"{unit.dataset} refused the connection")
        return [(PLAN, judge(PLAN, {"scanned_rows": 8.0, "violating_rows": 1.0}), None)]

    return run


class TestAFleetUnderStress:
    @pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
    async def test_the_invariants_hold_whatever_happens(self, seed: int) -> None:
        rng = random.Random(seed)
        provider = MemoryLeaseProvider()
        queue = WorkQueue()
        units = 60
        for n in range(units):
            queue.offer(a_unit(n))

        writer = FencedWriter()
        recorders = []
        workers = []
        for n in range(5):
            recorder = Recorder(Ledger(), SampleStore(), engine="duckdb")
            recorders.append(recorder)
            workers.append(
                Worker(
                    queue,
                    recorder,
                    lease_provider=provider,
                    runner=a_runner(rng, failure_rate=0.15),
                    writer=writer,
                    worker_id=f"w{n}",
                )
            )

        report = await run_fleet(workers, queue)

        # 1. Nothing is lost: every unit that completed wrote exactly one record.
        assert report.records == report.done

        # 2. Nothing is duplicated: no resource was recorded by two workers.
        recorded = [r.plan_id for rec in recorders for r in rec.ledger]
        assert len(recorded) == report.records

        # 3. Every chain verifies.
        assert all(rec.ledger.verify().is_intact for rec in recorders)

        # 4. Progress: a system that survives by doing nothing has not survived.
        assert report.done > units * 0.5
        # And a failing source produced findings rather than stopping the fleet.
        assert report.done + len(report.failed) == units

    async def test_a_stalled_worker_cannot_write_over_a_newer_one(self) -> None:
        # The whole reason for fencing: a worker resumes after a pause, its
        # lease long gone, holding a result computed from data a minute old.
        provider = MemoryLeaseProvider()
        queue = WorkQueue()
        queue.offer(a_unit(0))
        writer = FencedWriter()
        rng = random.Random(0)

        fast_recorder = Recorder(Ledger(), SampleStore())
        fast = Worker(
            queue,
            fast_recorder,
            lease_provider=provider,
            runner=a_runner(rng),
            writer=writer,
            worker_id="fast",
        )
        await fast.take_one()
        assert len(fast_recorder.ledger) == 1

        # The stalled worker wakes with an older token.
        stalled_recorder = Recorder(Ledger(), SampleStore())
        stalled = Worker(
            queue,
            stalled_recorder,
            lease_provider=provider,
            runner=a_runner(rng),
            writer=writer,
            worker_id="stalled",
        )
        outcome = await stalled._run(Claim(unit=a_unit(0), worker_id="stalled", fencing_token=0))
        assert outcome.status == "lost"
        assert len(stalled_recorder.ledger) == 0


class TestAnAgentThroughABadNight:
    def _agent(self, registry: AgentRegistry, **changes: Any):
        _, secret = registry.issue_token("eu-frankfurt")
        identity, key = registry.enrol(secret.reveal())
        options: dict[str, Any] = {
            "executor": lambda _sql: [{"scanned_rows": 8, "violating_rows": 1}],
            "residency": ResidencyPolicy(
                zone="eu-frankfurt",
                samples=SampleDisposition.MASK,
                may_send=("account_id",),
            ),
            "capabilities": AgentCapabilities(engines=("sqlite",)),
        }
        options.update(changes)
        return identity, Agent(identity.agent_id, bytes.fromhex(key.reveal()), **options)

    def _assignment(self) -> Assignment:
        return Assignment(
            plan_id=PLAN.plan_id,
            dataset="t",
            binding="t",
            engine="sqlite",
            metric_query="SELECT 1",
            metric_names=("scanned_rows", "violating_rows"),
            plan=PLAN.to_dict(),
        )

    def test_a_day_of_outage_loses_nothing(self) -> None:
        # The acceptance criterion: execution continues for a day during a
        # control-plane outage, buffering and replaying. A day of an hourly
        # estate is a few hundred findings; the spool holds fifty thousand.
        registry = AgentRegistry()
        _, agent = self._agent(registry)
        coordinator = Coordinator(registry)
        assignment = self._assignment()

        for _ in range(1_000):  # the outage
            agent.run(assignment)
        assert len(agent.spool) == 1_000

        while len(agent.spool):  # the network comes back
            report, signature = agent.report(batch_size=250)
            assert agent.apply(coordinator.report(report, signature))
        assert len(coordinator.ledger) == 1_000
        assert coordinator.ledger.verify().is_intact

    def test_lost_receipts_do_not_duplicate_findings(self) -> None:
        # At-least-once delivery: the agent sends again because it heard
        # nothing. The ledger must keep one.
        registry = AgentRegistry()
        _, agent = self._agent(registry)
        coordinator = Coordinator(registry)
        assignment = self._assignment()
        for _ in range(30):
            agent.run(assignment)

        rng = random.Random(7)
        while len(agent.spool):
            report, signature = agent.report(batch_size=10)
            response = coordinator.report(report, signature)
            if rng.random() < 0.4:
                continue  # the receipt was lost; the agent will resend
            agent.apply(response)
        assert len(coordinator.ledger) == 30
        assert coordinator.ledger.verify().is_intact

    def test_a_restart_mid_outage_keeps_everything(self, tmp_path: Any) -> None:
        registry = AgentRegistry()
        path = tmp_path / "spool.json"
        identity, agent = self._agent(registry, spool=Spool(path=path))
        assignment = self._assignment()
        for _ in range(50):
            agent.run(assignment)

        # The machine reboots. Same identity, same spool file.
        restarted = Agent(
            identity.agent_id,
            b"",
            executor=lambda _sql: [],
            residency=agent.residency,
            spool=Spool(path=path),
        )
        assert len(restarted.spool) == 50
        assert restarted.spool.head == agent.spool.head

    def test_an_agent_revoked_mid_flight_stops(self) -> None:
        registry = AgentRegistry()
        identity, agent = self._agent(registry)
        coordinator = Coordinator(registry)
        assignment = self._assignment()
        for _ in range(5):
            agent.run(assignment)

        registry.revoke(identity.agent_id)
        report, signature = agent.report()
        response = coordinator.report(report, signature)
        assert agent.apply(response) is False
        # Nothing from a revoked agent reaches the ledger, however well signed.
        assert len(coordinator.ledger) == 0

    def test_an_overflowing_spool_reports_the_hole_rather_than_hiding_it(self) -> None:
        registry = AgentRegistry()
        _, agent = self._agent(registry, spool=Spool(capacity=20))
        coordinator = Coordinator(registry)
        assignment = self._assignment()
        for _ in range(60):
            agent.run(assignment)

        report, signature = agent.report()
        assert report.gaps
        assert report.gaps[0].count == 40
        response = coordinator.report(report, signature)
        assert isinstance(response, Receipt)
        # What survived is intact, and the hole is on the record rather than
        # being a silent shortfall in the coverage report.
        assert len(coordinator.ledger) == 20
        assert coordinator.ledger.verify().records == 20
