"""The no-code rule builder, now at `prama.pql.builder`.

Kept as a name so older imports (the QA harness among them) still resolve. The
builder composes a PQL AST and nothing about it is specific to the console, so
it lives with the language, where the HTTP API can reach it as well.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.pql.builder import (
    QUESTIONS,
    QUESTIONS_BY_KEY,
    Question,
    _number,
    _values,
    build,
    render_and_verify,
)

__all__ = [
    "QUESTIONS",
    "QUESTIONS_BY_KEY",
    "Question",
    "_number",
    "_values",
    "build",
    "render_and_verify",
]
