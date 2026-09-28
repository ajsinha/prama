"""
Parts 1 to 3 of the Prama deck: why data quality fails, declaring what data means, and the
language controls are written in.

Every figure is from the code, a test, a case study's run or ``prama bench run --seed 42``.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""

from __future__ import annotations

from typing import Any

SLIDES: list[dict[str, Any]] = [
    # ------------------------------------------------------------------ part 1
    {
        "kind": "divider",
        "num": "1",
        "title": "Why data quality fails",
        "sub": "The dashboard is green and the number is wrong. Nobody lied; nothing was proved.",
        "points": [
            "The question every number must answer",
            "Four ways a data quality programme fails",
            "What a supervisor actually asks for",
            "Prama in one slide",
        ],
    },
    {
        "kind": "bullets",
        "kicker": "The question",
        "title": "Can you prove this number is right?",
        "intro": "Every reported figure (a capital ratio, an exposure, a settled balance) "
        "eventually meets somebody who asks how you know. Most estates can answer only "
        "with a feeling.",
        "items": [
            (
                "“The checks passed”",
                "Which checks, written by whom, against what declared meaning, on which rows, "
                "and where is the record?",
            ),
            (
                "“The dashboard is green”",
                "Green is the absence of a failure somebody thought to look for. It is not the "
                "presence of a proof.",
            ),
            (
                "“The vendor tool said so”",
                "A verdict you cannot recompute without trusting the tool that issued it is an "
                "assertion, not evidence.",
            ),
        ],
        "note": "pramā (Sanskrit): knowledge that is both true and arrived at by a "
        "reliable means. The product is named for the second half.",
    },
    {
        "kind": "cards",
        "kicker": "Diagnosis",
        "title": "Four ways a data quality programme fails",
        "cols": 2,
        "cards": [
            (
                "01",
                "Rules restated, then drifting",
                "The meaning of a column lives in a wiki; the check lives in a YAML file; the "
                "two are edited by different people and diverge, always in the flattering "
                "direction.",
            ),
            (
                "02",
                "Thresholds that mean nothing",
                "A sensitivity dial of “high” is not a false-alarm rate. Stewards learn to "
                "ignore the alerts, and then miss the one that mattered.",
            ),
            (
                "03",
                "Verdicts without evidence",
                "Results overwritten each run, no record of the rule's version or the data it "
                "saw, nothing an auditor can re-verify offline.",
            ),
            (
                "04",
                "A model deciding pass or fail",
                "An LLM that says “this looks fine” is persuasive and unrepeatable. In a "
                "control, persuasion is the defect.",
            ),
        ],
    },
    {
        "kind": "table",
        "kicker": "What is expected",
        "title": "What a supervisor asks for, and what it takes",
        "rows": [
            ["The expectation", "What it takes in practice", "Where Prama does it"],
            [
                "Accuracy and integrity (BCBS 239, principle 3)",
                "Controls tied to declared meaning, reconciled to source",
                "Semantic layer, derived controls, RECONCILE",
            ],
            [
                "Completeness (principle 4)",
                "Coverage measured against what is critical, not counted",
                "Coverage analysis names the uncovered remainder",
            ],
            [
                "Timeliness (principle 5)",
                "Arrival declared and checked, with calendars",
                "Rhythm on the dataset; business calendars in the banking pack",
            ],
            [
                "Documented, validated, auditable",
                "A record that can be checked without the system",
                "Hash-chained evidence, Merkle root, offline verifier",
            ],
            [
                "Human accountability",
                "A named owner approves each rule; no model decides",
                "Proposals, approval, the no-model-verdict guard",
            ],
        ],
        "col_w": [1.3, 1.5, 1.5],
        "note": "Prama is not legal or regulatory advice, and discharges no obligation by "
        "itself: `prama pack claims` lists what the banking pack does not claim.",
    },
    {
        "kind": "flow",
        "kicker": "Prama in one slide",
        "title": "Declare it. Prove it. Trust it.",
        "steps": [
            (
                "Declare it",
                "Owners say what a dataset means: its grain, domains, relationships, "
                "business context. Controls are derived from that, not restated.",
            ),
            (
                "Prove it",
                "A deterministic engine runs each control where the data lives and writes a "
                "hash-chained, independently verifiable record.",
            ),
            (
                "Trust it",
                "Calibrated alerts, scores derived from evidence, trust propagated along "
                "lineage, and every defect traced to what it reaches.",
            ),
        ],
        "items": [
            "Models author, rank, explain and summarise. A versioned engine decides. "
            "An architecture test fails the build if a model's output can reach a verdict.",
            "One application database, two schema files as the authority, no migrations; "
            "remote agents run checks beside data that must not move.",
        ],
        "box_h": 2.0,
    },
    # ------------------------------------------------------------------ part 2
    {
        "kind": "divider",
        "num": "2",
        "title": "Declare it",
        "sub": "The business semantic layer: say once what data means, and let the controls "
        "follow from it.",
        "points": [
            "Datasets, grain and attributes",
            "Controls derived from declarations",
            "Coverage, and the remainder named",
            "Metadata, glossary and business context",
            "Proposals: the only way anything changes",
        ],
    },
    {
        "kind": "table",
        "kicker": "The vocabulary",
        "title": "What an owner declares",
        "intro": "Every term below is something the owner already knows. None of it is a "
        "quality rule, and all of it implies some.",
        "rows": [
            ["Declared", "Example", "What it implies"],
            ["Grain", "one row per trade (trade_id)", "Uniqueness and duplication controls"],
            ["Value domain", "currency in ISO 4217; notional ≥ 0", "Validity controls"],
            ["Mandatory, CDE", "account_id is critical", "Completeness; weight in the score"],
            ["Relationship", "trades.account_id → accounts", "Referential integrity"],
            ["Equivalence", "positions agree with the ledger", "A reconciliation"],
            ["Rhythm", "daily, by 06:30 on TARGET2 days", "Arrival and freshness"],
            ["Business context", "“used for sanctions screening”", "Search; explanations"],
        ],
        "col_w": [1.0, 1.6, 1.6],
    },
    {
        "kind": "flow",
        "kicker": "Derive, never restate",
        "title": "Controls come from declarations",
        "steps": [
            ("Declaration", "Grain, domains and relationships, approved by the owner."),
            ("Generator", "Deterministic rules turn each fact into PQL, quoting the reason."),
            ("Proposal", "Queued with its provenance; a person accepts or rejects it."),
            ("Control", "Active, versioned, and re-derived when the declaration changes."),
        ],
        "items": [
            "Change the declaration and the controls change with it. There is no second "
            "copy of the meaning to fall out of date.",
            "A rejected proposal stays rejected: its content hash is remembered, so "
            "regeneration does not refill the queue.",
            "Mining (keys, dependencies) and declaration can propose the same rule; it "
            "becomes one corroborated proposal, ranked higher.",
        ],
    },
    {
        "kind": "split",
        "kicker": "Coverage",
        "title": "The uncovered remainder is named, not rounded away",
        "left": {
            "head": "What coverage measures",
            "items": [
                "Each critical data element against the dimensions it needs",
                "Which controls discharge which requirement, and on what evidence",
                "What the declarations alone cannot reach",
            ],
        },
        "right": {
            "head": "An honest finding",
            "items": [
                "A dataset declaration alone cannot cover its own CDEs: some checks need a "
                "second dataset",
                "Declaring the relationships closes the gap",
                "Both facts are tests in the suite, so neither can quietly change",
            ],
        },
        "note": "tests/propose/test_wave6_acceptance.py: "
        "test_a_dataset_declaration_alone_cannot_cover_its_own_cdes and "
        "test_the_uncovered_remainder_is_named_rather_than_rounded_away.",
    },
    {
        "kind": "table",
        "kicker": "Metadata",
        "title": "Rules grow from metadata an owner fills in",
        "intro": "Templates define typed fields. A field can carry a rule, so filling it in "
        "proposes a check, with the literal typed and quoted by the engine, never pasted.",
        "rows": [
            ["Field on an attribute", "Value", "Proposed control"],
            ["mandatory", "yes", "CHECK t.col IS NOT NULL DIMENSION completeness"],
            ["unique", "yes", "CHECK t.col IS UNIQUE DIMENSION uniqueness"],
            ["allowed values", "RETAIL, SME, CORPORATE", "CHECK t.col IN (…) DIMENSION validity"],
            ["minimum", "0", "CHECK t.col >= 0 DIMENSION validity"],
            ["key (dataset)", "customer_id", "CHECK t HAS UNIQUE KEY (…)"],
        ],
        "col_w": [1.1, 1.1, 2.4],
        "note": "Case study 7 declares three datasets with no rules at all; every check "
        "that runs comes from metadata or correlation, and all four planted defects are found.",
    },
    {
        "kind": "bullets",
        "kicker": "Correlation",
        "title": "Same meaning, different datasets",
        "items": [
            (
                "Grouped by concept, glossary term or semantic type",
                "customers.lei and accounts.customer_lei are both bound to the term LEI.",
            ),
            (
                "The owner of a meaning is derived",
                "A column in the grain, in the declared key, or declared unique owns it; "
                "the others must reference it.",
            ),
            (
                "Proposed: a referential check",
                "CHECK accounts.customer_lei REFERENCES customers.lei DIMENSION integrity.",
            ),
            (
                "Reported: held inconsistently",
                "The same identifier marked PII in one dataset and not the other is a finding "
                "for a steward, not a check: which side is right is a business decision.",
            ),
        ],
    },
    {
        "kind": "bullets",
        "kicker": "Change control",
        "title": "Proposals are the only way anything changes",
        "items": [
            (
                "One channel for every author",
                "Declarations, mining, metadata, lineage, correlation and models all produce "
                "proposals. None of them activates a control.",
            ),
            (
                "A person approves, by tier",
                "Nothing activates without a named approver; tier-1 and tier-2 changes "
                "need approval.",
            ),
            (
                "Every change is a version",
                "A control's PQL, its reason and its approver are kept; nothing is edited in "
                "place.",
            ),
            (
                "Discussion sits on the object",
                "Comment threads with mentions reach each person's queue.",
            ),
        ],
    },
    # ------------------------------------------------------------------ part 3
    {
        "kind": "divider",
        "num": "3",
        "title": "The language",
        "sub": "PQL: one statement a data owner can read and an engine can run.",
        "points": [
            "What a control looks like",
            "One IR, several engines",
            "Fused scans",
            "Five verdicts, not two",
            "When PQL cannot say it",
        ],
    },
    {
        "kind": "table",
        "kicker": "PQL",
        "title": "What a control looks like",
        "rows": [
            ["Kind", "PQL"],
            ["Validity", "CHECK trades.notional >= 0 SEVERITY critical DIMENSION validity"],
            ["Uniqueness", "CHECK trades HAS UNIQUE KEY (trade_id)"],
            ["Referential", "CHECK trades.account_id REFERENCES accounts.account_id"],
            [
                "Freshness",
                "CHECK trades.loaded_at IS FRESH WITHIN 4 HOURS OF '06:30' CALENDAR 'TARGET2'",
            ],
            [
                "Reconciliation",
                "RECONCILE subledger AGAINST general_ledger ON (account, posting_date) "
                "COMPARING amount = balance_eur WITHIN 0.01 EUR",
            ],
            ["Custom SQL", 'CHECK trades CUSTOM SQL """SELECT … AS violating_rows …"""'],
            ["Delegate", "CHECK trades USING DELEGATE 'acme.settlement_cycle'"],
        ],
        "col_w": [1.0, 4.2],
        "note": "Every control ends BECAUSE '…': the reason is part of the control, and "
        "`prama control explain` reads it back as a sentence an owner can check.",
    },
    {
        "kind": "flow",
        "kicker": "Compilation",
        "title": "One IR, several engines",
        "steps": [
            ("PQL", "Parsed, linted, and type-checked against the catalogue of schemas."),
            ("IR", "Resolved and versioned; the thing that is hashed into evidence."),
            ("Backend", "Compiled to SQLite, DuckDB or PostgreSQL SQL, pushed to the data."),
            ("Metrics", "Scanned and violating rows come back; the engine judges."),
        ],
        "items": [
            "A conformance suite runs the same IR on each engine and requires the same "
            "verdict on the same data: assert the executed verdict, not plausible SQL.",
            "`prama control compile --fuse` groups controls over one table into shared "
            "scans: in the fusion test, 400 controls run as 160 scans.",
            "Pushdown coverage is published: `prama control functions` says what runs on "
            "which engine, and what does not.",
        ],
    },
    {
        "kind": "table",
        "kicker": "Verdicts",
        "title": "Five verdicts, because two would lie",
        "rows": [
            ["Verdict", "Meaning", "Why it is separate"],
            ["pass", "The exact test ran and found no violation", "The only green"],
            ["fail", "Violations found above the threshold", "With counts and a sample"],
            [
                "indeterminate",
                "A screen ran, or the metrics cannot be judged",
                "Zero from a lower bound is not a pass",
            ],
            ["error", "The control could not run", "Checked nothing, and says so"],
            ["skipped", "Not run in this pass", "Recorded, never counted as a pass"],
        ],
        "col_w": [0.9, 2.0, 1.8],
        "note": "Nulls are UNKNOWN and count as violations by default: an account that names "
        "nobody does not reference a customer. TREAT UNKNOWN AS PASS says otherwise, in the "
        "control, where a reviewer can see it.",
    },
    {
        "kind": "split",
        "kicker": "Beyond PQL",
        "title": "When the language cannot say it",
        "left": {
            "head": "CHECK CUSTOM SQL",
            "items": [
                "The SQL is the author's; the verdict is still the engine's",
                "One read-only SELECT returning violating_rows and scanned_rows",
                "Same evidence, same approval, same versioning",
            ],
        },
        "right": {
            "head": "DQ delegates, in Python",
            "items": [
                "A class behind the DqDelegate interface, named from PQL",
                "Sandboxed: clean environment, audit hook, network namespace where allowed",
                "Uploaded through the console with checks and an approval step",
                "A test kit for the author's own CI; remote agents run them beside the data",
            ],
        },
        "note": "Case study 5 runs a settlement-cycle delegate locally and on a remote agent; "
        "the delegate returns counts, and Prama judges them.",
    },
]
