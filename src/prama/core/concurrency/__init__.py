"""Structured concurrency primitives.

Prama's concurrency rules are narrow on purpose (CLAUDE.md):

* **No bare threads or fire-and-forget tasks.** Every task belongs to a
  ``TaskSupervisor`` that owns its lifetime, propagates its failure, and can
  cancel it. A task nobody owns is a task nobody notices failing.
* **No unbounded queues.** Every queue is bounded by *bytes*, not item count.
  Ten million small records and ten large ones are not the same memory risk, and
  an item-bounded "bounded" queue behaves like a leak under a payload change.
* **Single-writer work is leased.** A component that must have exactly one
  active instance across the fleet holds a lease with a TTL and renews it. It
  never assumes it is alone.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.core.concurrency.bounded_queue import BoundedQueue, QueueStats
from prama.core.concurrency.leases import (
    Lease,
    LeaseHolder,
    LeaseProvider,
    LeaseSettings,
    MemoryLeaseProvider,
)
from prama.core.concurrency.limits import ConcurrencyLimiter, RateLimiter
from prama.core.concurrency.supervisor import TaskHandle, TaskSupervisor

__all__ = [
    "BoundedQueue",
    "ConcurrencyLimiter",
    "Lease",
    "LeaseHolder",
    "LeaseProvider",
    "LeaseSettings",
    "MemoryLeaseProvider",
    "QueueStats",
    "RateLimiter",
    "TaskHandle",
    "TaskSupervisor",
]
