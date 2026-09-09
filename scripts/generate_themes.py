#!/usr/bin/env python3
"""Generate src/prama/web/static/css/themes.css from prama.report.themes.

The stylesheet cannot call Python, so it holds a copy of colours the arithmetic
produced. This script writes that copy, and a test regenerates it in memory and
compares — so a hand-edit is caught rather than silently shipped. A hand-edited
token is the one that will be wrong, because it is the one nobody checked
against a contrast threshold.

Run it after changing a theme's surfaces or the brand palette:

    python scripts/generate_themes.py

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from prama.report.themes import THEMES, Theme

TARGET = Path(__file__).resolve().parents[1] / "src/prama/web/static/css/themes.css"

HEADER = """/* Prama themes. GENERATED — do not edit.
 *
 * Written by scripts/generate_themes.py from prama/report/themes.py, where the
 * dimension colours are *derived* rather than picked: each theme declares its
 * surfaces, and every hue is moved only as far as the contrast threshold for
 * its job requires — 3:1 for a mark, 4.5:1 for a word.
 *
 * That is why a theme here is five colours and a gradient rather than forty
 * hex codes. Hand-editing one would produce exactly the token nobody checked,
 * which is why tests/web/test_accessibility.py regenerates this file and
 * compares it byte for byte.
 *
 * Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
 */
"""


def block(theme: Theme) -> str:
    selector = (
        ':root, [data-theme="light"]' if theme.name == "light" else f'[data-theme="{theme.name}"]'
    )
    lines = [f"\n/* {theme.label} — {theme.note} */", f"{selector} {{"]
    lines.append(f"    --bg-body: {theme.body};")
    lines.append(f"    --bg-card: {theme.surface};")
    lines.append(f"    --bg-header: {theme.header};")
    # The *derived* values, not the declared ones. A colour declared in
    # themes.py is the designer's intent; what a reader has to be able to see is
    # that intent walked to legibility on every ground it can land on — card,
    # page and striped row. Emitting the declaration would put a number in the
    # stylesheet that nothing has checked, which is how muted text shipped at
    # 4.12:1 against a background no test had computed.
    lines.append(f"    --text-primary: {theme.legible_ink};")
    lines.append(f"    --text-muted: {theme.legible_muted};")
    lines.append(f"    --text-link: {theme.legible_link};")
    lines.append(f"    --accent: {theme.legible_accent};")
    lines.append(f"    --border-color: {theme.border};")
    lines.append("")
    lines.append("    /* Marks: bars, rings, dots. 3:1 against this theme's card. */")
    for name, value in theme.fills().items():
        lines.append(f"    --dim-{name}: {value};")
    lines.append("")
    lines.append("    /* Words: dimension names, verdicts. 4.5:1 against the same. */")
    for name, value in theme.texts().items():
        lines.append(f"    --dim-{name}-text: {value};")
    lines.append("")
    lines.append("    /* Reserved for 'stale or not yet examined'. Nothing else may use it. */")
    lines.append(f"    --unverified-grey: {theme.unverified_fill()};")
    lines.append(f"    --unverified-grey-text: {theme.unverified_text()};")
    lines.append("}")
    return "\n".join(lines) + "\n"


def render() -> str:
    return HEADER + "".join(block(theme) for theme in THEMES)


if __name__ == "__main__":
    TARGET.write_text(render(), encoding="utf-8")
    print(f"wrote {TARGET.relative_to(Path(__file__).resolve().parents[1])}")
