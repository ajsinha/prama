"""The Kafka transport, against a real broker.

Skipped unless PRAMA_TEST_KAFKA_BOOTSTRAP names one. Everything here is about
the things a broker does that an in-memory double cannot: offset semantics,
group state surviving a reconnect, and partitions that genuinely are separate.

    docker run -d --name prama-kafka -p 19092:19092 ... apache/kafka:3.8.0
    PRAMA_TEST_KAFKA_BOOTSTRAP=127.0.0.1:19092 pytest -q tests/execute/test_kafka.py

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
import os
import time
import uuid

import pytest

from prama.core.errors import PramaError
from prama.execute.actions import Action
from prama.execute.inflight import Pipeline
from prama.execute.stream import StreamAssertion
from prama.execute.transport import StreamRunner
from prama.ir.resolve import resolved
from prama.pql import parse_control

BOOTSTRAP = os.environ.get("PRAMA_TEST_KAFKA_BOOTSTRAP", "")

pytestmark = pytest.mark.skipif(
    not BOOTSTRAP, reason="set PRAMA_TEST_KAFKA_BOOTSTRAP to run against a broker"
)

NOT_NULL = (
    "CHECK payments.amount IS NOT NULL SEVERITY critical DIMENSION completeness BECAUSE 'CDE'"
)


@pytest.fixture
def topic() -> str:
    """A topic per test, so one test's offsets cannot explain another's pass."""
    from confluent_kafka.admin import AdminClient, NewTopic

    name = f"prama-test-{uuid.uuid4().hex[:12]}"
    admin = AdminClient({"bootstrap.servers": BOOTSTRAP})
    for future in admin.create_topics([NewTopic(name, num_partitions=3)]).values():
        future.result(timeout=30)
    yield name
    admin.delete_topics([name])


def produce(topic: str, payloads: list[dict], *, raw: list[bytes] | None = None) -> None:
    from confluent_kafka import Producer

    producer = Producer({"bootstrap.servers": BOOTSTRAP})
    for index, payload in enumerate(payloads):
        producer.produce(topic, key=f"k{index}", value=json.dumps(payload))
    for body in raw or []:
        producer.produce(topic, value=body)
    producer.flush(30)


def transport(topic: str, group: str):
    from prama.execute.kafka import KafkaTransport

    return KafkaTransport(
        bootstrap_servers=BOOTSTRAP,
        group_id=group,
        topics=[topic],
        poll_timeout=2.0,
    )


def pipeline(dead_letter=None) -> Pipeline:
    assertion = StreamAssertion(resolved(parse_control(NOT_NULL)))
    return Pipeline(
        [assertion], action=Action.QUARANTINE, dead_letter=dead_letter or (lambda _p, _r: True)
    )


def drain(runner: StreamRunner, *, expect: int, seconds: float = 30.0) -> int:
    """Poll until `expect` messages have been seen. Kafka assigns partitions
    asynchronously, so the first poll of a fresh group is routinely empty."""
    seen = 0
    deadline = time.time() + seconds
    while seen < expect and time.time() < deadline:
        seen += runner.poll_once().polled
    return seen


class TestOffsetSemantics:
    def test_a_committed_message_is_not_redelivered(self, topic: str) -> None:
        """The single most common Kafka bug: a committed offset is the *next*
        one to read, so committing the offset just handled replays it forever.
        Invisible unless you reconnect, which is why this test reconnects."""
        produce(topic, [{"amount": 10.0 + n, "id": n} for n in range(6)])
        group = f"g-{uuid.uuid4().hex[:8]}"

        first = transport(topic, group)
        try:
            assert drain(StreamRunner(first, pipeline(), batch_size=10), expect=6) == 6
        finally:
            first.close()

        second = transport(topic, group)
        try:
            again = drain(StreamRunner(second, pipeline(), batch_size=10), expect=1, seconds=8.0)
        finally:
            second.close()
        assert again == 0, f"{again} message(s) came back after being committed"

    def test_an_uncommitted_batch_is_redelivered(self, topic: str) -> None:
        """The other half, and what makes the first test mean something: if
        nothing were ever redelivered the assertion above would pass for the
        wrong reason."""
        produce(topic, [{"amount": 10.0 + n, "id": n} for n in range(4)])
        group = f"g-{uuid.uuid4().hex[:8]}"

        first = transport(topic, group)
        try:
            polled = 0
            deadline = time.time() + 30
            while polled < 4 and time.time() < deadline:
                polled += len(first.poll(10))
            assert polled == 4
        finally:
            first.close()  # nothing committed

        second = transport(topic, group)
        try:
            assert drain(StreamRunner(second, pipeline(), batch_size=10), expect=4) == 4
        finally:
            second.close()


class TestEnforcementAcrossPartitions:
    def test_every_message_is_judged_and_the_bad_ones_dead_lettered(self, topic: str) -> None:
        produce(
            topic,
            [{"amount": None if n % 3 == 0 else 10.0 + n, "id": n} for n in range(9)],
        )
        held: list[tuple[dict, str]] = []
        runner = StreamRunner(
            transport(topic, f"g-{uuid.uuid4().hex[:8]}"),
            pipeline(lambda payload, reason: held.append((payload, reason)) or True),
            batch_size=10,
        )
        assert drain(runner, expect=9) == 9
        assert len(held) == 3

    def test_offsets_commit_per_partition(self, topic: str) -> None:
        """A single 'last offset' across a three-partition batch is meaningless,
        and committing one partition's against another's silently skips data."""
        produce(topic, [{"amount": 10.0 + n, "id": n} for n in range(9)])
        group = f"g-{uuid.uuid4().hex[:8]}"
        source = transport(topic, group)
        try:
            runner = StreamRunner(source, pipeline(), batch_size=10)
            committed: set[tuple[str, int]] = set()
            deadline = time.time() + 30
            seen = 0
            while seen < 9 and time.time() < deadline:
                result = runner.poll_once()
                seen += result.polled
                committed.update((p.topic, p.partition) for p in result.committed)
            assert seen == 9
            assert len(committed) == 3, f"committed on {committed}"
        finally:
            source.close()


class TestAwkwardMessages:
    def test_a_message_that_is_not_json_is_kept_not_dropped(self, topic: str) -> None:
        """Discarding it removes the only evidence of what the sender sent."""
        produce(topic, [{"amount": 1.0}], raw=[b"this is not json at all"])
        held: list[tuple[dict, str]] = []
        runner = StreamRunner(
            transport(topic, f"g-{uuid.uuid4().hex[:8]}"),
            pipeline(lambda payload, reason: held.append((payload, reason)) or True),
            batch_size=10,
        )
        assert drain(runner, expect=2) == 2
        unreadable = [p for p, _ in held if p.get("_unreadable")]
        assert unreadable, f"the unparseable message was lost; dead letter held {held}"
        assert "this is not json" in unreadable[0]["_raw"]

    def test_the_key_and_headers_survive(self, topic: str) -> None:
        produce(topic, [{"amount": 1.0, "id": 0}])
        source = transport(topic, f"g-{uuid.uuid4().hex[:8]}")
        try:
            batch: list = []
            deadline = time.time() + 30
            while not batch and time.time() < deadline:
                batch = list(source.poll(10))
            assert batch[0].key == "k0"
            assert batch[0].position.topic == topic
        finally:
            source.close()


class TestConfigurationRefusals:
    def test_auto_commit_is_refused_rather_than_overridden(self) -> None:
        """An operator who set it deliberately needs to know it cannot mean what
        they wanted: it commits on a timer with no idea whether enforcement
        happened."""
        from prama.execute.kafka import KafkaTransport

        with pytest.raises(PramaError, match=r"auto\.commit") as caught:
            KafkaTransport(
                bootstrap_servers=BOOTSTRAP,
                group_id="g",
                topics=["t"],
                config={"enable.auto.commit": True},
            )
        assert "never checked and is never redelivered" in caught.value.remedy

    def test_the_seam_module_imports_no_broker_client(self) -> None:
        """The ordering rule has to stay testable without a broker, which is
        why the client lives in its own module."""
        import ast
        import pathlib

        from prama.execute import transport as seam

        tree = ast.parse(pathlib.Path(seam.__file__).read_text())
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert "confluent_kafka" not in imported
