"""The rest of the control estate over the SDK: the language, the builder, imports,
the proposal queue, relationships, and a control's life from proposal to retirement.

Each test asserts what the server did — a control that was accepted is active,
a rejection keeps a proposal out of the queue, a compiled control carries its
SQL — rather than that a call returned.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

import prama.sdk as prama
from prama.sdk import AsyncClient

UNIQUE = "CHECK positions HAS UNIQUE KEY (account_id) SEVERITY minor"

DBT = """
version: 2
models:
  - name: positions
    columns:
      - name: account_id
        tests:
          - not_null
      - name: currency
        tests:
          - accepted_values:
              values: ['GBP', 'USD']
      - name: notional
        tests:
          - my_company.check_frtb_eligible
"""


async def test_the_language_answers_without_storing_anything(client: AsyncClient) -> None:
    await client.datasets.declare("positions")
    checked = await client.pql.check(UNIQUE + "\n\nCHECK positions HAS UNIQUE KEY (nope")
    assert checked["syntax_error"] is not None and checked["errors"] == 1

    checked = await client.pql.check(UNIQUE)
    assert checked["controls"] == 1 and checked["syntax_error"] is None
    assert "account_id" in checked["explanations"][0]["sentence"]

    compiled = await client.pql.compile(UNIQUE, dialect="sqlite", fuse=True)
    assert "positions" in compiled["plans"][0]["metric_query"]
    assert compiled["fused"]["scans"] == 1

    explained = await client.pql.explain(UNIQUE)
    assert explained["controls"][0]["sentence"]
    assert (await client.pql.format("CHECK   positions HAS UNIQUE KEY (account_id)"))[
        "source"
    ].startswith("CHECK positions")

    coverage = await client.pql.functions(engine="sqlite")
    assert coverage["functions"] and coverage["coverage"][0]["engine"] == "sqlite"
    with pytest.raises(prama.ValidationError):
        await client.pql.functions(engine="no-such-engine")
    assert await client.controls.list() == []


async def test_the_builder_and_an_import_come_back_as_pql(client: AsyncClient) -> None:
    questions = await client.controls.builder_questions()
    assert "in_list" in [q["key"] for q in questions["questions"]]
    built = await client.controls.build(
        "positions",
        "in_list",
        column="currency",
        values="GBP, USD",
        because="only the currencies we settle in",
    )
    assert "IN" in built["pql"] and built["sentence"]
    with pytest.raises(prama.ValidationError):
        await client.controls.build("positions", "no_such_rule")

    imported = await client.controls.import_(DBT, "dbt", declare=True)
    assert imported["imported"] >= 2 and not imported["complete"]
    assert any("check_frtb_eligible" in u["source"] for u in imported["unmapped"])
    stored = await client.controls.list(status="proposed")
    assert {c["origin"] for c in stored} == {"import"}
    assert len(stored) == len(imported["declared"]) == imported["imported"]


async def test_a_control_from_proposal_to_retirement(client: AsyncClient) -> None:
    proposed = await client.controls.declare(UNIQUE, schedule="daily")
    assert proposed["status"] == "proposed" and proposed["schedule_described"]
    with pytest.raises(prama.ValidationError):
        await client.controls.declare(UNIQUE, schedule="every 1 second")
    active = await client.controls.activate(proposed["id"], reason="reviewed")
    suppressed = await client.controls.suppress(
        proposed["id"], until="2030-01-01T00:00:00+00:00", because="vendor outage"
    )
    assert active["status"] == "active" and suppressed["status"] == "suppressed"
    with pytest.raises(prama.ValidationError):
        await client.controls.suppress(proposed["id"], until=" ", because="forever")
    retired = await client.controls.retire(proposed["id"], reason="replaced")
    assert retired["status"] == "retired"
    history = await client.controls.history(proposed["id"])
    assert [v["status"] for v in history] == ["proposed", "active", "suppressed", "retired"]
    assert (await client.controls.get(proposed["id"]))["status"] == "retired"
    with pytest.raises(prama.ValidationError):
        await client.controls.activate(proposed["id"])
    with pytest.raises(prama.NotFoundError):
        await client.controls.get("01NOSUCHCONTROL0000000000")


async def test_the_queue_accepts_and_remembers_a_rejection(client: AsyncClient) -> None:
    dataset = await client.datasets.declare(
        "accounts", grain={"attributes": ["account_id"], "statement": "one row per account"}
    )
    await client.datasets.add_attribute(dataset["id"], "account_id", optionality="mandatory")
    await client.datasets.add_attribute(dataset["id"], "status", codelist=["open", "closed"])
    queue = await client.proposals.list(dataset_id=dataset["id"])
    first, second, *_ = queue["proposals"]

    accepted = await client.proposals.accept(
        first["identity"], first["pql"], rule=first["rule"], dataset_id=dataset["id"]
    )
    assert accepted["status"] == "active" and accepted["source_ref"] == dataset["id"]
    await client.proposals.reject(
        second["identity"], second["content_hash"], reason="not_material", note="noise"
    )
    with pytest.raises(prama.ValidationError):
        await client.proposals.reject("x", "y", reason="because")

    again = await client.proposals.list(dataset_id=dataset["id"])
    offered = {p["identity"] for p in again["proposals"]}
    assert first["identity"] not in offered and second["identity"] not in offered
    assert again["accepted_already"] == 1 and again["rejected_already"] == 1
    assert (await client.proposals.rejections())[0]["reason"] == "not_material"


async def test_a_relationship_derives_its_controls(client: AsyncClient) -> None:
    trades = await client.datasets.declare("trades")
    accounts = await client.datasets.declare("accounts")
    for dataset in (trades, accounts):
        await client.datasets.add_attribute(dataset["id"], "account_id")
    relation = await client.relationships.declare(
        "references",
        trades["id"],
        accounts["id"],
        match_keys=[{"left": "account_id", "right": "account_id"}],
    )
    seen = await client.derive.preview_relationship(relation["id"])
    assert seen["controls"] and all("accounts" in c["pql"] for c in seen["controls"])
    assert relation["status"] == "confirmed"  # declared by a person, so asserted true
    made = await client.derive.relationship(relation["id"], accept=True)
    assert made["declared"] == len(seen["controls"])
    assert {c["control"]["status"] for c in made["controls"]} == {"active"}

    # A relationship nobody stands behind implies nothing that may run.
    await client.relationships.reject(relation["id"], reason="wrong direction")
    with pytest.raises(prama.ValidationError, match="not confirmed"):
        await client.derive.relationship(relation["id"], accept=True)


async def test_the_schedule_is_readable_and_a_tick_needs_a_scheduler(client: AsyncClient) -> None:
    proposed = await client.controls.declare(UNIQUE, schedule="06:30")
    await client.controls.activate(proposed["id"])
    schedule = await client.schedule.get()
    assert schedule["scheduler"] is None
    assert [c["control_id"] for c in schedule["controls"]] == [proposed["id"]]
    assert schedule["controls"][0]["described"]
    with pytest.raises(prama.ValidationError, match="scheduler is off"):
        await client.schedule.run_now()
