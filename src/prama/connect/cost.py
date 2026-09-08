"""What a scan will cost, before it runs.

Nobody in a bank will let an unfamiliar tool loose on a production warehouse
without knowing what it is about to do. The honest answer is not a spinner and
an apology afterwards; it is a sentence beforehand: *reading sales.orders will
scan about 3.9 GB across 50,000 rows, roughly forty seconds at the speed this
connection has managed before, and that is within this connection's ten gigabyte
budget.*

Three principles hold this together:

* **The estimate costs nothing.** It is built from catalogue metadata that
  discovery already fetched. An estimate that requires a scan to produce is not
  a preview.
* **Where the number came from travels with it.** A catalogue estimate, a
  measured throughput and a guess are three different things, and a preview that
  renders them identically teaches people to distrust all three.
* **Unknown is a valid answer.** A duration invented from a default throughput
  constant is a fabrication, and a confident wrong number is worse for trust
  than an admitted absence.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
from datetime import datetime
from typing import Any

from prama.connect.spi import (
    DiscoveredObject,
    ObjectSchema,
    ReadPolicy,
    SamplePlan,
    SamplingStrategy,
)
from prama.core.clock import utc_now

#: Bytes per row assumed only when a source reports rows but not size. Stated
#: rather than hidden, and the resulting estimate is marked as derived.
ASSUMED_BYTES_PER_ROW = 128


class EstimateBasis(enum.Enum):
    """Where a number came from. Rendered, never dropped."""

    MEASURED = "measured"
    CATALOGUE = "catalogue"
    DERIVED = "derived"
    UNKNOWN = "unknown"

    @property
    def is_trustworthy(self) -> bool:
        return self in (EstimateBasis.MEASURED, EstimateBasis.CATALOGUE)

    @property
    def caveat(self) -> str:
        return {
            EstimateBasis.MEASURED: "",
            EstimateBasis.CATALOGUE: "from the source's own statistics, so approximate",
            EstimateBasis.DERIVED: "inferred, not reported by the source",
            EstimateBasis.UNKNOWN: "the source does not report this",
        }[self]


@dataclasses.dataclass(frozen=True, slots=True)
class Throughput:
    """How fast a connection has actually gone, from previous reads."""

    bytes_per_second: float
    rows_per_second: float
    samples: int
    measured_at: datetime

    @classmethod
    def from_read(cls, *, rows: int, byte_count: int, seconds: float) -> Throughput | None:
        # A read too short to time says nothing useful, and letting it into the
        # average would make the next estimate worse rather than better.
        if seconds < 0.05 or rows <= 0:
            return None
        return cls(
            bytes_per_second=byte_count / seconds,
            rows_per_second=rows / seconds,
            samples=1,
            measured_at=utc_now(),
        )

    def merged_with(self, other: Throughput) -> Throughput:
        """Weighted by sample count, so one slow morning does not dominate."""
        total = self.samples + other.samples
        return Throughput(
            bytes_per_second=(
                self.bytes_per_second * self.samples + other.bytes_per_second * other.samples
            )
            / total,
            rows_per_second=(
                self.rows_per_second * self.samples + other.rows_per_second * other.samples
            )
            / total,
            samples=total,
            measured_at=max(self.measured_at, other.measured_at),
        )


@dataclasses.dataclass(frozen=True, slots=True)
class ScanEstimate:
    """What a read is expected to cost, and how much to believe it."""

    path: tuple[str, ...]
    rows: int | None
    rows_basis: EstimateBasis
    byte_count: int | None
    bytes_basis: EstimateBasis
    fraction: float = 1.0
    duration_seconds: float | None = None
    duration_basis: EstimateBasis = EstimateBasis.UNKNOWN
    paced_duration_seconds: float | None = None
    exceeds: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def object_name(self) -> str:
        return ".".join(self.path)

    @property
    def within_budget(self) -> bool:
        return not self.exceeds

    @property
    def is_confident(self) -> bool:
        return self.rows_basis.is_trustworthy and self.bytes_basis.is_trustworthy

    def render(self) -> str:
        """One sentence somebody can act on."""
        parts = [f"Reading {self.object_name} will"]
        if self.fraction < 1.0:
            parts.append(f"sample {self.fraction:.2%} of the table,")
        parts.append("scan")
        parts.append(_render_bytes(self.byte_count) if self.byte_count is not None else "?")
        if self.rows is not None:
            parts.append(f"across about {self.rows:,} rows")
        if self.paced_duration_seconds is not None:
            parts.append(f"and take around {_render_duration(self.paced_duration_seconds)}")
        elif self.duration_seconds is not None:
            parts.append(f"and take around {_render_duration(self.duration_seconds)}")
        else:
            parts.append("— duration unknown, nothing has been read through this connection yet")
        sentence = " ".join(parts).rstrip() + "."
        if self.exceeds:
            sentence += f" This exceeds {', '.join(self.exceeds)}."
        return sentence

    def to_dict(self) -> dict[str, Any]:
        return {
            "object": self.object_name,
            "rows": self.rows,
            "rows_basis": self.rows_basis.value,
            "bytes": self.byte_count,
            "bytes_basis": self.bytes_basis.value,
            "fraction": self.fraction,
            "duration_seconds": self.duration_seconds,
            "duration_basis": self.duration_basis.value,
            "paced_duration_seconds": self.paced_duration_seconds,
            "within_budget": self.within_budget,
            "exceeds": list(self.exceeds),
            "warnings": list(self.warnings),
            "summary": self.render(),
        }


class CostEstimator:
    """Builds a preview from metadata that has already been fetched."""

    def __init__(self, policy: ReadPolicy | None = None) -> None:
        self._policy = policy or ReadPolicy()

    def estimate(
        self,
        *,
        path: tuple[str, ...],
        discovered: DiscoveredObject | None = None,
        schema: ObjectSchema | None = None,
        plan: SamplePlan | None = None,
        throughput: Throughput | None = None,
    ) -> ScanEstimate:
        plan = plan or SamplePlan()
        rows, rows_basis = self._rows(discovered, schema)
        byte_count, bytes_basis = self._bytes(discovered, rows, rows_basis)
        fraction = self._fraction(plan, rows)

        scanned_rows = int(rows * fraction) if rows is not None else None
        scanned_bytes = int(byte_count * fraction) if byte_count is not None else None
        scanned_rows, scanned_bytes = self._apply_row_cap(plan, scanned_rows, scanned_bytes)

        duration, duration_basis = self._duration(scanned_rows, scanned_bytes, throughput)
        return ScanEstimate(
            path=path,
            rows=scanned_rows,
            rows_basis=rows_basis,
            byte_count=scanned_bytes,
            bytes_basis=bytes_basis,
            fraction=fraction,
            duration_seconds=duration,
            duration_basis=duration_basis,
            paced_duration_seconds=self._paced(duration),
            exceeds=self._exceeds(scanned_rows, scanned_bytes),
            warnings=self._warnings(plan, rows_basis, bytes_basis),
        )

    # -- the numbers -------------------------------------------------------

    def _rows(
        self, discovered: DiscoveredObject | None, schema: ObjectSchema | None
    ) -> tuple[int | None, EstimateBasis]:
        if discovered is not None and discovered.estimated_rows is not None:
            return discovered.estimated_rows, EstimateBasis.CATALOGUE
        if schema is not None and schema.estimated_rows is not None:
            return schema.estimated_rows, EstimateBasis.CATALOGUE
        return None, EstimateBasis.UNKNOWN

    def _bytes(
        self, discovered: DiscoveredObject | None, rows: int | None, rows_basis: EstimateBasis
    ) -> tuple[int | None, EstimateBasis]:
        if discovered is not None and discovered.estimated_bytes is not None:
            return discovered.estimated_bytes, EstimateBasis.CATALOGUE
        if rows is not None and rows_basis is not EstimateBasis.UNKNOWN:
            # A crude multiple, and marked as such: a preview that presented
            # this as a catalogue figure would be quietly lying about a number
            # somebody is using to decide whether to run the scan.
            return rows * ASSUMED_BYTES_PER_ROW, EstimateBasis.DERIVED
        return None, EstimateBasis.UNKNOWN

    @staticmethod
    def _fraction(plan: SamplePlan, rows: int | None) -> float:
        if plan.strategy in (SamplingStrategy.FULL,):
            return 1.0
        if plan.fraction is not None:
            return max(0.0, min(1.0, plan.fraction))
        if plan.rows is not None and rows:
            return max(0.0, min(1.0, plan.rows / rows))
        return 1.0

    @staticmethod
    def _apply_row_cap(
        plan: SamplePlan, scanned_rows: int | None, scanned_bytes: int | None
    ) -> tuple[int | None, int | None]:
        if plan.rows is None or scanned_rows is None:
            return scanned_rows, scanned_bytes
        if scanned_rows <= plan.rows:
            return scanned_rows, scanned_bytes
        share = plan.rows / scanned_rows
        return plan.rows, int(scanned_bytes * share) if scanned_bytes is not None else None

    @staticmethod
    def _duration(
        rows: int | None, byte_count: int | None, throughput: Throughput | None
    ) -> tuple[float | None, EstimateBasis]:
        # No measurement means no duration. Inventing one from a default
        # throughput constant would be a fabrication, and a confident wrong
        # number costs more trust than an admitted absence.
        if throughput is None:
            return None, EstimateBasis.UNKNOWN
        # Rows first, because rows are the one quantity measured and estimated
        # in the same currency. The catalogue's byte figure is size *on disk* —
        # for PostgreSQL, pg_total_relation_size, which counts indexes, TOAST
        # and page padding — while measured throughput is bytes *delivered*.
        # Dividing one by the other looks arithmetically fine and is a unit
        # error, and on an index-heavy table it overstates the duration
        # severalfold.
        if rows is not None and throughput.rows_per_second > 0:
            return rows / throughput.rows_per_second, EstimateBasis.MEASURED
        if byte_count is not None and throughput.bytes_per_second > 0:
            # No row count, so bytes are all there is. Marked derived: the two
            # byte figures are not the same measurement.
            return byte_count / throughput.bytes_per_second, EstimateBasis.DERIVED
        return None, EstimateBasis.UNKNOWN

    def _paced(self, duration: float | None) -> float | None:
        """Wall clock once the load ceiling's waiting is added."""
        ceiling = self._policy.load_ceiling
        if duration is None or not 0.0 < ceiling < 1.0:
            return duration
        return duration / ceiling

    # -- the judgement -----------------------------------------------------

    def _exceeds(self, rows: int | None, byte_count: int | None) -> tuple[str, ...]:
        breached = []
        limit_rows = self._policy.max_rows_read
        limit_bytes = self._policy.max_bytes_scanned
        if limit_rows is not None and rows is not None and rows > limit_rows:
            breached.append(f"this connection's limit of {limit_rows:,} rows")
        if limit_bytes is not None and byte_count is not None and byte_count > limit_bytes:
            breached.append(f"this connection's limit of {_render_bytes(limit_bytes)}")
        return tuple(breached)

    @staticmethod
    def _warnings(
        plan: SamplePlan, rows_basis: EstimateBasis, bytes_basis: EstimateBasis
    ) -> tuple[str, ...]:
        out = []
        if rows_basis is EstimateBasis.UNKNOWN:
            out.append(
                "the source does not report a row count, so this scan's size is unknown "
                "until it runs"
            )
        elif bytes_basis is EstimateBasis.DERIVED:
            out.append(
                f"the source reports rows but not size; volume assumes "
                f"{ASSUMED_BYTES_PER_ROW} bytes per row"
            )
        if plan.strategy is SamplingStrategy.FULL:
            out.append("this is a full scan; sampling would cost a fraction of it")
        return tuple(out)

    def plan_that_fits(self, estimate: ScanEstimate) -> SamplePlan | None:
        """A sampling plan that would bring an over-budget scan inside it.

        Offered instead of a refusal, because "you cannot do that" is a dead end
        and "you cannot do that, but this would work" is an answer.
        """
        if estimate.within_budget or estimate.rows is None:
            return None
        limit = self._policy.max_rows_read
        if limit is None and self._policy.max_bytes_scanned is not None and estimate.byte_count:
            share = self._policy.max_bytes_scanned / estimate.byte_count
            limit = max(1, int(estimate.rows * share))
        if limit is None:
            return None
        return SamplePlan(
            strategy=SamplingStrategy.SYSTEMATIC,
            rows=min(limit, estimate.rows),
            fraction=min(1.0, limit / estimate.rows),
        )


class ThroughputRegistry:
    """What each connection has actually managed, so previews improve with use.

    In memory and per process. A shared history belongs in the metric store; the
    point here is that the first preview says "unknown" and the second says
    something true.
    """

    def __init__(self) -> None:
        self._observed: dict[str, Throughput] = {}

    def record(self, connection_id: str, sample: Throughput | None) -> None:
        if sample is None:
            return
        existing = self._observed.get(connection_id)
        self._observed[connection_id] = sample if existing is None else existing.merged_with(sample)

    def of(self, connection_id: str) -> Throughput | None:
        return self._observed.get(connection_id)


def _render_bytes(count: int) -> str:
    step = 1024.0
    value = float(count)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < step or unit == "TB":
            return f"{value:,.0f} {unit}" if unit == "B" else f"{value:,.1f} {unit}"
        value /= step
    return f"{value:,.1f} TB"


def _render_duration(seconds: float) -> str:
    if seconds < 1:
        return "under a second"
    if seconds < 90:
        return f"{seconds:.0f} seconds"
    if seconds < 5400:
        return f"{seconds / 60:.0f} minutes"
    return f"{seconds / 3600:.1f} hours"
