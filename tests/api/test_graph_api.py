"""Concepts, journeys, connections and bindings over HTTP.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import httpx


async def _dataset(client: httpx.AsyncClient, name: str) -> dict:
    return (await client.post("/datasets", json={"name": name})).json()


async def _connection(client: httpx.AsyncClient, name: str = "Risk warehouse") -> dict:
    return (
        await client.post(
            "/connections",
            json={
                "name": name,
                "source_type": "snowflake",
                "credential_ref": "vault://prama/risk-wh",
                "config": {"account": "acme", "warehouse": "RISK_WH"},
            },
        )
    ).json()


class TestConcepts:
    async def test_declare_a_concept_and_a_property(self, client: httpx.AsyncClient) -> None:
        concept = (await client.post("/concepts", json={"name": "Instrument"})).json()
        assert concept["name"] == "Instrument"

        prop = await client.post(
            f"/concepts/{concept['id']}/properties",
            json={"name": "ISIN", "semantic_type": "isin", "is_identifier": True},
        )
        assert prop.status_code == 201
        assert prop.json()["is_identifier"] is True
        assert prop.json()["mapped_attribute_count"] == 0

    async def test_a_duplicate_concept_is_refused(self, client: httpx.AsyncClient) -> None:
        await client.post("/concepts", json={"name": "Party"})
        response = await client.post("/concepts", json={"name": "Party"})
        assert response.status_code == 409
        assert response.json()["remedy"]

    async def test_mapping_shows_what_the_mapping_bought(self, client: httpx.AsyncClient) -> None:
        concept = (await client.post("/concepts", json={"name": "Party"})).json()
        prop = (
            await client.post(
                f"/concepts/{concept['id']}/properties",
                json={"name": "LEI", "semantic_type": "lei", "is_identifier": True},
            )
        ).json()

        for name in ("Exposures", "Counterparties"):
            dataset = await _dataset(client, name)
            attribute = (
                await client.post(
                    f"/datasets/{dataset['id']}/attributes",
                    json={"name": "counterparty_lei", "semantic_type": "lei"},
                )
            ).json()
            mapped = await client.post(
                f"/attributes/{attribute['id']}/mapping", json={"property_id": prop["id"]}
            )
            assert mapped.status_code == 200

        properties = (await client.get(f"/concepts/{concept['id']}/properties")).json()
        # One control authored here reaches both.
        assert properties[0]["mapped_attribute_count"] == 2

    async def test_mapping_to_a_missing_property_is_refused(
        self, client: httpx.AsyncClient
    ) -> None:
        dataset = await _dataset(client, "Positions")
        attribute = (
            await client.post(f"/datasets/{dataset['id']}/attributes", json={"name": "lei"})
        ).json()
        response = await client.post(
            f"/attributes/{attribute['id']}/mapping",
            json={"property_id": "01AAAAAAAAAAAAAAAAAAAAAAAA"},
        )
        assert response.status_code == 404


class TestJourneys:
    async def test_a_journey_may_contain_a_black_box(self, client: httpx.AsyncClient) -> None:
        trades = await _dataset(client, "Trades")
        response = await client.post(
            "/journeys",
            json={
                "name": "Trade capture to FRTB",
                "steps": [
                    {"kind": "dataset", "dataset_id": trades["id"]},
                    {
                        "kind": "black_box",
                        "description": "Overnight COBOL enrichment on the mainframe",
                        "expected_latency_seconds": 5400,
                    },
                ],
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["slug"] == "trade_capture_to_frtb"
        assert body["step_count"] == 2
        assert body["steps"][1]["kind"] == "black_box"

    async def test_a_black_box_with_no_description_is_refused(
        self, client: httpx.AsyncClient
    ) -> None:
        # The step Prama cannot read is exactly the one that needs a sentence.
        response = await client.post(
            "/journeys",
            json={"name": "Opaque", "steps": [{"kind": "black_box"}]},
        )
        assert response.status_code == 422
        assert "description" in response.json()["title"]

    async def test_a_dataset_step_pointing_nowhere_is_refused(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.post(
            "/journeys",
            json={
                "name": "Broken",
                "steps": [{"kind": "dataset", "dataset_id": "01AAAAAAAAAAAAAAAAAAAAAAAA"}],
            },
        )
        assert response.status_code == 404

    async def test_steps_are_renumbered_so_ordinal_matches_position(
        self, client: httpx.AsyncClient
    ) -> None:
        a, b = await _dataset(client, "A"), await _dataset(client, "B")
        journey = (
            await client.post(
                "/journeys",
                json={
                    "name": "Chain",
                    "steps": [
                        {"kind": "dataset", "dataset_id": a["id"]},
                        {"kind": "dataset", "dataset_id": b["id"]},
                    ],
                },
            )
        ).json()
        reordered = await client.put(
            f"/journeys/{journey['id']}/steps",
            json={
                "reason": "the enrichment moved before the load",
                "steps": [
                    {"kind": "dataset", "dataset_id": b["id"]},
                    {"kind": "dataset", "dataset_id": a["id"]},
                ],
            },
        )
        steps = reordered.json()["steps"]
        assert [s["ordinal"] for s in steps] == [0, 1]
        assert steps[0]["dataset_id"] == b["id"]

    async def test_journeys_are_findable_by_the_dataset_they_contain(
        self, client: httpx.AsyncClient
    ) -> None:
        trades = await _dataset(client, "Trades")
        await client.post(
            "/journeys",
            json={"name": "FRTB", "steps": [{"kind": "dataset", "dataset_id": trades["id"]}]},
        )
        found = (await client.get("/journeys", params={"dataset_id": trades["id"]})).json()
        assert [j["slug"] for j in found] == ["frtb"]


class TestConnections:
    async def test_configure_a_connection_with_a_vault_reference(
        self, client: httpx.AsyncClient
    ) -> None:
        body = await _connection(client)
        assert body["credential_ref"] == "vault://prama/risk-wh"
        assert body["health_state"] == "unknown"
        assert body["is_usable"] is False

    async def test_a_secret_written_inline_is_refused(self, client: httpx.AsyncClient) -> None:
        # Accepting one 'just this once' is how a credential reaches a Git export.
        response = await client.post(
            "/connections",
            json={
                "name": "Careless",
                "source_type": "postgres",
                "config": {"host": "db", "password": "hunter2"},
            },
        )
        assert response.status_code == 422
        assert "secret" in response.json()["title"]
        assert "credential_ref" in response.json()["remedy"]

    async def test_a_duplicate_connection_name_is_refused(self, client: httpx.AsyncClient) -> None:
        await _connection(client)
        response = await client.post(
            "/connections", json={"name": "Risk warehouse", "source_type": "snowflake"}
        )
        assert response.status_code == 409


class TestBindings:
    async def test_binding_a_dataset_makes_it_no_longer_unbound(
        self, client: httpx.AsyncClient
    ) -> None:
        dataset = await _dataset(client, "Positions EOD")
        connection = await _connection(client)
        assert dataset["is_bound"] is False

        binding = await client.post(
            f"/datasets/{dataset['id']}/bindings",
            json={
                "connection_id": connection["id"],
                "physical_ref": {"schema": "RISK", "object": "POSITIONS_EOD"},
                "shape": "table",
            },
        )
        assert binding.status_code == 201
        assert binding.json()["drift_state"] == "intact"

        # The declaration and the shape must agree, or coverage reporting lies.
        refreshed = (await client.get(f"/datasets/{dataset['id']}")).json()
        assert refreshed["is_bound"] is True
        assert refreshed["shape"] == "table"
        gaps = (await client.get("/estate/coverage-gaps")).json()
        assert gaps["unbound"] == []

    async def test_binding_through_a_missing_connection_is_refused(
        self, client: httpx.AsyncClient
    ) -> None:
        dataset = await _dataset(client, "Positions")
        response = await client.post(
            f"/datasets/{dataset['id']}/bindings",
            json={
                "connection_id": "01AAAAAAAAAAAAAAAAAAAAAAAA",
                "physical_ref": {"object": "X"},
            },
        )
        assert response.status_code == 404
        assert "connection" in response.json()["title"]

    async def test_drifted_bindings_are_listed_for_the_declaration_owner(
        self, client: httpx.AsyncClient
    ) -> None:
        dataset = await _dataset(client, "Positions")
        connection = await _connection(client)
        await client.post(
            f"/datasets/{dataset['id']}/bindings",
            json={"connection_id": connection["id"], "physical_ref": {"object": "P"}},
        )
        assert (await client.get("/bindings/drifted")).json() == []

    async def test_an_attribute_binding_carries_its_transform(
        self, client: httpx.AsyncClient
    ) -> None:
        dataset = await _dataset(client, "Positions")
        connection = await _connection(client)
        attribute = (
            await client.post(f"/datasets/{dataset['id']}/attributes", json={"name": "notional"})
        ).json()
        binding = (
            await client.post(
                f"/datasets/{dataset['id']}/bindings",
                json={
                    "connection_id": connection["id"],
                    "attribute_id": attribute["id"],
                    "physical_ref": {"column": "NOTNL_AMT"},
                    "transform": "CAST(NOTNL_AMT AS DECIMAL(18,2))",
                },
            )
        ).json()
        assert binding["target_kind"] == "attribute"
        assert binding["transform"].startswith("CAST(")
