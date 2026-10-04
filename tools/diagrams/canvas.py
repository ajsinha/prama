"""
The drawing kit every diagram in this repository is made with, and its audit.

    from canvas import Canvas, build        # tools/diagrams on sys.path

A diagram is a function returning a ``Canvas``: boxes, cards, chips, arrows and
wrapped text placed on a fixed-width page, written out as SVG (the source,
reviewable in a diff). The audit then asks Inkscape for the laid-out bounding
box of every element, which is the rendered geometry rather than an estimate,
and reports text printed over text, text escaping the box it belongs to, and
anything leaving the canvas. That is the lesson of the deck's rendered audit:
a diagram that builds and looks plausible in the source can still be wrong on
the page.

Colours are the brand's (docs/reference/brand.md): Prama Indigo, Refract Blue,
and the prism's six dimension colours, which are only ever used to mean their
dimension or a verdict.

Used by tools/medium/diagrams.py (the article) and tools/docs/diagrams.py (the
architecture and developer guides).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""

from __future__ import annotations

import html
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

INDIGO, REFRACT, INK, SLATE = "#0E1A46", "#2B3FA8", "#14182E", "#5A6480"
GREY, RULE, FROST, MIST, WHITE = "#8A93AD", "#D6DAE6", "#F3F5FA", "#E4E8F8", "#FFFFFF"
TEAL, GREEN, LIME, AMBER, ORANGE, RED = (
    "#00B3A4",
    "#2FB673",
    "#8CBF3F",
    "#E8B33A",
    "#E8823A",
    "#D9534F",
)
SPECTRUM = (TEAL, GREEN, LIME, AMBER, ORANGE, RED)
SANS = "Inter, 'DejaVu Sans', sans-serif"
MONO = "'DejaVu Sans Mono', monospace"
WIDTH = 1400


def wrap(text: str, width: float, size: float, bold: bool = False, mono: bool = False) -> list:
    """Greedy word wrap on a pessimistic character width. The audit is the real check."""
    per = size * (0.62 if mono else (0.6 if bold else 0.56))
    limit = max(4, int(width / per))
    lines: list[str] = []
    line = ""
    for word in text.split():
        candidate = f"{line} {word}".strip()
        if len(candidate) > limit and line:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines


@dataclass
class Canvas:
    name: str
    height: int
    parts: list[str] = field(default_factory=list)
    serial: int = 0
    #: The lowest point drawn so far. The canvas is sized from it, so a diagram
    #: that grows cannot run off its own bottom edge.
    bottom: float = 0.0

    @property
    def size(self) -> int:
        return int(max(self.height, self.bottom + 48))

    def _id(self, kind: str) -> str:
        self.serial += 1
        return f"{kind}{self.serial}"

    def rect(self, x, y, w, h, fill=WHITE, stroke=RULE, radius=14, sw=2, box="") -> str:
        ident = f"box-{box}" if box else self._id("r")
        self.bottom = max(self.bottom, y + h)
        self.parts.append(
            f'<rect id="{ident}" x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'
        )
        return ident

    def text(
        self,
        x,
        y,
        content: str,
        size=24,
        color=INK,
        weight=400,
        anchor="start",
        mono=False,
        italic=False,
        box="",
    ) -> None:
        ident = f"t-{box}-{self._id('')}" if box else self._id("t")
        self.bottom = max(self.bottom, y + size * 0.35)
        family = MONO if mono else SANS
        style = ' font-style="italic"' if italic else ""
        self.parts.append(
            f'<text id="{ident}" x="{x}" y="{y}" font-family="{family}" font-size="{size}" '
            f'font-weight="{weight}" fill="{color}" text-anchor="{anchor}"{style} '
            'xml:space="preserve">'
            f"{html.escape(content)}</text>"
        )

    def block(
        self,
        x,
        y,
        w,
        lines_of: str,
        size=22,
        color=SLATE,
        weight=400,
        mono=False,
        anchor="start",
        box="",
        line=1.35,
    ) -> float:
        """Wrapped text from the top-left; returns the y below the last line."""
        tx = x + w / 2 if anchor == "middle" else x
        for i, part in enumerate(wrap(lines_of, w, size, weight >= 600, mono)):
            self.text(
                tx, y + size + i * size * line, part, size, color, weight, anchor, mono, box=box
            )
            y_end = y + size + i * size * line
        return y_end + size * 0.4

    def card(
        self,
        x,
        y,
        w,
        h,
        title,
        body="",
        key="",
        accent=REFRACT,
        fill=WHITE,
        title_size=26,
        body_size=21,
        centre=False,
    ) -> None:
        key = key or self._id("c")
        self.rect(x, y, w, h, fill=fill, box=key)
        self.parts.append(
            f'<rect x="{x + 2}" y="{y + 2}" width="{w - 4}" height="8" rx="3" fill="{accent}"/>'
        )
        pad = 24
        anchor = "middle" if centre else "start"
        below = self.block(
            x + pad, y + 26, w - 2 * pad, title, title_size, INK, 700, anchor=anchor, box=key
        )
        if body:
            self.block(
                x + pad, below + 2, w - 2 * pad, body, body_size, SLATE, anchor=anchor, box=key
            )

    def chip(self, x, y, w, h, label, fill, color=WHITE, size=24, key="") -> None:
        key = key or self._id("k")
        self.rect(x, y, w, h, fill=fill, stroke=fill, radius=h // 2, box=key)
        self.text(x + w / 2, y + h / 2 + size * 0.36, label, size, color, 700, "middle", box=key)

    def arrow(self, x1, y1, x2, y2, color=SLATE, width=3, dashed=False) -> None:
        dash = ' stroke-dasharray="10 8"' if dashed else ""
        self.parts.append(
            f'<line id="{self._id("a")}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="{color}" stroke-width="{width}" marker-end="url(#head)"{dash}/>'
        )

    def title(self, heading: str, sub: str = "") -> float:
        self.parts.append(f'<rect x="0" y="0" width="{WIDTH}" height="10" fill="{INDIGO}"/>')
        for i, colour in enumerate(SPECTRUM):
            self.parts.append(
                f'<rect x="{i * WIDTH / 6}" y="10" width="{WIDTH / 6}" height="6" fill="{colour}"/>'
            )
        self.text(60, 78, heading, 38, INK, 700)
        if sub:
            return self.block(60, 94, WIDTH - 120, sub, 23, SLATE) + 16
        return 110

    def svg(self) -> str:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{self.size}" '
            f'viewBox="0 0 {WIDTH} {self.size}">'
            "<defs>"
            '<marker id="head" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
            f'markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" '
            f'fill="{SLATE}"/></marker></defs>'
            f'<rect width="{WIDTH}" height="{self.size}" fill="{WHITE}"/>'
            + "".join(self.parts)
            + "</svg>"
        )


# --------------------------------------------------------------------------- audit


def _boxes(svg: Path) -> dict[str, tuple[float, float, float, float]]:
    out = subprocess.run(
        ["inkscape", "--query-all", str(svg)], capture_output=True, text=True, check=True
    ).stdout
    boxes = {}
    for row in out.splitlines():
        parts = row.split(",")
        if len(parts) == 5:
            boxes[parts[0]] = tuple(float(v) for v in parts[1:])
    return boxes


def audit(svg: Path, height: int) -> list[str]:
    boxes = _boxes(svg)
    issues = []
    texts = {k: v for k, v in boxes.items() if k.startswith("t")}
    for key, (x, y, w, h) in boxes.items():
        if key.startswith(("t", "box-")) and (x < 0 or y < 0 or x + w > WIDTH or y + h > height):
            issues.append(f"{svg.name}: {key} leaves the canvas")
    for key, (x, y, w, h) in texts.items():
        if key.startswith("t-"):
            owner = "box-" + key.split("-")[1]
            bx, by, bw, bh = boxes[owner]
            if x < bx + 4 or y < by + 4 or x + w > bx + bw - 4 or y + h > by + bh - 4:
                issues.append(f"{svg.name}: text {key} escapes {owner}")
    keys = list(texts)
    for i, a in enumerate(keys):
        ax, ay, aw, ah = texts[a]
        for b in keys[i + 1 :]:
            bx, by, bw, bh = texts[b]
            if min(ax + aw, bx + bw) - max(ax, bx) > 1 and min(ay + ah, by + bh) - max(
                ay, by
            ) > 0.3 * min(ah, bh):
                issues.append(f"{svg.name}: texts {a} and {b} overlap")
    return issues


def build(
    diagrams: Sequence[Callable[[], Canvas]], out: Path, argv: Sequence[str], png: bool = False
) -> int:
    """Write each diagram as SVG into ``out`` (and PNG if asked), then audit them all.

    With ``--check`` in ``argv`` nothing is written: the SVGs on disk are
    audited, and compared with what the code would draw now, so a diagram
    edited in code but not rebuilt is reported as stale.
    """
    if shutil.which("inkscape") is None:
        print("Inkscape is not installed: the diagrams cannot be exported or audited")
        return 2
    out.mkdir(parents=True, exist_ok=True)
    issues: list[str] = []
    for make in diagrams:
        canvas = make()
        svg = out / f"{canvas.name}.svg"
        if "--check" in argv:
            if not svg.is_file() or svg.read_text(encoding="utf-8") != canvas.svg():
                issues.append(f"{svg.name}: stale; rebuild without --check")
                continue
        else:
            svg.write_text(canvas.svg(), encoding="utf-8")
            if png:
                subprocess.run(
                    [
                        "inkscape",
                        str(svg),
                        "--export-type=png",
                        f"--export-filename={out / (canvas.name + '.png')}",
                        f"--export-width={WIDTH}",
                    ],
                    check=True,
                    capture_output=True,
                )
        issues += audit(svg, canvas.size)
        print(canvas.name)
    for issue in issues:
        print(issue)
    print("no diagram issues detected" if not issues else f"{len(issues)} diagram issue(s)")
    return 1 if issues else 0
