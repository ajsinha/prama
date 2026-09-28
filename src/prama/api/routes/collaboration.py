"""Comments and the caller's queue, for programs and agents.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from prama.api.deps import Commenter, Reader, Uow
from prama.core.errors import ValidationError
from prama.security.scopes import permits
from prama.semantic.services import collaboration

router = APIRouter(tags=["collaboration"])


class CommentIn(BaseModel):
    object_kind: str = "dataset"
    object_ref: str = ""
    body: str
    parent_id: str | None = None


def _row(r: Any) -> dict[str, Any]:
    return {
        "id": r.id,
        "object_kind": r.object_kind,
        "object_ref": r.object_ref,
        "parent_id": r.parent_id,
        "author_id": r.author_id,
        "body": r.body,
        "state": r.state,
        "created_at": r.created_at,
    }


@router.post("/comments", status_code=201)
async def post_comment(body: CommentIn, uow: Uow, caller: Commenter) -> dict[str, Any]:
    if not caller.principal_id:
        raise ValidationError("a comment needs a person", remedy="Use a key issued to a person.")
    row = await collaboration.post(
        uow,
        caller.tenant_id,
        object_kind=body.object_kind,
        object_ref=body.object_ref,
        body=body.body,
        by=caller.principal_id,
        parent_id=body.parent_id,
    )
    return _row(row)


@router.get("/comments")
async def comments(
    object_kind: str, object_ref: str, uow: Uow, caller: Reader
) -> list[dict[str, Any]]:
    return [_row(r) for r in await uow.comments.on(caller.tenant_id, object_kind, object_ref)]


@router.get("/queue")
async def my_queue(uow: Uow, caller: Reader) -> dict[str, Any]:
    if not caller.principal_id:
        raise ValidationError("a queue belongs to a person", remedy="Use a key issued to a person.")
    return await collaboration.queue(
        uow,
        caller.tenant_id,
        caller.principal_id,
        approver=permits(caller.scopes, "control:approve"),
    )
