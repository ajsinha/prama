"""The themes, and the arithmetic that keeps the palette honest in each.

DishtaYantra ships a named-theme system — one ``data-theme`` attribute, a token
block per theme, and a Bootstrap base of ``light`` or ``dark`` underneath — and
Prama uses the same shape so a template moves between the two products
unchanged.

What Prama adds is the part it cannot do without. Its six dimension hues are a
*language*: the same colour means the same dimension on every chart, chip and
scorecard, and a reader learns it once. A theme that re-picked those hues by
eye would break the language on the theme where it happened to look best. So
each theme declares only its **surfaces**, and every dimension token is derived
from the brand hue against that surface:

* the **fill** — a bar, a ring, a status dot — darkened or lifted only as far
  as WCAG 1.4.11's 3:1 requires;
* the **text** — the dimension's name, a verdict — to 4.5:1.

Two tokens because they are two jobs with two thresholds. Accuracy Teal on
white is 2.63:1: fine as a large area, illegible as a word, and failing even as
a bar under 1.4.11. Deriving both means a new theme is four colours and a
background, not forty hand-picked hex codes that will drift.

``tests/web/test_accessibility.py`` checks every theme against both thresholds,
so a theme cannot ship looking good and reading badly.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses

from prama.report.contrast import BODY_TEXT, NON_TEXT, accessible_on
from prama.report.palette import (
    DIMENSION_DARK_HEX,
    DIMENSION_HEX,
    UNVERIFIED_GREY,
    UNVERIFIED_GREY_DARK,
)


@dataclasses.dataclass(frozen=True, slots=True)
class Theme:
    """One named theme: its surfaces, and which hue family it draws from."""

    name: str
    label: str
    #: ``light`` or ``dark``. Chooses Bootstrap 5.3's own base, which everything
    #: Prama does not style itself inherits.
    base: str
    #: The card background. Contrast is measured against this rather than
    #: against the page, because text and chart marks sit on cards — checking
    #: the page would pass a colour that fails where it is actually used.
    surface: str
    body: str
    ink: str
    muted: str
    border: str
    #: The masthead. A gradient, because a flat bar reads as unfinished at this
    #: size and every one of these brands uses one.
    header: str
    link: str
    accent: str
    #: Why this theme exists, shown in the picker. A theme nobody can tell apart
    #: from the next one is a theme nobody chooses deliberately.
    note: str = ""

    @property
    def is_dark(self) -> bool:
        return self.base == "dark"

    @property
    def source_hues(self) -> dict[str, str]:
        """The hue family this theme derives from.

        Dark themes start from the lifted set: darkening a mid-tone teal
        against black would make it *less* legible, and the derivation only
        moves away from the background.
        """
        return DIMENSION_DARK_HEX if self.is_dark else DIMENSION_HEX

    @property
    def unverified_source(self) -> str:
        return UNVERIFIED_GREY_DARK if self.is_dark else UNVERIFIED_GREY

    def fills(self) -> dict[str, str]:
        """Dimension colours for marks, at the 3:1 non-text threshold."""
        return {
            name: accessible_on(value, self.surface, threshold=NON_TEXT)
            for name, value in self.source_hues.items()
        }

    def texts(self) -> dict[str, str]:
        """Dimension colours for words, at the 4.5:1 body-text threshold."""
        return {
            name: accessible_on(value, self.surface, threshold=BODY_TEXT)
            for name, value in self.source_hues.items()
        }

    def unverified_fill(self) -> str:
        return accessible_on(self.unverified_source, self.surface, threshold=NON_TEXT)

    def unverified_text(self) -> str:
        return accessible_on(self.unverified_source, self.surface, threshold=BODY_TEXT)


#: Every theme, in the order the picker offers them.
THEMES: tuple[Theme, ...] = (
    Theme(
        name="light",
        label="Prama light",
        base="light",
        surface="#FFFFFF",
        body="#F6F7FB",
        ink="#14182E",
        muted="#6B7391",
        border="#DFE3EF",
        header="linear-gradient(135deg, #0E1A46 0%, #1B2A63 50%, #0E1A46 100%)",
        link="#2B3FA8",
        accent="#2B3FA8",
        note="The default. Prama Indigo on a cool white ground.",
    ),
    Theme(
        name="dark",
        label="Prama dark",
        base="dark",
        surface="#141A33",
        body="#0B0F21",
        ink="#E8EBF5",
        muted="#8891AD",
        border="#262E50",
        header="linear-gradient(135deg, #080D20 0%, #141C3F 50%, #080D20 100%)",
        link="#7D8FE0",
        accent="#7D8FE0",
        note="The same palette on a night ground, for long sessions.",
    ),
    Theme(
        name="crimson",
        label="Harvard crimson",
        base="light",
        # Harvard Crimson is #A51C30. Used for the masthead and the accent, and
        # deliberately *not* for any dimension: it sits between the validity red
        # and the uniqueness orange, and a brand colour that reads as a
        # dimension would corrupt the language on this theme alone.
        surface="#FFFFFF",
        body="#F7F4F4",
        ink="#1C1416",
        muted="#6E5C60",
        border="#E7DDDF",
        header="linear-gradient(135deg, #6B1220 0%, #A51C30 55%, #6B1220 100%)",
        link="#8C1727",
        accent="#A51C30",
        note="Harvard Crimson on warm paper. An academic, print-like register.",
    ),
    Theme(
        name="bmo",
        label="BMO blue",
        base="light",
        # BMO Blue #0079C0 with the red roundel as the accent, on cool grey.
        surface="#FFFFFF",
        body="#F1F5F9",
        ink="#0B2545",
        muted="#5A6E85",
        border="#D8E3EE",
        header="linear-gradient(135deg, #0B2545 0%, #0A4D86 55%, #0079C0 100%)",
        link="#0A4D86",
        accent="#E11B22",
        note="BMO Blue on cool grey. A retail-banking register.",
    ),
    Theme(
        name="wallstreet",
        label="Wall Street",
        base="dark",
        # A trading terminal: amber on black, cyan for data. The convention is
        # decades old and the people who read these screens all day already
        # know it — which is the only reason to adopt somebody else's palette.
        surface="#141210",
        body="#0A0A0A",
        ink="#FFB43D",
        muted="#9A835A",
        border="#332D20",
        header="linear-gradient(135deg, #000000 0%, #14120C 50%, #000000 100%)",
        link="#FFCF80",
        accent="#FFA028",
        note="Amber on black, as a terminal. For a desk that lives in one.",
    ),
)

BY_NAME: dict[str, Theme] = {theme.name: theme for theme in THEMES}

#: The Bootstrap base each theme sits on, for the client-side switcher.
BASES: dict[str, str] = {theme.name: theme.base for theme in THEMES}
