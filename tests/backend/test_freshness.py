"""Freshness: measured on the column that records arrival, judged on a calendar.

Q-64: a freshness control, generated from every declared rhythm, emitted no
metric and could never be red. These tests hold what replaced it: the newest
arrival is measured, the cycle due is found on the plan's business calendar, and
the verdict is reproducible from the recorded evidence alone.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime, timedelta

import duckdb
import pytest

from prama.backend import compile_for
from prama.backend.execute import as_number, judge, unanswerable
from prama.core.calendars import default_calendars
from prama.ir.model import Verdict
from prama.ir.resolve import resolved
from prama.packs import install_shipped
from prama.pql import parse_control

install_shipped()  # TARGET2 lives in the banking pack
DUE = "CHECK trades.loaded_at IS FRESH WITHIN 30 MINUTES OF '06:30' CALENDAR 'TARGET2'"
ZONE = default_calendars().get("TARGET2").zone


def local(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=ZONE)


def verdict(pql: str, latest: datetime | None, now: datetime, rows: float = 10) -> Verdict:
    plan = resolved(parse_control(pql))
    metrics = {"scanned_rows": rows}
    if latest is not None:
        metrics["latest_at"] = latest.timestamp()
    return judge(plan, metrics, now=now).verdict


TUESDAY, MONDAY, FRIDAY = date(2026, 9, 29), date(2026, 9, 28), date(2026, 9, 25)


def test_a_freshness_control_on_a_column_can_be_answered() -> None:
    assert not unanswerable(resolved(parse_control(DUE)))
    assert unanswerable(resolved(parse_control("CHECK trades IS FRESH WITHIN 30 MINUTES")))


@pytest.mark.parametrize(
    ("latest", "now", "expected"),
    [
        # After today's deadline (06:30 + 30 min), today's load is what counts.
        (local(TUESDAY, 6, 0), local(TUESDAY, 10), Verdict.PASS),
        (local(MONDAY, 6, 0), local(TUESDAY, 10), Verdict.FAIL),
        # Within the tolerance, today is not yet due: yesterday's cycle is judged.
        (local(MONDAY, 6, 0), local(TUESDAY, 6, 45), Verdict.PASS),
        # Before the deadline, yesterday's cycle is judged.
        (local(MONDAY, 6, 0), local(TUESDAY, 5), Verdict.PASS),
        # Over a weekend: Friday's load holds until Monday's deadline, not after.
        (local(FRIDAY, 6, 0), local(MONDAY, 5), Verdict.PASS),
        (local(FRIDAY, 6, 0), local(MONDAY, 10), Verdict.FAIL),
    ],
)
def test_the_cycle_due_is_found_on_the_business_calendar(
    latest: datetime, now: datetime, expected: Verdict
) -> None:
    assert verdict(DUE, latest, now) is expected


def test_nothing_arrived_fails_and_no_timestamp_establishes_nothing() -> None:
    assert verdict(DUE, None, local(TUESDAY, 10), rows=0) is Verdict.FAIL
    assert verdict(DUE, None, local(TUESDAY, 10), rows=10) is Verdict.INDETERMINATE


def test_without_a_due_time_the_newest_row_must_be_recent_enough() -> None:
    rolling = "CHECK trades.loaded_at IS FRESH WITHIN 4 HOURS"
    now = datetime(2026, 9, 29, 12, tzinfo=UTC)
    assert verdict(rolling, now - timedelta(hours=3), now) is Verdict.PASS
    assert verdict(rolling, now - timedelta(hours=5), now) is Verdict.FAIL


def test_the_verdict_is_reproducible_from_the_evidence() -> None:
    """The instant is a metric, so judging the recorded metrics again, at any
    later time, reaches the verdict the run reached."""
    plan = resolved(parse_control(DUE))
    first = judge(
        plan,
        {"scanned_rows": 5, "latest_at": local(TUESDAY, 6).timestamp()},
        now=local(TUESDAY, 10),
    )
    later = judge(plan, dict(first.metrics), now=local(TUESDAY, 10) + timedelta(days=30))
    assert first.verdict is later.verdict is Verdict.PASS
    assert later.metrics["evaluated_at"] == local(TUESDAY, 10).timestamp()


def test_an_instant_is_a_number_whatever_the_engine_returns() -> None:
    moment = datetime(2026, 9, 29, 6, 0, tzinfo=UTC)
    assert as_number(moment) == moment.timestamp()
    assert as_number(moment.replace(tzinfo=None)) == moment.timestamp()  # naive is UTC
    assert as_number("2026-09-29T06:00:00Z") == moment.timestamp()
    assert as_number("2026-09-29 06:00:00") == moment.timestamp()
    assert as_number(date(2026, 9, 29)) == datetime(2026, 9, 29, tzinfo=UTC).timestamp()
    assert as_number("EUR") is None and as_number(True) is None and as_number(None) is None


@pytest.mark.parametrize("engine", ["duckdb", "sqlite"])
def test_executed_on_a_real_engine(engine: str) -> None:
    """Assert the executed verdict: the compiled SQL reads the newest arrival
    (a TIMESTAMP in DuckDB, ISO text in SQLite) and the judge decides."""
    loads = [local(MONDAY, 6).astimezone(UTC), local(TUESDAY, 6).astimezone(UTC)]
    plan = resolved(parse_control(DUE))
    sql = compile_for(plan, engine, table="trades").metric_query
    if engine == "duckdb":
        db = duckdb.connect()
        # TIMESTAMP, stored in UTC. (Fetching a TIMESTAMPTZ needs DuckDB's
        # optional pytz dependency, which is the client's concern, not this one.)
        db.execute("CREATE TABLE trades (id INTEGER, loaded_at TIMESTAMP)")
        db.executemany(
            "INSERT INTO trades VALUES (?, ?)",
            [(i, t.replace(tzinfo=None)) for i, t in enumerate(loads)],
        )
        cursor = db.execute(sql)
    else:
        db = sqlite3.connect(":memory:")
        db.execute("CREATE TABLE trades (id INTEGER, loaded_at TEXT)")
        db.executemany(
            "INSERT INTO trades VALUES (?, ?)", [(i, t.isoformat()) for i, t in enumerate(loads)]
        )
        cursor = db.execute(sql)
    names = [d[0] for d in cursor.description]
    row = dict(zip(names, cursor.fetchone(), strict=True))
    metrics = {k: n for k, v in row.items() if (n := as_number(v)) is not None}
    assert judge(plan, metrics, now=local(TUESDAY, 10)).verdict is Verdict.PASS
    assert judge(plan, metrics, now=local(TUESDAY, 10) + timedelta(days=1)).verdict is Verdict.FAIL


def test_each_segment_is_judged_at_the_same_instant() -> None:
    """FOR EACH currency_pair: one stale pair fails the control, the fresh one does
    not hide it, and the instants are maxima rather than sums."""
    from prama.backend.execute import judge_segments

    plan = resolved(
        parse_control(DUE.replace("CHECK trades.loaded_at", "CHECK fx.rate_at") + " FOR EACH pair")
    )
    now = local(TUESDAY, 10)
    result = judge_segments(
        plan,
        [
            ("EURUSD", {"scanned_rows": 1, "latest_at": local(TUESDAY, 6).timestamp()}),
            ("USDJPY", {"scanned_rows": 1, "latest_at": local(FRIDAY, 6).timestamp()}),
        ],
        now=now,
    )
    assert [s.verdict for s in result.segments] == [Verdict.PASS, Verdict.FAIL]
    assert result.verdict is Verdict.FAIL
    assert result.metrics["evaluated_at"] == now.timestamp()
