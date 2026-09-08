"""Charts, rendered as SVG in Python.

No chart library, on purpose. Three things follow from generating the markup
here that no JavaScript charting library gives you:

* **The same picture in the console and in the PDF.** One renderer, so an
  attestation pack cannot disagree with the screen it was produced from.
* **A chart is a test subject.** ``assert "no observations" in svg`` is an
  ordinary pytest assertion. A canvas is not.
* **Nothing to load.** The chart is in the HTML the server already sent.

Every function here is deterministic: the same input produces the same bytes,
which is what makes the assertions above worth writing.

Three rules the functions enforce rather than document, because each of them
is a way a chart lies:

* **No data is not zero.** An empty series renders as "no observations", never
  as a flat line along the axis. A zero-height bar and an absent bar look
  identical and mean opposite things.
* **A truncated axis says so.** Quality rates live between 99% and 100%, where
  a zero-based axis shows nothing and a truncated one exaggerates everything.
  The truncation is allowed and it is *labelled*, on the chart, in the axis.
* **Colour is never the only signal.** Every series carries its name as text.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import html
from collections.abc import Sequence

from prama.report.palette import SCREEN, Palette

#: Chart geometry. Fixed rather than configurable: a page of charts drawn to
#: five different heights reads as five unrelated facts.
SPARK_WIDTH = 120
SPARK_HEIGHT = 28
BAR_HEIGHT = 18
BAR_GAP = 6


def _escape(text: object) -> str:
    """Every string that reaches the markup goes through here.

    Labels are dataset names, attribute names and free-text descriptions —
    written by users, imported from dbt, read out of a warehouse catalogue. An
    unescaped ``&`` breaks the document; an unescaped ``<`` is script
    injection through a chart title.
    """
    return html.escape(str(text), quote=True)


def _number(value: float) -> str:
    """Coordinates, at a fixed precision.

    Rounded so the output is byte-stable across platforms: an SVG whose
    coordinates depend on the last bits of a float cannot be asserted against,
    and the diff of two identical charts becomes unreadable.
    """
    return f"{value:.2f}".rstrip("0").rstrip(".") or "0"


@dataclasses.dataclass(frozen=True, slots=True)
class Series:
    """One named, coloured set of values."""

    label: str
    values: tuple[float, ...] = ()
    #: A dimension name, so the chart takes that dimension's hue everywhere it
    #: appears. Blank means the neutral ink colour.
    dimension: str = ""
    #: True when this series is stale or unmeasured. Renders in Unverified
    #: Grey, which nothing else may use.
    unverified: bool = False

    def colour(self, palette: Palette) -> str:
        if self.unverified:
            return palette.unverified()
        return palette.dimension(self.dimension) if self.dimension else palette.ink()


@dataclasses.dataclass(frozen=True, slots=True)
class Axis:
    """The range a chart is drawn against, and whether it was truncated."""

    minimum: float
    maximum: float

    @property
    def span(self) -> float:
        # Never zero: a flat series would divide by it, and drawing a flat
        # series along the top of the chart is as wrong as along the bottom.
        return (self.maximum - self.minimum) or 1.0

    @property
    def is_truncated(self) -> bool:
        return self.minimum > 0.0

    def position(self, value: float) -> float:
        """Where a value sits, 0 at the bottom and 1 at the top."""
        return max(0.0, min(1.0, (value - self.minimum) / self.span))

    @classmethod
    def for_values(cls, values: Sequence[float], *, zero_based: bool = False) -> Axis:
        """Choose a range, and prefer honesty to drama.

        Zero-based whenever the data reaches low enough for it to show
        anything. A quality series that never leaves 99.7%-100% is drawn
        truncated because a zero-based axis would render it as a flat line at
        the top — technically honest and completely uninformative. The
        truncation is then stated in the axis label, which is the part that
        makes it defensible.
        """
        if not values:
            return cls(0.0, 1.0)
        low, high = min(values), max(values)
        if zero_based or low <= 0.0:
            return cls(0.0, high if high > 0 else 1.0)
        # Truncate only when the variation is small relative to the level.
        # Otherwise a zero baseline shows the shape perfectly well and there is
        # no reason to distort it.
        if (high - low) >= low * 0.25:
            return cls(0.0, high)
        padding = (high - low) * 0.15 or abs(high) * 0.001 or 1.0
        return cls(low - padding, high + padding)


def _frame(
    width: int,
    height: int,
    body: str,
    *,
    title: str,
    description: str,
) -> str:
    """Wrap markup as an accessible standalone chart.

    ``role="img"`` with a ``<title>`` and a ``<desc>`` is the minimum that
    makes a chart exist for a screen reader at all. It is a minimum, not a
    solution: every template that embeds one of these also renders the numbers
    as text, because a described picture is still a picture.
    """
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{_escape(title)}" class="prama-chart">'
        f"<title>{_escape(title)}</title>"
        f"<desc>{_escape(description)}</desc>"
        f"{body}"
        "</svg>"
    )


def _nothing_observed(width: int, height: int, palette: Palette, what: str) -> str:
    """The empty state, and it is never a flat line.

    A chart with no observations drawn as a line along the bottom says "the
    value was zero". Drawn along the top it says "the value was perfect".
    Both are claims, and neither was measured.
    """
    message = f"no observations of {what}"
    return _frame(
        width,
        height,
        f'<text x="{_number(width / 2)}" y="{_number(height / 2 + 4)}" '
        f'text-anchor="middle" font-size="11" fill="{palette.unverified()}" '
        'font-style="italic">not examined</text>',
        title=message,
        description=(
            f"Nothing has been measured for {what}. This is the absence of "
            "observation, not a measurement of zero."
        ),
    )


def sparkline(
    values: Sequence[float],
    *,
    label: str = "the series",
    dimension: str = "",
    palette: Palette = SCREEN,
    width: int = SPARK_WIDTH,
    height: int = SPARK_HEIGHT,
) -> str:
    """A trend, small enough to live in a table cell."""
    numbers = [float(v) for v in values]
    if not numbers:
        return _nothing_observed(width, height, palette, label)
    if len(numbers) == 1:
        # One point is a value, not a trend. Drawing a line through it invents
        # a direction the data does not have.
        return _frame(
            width,
            height,
            f'<circle cx="{_number(width / 2)}" cy="{_number(height / 2)}" r="3" '
            f'fill="{palette.dimension(dimension) if dimension else palette.ink()}"/>',
            title=f"{label}: a single observation",
            description=(
                f"One observation of {label}, {numbers[0]:.4g}. A single point has no "
                "trend, and none is drawn."
            ),
        )

    axis = Axis.for_values(numbers)
    step = (width - 2) / (len(numbers) - 1)
    points = " ".join(
        f"{_number(1 + index * step)},{_number(height - 1 - axis.position(value) * (height - 2))}"
        for index, value in enumerate(numbers)
    )
    colour = palette.dimension(dimension) if dimension else palette.ink()
    last_x = 1 + (len(numbers) - 1) * step
    last_y = height - 1 - axis.position(numbers[-1]) * (height - 2)
    body = (
        f'<polyline points="{points}" fill="none" stroke="{colour}" '
        'stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>'
        f'<circle cx="{_number(last_x)}" cy="{_number(last_y)}" r="2" fill="{colour}"/>'
    )
    direction = (
        "rising" if numbers[-1] > numbers[0] else "falling" if numbers[-1] < numbers[0] else "flat"
    )
    truncation = (
        f" The vertical axis runs from {axis.minimum:.4g} to {axis.maximum:.4g}, not from zero."
        if axis.is_truncated
        else ""
    )
    return _frame(
        width,
        height,
        body,
        title=f"{label}: {direction}, now {numbers[-1]:.4g}",
        description=(
            f"{len(numbers)} observations of {label}, from {numbers[0]:.4g} to "
            f"{numbers[-1]:.4g}, {direction}.{truncation}"
        ),
    )


def bars(
    series: Sequence[Series],
    *,
    label: str = "the breakdown",
    palette: Palette = SCREEN,
    width: int = 320,
    maximum: float | None = None,
) -> str:
    """A horizontal bar per series, each carrying its own name.

    Horizontal because the labels are words — dimension names, dataset names —
    and rotated axis text is unreadable at every size that fits on a card.
    """
    rows = list(series)
    if not rows:
        return _nothing_observed(width, BAR_HEIGHT * 2, palette, label)

    values = [s.values[-1] if s.values else 0.0 for s in rows]
    top = maximum if maximum is not None else (max(values) or 1.0)
    label_width = 96
    track = width - label_width - 44
    height = len(rows) * (BAR_HEIGHT + BAR_GAP) + BAR_GAP

    parts = []
    for index, (row, value) in enumerate(zip(rows, values, strict=True)):
        y = BAR_GAP + index * (BAR_HEIGHT + BAR_GAP)
        length = max(0.0, min(1.0, value / top)) * track
        parts.append(
            f'<text x="0" y="{_number(y + BAR_HEIGHT - 5)}" font-size="11" '
            f'fill="{palette.muted()}">{_escape(row.label)}</text>'
        )
        parts.append(
            f'<rect x="{label_width}" y="{_number(y)}" width="{_number(track)}" '
            f'height="{BAR_HEIGHT}" rx="3" fill="{palette.grid()}" opacity="0.5"/>'
        )
        if row.values:
            parts.append(
                f'<rect x="{label_width}" y="{_number(y)}" width="{_number(length)}" '
                f'height="{BAR_HEIGHT}" rx="3" fill="{row.colour(palette)}"/>'
            )
            parts.append(
                f'<text x="{label_width + track + 6}" y="{_number(y + BAR_HEIGHT - 5)}" '
                f'font-size="11" fill="{palette.ink()}">{value:.4g}</text>'
            )
        else:
            # An unmeasured series is not a zero-length bar, which is what a
            # bar chart naturally renders it as and which reads as "measured,
            # and it was nothing".
            parts.append(
                f'<text x="{label_width + 6}" y="{_number(y + BAR_HEIGHT - 5)}" '
                f'font-size="11" font-style="italic" fill="{palette.unverified()}">'
                "not examined</text>"
            )

    described = ", ".join(
        f"{s.label} {v:.4g}" if s.values else f"{s.label} not examined"
        for s, v in zip(rows, values, strict=True)
    )
    return _frame(
        width,
        height,
        "".join(parts),
        title=label,
        description=f"{label}: {described}.",
    )


def score_ring(
    value: float | None,
    *,
    label: str = "score",
    dimension: str = "",
    palette: Palette = SCREEN,
    size: int = 96,
) -> str:
    """A single rate, as a ring, with the number in the middle.

    ``None`` is not zero and never renders as an empty ring: an unmeasured
    score drawn as 0% is a false alarm, and drawn as 100% is a false
    assurance. It renders as "not examined".
    """
    radius = size / 2 - 8
    centre = size / 2
    if value is None:
        return _frame(
            size,
            size,
            f'<circle cx="{_number(centre)}" cy="{_number(centre)}" r="{_number(radius)}" '
            f'fill="none" stroke="{palette.unverified()}" stroke-width="6" '
            'stroke-dasharray="3 5"/>'
            f'<text x="{_number(centre)}" y="{_number(centre + 4)}" text-anchor="middle" '
            f'font-size="11" fill="{palette.unverified()}">—</text>',
            title=f"{label}: not examined",
            description=(
                f"No measurement of {label}. The dashed ring means nothing has been "
                "observed, which is not the same as a score of zero."
            ),
        )

    fraction = max(0.0, min(1.0, float(value)))
    circumference = 2 * 3.141592653589793 * radius
    filled = circumference * fraction
    colour = palette.dimension(dimension) if dimension else palette.ink()
    body = (
        f'<circle cx="{_number(centre)}" cy="{_number(centre)}" r="{_number(radius)}" '
        f'fill="none" stroke="{palette.grid()}" stroke-width="6"/>'
        f'<circle cx="{_number(centre)}" cy="{_number(centre)}" r="{_number(radius)}" '
        f'fill="none" stroke="{colour}" stroke-width="6" stroke-linecap="round" '
        f'stroke-dasharray="{_number(filled)} {_number(circumference)}" '
        f'transform="rotate(-90 {_number(centre)} {_number(centre)})"/>'
        f'<text x="{_number(centre)}" y="{_number(centre + 5)}" text-anchor="middle" '
        f'font-size="16" font-weight="600" fill="{palette.ink()}">'
        f"{fraction * 100:.1f}%</text>"
    )
    return _frame(
        size,
        size,
        body,
        title=f"{label}: {fraction * 100:.1f}%",
        description=f"{label} is {fraction * 100:.2f} per cent.",
    )


def distribution(
    buckets: Sequence[tuple[str, int]],
    *,
    label: str = "the distribution",
    palette: Palette = SCREEN,
    dimension: str = "",
    width: int = 320,
    height: int = 120,
) -> str:
    """A histogram, for a profile or a break-classification breakdown."""
    if not buckets or all(count == 0 for _, count in buckets):
        return _nothing_observed(width, height, palette, label)

    top = max(count for _, count in buckets) or 1
    slot = width / len(buckets)
    bar_width = max(2.0, slot - 4)
    colour = palette.dimension(dimension) if dimension else palette.ink()
    floor = height - 16

    parts = []
    for index, (name, count) in enumerate(buckets):
        bar_height = (count / top) * (floor - 4)
        x = index * slot + 2
        parts.append(
            f'<rect x="{_number(x)}" y="{_number(floor - bar_height)}" '
            f'width="{_number(bar_width)}" height="{_number(bar_height)}" rx="2" '
            f'fill="{colour}"/>'
        )
        # Every bar carries its bucket name. A histogram whose axis labels were
        # dropped to fit is a picture of some numbers.
        parts.append(
            f'<text x="{_number(x + bar_width / 2)}" y="{height - 3}" text-anchor="middle" '
            f'font-size="9" fill="{palette.muted()}">{_escape(name)}</text>'
        )
    described = ", ".join(f"{name}: {count}" for name, count in buckets)
    return _frame(
        width,
        height,
        "".join(parts),
        title=label,
        description=f"{label}. {described}.",
    )


def table_alternative(rows: Sequence[tuple[str, str]], *, caption: str) -> str:
    """The same facts as an HTML table.

    Not a fallback for a broken chart — a peer of it. Every chart in the
    console is accompanied by one of these, because a described picture is
    still a picture, and finding one named row among forty is something a
    table does better than a graphic for everybody.
    """
    body = "".join(
        f'<tr><th scope="row">{_escape(name)}</th><td>{_escape(value)}</td></tr>'
        for name, value in rows
    )
    return (
        f'<table class="table table-sm chart-data"><caption>{_escape(caption)}</caption>'
        f"<tbody>{body}</tbody></table>"
    )
