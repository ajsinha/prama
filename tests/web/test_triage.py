"""The one-incident screen, and the four ways a sample can be absent.

The panel that shows failing rows is the easiest thing on the console to get
wrong in a way that reads as helpful. Fifty rows of four thousand, rendered
without the ratio, invites a steward to work the list and believe they are
finished. These tests are mostly about the sentences beside the rows.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import httpx
import pytest

from prama.db import Database
from prama.evidence.record import EvidenceRecord

pytestmark = pytest.mark.anyio

PQL = (
    "CHECK positions_eod.notional IS NOT NULL "
    "SEVERITY critical DIMENSION completeness BECAUSE 'the book must foot'"
)


async def _control(database: Database, tenant_id: str, identity: str = "a") -> str:
    async with database.unit_of_work() as uow:
        control, _ = await uow.controls.declare(tenant_id=tenant_id, identity=identity, pql=PQL)
        await uow.controls.activate(str(control.id), tenant_id=tenant_id, approved_by="bob")
        return str(control.id)


async def _record(
    database: Database,
    tenant_id: str,
    control_id: str,
    *,
    verdict: str = "fail",
    when: str = "2026-09-10T06:00:00Z",
    violating: float = 4000.0,
    digest: str = "",
    sample_count: int = 0,
    **extra: object,
) -> None:
    async with database.unit_of_work() as uow:
        await uow.evidence.append(
            EvidenceRecord(
                control_id=control_id,
                dataset="positions_eod",
                verdict=verdict,
                metrics={"scanned_rows": 100_000.0, "violating_rows": violating},
                finished_at=when,
                samples_digest=digest,
                sample_count=sample_count,
                dimensions=("completeness",),
                **extra,  # type: ignore[arg-type]
            ),
            tenant_id=tenant_id,
        )


async def _samples(
    database: Database, tenant_id: str, digest: str, rows: list[dict], **kwargs: object
) -> None:
    async with database.unit_of_work() as uow:
        await uow.samples.put(
            tenant_id=tenant_id,
            digest=digest,
            rows=rows,
            created_at="2026-09-10T06:00:00Z",
            **kwargs,  # type: ignore[arg-type]
        )


class TestTheSampleIsNeverMistakenForTheFailure:
    async def test_a_partial_sample_says_what_it_is_a_sample_of(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """The specific failure this panel exists to prevent: fifty rows read as
        the whole problem, worked through, and declared done."""
        control = await _control(started_database, tenant_id)
        await _record(started_database, tenant_id, control, digest="d1", sample_count=50)
        await _samples(
            started_database,
            tenant_id,
            "d1",
            [{"account_id": f"ACC{n:03d}", "notional": None} for n in range(50)],
        )

        body = " ".join((await ui.get(f"/incidents/{control}")).text.split())
        assert "50 of 4,000 failing rows" in body
        assert "working this list is not the same as working the failure" in body

    async def test_a_complete_sample_does_not_claim_to_be_partial(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """Telling a reader their complete list is partial sends them looking
        for rows that do not exist."""
        control = await _control(started_database, tenant_id)
        await _record(
            started_database, tenant_id, control, violating=3.0, digest="d2", sample_count=3
        )
        await _samples(
            started_database,
            tenant_id,
            "d2",
            [{"account_id": f"ACC{n}", "notional": None} for n in range(3)],
        )

        body = " ".join((await ui.get(f"/incidents/{control}")).text.split())
        assert "All 3 failing rows." in body
        assert "not the same as working the failure" not in body

    async def test_rows_never_collected_is_not_rows_lost(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """A control that records counts has no retention problem, and telling
        its owner to check retention wastes the one person who could fix a real
        one."""
        control = await _control(started_database, tenant_id)
        await _record(started_database, tenant_id, control)

        body = " ".join((await ui.get(f"/incidents/{control}")).text.split())
        assert "records counts rather than rows" in body
        assert "The counts are not an approximation of them." in body
        assert "no longer held" not in body

    async def test_rows_that_have_gone_say_so_and_do_not_guess_why(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """Expired and erased-on-request leave the store in the same state, so
        the screen names both rather than picking the flattering one."""
        control = await _control(started_database, tenant_id)
        await _record(started_database, tenant_id, control, digest="gone", sample_count=50)

        body = " ".join((await ui.get(f"/incidents/{control}")).text.split())
        assert "no longer held" in body
        assert "reached the end of their retention or were erased on request" in body
        assert "it can no longer show which" in body

    async def test_masked_columns_are_named(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """A sample with a column silently removed is one a reader draws
        conclusions from without knowing what is missing."""
        control = await _control(started_database, tenant_id)
        await _record(
            started_database, tenant_id, control, violating=2.0, digest="d3", sample_count=2
        )
        await _samples(
            started_database,
            tenant_id,
            "d3",
            [{"account_id": "ACC1"}, {"account_id": "ACC2"}],
            masked=("customer_name", "national_id"),
        )

        body = " ".join((await ui.get(f"/incidents/{control}")).text.split())
        assert "Withheld from these rows:" in body
        assert "customer_name" in body
        assert "national_id" in body

    async def test_a_null_is_marked_rather_than_rendered_as_a_blank_cell(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """On a completeness control the null *is* the finding, and an empty
        cell is indistinguishable from an empty string."""
        control = await _control(started_database, tenant_id)
        await _record(
            started_database, tenant_id, control, violating=1.0, digest="d4", sample_count=1
        )
        await _samples(
            started_database, tenant_id, "d4", [{"account_id": "ACC1", "notional": None}]
        )

        body = (await ui.get(f"/incidents/{control}")).text
        assert "null</span>" in body

    async def test_another_tenants_samples_are_not_shown(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """The sample store is keyed by digest, which is content — so the same
        failing rows in two tenants are one row in the table, and the tenant
        check is the only thing between them."""
        async with started_database.unit_of_work() as uow:
            other = uow.tenants.create(slug="rival", display_name="Rival")
            await uow.flush()
            other_id = str(other.id)

        control = await _control(started_database, tenant_id)
        await _record(
            started_database, tenant_id, control, violating=1.0, digest="shared", sample_count=1
        )
        await _samples(started_database, other_id, "shared", [{"account_id": "THEIRS"}])

        body = (await ui.get(f"/incidents/{control}")).text
        assert "THEIRS" not in body
        assert "no longer held" in body


class TestSinceWhen:
    async def test_it_names_when_the_failing_started(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        control = await _control(started_database, tenant_id)
        for when, verdict in [
            ("2026-09-01T06:00:00Z", "pass"),
            ("2026-09-02T06:00:00Z", "fail"),
            ("2026-09-03T06:00:00Z", "fail"),
        ]:
            await _record(started_database, tenant_id, control, verdict=verdict, when=when)

        body = " ".join((await ui.get(f"/incidents/{control}")).text.split())
        assert "Not passing since <strong>2026-09-02T06:00:00Z" in body.replace("&lt;", "<")

    async def test_a_start_older_than_the_window_is_not_invented(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """A date that is really "the oldest run we still hold" reads as the
        date the problem began, which is the more comforting of the two."""
        from prama.web.routes.triage_routes import HISTORY

        control = await _control(started_database, tenant_id)
        for day in range(HISTORY + 5):
            await _record(
                started_database,
                tenant_id,
                control,
                verdict="fail",
                when=f"2026-07-{(day % 28) + 1:02d}T{day % 24:02d}:00:00Z",
            )

        body = " ".join((await ui.get(f"/incidents/{control}")).text.split())
        assert "when it started is not known from this page" in body
        assert "Not passing since" not in body

    async def test_a_passing_control_claims_no_start(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        control = await _control(started_database, tenant_id)
        await _record(started_database, tenant_id, control, verdict="pass", violating=0.0)

        body = " ".join((await ui.get(f"/incidents/{control}")).text.split())
        assert "Not passing since" not in body


class TestWhatTheControlSays:
    async def test_the_sentence_is_derived_from_the_stored_pql(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """Derived from the same structure the SQL comes from. A second English
        renderer is how a screen explains one control and runs another."""
        control = await _control(started_database, tenant_id)
        await _record(started_database, tenant_id, control)

        body = " ".join((await ui.get(f"/incidents/{control}")).text.split())
        assert "notional" in body
        assert "the book must foot" in body

    async def test_evidence_survives_a_control_leaving_the_estate(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """Hiding the evidence because the control is gone would erase the
        record of a failure by retiring the control that found it."""
        await _record(started_database, tenant_id, "01NOSUCHCONTROL")

        body = " ".join((await ui.get("/incidents/01NOSUCHCONTROL")).text.split())
        assert "no longer in the estate" in body
        assert "4,000</strong> of 100,000 rows" in body

    async def test_an_unknown_control_with_no_evidence_is_a_404(
        self, ui: httpx.AsyncClient
    ) -> None:
        response = await ui.get("/incidents/01NOTHINGATALL")
        assert response.status_code == 404

    async def test_a_control_that_has_never_run_says_so(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """Not "no problems". The control exists and has produced no verdict,
        which is the fact worth acting on."""
        control = await _control(started_database, tenant_id)

        body = " ".join((await ui.get(f"/incidents/{control}")).text.split())
        assert "This control has never run." in body
        assert "Nothing on this page describes the data." in body


class TestTheListLinksToIt:
    async def test_an_incident_row_reaches_its_detail(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        control = await _control(started_database, tenant_id)
        await _record(started_database, tenant_id, control)

        assert f"/incidents/{control}" in (await ui.get("/incidents")).text
