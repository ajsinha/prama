"""Feeds: a contract about arrival, not a file.

The controls that catch the failures nothing else catches. A file that arrives
late, twice, out of order, truncated, or not at all passes every content-level
check, because the rows that did arrive are perfectly valid.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.connect.feed.arrival import (
    ArrivalFinding,
    ArrivalJudge,
    ArrivalStatus,
    ObservedFile,
    summarise,
)
from prama.connect.feed.definition import (
    DuplicatePolicy,
    FeedDefinition,
    TrailerSpec,
)
from prama.connect.feed.integrity import (
    IntegrityFinding,
    IntegrityStatus,
    ManifestChecker,
    TrailerChecker,
)
from prama.connect.feed.pattern import FilenamePattern, ParsedName

__all__ = [
    "ArrivalFinding",
    "ArrivalJudge",
    "ArrivalStatus",
    "DuplicatePolicy",
    "FeedDefinition",
    "FilenamePattern",
    "IntegrityFinding",
    "IntegrityStatus",
    "ManifestChecker",
    "ObservedFile",
    "ParsedName",
    "TrailerChecker",
    "TrailerSpec",
    "summarise",
]
