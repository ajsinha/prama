"""Reconciliation through the SDK: what a run recorded, the break workbench, and the certificate.

The run itself is made with `ControlRun` directly — running a control is the
runs API's business, and this area deliberately adds no second way to do it.
Everything after the run goes through the SDK.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from tests.sdk.conftest import PASSWORD

import prama.sdk as prama
from prama.db import Database
from prama.execute import ControlRun
from prama.sdk import AsyncClient
from prama.security.accounts import grant_roles

SOURCE = (
    "RECONCILE positions AGAINST ledger ON (account, desk = book) "
    "COMPARING amount = balance WITHIN 1.00 EUR SEVERITY critical"
)
DEFINITION = "positions against ledger"
LEFT = [
    {"account": "A1", "desk": "EQ", "amount": 100.00},
    {"account": "A2", "desk": "EQ", "amount": 250.00},
    {"account": "A3", "desk": "FX", "amount": 75.00},
]
RIGHT = [
    {"account": "A1", "book": "EQ", "balance": 100.40},  # within 1.00: agrees
    {"account": "A2", "book": "EQ", "balance": 260.00},  # a genuine value break
]  # A3 is missing from the ledger


async def _run(database: Database, tenant_id: str, right: list[dict[str, Any]]) -> None:
    def execute(sql: str) -> list[dict[str, Any]]:
        return LEFT if '"positions"' in sql else right

    async with database.unit_of_work() as uow:
        await ControlRun(uow, tenant_id, execute=execute, engine="duckdb").execute_all()


@pytest.fixture
async def reconciled(started_database: Database, tenant_id: str) -> str:
    """An active RECONCILE control, run once over data with two breaks. Returns its id."""
    async with started_database.unit_of_work() as uow:
        control, _ = await uow.controls.declare(
            tenant_id=tenant_id, identity="positions-ledger", pql=SOURCE
        )
        await uow.controls.activate(str(control.id), tenant_id=tenant_id, approved_by="bo")
    await _run(started_database, tenant_id, RIGHT)
    return str(control.id)


async def _signed_in_as(
    client: AsyncClient, database: Database, tenant_id: str, username: str, role: str
) -> AsyncClient:
    async with database.unit_of_work() as uow:
        principal = uow.principals.create(
            tenant_id=tenant_id, username=username, display_name=username.title()
        )
        uow.principals.set_password(principal, PASSWORD)
        await uow.flush()
        await grant_roles(uow, tenant_id, principal, [role])
    anonymous = AsyncClient(app=client._app)
    issued = await anonymous.auth.token(username, PASSWORD, tenant="acme-bank")
    await anonymous.close()
    return anonymous.as_key(issued["api_key"])


def _by_key(workbench: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["key"]: row for row in workbench["rows"]}


async def test_the_list_reads_what_the_run_recorded(client: AsyncClient, reconciled: str) -> None:
    listed = await client.reconciliation.list()
    (item,) = listed["reconciliations"]
    assert item["control_id"] == reconciled and item["definition"] == DEFINITION
    assert item["latest"]["verdict"] == "fail"
    assert item["latest"]["breaks_needing_a_person"] == 2
    # 4 of 5 rows matched (A1 and A2 on both sides; A3 on the left only).
    assert item["latest"]["match_rate"] == pytest.approx(4 / 5)
    assert item["breaks"] == {"open": 2}
    assert listed["queues"] == [DEFINITION] and listed["unowned_queues"] == []

    one = await client.reconciliation.get(reconciled, history=5)
    assert one["latest"]["verdict"] == "fail" and len(one["history"]) == 1
    with pytest.raises(prama.NotFoundError):
        await client.reconciliation.get("01NOSUCHCONTROL0000000000")


async def test_the_workbench_puts_the_genuine_break_first_and_explains_both(
    client: AsyncClient, reconciled: str
) -> None:
    bench = await client.breaks.workbench(DEFINITION)
    keys = [row["key"] for row in bench["rows"]]
    assert len(keys) == 2
    genuine, missing = bench["rows"]
    assert genuine["kind"] == "genuine" and Decimal(genuine["difference"]) == 10
    assert missing["kind"] == "missing" and missing["is_one_sided"]
    # The deterministic explanation is on every break, before anybody writes one.
    assert genuine["because"] and missing["because"]
    assert bench["by_state"] == {"open": 2} and bench["cleared_count"] == 0
    assert (await client.breaks.get(genuine["id"]))["key"] == genuine["key"]


async def test_a_break_is_assigned_explained_and_accepted_and_stays_visible(
    client: AsyncClient, reconciled: str
) -> None:
    genuine = (await client.breaks.workbench(DEFINITION))["rows"][0]
    assigned = await client.breaks.assign(genuine["id"], "ops-eq")
    assert assigned["state"] == "assigned" and assigned["owner"] == "ops-eq"
    explained = await client.breaks.explain(genuine["id"], "late booking adjustment on A2")
    assert explained["state"] == "explained"

    # The counterfactual: an acceptance with no reason is refused.
    with pytest.raises(prama.ValidationError):
        await client.breaks.accept(genuine["id"], "   ")
    accepted = await client.breaks.accept(genuine["id"], "known fee, reverses on the 3rd")
    assert accepted["state"] == "accepted"
    assert accepted["accepted_reason"] == "known fee, reverses on the 3rd"
    assert [c["text"] for c in accepted["comments"]] == [
        "Assigned to ops-eq",
        "late booking adjustment on A2",
        "Accepted: known fee, reverses on the 3rd",
    ]
    bench = await client.breaks.workbench(DEFINITION)
    assert bench["accepted"] == [genuine["id"]]  # accepted, and still on the workbench


async def test_the_next_run_clears_what_went_away_and_keeps_what_was_accepted(
    client: AsyncClient, reconciled: str, started_database: Database, tenant_id: str
) -> None:
    rows = _by_key(await client.breaks.workbench(DEFINITION))
    genuine = next(row for row in rows.values() if row["kind"] == "genuine")
    await client.breaks.accept(genuine["id"], "known fee")

    await _run(
        started_database, tenant_id, [*RIGHT, {"account": "A3", "book": "FX", "balance": 75}]
    )

    outstanding = await client.breaks.workbench(DEFINITION)
    assert [row["state"] for row in outstanding["rows"]] == ["accepted"]
    assert outstanding["cleared_count"] == 1
    everything = await client.breaks.workbench(DEFINITION, show="all")
    assert sorted(row["state"] for row in everything["rows"]) == ["accepted", "cleared"]
    latest = (await client.reconciliation.list())["reconciliations"][0]["latest"]
    # The ledger now has A3; A2 still differs. Accepting a break carries it,
    # and does not make the reconciliation agree.
    assert latest["breaks_needing_a_person"] == 1 and latest["verdict"] == "fail"


async def test_the_certificate_names_the_residue_and_who_accepted_it(
    client: AsyncClient, reconciled: str
) -> None:
    genuine = (await client.breaks.workbench(DEFINITION))["rows"][0]
    await client.breaks.accept(genuine["id"], "known fee")
    issued = await client.reconciliation.certify(DEFINITION, period_end="2026-09-30")
    assert issued["period_end"] == "2026-09-30" and issued["signed_by"]
    assert not issued["clean"] and len(issued["outstanding"]) == 2
    assert Decimal(issued["accepted_total"]) == 10
    # A3's 75.00 is missing from the ledger: right minus left is -75.00.
    assert Decimal(issued["unexplained_total"]) == -75
    assert issued["matched_rate"] == pytest.approx(0.8)
    assert len(issued["content_hash"]) == 64 and "known fee" in issued["markdown"]
    with pytest.raises(prama.NotFoundError):
        await client.reconciliation.certify("no such reconciliation")


async def test_a_caller_without_break_write_is_refused(
    client: AsyncClient, reconciled: str, started_database: Database, tenant_id: str
) -> None:
    genuine = (await client.breaks.workbench(DEFINITION))["rows"][0]
    auditor = await _signed_in_as(client, started_database, tenant_id, "aud", "auditor")
    with pytest.raises(prama.ForbiddenError):
        await auditor.breaks.assign(genuine["id"], "me")
    with pytest.raises(prama.ForbiddenError):
        await auditor.breaks.workbench(DEFINITION)
    # Nothing the refused caller tried was recorded.
    unchanged = await client.breaks.get(genuine["id"])
    assert unchanged["state"] == "open" and unchanged["comments"] == []
    # A steward works breaks but does not sign certificates.
    steward = await _signed_in_as(client, started_database, tenant_id, "stu", "steward")
    assert (await steward.breaks.assign(genuine["id"], "stu"))["owner"] == "stu"
    with pytest.raises(prama.ForbiddenError):
        await steward.reconciliation.certify(DEFINITION)
    for c in (auditor, steward):
        await c.close()


async def test_another_estate_s_break_is_not_found(client: AsyncClient, reconciled: str) -> None:
    genuine = (await client.breaks.workbench(DEFINITION))["rows"][0]
    made = await client.tenants.create("elsewhere", "Elsewhere")
    inside = client.as_key(made["credentials"]["api_key"])
    with pytest.raises(prama.NotFoundError):
        await inside.breaks.accept(genuine["id"], "not mine to accept")
    assert (await inside.breaks.workbench(DEFINITION))["rows"] == []
    await inside.close()
