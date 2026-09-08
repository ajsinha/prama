"""Structured concurrency: queues, supervision, limits and leases.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import asyncio

import pytest

from prama.core.clock import ManualClock
from prama.core.concurrency import (
    BoundedQueue,
    ConcurrencyLimiter,
    LeaseSettings,
    MemoryLeaseProvider,
    RateLimiter,
    TaskSupervisor,
)
from prama.core.concurrency.supervisor import RestartPolicy
from prama.core.errors import BackPressureError, ConcurrencyError, LeaseLostError


class TestBoundedQueue:
    async def test_byte_budget_is_enforced_not_just_item_count(self) -> None:
        queue = BoundedQueue[bytes](max_bytes=1024, offer_timeout=0.01, name="q")
        await queue.put(b"x" * 900)
        with pytest.raises(BackPressureError, match="full"):
            await queue.put(b"y" * 900)

    async def test_a_single_oversized_item_is_accepted_when_empty(self) -> None:
        # Refusing it would strand the pipeline forever on one wide row, which
        # is a worse failure than a visible, temporary overshoot.
        queue = BoundedQueue[bytes](max_bytes=100, offer_timeout=0.01)
        await queue.put(b"z" * 10_000)
        assert len(queue) == 1

    async def test_unbounded_is_not_permitted(self) -> None:
        with pytest.raises(ValueError, match="unbounded"):
            BoundedQueue[int](max_bytes=0)

    async def test_drain_takes_a_page_in_one_wake_up(self) -> None:
        queue = BoundedQueue[int](max_bytes=1_000_000)
        for i in range(50):
            await queue.put(i)
        assert await queue.drain(max_items=20) == list(range(20))
        assert len(queue) == 30

    async def test_stats_track_offers_acceptances_and_rejections(self) -> None:
        queue = BoundedQueue[bytes](max_bytes=256, max_items=1, offer_timeout=0.01)
        await queue.put(b"a")
        with pytest.raises(BackPressureError):
            await queue.put(b"b")
        stats = queue.stats()
        assert (stats.offered, stats.accepted, stats.rejected) == (2, 1, 1)
        assert 0 < stats.utilisation <= 1

    async def test_resize_widens_capacity_live(self) -> None:
        queue = BoundedQueue[bytes](max_bytes=256, max_items=1, offer_timeout=0.01)
        await queue.put(b"a")
        assert queue.try_put(b"b") is False
        queue.resize(max_items=10)
        assert queue.try_put(b"b") is True


class TestSupervisor:
    async def test_a_failing_one_shot_task_surfaces_rather_than_vanishing(self) -> None:
        async with TaskSupervisor("s", shutdown_grace=1) as supervisor:

            async def boom() -> None:
                raise RuntimeError("expected")

            supervisor.spawn("boom", boom, policy=RestartPolicy.NEVER)
            await asyncio.sleep(0.05)
        assert supervisor.failures()
        with pytest.raises(RuntimeError, match="expected"):
            supervisor.raise_for_failures()

    async def test_on_failure_restarts_until_success(self) -> None:
        attempts: list[int] = []

        async with TaskSupervisor("s", shutdown_grace=1, base_backoff=0.001) as supervisor:

            async def flaky() -> None:
                attempts.append(1)
                if len(attempts) < 3:
                    raise RuntimeError("transient")

            supervisor.spawn("flaky", flaky, policy=RestartPolicy.ON_FAILURE)
            await asyncio.sleep(0.3)
        assert len(attempts) == 3
        assert supervisor.healthy()

    async def test_a_crash_loop_is_given_up_on_and_reported(self) -> None:
        async with TaskSupervisor(
            "s", shutdown_grace=1, max_restarts=3, base_backoff=0.001
        ) as supervisor:

            async def always() -> None:
                raise RuntimeError("never works")

            supervisor.spawn("always", always, policy=RestartPolicy.ON_FAILURE)
            await asyncio.sleep(0.3)
        assert any(isinstance(f, ConcurrencyError) for f in supervisor.failures())

    async def test_leaving_the_scope_cancels_children(self) -> None:
        started = asyncio.Event()
        async with TaskSupervisor("s", shutdown_grace=1) as supervisor:

            async def forever() -> None:
                started.set()
                await asyncio.sleep(3600)

            handle = supervisor.spawn("forever", forever)
            await started.wait()
        assert not handle.running

    async def test_duplicate_task_name_is_refused(self) -> None:
        async with TaskSupervisor("s", shutdown_grace=1) as supervisor:

            async def forever() -> None:
                await asyncio.sleep(3600)

            supervisor.spawn("t", forever)
            with pytest.raises(ConcurrencyError, match="already running"):
                supervisor.spawn("t", forever)


class TestLimits:
    async def test_concurrency_limiter_caps_in_flight_work(self) -> None:
        limiter = ConcurrencyLimiter(2, name="src")
        peak = 0

        async def work() -> None:
            nonlocal peak
            async with limiter.acquire():
                peak = max(peak, limiter.in_flight)
                await asyncio.sleep(0.02)

        await asyncio.gather(*(work() for _ in range(10)))
        assert peak == 2
        assert limiter.high_water == 2

    async def test_waiting_past_the_budget_is_back_pressure_not_a_hang(self) -> None:
        limiter = ConcurrencyLimiter(1, name="src")
        async with limiter.acquire():
            with pytest.raises(BackPressureError, match="slot"):
                async with limiter.acquire(timeout=0.01):
                    pass

    async def test_token_bucket_bursts_then_throttles(self) -> None:
        bucket = RateLimiter(1000.0, capacity=3.0, name="src")
        assert [bucket.try_acquire() for _ in range(4)] == [True, True, True, False]


class TestLeases:
    async def test_only_one_holder_at_a_time(self) -> None:
        provider = MemoryLeaseProvider()
        first = provider.hold("dispatch", holder="a")
        assert await first.acquire() is True
        assert await provider.hold("dispatch", holder="b").acquire() is False
        await first.release()
        assert await provider.hold("dispatch", holder="b").acquire() is True

    async def test_fencing_token_increases_on_every_acquisition(self) -> None:
        provider = MemoryLeaseProvider()
        tokens = []
        for holder in ("a", "b", "c"):
            handle = provider.hold("dispatch", holder=holder)
            await handle.acquire()
            tokens.append(handle.fencing_token)
            await handle.release()
        assert tokens == sorted(tokens) and len(set(tokens)) == 3

    async def test_an_expired_lease_is_taken_over(self) -> None:
        clock = ManualClock()
        provider = MemoryLeaseProvider(clock=clock)
        assert await provider.acquire("dispatch", "a", ttl_seconds=10) is not None
        assert await provider.acquire("dispatch", "b", ttl_seconds=10) is None
        clock.advance(11)
        assert await provider.acquire("dispatch", "b", ttl_seconds=10) is not None

    async def test_raise_if_lost_refuses_to_let_work_continue(self) -> None:
        clock = ManualClock()
        provider = MemoryLeaseProvider(clock=clock)
        handle = provider.hold(
            "dispatch",
            holder="a",
            settings=LeaseSettings(ttl_seconds=5, renew_interval_seconds=1),
            clock=clock,
        )
        await handle.acquire()
        handle.raise_if_lost()
        clock.advance(10)
        with pytest.raises(LeaseLostError, match="expired"):
            handle.raise_if_lost()
        await handle.release()

    def test_renew_interval_must_be_shorter_than_ttl(self) -> None:
        with pytest.raises(ValueError, match="shorter than ttl"):
            LeaseSettings(ttl_seconds=5, renew_interval_seconds=10).validate()
