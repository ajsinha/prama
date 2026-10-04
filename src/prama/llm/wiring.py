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
from prama.llm.gateway import (
    CallLedger,
    Candidate,
    LlmGateway,
    MemoryLedger,
    ResponseCache,
    Route,
)
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
    pinned: dict[str, int] | None = None,
) -> dict[str, Route]:
    """Every purpose's current route for *tenant_id*, with providers built.

    *pinned* names a version per purpose to use instead of the current one: an
    evaluation run of a version that is not yet current.

    A disabled provider is skipped, not an error: switching one off is how an
    operator takes a model out of service without editing every profile.
    """
    resolver = secrets or default_resolver()
    providers = {p.id: p for p in await uow.llm.providers(tenant_id)}
    routes: dict[str, Route] = {}
    for profile in await uow.llm.profiles(tenant_id):
        wanted = (pinned or {}).get(profile.purpose)
        if wanted is not None:
            version = next((v for v in profile.versions if v.version == wanted), None)
            if version is None:
                continue
        else:
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
    api_key_id: str | None = None,
    offline: bool = False,
    ledger: CallLedger | None = None,
    opener: Any = None,
    cache: ResponseCache | None = None,
    config: Any = None,
) -> tuple[LlmGateway, MemoryLedger]:
    """A gateway over the tenant's profiles, and the ledger to persist after."""
    from prama.llm.budget import guard_for

    memory = ledger if isinstance(ledger, MemoryLedger) else MemoryLedger()
    routes = await load_routes(uow, tenant_id, offline=offline, opener=opener)
    # Every gateway is held to the tenant's budgets, whoever built it.
    guard = await guard_for(
        uow, tenant_id, routes, principal_id=principal_id, api_key_id=api_key_id
    )
    gateway = LlmGateway(
        routes,
        memory,
        tenant_id=tenant_id,
        surface=surface,
        principal_id=principal_id,
        api_key_id=api_key_id,
        cache=cache,
        payloads=_policy(config)[0],
        guard=guard,
    )
    memory.retention_days = _policy(config)[1]
    return gateway, memory


def _policy(config: Any) -> tuple[str, int]:
    """`llm.audit.payloads` (none, redacted, full) and the days a payload is kept."""
    if config is None:
        return "none", 30
    mode = str(config.get("llm.audit.payloads", "none") or "none")
    if mode not in ("none", "redacted", "full"):
        mode = "none"
    return mode, int(config.get("llm.audit.payload_retention_days", 30) or 30)


async def persist(uow: Any, tenant_id: str, ledger: MemoryLedger) -> int:
    """Write what the gateway recorded to the tenant's hash-chained ledger."""
    from datetime import UTC, datetime, timedelta

    from prama.llm.budget import costed

    records = [await costed(uow, record) for record in ledger.records]
    written: int = await uow.llm.append_calls(tenant_id, records)
    ledger.records.clear()
    if ledger.payloads:
        expires = (datetime.now(UTC) + timedelta(days=ledger.retention_days)).isoformat(
            timespec="milliseconds"
        )
        for digest, (asked, answered, mode) in ledger.payloads.items():
            await uow.llm_governance.put_payload(
                tenant_id,
                digest,
                request_json=asked,
                response_json=answered,
                mode=mode,
                expires_at=expires,
            )
        ledger.payloads.clear()
        await uow.llm_governance.expire_payloads(tenant_id)
    return written
