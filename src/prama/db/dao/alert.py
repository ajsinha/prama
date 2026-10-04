"""The alert router's memory: what it has sent, and what waits for the digest.

`prama.alert.route.Router` deduplicates within a quiet period, and a router
that forgot everything on restart — or that each of three servers held its own
copy of — would announce a three-day-old incident again every time a process
started or a different server ran the controls. So its state is here, in the
database every server shares, and a router is seeded from it before it routes
and saved back to it afterwards.

Every read and write takes the tenant.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select, update

from prama.db.dao.base import Dao
from prama.db.models.alert import AlrDigest, AlrState

#: Kept from a failure message. A notifier's error is a sentence and a remedy,
#: not a stack trace.
_ERROR_WIDTH = 2000


def _instant(stamp: str) -> datetime:
    parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


class AlertDao(Dao[AlrState]):
    """Open alerts and the digest queue, one estate at a time."""

    model = AlrState

    # -- what has been sent ------------------------------------------------

    async def history(self, tenant_id: str) -> dict[str, tuple[datetime, float]]:
        """Fingerprint → (last sent, severity): what `Router(history=...)` takes."""
        await self._guarded_flush()
        rows = await self._session.execute(
            select(AlrState.fingerprint, AlrState.last_sent_at, AlrState.severity).where(
                AlrState.tenant_id == tenant_id
            )
        )
        return {fp: (_instant(sent), float(severity)) for fp, sent, severity in rows.all()}

    async def open_for(self, tenant_id: str, identity: str) -> list[AlrState]:
        """The open alerts a control raised: what a pass now resolves."""
        await self._guarded_flush()
        return await self._all(
            select(AlrState)
            .where(AlrState.tenant_id == tenant_id, AlrState.identity == identity)
            .order_by(AlrState.last_sent_at)
        )

    async def open_alerts(self, tenant_id: str) -> list[AlrState]:
        await self._guarded_flush()
        return await self._all(
            select(AlrState)
            .where(AlrState.tenant_id == tenant_id)
            .order_by(AlrState.last_sent_at.desc())
        )

    async def remember(
        self,
        tenant_id: str,
        *,
        fingerprint: str,
        identity: str,
        dataset: str,
        fault: str,
        severity: float,
        last_sent_at: str,
        alert: dict[str, Any],
    ) -> AlrState:
        """Record that this alert went out, replacing what was known about it."""
        await self._guarded_flush()
        existing = await self._one_or_none(
            select(AlrState).where(
                AlrState.tenant_id == tenant_id, AlrState.fingerprint == fingerprint
            )
        )
        if existing is None:
            existing = AlrState(tenant_id=tenant_id, fingerprint=fingerprint, last_error="")
            self._session.add(existing)
        existing.identity = identity[:128]
        existing.dataset = dataset[:255]
        existing.fault = fault
        existing.severity = float(severity)
        existing.last_sent_at = last_sent_at
        existing.alert_json = dict(alert)
        await self._guarded_flush()
        return existing

    async def forget(self, tenant_id: str, fingerprint: str) -> bool:
        """The alert is over. False when there was nothing to forget."""
        result = await self._session.execute(
            delete(AlrState)
            .where(AlrState.tenant_id == tenant_id, AlrState.fingerprint == fingerprint)
            .execution_options(synchronize_session="fetch")
        )
        return bool(getattr(result, "rowcount", 0))

    async def record_error(self, tenant_id: str, fingerprint: str, error: str) -> None:
        """Keep why the last delivery of this alert failed; empty clears it."""
        await self._session.execute(
            update(AlrState)
            .where(AlrState.tenant_id == tenant_id, AlrState.fingerprint == fingerprint)
            .values(last_error=error[:_ERROR_WIDTH])
            .execution_options(synchronize_session="fetch")
        )

    # -- the digest ----------------------------------------------------------

    async def queue(
        self,
        tenant_id: str,
        *,
        fingerprint: str,
        dataset: str,
        change: str,
        dispatch: dict[str, Any],
        queued_at: str,
    ) -> AlrDigest:
        row = AlrDigest(
            tenant_id=tenant_id,
            fingerprint=fingerprint,
            dataset=dataset[:255],
            change=change,
            dispatch_json=dict(dispatch),
            queued_at=queued_at,
            error="",
        )
        self._session.add(row)
        await self._guarded_flush()
        return row

    async def pending(self, tenant_id: str) -> list[AlrDigest]:
        """Items no digest has carried yet, oldest first."""
        await self._guarded_flush()
        result = await self._session.execute(
            select(AlrDigest)
            .where(AlrDigest.tenant_id == tenant_id, AlrDigest.sent_at.is_(None))
            .order_by(AlrDigest.queued_at)
        )
        return list(result.scalars().all())

    async def last_digest_at(self, tenant_id: str) -> str | None:
        """When the last digest went out, or None if none ever has."""
        await self._guarded_flush()
        result = await self._session.execute(
            select(func.max(AlrDigest.sent_at)).where(AlrDigest.tenant_id == tenant_id)
        )
        value = result.scalar_one_or_none()
        return str(value) if value else None

    async def mark_sent(
        self, tenant_id: str, ids: list[str], *, sent_at: str, error: str = ""
    ) -> None:
        """Close digest items: carried by the digest sent at *sent_at*."""
        if not ids:
            return
        await self._session.execute(
            update(AlrDigest)
            .where(AlrDigest.tenant_id == tenant_id, AlrDigest.id.in_(ids))
            .values(sent_at=sent_at, error=error[:_ERROR_WIDTH])
            .execution_options(synchronize_session="fetch")
        )
