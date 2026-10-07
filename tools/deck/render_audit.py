"""
The rendered audit: what the deck looks like once a real renderer has laid it out.

    python tools/deck/render_audit.py docs/publications/deck/Prama-Evidence-First-Data-Quality.pptx

``audit.py`` checks geometry from estimates. Estimates are what failed in Maya's decks:
the builder believed a box fitted, the audit agreed, and the rendered slide had its last
line on the footer rule. This audit does not estimate. It converts the deck to PDF with
LibreOffice, reads every word's box back with ``pdftotext -bbox-layout``, and reports:

* a word that leaves the slide;
* a word of content at or below the footer rule (the footer's own words excepted);
* two words whose boxes overlap: text printed over text, whatever caused it.

It must print ``no rendered issues detected`` before a deck ships;
``tests/docs/test_deck.py`` makes that a test wherever LibreOffice is installed.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from metrics import FOOTER_Y, SH

_PAGE = re.compile(r'<page width="([\d.]+)" height="([\d.]+)">')
_WORD = re.compile(
    r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</word>'
)
#: Where the footer's own text starts (theme.footer draws it at SH - 0.46in).
FOOTER_TEXT_Y = SH - 0.46
#: Overlap smaller than this, in points, is glyph side-bearing, not a collision.
TOLERANCE = 1.0
#: The share of the shorter word's height two boxes must share to be a collision.
OVERLAP = 0.4


def _pdf(deck: Path, workdir: Path) -> Path:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice is None:
        raise SystemExit("LibreOffice is not installed: the rendered audit cannot run")
    # A profile of its own, in the scratch directory: LibreOffice allows one instance per
    # profile, so with the default one a conversion fails outright whenever any other
    # LibreOffice (a desktop session, another build) is running on the machine.
    profile = (workdir / "lo-profile").as_uri()
    subprocess.run(
        [
            soffice,
            f"-env:UserInstallation={profile}",
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(workdir),
            str(deck),
        ],
        check=True,
        capture_output=True,
        timeout=300,
    )
    return workdir / f"{deck.stem}.pdf"


def _pages(pdf: Path) -> list[tuple[float, float, list[tuple[float, float, float, float, str]]]]:
    html = subprocess.run(
        ["pdftotext", "-bbox-layout", str(pdf), "-"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    pages = []
    chunks = html.split("<page ")[1:]
    for chunk in chunks:
        head = _PAGE.match("<page " + chunk)
        if head is None:
            continue
        words = [
            (float(a), float(b), float(c), float(d), text)
            for a, b, c, d, text in _WORD.findall(chunk)
        ]
        pages.append((float(head.group(1)), float(head.group(2)), words))
    return pages


def audit(deck: Path) -> list[str]:
    issues: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        pages = _pages(_pdf(deck, Path(tmp)))
    for n, (width, height, words) in enumerate(pages, 1):
        per_inch_y = height / SH
        rule = FOOTER_Y * per_inch_y
        footer_text = FOOTER_TEXT_Y * per_inch_y
        for x0, y0, x1, y1, text in words:
            if x0 < 0 or y0 < 0 or x1 > width or y1 > height:
                issues.append(f"slide {n}: {text!r} leaves the slide")
            elif y0 < footer_text and y1 > rule:
                issues.append(f"slide {n}: {text!r} reaches the footer rule")
        for i, (ax0, ay0, ax1, ay1, at) in enumerate(words):
            for bx0, by0, bx1, by1, bt in words[i + 1 :]:
                dx = min(ax1, bx1) - max(ax0, bx0)
                dy = min(ay1, by1) - max(ay0, by0)
                # A word's box is its font's full ascent and descent, which is taller
                # than a tightly set heading's line pitch: consecutive lines of one
                # heading overlap by a sliver that no reader sees. Text printed over
                # text overlaps by a large share of its height.
                if dx > TOLERANCE and dy > OVERLAP * min(ay1 - ay0, by1 - by0):
                    issues.append(f"slide {n}: {at!r} and {bt!r} are printed over each other")
    return issues


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    issues = audit(Path(argv[1]))
    for issue in issues:
        print(issue)
    print("no rendered issues detected" if not issues else f"{len(issues)} rendered issue(s)")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
