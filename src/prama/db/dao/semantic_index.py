"""Dataset-profile embeddings. Every signature takes the tenant.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select

from prama.db.dao.base import Dao
from prama.db.models.semantic_index import SxVector


class SemanticIndexDao(Dao[SxVector]):
    model = SxVector

    async def vectors(self, tenant_id: str, model: str) -> dict[str, tuple[str, list[float]]]:
        """dataset_id -> (text hash, vector) for *model*."""
        await self._session.flush()
        result = await self._session.execute(
            select(SxVector).where(SxVector.tenant_id == tenant_id, SxVector.model == model)
        )
        return {
            r.dataset_id: (r.text_hash, [float(x) for x in json.loads(r.vector_json)])
            for r in result.scalars()
        }

    async def store(
        self, tenant_id: str, dataset_id: str, model: str, text_hash: str, vector: list[float]
    ) -> None:
        row = (
            (
                await self._session.execute(
                    select(SxVector).where(
                        SxVector.tenant_id == tenant_id,
                        SxVector.dataset_id == dataset_id,
                        SxVector.model == model,
                    )
                )
            )
            .scalars()
            .first()
        )
        if row is None:
            row = SxVector(
                tenant_id=tenant_id,
                dataset_id=dataset_id,
                model=model,
                text_hash="",
                vector_json="[]",
                updated_at="",
            )
            self._session.add(row)
        row.text_hash, row.vector_json = text_hash, json.dumps(vector)
        row.updated_at = datetime.now(UTC).isoformat(timespec="milliseconds")
        await self._session.flush()
