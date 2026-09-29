"""Data contracts through the SDK: the build gate, the keyed diff, import and export.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.sdk.test_reconciliation import _signed_in_as

import prama.sdk as prama
from prama.db import Database
from prama.sdk import AsyncClient

CONTRACT = {
    "apiVersion": "3.0.0",
    "kind": "DataContract",
    "dataProduct": "positions",
    "criticality": "critical",
    "description": {"purpose": "EOD positions", "usage": "Risk"},
    "schema": [
        {
            "name": "positions_eod",
            "properties": [
                {"name": "account_id", "logicalType": "string", "required": True},
                {
                    "name": "notional",
                    "logicalType": "number",
                    "required": True,
                    "quality": [{"rule": "nullCount", "mustBe": 0}],
                },
            ],
        }
    ],
}
GOOD = [{"account_id": "A1", "notional": 10}, {"account_id": "A2", "notional": 20}]


async def test_a_clean_file_passes_the_gate(client: AsyncClient) -> None:
    result = await client.contracts.check(CONTRACT, GOOD)
    assert result["checked"] and not result["breached"]
    assert result["rows"] == 2
    assert result["missing_columns"] == result["mandatory_with_nulls"] == []


async def test_a_planted_breach_is_returned_not_raised(client: AsyncClient) -> None:
    planted = [{"account_id": "A1", "notional": 10}, {"account_id": None, "notional": 20}]
    result = await client.contracts.check(CONTRACT, planted)
    assert result["breached"] and result["mandatory_with_nulls"] == ["account_id"]

    dropped = await client.contracts.check(CONTRACT, [{"account_id": "A1"}])
    assert dropped["breached"] and dropped["missing_columns"] == ["notional"]


async def test_an_added_column_breaches_unless_additions_are_allowed(client: AsyncClient) -> None:
    extra = [{"account_id": "A1", "notional": 10, "desk": "EQ"}]
    blocked = await client.contracts.check(CONTRACT, extra)
    allowed = await client.contracts.check(CONTRACT, extra, allow_additions=True)
    assert blocked["breached"] and blocked["unexpected_columns"] == ["desk"]
    assert not allowed["breached"] and allowed["unexpected_columns"] == ["desk"]


async def test_no_rows_is_never_a_pass(client: AsyncClient) -> None:
    result = await client.contracts.check(CONTRACT, [])
    assert result["breached"] and not result["checked"]


async def test_files_are_read_by_their_suffix(client: AsyncClient, tmp_path: Path) -> None:
    import yaml

    (tmp_path / "contract.yaml").write_text(yaml.safe_dump(CONTRACT))
    (tmp_path / "rows.csv").write_text("account_id,notional\nA1,10\n,20\n")
    result = await client.contracts.check(tmp_path / "contract.yaml", tmp_path / "rows.csv")
    assert result["contract"] == "contract.yaml"
    assert result["breached"] and result["mandatory_with_nulls"] == ["account_id"]
    lines = b'{"account_id": "A1", "notional": 1}\n{"account_id": "A2", "notional": 2}\n'
    assert not (await client.contracts.check(CONTRACT, ("rows.jsonl", lines)))["breached"]


async def test_a_check_that_cannot_be_made_is_an_error_not_a_breach(client: AsyncClient) -> None:
    with pytest.raises(prama.ValidationError, match="declares no schema"):
        await client.contracts.check({"apiVersion": "3.0.0", "kind": "DataContract"}, GOOD)
    with pytest.raises(prama.ValidationError, match="not valid JSON"):
        await client.contracts.check(CONTRACT, ("rows.json", b"[{"))


async def test_the_diff_finds_the_changed_row_by_its_key(client: AsyncClient) -> None:
    before = [
        {"id": 1, "ccy": "EUR", "amount": 10},
        {"id": 2, "ccy": "USD", "amount": 20},
        {"id": 3, "ccy": "GBP", "amount": 30},
    ]
    after = [
        {"id": 3, "ccy": "GBP", "amount": 30},
        {"id": 2, "ccy": "USD", "amount": 25},
        {"id": 4, "ccy": "JPY", "amount": 40},
    ]
    found = await client.contracts.diff(before, after, key=["id"])
    assert found["comparable"] and not found["identical"]
    assert (found["added"], found["removed"], found["changed"], found["unchanged"]) == (1, 1, 1, 1)
    assert found["columns_that_changed"] == ["amount"]
    (change,) = found["changed_examples"]
    assert "2" in change and "amount" in change
    ignoring = await client.contracts.diff(before, after, key=["id"], ignore=["amount"])
    assert ignoring["changed"] == 0
    # Without a key nothing says which row is which, and the diff says so.
    unkeyed = await client.contracts.diff(before, after)
    assert not unkeyed["comparable"] and unkeyed["changed"] == 0


async def test_import_reports_the_quality_checks_and_stores_nothing(client: AsyncClient) -> None:
    read = await client.contracts.read(CONTRACT)
    assert read["imported"] and read["dataset"]["name"] == "positions_eod"
    assert [a["name"] for a in read["dataset"]["attributes"]] == ["account_id", "notional"]
    assert read["quality"]["controls"], read["quality"]
    assert (await client.datasets.list())["items"] == []
    with pytest.raises(prama.ValidationError, match="does not hold a contract"):
        await client.contracts.read(("contract.json", json.dumps([1, 2]).encode()))


async def test_a_declared_dataset_exports_as_a_contract_that_reads_back(
    client: AsyncClient,
) -> None:
    declared = await client.datasets.declare("Trades", description="Executed trades.")
    await client.datasets.add_attribute(declared["id"], "trade_id", optionality="mandatory")
    document = await client.contracts.export(declared["slug"])
    assert document["kind"] == "DataContract"
    read = await client.contracts.read(document)
    assert [a["name"] for a in read["dataset"]["attributes"]] == ["trade_id"]
    assert read["dataset"]["attributes"][0]["optionality"] == "mandatory"
    with pytest.raises(prama.NotFoundError):
        await client.contracts.export("no_such_dataset")


async def test_checking_a_contract_needs_its_own_scope(
    client: AsyncClient, started_database: Database, tenant_id: str
) -> None:
    """An auditor holds no `contract:check`; a steward does, and holds no `declaration:write`,
    which is the point — a key that gates a build must not be able to amend the estate."""
    auditor = await _signed_in_as(client, started_database, tenant_id, "aud", "auditor")
    with pytest.raises(prama.ForbiddenError):
        await auditor.contracts.check(CONTRACT, GOOD)
    steward = await _signed_in_as(client, started_database, tenant_id, "stu", "steward")
    assert not (await steward.contracts.check(CONTRACT, GOOD))["breached"]
    with pytest.raises(prama.ForbiddenError):
        await steward.datasets.declare("Anything")
    for c in (auditor, steward):
        await c.close()
