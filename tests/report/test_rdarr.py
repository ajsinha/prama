"""The RDARR pack.

The demonstration docs/19 calls the one that closes deals — and the reason it
works is that nothing in it is a number somebody typed. Which controls address
an obligation comes from a binding the estate declared; whether they passed
comes from the ledger.

Most of these tests are about the reading order, because the order is the
argument. A pack that led with what passed would be a marketing document, and an
examiner who had to go looking for the gaps would rightly wonder what else had
been arranged for them.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.db import Database
from prama.evidence.record import EvidenceRecord
from prama.packs.banking.obligations import BCBS_239, catalogue
from prama.report import rdarr

pytestmark = pytest.mark.anyio

PERIOD = {"period_start": "2026-09-01", "period_end": "2026-09-30"}


async def _record(
    database: Database,
    tenant_id: str,
    control_id: str,
    verdict: str,
    when: str = "2026-09-10T06:00:00Z",
) -> None:
    async with database.unit_of_work() as uow:
        await uow.evidence.append(
            EvidenceRecord(
                control_id=control_id,
                dataset="positions_eod",
                verdict=verdict,
                metrics={"scanned_rows": 1000.0, "violating_rows": 0.0},
                finished_at=when,
            ),
            tenant_id=tenant_id,
        )


async def _pack(database: Database, tenant_id: str, bindings: dict, **kw):
    async with database.unit_of_work() as uow:
        return await rdarr.build(
            uow,
            tenant_id,
            catalogue=catalogue(),
            regime=BCBS_239,
            scope="Trading book",
            bindings=bindings,
            **{**PERIOD, **kw},
        )


class TestTheHeadlineNamesTheGaps:
    async def test_an_estate_with_nothing_bound_says_how_many(
        self, started_database: Database, tenant_id: str
    ) -> None:
        pack = await _pack(started_database, tenant_id, {})
        assert not pack.is_defensible
        assert "have no control" in pack.headline()
        assert "an examiner would ask about" in pack.headline()

    async def test_controls_that_never_ran_are_counted_separately(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """ "We have a control for that" and "we have evidence of that" are the
        two answers being separated."""
        pack = await _pack(started_database, tenant_id, {"cde-not-null": ["C1"]})
        assert "produced no evidence in the period" in pack.headline()
        assert len(pack.coverage.unproven) == 1

    async def test_a_fully_evidenced_regime_reads_as_defensible(
        self, started_database: Database, tenant_id: str
    ) -> None:
        book = catalogue()
        bindings = {}
        for index, obligation in enumerate(book.of_regime(BCBS_239)):
            for template in obligation.templates:
                bindings[template.identity] = [f"C{index}"]
            await _record(started_database, tenant_id, f"C{index}", "pass")

        pack = await _pack(started_database, tenant_id, bindings)
        assert pack.is_defensible
        assert "all 6 obligations have controls that produced evidence" in pack.headline()

    async def test_defensible_does_not_mean_everything_passed(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """A pack full of exceptions that were found, explained and signed is
        defensible. A pack with an obligation nobody has evidence for is not,
        however clean the rest looks."""
        book = catalogue()
        bindings = {}
        for index, obligation in enumerate(book.of_regime(BCBS_239)):
            for template in obligation.templates:
                bindings[template.identity] = [f"C{index}"]
            await _record(
                started_database, tenant_id, f"C{index}", "fail" if index == 0 else "pass"
            )

        pack = await _pack(started_database, tenant_id, bindings)
        assert pack.is_defensible
        assert len(pack.coverage.with_exceptions) == 1
        assert "carried exceptions" in pack.headline()


class TestTheReadingOrder:
    async def test_gaps_come_before_what_held(
        self, started_database: Database, tenant_id: str
    ) -> None:
        pack = await _pack(started_database, tenant_id, {"cde-not-null": ["C1"]})
        titles = [section["title"] for section in pack.sections()]
        assert titles.index("Obligations with no control") == 0
        assert titles.index("Obligations with controls that produced no evidence") == 1
        assert titles.index("Obligations proven clean") == len(titles) - 1

    async def test_every_section_says_why_it_is_there(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """A section an examiner has to interpret is one they will interpret
        differently from the author."""
        pack = await _pack(started_database, tenant_id, {})
        for section in pack.sections():
            assert len(section["why"]) > 30, section["title"]

    async def test_a_standing_names_its_controls_not_a_count(
        self, started_database: Database, tenant_id: str
    ) -> None:
        await _record(started_database, tenant_id, "C1", "fail")
        pack = await _pack(started_database, tenant_id, {"cde-not-null": ["C1", "C2"]})
        [section] = [
            s for s in pack.sections() if s["title"] == "Obligations proven with exceptions"
        ]
        assert section["standings"][0]["controls"] == ["C1", "C2"]


class TestEverythingIsDerived:
    async def test_the_verdicts_come_from_the_ledger(
        self, started_database: Database, tenant_id: str
    ) -> None:
        await _record(started_database, tenant_id, "C1", "fail")
        pack = await _pack(started_database, tenant_id, {"cde-not-null": ["C1"]})
        [standing] = [s for s in pack.coverage.standings if s.controls]
        assert standing.failed == 1

    async def test_a_control_that_ran_many_times_contributes_one_standing(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """An obligation is not more addressed for having been checked
        hourly. The latest record in the period is the one that stands."""
        for hour in range(1, 6):
            await _record(started_database, tenant_id, "C1", "fail", f"2026-09-10T0{hour}:00:00Z")
        await _record(started_database, tenant_id, "C1", "pass", "2026-09-10T09:00:00Z")

        pack = await _pack(started_database, tenant_id, {"cde-not-null": ["C1"]})
        [standing] = [s for s in pack.coverage.standings if s.controls]
        assert standing.passed == 1
        assert standing.failed == 0

    async def test_evidence_outside_the_period_does_not_count(
        self, started_database: Database, tenant_id: str
    ) -> None:
        await _record(started_database, tenant_id, "C1", "pass", "2026-08-15T06:00:00Z")
        pack = await _pack(started_database, tenant_id, {"cde-not-null": ["C1"]})
        [standing] = [s for s in pack.coverage.standings if s.controls]
        assert standing.standing.value == "addressed_unproven"

    async def test_the_pack_carries_the_evidence_root(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """What ties the statement to the facts. Without it the pack floats
        free of the records, and evidence written afterwards is
        indistinguishable from evidence written before."""
        await _record(started_database, tenant_id, "C1", "pass")
        pack = await _pack(started_database, tenant_id, {"cde-not-null": ["C1"]})
        assert pack.evidence_records == 1
        assert pack.evidence_root

    async def test_an_empty_catalogue_establishes_nothing_and_says_so(
        self, started_database: Database, tenant_id: str
    ) -> None:
        from prama.packs.banking.regulatory import Catalogue

        async with started_database.unit_of_work() as uow:
            pack = await rdarr.build(
                uow,
                tenant_id,
                catalogue=Catalogue(),
                regime="Nothing",
                scope="s",
                bindings={},
                **PERIOD,
            )
        assert "establishes nothing" in pack.headline()


class TestTheDictionaryForm:
    async def test_it_carries_the_sections_and_the_headline(
        self, started_database: Database, tenant_id: str
    ) -> None:
        await _record(started_database, tenant_id, "C1", "pass")
        payload = (await _pack(started_database, tenant_id, {"cde-not-null": ["C1"]})).to_dict()
        assert payload["regime"] == BCBS_239
        assert payload["defensible"] is False
        assert len(payload["sections"]) == 4
        assert payload["coverage"]["standings"]
        assert payload["headline"]
