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


class TestABySubresourceReadIsScopedToo:
    """QA finding F-02. The S2 fix scoped every by-*id* read on `VersionedDao`
    and missed the by-*parent* reads on its subclasses.

    `GET /datasets/{id}/attributes` with a valid key from another estate
    returned **200 with the declarations in full** — not a 404, and not an empty
    list. Same for `/datasets/{id}/bindings` and `/concepts/{id}/properties`.
    `AttributeDao.for_dataset`, `BindingDao.for_dataset`,
    `BindingDao.for_attribute` and `ConceptPropertyDao.for_concept` filtered on
    the parent and never on the estate, while siblings in the same classes —
    `critical_data_elements`, `drifted` — always filtered.

    The sweep in `tests/security/test_tenant_isolation.py` could not see them:
    it probes methods callable with a tenant alone, enumerating by `tenant_id`
    as the **first** parameter, and a method taking `dataset_id` is invisible to
    it however carefully it is written. `TestEveryDaoReadTakesATenant` is the
    static half added alongside these.

    Found by a QA pass driving the HTTP API, not by 4,666 unit tests.
    """

    async def dataset_with_an_attribute(self, client: httpx.AsyncClient) -> str:
        created = await client.post(
            "/datasets", json={"name": "settlement_instructions", "criticality": 3}
        )
        assert created.status_code == 201, created.text
        dataset_id = str(created.json()["id"])
        added = await client.post(
            f"/datasets/{dataset_id}/attributes",
            json={"name": "counterparty_lei", "definition": "who we owe it to"},
        )
        assert added.status_code == 201, added.text
        return dataset_id

    async def test_another_tenant_cannot_list_attributes(
        self, client: httpx.AsyncClient, intruder: httpx.AsyncClient
    ) -> None:
        dataset_id = await self.dataset_with_an_attribute(client)
        response = await intruder.get(f"/datasets/{dataset_id}/attributes")
        assert response.status_code in (200, 404), response.text
        if response.status_code == 200:
            assert response.json() == [], (
                "another estate's attributes were returned in full: " + response.text
            )
        assert "counterparty_lei" not in response.text

    async def test_the_owner_still_sees_them(self, client: httpx.AsyncClient) -> None:
        """The positive control. A filter that returns nothing to everybody is
        not isolation, it is an outage — and it would pass the test above."""
        dataset_id = await self.dataset_with_an_attribute(client)
        response = await client.get(f"/datasets/{dataset_id}/attributes")
        assert response.status_code == 200, response.text
        assert [a["name"] for a in response.json()] == ["counterparty_lei"]

    async def test_another_tenant_cannot_list_bindings(
        self, client: httpx.AsyncClient, intruder: httpx.AsyncClient
    ) -> None:
        dataset_id = await self.dataset_with_an_attribute(client)
        response = await intruder.get(f"/datasets/{dataset_id}/bindings")
        assert response.status_code in (200, 404)
        if response.status_code == 200:
            assert response.json() == [], response.text
