"""Correlating datasets through shared meaning: groups, references, inconsistencies.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama.db import Database
from prama.pql import parse_control
from prama.semantic.correlate import AttributeFact, findings, groups, references
from prama.semantic.services import metadata as service
from prama.semantic.services.datasets import DatasetService


def _fact(ds: str, col: str, **kw: Any) -> AttributeFact:
    return AttributeFact(dataset=ds, attribute=col, **kw)


def test_a_shared_term_groups_and_the_key_owner_is_referenced() -> None:
    facts = [
        _fact("counterparties", "lei", terms=("LEI",), is_key=True, semantic_type="lei"),
        _fact("trades", "counterparty_lei", terms=("LEI",)),
        _fact("exposures", "cpty", terms=("LEI",), semantic_type="lei"),
    ]
    (group,) = groups(facts)
    assert group.by == "term" and len(group.members) == 3
    pql = sorted(r.pql.split(" BECAUSE")[0] for r in references(group))
    assert pql == [
        "CHECK exposures.cpty REFERENCES counterparties.lei",
        "CHECK trades.counterparty_lei REFERENCES counterparties.lei",
    ]
    assert all(parse_control(r.pql) for r in references(group))
    aspects = {f.aspect for f in findings(group)}
    assert "semantic type" in aspects  # validated as an LEI in two places, not in trades


def test_no_owner_or_two_owners_means_no_reference() -> None:
    shared = {"terms": ("Account",)}
    nobody = groups([_fact("a", "acct", **shared), _fact("b", "account", **shared)])
    both = groups(
        [_fact("a", "acct", is_key=True, **shared), _fact("b", "account", is_key=True, **shared)]
    )
    assert references(nobody[0]) == [] and references(both[0]) == []


def test_a_generic_type_groups_for_consistency_but_never_proposes_a_reference() -> None:
    facts = [
        _fact("trades", "ccy", semantic_type="currency", is_key=True, sensitivity="internal"),
        _fact("fx", "base", semantic_type="currency", sensitivity="confidential"),
    ]
    (group,) = groups(facts)
    assert references(group) == []
    assert [f.aspect for f in findings(group)] == ["sensitivity"]


def test_an_attribute_joins_only_its_strongest_group() -> None:
    facts = [
        _fact("a", "x", concept_property="P1", terms=("T",)),
        _fact("b", "y", concept_property="P1", terms=("T",)),
    ]
    assert [g.by for g in groups(facts)] == ["concept"]


async def test_the_estate_is_correlated_through_glossary_bindings(
    started_database: Database, tenant_id: str
) -> None:
    async with started_database.unit_of_work() as uow:
        declare = DatasetService(uow)
        _, cp = await declare.declare(tenant_id=tenant_id, name="Counterparties", criticality=4)
        _, tr = await declare.declare(tenant_id=tenant_id, name="Trades", criticality=4)
        await declare.declare_attribute(
            tenant_id=tenant_id,
            dataset_id=cp.dataset_id,
            name="lei",
            definition="The legal entity identifier.",
        )
        await declare.declare_attribute(
            tenant_id=tenant_id, dataset_id=tr.dataset_id, name="counterparty_lei"
        )
        await service.install_starter(uow, tenant_id, "data-quality-dataset")
        await service.install_starter(uow, tenant_id, "data-quality-attribute")
        await service.set_values(uow, tenant_id, "counterparties", {"key": "lei"})
        await service.set_values(uow, tenant_id, "trades.counterparty_lei", {"pii": "yes"})
        await service.set_values(uow, tenant_id, "counterparties.lei", {"pii": "no"})
        await uow.glossary.upsert(tenant_id, name="LEI", definition="Legal Entity Identifier")
        await uow.glossary.bind(tenant_id, "LEI", "attribute", "counterparties.lei")
        await uow.glossary.bind(tenant_id, "LEI", "attribute", "trades.counterparty_lei")
        result = await service.correlation(uow, tenant_id)
    assert result["groups"] == [
        {
            "meaning": "LEI",
            "by": "term",
            "members": ["counterparties.lei", "trades.counterparty_lei"],
        }
    ]
    (proposal,) = result["proposals"]
    assert proposal["pql"].startswith("CHECK trades.counterparty_lei REFERENCES counterparties.lei")
    aspects = {f["aspect"] for f in result["findings"]}
    assert {"pii", "description"} <= aspects
