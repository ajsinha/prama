"""Benchmarking: making the product's claim falsifiable.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from prama.bench.scoring import Alert, Defect, FamilyScore, Score, score
from prama.bench.shadow import Blinding, Judgement, ShadowAlert, ShadowResult, evaluate

__all__ = [
    "Alert",
    "Blinding",
    "Defect",
    "FamilyScore",
    "Judgement",
    "Score",
    "ShadowAlert",
    "ShadowResult",
    "evaluate",
    "score",
]
