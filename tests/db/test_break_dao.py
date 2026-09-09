"""The persisted break queue.

``BreakQueue`` already has the semantics tested in memory. What a database adds
is the part that is easy to get wrong on the way through it: a first-seen date
that must not move, a clearing that is inferred from absence rather than
announced, and rows that must survive being resolved.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from prama.core.errors import ConflictError, NotFoundError, ValidationError
from prama.db import Database
from prama.recon.classify import Break, BreakKind

pytestmark = pytest.mark.anyio

DEFINITION = "ledger-vs-custodian"


def _break(key: str, *, kind: BreakKind = BreakKind.GENUINE, left="100.00", right="105.00", **kw):
    return Break(
        key=key,
        kind=kind,
        left=Decimal(left) if left is not None else None,
        right=Decimal(right) if right is not None else None,
        because=kw.pop("because", "the two sides disagree"),
        **kw,
    )


async def _observe(database: Database, tenant_id: str, breaks, when: str):
    async with database.unit_of_work() as uow:
        return await uow.breaks.observe(
            breaks, tenant_id=tenant_id, definition=DEFINITION, when=when
        )


class TestAgeing:
    async def test_first_seen_does_not_move_on_re_detection(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """The failure this exists to prevent: a break re-detected for forty
        days reported as new every morning, so nothing ever ages and nothing is
        ever escalated."""
        await _observe(started_database, tenant_id, [_break("ACC1")], "2026-09-01")
        await _observe(started_database, tenant_id, [_break("ACC1")], "2026-09-02")
        await _observe(started_database, tenant_id, [_break("ACC1")], "2026-09-03")

        async with started_database.unit_of_work() as uow:
            [row] = await uow.breaks.for_definition(tenant_id, DEFINITION)
        assert row.first_seen == "2026-09-01"
        assert row.last_seen == "2026-09-03"

    async def test_the_sides_are_refreshed_on_re_detection(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """The age is historical; the amounts are not. A workbench showing
        yesterday's difference beside today's date is showing neither."""
        await _observe(started_database, tenant_id, [_break("ACC1", right="105.00")], "2026-09-01")
        await _observe(started_database, tenant_id, [_break("ACC1", right="999.00")], "2026-09-02")

        async with started_database.unit_of_work() as uow:
            [row] = await uow.breaks.for_definition(tenant_id, DEFINITION)
        assert row.right_value == "999.00"
        assert row.first_seen == "2026-09-01"


class TestClearingIsInferred:
    async def test_a_break_absent_from_a_run_clears(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """No reconciliation tells you a break has gone; it stops reporting it.
        A queue that waits to be told never closes anything."""
        await _observe(started_database, tenant_id, [_break("ACC1"), _break("ACC2")], "2026-09-01")
        _, _, cleared = await _observe(started_database, tenant_id, [_break("ACC1")], "2026-09-02")

        assert cleared == 1
        async with started_database.unit_of_work() as uow:
            outstanding = await uow.breaks.outstanding(tenant_id, DEFINITION)
        assert [row.break_key for row in outstanding] == ["ACC1"]

    async def test_a_cleared_break_is_kept_not_deleted(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """ "We had four hundred breaks and they cleared" and "we had four
        hundred breaks" are the same sentence in a system that forgets."""
        await _observe(started_database, tenant_id, [_break("ACC1")], "2026-09-01")
        await _observe(started_database, tenant_id, [], "2026-09-02")

        async with started_database.unit_of_work() as uow:
            everything = await uow.breaks.for_definition(tenant_id, DEFINITION)
        [row] = everything
        assert row.state == "cleared"
        assert row.cleared_at == "2026-09-02"

    async def test_a_break_that_comes_back_keeps_its_original_age(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """A break that recurs after being closed is an old problem, not a new
        one, and restarting the clock is how a chronic difference stays out of
        every ageing report."""
        await _observe(started_database, tenant_id, [_break("ACC1")], "2026-09-01")
        await _observe(started_database, tenant_id, [], "2026-09-02")
        await _observe(started_database, tenant_id, [_break("ACC1")], "2026-09-03")

        async with started_database.unit_of_work() as uow:
            [row] = await uow.breaks.for_definition(tenant_id, DEFINITION)
        assert row.state == "open"
        assert row.cleared_at is None
        assert row.first_seen == "2026-09-01"

    async def test_an_accepted_break_does_not_clear_by_absence(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """Accepted is a decision, not a state a run may overturn."""
        await _observe(started_database, tenant_id, [_break("ACC1")], "2026-09-01")
        async with started_database.unit_of_work() as uow:
            [row] = await uow.breaks.for_definition(tenant_id, DEFINITION)
            await uow.breaks.accept(
                str(row.id), tenant_id, reason="known FX timing", by="alice", at="2026-09-01"
            )
        await _observe(started_database, tenant_id, [], "2026-09-02")

        async with started_database.unit_of_work() as uow:
            [row] = await uow.breaks.for_definition(tenant_id, DEFINITION)
        assert row.state == "accepted"

    async def test_the_counts_distinguish_churn_from_stillness(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """ "Forty cleared and forty appeared" and "nothing changed" produce the
        same queue length."""
        await _observe(started_database, tenant_id, [_break("A"), _break("B")], "2026-09-01")
        new, again, cleared = await _observe(
            started_database, tenant_id, [_break("B"), _break("C")], "2026-09-02"
        )
        assert (new, again, cleared) == (1, 1, 1)


class TestDefinitionsDoNotCollide:
    async def test_one_reconciliation_does_not_clear_anothers_breaks(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """A break key is unique only within its own definition. Two
        reconciliations over the same accounts would otherwise clear each
        other's breaks on every run."""
        async with started_database.unit_of_work() as uow:
            await uow.breaks.observe(
                [_break("ACC1")], tenant_id=tenant_id, definition="a", when="2026-09-01"
            )
            await uow.breaks.observe(
                [_break("ACC2")], tenant_id=tenant_id, definition="b", when="2026-09-01"
            )
            await uow.breaks.observe(
                [_break("ACC1")], tenant_id=tenant_id, definition="a", when="2026-09-02"
            )
            in_b = await uow.breaks.outstanding(tenant_id, "b")
        assert [row.break_key for row in in_b] == ["ACC2"]


class TestDispositions:
    async def _one(self, database: Database, tenant_id: str) -> str:
        await _observe(database, tenant_id, [_break("ACC1")], "2026-09-01")
        async with database.unit_of_work() as uow:
            [row] = await uow.breaks.for_definition(tenant_id, DEFINITION)
            return str(row.id)

    async def test_assigning_records_the_handover_as_well_as_the_owner(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """The owner answers "whose is this"; only the trail answers "who gave
        it to them and when", which is what gets asked about a break that sat
        with the wrong team for a month."""
        identifier = await self._one(started_database, tenant_id)
        async with started_database.unit_of_work() as uow:
            row = await uow.breaks.assign(
                identifier, tenant_id, owner="ops-emea", by="alice", at="2026-09-02"
            )
        assert row.owner == "ops-emea"
        assert row.state == "assigned"
        assert "Assigned to ops-emea" in row.comments_json[0]["text"]

    async def test_reassignment_names_both_teams(
        self, started_database: Database, tenant_id: str
    ) -> None:
        identifier = await self._one(started_database, tenant_id)
        async with started_database.unit_of_work() as uow:
            await uow.breaks.assign(
                identifier, tenant_id, owner="ops-emea", by="alice", at="2026-09-02"
            )
            row = await uow.breaks.assign(
                identifier, tenant_id, owner="ops-apac", by="bob", at="2026-09-03"
            )
        assert "from ops-emea to ops-apac" in row.comments_json[-1]["text"]

    async def test_an_unowned_assignment_is_refused(
        self, started_database: Database, tenant_id: str
    ) -> None:
        identifier = await self._one(started_database, tenant_id)
        async with started_database.unit_of_work() as uow:
            with pytest.raises(ValidationError, match="nobody is working"):
                await uow.breaks.assign(
                    identifier, tenant_id, owner="  ", by="alice", at="2026-09-02"
                )

    async def test_notes_append_and_never_overwrite(
        self, started_database: Database, tenant_id: str
    ) -> None:
        identifier = await self._one(started_database, tenant_id)
        async with started_database.unit_of_work() as uow:
            await uow.breaks.explain(
                identifier, tenant_id, text="chasing the custodian", by="a", at="2026-09-02"
            )
            row = await uow.breaks.explain(
                identifier, tenant_id, text="they resend tomorrow", by="a", at="2026-09-03"
            )
        assert [c["text"] for c in row.comments_json] == [
            "chasing the custodian",
            "they resend tomorrow",
        ]
        assert row.state == "explained"

    async def test_accepting_without_a_reason_is_refused(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """An acceptance nobody explained is indistinguishable from one
        somebody clicked away, and the difference is the whole value of the
        state."""
        identifier = await self._one(started_database, tenant_id)
        async with started_database.unit_of_work() as uow:
            with pytest.raises(ValidationError, match="without a reason"):
                await uow.breaks.accept(
                    identifier, tenant_id, reason="   ", by="alice", at="2026-09-02"
                )

    async def test_accepting_a_cleared_break_is_refused(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """Accepting a break that has gone would carry a difference nobody
        has."""
        identifier = await self._one(started_database, tenant_id)
        await _observe(started_database, tenant_id, [], "2026-09-02")
        async with started_database.unit_of_work() as uow:
            with pytest.raises(ConflictError, match="already cleared"):
                await uow.breaks.accept(
                    identifier, tenant_id, reason="known", by="alice", at="2026-09-03"
                )

    async def test_a_break_cannot_be_deleted(
        self, started_database: Database, tenant_id: str
    ) -> None:
        identifier = await self._one(started_database, tenant_id)
        async with started_database.unit_of_work() as uow:
            row = await uow.breaks.require(identifier)
            with pytest.raises(ConflictError, match="cannot be deleted"):
                await uow.breaks.delete(row)


class TestTenantScoping:
    async def test_another_tenants_break_reads_as_absent(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            other = uow.tenants.create(slug="rival", display_name="Rival")
            await uow.flush()
            other_id = str(other.id)
            await uow.breaks.observe(
                [_break("ACC1")], tenant_id=other_id, definition=DEFINITION, when="2026-09-01"
            )
            await uow.flush()
            [row] = await uow.breaks.for_definition(other_id, DEFINITION)
            identifier = str(row.id)

        async with started_database.unit_of_work() as uow:
            with pytest.raises(NotFoundError, match="no break"):
                await uow.breaks.in_tenant(identifier, tenant_id)


class TestAMissingSideIsNotZero:
    async def test_nothing_on_one_side_is_stored_as_nothing(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """ "Nothing on the right" and "zero on the right" are different breaks,
        and storing the first as the second turns a missing record into a
        balanced one."""
        await _observe(
            started_database,
            tenant_id,
            [_break("ACC1", kind=BreakKind.MISSING, left="100.00", right=None)],
            "2026-09-01",
        )
        async with started_database.unit_of_work() as uow:
            [row] = await uow.breaks.for_definition(tenant_id, DEFINITION)
        assert row.right_value == ""
        assert row.right_value != "0"
