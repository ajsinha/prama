"""The persisted evidence ledger.

The in-memory ledger already has the chain arithmetic tested. What is new here
is a database, and a database introduces three failures the in-memory version
cannot have: two writers claiming the same position, a stored hash that no
longer matches its stored content, and an erasure that breaks everything after
it. Those are what this file is about.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.core.errors import ConflictError, NotFoundError
from prama.db import Database
from prama.evidence.ledger import verify
from prama.evidence.record import GENESIS, EvidenceRecord

pytestmark = pytest.mark.anyio


def _record(**overrides: object) -> EvidenceRecord:
    base: dict[str, object] = {
        "plan_id": "ir:sha256:abc",
        "control_id": "01CONTROL",
        "dataset": "positions_eod",
        "verdict": "pass",
        "metrics": {"scanned_rows": 1000.0, "violating_rows": 0.0},
        "started_at": "2026-09-08T06:00:00Z",
        "finished_at": "2026-09-08T06:00:03Z",
        "duration_ms": 3000,
    }
    base.update(overrides)
    return EvidenceRecord(**base)  # type: ignore[arg-type]


class TestAppending:
    async def test_the_first_record_starts_from_genesis(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            stored = await uow.evidence.append(_record(), tenant_id=tenant_id)
            assert stored.sequence == 0
            assert stored.previous_hash == GENESIS

    async def test_each_record_links_to_the_one_before(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            first = await uow.evidence.append(_record(), tenant_id=tenant_id)
            second = await uow.evidence.append(_record(verdict="fail"), tenant_id=tenant_id)
            assert second.sequence == 1
            assert second.previous_hash == first.record_hash

    async def test_the_caller_cannot_choose_the_position(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """A caller that could choose sequence and previous hash could write a
        record that looked linked and was not, and the whole guarantee would
        rest on every caller getting it right."""
        async with started_database.unit_of_work() as uow:
            await uow.evidence.append(_record(), tenant_id=tenant_id)
            forged = await uow.evidence.append(
                _record(sequence=999, previous_hash="f" * 64), tenant_id=tenant_id
            )
            assert forged.sequence == 1
            assert forged.previous_hash != "f" * 64

    async def test_a_record_with_no_tenant_is_refused(self, started_database: Database) -> None:
        async with started_database.unit_of_work() as uow:
            with pytest.raises(ConflictError, match="needs a tenant"):
                await uow.evidence.append(_record())

    async def test_two_tenants_have_independent_chains(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """Per-tenant, so one estate's activity cannot be inferred from
        another's sequence numbers — and so a tenant's chain can be exported
        and verified on its own."""
        async with started_database.unit_of_work() as uow:
            other = uow.tenants.create(slug="other-bank", display_name="Other")
            await uow.flush()
            await uow.evidence.append(_record(), tenant_id=tenant_id)
            await uow.evidence.append(_record(), tenant_id=tenant_id)
            first_elsewhere = await uow.evidence.append(_record(), tenant_id=str(other.id))
            assert first_elsewhere.sequence == 0
            assert first_elsewhere.previous_hash == GENESIS


class TestTheChainVerifiesAfterARoundTrip:
    async def test_what_was_written_verifies_when_read_back(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """The property that makes persistence worth anything. The in-memory
        chain verifying says nothing about whether the database preserved it."""
        async with started_database.unit_of_work() as uow:
            for index in range(5):
                await uow.evidence.append(
                    _record(verdict="pass" if index % 2 else "fail"), tenant_id=tenant_id
                )
            verification = await uow.evidence.verify(tenant_id)

        assert verification.is_intact, verification.render()

    async def test_a_float_metric_survives_as_the_same_hash(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """A count written as 8.0 and read back as 8 must hash the same, or a
        chain breaks on a driver upgrade — which has nothing to do with the
        data."""
        async with started_database.unit_of_work() as uow:
            written = await uow.evidence.append(
                _record(metrics={"scanned_rows": 8.0}), tenant_id=tenant_id
            )
            [read] = await uow.evidence.chain(tenant_id)
            assert read.content_hash == written.content_hash

    async def test_tampering_with_stored_content_is_detectable(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """The one failure this subsystem exists to prevent. The hashes are
        *stored*, not recomputed on read — recomputing would launder a tampered
        row into a valid one."""
        from sqlalchemy import text

        async with started_database.unit_of_work() as uow:
            await uow.evidence.append(_record(verdict="fail"), tenant_id=tenant_id)
            await uow.commit()

        # Reaching past the DAO on purpose: this is what tampering looks like,
        # and no honest path through Prama can produce it.
        with started_database.sync_engine().begin() as connection:
            connection.execute(text("UPDATE ev_record SET verdict = 'pass' WHERE sequence = 0"))

        async with started_database.unit_of_work() as uow:
            verification = await uow.evidence.verify(tenant_id)

        assert not verification.is_intact
        assert any(breach.kind == "content" for breach in verification.breaches)


class TestVerificationUsesStoredHashes:
    """The distinction the whole subsystem turns on.

    ``EvidenceRecord.content_hash`` is a computed property, so a record
    reconstructed from a row hashes whatever the row currently holds —
    tampered content included. Verification has to compare the *stored* hash
    against what the *stored* content hashes to, and nothing else.
    """

    async def test_the_stored_form_carries_the_stored_hashes(
        self, started_database: Database, tenant_id: str
    ) -> None:
        from sqlalchemy import text

        async with started_database.unit_of_work() as uow:
            await uow.evidence.append(_record(), tenant_id=tenant_id)
            await uow.commit()

        with started_database.sync_engine().begin() as connection:
            connection.execute(text("UPDATE ev_record SET dataset = 'somewhere_else'"))

        async with started_database.unit_of_work() as uow:
            [stored] = await uow.evidence.as_stored(tenant_id)
            [reconstructed] = await uow.evidence.chain(tenant_id)

        # The stored hash still describes the original content; the
        # reconstructed record cheerfully hashes the tampered content.
        assert stored["dataset"] == "somewhere_else"
        assert stored["content_hash"] != reconstructed.content_hash

    async def test_a_broken_link_is_found_as_well_as_broken_content(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """Two independent checks. Content hashing catches an edited field;
        link checking catches a record swapped in wholesale with a
        self-consistent hash of its own."""
        from sqlalchemy import text

        async with started_database.unit_of_work() as uow:
            for _ in range(3):
                await uow.evidence.append(_record(), tenant_id=tenant_id)
            await uow.commit()

        with started_database.sync_engine().begin() as connection:
            connection.execute(
                text("UPDATE ev_record SET previous_hash = :h WHERE sequence = 2"),
                {"h": "0" * 64},
            )

        async with started_database.unit_of_work() as uow:
            verification = await uow.evidence.verify(tenant_id)

        assert not verification.is_intact
        assert {breach.kind for breach in verification.breaches} & {"link", "order", "genesis"}


class TestErasure:
    async def test_erasing_keeps_the_chain_verifiable(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """A right to erasure and an immutable hash chain are in genuine
        conflict. Deleting the record breaks every hash after it; refusing is
        not lawful. The content goes, the hash stays, and the chain still
        links."""
        async with started_database.unit_of_work() as uow:
            for _ in range(3):
                await uow.evidence.append(_record(), tenant_id=tenant_id)
            await uow.evidence.erase(
                tenant_id, 1, by="dpo@acme", authority="DSAR-2026-114", at="2026-09-08T09:00:00Z"
            )
            verification = await uow.evidence.verify(tenant_id)

        assert verification.is_intact, verification.render()

    async def test_the_erasure_is_visible_rather_than_a_hole(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            await uow.evidence.append(_record(), tenant_id=tenant_id)
            await uow.evidence.erase(tenant_id, 0, by="dpo@acme", authority="DSAR-2026-114")
            [record] = await uow.evidence.chain(tenant_id)

        assert record.is_erased
        assert record.tombstone is not None
        assert record.tombstone.erased_by == "dpo@acme"
        assert record.tombstone.authority == "DSAR-2026-114"
        assert record.dataset == ""

    async def test_the_record_count_is_unchanged_by_erasure(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """Nothing is removed. A chain that got shorter would be one whose
        gaps nobody could account for."""
        async with started_database.unit_of_work() as uow:
            for _ in range(3):
                await uow.evidence.append(_record(), tenant_id=tenant_id)
            await uow.evidence.erase(tenant_id, 1, by="dpo@acme")
            assert await uow.evidence.count_for(tenant_id) == 3

    async def test_erasing_twice_is_not_a_second_erasure(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """Idempotent, because a retried request must not overwrite the
        original content hash the chain depends on."""
        async with started_database.unit_of_work() as uow:
            await uow.evidence.append(_record(), tenant_id=tenant_id)
            first = await uow.evidence.erase(tenant_id, 0, by="dpo@acme")
            second = await uow.evidence.erase(tenant_id, 0, by="someone-else")
            assert second.tombstone is not None
            assert first.tombstone is not None
            assert second.tombstone.erased_by == "dpo@acme"
            assert second.content_hash == first.content_hash

    async def test_erasing_a_missing_record_says_a_gap_is_a_finding(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            with pytest.raises(NotFoundError, match="no evidence record at sequence"):
                await uow.evidence.erase(tenant_id, 42, by="dpo@acme")


class TestReading:
    async def test_failing_includes_error_and_skipped(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """A control that could not run has no verdict. A list of problems that
        quietly omitted it would report the controls that did run as though
        they were all of them."""
        async with started_database.unit_of_work() as uow:
            for verdict in ("pass", "fail", "error", "skipped", "indeterminate"):
                await uow.evidence.append(_record(verdict=verdict), tenant_id=tenant_id)
            failing = await uow.evidence.failing(tenant_id)

        assert {record.verdict for record in failing} == {
            "fail",
            "error",
            "skipped",
            "indeterminate",
        }

    async def test_latest_per_control_does_not_weight_by_schedule(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """A scorecard built from every record would weight an hourly control
        sixty times as heavily as a daily one, which measures the schedule
        rather than the data."""
        async with started_database.unit_of_work() as uow:
            for _ in range(10):
                await uow.evidence.append(
                    _record(control_id="hourly", verdict="pass"), tenant_id=tenant_id
                )
            await uow.evidence.append(
                _record(control_id="daily", verdict="fail"), tenant_id=tenant_id
            )
            latest = await uow.evidence.latest_per_control(tenant_id)

        assert set(latest) == {"hourly", "daily"}
        assert latest["daily"].verdict == "fail"

    async def test_latest_per_control_takes_the_most_recent(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            await uow.evidence.append(_record(control_id="c", verdict="fail"), tenant_id=tenant_id)
            await uow.evidence.append(_record(control_id="c", verdict="pass"), tenant_id=tenant_id)
            latest = await uow.evidence.latest_per_control(tenant_id)

        assert latest["c"].verdict == "pass"

    async def test_records_are_scoped_to_their_dataset(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            await uow.evidence.append(_record(dataset="a"), tenant_id=tenant_id)
            await uow.evidence.append(_record(dataset="b"), tenant_id=tenant_id)
            found = await uow.evidence.for_dataset(tenant_id, "a")

        assert [record.dataset for record in found] == ["a"]


class TestRuns:
    async def test_a_run_groups_the_records_it_produced(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """Without it, the only way to group records is timestamp proximity,
        which merges two runs that overlapped and splits one that was slow."""
        async with started_database.unit_of_work() as uow:
            run = await uow.evidence_runs.start(
                tenant_id=tenant_id, started_at="2026-09-08T06:00:00Z"
            )
            run_id = str(run.id)
            for _ in range(3):
                await uow.evidence.append(_record(), tenant_id=tenant_id, run_id=run_id)
            finished = await uow.evidence_runs.finish(run_id, finished_at="2026-09-08T06:05:00Z")
            assert finished.record_count == 3
            assert len(await uow.evidence.for_run(run_id)) == 3

    async def test_an_unfinished_run_is_a_first_class_query(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """Its controls have no verdict, and every screen built on "the latest
        evidence" is silently missing them."""
        async with started_database.unit_of_work() as uow:
            await uow.evidence_runs.start(tenant_id=tenant_id, started_at="2026-09-08T06:00:00Z")
            done = await uow.evidence_runs.start(
                tenant_id=tenant_id, started_at="2026-09-08T07:00:00Z"
            )
            await uow.evidence_runs.finish(str(done.id), finished_at="2026-09-08T07:05:00Z")
            unfinished = await uow.evidence_runs.unfinished(tenant_id)

        assert len(unfinished) == 1
        assert unfinished[0].status == "running"


