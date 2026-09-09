"""The break workbench.

Mostly about ordering. A queue sorted by size looks authoritative and puts the
work in exactly the wrong sequence: a hundred-million-euro timing break clears
itself, and the thousand-euro genuine one underneath it is somebody's missing
trade.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import httpx
import pytest

from prama.core.clock import utc_now
from prama.db import Database
from prama.recon.classify import Break, BreakKind

pytestmark = pytest.mark.anyio

DEFINITION = "ledger-vs-custodian"


def _break(key: str, kind: BreakKind, *, left="100.00", right="105.00", **kw) -> Break:
    return Break(
        key=key,
        kind=kind,
        left=Decimal(left) if left is not None else None,
        right=Decimal(right) if right is not None else None,
        because=kw.pop("because", "the two sides disagree"),
        **kw,
    )


async def _observe(database: Database, tenant_id: str, breaks, *, when: str | None = None):
    async with database.unit_of_work() as uow:
        await uow.breaks.observe(
            breaks,
            tenant_id=tenant_id,
            definition=DEFINITION,
            when=when or utc_now().date().isoformat(),
        )


async def _ids(database: Database, tenant_id: str) -> dict[str, str]:
    async with database.unit_of_work() as uow:
        rows = await uow.breaks.for_definition(tenant_id, DEFINITION)
        return {row.break_key: str(row.id) for row in rows}


class TestTheOrdering:
    async def test_a_genuine_break_outranks_a_larger_timing_one(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """The whole reason this screen sorts the way it does."""
        await _observe(
            started_database,
            tenant_id,
            [
                _break("HUGE", BreakKind.TIMING, left="0", right="100000000.00"),
                _break("SMALL", BreakKind.GENUINE, left="1000.00", right="2000.00"),
            ],
        )
        body = (await ui.get(f"/reconciliation/{DEFINITION}")).text
        assert body.index("SMALL") < body.index("HUGE")

    async def test_it_says_why_it_is_not_sorted_by_size(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        await _observe(started_database, tenant_id, [_break("A", BreakKind.GENUINE)])
        body = " ".join((await ui.get(f"/reconciliation/{DEFINITION}")).text.split())
        assert "Ordered by what needs a person, not by size." in body

    async def test_configuration_faults_are_grouped_and_named(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """Sending a sign-convention fault to a data steward wastes their day
        and leaves the setup wrong."""
        await _observe(
            started_database,
            tenant_id,
            [
                _break("A", BreakKind.SIGN),
                _break("B", BreakKind.DUPLICATE),
                _break("C", BreakKind.GENUINE),
            ],
        )
        body = " ".join((await ui.get(f"/reconciliation/{DEFINITION}")).text.split())
        assert "2 of these look like setup, not data." in body
        assert "wastes their day and leaves the setup wrong" in body


class TestWhatIsShownBesideTheAmounts:
    async def test_the_normalisation_trail_is_shown(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """The first question about any break is whether it is real or a
        translation error, and two amounts without the trail invite the reader
        to answer it wrong."""
        await _observe(
            started_database,
            tenant_id,
            [
                _break(
                    "A",
                    BreakKind.FX,
                    normalisation=("converted GBP to EUR at 1.1732 (ECB, 2026-09-01)",),
                )
            ],
        )
        body = " ".join((await ui.get(f"/reconciliation/{DEFINITION}")).text.split())
        assert "Before comparing:" in body
        assert "converted GBP to EUR at 1.1732" in body

    async def test_a_missing_side_renders_as_nothing_not_zero(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """Rendering "nothing on the right" as "0" turns a missing record into
        a balanced one."""
        await _observe(
            started_database,
            tenant_id,
            [_break("A", BreakKind.MISSING, left="100.00", right=None)],
        )
        body = (await ui.get(f"/reconciliation/{DEFINITION}")).text
        assert "nothing</span>" in body

    async def test_an_aggregated_break_says_the_key_repeats(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        await _observe(
            started_database, tenant_id, [_break("A", BreakKind.GENUINE, aggregated=True)]
        )
        body = " ".join((await ui.get(f"/reconciliation/{DEFINITION}")).text.split())
        assert "These are totals: the key repeats" in body


class TestAgeIsItsOwnSeverity:
    async def test_a_long_open_break_is_flagged(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """A small break nobody has explained in a month says the process is
        not working, and the amount is beside the point."""
        old = (utc_now().date() - timedelta(days=45)).isoformat()
        await _observe(started_database, tenant_id, [_break("OLD", BreakKind.GENUINE)], when=old)
        await _observe(started_database, tenant_id, [_break("OLD", BreakKind.GENUINE)])

        body = " ".join((await ui.get(f"/reconciliation/{DEFINITION}")).text.split())
        assert "have been open a long time" in body
        assert "45 day(s) old" in body


class TestWhatStaysVisible:
    async def test_an_accepted_break_stays_on_the_screen(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """A carried reconciling item that disappears once accepted is how a
        reconciliation quietly stops reconciling."""
        await _observe(started_database, tenant_id, [_break("A", BreakKind.GENUINE)])
        identifier = (await _ids(started_database, tenant_id))["A"]
        await ui.post(
            f"/reconciliation/breaks/{identifier}/accept",
            data={"definition": DEFINITION, "reason": "known settlement lag"},
        )

        body = " ".join((await ui.get(f"/reconciliation/{DEFINITION}")).text.split())
        assert "known settlement lag" in body
        assert "quietly stops reconciling" in body

    async def test_cleared_breaks_are_counted_even_when_not_listed(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """ "Forty cleared and forty appeared" and "nothing changed" produce the
        same queue length."""
        await _observe(started_database, tenant_id, [_break("WENT-AWAY", BreakKind.GENUINE)])
        await _observe(started_database, tenant_id, [_break("TURNED-UP", BreakKind.GENUINE)])

        body = " ".join((await ui.get(f"/reconciliation/{DEFINITION}")).text.split())
        assert "1 have cleared." in body
        assert "1</strong> outstanding" in body
        # Counted, not listed. The queue length alone cannot tell churn from
        # stillness, which is exactly why the count is stated separately.
        assert "WENT-AWAY" not in body
        assert "TURNED-UP" in body

    async def test_cleared_breaks_can_be_shown(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        await _observe(started_database, tenant_id, [_break("GONE", BreakKind.GENUINE)])
        await _observe(started_database, tenant_id, [])

        outstanding = (await ui.get(f"/reconciliation/{DEFINITION}")).text
        everything = (await ui.get(f"/reconciliation/{DEFINITION}?show=all")).text
        assert "GONE" not in outstanding
        assert "GONE" in everything

    async def test_an_empty_queue_is_not_a_clean_reconciliation(
        self, ui: httpx.AsyncClient
    ) -> None:
        """An empty screen reads as "everything matched". It means nothing has
        been observed into this queue."""
        body = " ".join((await ui.get("/reconciliation/never-observed")).text.split())
        assert "That is not the same as a clean reconciliation" in body


class TestDispositions:
    async def _one(self, database: Database, tenant_id: str) -> str:
        await _observe(database, tenant_id, [_break("A", BreakKind.GENUINE)])
        return (await _ids(database, tenant_id))["A"]

    async def test_assigning_and_noting_land_on_the_screen(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        identifier = await self._one(started_database, tenant_id)
        await ui.post(
            f"/reconciliation/breaks/{identifier}/assign",
            data={"definition": DEFINITION, "owner": "ops-emea"},
        )
        await ui.post(
            f"/reconciliation/breaks/{identifier}/explain",
            data={"definition": DEFINITION, "text": "custodian resends tomorrow"},
        )

        body = " ".join((await ui.get(f"/reconciliation/{DEFINITION}")).text.split())
        assert "ops-emea" in body
        assert "custodian resends tomorrow" in body

    async def test_an_acceptance_without_a_reason_is_refused_and_says_so(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        identifier = await self._one(started_database, tenant_id)
        response = await ui.post(
            f"/reconciliation/breaks/{identifier}/accept",
            data={"definition": DEFINITION, "reason": "  "},
        )
        assert response.status_code == 303

        async with started_database.unit_of_work() as uow:
            [row] = await uow.breaks.for_definition(tenant_id, DEFINITION)
        assert row.state == "open"

    async def test_another_tenants_break_cannot_be_dispositioned(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            other = uow.tenants.create(slug="rival", display_name="Rival")
            await uow.flush()
            other_id = str(other.id)
            await uow.breaks.observe(
                [_break("THEIRS", BreakKind.GENUINE)],
                tenant_id=other_id,
                definition=DEFINITION,
                when="2026-09-01",
            )
            await uow.flush()
            [row] = await uow.breaks.for_definition(other_id, DEFINITION)
            identifier = str(row.id)

        await ui.post(
            f"/reconciliation/breaks/{identifier}/accept",
            data={"definition": DEFINITION, "reason": "not mine to accept"},
        )
        async with started_database.unit_of_work() as uow:
            row = await uow.breaks.require(identifier)
        assert row.state == "open"


class TestTheListLinksToIt:
    async def test_a_queue_appears_on_the_reconciliation_list(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        await _observe(started_database, tenant_id, [_break("A", BreakKind.GENUINE)])
        body = (await ui.get("/reconciliation")).text
        assert f"/reconciliation/{DEFINITION}" in body
        assert "has not been observed, which is not" in " ".join(body.split())
