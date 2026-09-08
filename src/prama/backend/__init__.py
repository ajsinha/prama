"""Backends: one plan, several engines, the same meaning.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from prama.backend.conformance import ConformanceRun, Disagreement, EngineOutcome
from prama.backend.corpus import CASES, Case
from prama.backend.dialect import (
    DIALECTS,
    DuckDbDialect,
    PostgresDialect,
    SqlDialect,
    SqliteDialect,
    Unsupported,
    dialect,
)
from prama.backend.execute import ControlResult, SegmentResult, judge, judge_segments
from prama.backend.sql import CompiledControl, SqlCompiler, compile_for

__all__ = [
    "CASES",
    "DIALECTS",
    "Case",
    "CompiledControl",
    "ConformanceRun",
    "ControlResult",
    "Disagreement",
    "DuckDbDialect",
    "EngineOutcome",
    "PostgresDialect",
    "SegmentResult",
    "SqlCompiler",
    "SqlDialect",
    "SqliteDialect",
    "Unsupported",
    "compile_for",
    "dialect",
    "judge",
    "judge_segments",
]
