<div align="center">

<img src="docs/assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="430"/>

### Declare it. &nbsp;Prove it. &nbsp;Trust it.

**A business-owned, AI-native, evidence-first data quality control plane.**
Banking and capital markets first. Any industry next.

<sub>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved · Proprietary and confidential<br/>
<a href="LICENSE">LICENSE</a> · <a href="NOTICE">NOTICE</a> · <a href="SECURITY.md">SECURITY</a> · <a href="CONTRIBUTING.md">CONTRIBUTING</a> · <a href="docs/">Documentation</a>
</sub>

</div>

---

## The name

> ***pramā*** (Sanskrit **प्रमा**) — *valid knowledge: a cognition that is both **true** and arrived
> at by a **reliable means***.
> ***pramāṇa*** (प्रमाण) — *the **instrument** by which valid knowledge is obtained*.

Classical Indian epistemology makes a distinction that the data industry has lost. A belief is
*pramā* only if it is true **and** produced by a trustworthy instrument. A guess that happens to be
correct is not knowledge. Neither is a dashboard that happens to be green.

That is precisely the gap between *"our data quality score is 98%"* and *"we can prove this number
is right, replay the control that proved it, and show you who approved it."* Prama is the
**instrument** — a *pramāṇa* — by which an organisation's beliefs about its data become justified.
The product does not decide what is true about your data. It is how you come to know.

The logo says the same thing: a broken, unverified beam enters a prism and leaves as six clean,
ordered rays — the six dimensions of data quality. **A prism adds nothing. It reveals what was
already in the light.**

---

## What Prama is

Prama is a **control plane for data quality**, organised around a simple inversion of how every
other tool in the category works.

Existing tools start from the **physical** estate: crawl the warehouse, monitor the columns, alert
the engineers. Prama starts from the **business** estate:

1. **Business owners and data architects declare** — in business language, through a UI or a
   conversation — what their datasets are, what one row means, when data is expected, which fields
   are critical, and **how datasets relate to one another** (*this reconciles with that*, *this is
   derived from that*, *these describe the same entities*).
2. **Prama compiles those declarations into executable controls**, reaches out through configured
   connectors, reads the data (fully or by sampling), and runs the controls **where the data
   already lives**.
3. **Every execution produces immutable, replayable evidence.** Scores are computed from evidence
   and propagate along lineage, so a consumer's trust reflects its ancestry, not just its own tests.
4. **AI authors and calibrates; it never adjudicates.** Machine learning proposes rules, mines
   constraints, and calibrates alarm rates; a deterministic engine decides pass or fail.
5. **The estate is re-examined continuously** on an adaptive cadence, so no finding is ever
   silently stale.

It is a tool for **business data owners, data architects, and stewards** — not for DBAs.

---

## The problem

| Fact | Source |
|---|---|
| Poor data quality costs the average enterprise **~$12.9M per year** | Gartner reference-customer survey (16 vendors, 154 customers) |
| **15–25% of revenue** lost annually to poor data quality | MIT Sloan / Cork University Business School |
| **~£95M** in UK FCA fines for MiFID transaction-reporting failures; **~£34.5M** for EMIR — including **Goldman Sachs >£34M for 220M+ errors** and **UBS >£27M for 135M+ errors** | A-Team Insight |
| Poor data quality is the **#1 obstacle to GenAI adoption** | Gartner IT-leader poll, 2024 |
| **50+ vendors**, and *"observability catches a load that silently stopped; quality testing catches a load that ran perfectly and delivered wrong numbers. Neither substitutes for the other."* | DataKitchen 2026 landscape |

Buyers assemble three to five products that share no rule model, no evidence model, no scoring
model, and no incident model. Seven structural gaps follow — see
**[docs/corpus/02 — Gap Analysis & Positioning](docs/corpus/02-gap-analysis-and-positioning.md)**.

---

## What makes it different

