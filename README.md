<div align="center">

<img src="docs/assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="430"/>

### Declare it. &nbsp;Prove it. &nbsp;Trust it.

**A business-owned, AI-native, evidence-first data quality control plane.**
Banking and capital markets first. Any industry next.

<sub>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved · Proprietary and confidential<br/>
<a href="LICENSE">LICENSE</a> · <a href="NOTICE">NOTICE</a> · <a href="docs/">Documentation</a>
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
**[docs/02 — Gap Analysis & Positioning](docs/02-gap-analysis-and-positioning.md)**.

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
The worked example is in **[docs/07 §10](docs/07-rule-language-spec.md)**.

---

## Documentation

Start with **[docs/00 — Executive Summary](docs/00-executive-summary.md)**, then
**[docs/03 — The Business Semantic Layer](docs/03-business-semantic-layer.md)** (the conceptual heart).

| # | Document | What it answers |
|---|---|---|
| 00 | [Executive Summary](docs/00-executive-summary.md) | What we are building, why it wins, what it costs |
| 01 | [Landscape Survey](docs/01-landscape-survey.md) | Research, commercial, and open-source state of the art |
| 02 | [Gap Analysis & Positioning](docs/02-gap-analysis-and-positioning.md) | Seven structural gaps; the product thesis; competitive stance |
| **03** | **[Business Semantic Layer & Data Estate Model](docs/03-business-semantic-layer.md)** | **Datasets, attributes, concepts, relationships, journeys, continuous re-examination** |
| 04 | [Functional Requirements](docs/04-requirements-functional.md) | 350+ FR-### across 22 capability areas |
| 05 | [Non-Functional Requirements](docs/05-requirements-nonfunctional.md) | Scale, latency, resilience, security, cost — with measurable targets |
| 06 | [Reference Architecture](docs/06-architecture.md) | Planes, services, compilation pipeline, deployment topologies |
| 07 | [PQL — Rule Language Specification](docs/07-rule-language-spec.md) | Grammar, assertion catalogue, semantics, IR, worked example |
| 08 | [AI/ML Capabilities](docs/08-ai-ml-capabilities.md) | Constraint mining, LLM induction, conformal calibration, model risk |
| 09 | [Connectivity & Formats](docs/09-connectivity-and-formats.md) | Every source, feed, protocol, and codec |
| 10 | [UX & Conversational Interface](docs/10-ux-and-chat-interface.md) | Estate map, workflows, the chat agent and its safety contract |
| 11 | [Reporting, Alerting & Learning](docs/11-reporting-alerting-learning.md) | Scoring, trust propagation, alert economics, the feedback loop |
| 12 | [Banking & Finance Domain Pack](docs/12-banking-domain-pack.md) | BCBS 239, regulations, message standards, reference reconciliations |
| 13 | [Security, Governance & Compliance](docs/13-security-governance-compliance.md) | Threat model, evidence ledger, attestation, compliance posture |
| 14 | [Data Model & APIs](docs/14-data-model-and-apis.md) | Canonical entities, REST/gRPC, events, SDKs, GitOps, MCP |
| 15 | [Evaluation & Benchmark Methodology](docs/15-evaluation-benchmark-methodology.md) | How we *prove* "best in world" — and how it could fail |
| 16 | [Roadmap & Delivery Plan](docs/16-roadmap-and-delivery-plan.md) | Phases, teams, build/buy, open-source strategy |
| 17 | [Risks & Open Questions](docs/17-risks-and-open-questions.md) | Risk register and open decisions |
| — | [Brand](docs/brand.md) | Name, mark, slogan, palette, voice |
| — | [Glossary](docs/glossary.md) | Terms of art |
| — | [Academic Paper](docs/paper/) | Manuscript, bibliography, experiment plan |

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

Details and threats to validity: **[docs/15](docs/15-evaluation-benchmark-methodology.md)**.

---

## Research

Five contributions, targeting **ACM JDIQ** with a **VLDB Industrial** companion — see
**[docs/paper/](docs/paper/)**:

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

**Pre-implementation.** This repository currently contains the complete research survey,
requirements corpus, architecture, language specification, evaluation methodology, and academic
manuscript. Figures marked as targets, gates, or ⟨TBD⟩ are **objectives, not measured results** —
see [NOTICE §6](NOTICE).

Repository layout:

```
prama/
├── README.md          ← you are here
├── LICENSE            ← proprietary; all rights reserved
├── NOTICE             ← legal notice, trademarks, third-party references
└── docs/
    ├── 00–17          ← the analysis, requirements, and design corpus
    ├── assets/        ← logo, seal, favicon, brand preview
    ├── brand.md · glossary.md
    └── paper/         ← manuscript, bibliography, experiment plan
```

Branching: work lands on **`develop`** and is merged to **`main`**.

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
