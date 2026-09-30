"""The model gateway's administration through the SDK: providers, profiles,
templates, prices, budgets, the ledger and evaluation runs.

Models here are the ``scripted`` kind — fixed answers, no network — so each
test can assert exactly what the gateway recorded.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import prama_sdk as prama
import pytest
from prama_sdk import AsyncClient

from prama.db import Database

EXPLAIN = {
    "name": "explain",
    "system": "Explain the check for a data owner.",
    "body": "Check {{pql}} on {{dataset}}.",
    "variables": [{"name": "pql", "trusted": True}, {"name": "dataset", "trusted": True}],
}

SUITE = {
    "name": "explain-suite",
    "purpose": "explain",
    "template": "explain",
    "cases": [
        {
            "name": "names the check",
            "vars": {"pql": "CHECK t.a IS NOT NULL", "dataset": "t"},
            "expect": {"nonempty": True, "contains": ["null"], "absent": ["DROP"]},
        },
    ],
}


async def test_adding_a_provider_stores_a_reference_and_never_a_secret(
    client: AsyncClient, started_database: Database, tenant_id: str
) -> None:
    added = await client.models.add_provider(
        "openai",
        kind="openai_compatible",
        hosting="hosted",
        endpoint="https://api.example.com/v1",
        credential_ref="env://OPENAI_KEY",
    )
    assert added["credential"] == "reference set"
    assert "env://OPENAI_KEY" not in str(await client.models.providers())

    async with started_database.unit_of_work() as uow:
        row = await uow.llm.provider(tenant_id, "openai")
        assert row is not None and row.credential_ref == "env://OPENAI_KEY"

    # A pasted key is refused, and nothing is written.
    with pytest.raises(prama.ValidationError, match="not a secret reference"):
        await client.models.add_provider(
            "leaky", kind="openai_compatible", hosting="hosted", credential_ref="sk-live-abc123"
        )
    with pytest.raises(prama.ValidationError, match="looks like a credential"):
        await client.models.add_provider(
            "leaky", kind="scripted", hosting="self_hosted", settings={"api_key": "sk-live-abc"}
        )
    assert [p["name"] for p in await client.models.providers()] == ["openai"]
    # A provider that could never be used is refused before it is stored.
    with pytest.raises(prama.ValidationError):
        await client.models.add_provider("odd", kind="no-such-kind", hosting="hosted")
    with pytest.raises(prama.ConflictError):
        await client.models.add_provider("openai", kind="scripted", hosting="self_hosted")


async def test_a_profile_routes_a_prompt_and_the_ledger_verifies_until_tampered_with(
    client: AsyncClient, started_database: Database, tenant_id: str
) -> None:
    await client.models.add_provider(
        "local", kind="scripted", hosting="self_hosted", settings={"answers": ["first", "second"]}
    )
    made = await client.models.set_profile("author", ["local:qwen"])
    assert made == {"purpose": "author", "version": 1, "current": True}
    with pytest.raises(prama.ValidationError):
        await client.models.set_profile("author", ["no-colon"])
    with pytest.raises(prama.NotFoundError):
        await client.models.set_profile("author", ["elsewhere:model"])

    answer = await client.models.try_model("author", "Say something.")
    assert answer["text"] == "first" and answer["provider"] == "scripted"
    await client.models.try_model("author", "And again.")

    calls = await client.models.calls()
    assert [c["sequence"] for c in calls] == [1, 0]
    assert {c["purpose"] for c in calls} == {"author"} and {c["outcome"] for c in calls} == {"ok"}
    assert "Say something" not in str(calls)  # hashes, never text
    assert await client.models.verify() == {"intact": True, "checked": 2, "break": ""}

    # The counterfactual: alter a recorded call and the chain says where.
    async with started_database.unit_of_work() as uow:
        (oldest,) = [c for c in await uow.llm.calls(tenant_id) if c.sequence == 0]
        oldest.output_tokens += 1000
    broken = await client.models.verify()
    assert broken["intact"] is False and "call 0" in broken["break"]

    profiles = await client.models.profiles()
    assert profiles[0]["purpose"] == "author" and profiles[0]["current_version"] == 1
    assert profiles[0]["versions"][0]["route"] == ["local:qwen"]


async def test_prices_and_budgets(client: AsyncClient) -> None:
    await client.models.add_provider("local", kind="scripted", hosting="self_hosted")
    await client.models.set_price("local", "qwen", input_per_million="2.50", output_per_million=10)
    (price,) = await client.models.prices()
    assert price["provider"] == "local" and price["input_per_million"] == "2.5"
    assert price["output_per_million"] == "10"
    with pytest.raises(prama.ValidationError):
        await client.models.set_price(
            "local", "qwen", input_per_million="cheap", output_per_million=1
        )

    await client.models.set_budget(limit="250.00", period="month")
    (budget,) = await client.models.budgets()
    assert budget["scope_kind"] == "tenant" and budget["limit"] == "250"
    assert budget["spent"] == "0" and budget["action"] == "refuse"
    # Replacing, not adding: one budget per scope and period.
    await client.models.set_budget(limit=100, period="month", action="warn")
    (budget,) = await client.models.budgets()
    assert budget["limit"] == "100" and budget["action"] == "warn"
    with pytest.raises(prama.ValidationError):
        await client.models.set_budget(limit=1, period="year")
    with pytest.raises(prama.ValidationError):
        await client.models.set_budget(period="day")


async def test_a_template_is_evaluated_then_approved_by_someone_other_than_its_author(
    client: AsyncClient,
) -> None:
    await client.models.add_provider(
        "local", kind="scripted", hosting="self_hosted", settings={"answers": ["a is never null"]}
    )
    await client.models.set_profile("explain", ["local:qwen"])
    draft = await client.models.add_template(EXPLAIN)
    assert draft == {"name": "explain", "version": 1, "status": "draft"}

    run = await client.models.evaluate(SUITE)
    assert run["status"] == "passed" and run["passed"] == run["cases"] == 1
    assert run["template_version"] == 1 and run["report"][0]["passed"] is True
    assert (await client.models.evaluation(run["id"]))["report"] == run["report"]
    assert [r["id"] for r in await client.models.evaluations()] == [run["id"]]

    # The author may not approve their own template.
    with pytest.raises(prama.ForbiddenError, match="author"):
        await client.models.approve_template("explain", 1)

    # A second administrator may.
    await client.principals.create("bo", roles=["admin"], password="bo-password-12")
    anonymous = AsyncClient(app=client._app)
    bo = anonymous.as_key(
        (await anonymous.auth.token("bo", "bo-password-12", tenant="acme-bank"))["api_key"]
    )
    approved = await bo.models.approve_template("explain", 1)
    assert approved["status"] == "approved" and approved["approved_by"] != run["started_by"]
    (row,) = await client.models.templates()
    assert row["current"] is True and row["status"] == "approved"
    await bo.close()


async def test_a_failing_evaluation_is_recorded_as_failed(client: AsyncClient) -> None:
    await client.models.add_provider(
        "local", kind="scripted", hosting="self_hosted", settings={"answers": ["DROP TABLE t"]}
    )
    await client.models.set_profile("explain", ["local:qwen"])
    await client.models.add_template(EXPLAIN)
    run = await client.models.evaluate(SUITE)
    assert run["status"] == "failed" and run["passed"] == 0
    assert run["report"][0]["misses"]


async def test_model_administration_needs_admin(client: AsyncClient) -> None:
    await client.principals.create("cy", roles=["owner"], password="cy-password-123")
    anonymous = AsyncClient(app=client._app)
    cy = anonymous.as_key(
        (await anonymous.auth.token("cy", "cy-password-123", tenant="acme-bank"))["api_key"]
    )
    for attempt in (
        cy.models.providers(),
        cy.models.verify(),
        cy.models.add_provider("x", kind="scripted", hosting="self_hosted"),
    ):
        with pytest.raises(prama.ForbiddenError):
            await attempt
    assert await client.models.providers() == []  # the counterfactual, and nothing was added
    await cy.close()
