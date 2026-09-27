"""Uploaded DQ delegates. Every signature takes the tenant.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from prama.core.errors import ConflictError
from prama.db.dao.base import Dao
from prama.db.models.delegate import DqDelegateUpload


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class DelegateUploadDao(Dao[DqDelegateUpload]):
    model = DqDelegateUpload

    async def submit(
        self,
        tenant_id: str,
        *,
        name: str,
        version: str,
        filename: str,
        source: str,
        source_hash: str,
        state: str,
        described: str,
        findings: str,
        by: str,
    ) -> DqDelegateUpload:
        await self._session.flush()
        clash = await self._session.execute(
            select(DqDelegateUpload.id).where(
                DqDelegateUpload.tenant_id == tenant_id,
                DqDelegateUpload.name == name,
                DqDelegateUpload.version == version,
            )
        )
        if clash.first() is not None:
            raise ConflictError(
                f"{name}@{version} has already been uploaded",
                remedy="Raise the delegate's version for a new upload; a version is immutable.",
            )
        row = DqDelegateUpload(
            tenant_id=tenant_id,
            name=name,
            version=version,
            filename=filename,
            source=source,
            source_hash=source_hash,
            state=state,
            described=described,
            findings=findings,
            submitted_by=by,
            submitted_at=_now(),
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def all(self, tenant_id: str) -> list[DqDelegateUpload]:
        await self._session.flush()
        result = await self._session.execute(
            select(DqDelegateUpload)
            .where(DqDelegateUpload.tenant_id == tenant_id)
            .order_by(DqDelegateUpload.name, DqDelegateUpload.submitted_at)
        )
        return list(result.scalars().all())

    async def approved(self, tenant_id: str) -> list[DqDelegateUpload]:
        return [r for r in await self.all(tenant_id) if r.state == "approved"]

    async def one(self, tenant_id: str, upload_id: str) -> DqDelegateUpload | None:
        row = await self._session.get(DqDelegateUpload, upload_id)
        return row if row is not None and row.tenant_id == tenant_id else None

    async def decide(
        self, row: DqDelegateUpload, *, state: str, by: str, note: str = ""
    ) -> DqDelegateUpload:
        row.state = state
        row.decided_by = by
        row.decided_at = _now()
        row.note = note
        await self._session.flush()
        return row
