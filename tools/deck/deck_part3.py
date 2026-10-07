"""
Sections 8 to 10 of the Prama deck and the close: how it runs, three worked examples
from the case studies, and where Prama stands (built, next, a comparison, what it does
not do, where to start).

Every figure is from the code, a test, a case study's run or
``prama bench run --seed 42``; ``{tests}`` is filled from the README's synced count.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""

from __future__ import annotations

from typing import Any

SLIDES: list[dict[str, Any]] = [
    {
        "kind": "divider",
        "num": "8",
        "title": "How it runs",
        "sub": "One application, one database, and agents beside data that must not move.",
        "points": [
            "Deploy anywhere",
            "Built and tested",
            "One schema, two engines, no migrations",
            "Agents, and what may leave the machine",
            "Security and tenancy",
        ],
    },
    {
        "kind": "cards",
        "kicker": "Deployment",
        "title": "Deploy anywhere the data's owner allows",
        "cols": 4,
        "cards": [
            (
                "",
                "A laptop or a VM",
                "One process, SQLite, `prama serve`: the console and the API on one port.",
            ),
            (
                "",
                "Containers",
                "The Dockerfile and Helm chart in deploy/, with PostgreSQL, probes and metrics.",
            ),
            (
                "",
                "Beside the data",
                "The prama-agent daemon runs checks where data must not move; it always calls out.",
            ),
            (
                "",
                "Offline",
                "Bundles sealed and verified before install; an end-to-end air-gapped "
                "install is not yet verified.",
            ),
        ],
        "note": "The same configuration file everywhere: application.yaml, with secrets "
        "only in the git-ignored local overlay or the environment.",
    },
    {
        "kind": "stats",
        "kicker": "Built and tested",
        "title": "Measured, not claimed",
        "stats": [
            ("{tests}", "tests passing in the suite, synced from a green run"),
            ("3", "engines run the same plans to the same verdicts"),
            ("47", "console pages, each with “About this page”"),
            ("8", "case studies, planted against found"),
        ],
        "items": [
            "Four separately built packages: the server, a standard-library "
            "kernel, a Python SDK, and the agent daemon.",
            "Python 3.12, 3.13 and 3.14 each run the whole suite; an accessibility "
            "audit and a phone-width check run every page in a real browser.",
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
        "intro": "An agent runs beside the data so the data does not travel. What "
        "crosses the boundary is declared, enforced at the agent, and recorded.",
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
        "note": "Agents take work under leases, spool when the centre is unreachable, "
        "and run the delegates their configuration admits (case study 5).",
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
            (
                "",
                "Sign-in",
                "Passwords hashed beside their column; OIDC tokens verified, console SSO to come.",
            ),
            ("", "API keys", "Shown once; a key cannot exceed its holder's rights."),
            ("", "Secrets", "Never in tracked config; a fresh clone refuses to boot."),
            ("", "Egress", "Every outbound call is declared, and a test checks the list."),
        ],
    },
    {
        "kind": "divider",
        "num": "9",
        "title": "Worked examples",
        "sub": "Three questions somebody actually asks, answered end to end by the case studies.",
        "points": [
            "Month-end close",
            "From code to impact",
            "Fit for a purpose",
            "Eight studies, planted against found",
            "Bounds, ablations, and Prama itself",
        ],
    },
    {
        "kind": "workflow",
        "kicker": "Case study 6 · month-end close",
        "title": "Workflow: the subledger against the general ledger",
        "question": "Does the subledger agree with the general ledger at month end, and "
        "which breaks need a person?",
        "steps": [
            (
                "Declare",
                "RECONCILE subledger AGAINST general_ledger … OFFSET BY 1 DAY, one "
                "statement, approved like any control.",
            ),
            (
                "Normalise",
                "Three currencies converted to EUR at the treasury's closing rates, "
                "read as a dataset.",
            ),
            (
                "Match",
                "Rows matched on account, cost centre and posting date; totals "
                "compared where a key repeats.",
            ),
            (
                "Classify",
                "Each break genuine, missing or extra; the timing allowance removes "
                "the late entries.",
            ),
            (
                "Work the queue",
                "5 breaks need a person, exactly the planted ones: assign, note, or "
                "accept with a reason.",
            ),
        ],
        "note": "Without OFFSET BY 1 DAY the same run reports 9 breaks: the allowance "
        "removes noise, and nothing real.",
    },
    {
        "kind": "workflow",
        "kicker": "Case study 8 · from code to impact",
        "title": "Workflow: a defect's blast radius",
        "question": "If raw.trades.notional is wrong, which numbers on the risk "
        "committee's dashboard are wrong too?",
        "steps": [
            (
                "Read the code",
                "Two SQL scripts and a Power BI model give 14 parsed column edges; "
                "nothing is executed.",
            ),
            (
                "Follow the edges",
                "Staging, then the mart, then the dashboard's Exposure column and its "
                "Total Exposure measure.",
            ),
            (
                "Attenuate",
                "100% of the defect in the copy, 35% once summed with FX rates, 12% "
                "in the measure.",
            ),
            (
                "Find the hidden one",
                "Lower-case 'usd' fails an inner join: 605,000,000 of notional leaves "
                "the mart, with no error.",
            ),
            (
                "Propose the check",
                "Every stg.trades.ccy must exist in ref.fx_rates: it fails on 3 of "
                "1,882, where the defect happens.",
            ),
        ],
        "note": "Value lineage cannot see a join dropping rows: the currency is never "
        "copied. Join keys are edges into the view's rows, so the blast radius "
        "follows them.",
    },
    {
        "kind": "workflow",
        "kicker": "Case study 7 · governance from metadata",
        "title": "Workflow: fit for a purpose, with no rule written",
        "question": "Which dataset should we use for sanctions screening, and is it fit "
        "for that purpose?",
        "steps": [
            (
                "Describe",
                "Owners fill in metadata and business context for three datasets; "
                "nobody writes a rule.",
            ),
            (
                "Propose",
                "Fields such as mandatory, unique and allowed values propose checks, "
                "each quoting its field.",
            ),
            (
                "Correlate",
                "customers.lei and accounts.customer_lei share the term LEI: a "
                "referential check is proposed.",
            ),
            (
                "Find",
                "The question returns Customers, matching legal_name, customer_id and "
                "lei, and says which ranking it used.",
            ),
            (
                "Prove",
                "All four planted defects are found by checks that came from metadata "
                "or correlation.",
            ),
        ],
        "note": "The better owners describe their data, the better this works: the "
        "incentive points the right way.",
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
        "note": "Each study writes to the application's own database under a fresh "
        "tenant, and runs in the test suite. The console shows each one under "
        "Help → Case studies.",
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
        "note": "Configuring a competitor is a job for someone incentivised to make it "
        "look good. A detector's blind spots do not appear in an aggregate F1 at "
        "all.",
    },
    {
        "kind": "divider",
        "num": "10",
        "title": "Where Prama stands",
        "sub": "What is built, what comes next, how it compares, and what it does not do.",
        "points": [
            "Built",
            "Coming next",
            "Competitive analysis",
            "What Prama does not do",
            "Where to start",
        ],
    },
    {
        "kind": "cards",
        "kicker": "Built",
        "title": "Built: the whole loop, end to end",
        "cols": 4,
        "cards": [
            ("", "Semantic layer", "Declarations, metadata, glossary, coverage, proposals."),
            (
                "",
                "PQL on three engines",
                "Parsed, type-checked, compiled, fused; conformance tested.",
            ),
            ("", "Evidence ledger", "Hash-chained, anchored, verified offline by a stdlib script."),
            (
                "",
                "Reconciliation",
                "RECONCILE, FX normalisation, timing offsets, the break workbench.",
            ),
            (
                "",
                "Lineage from code",
                "SQL, procedures, Python jobs, Power BI; impact and change review.",
            ),
            (
                "",
                "AI under control",
                "One gateway, budgets on every call, stewards that only propose.",
            ),
            (
                "",
                "Agents beside data",
                "Enrolled, signed, spooling daemon; only facts about data travel.",
            ),
            ("", "Four ways in", "Console, REST API, CLI and Python SDK over one ledger."),
        ],
    },
    {
        "kind": "numbered",
        "kicker": "Coming next",
        "title": "Coming next: the gaps, listed",
        "cols": 2,
        "items": [
            ("Reference customers", "Design partners on named, referenceable terms."),
            (
                "Legacy-ETL scanners, verified",
                "SQL dialects are verified; SSIS, PowerCenter and DataStage shapes "
                "are only configurable.",
            ),
            (
                "Certified connectors",
                "ODBC is not built; Snowflake and several JDBC dialects are written "
                "but unverified.",
            ),
            (
                "Console single sign-on",
                "OIDC tokens are verified; no console sign-in flow uses them yet.",
            ),
            (
                "Air-gapped install, end to end",
                "With a local model and no egress, verified, not argued.",
            ),
            (
                "A published benchmark",
                "Against named competitors, configured by people with a reason to "
                "make them look good.",
            ),
        ],
        "note": "docs/corpus/remaining-work.md is the full list, ordered by what each "
        "item blocks; the implementation roadmap stays the authority.",
    },
    {
        "kind": "compare",
        "kicker": "Competitive analysis",
        "title": "Prama against the categories it meets",
        "rows": [
            ["Capability", "Prama", "Catalogs", "Observability", "Lineage tools", "Reconciliation"],
            ["Business meaning declared by owners", "Yes", "Yes", "No", "Partly", "No"],
            ["Declarations compile into controls", "Yes", "No", "No", "No", "No"],
            ["Rules portable across engines", "Yes", "No", "No", "No", "No"],
            ["Calibrated alerts, stated false-alarm rate", "Yes", "No", "No", "No", "No"],
            ["Statistical monitoring maturity", "Partly", "Partly", "Yes", "No", "Partly"],
            ["Cross-system reconciliation", "Yes", "No", "No", "No", "Yes"],
            ["Evidence verifiable offline", "Yes", "Partly", "No", "Partly", "Partly"],
            ["Lineage from legacy ETL", "Partly", "Partly", "Partly", "Yes", "No"],
            ["Catalog search and curation", "No, by choice", "Yes", "Partly", "Partly", "No"],
            ["Tier-1 bank reference customers", "No", "Yes", "Yes", "Yes", "Yes"],
        ],
        "col_w": [2.3, 1.0, 1.0, 1.1, 1.1, 1.1],
        "note": "Derived from the capability matrix in docs/corpus/20, which names the "
        "vendors in each category and says where each is genuinely better than "
        "Prama today.",
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
                "It supplies evidence; `prama pack claims` lists what the banking "
                "pack does not claim.",
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
        "research paper in docs/publications/paper/ has the formal argument and "
        "its proofs.",
    },
    {
        "kind": "thanks",
        "title": "Thank you",
        "sub": "Declare it. Prove it. Trust it.",
        "lines": [
            "Ashutosh Sinha",
            "ajsinha@gmail.com",
            "The documentation: docs/README.md, and Help in the console",
        ],
    },
]
