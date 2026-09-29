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


async def review_zips(
    config: Any,
    base: Path,
    head: Path,
    *,
    dialect: str = "ansi",
    live: Any = (),
    base_label: str = "base",
    head_label: str = "head",
) -> Any:
    """`review.review_trees` over two received archives, extracted as intake extracts."""
    import asyncio
    import shutil

    from prama.codeintake.review import review_trees

    roots = [_quarantine(config, "review-base"), _quarantine(config, "review-head")]
    try:
        base_root = archive.extract(base, roots[0]).root
        head_root = archive.extract(head, roots[1]).root
        return await asyncio.to_thread(
            review_trees,
            base_root,
            head_root,
            base_label,
            head_label,
            dialect=dialect,
            live=live,
            timeout=float(config.get_int("codeintake.timeout", 300)),
        )
    finally:
        for root in roots:
            shutil.rmtree(root, ignore_errors=True)


async def review_refs(
    config: Any,
    url: str,
    base: str,
    head: str,
    *,
    credential_ref: str | None = None,
    dialect: str = "ansi",
    live: Any = (),
) -> Any:
    """`review.review_trees` over two refs fetched from a repository, location-checked first."""
    import asyncio
    import shutil

    from prama.codeintake.review import review_trees
    from prama.secrets.resolver import default_resolver

    allowed = config.get("codeintake.git.allowed_hosts", []) or []
    git.check_location(url, allowed_hosts=allowed)  # refuse before fetching anything
    token = default_resolver().resolve_optional(credential_ref) if credential_ref else None
    timeout = float(config.get_int("codeintake.timeout", 300))
    roots = [_quarantine(config, "review-base"), _quarantine(config, "review-head")]
    try:
        trees = []
        for ref, root in zip((base, head), roots, strict=True):
            snapshot = await asyncio.to_thread(
                git.fetch, url, ref, root, token=token, allowed_hosts=allowed, timeout=timeout
            )
            trees.append(snapshot.root)
        return await asyncio.to_thread(
            review_trees,
            trees[0],
            trees[1],
            base,
            head,
            dialect=dialect,
            live=live,
            timeout=timeout,
        )
    finally:
        for root in roots:
            shutil.rmtree(root, ignore_errors=True)
