"""Delegates uploaded through the console: vetted in a sandbox, approved by someone else.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from prama.core.errors import ConflictError, ForbiddenError, ValidationError
from prama.db import Database
from prama.delegates import uploads
from prama.delegates.host import DelegateHost
from prama.execute import ControlRun

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "delegates"
GOOD = (FIXTURES / "good" / "threshold_count.py").read_bytes()
CONTROL = "CHECK payments USING DELEGATE 'test.over_limit@2' (limit = 100)"
ROWS = [{"id": 1, "amount": 50}, {"id": 2, "amount": 150}]


async def _people(uow: Any, tenant_id: str) -> tuple[str, str]:
    ada = uow.principals.create(tenant_id=tenant_id, username="ada", display_name="Ada")
    bo = uow.principals.create(tenant_id=tenant_id, username="bo", display_name="Bo")
    await uow.flush()
    return str(ada.id), str(bo.id)


async def test_a_conforming_upload_is_proposed_with_what_vetting_found(
    started_database: Database, tenant_id: str
) -> None:
    async with started_database.unit_of_work() as uow:
        ada, _ = await _people(uow, tenant_id)
        row = await uploads.submit(uow, tenant_id, "over_limit.py", GOOD, by=ada)
    assert (row.name, row.version, row.state) == ("test.over_limit", "2", "proposed")
    assert '"requires": ["id", "amount", "booked"]' in row.described
    assert "reads its rows in one pass" in row.findings


@pytest.mark.parametrize(
    ("filename", "body", "why"),
    [
        ("phones_home.py", (FIXTURES / "impure" / "phones_home.py").read_bytes(), "socket"),
        ("notes.txt", b"hello", "not a delegate file"),
        ("big.py", b"#" * (uploads.MAX_BYTES + 1), "larger than"),
        ("none.py", b'"""No delegate here."""\nX = 1\n', "holds 0 delegates"),
    ],
)
async def test_a_non_conforming_upload_is_refused_and_not_stored(
    started_database: Database, tenant_id: str, filename: str, body: bytes, why: str
) -> None:
    async with started_database.unit_of_work() as uow:
        ada, _ = await _people(uow, tenant_id)
        with pytest.raises(ValidationError, match=why):
            await uploads.submit(uow, tenant_id, filename, body, by=ada)
        assert await uow.delegate_uploads.all(tenant_id) == []


async def test_four_eyes_and_an_immutable_version(
    started_database: Database, tenant_id: str
) -> None:
    async with started_database.unit_of_work() as uow:
        ada, bo = await _people(uow, tenant_id)
        row = await uploads.submit(uow, tenant_id, "over_limit.py", GOOD, by=ada)
        with pytest.raises(ForbiddenError, match="cannot approve their own"):
            await uploads.decide(uow, tenant_id, row.id, action="approve", by=ada)
        approved = await uploads.decide(uow, tenant_id, row.id, action="approve", by=bo)
        assert approved.state == "approved" and approved.decided_by == bo
        with pytest.raises(ConflictError, match="already been uploaded"):
            await uploads.submit(uow, tenant_id, "over_limit.py", GOOD, by=ada)


async def _declared(database: Database, tenant_id: str) -> tuple[str, str]:
    async with database.unit_of_work() as uow:
        ada, bo = await _people(uow, tenant_id)
        row = await uploads.submit(uow, tenant_id, "over_limit.py", GOOD, by=ada)
        control, _ = await uow.controls.declare(tenant_id=tenant_id, identity="d", pql=CONTROL)
        await uow.controls.activate(str(control.id), tenant_id=tenant_id, approved_by=bo)
    return row.id, bo


async def _run(database: Database, tenant_id: str, host: DelegateHost) -> Any:
    async with database.unit_of_work() as uow:
        report = await ControlRun(
            uow, tenant_id, execute=lambda _sql: ROWS, engine="duckdb", delegates=host
        ).execute_all()
    (outcome,) = report.outcomes
    return outcome.record


async def test_only_an_approved_upload_runs_and_a_retired_one_stops(
    started_database: Database, tenant_id: str, tmp_path: Path
) -> None:
    upload_id, bo = await _declared(started_database, tenant_id)
    host = DelegateHost(sandbox=False, upload_dir=str(tmp_path))

    proposed = await _run(started_database, tenant_id, host)
    assert proposed.verdict == "error"  # proposed is not approved: the control cannot run

    async with started_database.unit_of_work() as uow:
        await uploads.decide(uow, tenant_id, upload_id, action="approve", by=bo)
    approved = await _run(started_database, tenant_id, host)
    assert approved.verdict == "fail" and approved.metrics["violating_rows"] == 1
    assert approved.parameters["delegate_origin"].startswith("upload:")
    # sandbox=False on the host, and it still ran sandboxed: the host holds only
    # a stand-in whose measure() raises, so a verdict at all proves it.
    assert host.registry.get("test.over_limit").sandbox_only

    async with started_database.unit_of_work() as uow:
        await uploads.decide(uow, tenant_id, upload_id, action="retire", by=bo)
    retired = await _run(started_database, tenant_id, host)
    assert retired.verdict == "error" and "not installed" in retired.detail


async def test_a_stored_file_tampered_with_on_disk_is_refused(
    started_database: Database, tenant_id: str, tmp_path: Path
) -> None:
    upload_id, bo = await _declared(started_database, tenant_id)
    async with started_database.unit_of_work() as uow:
        row = await uploads.decide(uow, tenant_id, upload_id, action="approve", by=bo)
    host = DelegateHost(upload_dir=str(tmp_path))
    assert (await _run(started_database, tenant_id, host)).verdict == "fail"
    stored = tmp_path / tenant_id / row.source_hash / "over_limit.py"
    stored.write_text(stored.read_text().replace("> float(params", "< float(params"))
    tampered = await _run(started_database, tenant_id, host)
    assert tampered.verdict == "error" and "changed since it was admitted" in tampered.detail


async def test_the_page_lists_uploads_and_the_upload_form(ui: Any) -> None:
    page = await ui.get("/delegates")
    assert page.status_code == 200
    assert "Upload and vet" in page.text and "Configured on this server" in page.text
