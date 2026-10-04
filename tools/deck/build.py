"""
Build the deck.

    python tools/deck/build.py
    python tools/deck/audit.py docs/publications/deck/Prama-Evidence-First-Data-Quality.pptx

The deck is a list of slide specs across three modules; ``layouts`` draws them with the
``theme``. The document properties are set explicitly: python-pptx's default template
carries a comment naming the library, and a deck's metadata should say who wrote it and
nothing else.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(ROOT / "src"))

import layouts  # noqa: E402
import prama_deck  # noqa: E402
import theme  # noqa: E402

OUT = ROOT / "docs" / "publications" / "deck"
NAME = "Prama-Evidence-First-Data-Quality"
AUTHOR = "Ashutosh Sinha"


def build(out_dir: Path = OUT) -> tuple[Path, int]:
    prs = theme.new_deck(prama_deck.CHAPTER)
    layouts.render(prama_deck.SLIDES)
    props = prs.core_properties
    props.title = prama_deck.TITLE
    props.subject = prama_deck.SUBJECT
    props.author = AUTHOR
    props.last_modified_by = AUTHOR
    props.comments = "Copyright (c) 2026 Ashutosh Sinha. All rights reserved."
    props.keywords = "Prama; data quality; evidence"
    props.category = ""
    props.revision = 1
    # Fixed, so a rebuild with no change of content is byte-for-byte comparable.
    stamp = dt.datetime(2026, 9, 28, 12, 0, 0)
    props.created = stamp
    props.modified = stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{NAME}.pptx"
    prs.save(str(out))
    return out, len(prs.slides)


if __name__ == "__main__":
    out, n = build()
    print(f"{n:3d} slides -> {out.relative_to(ROOT)}")
