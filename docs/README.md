# Prama — Documentation Index

<img src="assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="400"/>

> **prama** (Sanskrit *pramā*, प्रमा) — *valid cognition; knowledge that is true and justified*.
> Related: *pramāṇa* (प्रमाण), *the instrument by which valid knowledge is obtained*.

**Prama is a business-owned data quality control plane.** Business owners and data architects
declare what their data means and how it relates; Prama reaches out through configured connectors,
reads the data, re-examines it continuously, and turns those declarations into calibrated,
provable quality conclusions — through a console, a Git repo, or a conversation.

---

## Start here

| If you are… | Read |
|---|---|
| **running Prama** | [QUICKSTART](../QUICKSTART.md), then [operations/](operations/) — runbook, troubleshooting, CLI and configuration reference |
| **evaluating it** | [00 Executive Summary](00-executive-summary.md), then [15 §2.4](15-evaluation-benchmark-methodology.md) for what has actually been measured |
| **building on it** | [03 Semantic Layer](03-business-semantic-layer.md) and [07 PQL](07-rule-language-spec.md) |
| **auditing it** | [13 §6.2a](13-security-governance-compliance.md) and `scripts/verify_evidence.py`, which checks evidence without Prama |
| **asking what is done** | [19 Implementation Roadmap](19-implementation-roadmap.md) — the authority, marker by marker |
| **asking what is left** | [Remaining work](remaining-work.md) — the open items, ordered; the roadmap stays the authority |

**Every design document opens with an "As built" section** saying what of it
exists, what does not, and what is built but has never met the real thing. The
design corpus describes the intent; that section describes the state. Where they
differ, `docs/19` decides.

---

## Reading order

| # | Document | What it answers |
|---|----------|-----------------|
| 00 | [Executive Summary](00-executive-summary.md) | What we are building, why it wins, what it costs |
| 01 | [Landscape Survey](01-landscape-survey.md) | Research, commercial, and open-source state of the art |
| 02 | [Gap Analysis & Positioning](02-gap-analysis-and-positioning.md) | Where the market is broken; our thesis and moats |
| **03** | **[Business Semantic Layer & Data Estate Model](03-business-semantic-layer.md)** | **The conceptual heart: datasets, attributes, concepts, relationships, journeys** |
| 04 | [Functional Requirements](04-requirements-functional.md) | FR-### catalogue across 22 capability areas |
| 05 | [Non-Functional Requirements](05-requirements-nonfunctional.md) | NFR-### catalogue: scale, latency, resilience, cost |
| 06 | [Reference Architecture](06-architecture.md) | Planes, services, deployment topologies |
| 07 | [PQL — Rule Language Specification](07-rule-language-spec.md) | Declarative DSL, IR, semantics, compilation |
| 08 | [AI/ML Capabilities](08-ai-ml-capabilities.md) | Monitors, rule induction, calibration, agents, MLOps |
| 09 | [Connectivity & Formats](09-connectivity-and-formats.md) | Every source, feed, protocol, and codec we support |
| 10 | [UX & Conversational Interface](10-ux-and-chat-interface.md) | Personas, screens, interaction model, chat agent |
| 11 | [Reporting, Alerting & Learning](11-reporting-alerting-learning.md) | Scorecards, trust propagation, incidents, feedback loop |
| 12 | [Banking & Finance Domain Pack](12-banking-domain-pack.md) | BCBS 239, regulations, message standards, reference data |
| 13 | [Security, Governance & Compliance](13-security-governance-compliance.md) | AuthN/Z, tenancy, privacy, model risk, evidence & audit |
| 14 | [Data Model & APIs](14-data-model-and-apis.md) | Canonical entities, REST/gRPC, events, SDKs, MCP |
| 15 | [Evaluation & Benchmark Methodology](15-evaluation-benchmark-methodology.md) | How we *prove* "best in world" |
| 16 | [Roadmap & Delivery Plan](16-roadmap-and-delivery-plan.md) | Phases, teams, build-vs-buy, milestones |
| 17 | [Risks & Open Questions](17-risks-and-open-questions.md) | What could kill this, and decisions still open |
| 18 | [Technology Stack & Reuse from DishtaYantra](18-technology-stack.md) | Languages, frameworks, UI stack, deployment, and what to reuse |
| 19 | [Implementation Roadmap — Ten Waves](19-implementation-roadmap.md) | The engineering plan: what gets built, in what order, and what done means |
| 20 | [Competitive Analysis](20-competitive-analysis.md) | Head-to-head against Solidatus, Manta, Alation, Collibra, Monte Carlo and the rest — including where we are behind |
| 21 | [How We Win](21-how-we-win.md) | The plan to beat them: three asymmetric unlocks, honest moat ratings, and the traps we set |
| 22 | [Distributed Execution: Prama Agents](22-distributed-execution.md) | Agents beside the data: outbound-only, residency-bounded, surviving an outage |
| 23 | [Intelligence and Lineage Roadmap](23-intelligence-and-lineage-roadmap.md) | Waves 12–18: the LLM gateway, lineage store and workbench, code-to-lineage, steward agents, DQ delegates, and the lineage scope (what Prama reads, and what it deliberately does not). Design notes in [design/](design/) |
| — | **[Operations](operations/)** | **Runbook, troubleshooting, CLI reference, configuration reference** |
| — | [Brand](brand.md) | Name, mark, slogan, palette, voice |
| — | [Glossary](glossary.md) | Terms of art |
| — | [Medium article](medium/your-dashboard-is-green.md) | *Your dashboard is green. Can you prove it?* Nine design ideas, with diagrams and examples |
| — | [Deck](deck/Prama-Evidence-First-Data-Quality.pptx) | 45 slides for the people who must stand behind a number; built from [`tools/deck/`](../tools/deck/GUIDE.md) and audited as rendered |
| — | [Academic Paper](paper/) | [*Data Quality as Justified Belief*](paper/data-quality-as-justified-belief.pdf): the paper, its LaTeX source, a long-form [article](paper/data-quality-as-justified-belief-article.md), bibliography, experiment plan |

