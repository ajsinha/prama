"""Delegates, domain packs and connectors through the SDK.

A delegate's path to running is vetted in the sandbox, proposed, and approved by
somebody other than its uploader; a try-out runs it exactly as a control would.
The pack's readers report what is wrong with a message; the connector catalogue
is derived from connector code, and a connection is tested, browsed and profiled
against a real SQLite file.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import prama_sdk as prama
import pytest
from prama_sdk import AsyncClient
from tests.sdk.test_knowledge import signed_in

from prama.db import Database

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "delegates"
GOOD = FIXTURES / "good" / "threshold_count.py"
ROWS = [{"id": 1, "amount": 50}, {"id": 2, "amount": 150}, {"id": 3, "amount": 250}]


# -- delegates -----------------------------------------------------------------


async def test_the_uploader_cannot_approve_their_own_delegate_but_a_second_admin_can(
    client: AsyncClient, started_database: Database, tenant_id: str
) -> None:
    upload = await client.delegates.upload(GOOD)
    assert (upload["name"], upload["version"], upload["state"]) == (
        "test.over_limit",
        "2",
        "proposed",
    )
    assert any("one pass" in f["name"] or "one pass" in str(f) for f in upload["findings"])

    with pytest.raises(prama.ForbiddenError, match="cannot approve their own"):
        await client.delegates.approve(upload["id"])
    assert (await client.delegates.get(upload["id"]))["state"] == "proposed"
    assert await client.delegates.uploads() == []  # nothing approved, nothing to pull

    bo = await signed_in(client, started_database, tenant_id, "bo", "admin")
    approved = await bo.delegates.approve(upload["id"], note="read it; one pass, no I/O")
    assert approved["state"] == "approved" and approved["decided_by"] != upload["submitted_by"]
    assert [u["id"] for u in await client.delegates.uploads()] == [upload["id"]]
    assert (await client.delegates.source(upload["id"])) == GOOD.read_text()
    await bo.close()


async def test_a_steward_may_upload_but_not_decide(
    client: AsyncClient, started_database: Database, tenant_id: str
) -> None:
    sam = await signed_in(client, started_database, tenant_id, "sam", "steward")
    upload = await sam.delegates.upload(GOOD)
    with pytest.raises(prama.ForbiddenError, match="control:approve"):
        await sam.delegates.reject(upload["id"])
    rejected = await client.delegates.reject(upload["id"], note="not now")
    assert rejected["state"] == "rejected"
    await sam.close()


async def test_a_refused_upload_says_why_and_is_not_stored(client: AsyncClient) -> None:
    impure = (FIXTURES / "impure" / "phones_home.py").read_bytes()
    with pytest.raises(prama.ValidationError, match="socket"):
        await client.delegates.upload(impure, filename="phones_home.py")
    assert (await client.delegates.list())["uploads"] == []


async def test_an_approved_delegate_runs_on_supplied_rows_as_a_control_would(
    client: AsyncClient, started_database: Database, tenant_id: str
) -> None:
    upload = await client.delegates.upload(GOOD)
    with pytest.raises(prama.PramaError):  # proposed is not approved: it cannot run
        await client.delegates.test("test.over_limit@2", ROWS, limit=100)
    bo = await signed_in(client, started_database, tenant_id, "bo", "admin")
    await bo.delegates.approve(upload["id"])
    tried = await client.delegates.test("test.over_limit@2", ROWS, limit=100)
    assert tried["control"] == "CHECK rows USING DELEGATE 'test.over_limit@2' (limit = 100)"
    assert tried["metrics"]["violating_rows"] == 2 and tried["verdict"] == "fail"
    assert tried["delegate"]["delegate_hash"] == upload["source_hash"]
    # The counterfactual: a limit nothing exceeds, and the same engine passes it.
    clean = await client.delegates.test("test.over_limit@2", ROWS, limit=1000)
    assert clean["metrics"]["violating_rows"] == 0 and clean["verdict"] == "pass"
    await bo.close()


# -- packs ---------------------------------------------------------------------


def _fix(body: str) -> str:
    from prama.packs.banking import fix

    raw = f"8=FIX.4.4\x019=0\x01{body}10=000\x01"
    raw = f"8=FIX.4.4\x019={fix.body_length(raw)}\x01{body}10=000\x01"
    return raw.replace("10=000", f"10={fix.checksum(raw)}")


async def test_a_malformed_fix_message_is_reported_with_its_defect(client: AsyncClient) -> None:
    whole = "35=D\x0149=S\x0156=T\x0111=ORD1\x0155=IBM\x0154=1\x0138=1\x0140=2\x01"
    clean = await client.packs.parse(_fix(whole))
    assert (clean["format"], clean["inferred"], clean["defects"]) == ("fix", True, [])

    no_side = whole.replace("54=1\x01", "")
    broken = await client.packs.parse(_fix(no_side))
    assert broken["defects"] and any("54" in d for d in broken["defects"])

    tampered = _fix(whole).replace("55=IBM", "55=IBX")  # the checksum no longer holds
    assert any(d.startswith("tag 10") for d in (await client.packs.parse(tampered))["defects"])

    with pytest.raises(prama.ValidationError, match="which format"):
        await client.packs.parse("just some notes about a payment")


async def test_the_pack_answers_what_it_does_not_claim(client: AsyncClient) -> None:
    listed = await client.packs.banking()
    assert set(listed["calendars"]) == {"TARGET2", "FederalReserve", "London", "NYSE"}
    claims = await client.packs.claims()
    assert claims["supported_not_discharged"] and claims["discharged"]
    calendar = await client.packs.calendar("TARGET2", year=2030)
    assert {"date": "2030-12-25", "weekday": "Wednesday"} in calendar["closures"]
    with pytest.raises(prama.ValidationError, match="no calendar"):
        await client.packs.calendar("TOKYO")
    exposure = await client.packs.concept("Exposure")
    assert "Gross notional is not exposure" in exposure["boundary"]
    recognised = await client.packs.recognise(["counterparty_id", "as_of_date", "exposure_amount"])
    assert "Exposure" in [c["concept"] for c in recognised["candidates"]]
    assert (await client.packs.recognise(["foo", "bar"]))["candidates"] == []
    soc2 = await client.packs.soc2()
    assert soc2["caveat"]


# -- connectors ----------------------------------------------------------------


async def test_listing_connectors_shows_what_sqlite_requires(client: AsyncClient) -> None:
    catalogue = {c["key"]: c for c in await client.connectors.list()}
    fields = {f["name"]: f for g in catalogue["sqlite"]["form"]["groups"] for f in g["fields"]}
    assert fields["database_path"]["required"] is True
    assert fields["include_views"]["required"] is False
    assert (await client.connectors.form("sqlite")) == catalogue["sqlite"]["form"]
    with pytest.raises(prama.NotFoundError):
        await client.connectors.form("no-such-connector")


async def test_a_connection_is_tested_browsed_and_profiled(
    client: AsyncClient, tmp_path: Path
) -> None:
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE trades (id INTEGER, ccy TEXT)")
        db.executemany(
            "INSERT INTO trades VALUES (?, ?)", [(i, "USD" if i % 4 else None) for i in range(40)]
        )
    connection = await client.connections.create(
        "desk", "sqlite", config={"database_path": str(source)}
    )
    tested = await client.connectors.test(connection["id"])
    assert tested["usable"] is True
    objects = await client.connectors.browse(connection["id"])
    assert [o["name"].split(".")[-1] for o in objects] == ["trades"]
    (run,) = await client.connectors.profile(connection["id"], ".".join(objects[0]["path"]))
    columns = {c["name"]: c for c in run["columns"]}
    assert set(columns) == {"id", "ccy"} and columns["ccy"]["nulls"] == 10

    missing = await client.connections.create(
        "gone", "sqlite", config={"database_path": str(tmp_path / "absent.db")}
    )
    assert (await client.connectors.test(missing["id"]))["usable"] is False
    with pytest.raises(prama.NotFoundError):
        await client.connectors.test("01NOSUCHCONNECTION000000000")
