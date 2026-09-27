"""acme.settlement_cycle — every trade settles on its market's business-day cycle.

Why this is a delegate and not PQL: "trade date plus N business days" needs a
calendar per market. The US moved equities to T+1 on 28 May 2024, the EU is
on T+2, and a TARGET2 closing day is not a settlement day. A column
comparison (`settlement_date >= trade_date`) passes every one of the defects
this finds.

The calendars live in this file, so they are part of its source hash: adding
a holiday changes the identity recorded on every evidence record this
delegate produces, which is exactly what should happen when the rule changes.
The 2026 calendars are illustrative, for the case study.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary; see LICENSE.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, timedelta
from typing import Any

from prama.delegates import DqDelegate, Measurement, Parameter

#: Closing days by market, 2026.
CLOSED: dict[str, frozenset[str]] = {
    "US": frozenset(
        {
            "2026-01-01",
            "2026-01-19",
            "2026-02-16",
            "2026-04-03",
            "2026-05-25",
            "2026-06-19",
            "2026-07-03",
            "2026-09-07",
            "2026-11-26",
            "2026-12-25",
        }
    ),
    "EU": frozenset(  # TARGET2
        {"2026-01-01", "2026-04-03", "2026-04-06", "2026-05-01", "2026-12-25", "2026-12-26"}
    ),
    "UK": frozenset(
        {
            "2026-01-01",
            "2026-04-03",
            "2026-04-06",
            "2026-05-04",
            "2026-05-25",
            "2026-08-31",
            "2026-12-25",
            "2026-12-28",
        }
    ),
}

#: How many violating rows to keep as evidence.
SAMPLES = 20


def add_business_days(start: date, days: int, closed: frozenset[str]) -> date:
    current = start
    while days > 0:
        current += timedelta(days=1)
        if current.weekday() < 5 and current.isoformat() not in closed:
            days -= 1
    return current


def _date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


class SettlementCycle(DqDelegate):
    name = "acme.settlement_cycle"
    version = "1"
    requires = ("trade_id", "market", "trade_date", "settlement_date")
    parameters = (
        Parameter("us_cycle", "number", 1, doc="US equities: T+1 since 28 May 2024."),
        Parameter("eu_cycle", "number", 2, doc="EU: T+2 (CSDR)."),
        Parameter("uk_cycle", "number", 2, doc="UK: T+2 until the move to T+1."),
    )
    unit = "rows"
    summary = "each trade settles exactly its market's cycle of business days after trading"

    def measure(self, rows: Iterable[Mapping[str, Any]], params: Mapping[str, Any]) -> Measurement:
        cycles = {
            "US": int(params["us_cycle"]),
            "EU": int(params["eu_cycle"]),
            "UK": int(params["uk_cycle"]),
        }
        scanned = violating = late = early = unreadable = unknown = 0
        samples: list[dict[str, Any]] = []
        for row in rows:
            scanned += 1
            market = str(row.get("market") or "").upper()
            traded, settled = _date(row.get("trade_date")), _date(row.get("settlement_date"))
            if traded is None or settled is None:
                unreadable += 1
                reason = "a date that cannot be read"
            elif market not in cycles:
                unknown += 1
                reason = f"no calendar for market {market or '(blank)'}"
            else:
                expected = add_business_days(traded, cycles[market], CLOSED[market])
                if settled == expected:
                    continue
                if settled > expected:
                    late += 1
                else:
                    early += 1
                reason = f"expected {expected.isoformat()} (T+{cycles[market]} {market})"
            violating += 1
            if len(samples) < SAMPLES:
                samples.append({**{k: row.get(k) for k in self.requires}, "why": reason})
        return Measurement(
            scanned=scanned,
            violating=violating,
            observations={
                "late_settlements": late,
                "early_settlements": early,
                "unreadable_dates": unreadable,
                "unknown_markets": unknown,
            },
            samples=tuple(samples),
            note=(
                f"{late} settle later than their cycle, {early} earlier, "
                f"{unreadable} have an unreadable date, {unknown} an unknown market"
            ),
        )
