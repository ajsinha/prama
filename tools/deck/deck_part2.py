"""
Parts 4 to 6 of the Prama deck: evidence and reconciliation, lineage and impact, and
trust that is calibrated and derived.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""

from __future__ import annotations

from typing import Any

SLIDES: list[dict[str, Any]] = [
    # ------------------------------------------------------------------ part 4
    {
        "kind": "divider",
        "num": "4",
        "title": "Prove it",
        "sub": "A verdict is worth what its record is worth. The record must survive without "
        "the system that wrote it.",
        "points": [
            "What one piece of evidence holds",
            "A chain, a root, and an offline check",
            "Reconciliation, and the break workbench",
            "A timing allowance that removes only noise",
        ],
    },
    {
        "kind": "table",
        "kicker": "Evidence",
        "title": "What one record of a run holds",
        "rows": [
            ["Field", "Why it is there"],
            ["The plan's identity, the control and its version", "Which rule ran, exactly"],
            ["The engine, binding and parameters", "Where it ran, and against what"],
            ["Metrics: scanned and violating rows", "The measurement, before any judgement"],
            ["Verdict, dimensions and criticality", "The judgement, and what it weighs"],
            ["A digest of the sampled rows", "What was shown, without keeping the rows"],
            ["Previous, content and record hashes", "Append-only: an edit breaks the chain"],
        ],
        "col_w": [1.6, 2.2],
        "note": "Evidence has its own store (EvidenceBase), its own retention and its own "
        "immutability, separate from the platform schema.",
    },
    {
        "kind": "flow",
        "kicker": "Verification",
        "title": "Checked without trusting Prama",
        "steps": [
            ("Hash chain", "Each record commits to the one before it."),
            ("Merkle root", "One digest summarises a whole run's evidence."),
            ("Sealed bundle", "Manifest and SBOM, HMAC-sealed; optionally Ed25519-signed."),
            ("Offline verifier", "A standalone script re-derives all of it, importing nothing."),
        ],
        "items": [
            "python3 scripts/verify_evidence.py bundle/ runs on an auditor's machine with "
            "only the standard library. It does not import Prama.",
            "prama bundle verify exits 3 when a bundle must not be installed: a failure an "
            "automated pipeline cannot mistake for success.",
            "Every case study ends by printing its evidence chain as verified, with the "
            "Merkle root.",
        ],
    },
    {
        "kind": "table",
        "kicker": "Reconciliation",
        "title": "RECONCILE says the whole agreement in one statement",
        "rows": [
            ["Clause", "Meaning"],
            ["ON (account, cost_centre, posting_date)", "How rows match; many can sum into one"],
            ["COMPARING amount = balance_eur", "Columns may have different names on each side"],
            ["WITHIN 0.01 EUR OR 0.1%", "Materiality; a break needs both bounds breached"],
            ["NORMALISING currency TO 'EUR' USING RATES fx", "Rates are a dataset, like any other"],
            ["OFFSET BY 1 DAY", "The ledger catching up overnight is not a break"],
        ],
        "col_w": [1.8, 2.0],
        "note": "Breaks are classified as genuine, missing or extra, and each lands in the break "
        "workbench with an owner: explain it, accept it, or fix it.",
    },
    {
        "kind": "stats",
        "kicker": "Case study 6 · month-end close",
        "title": "The subledger against the general ledger",
        "stats": [
            ("5", "breaks needing a person: exactly the planted ones"),
            ("9", "breaks reported without OFFSET BY 1 DAY"),
            ("3", "currencies normalised to EUR with the treasury's closing rates"),
            ("23", "false breaks in the first build: a rounding convention, found and documented"),
        ],
        "items": [
            "Planted: three manual journals, one day that never reached the ledger, one "
            "ledger-only account, and two late entries that must not fail the close.",
            "The counterfactual is part of the study: each late entry without the offset "
            "becomes one missing and one extra. The allowance removes noise and nothing real.",
            "The ledger converts each day's total and rounds once; converting each entry "
            "differs by cents. A real difference between systems, stated, not assumed away.",
        ],
    },
    # ------------------------------------------------------------------ part 5
    {
        "kind": "divider",
        "num": "5",
        "title": "Lineage and impact",
        "sub": "Read from the code that moves the data, never drawn by hand, and never executed.",
        "points": [
            "What code intake reads",
            "Parsed and inferred, kept apart",
            "The blast radius of a defect",
            "Controls carried downstream",
            "What column lineage cannot see",
        ],
    },
    {
        "kind": "table",
        "kicker": "Code intake",
        "title": "What Prama reads to find lineage",
        "rows": [
            ["Source", "How it is read", "Edge status"],
            ["SQL scripts and views", "Parsed with sqlglot, dialect-aware", "parsed"],
            ["T-SQL, PL/SQL and DB2 procedures", "Procedure readers", "parsed"],
            ["PySpark, pandas, Airflow SQL", "Python syntax tree, never run", "parsed"],
            ["Power BI models (.bim)", "Tables, Power Query, measures", "parsed"],
            ["Anything the readers cannot read", "Pattern fallback, or a model", "inferred"],
            ["Manta, Alation exports", "Imported beside Prama's own parse", "as stated"],
        ],
        "col_w": [1.4, 1.6, 0.8],
        "note": "A ZIP or a repository is extracted into quarantine, parsed in a separate "
        "process, and deleted. A test plants code that writes a marker file if executed.",
    },
    {
        "kind": "bullets",
        "kicker": "Impact",
        "title": "Where a defect goes, and how much of it arrives",
        "intro": "The blast radius follows edges downstream and attenuates by transform: a "
        "copy carries the whole defect, an aggregation dilutes it.",
        "items": [
            ("raw.trades.notional_amt → stg.trades.notional", "100% of the defect, 1 hop"),
            ("→ mart.positions.exposure_usd", "35%, 2 hops: summed with FX rates"),
            ("→ the Risk Dashboard's Exposure column", "35%, 3 hops: a rename"),
            ("→ its Total Exposure measure", "12%, 4 hops: aggregated again"),
        ],
        "note": "Case study 8: two SQL scripts and a Power BI model give 12 parsed column "
        "edges; the defect is traced from the raw feed to the measure a risk committee reads.",
    },
    {
        "kind": "table",
        "kicker": "Lineage-derived proposals",
        "title": "A control on a column is owed by every faithful copy",
        "rows": [
            ["Rule", "Proposed", "Held when"],
            ["Propagated", "The source column's control, on the copy", "The edge is inferred"],
            ["Referential", "Each copied key must exist at its source", "The edge is inferred"],
            [
                "Reconcile",
                "The copy agrees with its source, exactly (WITHIN 0)",
                "Inferred, or the copy is filtered",
            ],
        ],
        "col_w": [0.9, 2.1, 1.3],
        "note": "Case study 8 found both defects this slide depends on: a proposed RECONCILE "
        "with no tolerance could not run, and a filtered copy reported 118 cancelled trades "
        "as breaks. Both are fixed, each with a test that fails on the old code.",
    },
    {
        "kind": "split",
        "kicker": "An honest limit",
        "title": "What column lineage cannot see",
        "left": {
            "head": "The defect",
            "items": [
                "Four trades with currency 'usd' in lower case",
                "Three are staged; the mart joins FX rates on currency",
                "Those trades have no rate, and silently leave the mart",
            ],
        },
        "right": {
            "head": "What each part of Prama sees",
            "items": [
                "The raw column's control: 4 of 2,000 rows",
                "The propagated control on staging: 3 of 1,882",
                "The blast radius: stops at staging, since a join key is not a value",
                "The mart: no error, no null; 605,000,000 of notional simply gone",
            ],
        },
        "note": "Lineage carries a control downstream; it does not replace the control at "
        "the source. That is the design, and case study 8 is its evidence.",
    },
    # ------------------------------------------------------------------ part 6
    {
        "kind": "divider",
        "num": "6",
        "title": "Trust it",
        "sub": "An alert level that means what it says, and a score derived from evidence "
        "rather than asserted beside it.",
        "points": [
            "Conformal alerting",
            "Scores derived from evidence",
            "Trust along lineage",
            "Usage: a priority, never a score",
        ],
    },
    {
        "kind": "bullets",
        "kicker": "Monitoring",
        "title": "An alert level that means what it says",
        "items": [
            (
                "Conformal p-values",
                "p = (1 + #{sᵢ ≥ s}) / (n + 1). Under exchangeability a normal point "
                "alerts at level \u03b1 with probability at most \u03b1, in finite samples, "
                "with no distributional assumption.",
            ),
            (
                "The +1 is the guarantee",
                "Drop it and a point beyond everything seen gets p = 0: the false-alarm rate "
                "becomes 1/n, not \u03b1.",
            ),
            (
                "Drift, said out loud",
                "Weighted and adaptive variants trade exactness for robustness, and say by "
                "how much.",
            ),
            (
                "Cold start, labelled",
                "Before there is history, a monitor starts from priors (semantic type, "
                "declared rhythm, sibling datasets) and says so on every verdict; it switches "
                "to calibration when history allows, and announces that too.",
            ),
        ],
    },
    {
        "kind": "split",
        "kicker": "Scores",
        "title": "Derived from evidence, propagated along lineage",
        "left": {
            "head": "A dataset's score",
            "items": [
                "Computed from its latest evidence, by dimension",
                "Weighted by criticality and CDEs, never typed in",
                "An error or an indeterminate verdict is not a pass",
            ],
        },
        "right": {
            "head": "Trust along lineage",
            "items": [
                "A consumer's trust reflects its ancestry, not only its own tests",
                "Propagated along paths by a stated combination rule",
                "Ranked by trust, a report shows its weakest input",
            ],
        },
        "note": "Usage signals (from query history) rank what to control next: most used, "
        "least controlled. They are never an input to a score, since popularity is not "
        "correctness.",
    },
]
