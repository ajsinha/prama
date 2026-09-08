"""Profiling a source object end to end.

Reads through a connector, accumulates bounded-memory statistics, and returns a
profile that records not only what was found but **how**: the sample plan, the
rows examined, the snapshot, and the time. A statistic without that provenance
cannot be replayed, and a threshold derived from one cannot be defended.

This is the machinery behind the Wave 3 release gate — connect, profile, and
have proposable controls in under thirty minutes, with nobody declaring anything
first (`NFR-OPS-002`). Everything here works at declaration stage zero.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import Any

from prama.connect.spi import (
    Connector,
    ObjectSchema,
    SamplePlan,
    SamplingStrategy,
    Snapshot,
)
from prama.core.clock import Clock, SystemClock
from prama.core.log import get_logger
from prama.profile.statistics import ColumnAccumulator, ColumnProfile

_log = get_logger(__name__)


@dataclasses.dataclass(frozen=True, slots=True)
class ProfileProvenance:
    """How a profile was produced. Stamped on every finding it generates."""

    computed_at: datetime
    snapshot: Snapshot | None
    plan: SamplePlan
    rows_examined: int
    duration_seconds: float
    truncated: bool = False

    @property
    def is_complete(self) -> bool:
        """Whether the profile saw everything, and so may state exact rates."""
        return self.plan.is_complete and not self.truncated

    @property
    def confidence_note(self) -> str:
        """What may honestly be said about a rate measured here.

        Rendered next to every derived threshold, so nobody mistakes a sampled
        estimate for a measured fact.
        """
        if self.is_complete:
            return f"measured over all {self.rows_examined:,} rows"
        if not self.plan.strategy.is_representative:
            return (
                f"read the first {self.rows_examined:,} rows only — indicative of shape, "
                f"not of any rate"
            )
        return f"estimated from {self.rows_examined:,} sampled rows ({self.plan.describe()})"

    def to_dict(self) -> dict[str, Any]:
        return {
            "computed_at": self.computed_at,
            "snapshot": self.snapshot.to_dict() if self.snapshot else None,
            "sampling": self.plan.describe(),
            "representative": self.plan.strategy.is_representative,
            "rows_examined": self.rows_examined,
            "complete": self.is_complete,
            "duration_seconds": round(self.duration_seconds, 3),
            "confidence": self.confidence_note,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class DatasetProfile:
    """A profiled object: its columns, and the provenance of the whole."""

    path: tuple[str, ...]
    columns: tuple[ColumnProfile, ...]
    provenance: ProfileProvenance
    schema: ObjectSchema | None = None

    @property
    def qualified_name(self) -> str:
        return ".".join(self.path)

    @property
    def rows(self) -> int:
        return self.provenance.rows_examined

    def column(self, name: str) -> ColumnProfile | None:
        return next((c for c in self.columns if c.name == name), None)

    @property
    def key_candidates(self) -> tuple[str, ...]:
        """Columns that could be the grain. Proposals, never conclusions."""
        return tuple(c.name for c in self.columns if c.is_key_candidate)

    @property
    def constant_columns(self) -> tuple[str, ...]:
        return tuple(c.name for c in self.columns if c.is_constant)

    @property
    def empty_columns(self) -> tuple[str, ...]:
        """Wholly null. Usually a field the source stopped populating."""
        return tuple(c.name for c in self.columns if c.rows > 0 and c.nulls == c.rows)

    def summary(self) -> str:
        """One line a person can read, which is what a first profile is for."""
        return (
            f"{self.qualified_name}: {self.rows:,} rows, {len(self.columns)} columns, "
            f"{len(self.key_candidates)} key candidate(s), "
            f"{len(self.empty_columns)} empty column(s) — {self.provenance.confidence_note}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": list(self.path),
            "rows": self.rows,
            "columns": [c.to_dict() for c in self.columns],
            "key_candidates": list(self.key_candidates),
            "constant_columns": list(self.constant_columns),
            "empty_columns": list(self.empty_columns),
            "provenance": self.provenance.to_dict(),
        }


class Profiler:
    """Profiles objects through a connector, within a budget."""

    def __init__(
        self,
        *,
        clock: Clock | None = None,
        max_rows: int | None = None,
        top_k: int = 20,
    ) -> None:
        self._clock = clock or SystemClock()
        self._max_rows = max_rows
        self._top_k = top_k

    async def profile(
        self,
        connector: Connector,
        path: tuple[str, ...],
        *,
        plan: SamplePlan | None = None,
        capture_snapshot: bool = True,
    ) -> DatasetProfile:
        """Read an object once and accumulate everything in a single pass."""
        accumulators, provenance, schema = await self.accumulate(
            connector, path, plan=plan, capture_snapshot=capture_snapshot
        )
        return self.assemble(path, accumulators, provenance, schema)

    async def accumulate(
        self,
        connector: Connector,
        path: tuple[str, ...],
        *,
        plan: SamplePlan | None = None,
        capture_snapshot: bool = True,
    ) -> tuple[dict[str, ColumnAccumulator], ProfileProvenance, ObjectSchema]:
        """The reading pass, with the sketches still intact.

        Separate from :meth:`profile` because a ``ColumnProfile`` cannot be
        turned back into an accumulator — a HyperLogLog is not recoverable from
        the distinct *estimate* it produced. Anything that folds segments
        together has to hold the accumulators, so this is where segmented and
        incremental profiling attach.
        """
        started = self._clock.monotonic()
        plan = plan or SamplePlan()
        snapshot = await connector.snapshot(path) if capture_snapshot else None
        schema = await connector.describe(path)

        accumulators: dict[str, ColumnAccumulator] = {}
        rows = 0
        truncated = False

        async for batch in connector.read(path, plan=plan):
            columns = batch.schema.names
            for index, name in enumerate(columns):
                accumulator = accumulators.get(name)
                if accumulator is None:
                    declared = schema.column(name)
                    accumulator = ColumnAccumulator(
                        name,
                        declared.type_name if declared else str(batch.schema.field(index).type),
                        top_k=self._top_k,
                    )
                    accumulators[name] = accumulator
                accumulator.add_values(batch.column(index).to_pylist())
            rows += batch.num_rows
            if self._max_rows is not None and rows >= self._max_rows:
                # Stopping is honest and recorded; silently reading 40 GB
                # because nobody set a limit is not.
                truncated = True
                _log.info(
                    "profiling %s stopped at the %d-row budget", ".".join(path), self._max_rows
                )
                break

        provenance = ProfileProvenance(
            computed_at=self._clock.now(),
            snapshot=snapshot,
            plan=plan,
            rows_examined=rows,
            duration_seconds=self._clock.monotonic() - started,
            truncated=truncated,
        )
        return accumulators, provenance, schema

    @staticmethod
    def assemble(
        path: tuple[str, ...],
        accumulators: dict[str, ColumnAccumulator],
        provenance: ProfileProvenance,
        schema: ObjectSchema,
    ) -> DatasetProfile:
        """Turn accumulated state into a profile, in the schema's column order."""
        ordered = [
            accumulators[name].profile() for name in schema.column_names if name in accumulators
        ]
        ordered += [
            accumulator.profile()
            for name, accumulator in accumulators.items()
            if name not in schema.column_names
        ]
        return DatasetProfile(
            path=path, columns=tuple(ordered), provenance=provenance, schema=schema
        )

    async def profile_source(
        self,
        connector: Connector,
        *,
        plan: SamplePlan | None = None,
        limit: int | None = None,
    ) -> list[DatasetProfile]:
        """Profile everything discoverable, largest first.

        Largest first because a budget will eventually bind, and the objects a
        person cares about are almost never the small ones.
        """
        profiles = []
        for discovered in (await connector.discover())[:limit]:
            try:
                profiles.append(await self.profile(connector, discovered.path, plan=plan))
            except Exception as exc:
                _log.warning("could not profile %s: %s", discovered.qualified_name, exc)
        return profiles


