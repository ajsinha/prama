"""Data Access Objects — the only database access layer.

Every read and write against Prama's schema is concentrated in this package.
Nothing outside ``prama.db`` issues SQL or touches an ORM session; higher layers
call a DAO through the unit of work and receive domain objects. An architecture
test enforces that by import scanning, so the rule is a property of the build.

    base.py       Dao, TenantScopedDao — scoping and error translation
    platform.py   tenancy, identity, audit, settings
    versioned.py  the bitemporal create / amend / correct / read protocol
    semantic.py   domain, dataset, attribute, concept, relationship, journey,
                  connection, binding

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.db.dao.attestation import AttestationDao
from prama.db.dao.base import Dao, TenantScopedDao
from prama.db.dao.control import ControlDao, RejectionDao
from prama.db.dao.evidence import AnchorDao, EvidenceDao, EvidenceRunDao, SampleDao
from prama.db.dao.fleet import FleetDao
from prama.db.dao.platform import (
    ApiKeyDao,
    AuditDao,
    PrincipalDao,
    RoleDao,
    SettingDao,
    TenantDao,
)
from prama.db.dao.recon import BreakDao
from prama.db.dao.semantic import (
    AttributeDao,
    BindingDao,
    ConceptDao,
    ConceptPropertyDao,
    ConnectionDao,
    DatasetDao,
    DomainDao,
    JourneyDao,
    RelationshipDao,
)
from prama.db.dao.versioned import VersionedDao

__all__ = [
    "AnchorDao",
    "ApiKeyDao",
    "AttestationDao",
    "AttributeDao",
    "AuditDao",
    "BindingDao",
    "BreakDao",
    "ConceptDao",
    "ConceptPropertyDao",
    "ConnectionDao",
    "ControlDao",
    "Dao",
    "DatasetDao",
    "DomainDao",
    "EvidenceDao",
    "EvidenceRunDao",
    "FleetDao",
    "JourneyDao",
    "PrincipalDao",
    "RejectionDao",
    "RelationshipDao",
    "RoleDao",
    "SampleDao",
    "SettingDao",
    "TenantDao",
    "TenantScopedDao",
    "VersionedDao",
]
