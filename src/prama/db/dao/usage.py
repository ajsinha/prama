"""Dataset usage by day. Every signature takes the tenant.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from sqlalchemy import func, select

from prama.db.dao.base import Dao
from prama.db.models.usage import UsCoaccess, UsUsage


class UsageDao(Dao[UsUsage]):
    model = UsUsage

    async def record(
        self, tenant_id: str, *, dataset: str, day: str, source: str, queries: int, users: int
    ) -> None:
        """One day's count for a dataset from one source; a re-import replaces it."""
        row = (
            (
                await self._session.execute(
                    select(UsUsage).where(
                        UsUsage.tenant_id == tenant_id,
                        UsUsage.dataset == dataset,
                        UsUsage.day == day,
                        UsUsage.source == source,
                    )
                )
            )
            .scalars()
            .first()
        )
        if row is None:
            row = UsUsage(tenant_id=tenant_id, dataset=dataset, day=day, source=source)
            self._session.add(row)
        row.queries, row.users = queries, users
        await self._session.flush()

    async def totals(self, tenant_id: str, *, since: str) -> dict[str, tuple[int, int]]:
        """dataset -> (queries, the busiest day's distinct users) since *since*."""
        await self._session.flush()
        result = await self._session.execute(
            select(UsUsage.dataset, func.sum(UsUsage.queries), func.max(UsUsage.users))
            .where(UsUsage.tenant_id == tenant_id, UsUsage.day >= since)
            .group_by(UsUsage.dataset)
        )
        return {str(d): (int(q or 0), int(u or 0)) for d, q, u in result.all()}

    async def daily(
        self, tenant_id: str, *, since: str, dataset: str = ""
    ) -> list[tuple[str, str, str, int, int]]:
        """(dataset, day, source, queries, users) rows since *since*, oldest day first.

        One row per source: a dataset read through two warehouses has two
        counts for a day, and adding them would count a person twice.
        """
        await self._session.flush()
        stmt = select(
            UsUsage.dataset, UsUsage.day, UsUsage.source, UsUsage.queries, UsUsage.users
        ).where(UsUsage.tenant_id == tenant_id, UsUsage.day >= since)
        if dataset:
            stmt = stmt.where(UsUsage.dataset == dataset)
        result = await self._session.execute(
            stmt.order_by(UsUsage.day, UsUsage.dataset, UsUsage.source)
        )
        return [(str(d), str(day), str(s), int(q), int(u)) for d, day, s, q, u in result.all()]

    async def record_pair(
        self, tenant_id: str, *, pair: tuple[str, str], day: str, source: str, queries: int
    ) -> None:
        """One day's count of queries reading both datasets; a re-import replaces it."""
        first, second = sorted(pair)
        row = (
            (
                await self._session.execute(
                    select(UsCoaccess).where(
                        UsCoaccess.tenant_id == tenant_id,
                        UsCoaccess.dataset_a == first,
                        UsCoaccess.dataset_b == second,
                        UsCoaccess.day == day,
                        UsCoaccess.source == source,
                    )
                )
            )
            .scalars()
            .first()
        )
        if row is None:
            row = UsCoaccess(
                tenant_id=tenant_id, dataset_a=first, dataset_b=second, day=day, source=source
            )
            self._session.add(row)
        row.queries = queries
        await self._session.flush()

    async def pairs(self, tenant_id: str, *, since: str) -> dict[tuple[str, str], int]:
        """(dataset, dataset) -> queries reading both, since *since*."""
        await self._session.flush()
        result = await self._session.execute(
            select(UsCoaccess.dataset_a, UsCoaccess.dataset_b, func.sum(UsCoaccess.queries))
            .where(UsCoaccess.tenant_id == tenant_id, UsCoaccess.day >= since)
            .group_by(UsCoaccess.dataset_a, UsCoaccess.dataset_b)
        )
        return {(str(a), str(b)): int(n or 0) for a, b, n in result.all()}
