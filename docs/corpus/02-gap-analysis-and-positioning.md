<img src="../assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

> ***pramā*** (Sanskrit **प्रमा**) — *valid knowledge: a cognition that is both true and arrived at
> by a reliable means*. Its companion ***pramāṇa*** (प्रमाण) is *the instrument by which valid
> knowledge is obtained*. Prama is that instrument for an organisation's data — it does not decide
> what is true, it is how a belief about data becomes **justified**.
>
> **Declare it. Prove it. Trust it.**


---
# 02 — Gap Analysis, Product Thesis, and Positioning

---

## As built

The seven gaps are the product's reason to exist, so their status matters more
than most.

**G1 business ownership** — built: the semantic layer, the console, and control
derivation from declarations rather than from SQL.
**G2 legacy estates** — partial: COBOL/EBCDIC and six financial message formats
are read and tested; ETL scanners are configurable and unverified against real
Informatica or DataStage exports.
**G3 engine divergence** — built, and the strongest part: a typed engine-neutral
IR, a reference interpreter, and a conformance suite that requires DuckDB,
SQLite and PostgreSQL to agree per function.
**G4 alert fatigue** — built: calibration, deduplication, severity, quiet
periods, and an alert with no recipient reported rather than dropped. The
*measured* precision claim needs design partners.
**G5 evidence** — built: hash-chained, replayable, and verifiable by a script
that imports nothing of ours.
**G6 regulatory framing** — built: twenty obligations across nine regimes, every
citation honestly marked unconfirmed.
**G7 AI that cannot be trusted with verdicts** — built and enforced: `CON-007`
is an import scan that fails the build, and the assistant cannot mutate anything
at all.

---

## 1. The seven structural gaps

Derived from [01 — Landscape Survey](01-landscape-survey.md). Each gap is stated as an observed
market fact, the consequence for the buyer, and the Prama response.

### GAP-1 — Three disjoint paradigms, three disjoint products

**Fact.** Quality knowledge exists in three forms — *declarative assertions* (GX, Soda, dbt),
*statistical/ML monitors* (Monte Carlo, Anomalo, Lightup), and *semantic/business judgements*
(spreadsheets, tribal knowledge, now LLM prompts). No vendor represents all three in one model.
Even single vendors that offer all three (Ataccama, Collibra) implement them as separate
subsystems with separate result schemas.

**Consequence.** No unified score, no unified incident, no unified evidence. A regulator asking
"show me every control over this figure and its outcome on 31-Mar" gets three exports and a
reconciliation exercise.

**Prama response.** One **Quality Assertion Algebra**: every check — declarative, statistical, or
LLM-authored — is an *assertion* over a *scope* producing an *evidence record* with a *verdict* and
a *calibrated confidence*. One IR, one evidence store, one score. ([07](07-rule-language-spec.md))

---

### GAP-2 — Uncalibrated alerting → alert fatigue → abandonment

**Fact.** Every ML-based DQ product ships anomaly scores with no statistical interpretation.
"Sensitivity: medium." Users cannot express "I will tolerate 5 false alarms per 1,000 checks per
week." The literature on industrial monitoring documents this as the dominant adoption failure;
the conformal-prediction literature (ICLR 2026; `nonconform`; FDR-guaranteed novelty detection)
already provides p-value-valued anomaly scores with guarantees that survive distribution shift.

**Consequence.** Teams disable monitors within two quarters. Trust in the tool collapses before
trust in the data improves.

**Prama response (novel).** **Risk-controlled alerting**: every statistical monitor emits a
conformal p-value; alerting is a *selection procedure* under a user-declared **false-alarm budget**,
with **hierarchical Benjamini–Hochberg FDR control** across the domain → dataset → column → check
lattice. Alert volume becomes a *dial*, not a surprise. ([08](08-ai-ml-capabilities.md) §4)

---

### GAP-3 — Rules are locked to an engine

**Fact.** SodaCL emits SQL for its supported warehouses; Deequ runs only on Spark; DQX only on
Databricks; dbt tests only where dbt models exist; DMFs only in Snowflake. Migrate the platform,
rewrite the controls.

**Consequence.** Controls become a migration liability. Banks running Teradata → Snowflake →
lakehouse migrations over a decade rewrite their entire control estate two or three times, and
each rewrite is a fresh audit finding.

