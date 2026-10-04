"""Activating a control is held to its tier, like declaring a dataset.

The approval policy governed declarations only: a Tier-1 control could be
written and switched on by one person, holding nothing but `control:approve`.
Every activation now goes through `prama.controls.approval.activate`.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import ast
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from httpx import ASGITransport
from tests.api.conftest import issue_key

from prama.api import create_app
from prama.api.app import API_PREFIX
from prama.db import Database

PQL = "CHECK trades.notional IS NOT NULL"


@asynccontextmanager
async def _second_person(
    sqlite_config: Any, database: Database, tenant_id: str
) -> AsyncIterator[httpx.AsyncClient]:
    key = await issue_key(database, tenant_id, principal="checker")
    app = create_app(sqlite_config, database=database)
    async with (
        httpx.AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver" + API_PREFIX,
            headers={"Authorization": f"Bearer {key}"},
        ) as http,
        app.router.lifespan_context(app),
    ):
        yield http


async def _declare(client: Any, criticality: int) -> str:
    reply = await client.post("/controls", json={"pql": PQL, "criticality": criticality})
    assert reply.status_code in (200, 201), reply.text
    return str(reply.json()["id"])


async def test_the_author_of_a_tier_one_control_cannot_switch_it_on(client: Any) -> None:
    control = await _declare(client, 1)
    reply = await client.post(f"/controls/{control}/activate", json={"reason": "mine"})
    assert reply.status_code == 422, reply.text
    assert "own author" in reply.text


async def test_a_second_person_can(
    client: Any, sqlite_config: Any, started_database: Database, tenant_id: str
) -> None:
    control = await _declare(client, 1)
    async with _second_person(sqlite_config, started_database, tenant_id) as checker:
        reply = await checker.post(f"/controls/{control}/activate", json={"reason": "checked"})
    assert reply.status_code == 200, reply.text
    assert reply.json()["status"] == "active"


async def test_below_tier_one_the_author_may(client: Any) -> None:
    control = await _declare(client, 3)
    reply = await client.post(f"/controls/{control}/activate", json={"reason": "fine"})
    assert reply.status_code == 200, reply.text


def test_nothing_activates_a_control_except_through_the_tier_check() -> None:
    """`uow.controls.activate` is the bare write; only the approval module may call it."""
    src = Path(__file__).resolve().parents[2] / "src" / "prama"
    callers = []
    for path in src.rglob("*.py"):
        if path.name == "approval.py" and path.parent.name == "controls":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "activate"
                and isinstance(node.func.value, ast.Attribute)
                and node.func.value.attr == "controls"
            ):
                callers.append(f"{path.relative_to(src)}:{node.lineno}")
    assert not callers, callers
