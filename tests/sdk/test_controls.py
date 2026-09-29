"""The case-study flow over the SDK: declare, derive, accept, run, read the verdicts.

The definition of done for the controls area of the API. Every stage a case
study walks — an estate, a dataset declared in business terms, Γ, acceptance, a
run against a registered connection the server reads itself — is driven through
`prama.sdk`, and what is asserted is the *executed verdict on real data*: the
planted defect is a ``fail`` in the recorded evidence, and a clean control over
the same rows is a ``pass``.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import sqlite3
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from tests.sdk.conftest import PASSWORD

import prama.sdk as prama
from prama.api import create_app
from prama.core.config import Configuration, ConfigurationBuilder
from prama.db import Database
from prama.sdk import AsyncClient
from prama.security.accounts import grant_roles

CURRENCIES = ["USD", "EUR", "GBP"]


@pytest.fixture
def sources(tmp_path: Path) -> Path:
    """Where the customer's data lives: the one directory a run may read."""
    root = tmp_path / "sources"
    root.mkdir()
    return root


@pytest.fixture
async def app(
    sqlite_config: Configuration, started_database: Database, sources: Path
) -> AsyncIterator[object]:
    config = (
        ConfigurationBuilder()
        .with_defaults(sqlite_config.raw())
        .with_mapping({"runs": {"roots": [str(sources)]}}, name="runs-test")
        .build()
    )
    application = create_app(config, database=started_database)
    async with application.router.lifespan_context(application):
        yield application


def write_book(path: Path, rows: list[tuple[str, str, float]]) -> Path:
    """The customer's side: a SQLite book of trades, written the way a system would."""
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE trades (trade_id TEXT, ccy TEXT, quantity REAL)")
    connection.executemany("INSERT INTO trades VALUES (?, ?, ?)", rows)
    connection.commit()
    connection.close()
    return path


CLEAN = [(f"T{n:03d}", CURRENCIES[n % 3], float(100 + n)) for n in range(20)]
#: One planted defect: a currency nobody agreed to. Quantities all in range.
PLANTED = [*CLEAN[:-1], ("T019", "XXX", 119.0)]


async def declare_trades(estate: AsyncClient) -> str:
    """A dataset described by its owner, in business terms, with no SQL."""
    dataset = await estate.datasets.declare(
        "trades",
        description="Executed trades, one row each.",
        criticality=3,
        shape="table",
        grain={"attributes": ["trade_id"], "statement": "one row per executed trade"},
        rhythm={"frequency": "daily", "arrival_by": "07:00"},
        tags=["MiFIR"],
    )
    await estate.datasets.add_attribute(
        dataset["id"], "trade_id", definition="The trade.", optionality="mandatory"
    )
    ccy = await estate.datasets.add_attribute(
        dataset["id"], "ccy", definition="Settlement currency.", codelist=CURRENCIES
    )
    quantity = await estate.datasets.add_attribute(
        dataset["id"], "quantity", definition="Units traded.", minimum=0, maximum=1_000_000
    )
    # The domains arrive as Γ will read them, not as the request spelled them.
    assert ccy["value_domain"]["kind"] == "codelist"
    assert ccy["value_domain"]["allowed_values"] == CURRENCIES
    assert quantity["value_domain"] == {
        **quantity["value_domain"],
        "kind": "range",
        "minimum": 0,
        "maximum": 1_000_000,
    }
    return str(dataset["id"])


def by_column(derived: dict[str, Any], column: str, word: str) -> dict[str, Any]:
    """The one derived control over *column* whose text says *word*."""
    found = [c for c in derived["controls"] if column in c["pql"] and word in c["pql"]]
    assert len(found) == 1, [c["pql"] for c in derived["controls"]]
    return found[0]


