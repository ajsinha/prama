"""Claiming work so that exactly one worker does it.

The obvious failure is two workers running the same control at the same moment
and writing two evidence records for one run. A lease prevents that, and a
lease alone is not enough — which is the whole reason fencing tokens exist and
the reason this file is separate from the worker that uses it.

The case a lease does not cover: a worker acquires the lease, reads the data,
and then stops. Not crashes — stops. A long garbage collection, a stalled disk,
a hypervisor pausing the VM for eleven seconds. The lease expires, a second
worker takes it and does the work properly, and *then* the first worker wakes
up holding a result computed from data it read a minute ago and writes it.
Nothing has failed, no error is raised, and the ledger now holds a record whose
verdict is stale and whose timestamp says otherwise.

A **fencing token** closes it. Every acquisition of a resource increments a
counter, and a write carrying a token lower than the highest already accepted is
rejected. The late worker's write is refused because a newer holder exists —
not by a rule somebody has to remember, but by the writer.

This is worth the machinery because the failure it prevents is silent. A
duplicate record is visible; a stale one is not.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from prama.core.errors import ConcurrencyError, LeaseLostError


class StaleWriteError(ConcurrencyError):
    """A worker tried to record a result after losing its claim."""

    code = "CONCURRENCY.STALE_WRITE"


@dataclasses.dataclass(frozen=True, slots=True)
class WorkUnit:
    """One thing a worker may claim.

    The resource is what the lease is taken on, and choosing it is the whole
    granularity decision. Per plan is the finest and gives the most parallelism;
    per dataset serialises a dataset's controls and lets them share a scan.
    Prama claims per *scan group*, which is the same thing the fuser groups by,
    so the unit of exclusion and the unit of work are the same object.
    """

    resource: str
    dataset: str
    zone: str = ""
    plan_ids: tuple[str, ...] = ()
    priority: str = "normal"
    #: What running this is expected to cost, for the budget policy.
    cost: float = 1.0

    @property
    def size(self) -> int:
        return len(self.plan_ids)


@dataclasses.dataclass(frozen=True, slots=True)
class Claim:
    """A worker's exclusive right to one unit of work, for a while."""

    unit: WorkUnit
    worker_id: str
    #: Strictly increasing per resource across the whole fleet. The number a
    #: writer compares.
    fencing_token: int
    holder: Any = None

    @property
    def resource(self) -> str:
        return self.unit.resource

    def check(self) -> None:
        """Confirm the claim still holds, at a point where it matters.

        Called before anything is written. It cannot make a lost lease safe —
        the work is already done against data the claim no longer covers — but
        it turns a silent stale write into an exception at the moment the
        decision is made, which is where somebody can act on it.
        """
        if self.holder is None:
            return
        self.holder.raise_if_lost()


class FencedWriter:
    """Accepts a result only from the newest holder of its resource.

    The guarantee lives here rather than in the worker, because a guarantee a
    caller has to remember is a guarantee that survives exactly as long as
    nobody adds a second caller.
    """

    def __init__(self) -> None:
        self._highest: dict[str, int] = {}

    def accept(self, claim: Claim) -> None:
        """Record that this claim has written, or refuse a stale one."""
        seen = self._highest.get(claim.resource, 0)
        if claim.fencing_token < seen:
            raise StaleWriteError(
                f"{claim.worker_id} tried to record work on {claim.resource} with "
                f"token {claim.fencing_token}, and token {seen} has already written",
                remedy=(
                    "Discard the result. Another worker took this resource while this "
                    "one was stalled and has already done the work; recording it now "
                    "would put a verdict computed from older data on the record, with "
                    "a timestamp saying otherwise."
                ),
                context={
                    "resource": claim.resource,
                    "worker": claim.worker_id,
                    "token": claim.fencing_token,
                    "highest": seen,
                },
            )
        self._highest[claim.resource] = claim.fencing_token

    def highest(self, resource: str) -> int:
        return self._highest.get(resource, 0)

    def would_accept(self, claim: Claim) -> bool:
        return claim.fencing_token >= self._highest.get(claim.resource, 0)


class WorkQueue:
    """Work waiting to be claimed, and who has what.

    In memory, with the storage seam kept to three methods, because where the
    queue lives — a table, a broker, a directory — is a deployment decision and
    a queue that knew about it would be reimplemented for each.
    """

    def __init__(self) -> None:
        self._pending: list[WorkUnit] = []
        self._claimed: dict[str, Claim] = {}

    def __len__(self) -> int:
        return len(self._pending)

    def offer(self, unit: WorkUnit) -> None:
        self._pending.append(unit)

    def pending(self, zone: str = "") -> list[WorkUnit]:
        return [u for u in self._pending if not zone or u.zone == zone]

    def claimed_by(self, worker_id: str) -> list[Claim]:
        return [c for c in self._claimed.values() if c.worker_id == worker_id]

    def take(self, unit: WorkUnit, claim: Claim) -> None:
        if unit in self._pending:
            self._pending.remove(unit)
        self._claimed[unit.resource] = claim

    def release(self, claim: Claim, *, requeue: bool = False) -> None:
        """Give up a claim. Requeue when the work was not finished.

        Requeuing is the caller's decision because only the caller knows
        whether the work completed. A queue that requeued on every release
        would rerun everything; one that never did would lose whatever a
        crashing worker was holding.
        """
        current = self._claimed.get(claim.resource)
        if current is not None and current.fencing_token == claim.fencing_token:
            del self._claimed[claim.resource]
        if requeue:
            self._pending.append(claim.unit)


async def claim_unit(
    provider: Any,
    unit: WorkUnit,
    *,
    worker_id: str,
    ttl_seconds: float = 60.0,
) -> Claim | None:
    """Take a lease on one unit, or return None if somebody else holds it.

    None rather than an exception: another worker holding the work is the
    ordinary case in a fleet, not an error, and a worker that logged an
    exception every time it lost a race would drown its own useful output.
    """
    from prama.core.concurrency.leases import LeaseSettings

    # Renewed three times within the TTL, so one missed renewal — a slow
    # network, a busy control plane — does not lose a claim that is still
    # being worked.
    settings = LeaseSettings(
        ttl_seconds=ttl_seconds, renew_interval_seconds=max(1.0, ttl_seconds / 3)
    )
    holder = provider.hold(unit.resource, holder=worker_id, settings=settings)
    if not await holder.acquire():
        return None
    return Claim(
        unit=unit,
        worker_id=worker_id,
        fencing_token=holder.fencing_token,
        holder=holder,
    )


async def release_claim(claim: Claim) -> None:
    if claim.holder is not None:
        await claim.holder.release()


__all__ = [
    "Claim",
    "FencedWriter",
    "LeaseLostError",
    "StaleWriteError",
    "WorkQueue",
    "WorkUnit",
    "claim_unit",
    "release_claim",
]
