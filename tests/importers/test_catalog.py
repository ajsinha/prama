"""Glossary and lineage from Alation, Collibra and Manta: what came across, and what did not.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama.db import Database
from prama.importers import catalog
from prama.lineage.graph import Column, Edge, Transform

ALATION_TERMS = [
    {
        "id": 11,
        "title": "Exposure",
        "description": "<p>The amount at risk &amp; its currency.</p>",
        "custom_fields": [
            {"field_name": "Synonyms", "value": "EAD; exposure at default"},
            {"field_name": "Steward", "value": [{"otype": "user", "name": "a.roy"}]},
        ],
    },
    {"id": 12, "title": "", "description": "no title"},
]
ALATION_LINEAGE = [
    {
        "dataflow_id": "df1",
        "source_nodes": [{"otype": "attribute", "key": "7.stg.trades.notional"}],
        "target_nodes": [{"otype": "attribute", "key": "7.mart.positions.exposure"}],
    },
    {
        "dataflow_id": "df2",
        "source_nodes": [
            {"otype": "attribute", "key": "7.stg.a.x"},
            {"otype": "attribute", "key": "7.stg.a.y"},
        ],
        "target_nodes": [
            {"otype": "attribute", "key": "7.mart.b.x"},
            {"otype": "attribute", "key": "7.mart.b.y"},
        ],
    },
    {
        "dataflow_id": "df3",
        "source_nodes": [{"otype": "table", "key": "7.stg.a"}],
        "target_nodes": [{"otype": "table", "key": "7.mart.b"}],
    },
]
COLLIBRA = {
    "results": [
        {
            "id": "c-1",
            "name": "Counterparty",
            "type": {"name": "Business Term"},
            "domain": {"name": "Credit Risk"},
            "status": {"name": "Candidate"},
            "attributes": [{"type": {"name": "Definition"}, "value": "The party we face."}],
        },
        {"id": "c-2", "name": "risk_db", "type": {"name": "Database"}},
    ]
}
MANTA = {
    "nodes": [
        {"id": "s", "name": "stg", "type": "Schema"},
        {"id": "t1", "name": "trades", "type": "Table", "parent": "s"},
        {"id": "c1", "name": "notional", "type": "Column", "parent": "t1"},
        {"id": "m", "name": "mart", "type": "Schema"},
        {"id": "t2", "name": "positions", "type": "Table", "parent": "m"},
        {"id": "c2", "name": "exposure", "type": "Column", "parent": "t2"},
        {"id": "c3", "name": "status", "type": "Column", "parent": "t1"},
    ],
    "edges": [
        {"source": "c1", "target": "c2", "type": "DIRECT"},
        {"source": "c3", "target": "c2", "type": "FILTER"},
        {"source": "t1", "target": "t2", "type": "DIRECT"},
    ],
}


def test_alation_terms_are_cleaned_and_a_nameless_one_is_dropped_by_name() -> None:
    result = catalog.alation_terms(ALATION_TERMS)
    (term,) = result.terms
    assert term.definition == "The amount at risk & its currency."
    assert term.synonyms == ("EAD", "exposure at default") and term.steward == "a.roy"
    assert [d.source for d in result.dropped] == ["term 12"]


def test_alation_lineage_never_invents_a_pairing() -> None:
    result = catalog.alation_lineage(ALATION_LINEAGE)
    assert [(e.source.qualified, e.target.qualified) for e in result.edges] == [
        ("stg.trades.notional", "mart.positions.exposure")
    ]
    reasons = " ".join(d.reason for d in result.dropped)
    assert "which feeds which is not stated" in reasons and "not column-level" in reasons


def test_collibra_takes_business_terms_and_names_what_it_leaves() -> None:
    result = catalog.collibra_terms(COLLIBRA)
    (term,) = result.terms
    assert (term.name, term.status, term.domain) == ("Counterparty", "candidate", "Credit Risk")
    assert term.definition == "The party we face."
    assert "a Database asset" in result.dropped[0].reason


def test_manta_edges_between_columns_keep_their_kind() -> None:
    result = catalog.manta(MANTA)
    kinds = {(e.source.qualified, e.transform.value) for e in result.edges}
    assert kinds == {("stg.trades.notional", "derived"), ("stg.trades.status", "filter")}
    assert result.dropped[0].reason == "not between two columns"


async def test_ingest_binds_by_name_and_a_reimport_updates_rather_than_duplicates(
    started_database: Database, tenant_id: str
) -> None:
    from prama.semantic.services import ConceptService

    async with started_database.unit_of_work() as uow:
        await ConceptService(uow).declare_concept(tenant_id=tenant_id, name="Exposure")
        first = await catalog.ingest(uow, tenant_id, catalog.alation_terms(ALATION_TERMS))
        renamed = [{**ALATION_TERMS[0], "title": "Exposure", "description": "Updated."}]
        again = await catalog.ingest(uow, tenant_id, catalog.alation_terms(renamed))
        (term,) = await uow.glossary.terms(tenant_id)
        (binding,) = await uow.glossary.bindings(tenant_id, term_id=term.id)
        found = await uow.glossary.search(tenant_id, "exposure at default")
    assert first["terms_created"] == 1 and first["bound_to_concepts"] == 1
    assert again["terms_updated"] == 1 and term.definition == "Updated."
    assert binding.object_kind == "concept" and binding.how == "name_match"
    assert [t.name for t in found] == ["Exposure"]  # found by synonym


async def test_imported_lineage_sits_beside_ours_and_disagreements_are_named(
    started_database: Database, tenant_id: str
) -> None:
    async with started_database.unit_of_work() as uow:
        ours = await uow.lineage.ensure_source(tenant_id, "warehouse", kind="sql")
        await uow.lineage.record_run(
            tenant_id,
            ours,
            [
                (
                    [
                        Edge(
                            Column("stg.fx", "rate"),
                            Column("mart.positions", "exposure"),
                            Transform.DERIVED,
                        )
                    ],
                    "parsed:sqlglot",
                    "parsed",
                    1.0,
                )
            ],
            [],
            statements=1,
            understood=1.0,
        )
        report = await catalog.ingest(uow, tenant_id, catalog.manta(MANTA), source="manta")
        conflicts = await catalog.disagreements(uow, tenant_id)
        methods = {e.method for e in await uow.lineage.edges(tenant_id)}
    assert report["edges_recorded"] == 2 and len(report["dropped"]) == 1
    assert methods == {"parsed:sqlglot", "imported:manta"}
    (conflict,) = conflicts
    assert conflict["column"] == "mart.positions.exposure"
    assert conflict["theirs_only"] == ["stg.trades.notional", "stg.trades.status"]
    assert conflict["ours_only"] == ["stg.fx.rate"]


async def test_the_glossary_page_lists_and_searches(ui: Any) -> None:
    page = await ui.get("/glossary?q=nothing-like-this")
    assert page.status_code == 200 and "No term mentions" in page.text