**Prama response.** Rules compile to an **engine-neutral IR** with pluggable backends: ANSI SQL
(with dialect adapters for 25+ engines), Spark, Flink (streaming), Arrow/DuckDB (local & file), and
a native row-scanner for non-relational feeds. **Write once, execute at source, prove equivalence.**
An IR-level *conformance test suite* certifies that a rule means the same thing on every backend —
itself a publishable systems result.

---

### GAP-4 — Assets are scored in isolation; trust does not propagate

**Fact.** Every product scores each table independently. Lineage is used for *root-cause navigation*
after an alert, never as a *carrier of quality semantics*.

**Consequence.** A "98% quality" gold table can be built entirely from a bronze table whose primary
control has been failing for six weeks. The score is not merely uninformative; it is misleading,
and in a regulatory context, materially so.

**Prama response (novel).** **Lineage-aware trust propagation**: a semiring-valued score that flows
along the column-level lineage DAG with transformation-aware attenuation, so a consumer's trust is
a function of its own controls *and* its ancestry. Enables "what is the trust of the LCR return?"
answered from first principles. ([11](11-reporting-alerting-learning.md) §3)

---

### GAP-5 — No evidence model; nothing is audit-grade

**Fact.** Observability vendors store alerts and metrics with retention windows and mutable state.
None produce an immutable, reproducible, attestable artefact per control execution. BCBS 239
principles 3–6 (accuracy & integrity, completeness, timeliness, adaptability) and supervisory review
(principles 12–14) demand exactly that.

**Consequence.** Banks buy an observability tool for engineering and *still* run a parallel manual
control-attestation process in spreadsheets and GRC tooling.

**Prama response.** **Evidence-first execution.** Every assertion run emits an immutable
`EvidenceRecord`: rule version hash, compiled IR hash, engine + engine version, data snapshot
identifier (Delta/Iceberg version, DB SCN/LSN, file digest), row counts examined, verdict, failing
sample under policy, wall-clock and logical time, executing identity, and a signature chain.
Hash-linked, append-only, WORM-exportable, and **deterministically replayable**. ([13](13-security-governance-compliance.md) §6)

---

### GAP-6 — Cross-system truth is out of scope

**Fact.** DQ tools validate *a* dataset. Banking's most expensive quality failures are *between*
datasets: front-office vs. back-office positions, sub-ledger vs. general ledger, custodian vs.
internal books, trade repository vs. source, T vs. T-1 balance roll-forwards, regulatory return
vs. its own feeder. This is sold separately, at high prices, by reconciliation vendors
(Gresham, Duco) with strong workflow but no DQ breadth, ML depth, or profiling.

**Consequence.** Two tools, two rule estates, two evidence trails, two vendors, for one control
objective.

**Prama response.** **Reconciliation as a first-class assertion type.** `RECONCILE A AGAINST B ON
keys WITH tolerance ...` compiles to the same IR, produces the same evidence, feeds the same score,
and gets the same break-management workflow. Includes N-way, many-to-many, netting, FX/unit
normalisation, and time-shifted comparison. ([07](07-rule-language-spec.md) §7)

---

### GAP-7 — The interface serves engineers, not the people accountable

**Fact.** GX requires Python. SodaCL requires YAML + Git. dbt requires the dbt project. The
"business user" products (RightData, Talend) sacrifice expressiveness for clicks. Chat interfaces,
where they exist, are bolted-on Q&A over docs.

**Consequence.** The Chief Data Officer, the risk controller, and the regulatory reporting analyst
— the people actually accountable — cannot author, inspect, or attest to a control without an
engineer. Control ownership and control authorship are separated, which is itself an audit finding.

**Prama response.** **Three coequal surfaces over one API**: (a) a visual authoring/monitoring
console, (b) declarative PQL text in Git, (c) a **conversational agent** that can author, explain,
triage, and report. All three are *the same system*; the chat agent's every mutating action is a
reviewable proposal that renders as PQL and passes through the same approval workflow.
([10](10-ux-and-chat-interface.md))

---

## 2. Product thesis

> **Prama is a neuro-symbolic, evidence-first data quality control plane.**
> AI *writes and calibrates* controls; a deterministic engine *executes* them at the source;
> every execution produces immutable, replayable evidence; trust flows along lineage;
> and humans direct all of it from a console, a Git repo, or a conversation.

Five commitments follow, and they are the design constraints for everything downstream:

