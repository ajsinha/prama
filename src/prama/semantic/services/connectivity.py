"""The bridge between a declared connection and a live connector.

A stored ``sem_connection`` is a *declaration*: what a data architect said the
route to a source is. A ``Connector`` is the live thing. This service turns one
into the other, and it lives here rather than in ``prama.connect`` because a
connector may never reach Prama's own store — if it could, a bug in a
third-party connector would share a blast radius with the evidence ledger.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from prama.connect import (
    Connector,
    ConnectorRegistry,
    DiscoveredObject,
    HealthState,
    ReadPolicy,
    SamplePlan,
    SamplingStrategy,
    default_registry,
)
from prama.core.errors import NotFoundError, ValidationError
from prama.db.session import UnitOfWork
from prama.profile import DatasetProfile, Profiler, suggest_sample_plan
from prama.semantic.policy import ApprovalPolicy
from prama.semantic.services.base import SemanticService


def read_policy_from(declared: dict[str, Any]) -> ReadPolicy:
    """Build the enforced policy from what the architect declared.

    The declaration is the promise shown to a source owner; this is the object
    that keeps it. They are separate so the promise can be reviewed as data.
    """
    return ReadPolicy(
        allowed_paths=tuple(declared.get("allowed_paths", ())),
        max_bytes_scanned=declared.get("max_bytes_scanned"),
        max_rows_read=declared.get("max_rows_read"),
        permitted_hours=tuple(declared.get("permitted_hours", ())),
        default_sampling=SamplingStrategy(declared.get("default_sampling", "full")),
        retain_failing_samples=bool(declared.get("retain_failing_samples", False)),
        max_concurrency=int(declared.get("max_concurrency", 4)),
        load_ceiling=float(declared.get("load_ceiling", 0.05)),
    )


@dataclasses.dataclass(frozen=True, slots=True)
class ProfileRun:
    """One profiling pass, and what it cost."""

    profile: DatasetProfile
    connection_id: str
    dataset_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "connection_id": self.connection_id,
            "dataset_id": self.dataset_id,
            **self.profile.to_dict(),
        }


class ConnectivityService(SemanticService):
    """Test, discover and profile through a declared connection."""

    def __init__(
        self,
        uow: UnitOfWork,
        *,
        policy: ApprovalPolicy | None = None,
        registry: ConnectorRegistry | None = None,
        profiler: Profiler | None = None,
    ) -> None:
        super().__init__(uow, policy=policy)
        self._registry = registry or default_registry()
        self._profiler = profiler or Profiler()

    async def connector_for(self, connection_id: str) -> Connector:
        """Build a live connector from a stored declaration.

        Secrets are resolved here, from the vault reference, and never from the
        stored configuration — which is why the configuration can safely be
        exported to Git and shown in the UI.
        """
        declared = await self._uow.connections.current(connection_id)
        if declared is None:
            raise NotFoundError(
                f"connection {connection_id!r} does not exist",
                remedy="Configure the connection before using it.",
                context={"connection_id": connection_id},
            )
        if declared.source_type not in self._registry:
            raise ValidationError(
                f"no connector is installed for source type {declared.source_type!r}",
                remedy=(
                    f"Installed: {', '.join(self._registry.keys()) or '(none)'}. "
                    f"Install the package providing it, or correct the source type."
                ),
                context={"source_type": declared.source_type},
            )
        config = dict(declared.config_json or {})
        config.update(self._resolve_credential(declared.credential_ref))
        return self._registry.create(
            declared.source_type,
            config,
            policy=read_policy_from(declared.read_policy_json or {}),
        )

    def _resolve_credential(self, reference: str | None) -> dict[str, Any]:
        """Fetch a secret from the vault named by the reference.

        Wave 2's stub: no vault is wired yet, so a reference resolves to nothing
        and connectors that need one will fail their health check with a clear
        message. That is the correct behaviour for a missing secret, and it is
        better than a silent empty password producing a confusing driver error.
        """
        _ = reference
        return {}

    # -- operations --------------------------------------------------------

    async def test(self, connection_id: str) -> dict[str, Any]:
        """Check reachability and record the outcome against the declaration."""
        from prama.semantic.services.graph import ConnectionService

        connector = await self.connector_for(connection_id)
        async with connector:
            report = await connector.health()
        await ConnectionService(self._uow, policy=self._policy).record_health(
            tenant_id=await self._tenant_of(connection_id),
            connection_id=connection_id,
            state=report.state.value,
            detail=report.detail,
            checked_at=report.checked_at,
        )
        return {
            "state": report.state.value,
            "usable": report.is_usable,
            "detail": report.detail,
            # The distinction that decides what the reader does next: an access
            # request, or a network change.
            "needs_access_request": report.needs_access_request,
            "missing_permissions": list(report.missing_permissions),
            "latency_ms": report.latency_ms,
        }

    async def discover(
        self, connection_id: str, path: tuple[str, ...] = (), *, limit: int = 200
    ) -> list[DiscoveredObject]:
        """What this source holds, ranked for a business reader."""
        connector = await self.connector_for(connection_id)
        async with connector:
            report = await connector.health()
            if report.state is HealthState.UNAUTHORISED:
                from prama.connect import UnauthorisedError

                raise UnauthorisedError(
                    report.detail or "this connection is not permitted to read the source",
                    remedy=(
                        "Request access for the credential this connection uses; the "
                        "source is reachable, so this is not a network problem."
                    ),
                    context={"connection_id": connection_id},
                )
            return (await connector.discover(path))[:limit]

    async def profile(
        self,
        connection_id: str,
        path: tuple[str, ...],
        *,
        dataset_id: str | None = None,
        plan: SamplePlan | None = None,
    ) -> ProfileRun:
        """Read an object and profile it in one pass."""
        connector = await self.connector_for(connection_id)
        async with connector:
            if plan is None:
                discovered = await connector.discover(path)
                estimate = discovered[0].estimated_rows if discovered else None
                plan = suggest_sample_plan(estimate)
            profile = await self._profiler.profile(connector, path, plan=plan)
        return ProfileRun(profile=profile, connection_id=connection_id, dataset_id=dataset_id)

    async def profile_source(self, connection_id: str, *, limit: int = 25) -> list[ProfileRun]:
        """Profile everything discoverable, largest first.

        The unattended sweep behind the Wave 3 gate: point Prama at a source and
        come back to an inventory, with nobody having declared anything.
        """
        connector = await self.connector_for(connection_id)
        async with connector:
            profiles = await self._profiler.profile_source(connector, limit=limit)
        return [ProfileRun(profile=profile, connection_id=connection_id) for profile in profiles]

    async def suggest_bindings(
        self, tenant_id: str, connection_id: str, *, limit: int = 200
    ) -> list[dict[str, Any]]:
        """Match declared-but-unbound datasets to objects this source holds.

        Name similarity only, and deliberately so: a suggestion a steward can
        check in a second is worth more than a clever one they have to trust.
        Content fingerprinting arrives when there is a profile to fingerprint.
        """
        unbound = await self._uow.datasets.unbound(tenant_id)
        if not unbound:
            return []
        objects = await self.discover(connection_id, limit=limit)
        suggestions = []
        for dataset in unbound:
            scored = [(self._similarity(dataset.slug, obj.qualified_name), obj) for obj in objects]
            scored.sort(key=lambda pair: -pair[0])
            best_score, best = scored[0] if scored else (0.0, None)
            if best is not None and best_score >= 0.55:
                suggestions.append(
                    {
                        "dataset_id": dataset.dataset_id,
                        "dataset_name": dataset.name,
                        "path": list(best.path),
                        "confidence": round(best_score, 3),
                        "evidence": {
                            "method": "name_similarity",
                            "compared": [dataset.slug, best.qualified_name],
                        },
                    }
                )
        return suggestions

    @staticmethod
    def _similarity(left: str, right: str) -> float:
        """Token overlap, normalised. Simple, explainable, good enough to rank."""
        import re

        def tokens(value: str) -> set[str]:
            return {t for t in re.split(r"[^a-z0-9]+", value.lower()) if t}

        a, b = tokens(left), tokens(right)
        if not a or not b:
            return 0.0
        return len(a & b) / len(a | b)

    async def _tenant_of(self, connection_id: str) -> str:
        entity = await self._uow.connections.get(connection_id)
        if entity is None:
            raise NotFoundError(
                f"connection {connection_id!r} does not exist",
                remedy="Configure the connection before using it.",
                context={"connection_id": connection_id},
            )
        return str(entity.tenant_id)