| # | Capability | Why nobody else has it |
|---|---|---|
| 1 | **Business semantic layer whose declarations execute** | Catalogs hold glossaries but don't run controls; DQ tools run controls but hold no business model. Declaring *"the sub-ledger reconciles with the GL on account and cost centre to within €1, one day in arrears"* generates a running, evidenced control — with no SQL written. |
| 2 | **Engine-neutral rule IR** | Write a control once; execute it on Snowflake, Databricks, Spark, Flink, Postgres, DuckDB, or a COBOL feed, with certified semantic equivalence. Controls outlive platform migrations. |
| 3 | **Calibrated alerting** | Every statistical monitor emits a **conformal p-value**; alerting is FDR-controlled under a user-declared false-alarm budget (*"no more than two false alarms a month in this domain"*). No deployed DQ product emits a calibrated alarm rate. Alert fatigue is the documented reason monitoring gets switched off. |
| 4 | **Evidence-first execution** | Immutable, hash-linked, signed, **deterministically replayable** records. The artefact BCBS 239, SOX, and SR 11-7 actually demand — and the hardest thing to retrofit. |
| 5 | **Trust propagation along lineage** | A "98%" gold table built from a failing bronze table is not 98%. Prama propagates trust over the column-level lineage DAG with transformation-aware attenuation. |
| 6 | **Reconciliation as a first-class control** | Banking's most expensive quality failures are *between* systems. Sold separately today by reconciliation vendors; here it shares one rule model, one evidence trail, one score. |
| 7 | **Chat and console as coequal surfaces** | The accountable owner becomes the author. Every AI mutation is a reviewable PQL diff with a backtest, passing the same approval workflow as a UI change. |
| 8 | **Breadth that regulated estates actually need** | 120+ connectors: warehouses, lakehouses, streams, APIs, **mainframe COBOL/EBCDIC/VSAM**, and **12+ financial message standards** — ISO 20022, SWIFT MT, FIX, FpML, FINOS CDM, XBRL, ISO 8583, NACHA/SEPA. |
| 9 | **Continuous re-examination** | Adaptive cadence per dataset; every finding carries its own freshness; **metadata drift** (broken bindings, violated grain, degraded relationships) is raised as an incident to the *business owner of the declaration*. |

---

## How it works

```
   BUSINESS DECLARES                  PRAMA COMPILES                PRAMA PROVES
 ┌───────────────────────┐        ┌────────────────────┐       ┌────────────────────┐
 │ Dataset: Positions EOD│        │  PQL  →  IR  →     │       │ Evidence record    │
 │ Grain: acct × instr   │        │  engine plan       │       │  (immutable,       │
 │ Arrives 06:30 TARGET2 │  ───►  │                    │ ───►  │   signed,          │
 │ notional = CDE (FRTB) │        │  pushdown to the   │       │   replayable)      │
 │ RECONCILES_WITH GL    │        │  source system     │       │ Scores + trust     │
 │ DERIVES_FROM Murex    │        │  (data never moves)│       │ Incidents + alerts │
 └───────────────────────┘        └────────────────────┘       └────────────────────┘
            │                              ▲                            │
            │       AI proposes, ranks, calibrates, explains            │
            │       (never adjudicates — CON-007)                       │
            └──────────────── human confirms / approves ◄───────────────┘
                              feedback becomes training signal
```

One screen of business declarations above yields **eight production controls, a reconciliation with
break workflow, and a calibrated volume monitor** — each carrying the sentence that justifies it.
The worked example is in **[docs/corpus/07 §10](docs/corpus/07-rule-language-spec.md)**.

---

## Run it

```bash
uv venv --python 3.13 && uv sync --extra dev --extra serve
source .venv/bin/activate
python run_prama_web.py --init-secret --prepare
```

Then open **http://127.0.0.1:5900/** — the landing page, with the help centre
at `/help` — or go straight to the console at `/estate`. The port is
`server.port` in configuration. That applies the schema, creates an estate,
writes a session secret into the git-ignored local config, and starts the
console and the API in one process.

**[QUICKSTART.md](QUICKSTART.md)** is the full path: which Python and why, `pip`
instead of `uv`, what each refusal means, and how to run the steps separately on
a real deployment. In PyCharm or IntelliJ IDEA, the repository ships run
configurations: **[the IDE guide](docs/developer/ide.md)**.

