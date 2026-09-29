"""About and the competitive landscape, laid out after Maya's.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import re
from pathlib import Path

import httpx
import pytest

from prama.web import about
from prama.web.rendering import STATIC_DIR


class TestTheComparisonAsData:
    def test_every_row_rates_every_category_and_prama(self) -> None:
        keys = {c.key for c in about.CATEGORIES} | {"prama"}
        for row in about.ROWS:
            assert set(row.ratings) == keys, row.id
            assert set(row.ratings.values()) <= set(about.RATINGS), row.id
            assert row.problem and row.how, row.id

    def test_ids_are_unique_anchors(self) -> None:
        ids = [row.id for row in about.ROWS]
        assert len(ids) == len(set(ids))
        assert all(re.fullmatch(r"[a-z][a-z-]*", i) for i in ids)

    def test_it_says_where_prama_is_behind_not_only_where_it_shines(self) -> None:
        """A comparison that only lists advantages is a morale exercise."""
        assert about.SHINES and about.BEHIND
        assert any(row.prama == about.NO for row in about.BEHIND)


class TestThePages:
    async def test_competitive_shows_every_row_with_its_note(self, ui: httpx.AsyncClient) -> None:
        response = await ui.get("/about/competitive")
        assert response.status_code == 200
        text = response.text
        for row in about.ROWS:
            assert f'href="#{row.id}"' in text, row.id
            assert f'id="{row.id}"' in text, row.id
        # Shines comes before behind, and every behind row sits under it.
        assert text.index("Where Prama shines") < text.index("Where Prama is partial")
        assert text.count('class="cmp cmp-') == len(about.ROWS) * (len(about.CATEGORIES) + 1) * 2

    @pytest.mark.parametrize("path", ["/about", "/help"])
    async def test_about_and_help_link_to_it(self, ui: httpx.AsyncClient, path: str) -> None:
        text = (await ui.get(path)).text
        assert 'href="/about/competitive"' in text, path

    async def test_the_vendor_by_vendor_long_form_is_in_help(self, ui: httpx.AsyncClient) -> None:
        response = await ui.get("/help/competitive-analysis")
        assert response.status_code == 200
        assert "Solidatus" in response.text

    async def test_about_counts_rather_than_types(self, ui: httpx.AsyncClient) -> None:
        text = (await ui.get("/about")).text
        assert "Crimson, Dark, Blue, Green" in text
        assert "Honest limits" in text


@pytest.mark.parametrize("sheet", sorted(p.name for p in (STATIC_DIR / "css").glob("*.css")))
def test_every_stylesheet_closes_every_rule(sheet: str) -> None:
    """An unclosed rule swallows every rule after it without a single error in
    the console: the competitive table rendered unstyled for exactly that."""
    text = re.sub(r"/\*.*?\*/", "", (STATIC_DIR / "css" / sheet).read_text(), flags=re.S)
    text = re.sub(r'"(?:\\.|[^"\\])*"', '""', text)
    depth = 0
    for index, char in enumerate(text):
        depth += {"{": 1, "}": -1}.get(char, 0)
        assert depth >= 0, f"{sheet}: a stray }} near {text[max(0, index - 60) : index]!r}"
    assert depth == 0, f"{sheet}: {depth} rule(s) never closed"


def test_the_stylesheet_guard_can_fail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "css").mkdir()
    (tmp_path / "css" / "bad.css").write_text(".a { color: red;\n.b { color: blue; }\n")
    monkeypatch.setattr(__import__(__name__, fromlist=["STATIC_DIR"]), "STATIC_DIR", tmp_path)
    with pytest.raises(AssertionError, match="never closed"):
        test_every_stylesheet_closes_every_rule("bad.css")


def test_a_rating_outside_the_three_is_refused(tmp_path: Path) -> None:
    """The counterfactual: the loader must reject a malformed row, not render it."""
    bad = about.CONTENT.read_text().replace("prama: 'Yes'", "prama: Maybe", 1)
    bad = bad.replace("prama: Yes", "prama: Maybe", 1)
    (tmp_path / "c.yaml").write_text(bad)
    with pytest.raises(ValueError, match="Maybe"):
        about.load(tmp_path / "c.yaml")
