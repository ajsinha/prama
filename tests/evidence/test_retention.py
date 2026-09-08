"""How long evidence is kept, and how it is let go.

The hard case is erasure: a right to be forgotten and an immutable hash chain
are in genuine conflict, and both obvious resolutions are wrong.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime, timedelta

import pytest

from prama.core.clock import Clock
from prama.core.errors import ValidationError
from prama.evidence import Archivist, Ledger, RetentionPolicy, Tier, verify
from prama.evidence.record import EvidenceRecord

NOW = datetime(2026, 4, 2, tzinfo=UTC)


class At(Clock):
    def now(self) -> datetime:
        return NOW

    def monotonic(self) -> float:
        return 0.0

    def epoch_millis(self) -> int:
        return int(NOW.timestamp() * 1000)


def a_ledger(ages_in_days: tuple[int, ...] = (1, 100, 500, 3000)) -> Ledger:
    ledger = Ledger()
    for days in ages_in_days:
        when = NOW - timedelta(days=days)
        ledger.append(
            EvidenceRecord(
                plan_id=f"ir:sha256:{days:064x}",
                dataset="positions_eod",
                verdict="pass",
                metrics={"scanned_rows": 100.0},
                parameters={"subject": "person-42"},
                finished_at=when.isoformat(),
                tenant_id="t1",
            )
        )
    return ledger


def archivist(policy: RetentionPolicy | None = None) -> Archivist:
    return Archivist(policy or RetentionPolicy(), clock=At())


class TestTiers:
    def test_evidence_ages_outward(self) -> None:
        counts = archivist().report(a_ledger())["counts"]
        assert counts["hot"] == 1
        assert counts["warm"] == 1
        assert counts["cold"] == 2

    def test_nothing_is_deleted_unless_the_policy_says_so(self) -> None:
        # A regulated estate often says never, and a policy that silently
        # deleted because a default said otherwise would be a compliance
        # failure caused by a default.
        counts = archivist().report(a_ledger((9999,)))["counts"]
        assert counts["expired"] == 0
        assert counts["cold"] == 1

    def test_expiry_happens_when_it_is_asked_for(self) -> None:
        policy = RetentionPolicy(hot_days=1, warm_days=2, cold_days=3, expire=True)
        assert archivist(policy).tier_of(a_ledger((9999,)).records()[0]) is Tier.EXPIRED

    def test_tiers_out_of_order_are_refused(self) -> None:
        with pytest.raises(ValidationError, match="out of order"):
            RetentionPolicy(hot_days=400, warm_days=90)

    def test_a_record_with_an_unreadable_date_stays_hot(self) -> None:
        # Deleting evidence because its date did not parse is not a trade
        # anybody would make deliberately.
        ledger = Ledger()
        ledger.append(EvidenceRecord(plan_id="p", finished_at="not a date"))
        assert archivist().tier_of(ledger.records()[0]) is Tier.HOT

    def test_the_policy_says_what_it_does(self) -> None:
        described = RetentionPolicy().describe()
        assert "Queryable for 90 days" in described
        assert "kept indefinitely" in described


class TestBundles:
    def test_a_bundle_is_two_files_so_neither_hides_the_other(self) -> None:
        bundle = archivist().bundle(a_ledger().records(), tenant_id="t1")
        assert set(bundle.files()) == {"manifest.json", "evidence.ndjson"}

    def test_it_verifies_itself(self) -> None:
        ok, detail = archivist().bundle(a_ledger().records()).check()
        assert ok
        assert "chain intact" in detail

    def test_a_truncated_bundle_is_detected(self) -> None:
        # The failure that matters for an archive is not a forged record. It is
        # a truncated file, and only the manifest's count reveals that.
        bundle = archivist().bundle(a_ledger().records())
        truncated = dataclasses.replace(bundle, payload="\n".join(bundle.payload.splitlines()[:-1]))
        ok, detail = truncated.check()
        assert not ok
        assert "incomplete" in detail

    def test_an_altered_record_is_detected(self) -> None:
        bundle = archivist().bundle(a_ledger().records())
        lines = bundle.payload.splitlines()
        tampered = json.loads(lines[0])
        tampered["verdict"] = "fail"
        lines[0] = json.dumps(tampered, sort_keys=True, separators=(",", ":"))
        ok, _ = dataclasses.replace(bundle, payload="\n".join(lines)).check()
        assert not ok

    def test_the_manifest_says_how_to_check_it(self) -> None:
        # For whoever opens this in ten years with nothing but a SHA-256
        # implementation.
        manifest = archivist().bundle(a_ledger().records()).manifest
        assert "SHA-256" in manifest.verification
        assert "sorted" in manifest.verification
        assert "tombstone" in manifest.verification

    def test_an_empty_bundle_is_refused(self) -> None:
        # It would look like a period in which nothing ran, which is a
        # different and much more alarming claim.
        with pytest.raises(ValidationError, match="nothing to bundle"):
            archivist().bundle([])

    def test_the_manifest_states_the_range_and_the_head(self) -> None:
        manifest = archivist().bundle(a_ledger().records(), tenant_id="t1").manifest
        assert manifest.tenant_id == "t1"
        assert manifest.from_sequence == 0
        assert manifest.to_sequence == 3
        assert manifest.chain_head
        assert manifest.merkle_root


class TestErasure:
    """A right to be forgotten, and an immutable chain, at the same time."""

    def test_the_chain_still_verifies_after_an_erasure(self) -> None:
        # Deleting the record would break every hash after it and destroy the
        # audit trail to satisfy one request. Refusing is not lawful.
        ledger = a_ledger()
        records = archivist().erase(ledger, [1], by="dpo@bank", authority="DSAR-118")
        result = verify(r.to_dict() for r in records)
        assert result.is_intact
        assert result.erased == 1

    def test_the_chain_head_does_not_move(self) -> None:
        # Which is what lets an erasure be applied to a bundle already written
        # without invalidating a root somebody has published.
        ledger = a_ledger()
        before = ledger.verify().head
        records = archivist().erase(ledger, [1], by="dpo@bank")
        assert verify(r.to_dict() for r in records).head == before

    def test_the_erased_record_carries_nothing_identifying(self) -> None:
        records = archivist().erase(a_ledger(), [1], by="dpo@bank")
        erased = json.dumps(records[1].to_dict())
        assert "person-42" not in erased
        assert "positions_eod" not in erased

    def test_but_it_still_says_a_control_ran(self) -> None:
        # A chain of records saying nothing at all about what it contains is
        # not an audit trail either.
        records = archivist().erase(a_ledger(), [1], by="dpo@bank")
        assert records[1].sequence == 1
        assert records[1].finished_at

    def test_the_tombstone_names_who_erased_it_and_under_what_authority(self) -> None:
        records = archivist().erase(a_ledger(), [1], by="dpo@bank", authority="DSAR-2026-118")
        tombstone = records[1].tombstone
        assert tombstone is not None
        assert tombstone.erased_by == "dpo@bank"
        assert tombstone.authority == "DSAR-2026-118"
        assert tombstone.erased_at

    def test_the_tombstone_does_not_record_the_subject(self) -> None:
        # Recording who was erased, in the ledger they were erased from, to
        # prove they were erased, would be absurd.
        records = archivist().erase(a_ledger(), [1], by="dpo@bank", authority="DSAR-118")
        assert "person-42" not in json.dumps(records[1].tombstone.to_dict())  # type: ignore[union-attr]

    def test_erasing_twice_changes_nothing(self) -> None:
        ledger = a_ledger()
        once = archivist().erase(ledger, [1], by="dpo@bank")
        twice = once[1].erase(by="somebody-else")
        assert twice.tombstone is not None
        assert twice.tombstone.erased_by == "dpo@bank"

    def test_untouched_records_are_untouched(self) -> None:
        records = archivist().erase(a_ledger(), [1], by="dpo@bank")
        assert records[0].dataset == "positions_eod"
        assert records[2].dataset == "positions_eod"

    def test_a_bundle_of_erased_records_still_verifies(self) -> None:
        ledger = a_ledger()
        records = archivist().erase(ledger, [1], by="dpo@bank")
        bundle = archivist().bundle(records)
        ok, _ = bundle.check()
        assert ok
        assert bundle.manifest.erased == 1

    def test_verification_says_what_it_can_no_longer_prove(self) -> None:
        # An auditor must be told that a record was erased rather than have it
        # be invisible — and that what is verified about it is weaker.
        records = archivist().erase(a_ledger(), [1], by="dpo@bank")
        rendered = verify(r.to_dict() for r in records).render()
        assert "erased" in rendered
        assert "their contents are gone" in rendered
