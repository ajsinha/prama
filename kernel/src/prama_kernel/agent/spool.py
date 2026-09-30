"""Keeping working when the control plane cannot be reached.

An agent that stops when the network does is worse than no agent: the estate
goes unchecked precisely during the incident that took the network out, and the
gap in the evidence is exactly where an auditor will look. So the agent keeps
running and spools its findings.

Three properties make the spool trustworthy rather than merely convenient.

**It is durable and bounded.** Findings survive the agent restarting, and the
spool has a ceiling — an unbounded buffer is a memory leak with a business case.
When the ceiling is reached the *oldest* findings are dropped, and the drop is
recorded as a numbered gap. Dropping the newest would be easier and would mean
that a long outage hides the recent failures rather than the old ones, which is
precisely backwards.

**It is hash-chained per agent.** Each finding links to the one before it, so
the control plane can tell a spool replayed intact from one that lost its
middle. Without this, an agent could send a subset of its findings and the
server could not tell.

**Delivery is at-least-once and the ledger deduplicates.** An agent that has
sent a batch and not heard back must send it again — the alternative is losing
it — so the same finding can arrive twice. Sequence numbers make the second
arrival recognisable, and the server keeps one. Exactly-once delivery over an
unreliable network is a thing people claim and nobody has; saying at-least-once
and deduplicating is the honest version.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Iterable, Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

from prama_kernel.clock import Clock, SystemClock
from prama_kernel.log import get_logger
from prama_kernel.record import GENESIS, EvidenceRecord

_log = get_logger(__name__)

#: How many findings an agent will hold before it starts dropping the oldest.
#: A day of a busy estate, so an overnight outage loses nothing.
DEFAULT_CAPACITY = 50_000


@dataclasses.dataclass(frozen=True, slots=True)
class Gap:
    """Findings the spool dropped, and what they were.

    Recorded rather than logged. A gap is a hole in the evidence and the
    control plane has to be told about it in the same channel as the evidence
    itself, or the hole is only visible to whoever reads agent logs.
    """

    first_sequence: int
    last_sequence: int
    dropped_at: datetime
    reason: str

    @property
    def count(self) -> int:
        return self.last_sequence - self.first_sequence + 1

    def render(self) -> str:
        return (
            f"{self.count} finding(s), sequences {self.first_sequence} to "
            f"{self.last_sequence}, dropped at "
            f"{self.dropped_at.isoformat(timespec='seconds')}: {self.reason}"
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Gap:
        return cls(
            first_sequence=int(payload["first_sequence"]),
            last_sequence=int(payload["last_sequence"]),
            dropped_at=datetime.fromisoformat(str(payload["dropped_at"])),
            reason=str(payload.get("reason", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "first_sequence": self.first_sequence,
            "last_sequence": self.last_sequence,
            "count": self.count,
            "dropped_at": self.dropped_at.isoformat(),
            "reason": self.reason,
        }


class Spool:
    """An agent's local, ordered, bounded store of findings not yet delivered."""

    def __init__(
        self,
        *,
        capacity: int = DEFAULT_CAPACITY,
        path: Path | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._capacity = max(1, capacity)
        self._path = path
        self._clock = clock or SystemClock()
        self._pending: list[EvidenceRecord] = []
        self._gaps: list[Gap] = []
        #: Everything written, ever — so a redelivery keeps its original
        #: sequence and the server can recognise it as the same finding.
        self._next_sequence = 0
        self._head = GENESIS
        if self._path is not None and self._path.exists():
            self._load()

    def __len__(self) -> int:
        return len(self._pending)

    def __iter__(self) -> Iterator[EvidenceRecord]:
        return iter(self._pending)

    @property
    def gaps(self) -> tuple[Gap, ...]:
        return tuple(self._gaps)

    @property
    def head(self) -> str:
        return self._head

    @property
    def is_full(self) -> bool:
        return len(self._pending) >= self._capacity

    # -- writing -----------------------------------------------------------

    def add(self, record: EvidenceRecord) -> EvidenceRecord:
        """Spool one finding, linked to the agent's own chain."""
        linked = dataclasses.replace(record, sequence=self._next_sequence, previous_hash=self._head)
        self._next_sequence += 1
        self._head = linked.record_hash
        self._pending.append(linked)
        self._evict()
        self._persist()
        return linked

    def _evict(self) -> None:
        if len(self._pending) <= self._capacity:
            return
        overflow = len(self._pending) - self._capacity
        dropped = self._pending[:overflow]
        self._pending = self._pending[overflow:]
        # The oldest go. Dropping the newest would be easier and would mean a
        # long outage hides the recent failures rather than the old ones.
        reason = (
            f"the spool reached its capacity of {self._capacity:,} while the control "
            f"plane was unreachable"
        )
        # Eviction happens one record at a time, so a long overflow would
        # otherwise produce one gap per record — a report of forty holes of one
        # finding each, when what happened was one hole of forty. Contiguous
        # drops are the same hole and are merged into it.
        if self._gaps and self._gaps[-1].last_sequence + 1 == dropped[0].sequence:
            previous = self._gaps[-1]
            self._gaps[-1] = dataclasses.replace(
                previous, last_sequence=dropped[-1].sequence, dropped_at=self._clock.now()
            )
            return
        gap = Gap(
            first_sequence=dropped[0].sequence,
            last_sequence=dropped[-1].sequence,
            dropped_at=self._clock.now(),
            reason=reason,
        )
        self._gaps.append(gap)
        # Logged once, when the hole opens. Logging every dropped record would
        # bury the fact that the spool is overflowing under the evidence of it.
        _log.warning("spool overflow began: %s", gap.render())

    # -- delivery ----------------------------------------------------------

    def batch(self, size: int = 500) -> list[EvidenceRecord]:
        """The next findings to send. Not removed until acknowledged."""
        return self._pending[:size]

    def acknowledge(self, through_sequence: int) -> int:
        """Drop what the control plane confirms it has.

        By sequence rather than by count, so an acknowledgement that crosses
        with a new finding cannot remove something that was never sent.
        """
        before = len(self._pending)
        self._pending = [r for r in self._pending if r.sequence > through_sequence]
        removed = before - len(self._pending)
        if removed:
            self._persist()
        return removed

    def forget_gaps(self, delivered: Iterable[Gap]) -> int:
        """Forget exactly the gaps that were delivered, and no others.

        Finding X3. The method this replaces, `take_gaps()`, cleared *every*
        gap the spool held, and its caller had no idea which had actually been
        delivered. Two ways that lost a hole in the evidence: a gap recorded
        between building a report and receiving its receipt was cleared without
        ever being sent, and a `hello` receipt — handled by the same `apply()`
        — cleared gaps that had never been in any report at all.

        A gap is the record of evidence this agent dropped. Losing it does not
        lose a log line; it makes the estate under-report and look complete
        while doing so, which is the failure `Gap` exists to prevent.
        """
        seen = {(gap.first_sequence, gap.last_sequence) for gap in delivered}
        before = len(self._gaps)
        self._gaps = [
            gap for gap in self._gaps if (gap.first_sequence, gap.last_sequence) not in seen
        ]
        removed = before - len(self._gaps)
        if removed:
            self._persist()
        return removed

    # -- durability --------------------------------------------------------

    def _persist(self) -> None:
        if self._path is None:
            return
        payload = {
            "next_sequence": self._next_sequence,
            "head": self._head,
            "pending": [r.to_dict() for r in self._pending],
            "gaps": [g.to_dict() for g in self._gaps],
        }
        # Written whole and moved into place. A spool half-written by a process
        # that died is a spool that will not load, which turns one outage into
        # a permanent loss.
        temporary = self._path.with_suffix(self._path.suffix + ".writing")
        temporary.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps(payload), encoding="utf-8")
        temporary.replace(self._path)

    def _load(self) -> None:
        assert self._path is not None
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            # A corrupt spool is a gap, not a crash. Refusing to start would
            # leave the estate unchecked over exactly the kind of incident that
            # corrupted it.
            _log.error("spool at %s could not be read and was discarded: %s", self._path, exc)
            self._gaps.append(
                Gap(
                    first_sequence=0,
                    last_sequence=0,
                    dropped_at=self._clock.now(),
                    reason=f"the spool file could not be read: {exc}",
                )
            )
            return
        self._next_sequence = int(payload.get("next_sequence", 0))
        self._head = str(payload.get("head", GENESIS))
        self._pending = [EvidenceRecord.from_dict(entry) for entry in payload.get("pending", [])]
        self._gaps = [
            Gap(
                first_sequence=int(g["first_sequence"]),
                last_sequence=int(g["last_sequence"]),
                dropped_at=datetime.fromisoformat(g["dropped_at"]),
                reason=str(g["reason"]),
            )
            for g in payload.get("gaps", [])
        ]
