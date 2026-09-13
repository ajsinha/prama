"""Type coercion for configuration values.

Configuration arrives from YAML (already typed), from environment variables and
from the command line (always strings). A reader asks for the type it needs and
gets it, or gets an error naming the key — never a silent ``"false"`` that is
truthy, which is the classic configuration defect.

Two domain-specific types are first class because Prama's settings are full of
them: **durations** (``30s``, ``5m``, ``2h``, ``1d``) and **byte sizes**
(``512mb``, ``4gb``). Expressing a queue budget as ``268435456`` is how a
production limit ends up an order of magnitude wrong.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import re
from typing import Any, Final

from prama.core.errors import ConfigTypeError
from prama.core.log import REDACTED, SENSITIVE_KEYS

_TRUE: Final[frozenset[str]] = frozenset({"1", "true", "yes", "y", "on", "enabled"})
_FALSE: Final[frozenset[str]] = frozenset({"0", "false", "no", "n", "off", "disabled"})

_DURATION_UNITS: Final[dict[str, float]] = {
    "ns": 1e-9,
    "us": 1e-6,
    "ms": 1e-3,
    "s": 1.0,
    "sec": 1.0,
    "secs": 1.0,
    "m": 60.0,
    "min": 60.0,
    "mins": 60.0,
    "h": 3600.0,
    "hr": 3600.0,
    "hrs": 3600.0,
    "d": 86400.0,
    "day": 86400.0,
    "days": 86400.0,
    "w": 604800.0,
}
_DURATION = re.compile(r"(?i)^\s*([0-9]*\.?[0-9]+)\s*([a-z]*)\s*$")

_SIZE_UNITS: Final[dict[str, int]] = {
    "": 1,
    "b": 1,
    "k": 1000,
    "kb": 1000,
    "ki": 1024,
    "kib": 1024,
    "m": 1000**2,
    "mb": 1000**2,
    "mi": 1024**2,
    "mib": 1024**2,
    "g": 1000**3,
    "gb": 1000**3,
    "gi": 1024**3,
    "gib": 1024**3,
    "t": 1000**4,
    "tb": 1000**4,
    "ti": 1024**4,
    "tib": 1024**4,
}
_SIZE = re.compile(r"(?i)^\s*([0-9]*\.?[0-9]+)\s*([a-z]*)\s*$")


class Coercer:
    """Converts a raw configuration value to a requested type."""

    def __init__(self, path: str = "") -> None:
        self._path = path

    def _fail(self, value: Any, wanted: str, hint: str) -> ConfigTypeError:
        return ConfigTypeError(
            f"configuration key {self._path or '<value>'} is not a valid {wanted}",
            remedy=hint,
            context={"key": self._path, "value": self._shown(value), "wanted": wanted},
        )

    def _shown(self, value: Any) -> str:
        """The offending value, unless naming it would publish a secret.

        The value is the most useful thing in a configuration type error, so it
        is withheld only where the key says it is one. It used to be included
        unconditionally, which meant a coercion failure on
        `security.session_secret` printed the real secret into an exception
        that goes on to be logged and rendered into an API problem document —
        the two places it most needs not to be.
        """
        leaf = (self._path or "").rsplit(".", 1)[-1].lower()
        return REDACTED if leaf in SENSITIVE_KEYS else repr(value)

    def to_str(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, (int, float, bool)):
            return str(value)
        raise self._fail(value, "string", "Provide a plain scalar value.")

    def to_bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in _TRUE:
                return True
            if lowered in _FALSE:
                return False
        raise self._fail(value, "boolean", "Use true/false, yes/no, on/off or 1/0.")

    def to_int(self, value: Any) -> int:
        if isinstance(value, bool):
            raise self._fail(value, "integer", "A boolean is not an integer here; be explicit.")
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, str):
            try:
                return int(value.strip(), 0)
            except ValueError:
                pass
        raise self._fail(value, "integer", "Provide a whole number, e.g. 20.")

    def to_float(self, value: Any) -> float:
        if isinstance(value, bool):
            raise self._fail(value, "number", "A boolean is not a number here; be explicit.")
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.strip())
            except ValueError:
                pass
        raise self._fail(value, "number", "Provide a number, e.g. 0.05.")

    def to_list(self, value: Any) -> list[Any]:
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        if isinstance(value, str):
            # Comma-separated is the only sane rendering of a list in an env var.
            return [item.strip() for item in value.split(",") if item.strip()]
        raise self._fail(value, "list", "Use a YAML list, or a comma-separated string.")

    def to_dict(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        raise self._fail(value, "mapping", "Use a YAML mapping of key: value pairs.")

    def to_duration_seconds(self, value: Any) -> float:
        """``30s``, ``5m``, ``2h``, ``1d``; a bare number means seconds."""
        if isinstance(value, bool):
            raise self._fail(value, "duration", "Use a duration such as 30s or 5m.")
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            match = _DURATION.match(value)
            if match:
                amount, unit = match.group(1), match.group(2).lower()
                if unit == "":
                    return float(amount)
                if unit in _DURATION_UNITS:
                    return float(amount) * _DURATION_UNITS[unit]
        raise self._fail(value, "duration", "Use a duration such as 500ms, 30s, 5m, 2h or 1d.")

    def to_bytes(self, value: Any) -> int:
        """``512mb``, ``4gib``; a bare number means bytes.

        Decimal units (kb, mb) are powers of 1000 and binary units (kib, mib)
        are powers of 1024, as the standards intend. Ambiguity here produces
        budgets that are 7% wrong, which is exactly wrong enough to be missed.
        """
        if isinstance(value, bool):
            raise self._fail(value, "byte size", "Use a size such as 512mb.")
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, str):
            match = _SIZE.match(value)
            if match:
                amount, unit = match.group(1), match.group(2).lower()
                if unit in _SIZE_UNITS:
                    return int(float(amount) * _SIZE_UNITS[unit])
        raise self._fail(value, "byte size", "Use a size such as 1024, 512kb, 256mb or 4gib.")
