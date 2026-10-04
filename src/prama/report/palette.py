"""The colours a chart may use, and the two forms they come in.

The console wants CSS custom properties, so a chart follows the reader's theme
and their density setting without being re-rendered. A PDF wants literal hex,
because a print artefact has no stylesheet and a ``var(--dim-accuracy)`` in a
PDF renders as nothing at all — silently, as a blank chart that looks like a
chart with no data.

Both come from the same table, which is the point: docs/reference/brand.md §4 is the
authority, and a second list of hex codes typed into a print renderer is the
thing that drifts.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses

#: The six dimensions, and the two brand colours a chart is allowed to reach
#: for. Named by what they mean, never by what they look like: a token called
#: ``validity`` cannot end up on a chart about something else, and a token
#: called ``red`` will.
DIMENSION_HEX: dict[str, str] = {
    "accuracy": "#00B3A4",
    "completeness": "#2FB673",
    "consistency": "#8CBF3F",
    "timeliness": "#E8B33A",
    "uniqueness": "#E8823A",
    "validity": "#D9534F",
    # Two more dimensions exist in the language and have no spectrum hue of
    # their own; they take the brand blues rather than borrowing a dimension's.
    "integrity": "#2B3FA8",
    "conformity": "#5A6480",
}

#: Reserved, absolutely, for "stale or not yet examined". Nothing else may use
#: it, in any chart, ever. Most products render that state as healthy or hide
#: it; giving it a colour nothing else may take is how the decision survives a
#: designer in a hurry.
UNVERIFIED_GREY = "#8A93AD"

INK_HEX = "#14182E"
MUTED_HEX = "#6B7391"
GRID_HEX = "#DFE3EF"

#: The card backgrounds the palette has to work on. Not the page background:
#: text and chart marks sit on cards, and checking against the page would pass
#: a colour that fails where it is actually used.
LIGHT_SURFACE = "#FFFFFF"
DARK_SURFACE = "#141A33"

#: The brand spectrum lifted for a dark ground. Each keeps its identity — a
#: shifted teal is still accuracy — because re-hueing here would break the one
#: promise the palette makes.
DIMENSION_DARK_HEX: dict[str, str] = {
    "accuracy": "#2AD4C5",
    "completeness": "#4FD693",
    "consistency": "#A8DB5F",
    "timeliness": "#F2C65C",
    "uniqueness": "#F29A5C",
    "validity": "#EA726E",
    "integrity": "#7D8FE0",
    "conformity": "#9AA3BD",
}

UNVERIFIED_GREY_DARK = "#9AA3BD"


def _readable(source: dict[str, str], background: str) -> dict[str, str]:
    """Text-safe variants of a fill palette, derived rather than hand-picked.

    The brand spectrum is a **fill** palette: Accuracy Teal on white is 2.63:1,
    which is fine behind a bar and illegible as a word. Rather than change the
    brand or ship unreadable text, the readable shade is computed from the
    brand hue — hue preserved, lightness moved away from the background — so
    teal still means accuracy and nobody has to hand-pick eight more hex codes
    that will drift from the eight above.
    """
    from prama.report.contrast import BODY_TEXT, accessible_on

    return {
        name: accessible_on(value, background, threshold=BODY_TEXT)
        for name, value in source.items()
    }


#: What a dimension's *name* is printed in. Computed at import: one authority,
#: no second list. ``tests/web/test_accessibility.py`` asserts the stylesheet
#: agrees with these, so the CSS cannot drift from the arithmetic.
DIMENSION_TEXT_HEX: dict[str, str] = _readable(DIMENSION_HEX, LIGHT_SURFACE)
DIMENSION_TEXT_DARK_HEX: dict[str, str] = _readable(DIMENSION_DARK_HEX, DARK_SURFACE)

#: "Not examined" as a *word*. Unverified Grey is 3.06:1 on a white card —
#: enough for a dashed ring, not enough for the sentence beside it. This is the
#: one place where under-contrast would be actively dishonest: the whole point
#: of the reserved colour is that unexamined data is *visible*, and rendering
#: the word too faint to read would be hiding it in the approved colour.
UNVERIFIED_TEXT_HEX: str = _readable({"g": UNVERIFIED_GREY}, LIGHT_SURFACE)["g"]
UNVERIFIED_TEXT_DARK_HEX: str = _readable({"g": UNVERIFIED_GREY_DARK}, DARK_SURFACE)["g"]


@dataclasses.dataclass(frozen=True, slots=True)
class Palette:
    """How a chart names its colours."""

    #: When true, colours are emitted as ``var(--token, #fallback)`` so the
    #: console's theme drives them. The fallback is not decoration: an SVG
    #: pulled out of the page — saved, emailed, embedded — keeps its colours.
    themed: bool = True

    def dimension(self, name: str) -> str:
        """The fill colour: bar bodies, ring strokes, chart marks."""
        hex_value = DIMENSION_HEX.get(name.lower(), MUTED_HEX)
        if not self.themed or name.lower() not in DIMENSION_HEX:
            return hex_value
        return f"var(--dim-{name.lower()}, {hex_value})"

    def dimension_text(self, name: str) -> str:
        """The colour a dimension's *name* is printed in.

        A separate accessor because they are separate jobs and the same hue
        cannot do both: a fill needs 3:1 against its surroundings, a word needs
        4.5:1, and the brand spectrum clears the first and not the second.
        """
        hex_value = DIMENSION_TEXT_HEX.get(name.lower(), MUTED_HEX)
        if not self.themed or name.lower() not in DIMENSION_TEXT_HEX:
            return hex_value
        return f"var(--dim-{name.lower()}-text, {hex_value})"

    def unverified(self) -> str:
        """The mark: a dashed ring, the track of an absent bar."""
        return f"var(--unverified-grey, {UNVERIFIED_GREY})" if self.themed else UNVERIFIED_GREY

    def unverified_text(self) -> str:
        """The words "not examined" themselves, which have to be readable."""
        if not self.themed:
            return UNVERIFIED_TEXT_HEX
        return f"var(--unverified-grey-text, {UNVERIFIED_TEXT_HEX})"

    def ink(self) -> str:
        return f"var(--text-primary, {INK_HEX})" if self.themed else INK_HEX

    def muted(self) -> str:
        return f"var(--text-muted, {MUTED_HEX})" if self.themed else MUTED_HEX

    def grid(self) -> str:
        return f"var(--border-color, {GRID_HEX})" if self.themed else GRID_HEX


#: What the console uses.
SCREEN = Palette(themed=True)
#: What a PDF or a print stylesheet uses. Literal, because there is no theme.
PRINT = Palette(themed=False)
