"""ORM models.

Every model lives under this package, and nothing outside ``prama.db`` imports
one: services and API handlers work with domain objects returned by
repositories, so the persistence shape is free to change without rippling.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.db.models.base import (
    Base,
    CreatedAt,
    EvidenceBase,
    ModelMixin,
    TenantScoped,
    Timestamped,
    UlidPrimaryKey,
)
from prama.db.models.evidence import EvRecord, EvRun, EvSample
from prama.db.models.platform import (
    ApiKey,
    AuditEvent,
    LeaseRow,
    Principal,
    PrincipalRole,
    Role,
    SchemaState,
    Setting,
    Tenant,
)
from prama.db.models.semantic import (
    SemAttribute,
    SemAttributeVersion,
    SemDataset,
    SemDatasetVersion,
    SemDomain,
    SemDomainVersion,
)
from prama.db.models.semantic_graph import (
    SemBinding,
    SemBindingVersion,
    SemConcept,
    SemConceptProperty,
    SemConceptPropertyVersion,
    SemConceptVersion,
    SemConnection,
    SemConnectionVersion,
    SemJourney,
    SemJourneyVersion,
    SemRelationship,
    SemRelationshipVersion,
)

__all__ = [
    "ApiKey",
    "AuditEvent",
    "Base",
    "CreatedAt",
    "EvRecord",
    "EvRun",
    "EvSample",
    "EvidenceBase",
    "LeaseRow",
    "ModelMixin",
    "Principal",
    "PrincipalRole",
    "Role",
    "SchemaState",
    "SemAttribute",
    "SemAttributeVersion",
    "SemBinding",
    "SemBindingVersion",
    "SemConcept",
    "SemConceptProperty",
    "SemConceptPropertyVersion",
    "SemConceptVersion",
    "SemConnection",
    "SemConnectionVersion",
    "SemDataset",
    "SemDatasetVersion",
    "SemDomain",
    "SemDomainVersion",
    "SemJourney",
    "SemJourneyVersion",
    "SemRelationship",
    "SemRelationshipVersion",
    "Setting",
    "Tenant",
    "TenantScoped",
    "Timestamped",
    "UlidPrimaryKey",
]
