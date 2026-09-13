"""Signing an attestation, end to end.

The figures are derived from the ledger, not typed. That is the whole
safeguard: an attestation whose numbers were typed is a statement about what
the attester believed; one whose numbers were derived is a statement about what
happened, which is what a regulator is asking for.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import re

import httpx
import pytest

from prama.core.errors import ConflictError
from prama.db import Database
from prama.evidence.record import EvidenceRecord

pytestmark = pytest.mark.anyio

PQL = (
    "CHECK positions_eod.notional IS NOT NULL "
    "SEVERITY critical DIMENSION completeness BECAUSE 'CDE'"
)


async def _control(database: Database, tenant_id: str, identity: str) -> str:
    async with database.unit_of_work() as uow:
        control, _ = await uow.controls.declare(tenant_id=tenant_id, identity=identity, pql=PQL)
        await uow.controls.activate(str(control.id), tenant_id=tenant_id, approved_by="bob")
        return str(control.id)


async def _record(
    database: Database, tenant_id: str, control_id: str, verdict: str, when: str
) -> None:
    async with database.unit_of_work() as uow:
        await uow.evidence.append(
            EvidenceRecord(
                control_id=control_id,
                dataset="positions_eod",
                verdict=verdict,
                metrics={
                    "scanned_rows": 1000.0,
                    "violating_rows": 12.0 if verdict == "fail" else 0.0,
                },
                finished_at=when,
                dimensions=("completeness",),
            ),
            tenant_id=tenant_id,
        )


class TestTheFiguresAreDerived:
    async def test_the_form_shows_what_the_evidence_says(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        good = await _control(started_database, tenant_id, "a")
        bad = await _control(started_database, tenant_id, "b")
        await _record(started_database, tenant_id, good, "pass", "2026-09-10T06:00:00Z")
        await _record(started_database, tenant_id, bad, "fail", "2026-09-10T06:00:00Z")

        body = " ".join(
            (
                await ui.get("/attestations/new?scope=Trading+book&start=2026-09-01&end=2026-09-30")
            ).text.split()
        )
        assert "2 of 2 control(s) produced a verdict" in body
        assert "1 passed" in body
        assert "1 failed" in body
        assert "12 of 1,000 rows" in body

    async def test_a_control_that_never_ran_is_counted_not_hidden(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """It is not an exception — there is no verdict to except from — and it
        is the number that decides how much the attestation covers."""
        ran = await _control(started_database, tenant_id, "a")
        await _control(started_database, tenant_id, "b")
        await _record(started_database, tenant_id, ran, "pass", "2026-09-10T06:00:00Z")

        body = " ".join(
            (await ui.get("/attestations/new?start=2026-09-01&end=2026-09-30")).text.split()
        )
        assert "1 live control(s) produced no verdict in this period" in body

    async def test_evidence_outside_the_period_is_not_counted(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        control = await _control(started_database, tenant_id, "a")
        await _record(started_database, tenant_id, control, "fail", "2026-08-15T06:00:00Z")

        body = " ".join(
            (await ui.get("/attestations/new?start=2026-09-01&end=2026-09-30")).text.split()
        )
        assert "0 of 1 control(s) produced a verdict" in body


class TestSigning:
    async def _sign(self, ui: httpx.AsyncClient, **extra: str) -> httpx.Response:
        data = {
            "attester_name": "Alice Chen",
            "statement": "I have reviewed the controls for September.",
            "scope": "Trading book",
            "period_start": "2026-09-01",
            "period_end": "2026-09-30",
        }
        data.update(extra)
        return await ui.post("/attestations/new", data=data)

    async def test_it_records_and_seals(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        control = await _control(started_database, tenant_id, "a")
        await _record(started_database, tenant_id, control, "pass", "2026-09-10T06:00:00Z")

        response = await self._sign(ui)
        assert response.status_code == 303

        async with started_database.unit_of_work() as uow:
            [row] = await uow.attestations.current(tenant_id)
        assert row.attester_name == "Alice Chen"
        assert len(row.seal) == 64
        assert row.evidence_root

    async def test_an_unnamed_attester_is_refused(self, ui: httpx.AsyncClient) -> None:
        """A control attested by 'the team' is a control nobody attested."""
        response = await self._sign(ui, attester_name="  ")
        assert response.status_code == 303
        assert "attestations/new" in response.headers["location"]

    async def test_an_empty_statement_is_refused(self, ui: httpx.AsyncClient) -> None:
        response = await self._sign(ui, statement="   ")
        assert response.status_code == 303
        assert "attestations/new" in response.headers["location"]

    async def test_the_detail_page_says_whether_it_still_verifies(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        control = await _control(started_database, tenant_id, "a")
        await _record(started_database, tenant_id, control, "pass", "2026-09-10T06:00:00Z")
        await self._sign(ui)
        async with started_database.unit_of_work() as uow:
            [row] = await uow.attestations.current(tenant_id)

        body = (await ui.get(f"/attestations/{row.id}")).text
        assert "Unchanged since signing, and the seal verifies" in body

    async def test_tampering_is_reported_on_the_page(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """A page that showed the signature without saying whether the content
        still matches it would be showing a seal on an envelope nobody
        checked."""
        from sqlalchemy import text

        control = await _control(started_database, tenant_id, "a")
        await _record(started_database, tenant_id, control, "pass", "2026-09-10T06:00:00Z")
        await self._sign(ui)
        async with started_database.unit_of_work() as uow:
            [row] = await uow.attestations.current(tenant_id)
            attestation_id = str(row.id)

        with started_database.sync_engine().begin() as connection:
            connection.execute(
                text("UPDATE att_attestation SET statement = 'Everything was perfect.'")
            )

        body = (await ui.get(f"/attestations/{attestation_id}")).text
        assert "no longer hashes to its stored hash" in body


class TestImmutability:
    async def test_an_attestation_cannot_be_deleted(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """The fact that somebody signed something is part of the record."""
        from prama.report.attestation import Attestation, Coverage

        async with started_database.unit_of_work() as uow:
            attestation = Attestation(
                attester_id="1",
                attester_name="Alice",
                statement="reviewed",
                scope="s",
                period_start="2026-09-01",
                period_end="2026-09-30",
                coverage=Coverage(controls_in_scope=1, controls_run=1, passed=1, failed=0),
                evidence_root="ab" * 32,
                evidence_records=1,
                signed_at="2026-10-01T00:00:00Z",
                tenant_id=tenant_id,
            )
            row = await uow.attestations.sign(attestation, seal=attestation.seal(b"k"))
            with pytest.raises(ConflictError, match="cannot be deleted"):
                await uow.attestations.delete(row)

    async def test_a_correction_supersedes_and_both_rows_survive(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        control = await _control(started_database, tenant_id, "a")
        await _record(started_database, tenant_id, control, "pass", "2026-09-10T06:00:00Z")

        data = {
            "attester_name": "Alice Chen",
            "statement": "First look.",
            "scope": "Trading book",
            "period_start": "2026-09-01",
            "period_end": "2026-09-30",
        }
        await ui.post("/attestations/new", data=data)
        async with started_database.unit_of_work() as uow:
            [first] = await uow.attestations.current(tenant_id)
            first_id = str(first.id)

        await ui.post(
            "/attestations/new",
            data={
                **data,
                "statement": "Corrected after the source fix.",
                "supersedes": first_id,
                "supersedes_because": "September evidence was re-run",
            },
        )
        async with started_database.unit_of_work() as uow:
            current = await uow.attestations.current(tenant_id)
            history = await uow.attestations.history(tenant_id, "Trading book")
            superseded = await uow.attestations.require(first_id)

        assert len(current) == 1
        assert len(history) == 2
        assert superseded.superseded_by == str(current[0].id)

    async def test_a_superseded_attestation_says_so_on_its_page(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """A reader who lands on an old one learns it was replaced rather than
        having to go looking for a newer one."""
        control = await _control(started_database, tenant_id, "a")
        await _record(started_database, tenant_id, control, "pass", "2026-09-10T06:00:00Z")
        data = {
            "attester_name": "Alice",
            "statement": "First.",
            "scope": "Trading book",
            "period_start": "2026-09-01",
            "period_end": "2026-09-30",
        }
        await ui.post("/attestations/new", data=data)
        async with started_database.unit_of_work() as uow:
            [first] = await uow.attestations.current(tenant_id)
            first_id = str(first.id)
        await ui.post(
            "/attestations/new",
            data={**data, "statement": "Second.", "supersedes": first_id},
        )
        body = (await ui.get(f"/attestations/{first_id}")).text
        assert "was superseded" in body


class TestThePack:
    async def test_it_prints_the_exceptions_in_full(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """Summarising them into a count would be asking somebody to sign for
        things they were not shown."""
        control = await _control(started_database, tenant_id, "a")
        await _record(started_database, tenant_id, control, "fail", "2026-09-10T06:00:00Z")
        await ui.post(
            "/attestations/new",
            data={
                "attester_name": "Alice Chen",
                "statement": "Reviewed, exceptions known.",
                "scope": "Trading book",
                "period_start": "2026-09-01",
                "period_end": "2026-09-30",
                f"disposition:{control}": "DQ-1187 raised",
            },
        )
        async with started_database.unit_of_work() as uow:
            [row] = await uow.attestations.current(tenant_id)

        body = " ".join((await ui.get(f"/attestations/{row.id}/pack")).text.split())
        assert "DQ-1187 raised" in body
        assert "This attestation is qualified." in body
        assert "says nothing to somebody who does not hold that key" in body

    async def test_the_pack_is_self_contained(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        control = await _control(started_database, tenant_id, "a")
        await _record(started_database, tenant_id, control, "pass", "2026-09-10T06:00:00Z")
        await ui.post(
            "/attestations/new",
            data={
                "attester_name": "Alice",
                "statement": "Reviewed.",
                "scope": "Trading book",
                "period_start": "2026-09-01",
                "period_end": "2026-09-30",
            },
        )
        async with started_database.unit_of_work() as uow:
            [row] = await uow.attestations.current(tenant_id)
        body = (await ui.get(f"/attestations/{row.id}/pack")).text
        assert "<style>" in body
        assert "/static/" not in body
        assert re.search(r"https?://", body) is None
