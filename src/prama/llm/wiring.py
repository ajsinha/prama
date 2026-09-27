"""From stored profiles to a working gateway, and back to the ledger.

The two steps every surface (CLI, console, API) needs around a gateway call:
load the tenant's profiles and build their providers, then persist what the
gateway recorded. Takes the unit of work as an opaque object, so `prama.llm`
still imports nothing from `prama.db`.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama.llm import kinds
from prama.llm.gateway import CallLedger, Candidate, LlmGateway, MemoryLedger, Route
from prama.llm.spi import Hosting
from prama.secrets.resolver import SecretResolver, default_resolver


def spec_of(row: Any) -> kinds.ProviderSpec:
    return kinds.ProviderSpec(
        name=row.name,
        kind=row.kind,
        hosting=row.hosting,
        endpoint=row.endpoint,
        dialect=row.dialect,
        region=row.region,
        settings=dict(row.settings_json or {}),
    )


async def load_routes(
    uow: Any,
    tenant_id: str,
    *,
    offline: bool = False,
    secrets: SecretResolver | None = None,
    opener: Any = None,
) -> dict[str, Route]:
    """Every purpose's current route for *tenant_id*, with providers built.

    A disabled provider is skipped, not an error: switching one off is how an
    operator takes a model out of service without editing every profile.
    """
    resolver = secrets or default_resolver()
    providers = {p.id: p for p in await uow.llm.providers(tenant_id)}
    routes: dict[str, Route] = {}
    for profile in await uow.llm.profiles(tenant_id):
        current = await uow.llm.current(tenant_id, profile.purpose)
        if current is None:
            continue
        _, version = current
        candidates = []
        for step in version.routes:
            row = providers.get(step.provider_id)
            if row is None or not row.enabled:
                continue
            credential = resolver.resolve_optional(row.credential_ref)
            provider = kinds.build(
                spec_of(row),
                model=step.model,
                credential=credential,
                offline=offline,
                opener=opener,
            )
            candidates.append(
                Candidate(provider, row.id, row.name, row.kind, Hosting(row.hosting), step.model)
            )
        routes[profile.purpose] = Route(
            purpose=profile.purpose,
            candidates=tuple(candidates),
            profile_id=profile.id,
            version=version.version,
            max_attempts=version.max_attempts,
            fallback_across_hosting=version.fallback_across_hosting,
        )
    return routes


async def gateway_for(
    uow: Any,
    tenant_id: str,
    *,
    surface: str,
    principal_id: str | None = None,
    offline: bool = False,
    ledger: CallLedger | None = None,
    opener: Any = None,
) -> tuple[LlmGateway, MemoryLedger]:
    """A gateway over the tenant's profiles, and the ledger to persist after."""
    memory = ledger if isinstance(ledger, MemoryLedger) else MemoryLedger()
    routes = await load_routes(uow, tenant_id, offline=offline, opener=opener)
    gateway = LlmGateway(
        routes, memory, tenant_id=tenant_id, surface=surface, principal_id=principal_id
    )
    return gateway, memory


async def persist(uow: Any, tenant_id: str, ledger: MemoryLedger) -> int:
    """Write what the gateway recorded to the tenant's hash-chained ledger."""
    written: int = await uow.llm.append_calls(tenant_id, ledger.records)
    ledger.records.clear()
    return written
