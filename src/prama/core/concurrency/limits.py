"""Admission control: concurrency limits and rate limits.

Prama runs against production databases owned by other teams. A control plane
that can saturate a source is a control plane that gets switched off, so
NFR-PRF-013 caps Prama-attributable load at a configured fraction of source
capacity. These two primitives are how that cap is expressed.

Both are fair (FIFO among waiters) rather than opportunistic. Unfair limiters
starve the unlucky caller, and the unlucky caller is usually the long-running
Tier-1 control that matters most.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import asyncio
from types import TracebackType

from prama.core.clock import Clock, SystemClock
from prama.core.errors import BackPressureError


class ConcurrencyLimiter:
    """At most *limit* holders at once, granted in arrival order.

    async with limiter.acquire(timeout=30):
        ...
    """

    def __init__(self, limit: int, *, name: str = "limiter") -> None:
        if limit <= 0:
            raise ValueError("concurrency limit must be positive")
        self.name = name
        self._limit = limit
        self._semaphore = asyncio.Semaphore(limit)
        self._in_flight = 0
        self._high_water = 0

    @property
    def limit(self) -> int:
        return self._limit

    @property
    def in_flight(self) -> int:
        return self._in_flight

    @property
    def high_water(self) -> int:
        return self._high_water

    def acquire(self, *, timeout: float | None = None) -> _LimiterContext:
        return _LimiterContext(self, timeout)

    async def _enter(self, timeout: float | None) -> None:
        try:
            if timeout is None:
                await self._semaphore.acquire()
            else:
                await asyncio.wait_for(self._semaphore.acquire(), timeout=timeout)
        except TimeoutError:
            raise BackPressureError(
                f"could not acquire a slot on {self.name!r} within {timeout:.1f}s "
                f"({self._in_flight}/{self._limit} in flight)",
                remedy=(
                    "Raise the limit if the source can take the load, or accept the wait: "
                    "this limiter exists to keep Prama inside its agreed share of the source."
                ),
                context={"limiter": self.name, "limit": self._limit},
            ) from None
        self._in_flight += 1
        self._high_water = max(self._high_water, self._in_flight)

    def _exit(self) -> None:
        self._in_flight -= 1
        self._semaphore.release()


class _LimiterContext:
    __slots__ = ("_limiter", "_timeout")

    def __init__(self, limiter: ConcurrencyLimiter, timeout: float | None) -> None:
        self._limiter = limiter
        self._timeout = timeout

    async def __aenter__(self) -> ConcurrencyLimiter:
        await self._limiter._enter(self._timeout)
        return self._limiter

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._limiter._exit()


class RateLimiter:
    """A token bucket: *rate* permits per second, bursting up to *capacity*.

    A bucket rather than a fixed window because sources care about instantaneous
    pressure, and a fixed window permits the whole quota in the first
    millisecond of every window — the pattern that trips a DBA's alerting.
    """

    def __init__(
        self,
        rate: float,
        *,
        capacity: float | None = None,
        clock: Clock | None = None,
        name: str = "rate",
    ) -> None:
        if rate <= 0:
            raise ValueError("rate must be positive")
        self.name = name
        self._rate = rate
        self._capacity = capacity if capacity is not None else max(1.0, rate)
        self._clock = clock or SystemClock()
        self._tokens = self._capacity
        self._updated = self._clock.monotonic()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        now = self._clock.monotonic()
        elapsed = max(0.0, now - self._updated)
        self._updated = now
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)

    async def acquire(self, permits: float = 1.0, *, timeout: float | None = None) -> None:
        """Wait until *permits* are available, or fail with back-pressure."""
        if permits > self._capacity:
            raise ValueError(
                f"cannot acquire {permits} permits from a bucket of capacity {self._capacity}"
            )
        waited = 0.0
        while True:
            async with self._lock:
                self._refill()
                if self._tokens >= permits:
                    self._tokens -= permits
                    return
                deficit = permits - self._tokens
                delay = deficit / self._rate
            if timeout is not None and waited + delay > timeout:
                raise BackPressureError(
                    f"rate limit {self.name!r} would require {waited + delay:.2f}s, "
                    f"over the {timeout:.2f}s budget",
                    remedy="Raise the configured rate, or reduce the request volume.",
                    context={"limiter": self.name, "rate": self._rate},
                )
            await asyncio.sleep(delay)
            waited += delay

    def try_acquire(self, permits: float = 1.0) -> bool:
        self._refill()
        if self._tokens >= permits:
            self._tokens -= permits
            return True
        return False

    @property
    def available(self) -> float:
        self._refill()
        return self._tokens
