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

from prama.report.contrast import BODY_TEXT, NON_TEXT, accessible_on, blend
from prama.report.palette import (
    DIMENSION_DARK_HEX,
    DIMENSION_HEX,
    UNVERIFIED_GREY,
    UNVERIFIED_GREY_DARK,
)

#: The grey behind a striped row, and how much of it shows. Mirrors
#: ``--bg-raised`` in prama.css; a test asserts the two agree, because a blend
#: computed from one number here and painted from another there is a ground
#: nothing has checked.
RAISED_GREY = "#7F7F7F"
RAISED_ALPHA = 0.08


@dataclasses.dataclass(frozen=True, slots=True)
class MayaTokens:
    """The rest of Maya's token set for one theme, beyond the surfaces.

    Emitted as ``--maya-*`` custom properties, so the console's chrome — the
    gradient navigation, mega-menus, cards and footer — is Maya's stylesheet
    rather than a lookalike. The names say "crimson" in Maya because they name
    a role (the accent), not a hue; here they are named for the role.
    """

    strong: str
    deep: str
    tint: str
    indigo: str
    on_accent: str
    ok: str
    warn: str
    bad: str
    highlight: str
    heading: str
    #: The navigation gradient: from, via, to. White text sits on all three.
    nav: tuple[str, str, str]
    glow: str


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
    maya: MayaTokens | None = None

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

    @property
    def raised(self) -> str:
        """The striped-row ground, computed rather than declared.

        ``--bg-raised`` is a translucent grey over whatever is behind it, so its
        actual colour is a blend and no token holds it. Computing it here is the
        only way the derivation can account for it — and a table header was
        failing at 4.12:1 precisely because nothing did.
        """
        return blend(RAISED_GREY, self.body, RAISED_ALPHA)

    @property
    def grounds(self) -> tuple[str, ...]:
        """Every background a coloured word can land on.

        A card, the page behind it, and a striped row. Deriving against one of
        them and rendering on another is the defect axe found three times over:
        a colour checked against the background the test assumed rather than
        the one it renders on is a colour nobody has checked.
        """
        return (self.surface, self.body, self.raised)

    def _legible(self, colour: str, threshold: float) -> str:
        """The nearest shade legible on **every** ground, not the first one.

        Applied in turn: each pass only moves further from the background, so
        the result of the last pass still satisfies the earlier ones. Taking
        the worst ground up front would be equivalent and would need this code
        to know which ground is worst for a given hue, which it does not.
        """
        for ground in self.grounds:
            colour = accessible_on(colour, ground, threshold=threshold)
        return colour

    @property
    def legible_ink(self) -> str:
        return self._legible(self.ink, BODY_TEXT)

    @property
    def legible_muted(self) -> str:
        return self._legible(self.muted, BODY_TEXT)

    @property
    def legible_link(self) -> str:
        return self._legible(self.link, BODY_TEXT)

    @property
    def legible_accent(self) -> str:
        """The brand colour, at the non-text threshold.

        Three to one rather than four and a half: ``--accent`` is never used for
        words — nothing in the stylesheet reads ``color: var(--accent)`` — and
        holding a brand mark to a text threshold would move it further from the
        brand than the standard requires. A test asserts it stays a mark.
        """
        return self._legible(self.accent, NON_TEXT)

    def fills(self) -> dict[str, str]:
        """Dimension colours for marks, at the 3:1 non-text threshold."""
        return {name: self._legible(value, NON_TEXT) for name, value in self.source_hues.items()}

    def texts(self) -> dict[str, str]:
        """Dimension colours for words, at the 4.5:1 body-text threshold."""
        return {name: self._legible(value, BODY_TEXT) for name, value in self.source_hues.items()}

    def unverified_fill(self) -> str:
        return self._legible(self.unverified_source, NON_TEXT)

    def unverified_text(self) -> str:
        return self._legible(self.unverified_source, BODY_TEXT)


