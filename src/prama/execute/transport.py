"""The broker seam: driving in-flight enforcement from a stream.

:mod:`prama.execute.stream` evaluates a control against a message and
:mod:`prama.execute.inflight` decides what happens to it. This decides
*when it is safe to say the message has been dealt with*, which on a stream
means one thing: when to commit the offset.

That is the whole substance of this module, and it is easy to get backwards.

**Commit after, never before.** A consumer that commits an offset and then
enforces has promised the broker it is finished with a message it has not
finished with. Crash in between and the message is never redelivered and never
dead-lettered: it is simply gone, and nothing anywhere records that it existed.
That is the same failure ``inflight`` exists to prevent, moved one layer out.

**At-least-once, and said out loud.** Committing after enforcement means a crash
between the two replays the batch, so a message can be dead-lettered twice. That
is the trade, taken deliberately: duplicate evidence is a reconciliation
problem, lost data is not a problem anybody can solve afterwards. Nothing here
claims exactly-once, because without a transaction spanning the broker and the
dead letter nothing can deliver it.

**A halted batch commits what completed, not what was polled.** When the dead
letter fills, the pipeline stops part-way. Committing the batch's last offset
would skip every message after the halt; committing nothing replays the ones
already dead-lettered. Committing through the last *enforced* message is the
only choice that loses nothing, and it is why positions are tracked per message
rather than per batch.

**Offsets are per partition.** A batch spans partitions, and a single "last
offset" is meaningless across them — committing one partition's offset against
another's is how a consumer group silently skips a partition's worth of data.

The transport is an ABC with a reference implementation, so the loop is tested
without a broker. **No Kafka or Flink client ships here**: the transport that
talks to a real broker belongs to the deployment, where the organisation's
security, retry and partition-assignment policy already lives.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import abc
import dataclasses
from collections.abc import Sequence
from typing import Any

from prama.core.errors import PramaError
from prama.execute.inflight import Outcome, Pipeline, Report

__all__ = [
    "MemoryTransport",
    "Position",
    "StreamMessage",
    "StreamRunner",
    "StreamTransport",
    "TransportError",
    "run_until_idle",
]


class TransportError(PramaError):
    """The transport failed. Never swallowed, never retried silently here.

    A retry policy belongs to the transport, which knows whether the broker is
    unreachable or the request was malformed. A loop that retried everything
    would retry a poison request forever.
    """

    code = "STREAM.TRANSPORT"


@dataclasses.dataclass(frozen=True, slots=True, order=True)
class Position:
    """Where one message sat. The unit an offset commit is expressed in."""

    topic: str
    partition: int
    offset: int

    def render(self) -> str:
        return f"{self.topic}[{self.partition}]@{self.offset}"


@dataclasses.dataclass(frozen=True, slots=True)
class StreamMessage:
    """One message, with enough to find it again."""

    position: Position
    payload: dict[str, Any]
    key: str = ""
    headers: dict[str, str] = dataclasses.field(default_factory=dict)


class StreamTransport(abc.ABC):
    """A source of messages that can be told how far we have got.

    Narrow on purpose. A transport that could also *produce* would invite the
    enforcement loop to republish, and a loop that both consumes and produces on
    the same broker is one topology change away from feeding itself.
    """

    @abc.abstractmethod
    def poll(self, max_messages: int) -> Sequence[StreamMessage]:
        """Up to ``max_messages``, or fewer, or none. Never blocks forever."""

    @abc.abstractmethod
    def commit(self, positions: Sequence[Position]) -> None:
        """Record that everything up to and including these is dealt with."""

    def close(self) -> None:
        """Release whatever the transport holds. Safe to call twice.

        Optional and does nothing by default: a transport holding no resource
        should not be made to write an empty override, and an abstract method
        here would mean every in-memory test double carries one.
        """
        return


class MemoryTransport(StreamTransport):
    """The reference transport: a list, and the offsets committed against it.

    Exists so the loop can be exercised without a broker, and so a real
    transport has something to be checked against. It also makes the commit
    ordering testable, which is the property this module is about — a bug there
    is invisible until a process dies at the wrong moment.
    """

    def __init__(self, messages: Sequence[StreamMessage] = ()) -> None:
        self._pending = list(messages)
        self.committed: dict[tuple[str, int], int] = {}
        self.commits: list[tuple[Position, ...]] = []
        self.closed = False

    def poll(self, max_messages: int) -> Sequence[StreamMessage]:
        batch = self._pending[:max_messages]
        self._pending = self._pending[max_messages:]
        return batch

    def commit(self, positions: Sequence[Position]) -> None:
        self.commits.append(tuple(positions))
        for position in positions:
            key = (position.topic, position.partition)
            # Highest wins. A commit that moved an offset backwards would
            # replay messages already dealt with, which is not wrong but is a
            # surprise nobody asked for.
            self.committed[key] = max(self.committed.get(key, -1), position.offset)

    def close(self) -> None:
        self.closed = True

    @property
    def remaining(self) -> int:
        return len(self._pending)


@dataclasses.dataclass(frozen=True, slots=True)
class StreamReport:
    """One batch: what the pipeline decided, and what was committed."""

    report: Report
    polled: int
    committed: tuple[Position, ...] = ()
    uncommitted: tuple[Position, ...] = ()

    @property
    def halted(self) -> bool:
        return bool(self.report.halted_because)

    def describe(self) -> str:
        if not self.polled:
            return "nothing to read"
        head = self.report.describe()
        if not self.halted:
            return f"{head} Committed through {len(self.committed)} partition(s)."
        return (
            f"{head} HALTED: {self.report.halted_because} "
            f"{len(self.uncommitted)} message(s) were polled and not enforced; their "
            "offsets were not committed, so the broker will redeliver them."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "polled": self.polled,
            "halted": self.halted,
            "committed": [p.render() for p in self.committed],
            "uncommitted": [p.render() for p in self.uncommitted],
            **self.report.to_dict(),
        }


class StreamRunner:
    """Polls, enforces, and commits — in that order, always."""

    def __init__(
        self,
        transport: StreamTransport,
        pipeline: Pipeline,
        *,
        batch_size: int = 100,
    ) -> None:
        if batch_size < 1:
            raise PramaError(
                f"a batch of {batch_size} reads nothing",
                code="STREAM.BATCH_SIZE",
                remedy="Use a positive batch size.",
            )
        self._transport = transport
        self._pipeline = pipeline
        self._batch_size = batch_size

    def poll_once(self) -> StreamReport:
        """One poll, one enforcement pass, one commit. Never reordered."""
        try:
            batch = list(self._transport.poll(self._batch_size))
        except Exception as exc:
            raise TransportError(
                "the transport failed while polling",
                remedy=(
                    "Nothing was enforced and nothing was committed, so no "
                    "message was lost. Fix the transport and the batch is "
                    "redelivered."
                ),
                context={"error": type(exc).__name__},
            ) from exc

        if not batch:
            return StreamReport(report=self._pipeline.run([]), polled=0)

        report = self._pipeline.run(m.payload for m in batch)

        # The pipeline reports one outcome per message it *finished*. On a halt
        # that is fewer than were polled, and the difference is exactly what
        # must not be committed.
        enforced = len(report.outcomes)
        done = batch[:enforced]
        undone = batch[enforced:]

        positions = _highest_per_partition(m.position for m in done)
        if positions:
            try:
                self._transport.commit(positions)
            except Exception as exc:
                raise TransportError(
                    "the transport failed while committing",
                    remedy=(
                        "Enforcement already happened, so these messages will be "
                        "redelivered and dead-lettered again. Duplicate evidence "
                        "is a reconciliation problem; losing it is not one "
                        "anybody can solve afterwards."
                    ),
                    context={"error": type(exc).__name__, "messages": str(enforced)},
                ) from exc

        return StreamReport(
            report=report,
            polled=len(batch),
            committed=positions,
            uncommitted=tuple(m.position for m in undone),
        )

    def run_until_idle(self, *, max_batches: int = 1000) -> tuple[StreamReport, ...]:
        """Poll until a poll returns nothing, or the pipeline halts.

        ``max_batches`` is a backstop, not a tuning knob: a transport that keeps
        returning messages forever is a bug, and a loop with no bound turns it
        into a hang nobody can interrupt.
        """
        reports: list[StreamReport] = []
        for _ in range(max_batches):
            result = self.poll_once()
            if result.polled == 0:
                break
            reports.append(result)
            if result.halted:
                # Stop rather than poll again. The dead letter is full; the next
                # batch would halt on its first bad message, and the loop would
                # spin against a broker for as long as the condition lasts.
                break
        return tuple(reports)


def _highest_per_partition(positions: Any) -> tuple[Position, ...]:
    """One commit per partition, at its highest enforced offset.

    A single "last offset" across a multi-partition batch is meaningless, and
    committing one partition's offset against another's is how a consumer group
    silently skips a partition's worth of data.
    """
    highest: dict[tuple[str, int], Position] = {}
    for position in positions:
        key = (position.topic, position.partition)
        current = highest.get(key)
        if current is None or position.offset > current.offset:
            highest[key] = position
    return tuple(sorted(highest.values()))


def run_until_idle(
    transport: StreamTransport, pipeline: Pipeline, *, batch_size: int = 100
) -> tuple[StreamReport, ...]:
    return StreamRunner(transport, pipeline, batch_size=batch_size).run_until_idle()


def outcomes_of(reports: Sequence[StreamReport]) -> tuple[Outcome, ...]:
    return tuple(outcome for report in reports for outcome in report.report.outcomes)
