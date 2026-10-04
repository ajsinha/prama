"""Time.

Every timestamp Prama records is UTC, and every component that needs the time
asks a ``Clock`` rather than calling ``datetime.now()``. Two reasons, both
load-bearing:

* **Evidence must replay.** A control execution is reproducible only if the
  temporal context it saw is an input, not an ambient fact (docs/corpus/13 §6.3).
* **Tests must be deterministic.** ``FixedClock`` and ``ManualClock`` let a
  scheduler, a cadence policy or a lease expiry be tested without sleeping.

Business dates are deliberately *not* handled here. A business date is a
function of a calendar, a timezone and a cut-off, and those arrive with the
semantic layer in Wave 2; conflating them with wall-clock time is how
month-end bugs are born.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta


class Clock(ABC):
    """A source of the current time and of monotonic durations."""

    @abstractmethod
    def now(self) -> datetime:
        """Current instant as a timezone-aware UTC datetime."""

    @abstractmethod
    def monotonic(self) -> float:
        """Seconds from an arbitrary origin, never decreasing.

        Used for durations and timeouts. Never for timestamps: a monotonic
        reading is meaningless across processes and restarts.
        """

    def epoch_millis(self) -> int:
        return int(self.now().timestamp() * 1000)

    def isoformat(self) -> str:
        return self.now().isoformat().replace("+00:00", "Z")


class SystemClock(Clock):
    """The real clock. The only implementation used in production."""

    def now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        return time.monotonic()


class FixedClock(Clock):
    """A clock frozen at a chosen instant."""

    def __init__(self, instant: datetime) -> None:
        if instant.tzinfo is None:
            raise ValueError("FixedClock requires a timezone-aware instant")
        self._instant = instant.astimezone(UTC)
        self._mono = 0.0

    def now(self) -> datetime:
        return self._instant

    def monotonic(self) -> float:
        return self._mono


class ManualClock(Clock):
    """A clock advanced explicitly by the test that owns it."""

    def __init__(self, start: datetime | None = None) -> None:
        self._instant = (start or datetime(2026, 1, 1, tzinfo=UTC)).astimezone(UTC)
        self._mono = 0.0

    def now(self) -> datetime:
        return self._instant

    def monotonic(self) -> float:
        return self._mono

    def advance(self, seconds: float) -> None:
        """Move both wall-clock and monotonic readings forward together."""
        if seconds < 0:
            raise ValueError("a clock does not run backwards")
        self._instant = self._instant + timedelta(seconds=seconds)
        self._mono += seconds


def utc_now() -> datetime:
    """Convenience for code that genuinely has no injected clock.

    Prefer a ``Clock``. Every use of this function is a small obstacle to
    deterministic replay, so it is deliberately unattractive to reach for.
    """
    return datetime.now(UTC)
