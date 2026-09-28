"""Comments on governed objects, and a steward's queue: what is waiting on one person.

Objects are named the way people name them: a dataset by its slug, an
attribute as `dataset.attribute`, a control or an incident by its control id,
a glossary term by its name. `@username` in a comment mentions that person,
and the mention is what puts the thread in their queue.

**The queue** gathers, for one person, everything waiting on them, from the
places it already lives, rather than copying it into a second store that would
drift:

* threads that mention them, and open threads on the datasets they own or steward;
* failing controls on those datasets;
* metadata inconsistencies that touch those datasets;
* curation suggestions for those datasets;
* for an approver: rules and delegate uploads that somebody else proposed.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
import re
from typing import Any

from prama.core.errors import ValidationError

KINDS = ("dataset", "attribute", "control", "term", "incident")
_MENTION = re.compile(r"(?<![\w.])@([A-Za-z0-9_.-]+)")
_UNRESOLVED = ("fail", "error", "skipped", "indeterminate")


async def post(
    uow: Any,
    tenant_id: str,
    *,
    object_kind: str,
    object_ref: str,
    body: str,
    by: str,
    parent_id: str | None = None,
) -> Any:
    """A comment, or a reply. `@username` mentions must name somebody who exists."""
    if not by:
        raise ValidationError("a comment needs a signed-in author", remedy="Sign in to comment.")
    if object_kind == "dataset" and "." in object_ref:
        object_kind = "attribute"  # `dataset.attribute` names an attribute, however it came
    if parent_id is None and object_kind not in KINDS:
        raise ValidationError(f"cannot comment on a {object_kind!r}", remedy=f"One of: {KINDS}.")
    mentioned = []
    for name in sorted(set(_MENTION.findall(body))):
        person = await uow.principals.by_username(tenant_id, name)
        if person is None:
            raise ValidationError(
                f"nobody is called @{name}",
                remedy="Mention a person by their username, or remove the @.",
            )
        mentioned.append(str(person.id))
    row = await uow.comments.post(
        tenant_id,
        object_kind=object_kind,
        object_ref=object_ref.strip(),
        author_id=by,
        body=body,
        mentions=mentioned,
        parent_id=parent_id,
    )
    uow.audit.record(
        tenant_id=tenant_id,
        action="comment.replied" if parent_id else "comment.posted",
        object_kind=row.object_kind,
        object_id=row.object_ref[:26] if row.object_kind != "term" else None,
        actor_id=by,
        detail={"comment": row.id, "mentions": mentioned, "object": row.object_ref},
    )
    return row


async def resolve(uow: Any, tenant_id: str, root_id: str, *, by: str) -> Any:
    row = await uow.comments.resolve(tenant_id, root_id, by=by)
    uow.audit.record(
        tenant_id=tenant_id,
        action="comment.resolved",
        object_kind=row.object_kind,
        actor_id=by,
        detail={"comment": row.id, "object": row.object_ref},
    )
    return row


async def threads(
    uow: Any, tenant_id: str, object_kind: str, object_ref: str
) -> list[dict[str, Any]]:
    """The object's threads, each with its replies, oldest first."""
    rows = await uow.comments.on(tenant_id, object_kind, object_ref)
    roots = [r for r in rows if r.parent_id is None]
    return [
        {"root": root, "replies": [r for r in rows if r.parent_id == root.id]} for root in roots
    ]


async def queue(uow: Any, tenant_id: str, principal_id: str, *, approver: bool) -> dict[str, Any]:
    """Everything waiting on *principal_id*."""
    from prama.semantic.services.metadata import correlation

    mine = [
        v
        for v in await uow.datasets.list_current(tenant_id, limit=5000)
        if principal_id in (v.owner_id, v.steward_id)
    ]
    slugs = {v.slug for v in mine}
    ids = {v.dataset_id for v in mine}

    def on_mine(kind: str, ref: str) -> bool:
        return (kind == "dataset" and ref in slugs) or (
            kind == "attribute" and ref.split(".", 1)[0] in slugs
        )

    mentioning, on_datasets = [], []
    for root in await uow.comments.open_threads(tenant_id):
        replies = await uow.comments.thread(tenant_id, root.id)
        mentions = {m for r in replies for m in json.loads(r.mentions_json)}
        item = {
            "id": root.id,
            "object": f"{root.object_kind} {root.object_ref}",
            "body": root.body,
            "replies": len(replies) - 1,
            "created_at": root.created_at,
        }
        if principal_id in mentions:
            mentioning.append(item)
        elif on_mine(root.object_kind, root.object_ref):
            on_datasets.append(item)
    failing = [
        {
            "control_id": key,
            "dataset": record.dataset,
            "verdict": record.verdict,
            "detail": record.detail,
        }
        for key, record in (await uow.evidence.latest_per_control(tenant_id)).items()
        if record.verdict in _UNRESOLVED and record.dataset in slugs
    ]
    inconsistent = [
        f
        for f in (await correlation(uow, tenant_id))["findings"]
        if any(m.split(".", 1)[0] in slugs for m in f["members"])
    ]
    suggestions = [
        {"id": s.id, "object": s.object_name, "field": s.field, "text": s.suggested}
        for s in await uow.stewards.suggestions(tenant_id)
        if s.object_id in ids
    ]
    approvals: list[dict[str, Any]] = []
    if approver:
        for control in await uow.controls.of_status(tenant_id, "proposed"):
            if control.authored_by != principal_id:
                approvals.append(
                    {
                        "kind": "rule",
                        "id": control.control_id,
                        "what": control.pql.splitlines()[0][:120],
                    }
                )
        for upload in await uow.delegate_uploads.all(tenant_id):
            if upload.state == "proposed" and upload.submitted_by != principal_id:
                approvals.append(
                    {"kind": "delegate", "id": upload.id, "what": f"{upload.name}@{upload.version}"}
                )
    return {
        "datasets": sorted(slugs),
        "mentions": mentioning,
        "threads": on_datasets,
        "failing": failing,
        "inconsistent": inconsistent,
        "suggestions": suggestions,
        "approvals": approvals,
        "total": len(mentioning)
        + len(on_datasets)
        + len(failing)
        + len(inconsistent)
        + len(suggestions)
        + len(approvals),
    }
