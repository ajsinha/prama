"""Profiling a dataset in parts, because the whole hides the problem.

A table-level null rate of 2% is a number that reassures. The same data
segmented by day says 100% null since Tuesday, and by region says every one of
those is EMEA. The aggregate did not merely fail to show the problem — it
actively concealed it, and it will keep concealing it as long as the healthy
segments outnumber the broken one.

That is the argument for segmentation as a first-class idea rather than a filter
somebody remembers to apply: the interesting failures in a data estate are
almost always confined to a slice, and a slice small enough to matter is small
enough to disappear into a total.

Segments are also the unit of incremental work. Because every accumulator here
merges, a segment profiled once never needs profiling again, and a dataset's
current profile is the fold of its segments' — which is what makes nightly
re-examination of a large estate arithmetic rather than a scan.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
from datetime import date, datetime
from typing import Any

from prama.core.errors import ValidationError

#: Beyond this, segmenting produces more findings than anyone will read and
#: more reads than the source will tolerate. Refused rather than truncated: a
#: silently truncated segmentation reports "all segments healthy" while never
#: having looked at most of them.
MAX_SEGMENTS = 2_000


class SegmentGrain(enum.Enum):
    """How a dataset is cut up."""

    NONE = "none"
    DAY = "day"
    MONTH = "month"
    VALUE = "value"

    @property
    def is_temporal(self) -> bool:
        return self in (SegmentGrain.DAY, SegmentGrain.MONTH)


@dataclasses.dataclass(frozen=True, slots=True)
class Segment:
    """One slice of a dataset, and how to read just that slice."""

    key: str
    column: str
    grain: SegmentGrain
    #: Inclusive lower and exclusive upper bound for a temporal segment.
    lower: Any = None
    upper: Any = None
    #: The exact value for a categorical segment.
    value: Any = None

    @property
    def label(self) -> str:
        return f"{self.column}={self.key}"

    def predicate(self, quote: Any) -> str:
        """A SQL predicate selecting this segment.

        ``quote`` is the dialect's identifier quoter, so the column name is
        never interpolated raw — segment columns come from a customer's
        catalogue and end up in a query string.
        """
        column = quote(self.column)
        if self.grain is SegmentGrain.VALUE:
            return f"{column} = {_literal(self.value)}"
        return f"{column} >= {_literal(self.lower)} AND {column} < {_literal(self.upper)}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "column": self.column,
            "grain": self.grain.value,
            "lower": _plain(self.lower),
            "upper": _plain(self.upper),
            "value": _plain(self.value),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Segmentation:
    """How a dataset should be divided, as a business person would say it.

    "By business date" or "by booking entity" — not a partition specification.
    A dataset's physical partitioning is often wrong for the question being
    asked, and is sometimes absent entirely.
    """

    column: str
    grain: SegmentGrain = SegmentGrain.DAY

    def __post_init__(self) -> None:
        if not self.column and self.grain is not SegmentGrain.NONE:
            raise ValidationError(
                "a segmentation needs the column that divides the dataset",
                remedy=(
                    "Name the column — usually the business date, or whatever "
                    "identifies the batch a row arrived in."
                ),
            )

    def over_dates(self, start: date, end: date) -> list[Segment]:
        """Segments covering ``[start, end]`` inclusive."""
        if not self.grain.is_temporal:
            raise ValidationError(
                f"a {self.grain.value} segmentation cannot be built from a date range",
                remedy="Use over_values() for a categorical segmentation.",
                context={"grain": self.grain.value},
            )
        if end < start:
            raise ValidationError(
                "the segmentation range ends before it begins",
                remedy="Give the earlier date first.",
                context={"start": start.isoformat(), "end": end.isoformat()},
            )
        segments = (
            self._daily(start, end) if self.grain is SegmentGrain.DAY else self._monthly(start, end)
        )
        self._check_count(len(segments))
        return segments

    def over_values(self, values: list[Any]) -> list[Segment]:
        """One segment per distinct value — by entity, region, product."""
        unique = sorted({v for v in values if v is not None}, key=str)
        self._check_count(len(unique))
        return [
            Segment(key=str(value), column=self.column, grain=SegmentGrain.VALUE, value=value)
            for value in unique
        ]

    def _daily(self, start: date, end: date) -> list[Segment]:
        from datetime import timedelta

        out = []
        day = start
        while day <= end:
            following = day + timedelta(days=1)
            out.append(
                Segment(
                    key=day.isoformat(),
                    column=self.column,
                    grain=SegmentGrain.DAY,
                    lower=day,
                    upper=following,
                )
            )
            day = following
        return out

    def _monthly(self, start: date, end: date) -> list[Segment]:
        out = []
        year, month = start.year, start.month
        while (year, month) <= (end.year, end.month):
            following = (year + 1, 1) if month == 12 else (year, month + 1)
            out.append(
                Segment(
                    key=f"{year:04d}-{month:02d}",
                    column=self.column,
                    grain=SegmentGrain.MONTH,
                    lower=date(year, month, 1),
                    upper=date(*following, 1),
                )
            )
            year, month = following
        return out

    @staticmethod
    def _check_count(count: int) -> None:
        if count > MAX_SEGMENTS:
            raise ValidationError(
                f"that segmentation produces {count:,} segments",
                remedy=(
                    f"Use a coarser grain, or a narrower range. Above {MAX_SEGMENTS:,} the "
                    f"reads cost more than the source will tolerate and the findings cost "
                    f"more than anyone will read."
                ),
                context={"segments": count, "maximum": MAX_SEGMENTS},
            )


def _literal(value: Any) -> str:
    """Render a bound as a SQL literal.

    Segment bounds are dates and values Prama itself generated from a
    segmentation declaration, not free text from a request — but a value from a
    catalogue-derived distinct list is a customer's data, so strings are quoted
    and their quotes doubled.
    """
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, datetime | date):
        return f"'{value.isoformat()}'"
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


def _plain(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime | date) else value