An empty console is honest but not persuasive. To see Prama find real defects in
a realistic banking estate:

```bash
cd case-studies/01-trading-book-sqlite && python run.py
```

There are eight studies in **[case-studies/](case-studies/)**: feeds in CSV, Parquet and JSON
Lines, reconciliation, delegates, governance from metadata, and lineage read from ETL code. The
console shows each one under **Help → Case studies**.

---

## Documentation

**[The documentation index](docs/README.md#start-here)** says who should read
which document, and how the folders divide the work: architecture (how it fits),
developer (how to extend it), sdk (scripting it), agent and operations (running
it), and the design corpus (why it is built this way, starting with
[00](docs/corpus/00-executive-summary.md) and
[03](docs/corpus/03-business-semantic-layer.md), the conceptual heart). The same
documents are in the console under **Help**.

---

## The claim, made falsifiable

Nine superiority criteria are **release gates**, measured against named baselines on public
benchmarks we build and publish (**DQ-Bench**, **FinDQ-Bench**), plus a 90-day blind live-shadow
evaluation at three banks. Failing any of them blocks release. Negative results are published.

| | Criterion | Target |
|---|---|---|
| S1 | Detection F1 vs. best baseline | ≥ +15% overall; ≥ +40% on *semantic* defects |
| S2 | Alert precision in live production | ≥ 0.85 at declared FDR ≤ 0.10 (baselines: 0.3–0.6) |
| S3 | Calibration error | ≤ 0.02 across all drift regimes |
| S4 | Time to a reviewed control | ≤ 3 min (vs. 25–60 min hand-authored) |
| S5 | Coverage after one week | ≥ 80% of columns; ≥ 95% of critical data elements |
| S6 | Certified connectors | ≥ 120, incl. ≥ 12 financial message standards |
| S7 | Detection latency | p95 ≤ 60 s streaming |
| S8 | Audit readiness | 100% pass an independent Big-4 RDARR test script |
| S9 | Cost per billion rows validated | ≤ 50% of naive full-scan |

Details and threats to validity: **[docs/corpus/15](docs/corpus/15-evaluation-benchmark-methodology.md)**.

---

## Research

**The paper:** [*Data Quality as Justified Belief*](docs/publications/paper/data-quality-as-justified-belief.pdf) — what is built, with every
formal claim marked by the test that carries it, and what is not ([article version](docs/publications/paper/data-quality-as-justified-belief-article.md)).

Five contributions, targeting **ACM JDIQ** with a **VLDB Industrial** companion — see
**[docs/publications/paper/](docs/publications/paper/)**:

1. A unified **quality assertion algebra and engine-neutral IR** with cross-engine equivalence.
2. **Risk-controlled data quality alerting** — conformal calibration + hierarchical FDR over the
   asset × attribute × check lattice, valid under drift.
3. **Neuro-symbolic rule induction** — algorithmic constraint discovery fused with
   template-constrained LLM authorship.
4. **Lineage-aware trust propagation** as a semiring over the column-level lineage DAG.
5. **DQ-Bench / FinDQ-Bench** — the first public, defect-labelled, cross-system enterprise data
   quality benchmarks.

---

## Status

**Implemented.** The eleven foundation waves of [docs/corpus/19](docs/corpus/19-implementation-roadmap.md)
are complete, apart from two tasks that are open on infrastructure rather than code. So is most of
the intelligence roadmap in [docs/corpus/23](docs/corpus/23-intelligence-and-lineage-roadmap.md): the LLM gateway
and the lineage workbench, code-to-lineage, steward agents, and DQ delegates. What is left is in
[docs/corpus/remaining-work.md](docs/corpus/remaining-work.md). The suite is at <!--tests-->6,809 passing, 96 skipped<!--/tests-->,
derived from a green run by `scripts/sync_test_counts.py` rather than typed — a
count in prose rots the first time somebody adds a test.

That figure is from a run with `helm` installed and a PostgreSQL reachable, so
it includes the chart and live-database tests. A bare clone sees about twenty
more skips and the same number of failures — none. The remaining skips need a
service nobody should have to install to read the code: MongoDB, ClickHouse, a
JDBC driver and a JRE, an S3 endpoint. Each says so by name when skipped.

A skip is worth reading rather than scrolling past. It reports neither pass nor
fail, so a suite summarised by its first number looks green whatever the second
one says — and on 2026-09-13 a chart test that had been failing since the
`OPS-014` fix stayed invisible through six consecutive gate runs, because `helm`
was not on the `PATH` those runs used. It surfaced only when a script that
*runs* the suite refused to publish a count from a red one.

It is two trees, both run by `pytest -q`: `tests/`, which mirrors the package
tree, and `qa/regression-suite/`, which holds what the QA rounds found. The
second exists because a defect found by hand is only fixed once, and a defect
with a test that failed before the fix stays fixed. Each file there names the
case that produced it and, where the fix was subtle, what the test would have
passed on had it been written carelessly.

`qa/` also holds the corpus behind them: a catalogue of <!--cases-->4,660<!--/cases--> cases, the
per-round execution logs, the harness scripts that produced them, and
`findings.md` — which records what was *not* a defect as carefully as what was,
because a findings list that only keeps the hits is one nobody can calibrate
against.

What that covers: the semantic layer and declaration model; PQL, its typed
engine-neutral IR, and a conformance suite that runs the same control on DuckDB,
SQLite and PostgreSQL and requires them to agree; a hash-chained evidence ledger
with deterministic replay, a verifier that imports nothing of ours, and each run's chain
head anchored with an RFC 3161 time-stamp authority when configured;
declaration-derived controls, mining and induction; monitoring and calibration;
the console; a banking pack with six financial message formats, a
seventeen-concept ontology and twenty regulatory obligations; seven of the eight
GA connectors verified against a live service, with Snowflake written and never
run against an account and ODBC not built ([19 §W3.11](docs/corpus/19-implementation-roadmap.md));
and the enterprise surface — SSO, SCIM, residency, customer-managed
keys, an operator, an offline bundle with publisher signing.

The intelligence layer adds these pieces:

- **An LLM gateway.** Models can be local (Ollama, vLLM, llama.cpp) or remote (Anthropic,
  OpenAI, Hugging Face, Amazon Bedrock, Azure OpenAI, Vertex AI). Each call is routed by purpose,
  budgeted, redacted and recorded in a hash-chained ledger. When no model is configured, a mock
  that answers with nothing stands in.
- **Column lineage, from many sources:**
  - SQL in about twenty dialects, including stored procedures;
  - dbt and OpenLineage;
  - PySpark, pandas and Airflow;
  - Power BI models;
  - Snowflake, Databricks and BigQuery query history.
- **Code intake.** A ZIP or a git repository is read in a sandbox and never executed, re-reading
  only what a commit changed. A model may propose further edges, which are checked before a
  person confirms them.
- **Change review on a pull request.** `prama code review --base origin/main` reads both versions
  and reports:
  - the lineage the change adds, removes or retypes;
  - what that reaches downstream;
  - the controls the change implies;
  - the live controls that lose their basis. It exits 3 when there are any, so CI can gate on it.
- **Metadata and business context.** Datasets and attributes carry a versioned business context and your own typed metadata fields. Rules grow from that metadata and are proposed for a person to accept, and datasets can be searched by meaning for the one fit for a purpose (embeddings if a model is configured, BM25 otherwise). Attributes that share a meaning across datasets are correlated: Prama proposes the reference checks that follow and flags where the same meaning is held inconsistently.
- **Usage signals** from warehouse query history rank the work as "most used, least controlled". Datasets often read by the same query, with a column in common and no declared relationship, are flagged to a steward with the likely `REFERENCES`. Neither signal ever changes a quality score.
- **Discussion and steward queues.** Comment threads with @mentions sit on datasets, attributes, controls and terms, and each person has a queue of everything waiting on them.
- **A business glossary**, imported from Alation or Collibra, with its terms bound to concepts, datasets and attributes. Lineage can also be imported from Manta or Alation, and is kept beside Prama's own parse, with any disagreements shown.
- **Controls proposed from lineage,** including a check at every join that each driving row finds its match.
- **Freshness measured on arrival.** A rhythm names its load-timestamp column, and freshness is judged against the due time on the business calendar.
- **Steward agents** that read and propose, and never approve.
- **Observability of Prama itself.**
  - Probes: `/livez` and `/readyz`.
  - Prometheus metrics at `/metrics`, with bounded cardinality.
  - OpenTelemetry spans for runs and controls (the `otel` extra).
  - OpenLineage run events.
  - A ServiceMonitor and a Grafana dashboard in the Helm chart.
- **DQ delegates.** These are Python checks named from PQL:
  - vetted before import;
  - run in a sandbox: clean environment, an audit hook refusing sockets and processes, and a
    network namespace where the host allows one;
  - streamed large inputs;
  - uploaded through the console with four-eyes approval.
- **`CHECK CUSTOM SQL`**, a read-only escape hatch.

Mainframe code (COBOL, JCL) is deliberately out of scope.

**Figures marked as targets or gates are objectives, not measured results**
(see [NOTICE §6](NOTICE)). Where something is built but unverified, the document
that describes it says so in those words — the operator has not met a real API
server, no cloud KMS has been exercised, and no disconnected install has been
performed on a host with no route out. `docs/corpus/19` tracks every one.

Repository layout:

```
prama/
├── README.md          ← you are here
├── QUICKSTART.md      ← install, run, and the first control
├── LICENSE · NOTICE   ← proprietary; legal notice, trademarks, third-party references
├── SECURITY.md        ← reporting, what Prama holds, and what is unverified
├── CONTRIBUTING.md    ← the habits this codebase is held to
├── src/prama/         ← the server: API, console, scheduler, evidence ledger
├── kernel/            ← prama-kernel: the deterministic core the server and agent share
├── sdk/               ← prama-sdk: the Python client
├── agent/             ← prama-agent: the daemon that runs beside the data
├── tests/             ← the suite, mirroring the package tree
├── qa/                ← the QA corpus: catalogue, logs, harness, regressions
├── schema/            ← sqlite.sql and postgres.sql; there are no migrations
├── config/            ← application.yaml; secrets live in application.local.yaml
├── deploy/            ← Dockerfile, Helm chart, operator CRDs
├── scripts/           ← the gate, the file-length ceiling, the evidence verifier
├── case-studies/      ← eight worked examples, end to end
├── tools/             ← the deck, diagram and screenshot generators
├── .run/              ← shared PyCharm and IntelliJ IDEA run configurations
└── docs/              ← architecture, developer, sdk, agent, operations, corpus (00–23),
                         design, reference, publications: see docs/README.md
```

Branching: work lands on **`develop`** and is merged to **`main`** at the end of
a wave ([CONTRIBUTING](CONTRIBUTING.md#git)).

---

## Licence and legal

**Copyright © 2026 Ashutosh Sinha &lt;ajsinha@gmail.com&gt;. All rights reserved.**

This repository is **proprietary and confidential**. No licence is granted except by separate
written agreement with the owner. You may not copy, modify, distribute, disclose, or use this work
— including to train or evaluate any machine-learning model — without written permission.
See **[LICENSE](LICENSE)** for the full terms and **[NOTICE](NOTICE)** for trademarks, third-party
references, and the data statement.

"PRAMA", the Prama logo (the *Pramāṇa Prism*), the Prama attestation seal, and the slogans
*"Declare it. Prove it. Trust it."*, *"Trust, proven."*, and *"The instrument of valid knowledge"*
are trademarks of Ashutosh Sinha. All third-party names and marks are the property of their
respective owners and are used nominatively for research and comparison; no endorsement or
affiliation is implied.

Licensing enquiries: **ajsinha@gmail.com**

<div align="center">
<br/>
<img src="docs/assets/prama-mark.svg" width="40" alt=""/>
<br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i></sub>
</div>
