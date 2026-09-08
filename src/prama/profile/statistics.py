"""Column statistics, accumulated from Arrow batches in bounded memory.

What a profile is *for* decides what it contains. These are not statistics for
their own sake: each one exists because a control or a monitor is derived from
it (docs/03 §5, docs/08 §3).

    null_rate           -> a completeness control, and its threshold
    distinct_ratio      -> whether this column is a key candidate
    min / max           -> a range control
    quantiles           -> a calibrated volume or value monitor's baseline
    top values          -> a dominant default, or a de-facto code list
    length distribution -> a format control, and truncation detection
    pattern classes     -> a semantic type, and a format control

A profile also records **how it was computed** — the sample plan, the rows
examined, the snapshot — because a statistic whose provenance is unknown cannot
be replayed, and a threshold derived from one cannot be defended.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import math
import re
from datetime import datetime
from typing import Any, ClassVar

from prama.profile.sketches import CountMin, HyperLogLog, TDigest, TopK

#: Quantiles worth keeping. The tails are the point: a monitor's baseline needs
#: p1 and p99 far more than it needs p25.
QUANTILES = (0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)

_DIGIT = re.compile(r"\d")
_UPPER = re.compile(r"[A-Z]")
_LOWER = re.compile(r"[a-z]")
_MASK_TRANSLATION = str.maketrans(
    {
        **{str(d): "9" for d in range(10)},
        **{chr(c): "A" for c in range(ord("A"), ord("Z") + 1)},
        **{chr(c): "a" for c in range(ord("a"), ord("z") + 1)},
    }
)

#: Beyond this, a mask is a fingerprint of one value rather than of a format.
MAX_MASK_LENGTH = 64


@dataclasses.dataclass(frozen=True, slots=True)
class NumericSummary:
    minimum: float | None = None
    maximum: float | None = None
    mean: float | None = None
    stddev: float | None = None
    quantiles: dict[str, float] = dataclasses.field(default_factory=dict)

    @property
    def spread(self) -> float | None:
        if self.minimum is None or self.maximum is None:
            return None
        return self.maximum - self.minimum


@dataclasses.dataclass(frozen=True, slots=True)
class StringSummary:
    min_length: int | None = None
    max_length: int | None = None
    mean_length: float | None = None
    blank_count: int = 0
    #: ``AAA-999`` style masks, most common first. A single dominant mask is a
    #: format control waiting to be written.
    top_masks: tuple[tuple[str, int], ...] = ()

    @property
    def is_fixed_length(self) -> bool:
        return (
            self.min_length is not None
            and self.min_length == self.max_length
            and self.min_length > 0
        )


@dataclasses.dataclass(frozen=True, slots=True)
class ColumnProfile:
    """Everything known about one column, and how it came to be known."""

    name: str
    type_name: str
    rows: int = 0
    nulls: int = 0
    distinct_estimate: int = 0
    distinct_error: float = 0.0
    top_values: tuple[tuple[Any, int], ...] = ()
    numeric: NumericSummary | None = None
    strings: StringSummary | None = None

    @property
    def null_rate(self) -> float:
        return 0.0 if self.rows == 0 else self.nulls / self.rows

    @property
    def distinct_ratio(self) -> float:
        return 0.0 if self.rows == 0 else min(1.0, self.distinct_estimate / self.rows)

    #: How many standard errors of slack to allow when judging uniqueness.
    #: Three, not one, and the asymmetry is deliberate. At one sigma a genuinely
    #: unique column is rejected roughly a third of the time, purely because the
    #: distinct sketch under-counted — and a missed key costs the grain
    #: declaration, which is the single most generative thing a business owner
    #: can state. A false candidate costs one verification query. The errors are
    #: not remotely equal, so the threshold should not be symmetric.
    KEY_CANDIDATE_SIGMA: ClassVar[float] = 3.0

    @property
    def is_key_candidate(self) -> bool:
        """Distinct in every row, and never null.

        Approximate, and honest about it: a candidate is a *proposal to verify
        on full data*, never a declared key. The verification is exact and
        cheap; the inference here only has to be generous enough not to miss one.
        """
        if self.rows == 0 or self.nulls:
            return False
        threshold = 1.0 - self.distinct_error * self.KEY_CANDIDATE_SIGMA
        return self.distinct_ratio >= threshold

    @property
    def is_constant(self) -> bool:
        return self.rows > 0 and self.distinct_estimate <= 1

    @property
    def dominant_value(self) -> tuple[Any, float] | None:
        """A value covering most of the column — usually an unfilled default."""
        if not self.top_values or self.rows == 0:
            return None
        value, count = self.top_values[0]
        share = count / self.rows
        return (value, share) if share >= 0.9 else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type_name,
            "rows": self.rows,
            "nulls": self.nulls,
            "null_rate": round(self.null_rate, 6),
            "distinct_estimate": self.distinct_estimate,
            "distinct_ratio": round(self.distinct_ratio, 6),
            "key_candidate": self.is_key_candidate,
            "constant": self.is_constant,
            "top_values": [[v, c] for v, c in self.top_values],
            "numeric": dataclasses.asdict(self.numeric) if self.numeric else None,
            "strings": dataclasses.asdict(self.strings) if self.strings else None,
        }


class ColumnAccumulator:
    """Consumes values in batches and yields a profile. Bounded memory."""

    def __init__(self, name: str, type_name: str, *, top_k: int = 20) -> None:
        self.name = name
        self.type_name = type_name
        self._rows = 0
        self._nulls = 0
        self._blank = 0
        self._distinct = HyperLogLog()
        self._top = TopK(top_k)
        self._frequency = CountMin()
        self._digest = TDigest()
        self._numeric_seen = 0
        self._sum = 0.0
        self._sum_squares = 0.0
        self._min_length: int | None = None
        self._max_length: int | None = None
        self._length_total = 0
        self._string_seen = 0
        self._masks = TopK(10)

    def add_values(self, values: list[Any]) -> None:
        for value in values:
            self._rows += 1
            if value is None or (isinstance(value, float) and math.isnan(value)):
                self._nulls += 1
                continue
            self._distinct.add(value)
            self._top.add(value)
            self._frequency.add(value)
            if isinstance(value, bool):
                continue  # a bool is not a number here; averaging one is nonsense
            if isinstance(value, (int, float)):
                self._add_numeric(float(value))
            elif isinstance(value, str):
                self._add_string(value)
            elif isinstance(value, datetime):
                self._add_numeric(value.timestamp())

    def _add_numeric(self, value: float) -> None:
        if not math.isfinite(value):
            return
        self._numeric_seen += 1
        self._sum += value
        self._sum_squares += value * value
        self._digest.add(value)

    def _add_string(self, value: str) -> None:
        self._string_seen += 1
        length = len(value)
        self._length_total += length
        self._min_length = length if self._min_length is None else min(self._min_length, length)
        self._max_length = length if self._max_length is None else max(self._max_length, length)
        if not value.strip():
            self._blank += 1
        if 0 < length <= MAX_MASK_LENGTH:
            self._masks.add(value.translate(_MASK_TRANSLATION))

    def profile(self) -> ColumnProfile:
        return ColumnProfile(
            name=self.name,
            type_name=self.type_name,
            rows=self._rows,
            nulls=self._nulls,
            distinct_estimate=self._distinct.estimate() if self._rows > self._nulls else 0,
            distinct_error=self._distinct.standard_error,
            top_values=tuple(self._top.most_common()),
            numeric=self._numeric_summary(),
            strings=self._string_summary(),
        )

    def _numeric_summary(self) -> NumericSummary | None:
        if self._numeric_seen == 0:
            return None
        mean = self._sum / self._numeric_seen
        variance = max(0.0, self._sum_squares / self._numeric_seen - mean * mean)
        return NumericSummary(
            minimum=self._digest.minimum,
            maximum=self._digest.maximum,
            mean=mean,
            stddev=math.sqrt(variance),
            quantiles={
                f"p{q * 100:g}": value
                for q in QUANTILES
                if (value := self._digest.quantile(q)) is not None
            },
        )

    def _string_summary(self) -> StringSummary | None:
        if self._string_seen == 0:
            return None
        return StringSummary(
            min_length=self._min_length,
            max_length=self._max_length,
            mean_length=self._length_total / self._string_seen,
            blank_count=self._blank,
            top_masks=tuple(self._masks.most_common(5)),
        )

    def merge(self, other: ColumnAccumulator) -> ColumnAccumulator:
        """Combine two partial accumulators over the same column.

        What lets a profile be computed by parallel workers over partitions and
        then rolled up, without re-reading anything.
        """
        merged = ColumnAccumulator(self.name, self.type_name)
        merged._rows = self._rows + other._rows
        merged._nulls = self._nulls + other._nulls
        merged._blank = self._blank + other._blank
        merged._distinct = self._distinct.merge(other._distinct)
        merged._top = self._top.merge(other._top)
        merged._frequency = self._frequency.merge(other._frequency)
        merged._digest = self._digest.merge(other._digest)
        merged._numeric_seen = self._numeric_seen + other._numeric_seen
        merged._sum = self._sum + other._sum
        merged._sum_squares = self._sum_squares + other._sum_squares
        merged._string_seen = self._string_seen + other._string_seen
        merged._length_total = self._length_total + other._length_total
        merged._masks = self._masks.merge(other._masks)
        lengths = [v for v in (self._min_length, other._min_length) if v is not None]
        merged._min_length = min(lengths) if lengths else None
        lengths = [v for v in (self._max_length, other._max_length) if v is not None]
        merged._max_length = max(lengths) if lengths else None
        return merged


def character_classes(value: str) -> set[str]:
    """Which character families a string uses. Input to semantic typing."""
    classes = set()
    if _DIGIT.search(value):
        classes.add("digit")
    if _UPPER.search(value):
        classes.add("upper")
    if _LOWER.search(value):
        classes.add("lower")
    if any(not c.isalnum() for c in value):
        classes.add("punctuation")
    if any(ord(c) > 127 for c in value):
        classes.add("non_ascii")
    return classes