async def test_the_case_study_flow_over_the_sdk(client: AsyncClient, sources: Path) -> None:
    made = await client.tenants.create("acme-trades", "Acme Trades")
    estate = client.as_key(made["credentials"]["api_key"])
    try:
        dataset_id = await declare_trades(estate)

        # Γ, looked at before anything is stored: what it derives, and what not.
        preview = await estate.derive.preview_dataset(dataset_id)
        assert preview["controls"] and "unsatisfiable" in preview
        assert await estate.controls.list() == []

        derived = await estate.derive.dataset(dataset_id, accept=True, reason="for the study")
        assert derived["declared"] == len(derived["controls"]) == derived["active"]
        assert [c["identity"] for c in derived["controls"]] == [
            c["identity"] for c in preview["controls"]
        ]
        membership = by_column(derived, "ccy", "IN")
        bounds = by_column(derived, "quantity", "BETWEEN")
        active = await estate.controls.list(status="active")
        assert {c["id"] for c in active} >= {
            membership["control"]["id"],
            bounds["control"]["id"],
        }

        book = write_book(sources / "book.db", PLANTED)
        connection = await estate.connections.create(
            "trading book", "sqlite", config={"path": str(book)}
        )
        # A preview finds the defect too, and records nothing: no run, no evidence.
        tried = await estate.controls.preview(membership["pql"], connection["id"])
        assert tried["verdict"] == "fail" and tried["violating_rows"] == 1, tried["error"]
        assert await estate.runs.list() == []

        report = await estate.runs.start(connection["id"], datasets=["trades"])

        outcomes = {o["control_id"]: o for o in report["outcomes"]}
        assert report["failed_to_run"] == 0, [o["error"] for o in report["outcomes"]]
        failing = outcomes[membership["control"]["id"]]
        assert failing["verdict"] == "fail"
        assert failing["metrics"]["violating_rows"] == 1
        assert outcomes[bounds["control"]["id"]]["verdict"] == "pass"

        # And it is the *recorded* evidence that says so, not only the reply.
        run = await estate.runs.get(report["run_id"])
        recorded = {r["control_id"]: r["verdict"] for r in run["records"]}
        assert recorded[membership["control"]["id"]] == "fail"
        assert recorded[bounds["control"]["id"]] == "pass"
        assert run["status"] == "complete" and run["record_count"] == len(report["outcomes"])
        assert report["run_id"] in [r["run_id"] for r in await estate.runs.list()]
    finally:
        await estate.close()


async def test_the_same_controls_pass_on_clean_data(client: AsyncClient, sources: Path) -> None:
    """The counterfactual: without the planted row, the membership control passes."""
    made = await client.tenants.create("acme-clean", "Acme Clean")
    estate = client.as_key(made["credentials"]["api_key"])
    try:
        dataset_id = await declare_trades(estate)
        derived = await estate.derive.dataset(dataset_id, accept=True)
        membership = by_column(derived, "ccy", "IN")
        book = write_book(sources / "clean.db", CLEAN)
        connection = await estate.connections.create("clean", "sqlite", config={"path": str(book)})
        report = await estate.runs.start(connection["id"])
        verdicts = {o["control_id"]: o["verdict"] for o in report["outcomes"]}
        assert verdicts[membership["control"]["id"]] == "pass"
    finally:
        await estate.close()


async def test_a_connection_outside_the_roots_is_not_read(
    client: AsyncClient, tmp_path: Path
) -> None:
    """The server reads only what the operator allowed, whatever a connection says."""
    elsewhere = write_book(tmp_path / "elsewhere.db", PLANTED)
    connection = await client.connections.create(
        "elsewhere", "sqlite", config={"path": str(elsewhere)}
    )
    with pytest.raises(prama.ForbiddenError, match="outside the directories"):
        await client.runs.start(connection["id"])
    # Nor Prama's own database, by pointing a connection straight at it.
    own = await client.connections.create(
        "own store", "sqlite", config={"path": str(tmp_path / "prama-test.db")}
    )
    with pytest.raises(prama.ForbiddenError):
        await client.runs.start(own["id"])
    assert await client.runs.list() == []


