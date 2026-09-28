"""Metadata: templates, values, business context, the rules they imply, and search.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

import pytest

from prama.core.errors import ValidationError
from prama.db import Database
from prama.pql import parse_control
from prama.semantic import metadata as md
from prama.semantic.services import metadata as service
from prama.semantic.services.datasets import DatasetService


def test_a_rule_may_only_use_placeholders_its_kind_can_fill() -> None:
    with pytest.raises(ValidationError, match="cannot fill"):
        md.parse_template(
            {
                "name": "t",
                "applies_to": "attribute",
                "fields": [
                    {"name": "f", "kind": "flag", "rules": [{"pql": "CHECK x IN {{ values }}"}]}
                ],
            }
        )
    with pytest.raises(ValidationError, match="cannot name an attribute"):
        md.parse_template(
            {
                "name": "t",
                "applies_to": "dataset",
                "fields": [
                    {
                        "name": "f",
                        "kind": "flag",
                        "rules": [{"pql": "CHECK {{ dataset }}.{{ attribute }} IS NOT NULL"}],
                    }
                ],
            }
        )
    with pytest.raises(ValidationError, match="unknown kind"):
        md.parse_template(
            {"name": "t", "applies_to": "dataset", "fields": [{"name": "f", "kind": "json"}]}
        )


@pytest.mark.parametrize(
    ("kind", "raw", "stored"),
    [
        ("number", "12", 12),
        ("flag", "yes", True),
        ("list", "USD, EUR", ["USD", "EUR"]),
        ("day", "2026-09-27", "2026-09-27"),
        ("columns", "a,b", ["a", "b"]),
        ("text", " x ", "x"),
    ],
)
def test_values_are_checked_against_their_kind(kind: str, raw: str, stored: Any) -> None:
    assert md.coerce(md.FieldSpec("f", kind), raw) == stored
    if kind in ("number", "flag", "day", "columns"):
        with pytest.raises(ValidationError, match="not a valid"):
            md.coerce(md.FieldSpec("f", kind), "not it; at all!")


def test_a_value_cannot_inject_pql() -> None:
    field = md.FieldSpec("allowed", "list")
    rule = md.Rule(pql="CHECK {{ dataset }}.{{ attribute }} IN {{ values }}")
    pql = md.render(rule, field, ["USD", "x') OR (1=1"], dataset="trades", attribute="ccy")
    control = parse_control(pql or "")
    assert [item.value for item in control.assertion.argument.items] == ["USD", "x') OR (1=1"]


async def _estate(uow: Any, tenant_id: str) -> Any:
    service_ = DatasetService(uow)
    _, version = await service_.declare(tenant_id=tenant_id, name="Trades", criticality=4)
    for name in ("trade_id", "account_id", "ccy"):
        await service_.declare_attribute(
            tenant_id=tenant_id, dataset_id=version.dataset_id, name=name
        )
    await service.install_starter(uow, tenant_id, "data-quality-attribute")
    await service.install_starter(uow, tenant_id, "data-quality-dataset")
    return version


async def test_metadata_proposes_its_rules_and_retracts_them_when_changed(
    started_database: Database, tenant_id: str
) -> None:
    async with started_database.unit_of_work() as uow:
        await _estate(uow, tenant_id)
        await service.set_values(uow, tenant_id, "trades.account_id", {"mandatory": "yes"})
        await service.set_values(uow, tenant_id, "trades.ccy", {"allowed_values": "USD,EUR"})
        await service.set_values(
            uow, tenant_id, "trades", {"key": "trade_id", "source_system": "Murex"}
        )
        offered = {p["pql"] for p in await service.proposals(uow, tenant_id)}
        await service.set_values(uow, tenant_id, "trades.account_id", {"mandatory": "no"})
        after = {p["pql"] for p in await service.proposals(uow, tenant_id)}
        (template,) = await uow.metadata.templates(tenant_id, applies_to="attribute")
        field = next(f for f in await uow.metadata.fields(template.id) if f.name == "mandatory")
        history = await uow.metadata.history(
            tenant_id,
            field.id,
            (await service.resolve(uow, tenant_id, "trades.account_id"))[1].attribute_id,
        )
    assert offered == {
        "CHECK trades.account_id IS NOT NULL DIMENSION completeness",
        "CHECK trades.ccy IN ('USD', 'EUR') DIMENSION validity",
        "CHECK trades HAS UNIQUE KEY (trade_id) DIMENSION uniqueness",
    }
    assert (
        "CHECK trades.account_id IS NOT NULL DIMENSION completeness" not in after
    )  # "no" implies nothing
    assert [h.valid_to is None for h in history] == [False, True]  # kept, not overwritten


async def test_business_context_is_versioned_and_found_by_meaning(
    started_database: Database, tenant_id: str
) -> None:
    async with started_database.unit_of_work() as uow:
        await _estate(uow, tenant_id)
        await service.set_context(uow, tenant_id, "trades", "Executed trades booked by the desks.")
        await service.set_context(
            uow, tenant_id, "trades.ccy", "The settlement currency agreed with the counterparty."
        )
        await service.set_values(uow, tenant_id, "trades.account_id", {"source_system": "Calypso"})
        described = await service.describe(uow, tenant_id, "trades")
        by_context = await service.search(uow, tenant_id, "settlement currency")
        by_metadata = await service.search(uow, tenant_id, "calypso")
        versions = await uow.datasets.history(described["dataset_id"], tenant_id=tenant_id)
    assert described["business_context"] == "Executed trades booked by the desks."
    assert described["attributes"][2]["business_context"].startswith("The settlement currency")
    assert by_context[0]["name"] == "trades.ccy"
    assert by_metadata[0]["name"] == "trades.account_id"
    assert len(versions) == 2  # the context arrived as an amendment


async def test_an_unknown_field_is_refused_with_the_fields_there_are(
    started_database: Database, tenant_id: str
) -> None:
    async with started_database.unit_of_work() as uow:
        await _estate(uow, tenant_id)
        with pytest.raises(ValidationError, match=r"Fields: .*mandatory"):
            await service.set_values(uow, tenant_id, "trades.ccy", {"colour": "red"})


async def test_the_pages_and_the_queue_show_it(
    ui: Any, started_database: Database, tenant_id: str
) -> None:
    async with started_database.unit_of_work() as uow:
        await _estate(uow, tenant_id)
        await service.set_values(uow, tenant_id, "trades.account_id", {"mandatory": "yes"})
    assert "Install data-quality-attribute" in (await ui.get("/metadata")).text
    page = await ui.get("/metadata/d/trades")
    assert page.status_code == 200 and "CHECK trades.account_id IS NOT NULL" in page.text
    queue = await ui.get("/proposals")
    assert "CHECK trades.account_id IS NOT NULL" in queue.text
