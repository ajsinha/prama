"""A conformance check for a lease provider: part of docs/developer/secrets-and-leases.md.

`prama.core.concurrency.leases.LeaseProvider` states its contract in two
sentences: ``acquire`` is atomic with respect to other holders, and ``renew`` and
``release`` are refused to a holder that no longer owns the resource. Everything
the scheduler and the steward protocol rely on follows from those two, plus a
fencing token that only ever grows.

``check`` runs a provider through each property and returns the ones it broke,
by name. A new provider (Redis, etcd, a cloud lock service) passes this before
anything is built on it; the test runs it against both shipped providers and
against a deliberately broken one, so the check itself is known to be able to fail.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.core.concurrency.leases import LeaseProvider

TTL = 30.0


async def check(provider: LeaseProvider, resource: str = "contract.check") -> list[str]:
    """Every property *provider* breaks, by name. Empty means it conforms."""
    broken: list[str] = []
    first = await provider.acquire(resource, "holder-a", TTL)
    if first is None:
        return ["a free resource could not be acquired"]

    if await provider.acquire(resource, "holder-b", TTL) is not None:
        broken.append("a second holder acquired a resource that was already held")

    held = await provider.inspect(resource)
    if held is None or held.holder != "holder-a":
        broken.append("inspect does not report the current holder")

    if await provider.release(first) is not True:
        broken.append("the holder could not release its own lease")
    if await provider.renew(first, TTL) is not None:
        broken.append("a released lease could still be renewed")

    second = await provider.acquire(resource, "holder-b", TTL)
    if second is None:
        broken.append("a released resource could not be acquired by somebody else")
        return broken
    if second.fencing_token <= first.fencing_token:
        broken.append("the fencing token did not increase between holders")
    if await provider.release(first) is not False:
        broken.append("a superseded holder released somebody else's lease")
    if await provider.renew(first, TTL) is not None:
        broken.append("a superseded holder renewed somebody else's lease")
    await provider.release(second)
    return broken
