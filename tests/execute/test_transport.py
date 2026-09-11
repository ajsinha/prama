"""The broker seam, and the one thing it has to get right.

Every test here is about commit ordering. A consumer that commits before it
enforces has promised the broker it is finished with a message it has not
finished with, and a crash in between loses that message permanently with no
record anywhere that it existed.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.core.errors import PramaError
from prama.execute.actions import Action
from prama.execute.inflight import Pipeline
from prama.execute.stream import StreamAssertion
from prama.execute.transport import (
    MemoryTransport,
    Position,
    StreamMessage,
    StreamRunner,
    StreamTransport,
    TransportError,
)
from prama.ir.resolve import resolved
from prama.pql import parse_control

NOT_NULL = (
    "CHECK payments.amount IS NOT NULL SEVERITY critical DIMENSION completeness BECAUSE 'CDE'"
)


def assertion() -> StreamAssertion:
    return StreamAssertion(resolved(parse_control(NOT_NULL)))


class Bin:
    """A dead letter that records, and can be told to refuse."""

    def __init__(self, capacity: int | None = None) -> None:
        self.held: list[tuple[dict, str]] = []
        self.capacity = capacity

    def __call__(self, payload: dict, reason: str) -> bool:
        if self.capacity is not None and len(self.held) >= self.capacity:
            return False
        self.held.append((payload, reason))
        return True


def messages(
    count: int, *, topic: str = "payments", partition: int = 0, bad: set[int] = frozenset()
):
    return [
        StreamMessage(
            position=Position(topic=topic, partition=partition, offset=index),
            payload={"amount": None if index in bad else 100.0},
        )
        for index in range(count)
    ]


def pipeline(
    action: Action = Action.QUARANTINE, capacity: int | None = None
) -> tuple[Pipeline, Bin]:
    bin_ = Bin(capacity)
    return Pipeline([assertion()], action=action, dead_letter=bin_), bin_


class TestCommitOrdering:
    def test_a_clean_batch_commits_its_last_offset(self) -> None:
        transport = MemoryTransport(messages(5))
        runner = StreamRunner(transport, pipeline()[0])
        result = runner.poll_once()
        assert result.polled == 5
        assert transport.committed[("payments", 0)] == 4

    def test_nothing_is_committed_before_enforcement(self) -> None:
        """The property the module exists for, asserted by watching the order
        in which the dead letter and the commit are touched."""
        order: list[str] = []

        class Watching(MemoryTransport):
            def commit(self, positions):
                order.append("commit")
                super().commit(positions)

        bin_ = Bin()

        def record(payload, reason):
            order.append("dead-letter")
            return bin_(payload, reason)

        transport = Watching(messages(3, bad={1}))
        pipe = Pipeline([assertion()], action=Action.QUARANTINE, dead_letter=record)
        StreamRunner(transport, pipe).poll_once()
        assert order == ["dead-letter", "commit"]

    def test_an_empty_poll_commits_nothing(self) -> None:
        transport = MemoryTransport([])
        result = StreamRunner(transport, pipeline()[0]).poll_once()
        assert result.polled == 0
        assert transport.commits == []


class TestAHaltedBatch:
    def test_it_commits_through_the_last_enforced_message_only(self) -> None:
        """Committing the batch's last offset would skip everything after the
        halt; committing nothing replays what was already dead-lettered."""
        transport = MemoryTransport(messages(6, bad={1, 3}))
        pipe, _ = pipeline(capacity=1)
        result = StreamRunner(transport, pipe).poll_once()

        assert result.halted
        assert transport.committed[("payments", 0)] == len(result.report.outcomes) - 1
        assert result.uncommitted

    def test_the_unenforced_messages_are_named(self) -> None:
        transport = MemoryTransport(messages(6, bad={1, 3}))
        pipe, _ = pipeline(capacity=1)
        result = StreamRunner(transport, pipe).poll_once()
        offsets = {p.offset for p in result.uncommitted}
        assert offsets
        assert min(offsets) == len(result.report.outcomes)

    def test_it_says_the_broker_will_redeliver_them(self) -> None:
        transport = MemoryTransport(messages(6, bad={1, 3}))
        pipe, _ = pipeline(capacity=1)
        described = StreamRunner(transport, pipe).poll_once().describe()
        assert "redeliver" in described
        assert "HALTED" in described

    def test_the_loop_stops_rather_than_spinning_on_a_full_dead_letter(self) -> None:
        """The next batch would halt on its first bad message, and the loop
        would spin against a broker for as long as the condition lasts."""
        transport = MemoryTransport(messages(20, bad={1, 3, 5, 7}))
        pipe, _ = pipeline(capacity=1)
        reports = StreamRunner(transport, pipe, batch_size=4).run_until_idle()
        assert reports[-1].halted
        assert transport.remaining > 0


class TestPartitions:
    def test_each_partition_commits_its_own_highest_offset(self) -> None:
        """A single last offset across a multi-partition batch is meaningless,
        and committing one partition's against another's is how a consumer
        group silently skips a partition's worth of data."""
        batch = messages(3, partition=0) + messages(5, partition=1)
        transport = MemoryTransport(batch)
        StreamRunner(transport, pipeline()[0]).poll_once()
        assert transport.committed[("payments", 0)] == 2
        assert transport.committed[("payments", 1)] == 4

    def test_topics_are_kept_apart(self) -> None:
        batch = messages(2, topic="payments") + messages(4, topic="trades")
        transport = MemoryTransport(batch)
        StreamRunner(transport, pipeline()[0]).poll_once()
        assert transport.committed[("payments", 0)] == 1
        assert transport.committed[("trades", 0)] == 3

    def test_one_commit_per_partition_not_per_message(self) -> None:
        transport = MemoryTransport(messages(10))
        StreamRunner(transport, pipeline()[0]).poll_once()
        assert len(transport.commits) == 1
        assert len(transport.commits[0]) == 1

    def test_a_commit_never_moves_an_offset_backwards(self) -> None:
        transport = MemoryTransport(messages(4))
        transport.commit([Position("payments", 0, 99)])
        StreamRunner(transport, pipeline()[0]).poll_once()
        assert transport.committed[("payments", 0)] == 99


