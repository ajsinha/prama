"""
The one Prama deck, as data: the title slide here, and the nine parts in order in
``deck_part1`` to ``deck_part3``.

It is written for the people who must stand behind a number: a chief data officer, a data
owner, a head of risk or audit, and the engineer asked to run it. It answers their questions
in the order they ask them: why data quality fails, how meaning is declared, the language,
the evidence, lineage, trust, the place of AI, how it runs, and what is measured.

Every figure comes from the code, a test, a case study's run, or ``prama bench run --seed 42``.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""

from __future__ import annotations

from deck_part1 import SLIDES as PART1
from deck_part2 import SLIDES as PART2
from deck_part3 import SLIDES as PART3

CHAPTER = "PRAMA · Evidence-first data quality"
TITLE = "Prama — Evidence-First Data Quality"
SUBJECT = "Why data quality fails, what Prama does about it, and the evidence"

OPENING = [
    {
        "kind": "title",
        "kicker": "PRAMA · THE INSTRUMENT OF VALID KNOWLEDGE",
        "title": ["Prama : Evidence-First", "Data Quality"],
        "sub": "Declare it. Prove it. Trust it.",
        "agenda": [
            "Why data quality fails",
            "Declare it: the semantic layer",
            "The language",
            "Prove it: evidence and reconciliation",
            "Lineage and impact",
            "Trust it",
            "AI that never adjudicates",
            "How it runs",
            "The evidence",
        ],
    },
]

SLIDES = OPENING + PART1 + PART2 + PART3
