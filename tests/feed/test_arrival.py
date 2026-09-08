"""Arrival judgement: the difference between late, missing and duplicate.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

import pytest

from prama.connect.feed import (
    ArrivalJudge,
    ArrivalStatus,
    DuplicatePolicy,
    FeedDefinition,
    FilenamePattern,
    ObservedFile,
    summarise,
)
from prama.core.calendars import BusinessCalendar
from prama.core.clock import Clock

#: Good Friday and Easter Monday 2026 — a four-day break, the case where a
#: naive weekday calendar raises two false alarms in a row.
TARGET2 = BusinessCalendar(
    "TARGET2",
    timezone="Europe/Berlin",
    holidays=frozenset({date(2026, 4, 3), date(2026, 4, 6)}),
)


class FrozenClock(Clock):
    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment

    def monotonic(self) -> float:
        return 0.0

    def epoch_millis(self) -> int:
        return int(self._moment.timestamp() * 1000)


def feed(**overrides: object) -> FeedDefinition:
    settings: dict[str, object] = {
        "name": "positions_eod",
        "landing_path": "/landing/positions",
        "filename_pattern": FilenamePattern("POS_{YYYYMMDD}.csv"),
        "calendar": TARGET2,
        "due_by": time(6, 30),
        "lateness_grace": timedelta(minutes=15),
    }
    settings.update(overrides)
    return FeedDefinition(**settings)  # type: ignore[arg-type]


def landed(day: date, at: datetime, *, size: int = 5000, digest: str | None = None) -> ObservedFile:
    return ObservedFile(f"POS_{day:%Y%m%d}.csv", size, at, digest=digest)


def judge(
    definition: FeedDefinition,
    observed: list[ObservedFile],
    *,
    now: datetime = datetime(2026, 4, 10, 12, 0, tzinfo=UTC),
    start: date = date(2026, 4, 1),
    end: date = date(2026, 4, 2),
    seen: dict[str, str] | None = None,
) -> list:
    return ArrivalJudge(definition, clock=FrozenClock(now)).judge(
        observed, start=start, end=end, previously_seen=seen
    )


class TestTimeliness:
    def test_a_file_inside_the_window_is_on_time(self) -> None:
        findings = judge(
            feed(),
            [
                landed(date(2026, 4, 1), datetime(2026, 4, 1, 4, 0, tzinfo=UTC)),
                landed(date(2026, 4, 2), datetime(2026, 4, 2, 4, 0, tzinfo=UTC)),
            ],
        )
        assert [f.status for f in findings] == [ArrivalStatus.ON_TIME] * 2
        assert all(f.is_healthy for f in findings)

    def test_the_grace_period_absorbs_a_trivial_overrun(self) -> None:
        # 06:30 Berlin in April is 04:30 UTC; ten minutes past is inside grace.
        findings = judge(
            feed(),
            [
                landed(date(2026, 4, 1), datetime(2026, 4, 1, 4, 40, tzinfo=UTC)),
                landed(date(2026, 4, 2), datetime(2026, 4, 2, 4, 0, tzinfo=UTC)),
            ],
        )
        assert findings[0].status is ArrivalStatus.ON_TIME

    def test_past_grace_is_late_and_says_by_how_much(self) -> None:
        findings = judge(
            feed(),
            [
                landed(date(2026, 4, 1), datetime(2026, 4, 1, 7, 0, tzinfo=UTC)),
                landed(date(2026, 4, 2), datetime(2026, 4, 2, 4, 0, tzinfo=UTC)),
            ],
        )
        assert findings[0].status is ArrivalStatus.LATE
        assert findings[0].lateness_seconds == pytest.approx(150 * 60)
        assert "150 minutes late" in findings[0].render()

    def test_a_file_before_the_window_opens_is_flagged_early(self) -> None:
        # Early is not harmless: it usually means yesterday's data resent under
        # today's name, and it is silent unless someone looks for it.
        findings = judge(
            feed(earliest=time(3, 0)),
            [
                landed(date(2026, 4, 1), datetime(2026, 4, 1, 0, 30, tzinfo=UTC)),
                landed(date(2026, 4, 2), datetime(2026, 4, 2, 4, 0, tzinfo=UTC)),
            ],
        )
        assert findings[0].status is ArrivalStatus.EARLY

    def test_a_deadline_written_locally_holds_across_a_clock_change(self) -> None:
        # 06:30 Berlin is 05:30 UTC in January and 04:30 UTC in April. A file at
        # 05:00 UTC is on time in winter and late in spring, and a platform that
        # stored the deadline as UTC would get exactly one of those wrong.
        winter = judge(
            feed(),
            [landed(date(2026, 1, 15), datetime(2026, 1, 15, 5, 0, tzinfo=UTC))],
            start=date(2026, 1, 15),
            end=date(2026, 1, 15),
        )
        spring = judge(
            feed(),
            [landed(date(2026, 4, 15), datetime(2026, 4, 15, 5, 0, tzinfo=UTC))],
            start=date(2026, 4, 15),
            end=date(2026, 4, 15),
        )
        assert winter[0].status is ArrivalStatus.ON_TIME
        assert spring[0].status is ArrivalStatus.LATE


class TestAbsence:
    def test_a_missing_file_is_named_so_someone_can_go_and_look(self) -> None:
        findings = judge(feed(), [landed(date(2026, 4, 1), datetime(2026, 4, 1, 4, 0, tzinfo=UTC))])
        missing = [f for f in findings if f.status is ArrivalStatus.MISSING]
        assert len(missing) == 1
        assert missing[0].expected_filename == "POS_20260402.csv"
        assert missing[0].severity == "critical"

    def test_nothing_is_missing_on_a_holiday(self) -> None:
        # The whole reason calendars are first-class: without TARGET2, Good
        # Friday and Easter Monday each raise a critical alert for a file that
        # was never going to arrive, and the team learns to ignore the feed.
        findings = judge(
            feed(),
            [landed(date(2026, 4, 2), datetime(2026, 4, 2, 4, 0, tzinfo=UTC))],
            start=date(2026, 4, 2),
            end=date(2026, 4, 7),
        )
        assert [f.business_date for f in findings if f.status is ArrivalStatus.MISSING] == [
            date(2026, 4, 7)
        ]

    def test_a_future_date_is_not_yet_missing(self) -> None:
        # Judged at 05:00 UTC on 2 April, before the 04:30 deadline has... has
        # passed, in fact — so a date whose deadline is still ahead is pending,
        # not missing.
        findings = judge(
            feed(due_by=time(23, 0)),
            [],
            now=datetime(2026, 4, 2, 5, 0, tzinfo=UTC),
            start=date(2026, 4, 2),
            end=date(2026, 4, 2),
        )
        assert findings == []


class TestDuplicates:
    def test_a_second_delivery_is_rejected_by_default(self) -> None:
        findings = judge(
            feed(),
            [
                landed(date(2026, 4, 1), datetime(2026, 4, 1, 4, 0, tzinfo=UTC)),
                landed(date(2026, 4, 1), datetime(2026, 4, 1, 5, 0, tzinfo=UTC)),
                landed(date(2026, 4, 2), datetime(2026, 4, 2, 4, 0, tzinfo=UTC)),
            ],
        )
        assert [f.status for f in findings].count(ArrivalStatus.DUPLICATE) == 1

    def test_a_feed_that_delivers_in_parts_is_not_duplicating(self) -> None:
        definition = feed(
            filename_pattern=FilenamePattern("POS_{YYYYMMDD}_{SEQ:3}.csv"),
            files_per_day=3,
            duplicates=DuplicatePolicy.ACCUMULATE,
        )
        observed = [
            ObservedFile(f"POS_20260401_{n:03d}.csv", 5000, datetime(2026, 4, 1, 4, n, tzinfo=UTC))
            for n in (1, 2, 3)
        ]
        findings = ArrivalJudge(
            definition, clock=FrozenClock(datetime(2026, 4, 10, tzinfo=UTC))
        ).judge(observed, start=date(2026, 4, 1), end=date(2026, 4, 1))
        assert all(f.status is ArrivalStatus.ON_TIME for f in findings)

    def test_an_out_of_order_sequence_is_reported(self) -> None:
        definition = feed(
            filename_pattern=FilenamePattern("POS_{YYYYMMDD}_{SEQ:3}.csv"),
            files_per_day=2,
            duplicates=DuplicatePolicy.ACCUMULATE,
        )
        observed = [
            ObservedFile("POS_20260401_002.csv", 5000, datetime(2026, 4, 1, 4, 1, tzinfo=UTC)),
            ObservedFile("POS_20260401_001.csv", 5000, datetime(2026, 4, 1, 4, 2, tzinfo=UTC)),
        ]
        findings = ArrivalJudge(
            definition, clock=FrozenClock(datetime(2026, 4, 10, tzinfo=UTC))
        ).judge(observed, start=date(2026, 4, 1), end=date(2026, 4, 1))
        assert ArrivalStatus.OUT_OF_SEQUENCE in {f.status for f in findings}


class TestSuspiciousFiles:
    def test_a_file_below_the_declared_floor_is_truncated(self) -> None:
        # A truncated file passes every row-level check, because every row that
        # made it is valid. Only the size says anything is wrong.
        findings = judge(
            feed(minimum_bytes=1000),
            [
                landed(date(2026, 4, 1), datetime(2026, 4, 1, 4, 0, tzinfo=UTC), size=42),
                landed(date(2026, 4, 2), datetime(2026, 4, 2, 4, 0, tzinfo=UTC)),
            ],
        )
        assert findings[0].status is ArrivalStatus.TRUNCATED
        assert findings[0].severity == "critical"

    def test_a_file_for_a_non_business_day_questions_the_calendar(self) -> None:
        findings = judge(
            feed(),
            [
                landed(date(2026, 4, 1), datetime(2026, 4, 1, 4, 0, tzinfo=UTC)),
                landed(date(2026, 4, 2), datetime(2026, 4, 2, 4, 0, tzinfo=UTC)),
                landed(date(2026, 4, 3), datetime(2026, 4, 3, 4, 0, tzinfo=UTC)),
            ],
        )
        unexpected = [f for f in findings if f.status is ArrivalStatus.UNEXPECTED_DAY]
        assert len(unexpected) == 1
        # Minor, not critical: the data is here. The declaration may be stale.
        assert unexpected[0].severity == "minor"

    def test_a_name_that_matches_but_carries_no_date_is_reported(self) -> None:
        findings = judge(
            feed(),
            [
                ObservedFile("POS_20260231.csv", 5000, datetime(2026, 3, 2, 4, 0, tzinfo=UTC)),
                landed(date(2026, 4, 1), datetime(2026, 4, 1, 4, 0, tzinfo=UTC)),
                landed(date(2026, 4, 2), datetime(2026, 4, 2, 4, 0, tzinfo=UTC)),
            ],
        )
        assert ArrivalStatus.UNREADABLE_NAME in {f.status for f in findings}

    def test_another_feeds_file_in_the_same_directory_is_ignored(self) -> None:
        findings = judge(
            feed(),
            [
                ObservedFile("TRADES_20260401.csv", 5000, datetime(2026, 4, 1, 4, 0, tzinfo=UTC)),
                landed(date(2026, 4, 1), datetime(2026, 4, 1, 4, 0, tzinfo=UTC)),
                landed(date(2026, 4, 2), datetime(2026, 4, 2, 4, 0, tzinfo=UTC)),
            ],
        )
        assert all(f.status is ArrivalStatus.ON_TIME for f in findings)


class TestSummary:
    def test_the_summary_carries_the_worst_severity_not_an_average(self) -> None:
        # A scorecard that averaged severities would show a feed with one
        # missing file and nine good ones as healthy.
        findings = judge(
            feed(),
            [landed(date(2026, 4, 1), datetime(2026, 4, 1, 4, 0, tzinfo=UTC))],
        )
        summary = summarise(findings)
        assert summary["total"] == 2
        assert summary["healthy"] == 1
        assert summary["worst_severity"] == "critical"
        assert summary["by_status"]["missing"] == 1

    def test_a_clean_sweep_reports_no_worst_severity(self) -> None:
        summary = summarise(
            judge(
                feed(),
                [
                    landed(date(2026, 4, 1), datetime(2026, 4, 1, 4, 0, tzinfo=UTC)),
                    landed(date(2026, 4, 2), datetime(2026, 4, 2, 4, 0, tzinfo=UTC)),
                ],
            )
        )
        assert summary["worst_severity"] is None
        assert summary["findings"] == []
