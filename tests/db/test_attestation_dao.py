"""The persisted attestation.

The value object's own arithmetic is tested in ``tests/report``. What a database
adds is a round trip: a hash computed over a Python object on the way in and
recomputed over a rebuilt object on the way out. If those two objects differ in
any way the hash covers — a tuple that comes back a list, an integer that comes
back a string — every attestation ever signed reads as tampered, and the alarm
that means "somebody edited the record" is on permanently and therefore off.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from prama.core.errors import ConflictError, NotFoundError
from prama.db import Database
from prama.report.attestation import Attestation, Coverage, Exception_

pytestmark = pytest.mark.anyio

KEY = b"a-deployment-key"


def _attestation(tenant_id: str, **overrides: object) -> Attestation:
    base: dict[str, object] = {
        "attester_id": "01ALICE",
        "attester_name": "Alice Chen",
        "statement": "I have reviewed the controls for September.",
        "scope": "Trading book",
        "period_start": "2026-09-01",
        "period_end": "2026-09-30",
        "coverage": Coverage(
            controls_in_scope=12, controls_run=11, passed=9, failed=2, never_ran=1
        ),
        "exceptions": (
            Exception_(
                control_id="01C1",
                dataset="positions_eod",
                verdict="fail",
                detail="12 of 1,000 rows",
                disposition="DQ-1187 raised",
            ),
            Exception_(control_id="01C2", dataset="trades", verdict="not_established"),
        ),
        "evidence_root": "ab" * 32,
        "evidence_records": 431,
        "signed_at": "2026-10-01T09:15:00Z",
        "tenant_id": tenant_id,
    }
    base.update(overrides)
    return Attestation(**base)  # type: ignore[arg-type]


class TestTheRoundTrip:
    async def test_what_is_read_back_is_the_value_that_was_signed(
        self, started_database: Database, tenant_id: str
    ) -> None:
        signed = _attestation(tenant_id)
        async with started_database.unit_of_work() as uow:
            row = await uow.attestations.sign(signed, seal=signed.seal(KEY))
            identifier = str(row.id)

        async with started_database.unit_of_work() as uow:
            read = await uow.attestations.value(identifier)

        assert read == signed

    async def test_the_hash_survives_the_database(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """Stronger than equality of the objects: the stored hash and the hash
        recomputed after a round trip must agree, because that comparison is
        exactly what tamper detection does."""
        signed = _attestation(tenant_id)
        async with started_database.unit_of_work() as uow:
            row = await uow.attestations.sign(signed, seal=signed.seal(KEY))
            identifier = str(row.id)

        async with started_database.unit_of_work() as uow:
            intact, sealed = await uow.attestations.verify(identifier, KEY)

        assert (intact, sealed) == (True, True)

    async def test_a_seal_from_another_deployment_is_a_separate_answer(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """Intact but not sealed. Collapsing this into one boolean would make
        "somebody edited this" indistinguishable from "this came from another
        deployment" — different incidents with different responses."""
        signed = _attestation(tenant_id)
        async with started_database.unit_of_work() as uow:
            row = await uow.attestations.sign(signed, seal=signed.seal(b"elsewhere"))
            identifier = str(row.id)

        async with started_database.unit_of_work() as uow:
            intact, sealed = await uow.attestations.verify(identifier, KEY)

        assert intact is True
        assert sealed is False

    async def test_an_edited_row_is_reported_as_not_intact(
        self, started_database: Database, tenant_id: str
    ) -> None:
        signed = _attestation(tenant_id)
        async with started_database.unit_of_work() as uow:
            row = await uow.attestations.sign(signed, seal=signed.seal(KEY))
            identifier = str(row.id)

        with started_database.sync_engine().begin() as connection:
            connection.execute(text("UPDATE att_attestation SET statement = 'Everything passed.'"))

        async with started_database.unit_of_work() as uow:
            intact, sealed = await uow.attestations.verify(identifier, KEY)

        assert intact is False
        assert sealed is False

    async def test_editing_the_coverage_is_caught_too(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """The numbers are the part somebody would be tempted to improve."""
        signed = _attestation(tenant_id)
        async with started_database.unit_of_work() as uow:
            row = await uow.attestations.sign(signed, seal=signed.seal(KEY))
            identifier = str(row.id)

        with started_database.sync_engine().begin() as connection:
            connection.execute(
                text(
                    "UPDATE att_attestation SET coverage_json = "
                    '\'{"controls_in_scope": 12, "controls_run": 12, "passed": 12, '
                    '"failed": 0, "not_established": 0, "errored": 0, "never_ran": 0}\''
                )
            )

        async with started_database.unit_of_work() as uow:
            intact, _ = await uow.attestations.verify(identifier, KEY)

        assert intact is False


class TestItIsAppendOnly:
    async def test_delete_refuses_and_says_what_to_do_instead(
        self, started_database: Database, tenant_id: str
    ) -> None:
        signed = _attestation(tenant_id)
        async with started_database.unit_of_work() as uow:
            row = await uow.attestations.sign(signed, seal=signed.seal(KEY))
            with pytest.raises(ConflictError) as caught:
                await uow.attestations.delete(row)

        assert "supersede" in str(caught.value.remedy).lower()

    async def test_the_dao_offers_no_way_to_amend_one(self) -> None:
        """A guard on the shape of the class, not on one call: an ``update``
        arriving later would be the whole safeguard gone, silently."""
        from prama.db.dao.attestation import AttestationDao

        assert not hasattr(AttestationDao, "update")
        assert not hasattr(AttestationDao, "amend")

    async def test_superseding_something_that_does_not_exist_is_refused(
        self, started_database: Database, tenant_id: str
    ) -> None:
        signed = _attestation(tenant_id)
        async with started_database.unit_of_work() as uow:
            with pytest.raises(NotFoundError):
                await uow.attestations.sign(signed, seal=signed.seal(KEY), supersedes="01NOTHING")

    async def test_a_superseded_row_keeps_its_own_seal(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """Being replaced does not make the earlier statement untrue, and the
        history is worth more than the correction on its own."""
        first = _attestation(tenant_id, statement="First look.")
        async with started_database.unit_of_work() as uow:
            row = await uow.attestations.sign(first, seal=first.seal(KEY))
            first_id = str(row.id)

        second = _attestation(tenant_id, statement="Corrected after the re-run.")
        async with started_database.unit_of_work() as uow:
            await uow.attestations.sign(second, seal=second.seal(KEY), supersedes=first_id)

        async with started_database.unit_of_work() as uow:
            intact, sealed = await uow.attestations.verify(first_id, KEY)
            earlier = await uow.attestations.require(first_id)

        assert (intact, sealed) == (True, True)
        assert earlier.statement == "First look."
        assert earlier.superseded_by


class TestWhatIsCurrent:
    async def test_current_excludes_what_has_been_replaced(
        self, started_database: Database, tenant_id: str
    ) -> None:
        first = _attestation(tenant_id, statement="First.")
        async with started_database.unit_of_work() as uow:
            first_id = str((await uow.attestations.sign(first, seal=first.seal(KEY))).id)

        second = _attestation(tenant_id, statement="Second.")
        async with started_database.unit_of_work() as uow:
            await uow.attestations.sign(second, seal=second.seal(KEY), supersedes=first_id)

        async with started_database.unit_of_work() as uow:
            current = await uow.attestations.current(tenant_id)
            history = await uow.attestations.history(tenant_id, "Trading book")

        assert [item.statement for item in current] == ["Second."]
        assert len(history) == 2

    async def test_another_tenants_attestation_is_not_visible(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            other = uow.tenants.create(slug="rival-bank", display_name="Rival Bank")
            await uow.flush()
            other_id = str(other.id)

        mine = _attestation(tenant_id)
        theirs = _attestation(other_id)
        async with started_database.unit_of_work() as uow:
            await uow.attestations.sign(mine, seal=mine.seal(KEY))
            await uow.attestations.sign(theirs, seal=theirs.seal(KEY))

        async with started_database.unit_of_work() as uow:
            current = await uow.attestations.current(tenant_id)

        assert len(current) == 1
        assert current[0].tenant_id == tenant_id


class TestItIsScopedToATenant:
    """Fetching by identifier is the path that forgets the tenant.

    A list is written against a tenant and stays that way; a detail page takes
    an identifier from the URL, and the check that the identifier belongs to
    the caller is the one that gets written on one screen and forgotten on the
    next. The forgotten screen is usually the one that prints the pack.
    """

    async def test_another_tenants_attestation_reads_as_absent(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            other = uow.tenants.create(slug="rival-bank", display_name="Rival Bank")
            await uow.flush()
            other_id = str(other.id)

        theirs = _attestation(other_id)
        async with started_database.unit_of_work() as uow:
            row = await uow.attestations.sign(theirs, seal=theirs.seal(KEY))
            identifier = str(row.id)

        async with started_database.unit_of_work() as uow:
            with pytest.raises(NotFoundError) as caught:
                await uow.attestations.in_tenant(identifier, tenant_id)

        # Absent, not forbidden: which identifiers exist elsewhere is not this
        # caller's business either.
        assert "no attestation" in str(caught.value)

    async def test_your_own_comes_back(self, started_database: Database, tenant_id: str) -> None:
        mine = _attestation(tenant_id)
        async with started_database.unit_of_work() as uow:
            identifier = str((await uow.attestations.sign(mine, seal=mine.seal(KEY))).id)

        async with started_database.unit_of_work() as uow:
            row = await uow.attestations.in_tenant(identifier, tenant_id)

        assert row.attester_name == "Alice Chen"
