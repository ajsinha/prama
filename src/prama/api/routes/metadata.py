"""A dataset's business context and metadata, and search by meaning, for programs and agents.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from prama.api.deps import Reader, Uow
from prama.semantic.services import metadata as service

router = APIRouter(tags=["metadata"])


@router.get("/metadata/search")
async def search(uow: Uow, caller: Reader, q: str = Query(min_length=1)) -> list[dict[str, Any]]:
    return await service.search(uow, caller.tenant_id, q)


@router.get("/metadata/correlation")
async def correlation(uow: Uow, caller: Reader) -> dict[str, Any]:
    return await service.correlation(uow, caller.tenant_id)


@router.get("/metadata/{dataset}")
async def describe(dataset: str, uow: Uow, caller: Reader) -> dict[str, Any]:
    return await service.describe(uow, caller.tenant_id, dataset)
