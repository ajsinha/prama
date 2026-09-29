"""Spans to any OpenTelemetry collector, over OTLP/HTTP.

The `otel` extra (``pip install 'prama[otel]'``) brings the OpenTelemetry SDK;
without it this tracer refuses to start rather than silently tracing nothing.
It keeps Prama's span names and attributes (`prama.telemetry.trace`) and adds
what OpenTelemetry has that the seam did not: nesting, so a run's controls are
children of the run.

What leaves is span names, durations and attributes: control ids, dataset
names, verdicts. No row of data. It still leaves, so it is a declared egress
point, checked against the residency gate when the tracer starts.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Iterator
from typing import Any

from prama.core.errors import ConfigError
from prama.security.egress import Gate
from prama.telemetry.trace import Span, Tracer


class OtlpTracer(Tracer):
    """Prama's spans, as OpenTelemetry spans."""

    def __init__(
        self,
        *,
        endpoint: str = "",
        service_name: str = "prama",
        region: str = "",
        exporter: Any = None,
    ) -> None:
        try:
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
        except ImportError as exc:
            raise ConfigError(
                "tracing is set to otlp and the OpenTelemetry SDK is not installed",
                remedy="Install the extra: pip install 'prama[otel]', or set "
                "observability.tracing.exporter to none.",
            ) from exc
        Gate.for_tenant(None).require(
            "telemetry-export", destination=region, subject="Prama's own spans"
        )
        if exporter is None:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            exporter = OTLPSpanExporter(endpoint=endpoint or None)
            processor: Any = BatchSpanProcessor(exporter)
        else:
            processor = SimpleSpanProcessor(exporter)  # a test's in-memory exporter
        self.provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
        self.provider.add_span_processor(processor)
        self._tracer = self.provider.get_tracer("prama")

    def record(self, span: Span) -> None:
        """A span recorded after the fact: sent with the times it ran."""
        end = time.time_ns()
        start = end - int(span.duration_ms * 1_000_000)
        otel = self._tracer.start_span(span.name, start_time=start, attributes=_clean(span))
        if span.error:
            _fail(otel, span.error)
        otel.end(end_time=end)

    @contextlib.contextmanager
    def span(self, name: str, **attributes: Any) -> Iterator[Span]:
        """A live span, current while the block runs, so inner spans nest under it."""
        ours = Span(name=name, attributes=dict(attributes), started=time.monotonic())
        with self._tracer.start_as_current_span(name, attributes=_clean(ours)) as otel:
            try:
                yield ours
            except Exception as exc:
                ours.error = f"{type(exc).__name__}: {exc}"
                _fail(otel, ours.error)
                raise
            finally:
                ours.duration_ms = (time.monotonic() - ours.started) * 1000
                otel.set_attributes(_clean(ours))

    def shutdown(self) -> None:
        self.provider.shutdown()


def _clean(span: Span) -> dict[str, Any]:
    """Attributes OpenTelemetry accepts: strings, numbers and booleans."""
    out: dict[str, Any] = {}
    for key, value in span.attributes.items():
        out[f"prama.{key}"] = value if isinstance(value, str | bool | int | float) else str(value)
    return out


def _fail(otel: Any, error: str) -> None:
    from opentelemetry.trace import Status, StatusCode

    otel.set_status(Status(StatusCode.ERROR, error[:500]))
