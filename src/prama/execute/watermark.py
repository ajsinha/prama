"""Checking only what has changed, and being honest about the rest.

Named for the watermark rather than for incrementality because
:mod:`prama.profile.incremental` already means something at a different level —
which segments of a dataset need re-profiling. This decides how much of a
dataset one *control run* reads. Two modules called the same thing at two levels
is a confusion nobody untangles at three in the morning.

A control over a table with four years of history should not read four years
every night. A watermark — the high point of some monotone column — lets a run
examine only what is new, and turns an hour into a second.

It also quietly changes what the verdict means, and that is the part everybody
gets wrong.

**An incremental run makes a narrower claim.** "positions_eod passed" after a
full scan means the whole table is sound. The same words after an incremental
run mean *today's rows* are sound and nothing was said about the rest. Those are
different sentences and a platform that renders them identically is
misrepresenting its own evidence. So the scope travels with the verdict, and a
narrow scope is stated rather than implied.

**A watermark cannot see backwards.** A correction booked to last Tuesday sits
below the high-water mark and is invisible for ever. This is not a corner case:
in a bank, late corrections *are* the workload. So an incremental scope carries
a **lookback** — a window of already-examined time that is examined again — and
the lookback is declared, because how long a restatement can arrive is a fact
about the business and not about the scheduler.

**Anything older than the lookback needs a different answer.** Either a periodic
full sweep, or a change signal the source can give — a row version, an
`updated_at`, a CDC stream. The policy says which, and a policy that says
neither is recorded as a gap rather than left to be discovered when a
restatement from three months ago turns up in a regulatory return.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
from datetime import date, datetime, timedelta
from typing import Any

from prama.core.errors import ValidationError


class Coverage(enum.Enum):
    """What a run actually examined. Carried into the evidence."""

    #: Everything in scope. The only one that supports "the dataset is sound".
    FULL = "full"
    #: New rows since the watermark, plus the lookback window.
    INCREMENTAL = "incremental"
    #: New rows only, with no lookback — a restatement would be invisible.
    FORWARD_ONLY = "forward_only"

    @property
    def sees_restatements(self) -> bool:
        return self is not Coverage.FORWARD_ONLY

    @property
    def supports_a_claim_about_the_whole_dataset(self) -> bool:
        return self is Coverage.FULL

    def qualify(self, verdict: str) -> str:
        """The verdict, said at the width it was actually established.

        "passed" and "passed over the rows examined" are different claims, and
        rendering them the same way is how a coverage report comes to overstate
        itself without anybody lying.
        """
        if self is Coverage.FULL:
            return verdict
        return f"{verdict} over the rows examined"


@dataclasses.dataclass(frozen=True, slots=True)
class Watermark:
    """The high point of a monotone column, and when it was reached."""

    column: str
    value: Any = None
    #: When this watermark was recorded, which is not the same as the value.
    #: A watermark of 2026-04-01 recorded a week late means a week of data
    #: arrived at once, and that is worth being able to see.
    observed_at: datetime | None = None
    rows_seen: int = 0

    @property
    def is_set(self) -> bool:
        return self.value is not None

    def advanced_to(self, value: Any, *, at: datetime, rows: int = 0) -> Watermark:
        """Move the mark forward. Never backwards.

        A watermark that could move back would silently re-admit rows already
        judged, and the same failing row would be reported every night until
        somebody noticed the count was wrong rather than the data.
        """
        if self.value is not None and value is not None and _before(value, self.value):
            return self
        return dataclasses.replace(
            self, value=value, observed_at=at, rows_seen=self.rows_seen + rows
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "column": self.column,
            "value": _plain(self.value),
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
            "rows_seen": self.rows_seen,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class LatenessPolicy:
    """How far back a restatement can arrive, and what covers the rest."""

    #: The window re-examined on every run. Declared, because how late a
    #: correction can be is a fact about the business.
    lookback: timedelta = timedelta(days=3)
    #: How often everything is examined regardless. None means never, which is
    #: legitimate only when the source can signal a change to an old row.
    full_sweep_every: timedelta | None = timedelta(days=7)
    #: A column that changes when a row is restated. When present, an
    #: incremental scope can find an old row that moved without a full sweep.
    change_column: str = ""

    def __post_init__(self) -> None:
        if self.lookback < timedelta(0):
            raise ValidationError(
                "a lookback cannot be negative",
                remedy="Give the period during which a correction may still arrive.",
            )

    @property
    def covers_the_past(self) -> bool:
        """Whether anything at all would notice a restatement outside the lookback."""
        return bool(self.full_sweep_every or self.change_column)

    @property
    def gap(self) -> str:
        """What this policy does not cover, in one sentence, or empty."""
        if self.covers_the_past:
            return ""
        return (
            f"Nothing examines rows older than {_period(self.lookback)}. A correction "
            f"booked before that would never be seen. Declare a full sweep, or name "
            f"the column that changes when a row is restated."
        )

    def describe(self) -> str:
        parts = [f"new rows, plus anything from the last {_period(self.lookback)}"]
        if self.change_column:
            parts.append(f"plus any row whose {self.change_column} has moved")
        if self.full_sweep_every:
            parts.append(f"and everything every {_period(self.full_sweep_every)}")
        return "Examines " + ", ".join(parts) + "."


@dataclasses.dataclass(frozen=True, slots=True)
class IncrementalScope:
    """What one run will look at, and what it will not."""

    coverage: Coverage
    watermark: Watermark
    #: The predicate narrowing the scan, in the language's own expression
    #: syntax so it composes with a control's own WHERE.
    predicate: str = ""
    lower_bound: Any = None
    #: Set when the run is a full sweep, so the evidence says why this one was
    #: wider than the others.
    reason: str = ""

    @property
    def is_narrowed(self) -> bool:
        return self.coverage is not Coverage.FULL

    def describe(self) -> str:
        if self.coverage is Coverage.FULL:
            return f"the whole dataset{f' — {self.reason}' if self.reason else ''}"
        if self.lower_bound is None:
            return "nothing has been examined before, so this run reads everything"
        return f"rows where {self.watermark.column} is at or after {_plain(self.lower_bound)}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "coverage": self.coverage.value,
            "predicate": self.predicate,
            "lower_bound": _plain(self.lower_bound),
            "watermark": self.watermark.to_dict(),
            "reason": self.reason,
            "describes": self.describe(),
        }


class WatermarkPlanner:
    """Decides how much of a dataset one run should read."""

    def __init__(self, policy: LatenessPolicy | None = None) -> None:
        self._policy = policy or LatenessPolicy()

    @property
    def policy(self) -> LatenessPolicy:
        return self._policy

    def scope(
        self,
        watermark: Watermark,
        *,
        now: datetime,
        last_full_sweep: datetime | None = None,
    ) -> IncrementalScope:
        """What to read this time.

        A dataset never examined reads everything, and says so. A dataset due a
        full sweep reads everything, and says why — the evidence should be able
        to explain why last Tuesday's run took an hour when the others took a
        second.
        """
        policy = self._policy
        if not watermark.is_set:
            return IncrementalScope(
                coverage=Coverage.FULL,
                watermark=watermark,
                reason="nothing has been examined before",
            )
        if self._sweep_is_due(now, last_full_sweep):
            return IncrementalScope(
                coverage=Coverage.FULL,
                watermark=watermark,
                reason=(
                    "a full sweep is due; the last was "
                    + (last_full_sweep.date().isoformat() if last_full_sweep else "never run")
                ),
            )
        lower = _shift(watermark.value, -policy.lookback)
        clauses = [f"{watermark.column} >= {_literal(lower)}"]
        if policy.change_column:
            # An old row that moved is found by its change column rather than
            # by its business date, which is the only way a restatement outside
            # the lookback is visible without reading everything.
            clauses.append(f"{policy.change_column} >= {_literal(lower)}")
        predicate = " OR ".join(clauses) if len(clauses) > 1 else clauses[0]
        return IncrementalScope(
            coverage=Coverage.INCREMENTAL
            if policy.lookback or policy.change_column
            else Coverage.FORWARD_ONLY,
            watermark=watermark,
            predicate=predicate,
            lower_bound=lower,
        )

    def _sweep_is_due(self, now: datetime, last: datetime | None) -> bool:
        every = self._policy.full_sweep_every
        if every is None:
            return False
        if last is None:
            return True
        return now - last >= every

    def audit(self) -> dict[str, Any]:
        """What this policy covers and what it does not.

        The gap is reported rather than left to be discovered when a
        restatement from three months ago turns up in a regulatory return.
        """
        return {
            "describes": self._policy.describe(),
            "covers_the_past": self._policy.covers_the_past,
            "gap": self._policy.gap,
        }


def _before(candidate: Any, current: Any) -> bool:
    try:
        return bool(candidate < current)
    except TypeError:
        # Two values that cannot be ordered are not evidence that the mark
        # should move back. Refusing to move is the safe direction: at worst a
        # row is examined twice.
        return True


def _shift(value: Any, delta: timedelta) -> Any:
    if isinstance(value, datetime):
        return value + delta
    if isinstance(value, date):
        return value + delta
    if isinstance(value, str):
        try:
            return (datetime.fromisoformat(value) + delta).isoformat()
        except ValueError:
            return value
    if isinstance(value, int | float):
        # A numeric watermark — a sequence, an offset — has no notion of days,
        # so the lookback cannot be applied and the mark itself is the bound.
        return value
    return value


def _literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, int | float) and not isinstance(value, bool):
        return repr(value)
    return "'" + str(_plain(value)).replace("'", "''") + "'"


def _plain(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime | date) else value


def _period(delta: timedelta) -> str:
    days = delta.days
    if days >= 1:
        return "day" if days == 1 else f"{days} days"
    hours = int(delta.total_seconds() // 3600)
    if hours >= 1:
        return "hour" if hours == 1 else f"{hours} hours"
    return f"{int(delta.total_seconds() // 60)} minutes"
