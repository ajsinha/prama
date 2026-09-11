"""A credential may only do what it was issued to do.

Finding S4 of `docs/reviews/2026-09-11-adversarial-review.md`. Scopes were
computed, stored on every API key, carried into every request on
`CallerIdentity.scopes` and read by **nothing**. `Principal.has_permission`
existed and was called by no code and no test. A read-only key could retire a
declaration, and the key record, the admin screen and the audit log all read as
though an authorisation decision were being made.

These are counterfactual tests: each was confirmed to fail against the
unenforced code, where every one of them returned 2xx.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from httpx import ASGITransport
from tests.api.conftest import issue_key

from prama.api import API_PREFIX, create_app
from prama.core.config import Configuration
from prama.db import Database

pytestmark = pytest.mark.anyio


async def client_with(
    config: Configuration, database: Database, tenant_id: str, scopes: list[str], who: str
) -> AsyncIterator[httpx.AsyncClient]:
    key = await issue_key(database, tenant_id, principal=who, scopes=scopes)
    app = create_app(config, database=database)
    async with (
        httpx.AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver" + API_PREFIX,
            headers={"Authorization": f"Bearer {key}"},
        ) as http,
        app.router.lifespan_context(app),
    ):
        yield http


@pytest.fixture
async def reader(
    sqlite_config: Configuration, started_database: Database, tenant_id: str
) -> AsyncIterator[httpx.AsyncClient]:
    """A key issued to look, not to touch."""
    async for http in client_with(
        sqlite_config, started_database, tenant_id, ["semantic:read"], "reader"
    ):
        yield http


@pytest.fixture
async def unscoped(
    sqlite_config: Configuration, started_database: Database, tenant_id: str
) -> AsyncIterator[httpx.AsyncClient]:
    """A key with no scopes recorded at all.

    The case that decides whether the default is safe. A credential minted
    before scopes were enforced has an empty list, and if empty meant
    "unrestricted" every such key would become a superuser on the day the
    control was switched on.
    """
    async for http in client_with(sqlite_config, started_database, tenant_id, [], "legacy"):
        yield http


class TestAReadKeyCannotWrite:
    async def test_it_may_read(self, reader: httpx.AsyncClient) -> None:
        """The counterfactual for the control itself. A scope check that
        refuses everything is not authorisation, it is an outage."""
        assert (await reader.get("/datasets")).status_code == 200

    async def test_it_may_not_declare(self, reader: httpx.AsyncClient) -> None:
        response = await reader.post("/datasets", json={"name": "Positions"})
        assert response.status_code == 403, response.text
        problem = response.json()
        assert problem["code"] == "AUTH.FORBIDDEN"
        assert "semantic:write" in problem["remedy"]

    async def test_it_may_not_retire(
        self, reader: httpx.AsyncClient, client: httpx.AsyncClient
    ) -> None:
        created = await client.post("/datasets", json={"name": "Positions"})
        assert created.status_code == 201
        dataset_id = created.json()["id"]

        assert (await reader.delete(f"/datasets/{dataset_id}")).status_code == 403
        # And the declaration is still there — the refusal is real.
        assert (await client.get(f"/datasets/{dataset_id}")).status_code == 200

    async def test_it_may_not_amend(
        self, reader: httpx.AsyncClient, client: httpx.AsyncClient
    ) -> None:
        created = await client.post("/datasets", json={"name": "Book", "criticality": 3})
        dataset_id = created.json()["id"]
        response = await reader.post(
            f"/datasets/{dataset_id}/amend",
            json={"reason": "because", "changes": {"criticality": 2}},
        )
        assert response.status_code == 403
        assert (await client.get(f"/datasets/{dataset_id}")).json()["criticality"] == 3


class TestNoScopesMeansNothing:
    async def test_an_unscoped_key_cannot_even_read(self, unscoped: httpx.AsyncClient) -> None:
        """ "No scopes recorded" is not "no restriction"."""
        response = await unscoped.get("/datasets")
        assert response.status_code == 403, response.text
        assert response.json()["context"]["held"] == "(none)"

    async def test_an_unscoped_key_cannot_write(self, unscoped: httpx.AsyncClient) -> None:
        assert (await unscoped.post("/datasets", json={"name": "x"})).status_code == 403


class TestTheWildcardStillWorks:
    async def test_a_star_key_does_everything(self, client: httpx.AsyncClient) -> None:
        """Issued as ["*"]. Without this the suite would pass by refusing
        everything, which proves nothing about the matcher."""
        assert (await client.get("/datasets")).status_code == 200
        assert (await client.post("/datasets", json={"name": "Star"})).status_code == 201