#: Every theme, in the order the picker offers them: exactly Maya's four, under
#: Maya's keys and names, so Prama and Maya read as one family on the same desk
#: and a user's choice means the same thing in both. The colours are Maya's
#: tokens (maya/web/static/css/tokens.css): canvas -> body, slate -> muted,
#: heading -> link, crimson -> accent, nav-from/via/to -> the masthead. The
#: dimension hues are still derived here, so the contrast guarantees hold.
THEMES: tuple[Theme, ...] = (
    Theme(
        name="light",
        label="Crimson",
        base="light",
        surface="#FFFFFF",
        body="#F7F5F2",
        ink="#1A1A1A",
        muted="#6B7480",
        border="#E3DED7",
        header="linear-gradient(100deg, #5C0E1B 0%, #A51C30 48%, #293352 100%)",
        link="#A51C30",
        accent="#A51C30",
        note="The default: Harvard crimson over indigo on warm paper.",
        maya=MayaTokens(
            strong="#8A1626", deep="#6E1120", tint="#FBEEF0", indigo="#293352",
            on_accent="#FFFFFF", ok="#1E6B3A", warn="#7A5200", bad="#8A1626",
            highlight="#F4DDA0", heading="#6E1120", nav=("#5C0E1B", "#A51C30", "#293352"),
            glow="#F3C6CF",
        ),
    ),
    Theme(
        name="dark",
        label="Dark",
        base="dark",
        surface="#1F1F23",
        body="#151517",
        ink="#ECECEF",
        muted="#8996A0",
        border="#34343A",
        header="linear-gradient(100deg, #2E0810 0%, #6E1120 48%, #1B2138 100%)",
        # Maya's rose (#DE6B81) sits 38 units from the validity red on this
        # ground, so as a *mark* it would read as a failing dimension. The
        # accent moves towards pink just far enough to clear the 60-unit guard;
        # links and headings keep Maya's rose, where no dimension can be meant.
        link="#DE6B81",
        accent="#E473AE",
        note="Maya's night ground, with a rose accent, for long sessions.",
        maya=MayaTokens(
            strong="#D4526A", deep="#E07A8E", tint="#2A1A1E", indigo="#A9B6D6",
            on_accent="#151517", ok="#7FD39B", warn="#E8C26A", bad="#F08A9C",
            highlight="#5A4712", heading="#DE6B81", nav=("#2E0810", "#6E1120", "#1B2138"),
            glow="#4A2530",
        ),
    ),
    Theme(
        name="blue",
        label="Blue",
        base="light",
        surface="#FFFFFF",
        body="#F0F5FA",
        ink="#1E293B",
        muted="#536578",
        border="#DCE4EE",
        header="linear-gradient(100deg, #002654 0%, #0079C1 48%, #003168 100%)",
        link="#0079C1",
        accent="#0079C1",
        note="SAJHA's blue on a cool ground.",
        maya=MayaTokens(
            strong="#00609A", deep="#003168", tint="#E6F2FA", indigo="#003168",
            on_accent="#FFFFFF", ok="#1E6B3A", warn="#7A5200", bad="#B42318",
            highlight="#CDE8F7", heading="#003168", nav=("#002654", "#0079C1", "#003168"),
            glow="#CBE6F7",
        ),
    ),
    Theme(
        name="green",
        label="Green",
        base="light",
        surface="#FFFFFF",
        body="#F7F5EF",
        ink="#1A1A1A",
        muted="#5E6A64",
        border="#E3DECF",
        header="linear-gradient(100deg, #00261A 0%, #006039 48%, #1C3A2E 100%)",
        link="#006039",
        accent="#006039",
        note="Deep green and house gold on a cream ground.",
        maya=MayaTokens(
            strong="#004D2E", deep="#00331F", tint="#E8F3EC", indigo="#1C3A2E",
            on_accent="#FFFFFF", ok="#3A6B1E", warn="#7A5200", bad="#A4161A",
            highlight="#EBDDB2", heading="#004D2E", nav=("#00261A", "#006039", "#1C3A2E"),
            glow="#E6D7A8",
        ),
    ),
)  # fmt: skip

BY_NAME: dict[str, Theme] = {theme.name: theme for theme in THEMES}

#: The Bootstrap base each theme sits on, for the client-side switcher.
BASES: dict[str, str] = {theme.name: theme.base for theme in THEMES}
