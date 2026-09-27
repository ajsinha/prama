"""Code sources, their analysis runs, and the units each run read.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from prama.core.errors import ConflictError
from prama.db.dao.base import Dao
from prama.db.models.code import CodeAnalysisRun, CodeSource, CodeUnit


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class CodeDao(Dao[CodeSource]):
    """Every signature takes the tenant."""

    model = CodeSource

    async def sources(self, tenant_id: str) -> list[CodeSource]:
        await self._session.flush()
        result = await self._session.execute(
            select(CodeSource).where(CodeSource.tenant_id == tenant_id).order_by(CodeSource.name)
        )
        return list(result.scalars().all())

    async def source(self, tenant_id: str, name: str) -> CodeSource | None:
        await self._session.flush()
        result = await self._session.execute(
            select(CodeSource).where(CodeSource.tenant_id == tenant_id, CodeSource.name == name)
        )
        return result.scalars().one_or_none()

    async def ensure_source(
        self,
        tenant_id: str,
        name: str,
        *,
        kind: str,
        url: str | None = None,
        ref: str | None = None,
        secret_ref: str | None = None,
        by: str | None = None,
    ) -> CodeSource:
        found = await self.source(tenant_id, name)
        if found is not None:
            if found.kind != kind:
                raise ConflictError(
                    f"the code source {name!r} is a {found.kind} source, not {kind}",
                    remedy="Use another name.",
                    context={"source": name},
                )
            return found
        row = CodeSource(
            tenant_id=tenant_id,
            name=name,
            kind=kind,
            url=url,
            ref=ref,
            secret_ref=secret_ref,
            created_by=by,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def start_run(
        self, tenant_id: str, source: CodeSource, snapshot_hash: str
    ) -> CodeAnalysisRun:
        run = CodeAnalysisRun(
            tenant_id=tenant_id,
            source_id=source.id,
            snapshot_hash=snapshot_hash,
            status="running",
            started_at=_now(),
        )
        self._session.add(run)
        await self._session.flush()
        return run

    async def finish_run(
        self,
        run: CodeAnalysisRun,
        *,
        status: str,
        inventory: dict[str, Any],
        coverage: dict[str, Any],
        error: str | None = None,
    ) -> None:
        run.status, run.inventory_json, run.coverage_json = status, inventory, coverage
        run.error, run.finished_at = error, _now()
        await self._session.flush()

    def add_unit(self, tenant_id: str, run_id: str, **fields: Any) -> CodeUnit:
        unit = CodeUnit(tenant_id=tenant_id, run_id=run_id, **fields)
        self._session.add(unit)
        return unit

    async def runs(self, tenant_id: str, *, limit: int = 20) -> list[CodeAnalysisRun]:
        result = await self._session.execute(
            select(CodeAnalysisRun)
            .where(CodeAnalysisRun.tenant_id == tenant_id)
            .order_by(CodeAnalysisRun.started_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def last_completed_run(
        self, tenant_id: str, source_id: str, *, before: str
    ) -> CodeAnalysisRun | None:
        """The source's most recent finished run other than *before*: the base to reuse."""
        await self._session.flush()
        result = await self._session.execute(
            select(CodeAnalysisRun)
            .where(
                CodeAnalysisRun.tenant_id == tenant_id,
                CodeAnalysisRun.source_id == source_id,
                CodeAnalysisRun.id != before,
                CodeAnalysisRun.status.in_(("succeeded", "partial")),
            )
            .order_by(CodeAnalysisRun.started_at.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def units(self, tenant_id: str, run_id: str) -> list[CodeUnit]:
        result = await self._session.execute(
            select(CodeUnit)
            .where(CodeUnit.tenant_id == tenant_id, CodeUnit.run_id == run_id)
            .order_by(CodeUnit.path)
        )
        return list(result.scalars().all())