1. **Symbolic execution, neural authorship.** No LLM ever decides a pass/fail. LLMs propose PQL;
   PQL is reviewed, versioned, and executed deterministically. This is the only auditable design
   and it is also the only affordable one at 10^10 rows.
2. **Calibrated by construction.** Any probabilistic output carries a calibrated confidence with a
   stated guarantee. Uncalibrated scores are a defect, not a feature.
3. **Compute goes to data.** Pushdown by default; the platform is a control plane, not a data plane.
   Data residency, cost, and DORA/air-gap constraints are satisfied structurally, not by policy.
4. **Everything is evidence.** If it can't be replayed and signed, it didn't happen.
5. **Open at the seams.** ODCS in/out, OpenLineage out, OpenTelemetry out, SQL/Python/MCP in.
   We win on depth, not lock-in.

---

## 3. Competitive positioning

### 3.1 Positioning statement

> For **regulated, data-intensive enterprises — beginning with banks and capital-markets firms —
> whose quality controls must be provable, not merely present**, Prama is a **unified data quality
> control plane** that combines declarative rules, calibrated machine learning, and conversational
> AI over a single evidence model. Unlike **observability tools** (which detect but cannot prove),
> **legacy DQ suites** (which prove but cannot learn), and **platform-native checks** (which do
> neither across systems), Prama makes every control **authored by anyone, executed anywhere,
> calibrated statistically, and defensible to a regulator.**

### 3.2 Against each competitor class

| Competitor class | They win when… | We win when… | Our wedge |
|---|---|---|---|
| **Monte Carlo / Anomalo / Bigeye** (observability) | The buyer is a data-engineering team on one cloud warehouse wanting fast time-to-alert | Alerts must be trusted, controls must be attested, sources span mainframe/feeds/streams, or reconciliation matters | Calibrated alerting + evidence + breadth |
| **Informatica / IBM / SAP / Oracle** (legacy suites) | Incumbency, procurement inertia, existing MDM entanglement | Buyer wants modern ML, pushdown, git-ops, chat, and a 6-week not 18-month deployment | Speed, AI depth, cost, developer experience |
| **Ataccama / Collibra** (unified governance) | Buyer is standardising governance + catalog + DQ in one procurement | Buyer already has a catalog and needs the quality engine to be materially better | Depth over breadth; interop with their catalog |
| **Soda / GX / dbt / Deequ** (OSS) | Small team, one platform, engineering-owned, budget zero | Business users must author; scale/regulation/multi-source; needs a control plane | We *import* their rules; we are the upgrade path |
| **Snowflake DMF / Databricks LHM** (platform-native) | Single-platform shop, basic checks, no extra spend | Multi-platform, cross-system, regulated, or needing workflow | We consume their metrics; we own the 40% they can't |
| **Gresham / Duco** (reconciliation) | Pure recon problem with mature ops teams | Recon is one of several control types and must share evidence with DQ | Recon inside a DQ platform, at DQ prices |
| **Reltio / Profisee / Semarchy** (MDM) | Golden-record mastering is the actual project | Matching is a *quality control*, not a mastering programme | ER as a check; feed their MDM, don't replace it |

### 3.3 What we deliberately do **not** build

Scope discipline is a survival requirement. We will **not** build:

- A data catalog (we integrate: OpenMetadata, DataHub, Collibra, Alation, Purview, Unity Catalog).
- An ETL/ingestion engine (we integrate: dbt, Airflow, Dagster, Spark, Flink, Informatica, ADF).
- A full MDM hub with survivorship and stewardship UI (we do ER *detection*; we feed MDM).
- Address/email/phone verification reference data (we integrate: Experian, Melissa, Loqate).
- A BI tool (we embed and we export; we ship scorecards, not a semantic-layer BI product).
- A general observability/APM platform (we emit OpenTelemetry to Datadog/Grafana/Splunk).

These are documented as **CON-001…CON-006** in [04](04-requirements-functional.md).

---

## 4. Target segments and entry sequence

