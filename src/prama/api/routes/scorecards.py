"""Scorecards, for programs: per dataset and for the estate, by dimension, from evidence.

The same cards as the console's scorecard screen (`prama.score.scorecard`):
built from each control's latest record, decomposed by dimension, with coverage
and the controls that could not run beside every number.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from prama.api.deps import ReportReader, Uow
from prama.evidence.service import observation
from prama.score import scorecard

router = APIRouter(prefix="/scorecards", tags=["scorecards"])


@router.get("")
async def scorecards(caller: ReportReader, uow: Uow) -> dict[str, Any]:
    """A card per dataset, the estate's card, and whether the breakdown is real.

    ``observation.state == "no_runs"`` means no score here says anything yet.
    """
    return {
        **await scorecard.scorecards(uow, caller.tenant_id),
        "observation": await observation(uow, caller.tenant_id),
    }


@router.get("/estate")
async def estate(caller: ReportReader, uow: Uow) -> dict[str, Any]:
    """The estate-wide card: every dataset's latest evidence, scored together."""
    cards = await scorecard.scorecards(uow, caller.tenant_id)
    return dict(cards["estate"])


@router.get("/{dataset}")
async def dataset(dataset: str, caller: ReportReader, uow: Uow) -> dict[str, Any]:
    """One dataset's card; not found when no control has evidence for it."""
    return await scorecard.for_dataset(uow, caller.tenant_id, dataset)
