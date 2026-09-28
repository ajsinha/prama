"""Finding data of interest: deterministic retrieval, a model that may only choose.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
from typing import Any

from prama.db import Database
from prama.semantic.services.datasets import DatasetService
from prama.semantic.services.finding import find_data


async def _estate(uow: Any, tenant_id: str) -> None:
    declare = DatasetService(uow)
    for name, context in (
        ("Trades", "Executed trades booked by the desks, with their settlement dates."),
        ("Fx Rates", "Closing exchange rates used to convert amounts into USD."),
        ("Payments", "Supplier payments released by accounts payable."),
    ):
        await declare.declare(
            tenant_id=tenant_id, name=name, business_context=context, criticality=4
        )


async def test_without_a_model_the_keyword_ranking_stands(
    started_database: Database, tenant_id: str
) -> None:
    async with started_database.unit_of_work() as uow:
        await _estate(uow, tenant_id)
        answer = await find_data(uow, tenant_id, "which data has settlement dates?")
    assert answer["ranked_by"] == "keywords"
    assert answer["matches"][0]["name"] == "Trades"
    assert "no LLM is configured" in answer["note"]


async def test_a_model_ranks_and_explains_and_cannot_invent_a_dataset(
    started_database: Database, tenant_id: str
) -> None:
    reply = json.dumps(
        {
            "matches": [
                {"name": "Fx Rates", "why": "Conversion into USD needs the closing rates."},
                {"name": "Ledger", "why": "An invented dataset."},
                {"name": "Trades", "why": "Amounts to convert."},
            ]
        }
    )
    async with started_database.unit_of_work() as uow:
        await _estate(uow, tenant_id)
        await uow.llm.add_provider(
            tenant_id,
            name="local",
            kind="scripted",
            hosting="self_hosted",
            settings={"answers": [reply]},
        )
        await uow.llm.set_profile(tenant_id, "discover", [("local", "qwen")])
        answer = await find_data(uow, tenant_id, "convert trade amounts to USD")
        calls = await uow.llm.calls(tenant_id)
    assert answer["ranked_by"] == "model"
    assert [m["name"] for m in answer["matches"]] == ["Fx Rates", "Trades"]  # Ledger dropped
    assert answer["matches"][0]["why"].startswith("Conversion")
    assert calls[0].purpose == "discover"  # recorded like any model call


async def test_the_search_box_uses_it(ui: Any, started_database: Database, tenant_id: str) -> None:
    async with started_database.unit_of_work() as uow:
        await _estate(uow, tenant_id)
    page = await ui.get("/metadata?q=settlement")
    assert "Ranked by keywords" in page.text and "Trades" in page.text
