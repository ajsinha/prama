"""The two JSON backends write the same bytes, so hashes and signatures agree everywhere.

Evidence is hashed and agent messages are signed over the kernel's compact
JSON. A machine with orjson and one without must produce identical bytes, or a
record's hash differs by where it was computed and an agent's correctly signed
report is refused by a server built differently. The standard library spells
some floats differently (``1e-05`` against ``0.00001``), which is what this
guards. Found building the agent fleet over HTTP.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
import json
import random
import struct
from decimal import Decimal

import pytest
from prama_kernel import pjson

orjson = pytest.importorskip("orjson", reason="orjson is not installed; nothing to compare")


def _fast(value: object, sort_keys: bool) -> bytes:
    option = orjson.OPT_PASSTHROUGH_DATETIME | (orjson.OPT_SORT_KEYS if sort_keys else 0)
    return orjson.dumps(pjson._sanitise(value), default=pjson._default, option=option)


def _floats() -> list[float]:
    rng = random.Random(20260930)
    edge = [0.0, -0.0, 1.0, -1.5, 1e-5, 1.5e-5, -2.25e-5, 1e-7, 1e-9, 1e-16, 1e16, 1e21]
    edge += [1e22, 123456789.125, 0.1 + 0.2, 5e-324, 1.7976931348623157e308, 2.0**53, -(2.0**60)]
    drawn = [struct.unpack("<d", struct.pack("<Q", rng.getrandbits(64)))[0] for _ in range(4000)]
    scaled = [rng.uniform(-1, 1) * 10.0 ** rng.randint(-12, 22) for _ in range(4000)]
    return [f for f in edge + drawn + scaled if f == f and abs(f) != float("inf")]


@pytest.mark.parametrize("sort_keys", [True, False])
def test_every_float_is_spelled_as_orjson_spells_it(sort_keys: bool) -> None:
    for value in _floats():
        assert pjson._compact([value], sort_keys=sort_keys).encode() == _fast([value], sort_keys)


def test_whole_documents_match_byte_for_byte() -> None:
    document = {
        "z": [1, 2.5e-5, "ünïcödé ✓", None, True, {"b": 1e-7, "a": -0.0}],
        "a": {"when": dt.datetime(2026, 9, 30, 6, 30, tzinfo=dt.UTC), "amount": Decimal("1.10")},
        "nested": [[{"k": 1e21}], [], {}],
        "nan": float("nan"),
    }
    assert pjson._compact(pjson._sanitise(document), sort_keys=True).encode() == _fast(
        document, True
    )
    assert json.loads(pjson._compact(pjson._sanitise(document), sort_keys=True))["nan"] is None


def test_the_standard_librarys_own_spelling_would_differ() -> None:
    """The counterfactual: without the explicit encoder the backends disagree."""
    plain = json.dumps([1e-05], separators=(",", ":")).encode()
    assert plain != _fast([1e-05], True)
