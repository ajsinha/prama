"""The connector registry.

Connectors are discovered through entry points, so adding one never edits core
code, and each declares a capability matrix the compiler consults rather than
probes. The registry also owns the derived configuration forms, so the UI asks
one question — "what does this connector need?" — of one object.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from prama.connect.capability import CapabilityMatrix
from prama.connect.config_schema import (
    ConnectorConfigSchema,
    FieldPresentation,
    FieldSpec,
)
from prama.connect.spi import Connector, ReadPolicy, SourceKind
from prama.core.errors import RegistryError
from prama.core.log import get_logger
from prama.core.registry import Registry

_log = get_logger(__name__)

ENTRY_POINT_GROUP = "prama.connectors"


class ConnectorRegistry:
    """Every known connector, its capabilities, and its configuration form."""

    def __init__(self) -> None:
        # Connector is abstract by design: the registry holds classes, not
        # instances, and every registered class is concrete.
        self._registry: Registry[Connector] = Registry(
            "connector",
            Connector,  # type: ignore[type-abstract]
            entry_point_group=ENTRY_POINT_GROUP,
        )
        self._matrices: dict[str, CapabilityMatrix] = {}
        self._overlays: dict[str, dict[str, FieldPresentation]] = {}
        self._extra_fields: dict[str, tuple[FieldSpec, ...]] = {}
        self._schemas: dict[str, ConnectorConfigSchema] = {}

    # -- registration ------------------------------------------------------

    def register(
        self,
        connector_class: type[Connector],
        *,
        capabilities: CapabilityMatrix | None = None,
        overlay: dict[str, FieldPresentation] | None = None,
        extra_fields: tuple[FieldSpec, ...] = (),
        replace: bool = False,
    ) -> None:
        self._registry.register(connector_class, replace=replace)
        key = connector_class.manifest().key
        self._matrices[key] = capabilities or CapabilityMatrix()
        self._overlays[key] = overlay or {}
        self._extra_fields[key] = extra_fields
        self._schemas.pop(key, None)  # rebuilt lazily against the new class

    def discover(self) -> int:
        """Load third-party connectors advertised on the entry-point group."""
        return self._registry.discover()

    # -- lookup ------------------------------------------------------------

    def keys(self) -> list[str]:
        return sorted(self._registry.keys())

    def __contains__(self, key: str) -> bool:
        return key in self._registry

    def __iter__(self) -> Iterator[str]:
        """Every registered key. Makes ``for key in registry`` read naturally."""
        return iter(self.keys())

    def __len__(self) -> int:
        return len(self.keys())

    def get(self, key: str) -> type[Connector]:
        return self._registry.get(key)

    def capabilities(self, key: str) -> CapabilityMatrix:
        self._registry.get(key)  # raises with the available keys if unknown
        return self._matrices.get(key, CapabilityMatrix())

    def schema(self, key: str) -> ConnectorConfigSchema:
        """The typed form for this connector, derived from its own code."""
        if key not in self._schemas:
            connector_class = self._registry.get(key)
            self._schemas[key] = ConnectorConfigSchema.build(
                connector_class,
                overlay=self._overlays.get(key, {}),
                extra_fields=self._extra_fields.get(key, ()),
            )
        return self._schemas[key]

    def of_kind(self, kind: SourceKind) -> list[str]:
        return sorted(
            key
            for key in self.keys()
            if getattr(self._registry.get(key), "source_kind", None) is kind
        )

    def create(
        self, key: str, config: dict[str, Any], *, policy: ReadPolicy | None = None
    ) -> Connector:
        """Validate the configuration, then build the connector.

        Validation first, always: a missing field should be a message beside the
        input, not a driver error twenty seconds into a connection attempt.
        """
        connector_class = self._registry.get(key)
        self.schema(key).validate(config)
        return connector_class(config, policy=policy)

    # -- health of the registry itself -------------------------------------

    def audit(self) -> list[str]:
        """Every place a curated overlay and a connector's code disagree.

        Run in CI. A form that has drifted from its connector is the defect this
        whole design exists to prevent, so it fails the build rather than
        appearing as a subtly wrong input six months later.
        """
        findings: list[str] = []
        for key in self.keys():
            try:
                findings.extend(self.schema(key).audit())
            except RegistryError as exc:  # pragma: no cover - defensive
                findings.append(f"{key}: {exc.message}")
        return findings

    def catalogue(self) -> list[dict[str, Any]]:
        """Everything the UI needs to offer a source picker."""
        catalogue = []
        for key in self.keys():
            manifest = self._registry.manifest(key)
            connector_class = self._registry.get(key)
            catalogue.append(
                {
                    "key": key,
                    "display_name": manifest.display_name,
                    "kind": getattr(connector_class, "source_kind", SourceKind.RELATIONAL).value,
                    "description": manifest.description,
                    "capabilities": self.capabilities(key).describe(),
                    "form": self.schema(key).to_form(),
                }
            )
        return catalogue


#: The process-wide registry. Held as an object rather than module functions so
#: a test can build an isolated one, and so a future multi-tenant process could
#: hold more than one.
_default = ConnectorRegistry()


def default_registry() -> ConnectorRegistry:
    return _default
