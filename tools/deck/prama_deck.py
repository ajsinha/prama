"""
The one Prama deck, as data: the title slide here, then the opening and ten sections in
``deck_part1`` to ``deck_part3``.

The storytelling follows a pyramid: a TL;DR in five questions, why the discipline matters
(ten principles, the ways it fails, what a supervisor asks for), how Prama works, the six
capabilities that carry it, three worked examples from the case studies, and an honest
close (what is built, what is next, how it compares, what it does not do). It is written
for the people who must stand behind a number: a chief data officer, a data owner, a head
of risk or audit, and the engineer asked to run it.

Every figure comes from the code, a test, a case study's run, or ``prama bench run --seed
42``. The one figure that changes with every commit, the number of passing tests, is read
from the README's synced marker when the deck is built, so it is never typed.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from deck_part1 import SLIDES as PART1
from deck_part2 import SLIDES as PART2
from deck_part3 import SLIDES as PART3

CHAPTER = ""
TITLE = "Prama — Evidence-First Data Quality"
SUBJECT = "Why data quality fails, what Prama does about it, and the evidence"

README = Path(__file__).resolve().parents[2] / "README.md"


def passing_tests() -> str:
    """The suite's passing count, as scripts/sync_test_counts.py last wrote it."""
    found = re.search(r"<!--tests-->([\d,]+) passing", README.read_text(encoding="utf-8"))
    if not found:
        raise RuntimeError("README.md has no <!--tests--> marker: run sync_test_counts.py")
    return found.group(1)


OPENING = [
    {
        "kind": "title",
        "kicker": "PRAMA · THE INSTRUMENT OF VALID KNOWLEDGE",
        "title": ["Prama — Evidence-First", "Data Quality"],
        "sub": "Declare it. Prove it. Trust it.",
        "date": "October 2026",
        "agenda": [
            "How Prama works",
            "Declare it",
            "The language",
            "Prove it",
            "Lineage and impact",
            "Trust it",
            "AI that never adjudicates",
            "How it runs",
            "Worked examples",
            "Where Prama stands",
        ],
    },
]


def _fill(value: Any, figures: dict[str, str]) -> Any:
    if isinstance(value, str):
        # Named placeholders only: slide text has braces of its own (a formula, PQL).
        for name, figure in figures.items():
            value = value.replace("{" + name + "}", figure)
        return value
    if isinstance(value, list):
        return [_fill(v, figures) for v in value]
    if isinstance(value, tuple):
        return tuple(_fill(v, figures) for v in value)
    if isinstance(value, dict):
        return {k: _fill(v, figures) for k, v in value.items()}
    return value


SLIDES = _fill(OPENING + PART1 + PART2 + PART3, {"tests": passing_tests()})
