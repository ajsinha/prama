"""Accessibility, in the parts that are arithmetic or structure.

Contrast is a formula, so it belongs in a test rather than in a design review:
a palette checked by looking at it passes on the reviewer's monitor and fails
on a projector, a cheap laptop panel, and for the eight per cent of men with a
colour vision deficiency.

The structural checks parse the pages the console actually renders. They catch
the four failures that make an otherwise-usable console unusable and that no
amount of careful markup in one template protects the next one from: an input
with no label, a table with no header cells, an icon that is announced as an
image with no name, and a form control whose only description is placeholder
text that disappears the moment it is typed into.

What this suite is *not*: `axe-core` in a real browser (W9.16). That needs a
DOM and a headless browser, catches things static analysis cannot — computed
contrast after cascade, focus order, ARIA validity — and it is not run here.
This file is the floor, not the ceiling, and saying so is the point.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

import httpx
import pytest

from prama.report.contrast import (
    BODY_TEXT,
    NON_TEXT,
    accessible_on,
    ratio,
    report,
)
from prama.report.palette import (
    DARK_SURFACE,
    DIMENSION_DARK_HEX,
    DIMENSION_HEX,
    DIMENSION_TEXT_DARK_HEX,
    DIMENSION_TEXT_HEX,
    GRID_HEX,
    INK_HEX,
    LIGHT_SURFACE,
    MUTED_HEX,
    UNVERIFIED_GREY,
    UNVERIFIED_GREY_DARK,
    UNVERIFIED_TEXT_DARK_HEX,
    UNVERIFIED_TEXT_HEX,
)

pytestmark = pytest.mark.anyio

CSS = Path(__file__).resolve().parents[2] / "src/prama/web/static/css/prama.css"

PAGES = (
    "/estate",
    "/estate/gaps",
    "/declarations",
    "/declarations/new",
    "/relationships",
    "/relationships/new",
    "/controls",
    "/proposals",
    "/incidents",
    "/reconciliation",
    "/scorecards",
)


class TestContrastArithmetic:
    def test_the_formula_matches_the_standard_s_own_examples(self) -> None:
        """White on black is 21:1 and a colour on itself is 1:1. Without this
        the rest of the file could be measuring the wrong thing consistently."""
        assert ratio("#FFFFFF", "#000000") == pytest.approx(21.0, abs=0.01)
        assert ratio("#777777", "#777777") == pytest.approx(1.0, abs=0.001)
        assert ratio("#FFFFFF", "#777777") == pytest.approx(4.48, abs=0.02)

    def test_short_hex_is_understood(self) -> None:
        assert ratio("#fff", "#000") == pytest.approx(21.0, abs=0.01)

    def test_an_unparseable_colour_raises_rather_than_skipping(self) -> None:
        """A skipped check reports a pass, which is the failure mode this
        whole file exists to prevent."""
        with pytest.raises(ValueError):
            ratio("teal", "#fff")


class TestPaletteContrast:
    def test_ink_and_muted_text_are_legible_on_both_surfaces(self) -> None:
        assert ratio(INK_HEX, LIGHT_SURFACE) >= BODY_TEXT, report(INK_HEX, LIGHT_SURFACE)
        assert ratio(MUTED_HEX, LIGHT_SURFACE) >= BODY_TEXT, report(MUTED_HEX, LIGHT_SURFACE)

    @pytest.mark.parametrize("dimension", sorted(DIMENSION_TEXT_HEX))
    def test_every_dimension_name_is_legible_in_light_mode(self, dimension: str) -> None:
        colour = DIMENSION_TEXT_HEX[dimension]
        assert ratio(colour, LIGHT_SURFACE) >= BODY_TEXT, report(colour, LIGHT_SURFACE)

    @pytest.mark.parametrize("dimension", sorted(DIMENSION_TEXT_DARK_HEX))
    def test_every_dimension_name_is_legible_in_dark_mode(self, dimension: str) -> None:
        colour = DIMENSION_TEXT_DARK_HEX[dimension]
        assert ratio(colour, DARK_SURFACE) >= BODY_TEXT, report(colour, DARK_SURFACE)

    @pytest.mark.parametrize("dimension", sorted(DIMENSION_DARK_HEX))
    def test_dark_mode_fills_meet_the_non_text_threshold(self, dimension: str) -> None:
        colour = DIMENSION_DARK_HEX[dimension]
        assert ratio(colour, DARK_SURFACE) >= NON_TEXT, report(
            colour, DARK_SURFACE, threshold=NON_TEXT
        )

    def test_the_words_not_examined_are_readable(self) -> None:
        """The one place under-contrast would be actively dishonest.

        The whole point of the reserved colour is that unexamined data is
        *visible*; rendering the word too faint to read would be hiding it in
        the approved colour. The mark may sit at the 3:1 non-text floor; the
        sentence beside it may not.
        """
        assert ratio(UNVERIFIED_TEXT_HEX, LIGHT_SURFACE) >= BODY_TEXT, report(
            UNVERIFIED_TEXT_HEX, LIGHT_SURFACE
        )
        assert ratio(UNVERIFIED_TEXT_DARK_HEX, DARK_SURFACE) >= BODY_TEXT, report(
            UNVERIFIED_TEXT_DARK_HEX, DARK_SURFACE
        )

    def test_the_chart_empty_state_uses_the_readable_variant(self) -> None:
        """The counterfactual for the fix: the words must not carry the mark
        colour, on any of the three charts that can be empty."""
        from prama.report import charts

        for svg in (
            charts.sparkline([], label="a"),
            charts.score_ring(None, label="a"),
            charts.bars([charts.Series("a", ())], label="a"),
        ):
            assert "not examined" in svg or "—" in svg
            assert "var(--unverified-grey-text" in svg
            assert 'fill="var(--unverified-grey,' not in svg

    def test_unverified_grey_is_legible_on_both_surfaces(self) -> None:
        """The most important one to get right: "not examined" is the state
        this product refuses to hide, and hiding it in low contrast would be
        hiding it."""
        assert ratio(UNVERIFIED_GREY, LIGHT_SURFACE) >= NON_TEXT, report(
            UNVERIFIED_GREY, LIGHT_SURFACE, threshold=NON_TEXT
        )
        assert ratio(UNVERIFIED_GREY_DARK, DARK_SURFACE) >= BODY_TEXT, report(
            UNVERIFIED_GREY_DARK, DARK_SURFACE
        )

    def test_a_derived_variant_stays_the_same_colour(self) -> None:
        """Hue preserved, lightness moved. A "readable" variant that changes
        hue would break the palette's one promise — that the same colour means
        the same dimension everywhere."""
        for name, brand in DIMENSION_HEX.items():
            derived = DIMENSION_TEXT_HEX[name]
            brand_channels = sorted(range(3), key=lambda i: int(brand[1:][i * 2 : i * 2 + 2], 16))
            derived_channels = sorted(
                range(3), key=lambda i: int(derived[1:][i * 2 : i * 2 + 2], 16)
            )
            assert brand_channels == derived_channels, name

    def test_the_derivation_stops_at_the_first_passing_shade(self) -> None:
        """So a darkened variant stays as close to the brand colour as the
        standard allows, rather than defaulting to near-black.

        Only checked where darkening actually happened: two of the eight hues
        already pass on white and are returned untouched, which is why the
        bound is applied to changed colours alone.
        """
        for name, brand in DIMENSION_HEX.items():
            derived = DIMENSION_TEXT_HEX[name]
            measured = ratio(derived, LIGHT_SURFACE)
            assert measured >= BODY_TEXT, name
            if derived.upper() != brand.upper():
                assert measured < BODY_TEXT + 0.5, f"{name} overshot: {measured:.2f}"

    def test_an_already_passing_colour_is_left_alone(self) -> None:
        assert accessible_on(INK_HEX, LIGHT_SURFACE) == INK_HEX


class TestStylesheetAgreesWithTheArithmetic:
    """Derive, never restate. The CSS holds a copy of these values because a
    stylesheet cannot call Python; this is what keeps the copy honest."""

    def test_the_light_text_tokens_match_what_is_computed(self) -> None:
        css = CSS.read_text()
        for name, value in DIMENSION_TEXT_HEX.items():
            assert f"--dim-{name}-text: {value};" in css, name

    def test_the_dark_text_tokens_match_what_is_computed(self) -> None:
        css = CSS.read_text()
        for name, value in DIMENSION_TEXT_DARK_HEX.items():
            assert f"--dim-{name}-text: {value};" in css, name

    def test_no_stray_dimension_text_token_exists(self) -> None:
        """A token the arithmetic did not produce is a hand-edit, and a
        hand-edited one is the one that will be wrong."""
        found = set(re.findall(r"--dim-([a-z]+)-text:\s*(#[0-9A-Fa-f]{6});", CSS.read_text()))
        expected = {(n, v) for n, v in DIMENSION_TEXT_HEX.items()} | {
            (n, v) for n, v in DIMENSION_TEXT_DARK_HEX.items()
        }
        assert found <= expected, found - expected

    def test_the_grid_colour_is_visible_against_the_card(self) -> None:
        """A chart's empty track at 1.05:1 is an invisible chart with an
        invisible axis, which reads as a rendering bug."""
        assert ratio(GRID_HEX, LIGHT_SURFACE) > 1.1, report(GRID_HEX, LIGHT_SURFACE)


class _Structure(HTMLParser):
    """Enough of a parse to answer four structural questions."""

    def __init__(self) -> None:
        super().__init__()
        self.inputs: list[dict[str, str]] = []
        self.labels_for: set[str] = set()
        self.images_without_text: list[str] = []
        self.tables = 0
        self.tables_with_headers = 0
        self._in_table = False
        self._table_had_header = False
        self.landmarks: set[str] = set()
        self.first_h1: str | None = None
        self.headings: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {k: (v or "") for k, v in attrs}
        if tag in ("input", "select", "textarea"):
            if attributes.get("type") not in ("hidden", "submit", "button"):
                self.inputs.append(attributes)
        elif tag == "label" and attributes.get("for"):
            self.labels_for.add(attributes["for"])
        elif tag == "img" and not attributes.get("alt"):
            self.images_without_text.append(attributes.get("src", "?"))
        elif tag == "table":
            self._in_table, self._table_had_header = True, False
            self.tables += 1
        elif tag == "th":
            self._table_had_header = True
        elif tag in ("main", "nav", "footer", "header"):
            self.landmarks.add(tag)
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.headings.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == "table" and self._in_table:
            self._in_table = False
            if self._table_had_header:
                self.tables_with_headers += 1


async def _parse(ui: httpx.AsyncClient, path: str) -> _Structure:
    response = await ui.get(path)
    assert response.status_code == 200, f"{path} returned {response.status_code}"
    structure = _Structure()
    structure.feed(response.text)
    return structure


class TestPageStructure:
    @pytest.mark.parametrize("path", PAGES)
    async def test_every_form_control_has_a_name(self, ui: httpx.AsyncClient, path: str) -> None:
        """An input a screen reader announces as "edit text, blank" is an input
        nobody can fill in. Placeholder text does not count: it is not exposed
        as a name and it vanishes the moment the field is typed into."""
        structure = await _parse(ui, path)
        unnamed = [
            attributes
            for attributes in structure.inputs
            if not (
                attributes.get("aria-label")
                or attributes.get("aria-labelledby")
                or (attributes.get("id") and attributes["id"] in structure.labels_for)
            )
        ]
        assert unnamed == [], f"{path}: unnamed controls {unnamed}"

    @pytest.mark.parametrize("path", PAGES)
    async def test_every_table_has_header_cells(self, ui: httpx.AsyncClient, path: str) -> None:
        """A table of <td> is a grid of unlabelled values: read row by row it
        says numbers with no idea what they are."""
        structure = await _parse(ui, path)
        assert structure.tables == structure.tables_with_headers, path

    @pytest.mark.parametrize("path", PAGES)
    async def test_the_landmarks_are_present(self, ui: httpx.AsyncClient, path: str) -> None:
        structure = await _parse(ui, path)
        assert {"nav", "main"} <= structure.landmarks, path

    @pytest.mark.parametrize("path", PAGES)
    async def test_there_is_exactly_one_first_level_heading(
        self, ui: httpx.AsyncClient, path: str
    ) -> None:
        structure = await _parse(ui, path)
        assert structure.headings.count("h1") == 1, f"{path}: {structure.headings}"

    @pytest.mark.parametrize("path", PAGES)
    async def test_no_image_lacks_a_text_alternative(
        self, ui: httpx.AsyncClient, path: str
    ) -> None:
        structure = await _parse(ui, path)
        assert structure.images_without_text == [], path

    @pytest.mark.parametrize("path", PAGES)
    async def test_every_decorative_icon_is_hidden_from_the_reader(
        self, ui: httpx.AsyncClient, path: str
    ) -> None:
        """Bootstrap icons are <i> elements with no text. Left exposed, a
        screen reader announces a stream of nothing between every label."""
        body = (await ui.get(path)).text
        for match in re.finditer(r"<i class=\"bi[^\"]*\"[^>]*>", body):
            assert 'aria-hidden="true"' in match.group(0), f"{path}: {match.group(0)}"


class TestChartsAreNotTheOnlyCopy:
    async def test_the_estate_map_has_a_list_of_the_same_datasets(
        self, ui: httpx.AsyncClient
    ) -> None:
        """A picture is not an interface. Everything on the canvas is also in a
        table — not as a fallback for a broken canvas, but because finding one
        named dataset among two thousand is something a table does better for
        everybody."""
        body = (await ui.get("/estate")).text
        assert 'id="map-table"' in body
        assert "as a list" in body
