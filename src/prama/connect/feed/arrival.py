"""Judging what arrived, and what did not.

The controls that catch the failures nobody else catches. A file that arrives
late, twice, out of order, truncated, or not at all is a defect that every
content-level check would pass — because the rows that *did* arrive are
perfectly valid. There is simply nothing to check.

Every status here is a distinct operational response, which is why they are not
collapsed into "ok" and "problem": a late file needs chasing, a duplicate needs
a decision, a truncated one needs re-sending, and a file for a date nobody
expected needs explaining.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
from datetime import date, datetime
from typing import Any

from prama.connect.feed.definition import FeedDefinition
from prama.connect.feed.pattern import ParsedName
from prama.core.clock import Clock, SystemClock


class ArrivalStatus(enum.Enum):
    """What happened to one expected delivery."""

    ON_TIME = "on_time"
    EARLY = "early"  # before the window opened: worth a look
    LATE = "late"
    MISSING = "missing"
    DUPLICATE = "duplicate"
    OUT_OF_SEQUENCE = "out_of_sequence"
    TRUNCATED = "truncated"
    UNEXPECTED_DAY = "unexpected_day"  # arrived for a non-business date
    UNREADABLE_NAME = "unreadable_name"

    @property
    def is_healthy(self) -> bool:
        return self is ArrivalStatus.ON_TIME

    @property
    def severity(self) -> str:
        return {
            ArrivalStatus.ON_TIME: "info",
            ArrivalStatus.EARLY: "info",
            ArrivalStatus.LATE: "major",
            ArrivalStatus.MISSING: "critical",
            ArrivalStatus.DUPLICATE: "major",
            ArrivalStatus.OUT_OF_SEQUENCE: "major",
            ArrivalStatus.TRUNCATED: "critical",
            ArrivalStatus.UNEXPECTED_DAY: "minor",
            ArrivalStatus.UNREADABLE_NAME: "minor",
        }[self]

    @property
    def next_action(self) -> str:
        """What the reader should do. Every alert carries one."""
        return {
            ArrivalStatus.ON_TIME: "nothing",
            ArrivalStatus.EARLY: "confirm with the sender that the schedule changed",
            ArrivalStatus.LATE: "chase the sender; downstream controls will run on stale data",
            ArrivalStatus.MISSING: "chase the sender before the downstream run",
            ArrivalStatus.DUPLICATE: (
                "decide whether this supersedes the earlier delivery or is a resend"
            ),
            ArrivalStatus.OUT_OF_SEQUENCE: "check whether an earlier delivery was skipped",
            ArrivalStatus.TRUNCATED: "request a re-send; the file is incomplete",
            ArrivalStatus.UNEXPECTED_DAY: (
                "confirm the calendar: either the feed now runs on this day, or the "
                "sender used the wrong date"
            ),
            ArrivalStatus.UNREADABLE_NAME: (
                "correct the filename pattern, or ask the sender to restore the convention"
            ),
        }[self]


@dataclasses.dataclass(frozen=True, slots=True)
class ObservedFile:
    """A file the landing zone actually holds."""

    filename: str
    size_bytes: int
    modified_at: datetime
    digest: str | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class ArrivalFinding:
    """One judgement about one delivery, with everything an alert needs."""

    feed: str
    status: ArrivalStatus
    business_date: date | None
    filename: str | None = None
    expected_filename: str | None = None
    due_at: datetime | None = None
    observed_at: datetime | None = None
    lateness_seconds: float | None = None
    detail: str = ""

    @property
    def severity(self) -> str:
        return self.status.severity

    @property
    def is_healthy(self) -> bool:
        return self.status.is_healthy

    def render(self) -> str:
        subject = self.filename or self.expected_filename or self.feed
        parts = [f"{subject}: {self.status.value.replace('_', ' ')}"]
        if self.lateness_seconds:
            parts.append(f"{self.lateness_seconds / 60:.0f} minutes late")
        if self.detail:
            parts.append(self.detail)
        return " — ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "feed": self.feed,
            "status": self.status.value,
            "severity": self.severity,
            "business_date": self.business_date.isoformat() if self.business_date else None,
            "filename": self.filename,
            "expected_filename": self.expected_filename,
            "due_at": self.due_at,
            "observed_at": self.observed_at,
            "lateness_seconds": self.lateness_seconds,
            "detail": self.detail,
            "next_action": self.status.next_action,
            "message": self.render(),
        }


class ArrivalJudge:
    """Compares what landed against what the feed's contract promised.

    Pure: it takes observed files and returns findings, touching nothing. That
    is what lets the same logic run in a scheduled sweep, in a test, and in a
    backfill over three months of history without behaving differently.
    """

    def __init__(self, definition: FeedDefinition, *, clock: Clock | None = None) -> None:
        self._feed = definition
        self._clock = clock or SystemClock()

    def judge(
        self,
        observed: list[ObservedFile],
        *,
        start: date,
        end: date,
        previously_seen: dict[str, str] | None = None,
    ) -> list[ArrivalFinding]:
        """Judge every expected date in ``[start, end]`` against what landed.

        *previously_seen* maps filename to digest from earlier sweeps, so a
        resend of identical bytes can be told from a genuine restatement.
        """
        feed = self._feed
        seen = previously_seen or {}
        findings: list[ArrivalFinding] = []

        parsed: dict[date, list[tuple[ParsedName, ObservedFile]]] = {}
        for file in observed:
            name = feed.filename_pattern.parse(file.filename)
            if name is None:
                continue  # not this feed's file at all
            if name.business_date is None:
                findings.append(
                    ArrivalFinding(
                        feed=feed.name,
                        status=ArrivalStatus.UNREADABLE_NAME,
                        business_date=None,
                        filename=file.filename,
                        observed_at=file.modified_at,
                        detail="the filename matched the feed but carried no readable date",
                    )
                )
                continue
            parsed.setdefault(name.business_date, []).append((name, file))

        expected = set(feed.expected_dates(start, end))
        for business_date in sorted(expected | set(parsed)):
            arrivals = parsed.get(business_date, [])
            if business_date not in expected and arrivals:
                findings.extend(self._unexpected(business_date, arrivals))
                continue
            findings.extend(self._for_date(business_date, arrivals, seen))
        return findings

    # -- per-date judgement ------------------------------------------------

    def _for_date(
        self,
        business_date: date,
        arrivals: list[tuple[ParsedName, ObservedFile]],
        seen: dict[str, str],
    ) -> list[ArrivalFinding]:
        feed = self._feed
        due = feed.due_at(business_date)
        deadline = feed.deadline(business_date)
        findings: list[ArrivalFinding] = []

        if not arrivals:
            # Absent, but only *missing* once the deadline has actually passed:
            # reporting a file missing at 06:00 when it is due at 06:30 is how a
            # feed monitor teaches people to ignore it.
            if feed.can_detect_missing and deadline and self._clock.now() > deadline:
                findings.append(
                    ArrivalFinding(
                        feed=feed.name,
                        status=ArrivalStatus.MISSING,
                        business_date=business_date,
                        expected_filename=feed.expected_filenames(business_date)[0],
                        due_at=due,
                        detail=f"nothing has arrived for {business_date.isoformat()}",
                    )
                )
            return findings

        # By arrival order, *not* by sequence number. Sorting by sequence would
        # put the deliveries back into the order the sender intended and make
        # the out-of-sequence check below unable to ever fire — which is the one
        # thing it exists to catch.
        arrivals.sort(key=lambda pair: (pair[1].modified_at, pair[0].sequence or 0))
        last_sequence = 0
        for index, (name, file) in enumerate(arrivals):
            if index > 0 and not feed.duplicates.permits_second_delivery:
                findings.append(self._duplicate(business_date, file, seen, due))
                continue
            if name.sequence is not None and name.sequence < last_sequence:
                findings.append(
                    ArrivalFinding(
                        feed=feed.name,
                        status=ArrivalStatus.OUT_OF_SEQUENCE,
                        business_date=business_date,
                        filename=file.filename,
                        observed_at=file.modified_at,
                        detail=f"sequence {name.sequence} arrived after {last_sequence}",
                    )
                )
                continue
            last_sequence = max(last_sequence, name.sequence or 0)
            findings.append(self._timeliness(business_date, file, due, deadline))

        missing = feed.files_per_day - len(arrivals)
        if missing > 0 and feed.can_detect_missing and deadline and self._clock.now() > deadline:
            findings.append(
                ArrivalFinding(
                    feed=feed.name,
                    status=ArrivalStatus.MISSING,
                    business_date=business_date,
                    expected_filename=feed.expected_filenames(business_date)[len(arrivals)],
                    due_at=due,
                    detail=f"{missing} of {feed.files_per_day} deliveries have not arrived",
                )
            )
        return findings

    def _timeliness(
        self,
        business_date: date,
        file: ObservedFile,
        due: datetime | None,
        deadline: datetime | None,
    ) -> ArrivalFinding:
        feed = self._feed
        if file.size_bytes < feed.minimum_bytes:
            return ArrivalFinding(
                feed=feed.name,
                status=ArrivalStatus.TRUNCATED,
                business_date=business_date,
                filename=file.filename,
                observed_at=file.modified_at,
                detail=(
                    f"{file.size_bytes:,} bytes is below the declared minimum of "
                    f"{feed.minimum_bytes:,}"
                ),
            )
        opens = feed.window_opens_at(business_date)
        if opens and file.modified_at < opens:
            return ArrivalFinding(
                feed=feed.name,
                status=ArrivalStatus.EARLY,
                business_date=business_date,
                filename=file.filename,
                due_at=due,
                observed_at=file.modified_at,
                detail="arrived before the window opened",
            )
        if deadline and file.modified_at > deadline:
            return ArrivalFinding(
                feed=feed.name,
                status=ArrivalStatus.LATE,
                business_date=business_date,
                filename=file.filename,
                due_at=due,
                observed_at=file.modified_at,
                # Measured from the *due* time, not from the grace-adjusted
                # deadline. Grace decides whether to raise the finding; it is an
                # alerting tolerance, not a renegotiated promise. Measuring from
                # the deadline would understate every breach and make the
                # lateness trend shift retroactively whenever someone tuned the
                # grace period.
                lateness_seconds=(file.modified_at - (due or deadline)).total_seconds(),
            )
        return ArrivalFinding(
            feed=feed.name,
            status=ArrivalStatus.ON_TIME,
            business_date=business_date,
            filename=file.filename,
            due_at=due,
            observed_at=file.modified_at,
        )

    def _duplicate(
        self,
        business_date: date,
        file: ObservedFile,
        seen: dict[str, str],
        due: datetime | None,
    ) -> ArrivalFinding:
        previous = seen.get(file.filename)
        if previous and file.digest and previous == file.digest:
            detail = "identical bytes to the earlier delivery: a resend, not a restatement"
        elif previous and file.digest:
            detail = "same name, different content: this is a restatement, not a resend"
        else:
            detail = f"a second delivery for {business_date.isoformat()}"
        return ArrivalFinding(
            feed=self._feed.name,
            status=ArrivalStatus.DUPLICATE,
            business_date=business_date,
            filename=file.filename,
            due_at=due,
            observed_at=file.modified_at,
            detail=detail,
        )

    def _unexpected(
        self, business_date: date, arrivals: list[tuple[ParsedName, ObservedFile]]
    ) -> list[ArrivalFinding]:
        return [
            ArrivalFinding(
                feed=self._feed.name,
                status=ArrivalStatus.UNEXPECTED_DAY,
                business_date=business_date,
                filename=file.filename,
                observed_at=file.modified_at,
                detail=(
                    f"{business_date.isoformat()} is not a business day on the "
                    f"{self._feed.calendar.name} calendar"
                ),
            )
            for _, file in arrivals
        ]


def summarise(findings: list[ArrivalFinding]) -> dict[str, Any]:
    """A feed's arrival health, in the shape a scorecard wants."""
    by_status: dict[str, int] = {}
    for finding in findings:
        by_status[finding.status.value] = by_status.get(finding.status.value, 0) + 1
    unhealthy = [f for f in findings if not f.is_healthy]
    return {
        "total": len(findings),
        "healthy": len(findings) - len(unhealthy),
        "by_status": dict(sorted(by_status.items())),
        "worst_severity": _worst([f.severity for f in unhealthy]),
        "findings": [f.to_dict() for f in unhealthy],
    }


def _worst(severities: list[str]) -> str | None:
    order = ["info", "minor", "major", "critical"]
    return max(severities, key=order.index) if severities else None