## The one-paragraph thesis

Existing tools start from the **physical** estate — crawl the warehouse, monitor the columns —
and so they serve engineers, produce uncalibrated alerts, score every asset in isolation, and
leave no evidence a regulator will accept. Prama starts from the **business** estate: a semantic
layer in which owners declare datasets, attribute meanings, and the relationships between them
(*reconciles-with*, *derives-from*, *feeds*, *same-entity-as*). Those declarations compile into
executable controls; AI proposes and calibrates them but never adjudicates them; a deterministic
engine executes them at the source and emits immutable, replayable evidence; trust propagates
along lineage; and the whole estate is re-examined on an adaptive cadence so no finding is ever
stale. See [02](02-gap-analysis-and-positioning.md) and [03](03-business-semantic-layer.md).

## Document conventions

- **FR-<AREA>-###** functional requirement, **NFR-###** non-functional, **CON-###** constraint,
  **ASM-###** assumption, **RSK-###** risk, **DEC-###** open decision, **GAP-#** market gap,
  **S#** superiority criterion.
- Priority: **P0** (must-have for GA), **P1** (competitive parity), **P2** (differentiator, post-GA),
  **P3** (research / long horizon).
- Where an external claim is load-bearing, the source is linked inline.
- **Generated documents carry a banner saying so.** `operations/cli-reference.md`
  and `operations/configuration-reference.md` are built from the argument parser
  and the shipped configuration by `scripts/generate_docs.py`; the gate refuses a
  version that has drifted. Edit the code, not the prose.
- **Advertised test counts are derived from a green run** by
  `scripts/sync_test_counts.py`, never typed. A number in prose rots the first
  time somebody adds a test.

---

<div align="center">
<img src="assets/prama-mark.svg" width="30" alt=""/><br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.<br/>
See <a href="../LICENSE">LICENSE</a> and <a href="../NOTICE">NOTICE</a>. Third-party names and marks are the property of their respective owners.</sub>
</div>
