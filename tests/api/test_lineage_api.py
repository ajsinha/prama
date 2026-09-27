"""Lineage ingestion over the API (E2) and impact over the API (E3).

The OpenLineage event is shaped as the OpenLineage 1.x spec's RunEvent with a
columnLineage facet, as Airflow and Spark emit it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama.db import Database

EVENT: dict[str, Any] = {
    "eventType": "COMPLETE",
    "eventTime": "2026-09-27T06:00:00.000Z",
    "producer": "https://github.com/OpenLineage/OpenLineage/tree/1.20.0/integration/airflow",
    "schemaURL": "https://openlineage.io/spec/2-0-2/OpenLineage.json#/$defs/RunEvent",
    "run": {"runId": "01926f5a-6d1e-7c3a-b2f7-3c1f0f9d2a11"},
    "job": {"namespace": "airflow", "name": "finrep.load_positions"},
    "inputs": [{"namespace": "postgres://prod:5432", "name": "raw.trades"}],
    "outputs": [
        {
            "namespace": "postgres://prod:5432",
            "name": "stg.positions",
            "facets": {
                "columnLineage": {
                    "_producer": "https://github.com/OpenLineage/OpenLineage",
                    "_schemaURL": "https://openlineage.io/spec/facets/1-2-0/ColumnLineageDatasetFacet.json",
                    "fields": {
                        "notional": {
                            "inputFields": [
                                {
                                    "namespace": "postgres://prod:5432",
                                    "name": "raw.trades",
                                    "field": "notional",
                                    "transformations": [
                                        {"type": "DIRECT", "subtype": "AGGREGATION"}
                                    ],
                                }
                            ]
                        },
                        "account": {
                            "inputFields": [
                                {
                                    "namespace": "postgres://prod:5432",
                                    "name": "raw.trades",
                                    "field": "account_id",
                                    "transformations": [{"type": "DIRECT", "subtype": "IDENTITY"}],
                                }
                            ]
                        },
                    },
                }
            },
        }
    ],
}


async def test_an_openlineage_event_lands_and_a_replay_does_not_duplicate(
    client: Any, started_database: Database, tenant_id: str
) -> None:
    first = await client.post("/lineage/openlineage", json=EVENT)
    assert first.status_code == 200, first.text
    assert first.json()["edges"] == 2
    again = await client.post("/lineage/openlineage", json=EVENT)
    assert again.status_code == 200
    async with started_database.unit_of_work() as uow:
        rows = await uow.lineage.edges(tenant_id, dataset="stg.positions")
    assert len(rows) == 2
    kinds = {(r.source_column, r.target_column): r.transform for r in rows}
    assert kinds[("notional", "notional")] == "aggregated"
    assert kinds[("account_id", "account")] == "identity"


async def test_impact_over_the_api(client: Any) -> None:
    await client.post("/lineage/openlineage", json=EVENT)
    reply = await client.get("/lineage/impact", params={"column": "raw.trades.account_id"})
    assert reply.status_code == 200
    assert reply.json()["reached"][0]["column"] == "stg.positions.account"


async def test_the_receiver_needs_the_write_scope(
    sqlite_config: Any, started_database: Database, tenant_id: str
) -> None:
    import httpx
    from httpx import ASGITransport
    from tests.api.conftest import issue_key

    from prama.api import create_app
    from prama.api.app import API_PREFIX

    key = await issue_key(
        started_database, tenant_id, principal="reader", scopes=["relationship:read"]
    )
    app = create_app(sqlite_config, database=started_database)
    async with (
        httpx.AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver" + API_PREFIX,
            headers={"Authorization": f"Bearer {key}"},
        ) as http,
        app.router.lifespan_context(app),
    ):
        assert (await http.post("/lineage/openlineage", json=EVENT)).status_code == 403
