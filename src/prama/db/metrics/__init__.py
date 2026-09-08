"""The metric history store: every number Prama computes about data.

Append-only and columnar, and it lives under ``prama.db`` because it is Prama's
own store. The platform has more than one store; it has exactly one package that
owns persistence.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.db.metrics.model import CORE_METRICS, MetricPoint, MetricSeries
from prama.db.metrics.store import (
    MemoryMetricStore,
    MetricStore,
    ParquetMetricStore,
    retention_cutoff,
)

__all__ = [
    "CORE_METRICS",
    "MemoryMetricStore",
    "MetricPoint",
    "MetricSeries",
    "MetricStore",
    "ParquetMetricStore",
    "retention_cutoff",
]
