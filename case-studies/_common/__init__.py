"""Shared machinery for the case studies.

Nothing here is part of Prama. These are the pieces a case study needs and a
product does not: fabricated data with defects planted on purpose, and a
harness that drives Prama end to end so the reader can watch it work.

The one rule that matters across all three studies: **every planted defect is
declared up front, in the README and in the code, before Prama is pointed at
the data.** A demonstration that shows only what the tool found is a
demonstration you cannot check. These studies state what was planted, what was
found, and — the part that matters — what was *not*.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from _common.defects import Defect, DefectLog
from _common.estate import Dataset, declare_estate
from _common.harness import Harness, configure

__all__ = [
    "Dataset",
    "Defect",
    "DefectLog",
    "Harness",
    "configure",
    "declare_estate",
]
