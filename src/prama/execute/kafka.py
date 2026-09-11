"""A Kafka :class:`~prama.execute.transport.StreamTransport`.

:mod:`prama.execute.transport` holds the ordering rule — enforce, then commit —
and deliberately imports no broker client so that rule can be tested without
one. This is the implementation that does talk to a broker, kept in its own
module for exactly that reason.

Three things Kafka gets to be wrong about, each of which loses data quietly:

**A committed offset is the *next* one to read, not the last one read.**
Committing the offset of the message you just handled replays it forever;
committing ``offset + 1`` is correct. This is the single most common Kafka bug
and it is invisible in a test that only ever consumes once, so the suite here
consumes, commits, reconnects with the same group, and asserts the message does
not come back.

**Auto-commit is refused, not merely defaulted off.** ``enable.auto.commit``
commits on a timer, in a background thread, with no idea whether enforcement
happened — which is the precise failure the whole module exists to prevent.
Passing it as true is a configuration error and is rejected at construction
rather than silently overridden, because an operator who set it deliberately
needs to know it cannot mean what they wanted.

**A message that will not deserialise is still a message.** Dropping it removes
the only evidence of what the sender sent. It arrives with its raw bytes and a
note, and the pipeline dead-letters it like any other unreadable message.

Needs the ``kafka`` extra. Without it this refuses by name rather than
pretending a broker is unreachable.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from prama.core.errors import PramaError
from prama.execute.transport import Position, StreamMessage, StreamTransport, TransportError

__all__ = ["KafkaTransport", "KafkaUnavailable"]


class KafkaUnavailable(PramaError):
    """The ``kafka`` extra is not installed."""

    code = "STREAM.KAFKA_UNAVAILABLE"


def _consumer_class() -> Any:
    try:
        from confluent_kafka import Consumer
    except ImportError as exc:  # pragma: no cover - exercised by the extra being absent
        raise KafkaUnavailable(
            "the Kafka transport needs the 'kafka' extra, which is not installed",
            remedy='Install it: pip install -e ".[kafka]".',
        ) from exc
    return Consumer


class KafkaTransport(StreamTransport):
    """Consume-only, manual-commit, and loud about both."""

    def __init__(
        self,
        *,
        bootstrap_servers: str,
        group_id: str,
        topics: Sequence[str],
        config: dict[str, Any] | None = None,
        poll_timeout: float = 1.0,
    ) -> None:
        settings = dict(config or {})

        if str(settings.get("enable.auto.commit", "false")).lower() in ("true", "1"):
            raise PramaError(
                "enable.auto.commit is set, and this transport cannot honour it",
                code="STREAM.AUTO_COMMIT",
                remedy=(
                    "Remove it. Auto-commit commits on a timer from a background "
                    "thread with no idea whether enforcement happened, which is "
                    "the exact failure this pipeline exists to prevent: a message "
                    "marked done that was never checked and is never redelivered."
                ),
            )

        consumer = _consumer_class()
        settings.update(
            {
                "bootstrap.servers": bootstrap_servers,
                "group.id": group_id,
                "enable.auto.commit": False,
            }
        )
        settings.setdefault("auto.offset.reset", "earliest")
        self._consumer = consumer(settings)
        self._consumer.subscribe(list(topics))
        self._poll_timeout = poll_timeout
        self._closed = False

    def poll(self, max_messages: int) -> Sequence[StreamMessage]:
        batch: list[StreamMessage] = []
        while len(batch) < max_messages:
            record = self._consumer.poll(self._poll_timeout if not batch else 0.0)
            if record is None:
                break
            error = record.error()
            if error is not None:
                raise TransportError(
                    f"the broker returned an error: {error}",
                    remedy=(
                        "Nothing was enforced and nothing was committed for this "
                        "batch, so no message was lost."
                    ),
                    context={"error": str(error)},
                )
            batch.append(self._message(record))
        return batch

    def _message(self, record: Any) -> StreamMessage:
        raw = record.value()
        headers = {k: _text(v) for k, v in (record.headers() or [])}
        try:
            payload = json.loads(raw) if raw else {}
            if not isinstance(payload, dict):
                payload = {"_raw": payload}
        except (ValueError, TypeError):
            # Not dropped. An unparseable message is a finding about the sender,
            # and discarding it removes the only evidence of what they sent.
            payload = {
                "_unreadable": True,
                "_raw": _text(raw),
                "_why": "the message body is not JSON",
            }
        return StreamMessage(
            position=Position(
                topic=record.topic(), partition=record.partition(), offset=record.offset()
            ),
            payload=payload,
            key=_text(record.key()),
            headers=headers,
        )

    def commit(self, positions: Sequence[Position]) -> None:
        """Commit through these positions.

        ``offset + 1``, because a committed offset in Kafka is the *next* one to
        read. Committing the offset just handled makes the consumer replay it on
        every restart, forever — the message is enforced again and again and the
        group never advances.
        """
        from confluent_kafka import TopicPartition

        self._consumer.commit(
            offsets=[TopicPartition(p.topic, p.partition, p.offset + 1) for p in positions],
            asynchronous=False,
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._consumer.close()


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)
