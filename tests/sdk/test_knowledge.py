"""Knowledge through the SDK: lineage, code review, glossary, metadata and comments.

Every test asserts what the estate now holds or what the engine concluded — an
edge in the store, a proposal implied, a thread resolved — and the important
behaviours carry their counterfactual.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any

import pytest
from tests.sdk.conftest import PASSWORD

import prama.sdk as prama
from prama.db import Database
from prama.sdk import AsyncClient
from prama.security.accounts import grant_roles

STAGE = """INSERT INTO stg.trades (trade_id, account_id, notional, ccy)
SELECT t.id, t.acct, {notional}, t.currency FROM raw.trades t WHERE t.status = 'BOOKED';
"""
MART = """CREATE VIEW mart.positions AS
SELECT s.account_id AS account_id, SUM(s.notional * fx.rate) AS exposure_usd
FROM stg.trades s JOIN ref.fx_rates fx ON s.ccy = fx.ccy
GROUP BY s.account_id;
"""


async def signed_in(
    client: AsyncClient, database: Database, tenant_id: str, username: str, role: str
) -> AsyncClient:
    """Another person in the estate, with one built-in role, signed in through the SDK."""
    async with database.unit_of_work() as uow:
        person = uow.principals.create(
            tenant_id=tenant_id, username=username, display_name=username.title()
        )
        uow.principals.set_password(person, PASSWORD)
        await uow.flush()
        await grant_roles(uow, tenant_id, person, [role])
    anonymous = AsyncClient(app=client._app)
    issued = await anonymous.auth.token(username, PASSWORD, tenant="acme-bank")
    return anonymous.as_key(issued["api_key"])


def _zip(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return buffer.getvalue()


# -- lineage -------------------------------------------------------------------


async def test_a_scanned_sql_file_yields_its_column_edge_and_impact(
    client: AsyncClient, tmp_path: Path
) -> None:
    sql = tmp_path / "01_stage.sql"
    sql.write_text(STAGE.format(notional="t.notional_amt"))
    run = await client.lineage.scan("warehouse", [sql, MART])
    assert run["outcome"] and run["edges"] >= 4 and run["statements"] == 2

    edges = {(e["from"], e["to"]) for e in (await client.lineage.edges())["edges"]}
    assert ("raw.trades.notional_amt", "stg.trades.notional") in edges
    assert ("stg.trades.notional", "mart.positions.exposure_usd") in edges

    reached = (await client.lineage.impact("raw.trades.notional_amt"))["reached"]
    assert "mart.positions.exposure_usd" in [r["column"] for r in reached]
    # The counterfactual: a column nothing reads reaches nothing.
    assert (await client.lineage.impact("raw.trades.status_note"))["reached"] == []
    assert [s["name"] for s in await client.lineage.sources()] == ["warehouse"]


async def test_an_edge_decision_is_recorded_and_a_change_reports_its_reach(
    client: AsyncClient,
) -> None:
    await client.lineage.scan("warehouse", STAGE.format(notional="t.notional_amt"))
    (edge,) = [
        e
        for e in (await client.lineage.edges(dataset="stg.trades"))["edges"]
        if e["to"] == "stg.trades.notional"
    ]
    decided = await client.lineage.reject(edge["id"], note="a copy in name only")
    assert decided["status"] == "rejected" and decided["decided_by"]
    # A rejected edge leaves the graph: what the notional reaches is recomputed without it.
    assert edge["id"] not in [e["id"] for e in (await client.lineage.edges())["edges"]]
    reached = (await client.lineage.impact("raw.trades.notional_amt"))["reached"]
    assert "stg.trades.notional" not in [r["column"] for r in reached]
    assert "stg.trades.account_id" in [
        r["column"] for r in (await client.lineage.impact("raw.trades.acct"))["reached"]
    ]

    changed = await client.lineage.change(
        STAGE.format(notional="t.notional_amt"), STAGE.format(notional="ABS(t.notional_amt)")
    )
    assert changed["changed"] == ["stg.trades.notional"]
    assert changed["at_risk"] is False  # nothing downstream is controlled yet
    unchanged = await client.lineage.change(
        STAGE.format(notional="t.x"), STAGE.format(notional="t.x")
    )
    assert unchanged["changed"] == []


async def test_a_manta_import_is_kept_beside_the_parse_and_says_what_it_dropped(
    client: AsyncClient,
) -> None:
    await client.lineage.scan("warehouse", STAGE.format(notional="t.notional_amt"))
    export = {
        "nodes": [
            {"id": "s1", "type": "Schema", "name": "raw"},
            {"id": "t1", "type": "Table", "name": "trades", "parent": "s1"},
            {"id": "c1", "type": "Column", "name": "notional_amt", "parent": "t1"},
            {"id": "c3", "type": "Column", "name": "fee", "parent": "t1"},
            {"id": "s2", "type": "Schema", "name": "stg"},
            {"id": "t2", "type": "Table", "name": "trades", "parent": "s2"},
            {"id": "c2", "type": "Column", "name": "notional", "parent": "t2"},
        ],
        "edges": [
            {"source": "c1", "target": "c2", "type": "DIRECT"},
            {"source": "c3", "target": "c2", "type": "DIRECT"},
            {"source": "c1", "target": "t2"},
        ],
    }
    result = await client.lineage.import_export("manta", export)
    assert result["edges_recorded"] == 2
    assert [d["reason"] for d in result["dropped"]] == ["not between two columns"]
    assert {s["name"] for s in await client.lineage.sources()} == {"warehouse", "manta-import"}
    (conflict,) = await client.lineage.conflicts()
    assert conflict["column"] == "stg.trades.notional"
    assert conflict["theirs_only"] == ["raw.trades.fee"] and conflict["ours_only"] == []


async def test_scanning_needs_relationship_write(
    client: AsyncClient, started_database: Database, tenant_id: str
) -> None:
    steward = await signed_in(client, started_database, tenant_id, "sam", "steward")
    with pytest.raises(prama.ForbiddenError, match="relationship:write"):
        await steward.lineage.scan("warehouse", STAGE.format(notional="t.notional_amt"))
    assert (await client.lineage.edges())["total"] == 0
    await steward.close()


# -- code ----------------------------------------------------------------------


async def test_a_zip_is_read_for_lineage_and_a_review_fails_when_a_control_loses_its_basis(
    client: AsyncClient,
    started_database: Database,
    tenant_id: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)  # codeintake.workdir is relative
    base = _zip({"sql/01_stage.sql": STAGE.format(notional="t.notional_amt"), "sql/02.sql": MART})
    head = _zip(
        {"sql/01_stage.sql": STAGE.format(notional="ABS(t.notional_amt)"), "sql/02.sql": MART}
    )
    run = await client.code.add_zip("etl", base)
    assert run["status"] in ("succeeded", "partial") and run["coverage"]["edges"] >= 4
    assert [r["run"] for r in await client.code.runs()] == [run["run"]]

    # The raw control, live: the base carries it onto staging, the head does not.
    async with started_database.unit_of_work() as uow:
        control, _ = await uow.controls.declare(
            tenant_id=tenant_id,
            identity="raw:notional-non-negative",
            pql="CHECK \"raw.trades\".notional_amt >= 0 BECAUSE 'a size'",
        )
        await uow.controls.activate(str(control.id), tenant_id=tenant_id, approved_by="x")
    first = await client.code.review(base, head)
    retyped = [c for c in first["changes"] if c["kind"] == "retyped"]
    assert [(c["source"], c["target"]) for c in retyped] == [
        ("raw.trades.notional_amt", "stg.trades.notional")
    ]
    assert first["fails"] is False  # counterfactual: the carried control is not live yet
    (carried,) = [p for p in first["lost"] if p["rule"] == "lineage_propagated"]

    async with started_database.unit_of_work() as uow:
        control, _ = await uow.controls.declare(
            tenant_id=tenant_id, identity=carried["identity"], pql=carried["pql"]
        )
        await uow.controls.activate(str(control.id), tenant_id=tenant_id, approved_by="x")
    second = await client.code.review(base, head)
    assert second["fails"] is True and carried["identity"] in second["broken"]
    assert "lose their basis" in second["markdown"]


async def test_a_git_location_on_a_private_address_is_refused_before_anything_is_stored(
    client: AsyncClient,
) -> None:
    with pytest.raises(prama.ValidationError):
        await client.code.add_git("internal", "https://127.0.0.1/org/repo.git")
    with pytest.raises(prama.ValidationError):
        await client.code.review_git("file:///etc", "main", "HEAD")
    assert await client.code.sources() == []


# -- glossary ------------------------------------------------------------------


async def test_a_glossary_import_reports_what_it_dropped_and_a_term_binds(
    client: AsyncClient,
) -> None:
    dataset = await client.datasets.declare("Trades", description="Executed trades.")
    await client.datasets.add_attribute(dataset["id"], "account_id")
    export = {
        "results": [
            {"id": 7, "title": "Account", "description": "<p>A customer account.</p>"},
            {"id": 8, "title": "", "description": "nameless"},
        ]
    }
    result = await client.glossary.import_export("alation", export)
    assert result["terms_created"] == 1
    assert [d["source"] for d in result["dropped"]] == ["term 8"]

    bound = await client.glossary.bind("Account", "attribute", "trades.account_id")
    assert [(b["kind"], b["ref"]) for b in bound["bound"]] == [("attribute", "trades.account_id")]
    assert [t["name"] for t in await client.glossary.search("customer")] == ["Account"]
    assert await client.glossary.search("nothing like it") == []
    with pytest.raises(prama.ValidationError, match="no concept"):
        await client.glossary.bind("Account", "concept", "NoSuchConcept")


# -- metadata ------------------------------------------------------------------


async def _trades(client: AsyncClient) -> dict[str, Any]:
    dataset = await client.datasets.declare("Trades", description="Executed trades.")
    for name in ("trade_id", "account_id"):
        await client.datasets.add_attribute(dataset["id"], name)
    await client.metadata.install_starter("data-quality-attribute")
    return dict(dataset)


async def test_setting_mandatory_proposes_a_not_null_check_for_a_person_to_accept(
    client: AsyncClient,
) -> None:
    await _trades(client)
    assert await client.metadata.proposals() == []  # counterfactual: nothing set, nothing implied
    result = await client.metadata.set("trades.account_id", mandatory="yes")
    assert result["changed"] == ["mandatory"]
    (proposal,) = result["proposals"]
    assert proposal["pql"].startswith("CHECK trades.account_id IS NOT NULL")
    assert [p["identity"] for p in await client.metadata.proposals(dataset="trades")] == [
        proposal["identity"]
    ]
    described = await client.metadata.describe("trades")
    account = next(a for a in described["attributes"] if a["name"] == "account_id")
    assert account["metadata"] == {"mandatory": True}
    # A proposal, not a control: nothing runs until a person accepts it.
    assert described["rules"] == []

    await client.metadata.set("trades.account_id", mandatory="no")
    assert await client.metadata.proposals() == []


async def test_a_hand_written_rule_is_proposed_and_one_for_another_dataset_is_refused(
    client: AsyncClient, started_database: Database, tenant_id: str
) -> None:
    await _trades(client)
    made = await client.metadata.author_rule("trades", "CHECK trades.trade_id IS NOT NULL")
    assert made["status"] == "proposed"
    assert [r["status"] for r in (await client.metadata.describe("trades"))["rules"]] == [
        "proposed"
    ]
    with pytest.raises(prama.ValidationError, match="not trades"):
        await client.metadata.author_rule("trades", "CHECK positions.id IS NOT NULL")
    reader = await signed_in(client, started_database, tenant_id, "rita", "auditor")
    with pytest.raises(prama.ForbiddenError):
        await reader.metadata.author_rule("trades", "CHECK trades.account_id IS NOT NULL")
    await reader.close()


async def test_templates_and_context_round_trip(client: AsyncClient) -> None:
    await _trades(client)
    saved = await client.metadata.save_template(
        yaml=(
            "name: ownership\napplies_to: dataset\n"
            "fields:\n  - name: source_system\n    kind: text\n"
        )
    )
    assert saved["added"] == 1
    names = {t["name"] for t in (await client.metadata.templates())["templates"]}
    assert names == {"data-quality-attribute", "ownership"}
    after = await client.metadata.set_context("trades", "Every booked trade, by trade date.")
    assert after["business_context"] == "Every booked trade, by trade date."
    hits = await client.metadata.search("booked trade")
    assert any(h["name"] == "Trades" for h in hits)


# -- comments ------------------------------------------------------------------


async def test_a_mention_reaches_a_queue_and_leaves_it_when_the_thread_resolves(
    client: AsyncClient, started_database: Database, tenant_id: str
) -> None:
    await client.datasets.declare("Trades", description="Executed trades.")
    bo = await signed_in(client, started_database, tenant_id, "bo", "owner")
    thread = await client.comments.post(
        "@bo is ccy upper case?", object_kind="dataset", object_ref="trades"
    )
    await bo.comments.reply(thread["id"], "Yes, ISO 4217.")
    (open_thread,) = await client.comments.threads("dataset", "trades")
    assert open_thread["state"] == "open" and len(open_thread["replies"]) == 1

    assert [m["id"] for m in (await bo.comments.queue())["mentions"]] == [thread["id"]]
    theirs = await client.comments.queue(person="bo", section="mentions")
    assert theirs["total"] == 1

    resolved = await bo.comments.resolve(thread["id"])
    assert resolved["state"] == "resolved"
    assert (await bo.comments.queue())["mentions"] == []
    # Reading somebody else's queue is an administrator's; bo is not one.
    with pytest.raises(prama.ForbiddenError, match="admin"):
        await bo.comments.queue(person="ada")
    await bo.close()
