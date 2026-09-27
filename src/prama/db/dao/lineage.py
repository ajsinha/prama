"""The lineage store, persisted.

A scan of a source is a run. Each edge the run finds is matched to the one
already stored by its identity (the source, both columns and the transform),
so a re-scan refreshes rather than duplicates. An edge the same source used to
produce and now does not is closed (`valid_to`), never deleted: "this report
was fed by that column until Tuesday" is lineage too.

A person's decision outlives the scans: a rejected edge stays rejected however
often a parser finds it again.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select

from prama.core.errors import ConflictError, NotFoundError, ValidationError
from prama.db.dao.base import Dao
from prama.db.models.lineage import LinEdge, LinGap, LinRun, LinSource
from prama.lineage.graph import Column, Edge, LineageGraph, Transform

#: Statuses that are part of the working graph.
ACTIVE = ("parsed", "inferred", "confirmed")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def identity_of(source_id: str, edge: Edge) -> str:
    key = "|".join((source_id, edge.source.qualified, edge.target.qualified, edge.transform.value))
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def edge_of(row: LinEdge) -> Edge:
    return Edge(
        source=Column(dataset=row.source_dataset, name=row.source_column),
        target=Column(dataset=row.target_dataset, name=row.target_column),
        transform=Transform(row.transform),
        produced_by=row.produced_by,
        expression=row.expression,
    )


class LineageDao(Dao[LinEdge]):
    """Sources, runs, edges and gaps, scoped by tenant in every signature."""

    model = LinEdge

    # -- sources -----------------------------------------------------------

    async def sources(self, tenant_id: str) -> list[LinSource]:
        await self._session.flush()
        result = await self._session.execute(
            select(LinSource).where(LinSource.tenant_id == tenant_id).order_by(LinSource.name)
        )
        return list(result.scalars().all())

    async def source(self, tenant_id: str, name: str) -> LinSource | None:
        await self._session.flush()
        result = await self._session.execute(
            select(LinSource).where(LinSource.tenant_id == tenant_id, LinSource.name == name)
        )
        return result.scalars().one_or_none()

    async def ensure_source(
        self,
        tenant_id: str,
        name: str,
        *,
        kind: str,
        location: str = "",
        dialect: str = "ansi",
        by: str | None = None,
    ) -> LinSource:
        """The named source, created on first use; a kind mismatch is refused."""
        found = await self.source(tenant_id, name)
        if found is not None:
            if found.kind != kind:
                raise ConflictError(
                    f"the lineage source {name!r} is a {found.kind} source, not {kind}",
                    remedy="Use another name for a different kind of source.",
                    context={"source": name},
                )
            return found
        created = LinSource(
            tenant_id=tenant_id,
            name=name,
            kind=kind,
            location=location,
            dialect=dialect,
            created_by=by,
        )
        self._session.add(created)
        await self._session.flush()
        return created

    # -- runs --------------------------------------------------------------

    async def record_run(
        self,
        tenant_id: str,
        source: LinSource,
        batches: Sequence[tuple[Sequence[Edge], str, str, float]],
        gaps: Iterable[Any],
        *,
        statements: int,
        understood: float,
        by: str | None = None,
    ) -> LinRun:
        """Store one scan: *batches* are (edges, method, status, confidence)."""
        now = _now()
        run = LinRun(
            tenant_id=tenant_id,
            source_id=source.id,
            started_at=now,
            statements=statements,
            understood=max(0.0, min(1.0, understood)),
            started_by=by,
        )
        self._session.add(run)
        await self._session.flush()
        existing = {
            row.identity: row
            for row in (
                await self._session.execute(
                    select(LinEdge).where(
                        LinEdge.tenant_id == tenant_id, LinEdge.source_id == source.id
                    )
                )
            ).scalars()
        }
        seen: set[str] = set()
        for edges, method, status, confidence in batches:
            for edge in edges:
                key = identity_of(source.id, edge)
                if key in seen:
                    continue
                seen.add(key)
                row = existing.get(key)
                if row is None:
                    self._session.add(
                        LinEdge(
                            tenant_id=tenant_id,
                            source_id=source.id,
                            identity=key,
                            source_dataset=edge.source.dataset,
                            source_column=edge.source.name,
                            target_dataset=edge.target.dataset,
                            target_column=edge.target.name,
                            transform=edge.transform.value,
                            produced_by=edge.produced_by,
                            expression=edge.expression,
                            status=status,
                            method=method,
                            confidence=confidence,
                            valid_from=now,
                            first_seen_run=run.id,
                            last_seen_run=run.id,
                        )
                    )
                    continue
                row.last_seen_run = run.id
                row.expression = edge.expression
                if row.valid_to is not None and row.status != "rejected":
                    row.valid_to = None  # found again: back in the working graph
        closed = 0
        for key, row in existing.items():
            if key not in seen and row.valid_to is None:
                row.valid_to = now
                closed += 1
        gap_rows = list(gaps)
        for gap in gap_rows:
            self._session.add(
                LinGap(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    kind=gap.kind,
                    detail=gap.detail,
                    statement=getattr(gap, "statement", "")[:4000],
                )
            )
        run.edges, run.gaps = len(seen), len(gap_rows)
        run.outcome = "ok" if not gap_rows else "partial"
        run.detail = f"{closed} edge(s) no longer produced by this source" if closed else ""
        run.finished_at = _now()
        source.last_run_id = run.id
        await self._session.flush()
        return run

    async def runs(self, tenant_id: str, *, limit: int = 20) -> list[LinRun]:
        result = await self._session.execute(
            select(LinRun)
            .where(LinRun.tenant_id == tenant_id)
            .order_by(LinRun.started_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def gaps(self, tenant_id: str, run_id: str) -> list[LinGap]:
        result = await self._session.execute(
            select(LinGap).where(LinGap.tenant_id == tenant_id, LinGap.run_id == run_id)
        )
        return list(result.scalars().all())

    # -- the graph ---------------------------------------------------------

    async def edges(self, tenant_id: str, *, dataset: str = "") -> list[LinEdge]:
        """Current edges (not closed, not rejected), optionally touching *dataset*."""
        await self._session.flush()
        statement = select(LinEdge).where(
            LinEdge.tenant_id == tenant_id,
            LinEdge.valid_to.is_(None),
            LinEdge.status.in_(ACTIVE),
        )
        if dataset:
            statement = statement.where(
                or_(LinEdge.source_dataset == dataset, LinEdge.target_dataset == dataset)
            )
        result = await self._session.execute(
            statement.order_by(LinEdge.target_dataset, LinEdge.target_column)
        )
        return list(result.scalars().all())

    async def graph(self, tenant_id: str) -> LineageGraph:
        graph = LineageGraph()
        graph.add_all(edge_of(row) for row in await self.edges(tenant_id))
        return graph

    async def decide(
        self, tenant_id: str, edge_id: str, decision: str, *, by: str | None, note: str = ""
    ) -> LinEdge:
        """A person confirms or rejects an edge. The decision outlives re-scans."""
        if decision not in ("confirmed", "rejected"):
            raise ValidationError(
                f"{decision!r} is not a decision", remedy="Confirm or reject the edge."
            )
        row = await self._session.get(LinEdge, edge_id)
        if row is None or row.tenant_id != tenant_id:
            raise NotFoundError(
                "no such lineage edge",
                remedy="Edges are listed on the Lineage page.",
                context={"edge": edge_id},
            )
        row.status, row.decided_by, row.decided_at = decision, by, _now()
        row.decision_note = note or None
        await self._session.flush()
        return row
