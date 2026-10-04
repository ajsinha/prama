"""
Diagrams for docs/architecture, drawn from the code they describe.

Each function returns a ``Canvas`` (tools/diagrams/canvas.py) and ``DIAGRAMS``
lists them; tools/docs/diagrams.py writes them to docs/assets/diagrams/ as
``arch-*.svg`` and audits the rendered geometry. Every module, class and
function named in a diagram is a real one: the pages that embed these pictures
are checked against the code, and a picture that names something that does not
exist is the same defect in a less searchable form.

Most diagrams use one layout, ``pipeline``: a step on the left, the code that
performs it on the right, in the order data flows. That keeps a diagram legible
at any length and makes it reviewable in a diff, which a hand-placed drawing is
not.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
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
    RED,
    REFRACT,
    RULE,
    SLATE,
    TEAL,
    Canvas,
    wrap,
)

LEFT, RIGHT = 60, 1340
CODE = 18
GAP = 40

# --------------------------------------------------------------------------- layout


def need(w: float, title: str, body: str = "", ts: int = 24, bs: int = 21) -> int:
    """The height a card needs, computed the way ``Canvas.card`` lays it out."""
    lines = len(wrap(title, w - 48, ts, bold=True))
    h = 26 + ts + (lines - 1) * ts * 1.35 + 0.4 * ts
    if body:
        lines = len(wrap(body, w - 48, bs))
        h += 2 + bs + (lines - 1) * bs * 1.35 + 0.4 * bs
    return int(h + 36)


def code_height(w: float, lines: Sequence[str], size: int = CODE) -> int:
    total = sum(len(wrap(line, w - 40, size, mono=True)) for line in lines)
    return int(22 + total * size * 1.35 + 2 * len(lines) + 16)


def code_box(c: Canvas, x, y, w, h, lines: Sequence[str], key: str, size: int = CODE) -> None:
    c.rect(x, y, w, h, fill=FROST, stroke=RULE, box=key)
    yy = y + 12
    for line in lines:
        yy = c.block(x + 20, yy, w - 40, line, size, INK, mono=True, box=key) - size * 0.4 + 6


def pipeline(
    c: Canvas,
    y: float,
    rows: Sequence[tuple[str, str, Sequence[str], str]],
    left_w: int = 460,
    prefix: str = "p",
) -> float:
    """Steps down the left, the code that performs each one on the right."""
    code_x = LEFT + left_w + 30
    code_w = RIGHT - code_x
    for i, (title, body, code, accent) in enumerate(rows):
        h = max(need(left_w, title, body), code_height(code_w, code) if code else 0, 90)
        c.card(LEFT, y, left_w, h, title, body, key=f"{prefix}{i}", accent=accent, title_size=24)
        if code:
            code_box(c, code_x, y, code_w, h, code, key=f"{prefix}c{i}")
            c.arrow(LEFT + left_w + 2, y + h / 2, code_x - 4, y + h / 2, color=GREY, width=2)
        if i < len(rows) - 1:
            c.arrow(LEFT + left_w / 2, y + h + 2, LEFT + left_w / 2, y + h + GAP - 4)
        y += h + GAP
    return y - GAP


def note(c: Canvas, y: float, text: str, key: str, fill: str = MIST, size: int = 21) -> float:
    lines = len(wrap(text, RIGHT - LEFT - 48, size))
    h = int(24 + size + (lines - 1) * size * 1.35 + 0.4 * size + 22)
    c.rect(LEFT, y, RIGHT - LEFT, h, fill=fill, stroke=fill, box=key)
    c.block(LEFT + 24, y + 14, RIGHT - LEFT - 48, text, size, INK, box=key)
    return y + h


def grid(
    c: Canvas,
    y: float,
    items: Sequence[tuple[str, str, str]],
    cols: int,
    prefix: str,
    gap: int = 30,
) -> float:
    """Cards in rows of ``cols``, each row as tall as its tallest card."""
    w = (RIGHT - LEFT - gap * (cols - 1)) / cols
    for start in range(0, len(items), cols):
        row = items[start : start + cols]
        h = max(need(w, t, b) for t, b, _ in row)
        for j, (title, body, accent) in enumerate(row):
            c.card(
                LEFT + j * (w + gap),
                y,
                w,
                h,
                title,
                body,
                key=f"{prefix}{start + j}",
                accent=accent,
            )
        y += h + gap
    return y - gap


# --------------------------------------------------------------------------- README


def distributions() -> Canvas:
    c = Canvas("arch-distributions", 900)
    y = c.title(
        "Four distributions, and which way the imports go",
        "One repository ships four Python packages. Arrows are imports; the dashed one is "
        "HTTP. Nothing points back up.",
    )
    w = 560
    top, bottom = y + 20, y + 330
    c.card(
        LEFT,
        top,
        w,
        230,
        "prama: the server",
        "src/prama. FastAPI, SQLAlchemy, DuckDB, sqlglot. Console, API, CLI, scheduler, "
        "compiler, evidence ledger. 27 of its modules are aliases of kernel modules.",
        key="server",
        accent=INDIGO,
    )
    c.card(
        780,
        top,
        w,
        230,
        "prama-sdk",
        "sdk/src/prama_sdk. httpx and PyYAML only. What a client installs: one method per "
        "endpoint, the server's errors mapped to its own.",
        key="sdk",
        accent=REFRACT,
    )
    c.card(
        LEFT,
        bottom,
        w,
        230,
        "prama-kernel",
        "kernel/src/prama_kernel. Standard library only. The plan model, judge, evidence "
        "record, reconciliation, calendars, delegate runtime, agent protocol.",
        key="kernel",
        accent=TEAL,
    )
    c.card(
        780,
        bottom,
        w,
        230,
        "prama-agent",
        "agent/src/prama_agent. The daemon beside the data. Depends on the kernel and the "
        "SDK, PyYAML, and duckdb or psycopg as extras.",
        key="agent",
        accent=GREEN,
    )
    c.arrow(LEFT + w / 2, top + 232, LEFT + w / 2, bottom - 6)
    c.text(LEFT + w / 2 + 14, top + 268, "imports", 19, SLATE)
    c.arrow(778, bottom + 115, LEFT + w + 6, bottom + 115)
    c.text(650, bottom + 104, "imports", 19, SLATE, anchor="middle")
    c.arrow(780 + w / 2, bottom - 2, 780 + w / 2, top + 236)
    c.text(780 + w / 2 + 14, top + 268, "imports", 19, SLATE)
    c.arrow(778, top + 115, LEFT + w + 6, top + 115, dashed=True)
    c.text(700, top + 104, "HTTP", 19, SLATE, anchor="middle")
    note(
        c,
        bottom + 260,
        "Enforced by tests/architecture/test_packages_standalone.py: no module imports "
        "against the arrows; the kernel, the SDK and a full agent cycle each run with prama "
        "made unimportable; each wheel carries only its own package and requires only its "
        "declared dependencies.",
        "rule",
    )
    return c


def life() -> Canvas:
    c = Canvas("arch-life-of-a-control", 1600)
    y = c.title(
        "The life of a control",
        "From what an owner says the data means to a verdict somebody else can check. "
        "Left: the step. Right: the code that performs it.",
    )
    pipeline(
        c,
        y + 10,
        [
            (
                "1. Declare",
                "An owner states grain, rhythm, domains, relationships, metadata.",
                [
                    "prama.semantic.services.DatasetService",
                    "sem_dataset_version (bitemporal)",
                    "ApprovalPolicy: tier 1 needs maker-checker",
                ],
                INDIGO,
            ),
            (
                "2. Derive and propose",
                "Deterministic generators turn each fact into PQL.",
                [
                    "prama.derive.ControlGenerator (Γ)",
                    "controls.proposals.queue()",
                    "propose.ProposalQueue: rejections remembered",
                ],
                REFRACT,
            ),
            (
                "3. Approve",
                "A person accepts; the control version becomes active.",
                [
                    "controls.proposals.accept()",
                    "ControlDao.declare, ControlDao.activate",
                    "ctl_control_version.status = 'active'",
                ],
                REFRACT,
            ),
            (
                "4. Compile",
                "PQL parses, type-checks, lowers to a hashed plan, then SQL.",
                [
                    "pql.parse_control → ir.resolve.resolved",
                    "ControlPlan  plan_id = ir:sha256:…",
                    "backend.compile_for(plan, dialect)",
                ],
                REFRACT,
            ),
            (
                "5. Execute",
                "On the server, or beside the data by an agent.",
                [
                    "execute.run.ControlRun.execute_all",
                    "or prama_agent.runner.Agent.run",
                    "read-only sources; the agent never compiles",
                ],
                TEAL,
            ),
            (
                "6. Judge",
                "One deterministic function decides the verdict.",
                [
                    "prama_kernel.judge.judge / judge_segments",
                    "pass | fail | indeterminate | error | skipped",
                ],
                TEAL,
            ),
            (
                "7. Record",
                "Each verdict becomes a hash-chained evidence record.",
                [
                    "EvidenceDao.append(EvidenceRecord)",
                    "record_hash = sha256(prev + content)",
                    "evidence.anchor: RFC 3161 witness",
                ],
                GREEN,
            ),
            (
                "8. Score, report, alert",
                "Everything downstream derives from the evidence.",
                [
                    "score.scorecard, score.trust.TrustPropagator",
                    "report.attest, incident.triage, alert.route.Router",
                ],
                AMBER,
            ),
        ],
    )
    return c


def request_path() -> Canvas:
    c = Canvas("arch-request-path", 1000)
    y = c.title(
        "One request, every surface",
        "Four ways in, one way to the database. A route never touches SQLAlchemy; a DAO "
        "never decides policy.",
    )
    w, gap = 295, 33
    entries = [
        ("Console", "Jinja pages, session cookie", INDIGO),
        ("SDK", "prama_sdk.Client over httpx", REFRACT),
        ("Any HTTP client", "X-Prama-API-Key or Bearer", REFRACT),
        ("CLI", "prama … in-process", TEAL),
    ]
    for i, (t, b, a) in enumerate(entries):
        c.card(LEFT + i * (w + gap), y + 10, w, 130, t, b, key=f"e{i}", accent=a)
    ly = y + 210
    c.card(
        LEFT,
        ly,
        w,
        150,
        "prama.web.routes",
        "ROUTE_CLASSES, mounted by mount_ui",
        key="web",
        accent=INDIGO,
    )
    c.card(
        LEFT + (w + gap),
        ly,
        2 * w + gap,
        150,
        "prama.api.routes  /api/v1",
        "discover() includes every module with a router; deps.scoped(scope) "
        "authenticates and checks the scope",
        key="api",
        accent=REFRACT,
    )
    c.arrow(LEFT + w / 2, y + 142, LEFT + w / 2, ly - 6)
    for i in (1, 2):
        x = LEFT + i * (w + gap) + w / 2
        c.arrow(x, y + 142, x, ly - 6)
    sy = ly + 220
    c.card(
        LEFT,
        sy,
        RIGHT - LEFT,
        130,
        "Services: shared domain operations",
        "prama.semantic.services, prama.controls.language / proposals / runs, "
        "prama.evidence.service, prama.recon.service. Some routes call a DAO directly.",
        key="svc",
        accent=GREY,
    )
    c.arrow(LEFT + w / 2, ly + 152, LEFT + w / 2, sy - 6)
    c.arrow(LEFT + 1.5 * (w + gap) + w / 2, ly + 152, LEFT + 1.5 * (w + gap) + w / 2, sy - 6)
    cx = LEFT + 3 * (w + gap) + w / 2
    c.arrow(cx, y + 142, cx, sy - 6)
    uy = sy + 190
    c.card(
        LEFT,
        uy,
        820,
        150,
        "prama.db.session.UnitOfWork",
        "one transaction per request; lazy DAOs (uow.controls → ControlDao); commit on "
        "success, rollback on error; db.guard translates failures",
        key="uow",
        accent=GREEN,
    )
    c.card(
        910,
        uy,
        430,
        150,
        "Two schema files",
        "schema/sqlite.sql and postgres.sql: 75 tables, applied and verified, never migrated",
        key="schema",
        accent=AMBER,
        body_size=18,
    )
    c.arrow(LEFT + 410, sy + 132, LEFT + 410, uy - 6)
    c.arrow(882, uy + 75, 906, uy + 75)
    return c


# --------------------------------------------------------------------------- packages


def alias() -> Canvas:
    c = Canvas("arch-kernel-alias", 800)
    y = c.title(
        "One module object under two names",
        "The server's old import paths still work, and they are the kernel's code, not a "
        "copy of it: the alias replaces itself in sys.modules.",
    )
    code_box(c, LEFT, y + 20, 360, 120, ["from prama.core.errors", "  import NotFoundError"], "use")
    code_box(
        c,
        450,
        y + 20,
        560,
        200,
        [
            "# src/prama/core/errors.py",
            "from prama_kernel import errors as _kernel",
            "from prama_kernel.errors import *",
            "sys.modules[__name__] = _kernel",
        ],
        "alias",
    )
    c.card(
        1070,
        y + 20,
        270,
        200,
        "prama_kernel",
        ".errors: the only copy, and what the agent imports",
        key="kernel",
        accent=TEAL,
    )
    c.arrow(422, y + 80, 446, y + 80)
    c.arrow(1012, y + 120, 1066, y + 120)
    code_box(
        c,
        LEFT,
        y + 270,
        RIGHT - LEFT,
        250,
        [
            "prama.core.{errors, clock, calendars, log, pjson} → prama_kernel.{same}",
            "prama.ir.model → prama_kernel.plan",
            "prama.backend.execute → prama_kernel.judge",
            "prama.evidence.record → prama_kernel.record",
            "prama.recon.{engine, match, normalise, classify, nway, pql} → prama_kernel.recon.*",
            "prama.delegates.{spi, registry, host, sandbox, worker} → prama_kernel.delegates.*",
            "prama.agent.{protocol, capability, residency, spool} → prama_kernel.agent.*",
            "prama.semantic.relationships, prama.classify.plugins, prama.packs.banking.{calendars,"
            " holidays} → their kernel modules",
        ],
        "list",
        size=17,
    )
    note(
        c,
        y + 560,
        "test_the_server_aliases_are_the_kernel_modules asserts identity (is), not equality: "
        "prama.core.errors is prama_kernel.errors. A copy would pass an equality test and "
        "drift on the first fix.",
        "id",
    )
    return c


# --------------------------------------------------------------------------- semantic


def semantic_model() -> Canvas:
    c = Canvas("arch-semantic-model", 1000)
    y = c.title(
        "What a declaration is, and where it is kept",
        "Every declared thing is an identity row plus versioned rows with valid and recorded "
        "time, author and approver. Controls are derived from it, never the other way round.",
    )
    y = grid(
        c,
        y + 10,
        [
            (
                "Dataset",
                "sem_dataset_version: grain, business key, rhythm, criticality 1-4, "
                "temporality, authoritativeness, owner, steward, business context",
                INDIGO,
            ),
            (
                "Attribute",
                "sem_attribute_version: definition, semantic type, unit, value domain, "
                "optionality, CDE flag, concept property, glossary term",
                INDIGO,
            ),
            (
                "Relationship",
                "sem_relationship_version: 13 kinds (references, reconciles_with, "
                "derives_from, feeds …), match keys, tolerance, status proposed or confirmed",
                REFRACT,
            ),
            (
                "Concepts, journeys",
                "sem_concept, sem_concept_property, sem_journey, "
                "sem_domain: the shared vocabulary and the map",
                REFRACT,
            ),
            (
                "Connection and binding",
                "sem_connection, sem_binding: where a declared dataset "
                "physically is, by a connector the business configured",
                TEAL,
            ),
            (
                "Metadata and glossary",
                "md_template, md_field, md_value; gl_term, gl_binding. A "
                "metadata field may carry a rule",
                AMBER,
            ),
        ],
        3,
        "m",
    )
    y += 50
    c.card(
        LEFT,
        y,
        600,
        170,
        "prama.derive.ControlGenerator (Γ)",
        "grain → uniqueness; rhythm → freshness and volume; value domain → membership; "
        "relationship → RelationshipGenerator",
        key="gamma",
        accent=GREEN,
    )
    c.card(
        740,
        y,
        600,
        170,
        "prama.semantic.policy.ApprovalPolicy",
        "tier 1: maker-checker; tier 2: review; tiers 3 and 4: none. An author cannot "
        "approve their own Tier-1 declaration",
        key="policy",
        accent=RED,
    )
    c.arrow(LEFT + 300, y - 46, LEFT + 300, y - 6)
    c.arrow(1040, y - 46, 1040, y - 6)
    return c


def metadata_flow() -> Canvas:
    c = Canvas("arch-metadata-to-proposal", 1100)
    y = c.title(
        "From a metadata value to a proposed control",
        "Setting mandatory=yes on a column proposes its check. Nothing runs until a person "
        "accepts it, and setting it back retracts the proposal.",
    )
    pipeline(
        c,
        y + 10,
        [
            (
                "Set a value",
                "prama metadata set trades.account_id mandatory=yes",
                [
                    "semantic.services.metadata.set_values",
                    "md_value row, coerced to the field kind",
                ],
                INDIGO,
            ),
            (
                "Render the field's rule",
                "Values enter only as literals: metadata cannot inject PQL.",
                [
                    "semantic.metadata.render",
                    "pql: CHECK {{ dataset }}.{{ attribute }} IS NOT NULL",
                ],
                REFRACT,
            ),
            (
                "Parse and identify",
                "A stable identity, so a re-render amends, never duplicates.",
                ["pql.parse_control", "identity = metadata-<sha256(row, target, index)>"],
                REFRACT,
            ),
            (
                "Queue with every other source",
                "Γ, lineage, metadata and correlation, merged.",
                ["controls.proposals.queue()", "skips what is live or was rejected"],
                TEAL,
            ),
            (
                "A person decides",
                "Accept activates; reject is remembered with a reason.",
                [
                    "controls.proposals.accept → ControlDao.activate",
                    "controls.proposals.reject → ctl_rejection",
                ],
                GREEN,
            ),
        ],
    )
    return c


# --------------------------------------------------------------------------- controls


def pql_pipeline() -> Canvas:
    c = Canvas("arch-pql-pipeline", 1300)
    y = c.title(
        "PQL to SQL: one pipeline for every surface",
        "The console's studio, prama control check, the language server and the API all "
        "call the same functions. Each stage refuses rather than guesses.",
    )
    pipeline(
        c,
        y + 10,
        [
            (
                "Tokens",
                "Keywords are recognised, not reserved: a column may be called severity.",
                ["prama.pql.tokens.tokenise / Lexer"],
                INDIGO,
            ),
            (
                "Syntax tree",
                "Recursive descent; every error carries a caret and a remedy.",
                ["prama.pql.parser.parse / parse_control", "→ ast.Control (Severity, Dimension …)"],
                INDIGO,
            ),
            (
                "Types and lint",
                "Against the declared estate, not a separate catalogue.",
                [
                    "pql.types.TypeChecker(Catalogue)",
                    "pql.lint.Linter: never-fires, subsumed …",
                    "pql.analysis.LanguageService (console, prama lsp)",
                ],
                REFRACT,
            ),
            (
                "Plan (IR)",
                "Engine-neutral, content-addressed; code lists frozen as of a date.",
                [
                    "prama.ir.resolve.resolved → ir.lower.Lowerer",
                    "prama_kernel.plan.ControlPlan",
                    "plan_id = ir:sha256:<meaning()>",
                ],
                REFRACT,
            ),
            (
                "SQL for one engine",
                "A function the engine cannot express is refused.",
                [
                    "prama.backend.compile_for(plan, dialect)",
                    "SqlCompiler → CompiledControl",
                    "metric_query, sample_query, residual_validators",
                ],
                TEAL,
            ),
            (
                "Shared scans (shown, not run)",
                "Fusion groups controls on one table.",
                ["prama.backend.fuse.Fuser", "prama control compile --fuse"],
                GREY,
            ),
        ],
    )
    return c


def proposal_lifecycle() -> Canvas:
    c = Canvas("arch-proposal-lifecycle", 820)
    y = c.title(
        "Where controls come from, and the four states they can be in",
        "Every origin reaches the same queue. Only a person turns a proposal into a running "
        "control, and a rejection is remembered, not forgotten.",
    )
    origins = [
        ("declaration", 100),
        ("document", 80),
        ("import", 60),
        ("mining", 40),
        ("example", 30),
        ("induction", 20),
    ]
    for i, (name, rank) in enumerate(origins):
        c.chip(
            LEFT,
            y + 10 + i * 66,
            300,
            50,
            f"{name} · {rank}",
            INDIGO if i == 0 else REFRACT,
            size=21,
            key=f"o{i}",
        )
        c.arrow(LEFT + 302, y + 35 + i * 66, 440, y + 200)
    c.card(
        444,
        y + 40,
        400,
        330,
        "ProposalQueue.offer",
        "admitted, duplicate, corroborated (stronger origin kept), already_live, "
        "superseded, suppressed, reopened (violation rate moved 2x)",
        key="q",
        accent=REFRACT,
    )
    states = [("proposed", GREY), ("active", GREEN), ("suppressed", AMBER), ("retired", SLATE)]
    for i, (name, col) in enumerate(states):
        c.chip(940, y + 10 + i * 80, 400, 56, name, col, size=22, key=f"s{i}")
    c.arrow(846, y + 150, 936, y + 40)
    note(
        c,
        y + 420,
        "ctl_control_version.status is one of these four (a CHECK constraint). Suppression "
        "needs an end date and a reason. Nothing is deleted. A rejection goes to "
        "ctl_rejection with one of six reasons; incorrect and coincidental indict the rule, "
        "the rest may be reconsidered when the data changes.",
        "n",
    )
    return c


# --------------------------------------------------------------------------- execution


def control_run() -> Canvas:
    c = Canvas("arch-control-run", 1400)
    y = c.title(
        "A scheduled run, from tick to evidence",
        "The path every server-side verdict takes. One compiled query per control; a "
        "failure becomes an error verdict with its reason, and the next control runs.",
    )
    pipeline(
        c,
        y + 10,
        [
            (
                "Tick, on one server",
                "Off unless scheduler.enabled and scheduler.against are set.",
                [
                    "execute.scheduler.Scheduler.tick",
                    "lease 'scheduler:tick' via lease_provider()",
                    "or POST /api/v1/runs → controls.runs.run_connection",
                ],
                INDIGO,
            ),
            (
                "Open the run",
                "Committed at once, so a crash leaves a visible running row.",
                [
                    "execute.run.ControlRun.execute_all",
                    "uow.evidence_runs.start",
                    "schedule.due.Schedule.plan(live, now, last_run)",
                ],
                INDIGO,
            ),
            (
                "Compile",
                "From the stored PQL, every time.",
                ["parse_control → resolved → compile_for(plan, engine)"],
                REFRACT,
            ),
            (
                "Execute at the source",
                "Read-only, confined to configured roots.",
                [
                    "connect.sources.query.executor_for",
                    "reconcile: recon.pql.measure",
                    "delegate: DelegateHost.measure_stream",
                ],
                TEAL,
            ),
            (
                "Judge",
                "Screen-only SQL cannot pass: pass becomes indeterminate.",
                [
                    "prama_kernel.judge.judge / judge_segments",
                    "Verdict: pass fail indeterminate",
                    "error skipped",
                ],
                TEAL,
            ),
            (
                "Record",
                "Failing rows stored apart, by hash; the record links to the last.",
                ["uow.samples.put, uow.evidence.append", "evidence.anchor.anchor_after_run"],
                GREEN,
            ),
        ],
    )
    return c


def delegate_sandbox() -> Canvas:
    c = Canvas("arch-delegate-sandbox", 1100)
    y = c.title(
        "A delegate measures; the control decides",
        "CHECK t USING DELEGATE 'acme.settlement_cycle@1' runs admitted Python in a separate, "
        "limited process. It returns counts. The threshold and the judge stay in Prama.",
    )
    pipeline(
        c,
        y + 10,
        [
            (
                "Admit",
                "Entry points, configured paths, or an upload approved by a second person.",
                [
                    "prama_kernel.delegates.registry.DelegateRegistry",
                    "delegates.uploads (vet, decide)",
                ],
                INDIGO,
            ),
            (
                "Stream the rows",
                "Batches of delegates.batch_rows (10,000).",
                ["DelegateHost.measure_stream(plan, batches)"],
                REFRACT,
            ),
            (
                "Isolate",
                "A new interpreter, no network where the host allows it.",
                [
                    "python -m prama_kernel.delegates.worker",
                    "unshare --net --map-root-user",
                    "RLIMIT_CPU, RLIMIT_AS 2048 MB, NOFILE 256, CORE 0",
                ],
                AMBER,
            ),
            (
                "Seal",
                "An audit hook refuses sockets, subprocesses and exec.",
                ["worker.seal → sys.addaudithook"],
                AMBER,
            ),
            (
                "Measure, then judge",
                "The delegate's numbers meet the control's threshold.",
                ["Measurement(scanned, violating, observations)", "prama_kernel.judge.judge"],
                GREEN,
            ),
        ],
    )
    return c


def reconciliation() -> Canvas:
    c = Canvas("arch-reconciliation", 1150)
    y = c.title(
        "RECONCILE: two systems, one control",
        "Case study 6: a subledger in three currencies against a EUR ledger. The same "
        "kernel code runs on the server and on an agent.",
    )
    pipeline(
        c,
        y + 10,
        [
            (
                "Define",
                "From the plan, never re-parsed by hand.",
                [
                    "prama_kernel.recon.pql.definition_of(plan)",
                    "Definition(left, right, key, tolerance, …)",
                ],
                INDIGO,
            ),
            (
                "Match",
                "Exact keys, or a date window when OFFSET BY allows it.",
                [
                    "recon.match.Matcher / ToleranceMatcher",
                    "MatchReport: pairs, unmatched, match_rate",
                ],
                REFRACT,
            ),
            (
                "Normalise",
                "Currency converted before comparing, and the rate recorded.",
                ["recon.normalise.AmountNormaliser (RateSource)"],
                REFRACT,
            ),
            (
                "Classify each break",
                "Ordered by what needs a person, not by size.",
                [
                    "recon.classify.Classifier → BreakKind",
                    "timing fx rounding missing extra",
                    "duplicate sign genuine",
                ],
                TEAL,
            ),
            (
                "Judge and work",
                "violating_rows = breaks that do not clear themselves.",
                ["uow.breaks.observe → rec_break", "recon.workflow.BreakQueue, certify"],
                GREEN,
            ),
        ],
    )
    return c


# --------------------------------------------------------------------------- evidence


def evidence_chain() -> Canvas:
    c = Canvas("arch-evidence-chain", 960)
    y = c.title(
        "The evidence ledger, and how it is checked without Prama",
        "Records chain to each other, roll up to a Merkle root, are witnessed outside Prama, "
        "and export to a bundle a standard-library script verifies.",
    )
    w, gap = 280, 50
    for i in range(4):
        x = LEFT + i * (w + gap)
        code_box(
            c,
            x,
            y + 20,
            w,
            170,
            [f"ev_record #{i}", "content_hash", f"prev = h{i}", f"hash = h{i + 1}"],
            f"r{i}",
        )
        if i:
            c.arrow(x - gap + 4, y + 105, x - 6, y + 105)
    c.card(
        LEFT,
        y + 240,
        600,
        150,
        "merkle_root(hashes)",
        "prama.evidence.ledger: one digest for the chain; an odd node is promoted",
        key="mr",
        accent=INDIGO,
    )
    c.card(
        740,
        y + 240,
        600,
        150,
        "Rfc3161Anchor",
        "evidence.anchor: the head time-stamped by a TSA, stored in ev_anchor",
        key="an",
        accent=AMBER,
    )
    for i in range(4):
        x = LEFT + i * (w + gap) + w / 2
        c.arrow(x, y + 192, x, y + 236)
    c.card(
        LEFT,
        y + 450,
        600,
        160,
        "prama evidence export bundle/",
        "manifest.json, evidence.ndjson, anchors.json; refused if the chain does not verify",
        key="ex",
        accent=GREEN,
    )
    c.card(
        740,
        y + 450,
        600,
        160,
        "scripts/verify_evidence.py",
        "imports nothing from Prama; checks count, digest, chain, Merkle root, and anchors "
        "with openssl ts -verify",
        key="vf",
        accent=GREEN,
    )
    c.arrow(LEFT + 300, y + 392, LEFT + 300, y + 446)
    c.arrow(1040, y + 392, 1040, y + 446)
    c.arrow(662, y + 530, 736, y + 530)
    note(
        c,
        y + 650,
        "EvidenceBase owns ev_run, ev_record, ev_sample and ev_anchor, so no cascade from the "
        "platform schema can reach them. Erasure replaces content with a sealed Tombstone and "
        "keeps the original content hash, so the chain still links.",
        "eb",
    )
    return c


def scoring() -> Canvas:
    c = Canvas("arch-score-from-evidence", 1250)
    y = c.title(
        "Scores are derived from evidence, never entered",
        "A scorecard is a function of the latest record per control. When the methods "
        "disagree the card says so instead of picking the flattering one.",
    )
    pipeline(
        c,
        y + 10,
        [
            (
                "Latest record per control",
                "Error, skipped and indeterminate did not run.",
                ["uow.evidence.latest_per_control", "score.scorecard._measurement"],
                INDIGO,
            ),
            (
                "Measurement",
                "rate = 1 - violating / scanned, weighted by criticality.",
                ["score.composite.Measurement", "CRITICALITY_WEIGHT tier 1-4: 16, 8, 2, 1"],
                REFRACT,
            ),
            (
                "Dimension scores",
                "Eight dimensions, each from its own controls.",
                [
                    "completeness uniqueness validity consistency",
                    "accuracy timeliness integrity conformity",
                ],
                REFRACT,
            ),
            (
                "Three composites",
                "MEAN, MINIMUM, WEIGHTED; methods_disagree beyond 0.1.",
                ["score.composite.score → Score.composites"],
                TEAL,
            ),
            (
                "Trust along lineage",
                "The deficit is attenuated, not the score.",
                [
                    "score.trust.TrustPropagator",
                    "ALL_INPUTS_MATTER, WEAKEST_LINK …",
                    "a passing containment control stops it",
                ],
                TEAL,
            ),
            (
                "Attest",
                "Coverage and exceptions from the period's evidence.",
                ["report.attest.build → Attestation", "evidence_root = the period's Merkle root"],
                GREEN,
            ),
        ],
    )
    return c


def monitoring() -> Canvas:
    c = Canvas("arch-monitoring", 1250)
    y = c.title(
        "From a metric to an alert somebody keeps switched on",
        "Detectors score; calibration decides what is unusual; a selection procedure "
        "controls false discoveries across the estate; routing decides who hears.",
    )
    pipeline(
        c,
        y + 10,
        [
            (
                "Detect",
                "Each detector emits a nonconformity score, not a verdict.",
                [
                    "monitor.detect: RobustDeviation, QuantileDistance,",
                    "LocalOutlierFactor, ForecastResidual (default_ensemble)",
                ],
                INDIGO,
            ),
            (
                "Calibrate",
                "p = (1 + #{s_i ≥ s}) / (n + 1); uncalibrated below 20 points.",
                ["calibrate.conformal.ConformalCalibrator", "monitor.season.SeasonalModel"],
                REFRACT,
            ),
            (
                "Select",
                "Domain, dataset, attribute, check: false discovery rate held.",
                ["calibrate.select.HierarchicalSelector (BH / BY)"],
                REFRACT,
            ),
            (
                "Keep honest",
                "When calibration drifts, alerts say so.",
                ["calibrate.validity.ValidityMonitor", "monitor.tournament: champion, challenger"],
                TEAL,
            ),
            (
                "Correlate and explain",
                "One incident per cause, with checks to run.",
                ["incident.correlate.Correlator", "incident.rca.RootCause → Hypothesis"],
                AMBER,
            ),
            (
                "Route",
                "Custodian for arrival and schema, steward for values.",
                [
                    "alert.route.Router: immediate, digest, quiet",
                    "unchanged alerts are not re-sent",
                ],
                GREEN,
            ),
        ],
    )
    return c


# --------------------------------------------------------------------------- lineage


def lineage_scan() -> Canvas:
    c = Canvas("arch-lineage-store", 1000)
    y = c.title(
        "Lineage: many readers, one store, every edge says how it is known",
        "Parsers read code and never run it. A model may suggest an edge; it is stored as "
        "inferred until a person confirms it.",
    )
    y = grid(
        c,
        y + 10,
        [
            (
                "SQL",
                "lineage.parsed (sqlglot, ~20 dialects); lineage.sql regex fallback leaves a "
                "regex_fallback gap",
                INDIGO,
            ),
            (
                "Code",
                "lineage.pyspark, pandas_ast, airflow, powerbi; lineage.scan for T-SQL, "
                "PL/SQL, SSIS, PowerCenter",
                INDIGO,
            ),
            (
                "Events and history",
                "lineage.ingest (OpenLineage, dbt manifest); lineage.history "
                "(Snowflake, Databricks, BigQuery exports)",
                REFRACT,
            ),
            (
                "Other catalogues",
                "importers.catalog: Manta and Alation lineage, kept beside Prama's own parse",
                REFRACT,
            ),
        ],
        2,
        "src",
    )
    y += 50
    c.card(
        LEFT,
        y,
        RIGHT - LEFT,
        150,
        "lin_source, lin_run, lin_edge, lin_gap",
        "lineage.store.scan_sql records each run; an edge is parsed (1.0), inferred (0.8, "
        "or a model's ≤ 0.85) or confirmed by a person; gaps are stored, not hidden",
        key="store",
        accent=TEAL,
    )
    for x in (370, 1030):
        c.arrow(x, y - 46, x, y - 6)
    y2 = y + 200
    grid(
        c,
        y2,
        [
            ("Impact", "graph.LineageGraph.blast_radius; prama lineage impact", AMBER),
            ("Change gate", "lineage.change.assess; exit 3 when a control is at risk", AMBER),
            ("Trust", "lineage.trust feeds score.trust", GREEN),
            ("Proposals", "derive.lineage_controls.propose", GREEN),
        ],
        2,
        "use",
    )
    for x in (370, 1030):
        c.arrow(x, y + 152, x, y2 - 6)
    return c


def code_review() -> Canvas:
    c = Canvas("arch-code-review", 1150)
    y = c.title(
        "prama code review: what a pull request does to the controls",
        "Exit 3 when a change removes the basis of a control that is running. No model is "
        "called anywhere on this path.",
    )
    pipeline(
        c,
        y + 10,
        [
            (
                "Two trees",
                "Base and head written out; the working tree is never touched.",
                ["codeintake.review.review", "git archive --format=tar, tarfile filter='data'"],
                INDIGO,
            ),
            (
                "Read each, sandboxed",
                "A separate process with CPU, memory and file limits.",
                ["codeintake.service.run_worker", "python -m prama.codeintake.worker ROOT DIALECT"],
                AMBER,
            ),
            (
                "Diff the lineage",
                "Edges added, removed or retyped, and what they reach.",
                ["codeintake.review.review_trees", "LineageGraph.blast_radius"],
                REFRACT,
            ),
            (
                "Proposals at base and at head",
                "What each version of the code implies.",
                [
                    "derive.lineage_controls.propose(edges, live)",
                    "lost = base - head; implied = head - base",
                ],
                REFRACT,
            ),
            (
                "Broken",
                "A lost proposal whose identity matches a live control.",
                ["Review.fails = bool(broken)", "prama code review … → exit 3"],
                RED,
            ),
        ],
    )
    return c


# --------------------------------------------------------------------------- intelligence


def gateway() -> Canvas:
    c = Canvas("arch-llm-gateway", 1400)
    y = c.title(
        "The model gateway: the only way Prama calls a model",
        "A purpose names an ordered route of provider and model. Every call is checked, "
        "redacted, and recorded as hashes in a chained ledger.",
    )
    pipeline(
        c,
        y + 10,
        [
            (
                "Budget (API surface)",
                "Refused calls are recorded too, as refused_budget.",
                ["llm.budget.admit: lease llm-budget:<tenant>", "BudgetExhausted → HTTP 429"],
                INDIGO,
            ),
            (
                "Route the purpose",
                "A purpose with no profile falls back to MockProvider.",
                ["llm.wiring.gateway_for → load_routes", "llm_profile_version, llm_profile_route"],
                REFRACT,
            ),
            (
                "Try candidates in order",
                "Never falls back to something less local.",
                ["llm.gateway.LlmGateway.run(purpose, request)", "unless fallback_across_hosting"],
                REFRACT,
            ),
            (
                "Policy, then redaction",
                "Sensitivity, residency, then secrets, cards, IBANs.",
                ["ModelProvider.ask: permit → permit_residency", "→ withhold → llm.redact.redact"],
                AMBER,
            ),
            (
                "Provider",
                "Local or remote, by kind.",
                [
                    "llm.kinds.KINDS: openai_compatible, anthropic,",
                    "bedrock, azure_openai, vertex, scripted, mock",
                ],
                TEAL,
            ),
            (
                "Record",
                "Hashes, never text, unless llm.audit.payloads says otherwise.",
                ["CallRecord → uow.llm.append_calls (seal chain)", "prama llm verify"],
                GREEN,
            ),
        ],
    )
    return c


def ai_boundary() -> Canvas:
    c = Canvas("arch-ai-boundary", 700)
    y = c.title(
        "AI never adjudicates: where the line is, and what holds it",
        "Model output is text. It becomes a control only through the same validator and the "
        "same person as anything else, and no verdict code can reach a model.",
    )
    c.card(
        LEFT,
        y + 10,
        400,
        330,
        "May reach prama.llm",
        "assistant (read and propose tools), induce.llm, the stewards, "
        "codeintake.model_lineage, metadata ask, curation drafts. They author, rank, "
        "explain and summarise.",
        key="may",
        accent=AMBER,
    )
    c.card(
        500,
        y + 10,
        400,
        330,
        "induce.validate.Validator",
        "PARSE → TYPE_CHECK → COMPILE → SANDBOX → COUNTERFACTUAL. Validated cannot be "
        "constructed unless every gate passed. Then the proposal queue, origin induction, "
        "and a person.",
        key="val",
        accent=REFRACT,
    )
    c.card(
        940,
        y + 10,
        400,
        330,
        "Must never reach it",
        "prama.backend, prama.execute, prama.evidence, prama.ir: the compiler, the run, the "
        "judge's caller and the ledger. They decide.",
        key="never",
        accent=GREEN,
    )
    c.arrow(462, y + 175, 496, y + 175)
    code_box(
        c,
        LEFT,
        y + 390,
        RIGHT - LEFT,
        150,
        [
            "tests/architecture/test_verdicts_cannot_reach_a_model.py   import graph: no path",
            "tests/architecture/test_layering.py::TestModelVerdicts      no file both calls a "
            "model "
            "and names a verdict",
            "tests/steward/test_stewards.py   a steward never calls approve, sign, activate …",
            "tests/assistant/test_injection.py   no registered tool can mutate",
        ],
        "tests",
        size=17,
    )
    return c


# --------------------------------------------------------------------------- fleet


def fleet_conversation() -> Canvas:
    c = Canvas("arch-fleet-conversation", 1250)
    y = c.title(
        "The fleet conversation: the agent always calls out",
        "Who sends what, over /api/v1/fleet. The server never connects to the agent; work "
        "reaches it when it next asks.",
    )
    lanes = [
        ("Administrator", "client.fleet (SDK)", INDIGO, 210),
        ("Server", "prama.agent.fleet.Fleet", REFRACT, 700),
        ("Agent daemon", "prama_agent", GREEN, 1190),
    ]
    for i, (t, b, a, x) in enumerate(lanes):
        c.card(x - 150, y + 10, 300, 110, t, b, key=f"lane{i}", accent=a, centre=True)
        c.parts.append(
            f'<line x1="{x}" y1="{y + 124}" x2="{x}" y2="{y + 1000}" '
            f'stroke="{RULE}" stroke-width="2" stroke-dasharray="6 6"/>'
        )
    steps = [
        (210, 700, "issue_token(zone) → token, shown once"),
        (1190, 700, "enrol(token) → agent_id and its key"),
        (210, 700, "dispatch(zone, engine): the server compiles"),
        (1190, 700, "Hello, signed with the key"),
        (700, 1190, "Receipt: assignments, claimed (lease)"),
        (1190, 1190, "run read-only, judge with the kernel, redact, spool"),
        (1190, 700, "Report, signed: records and gaps"),
        (700, 1190, "Receipt: accepted_through, duplicates"),
        (210, 700, "revoke(agent_id)"),
        (700, 1190, "next Hello → Refusal(permanent): exit 3"),
    ]
    yy = y + 180
    for i, (a, b, label) in enumerate(steps):
        if a == b:
            c.rect(b - 280, yy - 22, 280, 64, fill=FROST, stroke=RULE, box=f"self{i}")
            c.block(b - 266, yy - 22, 252, label, 16, INK, box=f"self{i}")
        else:
            c.arrow(a, yy + 20, b + (-8 if b > a else 8), yy + 20)
            mid = (a + b) / 2
            c.text(mid, yy + 4, label, 17, INK, anchor="middle")
        yy += 84
    return c


def agent_cycle() -> Canvas:
    c = Canvas("arch-agent-cycle", 1350)
    y = c.title(
        "One daemon cycle beside the data",
        "prama-agent run loops this until stopped; --once loops it until a cycle runs "
        "nothing. Every step that can fail becomes a finding or a gap, never a crash.",
    )
    pipeline(
        c,
        y + 10,
        [
            (
                "Hello",
                "Free slots, pending findings, capabilities derived from config.",
                ["prama_agent.runner.Agent.hello", "daemon.capabilities_for"],
                INDIGO,
            ),
            (
                "Run each assignment",
                "On the source the binding names, opened read-only.",
                ["prama_agent.executors: sqlite mode=ro,", "duckdb read_only, postgres read_only"],
                TEAL,
            ),
            (
                "Judge",
                "With the plan's own threshold, in the shared kernel.",
                ["prama_kernel.judge.judge", "recon.pql.measure, DelegateHost"],
                TEAL,
            ),
            (
                "Redact",
                "Rows stay on the machine under every disposition.",
                [
                    "prama_kernel.agent.residency.Boundary.apply",
                    "withhold | fingerprint | mask | send",
                ],
                AMBER,
            ),
            (
                "Spool",
                "Hash-chained; full means the oldest go, as a numbered gap.",
                [
                    "prama_kernel.agent.spool (spool.json)",
                    "capacity 50,000; written whole, renamed",
                ],
                AMBER,
            ),
            (
                "Report, then wait",
                "Until the spool is empty; then poll_after_seconds.",
                [
                    "Agent.report: 500 findings per batch",
                    "unreachable: jittered exponential backoff",
                ],
                GREEN,
            ),
        ],
    )
    return c


# --------------------------------------------------------------------------- platform


def unit_of_work() -> Canvas:
    c = Canvas("arch-unit-of-work", 1000)
    y = c.title(
        "The database layer: one package, two bases, no migrations",
        "Only prama.db imports SQLAlchemy. Everything else asks a DAO through the unit of "
        "work, and the live schema is checked against two files rather than migrated.",
    )
    c.card(
        LEFT,
        y + 10,
        RIGHT - LEFT,
        130,
        "prama.db.Database",
        "from_config; initialise() applies schema/<dialect>.sql; verify() fails loudly on "
        "drift; unit_of_work(); lease_provider()",
        key="db",
        accent=INDIGO,
    )
    c.card(
        LEFT,
        y + 190,
        RIGHT - LEFT,
        130,
        "prama.db.session.UnitOfWork",
        "async with: one transaction; DAOs are lazy properties built as cls(session, "
        "dialect); db.guard.guarded turns IntegrityError into ConflictError",
        key="uow",
        accent=REFRACT,
    )
    c.arrow(700, y + 142, 700, y + 186)
    y2 = grid(
        c,
        y + 370,
        [
            (
                "Base",
                "platform and semantic tables: tenant, principal, sem_*, ctl_*, lin_*, llm_*, "
                "fl_*, md_*, gl_* …",
                TEAL,
            ),
            (
                "EvidenceBase",
                "ev_run, ev_record, ev_sample, ev_anchor: no foreign key into the "
                "platform, no updated_at",
                GREEN,
            ),
            ("Dialect", "db.dialects: the only module that branches on sqlite or postgres", AMBER),
        ],
        3,
        "b",
    )
    for x in (270, 700, 1130):
        c.arrow(x, y + 322, x, y + 366)
    note(
        c,
        y2 + 40,
        "schema/sqlite.sql and schema/postgres.sql are byte-identical apart from their "
        "headers, and use only VARCHAR(n), TEXT, INTEGER and REAL. A changed table is a "
        "changed CREATE TABLE and a fresh prama db init; there is no ALTER anywhere.",
        "n",
    )
    return c


def config_layers() -> Canvas:
    c = Canvas("arch-config-layers", 900)
    y = c.title(
        "Configuration: five layers, the later one wins",
        "prama.core.config.load_configuration. A secret belongs only in the git-ignored "
        "overlay, and the shipped session secret is empty so a fresh clone refuses to boot.",
    )
    y = pipeline(
        c,
        y + 10,
        [
            ("Defaults", "Every key, with its default.", ["prama.core.config.defaults"], GREY),
            (
                "The tracked file",
                "Reviewable; no secret allowed.",
                ["config/application.yaml"],
                INDIGO,
            ),
            (
                "The local overlay",
                "Git-ignored; where a real secret goes.",
                ["config/application.local.yaml"],
                RED,
            ),
            (
                "The environment",
                "PRAMA_ prefix, __ between levels.",
                ["PRAMA_DATABASE__POOL__SIZE=20"],
                REFRACT,
            ),
            ("The command line", "One invocation only.", ["--set key=value"], TEAL),
        ],
    )
    note(
        c,
        y + 40,
        "${VAR:default} placeholders are resolved, nested ones included; an unresolved one "
        "is an error, not a literal. prama config show prints the merged result with secrets "
        "redacted.",
        "n",
    )
    return c


DIAGRAMS = [
    distributions,
    life,
    request_path,
    alias,
    semantic_model,
    metadata_flow,
    pql_pipeline,
    proposal_lifecycle,
    control_run,
    delegate_sandbox,
    reconciliation,
    evidence_chain,
    scoring,
    monitoring,
    lineage_scan,
    code_review,
    gateway,
    ai_boundary,
    fleet_conversation,
    agent_cycle,
    unit_of_work,
    config_layers,
]
