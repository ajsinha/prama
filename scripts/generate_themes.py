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

from prama.report.contrast import BODY_TEXT
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
    lines.extend(maya_tokens(theme))
    lines.append("}")
    return "\n".join(lines) + "\n"


def maya_tokens(theme: Theme) -> list[str]:
    """Maya's token set, so the console's chrome is Maya's stylesheet.

    The colours a reader has to *read* — the accent as a link, the heading, the
    ink and the slate — are the derived, legible ones; the rest are Maya's
    declarations, which are grounds, rules and gradients.
    """
    m = theme.maya
    if m is None:
        return []
    heading = theme._legible(m.heading, BODY_TEXT)
    tokens = {
        "crimson": theme.legible_link,
        "crimson-strong": m.strong,
        "crimson-deep": m.deep,
        "crimson-tint": m.tint,
        "ink": theme.legible_ink,
        "slate": theme.legible_muted,
        "surface": theme.surface,
        "canvas": theme.body,
        "indigo": m.indigo,
        "on-crimson": m.on_accent,
        "border": theme.border,
        "ok": m.ok,
        "warn": m.warn,
        "bad": m.bad,
        "highlight": m.highlight,
        "heading": heading,
        "nav-from": m.nav[0],
        "nav-via": m.nav[1],
        "nav-to": m.nav[2],
        "on-nav": "#FFFFFF",
        "glow": m.glow,
    }
    lines = ["", "    /* Maya's tokens: the chrome — navigation, menus, cards, footer. */"]
    lines += [f"    --maya-{name}: {value};" for name, value in tokens.items()]
    lines.append(f"    color-scheme: {theme.base};")
    return lines


def render() -> str:
    return HEADER + "".join(block(theme) for theme in THEMES)


if __name__ == "__main__":
    TARGET.write_text(render(), encoding="utf-8")
    print(f"wrote {TARGET.relative_to(Path(__file__).resolve().parents[1])}")
