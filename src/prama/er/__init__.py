"""Deciding whether two records describe the same thing.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from prama.er.match import (
    MATCH_THRESHOLD,
    NON_MATCH_THRESHOLD,
    BlockingKey,
    Comparison,
    Decision,
    Judgement,
    Resolution,
    Resolver,
    estimate_m,
    estimate_u,
    exact,
    expectation_maximisation,
    normalised,
    similar,
)

__all__ = [
    "MATCH_THRESHOLD",
    "NON_MATCH_THRESHOLD",
    "BlockingKey",
    "Comparison",
    "Decision",
    "Judgement",
    "Resolution",
    "Resolver",
    "estimate_m",
    "estimate_u",
    "exact",
    "expectation_maximisation",
    "normalised",
    "similar",
]
