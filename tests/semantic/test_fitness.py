"""Which dataset is fit for a purpose: BM25 without a model, embeddings with one.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama.db import Database
from prama.semantic.services import fitness
from prama.semantic.services.datasets import DatasetService


async def _estate(uow: Any, tenant_id: str) -> None:
    declare = DatasetService(uow)
    _, trades = await declare.declare(
        tenant_id=tenant_id,
        name="Trades",
        criticality=4,
        business_context="Executed trades booked by the desks, with settlement dates.",
    )
    await declare.declare_attribute(
        tenant_id=tenant_id,
        dataset_id=trades.dataset_id,
        name="settlement_date",
        definition="When the trade settles.",
    )
    await declare.declare_attribute(
        tenant_id=tenant_id,
        dataset_id=trades.dataset_id,
        name="notional",
        definition="Trade value.",
    )
    await declare.declare(
        tenant_id=tenant_id,
        name="Fx Rates",
        criticality=4,
        business_context="Closing exchange rates used to convert amounts into USD.",
    )


async def test_without_an_embedding_model_bm25_ranks_and_names_its_evidence(
    started_database: Database, tenant_id: str
) -> None:
    async with started_database.unit_of_work() as uow:
        await _estate(uow, tenant_id)
        answer = await fitness.rank(uow, tenant_id, "when do trades settle?")
    assert answer["ranked_by"] == "relevance"
    first = answer["matches"][0]
    assert first["name"] == "Trades" and first["evidence"][0] == "settlement_date"
    assert all(m["name"] != "Fx Rates" for m in answer["matches"])  # nothing in common


async def test_with_an_embedding_model_profiles_are_embedded_once_and_again_on_change(
    started_database: Database, tenant_id: str
) -> None:
    from prama.semantic.services.metadata import set_context

    async with started_database.unit_of_work() as uow:
        await _estate(uow, tenant_id)
        await uow.llm.add_provider(
            tenant_id,
            name="local",
            kind="scripted",
            hosting="self_hosted",
            settings={"embeddings": True},
        )
        await uow.llm.set_profile(tenant_id, "embed", [("local", "nomic-embed-text")])
        first = await fitness.rank(uow, tenant_id, "exchange rates to convert amounts")
        stored = await uow.semantic_index.vectors(tenant_id, "nomic-embed-text")
        calls_after_first = await uow.llm.count_calls(tenant_id)
        await fitness.rank(uow, tenant_id, "exchange rates to convert amounts")
        calls_after_second = await uow.llm.count_calls(tenant_id)
        await set_context(uow, tenant_id, "fx_rates", "Daily fixing rates from the ECB.")
        await fitness.rank(uow, tenant_id, "ecb fixing")
        restored = await uow.semantic_index.vectors(tenant_id, "nomic-embed-text")
        calls = await uow.llm.calls(tenant_id)
    assert first["ranked_by"] == "embeddings" and first["model"] == "nomic-embed-text"
    assert first["matches"][0]["name"] == "Fx Rates"
    assert len(stored) == 2
    assert calls_after_first == 2  # the question, then both profiles in one batch
    assert calls_after_second == 3  # only the question: nothing changed, nothing re-embedded
    fx_id = next(k for k in stored if stored[k][0] != restored[k][0])
    assert fx_id and len(restored) == 2  # only the changed profile got a new vector
    assert {c.purpose for c in calls} == {"embed"}


def test_an_openai_compatible_server_is_asked_for_embeddings() -> None:
    import json
    import urllib.request

    from prama.llm.providers import AzureOpenAiProvider, OpenAiCompatibleProvider
    from prama.llm.spi import Hosting

    seen: list[str] = []

    def opener(request: urllib.request.Request, timeout: float) -> bytes:
        seen.append(request.full_url)
        return json.dumps(
            {"data": [{"index": 1, "embedding": [0.0, 1.0]}, {"index": 0, "embedding": [1.0, 0.0]}]}
        ).encode()

    local = OpenAiCompatibleProvider(
        endpoint="http://localhost:11434", model="e", hosting=Hosting.SELF_HOSTED, opener=opener
    )
    assert local.embed_texts(["a", "b"]) == [[1.0, 0.0], [0.0, 1.0]]  # ordered by index
    azure = AzureOpenAiProvider(endpoint="https://x.openai.azure.com", model="emb", opener=opener)
    azure.embed_texts(["a", "b"])
    assert seen[0].endswith("/v1/embeddings")
    assert "/openai/deployments/emb/embeddings?api-version=" in seen[1]
