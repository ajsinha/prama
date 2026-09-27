"""Accepting or rejecting a curation suggestion. No model is involved here.

A suggestion is a model's draft of a missing description. Accepting it amends
the declaration as the person who accepted it: they are the author of record,
and the model is named only in the amendment's reason. A suggestion whose
declaration has since gained a description is stale, not applied, because the
draft was written for a gap that is no longer there.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from prama.core.errors import NotFoundError, ValidationError


async def undescribed(uow: Any, tenant_id: str, *, limit: int = 10) -> list[Any]:
    """Current datasets with no description, the gap a draft fills."""
    rows = await uow.datasets.list_current(tenant_id, limit=500)
    return [row for row in rows if not (row.description or "").strip()][:limit]


async def decide(
    uow: Any, tenant_id: str, suggestion_id: str, *, accept: bool, by: str | None
) -> Any:
    """Record a person's decision; an acceptance amends the declaration as *by*."""
    from prama.semantic.services.datasets import DatasetService

    if not by:
        raise ValidationError(
            "a curation decision needs a signed-in person",
            remedy="Sign in: an accepted description is attributed to whoever accepted it.",
        )
    row = await uow.stewards.suggestion(tenant_id, suggestion_id)
    if row is None or row.state != "open":
        raise NotFoundError(
            "no open suggestion with that id", remedy="Open suggestions are on the Agents page."
        )
    state = "rejected"
    if accept:
        if row.object_kind != "dataset" or row.field != "description":
            raise ValidationError(
                f"cannot apply a {row.object_kind} {row.field} suggestion",
                remedy="Only dataset descriptions are drafted today.",
            )
        current = await uow.datasets.current(row.object_id, tenant_id=tenant_id)
        if current is None or (current.description or "").strip():
            state = "stale"
        else:
            await DatasetService(uow).amend(
                tenant_id=tenant_id,
                dataset_id=row.object_id,
                reason=f"description drafted by {row.model or 'a model'}, accepted by a person",
                authored_by=by,
                description=row.suggested,
            )
            state = "accepted"
    row.state = state
    row.decided_by = by
    row.decided_at = datetime.now(UTC).isoformat(timespec="milliseconds")
    await uow.flush()
    return row
