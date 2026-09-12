"""A queue bounded by bytes.

An item-bounded queue is a memory bound only if every item is the same size,
which is never true of a data platform. A queue of 100,000 "records" is 10 MB of
telemetry or 40 GB of wide rows depending on the day, and the day it becomes the
latter is the day the process dies with a bound configured and honoured.

So the budget here is bytes, with an item count as a secondary guard. Producers
that would breach the budget wait, and if they wait past ``offer_timeout`` they
receive ``BackPressureError`` — a signal to slow down, which propagates back to
the scheduler as reduced admission rather than as an out-of-memory kill.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import asyncio
import dataclasses
import sys
from collections import deque
from collections.abc import Callable
from typing import Any, Generic, TypeVar

from prama.core.errors import BackPressureError

T = TypeVar("T")

#: Every queued item carries at least this much overhead: a deque slot, a
#: pointer, and the object header. Charging it stops a flood of tiny items from
#: appearing free.
ITEM_OVERHEAD_BYTES = 64


@dataclasses.dataclass(slots=True)
class QueueStats:
    """Observable state. Exported to Prometheus and shown in health output."""

    items: int = 0
    bytes: int = 0
    max_items: int = 0
    max_bytes: int = 0
    offered: int = 0
    accepted: int = 0
    rejected: int = 0
    high_water_items: int = 0
    high_water_bytes: int = 0

    @property
    def utilisation(self) -> float:
        """Fraction of the byte budget in use, 0.0-1.0."""
        return 0.0 if self.max_bytes == 0 else min(1.0, self.bytes / self.max_bytes)


def default_sizer(item: Any) -> int:
    """A cheap, deliberately approximate size estimate.

    ``sys.getsizeof`` is shallow, so containers are walked one level. Exactness
    is not the goal: the budget exists to prevent an order-of-magnitude
    surprise, and an estimate that costs a deep traversal per item would cost
    more than the leak it prevents.
    """
    try:
        size = sys.getsizeof(item)
    except TypeError:
        return ITEM_OVERHEAD_BYTES
    if isinstance(item, (bytes, bytearray, memoryview, str)):
        return size + ITEM_OVERHEAD_BYTES
    if isinstance(item, dict):
        for key, value in item.items():
            size += sys.getsizeof(key) + sys.getsizeof(value)
    elif isinstance(item, (list, tuple, set, frozenset)):
        for value in item:
            size += sys.getsizeof(value)
    return size + ITEM_OVERHEAD_BYTES


class BoundedQueue(Generic[T]):
    """An asyncio queue bounded by bytes and by item count.

    Capacity is adjustable at runtime (``resize``) so an operator can widen a
    queue under load without a restart — a capability DishtaYantra proved
    valuable and that is cheap to provide here.
    """

    def __init__(
        self,
        *,
        max_bytes: int,
        max_items: int = 0,
        offer_timeout: float = 5.0,
        sizer: Callable[[Any], int] | None = None,
        name: str = "queue",
    ) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive; an unbounded queue is not permitted")
        self.name = name
        self._max_bytes = max_bytes
        self._max_items = max_items
        self._offer_timeout = offer_timeout
        self._sizer = sizer or default_sizer
        self._items: deque[tuple[T, int]] = deque()
        self._bytes = 0
        self._stats = QueueStats(max_items=max_items, max_bytes=max_bytes)
        self._not_empty = asyncio.Condition()
        self._not_full = asyncio.Condition()
        self._closed = False

    # -- properties --------------------------------------------------------

    def __len__(self) -> int:
        return len(self._items)

    @property
    def byte_size(self) -> int:
        return self._bytes

    @property
    def closed(self) -> bool:
        return self._closed

    def stats(self) -> QueueStats:
        self._stats.items = len(self._items)
        self._stats.bytes = self._bytes
        return dataclasses.replace(self._stats)

    def _would_fit(self, size: int) -> bool:
        if self._bytes + size > self._max_bytes and self._items:
            return False
        return not (self._max_items and len(self._items) >= self._max_items)

    # -- producer side -----------------------------------------------------

    async def put(self, item: T, *, timeout: float | None = None) -> None:
        """Enqueue, waiting up to *timeout* for room.

        A single item larger than the whole budget is accepted when the queue is
        empty rather than deadlocking forever: refusing it would strand the
        pipeline on one oversized record, which is a worse failure than a
        temporary overshoot that is visible in the stats.
        """
        size = self._sizer(item)
        deadline = timeout if timeout is not None else self._offer_timeout
        self._stats.offered += 1
        async with self._not_full:
            if not self._would_fit(size):
                try:
                    await asyncio.wait_for(
                        self._not_full.wait_for(lambda: self._closed or self._would_fit(size)),
                        timeout=deadline,
                    )
                except TimeoutError:
                    self._stats.rejected += 1
                    raise BackPressureError(
                        f"queue {self.name!r} is full: "
                        f"{self._bytes}/{self._max_bytes} bytes, {len(self._items)} items",
                        remedy=(
                            "Slow the producer, widen concurrency.queue.max_bytes, or add "
                            "consumers. Sustained back-pressure means the sink is the bottleneck."
                        ),
                        context={
                            "queue": self.name,
                            "bytes": self._bytes,
                            "max_bytes": self._max_bytes,
                            "items": len(self._items),
                        },
                    ) from None
            if self._closed:
                raise BackPressureError(
                    f"queue {self.name!r} is closed",
                    remedy="Stop producing to a closed queue; the consumer has shut down.",
                    context={"queue": self.name},
                )
            self._items.append((item, size))
            self._bytes += size
            self._stats.accepted += 1
            self._stats.high_water_items = max(self._stats.high_water_items, len(self._items))
            self._stats.high_water_bytes = max(self._stats.high_water_bytes, self._bytes)
        async with self._not_empty:
            self._not_empty.notify()

    async def try_put(self, item: T) -> bool:
        """Enqueue without waiting for room. False means the budget is full.

        "Non-blocking" is about back-pressure: this never waits for capacity, it
        refuses. It is a coroutine because it has to wake a consumer, and
        finding X6 was that it did not — a consumer parked in `get()` or
        `drain()` on `_not_empty` was never notified, and with the default
        `timeout=None` waited for ever while the item sat in the deque. `put()`
        two methods above notifies on exactly the same line; this one returned
        `True` and told nobody.
        """
        size = self._sizer(item)
        self._stats.offered += 1
        if self._closed or not self._would_fit(size):
            self._stats.rejected += 1
            return False
        self._items.append((item, size))
        self._bytes += size
        self._stats.accepted += 1
        self._stats.high_water_items = max(self._stats.high_water_items, len(self._items))
        self._stats.high_water_bytes = max(self._stats.high_water_bytes, self._bytes)
        async with self._not_empty:
            self._not_empty.notify()
        return True

    # -- consumer side -----------------------------------------------------

    async def get(self, *, timeout: float | None = None) -> T:
        async with self._not_empty:
            if not self._items:
                waiter = self._not_empty.wait_for(lambda: bool(self._items) or self._closed)
                if timeout is None:
                    await waiter
                else:
                    await asyncio.wait_for(waiter, timeout=timeout)
            if not self._items and self._closed:
                raise BackPressureError(
                    f"queue {self.name!r} is closed and drained",
                    remedy="Stop consuming; the producer has finished.",
                    context={"queue": self.name},
                )
            item, size = self._items.popleft()
            self._bytes -= size
        async with self._not_full:
            self._not_full.notify_all()
        return item

    async def drain(self, max_items: int = 0) -> list[T]:
        """Take everything currently queued, in one wake-up.

        Batch consumers are the normal case here — a metric writer or an
        evidence appender wants a page, not a record — and draining once per
        wake-up is far cheaper than a ``get`` per item.
        """
        async with self._not_empty:
            if not self._items:
                await self._not_empty.wait_for(lambda: bool(self._items) or self._closed)
            taken: list[T] = []
            while self._items and (max_items == 0 or len(taken) < max_items):
                item, size = self._items.popleft()
                self._bytes -= size
                taken.append(item)
        async with self._not_full:
            self._not_full.notify_all()
        return taken

    # -- lifecycle ---------------------------------------------------------

    async def resize(self, *, max_bytes: int | None = None, max_items: int | None = None) -> None:
        """Adjust capacity live. Shrinking never discards queued items.

        Wakes every blocked producer, because widening a queue that nobody is
        told about is not widening it — finding X6. Producers already parked on
        `_not_full` used to sit out their full `offer_timeout` and then take a
        `BackPressureError` against a queue with room in it, which contradicts
        the reason this method exists: "an operator can widen a queue under load
        without a restart."
        """
        if max_bytes is not None:
            if max_bytes <= 0:
                raise ValueError("max_bytes must be positive")
            self._max_bytes = max_bytes
            self._stats.max_bytes = max_bytes
        if max_items is not None:
            self._max_items = max_items
            self._stats.max_items = max_items
        async with self._not_full:
            self._not_full.notify_all()

    async def close(self) -> None:
        """Close for production and wake every waiter."""
        self._closed = True
        async with self._not_full:
            self._not_full.notify_all()
        async with self._not_empty:
            self._not_empty.notify_all()
