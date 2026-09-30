"""The SDK signs an agent's message exactly as the server checks it.

The server verifies ``HMAC(key, message.signable())``, where ``signable()`` is
the kernel's canonical JSON. The SDK may not import the kernel, so it writes
that encoding itself (`prama_sdk.signing`), and these tests hold the two
byte-equal: for real Hello and Report messages, and for the values where JSON
encoders are known to disagree — floats at every magnitude, non-finite floats,
datetimes carried as strings, nested dictionaries whose keys need sorting, and
text outside ASCII.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
from prama_kernel import pjson
from prama_kernel.agent.capability import AgentCapabilities
from prama_kernel.agent.protocol import Hello, Report
from prama_kernel.agent.signing import sign_payload
from prama_kernel.agent.spool import Gap
from prama_kernel.record import EvidenceRecord, SnapshotRef
from prama_sdk.signing import canonical_json, sign

#: The kernel's fast backend is the one whose float spelling the SDK follows.
#: Without it the kernel's own two backends disagree on exponents -5 to -9
#: (``1e-05`` against ``0.00001``), which is a property of the kernel, not of
#: the SDK, and is named in docs/sdk/fleet.md.
needs_orjson = pytest.mark.skipif(
    not pjson.HAVE_ORJSON, reason="the kernel's stdlib backend spells small exponents differently"
)


def kernel(value: Any) -> str:
    return pjson.dumps(value, sort_keys=True)


def a_hello() -> Hello:
    return Hello(
        agent_id="01M3SEZ1H8068C5BM352CKW0M7",
        version="1.2.3-ünïcødé",
        capabilities=AgentCapabilities(
            engines=("sqlite", "duckdb"),
            pushdown=("pushdown.aggregation",),
            budget=12.5,
            datasets=("trades", "Zürich-bücher"),
            delegates=("acme.x@1.0",),
        ),
        pending_findings=7,
        free_slots=3,
    )


def a_report() -> Report:
    record = EvidenceRecord(
        sequence=41,
        plan_id="ir:sha256:" + "ab" * 32,
        control_id="01CONTROL0000000000000000A",
        dataset="trades",
        binding="warehouse.trades",
        snapshot=SnapshotRef(kind="wall_clock", identifier="2026-09-30T06:00:00+00:00"),
        parameters={"threshold": "violating_rows<=0", "note": "naïve → “quoted” \n\t\\"},
        engine="sqlite",
        verdict="fail",
        metrics={
            "scanned_rows": 1_000_000.0,
            "violating_rows": 1.0,
            "rate": 1e-05,
            "tiny": 1.2345e-07,
            "huge": 1e16,
            "negative": -2.5e-06,
            "third": 1 / 3,
        },
        sample_count=1,
        started_at="2026-09-30T06:00:00.123456+00:00",
        finished_at="2026-09-30T06:00:01+00:00",
        duration_ms=877,
        triggered_by="agent:x",
        detail="日本語 and emoji 🚩 and a line\u2028separator",
    )
    return Report(
        agent_id="01M3SEZ1H8068C5BM352CKW0M7",
        records=(record,),
        gaps=(
            Gap(
                first_sequence=3,
                last_sequence=9,
                dropped_at=datetime(2026, 9, 30, 5, 0, tzinfo=UTC),
                reason="spool full: “disk”",
            ),
        ),
        residency={"zone": "eu", "samples": "mask", "nested": {"b": [1, 2.0, None], "a": True}},
    )


@needs_orjson
def test_a_hello_is_signed_as_the_kernel_signs_it() -> None:
    hello = a_hello()
    assert canonical_json(hello.to_dict()) == hello.signable()
    key = b"k" * 32
    assert sign(key, hello.to_dict()) == sign_payload(key, hello.signable())


@needs_orjson
def test_a_report_is_signed_as_the_kernel_signs_it() -> None:
    report = a_report()
    payload = report.to_dict()
    assert canonical_json(payload) == report.signable()
    # And the server's side: the message rebuilt from what arrived.
    rebuilt = Report.from_dict(pjson.loads(pjson.dumps(payload)))
    assert canonical_json(payload) == rebuilt.signable()


@needs_orjson
def test_floats_at_every_magnitude_are_spelled_as_the_kernel_spells_them() -> None:
    rng = random.Random(20260930)
    values: list[float] = [0.0, -0.0, 1.0, 0.1, 5e-324, 1.7976931348623157e308]
    for power in range(-30, 31):
        values += [10.0**power, -(10.0**power), 1.2345 * 10.0**power, 9.99 * 10.0**power]
    values += [rng.uniform(-1e6, 1e6) for _ in range(2000)]
    values += [10 ** rng.uniform(-30, 30) for _ in range(2000)]
    mismatched = [v for v in values if canonical_json(v) != kernel(v)]
    assert not mismatched, [(v, canonical_json(v), kernel(v)) for v in mismatched[:10]]


def test_structures_text_and_non_finite_values_agree() -> None:
    value = {
        "z": [1, "two", {"é": None, "a": [True, False]}],
        "A": {"nested": {"deeper": {"b": 1, "a": 2}}},
        "text": 'quotes " and \\ and / and \u0000\u001f\u007f\u2028 and 🚩',
        "nan": float("nan"),
        "inf": [float("-inf")],
        "when": "2026-09-30T06:00:00+00:00",
        "ints": [0, -1, 2**62],
    }
    assert canonical_json(value) == kernel(value)


def test_aware_datetimes_become_utc_with_z_and_naive_ones_are_refused() -> None:
    moment = datetime(2026, 9, 30, 8, 0, tzinfo=timezone(timedelta(hours=2)))
    expected = '{"at":"2026-09-30T06:00:00Z"}'
    assert canonical_json({"at": moment}) == kernel({"at": moment}) == expected
    with pytest.raises(TypeError, match="naive"):
        canonical_json({"at": datetime(2026, 9, 30)})


def test_the_equality_check_can_fail() -> None:
    """The counterfactual: a one-character difference is a different signature."""
    hello = a_hello()
    other = {**hello.to_dict(), "free_slots": 4}
    assert sign(b"k", other) != sign_payload(b"k", hello.signable())
