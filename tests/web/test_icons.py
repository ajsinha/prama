"""Every icon the console names exists in the icon font it ships.

A Bootstrap Icons name the vendored version does not have renders as nothing, and
nothing fails: the "Who can use this page" tile, the Quickstart and SDK cards in
Help, the data-model card, the language-server line on the landing page and
"Switch estate" all drew an empty square, found by looking at a screenshot. The
names are checked here against the stylesheet the console actually loads.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import re
from pathlib import Path

from prama.web import help_catalog, page_help

WEB = Path(help_catalog.__file__).parent
SHIPPED = set(
    re.findall(
        r"\.bi-([a-z0-9-]+)::before",
        (WEB / "static" / "vendor" / "bootstrap-icons" / "bootstrap-icons.css").read_text(),
    )
)
#: `bi-` followed by a name, as a class in a template or a string in code;
#: not the `bi-` of a Jinja expression or of a CSS selector for a family of icons.
NAMED = re.compile(r"""(?<![\w-])bi-([a-z0-9]+(?:-[a-z0-9]+)*)(?=["'\s}])""")


def test_the_icon_font_was_read() -> None:
    assert len(SHIPPED) > 1500


def test_every_icon_in_the_templates_and_the_help_exists() -> None:
    sources = [*WEB.rglob("*.html"), WEB / "help_catalog.py", WEB / "rendering.py"]
    named = {
        (path.relative_to(WEB).as_posix(), name)
        for path in sources
        for name in NAMED.findall(path.read_text(encoding="utf-8"))
    }
    named |= {("help_catalog", e.icon.removeprefix("bi-")) for e in help_catalog.BY_SLUG.values()}
    named |= {
        ("page_help", tile.icon) for entry in page_help.PAGES.values() for tile in entry.tiles
    }
    named |= {("page_help", "shield-lock"), ("page_help", "unlock")}  # the derived tile
    missing = sorted((where, name) for where, name in named if name not in SHIPPED)
    assert missing == [], f"icons the shipped font does not have: {missing}"
