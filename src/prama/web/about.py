"""What the About and competitive-landscape pages say, as data.

Laid out after Maya's About and ``/about/competitive`` pages. The comparison is
by **category, not vendor**: a row naming one product's features would be
wrong by its next release, and is not Prama's to state. What stays true for
longer is where each category's centre of gravity sits, and that is what a
rating claims. ``docs/20-competitive-analysis.md`` is the long form, vendor by
vendor, and says where each vendor is better than Prama today.

Every rating here is about what is **built**, not what is planned. A row where
Prama is ``Partial`` or ``No`` stays on the page, below the ones where it is
strong, with the reason: a comparison that only lists advantages is a morale
exercise, not an analysis.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses

YES, PARTIAL, NO = "Yes", "Partial", "No"
RATINGS = (YES, PARTIAL, NO)


@dataclasses.dataclass(frozen=True, slots=True)
class Category:
    """A family of products Prama is compared with."""

    key: str
    label: str
    short: str
    examples: str


CATEGORIES: tuple[Category, ...] = (
    Category("cat", "Catalogs & governance", "Catalog",
             "Collibra, Alation, Atlan, Microsoft Purview"),
    Category("lin", "Lineage specialists", "Lineage", "Solidatus, IBM Manta, Octopai"),
    Category("obs", "Data observability", "Observability",
             "Monte Carlo, Anomalo, Bigeye, Sifflet"),
    Category("dq", "DQ suites & open-source checks", "DQ",
             "Informatica, Ataccama, Soda, Great Expectations, dbt tests, Deequ"),
    Category("rec", "Reconciliation", "Recon", "Duco, Gresham, SmartStream"),
)  # fmt: skip


@dataclasses.dataclass(frozen=True, slots=True)
class Row:
    """One capability: how each category stands, the problem, and how Prama does it."""

    id: str
    cap: str
    #: Keyed by `Category.key`, plus ``prama``.
    ratings: dict[str, str]
    problem: str
    #: Paragraphs. Trusted markup (``<code>``, ``<em>``) written here, never user input.
    how: tuple[str, ...]

    @property
    def prama(self) -> str:
        return self.ratings["prama"]


def _r(cat: str, lin: str, obs: str, dq: str, rec: str, prama: str) -> dict[str, str]:
    return {"cat": cat, "lin": lin, "obs": obs, "dq": dq, "rec": rec, "prama": prama}


Y, P, N = YES, PARTIAL, NO

ROWS: tuple[Row, ...] = (
    Row(
        "declared",
        "Business meaning declared by its owner, and controls derived from it",
        _r(P, P, N, P, N, Y),
        "A glossary says what a term means and a rule engine checks columns, and nothing connects "
        "the two: the owner's sentence and the engineer's rule drift apart, and neither notices.",
        (
            "An owner declares a dataset, its attributes, its concepts and its relationships in "
            "the "
            "business's words, with a version. Metadata such as <code>mandatory=yes</code> or a "
            "value domain <em>implies</em> controls, and those arrive in Proposals for a person to "
            "accept. The control is derived from the declaration, never restated beside it.",
            "Glossaries already curated elsewhere come in (<code>prama glossary import --from "
            "alation</code> or <code>collibra</code>), and the import lists what it dropped rather "
            "than leaving that to be discovered.",
        ),
    ),
    Row(
        "language",
        "One declarative rule language, pushed down to more than one engine",
        _r(N, N, N, P, P, Y),
        "Rules are written in each tool's dialect or UI, so moving engines means rewriting them, "
        "and two engines can silently disagree about the same rule.",
        (
            "Controls are written in PQL, compiled through a typed intermediate representation to "
            "SQL for SQLite, DuckDB and PostgreSQL, and run where the data is. A conformance suite "
            "runs every construct on the real engines and compares the <em>executed verdicts</em>, "
            "not the SQL text. <code>prama control functions</code> prints what pushes down where.",
            "Every control reads back as a sentence an owner can check (<code>prama control "
            "explain</code>), a language server gives the editor completion and type errors, and "
            "rules already written for dbt, Great Expectations or Soda are imported, with a list "
            "of "
            "what did not come across.",
        ),
    ),
    Row(
        "calibrated",
        "Alerts with a stated false-alarm rate that you can set",
        _r(N, N, P, N, N, Y),
        "Anomaly detectors learn what normal looks like and alert on deviation, but none says how "
        "many of this month's alerts were expected to be false, so alert fatigue is managed by "
        "muting.",
        (
            "Monitors produce conformal p-values rather than scores, so a threshold means a "
            "false-alarm rate. Across many monitors a Benjamini-Hochberg budget controls the "
            "false-discovery rate for the whole estate, and a monitor without enough history says "
            "it is uncalibrated instead of guessing.",
            "The calibration adapts with a stated half-life, so a regime change degrades visibly "
            "rather than silently.",
        ),
    ),
    Row(
        "evidence",
        "Hash-chained evidence, replayable, verified without the platform",
        _r(N, P, N, N, P, Y),
        "Results live in the tool that produced them, with retention windows and mutable history, "
        "so the tool ends up vouching for itself.",
        (
            "Every verdict is appended to a hash-chained ledger. The chain head can be "
            "time-stamped "
            "outside Prama by an RFC 3161 authority (<code>prama evidence anchor</code>), so a "
            "rewritten and re-chained history is still caught.",
            "A run can be replayed and compared with what was recorded, and an export is checked "
            "by <code>scripts/verify_evidence.py</code>, which needs no Prama installed: the "
            "auditor does not have to trust the platform under audit.",
        ),
    ),
    Row(
        "attest",
        "Owner attestation and regulator-shaped evidence packs",
        _r(P, P, N, N, P, Y),
        "Lineage tools evidence where a number came from; catalogs evidence a policy. What an "
        "auditor signs is whether the controls on it held, over a period, and who says so.",
        (
            "An owner attests that a dataset met its controls over a period, from the evidence "
            "itself, and the attestation pack assembles what BCBS 239 / RDARR work asks for. "
            "Reports for owners, auditors and regulators are built from the same ledger, so the "
            "report and the evidence cannot disagree.",
        ),
    ),
    Row(
        "recon",
        "Reconciliation in the same rule model, evidence and score as every other control",
        _r(N, N, N, P, Y, Y),
        "Reconciliation lives in a separate product with its own rules and its own audit trail, "
        "so the break between the GL and the sub-ledger never reaches the quality score of the "
        "return that depends on both.",
        (
            "<code>RECONCILE</code> is a PQL control like any other: keyed and n-way matching, "
            "normalisation, tolerance, classification of breaks, and a break workbench to explain, "
            "assign and accept them. Its verdicts land in the same ledger and the same scorecards.",
        ),
    ),
    Row(
        "lineage-controls",
        "Lineage that runs controls: impact, and controls carried downstream",
        _r(P, P, P, N, N, Y),
        "A lineage map is a claim about topology. It says where a number comes from, not whether "
        "what flowed through that path today was right.",
        (
            "Column lineage is parsed from ETL SQL (sqlglot, with a regex fallback), pandas and "
            "PySpark code, Airflow, Power BI and warehouse query history, and imported from Manta "
            "or Alation exports beside Prama's own parse. <code>prama lineage impact</code> says "
            "what a defect in a column reaches.",
            "A control the business already has is proposed again downstream along that lineage, "
            "and trust in a source propagates to what is derived from it.",
        ),
    ),
    Row(
        "change-review",
        "A pull request's effect on lineage and controls, reviewed in CI",
        _r(N, P, N, P, N, Y),
        "A change to ETL code can remove the column a control depends on, and nothing notices "
        "until the control errors in production.",
        (
            "<code>prama code review --base origin/main</code> parses the changed code, diffs the "
            "lineage, and names every control that loses its basis, with exit code 3 so the "
            "pipeline can block the merge. Data contracts gate CI the same way "
            "(<code>prama contract check</code>).",
        ),
    ),
    Row(
        "ai",
        "Models that draft and explain, and never decide a verdict",
        _r(P, P, P, P, P, Y),
        "AI features are added to the product, and it is not always clear which answers a model "
        "gave, what it cost, or whether a model's output decided that data passed.",
        (
            "No code path lets a model's output decide pass or fail, and an architecture test "
            "fails "
            "the build if one appears. Models author, rank, explain and summarise; a "
            "deterministic, "
            "versioned engine decides.",
            "Every model call goes through one gateway with routes, budgets and evaluations, and "
            "is "
            "recorded in its own hash-chained ledger (<code>prama llm verify</code>). A "
            "self-hosted "
            "model works as well as a hosted one.",
        ),
    ),
    Row(
        "banking",
        "Financial message formats, calendars and banking concepts built in",
        _r(N, N, N, P, P, Y),
        "General tools see a SWIFT message or a FIX order as a string column, and a settlement "
        "date check does not know TARGET2 was closed that day.",
        (
            "The banking pack parses FIX, ISO 8583, ISO 20022, SWIFT and FpML and says what is "
            "wrong with a message; computes market calendars from their rules; recognises business "
            "concepts such as Exposure from column names; and states what it does <em>not</em> "
            "claim to discharge (<code>prama pack claims</code>).",
        ),
    ),
    Row(
        "delegates",
        "Existing Python checks admitted as governed, sandboxed controls",
        _r(N, N, N, P, N, Y),
        "Years of Python DQ code cannot be rewritten at once, and running it inside a governed "
        "platform usually means trusting it completely.",
        (
            "A Python check is admitted after review as a delegate, runs sandboxed in its own "
            "process with a time limit, and records evidence exactly as a PQL control does. Code "
            "intake reads controls out of existing DQ code and proposes PQL for them.",
        ),
    ),
    # -- where Prama is partial or behind ----------------------------------------------
    Row(
        "legacy-lineage",
        "Automated lineage from legacy ETL tools and BI",
        _r(P, Y, P, P, N, P),
        "This is where the lineage specialists are strongest: dozens of scanners for ETL tools, "
        "stored procedures and BI semantic layers.",
        (
            "Prama verifies its SQL dialects, parses Power BI, and has configurable shapes for ETL "
            "exports, but those shapes are <em>not verified</em> against real Informatica or SSIS "
            "exports. Mainframe code, DataStage, Talend, Ab Initio and SAS are out of scope by "
            "decision.",
            "Where Prama does not scan, it imports the specialist's lineage and attaches controls "
            "to it: keep the scanner, let Prama execute.",
        ),
    ),
    Row(
        "detectors",
        "Unsupervised monitoring with minutes to a first alert",
        _r(N, N, Y, P, N, P),
        "Observability tools point at a warehouse and monitor it the same afternoon, with "
        "detectors tuned for years on real estates.",
        (
            "Prama profiles and proposes controls with no declarations, and its monitors cover "
            "freshness, volume and distribution, but its detectors are younger. Prama competes on "
            "<em>calibration</em>, not raw detection: a detector tournament can adopt any "
            "detector, and a calibrated one is what reaches the alert queue.",
        ),
    ),
    Row(
        "catalog",
        "Catalog, search and curation",
        _r(Y, P, P, P, N, P),
        "Catalogs are years ahead in curation and discovery, and in accounts that own one the "
        "glossary is already populated.",
        (
            "Prama finds data by business meaning (<code>prama metadata find</code>), keeps a "
            "glossary, and imports catalog glossaries, but it is not a catalog and will not become "
            "one. Write-back adapters that publish quality into Collibra, Alation and DataHub are "
            "written and <em>not yet run</em> against a live server.",
        ),
    ),
    Row(
        "recon-ops",
        "Reconciliation operations at scale",
        _r(N, N, N, N, Y, P),
        "Reconciliation products have decades of break-management workflow and operations teams "
        "built around them.",
        (
            "Prama's reconciliation is data-quality grade: it matches, classifies and explains, "
            "and "
            "its verdicts are evidence. It does not claim parity with a dedicated reconciliation "
            "operation's workflow depth.",
        ),
    ),
    Row(
        "identity",
        "Enterprise identity: single sign-on, MFA, custom roles",
        _r(Y, Y, Y, Y, Y, P),
        "An enterprise buyer expects sign-in through its own identity provider.",
        (
            "Prama verifies OIDC ID tokens, but no console sign-in flow uses it yet; there is no "
            "MFA, and there are four built-in roles rather than custom roles and groups. Scoped, "
            "expiring API keys and four-eyes approval are built.",
        ),
    ),
    Row(
        "airgap",
        "On-premises and air-gapped deployment",
        _r(P, P, N, P, P, P),
        "Much of this market is SaaS-first, and a regulated estate often cannot send data or "
        "metadata out.",
        (
            "Every browser asset is vendored, a self-hosted model works through the gateway, and "
            "an "
            "offline bundle is sealed with a manifest and SBOM and can be signed with Ed25519. An "
            "air-gapped install with a local model has <em>not yet been verified end to end</em>, "
            "so this stays Partial until it has.",
        ),
    ),
    Row(
        "mdm",
        "Master data: golden records and survivorship",
        _r(P, N, N, P, N, N),
        "Mastering is its own discipline, with its own steward tooling.",
        (
            "Prama does not master data, by choice. It treats entity resolution as a control and "
            "feeds a mastering product rather than competing with one.",
        ),
    ),
    Row(
        "scale",
        "Deployments, references, ecosystem and support",
        _r(Y, Y, Y, Y, Y, N),
        "The established products have customers, integrations, certifications and support desks.",
        (
            "Prama is one author's work and has not been deployed at a supervised institution, and "
            "no competitor has been benchmarked against it: configuring another tool fairly is not "
            "something the party who benefits from the result should do. It is built to be "
            "inspected rather than taken on trust: the benchmark, its ablations and the fifteen "
            "baselines it did <em>not</em> run are printed by <code>prama bench run</code>.",
        ),
    ),
)

SHINES = tuple(row for row in ROWS if row.prama == YES)
BEHIND = tuple(row for row in ROWS if row.prama != YES)
