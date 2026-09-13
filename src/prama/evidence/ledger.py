"""The chain, and how to check it without us.

The ledger is append-only and hash-linked: each record carries the previous
record's hash, so altering any record breaks every hash after it. That is the
easy half.

The half that matters is that **verification does not require Prama**. An audit
trail only checkable by the tool that produced it is the tool's own account of
itself, which is exactly what an auditor is there not to accept. So the
algorithm is written out here in full, in words, and it is short:

1. Read the records in sequence order. Sequence numbers must be contiguous from
   the first one present; a gap is a missing record and no hash can reveal it.
2. For each record, take every field except ``previous_hash``, ``content_hash``
   and ``record_hash``. Serialise them as JSON with keys sorted at every level,
   no insignificant whitespace, UTF-8. SHA-256 that. It must equal the stored
   ``content_hash``.
3. Concatenate the stored ``previous_hash`` and the ``content_hash`` as ASCII
   hex and SHA-256 the result. It must equal ``record_hash``.
4. Each record's ``previous_hash`` must equal the previous record's
   ``record_hash``. The first record's must be sixty-four zeros.

That is the whole thing. The test suite reimplements it in stdlib and requires
the two implementations to agree, so the description above cannot drift from
what the code does.

A **Merkle root** over a period lets one short string stand for a whole day's
evidence — publishable somewhere Prama cannot reach, which is what turns
"our records are internally consistent" into "our records are what they were on
the third".

**Signing** is HMAC over the chain head. That proves a record came from a holder
of the key; it does not prove anything to a third party who does not have it,
and this file says so rather than letting the word "signed" imply more than it
delivers.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import hashlib
import hmac
import threading
from collections.abc import Iterable, Iterator
from typing import Any

from prama.evidence.record import GENESIS, EvidenceRecord


@dataclasses.dataclass(frozen=True, slots=True)
class Breach:
    """One thing wrong with a chain, named precisely enough to act on."""

    #: ``content``, ``link``, ``gap``, ``order`` or ``genesis``.
    kind: str
    sequence: int
    detail: str

    def render(self) -> str:
        return f"record {self.sequence}: {self.detail}"


@dataclasses.dataclass(frozen=True, slots=True)
class Verification:
    """What checking a chain found."""

    records: int = 0
    breaches: tuple[Breach, ...] = ()
    head: str = GENESIS
    merkle_root: str = ""
    #: Records whose content has been erased. Counted and reported, because an
    #: auditor must be told that three records were erased rather than have it
    #: be invisible — and because what verification proves about them is
    #: weaker: their place in the chain, not their contents, which no longer
    #: exist to be re-derived.
    erased: int = 0

    @property
    def is_intact(self) -> bool:
        return not self.breaches

    def render(self) -> str:
        erased = (
            f" {self.erased} record(s) have been erased under a right-to-erasure "
            f"request; their place in the chain is verified, their contents are gone."
            if self.erased
            else ""
        )
        if self.is_intact:
            return (
                f"{self.records} record(s) verified. Chain head {self.head[:16]}…, "
                f"Merkle root {self.merkle_root[:16]}…{erased}"
            )
        lines = [f"{self.records} record(s) checked; {len(self.breaches)} problem(s):"]
        lines.extend(f"  {b.render()}" for b in self.breaches)
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "records": self.records,
            "intact": self.is_intact,
            "head": self.head,
            "merkle_root": self.merkle_root,
            "erased": self.erased,
            "breaches": [
                {"kind": b.kind, "sequence": b.sequence, "detail": b.detail} for b in self.breaches
            ],
        }


class Ledger:
    """An append-only chain of evidence records.

    In memory here, with the storage seam deliberately narrow: append and
    iterate. Where the records live — a table, an object store with a WORM
    policy, both — is a deployment decision, and a ledger that knew about it
    would have to be reimplemented for each.
    """

    def __init__(self, records: Iterable[EvidenceRecord] = ()) -> None:
        self._records: list[EvidenceRecord] = list(records)
        #: Guards the read-modify-write in `append`. Reading `next_sequence`
        #: and `head`, then appending, is three steps, and two threads
        #: interleaving them both linked to the same head and claimed the same
        #: sequence. Measured: eight threads writing four thousand records
        #: produced two thousand two hundred and fifty duplicate sequence
        #: numbers, and a chain that no longer verified (QA finding EVD-052).
        #:
        #: The durable ledger is protected by a unique index on
        #: `(tenant_id, sequence)`, so the database would have refused those
        #: writes. This one had nothing, and it is the implementation the
        #: reference verifier and every in-process caller use.
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._records)

    def __iter__(self) -> Iterator[EvidenceRecord]:
        return iter(self._records)

    @property
    def head(self) -> str:
        """The hash everything so far reduces to."""
        return self._records[-1].record_hash if self._records else GENESIS

    @property
    def next_sequence(self) -> int:
        return self._records[-1].sequence + 1 if self._records else 0

    def append(self, record: EvidenceRecord) -> EvidenceRecord:
        """Add a record, linked to the current head.

        The sequence and the previous hash are set here rather than by the
        caller. A caller that could choose them could write a record that
        looked linked and was not, and the whole guarantee would rest on every
        caller getting it right.
        """
        with self._lock:
            linked = dataclasses.replace(
                record, sequence=self.next_sequence, previous_hash=self.head
            )
            self._records.append(linked)
            return linked

    def extend(self, records: Iterable[EvidenceRecord]) -> list[EvidenceRecord]:
        return [self.append(r) for r in records]

    def records(self) -> list[EvidenceRecord]:
        return list(self._records)

    def since(self, sequence: int) -> list[EvidenceRecord]:
        return [r for r in self._records if r.sequence >= sequence]

    def find(self, plan_id: str) -> list[EvidenceRecord]:
        return [r for r in self._records if r.plan_id == plan_id]

    # -- verification ------------------------------------------------------

    def verify(self) -> Verification:
        return verify(r.to_dict() for r in self._records)

    def merkle_root(self) -> str:
        return merkle_root([r.record_hash for r in self._records])

    def export(self) -> str:
        """The chain as newline-delimited JSON, one record per line.

        Chosen over a JSON array because it appends without rewriting, streams
        without a parser holding the whole file, and survives truncation with
        every complete line still readable — which is what an archive format
        has to do when the thing that failed is the process writing it.
        """
        return "\n".join(r.to_json() for r in self._records)


def verify(payloads: Iterable[dict[str, Any]]) -> Verification:
    """Check a chain from its stored form. The algorithm in the docstring above."""
    breaches: list[Breach] = []
    #: The hash the next record must name. `None` until the first record is
    #: seen, because a window that legitimately starts part-way along the chain
    #: has no way to know what preceded it — and demanding GENESIS there was
    #: how a valid export came to report itself as broken (QA finding Q-57).
    previous_hash: str | None = None
    expected_sequence: int | None = None
    count = 0
    erased = 0
    hashes: list[str] = []

    for payload in payloads:
        count += 1
        record = EvidenceRecord.from_dict(payload)
        sequence = record.sequence
        if expected_sequence is None:
            expected_sequence = sequence
            if str(payload.get("previous_hash", "")) != GENESIS and sequence == 0:
                breaches.append(
                    Breach("genesis", sequence, "the first record does not start the chain")
                )
        elif sequence != expected_sequence:
            breaches.append(
                Breach(
                    "gap",
                    sequence,
                    f"expected sequence {expected_sequence} and found {sequence}; "
                    f"{sequence - expected_sequence} record(s) are missing"
                    if sequence > expected_sequence
                    else "records are out of order",
                )
            )
            expected_sequence = sequence
        expected_sequence += 1

        if record.is_erased:
            # Its content cannot be re-derived — that is what erasure means —
            # so what is checked is that it still links. The tombstone carries
            # the hash the content had, which is what keeps the chain whole.
            erased += 1
        stored_content = str(payload.get("content_hash", ""))
        if record.content_hash != stored_content:
            breaches.append(
                Breach(
                    "content",
                    sequence,
                    "the content does not match its hash; this record has been altered",
                )
            )
        stored_record_hash = str(payload.get("record_hash", ""))
        if record.record_hash != stored_record_hash:
            breaches.append(
                Breach("link", sequence, "the record hash does not match its own contents")
            )
        if previous_hash is None:
            # The first record of whatever was handed in. Its own
            # `previous_hash` links it to a record that may simply not be in
            # this window — `Archivist.bundle` exists to export a range, and
            # its manifest carries `from_sequence` and `to_sequence` precisely
            # because a bundle is not expected to start at zero.
            #
            # Only sequence 0 can be checked against GENESIS, and the guard
            # above already does that. Here there is nothing to compare, and
            # comparing anyway reported every windowed export as broken
            # evidence. A verifier that cries wolf on valid evidence gets
            # switched off, and an ignored verifier is worse than none.
            pass
        elif record.previous_hash != previous_hash:
            breaches.append(
                Breach(
                    "link",
                    sequence,
                    "this record does not follow the one before it; the chain is broken here",
                )
            )
        previous_hash = record.record_hash
        hashes.append(record.record_hash)

    return Verification(
        records=count,
        breaches=tuple(breaches),
        head=previous_hash if previous_hash is not None else GENESIS,
        merkle_root=merkle_root(hashes),
        erased=erased,
    )


def merkle_root(hashes: list[str]) -> str:
    """A single hash standing for the whole set.

    Pairs are hashed upward until one remains. An odd node at any level is
    promoted rather than duplicated: duplicating it is the well-known
    construction that lets two different sets produce the same root, and a root
    that can be forged is not worth publishing.
    """
    if not hashes:
        return GENESIS
    level = list(hashes)
    while len(level) > 1:
        nxt: list[str] = []
        for index in range(0, len(level) - 1, 2):
            nxt.append(
                hashlib.sha256((level[index] + level[index + 1]).encode("ascii")).hexdigest()
            )
        if len(level) % 2:
            nxt.append(level[-1])
        level = nxt
    return level[0]


def sign(head: str, key: bytes) -> str:
    """An HMAC over a chain head.

    Says: this head was seen by a holder of the key. It does not say anything
    to somebody who does not hold the key, which an asymmetric signature would
    — and calling this "signed" without that sentence would let the word imply
    more than it delivers.
    """
    return hmac.new(key, head.encode("ascii"), hashlib.sha256).hexdigest()


def verify_signature(head: str, key: bytes, signature: str) -> bool:
    return hmac.compare_digest(sign(head, key), signature)
