"""The evidence format across versions.

A hashed record format that cannot evolve is a format that gets frozen or gets
broken, and the second is worse: emitting a newly added field unconditionally
changes the content of every record already written, breaks every hash after
the first, and presents as an estate-wide tampering alert the morning after a
deploy. These tests are the reason that cannot happen here.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.evidence.ledger import Ledger, verify
from prama.evidence.record import (
    EVIDENCE_VERSION,
    FIELDS_SINCE,
    EvidenceRecord,
    _version_tuple,
)

#: A chain written by a 1.0 build, hashes and all. Frozen here on purpose: it
#: is the only way to prove a *later* build reads it unchanged, and
#: regenerating it from today's code would make the test prove nothing.
LEGACY_CHAIN: list[dict[str, object]] = [
    {
        "evidence_version": "1.0",
        "sequence": 0,
        "plan_id": "ir:sha256:abc",
        "control_id": "01CONTROL",
        "control_version": 1,
        "dataset": "positions_eod",
        "binding": "",
        "snapshot": {"kind": "wall_clock", "identifier": "", "exact": False},
        "parameters": {},
        "engine": "postgresql",
        "coverage": "full",
        "verdict": "pass",
        "metrics": {"scanned_rows": 1000, "violating_rows": 0},
        "samples_digest": "",
        "sample_count": 0,
        "started_at": "2026-03-04T06:00:00Z",
        "finished_at": "2026-03-04T06:00:03Z",
        "duration_ms": 3000,
        "triggered_by": "schedule",
        "tenant_id": "01TENANT",
        "detail": "",
    }
]


def _seal(payload: dict[str, object], previous: str) -> dict[str, object]:
    """Hash a legacy payload the way a 1.0 build did: over its own fields."""
    import hashlib

    from prama.core.pjson import canonical

    content = hashlib.sha256(canonical(payload)).hexdigest()
    return {
        **payload,
        "previous_hash": previous,
        "content_hash": content,
        "record_hash": hashlib.sha256((previous + content).encode("ascii")).hexdigest(),
    }


class TestOldRecordsSurviveANewBuild:
    def test_a_ten_record_written_under_one_zero_still_verifies(self) -> None:
        """The test this whole mechanism exists for."""
        sealed = _seal(LEGACY_CHAIN[0], "0" * 64)
        verification = verify([sealed])
        assert verification.is_intact, verification.render()

    def test_a_one_zero_record_read_back_hashes_to_what_was_stored(self) -> None:
        """Reconstructed by today's code, which knows about two fields the
        record does not have. It must not emit them."""
        sealed = _seal(LEGACY_CHAIN[0], "0" * 64)
        record = EvidenceRecord.from_dict(sealed)
        assert record.evidence_version == "1.0"
        assert record.content_hash == sealed["content_hash"]

    def test_a_one_zero_record_does_not_gain_the_new_fields(self) -> None:
        record = EvidenceRecord.from_dict(_seal(LEGACY_CHAIN[0], "0" * 64))
        content = record.content()
        for field in FIELDS_SINCE:
            assert field not in content, field

    def test_the_new_fields_default_harmlessly_on_an_old_record(self) -> None:
        """Present on the object, absent from the hash. A reader gets the
        empty answer rather than an attribute error."""
        record = EvidenceRecord.from_dict(_seal(LEGACY_CHAIN[0], "0" * 64))
        assert record.dimensions == ()
        assert record.criticality == 4

    def test_a_mixed_chain_verifies(self) -> None:
        """The realistic case: a chain that spans an upgrade. Records written
        before the deploy are 1.0, records after it are 1.1, and the links
        between them have to hold."""
        legacy = _seal(LEGACY_CHAIN[0], "0" * 64)
        ledger = Ledger([EvidenceRecord.from_dict(legacy)])
        ledger.append(
            EvidenceRecord(
                dataset="positions_eod",
                verdict="fail",
                dimensions=("uniqueness",),
                criticality=1,
                tenant_id="01TENANT",
            )
        )
        records = ledger.records()
        assert records[0].evidence_version == "1.0"
        assert records[1].evidence_version == EVIDENCE_VERSION

        # The first record's stored hashes, the second's computed ones.
        payloads = [legacy, records[1].to_dict()]
        verification = verify(payloads)
        assert verification.is_intact, verification.render()


class TestNewRecords:
    def test_the_new_fields_are_hashed(self) -> None:
        """A field left out of the hash is a field somebody can change without
        detection, which would make carrying the dimension pointless."""
        base = EvidenceRecord(dataset="d", dimensions=("uniqueness",), criticality=1)
        retiered = EvidenceRecord(dataset="d", dimensions=("uniqueness",), criticality=4)
        redimensioned = EvidenceRecord(dataset="d", dimensions=("validity",), criticality=1)
        assert base.content_hash != retiered.content_hash
        assert base.content_hash != redimensioned.content_hash

    def test_erasure_clears_the_dimensions_too(self) -> None:
        """Everything that could identify anything goes. A dimension is not
        personal data, but leaving one field behind on a record whose content
        was erased is how the next field gets left behind too."""
        record = EvidenceRecord(dataset="d", dimensions=("uniqueness",), criticality=1)
        erased = record.erase(by="dpo@acme")
        assert erased.dimensions == ()
        # The chain still holds: the original content hash is preserved.
        assert erased.content_hash == record.content_hash


class TestVersionComparison:
    def test_it_compares_numerically_not_as_text(self) -> None:
        """ "1.10" sorts after "1.9", which string comparison gets backwards —
        and getting it backwards means a future build silently treats new
        records as old ones."""
        assert _version_tuple("1.10") > _version_tuple("1.9")
        assert _version_tuple("2.0") > _version_tuple("1.99")

    def test_an_unparseable_version_is_treated_as_the_oldest(self) -> None:
        """The safe direction: it emits the fewest fields, so a record with a
        corrupt version string fails its hash check rather than being
        rewritten into something that passes."""
        assert _version_tuple("not-a-version") == (0, 0)

    @pytest.mark.parametrize("field", sorted(FIELDS_SINCE))
    def test_every_versioned_field_is_present_in_the_current_format(self, field: str) -> None:
        """FIELDS_SINCE must not name a field the record no longer has."""
        content = EvidenceRecord(evidence_version=EVIDENCE_VERSION).content()
        assert field in content
