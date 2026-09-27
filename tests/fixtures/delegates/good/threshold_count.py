"""A small, well-behaved delegate for the tests: counts amounts above a limit.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from prama.delegates import DqDelegate, Measurement, Parameter


class OverLimit(DqDelegate):
    name = "test.over_limit"
    version = "2"
    requires = ("id", "amount", "booked")
    parameters = (Parameter("limit", "number", 100),)
    summary = "no amount exceeds the limit"

    def measure(self, rows: Iterable[Mapping[str, Any]], params: Mapping[str, Any]) -> Measurement:
        scanned = violating = 0
        samples = []
        seen_types = set()
        for row in rows:
            scanned += 1
            seen_types.add(type(row.get("booked")).__name__)
            try:
                over = float(row.get("amount")) > float(params["limit"])
            except (TypeError, ValueError):
                over = True
            if over:
                violating += 1
                samples.append({"id": row.get("id")})
        return Measurement(
            scanned=scanned,
            violating=violating,
            samples=tuple(samples),
            note="booked types: " + ",".join(sorted(seen_types)),
        )
