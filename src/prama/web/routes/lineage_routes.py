"""The Lineage workbench: what feeds what, how it is known, and what it reaches.

Every edge on the page comes from the lineage store and says where it came
from: `parsed` by the SQL parser, `inferred` by the fallback reader or a model
(waiting for a person), `confirmed` or `rejected` by one. The gaps of the
latest scans sit beside the graph, because a partial graph whose gaps are
visible is worth more than a complete-looking one whose gaps are not.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Form, Query, Request

from prama.core.errors import PramaError
from prama.lineage.graph import Column
from prama.lineage.trust import trust_of
from prama.web.deps import Caller, Uow
from prama.web.rendering import flash_error_and_log, redirect_to, render
from prama.web.routes.base import UiRoutes


class LineageRoutes(UiRoutes):
    """The lineage workbench."""

    SUBJECT = "relationship"

    def register(self) -> None:
        self.page("/lineage", self.index, name="lineage")
        self.page(
            "/lineage/edges/{edge_id}/decide",
            self.decide,
            name="lineage_decide",
            methods=["POST"],
        )

    async def index(
        self,
        request: Request,
        uow: Uow,
        caller: Caller,
        dataset: Annotated[str, Query()] = "",
        column: Annotated[str, Query()] = "",
    ) -> Any:
        tenant = caller.tenant_id
        edges = await uow.lineage.edges(tenant, dataset=dataset.strip())
        runs = await uow.lineage.runs(tenant, limit=10)
        sources = {s.id: s.name for s in await uow.lineage.sources(tenant)}
        gaps = await uow.lineage.gaps(tenant, runs[0].id) if runs else []
        impact: dict[str, Any] | None = None
        if column.strip():
            try:
                origin = Column.parse(column.strip())
                graph = await uow.lineage.graph(tenant)
                radius = graph.blast_radius(origin)
                latest = (await uow.evidence.latest_per_control(tenant)).values()
                trust = trust_of(origin, graph, latest)
                impact = {
                    "trust": trust.score,
                    "trust_explained": trust.explain(),
                    "origin": origin.qualified,
                    "upstream": [e.source.qualified for e in graph.upstream(origin)],
                    "reached": [(r.column.qualified, r.impact, r.depth) for r in radius.reached],
                }
            except ValueError as exc:
                impact = {"origin": column, "error": str(exc)}
        return render(
            request,
            "lineage/index.html",
            edges=edges[:500],
            total=len(edges),
            runs=runs,
            sources=sources,
            gaps=gaps,
            dataset=dataset,
            column=column,
            impact=impact,
            conflicts=await _conflicts(uow, caller.tenant_id),
        )

    async def decide(
        self,
        request: Request,
        uow: Uow,
        caller: Caller,
        edge_id: str,
        decision: Annotated[str, Form()] = "",
        note: Annotated[str, Form()] = "",
    ) -> Any:
        try:
            await uow.lineage.decide(
                caller.tenant_id, edge_id, decision, by=caller.principal_id, note=note
            )
        except PramaError as exc:
            flash_error_and_log(request, "That decision could not be recorded", exc)
            return redirect_to(request, "lineage")
        return redirect_to(request, "lineage", flash_message=f"Edge {decision}.")


async def _conflicts(uow: Any, tenant_id: str) -> list[dict[str, Any]]:
    from prama.importers.catalog import disagreements

    return await disagreements(uow, tenant_id)
