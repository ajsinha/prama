"""Integrations: putting Prama's answers where people already look.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from prama.integrate.catalog import (
    Badge,
    CatalogTarget,
    RecordingTarget,
    Standing,
    WriteReport,
    badges_from,
)
from prama.integrate.operator import Plan, Step, Verb, plan
from prama.integrate.vendors import AlationTarget, CollibraTarget, DataHubTarget

__all__ = [
    "AlationTarget",
    "Badge",
    "CatalogTarget",
    "CollibraTarget",
    "DataHubTarget",
    "Plan",
    "RecordingTarget",
    "Standing",
    "Step",
    "Verb",
    "WriteReport",
    "badges_from",
    "plan",
]