def suggest_sample_plan(
    estimated_rows: int | None,
    *,
    full_scan_ceiling: int = 5_000_000,
    target_rows: int = 1_000_000,
) -> SamplePlan:
    """Choose how much to read, and be able to justify it.

    Below the ceiling, read everything: an exact rate is worth more than the
    compute saved. Above it, sample enough rows that a defect rate of interest
    is detectable, and say so rather than quietly reading a fixed 1%.
    """
    if estimated_rows is None or estimated_rows <= full_scan_ceiling:
        return SamplePlan(strategy=SamplingStrategy.FULL)
    fraction = min(1.0, target_rows / estimated_rows)
    return SamplePlan(strategy=SamplingStrategy.SYSTEMATIC, fraction=fraction, seed=1)


def detectable_rate(sampled_rows: int, *, confidence: float = 0.95) -> float:
    """The smallest defect rate a sample of this size can be expected to find.

    The "rule of three": seeing zero defects in *n* rows bounds the true rate
    below roughly 3/n at 95% confidence. This is the number that turns "we
    sampled 1%" into a sentence a business owner can act on — "we would have
    caught anything above 0.03%".
    """
    if sampled_rows <= 0:
        return 1.0
    multiplier = 3.0 if confidence >= 0.95 else 2.3
    return min(1.0, multiplier / sampled_rows)
