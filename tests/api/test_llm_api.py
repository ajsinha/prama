"""/api/v1/llm: the server is the only door to a model.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama.db import Database
from prama.llm.budget import cost_micros


async def _configure(database: Database, tenant: str, answers: list[str]) -> None:
    async with database.unit_of_work() as uow:
        await uow.llm.add_provider(
            tenant,
            name="local",
            kind="scripted",
            hosting="self_hosted",
            settings={"answers": answers},
        )
        await uow.llm.set_profile(tenant, "author", [("local", "qwen")])
        # $2 per million input tokens, $6 per million output, from long ago.
        await uow.llm.set_price(
            tenant,
            "local",
            "qwen",
            input_micros=2_000_000,
            output_micros=6_000_000,
            effective_from="2020-01-01T00:00:00.000+00:00",
        )


async def test_a_chat_is_answered_recorded_and_costed(
    client: Any, started_database: Database, tenant_id: str
) -> None:
    await _configure(started_database, tenant_id, ["CHECK t.a IS NOT NULL"])
    reply = await client.post("/llm/chat", json={"purpose": "author", "prompt": "write one"})
    assert reply.status_code == 200, reply.text
    assert reply.json()["text"] == "CHECK t.a IS NOT NULL"
    async with started_database.unit_of_work() as uow:
        (call,) = await uow.llm.calls(tenant_id)
    assert call.surface == "api" and call.api_key_id and call.price_model_id


async def test_a_spent_budget_refuses_with_429(
    client: Any, started_database: Database, tenant_id: str
) -> None:
    await _configure(started_database, tenant_id, ["a", "b"])
    async with started_database.unit_of_work() as uow:
        await uow.llm.set_budget(tenant_id, scope_kind="tenant", limit_tokens=0)
    reply = await client.post("/llm/chat", json={"purpose": "author", "prompt": "p"})
    assert reply.status_code == 429
    assert "budget" in reply.text
    async with started_database.unit_of_work() as uow:
        (call,) = await uow.llm.calls(tenant_id)
    assert call.outcome == "refused_budget"  # the refusal itself is on the record


async def test_a_warn_budget_answers_and_warns(
    client: Any, started_database: Database, tenant_id: str
) -> None:
    await _configure(started_database, tenant_id, ["a"])
    async with started_database.unit_of_work() as uow:
        await uow.llm.set_budget(tenant_id, scope_kind="tenant", limit_tokens=0, action="warn")
    reply = await client.post("/llm/chat", json={"purpose": "author", "prompt": "p"})
    assert reply.status_code == 200 and reply.json()["warnings"]


def test_cost_is_integer_micro_units_rounded_up() -> None:
    price = type("P", (), {"price_in_micros": 2_000_000, "price_out_micros": 6_000_000})()
    # 1,000 in at $2/M = 2,000 micros; 1 out at $6/M = 6 micros.
    assert cost_micros(price, 1000, 1) == 2006
    assert cost_micros(price, 1, 0) == 2  # 2 micros exactly
    assert cost_micros(None, 10, 10) == 0


async def test_the_route_needs_llm_use(
    sqlite_config: Any, started_database: Database, tenant_id: str
) -> None:
    import httpx
    from httpx import ASGITransport
    from tests.api.conftest import issue_key

    from prama.api import create_app
    from prama.api.app import API_PREFIX

    key = await issue_key(started_database, tenant_id, principal="r", scopes=["report:read"])
    app = create_app(sqlite_config, database=started_database)
    async with (
        httpx.AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver" + API_PREFIX,
            headers={"Authorization": f"Bearer {key}"},
        ) as http,
        app.router.lifespan_context(app),
    ):
        reply = await http.post("/llm/chat", json={"purpose": "author", "prompt": "p"})
        assert reply.status_code == 403


async def test_a_reservation_counts_as_spend_until_released(
    started_database: Database, tenant_id: str
) -> None:
    """The fleet-wide half: another server's call in flight is visible spend."""
    await _configure(started_database, tenant_id, ["a"])
    async with started_database.unit_of_work() as uow:
        await uow.llm.set_budget(tenant_id, scope_kind="tenant", limit_tokens=5000)
        before = await uow.llm.spend(tenant_id, "2000-01-01")
        held = await uow.llm.reserve(tenant_id, ["tenant:"], micros=10, tokens=4000, seconds=60)
        during = await uow.llm.spend(tenant_id, "2000-01-01")
        await uow.llm.release_reservation(tenant_id, held.id)
        after = await uow.llm.spend(tenant_id, "2000-01-01")
    assert during == (before[0] + 10, before[1] + 4000)
    assert after == before  # the control: released, it no longer counts


async def test_a_streamed_chat_arrives_as_events_and_is_recorded(
    client: Any, started_database: Database, tenant_id: str
) -> None:
    await _configure(started_database, tenant_id, ["CHECK t.a IS NOT NULL"])
    reply = await client.post("/llm/chat/stream", json={"purpose": "author", "prompt": "p"})
    assert reply.status_code == 200
    assert reply.headers["content-type"].startswith("text/event-stream")
    assert 'data: {"text": "CHECK t.a IS NOT NULL"}' in reply.text
    assert "event: done" in reply.text
    async with started_database.unit_of_work() as uow:
        (call,) = await uow.llm.calls(tenant_id)
    assert call.outcome == "ok" and call.response_hash
