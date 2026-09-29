"""Which exporters this process uses, from configuration.

    observability:
      tracing:     {exporter: none | otlp, endpoint, service_name, region}
      openlineage: {url, namespace, region, timeout}

Both default to off. Traces and OpenLineage events are sent only to where the
operator points them, through declared egress points behind the residency gate,
and neither carries a row of data: spans name controls and datasets, events
carry verdicts.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama.core.errors import ConfigError
from prama.telemetry.lineage import Lineage
from prama.telemetry.trace import NullTracer, use

_lineage: list[Lineage] = [Lineage()]


def lineage() -> Lineage:
    """The process's OpenLineage publisher: silent unless configured."""
    return _lineage[0]


def configure(config: Any) -> None:
    """Install the configured tracer and lineage emitter. Idempotent."""
    exporter = str(config.get("observability.tracing.exporter", "none") or "none")
    if exporter == "none":
        use(NullTracer())
    elif exporter == "otlp":
        from prama.telemetry.otlp import OtlpTracer

        use(
            OtlpTracer(
                endpoint=str(config.get("observability.tracing.endpoint", "") or ""),
                service_name=str(config.get("observability.tracing.service_name", "prama")),
                region=str(config.get("observability.tracing.region", "") or ""),
            )
        )
    else:
        raise ConfigError(
            f"no tracing exporter called {exporter!r}",
            remedy="Set observability.tracing.exporter to none or otlp.",
        )
    url = str(config.get("observability.openlineage.url", "") or "")
    namespace = str(config.get("observability.openlineage.namespace", "prama") or "prama")
    if url:
        from prama.telemetry.openlineage_http import HttpEmitter

        _lineage[0] = Lineage(
            HttpEmitter(
                url,
                region=str(config.get("observability.openlineage.region", "") or ""),
                timeout=float(config.get("observability.openlineage.timeout", 10) or 10),
            ),
            namespace=namespace,
        )
    else:
        _lineage[0] = Lineage(namespace=namespace)
