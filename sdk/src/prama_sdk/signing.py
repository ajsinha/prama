"""Signing an agent's message the way the server checks it, with the standard library.

The server verifies ``HMAC-SHA256(key, message.signable())``, where
``signable()`` is the kernel's canonical JSON of the message
(``prama_kernel.pjson.dumps(payload, sort_keys=True)``). The SDK does not import
the kernel — it depends on httpx and PyYAML only — so this module reproduces
that encoding, byte for byte, and ``tests/sdk/test_fleet_signing.py`` proves it
against the kernel for Hello and Report payloads.

The canonical form:

* keys sorted, no whitespace, UTF-8 (not ASCII-escaped);
* ``NaN`` and infinities become ``null``;
* an aware datetime becomes UTC ISO-8601 with ``Z``; a naive one is refused;
* floats as the kernel's fast backend (orjson) writes them, which differs from
  Python's ``repr`` in exactly two places: an exponent of -5 is written out as a
  decimal (``0.00001``, not ``1e-05``), and a negative exponent is not
  zero-padded (``1e-7``, not ``1e-07``).

The payload to sign is the message's ``to_dict()`` exactly as the kernel builds
it: the server rebuilds the message from what arrived and signs *that*, so a
field left out here and defaulted there would not verify.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import hmac
import json
import math
from decimal import Decimal
from typing import Any


def _float(value: float) -> str:
    if not math.isfinite(value):
        return "null"
    text = repr(value)
    if "e" not in text:
        return text
    mantissa, _, exponent = text.partition("e")
    power = int(exponent)
    if power == -5:
        sign = "-" if mantissa.startswith("-") else ""
        digits = mantissa.lstrip("-").replace(".", "")
        return f"{sign}0.0000{digits}"
    return f"{mantissa}e{'-' if power < 0 else '+'}{abs(power)}"


def _encode(value: Any, out: list[str]) -> None:
    if value is None:
        out.append("null")
    elif value is True:
        out.append("true")
    elif value is False:
        out.append("false")
    elif isinstance(value, int):
        out.append(str(value))
    elif isinstance(value, float):
        out.append(_float(value))
    elif isinstance(value, str):
        out.append(json.dumps(value, ensure_ascii=False))
    elif isinstance(value, dict):
        out.append("{")
        for index, key in enumerate(sorted(value)):
            if not isinstance(key, str):
                raise TypeError(f"a canonical JSON key must be a string, not {type(key).__name__}")
            if index:
                out.append(",")
            out.append(json.dumps(key, ensure_ascii=False))
            out.append(":")
            _encode(value[key], out)
        out.append("}")
    elif isinstance(value, (list, tuple, set, frozenset)):
        out.append("[")
        for index, item in enumerate(value):
            if index:
                out.append(",")
            _encode(item, out)
        out.append("]")
    elif isinstance(value, _dt.datetime):
        if value.tzinfo is None:
            raise TypeError("refusing to serialise a naive datetime; attach UTC")
        out.append(json.dumps(value.astimezone(_dt.UTC).isoformat().replace("+00:00", "Z")))
    elif isinstance(value, (_dt.date, _dt.time)):
        out.append(json.dumps(value.isoformat()))
    elif isinstance(value, Decimal):
        out.append(json.dumps(str(value)))
    elif isinstance(value, bytes):
        out.append(json.dumps(value.decode("utf-8", errors="replace"), ensure_ascii=False))
    else:
        raise TypeError(f"cannot serialise {type(value).__name__} to JSON")


def canonical_json(value: Any) -> str:
    """*value* as the kernel's ``dumps(value, sort_keys=True)`` would write it."""
    out: list[str] = []
    _encode(value, out)
    return "".join(out)


def sign(key: bytes, payload: dict[str, Any]) -> str:
    """The hex HMAC-SHA256 of *payload*'s canonical JSON under *key*."""
    return hmac.new(key, canonical_json(payload).encode("utf-8"), hashlib.sha256).hexdigest()
