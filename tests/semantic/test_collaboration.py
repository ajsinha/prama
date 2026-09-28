"""Comments with mentions, threads that reopen, and the queue of what waits on a person.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

import pytest

from prama.core.errors import ValidationError
from prama.db import Database
from prama.semantic.services import collaboration
from prama.semantic.services.datasets import DatasetService


async def _people(uow: Any, tenant_id: str) -> tuple[str, str]:
    ada = uow.principals.create(tenant_id=tenant_id, username="ada", display_name="Ada")
    bo = uow.principals.create(tenant_id=tenant_id, username="bo", display_name="Bo")
    await uow.flush()
    return str(ada.id), str(bo.id)


async def test_a_mention_reaches_the_queue_and_resolving_clears_it(
    started_database: Database, tenant_id: str
) -> None:
    async with started_database.unit_of_work() as uow:
        ada, bo = await _people(uow, tenant_id)
        root = await collaboration.post(
            uow,
            tenant_id,
            object_kind="dataset",
            object_ref="trades.ccy",
            body="@bo is lower case allowed here?",
            by=ada,
        )
        assert root.object_kind == "attribute"  # dataset.attribute names an attribute
        waiting = await collaboration.queue(uow, tenant_id, bo, approver=False)
        assert [m["id"] for m in waiting["mentions"]] == [root.id]
        await collaboration.resolve(uow, tenant_id, root.id, by=bo)
        assert (await collaboration.queue(uow, tenant_id, bo, approver=False))["mentions"] == []
        await collaboration.post(
            uow,
            tenant_id,
            object_kind="attribute",
            object_ref="",
            body="Still happening.",
            by=ada,
            parent_id=root.id,
        )
        reopened = await collaboration.queue(uow, tenant_id, bo, approver=False)
        audit = [e.action for e in await uow.audit.recent(tenant_id)]
    assert len(reopened["mentions"]) == 1  # a reply reopens a resolved thread
    assert {"comment.posted", "comment.resolved", "comment.replied"} <= set(audit)


async def test_an_unknown_mention_is_refused(started_database: Database, tenant_id: str) -> None:
    async with started_database.unit_of_work() as uow:
        ada, _ = await _people(uow, tenant_id)
        with pytest.raises(ValidationError, match="nobody is called @carol"):
            await collaboration.post(
                uow, tenant_id, object_kind="dataset", object_ref="t", body="@carol look", by=ada
            )


async def test_the_queue_gathers_what_waits_on_an_owner_and_an_approver(
    started_database: Database, tenant_id: str
) -> None:
    from prama.evidence.record import EvidenceRecord, SnapshotRef

    async with started_database.unit_of_work() as uow:
        ada, bo = await _people(uow, tenant_id)
        await DatasetService(uow).declare(
            tenant_id=tenant_id, name="Trades", owner_id=ada, criticality=4
        )
        await collaboration.post(
            uow,
            tenant_id,
            object_kind="dataset",
            object_ref="trades",
            body="Why so many rows today?",
            by=bo,
        )
        await uow.evidence.append(
            EvidenceRecord(
                plan_id="ir:sha256:" + "e" * 64,
                control_id="c1",
                dataset="trades",
                binding="trades",
                engine="duckdb",
                snapshot=SnapshotRef(kind="wall_clock", identifier="t0"),
                verdict="fail",
                metrics={"scanned_rows": 5.0, "violating_rows": 1.0},
                started_at="2026-09-28T06:00:00Z",
                finished_at="2026-09-28T06:00:01Z",
                tenant_id=tenant_id,
            ),
            tenant_id=tenant_id,
        )
        await uow.controls.declare(
            tenant_id=tenant_id,
            identity="x",
            pql="CHECK trades.a IS NOT NULL",
            status="proposed",
            authored_by=bo,
        )
        owner = await collaboration.queue(uow, tenant_id, ada, approver=True)
        author = await collaboration.queue(uow, tenant_id, bo, approver=True)
    assert owner["datasets"] == ["trades"]
    assert len(owner["threads"]) == 1 and owner["failing"][0]["control_id"] == "c1"
    assert [a["kind"] for a in owner["approvals"]] == ["rule"]
    assert author["approvals"] == []  # nobody approves their own rule


async def test_the_queue_page_and_the_redirect_guard(ui: Any) -> None:
    assert (await ui.get("/queue")).status_code == 200
    reply = await ui.post(
        "/comments",
        data={
            "object_kind": "dataset",
            "object_ref": "t",
            "body": "x",
            "back": "https://evil.example",
        },
    )
    assert reply.headers["location"] == "/queue"
