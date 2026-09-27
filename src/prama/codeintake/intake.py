"""The two ways code arrives, each ending in `service.analyse`.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from prama.codeintake import archive, git
from prama.codeintake.service import analyse
from prama.core.ids import new_ulid


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
    return await analyse(
        uow,
        tenant_id,
        source,
        snapshot,
        dialect=dialect,
        timeout=float(config.get_int("codeintake.timeout", 300)),
    )


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
    return await analyse(
        uow,
        tenant_id,
        source,
        snapshot,
        dialect=dialect,
        timeout=float(config.get_int("codeintake.timeout", 300)),
    )
