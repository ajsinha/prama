"""Schema handling: load the authoritative file, apply it, verify against it.

There are no migrations in Prama. These three operations are the whole
lifecycle.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.db.schema.bootstrap import BootstrapResult, SchemaBootstrapper
from prama.db.schema.loader import ColumnSpec, SchemaFile, SchemaLoader, TableSpec
from prama.db.schema.verifier import (
    Drift,
    DriftKind,
    SchemaVerifier,
    VerificationReport,
)

__all__ = [
    "BootstrapResult",
    "ColumnSpec",
    "Drift",
    "DriftKind",
    "SchemaBootstrapper",
    "SchemaFile",
    "SchemaLoader",
    "SchemaVerifier",
    "TableSpec",
    "VerificationReport",
]
