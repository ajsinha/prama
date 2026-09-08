"""The database-backed lease provider.

``prama.core.concurrency`` defines the lease contract and an in-process
implementation; the durable one lives here because ``prama.db`` is the only
package permitted to touch SQLAlchemy.

Correctness rests on two things:

* **Atomic acquisition.** The insert/update that grants a lease is a single
  conditional statement, so two instances racing for the same resource cannot
  both win. Expiry is evaluated by the same statement, against the values in the
  row, rather than read-then-write from the application.
* **Monotonic fencing tokens.** Every successful acquisition increments a
  counter for that resource. A holder that stalls past its TTL and resumes will
  present a stale token, which a downstream store can reject — the difference
  between "we hope only one writer is active" and "a second writer cannot do
  damage".

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from prama.core.clock import Clock, SystemClock
from prama.core.concurrency.leases import Lease, LeaseProvider
from prama.core.ids import new_ulid
from prama.core.log import get_logger

_log = get_logger(__name__)

#: Timestamps are ISO-8601 UTC text on both engines, which sorts chronologically,
#: so expiry comparison is a plain string comparison and needs no dialect branch.
_ISO = "%Y-%m-%dT%H:%M:%S.%f"


def _iso(value: object) -> str:
    from datetime import datetime

    assert isinstance(value, datetime)
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


class DatabaseLeaseProvider(LeaseProvider):
    """Durable, fleet-wide leases held in the ``lease`` table."""

    def __init__(self, engine: AsyncEngine, *, clock: Clock | None = None) -> None:
        self._engine = engine
        self._clock = clock or SystemClock()

    async def acquire(self, resource: str, holder: str, ttl_seconds: float) -> Lease | None:
        now = self._clock.now()
        expires = now + timedelta(seconds=ttl_seconds)
        token = new_ulid()
        params = {
            "resource": resource,
            "holder": holder,
            "token": token,
            "acquired_at": _iso(now),
            "expires_at": _iso(expires),
            "now": _iso(now),
        }
        async with self._engine.begin() as conn:
            # A single conditional statement: insert when free, or take over an
            # expired or self-owned lease, incrementing the fencing token.
            await conn.execute(
                text(
                    """
                    INSERT INTO lease
                        (resource, holder, token, fencing_token,
                         acquired_at, expires_at, metadata_json)
                    VALUES (:resource, :holder, :token, 1,
                            :acquired_at, :expires_at, '{}')
                    ON CONFLICT (resource) DO UPDATE SET
                        holder        = excluded.holder,
                        token         = excluded.token,
                        fencing_token = lease.fencing_token + 1,
                        acquired_at   = excluded.acquired_at,
                        expires_at    = excluded.expires_at
                    WHERE lease.expires_at <= :now OR lease.holder = excluded.holder
                    """
                ),
                params,
            )
            row = (
                await conn.execute(
                    text(
                        "SELECT holder, token, fencing_token, acquired_at, expires_at "
                        "FROM lease WHERE resource = :resource"
                    ),
                    {"resource": resource},
                )
            ).first()
        if row is None or row[1] != token:
            return None  # another holder owns it
        return Lease(
            resource=resource,
            holder=holder,
            token=token,
            fencing_token=int(row[2]),
            acquired_at=now,
            expires_at=expires,
        )

    async def renew(self, lease: Lease, ttl_seconds: float) -> Lease | None:
        now = self._clock.now()
        expires = now + timedelta(seconds=ttl_seconds)
        async with self._engine.begin() as conn:
            result = await conn.execute(
                text(
                    "UPDATE lease SET expires_at = :expires_at "
                    "WHERE resource = :resource AND token = :token AND expires_at > :now"
                ),
                {
                    "resource": lease.resource,
                    "token": lease.token,
                    "expires_at": _iso(expires),
                    "now": _iso(now),
                },
            )
        if result.rowcount != 1:
            _log.warning(
                "lease renewal rejected for %s (holder %s): no longer owned",
                lease.resource,
                lease.holder,
            )
            return None
        return Lease(
            resource=lease.resource,
            holder=lease.holder,
            token=lease.token,
            fencing_token=lease.fencing_token,
            acquired_at=lease.acquired_at,
            expires_at=expires,
        )

    async def release(self, lease: Lease) -> bool:
        """Give up the lease by expiring it, not by deleting the row.

        Deleting would reset ``fencing_token`` for that resource, and a fencing
        token that can go backwards protects nothing: a stalled holder from a
        previous era would present a token indistinguishable from a current one.
        The row is one per resource, so keeping it costs nothing that matters.
        """
        async with self._engine.begin() as conn:
            result = await conn.execute(
                text(
                    "UPDATE lease SET expires_at = :now, holder = :holder "
                    "WHERE resource = :resource AND token = :token"
                ),
                {
                    "resource": lease.resource,
                    "token": lease.token,
                    "holder": f"{lease.holder} (released)",
                    "now": _iso(self._clock.now()),
                },
            )
        return result.rowcount == 1

    async def inspect(self, resource: str) -> Lease | None:
        from datetime import UTC, datetime

        now = self._clock.now()
        async with self._engine.connect() as conn:
            row = (
                await conn.execute(
                    text(
                        "SELECT holder, token, fencing_token, acquired_at, expires_at "
                        "FROM lease WHERE resource = :resource AND expires_at > :now"
                    ),
                    {"resource": resource, "now": _iso(now)},
                )
            ).first()
        if row is None:
            return None

        def parse(value: str) -> datetime:
            text_value = value[:-1] + "+00:00" if value.endswith("Z") else value
            return datetime.fromisoformat(text_value).astimezone(UTC)

        return Lease(
            resource=resource,
            holder=row[0],
            token=row[1],
            fencing_token=int(row[2]),
            acquired_at=parse(row[3]),
            expires_at=parse(row[4]),
        )

    async def purge_before(self, cutoff_iso: str) -> int:
        """Delete lease rows that expired before *cutoff_iso*.

        Housekeeping only, and deliberately awkward to call. Deleting a row
        resets that resource's fencing token, so the cutoff must be far enough
        in the past that no holder from before it could conceivably still be
        running — days, not minutes. The table holds one row per resource, so
        in practice this is never needed.
        """
        async with self._engine.begin() as conn:
            result = await conn.execute(
                text("DELETE FROM lease WHERE expires_at <= :cutoff"),
                {"cutoff": cutoff_iso},
            )
        return int(result.rowcount or 0)
