"""A remedy names something the reader can actually do.

Finding H6. Several `remedy=` strings told the reader to change a configuration
key that nothing reads — `security.api_key_hash_rounds`, `plugins.disabled`,
`concurrency.queue.max_bytes`. Each key exists in `defaults.py` and in
`application.yaml`, so a naive existence check passes; `grep` for the key in
`src/` returns the default and the remedy and nothing else.

That is the "derive, never restate" failure the project's own notes warn about,
in its most expensive form: an inert knob reads as a live one. Somebody follows
the advice, changes the value, and the behaviour does not move — so they
conclude the problem is elsewhere, which is the opposite of what a remedy is
for. A remedy that does nothing is worse than no remedy.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import ClassVar

SRC = Path(__file__).resolve().parents[2] / "src" / "prama"

#: A dotted configuration key as it appears in prose: `security.session_secret`,
#: `concurrency.queue.max_bytes`. Two segments minimum, lower-case and dotted,
#: which is what this codebase's keys look like and ordinary English is not.
#: A dotted name *not* immediately called, because `catalogue.of(kind)` is a
#: method and `security.session_secret` is a setting, and only the second is
#: something a reader can put in a file.
KEY = re.compile(r"\b([a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+)\b(?!\s*\()")

#: Words that look like keys and are not — module paths, file names, and the
#: handful of dotted identifiers that turn up in a sentence.
NOT_A_KEY = re.compile(
    r"^(prama|tests|scripts|docs|schema)\."
    # File extensions a remedy plausibly names. `pem`, `crt` and `pql` were
    # added when a remedy first told somebody to run `openssl genpkey ... -out
    # key.pem` and this rule read the filename as a setting nothing reads.
    # Deliberately NOT `key`: a real setting could end in `.key`, and excluding
    # that would hide the thing this test exists to find.
    r"|\.(py|sql|json|jsonl|yaml|yml|md|toml|pem|crt|cer|csv|parquet|pql|lock|txt)$"
)


def remedies() -> list[tuple[str, int, str]]:
    """Every `remedy=` literal in the source, with where it is."""
    found: list[tuple[str, int, str]] = []
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg != "remedy":
                    continue
                text = _literal(keyword.value)
                if text:
                    found.append((path.relative_to(SRC).as_posix(), node.lineno, text))
    return found


def _literal(node: ast.expr) -> str:
    """The string a remedy argument spells, where it can be known statically.

    Handles the implicit concatenation and `+` joins this codebase uses for
    long messages; an f-string's literal parts are kept and its expressions
    dropped, because a key is never interpolated.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            part.value
            for part in node.values
            if isinstance(part, ast.Constant) and isinstance(part.value, str)
        )
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _literal(node.left) + _literal(node.right)
    return ""


def configuration_keys(text: str) -> set[str]:
    return {
        candidate
        for candidate in KEY.findall(text)
        if not NOT_A_KEY.search(candidate) and "." in candidate
    }


def _sources() -> list[str]:
    """Every source file except the defaults, which define keys rather than
    read them."""
    return [
        path.read_text(encoding="utf-8")
        for path in SRC.rglob("*.py")
        if not path.relative_to(SRC).as_posix().startswith("core/config/defaults")
    ]


def _without_remedies(source: str) -> str:
    """The file with its remedy strings removed.

    A remedy naming a key is the thing under test; it cannot also be the
    evidence that the key is read.
    """
    return re.sub(r"remedy=\s*\(?[^)]*\)?", "", source, flags=re.S)


def is_read_anywhere(key: str) -> bool:
    """Whether anything reads this configuration key.

    Two spellings count, because the codebase uses both. The dotted key may
    appear whole — `config.get_str("security.session_secret")` — or a section
    may be taken first and its leaf read from that: `database.schema_dir` is
    read as `section.get_str("schema_dir", "schema")`, and a scan looking only
    for the dotted form calls a live key dead.

    Deliberately coarse about *which* read: it asks whether the key is reachable
    at all, not whether the code path the remedy is about is the one that reads
    it. A guard claiming more precision than it has is worse than one that
    states its limit. What it catches, and what nothing caught, is a key that
    appears in exactly two places — the default, and the remedy naming it.
    """
    leaf = key.rsplit(".", 1)[-1]
    forms = (f'"{key}"', f"'{key}'", f'"{leaf}"', f"'{leaf}'")
    return any(
        any(form in _without_remedies(source) for form in forms)
        for source in _sources()
        if any(form in source for form in forms)
    )


class TestEveryConfigurationKeyARemedyNamesIsLive:
    #: Keys a remedy names that nothing reads, each with what was done instead.
    #: The list is empty because every one was either wired up or the remedy
    #: was rewritten to name the real lever; an entry here would be an
    #: admission that a remedy still points at an inert knob.
    INERT: ClassVar[dict[str, str]] = {}

    def test_there_are_remedies_to_check(self) -> None:
        """Anti-vacuity. A scan that matched no remedies would pass this whole
        class while checking nothing — which is the shape of half this review."""
        assert len(remedies()) >= 200

    def test_the_key_pattern_matches_a_real_key(self) -> None:
        """And that the pattern works, which the test above does not show."""
        assert configuration_keys("Set security.session_secret in configuration.") == {
            "security.session_secret"
        }
        assert not configuration_keys("Check the file and retry.")
        assert not configuration_keys("Use catalogue.of(kind) to fetch it."), (
            "a method call is not a setting"
        )

    def test_no_remedy_names_a_key_nothing_reads(self) -> None:
        dead: list[str] = []
        for module, line, text in remedies():
            for key in configuration_keys(text):
                if key in self.INERT:
                    continue
                if not is_read_anywhere(key):
                    dead.append(f"{module}:{line} names {key!r}")
        assert not dead, (
            "these remedies tell the reader to change configuration that nothing "
            f"reads, so following them changes nothing: {dead}"
        )
