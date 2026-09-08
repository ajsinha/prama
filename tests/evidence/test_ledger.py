"""The chain, and the claim that anybody can check it.

The most important test in this file reimplements verification from the
docstring, in the standard library alone, and requires the two implementations
to agree. If they ever disagree, either the description is wrong — in which case
an auditor following it would reach the wrong conclusion — or the code is, and
either way the claim "verifiable without Prama" has stopped being true.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import hashlib
import itertools
import json
from typing import Any

import pytest

from prama.evidence.ledger import (
    GENESIS,
    Ledger,
    merkle_root,
    sign,
    verify,
    verify_signature,
)
from prama.evidence.record import EvidenceRecord, SnapshotRef


def a_record(n: int = 0, **changes: Any) -> EvidenceRecord:
    base = {
        "plan_id": f"ir:sha256:{n:064x}",
        "control_id": "ctl-1",
        "dataset": "positions_eod",
        "binding": "pg://RISK.POSITIONS",
        "engine": "postgresql",
        "snapshot": SnapshotRef(kind="lsn", identifier=f"0/{1000 + n}", exact=True),
        "verdict": "pass",
        "metrics": {"scanned_rows": 50000.0, "violating_rows": float(n)},
        "started_at": "2026-04-02T06:31:00Z",
        "finished_at": "2026-04-02T06:31:02Z",
        "duration_ms": 2100,
        "tenant_id": "t1",
    }
    base.update(changes)
    return EvidenceRecord(**base)  # type: ignore[arg-type]


def a_chain(length: int = 5) -> Ledger:
    ledger = Ledger()
    for n in range(length):
        ledger.append(a_record(n))
    return ledger


# ---------------------------------------------------------------------------
# The independent implementation. Nothing imported from prama.
# ---------------------------------------------------------------------------

HASH_FIELDS_EXCLUDED = {"previous_hash", "content_hash", "record_hash"}


def verify_independently(lines: list[str]) -> list[str]:
    """Verification as described in the ledger's docstring, in stdlib alone.

    Deliberately written from the words rather than from the code, and kept
    short: an auditor who cannot reimplement the check in an afternoon will not
    perform it, and a check nobody performs is a claim rather than a control.
    """
    problems: list[str] = []
    previous = GENESIS
    expected = None
    for line in lines:
        record = json.loads(line)
        sequence = record["sequence"]
        if expected is None:
            expected = sequence
        elif sequence != expected:
            problems.append(f"sequence {sequence}: expected {expected}")
            expected = sequence
        expected += 1

        content = {k: v for k, v in record.items() if k not in HASH_FIELDS_EXCLUDED}
        digest = hashlib.sha256(
            json.dumps(content, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if digest != record["content_hash"]:
            problems.append(f"sequence {sequence}: content hash does not match")
        link = hashlib.sha256(
            (record["previous_hash"] + record["content_hash"]).encode("ascii")
        ).hexdigest()
        if link != record["record_hash"]:
            problems.append(f"sequence {sequence}: record hash does not match")
        if record["previous_hash"] != previous:
            problems.append(f"sequence {sequence}: does not follow the previous record")
        previous = record["record_hash"]
    return problems


class TestVerifiableWithoutPrama:
    """The claim the whole audit proposition rests on."""

    def test_an_independent_reader_reaches_the_same_conclusion(self) -> None:
        exported = a_chain(8).export().splitlines()
        assert verify_independently(exported) == []

    def test_and_the_same_conclusion_when_a_record_is_altered(self) -> None:
        exported = a_chain(8).export().splitlines()
        tampered = json.loads(exported[3])
        tampered["verdict"] = "pass"
        tampered["metrics"]["violating_rows"] = 0
        exported[3] = json.dumps(tampered, sort_keys=True, separators=(",", ":"))

        ours = verify(json.loads(line) for line in exported)
        theirs = verify_independently(exported)
        assert not ours.is_intact
        assert theirs
        # Both name the same record. An auditor and the platform must agree not
        # only that something is wrong but about where.
        assert all(b.sequence == 3 for b in ours.breaches if b.kind == "content")
        assert any("sequence 3" in problem for problem in theirs)

    def test_the_export_format_survives_truncation(self) -> None:
        # Newline-delimited, so a file cut short by the process that died
        # writing it still yields every complete record.
        exported = a_chain(8).export()
        truncated = exported[: exported.rindex("\n") + 40].splitlines()
        assert len(truncated) == 8
        assert verify_independently(truncated[:-1]) == []


class TestTheChain:
    def test_a_fresh_chain_starts_from_genesis(self) -> None:
        ledger = Ledger()
        assert ledger.head == GENESIS
        assert ledger.append(a_record()).previous_hash == GENESIS

    def test_each_record_links_to_the_one_before(self) -> None:
        ledger = a_chain(4)
        records = ledger.records()
        for earlier, later in itertools.pairwise(records):
            assert later.previous_hash == earlier.record_hash

    def test_sequences_are_assigned_by_the_ledger(self) -> None:
        # A caller that could choose its own sequence and parent could write a
        # record that looked linked and was not.
        ledger = Ledger()
        written = ledger.append(a_record(0, sequence=99, previous_hash="deadbeef"))
        assert written.sequence == 0
        assert written.previous_hash == GENESIS

    def test_an_intact_chain_verifies(self) -> None:
        result = a_chain(20).verify()
        assert result.is_intact
        assert result.records == 20
        assert "20 record(s) verified" in result.render()

    def test_altering_a_record_is_detected(self) -> None:
        payloads = [r.to_dict() for r in a_chain(5)]
        payloads[2]["verdict"] = "fail"
        result = verify(payloads)
        assert not result.is_intact
        assert any(b.kind == "content" and b.sequence == 2 for b in result.breaches)
        assert "has been altered" in result.render()

    def test_a_missing_record_is_detected_as_a_gap(self) -> None:
        # A hash chain alone cannot reveal a deletion from the end, and a
        # deletion from the middle breaks the link — but naming it as a gap
        # tells the reader a record is missing rather than merely corrupt.
        payloads = [r.to_dict() for r in a_chain(5)]
        del payloads[2]
        result = verify(payloads)
        assert any(b.kind == "gap" for b in result.breaches)
        assert "missing" in result.render()

    def test_reordering_is_detected(self) -> None:
        payloads = [r.to_dict() for r in a_chain(5)]
        payloads[1], payloads[3] = payloads[3], payloads[1]
        assert not verify(payloads).is_intact

    def test_a_record_round_trips_through_its_stored_form(self) -> None:
        original = a_chain(1).records()[0]
        restored = EvidenceRecord.from_dict(json.loads(original.to_json()))
        assert restored.content_hash == original.content_hash
        assert restored.record_hash == original.record_hash


class TestSize:
    def test_a_record_is_well_under_two_kilobytes(self) -> None:
        # Evidence accumulates at the rate controls run and is kept for years.
        # A record carrying its failing rows inline would be a hundred times
        # larger, and retention cost would quietly decide that evidence is
        # unaffordable.
        sizes = sorted(r.size_bytes for r in a_chain(50))
        assert sizes[len(sizes) // 2] < 2048

    def test_samples_are_referenced_not_carried(self) -> None:
        record = a_record(0, samples_digest="sha256:abc", sample_count=50)
        assert "sha256:abc" in record.to_json()
        assert record.size_bytes < 2048


class TestNumbersHashStably:
    def test_an_integer_metric_hashes_the_same_however_the_driver_returned_it(
        self,
    ) -> None:
        # A count returned as 8.0 by one driver and 8 by another must not break
        # an evidence chain: that is a library upgrade, not a change in the
        # data.
        as_float = a_record(0, metrics={"scanned_rows": 8.0})
        as_int = a_record(0, metrics={"scanned_rows": 8})
        assert as_float.content_hash == as_int.content_hash

    def test_a_fractional_metric_keeps_its_value(self) -> None:
        record = a_record(0, metrics={"rate": 0.125})
        assert json.loads(record.to_json())["metrics"]["rate"] == 0.125

    def test_parameter_order_does_not_change_the_hash(self) -> None:
        first = a_record(0, parameters={"a": "1", "b": "2"})
        second = a_record(0, parameters={"b": "2", "a": "1"})
        assert first.content_hash == second.content_hash


class TestMerkleRoots:
    def test_a_root_stands_for_the_whole_set(self) -> None:
        assert a_chain(9).merkle_root() != GENESIS

    def test_changing_any_record_changes_the_root(self) -> None:
        before = a_chain(9).merkle_root()
        ledger = a_chain(9)
        ledger.append(a_record(99))
        assert ledger.merkle_root() != before

    def test_an_odd_node_is_promoted_not_duplicated(self) -> None:
        # Duplicating it is the well-known construction that lets two different
        # sets produce the same root. A root that can be forged is not worth
        # publishing.
        three = merkle_root(["a" * 64, "b" * 64, "c" * 64])
        four = merkle_root(["a" * 64, "b" * 64, "c" * 64, "c" * 64])
        assert three != four

    def test_an_empty_set_has_no_root(self) -> None:
        assert merkle_root([]) == GENESIS


class TestSigning:
    def test_a_signature_proves_the_head_was_seen_by_a_key_holder(self) -> None:
        head = a_chain(5).head
        signature = sign(head, b"secret")
        assert verify_signature(head, b"secret", signature)

    def test_a_different_key_does_not_verify(self) -> None:
        head = a_chain(5).head
        assert not verify_signature(head, b"other", sign(head, b"secret"))

    def test_a_changed_head_does_not_verify(self) -> None:
        signature = sign(a_chain(5).head, b"secret")
        assert not verify_signature(a_chain(6).head, b"secret", signature)


@pytest.mark.parametrize("length", [0, 1, 2, 3, 100])
def test_a_chain_of_any_length_verifies(length: int) -> None:
    assert a_chain(length).verify().is_intact
