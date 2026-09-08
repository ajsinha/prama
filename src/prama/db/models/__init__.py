"""ORM models.

Every model lives under this package, and nothing outside ``prama.db`` imports
one: services and API handlers work with domain objects returned by
repositories, so the persistence shape is free to change without rippling.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.db.models.base import Base, CreatedAt, TenantScoped, Timestamped, UlidPrimaryKey
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

__all__ = [
    "ApiKey",
    "AuditEvent",
    "Base",
    "CreatedAt",
    "LeaseRow",
    "Principal",
    "PrincipalRole",
    "Role",
    "SchemaState",
    "Setting",
    "Tenant",
    "TenantScoped",
    "Timestamped",
    "UlidPrimaryKey",
]
