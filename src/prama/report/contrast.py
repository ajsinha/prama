"""WCAG contrast, computed rather than eyeballed.

Contrast is arithmetic — the WCAG 2.2 relative-luminance formula and a ratio —
so it belongs in a test, not in a design review. A palette checked by looking
at it passes on the reviewer's monitor and fails on a projector, a cheap laptop
panel, and for the eight per cent of men with a colour vision deficiency.

The thresholds are the standard's, and they are not the same for everything:
body text needs 4.5:1, large text 3:1, and a non-text element that carries
meaning — the fill of a bar, the stroke of a ring, a status dot — also needs
3:1 against what is behind it (WCAG 1.4.11). That last one is the rule most
often missed, and it is exactly the rule a data quality product cannot afford
to miss, because its charts *are* the meaning.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

#: WCAG 2.2 AA.
BODY_TEXT = 4.5
LARGE_TEXT = 3.0
NON_TEXT = 3.0


def _channel(value: int) -> float:
    """One sRGB channel, linearised. The formula is from WCAG 2.x §relative luminance."""
    fraction = value / 255
    return fraction / 12.92 if fraction <= 0.04045 else ((fraction + 0.055) / 1.055) ** 2.4


def rgb(colour: str) -> tuple[int, int, int]:
    """Parse ``#rgb`` or ``#rrggbb``.

    Deliberately strict: a colour this cannot parse is a colour the check would
    otherwise skip, and a skipped check reports a pass.
    """
    text = colour.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(character * 2 for character in text)
    if len(text) != 6:
        raise ValueError(f"not a hex colour: {colour!r}")
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def luminance(colour: str) -> float:
    red, green, blue = rgb(colour)
    return 0.2126 * _channel(red) + 0.7152 * _channel(green) + 0.0722 * _channel(blue)


def ratio(foreground: str, background: str) -> float:
    """The contrast ratio, between 1 and 21. Order does not matter."""
    first, second = luminance(foreground), luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def passes(foreground: str, background: str, *, threshold: float = BODY_TEXT) -> bool:
    return ratio(foreground, background) >= threshold


def report(foreground: str, background: str, *, threshold: float = BODY_TEXT) -> str:
    """A sentence a failure message can use.

    Carries the measured ratio, not just the verdict: "3.1:1, needs 4.5:1"
    tells whoever is fixing it how far off they are, and a bare "fails" sends
    them guessing.
    """
    measured = ratio(foreground, background)
    verdict = "passes" if measured >= threshold else "FAILS"
    return f"{foreground} on {background}: {measured:.2f}:1 {verdict} (needs {threshold}:1)"


def _clamp(value: float) -> int:
    return max(0, min(255, round(value)))


def _hex(red: float, green: float, blue: float) -> str:
    return f"#{_clamp(red):02X}{_clamp(green):02X}{_clamp(blue):02X}"


def accessible_on(
    colour: str, background: str, *, threshold: float = BODY_TEXT, steps: int = 100
) -> str:
    """The nearest shade of *colour* that meets *threshold* on *background*.

    Hue is preserved; only lightness moves, and it moves away from the
    background — darker on a light ground, lighter on a dark one. So a derived
    variant is recognisably the same colour, which is what keeps the dimension
    language intact: teal still means accuracy after this function has run.

    This exists because the brand spectrum (docs/brand.md §4) is a *fill*
    palette. Accuracy Teal on white is 2.63:1 — fine behind a bar, illegible as
    a word. Rather than change the brand or ship unreadable text, the readable
    variant is *derived* from the brand hue, in one place, so the two cannot
    drift and no designer has to hand-pick eight more hex codes.

    Returns the original when it already passes. Returns black or white when
    the threshold is unreachable in this hue, which is a real outcome for a
    yellow on white and is better than silently returning something that fails.
    """
    if ratio(colour, background) >= threshold:
        return colour

    red, green, blue = rgb(colour)
    darken = luminance(background) > luminance(colour)
    target = (0.0, 0.0, 0.0) if darken else (255.0, 255.0, 255.0)

    best = _hex(*target)
    for step in range(1, steps + 1):
        fraction = step / steps
        candidate = _hex(
            red + (target[0] - red) * fraction,
            green + (target[1] - green) * fraction,
            blue + (target[2] - blue) * fraction,
        )
        if ratio(candidate, background) >= threshold:
            # The first shade that clears the bar, so the result stays as close
            # to the brand colour as the standard allows.
            best = candidate
            break
    return best
