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
    rgb,
)
from prama.report.palette import (
    DARK_SURFACE,
    DIMENSION_DARK_HEX,
    DIMENSION_HEX,
    DIMENSION_TEXT_DARK_HEX,
    DIMENSION_TEXT_HEX,
    INK_HEX,
    LIGHT_SURFACE,
    MUTED_HEX,
    UNVERIFIED_GREY,
    UNVERIFIED_GREY_DARK,
    UNVERIFIED_TEXT_DARK_HEX,
    UNVERIFIED_TEXT_HEX,
)
from prama.report.themes import THEMES, Theme

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
    "/controls/studio",
    "/controls/build",
    "/proposals",
    "/evidence",
    "/reports",
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


class TestEveryThemeIsLegible:
    """The check that makes five themes safe to ship.

    A theme declares surfaces; every dimension colour is derived against them.
    So this is not a spot check of colours somebody chose — it is the assertion
    that the derivation actually cleared the threshold for every hue, in every
    theme, for both of the jobs a colour does here.
    """

    @pytest.mark.parametrize("theme", THEMES, ids=lambda t: t.name)
    def test_every_mark_meets_the_non_text_threshold(self, theme: Theme) -> None:
        """WCAG 1.4.11. A bar, a ring or a status dot carries meaning, and it
        has to be distinguishable from the card behind it."""
        for name, colour in theme.fills().items():
            assert ratio(colour, theme.surface) >= NON_TEXT, f"{theme.name}/{name}: " + report(
                colour, theme.surface, threshold=NON_TEXT
            )

    @pytest.mark.parametrize("theme", THEMES, ids=lambda t: t.name)
    def test_every_dimension_name_meets_the_body_threshold(self, theme: Theme) -> None:
        for name, colour in theme.texts().items():
            assert ratio(colour, theme.surface) >= BODY_TEXT, f"{theme.name}/{name}: " + report(
                colour, theme.surface
            )

    @pytest.mark.parametrize("theme", THEMES, ids=lambda t: t.name)
    def test_the_words_not_examined_are_readable(self, theme: Theme) -> None:
        """The one place under-contrast would be actively dishonest: the point
        of the reserved colour is that unexamined data is *visible*."""
        assert ratio(theme.unverified_text(), theme.surface) >= BODY_TEXT, report(
            theme.unverified_text(), theme.surface
        )

    def test_the_raised_ground_matches_the_stylesheet(self) -> None:
        """The blend Python computes and the one the browser paints must be the
        same colour.

        ``--bg-raised`` is translucent, so no token holds its actual value and
        the derivation has to compute it. Two numbers for one ground is a
        ground nothing has really checked — which is how a table header came to
        sit at 4.12:1 with every arithmetic test passing.
        """
        from prama.report.themes import RAISED_ALPHA, RAISED_GREY

        declared = re.search(r"--bg-raised:\s*rgba\(([^)]*)\)", CSS.read_text())
        assert declared, "prama.css no longer declares --bg-raised as an rgba()"
        red, green, blue, alpha = [part.strip() for part in declared.group(1).split(",")]
        assert (int(red), int(green), int(blue)) == rgb(RAISED_GREY)
        assert float(alpha) == RAISED_ALPHA

    @pytest.mark.parametrize("theme", THEMES, ids=lambda t: t.name)
    def test_every_dimension_word_is_legible_on_every_ground(self, theme: Theme) -> None:
        """A card, the page behind it, and a striped row.

        Deriving against one and rendering on another is the defect axe found
        three times over. This is that check without a browser, so the next one
        fails in a unit test rather than in an audit.
        """
        for name, colour in theme.texts().items():
            for ground in theme.grounds:
                assert ratio(colour, ground) >= BODY_TEXT, (
                    f"{theme.name}: {name} {colour} on {ground} is {ratio(colour, ground):.2f}:1"
                )

    @pytest.mark.parametrize("theme", THEMES, ids=lambda t: t.name)
    def test_every_dimension_mark_is_visible_on_every_ground(self, theme: Theme) -> None:
        for name, colour in theme.fills().items():
            for ground in theme.grounds:
                assert ratio(colour, ground) >= NON_TEXT, (
                    f"{theme.name}: {name} {colour} on {ground} is {ratio(colour, ground):.2f}:1"
                )

    @pytest.mark.parametrize("theme", THEMES, ids=lambda t: t.name)
    def test_every_text_token_is_legible_on_every_ground(self, theme: Theme) -> None:
        """The tokens the stylesheet actually emits, on all three grounds.

        The gap axe found: `muted` was measured against `surface` and passed at
        4.68:1, while the footer sits on `body` where it was 4.37:1 — and on a
        striped row where it was 4.12:1. A colour checked against the background
        the test assumed rather than the one it renders on is a colour nobody
        has checked.

        Asserted on the *derived* values, because those are what
        ``generate_themes.py`` writes. Checking the declarations would pass
        while the stylesheet shipped something else.
        """
        for name in ("legible_ink", "legible_muted", "legible_link"):
            colour = getattr(theme, name)
            for ground in theme.grounds:
                assert ratio(colour, ground) >= BODY_TEXT, (
                    f"{theme.name}: {name} {colour} on {ground} is {ratio(colour, ground):.2f}:1"
                )

    @pytest.mark.parametrize("theme", THEMES, ids=lambda t: t.name)
    def test_the_accent_is_a_mark_and_is_held_to_a_marks_threshold(self, theme: Theme) -> None:
        """Three to one, not four and a half, and the reason is checkable:
        nothing in the stylesheet reads ``color: var(--accent)``. If that ever
        changes, this test is wrong and should start failing."""
        assert "color: var(--accent)" not in CSS.read_text()
        for ground in theme.grounds:
            assert ratio(theme.legible_accent, ground) >= NON_TEXT

    @pytest.mark.parametrize("theme", THEMES, ids=lambda t: t.name)
    def test_ink_and_muted_text_are_legible(self, theme: Theme) -> None:
        assert ratio(theme.ink, theme.surface) >= BODY_TEXT, report(theme.ink, theme.surface)
        assert ratio(theme.muted, theme.surface) >= BODY_TEXT, report(theme.muted, theme.surface)

    @pytest.mark.parametrize("theme", THEMES, ids=lambda t: t.name)
    def test_a_dimension_keeps_its_hue_family(self, theme: Theme) -> None:
        """The palette's one promise: the same colour means the same dimension
        everywhere. A theme that re-ordered a hue's channels would break the
        language on that theme alone, which is worse than not having it."""
        for name, source in theme.source_hues.items():
            for derived in (theme.fills()[name], theme.texts()[name]):
                assert _channel_order(source) == _channel_order(derived), (
                    f"{theme.name}/{name}: {source} -> {derived}"
                )

    #: The six spectrum hues. ``integrity`` and ``conformity`` are excluded
    #: because they have no spectrum hue of their own and take the brand blues
    #: by design (docs/brand.md §4) — so on the default theme the accent
    #: legitimately *is* the integrity colour.
    SPECTRUM = ("accuracy", "completeness", "consistency", "timeliness", "uniqueness", "validity")

    def test_no_theme_borrows_a_spectrum_hue_for_its_brand(self) -> None:
        """A brand colour that reads as one of the six corrupts the language.

        Harvard Crimson sits between validity red and uniqueness orange, which
        is exactly why it is the masthead and never a dimension. The rule is
        about the six, not about integrity and conformity, which take the brand
        blues deliberately.
        """
        for theme in THEMES:
            for name in self.SPECTRUM:
                assert theme.fills()[name].upper() != theme.accent.upper(), (
                    f"{theme.name}/{name} is the same colour as the brand accent"
                )

    def test_a_brand_accent_is_distinguishable_from_every_spectrum_hue(self) -> None:
        """Not merely different — far enough apart that a reader does not have
        to decide whether the masthead red is the validity red."""
        from prama.report.contrast import rgb

        for theme in THEMES:
            accent = rgb(theme.accent)
            for name in self.SPECTRUM:
                hue = rgb(theme.fills()[name])
                distance = sum(abs(a - b) for a, b in zip(accent, hue, strict=True))
                assert distance > 60, f"{theme.name}/{name} is too close to the accent"


