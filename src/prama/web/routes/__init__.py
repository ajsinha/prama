"""Route classes, one per area of the console.

Registered here rather than discovered, so the set of pages a build serves is
readable in one place and a half-finished module cannot quietly appear in
production because it happened to be importable.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.web.routes.base import UiRoutes
from prama.web.routes.control_routes import ControlRoutes
from prama.web.routes.declaration_routes import DeclarationRoutes
from prama.web.routes.estate_routes import EstateRoutes
from prama.web.routes.operations_routes import OperationsRoutes
from prama.web.routes.proposal_routes import ProposalRoutes
from prama.web.routes.relationship_routes import RelationshipRoutes

ROUTE_CLASSES: tuple[type[UiRoutes], ...] = (
    EstateRoutes,
    DeclarationRoutes,
    ControlRoutes,
    RelationshipRoutes,
    ProposalRoutes,
    OperationsRoutes,
)

__all__ = [
    "ROUTE_CLASSES",
    "ControlRoutes",
    "DeclarationRoutes",
    "EstateRoutes",
    "OperationsRoutes",
    "ProposalRoutes",
    "RelationshipRoutes",
    "UiRoutes",
]
