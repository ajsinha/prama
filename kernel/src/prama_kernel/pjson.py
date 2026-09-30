"""One JSON API for the whole platform.

``orjson`` where it is installed, the standard library where it is not — chosen
at import time, never at call time, so the decision does not cost anything per
call and never varies within a process.

Three deliberate encoding choices, each of which has bitten this class of system
before:

* **UTC-normalised datetimes**, serialised with a trailing ``Z``. A naive
  datetime is rejected rather than silently interpreted as local time.
* **Non-finite floats become ``null``.** ``NaN`` and ``Infinity`` are not JSON,
  and emitting them produces documents that some parsers accept and others
  reject — the worst possible outcome for an evidence record.
* **Sorted keys on canonical encoding.** Evidence records are hashed; a hash
  that depends on dict insertion order is not a hash of the content.
* **One spelling of every float, whichever backend is installed.** The standard
  library writes ``1e-05`` and ``1e-07`` where orjson writes ``0.00001`` and
  ``1e-7``. Compact output (what is hashed and signed) therefore goes through
  an encoder that spells floats as orjson does, so a record hashed on a machine
  without orjson has the hash it has everywhere else, and an agent's signed
  message verifies on a server built differently (`tests/core/test_pjson_backends.py`).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import datetime as _dt
import json as _stdjson
import math
from decimal import Decimal
from typing import Any, Final

try:  # pragma: no cover - exercised by whichever backend is installed
    import orjson as _orjson

    _have_orjson = True
except ImportError:  # pragma: no cover
    _orjson = None  # type: ignore[assignment]
    _have_orjson = False

#: Which backend was chosen, decided once at import time so the choice costs
#: nothing per call and cannot vary within a process.
HAVE_ORJSON: Final[bool] = _have_orjson

BACKEND: Final[str] = "orjson" if HAVE_ORJSON else "stdlib"


def _default(obj: Any) -> Any:
    """Coerce the types Prama actually serialises; refuse everything else."""
    if isinstance(obj, _dt.datetime):
        if obj.tzinfo is None:
            raise TypeError("refusing to serialise a naive datetime; attach UTC")
        return obj.astimezone(_dt.UTC).isoformat().replace("+00:00", "Z")
    if isinstance(obj, (_dt.date, _dt.time)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return str(obj)  # never float(): Decimal exists precisely to avoid that
    if isinstance(obj, (set, frozenset, tuple)):
        return list(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    raise TypeError(f"cannot serialise {type(obj).__name__} to JSON")


def _sanitise(value: Any) -> Any:
    """Normalise a structure before encoding.

    Runs on both backends so they cannot disagree: orjson rewrites the message
    of any exception raised inside ``default``, which would otherwise turn a
    precise "naive datetime" complaint into a generic one on machines that
    happen to have orjson installed.
    """
    if isinstance(value, _dt.datetime) and value.tzinfo is None:
        raise TypeError("refusing to serialise a naive datetime; attach UTC")
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _sanitise(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitise(v) for v in value]
    return value


def dumpb(value: Any, *, sort_keys: bool = False, indent: bool = False) -> bytes:
    """Encode to UTF-8 bytes."""
    value = _sanitise(value)
    if HAVE_ORJSON:
        # PASSTHROUGH_DATETIME routes datetimes to _default instead of orjson's
        # native encoder. Without it the two backends disagree: orjson would
        # accept a naive datetime and emit "+00:00" where the stdlib path
        # refuses it and emits "Z" — a difference that would surface as a
        # hash mismatch in the evidence ledger on some machines and not others.
        option = _orjson.OPT_PASSTHROUGH_DATETIME
        if sort_keys:
            option |= _orjson.OPT_SORT_KEYS
        if indent:
            option |= _orjson.OPT_INDENT_2
        return _orjson.dumps(value, default=_default, option=option)
    if not indent:
        return _compact(value, sort_keys=sort_keys).encode("utf-8")
    text = _stdjson.dumps(
        value,
        default=_default,
        sort_keys=sort_keys,
        indent=2,
        allow_nan=False,
        ensure_ascii=False,
    )
    return text.encode("utf-8")


def float_text(value: float) -> str:
    """A finite float as orjson writes it.

    Python's ``repr`` differs in two places only: an exponent of -5 is written
    out as a decimal (``0.00001``, not ``1e-05``), and exponents are not
    zero-padded (``1e-7``, not ``1e-07``). The SDK signs with the same rule
    (``prama_sdk.signing``), because it cannot import this module.
    """
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


def _compact(value: Any, *, sort_keys: bool) -> str:
    """Compact JSON, spelled exactly as orjson spells it (standard library only)."""
    out: list[str] = []

    def encode(item: Any) -> None:
        if item is None:
            out.append("null")
        elif item is True:
            out.append("true")
        elif item is False:
            out.append("false")
        elif isinstance(item, int):
            out.append(str(item))
        elif isinstance(item, float):
            out.append(float_text(item) if math.isfinite(item) else "null")
        elif isinstance(item, str):
            out.append(_stdjson.dumps(item, ensure_ascii=False))
        elif isinstance(item, dict):
            out.append("{")
            keys = sorted(item) if sort_keys else list(item)
            for index, key in enumerate(keys):
                if not isinstance(key, str):
                    raise TypeError(f"a JSON key must be a string, not {type(key).__name__}")
                if index:
                    out.append(",")
                out.append(_stdjson.dumps(key, ensure_ascii=False))
                out.append(":")
                encode(item[key])
            out.append("}")
        elif isinstance(item, (list, tuple)):
            out.append("[")
            for index, element in enumerate(item):
                if index:
                    out.append(",")
                encode(element)
            out.append("]")
        else:
            encode(_default(item))

    encode(value)
    return "".join(out)


def dumps(value: Any, *, sort_keys: bool = False, indent: bool = False) -> str:
    return dumpb(value, sort_keys=sort_keys, indent=indent).decode("utf-8")


def canonical(value: Any) -> bytes:
    """Deterministic encoding for hashing.

    Sorted keys, no insignificant whitespace, UTF-8. Two structures that are
    equal produce identical bytes; that is the whole contract, and the evidence
    ledger's hash chain depends on it.
    """
    return dumpb(value, sort_keys=True, indent=False)


def loads(data: str | bytes) -> Any:
    if HAVE_ORJSON:
        return _orjson.loads(data)
    if isinstance(data, bytes):
        data = data.decode("utf-8")
    return _stdjson.loads(data)
