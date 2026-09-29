"""Prama's own operational metrics, in the Prometheus text exposition format.

Counters, gauges and histograms, rendered by `render()` for ``GET /metrics``.
Written directly rather than through a client library: the format is a page of
text, and a dependency whose job is to print it is not worth its weight.

**Cardinality is bounded by construction.** Labels name kinds (a verdict, an
assertion kind, a route template, a purpose), never a control, a dataset, a
tenant or a raw path: those grow with the estate, and a series per control is
how a metrics system falls over. Each metric also caps its series; past the cap
new label values fold into ``other``, and the fold is itself counted
(``prama_metric_series_folded_total``), so a cardinality leak is visible
rather than silent.

These are measurements *of Prama*. They are never inputs to a data quality
score, and nothing here is read by a control.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager

#: Past this many label combinations, new ones fold into "other".
MAX_SERIES = 200
#: The cap for the HTTP metrics, whose route label is a route *template*. Those
#: are bounded by the routing table rather than by the estate, and the table
#: now holds several hundred templates across the API and the console; at 200
#: the cap folded real routes into "other" and the per-route series went dark.
#: Templates x methods x five status classes stays well under this.
MAX_ROUTE_SERIES = 4000
#: Seconds. Control and HTTP durations sit between a millisecond and a few minutes.
DEFAULT_BUCKETS: tuple[float, ...] = (
    0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 300.0,
)  # fmt: skip

Labels = tuple[str, ...]


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _format(value: float) -> str:
    if math.isinf(value):
        return "+Inf" if value > 0 else "-Inf"
    return repr(float(value)) if not float(value).is_integer() else str(int(value))


class _Metric:
    kind = ""

    def __init__(
        self,
        name: str,
        help: str,  # noqa: A002
        labels: Sequence[str] = (),
        *,
        max_series: int | None = None,
    ) -> None:
        self.name, self.help, self.labels = name, help, tuple(labels)
        #: None means the module's MAX_SERIES, read when it applies.
        self.max_series = max_series
        self._lock = threading.Lock()
        self._folded = 0

    def _key(self, values: dict[str, str], known: Mapping[Labels, object]) -> Labels:
        if set(values) != set(self.labels):
            raise ValueError(f"{self.name} takes labels {self.labels}, not {sorted(values)}")
        key = tuple(str(values[label]) for label in self.labels)
        cap = self.max_series if self.max_series is not None else MAX_SERIES
        if key not in known and len(known) >= cap:
            self._folded += 1
            return tuple("other" for _ in self.labels)
        return key

    def _label_text(self, key: Labels, extra: str = "") -> str:
        parts = [f'{name}="{_escape(value)}"' for name, value in zip(self.labels, key, strict=True)]
        if extra:
            parts.append(extra)
        return "{" + ",".join(parts) + "}" if parts else ""

    def lines(self) -> list[str]:
        raise NotImplementedError


class Counter(_Metric):
    """A count that only goes up."""

    kind = "counter"

    def __init__(
        self,
        name: str,
        help: str,  # noqa: A002
        labels: Sequence[str] = (),
        *,
        max_series: int | None = None,
    ) -> None:
        super().__init__(name, help, labels, max_series=max_series)
        self._values: dict[Labels, float] = {}

    def inc(self, amount: float = 1.0, **labels: str) -> None:
        if amount < 0:
            raise ValueError("a counter only goes up")
        with self._lock:
            key = self._key(labels, self._values)
            self._values[key] = self._values.get(key, 0.0) + amount

    def value(self, **labels: str) -> float:
        return self._values.get(tuple(str(labels[k]) for k in self.labels), 0.0)

    def lines(self) -> list[str]:
        with self._lock:
            items = sorted(self._values.items())
            return [f"{self.name}{self._label_text(k)} {_format(v)}" for k, v in items]


class Gauge(_Metric):
    """A value that goes up and down."""

    kind = "gauge"

    def __init__(self, name: str, help: str, labels: Sequence[str] = ()) -> None:  # noqa: A002
        super().__init__(name, help, labels)
        self._values: dict[Labels, float] = {}

    def set(self, value: float, **labels: str) -> None:
        with self._lock:
            self._values[self._key(labels, self._values)] = float(value)

    def value(self, **labels: str) -> float:
        return self._values.get(tuple(str(labels[k]) for k in self.labels), 0.0)

    def lines(self) -> list[str]:
        with self._lock:
            items = sorted(self._values.items())
            return [f"{self.name}{self._label_text(k)} {_format(v)}" for k, v in items]


class Histogram(_Metric):
    """Observations in cumulative buckets, with their sum and count."""

    kind = "histogram"

    def __init__(
        self,
        name: str,
        help: str,  # noqa: A002
        labels: Sequence[str] = (),
        buckets: Sequence[float] = DEFAULT_BUCKETS,
        *,
        max_series: int | None = None,
    ) -> None:
        super().__init__(name, help, labels, max_series=max_series)
        self.buckets = tuple(sorted(buckets))
        self._counts: dict[Labels, list[int]] = {}
        self._sums: dict[Labels, float] = {}

    def observe(self, value: float, **labels: str) -> None:
        with self._lock:
            key = self._key(labels, self._counts)
            counts = self._counts.setdefault(key, [0] * (len(self.buckets) + 1))
            for index, bound in enumerate(self.buckets):
                if value <= bound:
                    counts[index] += 1
            counts[-1] += 1  # +Inf
            self._sums[key] = self._sums.get(key, 0.0) + value

    @contextmanager
    def time(self, **labels: str) -> Iterator[None]:
        started = time.perf_counter()
        try:
            yield
        finally:
            self.observe(time.perf_counter() - started, **labels)

    def count(self, **labels: str) -> int:
        counts = self._counts.get(tuple(str(labels[k]) for k in self.labels))
        return counts[-1] if counts else 0

    def lines(self) -> list[str]:
        out = []
        with self._lock:
            for key, counts in sorted(self._counts.items()):
                for bound, count in zip((*self.buckets, math.inf), counts, strict=True):
                    le = f'le="{_format(bound)}"'
                    out.append(f"{self.name}_bucket{self._label_text(key, le)} {count}")
                out.append(f"{self.name}_sum{self._label_text(key)} {_format(self._sums[key])}")
                out.append(f"{self.name}_count{self._label_text(key)} {counts[-1]}")
        return out


class Registry:
    """The metrics one process exposes."""

    def __init__(self) -> None:
        self._metrics: dict[str, _Metric] = {}
        self._lock = threading.Lock()

    def _add(self, metric: _Metric) -> _Metric:
        with self._lock:
            existing = self._metrics.get(metric.name)
            if existing is not None:
                return existing
            self._metrics[metric.name] = metric
            return metric

    def counter(
        self,
        name: str,
        help: str,  # noqa: A002
        labels: Sequence[str] = (),
        *,
        max_series: int | None = None,
    ) -> Counter:
        metric = self._add(Counter(name, help, labels, max_series=max_series))
        assert isinstance(metric, Counter)
        return metric

    def gauge(self, name: str, help: str, labels: Sequence[str] = ()) -> Gauge:  # noqa: A002
        metric = self._add(Gauge(name, help, labels))
        assert isinstance(metric, Gauge)
        return metric

    def histogram(
        self,
        name: str,
        help: str,  # noqa: A002
        labels: Sequence[str] = (),
        buckets: Sequence[float] = DEFAULT_BUCKETS,
        *,
        max_series: int | None = None,
    ) -> Histogram:
        metric = self._add(Histogram(name, help, labels, buckets, max_series=max_series))
        assert isinstance(metric, Histogram)
        return metric

    def render(self) -> str:
        """The whole registry, as Prometheus text exposition format 0.0.4."""
        lines: list[str] = []
        folded = 0
        for name in sorted(self._metrics):
            metric = self._metrics[name]
            folded += metric._folded
            lines.append(f"# HELP {name} {metric.help}")
            lines.append(f"# TYPE {name} {metric.kind}")
            lines.extend(metric.lines())
        lines.append(
            "# HELP prama_metric_series_folded_total Observations folded into 'other' "
            "because a metric reached its series cap."
        )
        lines.append("# TYPE prama_metric_series_folded_total counter")
        lines.append(f"prama_metric_series_folded_total {folded}")
        return "\n".join(lines) + "\n"


#: The process's registry, and the metrics Prama records into it.
REGISTRY = Registry()

BUILD = REGISTRY.gauge("prama_build_info", "The running build; always 1.", ("version",))
RUNS = REGISTRY.counter("prama_control_runs_total", "Control runs started.", ("trigger",))
VERDICTS = REGISTRY.counter(
    "prama_control_verdicts_total", "Verdicts recorded, by verdict and assertion kind.",
    ("verdict", "kind"),
)  # fmt: skip
CONTROL_SECONDS = REGISTRY.histogram(
    "prama_control_duration_seconds", "Time from compiling a control to recording it.", ("kind",)
)
RUN_SECONDS = REGISTRY.histogram(
    "prama_run_duration_seconds", "Time for a whole run over one source.", ("trigger",)
)
EVIDENCE = REGISTRY.counter("prama_evidence_records_total", "Evidence records appended.")
ANCHORS = REGISTRY.counter(
    "prama_evidence_anchors_total", "Attempts to anchor the chain head, by outcome.", ("status",)
)
SCHEDULER = REGISTRY.counter(
    "prama_scheduler_ticks_total", "Scheduler ticks, by outcome.", ("outcome",)
)
DELEGATES = REGISTRY.counter(
    "prama_delegate_runs_total", "Delegate measurements, by outcome.", ("outcome",)
)
LLM_CALLS = REGISTRY.counter(
    "prama_llm_calls_total", "Model calls through the gateway, by purpose and outcome.",
    ("purpose", "outcome"),
)  # fmt: skip
LLM_COST = REGISTRY.counter(
    "prama_llm_cost_micros_total", "Model spend in millionths of the ledger's currency.",
    ("purpose",),
)  # fmt: skip
HTTP_REQUESTS = REGISTRY.counter(
    "prama_http_requests_total", "HTTP requests, by method, route template and status class.",
    ("method", "route", "status"), max_series=MAX_ROUTE_SERIES,
)  # fmt: skip
HTTP_SECONDS = REGISTRY.histogram(
    "prama_http_request_duration_seconds", "HTTP request latency, by route template.", ("route",),
    max_series=MAX_ROUTE_SERIES,
)  # fmt: skip
