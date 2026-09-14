"""A bundle's manifest cannot claim a range it does not contain.

QA round 4, finding `Q-76`, found by the trust agent probing beyond the
catalogue. `Bundle.check()` validates four things — the record count, the
payload digest, the hash chain, and the chain head — and does **not** compare
`manifest.from_sequence` or `manifest.to_sequence` against the sequences of the
records actually present.

So every integrity property a bundle checks is about the records being
*unaltered*, and none is about them being **the records the manifest says they
are**. A payload that is internally perfect and mislabelled verifies clean.

**Why mislabelling is the attack worth caring about.** A bundle is the artefact
handed to an auditor, and the range fields are how they know *which period they
are looking at*. Forging a record means defeating the hash chain and the Merkle
root. Editing two integers in a manifest requires nothing at all — and produces
a bundle that passes every check while answering a different question than the
one asked. "Show me March" and "show me a clean chain" are not the same request.

**What a careless version of this test would do.** Tamper with a *record* and
watch `check()` refuse. It already does that, for four different reasons, and it
would tell you nothing about the range. The tamper here has to leave the payload
byte-identical and change only the manifest.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses

import pytest

from prama.evidence.ledger import Ledger
from prama.evidence.record import EvidenceRecord
from prama.evidence.retention import Archivist


@pytest.fixture
def bundle():
    """A genuine export of an interior window, so the boundaries are not 0..n."""
    ledger = Ledger()
    for index in range(40):
        ledger.append(
            EvidenceRecord(
                plan_id=f"plan-{index}",
                control_id=f"control-{index}",
                dataset="trades",
                verdict="pass",
            )
        )
    records = list(ledger)[10:30]
    return Archivist().bundle(records, tenant_id="acme")


def test_a_genuine_bundle_verifies(bundle) -> None:
    """The control that makes the rest of this file mean something."""
    ok, message = bundle.check()
    assert ok, message


def test_a_manifest_claiming_a_wider_range_than_it_holds_is_refused(bundle) -> None:
    """Two integers edited; not a byte of the payload touched."""
    forged = dataclasses.replace(
        bundle,
        manifest=dataclasses.replace(bundle.manifest, from_sequence=0, to_sequence=39),
    )

    ok, message = forged.check()
    assert not ok, (
        "a bundle holding records 10-29 verified while its manifest claimed 0-39. "
        "Every record in it is genuine and the chain is intact; it is simply not "
        f"the period the manifest names. check() said: {message}"
    )
    assert "sequence" in message.lower() or "range" in message.lower(), (
        f"the refusal does not say the range is wrong: {message!r}"
    )


def test_a_manifest_claiming_a_narrower_range_is_also_refused(bundle) -> None:
    """The other direction, which is the one that hides records.

    A manifest naming a *smaller* window than the payload holds is how a bundle
    is made to look like it answers a narrow question while carrying more than
    was asked for — and an auditor reading the manifest would never know to
    count.
    """
    forged = dataclasses.replace(
        bundle,
        manifest=dataclasses.replace(bundle.manifest, from_sequence=15, to_sequence=20),
    )
    ok, _ = forged.check()
    assert not ok, "a manifest naming a narrower window than the payload holds verified"


def test_the_existing_refusals_still_fire(bundle) -> None:
    """The four checks that already worked, so the new one did not displace them.

    Adding a comparison before the others is exactly the change that makes an
    earlier check unreachable, and a bundle that refuses for the wrong reason is
    harder to diagnose than one that refuses for the right one.
    """
    truncated = dataclasses.replace(bundle, payload="\n".join(bundle.payload.splitlines()[:-1]))
    ok, message = truncated.check()
    assert not ok and "incomplete" in message, (
        f"a truncated payload no longer refuses for its own reason: {message!r}"
    )
