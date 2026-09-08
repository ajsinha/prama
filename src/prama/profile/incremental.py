"""Re-examining a dataset without re-reading it.

Prama is supposed to keep looking — to re-examine what it has been pointed at
and refresh its findings on a schedule. Done naively that means reading every
table every night, which for a real estate is somewhere between expensive and
impossible, and it is the reason most tools quietly profile once and then show
a stale number for a year.

The way out is that a segment, once profiled, does not change. Yesterday's
partition of a ledger is yesterday's partition forever. So the nightly job reads
only what is new or has moved, and folds it into what is already known — the
merge is exact, so the result is the profile that a full scan would have
produced, at the cost of the part that changed.

What makes this safe rather than merely fast is knowing when a segment *has*
moved, and being honest when that cannot be known. A segment is re-read when:

* it has never been profiled;
* the source's snapshot marker differs from the one recorded against it;
* it is inside the mutable window — recent enough that late-arriving corrections
  are still plausible;
* or the source offers no exact snapshot at all, in which case nothing can be
  assumed and the honest answer is to read it again.

That last case matters. A tool that assumes immutability it cannot verify will
be wrong silently, and the failure surfaces months later as a number nobody can
reproduce.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
from datetime import date, datetime, timedelta
from typing import Any

from prama.connect.spi import Snapshot
from prama.core.clock import Clock, SystemClock
from prama.profile.segments import Segment

#: How far back corrections are still expected to arrive. Everything inside the
#: window is re-read every time; everything outside it is trusted once profiled.
#: Three days rather than one, because a Friday's late correction lands on
#: Monday and a window of one day would miss it every weekend.
DEFAULT_MUTABLE_DAYS = 3


class SegmentState(enum.Enum):
    """Why a segment is or is not being read this time."""

    NEW = "new"
    CHANGED = "changed"
    MUTABLE = "mutable"
    UNVERIFIABLE = "unverifiable"
    SETTLED = "settled"

    @property
    def needs_read(self) -> bool:
        return self is not SegmentState.SETTLED

    @property
    def reason(self) -> str:
        return {
            SegmentState.NEW: "never profiled",
            SegmentState.CHANGED: "the source's snapshot has moved since it was profiled",
            SegmentState.MUTABLE: "recent enough that late corrections are still plausible",
            SegmentState.UNVERIFIABLE: (
                "this source offers no exact snapshot, so no segment can be assumed unchanged"
            ),
            SegmentState.SETTLED: "already profiled, and the source says it has not moved",
        }[self]


@dataclasses.dataclass(frozen=True, slots=True)
class SegmentRecord:
    """What is known about one segment from previous runs."""

    segment_key: str
    snapshot_identifier: str
    snapshot_exact: bool
    rows: int
    profiled_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment": self.segment_key,
            "snapshot": self.snapshot_identifier,
            "exact": self.snapshot_exact,
            "rows": self.rows,
            "profiled_at": self.profiled_at.isoformat(),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class SegmentDecision:
    """One segment, and whether this run will read it."""

    segment: Segment
    state: SegmentState
    known: SegmentRecord | None = None

    @property
    def needs_read(self) -> bool:
        return self.state.needs_read

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment": self.segment.key,
            "state": self.state.value,
            "reason": self.state.reason,
            "reading": self.needs_read,
            "previously": self.known.to_dict() if self.known else None,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class IncrementalPlan:
    """What a re-examination will actually do, and what it will skip."""

    decisions: tuple[SegmentDecision, ...]

    @property
    def to_read(self) -> tuple[Segment, ...]:
        return tuple(d.segment for d in self.decisions if d.needs_read)

    @property
    def reused(self) -> tuple[Segment, ...]:
        return tuple(d.segment for d in self.decisions if not d.needs_read)

    @property
    def saved_fraction(self) -> float:
        if not self.decisions:
            return 0.0
        return len(self.reused) / len(self.decisions)

    def render(self) -> str:
        """What this run costs, in a sentence, before it runs."""
        total = len(self.decisions)
        reading = len(self.to_read)
        if total == 0:
            return "Nothing to examine: the segmentation produced no segments."
        if reading == total:
            return f"Reading all {total} segments — {self.decisions[0].state.reason}."
        return (
            f"Reading {reading} of {total} segments; the other {total - reading} are "
            f"already profiled and the source says they have not moved."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "segments": len(self.decisions),
            "reading": len(self.to_read),
            "reusing": len(self.reused),
            "saved_fraction": round(self.saved_fraction, 4),
            "summary": self.render(),
            "decisions": [d.to_dict() for d in self.decisions],
        }


class SegmentLedger:
    """What has been profiled, so the next run knows what to skip.

    In memory here. The durable version lives in the metric store; this keeps
    the decision logic testable and independent of where the record is kept.
    """

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], SegmentRecord] = {}

    def record(
        self,
        dataset: str,
        segment: Segment,
        *,
        snapshot: Snapshot | None,
        rows: int,
        at: datetime,
    ) -> None:
        self._records[dataset, segment.key] = SegmentRecord(
            segment_key=segment.key,
            snapshot_identifier=snapshot.identifier if snapshot else "",
            snapshot_exact=bool(snapshot and snapshot.exact),
            rows=rows,
            profiled_at=at,
        )

    def known(self, dataset: str, segment: Segment) -> SegmentRecord | None:
        return self._records.get((dataset, segment.key))

    def forget(self, dataset: str) -> None:
        """Drop everything known about a dataset, forcing a full re-read.

        Needed after a declaration changes in a way that invalidates earlier
        profiles — a column reinterpreted, a segmentation redrawn.
        """
        for key in [k for k in self._records if k[0] == dataset]:
            del self._records[key]


class IncrementalPlanner:
    """Decides which segments this run must actually read."""

    def __init__(
        self,
        ledger: SegmentLedger | None = None,
        *,
        mutable_days: int = DEFAULT_MUTABLE_DAYS,
        clock: Clock | None = None,
    ) -> None:
        self._ledger = ledger or SegmentLedger()
        self._mutable_days = mutable_days
        self._clock = clock or SystemClock()

    @property
    def ledger(self) -> SegmentLedger:
        return self._ledger

    def plan(
        self,
        dataset: str,
        segments: list[Segment],
        *,
        snapshot: Snapshot | None = None,
    ) -> IncrementalPlan:
        """Decide, segment by segment, what this run will read.

        *snapshot* is the source's current marker for the whole object. When it
        is not exact, nothing can be assumed and every segment is re-read —
        stated as a reason rather than applied silently, because "we read
        everything again" and "we trusted what we had" are very different
        answers to give an auditor.
        """
        today = self._clock.now().date()
        cutoff = today - timedelta(days=self._mutable_days)
        return IncrementalPlan(
            decisions=tuple(
                SegmentDecision(
                    segment=segment,
                    state=self._state(dataset, segment, snapshot, cutoff),
                    known=self._ledger.known(dataset, segment),
                )
                for segment in segments
            )
        )

    def _state(
        self,
        dataset: str,
        segment: Segment,
        snapshot: Snapshot | None,
        cutoff: date,
    ) -> SegmentState:
        known = self._ledger.known(dataset, segment)
        if known is None:
            return SegmentState.NEW
        if snapshot is None or not snapshot.exact:
            # Assuming immutability that cannot be verified is how a number
            # nobody can reproduce appears six months later.
            return SegmentState.UNVERIFIABLE
        if not known.snapshot_exact or known.snapshot_identifier != snapshot.identifier:
            return SegmentState.CHANGED
        if self._is_mutable(segment, cutoff):
            return SegmentState.MUTABLE
        return SegmentState.SETTLED

    @staticmethod
    def _is_mutable(segment: Segment, cutoff: date) -> bool:
        """Whether late corrections are still plausible for this segment.

        Only temporal segments settle. A categorical one — by entity, by
        product — has no age, so nothing about it can be called old enough to
        stop checking.
        """
        if not segment.grain.is_temporal:
            return True
        upper = segment.upper
        if isinstance(upper, datetime):
            upper = upper.date()
        if not isinstance(upper, date):
            return True
        return upper > cutoff
