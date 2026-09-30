#!/usr/bin/env python3
"""Enforce the source-file length ceiling.

No source file may exceed MAX_CODE_LINES lines of *code* — comments, docstrings
and blank lines do not count, so documenting a module is never penalised. The UI
tree is exempt because generated and component-tree files legitimately run long.

A file that has outgrown the ceiling is a design signal, not a formatting one:
it is doing more than one thing. Split it rather than raising the limit.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import io
import sys
import tokenize
from pathlib import Path

MAX_CODE_LINES = 1500
EXEMPT_PREFIXES = ("prama-web/", "web/", "node_modules/", "build/", "dist/")
#: Directories that are never ours to police, wherever they appear in a path.
EXEMPT_PARTS = frozenset(
    {
        ".venv",
        "venv",
        "site-packages",
        "node_modules",
        ".git",
        "__pycache__",
        ".tox",
        "build",
        "dist",
    }
)
#: When no paths are given, only these roots are walked.
DEFAULT_ROOTS = ("src", "sdk", "kernel", "tests", "scripts", "schema")
CHECKED_SUFFIXES = {".py", ".rs", ".sql", ".sh", ".ts", ".tsx"}
UI_SUFFIXES = {".ts", ".tsx", ".css", ".scss"}


class LengthChecker:
    """Counts significant (non-comment, non-blank) lines in a source file."""

    def __init__(self, max_lines: int = MAX_CODE_LINES) -> None:
        self._max = max_lines

    def is_exempt(self, path: Path) -> bool:
        if EXEMPT_PARTS & set(path.parts):
            return True
        posix = path.as_posix()
        if any(posix.startswith(p) for p in EXEMPT_PREFIXES):
            return True
        return path.suffix in UI_SUFFIXES

    def count(self, path: Path) -> int:
        text = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix == ".py":
            return self._count_python(text)
        return self._count_generic(text, path.suffix)

    @staticmethod
    def _count_generic(text: str, suffix: str) -> int:
        line_comment = {"sql": "--", "sh": "#", "rs": "//"}.get(suffix.lstrip("."), "#")
        n = 0
        for raw in text.splitlines():
            s = raw.strip()
            if not s or s.startswith(line_comment) or s.startswith("/*") or s.startswith("*"):
                continue
            n += 1
        return n

    @staticmethod
    def _count_python(text: str) -> int:
        """Significant lines = lines carrying a token that is not a comment or a
        bare string expression (docstring)."""
        significant: set[int] = set()
        try:
            tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
        except (tokenize.TokenError, IndentationError, SyntaxError):
            return LengthChecker._count_generic(text, ".py")
        prev_meaningful = tokenize.INDENT
        for tok in tokens:
            if tok.type in (
                tokenize.COMMENT,
                tokenize.NL,
                tokenize.NEWLINE,
                tokenize.INDENT,
                tokenize.DEDENT,
                tokenize.ENDMARKER,
            ):
                continue
            if tok.type == tokenize.STRING and prev_meaningful in (
                tokenize.NEWLINE,
                tokenize.INDENT,
                tokenize.DEDENT,
            ):
                prev_meaningful = tok.type  # docstring — skip its span
                continue
            for ln in range(tok.start[0], tok.end[0] + 1):
                significant.add(ln)
            prev_meaningful = tok.type
        return len(significant)

    def offenders(self, paths: list[Path]) -> list[tuple[Path, int]]:
        out = []
        for p in paths:
            if not p.is_file() or p.suffix not in CHECKED_SUFFIXES or self.is_exempt(p):
                continue
            n = self.count(p)
            if n > self._max:
                out.append((p, n))
        return sorted(out, key=lambda t: -t[1])


def main(argv: list[str]) -> int:
    root = Path.cwd()
    if argv[1:]:
        paths = [Path(a) for a in argv[1:]]
    else:
        paths = [
            p
            for name in DEFAULT_ROOTS
            for p in (root / name).rglob("*")
            if p.suffix in CHECKED_SUFFIXES
        ]
    checker = LengthChecker()
    bad = checker.offenders(paths)
    if not bad:
        return 0
    print(
        f"file-length: refused — {len(bad)} file(s) exceed {MAX_CODE_LINES} code lines:",
        file=sys.stderr,
    )
    for p, n in bad:
        print(f"  {n:>6} lines  {p}", file=sys.stderr)
    print("\n  A file over the ceiling is doing more than one thing. Split it.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
