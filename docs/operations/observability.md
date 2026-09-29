<img src="../assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

*Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.*

---

# Observability

How to watch Prama itself. These are signals about the platform (runs, latency, the
scheduler, anchors, models), not about your data, and none of them is ever an input to a
data quality score.

## Endpoints

| Endpoint | For | What it checks |
|---|---|---|
| `GET /livez` | Kubernetes liveness | The process answers. Touches nothing else. |
| `GET /readyz` | Kubernetes readiness | The database answers and its schema is the one the code was built for. Returns 503 with the reason when not. |
| `GET /metrics` | Prometheus | Operational metrics in the text exposition format. The [metrics reference](metrics-reference.md) lists every metric, generated from the code. |
| `GET /api/v1/health` | API clients | As before: version, schema and dialect. |

**Why liveness and readiness differ.** A database outage makes every pod unready, so traffic
stops. It does not make them unlive, so Kubernetes doesn't restart pods that are healthy. A
restart can't repair a database; it only turns one incident into two.

### Protecting `/metrics`

It's open by default, which is usual inside a cluster. To require a bearer token, put it in
the untracked local configuration, never in `application.yaml`:

```yaml
# config/application.local.yaml
observability:
  metrics:
    token: "a-long-random-string"
```

Set `observability.metrics.enabled: false` to turn the endpoint off.

## What is measured

The labels name *kinds*, never a control, a dataset or a tenant, so the number of series
doesn't grow with the estate:

- **Runs and verdicts.** Runs started, and verdicts by verdict and assertion kind (check,
  referential, unique key, reconcile, freshness, delegate, custom SQL).
- **Durations.** Per control, per run, and per HTTP route template (`/datasets/{id}`, never
  the raw path).
- **The platform:**
  - scheduler ticks (ran, skipped for want of the lease, failed);
  - evidence records appended;
  - evidence anchors (anchored, failed);
  - delegate outcomes (measured, timeout, failed);
  - model calls and model spend by purpose;
  - OpenLineage delivery.

Each metric caps its series at 200; past that, new label values fold into `other`.
`prama_metric_series_folded_total` counts the fold, so a cardinality leak is visible
rather than silent.

## Traces

Spans for each run and each control, with the control, the dataset, its kind and its
verdict as attributes. Controls nest under their run. They go to any OpenTelemetry collector
over OTLP/HTTP:

```bash
pip install 'prama[otel]'
```

```yaml
observability:
  tracing:
    exporter: otlp
    endpoint: http://otel-collector:4318/v1/traces
    region: eu-west-1        # where the collector is, for the residency gate
```

What leaves is span names, durations and those attributes, with no row of data. It is a
declared egress point (`telemetry-export`), checked against the residency gate when tracing
starts. Asking for `otlp` without the extra installed refuses to start; it never traces
nothing silently.

## OpenLineage

Each run publishes a START event and then a final event, carrying each dataset's assertions
and whether they held, to any OpenLineage endpoint (Marquez, say):

```yaml
observability:
  openlineage:
    url: http://marquez:5000/api/v1/lineage
```

It is a declared egress point (`lineage-export`). A collector that is down does not fail a
run: the event is counted as not delivered and logged. The evidence ledger, not the
collector, is the record.

## Kubernetes

The chart probes `/livez` and `/readyz`, and offers:

```yaml
metrics:
  tokenSecret: ""              # a Secret with key metrics-token, if /metrics is protected
  serviceMonitor:
    enabled: true              # needs the Prometheus Operator
    labels: {release: kube-prometheus-stack}
  grafanaDashboard:
    enabled: true              # a ConfigMap the Grafana sidecar loads
tracing:
  exporter: otlp               # the image needs the otel extra
  endpoint: http://otel-collector:4318/v1/traces
openlineage:
  url: http://marquez:5000/api/v1/lineage
```

The dashboard (`deploy/helm/prama/dashboards/prama.json`) has panels for verdicts, control
and HTTP latency, the scheduler, anchors, delegates, model calls and spend, and lineage
delivery. A test checks that every metric it queries is one the code exports.

## Alerts worth having

```yaml
- alert: PramaSchedulerFailing
  expr: increase(prama_scheduler_ticks_total{outcome="failed"}[30m]) > 0
- alert: PramaAnchorFailing
  expr: increase(prama_evidence_anchors_total{status="failed"}[1h]) > 0
  # evidence written since the last anchor is unwitnessed until one succeeds
- alert: PramaDelegateTimeouts
  expr: increase(prama_delegate_runs_total{outcome="timeout"}[1h]) > 0
- alert: PramaServerErrors
  expr: sum(rate(prama_http_requests_total{status="5xx"}[5m])) > 0
- alert: PramaCardinalityLeak
  expr: increase(prama_metric_series_folded_total[1h]) > 0
```

A run whose verdicts are mostly `error` is a platform problem, not a data problem. Alert on
`rate(prama_control_verdicts_total{verdict="error"}[15m])` separately from failures.
