"""Profiling: what is in a source, computed in bounded memory.

Everything here works at declaration stage zero — connect a source and get a
profile, inferred key candidates and proposable controls without anyone having
declared anything first.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.profile.incremental import (
    DEFAULT_MUTABLE_DAYS,
    IncrementalPlan,
    IncrementalPlanner,
    SegmentDecision,
    SegmentLedger,
    SegmentRecord,
    SegmentState,
)
from prama.profile.profiler import (
    DatasetProfile,
    ProfileProvenance,
    Profiler,
    detectable_rate,
    suggest_sample_plan,
)
from prama.profile.recording import points_from_profile
from prama.profile.segmented import (
    SegmentAccumulation,
    SegmentedProfile,
    SegmentedProfiler,
)
from prama.profile.segments import (
    MAX_SEGMENTS,
    Segment,
    Segmentation,
    SegmentGrain,
)
from prama.profile.sketches import CountMin, HyperLogLog, TDigest, TopK
from prama.profile.statistics import (
    ColumnAccumulator,
    ColumnProfile,
    NumericSummary,
    StringSummary,
    character_classes,
)

__all__ = [
    "DEFAULT_MUTABLE_DAYS",
    "MAX_SEGMENTS",
    "ColumnAccumulator",
    "ColumnProfile",
    "CountMin",
    "DatasetProfile",
    "HyperLogLog",
    "IncrementalPlan",
    "IncrementalPlanner",
    "NumericSummary",
    "ProfileProvenance",
    "Profiler",
    "Segment",
    "SegmentAccumulation",
    "SegmentDecision",
    "SegmentGrain",
    "SegmentLedger",
    "SegmentRecord",
    "SegmentState",
    "Segmentation",
    "SegmentedProfile",
    "SegmentedProfiler",
    "StringSummary",
    "TDigest",
    "TopK",
    "character_classes",
    "detectable_rate",
    "points_from_profile",
    "suggest_sample_plan",
]
