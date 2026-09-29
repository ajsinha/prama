"""OpenLineage run events to a collector over HTTP (Marquez, or any OpenLineage endpoint).

What leaves is a run's verdicts per dataset (`prama.telemetry.lineage`): dataset
names and whether each assertion held. No row of data. It is a declared egress
point, checked against the residency gate before anything is sent.

A collector that is down does not fail a run: the event is logged as not
delivered and counted (``prama_openlineage_events_total{outcome="failed"}``).
The evidence ledger, not the collector, is the record.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import urllib.request

from prama.core.log import get_logger
from prama.security.egress import Gate
from prama.telemetry.lineage import LineageEmitter, RunEvent
from prama.telemetry.metrics import REGISTRY

_log = get_logger(__name__)
EVENTS = REGISTRY.counter(
    "prama_openlineage_events_total", "OpenLineage events, by outcome.", ("outcome",)
)


class HttpEmitter(LineageEmitter):
    """POSTs each event as JSON to *url*."""

    def __init__(self, url: str, *, region: str = "", timeout: float = 10.0) -> None:
        self._url, self._region, self._timeout = url, region, timeout
        self._gate = Gate.for_tenant(None)

    def emit(self, event: RunEvent) -> None:
        self._gate.require(
            "lineage-export", destination=self._region, subject="OpenLineage run events"
        )
        request = urllib.request.Request(
            self._url,
            data=event.to_json().encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                response.read()
        except OSError as exc:
            EVENTS.inc(outcome="failed")
            _log.warning("OpenLineage event not delivered to %s: %s", self._url, exc)
            return
        EVENTS.inc(outcome="delivered")
