"""Route classes, one per area of the console.

Registered here rather than discovered, so the set of pages a build serves is
readable in one place and a half-finished module cannot quietly appear in
production because it happened to be importable.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.web.routes.account_routes import AccountRoutes
from prama.web.routes.admin_routes import AdminRoutes
from prama.web.routes.agent_routes import AgentRoutes
from prama.web.routes.attestation_routes import AttestationRoutes
from prama.web.routes.auth_routes import AuthRoutes
from prama.web.routes.base import UiRoutes
from prama.web.routes.code_routes import CodeRoutes
from prama.web.routes.control_routes import ControlRoutes
from prama.web.routes.declaration_routes import DeclarationRoutes
from prama.web.routes.delegate_routes import DelegateRoutes
from prama.web.routes.estate_routes import EstateRoutes
from prama.web.routes.glossary_routes import GlossaryRoutes
from prama.web.routes.lineage_routes import LineageRoutes
from prama.web.routes.llm_routes import LlmRoutes
from prama.web.routes.operations_routes import OperationsRoutes
from prama.web.routes.preview_routes import PreviewRoutes
from prama.web.routes.proposal_routes import ProposalRoutes
from prama.web.routes.public_routes import PublicRoutes
from prama.web.routes.recon_routes import ReconRoutes
from prama.web.routes.relationship_routes import RelationshipRoutes
from prama.web.routes.report_routes import ReportRoutes
from prama.web.routes.schedule_routes import ScheduleRoutes
from prama.web.routes.triage_routes import TriageRoutes

ROUTE_CLASSES: tuple[type[UiRoutes], ...] = (
    PublicRoutes,
    AuthRoutes,
    AccountRoutes,
    AdminRoutes,
    LlmRoutes,
    AgentRoutes,
    DelegateRoutes,
    GlossaryRoutes,
    EstateRoutes,
    DeclarationRoutes,
    ControlRoutes,
    PreviewRoutes,
    RelationshipRoutes,
    LineageRoutes,
    CodeRoutes,
    ProposalRoutes,
    OperationsRoutes,
    TriageRoutes,
    ReconRoutes,
    AttestationRoutes,
    ReportRoutes,
    ScheduleRoutes,
)

__all__ = [
    "ROUTE_CLASSES",
    "AccountRoutes",
    "AdminRoutes",
    "AgentRoutes",
    "AttestationRoutes",
    "AuthRoutes",
    "CodeRoutes",
    "ControlRoutes",
    "DeclarationRoutes",
    "DelegateRoutes",
    "EstateRoutes",
    "GlossaryRoutes",
    "LineageRoutes",
    "LlmRoutes",
    "OperationsRoutes",
    "PreviewRoutes",
    "ProposalRoutes",
    "PublicRoutes",
    "ReconRoutes",
    "RelationshipRoutes",
    "ReportRoutes",
    "ScheduleRoutes",
    "TriageRoutes",
    "UiRoutes",
]
