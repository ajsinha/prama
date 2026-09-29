"""The estate map, and one dataset's page.

The map is the front door. It is drawn from *declarations*, not from a crawl,
which is why it can show a dataset the platform has never connected to — and
showing those is the point. A physical-first tool draws a picture of what it
managed to reach and calls it the estate; the gap between that picture and the
business's actual estate is invisible, and it is exactly where the risk lives.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Form, Request

from prama.core.errors import PramaError
from prama.security.scopes import permits
from prama.semantic.services import EstateService
from prama.web.deps import Caller, Uow
from prama.web.rendering import flash_error_and_log, redirect_to, render
from prama.web.routes.base import UiRoutes
from prama.web.viewmodels import DatasetCard, RelationshipEdge


class EstateRoutes(UiRoutes):
    """The map, its data endpoint, and a dataset's detail page."""

    def register(self) -> None:
        self.page("/estate", self.estate_map, name="estate_map")
        self.page("/estate/graph.json", self.estate_graph, name="estate_graph")
        self.page("/estate/gaps", self.estate_gaps, name="estate_gaps")
        self.page("/estate/{dataset_id}", self.dataset_detail, name="dataset_detail")
        self.page(
            "/estate/{dataset_id}/approve",
            self.approve_dataset,
            name="dataset_approve",
            methods=["POST"],
            scope="declaration:approve",
        )

    async def estate_map(self, request: Request, caller: Caller, uow: Uow) -> Any:
        """The map shell. The graph itself arrives separately.

        Two requests rather than one because the node set can run to thousands
        and a page that blocks on the whole graph feels broken before it feels
        slow. The shell renders with the counts immediately; the canvas fills
        when the data lands.
        """
        datasets = [
            DatasetCard.of(v) for v in await uow.datasets.list_current(caller.tenant_id, limit=5000)
        ]
        return render(
            request,
            "estate/map.html",
            total=len(datasets),
            unbound=sum(1 for d in datasets if not d.is_bound),
            incomplete=sum(1 for d in datasets if not d.is_complete),
            tier_one=sum(1 for d in datasets if d.criticality == 1),
        )

    async def estate_graph(self, caller: Caller, uow: Uow) -> dict[str, Any]:
        """Nodes and edges for Sigma, in graphology's serialised form.

        Colour carries criticality and *nothing else*; the proposed/declared
        distinction is carried by the edge style, because a reader who cannot
        distinguish the hues must still be able to distinguish an inference
        from a statement of fact.
        """
        datasets = [
            DatasetCard.of(v) for v in await uow.datasets.list_current(caller.tenant_id, limit=5000)
        ]
        edges = [
            RelationshipEdge.of(v)
            for v in await uow.relationships.list_current(caller.tenant_id, limit=20000)
        ]
        known = {d.id for d in datasets}
        return {
            "nodes": [
                {
                    "key": d.id,
                    "attributes": {
                        "label": d.name,
                        # 14 down to 8, not 10 down to 4. Criticality should be
                        # legible at a glance and a Tier 4 node still has to be
                        # big enough to click: a map whose least important
                        # nodes cannot be hit is a map that hides them.
                        "size": 16 - 2 * d.criticality,
                        "tier": d.criticality,
                        "bound": d.is_bound,
                        "complete": d.is_complete,
                        "shape": d.shape,
                    },
                }
                for d in datasets
            ],
            # An edge to a dataset that is not in the node set would make Sigma
            # throw and the whole map disappear. It happens legitimately —
            # a relationship survives its counterparty being retired — so it is
            # dropped here and counted, never left to fail at render time.
            "edges": [
                {
                    "key": e.id,
                    "source": e.from_dataset_id,
                    "target": e.to_dataset_id,
                    "attributes": {"kind": e.kind, "style": e.style, "status": e.status},
                }
                for e in edges
                if e.from_dataset_id in known and e.to_dataset_id in known
            ],
            "dangling_edges": sum(
                1 for e in edges if e.from_dataset_id not in known or e.to_dataset_id not in known
            ),
        }

    async def estate_gaps(self, request: Request, caller: Caller, uow: Uow) -> Any:
        """The honest list: declared but unreachable, unowned, or unshaped."""
        gaps = await EstateService(uow).coverage_gaps(caller.tenant_id)
        return render(request, "estate/gaps.html", gaps=gaps)

    async def dataset_detail(
        self, request: Request, dataset_id: str, caller: Caller, uow: Uow
    ) -> Any:
        version = await uow.datasets.require_current(dataset_id, tenant_id=caller.tenant_id)
        attributes = await uow.attributes.for_dataset(dataset_id, tenant_id=caller.tenant_id)
        relationships = await uow.relationships.touching(caller.tenant_id, dataset_id)
        return render(
            request,
            "estate/dataset.html",
            dataset=DatasetCard.of(version),
            attributes=attributes,
            relationships=[RelationshipEdge.of(r) for r in relationships],
            history_count=len(await uow.datasets.history(dataset_id, tenant_id=caller.tenant_id)),
            # Held, and whether this person may approve it: the approve scope,
            # and at Tier 1 not being its author (the service refuses anyway;
            # hiding a button that would be refused is courtesy).
            held=version.lifecycle_state == "proposed",
            author=version.authored_by,
            can_approve=(
                version.lifecycle_state == "proposed"
                and permits(caller.scopes, "declaration:approve")
                and not (version.criticality == 1 and version.authored_by == caller.principal_id)
            ),
        )

    async def approve_dataset(
        self,
        request: Request,
        dataset_id: str,
        caller: Caller,
        uow: Uow,
        reason: Annotated[str, Form()] = "",
    ) -> Any:
        """Approve a held declaration, as the signed-in person."""
        from prama.semantic.services import DatasetService

        try:
            version = await DatasetService(uow).approve(
                tenant_id=caller.tenant_id,
                dataset_id=dataset_id,
                approved_by=caller.require_principal(),
                reason=reason.strip() or "approved in the console",
            )
        except PramaError as exc:
            flash_error_and_log(request, "That declaration could not be approved", exc)
            return redirect_to(request, "dataset_detail", dataset_id=dataset_id)
        return redirect_to(
            request,
            "dataset_detail",
            dataset_id=dataset_id,
            flash_message=f"{version.name} approved; it is now in effect.",
        )
