"""Spans, without requiring an exporter to exist.

Prama should be traceable — a run that takes four minutes should be
attributable to the query, the network or the judging — and it should not
require OpenTelemetry to be installed to start. A bank evaluating the platform
on a laptop and a bank running it on a fleet want the same code.

So tracing is a seam. The default records nothing and costs a function call;
an OpenTelemetry exporter, when one is configured, is a different implementation
of two methods. The span *names and attributes* are decided here, once, so they
do not drift between deployments — which is what makes a dashboard built for one
estate work on the next.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import contextlib
import dataclasses
import time
from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any


@dataclasses.dataclass(slots=True)
class Span:
    """One timed piece of work."""

    name: str
    attributes: dict[str, Any] = dataclasses.field(default_factory=dict)
    started: float = 0.0
    duration_ms: float = 0.0
    error: str = ""

    def set(self, **attributes: Any) -> Span:
        """Attach what was learned during the span, not only before it.

        A span that could only be described before it ran would have to guess
        the row count, and a trace whose attributes are guesses is a trace
        nobody can reason from.
        """
        self.attributes.update(attributes)
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "duration_ms": round(self.duration_ms, 3),
            "attributes": dict(sorted(self.attributes.items())),
            "error": self.error,
        }


class Tracer(ABC):
    """Where spans go."""

    @abstractmethod
    def record(self, span: Span) -> None: ...

    @contextlib.contextmanager
    def span(self, name: str, **attributes: Any) -> Iterator[Span]:
        """Time a block, and record it whether or not it succeeded.

        A span abandoned on an exception is the one you most want: it is the
        four-minute query that failed, and losing it leaves a gap exactly where
        the investigation starts.
        """
        span = Span(name=name, attributes=dict(attributes), started=time.monotonic())
        try:
            yield span
        except Exception as exc:
            span.error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            span.duration_ms = (time.monotonic() - span.started) * 1000
            self.record(span)


class NullTracer(Tracer):
    """Records nothing. The default, and the reason there is no dependency."""

    def record(self, span: Span) -> None:  # noqa: ARG002 - discarding is the point
        return None


class MemoryTracer(Tracer):
    """Keeps spans. For tests, and for a local run somebody is watching."""

    def __init__(self) -> None:
        self.spans: list[Span] = []

    def record(self, span: Span) -> None:
        self.spans.append(span)

    def named(self, name: str) -> list[Span]:
        return [s for s in self.spans if s.name == name]

    def slowest(self, count: int = 5) -> list[Span]:
        return sorted(self.spans, key=lambda s: -s.duration_ms)[:count]

    def __len__(self) -> int:
        return len(self.spans)


#: The tracer spans are recorded to. `NullTracer` unless observability
#: configures an exporter (`prama.telemetry.configure`).
_current: list[Tracer] = [NullTracer()]


def current() -> Tracer:
    """The process's tracer."""
    return _current[0]


def use(tracer: Tracer) -> Tracer:
    """Make *tracer* the process's tracer; returns the one it replaced."""
    previous, _current[0] = _current[0], tracer
    return previous


#: The span names Prama emits. Named here rather than at each call site, so a
#: dashboard built against one deployment works against the next — and so
#: renaming one is a change to a constant rather than a search.
RUN = "prama.run"
CONTROL = "prama.control"
CLAIM = "prama.claim"
COMPILE = "prama.compile"
EXECUTE = "prama.execute"
JUDGE = "prama.judge"
RECORD = "prama.record"
DELIVER = "prama.deliver"
