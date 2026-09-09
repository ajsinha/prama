"""Rendering: charts, and the print artefacts that use them.

One renderer for the console and for the PDF, so an attestation pack cannot
disagree with the screen it was produced from.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.report.charts import (
    Axis,
    Series,
    bars,
    distribution,
    score_ring,
    sparkline,
    table_alternative,
)
from prama.report.palette import PRINT, SCREEN, UNVERIFIED_GREY, Palette

__all__ = [
    "PRINT",
    "SCREEN",
    "UNVERIFIED_GREY",
    "Axis",
    "Palette",
    "Series",
    "bars",
    "distribution",
    "score_ring",
    "sparkline",
    "table_alternative",
]
