"""Dataset usage from warehouse query history: import it, read it, and rank by it.

A priority signal and nothing more. It orders a steward's list; it never feeds
a quality score, because a popular dataset is not a better one.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, File, Query, UploadFile

from prama.api.deps import Reader, ReportReader, Uow, Writer
from prama.api.uploaded_text import text_of
from prama.core.errors import NotFoundError
from prama.lineage import usage
from prama.semantic.services.priorities import priorities as rank

router = APIRouter(tags=["usage"])


def _query_for(warehouse: str) -> str:
    try:
        return usage.QUERIES[warehouse]
    except KeyError:
        raise NotFoundError(
            f"no usage reader for {warehouse!r}",
            remedy=f"One of: {', '.join(sorted(usage.QUERIES))}.",
            context={"warehouse": warehouse},
        ) from None


@router.get("/usage/export-query/{warehouse}")
async def export_query(warehouse: str, caller: Reader) -> dict[str, Any]:
    """The query to run in the warehouse; its result is what `import` reads."""
    return {"warehouse": warehouse, "query": _query_for(warehouse)}


@router.post("/usage/import/{warehouse}")
async def import_history(
    warehouse: str, caller: Writer, uow: Uow, history: Annotated[UploadFile, File()]
) -> dict[str, Any]:
    """Read a query-history export into daily usage. Re-importing a day replaces it."""
    _query_for(warehouse)
    name, text = await text_of(history, "history.json")
    rows = usage.rows_from_text(text, name=name)
    days = await usage.ingest(uow, caller.tenant_id, warehouse, rows)
    return {"warehouse": warehouse, "rows": len(rows), "dataset_days": days}


@router.get("/usage/daily")
async def daily(
    caller: Reader,
    uow: Uow,
    days: int = Query(30, ge=1, le=3660),
    dataset: str = Query(""),
) -> dict[str, Any]:
    """Queries and readers per dataset, day and source."""
    return await usage.daily(uow, caller.tenant_id, days=days, dataset=dataset)


@router.get("/usage/coaccess")
async def coaccess(
    caller: Reader, uow: Uow, days: int = Query(30, ge=1, le=3660)
) -> dict[str, Any]:
    """Datasets read together by the same query, busiest pair first."""
    return await usage.coaccess(uow, caller.tenant_id, days=days)


@router.get("/usage/priorities")
async def priorities(
    caller: ReportReader, uow: Uow, days: int = Query(30, ge=1, le=3660)
) -> dict[str, Any]:
    """Most used, least controlled first. Never an input to any score."""
    return await rank(uow, caller.tenant_id, days=days)
