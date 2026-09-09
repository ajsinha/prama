"""The control estate.

The failures these are written against are the ones that make a control store
worse than no control store: a row that disagrees with its own text, a
generator that fills the estate with duplicates of what it produced yesterday,
a control that was silenced "temporarily" three years ago, and a rejection that
either never comes back or comes back every night.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.core.errors import ValidationError
from prama.db import Database
from prama.db.dao.control import derived_fields
from prama.ir import lower
from prama.pql import parse_control

pytestmark = pytest.mark.anyio

UNIQUE = (
    "CHECK positions_eod HAS UNIQUE KEY (account_id, instrument_id) "
    "SEVERITY critical DIMENSION uniqueness BECAUSE 'declared grain'"
)
NOT_NULL = (
    "CHECK positions_eod.notional IS NOT NULL "
    "SEVERITY major DIMENSION completeness BECAUSE 'CDE for FRTB'"
)


class TestEverythingIsDerivedFromTheText:
    """A caller who could supply a severity could store a control whose text
    says ``minor`` and whose row says ``critical`` — and the row is what the
    alert router reads. Nothing would look wrong until an incident went to the
    wrong person at three in the morning."""

    def test_the_row_fields_come_from_the_pql(self) -> None:
        fields = derived_fields(UNIQUE)
        assert fields["severity"] == "critical"
        assert fields["dimensions_json"] == ["uniqueness"]
        assert fields["dataset"] == "positions_eod"

    def test_the_plan_id_matches_what_the_text_lowers_to(self) -> None:
        fields = derived_fields(UNIQUE)
        assert fields["plan_id"] == lower(parse_control(UNIQUE)).plan_id

    def test_the_content_hash_changes_with_the_text(self) -> None:
        assert derived_fields(UNIQUE)["content_hash"] != derived_fields(NOT_NULL)["content_hash"]

    def test_a_control_that_does_not_parse_is_refused(self) -> None:
        """Storing it would mean an estate holding a control nothing can
        execute, discovered at run time by a scheduler with nowhere to report
        it."""
        with pytest.raises(ValidationError, match="does not parse"):
            derived_fields("CHECK CHECK CHECK")

    async def test_the_stored_row_still_agrees_with_the_stored_text(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """Derive, never restate — checked by re-deriving, not by trusting."""
        async with started_database.unit_of_work() as uow:
            _, version = await uow.controls.declare(tenant_id=tenant_id, identity="i1", pql=UNIQUE)
            fresh = derived_fields(version.pql)
            assert version.severity == fresh["severity"]
            assert version.plan_id == fresh["plan_id"]
            assert list(version.dimensions_json) == fresh["dimensions_json"]

    async def test_a_caller_cannot_override_a_derived_field(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """``declare`` takes no severity, and the absence is the guarantee."""
        import inspect

        from prama.db.dao.control import ControlDao

        parameters = set(inspect.signature(ControlDao.declare).parameters)
        assert not parameters & {"severity", "plan_id", "dimensions", "content_hash", "name"}


class TestRegenerationIsIdempotent:
    async def test_declaring_the_same_control_twice_makes_one(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """Identity is derived from what a control is *about*, not its text, so
        a nightly generator does not fill the review queue with controls that
        already exist."""
        async with started_database.unit_of_work() as uow:
            first, _ = await uow.controls.declare(tenant_id=tenant_id, identity="i1", pql=UNIQUE)
            second, _ = await uow.controls.declare(tenant_id=tenant_id, identity="i1", pql=UNIQUE)
            assert first.id == second.id
            assert len(await uow.controls.history(str(first.id))) == 1

    async def test_an_unchanged_redeclaration_writes_no_new_version(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """A history full of entries differing only in their timestamp makes a
        genuine change impossible to find in the diff."""
        async with started_database.unit_of_work() as uow:
            control, first = await uow.controls.declare(
                tenant_id=tenant_id, identity="i1", pql=UNIQUE
            )
            _, again = await uow.controls.declare(tenant_id=tenant_id, identity="i1", pql=UNIQUE)
            assert again.version == first.version
            assert len(await uow.controls.history(str(control.id))) == 1

    async def test_a_changed_control_amends_rather_than_duplicating(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """An amend, not a correct: the old threshold really was the rule
        until now, and evidence written under it must still resolve to it."""
        async with started_database.unit_of_work() as uow:
            control, _ = await uow.controls.declare(tenant_id=tenant_id, identity="i1", pql=UNIQUE)
            _, changed = await uow.controls.declare(
                tenant_id=tenant_id,
                identity="i1",
                pql=UNIQUE.replace("critical", "major"),
            )
            history = await uow.controls.history(str(control.id))

        assert changed.version == 2
        assert changed.severity == "major"
        assert len(history) == 2
        # The superseded version is still there, still saying what it said.
        assert any(item.severity == "critical" for item in history)

    async def test_two_tenants_may_share_an_identity(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            other = uow.tenants.create(slug="other", display_name="Other")
            await uow.flush()
            mine, _ = await uow.controls.declare(tenant_id=tenant_id, identity="i1", pql=UNIQUE)
            theirs, _ = await uow.controls.declare(
                tenant_id=str(other.id), identity="i1", pql=UNIQUE
            )
            assert mine.id != theirs.id


class TestLifecycle:
    async def test_a_proposal_does_not_run(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """``proposed`` and ``suppressed`` are states a reader mistakes for
        running, and a coverage figure that counted them would claim protection
        the estate does not have."""
        async with started_database.unit_of_work() as uow:
            await uow.controls.declare(tenant_id=tenant_id, identity="i1", pql=UNIQUE)
            assert await uow.controls.live(tenant_id) == []

    async def test_accepting_a_proposal_makes_it_run(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            control, _ = await uow.controls.declare(tenant_id=tenant_id, identity="i1", pql=UNIQUE)
            await uow.controls.activate(str(control.id), approved_by="alice")
            live = await uow.controls.live(tenant_id)

        assert [version.status for version in live] == ["active"]
        assert live[0].approved_by == "alice"

    async def test_suppressing_needs_an_expiry_and_a_reason(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """A control muted with neither is one nobody turns back on, and the
        estate stops checking something without anyone deciding to."""
        async with started_database.unit_of_work() as uow:
            control, _ = await uow.controls.declare(tenant_id=tenant_id, identity="i1", pql=UNIQUE)
            with pytest.raises(ValidationError, match="expiry and a reason"):
                await uow.controls.suppress(str(control.id), until="", because="noisy")
            with pytest.raises(ValidationError, match="expiry and a reason"):
                await uow.controls.suppress(
                    str(control.id), until="2026-10-01T00:00:00Z", because="  "
                )

    async def test_a_suppression_past_its_expiry_is_reported_not_lifted(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """Turning it back on by itself would surprise whoever silenced it;
        leaving it silent for ever is how "temporary" becomes permanent.
        Naming them is the only honest option."""
        async with started_database.unit_of_work() as uow:
            control, _ = await uow.controls.declare(tenant_id=tenant_id, identity="i1", pql=UNIQUE)
            await uow.controls.activate(str(control.id), approved_by="alice")
            await uow.controls.suppress(
                str(control.id), until="2026-01-01T00:00:00Z", because="upstream migration"
            )
            overdue = await uow.controls.silenced_past_expiry(tenant_id, "2026-09-09T00:00:00Z")
            still_live = await uow.controls.live(tenant_id)

        assert [version.suppressed_because for version in overdue] == ["upstream migration"]
        assert still_live == []

    async def test_a_retired_control_is_kept(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """The evidence it produced has to stay attributable to something. A
        record naming a control that no longer exists is an audit trail with a
        hole in it."""
        async with started_database.unit_of_work() as uow:
            control, _ = await uow.controls.declare(tenant_id=tenant_id, identity="i1", pql=UNIQUE)
            await uow.controls.retire(str(control.id))
            assert await uow.controls.live(tenant_id) == []
            assert await uow.controls.current(str(control.id)) is not None


class TestRejections:
    async def test_an_unchanged_reproposal_is_recognised(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """Which is what a nightly generator produces. Asking again every
        night is the fastest way to lose a steward's attention."""
        digest = derived_fields(UNIQUE)["content_hash"]
        async with started_database.unit_of_work() as uow:
            await uow.rejections.record(
                tenant_id=tenant_id,
                identity="i1",
                content_hash=digest,
                reason="not_material",
                rejected_at="2026-09-08T00:00:00Z",
            )
            assert await uow.rejections.was_rejected(tenant_id, "i1", digest) is True

    async def test_a_materially_different_rewrite_is_asked_again(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """Rejecting a control does not reject every future version of it."""
        async with started_database.unit_of_work() as uow:
            await uow.rejections.record(
                tenant_id=tenant_id,
                identity="i1",
                content_hash=derived_fields(UNIQUE)["content_hash"],
                rejected_at="2026-09-08T00:00:00Z",
            )
            rewritten = derived_fields(UNIQUE.replace("critical", "minor"))["content_hash"]
            assert await uow.rejections.was_rejected(tenant_id, "i1", rewritten) is False

    async def test_the_reason_is_kept_for_the_learning_loop(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """ "Too noisy" and "incorrect" are different signals: one is a
        threshold problem and the other is a rule that should never have been
        proposed."""
        async with started_database.unit_of_work() as uow:
            await uow.rejections.record(
                tenant_id=tenant_id,
                identity="i1",
                reason="too_noisy",
                note="fires on every month end",
                rejected_at="2026-09-08T00:00:00Z",
            )
            [rejection] = await uow.rejections.for_tenant(tenant_id)

        assert rejection.reason == "too_noisy"
        assert rejection.note == "fires on every month end"


class TestTheSchemaAgreesWithTheEnums:
    def test_every_rejection_reason_is_accepted_by_the_constraint(self) -> None:
        """A constraint listing reasons the enum lacks accepts rows nothing can
        read; one missing a reason the enum has rejects an ordinary rejection at
        the worst possible moment."""
        from pathlib import Path

        from prama.propose.proposal import RejectionReason

        schema = (Path(__file__).resolve().parents[2] / "schema" / "sqlite.sql").read_text()
        clause = schema.split("ck_ctl_rejection_reason")[1].split("))")[0]
        for reason in RejectionReason:
            assert f"'{reason.value}'" in clause, reason.value

    def test_every_origin_is_accepted_by_the_constraint(self) -> None:
        from pathlib import Path

        from prama.core.provenance import Origin

        schema = (Path(__file__).resolve().parents[2] / "schema" / "sqlite.sql").read_text()
        clause = schema.split("ck_ctl_control_origin")[1].split("))")[0]
        for origin in Origin:
            assert f"'{origin.value}'" in clause, origin.value

    def test_every_severity_is_accepted_by_the_constraint(self) -> None:
        from pathlib import Path

        from prama.pql.ast import Severity

        schema = (Path(__file__).resolve().parents[2] / "schema" / "sqlite.sql").read_text()
        clause = schema.split("ck_ctl_control_severity")[1].split("))")[0]
        for severity in Severity:
            assert f"'{severity.value}'" in clause, severity.value
