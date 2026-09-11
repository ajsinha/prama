"""A valid caller of one estate must not reach another's declarations.

Finding S2 of ``docs/reviews/2026-09-11-adversarial-review.md``. The by-id
reads and writes on ``VersionedDao`` used to take only an identifier. Every
route had the caller's tenant in hand and passed it to the audit event but not
to the query, so a caller holding an identifier from another estate — an id
leaked in a screenshot, a support ticket, a shared spreadsheet — read and wrote
the other estate's rows, and the audit trail recorded the *attacker's* tenant.

These are counterfactual tests: each one was confirmed to fail against the
unscoped code before the scope was added. An isolation test that has never been
seen to fail is a test that proves nothing.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.anyio


@pytest.fixture
async def victim_dataset(client: httpx.AsyncClient) -> str:
    """A dataset declared by the legitimate tenant."""
    response = await client.post(
        "/datasets",
        json={
            "name": "settlement_instructions",
            "description": "What we owe and to whom.",
            "criticality": 3,
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def test_another_tenant_cannot_read_a_dataset(
    victim_dataset: str, intruder: httpx.AsyncClient
) -> None:
    response = await intruder.get(f"/datasets/{victim_dataset}")
    assert response.status_code == 404, (
        "a caller of another estate read a declaration by id: " + response.text
    )


async def test_another_tenant_cannot_read_a_dataset_history(
    victim_dataset: str, intruder: httpx.AsyncClient
) -> None:
    """History is the interesting one: it leaks every past name and definition."""
    response = await intruder.get(f"/datasets/{victim_dataset}/history")
    if response.status_code == 200:
        assert response.json() == [], "history leaked another estate's versions"
    else:
        assert response.status_code == 404, response.text


async def test_another_tenant_cannot_amend_a_dataset(
    victim_dataset: str, intruder: httpx.AsyncClient, client: httpx.AsyncClient
) -> None:
    response = await intruder.post(
        f"/datasets/{victim_dataset}/amend",
        json={"reason": "hostile edit", "changes": {"criticality": 2}},
    )
    assert response.status_code == 404, response.text

    # And the victim's declaration is untouched — the refusal is real, not a
    # 404 returned after the write landed.
    still = await client.get(f"/datasets/{victim_dataset}")
    assert still.status_code == 200
    assert still.json()["criticality"] == 3


async def test_another_tenant_cannot_retire_a_dataset(
    victim_dataset: str, intruder: httpx.AsyncClient, client: httpx.AsyncClient
) -> None:
    """The starkest case: DELETE by id, previously with no scope at all."""
    response = await intruder.delete(f"/datasets/{victim_dataset}")
    assert response.status_code in (403, 404), response.text

    still = await client.get(f"/datasets/{victim_dataset}")
    assert still.status_code == 200, "another estate retired the declaration"
