"""Bounded-memory sketches.

Profiling a 10^10-row table cannot hold a set of its distinct values or a sorted
copy of its numbers, so the statistics that matter are computed approximately in
bounded space. Each sketch here states its error bound, because an approximation
whose error nobody knows is not a measurement — and a monitor built on one
cannot be calibrated.

All four are mergeable: partial sketches from parallel workers combine into the
sketch of the whole, which is what lets a profile be computed in parallel and a
metric history be rolled up across partitions without re-reading anything.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import hashlib
import math
from collections.abc import Iterable
from typing import Any

#: 2^14 registers: ~1.6% standard error for 16 KB, which is the right trade for
#: a distinct count used to decide whether a column is a key candidate.
HLL_PRECISION = 14


def _hash64(value: Any) -> int:
    """A stable 64-bit hash.

    ``hash()`` is salted per process, so two workers would disagree and a
    merged sketch would be silently wrong. Stability across processes and
    across runs is the whole requirement.
    """
    encoded = repr(value).encode("utf-8") if not isinstance(value, bytes) else value
    return int.from_bytes(hashlib.blake2b(encoded, digest_size=8).digest(), "big")


class HyperLogLog:
    """Approximate distinct count in fixed space.

    Standard error is ``1.04 / sqrt(2^precision)`` — about 1.6% at the default.
    Exact for small cardinalities, where linear counting takes over and the
    error would otherwise be worst exactly where it matters most.
    """

    __slots__ = ("_m", "_precision", "_registers")

    def __init__(self, precision: int = HLL_PRECISION) -> None:
        if not 4 <= precision <= 18:
            raise ValueError("HLL precision must be between 4 and 18")
        self._precision = precision
        self._m = 1 << precision
        self._registers = bytearray(self._m)

    def add(self, value: Any) -> None:
        if value is None:
            return  # nulls are counted separately; they are not a distinct value
        digest = _hash64(value)
        index = digest >> (64 - self._precision)
        remaining = (digest << self._precision) & ((1 << 64) - 1)
        rank = 1 if remaining == 0 else (64 - remaining.bit_length()) + 1
        if rank > self._registers[index]:
            self._registers[index] = min(rank, 255)

    def update(self, values: Iterable[Any]) -> None:
        for value in values:
            self.add(value)

    def merge(self, other: HyperLogLog) -> HyperLogLog:
        if other._precision != self._precision:
            raise ValueError("cannot merge HyperLogLogs of different precision")
        merged = HyperLogLog(self._precision)
        merged._registers = bytearray(
            max(a, b) for a, b in zip(self._registers, other._registers, strict=True)
        )
        return merged

    def estimate(self) -> int:
        raw = self._alpha() * self._m * self._m / sum(2.0**-r for r in self._registers)
        zeros = self._registers.count(0)
        if raw <= 2.5 * self._m and zeros:
            # Linear counting: far more accurate for small cardinalities, which
            # is where a key-candidate decision is actually made.
            return round(self._m * math.log(self._m / zeros))
        return round(raw)

    @property
    def standard_error(self) -> float:
        return 1.04 / math.sqrt(self._m)

    def _alpha(self) -> float:
        if self._m == 16:
            return 0.673
        if self._m == 32:
            return 0.697
        if self._m == 64:
            return 0.709
        return 0.7213 / (1 + 1.079 / self._m)

    def __len__(self) -> int:
        return self.estimate()


@dataclasses.dataclass(slots=True)
class _Centroid:
    mean: float
    count: int


class TDigest:
    """Approximate quantiles, accurate at the tails.

    Chosen over an equi-width histogram because the interesting quantiles in
    data quality are extreme: p99 latency, p1 of a value distribution, the tail
    where the outliers live. A structure that is accurate in the middle and
    vague at the edges is precisely wrong for this job.
    """

    __slots__ = ("_buffer", "_centroids", "_compression", "_count", "_max", "_min")

    def __init__(self, compression: float = 100.0) -> None:
        self._compression = compression
        self._centroids: list[_Centroid] = []
        self._buffer: list[float] = []
        self._count = 0
        self._min = math.inf
        self._max = -math.inf

    def add(self, value: float, weight: int = 1) -> None:
        if value is None or (isinstance(value, float) and not math.isfinite(value)):
            return
        value = float(value)
        self._buffer.append(value)
        self._count += weight
        self._min = min(self._min, value)
        self._max = max(self._max, value)
        if len(self._buffer) >= 1000:
            self._flush()

    def update(self, values: Iterable[float]) -> None:
        for value in values:
            self.add(value)

    def _flush(self) -> None:
        if not self._buffer:
            return
        points = sorted(
            [(c.mean, c.count) for c in self._centroids] + [(v, 1) for v in self._buffer]
        )
        self._buffer.clear()
        self._centroids = []
        total = sum(count for _, count in points)
        if total == 0:
            return
        limit = max(1, int(total / self._compression))
        current_mean, current_count = points[0]
        for mean, count in points[1:]:
            if current_count + count <= limit:
                current_mean = (current_mean * current_count + mean * count) / (
                    current_count + count
                )
                current_count += count
            else:
                self._centroids.append(_Centroid(current_mean, current_count))
                current_mean, current_count = mean, count
        self._centroids.append(_Centroid(current_mean, current_count))

    def quantile(self, q: float) -> float | None:
        """The value at quantile *q*, or None if nothing has been seen."""
        if not 0.0 <= q <= 1.0:
            raise ValueError("quantile must be between 0 and 1")
        self._flush()
        if self._count == 0:
            return None
        if q <= 0:
            return self._min
        if q >= 1:
            return self._max
        target = q * self._count
        seen = 0.0
        for centroid in self._centroids:
            if seen + centroid.count >= target:
                return centroid.mean
            seen += centroid.count
        return self._max

    def merge(self, other: TDigest) -> TDigest:
        merged = TDigest(self._compression)
        self._flush()
        other._flush()
        merged._centroids = [_Centroid(c.mean, c.count) for c in self._centroids + other._centroids]
        merged._count = self._count + other._count
        merged._min = min(self._min, other._min)
        merged._max = max(self._max, other._max)
        merged._flush()
        return merged

    @property
    def count(self) -> int:
        return self._count

    @property
    def minimum(self) -> float | None:
        return None if self._count == 0 else self._min

    @property
    def maximum(self) -> float | None:
        return None if self._count == 0 else self._max


class CountMin:
    """Approximate frequency of a value, never underestimating.

    One-sided error matters: a top-K list that might *miss* a frequent value is
    useless for finding a dominant default, while one that might slightly
    over-count a rare one is harmless.
    """

    __slots__ = ("_depth", "_table", "_total", "_width")

    def __init__(self, width: int = 2048, depth: int = 5) -> None:
        self._width = width
        self._depth = depth
        self._table = [[0] * width for _ in range(depth)]
        self._total = 0

    def add(self, value: Any, count: int = 1) -> None:
        if value is None:
            return
        digest = _hash64(value)
        for row in range(self._depth):
            column = (digest + row * 0x9E3779B97F4A7C15) % self._width
            self._table[row][column] += count
        self._total += count

    def estimate(self, value: Any) -> int:
        if value is None:
            return 0
        digest = _hash64(value)
        return min(
            self._table[row][(digest + row * 0x9E3779B97F4A7C15) % self._width]
            for row in range(self._depth)
        )

    def merge(self, other: CountMin) -> CountMin:
        if (other._width, other._depth) != (self._width, self._depth):
            raise ValueError("cannot merge CountMin sketches of different shape")
        merged = CountMin(self._width, self._depth)
        merged._table = [
            [a + b for a, b in zip(left, right, strict=True)]
            for left, right in zip(self._table, other._table, strict=True)
        ]
        merged._total = self._total + other._total
        return merged

    @property
    def total(self) -> int:
        return self._total

    @property
    def error_bound(self) -> float:
        """Absolute over-count bound, with probability 1 - 2^-depth."""
        return math.e * self._total / self._width


class TopK:
    """The most frequent values, exactly, for a bounded K.

    Exact rather than sketched because K is small and the answer is read by a
    person: "97% of this column is the single value 'N'" is a finding, and a
    finding that might be wrong is worse than no finding.
    """

    __slots__ = ("_capacity", "_counts", "_k")

    def __init__(self, k: int = 20, capacity_multiple: int = 50) -> None:
        self._k = k
        self._capacity = k * capacity_multiple
        self._counts: dict[Any, int] = {}

    def add(self, value: Any, count: int = 1) -> None:
        if value is None:
            return
        key = value if isinstance(value, (str, int, float, bool, bytes)) else repr(value)
        self._counts[key] = self._counts.get(key, 0) + count
        if len(self._counts) > self._capacity:
            self._evict()

    def update(self, values: Iterable[Any]) -> None:
        for value in values:
            self.add(value)

    def _evict(self) -> None:
        """Drop the rarest half once the map grows past its ceiling.

        A high-cardinality column would otherwise turn a bounded sketch into an
        unbounded dictionary — the exact leak this module exists to prevent.
        """
        keep = sorted(self._counts.items(), key=lambda kv: -kv[1])[: self._capacity // 2]
        self._counts = dict(keep)

    def most_common(self, k: int | None = None) -> list[tuple[Any, int]]:
        return sorted(self._counts.items(), key=lambda kv: (-kv[1], repr(kv[0])))[: k or self._k]

    def merge(self, other: TopK) -> TopK:
        merged = TopK(self._k)
        for source in (self._counts, other._counts):
            for value, count in source.items():
                merged.add(value, count)
        return merged

    @property
    def tracked(self) -> int:
        return len(self._counts)
