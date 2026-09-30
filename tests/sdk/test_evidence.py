"""Evidence and assurance through the SDK: a failing run, end to end.

A control is declared and activated, run against rows two of which violate it,
and everything downstream is then read back through the SDK only — the ledger,
its verification, an exported bundle checked by the independent verifier, the
incident, the scorecard, an attestation and the packs. Each important behaviour
has its counterfactual beside it: a tampered chain fails verification and is
refused for export, a tampered bundle fails the verifier, a passing run closes
the incident, and a caller without the scope is refused.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
import io
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

import prama_sdk as prama
import pytest
from prama_sdk import AsyncClient
from tests.api.conftest import issue_key

from prama.db import Database
from prama.execute import ControlRun

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFIER = REPO_ROOT / "scripts" / "verify_evidence.py"

PQL = (
    "CHECK trades.notional IS NOT NULL SEVERITY critical DIMENSION completeness "
    "BECAUSE 'every trade has a notional'"
)


def _rows(**values: float) -> Any:
    def execute(_: str) -> list[dict[str, float]]:
        return [values]

    return execute


async def _declare(database: Database, tenant_id: str) -> str:
    async with database.unit_of_work() as uow:
        control, _ = await uow.controls.declare(tenant_id=tenant_id, identity="a", pql=PQL)
        await uow.controls.activate(str(control.id), tenant_id=tenant_id, approved_by="bo")
    return str(control.id)


async def _run(database: Database, tenant_id: str, *, scanned: int, violating: int) -> None:
    async with database.unit_of_work() as uow:
        await ControlRun(
            uow, tenant_id, execute=_rows(scanned_rows=scanned, violating_rows=violating)
        ).execute_all()


@pytest.fixture
async def failed(started_database: Database, tenant_id: str) -> str:
    """One active control, and one run in which 2 of 10 rows violate it."""
    control_id = await _declare(started_database, tenant_id)
    await _run(started_database, tenant_id, scanned=10, violating=2)
    return control_id


def _verify_bundle(directory: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VERIFIER), str(directory)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


# -- the ledger ------------------------------------------------------------------------


async def test_the_failure_is_recorded_and_the_chain_verifies(
    client: AsyncClient, failed: str
) -> None:
    listed = (await client.evidence.list())["items"]
    assert [(r["control_id"], r["verdict"]) for r in listed] == [(failed, "fail")]
    record = listed[0]
    assert record["metrics"]["violating_rows"] == 2 and record["dataset"] == "trades"
    assert await client.evidence.get(record["sequence"]) == record
    # Filters filter: nothing passed, and the failure is found by its control.
    assert (await client.evidence.list(verdict="pass"))["items"] == []
    assert len((await client.evidence.list(control_id=failed, verdict="fail"))["items"]) == 1
    assert (await client.evidence.list(since="2999-01-01"))["items"] == []

    verification = await client.evidence.verify()
    assert verification["intact"] is True and verification["records"] == 1
    assert verification["head"] == record["record_hash"]
    assert len(verification["merkle_root"]) == 64

    latest = await client.evidence.latest()
    assert latest[failed]["sequence"] == record["sequence"]
    assert (await client.evidence.status())["state"] == "observed"

    (run,) = await client.evidence.runs()
    assert run["record_count"] == 1 and run["status"] != "running"
    assert [r["sequence"] for r in (await client.evidence.run(run["id"]))["records"]] == [
        record["sequence"]
    ]
    with pytest.raises(prama.NotFoundError):
        await client.evidence.get(999)


async def test_an_exported_bundle_passes_the_independent_verifier(
    client: AsyncClient, failed: str, tmp_path: Path
) -> None:
    archive = await client.evidence.export()
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        assert sorted(bundle.namelist()) == ["anchors.json", "evidence.ndjson", "manifest.json"]
        bundle.extractall(tmp_path / "bundle")
    checked = _verify_bundle(tmp_path / "bundle")
    assert checked.returncode == 0, checked.stdout + checked.stderr

    # The counterfactual: the verifier is not a rubber stamp. One changed verdict
    # in the exported records and it fails.
    records = tmp_path / "bundle" / "evidence.ndjson"
    records.write_text(records.read_text().replace('"fail"', '"pass"'))
    assert _verify_bundle(tmp_path / "bundle").returncode == 1


async def test_a_tampered_chain_fails_verification_and_is_not_exported(
    client: AsyncClient, failed: str, started_database: Database
) -> None:
    from sqlalchemy import text

    assert (await client.evidence.verify())["intact"] is True
    # Reaching past the DAO on purpose: this is what tampering looks like, and
    # no honest path through Prama can produce it.
    with started_database.sync_engine().begin() as connection:
        connection.execute(text("UPDATE ev_record SET verdict = 'pass'"))

    verification = await client.evidence.verify()
    assert verification["intact"] is False
    assert any(b["kind"] == "content" for b in verification["breaches"])
    # An export recomputes hashes, so it would launder the tampering. Refused.
    with pytest.raises(prama.ConflictError):
        await client.evidence.export()


async def test_an_empty_ledger_says_so_rather_than_passing(client: AsyncClient) -> None:
    assert (await client.evidence.status())["state"] == "no_runs"
    assert (await client.evidence.verify())["records"] == 0
    with pytest.raises(prama.NotFoundError):
        await client.evidence.export()


async def test_a_rerun_is_compared_with_the_original(
    client: AsyncClient, failed: str, started_database: Database, tenant_id: str
) -> None:
    await _run(started_database, tenant_id, scanned=10, violating=0)
    first, second = sorted(r["sequence"] for r in (await client.evidence.list())["items"])
    divergence = await client.evidence.compare(first)  # against the control's newest record
    assert divergence["verdict_changed"] is True
    assert (divergence["original_verdict"], divergence["replayed_verdict"]) == ("fail", "pass")
    assert (await client.evidence.compare(first, second)) == divergence
    with pytest.raises(prama.ValidationError):  # nothing newer to compare the newest with
        await client.evidence.compare(second)


async def test_anchoring_off_is_said_rather_than_pretended(
    client: AsyncClient, failed: str
) -> None:
    with pytest.raises(prama.ValidationError, match="anchoring is off"):
        await client.evidence.anchor()
    assert await client.evidence.anchors() == []


# -- incidents and scorecards -----------------------------------------------------------


async def test_the_failure_is_an_incident_until_the_control_passes(
    client: AsyncClient, failed: str, started_database: Database, tenant_id: str
) -> None:
    listed = await client.incidents.list()
    assert [(i["control_id"], i["verdict"]) for i in listed["items"]] == [(failed, "fail")]
    assert listed["passing"] == 0 and listed["observation"]["state"] == "observed"
    assert (await client.incidents.list(dataset="elsewhere"))["items"] == []

    incident = await client.incidents.get(failed)
    # One failing record and nothing before it: when it began is not known, and
    # blank is the honest answer rather than "the oldest run we hold".
    assert incident["open"] is True and incident["began"] == ""
    assert incident["control"]["pql"] == PQL
    assert "notional" in incident["sentence"]
    assert incident["sample"]["failing"] == 2

    posted = await client.incidents.comment(failed, "Looking at the upstream feed.")
    assert [c["id"] for c in await client.incidents.comments(failed)] == [posted["id"]]

    # The counterfactual: once the control passes, there is no incident.
    await _run(started_database, tenant_id, scanned=10, violating=0)
    after = await client.incidents.list()
    assert after["items"] == [] and after["passing"] == 1
    assert (await client.incidents.get(failed))["open"] is False
    with pytest.raises(prama.NotFoundError):
        await client.incidents.get("no-such-control")


async def test_the_scorecard_is_derived_from_the_evidence(
    client: AsyncClient, failed: str, started_database: Database, tenant_id: str
) -> None:
    cards = await client.scorecards.list()
    (trades,) = cards["scores"]
    assert trades["subject"] == "trades" and trades["controls"] == 1
    assert trades["value"] == pytest.approx(0.8)
    (part,) = trades["components"]
    assert part["dimension"] == "completeness" and part["violations"] == 2
    assert cards["decomposed"] is True
    assert (await client.scorecards.get("trades")) == trades
    assert (await client.scorecards.estate())["value"] == pytest.approx(0.8)

    await _run(started_database, tenant_id, scanned=10, violating=0)
    assert (await client.scorecards.get("trades"))["value"] == pytest.approx(1.0)
    with pytest.raises(prama.NotFoundError):
        await client.scorecards.get("never-examined")


# -- attestations and reports ------------------------------------------------------------


def _period() -> tuple[str, str]:
    today = dt.datetime.now(dt.UTC).date()
    return (today - dt.timedelta(days=1)).isoformat(), (today + dt.timedelta(days=1)).isoformat()


async def test_an_attestation_derives_its_figures_and_is_sealed(
    client: AsyncClient, failed: str
) -> None:
    start, end = _period()
    draft = await client.attestations.draft(start=start, end=end)
    assert draft["coverage"]["failed"] == 1 and draft["evidence_records"] == 1
    signed = await client.attestations.sign(
        "Ada Lovelace",
        "I reviewed trade completeness for the period.",
        start,
        end,
        dispositions={failed: "Upstream feed fixed on the 3rd."},
    )
    assert signed["intact"] is True and signed["sealed"] is True
    assert signed["is_qualified"] is True
    (exception,) = signed["exceptions"]
    assert exception["control_id"] == failed and "fixed" in exception["disposition"]
    assert [a["id"] for a in await client.attestations.list()] == [signed["id"]]
    assert (await client.attestations.get(signed["id"]))["seal"] == signed["seal"]
    pack = await client.attestations.pack(signed["id"])
    assert b"Ada Lovelace" in pack and signed["evidence_root"].encode() in pack

    # Superseding needs a reason; with one, the first leaves the register.
    with pytest.raises(prama.ValidationError, match="reason"):
        await client.attestations.sign("Ada", "Again.", start, end, supersedes=signed["id"])
    second = await client.attestations.sign(
        "Ada", "Again.", start, end, supersedes=signed["id"], supersedes_because="typo"
    )
    assert [a["id"] for a in await client.attestations.list()] == [second["id"]]
    assert len(await client.attestations.history("the estate")) == 2

    with pytest.raises(prama.ValidationError, match="name"):
        await client.attestations.sign("  ", "Nobody signed this.", start, end)


async def test_the_packs_download_as_html_and_read_as_json(client: AsyncClient) -> None:
    await client.datasets.declare("Trades", description="Executed trades.")
    index = await client.reports.list()
    assert index["declared"] == 1
    assert {r["name"] for r in index["reports"]} == {"declarations", "controls"}

    html = await client.reports.declarations()
    assert html.lstrip().lower().startswith(b"<!doctype html") and b"Trades" in html
    content = await client.reports.declarations(as_json=True)
    assert [d["name"] for d in content["datasets"]] == ["Trades"]
    assert content["coverage"]["included"] == 1
    assert "coverage" in await client.reports.controls(as_json=True)
    assert b"<html" in (await client.reports.controls()).lower()


# -- the estate as files ------------------------------------------------------------------


async def test_the_estate_exports_and_diffs_against_its_export(client: AsyncClient) -> None:
    await client.datasets.declare("Trades", description="Executed trades.")
    await client.datasets.declare("Positions", description="End-of-day positions.")
    files = (await client.estate.export())["files"]
    assert sorted(files) == ["datasets/positions.yaml", "datasets/trades.yaml"]
    assert (await client.estate.diff(files))["in_sync"] is True

    # The counterfactual: a file missing from the repository is drift.
    del files["datasets/positions.yaml"]
    drifted = await client.estate.diff(files)
    assert drifted["in_sync"] is False and len(drifted["drifts"]) == 1


# -- who may -------------------------------------------------------------------------------


async def test_a_caller_without_the_scope_is_refused(
    client: AsyncClient, failed: str, started_database: Database, tenant_id: str
) -> None:
    catalogue_only = client.as_key(
        await issue_key(started_database, tenant_id, principal="cat", scopes=["declaration:read"])
    )
    for refused in (
        catalogue_only.evidence.list(),
        catalogue_only.evidence.verify(),
        catalogue_only.evidence.export(),
        catalogue_only.incidents.list(),
        catalogue_only.scorecards.list(),
        catalogue_only.attestations.list(),
        catalogue_only.reports.list(),
    ):
        with pytest.raises(prama.ForbiddenError):
            await refused

    auditor = client.as_key(
        await issue_key(
            started_database,
            tenant_id,
            principal="aud",
            scopes=["evidence:read", "attestation:read"],
        )
    )
    assert len((await auditor.evidence.list())["items"]) == 1  # the scope is what decides
    with pytest.raises(prama.ForbiddenError):
        await auditor.evidence.anchor()
    start, end = _period()
    with pytest.raises(prama.ForbiddenError):
        await auditor.attestations.sign("Aud", "Not mine to sign.", start, end)
    for c in (catalogue_only, auditor):
        await c.close()
