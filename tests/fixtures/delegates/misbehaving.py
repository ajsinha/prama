"""Delegates that must fail admission, each for one reason. Kept in a module of
their own, with clean imports, so the gate judges them rather than the test file.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from prama.delegates import DqDelegate, Measurement


class Flaky(DqDelegate):
    """Answers differently each time: it keeps state."""

    name = "test.flaky"
    calls = 0

    def measure(self, rows: Iterable[Mapping[str, Any]], params: Mapping[str, Any]) -> Measurement:
        type(self).calls += 1
        return Measurement(scanned=len(list(rows)), violating=0, note=str(self.calls))


class Fragile(DqDelegate):
    """Raises on a null, which production will send it."""

    name = "test.fragile"
    requires = ("amount",)

    def measure(self, rows: Iterable[Mapping[str, Any]], params: Mapping[str, Any]) -> Measurement:
        return Measurement(scanned=0, violating=sum(1 for r in rows if float(r["amount"]) > 1))


class Liar(DqDelegate):
    """Claims more violating rows than it scanned."""

    name = "test.liar"

    def measure(self, rows: Iterable[Mapping[str, Any]], params: Mapping[str, Any]) -> Measurement:
        return Measurement(scanned=0, violating=3)


class Thin(DqDelegate):
    """Counts findings, and never has enough data to establish any."""

    name = "test.thin"
    unit = "findings"

    def measure(self, rows: Iterable[Mapping[str, Any]], params: Mapping[str, Any]) -> Measurement:
        return Measurement(scanned=len(list(rows)), violating=0, established=False)
