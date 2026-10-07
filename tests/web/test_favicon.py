"""The favicon is the header's mark on the header's own colours, and stays so.

It used to be a navy tile left over from an earlier palette, so the browser tab
showed a different brand from the page it named. Here it is derived, not
restated: its shapes must be the header mark's, shape for shape, and its tile
must use the console header's gradient stops from the light theme. Change either
the mark or the theme and this fails until the favicon follows.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from prama.web import help_catalog

STATIC = Path(help_catalog.__file__).parent / "static"
ROOT = Path(__file__).resolve().parents[2]
SVG = "{http://www.w3.org/2000/svg}"


def _shapes(path: Path) -> list[tuple[str, dict[str, str]]]:
    """Every drawn shape outside the tile, in order, as (tag, attributes)."""
    out = []
    for el in ET.parse(path).getroot().iter():
        tag = el.tag.removeprefix(SVG)
        if tag in ("path", "line", "polygon", "circle", "g"):
            out.append((tag, dict(el.attrib)))
    return out


def test_the_favicon_draws_the_header_mark_shape_for_shape() -> None:
    mark = _shapes(STATIC / "img" / "prama-mark-white.svg")
    favicon = _shapes(STATIC / "img" / "favicon.svg")
    assert mark, "the header mark has no shapes"
    assert favicon == mark


def test_the_favicon_tile_is_the_console_header_gradient() -> None:
    css = (STATIC / "css" / "themes.css").read_text(encoding="utf-8")
    light = css[: css.index("--maya-nav-to") + 40]  # the first theme block is the light one
    tokens = []
    for name in ("from", "via", "to"):
        found = re.search(rf"--maya-nav-{name}:\s*(#[0-9A-Fa-f]{{6}})", light)
        assert found, f"themes.css no longer defines --maya-nav-{name}"
        tokens.append(found.group(1).upper())
    root = ET.parse(STATIC / "img" / "favicon.svg").getroot()
    stops = [s.attrib["stop-color"].upper() for s in root.iter(f"{SVG}stop")]
    assert stops == tokens
    tile = next(root.iter(f"{SVG}rect"))
    assert tile.attrib["fill"] == "url(#nav)"


def test_the_favicon_is_well_formed_xml() -> None:
    # A browser parses an SVG favicon strictly and draws nothing at all if it is not
    # well-formed; a lenient renderer (Inkscape) will happily draw it anyway. "--"
    # inside a comment is the easy way to get here, by naming a CSS custom property.
    for path in (STATIC / "img").glob("*.svg"):
        ET.parse(path)


def test_the_brand_asset_is_the_favicon_the_console_serves() -> None:
    served = (STATIC / "img" / "favicon.svg").read_bytes()
    assert (ROOT / "docs" / "assets" / "prama-favicon.svg").read_bytes() == served