def _channel_order(colour: str) -> list[int]:
    raw = colour.lstrip("#")
    return sorted(range(3), key=lambda i: int(raw[i * 2 : i * 2 + 2], 16))


class TestTheGeneratedStylesheetIsNotHandEdited:
    """Derive, never restate. The stylesheet cannot call Python, so it holds a
    copy — and this is what keeps the copy honest."""

    def test_regenerating_produces_exactly_what_is_checked_in(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "generate_themes",
            Path(__file__).resolve().parents[2] / "scripts" / "generate_themes.py",
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert module.TARGET.read_text(encoding="utf-8") == module.render(), (
            "themes.css is out of date or hand-edited. Run: python scripts/generate_themes.py"
        )

    def test_every_theme_has_a_block(self) -> None:
        css = (
            Path(__file__).resolve().parents[2] / "src/prama/web/static/css/themes.css"
        ).read_text()
        for theme in THEMES:
            marker = (
                ':root, [data-theme="light"]'
                if theme.name == "light"
                else f'[data-theme="{theme.name}"]'
            )
            assert marker in css, theme.name

    def test_prama_css_holds_no_second_copy_of_a_dimension_colour(self) -> None:
        """A copy in the hand-written stylesheet would be the one nobody
        checked against a threshold."""
        css = CSS.read_text()
        assert "--dim-accuracy:" not in css
        assert "--dim-accuracy-text:" not in css


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
        #: Depth of open <label> elements. An input nested inside a label is
        #: labelled by it — implicit labelling, which is valid, is what every
        #: Bootstrap radio list uses, and a checker that only understood
        #: ``for=`` would fail correct markup and get switched off.
        self._label_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {k: (v or "") for k, v in attrs}
        if tag in ("input", "select", "textarea"):
            if attributes.get("type") not in ("hidden", "submit", "button"):
                attributes = {**attributes, "_wrapped_in_label": str(self._label_depth > 0)}
                self.inputs.append(attributes)
        elif tag == "label":
            self._label_depth += 1
            if attributes.get("for"):
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
        if tag == "label":
            self._label_depth = max(0, self._label_depth - 1)
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
                or attributes.get("_wrapped_in_label") == "True"
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
