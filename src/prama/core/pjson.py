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

    HAVE_ORJSON: Final[bool] = True
except ImportError:  # pragma: no cover
    _orjson = None  # type: ignore[assignment]
    HAVE_ORJSON = False

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
    """Replace non-finite floats anywhere in a structure with ``None``."""
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
        option = 0
        if sort_keys:
            option |= _orjson.OPT_SORT_KEYS
        if indent:
            option |= _orjson.OPT_INDENT_2
        return _orjson.dumps(value, default=_default, option=option)
    text = _stdjson.dumps(
        value,
        default=_default,
        sort_keys=sort_keys,
        indent=2 if indent else None,
        separators=None if indent else (",", ":"),
        allow_nan=False,
        ensure_ascii=False,
    )
    return text.encode("utf-8")


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
