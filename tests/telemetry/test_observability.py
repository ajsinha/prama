"""Prama's own observability: Prometheus metrics, probes, spans and OpenLineage events.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import http.server
import json
import threading
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import pytest
from httpx import ASGITransport

from prama.api import create_app
from prama.core.config import Configuration
from prama.db import Database
from prama.execute import ControlRun
from prama.telemetry import metrics
from prama.telemetry.lineage import Lineage, MemoryEmitter
from prama.telemetry.trace import CONTROL, RUN, MemoryTracer, use

CLEAN = (
    "CHECK trades.notional IS NOT NULL SEVERITY critical DIMENSION completeness "
    "BECAUSE 'every trade has a notional'"
)


# -- the exposition format ----------------------------------------------------


def test_the_text_format_is_what_prometheus_parses() -> None:
    registry = metrics.Registry()
    runs = registry.counter("x_runs_total", "Runs.", ("trigger",))
    depth = registry.gauge("x_depth", "Depth.")
    seconds = registry.histogram("x_seconds", "Seconds.", ("kind",), buckets=(0.1, 1.0))
    runs.inc(trigger='say "hi"')
    depth.set(3)
    seconds.observe(0.5, kind="check")
    text = registry.render()
    assert "# TYPE x_runs_total counter" in text
    assert 'x_runs_total{trigger="say \\"hi\\""} 1' in text
    assert "x_depth 3" in text
    assert 'x_seconds_bucket{kind="check",le="0.1"} 0' in text
    assert 'x_seconds_bucket{kind="check",le="1"} 1' in text
    assert 'x_seconds_bucket{kind="check",le="+Inf"} 1' in text
    assert 'x_seconds_count{kind="check"} 1' in text
    assert text.endswith("\n")


def test_cardinality_is_capped_and_the_fold_is_counted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(metrics, "MAX_SERIES", 3)
    registry = metrics.Registry()
    hits = registry.counter("x_hits_total", "Hits.", ("route",))
    for i in range(10):
        hits.inc(route=f"/datasets/{i}")
    text = registry.render()
    assert 'x_hits_total{route="other"} 7' in text
    assert "prama_metric_series_folded_total 7" in text


def test_a_label_the_metric_does_not_take_is_refused() -> None:
    with pytest.raises(ValueError, match="takes labels"):
        metrics.Registry().counter("x_total", "X.", ("kind",)).inc(dataset="trades")


# -- the endpoints -------------------------------------------------------------


async def _client(config: Configuration, database: Database) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(config, database=database)
    async with (
        httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as http,
        app.router.lifespan_context(app),
    ):
        yield http


async def test_probes_and_metrics_answer(
    sqlite_config: Configuration, started_database: Database
) -> None:
    async for client in _client(sqlite_config, started_database):
        assert (await client.get("/livez")).json()["status"] == "alive"
        ready = await client.get("/readyz")
        assert ready.status_code == 200 and ready.json()["status"] == "ready"
        await client.get("/api/v1/health")
        scraped = await client.get("/metrics")
        assert scraped.status_code == 200
        assert scraped.headers["content-type"].startswith("text/plain; version=0.0.4")
        assert "prama_build_info{" in scraped.text
        # The route template, not the raw path.
        assert 'prama_http_requests_total{method="GET",route="/livez",status="2xx"}' in (
            scraped.text
        )


async def test_readiness_fails_when_the_database_does_not_answer(
    sqlite_config: Configuration, started_database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def down() -> dict[str, Any]:
        raise ConnectionError("no route to the database")

    async for client in _client(sqlite_config, started_database):
        monkeypatch.setattr(started_database, "health", down)
        ready = await client.get("/readyz")
        assert ready.status_code == 503 and "did not answer" in ready.json()["reason"]
        assert (await client.get("/livez")).status_code == 200  # alive, only not ready


async def test_a_metrics_token_is_required_when_set(
    sqlite_config: Configuration, started_database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = sqlite_config.get

    def get(path: str, default: Any = None) -> Any:
        return "s3cret-token" if path == "observability.metrics.token" else real(path, default)

    monkeypatch.setattr(sqlite_config, "get", get)
    async for client in _client(sqlite_config, started_database):
        assert (await client.get("/metrics")).status_code == 401
        allowed = await client.get("/metrics", headers={"Authorization": "Bearer s3cret-token"})
        assert allowed.status_code == 200


# -- a run: metrics, spans and lineage -------------------------------------------------


def _rows(**values: float) -> Any:
    def execute(_: str) -> list[dict[str, float]]:
        return [values]

    return execute


async def test_a_run_counts_verdicts_emits_spans_and_lineage(
    started_database: Database, tenant_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from prama.telemetry import setup

    async with started_database.unit_of_work() as uow:
        control, _ = await uow.controls.declare(tenant_id=tenant_id, identity="a", pql=CLEAN)
        await uow.controls.activate(str(control.id), tenant_id=tenant_id, approved_by="bo")
    tracer, emitter = MemoryTracer(), MemoryEmitter()
    previous = use(tracer)
    monkeypatch.setattr(setup, "_lineage", [Lineage(emitter)])
    before = metrics.VERDICTS.value(verdict="fail", kind="check")
    try:
        async with started_database.unit_of_work() as uow:
            await ControlRun(
                uow, tenant_id, execute=_rows(scanned_rows=10, violating_rows=2)
            ).execute_all()
    finally:
        use(previous)
    assert metrics.VERDICTS.value(verdict="fail", kind="check") == before + 1
    (control_span,) = tracer.named(CONTROL)
    assert control_span.attributes["verdict"] == "fail"
    assert control_span.attributes["dataset"] == "trades"
    assert tracer.named(RUN)
    kinds = [e.event_type.value for e in emitter.events]
    assert kinds[0] == "START" and kinds[-1] in ("FAIL", "COMPLETE")


# -- exporters ---------------------------------------------------------------------------


def test_otlp_spans_nest_a_control_under_its_run() -> None:
    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    from prama.telemetry.otlp import OtlpTracer

    exported = InMemorySpanExporter()
    tracer = OtlpTracer(exporter=exported)
    with tracer.span(RUN, run="r1"), tracer.span(CONTROL, control="c1") as span:
        span.set(verdict="pass")
    spans = {s.name: s for s in exported.get_finished_spans()}
    assert spans[CONTROL].parent.span_id == spans[RUN].context.span_id
    assert spans[CONTROL].attributes["prama.verdict"] == "pass"


@pytest.fixture
def collector() -> Iterator[tuple[str, list[dict[str, Any]]]]:
    received: list[dict[str, Any]] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers["Content-Length"]))
            received.append(json.loads(body))
            self.send_response(201)
            self.end_headers()

        def log_message(self, *_: Any) -> None:
            return None

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/api/v1/lineage", received
    finally:
        server.shutdown()


def test_openlineage_events_reach_a_collector_and_a_dead_one_fails_nothing(
    collector: tuple[str, list[dict[str, Any]]],
) -> None:
    from prama.telemetry.openlineage_http import EVENTS, HttpEmitter

    url, received = collector
    Lineage(HttpEmitter(url)).started(job="prama.run.duckdb", run_id="run:1", datasets=("trades",))
    assert received and received[0]["eventType"] == "START"
    assert received[0]["inputs"][0]["name"] == "trades"
    before = EVENTS.value(outcome="failed")
    Lineage(HttpEmitter("http://127.0.0.1:9/nowhere", timeout=1)).started(job="j")
    assert EVENTS.value(outcome="failed") == before + 1


def test_every_metric_the_dashboard_queries_exists() -> None:
    """A renamed metric leaves a panel silently empty. The shipped dashboard
    is checked against the registry the code actually exports."""
    import re
    from pathlib import Path

    import prama.telemetry.openlineage_http  # noqa: F401  (registers its counter)

    dashboard = Path(__file__).resolve().parents[2] / "deploy/helm/prama/dashboards/prama.json"
    exprs = [t["expr"] for p in json.loads(dashboard.read_text())["panels"] for t in p["targets"]]
    queried = {
        re.sub(r"_(bucket|sum|count)$", "", name)
        for expr in exprs
        for name in re.findall(r"prama_[a-z_]+", expr)
    }
    exported = set(metrics.REGISTRY._metrics) | {"prama_metric_series_folded_total"}
    assert queried and queried <= exported, sorted(queried - exported)


def test_the_http_metrics_have_room_for_every_route_template(
    sqlite_config: Configuration,
) -> None:
    """The route label is bounded by the routing table, and the cap must exceed it.

    At the old cap of 200 a long-running server folded real routes into "other"
    once the API grew past a few hundred endpoints, and per-route latency and
    error counts went dark. Three series per template (methods and status
    classes) is the least a route needs; the cap must cover that for every
    template the application serves, the console's included.
    """
    from starlette.routing import Route

    app = create_app(sqlite_config)
    templates = set(app.openapi()["paths"]) | {
        route.path for route in app.routes if isinstance(route, Route)
    }
    assert len(templates) > 200 // 3  # the counterfactual: the old cap could not hold them
    for metric in (metrics.HTTP_REQUESTS, metrics.HTTP_SECONDS):
        assert metric.max_series is not None
        assert metric.max_series >= 3 * len(templates), metric.name
