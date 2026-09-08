"""Profiling by segment, and re-examining only what moved.

Two capabilities that are really one mechanism. Because every accumulator
merges exactly, a dataset's profile is the fold of its segments' profiles — so
segments can be profiled independently, in parallel, at different times, and
combined into precisely the result a single scan would have produced.

That identity is what makes the rest possible:

* **Segmented findings.** A fault confined to one day or one entity survives in
  its own segment instead of being averaged into invisibility by the healthy
  ones around it.
* **Incremental re-examination.** A settled segment never needs reading again,
  so a nightly refresh costs the part that changed rather than the whole table.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import asyncio
import dataclasses
from typing import Any

from prama.connect.spi import Connector, ObjectSchema, SamplePlan
from prama.core.clock import Clock, SystemClock
from prama.core.errors import ValidationError
from prama.core.log import get_logger
from prama.profile.incremental import IncrementalPlan, IncrementalPlanner
from prama.profile.profiler import DatasetProfile, ProfileProvenance, Profiler
from prama.profile.segments import Segment
from prama.profile.statistics import ColumnAccumulator

_log = get_logger(__name__)


@dataclasses.dataclass(slots=True)
class SegmentAccumulation:
    """One segment's accumulated observations, kept so they can be folded.

    Named for what it holds rather than for the segment, because
    ``SegmentState`` already means something else here — why a segment is being
    read this time — and two ideas under one name in the same package is a
    confusion that costs more than the longer word.
    """

    segment: Segment
    accumulators: dict[str, ColumnAccumulator]
    provenance: ProfileProvenance
    schema: ObjectSchema

    def profile(self, path: tuple[str, ...]) -> DatasetProfile:
        return Profiler.assemble(path, self.accumulators, self.provenance, self.schema)


class SegmentedProfile:
    """A dataset's profile, held as its parts.

    Kept as parts rather than folded eagerly because the parts are the useful
    thing: the fold answers "how is this dataset", the parts answer "which day
    broke", and only the second is actionable.
    """

    def __init__(self, path: tuple[str, ...]) -> None:
        self.path = path
        self._segments: dict[str, SegmentAccumulation] = {}

    def __len__(self) -> int:
        return len(self._segments)

    @property
    def segment_keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._segments))

    def put(self, state: SegmentAccumulation) -> None:
        self._segments[state.segment.key] = state

    def state(self, key: str) -> SegmentAccumulation | None:
        return self._segments.get(key)

    def profile_of(self, key: str) -> DatasetProfile | None:
        state = self._segments.get(key)
        return state.profile(self.path) if state else None

    def folded(self) -> DatasetProfile | None:
        """The whole dataset, assembled from its segments.

        Exact: this is the profile a single scan would have produced, which is
        the property the whole design rests on.
        """
        if not self._segments:
            return None
        ordered = [self._segments[key] for key in sorted(self._segments)]
        merged: dict[str, ColumnAccumulator] = {}
        for state in ordered:
            for name, accumulator in state.accumulators.items():
                merged[name] = (
                    accumulator if name not in merged else merged[name].merge(accumulator)
                )
        newest = max(ordered, key=lambda s: s.provenance.computed_at)
        oldest = min(ordered, key=lambda s: s.provenance.computed_at)
        provenance = ProfileProvenance(
            # As current as its oldest part, not its newest. A folded profile
            # stamped with the newest segment's time would make a segment that
            # has not been looked at for a month appear fresh.
            computed_at=oldest.provenance.computed_at,
            snapshot=newest.provenance.snapshot,
            plan=dataclasses.replace(newest.provenance.plan, predicate=""),
            rows_examined=sum(s.provenance.rows_examined for s in ordered),
            duration_seconds=sum(s.provenance.duration_seconds for s in ordered),
            truncated=any(s.provenance.truncated for s in ordered),
        )
        return Profiler.assemble(self.path, merged, provenance, newest.schema)

    def to_dict(self) -> dict[str, Any]:
        folded = self.folded()
        return {
            "object": ".".join(self.path),
            "segments": len(self._segments),
            "segment_keys": list(self.segment_keys),
            "rows": folded.provenance.rows_examined if folded else 0,
            "oldest_segment_profiled_at": (
                folded.provenance.computed_at.isoformat() if folded else None
            ),
        }


class SegmentedProfiler:
    """Profiles a dataset segment by segment, reading only what it must."""

    def __init__(
        self,
        profiler: Profiler | None = None,
        *,
        planner: IncrementalPlanner | None = None,
        clock: Clock | None = None,
        concurrency: int = 4,
    ) -> None:
        self._profiler = profiler or Profiler()
        self._planner = planner or IncrementalPlanner()
        self._clock = clock or SystemClock()
        #: Segments are read concurrently, but not unboundedly: the point of
        #: reading less is to be gentler on the source, and firing four hundred
        #: partition queries at once would undo that entirely.
        self._concurrency = max(1, concurrency)

    @property
    def planner(self) -> IncrementalPlanner:
        return self._planner

    def plan(
        self,
        dataset: str,
        segments: list[Segment],
        *,
        snapshot: Any = None,
    ) -> IncrementalPlan:
        return self._planner.plan(dataset, segments, snapshot=snapshot)

    async def refresh(
        self,
        connector: Connector,
        path: tuple[str, ...],
        segments: list[Segment],
        *,
        dataset: str | None = None,
        plan: SamplePlan | None = None,
        into: SegmentedProfile | None = None,
        quote: Any = None,
    ) -> tuple[SegmentedProfile, IncrementalPlan]:
        """Bring a segmented profile up to date, reading only what moved.

        Returns the profile and the plan that produced it, because "what did
        this run actually look at" is not a detail — a refresh that skipped
        nine tenths of a table is a different claim from one that read it all,
        and both are legitimate.
        """
        if not segments:
            raise ValidationError(
                "a segmented profile needs at least one segment",
                remedy=(
                    "Declare the segmentation — usually by business date — or profile "
                    "the dataset whole."
                ),
                context={"object": ".".join(path)},
            )
        connector.require_predicate_support(SamplePlan(predicate="x"))
        name = dataset or ".".join(path)
        quote = quote or _default_quote
        base = plan or SamplePlan()

        snapshot = await connector.snapshot(path)
        decided = self._planner.plan(name, segments, snapshot=snapshot)
        result = SegmentedProfile(path) if into is None else into

        semaphore = asyncio.Semaphore(self._concurrency)

        async def read_one(segment: Segment) -> SegmentAccumulation:
            async with semaphore:
                segment_plan = dataclasses.replace(base, predicate=segment.predicate(quote))
                accumulators, provenance, schema = await self._profiler.accumulate(
                    connector, path, plan=segment_plan, capture_snapshot=False
                )
                return SegmentAccumulation(
                    segment=segment,
                    accumulators=accumulators,
                    provenance=dataclasses.replace(provenance, snapshot=snapshot),
                    schema=schema,
                )

        to_read = decided.to_read
        if to_read:
            for state in await asyncio.gather(*(read_one(s) for s in to_read)):
                result.put(state)
                self._planner.ledger.record(
                    name,
                    state.segment,
                    snapshot=snapshot,
                    rows=state.provenance.rows_examined,
                    at=self._clock.now(),
                )
        _log.info(
            "refreshed %s: read %d of %d segments (%.0f%% reused)",
            name,
            len(to_read),
            len(decided.decisions),
            decided.saved_fraction * 100,
        )
        return result, decided

    def compare(self, profile: SegmentedProfile, column: str) -> list[tuple[str, float | None]]:
        """A column's null rate across segments, oldest key first.

        The view a table-level number cannot give: 2% overall is reassuring
        until it turns out to be 0% everywhere and 100% since Tuesday.
        """
        out: list[tuple[str, float | None]] = []
        for key in profile.segment_keys:
            segment_profile = profile.profile_of(key)
            found = segment_profile.column(column) if segment_profile else None
            out.append((key, found.null_rate if found else None))
        return out

    @staticmethod
    def divergent(
        rates: list[tuple[str, float | None]], *, tolerance: float = 0.2
    ) -> list[tuple[str, float]]:
        """Segments whose rate departs from the others by more than *tolerance*.

        Compared against the median rather than the mean: one catastrophic
        segment drags a mean far enough to make itself look ordinary, which is
        exactly the segment worth finding.
        """
        present = [(key, rate) for key, rate in rates if rate is not None]
        if len(present) < 3:
            # Two segments cannot tell which of them is the odd one out.
            return []
        ordered = sorted(rate for _, rate in present)
        middle = len(ordered) // 2
        median = (
            ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2
        )
        return [(key, rate) for key, rate in present if abs(rate - median) > tolerance]


def _default_quote(identifier: str) -> str:
    escaped = identifier.replace('"', '""')
    return f'"{escaped}"'
