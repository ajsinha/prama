"""
The diagrams for the Medium article, drawn from code and audited as rendered.

    python tools/medium/diagrams.py            # SVG and PNG into docs/publications/medium/img/
    python tools/medium/diagrams.py --check    # audit only; non-zero on any issue

Medium takes raster images, so each diagram is written as SVG (the source, reviewable in
a diff) and exported to PNG by Inkscape. The audit then asks Inkscape for the laid-out
bounding box of every element, which is the rendered geometry rather than an estimate,
and reports text printed over text, text escaping the box it belongs to, and anything
leaving the canvas. That is the lesson of the deck's rendered audit, applied here too.

Colours are the brand's (docs/reference/brand.md): Prama Indigo, Refract Blue, and the prism's six
dimension colours, which are only ever used to mean their dimension or a verdict.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "diagrams"))

from canvas import (
    AMBER,
    FROST,
    GREEN,
    GREY,
    INDIGO,
    INK,
    MIST,
    ORANGE,
    RED,
    REFRACT,
    RULE,
    SLATE,
    SPECTRUM,
    TEAL,
    WHITE,
    Canvas,
    build,
)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "publications" / "medium" / "img"


# --------------------------------------------------------------------------- diagrams


def justified() -> Canvas:
    c = Canvas("01-justified-belief", 560)
    y = c.title(
        "Green is a belief. Prama asks what justifies it.",
        "A data quality claim is justified only when all three hold. Most estates have one.",
    )
    c.card(
        60,
        y + 10,
        330,
        250,
        "“Trades are fine”",
        "A dashboard is green. Somebody believes the data. Nothing yet says why they should.",
        key="belief",
        accent=GREY,
    )
    xs = [470, 770, 1070]
    heads = [
        ("Declared meaning", "The control derives from what the owner said the data means."),
        ("A deterministic verdict", "A versioned engine decides. No model, no mood."),
        ("Verifiable evidence", "The record checks out without trusting its author."),
    ]
    for i, (x, (head, body)) in enumerate(zip(xs, heads, strict=True)):
        c.card(x, y + 10, 270, 250, head, body, key=f"p{i}", accent=SPECTRUM[i * 2])
    c.arrow(392, y + 135, 466, y + 135)
    c.rect(470, y + 300, 870, 70, fill=INDIGO, stroke=INDIGO, radius=14, box="pram")
    c.text(
        905,
        y + 345,
        "pramā: knowledge that is true and arrived at by a reliable means",
        24,
        WHITE,
        600,
        "middle",
        box="pram",
    )
    for x in xs:
        c.arrow(x + 135, y + 262, x + 135, y + 296)
    return c


def loop() -> Canvas:
    c = Canvas("02-control-loop", 640)
    y = c.title(
        "The control loop: derive, never restate",
        "The meaning lives in one place. Controls follow from it, and change when it changes.",
    )
    top = [
        ("Declare", "Grain, domains, relationships, metadata, business context"),
        ("Derive", "Deterministic generators turn each fact into PQL"),
        ("Propose", "Queued with provenance; rejections remembered"),
        ("Approve", "A named person activates it, by tier"),
    ]
    w, gap, x0 = 290, 46, 60
    for i, (head, body) in enumerate(top):
        c.card(x0 + i * (w + gap), y + 10, w, 200, head, body, key=f"top{i}")
        if i:
            c.arrow(x0 + i * (w + gap) - gap + 4, y + 110, x0 + i * (w + gap) - 6, y + 110)
    bottom = [
        ("Score and trust", "Derived from evidence; propagated along lineage"),
        ("Evidence", "Hash-chained, Merkle-rooted, verifiable offline"),
        ("Run", "Compiled, fused, pushed to the data, judged"),
    ]
    by = y + 290
    for i, (head, body) in enumerate(bottom):
        x = x0 + (i + 1) * (w + gap)
        c.card(x, by, w, 200, head, body, key=f"bot{i}", accent=SPECTRUM[i])
        if i:
            c.arrow(x - 6, by + 100, x - gap + 4, by + 100)
    last = x0 + 3 * (w + gap) + w / 2
    c.arrow(last, y + 214, last, by - 6)
    c.rect(x0, by, w, 200, fill=FROST, stroke=RULE, box="note")
    c.block(
        x0 + 22,
        by + 20,
        w - 44,
        "Change the declaration and the loop runs again. "
        "There is no second copy of the meaning to rot.",
        21,
        SLATE,
        box="note",
    )
    return c


def compile_() -> Canvas:
    c = Canvas("03-one-plan-many-engines", 620)
    y = c.title(
        "One plan, several engines, one verdict",
        "PQL compiles to a versioned plan. The plan runs where the data lives, and the "
        "conformance suite requires the same verdict on every engine.",
    )
    c.rect(60, y + 20, 520, 210, fill=FROST, box="pql")
    c.text(84, y + 60, "PQL", 22, REFRACT, 700, box="pql")
    for i, line in enumerate(
        [
            "CHECK trades.notional >= 0",
            "  SEVERITY critical",
            "  DIMENSION validity",
            "  BECAUSE 'a notional is a size;",
            "    the side carries direction'",
        ]
    ):
        c.text(84, y + 100 + i * 26, line, 20, INK, 400, mono=True, box="pql")
    c.card(
        640, y + 25, 240, 200, "Plan (IR)", "resolved, versioned, hashed into evidence", key="ir"
    )
    c.arrow(582, y + 125, 636, y + 125)
    engines = [("SQLite", TEAL), ("DuckDB", GREEN), ("PostgreSQL", AMBER)]
    for i, (name, colour) in enumerate(engines):
        ey = y + 10 + i * 78
        c.card(960, ey, 380, 64, name, key=f"e{i}", accent=colour, title_size=24)
        c.arrow(882, y + 125, 956, ey + 32)
    c.rect(60, y + 270, 1280, 110, fill=MIST, stroke=MIST, box="fuse")
    c.block(
        84,
        y + 288,
        1232,
        "Fusion: controls over the same table share one scan. In the "
        "fusion test, 400 controls run as 160 scans. What does not push down to an engine "
        "is published, not hidden: prama control functions.",
        22,
        INK,
        box="fuse",
    )
    return c


def verdicts() -> Canvas:
    c = Canvas("04-five-verdicts", 470)
    y = c.title(
        "Five verdicts, because two would lie",
        "Only one of them is green. Nothing else is ever rounded up to it.",
    )
    rows = [
        ("pass", GREEN, "The exact test ran and found nothing"),
        ("fail", RED, "Violations above the threshold, with counts and a sample"),
        ("indeterminate", AMBER, "A screen ran, or too little data: not a pass"),
        ("error", ORANGE, "The control could not run, and says so"),
        ("skipped", GREY, "Not run in this pass; recorded"),
    ]
    w, gap = 244, 15
    for i, (name, colour, meaning) in enumerate(rows):
        x = 60 + i * (w + gap)
        c.chip(x, y + 20, w, 56, name, colour, size=23, key=f"v{i}")
        c.rect(x, y + 96, w, 170, fill=FROST, stroke=RULE, box=f"m{i}")
        c.block(x + 18, y + 110, w - 36, meaning, 21, SLATE, box=f"m{i}")
    return c


def chain() -> Canvas:
    c = Canvas("05-evidence-chain", 640)
    y = c.title(
        "Evidence that verifies without its author",
        "Each record commits to the one before it. A run's records roll up to one root. An "
        "auditor re-derives both with a script that never imports Prama.",
    )
    w, gap = 280, 50
    for i in range(4):
        x = 60 + i * (w + gap)
        key = f"rec{i}"
        c.rect(x, y + 20, w, 190, fill=WHITE, box=key)
        c.text(x + 22, y + 58, f"record {i + 1}", 24, INK, 700, box=key)
        c.text(x + 22, y + 94, "control · version · plan", 19, SLATE, box=key)
        c.text(x + 22, y + 122, "metrics · verdict · digest", 19, SLATE, box=key)
        c.text(x + 22, y + 160, f"prev = h{i}", 20, REFRACT, 600, mono=True, box=key)
        c.text(x + 22, y + 188, f"hash = h{i + 1}", 20, INDIGO, 600, mono=True, box=key)
        if i:
            c.arrow(x - gap + 4, y + 115, x - 6, y + 115)
    c.rect(60, y + 260, 1270, 70, fill=INDIGO, stroke=INDIGO, box="root")
    c.text(
        695,
        y + 305,
        "Merkle root of the run: one digest for every record in it",
        24,
        WHITE,
        600,
        "middle",
        box="root",
    )
    for i in range(4):
        c.arrow(60 + i * (w + gap) + w / 2, y + 212, 60 + i * (w + gap) + w / 2, y + 256)
    c.rect(60, y + 360, 1270, 64, fill=FROST, box="cmd")
    c.text(
        84,
        y + 400,
        "$ python3 scripts/verify_evidence.py bundle/",
        22,
        INK,
        600,
        mono=True,
        box="cmd",
    )
    return c


def recon() -> Canvas:
    c = Canvas("06-month-end-close", 700)
    y = c.title(
        "Month-end close in one RECONCILE",
        "Case study 6: a subledger in three currencies against a EUR general ledger, with "
        "entries that reach the ledger the next morning.",
    )
    c.card(
        60, y + 20, 300, 200, "Subledger", "every entry, in EUR, USD or GBP", key="sl", accent=TEAL
    )
    c.card(
        60,
        y + 260,
        300,
        200,
        "General ledger",
        "one EUR balance per account, cost centre and day",
        key="gl",
        accent=AMBER,
    )
    c.card(
        440,
        y + 20,
        360,
        440,
        "RECONCILE",
        "ON account, cost centre, day. COMPARING "
        "amount = balance_eur WITHIN 0.01 EUR. NORMALISING currency TO EUR USING RATES "
        "fx_rates. OFFSET BY 1 DAY.",
        key="rc",
        accent=REFRACT,
    )
    c.arrow(362, y + 120, 436, y + 150)
    c.arrow(362, y + 360, 436, y + 330)
    outcomes = [
        ("3 genuine", RED, "manual journals on the ledger only"),
        ("1 missing", ORANGE, "a day that never reached the ledger"),
        ("1 extra", AMBER, "an account the subledger never booked"),
        ("2 matched", GREEN, "late entries, matched across the offset"),
    ]
    for i, (head, colour, body) in enumerate(outcomes):
        oy = y + 20 + i * 112
        c.chip(880, oy + 14, 190, 50, head, colour, size=22, key=f"o{i}")
        c.block(1090, oy + 8, 250, body, 20, SLATE, box=f"ob{i}")
        c.parts.append(
            f'<rect id="box-ob{i}" x="1086" y="{oy + 2}" width="260" height="100" '
            'fill="none" stroke="none"/>'
        )
        c.arrow(802, y + 240, 876, oy + 39)
    c.rect(60, y + 500, 1280, 64, fill=MIST, stroke=MIST, box="cf")
    c.text(
        84,
        y + 540,
        "Without OFFSET BY 1 DAY the same books report 9 breaks, not 5.",
        22,
        INK,
        600,
        box="cf",
    )
    return c


def blast() -> Canvas:
    c = Canvas("07-blast-radius", 900)
    y = c.title(
        "From code to impact, across a join",
        "Case study 8: lineage parsed from two SQL scripts and a Power BI model. How much of "
        "each raw-feed defect reaches each column downstream.",
    )

    def lane(top: float, heading: str, nodes: list, key: str) -> float:
        c.text(60, top + 26, heading, 24, INDIGO, 700)
        for i, (name, share, how) in enumerate(nodes):
            ny = top + 46 + i * 76
            box = f"{key}{i}"
            c.rect(60, ny, 520, 58, fill=FROST if name.endswith("rows)") else WHITE, box=box)
            c.text(80, ny + 37, name, 21, INK, 600, mono=True, box=box)
            c.rect(
                620,
                ny + 11,
                540 * share,
                36,
                fill=RED if i == 0 else REFRACT,
                stroke="none",
                radius=6,
            )
            # A long bar carries its label inside, so the label never runs off the canvas.
            inside = share >= 0.6
            c.text(
                620 + 540 * share - 16 if inside else 640 + 540 * share,
                ny + 36,
                f"{share:.0%} · {how}",
                20,
                WHITE if inside else SLATE,
                600 if inside else 400,
                "end" if inside else "start",
            )
            if i:
                c.arrow(320, ny - 16, 320, ny - 4)
        return top + 46 + len(nodes) * 76

    below = lane(
        y,
        "A wrong value travels as a value",
        [
            ("raw.trades.notional_amt", 1.0, "the defect"),
            ("mart.positions.exposure_usd", 0.35, "summed with FX"),
            ("Dashboard: Total Exposure", 0.12, "aggregated twice"),
        ],
        "v",
    )
    below = lane(
        below + 12,
        "A lost row travels through the join",
        [
            ("stg.trades.ccy", 1.0, "'usd' has no rate"),
            ("mart.positions.* (rows)", 0.8, "inner join on ccy"),
            ("Dashboard: Total Exposure", 0.28, "computed over those rows"),
        ],
        "p",
    )
    c.rect(60, below + 20, 1280, 104, fill=MIST, stroke=MIST, box="join")
    c.block(
        84,
        below + 34,
        1232,
        "The join proposes: CHECK stg.trades.ccy REFERENCES "
        "ref.fx_rates.ccy. It fails on 3 of 1,882 staged trades, where 605,000,000 of "
        "notional would otherwise leave the mart with no error and no null.",
        21,
        INK,
        box="join",
    )
    return c


def boundary() -> Canvas:
    c = Canvas("08-ai-boundary", 600)
    y = c.title(
        "Models author. The engine decides.",
        "The line is enforced by an architecture test that fails the build if model output "
        "can reach a verdict.",
    )
    c.rect(60, y + 20, 590, 380, fill=FROST, box="may")
    c.text(90, y + 66, "A model may", 28, REFRACT, 700, box="may")
    for i, item in enumerate(
        [
            "author a proposed control",
            "suggest lineage, marked inferred",
            "rank datasets for a purpose",
            "explain a failure in plain words",
            "summarise an incident",
        ]
    ):
        c.text(90, y + 120 + i * 50, f"✓  {item}", 23, INK, 400, box="may")
    c.rect(750, y + 20, 590, 380, fill=WHITE, stroke=INDIGO, sw=3, box="engine")
    c.text(780, y + 66, "Only the engine and a person", 28, INDIGO, 700, box="engine")
    for i, item in enumerate(
        [
            "pass or fail data",
            "activate a control (a person)",
            "turn inferred lineage into parsed",
            "change a score",
            "write evidence",
        ]
    ):
        c.text(780, y + 120 + i * 50, f"■  {item}", 23, INK, 400, box="engine")
    c.parts.append(f'<rect x="690" y="{y + 10}" width="20" height="400" fill="{INDIGO}"/>')
    c.text(700, y + 440, "tests/architecture/test_layering.py", 20, SLATE, 600, "middle", mono=True)
    return c


DIAGRAMS = [justified, loop, compile_, verdicts, chain, recon, blast, boundary]


if __name__ == "__main__":
    sys.exit(build(DIAGRAMS, OUT, sys.argv, png=True))