class TestSamples:
    async def test_the_digest_is_the_identity(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """The same failing rows recorded twice are one set. Overwriting would
        reset the expiry clock on personal data every time the same failure
        recurred."""
        async with started_database.unit_of_work() as uow:
            first = await uow.samples.put(
                tenant_id=tenant_id,
                digest="d" * 64,
                rows=[{"account_id": "A1"}],
                created_at="2026-09-01T00:00:00Z",
                expires_at="2026-10-01T00:00:00Z",
            )
            again = await uow.samples.put(
                tenant_id=tenant_id,
                digest="d" * 64,
                rows=[{"account_id": "A1"}],
                created_at="2026-09-08T00:00:00Z",
                expires_at="2026-11-01T00:00:00Z",
            )
        assert again.created_at == first.created_at
        assert again.expires_at == "2026-10-01T00:00:00Z"

    async def test_samples_expire_on_their_own_clock(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            await uow.samples.put(
                tenant_id=tenant_id,
                digest="a" * 64,
                rows=[],
                created_at="2026-01-01T00:00:00Z",
                expires_at="2026-02-01T00:00:00Z",
            )
            await uow.samples.put(
                tenant_id=tenant_id,
                digest="b" * 64,
                rows=[],
                created_at="2026-01-01T00:00:00Z",
                expires_at="2027-01-01T00:00:00Z",
            )
            expired = await uow.samples.expired("2026-06-01T00:00:00Z")

        assert [sample.digest for sample in expired] == ["a" * 64]

    async def test_a_sample_without_an_expiry_never_expires(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            await uow.samples.put(
                tenant_id=tenant_id, digest="c" * 64, rows=[], created_at="2026-01-01T00:00:00Z"
            )
            assert await uow.samples.expired("2099-01-01T00:00:00Z") == []

    async def test_forgetting_samples_leaves_the_record_truthful(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """The asymmetry is the point: the rows are the personal data, the
        record is the audit trail. A record whose samples have expired still
        says truthfully that a control failed and how many rows failed it — it
        simply can no longer show which."""
        async with started_database.unit_of_work() as uow:
            await uow.samples.put(
                tenant_id=tenant_id,
                digest="e" * 64,
                rows=[{"x": 1}],
                created_at="2026-01-01T00:00:00Z",
            )
            await uow.evidence.append(
                _record(verdict="fail", samples_digest="e" * 64, sample_count=1),
                tenant_id=tenant_id,
            )
            assert await uow.samples.forget("e" * 64) is True
            [record] = await uow.evidence.chain(tenant_id)
            [stored] = await uow.evidence.as_stored(tenant_id)

        assert record.verdict == "fail"
        assert record.sample_count == 1
        # `as_stored`, not `record.to_dict()` — finding T11. `content_hash` and
        # `record_hash` are computed properties, so `to_dict()` emits hashes
        # over whatever the object currently holds and `verify` compares them
        # against themselves. It is intact for any content at all:
        # `replace(r, verdict="pass", dataset="TAMPERED")` verifies clean. The
        # file's own `TestVerificationUsesStoredHashes` explains this trap; this
        # line reached for the wrong helper.
        assert verify([stored]).is_intact

    async def test_forgetting_what_is_not_there_is_not_an_error(
        self, started_database: Database
    ) -> None:
        async with started_database.unit_of_work() as uow:
            assert await uow.samples.forget("f" * 64) is False


class TestTheSchemaAgreesWithTheEnums:
    """Derive, never restate — checked, because this one was got wrong.

    The verdict constraint was first written from memory and listed ``warn``
    and ``unknown``, neither of which the engine produces, while omitting
    ``indeterminate``, which it does. The result was an integrity error at the
    end of a run: the finding was real, and there was nowhere to put it.
    """

    def test_every_verdict_the_engine_produces_is_accepted(self) -> None:
        from pathlib import Path

        from prama.ir import Verdict

        schema = (Path(__file__).resolve().parents[2] / "schema" / "sqlite.sql").read_text()
        clause = schema.split("ck_ev_record_verdict")[1].split("))")[0]
        for verdict in Verdict:
            assert f"'{verdict.value}'" in clause, verdict.value

    def test_the_constraint_names_no_verdict_the_engine_cannot_produce(self) -> None:
        """The other direction. A constraint accepting values nothing writes
        is a constraint nobody has checked against the code."""
        import re
        from pathlib import Path

        from prama.ir import Verdict

        schema = (Path(__file__).resolve().parents[2] / "schema" / "sqlite.sql").read_text()
        clause = schema.split("ck_ev_record_verdict")[1].split("))")[0]
        listed = set(re.findall(r"'([a-z_]+)'", clause))
        assert listed == {verdict.value for verdict in Verdict}

    def test_every_coverage_width_is_accepted(self) -> None:
        from pathlib import Path

        from prama.execute import Coverage

        schema = (Path(__file__).resolve().parents[2] / "schema" / "sqlite.sql").read_text()
        clause = schema.split("ck_ev_record_coverage")[1].split("))")[0]
        for coverage in Coverage:
            assert f"'{coverage.value}'" in clause, coverage.value


class TestTheDaoHasNoUpdatePath:
    def test_erase_is_the_only_method_that_writes_to_an_existing_row(self) -> None:
        """Append-only enforced by the shape of the class, not by convention.

        A future "fix the verdict" helper would be the end of the guarantee,
        and it would look entirely reasonable in review — so the absence is
        asserted rather than trusted.
        """
        from prama.db.dao.evidence import EvidenceDao

        writers = {
            name
            for name in dir(EvidenceDao)
            if not name.startswith("_")
            and any(word in name for word in ("update", "set_", "remove", "amend"))
        }
        assert writers == set(), writers

    async def test_delete_is_inherited_and_refused(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """The hole the guarantee would otherwise have.

        ``Dao.delete`` is inherited, does exactly what a caller under time
        pressure wants, and would look entirely reasonable in review — so it is
        overridden to refuse, with the reason and the two things to do instead.
        """
        async with started_database.unit_of_work() as uow:
            await uow.evidence.append(_record(), tenant_id=tenant_id)
            stored = await uow.evidence.row_at(tenant_id, 0)
            assert stored is not None
            with pytest.raises(ConflictError, match="cannot be deleted"):
                await uow.evidence.delete(stored)


class TestToDictCannotBeUsedToVerify:
    """Finding T11, pinned. `verify([record.to_dict()])` proves nothing.

    `content_hash` and `record_hash` are computed properties. `to_dict()`
    therefore emits hashes over whatever the object currently holds, and
    `verify` compares them against themselves — a tautology that reads exactly
    like tamper-evidence.
    """

    def test_a_reconstructed_record_verifies_whatever_it_says(self) -> None:
        import dataclasses

        original = _record()
        tampered = dataclasses.replace(
            original, verdict="pass", dataset="TAMPERED", sample_count=99
        )
        assert verify([tampered.to_dict()]).is_intact, (
            "if this ever fails, to_dict() has stopped recomputing its hashes "
            "and the warning below can go"
        )
        assert tampered.content_hash != original.content_hash, (
            "the content differs, and only the *stored* hash can reveal it"
        )