| Wave | Segment | Beachhead use case | Why they buy first |
|---|---|---|---|
| **1** | Tier-1/Tier-2 banks — Risk & Finance data offices | **BCBS 239 / RDARR control attestation** and regulatory-return feeder quality | Existing regulatory pressure, existing budget, existing pain, spreadsheet-based status quo |
| **1** | Capital markets — Ops & Control | **Trade/position/cash reconciliation + transaction-reporting (EMIR/MiFIR/CFTC) pre-submission validation** | Direct fine exposure; quantifiable ROI |
| **2** | Banks — Data Office / CDO | Enterprise **data quality scorecard** across domains, DQ SLAs with data producers | Follows from Wave 1 evidence; expands seats |
| **2** | Insurance, asset management, payments | Solvency II / IFRS 17 / scheme reporting; same control shape | Same regulatory grammar, adjacent sales motion |
| **3** | Healthcare/life sciences (HIPAA, GxP, EHR), Telco, Public sector, Energy | Domain packs; same platform | Proves the "any industry" claim; the domain-pack model is the mechanism |
| **3** | AI/ML platform teams (any industry) | **AI-readiness certification** of training/RAG corpora | Rides the GenAI budget; uses the same engine on unstructured assets |

**Industry-adaptation mechanism.** The platform core is domain-neutral. All verticality lives in
**Domain Packs** — versioned bundles of: reference-data validators, message-format parsers,
rule libraries, dimension weightings, scorecard templates, regulatory control catalogues, and
glossary/ontology fragments. Banking is Pack #1 ([12](12-banking-domain-pack.md)); the pack SDK is
public so partners and customers can build their own. This is how "banking-first, industry-general"
becomes an architecture rather than a slogan.

---

## 5. The "best in world" claim — how we make it falsifiable

A claim of superiority that cannot fail is marketing. We define nine measurable superiority
criteria, each with a target, a method, and a named competitor baseline. Full protocol in
[15 — Evaluation & Benchmark Methodology](15-evaluation-benchmark-methodology.md).

| # | Criterion | Metric | Target vs. best baseline |
|---|---|---|---|
| S1 | Detection quality | F1 on seeded-error benchmark (tabular + financial feeds) | **≥ +15% F1** vs. best of {Monte Carlo-class ML, GX-class rules} alone |
| S2 | Alert precision | Precision@alert over 90 days of production monitors | **≥ 0.85** at a declared FDR ≤ 0.10; baselines typically 0.3–0.6 |
| S3 | Calibration | Empirical vs. nominal false-alarm rate | \|empirical − nominal\| **≤ 0.02** across drift regimes |
| S4 | Rule-authoring effort | Median minutes to a reviewed, production-ready control | **≤ 3 min** (chat/induction) vs. 25–60 min (hand-authored YAML/Python) |
| S5 | Coverage | % of columns in a 5,000-table estate under ≥1 meaningful control after 1 week | **≥ 80%** vs. typical 5–15% |
| S6 | Source breadth | # of source/format families with certified connectors | **≥ 120**, incl. ≥ 12 financial message standards |
| S7 | Time-to-detection | Median minutes from defect introduction to alert (streaming and batch) | **≤ 60 s streaming / ≤ 1 scheduling interval batch** |
| S8 | Audit readiness | % of controls with replayable evidence satisfying a Big-4 RDARR test script | **100%** |
| S9 | Cost of quality | Compute $ per billion rows validated | **≤ 50%** of equivalent full-scan baseline (via sampling + incremental + pushdown) |

Failing any of S1–S9 at GA is a release blocker, not a marketing footnote.

---

## 6. Strategic risks to the thesis

Full register in [17](17-risks-and-open-questions.md); the three that could invalidate the thesis:

- **RSK-01 — Platform absorption.** Snowflake/Databricks ship "good enough" quality, free.
  *Mitigation:* own the cross-system, regulated, and feed-based 40%; integrate rather than compete
  on the 60%; make multi-platform estates our home ground.
- **RSK-02 — Calibration is hard in the wild.** Conformal guarantees rest on exchangeability
  assumptions that seasonal, bursty, regime-switching financial data violates.
  *Mitigation:* adaptive/weighted conformal, regime detection, explicit guarantee-degradation
  reporting, and honest UI when guarantees are suspended. Never silently break the promise.
- **RSK-03 — Enterprise sales cycle vs. runway.** Tier-1 bank procurement is 9–18 months.
  *Mitigation:* OSS core (engine + PQL + connectors) for bottom-up adoption; land in one control
  domain (reg reporting) with a 6-week proof; commercial control plane for evidence/workflow/scale.

---

<div align="center">
<img src="../assets/prama-mark.svg" width="30" alt=""/><br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.<br/>
See <a href="../../LICENSE">LICENSE</a> and <a href="../../NOTICE">NOTICE</a>. Third-party names and marks are the property of their respective owners.</sub>
</div>
