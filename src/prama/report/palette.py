"""The colours a chart may use, and the two forms they come in.

The console wants CSS custom properties, so a chart follows the reader's theme
and their density setting without being re-rendered. A PDF wants literal hex,
because a print artefact has no stylesheet and a ``var(--dim-accuracy)`` in a
PDF renders as nothing at all — silently, as a blank chart that looks like a
chart with no data.

Both come from the same table, which is the point: docs/brand.md §4 is the
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


@dataclasses.dataclass(frozen=True, slots=True)
class Palette:
    """How a chart names its colours."""

    #: When true, colours are emitted as ``var(--token, #fallback)`` so the
    #: console's theme drives them. The fallback is not decoration: an SVG
    #: pulled out of the page — saved, emailed, embedded — keeps its colours.
    themed: bool = True

    def dimension(self, name: str) -> str:
        hex_value = DIMENSION_HEX.get(name.lower(), MUTED_HEX)
        if not self.themed or name.lower() not in DIMENSION_HEX:
            return hex_value
        return f"var(--dim-{name.lower()}, {hex_value})"

    def unverified(self) -> str:
        return f"var(--unverified-grey, {UNVERIFIED_GREY})" if self.themed else UNVERIFIED_GREY

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
