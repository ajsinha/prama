"""The two ways code arrives, each ending in `service.analyse`.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from prama.codeintake import archive, git
from prama.codeintake.service import analyse
from prama.core.ids import new_ulid


async def _read(
    uow: Any,
    config: Any,
    tenant_id: str,
    source: Any,
    snapshot: Any,
    *,
    dialect: str,
    by: str | None,
) -> Any:
    """Analyse, with the model pass when the estate has a `lineage` profile."""
    from prama.codeintake.model_lineage import PURPOSE
    from prama.llm.wiring import gateway_for, persist

    model = ledger = None
    if await uow.llm.current(tenant_id, PURPOSE) is not None:
        model, ledger = await gateway_for(
            uow,
            tenant_id,
            surface="codeintake",
            principal_id=by,
            offline=config.get_bool("llm.offline", False),
            config=config,
        )
    try:
        return await analyse(
            uow,
            tenant_id,
            source,
            snapshot,
            dialect=dialect,
            timeout=float(config.get_int("codeintake.timeout", 300)),
            model=model,
        )
    finally:
        if ledger is not None:
            await persist(uow, tenant_id, ledger)


def _quarantine(config: Any, name: str) -> Path:
    base = Path(config.get_str("codeintake.workdir", "data/code"))
    return base / f"{name}-{new_ulid()}"


async def receive_zip(
    uow: Any,
    config: Any,
    tenant_id: str,
    name: str,
    path: Path,
    *,
    dialect: str = "ansi",
    by: str | None = None,
) -> Any:
    source = await uow.code.ensure_source(tenant_id, name, kind="zip", by=by)
    snapshot = archive.extract(path, _quarantine(config, name))
    return await _read(uow, config, tenant_id, source, snapshot, dialect=dialect, by=by)


async def receive_git(
    uow: Any,
    config: Any,
    tenant_id: str,
    name: str,
    url: str,
    ref: str,
    *,
    credential_ref: str | None = None,
    dialect: str = "ansi",
    by: str | None = None,
) -> Any:
    import asyncio

    from prama.secrets.resolver import default_resolver

    allowed = config.get("codeintake.git.allowed_hosts", []) or []
    git.check_location(url, allowed_hosts=allowed)  # refuse before storing anything
    source = await uow.code.ensure_source(
        tenant_id, name, kind="git", url=url, ref=ref, secret_ref=credential_ref, by=by
    )
    token = default_resolver().resolve_optional(credential_ref) if credential_ref else None
    snapshot = await asyncio.to_thread(
        git.fetch,
        url,
        ref,
        _quarantine(config, name),
        token=token,
        allowed_hosts=allowed,
        timeout=float(config.get_int("codeintake.timeout", 300)),
    )
    return await _read(uow, config, tenant_id, source, snapshot, dialect=dialect, by=by)
