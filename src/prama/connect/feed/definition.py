"""What a feed is.

A feed is not a file; it is *a contract about arrival*. Declaring one is how a
business owner says "positions arrive from the front office by 06:30 on TARGET2
business days, one file, with a trailer record carrying the count" — and every
one of those clauses becomes a control.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
from datetime import date, datetime, time, timedelta
from typing import Any

from prama.connect.feed.pattern import FilenamePattern
from prama.core.calendars import ALWAYS_OPEN, BusinessCalendar
from prama.core.errors import ValidationError


class DuplicatePolicy(enum.Enum):
    """What a second file for the same business date means.

    Not one answer for everyone: some feeds resend on failure and the latest
    wins; some send corrections that must both be kept; for some a second file
    is always a defect. Guessing produces either lost restatements or false
    alarms every time a sender retries.
    """

    REJECT = "reject"  # a second delivery is a defect
    LATEST_WINS = "latest_wins"  # a resend supersedes
    ACCUMULATE = "accumulate"  # each delivery is a genuine increment

    @property
    def permits_second_delivery(self) -> bool:
        return self is not DuplicatePolicy.REJECT


@dataclasses.dataclass(frozen=True, slots=True)
class TrailerSpec:
    """How a file states what it should contain.

    The cheapest genuine integrity check there is: the sender counted the rows
    on the way out, and comparing that to what arrived catches truncation, a
    half-written file and a failed transfer — none of which any content-level
    control would notice, because the rows that *did* arrive are all valid.
    """

    #: Marker that identifies the trailer line, e.g. ``TRLR`` or ``9``.
    marker: str = ""
    #: Which delimited field holds the record count, zero-based.
    count_field: int = 1
    #: Which field of the *trailer* holds a monetary or hash total, if any.
    total_field: int | None = None
    #: Which column of the *data rows* that total sums. A separate setting
    #: because the two coincide only by accident: the trailer is usually
    #: ``TRLR,<count>,<total>`` while the amount sits in column nine of the
    #: data. Defaults to ``total_field`` when unset, which is right for the
    #: fixed-layout feeds where the trailer mirrors the record.
    amount_field: int | None = None
    delimiter: str = ","
    #: Whether the trailer itself counts toward the stated total.
    counts_itself: bool = False
    #: Header rows to exclude from the count. Without this a headed CSV reports
    #: a one-row shortfall on every single delivery, and the check gets muted.
    header_lines: int = 0
    #: Permitted difference between declared and summed totals, as a decimal
    #: string. Exact by default; senders who truncate the hash total to two
    #: places while carrying six in the rows need a little room.
    total_tolerance: str = "0"

    @property
    def is_declared(self) -> bool:
        return bool(self.marker)

    @property
    def sum_column(self) -> int | None:
        return self.amount_field if self.amount_field is not None else self.total_field


@dataclasses.dataclass(frozen=True, slots=True)
class FeedDefinition:
    """A feed's arrival contract.

    Every field here generates a control (docs/03 §5): the window generates
    timeliness, the calendar decides which absences are real, the trailer
    generates a completeness check, and the duplicate policy decides whether a
    second file is an incident or a restatement.
    """

    name: str
    #: Where files land, relative to the connection's root.
    landing_path: str
    filename_pattern: FilenamePattern
    calendar: BusinessCalendar = ALWAYS_OPEN
    #: When the file is due, in the calendar's local time.
    due_by: time | None = None
    #: How early it may legitimately arrive before the window opens.
    earliest: time | None = None
    #: Grace before lateness becomes an incident.
    lateness_grace: timedelta = timedelta(0)
    files_per_day: int = 1
    duplicates: DuplicatePolicy = DuplicatePolicy.REJECT
    trailer: TrailerSpec = dataclasses.field(default_factory=TrailerSpec)
    #: A manifest naming the files that make up one logical delivery.
    manifest_pattern: FilenamePattern | None = None
    minimum_bytes: int = 0
    encoding: str = "utf-8"
    decryption_key_ref: str | None = None

    def __post_init__(self) -> None:
        if self.files_per_day < 1:
            raise ValidationError(
                f"feed {self.name!r} expects fewer than one file per day",
                remedy="A feed that never delivers is not a feed; remove it or set at least 1.",
                context={"feed": self.name},
            )
        if self.files_per_day > 1 and not self.filename_pattern.carries_sequence:
            raise ValidationError(
                f"feed {self.name!r} expects {self.files_per_day} files a day but its "
                f"filename pattern has no sequence token",
                remedy=(
                    "Add {SEQ} (or {SEQ:3} for a padded one) to the pattern, so the "
                    "deliveries can be told apart and a missing one identified."
                ),
                context={"feed": self.name, "pattern": self.filename_pattern.pattern},
            )
        if self.due_by is None and self.earliest is not None:
            raise ValidationError(
                f"feed {self.name!r} declares an earliest time but no due time",
                remedy="State when the file is due; an open-ended window cannot be late.",
                context={"feed": self.name},
            )

    @property
    def has_arrival_window(self) -> bool:
        return self.due_by is not None

    @property
    def can_detect_missing(self) -> bool:
        """Whether an absence can be reported at all.

        Needs both a due time and a date readable from the name — otherwise
        "the file has not arrived" cannot be distinguished from "the file
        arrived and we could not tell which day it was for".
        """
        return self.has_arrival_window and self.filename_pattern.carries_date

    def due_at(self, business_date: date) -> datetime | None:
        if self.due_by is None:
            return None
        return self.calendar.expected_at(business_date, self.due_by)

    def deadline(self, business_date: date) -> datetime | None:
        due = self.due_at(business_date)
        return None if due is None else due + self.lateness_grace

    def window_opens_at(self, business_date: date) -> datetime | None:
        if self.earliest is None:
            return None
        return self.calendar.expected_at(business_date, self.earliest)

    def expected_dates(self, start: date, end: date) -> list[date]:
        """Business dates in ``[start, end]`` for which a file is expected."""
        dates, cursor = [], start
        while cursor <= end:
            if self.calendar.is_business_day(cursor):
                dates.append(cursor)
            cursor += timedelta(days=1)
        return dates

    def expected_filenames(self, business_date: date) -> list[str]:
        """What should arrive for a date, named so an alert can quote it."""
        return [
            self.filename_pattern.render(business_date, sequence=n)
            for n in range(1, self.files_per_day + 1)
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "landing_path": self.landing_path,
            "pattern": self.filename_pattern.pattern,
            "calendar": self.calendar.name,
            "due_by": self.due_by.isoformat() if self.due_by else None,
            "lateness_grace_seconds": self.lateness_grace.total_seconds(),
            "files_per_day": self.files_per_day,
            "duplicates": self.duplicates.value,
            "trailer_declared": self.trailer.is_declared,
            "can_detect_missing": self.can_detect_missing,
        }

    @classmethod
    def from_dict(
        cls, data: dict[str, Any], *, calendar: BusinessCalendar | None = None
    ) -> FeedDefinition:
        trailer = data.get("trailer") or {}
        return cls(
            name=data["name"],
            landing_path=data.get("landing_path", ""),
            filename_pattern=FilenamePattern(data["pattern"]),
            calendar=calendar or ALWAYS_OPEN,
            due_by=time.fromisoformat(data["due_by"]) if data.get("due_by") else None,
            earliest=time.fromisoformat(data["earliest"]) if data.get("earliest") else None,
            lateness_grace=timedelta(seconds=float(data.get("lateness_grace_seconds", 0))),
            files_per_day=int(data.get("files_per_day", 1)),
            duplicates=DuplicatePolicy(data.get("duplicates", "reject")),
            trailer=TrailerSpec(
                marker=trailer.get("marker", ""),
                count_field=int(trailer.get("count_field", 1)),
                total_field=trailer.get("total_field"),
                delimiter=trailer.get("delimiter", ","),
                counts_itself=bool(trailer.get("counts_itself", False)),
            ),
            minimum_bytes=int(data.get("minimum_bytes", 0)),
            encoding=data.get("encoding", "utf-8"),
            decryption_key_ref=data.get("decryption_key_ref"),
        )
