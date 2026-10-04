"""
Parts 7 to 9 of the Prama deck: AI that authors but never adjudicates, how Prama runs, and
the case studies, the benchmark, and what Prama does not do.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""

from __future__ import annotations

from typing import Any

SLIDES: list[dict[str, Any]] = [
    # ------------------------------------------------------------------ part 7
    {
        "kind": "divider",
        "num": "7",
        "title": "AI that never adjudicates",
        "sub": "Models author, rank, explain and summarise. A deterministic, versioned engine "
        "decides.",
        "points": [
            "The line, and the test that holds it",
            "One gateway for every model call",
            "Finding the dataset fit for a purpose",
        ],
    },
    {
        "kind": "split",
        "kicker": "The line",
        "title": "What a model may do, and what it may not",
        "left": {
            "head": "A model may",
            "items": [
                "Author a proposed control from a document or an example",
                "Suggest lineage for code no reader could parse, marked inferred",
                "Rank datasets for a purpose, and explain the ranking",
                "Summarise an incident, or explain a failure in plain words",
            ],
        },
        "right": {
            "head": "A model may not",
            "items": [
                "Pass or fail data, directly or through any code path",
                "Activate a control: that is a person's approval",
                "Turn an inferred lineage edge into a parsed one",
                "Change a score",
            ],
        },
        "note": "tests/architecture/test_layering.py fails the build if model output can reach "
        "a verdict (CON-007, NFR-AI-002). A guard wired into no test is a guard somebody forgets.",
    },
    {
        "kind": "table",
        "kicker": "The gateway",
        "title": "One gateway for every model call",
        "rows": [
            ["Property", "What it means"],
            ["Purposes", "author, explain, summarise, lineage, curate, discover, embed"],
            ["Routes", "Each purpose has an ordered route of provider and model"],
            ["Providers", "OpenAI-compatible (Ollama, vLLM), Anthropic, Bedrock, Azure, Vertex"],
            ["Default", "A mock provider: with nothing configured, Prama works and says so"],
            ["Call ledger", "Every call recorded and hash-chained; prama llm verify checks it"],
            ["Evaluation gate", "A route activates only after its evaluation suite passes"],
            ["Redaction", "Secrets, card numbers, IBANs and emails withheld, both ways"],
        ],
        "col_w": [1.0, 3.2],
    },
    {
        "kind": "flow",
        "kicker": "Fitness for purpose",
        "title": "Which dataset should I use for this?",
        "steps": [
            ("Profile", "Each dataset's name, description, business context, metadata, terms."),
            ("Rank", "Embeddings when a model is configured; BM25 relevance when not."),
            ("Evidence", "The attributes whose own text best matches, so the reader sees why."),
        ],
        "items": [
            "The answer always says which ranking was used. Nothing here reads the data, and "
            "nothing here touches a score.",
            "Case study 7: “who is the customer and where are they registered, for "
            "sanctions screening” returns Customers, matching legal_name, customer_id "
            "and lei.",
            "The better owners describe their data, the better this works: the incentive "
            "points the right way.",
        ],
    },
    # ------------------------------------------------------------------ part 8
    {
        "kind": "divider",
        "num": "8",
        "title": "How it runs",
        "sub": "One application, one database, and agents beside data that must not move.",
        "points": [
            "The system in context",
            "One schema, two engines, no migrations",
            "Agents, and what may leave the machine",
            "Security and tenancy",
        ],
    },
    {
        "kind": "context",
        "kicker": "Architecture",
        "title": "The system in context",
        "nodes": [
            {
                "id": "people",
                "x": 0.0,
                "y": 0.0,
                "w": 0.26,
                "h": 0.36,
                "head": "Owners, stewards, auditors",
                "body": "Console, CLI, API, editor (LSP), assistants (MCP)",
            },
            {
                "id": "core",
                "x": 0.37,
                "y": 0.0,
                "w": 0.26,
                "h": 0.36,
                "head": "Prama",
                "body": "Semantic layer, PQL, derivation, proposals, scoring",
            },
            {
                "id": "llm",
                "x": 0.74,
                "y": 0.0,
                "w": 0.26,
                "h": 0.36,
                "head": "LLM gateway",
                "body": "Purposes, routes, call ledger; mock by default",
            },
            {
                "id": "db",
                "x": 0.0,
                "y": 0.60,
                "w": 0.26,
                "h": 0.40,
                "head": "Application database",
                "body": "SQLite or PostgreSQL; evidence in its own store",
            },
            {
                "id": "exec",
                "x": 0.37,
                "y": 0.60,
                "w": 0.26,
                "h": 0.40,
                "head": "Execution",
                "body": "Compiled SQL pushed down; fused scans; delegates out of process",
            },
            {
                "id": "agent",
                "x": 0.74,
                "y": 0.60,
                "w": 0.26,
                "h": 0.40,
                "head": "Remote agents",
                "body": "Beside the data; only counts, verdicts and hashes return",
            },
        ],
        "edges": [
            ("people", "core", ""),
            ("core", "llm", ""),
            ("core", "exec", ""),
            ("exec", "db", ""),
            ("exec", "agent", ""),
        ],
    },
    {
        "kind": "split",
        "kicker": "Storage",
        "title": "One schema, two engines, no migrations",
        "left": {
            "head": "The rule",
            "items": [
                "schema/sqlite.sql and schema/postgres.sql are the authority",
                "Byte-identical apart from their headers; a test fails if not",
                "Four column types only: VARCHAR(n), TEXT, INTEGER, REAL",
                "A table changes by editing its CREATE TABLE, never with ALTER",
            ],
        },
        "right": {
            "head": "What follows",
            "items": [
                "prama db init applies the schema idempotently",
                "prama db verify fails loudly on drift; nothing is repaired silently",
                "Identifiers are ULIDs minted client-side: a retry reuses one",
                "Only prama/db imports SQLAlchemy; everything else uses DAOs",
            ],
        },
    },
    {
        "kind": "table",
        "kicker": "Distributed execution",
        "title": "Agents, and what may leave the machine",
        "intro": "An agent runs beside the data so the data does not travel. What crosses the "
        "boundary is declared, enforced at the agent, and recorded.",
        "rows": [
            ["Tier", "What", "Rule"],
            [
                "Always crosses",
                "Counts, verdicts, plan identities, hashes, timings",
                "Facts about data",
            ],
            ["By declaration", "Samples of failing rows", "Only under a stated policy"],
            ["Never crosses", "The data itself", "Not configurable"],
        ],
        "col_w": [1.0, 2.0, 1.2],
        "note": "Agents take work under leases, spool when the centre is unreachable, and run "
        "the delegates their configuration admits (case study 5).",
    },
    {
        "kind": "cards",
        "kicker": "Security",
        "title": "Security and tenancy",
        "cols": 3,
        "cards": [
            ("", "Tenants", "Every row carries its tenant; one database serves many estates."),
            (
                "",
                "Roles and scopes",
                "Mutating routes need write scopes; a test checks every route.",
            ),
            ("", "Sign-in", "Passwords hashed beside their column; OIDC single sign-on."),
            ("", "API keys", "Shown once; a key cannot exceed its holder's rights."),
            ("", "Secrets", "Never in tracked config; a fresh clone refuses to boot."),
            ("", "Egress", "Every outbound call is declared, and a test checks the list."),
        ],
    },
    # ------------------------------------------------------------------ part 9
    {
        "kind": "divider",
        "num": "9",
        "title": "The evidence",
        "sub": "Eight case studies, a labelled benchmark, and what Prama does not do.",
        "points": [
            "Eight case studies, planted against found",
            "Bounds, ablations, and Prama itself",
            "What Prama does not do",
            "Where to start",
        ],
    },
    {
        "kind": "table",
        "kicker": "Case studies",
        "title": "Eight studies, each planted against found",
        "rows": [
            ["#", "Study", "Result"],
            ["1", "Trading book in SQLite", "The whole loop on one source"],
            [
                "2",
                "Feeds: CSV, Parquet, JSON Lines",
                "9 negative amounts, 5 unknown statuses found",
            ],
            ["3", "A mixed estate", "Defects no single dataset can see"],
            ["4", "Expressions and plugins", "Excel formulas; a third-party validator"],
            ["5", "DQ delegates", "Python checks, local and on a remote agent"],
            ["6", "Month-end close", "5 breaks; 9 without the timing offset"],
            ["7", "Governance from metadata", "4 of 4 found, with no rule written by hand"],
            ["8", "From code to impact", "Both defects traced; the FX join catches 3"],
        ],
        "col_w": [0.3, 1.9, 2.6],
        "note": "Each study writes to the application's own database under a fresh tenant, "
        "and runs in the test suite. The console shows each one under Help → Case studies.",
    },
    {
        "kind": "stats",
        "kicker": "prama bench run --seed 42",
        "title": "Bounds, ablations, and Prama itself",
        "stats": [
            ("28", "scenarios of 200 rows, one defect each"),
            ("6", "defect families, from structural to semantic"),
            ("0.49", "F1 of Prama's declared path; 0.39 for the best single technique"),
            ("15", "named competitors not run, and said so"),
        ],
        "rows": [
            ["Baseline", "Found", "Precision", "Recall", "Blind to"],
            ["alert-on-everything (bound)", "28/28", "0.08", "1.00", "nothing"],
            ["schema-only", "2/28", "0.67", "0.07", "five of six families"],
            ["patterns-only", "5/28", "0.83", "0.18", "four families"],
            ["statistics-only", "7/28", "0.88", "0.25", "relational"],
            ["prama-declared (system)", "10/28", "0.77", "0.36", "relational, temporal, semantic"],
        ],
        "col_w": [1.8, 0.6, 0.7, 0.6, 1.3],
        "note": "Configuring a competitor is a job for someone incentivised to make it look "
        "good. A detector's blind spots do not appear in an aggregate F1 at all.",
    },
    {
        "kind": "bullets",
        "kicker": "Scope",
        "title": "What Prama does not do",
        "items": [
            (
                "It does not decide what is true",
                "It establishes whether what you declared holds, and proves it did.",
            ),
            (
                "It does not repair data",
                "A defect is fixed at its source by its owner; Prama records that it was.",
            ),
            (
                "It does not let a model judge",
                "Not as a fallback, not with a confidence threshold, not at all.",
            ),
            (
                "It does not read mainframe code",
                "Lineage covers SQL, procedures, Python jobs, Airflow and Power BI; "
                "not COBOL or JCL.",
            ),
            (
                "It does not discharge a regulation",
                "It supplies evidence; `prama pack claims` lists what the banking pack "
                "does not claim.",
            ),
        ],
    },
    {
        "kind": "table",
        "kicker": "Where to start",
        "title": "An afternoon, in six commands",
        "rows": [
            ["Command", "What it does"],
            ["prama db init", "Applies the schema to the configured database"],
            ["prama tenant create acme-bank", "Creates the estate"],
            ["prama principal create alice --admin", "Somebody who can sign in"],
            ["prama serve", "The console and the API, on one port"],
            ["python case-studies/01-trading-book-sqlite/run.py", "Real evidence in the console"],
            ["prama control explain suite.pql", "Each control as a sentence an owner reads"],
        ],
        "col_w": [2.2, 2.0],
        "note": "QUICKSTART.md has the full path, including what each refusal means. The "
        "research paper in docs/publications/paper/ has the formal argument and its proofs.",
    },
]
