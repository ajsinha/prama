"""Diagrams for docs/developer. Each function returns a Canvas; DIAGRAMS lists them.

Built and audited by ``tools/docs/diagrams.py``. Every name starts with ``dev-``,
and every guide embeds its own as ``../assets/diagrams/dev-<name>.svg``.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "diagrams"))

from canvas import (
    AMBER,
    FROST,
    GREEN,
    GREY,
    INK,
    LIME,
    MIST,
    ORANGE,
    RED,
    REFRACT,
    RULE,
    TEAL,
    Canvas,
    wrap,
)

#: Cards carry a title and a body; this is the pair, plus the accent.
Item = tuple[str, str, str]

LEFT, FULL = 60, 1280


# --------------------------------------------------------------------------- helpers


def _lines(text: str, width: float, size: float, bold: bool = False) -> int:
    return len(wrap(text, width, size, bold)) if text else 0


def card_height(width: float, title: str, body: str, ts: int = 24, bs: int = 19) -> int:
    """The height a card needs for its wrapped title and body, with padding."""
    inner = width - 48
    height = 26 + ts * 1.4 + (_lines(title, inner, ts, True) - 1) * ts * 1.35 + 18
    if body:
        height += 2 + bs * 1.4 + (_lines(body, inner, bs) - 1) * bs * 1.35
    return int(height + 6)


def row(
    c: Canvas,
    y: float,
    items: Sequence[Item],
    *,
    key: str,
    x0: float = LEFT,
    width: float = FULL,
    gap: float = 40,
    ts: int = 24,
    bs: int = 19,
    arrows: bool = True,
    height: int = 0,
) -> tuple[list[tuple[float, float]], int]:
    """Cards side by side, sized to the tallest, optionally joined left to right."""
    count = len(items)
    w = (width - gap * (count - 1)) / count
    h = height or max(card_height(w, t, b, ts, bs) for t, b, _ in items)
    spots = []
    for index, (title, body, accent) in enumerate(items):
        x = x0 + index * (w + gap)
        c.card(
            x, y, w, h, title, body, key=f"{key}{index}", accent=accent, title_size=ts, body_size=bs
        )
        if arrows and index:
            c.arrow(x - gap + 4, y + h / 2, x - 6, y + h / 2)
        spots.append((x, w))
    return spots, h


def note(
    c: Canvas,
    x: float,
    y: float,
    w: float,
    text: str,
    *,
    key: str,
    size: int = 20,
    fill: str = MIST,
    color: str = INK,
) -> float:
    """A shaded band of prose; returns the y below it."""
    h = int(_lines(text, w - 48, size) * size * 1.35 + 36)
    c.rect(x, y, w, h, fill=fill, stroke=fill, box=key)
    c.block(x + 24, y + 12, w - 48, text, size, color, box=key)
    return y + h


def label(c: Canvas, x: float, y: float, text: str, color: str = REFRACT) -> None:
    c.text(x, y, text.upper(), 17, color, 700)


def down(c: Canvas, x: float, y1: float, y2: float, dashed: bool = False) -> None:
    c.arrow(x, y1 + 4, x, y2 - 6, dashed=dashed)


# --------------------------------------------------------------------------- README


def plugin_model() -> Canvas:
    c = Canvas("dev-plugin-model", 300)
    y = c.title(
        "How an extension is found",
        "Three ways in, one rule: core code never names a concrete implementation. "
        "It asks a registry by key, and the registry checks what it is given.",
    )
    label(c, LEFT, y + 18, "Discovery")
    ways: list[Item] = [
        (
            "Entry point",
            "A distribution advertises it (prama.validators, prama.delegates); "
            "loaded at start, vetted before use.",
            TEAL,
        ),
        (
            "Table in its package",
            "One mapping in the owning package: BUILTIN connectors, DIALECTS, "
            "IMPORTERS, KINDS, _BY_ENGINE.",
            GREEN,
        ),
        (
            "Explicit install",
            "install(registry), called from the CLI entry point and create_app, "
            "never as a side effect of an import.",
            LIME,
        ),
    ]
    top = y + 34
    hs = [card_height(400, t, b) for t, b, _ in ways]
    h = max(hs)
    for i, (t, b, a) in enumerate(ways):
        c.card(
            LEFT,
            top + i * (h + 18),
            400,
            h,
            t,
            b,
            key=f"way{i}",
            accent=a,
            title_size=24,
            body_size=19,
        )
    mid = top + (3 * h + 36) / 2
    label(c, 540, y + 18, "Registration")
    reg_h = card_height(
        360,
        "Registry",
        "Checks the class subclasses the base, its manifest's kind and key, and "
        "refuses a duplicate key. An ill-formed plugin fails here, by name.",
    )
    c.card(
        540,
        mid - reg_h / 2,
        360,
        reg_h,
        "Registry",
        "Checks the class subclasses the base, its manifest's kind and key, and "
        "refuses a duplicate key. An ill-formed plugin fails here, by name.",
        key="registry",
        accent=REFRACT,
        title_size=24,
        body_size=19,
    )
    for i in range(3):
        c.arrow(464, top + i * (h + 18) + h / 2, 534, mid)
    label(c, 960, y + 18, "Proof")
    proof = (
        "Conformance",
        "Each kind has a suite: the connector contract, function agreement on real "
        "engines, the delegate kit, the lease contract.",
        AMBER,
    )
    ph = card_height(380, proof[0], proof[1])
    c.card(
        960,
        mid - ph / 2,
        380,
        ph,
        proof[0],
        proof[1],
        key="proof",
        accent=AMBER,
        title_size=24,
        body_size=19,
    )
    c.arrow(904, mid, 954, mid)
    note(
        c,
        LEFT,
        top + 3 * h + 36 + 30,
        FULL,
        "A plugin's manifest says what it is and what it can do (Capability); the "
        "compiler consults capabilities and never probes. The verification field "
        "says whether it has met the real thing or is code-complete only.",
        key="rule",
    )
    return c


def extension_map() -> Canvas:
    c = Canvas("dev-extension-map", 300)
    y = c.title(
        "Where each extension point sits",
        "The control loop from left to right, and the platform underneath it. "
        "Each name is a developer guide.",
    )
    lanes: list[Item] = [
        ("Bring in", "connectors · importers · code readers · packs", TEAL),
        ("Declare and compile", "PQL functions · validators · SQL dialects · packs", GREEN),
        ("Run", "backends · delegates · agent executors", LIME),
        ("Assure", "monitors and alerts · scorers", AMBER),
    ]
    _, h = row(c, y + 24, lanes, key="lane", ts=26, bs=21)
    under = y + 24 + h + 44
    c.rect(LEFT, under, FULL, 2, fill=RULE, stroke=RULE, radius=0, sw=0)
    label(c, LEFT, under + 40, "Beside the loop")
    side: list[Item] = [
        ("Intelligence", "LLM providers: they draft and explain, never decide", ORANGE),
        ("Platform", "API routes and console pages · schema and DAOs · SDK methods", REFRACT),
        ("Infrastructure", "secret providers · lease providers · config sources", GREY),
    ]
    row(c, under + 60, side, key="side", arrows=False, ts=24, bs=20)
    return c


# --------------------------------------------------------------------------- connectors


def connector_classes() -> Canvas:
    c = Canvas("dev-connector-classes", 300)
    y = c.title(
        "A connector, as a class and as a form",
        "What you subclass, what you write, and how the form a data architect fills "
        "in is derived from what you wrote.",
    )
    base_w = 420
    plugin_h = card_height(base_w, "Plugin (ABC)", "manifest(): PluginManifest")
    c.card(
        LEFT,
        y + 20,
        base_w,
        plugin_h,
        "Plugin (ABC)",
        "manifest(): PluginManifest",
        key="plugin",
        accent=GREY,
        title_size=24,
        body_size=19,
    )
    conn_body = (
        "health · discover · describe · snapshot · read are abstract. Optional: "
        "pushdown_capabilities, can_run_controls, run_metric_query, open, close."
    )
    conn_y = y + 20 + plugin_h + 40
    conn_h = card_height(base_w, "Connector (Plugin, ABC)", conn_body)
    c.card(
        LEFT,
        conn_y,
        base_w,
        conn_h,
        "Connector (Plugin, ABC)",
        conn_body,
        key="conn",
        accent=REFRACT,
        title_size=24,
        body_size=19,
    )
    down(c, LEFT + base_w / 2, conn_y, y + 20 + plugin_h)

    kids_y = conn_y + conn_h + 60
    kids: list[Item] = [
        ("Direct", "SqliteConnector, FilesystemConnector, ObjectStore, Rest, Mongo", TEAL),
        (
            "SqlConnector",
            "writes _fetch, _stream, _column_names; a SqlDialect does the rest",
            GREEN,
        ),
    ]
    spots, kh = row(c, kids_y, kids, key="kid", x0=LEFT, width=base_w * 2 + 40, arrows=False, bs=18)
    for x, w in spots:
        c.arrow(x + w / 2, kids_y - 4, LEFT + base_w / 2, conn_y + conn_h + 6)
    leaf_y = kids_y + kh + 50
    leaf_x, leaf_w = spots[1]
    leaf_h = card_height(
        leaf_w, "Postgres, Jdbc, Snowflake, ClickHouse", "each sets dialect = its SqlDialect"
    )
    c.card(
        leaf_x,
        leaf_y,
        leaf_w,
        leaf_h,
        "Postgres, Jdbc, Snowflake, ClickHouse",
        "each sets dialect = its SqlDialect",
        key="leaf",
        accent=LIME,
        title_size=24,
        body_size=19,
    )
    c.arrow(leaf_x + leaf_w / 2, leaf_y - 4, leaf_x + leaf_w / 2, kids_y + kh + 6)

    fx = LEFT + base_w * 2 + 40 + 60
    fw = 1340 - fx
    label(c, fx, y + 40, "The form, derived")
    steps: list[Item] = [
        (
            'self.config.get("name", default)',
            "every literal key your code reads, through the MRO",
            TEAL,
        ),
        ("FieldSpec", "name, default; required when read with no default", GREEN),
        ("FieldPresentation overlay", "label, help, input kind, secret: presentation only", AMBER),
        (
            "ConnectorConfigSchema",
            "to_form() for the console, API and prama connectors --key",
            REFRACT,
        ),
    ]
    sy = y + 60
    prev_bottom = 0.0
    for i, (t, b, a) in enumerate(steps):
        sh = card_height(fw, t, b, 22, 18)
        c.card(fx, sy, fw, sh, t, b, key=f"form{i}", accent=a, title_size=22, body_size=18)
        if i:
            down(c, fx + fw / 2, prev_bottom, sy)
        prev_bottom = sy + sh
        sy += sh + 34
    note(
        c,
        fx,
        sy - 6,
        fw,
        "audit() reports an overlay key the code never reads, and the suite fails the build on it.",
        key="audit",
        size=18,
        fill=FROST,
    )
    return c


LOCAL = (
    "can_run_controls is False: the control is evaluated locally over the Arrow "
    "batches read() yields. Correct, and the cost is shown to the author."
)
PUSH = (
    "can_run_controls is True: run_metric_query(sql) runs the compiled control "
    "at the source, and only the metrics come back."
)


def connector_lifecycle() -> Canvas:
    c = Canvas("dev-connector-lifecycle", 300)
    y = c.title(
        "A connector's life, from a form to a verdict",
        "Configure, verify, discover, pin, read. Each step is a method on your class, "
        "and each failure names who has to fix it.",
    )
    steps: list[Item] = [
        (
            "Configure",
            "registry.create(key, config): the form validates before any driver runs",
            TEAL,
        ),
        ("Verify", "health(): healthy, unreachable, unauthorised or misconfigured", GREEN),
        ("Discover", "discover() ranks objects; describe(path) gives the columns", LIME),
        ("Pin", "snapshot(path) names the exact state read; exact or not, it says so", AMBER),
        (
            "Read or sample",
            "read(path, plan=SamplePlan) yields Arrow; a HEAD sample is a preview",
            ORANGE,
        ),
    ]
    _, h = row(c, y + 30, steps, key="step", gap=30, ts=23, bs=18)
    after = y + 30 + h + 50
    half = (FULL - 40) / 2
    lh = max(
        card_height(half, "No query engine (the default)", LOCAL),
        card_height(half, "A source with an engine", PUSH),
    )
    c.card(
        LEFT,
        after,
        half,
        lh,
        "No query engine (the default)",
        LOCAL,
        key="local",
        accent=GREY,
        title_size=24,
        body_size=19,
    )
    c.card(
        LEFT + half + 40,
        after,
        half,
        lh,
        "A source with an engine",
        PUSH,
        key="push",
        accent=REFRACT,
        title_size=24,
        body_size=19,
    )
    for x in (LEFT + half / 2, LEFT + half + 40 + half / 2):
        c.arrow(LEFT + FULL - 130, y + 30 + h + 4, x, after - 6)
    note(
        c,
        LEFT,
        after + lh + 40,
        FULL,
        "Refusals, not fallbacks: a predicate the connector cannot apply, a sampling "
        "strategy it cannot draw, a path the read policy does not allow. Each raises "
        "with a remedy, so a table is never quietly recorded as one day of itself.",
        key="refuse",
    )
    return c


# --------------------------------------------------------------------------- dialects


def dialect_families() -> Canvas:
    c = Canvas("dev-dialect-families", 300)
    y = c.title(
        "Three dialect families, three different jobs",
        "Same word, different seams. Pick the one whose job your engine changes.",
    )
    fams: list[Item] = [
        (
            "Reading a source",
            "connect.sources.sql.dialect.SqlDialect (ABC). Catalogue SQL, row "
            "estimates, sampling, snapshots, read-only session setup. Oracle, SQL "
            "Server, DB2, Teradata, MySQL, Redshift, Databricks, Synapse, Trino, "
            "BigQuery, Snowflake, ClickHouse, PostgreSQL.",
            TEAL,
        ),
        (
            "Compiling a control",
            "backend.dialect.SqlDialect, a concrete portable base. Quoting, literals, "
            "regex, count_if, modulo, capabilities. DIALECTS: postgresql, duckdb, "
            "sqlite. What compile_for(plan, engine) renders for.",
            GREEN,
        ),
        (
            "Prama's own store",
            "db.dialects.Dialect (ABC). URLs, pools, on-connect setup, introspection, "
            "upsert. sqlite and postgres, chosen by database.dialect, and the only "
            "module allowed to branch on it.",
            AMBER,
        ),
    ]
    _, h = row(c, y + 24, fams, key="fam", arrows=False, ts=24, bs=19)
    note(
        c,
        LEFT,
        y + 24 + h + 36,
        FULL,
        "A fourth, smaller one lives in the model gateway: llm.providers.Dialect "
        "names the request field an OpenAI-compatible server reads a grammar from. "
        "It is covered in the LLM providers guide.",
        key="fourth",
        size=19,
        fill=FROST,
    )
    return c


def pushdown_choice() -> Canvas:
    c = Canvas("dev-pushdown-choice", 300)
    y = c.title(
        "How a control finds its engine",
        "The engine is named by whoever runs the control; the dialect then decides "
        "whether the control can be said there at all.",
    )
    sources: list[Item] = [
        ("prama control run", "--dialect", TEAL),
        ("The scheduler", "scheduler.dialect", GREEN),
        ("A server-side run", "the connection's opener", LIME),
        ("A fleet assignment", "the agent's source engine", AMBER),
    ]
    spots, h = row(c, y + 24, sources, key="src", arrows=False, ts=22, bs=19, gap=30)
    cy = y + 24 + h + 60
    comp = (
        "compile_for(plan, engine)",
        "SqlCompiler(dialect(engine)): capabilities checked, each function rendered "
        "with Function.render(engine)",
        REFRACT,
    )
    cw = 640
    cx = LEFT + (FULL - cw) / 2
    ch = card_height(cw, comp[0], comp[1])
    c.card(
        cx, cy, cw, ch, comp[0], comp[1], key="compile", accent=REFRACT, title_size=24, body_size=19
    )
    for x, w in spots:
        c.arrow(x + w / 2, y + 24 + h + 4, cx + cw / 2, cy - 6)
    oy = cy + ch + 60
    outs: list[Item] = [
        ("SQL for that engine", "a metric query, fused with others over the same table", GREEN),
        ("Unsupported", "a refusal naming the capability and a remedy; never something close", RED),
    ]
    ospots, _ = row(c, oy, outs, key="out", x0=LEFT + 60, width=FULL - 120, arrows=False, gap=80)
    for x, w in ospots:
        c.arrow(cx + cw / 2, cy + ch + 4, x + w / 2, oy - 6)
    return c


# --------------------------------------------------------------------------- functions


def pql_function() -> Canvas:
    c = Canvas("dev-pql-function", 300)
    y = c.title(
        "A PQL function is two implementations that must agree",
        "The reference implementation and the SQL are written together, and the "
        "suite runs both on the same inputs, on every engine that claims the function.",
    )
    fw = 470
    fbody = (
        "name, summary, arity, argument_types, returns; evaluate (the reference, "
        "required); sql and sql_by_engine; unsupported_on; requires; excel_divergence"
    )
    fh = card_height(fw, "Function(...)", fbody)
    c.card(
        LEFT,
        y + 30,
        fw,
        fh,
        "Function(...)",
        fbody,
        key="fn",
        accent=REFRACT,
        title_size=24,
        body_size=19,
    )
    rx = LEFT + fw + 70
    rw = 1340 - rx
    reg = (
        "FunctionRegistry.register",
        "refuses a volatile name (NOW, RAND): a control must replay. Registered by an "
        "explicit install(), never on import.",
        GREY,
    )
    rh = card_height(rw, reg[0], reg[1])
    c.card(rx, y + 30, rw, rh, reg[0], reg[1], key="reg", accent=GREY, title_size=24, body_size=19)
    c.arrow(LEFT + fw + 4, y + 30 + fh / 2, rx - 6, y + 30 + rh / 2)
    uy = y + 30 + max(fh, rh) + 60
    uses: list[Item] = [
        ("Checker", "arity and argument families, at prama control check", TEAL),
        ("Compiler", "render(engine): the template for that engine, or a refusal", GREEN),
        ("Reference interpreter", "evaluate(arguments): exact Decimal arithmetic", AMBER),
    ]
    spots, uh = row(c, uy, uses, key="use", arrows=False)
    for x, w in spots:
        c.arrow(rx + rw / 2, y + 30 + rh + 4, x + w / 2, uy - 6)
    note(
        c,
        LEFT,
        uy + uh + 36,
        FULL,
        "tests/pql/test_function_catalogue.py executes the compiler's SQL on DuckDB, "
        "SQLite and, with a DSN, PostgreSQL, and compares it with evaluate on the same "
        "arguments. prama control functions prints what each engine refuses.",
        key="suite",
    )
    return c


# --------------------------------------------------------------------------- validators


def validator_flow() -> Canvas:
    c = Canvas("dev-validator", 300)
    y = c.title(
        "A validator: a screen in SQL, a decision in Python",
        "IS VALID 'nhs_number' compiles the screen into the warehouse and checks "
        "the survivors exactly. The screen alone may never report a pass.",
    )
    label(c, LEFT, y + 22, "Admission, once")
    adm: list[Item] = [
        ("Entry point", "prama.validators in the distribution's metadata", TEAL),
        ("Source scan", "no clock, network, file, model or dynamic import", GREEN),
        ("Probes twice", "same answer, never raises on a blank", LIME),
        ("Implementation hash", "folded into every plan that names it", AMBER),
    ]
    _, ah = row(c, y + 40, adm, key="adm", ts=22, bs=18, gap=30)
    ry = y + 40 + ah + 70
    label(c, LEFT, ry - 18, "Every run")
    run: list[Item] = [
        ("Screen in SQL", "screen_pattern: a necessary condition every valid value meets", TEAL),
        ("Survivors", "rows that pass the screen, fetched to the residual", GREEN),
        ("check(value)", "the algorithm: a Judgement with a reason", REFRACT),
        ("Verdict", "fail with reasons; indeterminate if the residual did not run", AMBER),
    ]
    _, rh = row(c, ry, run, key="run", ts=22, bs=18, gap=30)
    note(
        c,
        LEFT,
        ry + rh + 36,
        FULL,
        "PATTERN and CODELIST validators are complete in SQL. An ALGORITHM validator "
        "is not: GB0000000000 passes every ISIN regex and is not an ISIN, so the "
        "screen narrows and the check decides.",
        key="why",
    )
    return c


# --------------------------------------------------------------------------- monitors


def monitor_flow() -> Canvas:
    c = Canvas("dev-monitor", 300)
    y = c.title(
        "From a metric to a person, and which parts are yours",
        "A detector scores; the calibrator decides how unusual the score is; the "
        "router decides who hears, once. Only the first is a plugin seam today.",
    )
    flow: list[Item] = [
        ("History", "one metric over time: rows, null rate, freshness", GREY),
        ("Detector.score", "a nonconformity score: larger when stranger. Your class.", REFRACT),
        ("Conformal calibration", "a p-value with a false-alarm bound alpha", TEAL),
        ("Alert", "fault, dataset, change since the last message", AMBER),
        ("Router", "fault to role, quiet period, digest, residency gate", GREEN),
    ]
    _, h = row(c, y + 30, flow, key="mon", ts=22, bs=18, gap=30)
    note(
        c,
        LEFT,
        y + 30 + h + 40,
        FULL,
        "A badly chosen detector costs sensitivity, never validity: noise scores are "
        "exchangeable with calibration scores, so the false-alarm rate still holds "
        "and the monitor simply finds less.",
        key="valid",
    )
    gy = y + 30 + h + 40 + 140
    gap_text = (
        "Delivery is not a plugin yet. Router.dispatch returns a Dispatch naming "
        "recipients and channels; nothing sends it. The prama.notifiers entry-point "
        "group is declared in configuration and read by nothing."
    )
    note(c, LEFT, gy, FULL, gap_text, key="gap", fill="#FBEFE6", size=19)
    return c


# --------------------------------------------------------------------------- scoring


def scoring_flow() -> Canvas:
    c = Canvas("dev-scoring", 300)
    y = c.title(
        "A score is derived from evidence, and names its arithmetic",
        "Nothing is typed in and nothing is a model's opinion. Change the method "
        "and every card says which method it is.",
    )
    flow: list[Item] = [
        ("Evidence", "the latest record per control, never every record", GREY),
        ("Measurement", "dimension, criticality weight, rows scanned and violating", TEAL),
        ("DimensionScore", "one per dimension, so the failing one is visible", GREEN),
        ("Composites", "Method: mean, minimum, weighted; disagreement is reported", AMBER),
    ]
    label(c, LEFT, y + 22, "Scores")
    _, h = row(c, y + 40, flow, key="sc", ts=22, bs=19)
    ty = y + 40 + h + 70
    label(c, LEFT, ty - 18, "Trust along lineage")
    trust: list[Item] = [
        ("Lineage graph", "column edges with transforms", GREY),
        ("Semiring", "how trust combines along a path and across paths: chosen, named", ORANGE),
        ("TrustPropagator", "with containment: a defect caught downstream stops", REFRACT),
    ]
    row(c, ty, trust, key="tr", ts=22, bs=19)
    return c


# --------------------------------------------------------------------------- importers


def importer_flow() -> Canvas:
    c = Canvas("dev-importer", 300)
    y = c.title(
        "An importer reports three things, and never guesses",
        "What came across exactly, what came across with a caveat, and what did not "
        "come across, each named.",
    )
    flow: list[Item] = [
        ("The other tool's file", "dbt schema.yml, SodaCL, a GX suite, a rules sheet", GREY),
        ("read_text", "_parse(text) into a document, then read(document)", TEAL),
        ("Collector", "control(pql, caveat=…) or unmapped(source, reason, remedy)", REFRACT),
        ("ImportResult", "controls, caveats, unmapped; render() for the reviewer", AMBER),
    ]
    _, h = row(c, y + 30, flow, key="imp", ts=22, bs=19)
    note(
        c,
        LEFT,
        y + 30 + h + 40,
        FULL,
        "Collector.control parses the PQL; an expression that does not parse becomes "
        "an unmapped entry rather than aborting the migration. Every control carries "
        "a BECAUSE naming its origin, built by because(origin).",
        key="coll",
    )
    return c


# --------------------------------------------------------------------------- llm


def llm_flow() -> Canvas:
    c = Canvas("dev-llm-provider", 300)
    y = c.title(
        "What happens before your provider is called",
        "You write complete(request). ask() runs three checks first, in the base "
        "class, so a provider somebody else wrote cannot skip them.",
    )
    flow: list[Item] = [
        ("Gateway", "profile route, budget, rate limit, call ledger", GREY),
        ("permit", "sensitivity against hosting: what class of data may go", TEAL),
        ("permit_residency", "where the data is from against where the model is", GREEN),
        ("withhold", "secrets, card numbers and IBANs redacted from the text", AMBER),
        ("complete", "your code: one HTTP call, a Response, never an exception", REFRACT),
    ]
    _, h = row(c, y + 30, flow, key="llm", ts=22, bs=18, gap=30)
    note(
        c,
        LEFT,
        y + 30 + h + 40,
        FULL,
        "A response is a draft for a person. It is re-validated against the data "
        "every time, and no module that calls a model may produce a verdict: "
        "tests/architecture/test_layering.py and test_verdicts_cannot_reach_a_model.py.",
        key="never",
        fill="#FBEFE6",
    )
    return c


# --------------------------------------------------------------------------- code readers


def code_reader_flow() -> Canvas:
    c = Canvas("dev-code-reader", 300)
    y = c.title(
        "Code in, lineage out, nothing executed",
        "Code intake reads bytes in a separate, resource-limited process and "
        "chooses a reader by the kind of each file.",
    )
    flow: list[Item] = [
        ("ZIP or git", "archive checks: paths, links, bombs", GREY),
        ("kind_of(path)", "suffix, refined by the first bytes", TEAL),
        ("_extract(kind)", "the worker's dispatch: one branch per kind", GREEN),
        ("Scanner.scan", "or SqlLineage: an Extraction of edges and gaps", REFRACT),
        ("Lineage store", "parsed, or inferred until a person confirms", AMBER),
    ]
    _, h = row(c, y + 30, flow, key="code", ts=22, bs=18, gap=30)
    note(
        c,
        LEFT,
        y + 30 + h + 40,
        FULL,
        "Three tables to touch when you add a reader: READ in inventory.py (what is "
        "read, and by what), the branch in worker._extract, and PARSED_METHODS in "
        "service.py if its edges are verified rather than inferred.",
        key="tables",
    )
    note(
        c,
        LEFT,
        y + 30 + h + 40 + 150,
        FULL,
        "Coverage is always reported: units found, units read, and every gap named, "
        "so a graph that is forty percent complete says so.",
        key="cover",
        fill=FROST,
    )
    return c


# --------------------------------------------------------------------------- delegates


def delegate_flow() -> Canvas:
    c = Canvas("dev-delegate", 300)
    y = c.title(
        "A delegate measures; Prama judges",
        "From a file to evidence, and the gate at each step.",
    )
    label(c, LEFT, y + 22, "Admission")
    adm: list[Item] = [
        ("File or entry point", "delegates.paths, prama.delegates, or a console upload", GREY),
        ("Vetted before import", "scan_source: no clock, network, file or model", TEAL),
        ("Admitted", "probe rows twice: same answer, never raises", GREEN),
        ("Registered", "name@version, with its source hash", AMBER),
    ]
    _, ah = row(c, y + 40, adm, key="dadm", ts=22, bs=18, gap=30)
    ry = y + 40 + ah + 70
    label(c, LEFT, ry - 18, "Every run")
    run: list[Item] = [
        ("USING DELEGATE", "the control names it, with parameters", GREY),
        ("Host", "fetches only requires, as JSON values, in batches", TEAL),
        ("Sandbox", "a subprocess with CPU, memory and row limits", GREEN),
        ("measure", "your code: a Measurement of counts", REFRACT),
        ("Judge", "the control's threshold, shared with every control", AMBER),
    ]
    _, rh = row(c, ry, run, key="drun", ts=22, bs=18, gap=26)
    note(
        c,
        LEFT,
        ry + rh + 36,
        FULL,
        "The design note docs/design/dq-delegates.md says why each gate exists. This "
        "guide is how to write one that passes them.",
        key="design",
        fill=FROST,
    )
    return c


# --------------------------------------------------------------------------- packs


def pack_flow() -> Canvas:
    c = Canvas("dev-pack", 300)
    y = c.title(
        "A pack contributes to the core, and adds no mechanism",
        "Everything a pack ships lands in a registry the core already has, "
        "installed explicitly at start.",
    )
    pw = 380
    body = (
        "functions, calendars, concepts, reconciliation templates, obligations, "
        "message readers, and a readout of what it does not claim"
    )
    ph = card_height(pw, "prama.packs.<domain>", body)
    c.card(
        LEFT,
        y + 40,
        pw,
        ph,
        "prama.packs.<domain>",
        body,
        key="pack",
        accent=REFRACT,
        title_size=24,
        body_size=19,
    )
    tx = LEFT + pw + 90
    tw = 1340 - tx
    targets: list[Item] = [
        ("PQL function registry", "crossfield.install: IBAN_BIC_CONSISTENT and friends", TEAL),
        ("Calendar registry", "TARGET2, FederalReserve, London, NYSE, from rules", GREEN),
        ("Readouts", "prama pack … and /api/v1/packs/banking", AMBER),
    ]
    ty = y + 40
    for i, (t, b, a) in enumerate(targets):
        th = card_height(tw, t, b, 22, 18)
        c.card(tx, ty, tw, th, t, b, key=f"tgt{i}", accent=a, title_size=22, body_size=18)
        c.arrow(LEFT + pw + 4, y + 40 + ph / 2, tx - 6, ty + th / 2)
        ty += th + 24
    note(
        c,
        LEFT,
        max(ty, y + 40 + ph) + 30,
        FULL,
        "install_shipped() in prama.packs runs once, from the CLI entry point and from "
        "create_app. A function that exists because a module happened to be imported "
        "compiles in one process and is refused in another.",
        key="once",
    )
    return c


# --------------------------------------------------------------------------- api and console


def api_console() -> Canvas:
    c = Canvas("dev-api-console", 300)
    y = c.title(
        "An endpoint and a page, and the tests that hold them",
        "A route declares its permission in its signature; the build walks the "
        "routing table to check, and requires an SDK method for every endpoint.",
    )
    label(c, LEFT, y + 22, "HTTP API")
    api: list[Item] = [
        ("routes/<area>.py", "a module with a router; found, not listed", TEAL),
        ("caller: Reader", "scoped('declaration:read') in the signature", GREEN),
        ("/api/v1/...", "mounted by create_app; OpenAPI lists it", REFRACT),
        ("SDK @endpoint", "prama_sdk.resources.<area>; test_parity both ways", AMBER),
    ]
    _, ah = row(c, y + 40, api, key="api", ts=22, bs=18, gap=30)
    cy = y + 40 + ah + 70
    label(c, LEFT, cy - 18, "Console")
    ui: list[Item] = [
        ("UiRoutes subclass", "SUBJECT and WRITE_SCOPE name what the pages are about", TEAL),
        ("self.page(...)", "scope 'auto': read for GET, write for POST, checked at import", GREEN),
        ("Template", "templates/<area>/*.html, extends base.html", REFRACT),
        ("Help", "a guide in web/guides or a document in docs/", AMBER),
    ]
    _, uh = row(c, cy, ui, key="ui", ts=22, bs=18, gap=30)
    note(
        c,
        LEFT,
        cy + uh + 36,
        FULL,
        "tests/architecture/test_scopes.py: every API route with a caller declares a "
        "real scope, a mutating route never settles for a read scope, and every role's "
        "grant is a scope some route requires.",
        key="scopes",
    )
    return c


# --------------------------------------------------------------------------- schema


def schema_dao() -> Canvas:
    c = Canvas("dev-schema-dao", 300)
    y = c.title(
        "A table, from the schema file to a service",
        "Change the CREATE TABLE in both files; never ALTER. Only prama.db imports "
        "SQLAlchemy, and everything above it talks to a DAO.",
    )
    flow: list[Item] = [
        ("schema/*.sql", "the same CREATE TABLE in sqlite.sql and postgres.sql", TEAL),
        ("ORM model", "db/models/<area>.py on Base, or EvidenceBase for the ledger", GREEN),
        ("DAO", "db/dao/<area>.py: Dao[Model], tenant on every method", REFRACT),
        ("Unit of work", "a lazy property on UnitOfWork: uow.<name>", AMBER),
        ("Service or route", "receives a unit of work, never a session", GREY),
    ]
    _, h = row(c, y + 30, flow, key="db", ts=22, bs=18, gap=30)
    note(
        c,
        LEFT,
        y + 30 + h + 40,
        FULL,
        "tests/db/test_schema.py: the two files are byte-identical below their "
        "headers, only VARCHAR(n), TEXT, INTEGER and REAL are used, every table has a "
        "model and every model a table, and widths and nullability agree.",
        key="checks",
    )
    return c


# --------------------------------------------------------------------------- sdk


def sdk_parity() -> Canvas:
    c = Canvas("dev-sdk-parity", 300)
    y = c.title(
        "Every endpoint has an SDK method, and every method an endpoint",
        "The decorator files a method under the route it calls; the parity test "
        "compares that registry with the server's OpenAPI document.",
    )
    half = (FULL - 120) / 2
    left = (
        "Server",
        "create_app(config).openapi(): every (method, path) under /api/v1",
        REFRACT,
    )
    right = (
        "SDK",
        "@endpoint(method, path) on a Resource method; base.ENDPOINTS",
        GREEN,
    )
    h = max(card_height(half, *left[:2]), card_height(half, *right[:2]))
    c.card(
        LEFT,
        y + 30,
        half,
        h,
        left[0],
        left[1],
        key="srv",
        accent=left[2],
        title_size=24,
        body_size=19,
    )
    c.card(
        LEFT + half + 120,
        y + 30,
        half,
        h,
        right[0],
        right[1],
        key="sdk",
        accent=right[2],
        title_size=24,
        body_size=19,
    )
    c.arrow(LEFT + half + 8, y + 30 + h / 2, LEFT + half + 112, y + 30 + h / 2)
    c.arrow(LEFT + half + 112, y + 30 + h / 2 + 24, LEFT + half + 8, y + 30 + h / 2 + 24)
    note(
        c,
        LEFT,
        y + 30 + h + 40,
        FULL,
        "tests/sdk/test_parity.py fails on an endpoint with no method (missing) and on "
        "a method calling no endpoint (phantom), and proves it can fail by filing a "
        "phantom of its own.",
        key="parity",
    )
    return c


# --------------------------------------------------------------------------- agent


def agent_executor() -> Canvas:
    c = Canvas("dev-agent-executor", 300)
    y = c.title(
        "An assignment, run beside the data",
        "The server compiles; the agent only executes, read-only, against the source "
        "the assignment's binding names.",
    )
    flow: list[Item] = [
        ("Assignment", "plan, binding, engine, metric_query: compiled on the server", GREY),
        ("Executors", "by binding, then by a source listing the dataset; engine must match", TEAL),
        ("SourceExecutor", "batches(sql, size): read-only by construction. Your class.", REFRACT),
        ("Kernel judge", "the same threshold code the server uses", GREEN),
        ("Spool and report", "evidence kept until the server acknowledges it", AMBER),
    ]
    _, h = row(c, y + 30, flow, key="ag", ts=22, bs=18, gap=30)
    note(
        c,
        LEFT,
        y + 30 + h + 40,
        FULL,
        "A new engine touches three places: ENGINES in prama_agent.config (what a "
        "source may name), _BY_ENGINE in prama_agent.executors, and backend DIALECTS "
        "on the server, so there is SQL to send it.",
        key="three",
    )
    return c


# --------------------------------------------------------------------------- secrets and leases


def secrets_leases() -> Canvas:
    c = Canvas("dev-secrets-leases", 300)
    y = c.title(
        "References in, values out; one holder at a time",
        "A secret provider turns a reference into a value that will not print. A "
        "lease provider makes one instance of a fleet do a job, provably.",
    )
    label(c, LEFT, y + 22, "Secrets")
    sec: list[Item] = [
        ("SecretRef", "scheme://location#key, parsed; never the value", GREY),
        ("SecretResolver", "by scheme; cached; every access audited", TEAL),
        ("SecretProvider.resolve", "your class: a value or a refusal with a remedy", REFRACT),
        ("SecretValue", "reveal() is the one way out", GREEN),
    ]
    _, sh = row(c, y + 40, sec, key="sec", ts=22, bs=18, gap=30)
    ly = y + 40 + sh + 70
    label(c, LEFT, ly - 18, "Leases")
    lease: list[Item] = [
        ("acquire", "atomic: None if another holder owns it", TEAL),
        ("LeaseHolder", "renews in the background; reports loss", GREEN),
        ("fencing_token", "strictly increasing; a store rejects a stale writer", AMBER),
        ("release", "on exit; False if it was already lost", GREY),
    ]
    _, lh = row(c, ly, lease, key="lease", ts=22, bs=18, gap=30)
    note(
        c,
        LEFT,
        ly + lh + 36,
        FULL,
        "Shipped: env, file and vault secrets; memory and database leases. "
        "Config sources (YAML, properties, environment, --set) follow the same "
        "pattern, behind ConfigSource.",
        key="shipped",
        fill=FROST,
    )
    return c


DIAGRAMS: list[Callable[[], Canvas]] = [
    plugin_model,
    extension_map,
    connector_classes,
    connector_lifecycle,
    dialect_families,
    pushdown_choice,
    pql_function,
    validator_flow,
    monitor_flow,
    scoring_flow,
    importer_flow,
    llm_flow,
    code_reader_flow,
    delegate_flow,
    pack_flow,
    api_console,
    schema_dao,
    sdk_parity,
    agent_executor,
    secrets_leases,
]