async def test_a_steward_may_author_but_not_approve_or_run(
    client: AsyncClient, started_database: Database, tenant_id: str, sources: Path
) -> None:
    async with started_database.unit_of_work() as uow:
        principal = uow.principals.create(tenant_id=tenant_id, username="sam", display_name="Sam")
        uow.principals.set_password(principal, PASSWORD)
        await uow.flush()
        await grant_roles(uow, tenant_id, principal, ["steward"])
    anonymous = AsyncClient(app=client._app)
    key = (await anonymous.auth.token("sam", PASSWORD, tenant="acme-bank"))["api_key"]
    steward = anonymous.as_key(key)
    try:
        dataset = await client.datasets.declare("positions", criticality=4)
        proposed = await steward.controls.declare(
            "CHECK positions HAS UNIQUE KEY (account_id) SEVERITY minor"
        )
        assert proposed["status"] == "proposed"
        with pytest.raises(prama.ForbiddenError):
            await steward.controls.activate(proposed["id"], reason="my own")
        with pytest.raises(prama.ForbiddenError):
            await steward.derive.dataset(dataset["id"], accept=True)
        book = write_book(sources / "s.db", CLEAN)
        connection = await client.connections.create("s", "sqlite", config={"path": str(book)})
        with pytest.raises(prama.ForbiddenError):
            await steward.runs.start(connection["id"])
        # The checker half, done by somebody holding it.
        approved = await client.controls.activate(proposed["id"], reason="reviewed")
        assert approved["status"] == "active" and approved["version"] == 2
    finally:
        await anonymous.close()


async def test_a_directory_of_files_is_read_in_place_and_nothing_beyond_it(
    client: AsyncClient, sources: Path, tmp_path: Path
) -> None:
    """A ``files`` connection: each CSV a table. And a custom-SQL control that
    reaches outside the roots is refused by the engine, recorded as an error —
    it checked nothing, and no verdict pretends otherwise."""
    landing = sources / "landing"
    landing.mkdir()
    lines = ["trade_id,ccy,quantity", *(f"{t},{c},{q}" for t, c, q in PLANTED)]
    (landing / "trades.csv").write_text("\n".join(lines) + "\n")
    secret = tmp_path / "secret.csv"
    secret.write_text("violating_rows\n0\n")

    dataset_id = await declare_trades(client)
    derived = await client.derive.dataset(dataset_id, accept=True)
    membership = by_column(derived, "ccy", "IN")
    reach = await client.controls.declare(
        f'CHECK trades CUSTOM SQL """SELECT COUNT(*) AS violating_rows '
        f'FROM read_csv(\'{secret}\')""" SEVERITY minor'
    )
    await client.controls.activate(reach["id"], reason="the fence is what is under test")
    connection = await client.connections.create("landing", "files", config={"path": str(landing)})
    report = await client.runs.start(connection["id"])

    assert report["engine"] == "duckdb" and report["tables"] == ["trades"]
    outcomes = {o["control_id"]: o for o in report["outcomes"]}
    assert outcomes[membership["control"]["id"]]["verdict"] == "fail"
    fenced = outcomes[reach["id"]]
    assert fenced["verdict"] == "error" and not fenced["ran"]
    assert "disabled by configuration" in fenced["error"]


async def test_a_run_refuses_roots_that_hold_pramas_own_store(tmp_path: Path) -> None:
    """If an operator lists the directory Prama's database is in, nothing runs:
    a control able to read the ledger it writes to is not a control."""
    from prama.connect.sources.confined import open_confined

    data = write_book(tmp_path / "book.db", CLEAN)
    store = tmp_path / "prama.db"
    store.write_bytes(b"")
    with pytest.raises(prama.ForbiddenError, match="holds Prama's own database"):
        open_confined("sqlite", {"path": str(data)}, roots=[tmp_path], forbidden=[store])
    with pytest.raises(prama.ForbiddenError, match="no directories"):
        open_confined("sqlite", {"path": str(data)}, roots=[])
    opened = open_confined("sqlite", {"path": str(data)}, roots=[tmp_path])
    try:
        assert opened.execute("SELECT COUNT(*) AS n FROM trades") == [{"n": 20}]
        with pytest.raises(prama.PramaError, match="single statement"):
            opened.execute("SELECT 1; ATTACH DATABASE 'x' AS y")
    finally:
        opened.close()
