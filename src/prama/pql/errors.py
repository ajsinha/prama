"""What a mistake in a control looks like when somebody reads it.

PQL is meant to be read by the people who own the data, not only by the people
who write software. That changes what an error has to do. A parser error which
says ``unexpected token at offset 147`` is acceptable in a compiler and useless
here: the reader is a market risk manager who has just been shown a control
Prama generated, has edited one clause, and needs to know which clause and why.

So every error carries the position, the line as written, a caret under the
offending text, and a remedy in the same register as the language itself.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses

from prama.core.errors import PramaError

#: How much of a long line to show around the error. Enough for context,
#: little enough that the caret still lines up in a terminal.
CONTEXT_CHARS = 60


@dataclasses.dataclass(frozen=True, slots=True)
class Position:
    """Where in the source something is. One-based, as an editor counts."""

    line: int = 1
    column: int = 1
    offset: int = 0
    length: int = 1

    def __str__(self) -> str:
        return f"line {self.line}, column {self.column}"

    def to_dict(self) -> dict[str, int]:
        return {
            "line": self.line,
            "column": self.column,
            "offset": self.offset,
            "length": self.length,
        }


class PqlError(PramaError):
    """A control could not be understood. Always says where and why."""

    code = "PQL.INVALID"

    def __init__(
        self,
        message: str,
        *,
        remedy: str,
        position: Position | None = None,
        source: str = "",
        context: dict[str, object] | None = None,
    ) -> None:
        self.position = position or Position()
        self.source = source
        super().__init__(
            message,
            remedy=remedy,
            context={
                **(context or {}),
                **({"position": str(self.position)} if position else {}),
            },
        )

    def render(self) -> str:
        """The error as it should appear to whoever wrote the control."""
        lines = [f"{self.args[0]} (at {self.position})"]
        excerpt = self.excerpt()
        if excerpt:
            lines.append("")
            lines.extend(excerpt)
        lines.append("")
        lines.append(f"→ {self.remedy}")
        return "\n".join(lines)

    def excerpt(self) -> list[str]:
        """The offending line with a caret under it.

        Long lines are windowed around the error rather than truncated from the
        left, because the interesting part of a hundred-character WHERE clause
        is wherever the mistake is, not its beginning.
        """
        if not self.source:
            return []
        source_lines = self.source.splitlines()
        index = self.position.line - 1
        if not 0 <= index < len(source_lines):
            return []
        line = source_lines[index]
        start = max(0, self.position.column - 1 - CONTEXT_CHARS)
        end = min(len(line), self.position.column - 1 + CONTEXT_CHARS)
        window = line[start:end]
        prefix = "…" if start > 0 else ""
        suffix = "…" if end < len(line) else ""
        caret_at = self.position.column - 1 - start + len(prefix)
        return [
            f"  {prefix}{window}{suffix}",
            "  " + " " * caret_at + "^" * max(1, self.position.length),
        ]


class PqlSyntaxError(PqlError):
    """The text is not a control at all."""

    code = "PQL.SYNTAX"


class PqlTypeError(PqlError):
    """The control parses, but does not mean anything coherent."""

    code = "PQL.TYPE"


class PqlUnsupportedError(PqlError):
    """The control is valid, and this backend genuinely cannot express it.

    Raised at authoring time and never at execution time. A control that
    compiles and then quietly does something slightly different on one engine
    is the failure this whole layer exists to prevent.
    """

    code = "PQL.UNSUPPORTED"
