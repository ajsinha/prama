"""A window of a valid chain is valid.

QA round 2, `Q-57`. `verify()` seeded `previous_hash` with `GENESIS` and then
required the first record to name it. Only sequence 0 can, so every export that
did not begin at the start of the ledger reported itself as broken evidence.

`Archivist.bundle` exists to export a range — its manifest carries
`from_sequence` and `to_sequence`, fields with no meaning otherwise — so this
was not a corner case. It was the feature.

A verifier that cries wolf on good evidence is worse than none: it teaches an
operator to dismiss the alarm, and the one that matters is indistinguishable
from the ones that did not.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.evidence.ledger import GENESIS, Ledger, verify
from prama.evidence.record import EvidenceRecord


@pytest.fixture
def chain() -> list[dict]:
    ledger = Ledger()
    for i in range(6):
        ledger.append(
            EvidenceRecord(
                plan_id=f"plan-{i}", control_id=f"control-{i}", dataset="trades", verdict="pass"
            )
        )
    return [record.to_dict() for record in ledger]


def test_the_whole_chain_verifies(chain: list[dict]) -> None:
    assert verify(chain).breaches == ()


def test_a_window_of_it_also_verifies(chain: list[dict]) -> None:
    """The defect, stated as the thing that must be true."""
    result = verify(chain[2:5])
    assert result.breaches == (), [b.detail for b in result.breaches]


def test_a_broken_link_inside_a_window_is_still_caught(chain: list[dict]) -> None:
    """The counterfactual, and the one that matters.

    The fix stops comparing the *first* record against a predecessor it cannot
    see. If it had stopped comparing records against each other at all, every
    test above would pass while the chain guarantee was gone — which would be a
    far worse defect than the one being fixed.
    """
    window = [dict(record) for record in chain[2:5]]
    window[2]["previous_hash"] = "ff" * 32
    breaches = verify(window).breaches
    assert any(b.kind == "link" for b in breaches), [b.detail for b in breaches]


def test_tampered_content_inside_a_window_is_still_caught(chain: list[dict]) -> None:
    window = [dict(record) for record in chain[2:5]]
    window[1]["content_hash"] = "00" * 32
    assert verify(window).breaches != ()


def test_a_chain_claiming_to_start_at_zero_must_start_from_genesis(chain: list[dict]) -> None:
    """The genesis guard is untouched.

    A record that says it is sequence 0 is claiming to be the beginning, and
    the beginning has a known predecessor. That check was always correct — it
    is the one I mistook for the whole of this finding and closed the finding
    on, which is recorded in qa/findings.md as the reason to reproduce a
    symptom before diagnosing it.
    """
    first = dict(chain[0])
    assert first["previous_hash"] == GENESIS
    first["previous_hash"] = "ab" * 32
    breaches = verify([first, *chain[1:]]).breaches
    assert any(b.kind == "genesis" for b in breaches), [b.detail for b in breaches]
