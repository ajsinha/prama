"""Leases: single-writer coordination across a fleet.

Several Prama components must have exactly one active instance across the whole
deployment — the scheduler's dispatch loop, a re-examination for one dataset, an
evidence compaction pass. The usual failure is not that two instances run, but
that two instances run *and neither knows*, producing duplicate work and, in the
evidence ledger, duplicate records that look like real history.

A lease is the answer, and it is deliberately time-bounded rather than a lock:

* A holder that dies stops renewing and the lease expires. No operator has to
  clear a stale lock.
* A holder that is merely slow (a long GC pause, a stalled disk) loses the lease
  and is told, via ``LeaseLostError``, so it can abandon work it can no longer
  claim to own. **Fencing tokens** make that safe: every acquisition increments
  a monotonically increasing token, and a downstream store rejects a write
  carrying a stale one.
* Clock skew is accounted for explicitly rather than assumed away.

``MemoryLeaseProvider`` is for single-process deployments and tests. The
database-backed provider lives in ``prama.db`` because it is the only place that
may touch SQLAlchemy.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from types import TracebackType
from typing import Any

from prama.core.clock import Clock, SystemClock
from prama.core.errors import LeaseLostError
from prama.core.ids import new_ulid
from prama.core.log import get_logger

_log = get_logger(__name__)


@dataclasses.dataclass(frozen=True, slots=True)
class LeaseSettings:
    """How a lease behaves. Bound from ``concurrency.lease`` configuration."""

    ttl_seconds: float = 30.0
    renew_interval_seconds: float = 10.0
    clock_skew_allowance_seconds: float = 2.0

    @classmethod
    def from_config(cls, config: Any) -> LeaseSettings:
        """``concurrency.lease.ttl``, ``renew_interval`` and ``clock_skew_allowance``."""
        settings = cls(
            ttl_seconds=config.get_duration("concurrency.lease.ttl", "30s"),
            renew_interval_seconds=config.get_duration("concurrency.lease.renew_interval", "10s"),
            clock_skew_allowance_seconds=config.get_duration(
                "concurrency.lease.clock_skew_allowance", "2s"
            ),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.renew_interval_seconds >= self.ttl_seconds:
            raise ValueError(
                "renew_interval must be shorter than ttl, or a lease expires between renewals"
            )
        if self.renew_interval_seconds * 2 > self.ttl_seconds:
            _log.warning(
                "lease renew_interval (%.1fs) leaves no room for a missed renewal within "
                "ttl (%.1fs); consider ttl >= 3x renew_interval",
                self.renew_interval_seconds,
                self.ttl_seconds,
            )


@dataclasses.dataclass(frozen=True, slots=True)
class Lease:
    """A granted lease.

    ``fencing_token`` increases strictly with every acquisition of the same
    resource across the fleet, and is the value a downstream store compares to
    reject a write from a superseded holder.
    """

    resource: str
    holder: str
    token: str
    fencing_token: int
    acquired_at: datetime
    expires_at: datetime

    def is_valid_at(self, moment: datetime, *, skew: float = 0.0) -> bool:
        return moment + timedelta(seconds=skew) < self.expires_at

    def remaining_seconds(self, moment: datetime) -> float:
        return max(0.0, (self.expires_at - moment).total_seconds())


class LeaseProvider(ABC):
    """Storage-agnostic lease operations.

    Implementations must make ``acquire`` atomic with respect to other holders,
    and must reject ``renew``/``release`` from a holder that no longer owns the
    resource. Those two properties are the whole contract; everything else here
    is convenience.
    """

    @abstractmethod
    async def acquire(self, resource: str, holder: str, ttl_seconds: float) -> Lease | None:
        """Grant the lease, or return None if another holder owns it."""

    @abstractmethod
    async def renew(self, lease: Lease, ttl_seconds: float) -> Lease | None:
        """Extend the lease, or return None if it has been lost."""

    @abstractmethod
    async def release(self, lease: Lease) -> bool:
        """Give up the lease. Returns False if it was already lost."""

    @abstractmethod
    async def inspect(self, resource: str) -> Lease | None:
        """Current holder, if any. For diagnostics and health output."""

    #: The configured ``concurrency.lease`` settings, for a holder that does not
    #: bring its own. Set by whoever builds the provider from configuration.
    default_settings: LeaseSettings | None = None

    def hold(
        self,
        resource: str,
        *,
        holder: str | None = None,
        settings: LeaseSettings | None = None,
        clock: Clock | None = None,
    ) -> LeaseHolder:
        chosen = settings or self.default_settings
        return LeaseHolder(self, resource, holder=holder, settings=chosen, clock=clock)


class LeaseHolder:
    """Acquires a lease, renews it in the background, and reports its loss.

        async with provider.hold("scheduler.dispatch") as lease:
            while holder.valid:
                ...   # work that only one instance may do

    Leaving the block releases the lease immediately, so a graceful shutdown
    hands over in milliseconds instead of after a TTL.
    """

    def __init__(
        self,
        provider: LeaseProvider,
        resource: str,
        *,
        holder: str | None = None,
        settings: LeaseSettings | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._provider = provider
        self._resource = resource
        self._holder = holder or f"holder:{new_ulid()}"
        self._settings = settings or LeaseSettings()
        self._settings.validate()
        self._clock = clock or SystemClock()
        self._lease: Lease | None = None
        self._renewer: asyncio.Task[None] | None = None
        self._lost = asyncio.Event()

    @property
    def lease(self) -> Lease | None:
        return self._lease

    @property
    def valid(self) -> bool:
        return self._lease is not None and not self._lost.is_set()

    @property
    def fencing_token(self) -> int:
        if self._lease is None:
            raise LeaseLostError(
                f"no lease held for {self._resource!r}",
                remedy="Acquire the lease before using its fencing token.",
                context={"resource": self._resource},
            )
        return self._lease.fencing_token

    async def acquire(self, *, wait: bool = False, poll_interval: float = 1.0) -> bool:
        """Try to take the lease; optionally wait until it becomes free."""
        while True:
            lease = await self._provider.acquire(
                self._resource, self._holder, self._settings.ttl_seconds
            )
            if lease is not None:
                self._lease = lease
                self._lost.clear()
                self._renewer = asyncio.create_task(
                    self._renew_loop(), name=f"lease-renew:{self._resource}"
                )
                return True
            if not wait:
                return False
            await asyncio.sleep(poll_interval)

    async def _renew_loop(self) -> None:
        """Renew until the lease is released or lost.

        Cancellation propagates: this task is owned by the holder, and a
        cancelled renewer must not be mistaken for a healthy one.
        """
        while True:
            await asyncio.sleep(self._settings.renew_interval_seconds)
            # Re-read: release() may have cleared the lease from another task
            # while this one was sleeping.
            current = self._lease
            if current is None:
                return
            renewed = await self._provider.renew(current, self._settings.ttl_seconds)
            if renewed is None:
                _log.error(
                    "lease on %r lost by holder %s; work under it must stop",
                    self._resource,
                    self._holder,
                )
                self._lease = None
                self._lost.set()
                return
            self._lease = renewed

    async def wait_until_lost(self) -> None:
        await self._lost.wait()

    def raise_if_lost(self) -> None:
        """Assert continued ownership at a safe point in the work."""
        if self._lost.is_set() or self._lease is None:
            raise LeaseLostError(
                f"lease on {self._resource!r} is no longer held",
                remedy=(
                    "Abandon the work started under it. Another instance now owns this "
                    "resource, and continuing would duplicate its effect."
                ),
                context={"resource": self._resource, "holder": self._holder},
            )
        if not self._lease.is_valid_at(
            self._clock.now(), skew=self._settings.clock_skew_allowance_seconds
        ):
            self._lost.set()
            raise LeaseLostError(
                f"lease on {self._resource!r} has expired",
                remedy="Abandon the work and re-acquire before continuing.",
                context={"resource": self._resource, "holder": self._holder},
            )

    async def release(self) -> None:
        if self._renewer is not None:
            self._renewer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._renewer
            self._renewer = None
        if self._lease is not None:
            await self._provider.release(self._lease)
            self._lease = None

    async def __aenter__(self) -> LeaseHolder:
        if not await self.acquire():
            raise LeaseLostError(
                f"lease on {self._resource!r} is held by another instance",
                remedy=(
                    "This is normal in a fleet: another instance owns the work. "
                    "Use acquire(wait=True) if this instance should queue for it."
                ),
                context={"resource": self._resource},
            )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.release()


class MemoryLeaseProvider(LeaseProvider):
    """In-process leases. Correct for a single process; useless across a fleet.

    Deliberately not the default: a provider that silently grants every request
    would make a two-node deployment duplicate all its work with no symptom.
    """

    def __init__(self, clock: Clock | None = None) -> None:
        self._clock = clock or SystemClock()
        self._leases: dict[str, Lease] = {}
        self._fencing: dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, resource: str, holder: str, ttl_seconds: float) -> Lease | None:
        async with self._lock:
            now = self._clock.now()
            current = self._leases.get(resource)
            if current is not None and current.is_valid_at(now) and current.holder != holder:
                return None
            token = self._fencing.get(resource, 0) + 1
            self._fencing[resource] = token
            lease = Lease(
                resource=resource,
                holder=holder,
                token=new_ulid(),
                fencing_token=token,
                acquired_at=now,
                expires_at=now + timedelta(seconds=ttl_seconds),
            )
            self._leases[resource] = lease
            return lease

    async def renew(self, lease: Lease, ttl_seconds: float) -> Lease | None:
        async with self._lock:
            current = self._leases.get(lease.resource)
            if current is None or current.token != lease.token:
                return None
            now = self._clock.now()
            if not current.is_valid_at(now):
                return None
            renewed = dataclasses.replace(current, expires_at=now + timedelta(seconds=ttl_seconds))
            self._leases[lease.resource] = renewed
            return renewed

    async def release(self, lease: Lease) -> bool:
        async with self._lock:
            current = self._leases.get(lease.resource)
            if current is None or current.token != lease.token:
                return False
            del self._leases[lease.resource]
            return True

    async def inspect(self, resource: str) -> Lease | None:
        async with self._lock:
            lease = self._leases.get(resource)
            if lease is None or not lease.is_valid_at(self._clock.now()):
                return None
            return lease
