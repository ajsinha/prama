"""The landing page's three moving moments say true things.

The hero types declarations and proves them, so each one must be PQL the
language accepts: a hero advertising a control the parser would refuse is the
"looks right while being wrong" failure this product exists to catch.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import html
import json
import re
from typing import Any

import pytest

from prama.pql.parser import parse_control
from prama.web.routes.public_routes import HERO_DECLARATIONS


@pytest.mark.parametrize("declaration", HERO_DECLARATIONS, ids=lambda d: str(d["said"]))
def test_every_hero_declaration_is_real_pql(declaration: dict[str, Any]) -> None:
    parse_control(str(declaration["pql"]))


def test_the_parser_would_catch_a_bad_one() -> None:
    """The counterfactual: the check above can fail."""
    with pytest.raises(Exception):  # noqa: B017 - any refusal will do
        parse_control("CHECK trades.notional IS NOT NULL SEVERITY HIGH")


def test_the_hero_does_not_only_show_passes() -> None:
    assert any(d["violations"] for d in HERO_DECLARATIONS)
    assert any(not d["violations"] for d in HERO_DECLARATIONS)


async def test_the_page_carries_all_three_and_rests_on_a_proved_declaration(ui: Any) -> None:
    text = (await ui.get("/")).text
    for hook in ("data-lp-hero", "data-lp-chain", "data-lp-estate"):
        assert hook in text, hook
    first = HERO_DECLARATIONS[0]
    # The still frame, before any script: the first declaration, proved.
    assert html.escape(str(first["said"])) in text
    assert html.escape(str(first["pql"])) in text
    match = re.search(r"data-declarations='([^']*)'", text)
    assert match
    shipped = json.loads(html.unescape(match.group(1)))
    assert [d["pql"] for d in shipped] == [d["pql"] for d in HERO_DECLARATIONS]
    assert "/static/js/landing.js" in text
    assert "vendor/fonts/landing-fonts.css" in text
