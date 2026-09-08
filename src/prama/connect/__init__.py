"""Connectivity: how Prama reaches a source, and what it may do there.

Every source implements one contract (``spi``), declares what its engine can be
relied upon to do (``capability``), and has a configuration form derived from
its own code rather than hand-maintained (``config_schema``).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.connect.capability import (
    BASELINE_SQL,
    NO_PUSHDOWN,
    CapabilityMatrix,
    PushdownFeature,
)
from prama.connect.config_schema import (
    ConfigSchemaDeriver,
    ConnectorConfigSchema,
    FieldPresentation,
    FieldSpec,
    InputKind,
)
from prama.connect.registry import ConnectorRegistry, default_registry
from prama.connect.spi import (
    ColumnSchema,
    Connector,
    ConnectorError,
    DiscoveredObject,
    HealthReport,
    HealthState,
    ObjectSchema,
    ReadPolicy,
    ReadResult,
    SamplePlan,
    SamplingStrategy,
    Snapshot,
    SnapshotKind,
    SourceKind,
    UnauthorisedError,
    UnreachableError,
)

__all__ = [
    "BASELINE_SQL",
    "NO_PUSHDOWN",
    "CapabilityMatrix",
    "ColumnSchema",
    "ConfigSchemaDeriver",
    "Connector",
    "ConnectorConfigSchema",
    "ConnectorError",
    "ConnectorRegistry",
    "DiscoveredObject",
    "FieldPresentation",
    "FieldSpec",
    "HealthReport",
    "HealthState",
    "InputKind",
    "ObjectSchema",
    "PushdownFeature",
    "ReadPolicy",
    "ReadResult",
    "SamplePlan",
    "SamplingStrategy",
    "Snapshot",
    "SnapshotKind",
    "SourceKind",
    "UnauthorisedError",
    "UnreachableError",
    "default_registry",
]
