"""The engine-neutral plan every backend compiles from.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from prama.ir.lower import SCANNED, VIOLATING, Lowerer, lower
from prama.ir.model import (
    IR_VERSION,
    Comparator,
    ControlPlan,
    EvidencePolicy,
    Expr,
    IrNode,
    Metric,
    MetricAggregate,
    Provenance,
    Scope,
    Threshold,
    Verdict,
)

__all__ = [
    "IR_VERSION",
    "SCANNED",
    "VIOLATING",
    "Comparator",
    "ControlPlan",
    "EvidencePolicy",
    "Expr",
    "IrNode",
    "Lowerer",
    "Metric",
    "MetricAggregate",
    "Provenance",
    "Scope",
    "Threshold",
    "Verdict",
    "lower",
]