class TestTransportFailures:
    def test_a_poll_failure_loses_nothing(self) -> None:
        class Broken(MemoryTransport):
            def poll(self, max_messages):
                raise OSError("broker unreachable")

        with pytest.raises(TransportError, match="while polling") as caught:
            StreamRunner(Broken(), pipeline()[0]).poll_once()
        assert "no message was lost" in caught.value.remedy

    def test_a_commit_failure_says_the_batch_will_be_redelivered(self) -> None:
        """Enforcement already happened, so these are dead-lettered twice.
        Duplicate evidence is a reconciliation problem; losing it is not one
        anybody can solve afterwards."""

        class Broken(MemoryTransport):
            def commit(self, positions):
                raise OSError("broker unreachable")

        with pytest.raises(TransportError, match="while committing") as caught:
            StreamRunner(Broken(messages(3)), pipeline()[0]).poll_once()
        assert "redelivered" in caught.value.remedy

    def test_a_transport_error_is_not_retried_here(self) -> None:
        """A retry policy belongs to the transport, which knows whether the
        broker is unreachable or the request was malformed. A loop that retried
        everything would retry a poison request forever."""
        calls = []

        class Broken(MemoryTransport):
            def poll(self, max_messages):
                calls.append(1)
                raise OSError("no")

        with pytest.raises(TransportError):
            StreamRunner(Broken(), pipeline()[0]).poll_once()
        assert len(calls) == 1


class TestTheLoop:
    def test_it_drains_a_backlog(self) -> None:
        transport = MemoryTransport(messages(25))
        reports = StreamRunner(transport, pipeline()[0], batch_size=10).run_until_idle()
        assert sum(r.polled for r in reports) == 25
        assert transport.remaining == 0

    def test_it_stops_when_a_poll_returns_nothing(self) -> None:
        transport = MemoryTransport(messages(3))
        reports = StreamRunner(transport, pipeline()[0], batch_size=10).run_until_idle()
        assert len(reports) == 1

    def test_the_batch_backstop_is_bounded(self) -> None:
        """A transport that keeps returning messages forever is a bug, and a
        loop with no bound turns it into a hang nobody can interrupt."""

        class Endless(StreamTransport):
            def poll(self, max_messages):
                return messages(1)

            def commit(self, positions):
                return None

        reports = StreamRunner(Endless(), pipeline()[0]).run_until_idle(max_batches=5)
        assert len(reports) == 5

    def test_a_zero_batch_size_is_refused(self) -> None:
        with pytest.raises(PramaError, match="reads nothing"):
            StreamRunner(MemoryTransport(), pipeline()[0], batch_size=0)


class TestTheSeamIsNarrow:
    def test_a_transport_cannot_produce(self) -> None:
        """A loop that both consumes and produces on the same broker is one
        topology change away from feeding itself."""
        assert not hasattr(StreamTransport, "produce")
        assert not hasattr(StreamTransport, "send")

    def test_no_broker_client_is_imported(self) -> None:
        """The transport that talks to a real broker belongs to the deployment,
        where the organisation's security and partition-assignment policy
        already lives."""
        import ast
        import pathlib

        from prama.execute import transport as module

        tree = ast.parse(pathlib.Path(module.__file__).read_text())
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert not {"kafka", "confluent_kafka", "aiokafka", "pyflink"} & imported

    def test_close_is_optional(self) -> None:
        """A transport holding no resource should not be made to write an empty
        override."""
        transport = MemoryTransport()
        transport.close()
        transport.close()
        assert transport.closed
