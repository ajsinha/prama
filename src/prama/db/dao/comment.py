"""Comment threads. Every signature takes the tenant.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select

from prama.core.errors import NotFoundError, ValidationError
from prama.db.dao.base import Dao
from prama.db.models.comment import CmComment


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class CommentDao(Dao[CmComment]):
    model = CmComment

    async def post(
        self,
        tenant_id: str,
        *,
        object_kind: str,
        object_ref: str,
        author_id: str,
        body: str,
        mentions: list[str],
        parent_id: str | None = None,
    ) -> CmComment:
        if not body.strip():
            raise ValidationError("a comment needs some text", remedy="Write the comment.")
        if parent_id is not None:
            parent = await self.one(tenant_id, parent_id)
            if parent is None or parent.parent_id is not None:
                raise NotFoundError(
                    "no thread to reply to", remedy="Reply to a thread's first comment."
                )
            object_kind, object_ref = parent.object_kind, parent.object_ref
            if parent.state == "resolved":
                parent.state, parent.resolved_by, parent.resolved_at = "open", None, None
        row = CmComment(
            tenant_id=tenant_id,
            object_kind=object_kind,
            object_ref=object_ref,
            parent_id=parent_id,
            author_id=author_id,
            body=body.strip(),
            mentions_json=json.dumps(sorted(set(mentions))),
            created_at=_now(),
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def one(self, tenant_id: str, comment_id: str) -> CmComment | None:
        row = await self._session.get(CmComment, comment_id)
        return row if row is not None and row.tenant_id == tenant_id else None

    async def thread(self, tenant_id: str, root_id: str) -> list[CmComment]:
        await self._session.flush()
        result = await self._session.execute(
            select(CmComment)
            .where(
                CmComment.tenant_id == tenant_id,
                (CmComment.id == root_id) | (CmComment.parent_id == root_id),
            )
            .order_by(CmComment.created_at)
        )
        return list(result.scalars().all())

    async def on(self, tenant_id: str, object_kind: str, object_ref: str) -> list[CmComment]:
        await self._session.flush()
        result = await self._session.execute(
            select(CmComment)
            .where(
                CmComment.tenant_id == tenant_id,
                CmComment.object_kind == object_kind,
                CmComment.object_ref == object_ref,
            )
            .order_by(CmComment.created_at)
        )
        return list(result.scalars().all())

    async def open_threads(self, tenant_id: str) -> list[CmComment]:
        await self._session.flush()
        result = await self._session.execute(
            select(CmComment)
            .where(
                CmComment.tenant_id == tenant_id,
                CmComment.parent_id.is_(None),
                CmComment.state == "open",
            )
            .order_by(CmComment.created_at.desc())
        )
        return list(result.scalars().all())

    async def resolve(self, tenant_id: str, root_id: str, *, by: str) -> CmComment:
        row = await self.one(tenant_id, root_id)
        if row is None or row.parent_id is not None:
            raise NotFoundError("no such thread", remedy="Resolve a thread's first comment.")
        row.state, row.resolved_by, row.resolved_at = "resolved", by, _now()
        await self._session.flush()
        return row
