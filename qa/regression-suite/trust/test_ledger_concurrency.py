"""Appending to a ledger from two threads must not mint one sequence twice.

QA round 2, `EVD-052`. `append` read `next_sequence`, read `head`, then
appended — three steps with nothing between them. Two threads interleaving
those steps both linked to the same head and claimed the same sequence.
Measured before the fix: eight threads writing four thousand records produced
**2,250 duplicate sequence numbers** and a chain that no longer verified.

The durable ledger has a unique index on `(tenant_id, sequence)` and would have
refused those writes. This implementation had nothing, and it is the one the
reference verifier and every in-process caller use.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import threading

from prama.evidence.ledger import Ledger, verify
from prama.evidence.record import EvidenceRecord

WRITERS = 8
EACH = 500


def test_concurrent_appends_mint_distinct_sequences() -> None:
    ledger = Ledger()

    def write() -> None:
        for _ in range(EACH):
            ledger.append(
                EvidenceRecord(
                    plan_id="plan", control_id="control", dataset="trades", verdict="pass"
                )
            )

    threads = [threading.Thread(target=write) for _ in range(WRITERS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    sequences = [record.sequence for record in ledger]
    assert len(sequences) == WRITERS * EACH
    assert len(set(sequences)) == len(sequences), (
        f"{len(sequences) - len(set(sequences))} duplicate sequence numbers"
    )
    assert sorted(sequences) == list(range(WRITERS * EACH))


def test_the_chain_those_writers_produced_still_verifies() -> None:
    """Distinct sequences are necessary and not sufficient.

    Two writers could take different sequences and still link to the same
    head, which leaves the numbering tidy and the chain broken. The chain is
    the actual guarantee, so it is the thing asserted.
    """
    ledger = Ledger()

    def write() -> None:
        for _ in range(EACH):
            ledger.append(
                EvidenceRecord(
                    plan_id="plan", control_id="control", dataset="trades", verdict="pass"
                )
            )

    threads = [threading.Thread(target=write) for _ in range(WRITERS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert verify(record.to_dict() for record in ledger).breaches == ()
