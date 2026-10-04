"""example.balance_continuity — the worked example of docs/developer/delegates.md.

Each day's opening balance for an account must equal the previous day's closing
balance. PQL cannot say this: it is a comparison between *rows*, in date order,
per account, and a column comparison passes every gap it should find.

It measures and never decides: it counts the rows it scanned and the rows that
break the chain, and the control's threshold turns those into a verdict.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date
from itertools import pairwise
from typing import Any

from prama.delegates import DqDelegate, Measurement, Parameter

#: How many violating rows to keep as evidence.
SAMPLES = 20


def _day(value: Any) -> str:
    """An ISO date as text, or "" when the value is not one."""
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError:
        return ""


def _amount(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class BalanceContinuity(DqDelegate):
    name = "example.balance_continuity"
    version = "1"
    requires = ("account_id", "as_of", "opening", "closing")
    parameters = (
        Parameter(
            "tolerance",
            "number",
            default=0.005,
            doc="The largest difference still counted as continuous, in the balance's units.",
        ),
    )
    unit = "rows"
    summary = "each day's opening balance equals the previous day's closing balance"

    def measure(self, rows: Iterable[Mapping[str, Any]], params: Mapping[str, Any]) -> Measurement:
        tolerance = float(params.get("tolerance") or 0.0)
        by_account: dict[str, list[tuple[str, Mapping[str, Any]]]] = {}
        scanned = undated = 0
        samples: list[Mapping[str, Any]] = []
        # One pass over the rows: Prama streams them, and a second pass would
        # silently see nothing.
        for row in rows:
            scanned += 1
            day = _day(row.get("as_of"))
            if not day:
                # A balance with no date cannot be placed in the chain at all.
                undated += 1
                if len(samples) < SAMPLES:
                    samples.append(dict(row))
                continue
            by_account.setdefault(str(row.get("account_id")), []).append((day, row))

        broken = 0
        for account in sorted(by_account):
            days = sorted(by_account[account], key=lambda item: item[0])
            for (_, previous), (_, current) in pairwise(days):
                closed, opened = _amount(previous.get("closing")), _amount(current.get("opening"))
                if closed is None or opened is None or abs(opened - closed) > tolerance:
                    broken += 1
                    if len(samples) < SAMPLES:
                        samples.append(dict(current))

        return Measurement(
            scanned=scanned,
            violating=broken + undated,
            observations={"accounts": float(len(by_account)), "undated": float(undated)},
            samples=tuple(samples),
            note=f"{broken} break(s) in the balance chain, {undated} undated row(s)",
            # One row proves nothing about continuity: there is no chain yet.
            established=scanned >= 2,
        )
