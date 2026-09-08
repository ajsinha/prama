"""The semantic-layer HTTP API.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import httpx
from httpx import ASGITransport

from prama.api import API_PREFIX, create_app
from prama.core.config import Configuration
from prama.db import Database

TENANT_HEADER = "X-Prama-Tenant"


class TestMeta:
    async def test_health_touches_the_database(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.json()["dialect"] == "sqlite"

    async def test_capabilities_are_honest_about_what_does_not_exist_yet(
        self, client: httpx.AsyncClient
    ) -> None:
        features = (await client.get("/capabilities")).json()["features"]
        assert features["semantic_layer"] is True
        assert features["bitemporal_history"] is True
        # A client that trusts this and finds it wrong will never trust it again.
        assert features["execution"] is False
        assert features["evidence"] is False

    async def test_every_response_carries_a_correlation_id(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/health")
        assert response.headers["X-Correlation-Id"]

    async def test_a_supplied_correlation_id_is_reused(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/health", headers={"X-Correlation-Id": "abc-123"})
        assert response.headers["X-Correlation-Id"] == "abc-123"

    async def test_openapi_is_published(self, client: httpx.AsyncClient) -> None:
        spec = (await client.get("/openapi.json")).json()
        assert spec["info"]["title"] == "Prama"
        assert f"{API_PREFIX}/datasets" in spec["paths"]


class TestDatasets:
    async def test_declare_and_read_back(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            "/datasets",
            json={
                "name": "Positions EOD",
                "description": "Daily end-of-day positions.",
                "owner_id": "alice",
                "grain": {
                    "attributes": ["account_id", "instrument_id", "as_of_date"],
                    "statement": "one position per account per instrument per business day",
                },
                "rhythm": {
                    "frequency": "daily",
                    "arrival_by": "06:30",
                    "calendar": "TARGET2",
                    "volume_drivers": ["trading_days", "month_end"],
                },
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["slug"] == "positions_eod"
        assert body["is_bound"] is False
        assert body["grain"]["attributes"][0] == "account_id"
        assert body["meta"]["version"] == 1
        assert body["meta"]["is_current"] is True
        assert body["meta"]["authored_by"] == "alice"

        fetched = await client.get(f"/datasets/{body['id']}")
        assert fetched.json()["name"] == "Positions EOD"

    async def test_a_duplicate_name_is_a_409_with_a_remedy(self, client: httpx.AsyncClient) -> None:
        await client.post("/datasets", json={"name": "Positions"})
        response = await client.post("/datasets", json={"name": "positions"})
        assert response.status_code == 409
        problem = response.json()
        assert problem["code"] == "ENTITY.CONFLICT"
        assert problem["remedy"]  # what to do next, not just what went wrong
        assert response.headers["content-type"].startswith("application/problem+json")

    async def test_tier_one_without_approval_is_422_naming_the_requirement(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.post("/datasets", json={"name": "FRTB Feeder", "criticality": 1})
        assert response.status_code == 422
        assert "approval" in response.json()["title"]

    async def test_an_unknown_field_is_rejected_not_silently_dropped(
        self, client: httpx.AsyncClient
    ) -> None:
        # A typo the caller believes they set is the worst possible outcome.
        response = await client.post("/datasets", json={"name": "X", "criticallity": 1})
        assert response.status_code == 422

    async def test_a_missing_dataset_is_404_with_a_remedy(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/datasets/01AAAAAAAAAAAAAAAAAAAAAAAA")
        assert response.status_code == 404
        assert response.json()["remedy"]

    async def test_a_missing_tenant_header_is_refused(
        self, sqlite_config: Configuration, started_database: Database
    ) -> None:
        app = create_app(sqlite_config, database=started_database)
        async with (
            httpx.AsyncClient(
                transport=ASGITransport(app=app), base_url="http://testserver" + API_PREFIX
            ) as http,
            app.router.lifespan_context(app),
        ):
            response = await http.get("/datasets")
            assert response.status_code == 422
            assert "tenant" in response.json()["title"].lower()

    async def test_listing_filters_by_unbound_and_criticality(
        self, client: httpx.AsyncClient
    ) -> None:
        await client.post("/datasets", json={"name": "Unbound One"})
        await client.post(
            "/datasets",
            json={"name": "Bound One", "shape": "table", "criticality": 3},
        )
        unbound = (await client.get("/datasets", params={"unbound": True})).json()
        assert [d["name"] for d in unbound["items"]] == ["Unbound One"]
        tier3 = (await client.get("/datasets", params={"criticality": 3})).json()
        assert [d["name"] for d in tier3["items"]] == ["Bound One"]


class TestBitemporalApi:
    async def test_amend_then_query_both_time_axes(self, client: httpx.AsyncClient) -> None:
        # Backdated, as a real declaration usually is: this has been true since
        # January, even though someone only wrote it down today.
        created = (
            await client.post(
                "/datasets",
                json={"name": "Positions", "valid_from": "2026-01-01T00:00:00Z"},
            )
        ).json()
        dataset_id = created["id"]

        amended = await client.post(
            f"/datasets/{dataset_id}/amend",
            json={
                "reason": "grain changed when instrument splits were introduced",
                "effective_from": "2026-04-01T00:00:00Z",
                "changes": {"purpose": "post-split"},
            },
        )
        assert amended.status_code == 200
        assert amended.json()["meta"]["version"] == 2

        before = await client.get(
            f"/datasets/{dataset_id}", params={"valid_at": "2026-02-01T00:00:00Z"}
        )
        assert before.json()["purpose"] == ""
        after = await client.get(f"/datasets/{dataset_id}")
        assert after.json()["purpose"] == "post-split"

    async def test_an_amendment_without_a_reason_is_refused(
        self, client: httpx.AsyncClient
    ) -> None:
        created = (await client.post("/datasets", json={"name": "Positions"})).json()
        response = await client.post(
            f"/datasets/{created['id']}/amend", json={"reason": "", "changes": {}}
        )
        assert response.status_code == 422

    async def test_history_shows_every_version(self, client: httpx.AsyncClient) -> None:
        created = (await client.post("/datasets", json={"name": "Positions"})).json()
        await client.post(
            f"/datasets/{created['id']}/amend",
            json={"reason": "renamed upstream", "changes": {"purpose": "x"}},
        )
        await client.post(
            f"/datasets/{created['id']}/correct",
            json={"reason": "description was wrong", "changes": {"description": "y"}},
        )
        history = (await client.get(f"/datasets/{created['id']}/history")).json()
        assert len(history) == 3
        superseded = [h for h in history if h["meta"]["superseded_at"]]
        closed = [h for h in history if h["meta"]["valid_to"] and not h["meta"]["superseded_at"]]
        assert len(superseded) == 1  # a correction: never true
        assert len(closed) == 1  # an amendment: true of its own period


class TestAttributes:
    async def test_declare_an_attribute_with_its_interpretation(
        self, client: httpx.AsyncClient
    ) -> None:
        dataset = (await client.post("/datasets", json={"name": "Positions"})).json()
        response = await client.post(
            f"/datasets/{dataset['id']}/attributes",
            json={
                "name": "notional_amount",
                "definition": "Face value of the position.",
                "interpretation": "Gross of collateral; excludes intercompany.",
                "semantic_type": "monetary_amount",
                "is_cde": True,
                "obligations": ["FRTB"],
            },
        )
        assert response.status_code == 201
        assert response.json()["is_cde"] is True
        assert "intercompany" in response.json()["interpretation"]

        cdes = (await client.get("/critical-data-elements")).json()
        assert [a["name"] for a in cdes] == ["notional_amount"]


class TestRelationships:
    async def test_the_thirteen_kinds_are_offered_in_business_language(
        self, client: httpx.AsyncClient
    ) -> None:
        kinds = (await client.get("/relationship-kinds")).json()
        assert len(kinds) == 13
        reconciles = next(k for k in kinds if k["kind"] == "reconciles_with")
        assert reconciles["prompt"] == "these two should agree"
        assert "reconciliation" in reconciles["generates"]
        assert reconciles["needs_tolerance"] is True

    async def test_declare_a_reconciliation_and_see_what_it_generates(
        self, client: httpx.AsyncClient
    ) -> None:
        sub = (await client.post("/datasets", json={"name": "Sub-ledger"})).json()
        gl = (await client.post("/datasets", json={"name": "General Ledger"})).json()
        response = await client.post(
            "/relationships",
            json={
                "kind": "reconciles_with",
                "from_dataset_id": sub["id"],
                "to_dataset_id": gl["id"],
                "match_keys": [{"left": "account_code"}, {"left": "cost_centre"}],
                "compare": ["amount"],
                "tolerance": {"absolute": 1.0, "currency": "EUR"},
                "offset": {"amount": 1, "unit": "business_days", "calendar": "TARGET2"},
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "confirmed"
        assert "break_workflow" in body["generates"]
        assert body["tolerance"]["absolute"] == 1.0

    async def test_a_reconciliation_without_a_tolerance_is_refused_before_storage(
        self, client: httpx.AsyncClient
    ) -> None:
        sub = (await client.post("/datasets", json={"name": "Sub-ledger"})).json()
        gl = (await client.post("/datasets", json={"name": "General Ledger"})).json()
        response = await client.post(
            "/relationships",
            json={
                "kind": "reconciles_with",
                "from_dataset_id": sub["id"],
                "to_dataset_id": gl["id"],
                "match_keys": [{"left": "account_code"}],
                "compare": ["amount"],
            },
        )
        assert response.status_code == 422
        assert "tolerance" in response.json()["title"]
        assert "rounding" in response.json()["remedy"]

    async def test_relationships_are_listed_from_either_side(
        self, client: httpx.AsyncClient
    ) -> None:
        a = (await client.post("/datasets", json={"name": "A"})).json()
        b = (await client.post("/datasets", json={"name": "B"})).json()
        await client.post(
            "/relationships",
            json={
                "kind": "references",
                "from_dataset_id": a["id"],
                "to_dataset_id": b["id"],
                "match_keys": [{"left": "account_id"}],
            },
        )
        for dataset in (a, b):
            found = (
                await client.get("/relationships", params={"dataset_id": dataset["id"]})
            ).json()
            assert len(found) == 1


class TestEstate:
    async def test_maturity_explains_itself_and_says_what_to_do_next(
        self, client: httpx.AsyncClient
    ) -> None:
        await client.post(
            "/datasets",
            json={
                "name": "Positions",
                "owner_id": "alice",
                "grain": {"attributes": ["account_id"]},
            },
        )
        await client.post("/datasets", json={"name": "Trades"})
        body = (await client.get("/estate/maturity")).json()
        assert 0 < body["percent"] < 100
        assert len(body["components"]) == 6  # never a black box
        assert body["next_actions"]  # and always actionable

    async def test_coverage_gaps_name_what_is_declared_but_unreachable(
        self, client: httpx.AsyncClient
    ) -> None:
        await client.post("/datasets", json={"name": "Declared Only"})
        gaps = (await client.get("/estate/coverage-gaps")).json()
        assert gaps["unbound"] == ["Declared Only"]
        assert gaps["unowned"] == ["Declared Only"]

    async def test_conflicts_are_empty_on_a_consistent_estate(
        self, client: httpx.AsyncClient
    ) -> None:
        assert (await client.get("/estate/conflicts")).json() == []
