"""Comments, threads, and the queue of what waits on a person, for programs and agents.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel

from prama.api.deps import Commenter, Reader, Uow
from prama.core.errors import ForbiddenError, NotFoundError, ValidationError
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


def _person(caller: Any, what: str) -> str:
    if not caller.principal_id:
        raise ValidationError(f"{what} needs a person", remedy="Use a key issued to a person.")
    return str(caller.principal_id)


@router.post("/comments", status_code=201)
async def post_comment(body: CommentIn, uow: Uow, caller: Commenter) -> dict[str, Any]:
    """A comment, or a reply (`parent_id`). An `@username` must name somebody who exists."""
    row = await collaboration.post(
        uow,
        caller.tenant_id,
        object_kind=body.object_kind,
        object_ref=body.object_ref,
        body=body.body,
        by=_person(caller, "a comment"),
        parent_id=body.parent_id,
    )
    return _row(row)


@router.get("/comments")
async def comments(
    object_kind: str, object_ref: str, uow: Uow, caller: Reader
) -> list[dict[str, Any]]:
    return [_row(r) for r in await uow.comments.on(caller.tenant_id, object_kind, object_ref)]


@router.get("/comments/threads")
async def threads(
    object_kind: str, object_ref: str, uow: Uow, caller: Reader
) -> list[dict[str, Any]]:
    """The object's threads, each with its replies, oldest first."""
    return [
        {**_row(t["root"]), "replies": [_row(r) for r in t["replies"]]}
        for t in await collaboration.threads(uow, caller.tenant_id, object_kind, object_ref)
    ]


@router.post("/comments/{root_id}/resolve")
async def resolve(root_id: str, uow: Uow, caller: Commenter) -> dict[str, Any]:
    """Resolve a thread. It leaves everybody's queue; the discussion is kept."""
    row = await collaboration.resolve(
        uow, caller.tenant_id, root_id, by=_person(caller, "resolving a thread")
    )
    return _row(row)


Section = Literal["mentions", "threads", "failing", "inconsistent", "suggestions", "approvals"]


@router.get("/queue")
async def my_queue(
    uow: Uow,
    caller: Reader,
    person: str = "",
    approver: bool | None = None,
    section: Section | None = None,
) -> dict[str, Any]:
    """Mentions, threads on your datasets, failures, inconsistencies, suggestions and
    approvals waiting on you.

    *person* reads somebody else's queue, which needs `admin`. *approver*
    includes or leaves out approvals; it defaults to whether you may approve,
    and asking for them without `control:approve` is refused. *section* keeps
    one list.
    """
    whom = _person(caller, "a queue")
    if person:
        if not caller.allows("admin"):
            raise ForbiddenError(
                "reading somebody else's queue needs the 'admin' scope",
                remedy="Read your own queue, or use an administrator's key.",
            )
        found = await uow.principals.by_username(caller.tenant_id, person)
        if found is None:
            raise NotFoundError(f"nobody is called {person}", remedy="Pass an existing username.")
        whom = str(found.id)
    may_approve = caller.allows("control:approve")
    if approver and not may_approve:
        raise ForbiddenError(
            "approvals are listed only for a credential that may approve",
            remedy="Leave approver unset, or use a key holding control:approve.",
        )
    waiting = await collaboration.queue(
        uow, caller.tenant_id, whom, approver=may_approve if approver is None else approver
    )
    if section is not None:
        return {"section": section, "items": waiting[section], "total": len(waiting[section])}
    return waiting
