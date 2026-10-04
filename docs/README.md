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
| **new to it** | [How Prama fits together](architecture/README.md): every component in one page, then one page each, with diagrams, real screenshots and examples |
| **running Prama** | [QUICKSTART](../QUICKSTART.md), then [operations/](operations/README.md): runbook, troubleshooting, CLI and configuration reference |
| **running it from an IDE** | [PyCharm and IntelliJ IDEA](developer/ide.md): the interpreter, the shared run configurations, live reload, debugging |
| **extending it** | [Developer guides](developer/README.md): a connector, a PQL function, a validator, a model provider, a delegate, a table, an endpoint |
| **scripting it** | [The Python SDK](sdk/README.md): everything the console does, from Python, against your running server |
| **running agents beside the data** | [The agent operator's guide](agent/README.md) |
| **evaluating it** | [00 Executive Summary](corpus/00-executive-summary.md), then [15 §2.4](corpus/15-evaluation-benchmark-methodology.md) for what has actually been measured |
| **auditing it** | [13 §6.2a](corpus/13-security-governance-compliance.md) and `scripts/verify_evidence.py`, which checks evidence without Prama |
| **asking what is done** | [19 Implementation Roadmap](corpus/19-implementation-roadmap.md): the authority, marker by marker |
| **asking what is left** | [Remaining work](corpus/remaining-work.md): the open items, ordered; the roadmap stays the authority |

## How the documentation is organised

Each folder is the one home for one kind of fact. A fact stated in a second
folder is a pointer to the first, never a copy: a copy drifts, and it drifts in
the flattering direction.

| Folder | What lives there | The authority for |
|---|---|---|
| [architecture/](architecture/README.md) | How every component works and fits, as built | Module maps, data flow, what calls what |
| [developer/](developer/README.md) | How to extend or change each component, with tested examples | Interfaces, registration, conformance |
| [sdk/](sdk/README.md) | The Python SDK, resource by resource | Client usage |
| [agent/](agent/README.md) | Installing and running the agent daemon | Operating an agent |
| [operations/](operations/README.md) | Running the server; the CLI, configuration and metrics references (generated) | Operations |
| [corpus/](corpus/00-executive-summary.md) | The numbered design corpus, below | Intent, requirements, rationale |
| [design/](design/agent-fleet-http.md) | Design notes for single features | A feature's design decisions |
| [reference/](reference/glossary.md) | Glossary and brand | Terms and names |
| [publications/](publications/paper/README.md) | The paper, the Medium article, the deck | — |
| [assets/](assets/) | Images: the mark, diagrams drawn by `tools/docs/diagrams.py`, screenshots taken by `tools/docs/screenshots.py` | — |

The console's **Help** renders every document here, with a card derived from
its heading and from the "What it answers" column of these tables.

**Every design document opens with an "As built" section** saying what of it
exists, what does not, and what is built but has never met the real thing. The
design corpus describes the intent; that section describes the state. Where they
differ, `docs/corpus/19` decides.

---

## Reading order

| # | Document | What it answers |
|---|----------|-----------------|
| 00 | [Executive Summary](corpus/00-executive-summary.md) | What we are building, why it wins, what it costs |
| 01 | [Landscape Survey](corpus/01-landscape-survey.md) | Research, commercial, and open-source state of the art |
| 02 | [Gap Analysis & Positioning](corpus/02-gap-analysis-and-positioning.md) | Where the market is broken; our thesis and moats |
| **03** | **[Business Semantic Layer & Data Estate Model](corpus/03-business-semantic-layer.md)** | **The conceptual heart: datasets, attributes, concepts, relationships, journeys** |
| 04 | [Functional Requirements](corpus/04-requirements-functional.md) | FR-### catalogue across 22 capability areas |
| 05 | [Non-Functional Requirements](corpus/05-requirements-nonfunctional.md) | NFR-### catalogue: scale, latency, resilience, cost |
| 06 | [Reference Architecture](corpus/06-architecture.md) | Planes, services, deployment topologies |
| 07 | [PQL — Rule Language Specification](corpus/07-rule-language-spec.md) | Declarative DSL, IR, semantics, compilation |
| 08 | [AI/ML Capabilities](corpus/08-ai-ml-capabilities.md) | Monitors, rule induction, calibration, agents, MLOps |
| 09 | [Connectivity & Formats](corpus/09-connectivity-and-formats.md) | Every source, feed, protocol, and codec we support |
| 10 | [UX & Conversational Interface](corpus/10-ux-and-chat-interface.md) | Personas, screens, interaction model, chat agent |
| 11 | [Reporting, Alerting & Learning](corpus/11-reporting-alerting-learning.md) | Scorecards, trust propagation, incidents, feedback loop |
| 12 | [Banking & Finance Domain Pack](corpus/12-banking-domain-pack.md) | BCBS 239, regulations, message standards, reference data |
| 13 | [Security, Governance & Compliance](corpus/13-security-governance-compliance.md) | AuthN/Z, tenancy, privacy, model risk, evidence & audit |
| 14 | [Data Model & APIs](corpus/14-data-model-and-apis.md) | Canonical entities, REST/gRPC, events, SDKs, MCP |
| 15 | [Evaluation & Benchmark Methodology](corpus/15-evaluation-benchmark-methodology.md) | How we *prove* "best in world" |
| 16 | [Roadmap & Delivery Plan](corpus/16-roadmap-and-delivery-plan.md) | Phases, teams, build-vs-buy, milestones |
| 17 | [Risks & Open Questions](corpus/17-risks-and-open-questions.md) | What could kill this, and decisions still open |
| 18 | [Technology Stack & Reuse from DishtaYantra](corpus/18-technology-stack.md) | Languages, frameworks, UI stack, deployment, and what to reuse |
| 19 | [Implementation Roadmap — Ten Waves](corpus/19-implementation-roadmap.md) | The engineering plan: what gets built, in what order, and what done means |
| 20 | [Competitive Analysis](corpus/20-competitive-analysis.md) | Head-to-head against Solidatus, Manta, Alation, Collibra, Monte Carlo and the rest — including where we are behind |
| 21 | [How We Win](corpus/21-how-we-win.md) | The plan to beat them: three asymmetric unlocks, honest moat ratings, and the traps we set |
| 22 | [Distributed Execution: Prama Agents](corpus/22-distributed-execution.md) | Agents beside the data: outbound-only, residency-bounded, surviving an outage |
| 23 | [Intelligence and Lineage Roadmap](corpus/23-intelligence-and-lineage-roadmap.md) | Waves 12–18: the LLM gateway, lineage store and workbench, code-to-lineage, steward agents, DQ delegates, and the lineage scope (what Prama reads, and what it deliberately does not). Design notes in [design/](design/) |
| — | [Remaining work](corpus/remaining-work.md) | The open items, ordered by what they block; the roadmap stays the authority |

## Design notes

| Note | What it answers |
|---|---|
| [The agent fleet over HTTP](design/agent-fleet-http.md) | The contract between the server and an agent: enrolment, signing, claims, dedupe |
| [Code lineage and steward agents](design/code-lineage-and-steward-agents.md) | Reading lineage from application code, and agents that read and propose but never approve |
| [DQ delegates](design/dq-delegates.md) | Python checks PQL cannot say: why the delegate measures and Prama decides |
| [The LLM gateway](design/llm-gateway.md) | One door for every model call: providers, profiles, budgets, residency and the call ledger |
| [Gap analysis: Manta and Alation](design/gap-manta-alation.md) | What the lineage incumbents do that Prama does not, and which gaps matter |

## Reference

| Document | What it answers |
|---|---|
| [Glossary](reference/glossary.md) | Terms of art |
| [Brand](reference/brand.md) | Name, mark, slogan, palette, voice |

## Publications and reviews

| Document | What it answers |
|---|---|
| [Academic paper](publications/paper/README.md) | *Data Quality as Justified Belief*: the [PDF](publications/paper/data-quality-as-justified-belief.pdf), its LaTeX source, bibliography and experiment plan |
| [The paper as an article](publications/paper/data-quality-as-justified-belief-article.md) | A long-form article version for engineers and data owners |
| [Experiment plan](publications/paper/experiment-plan.md) | The experimental protocol written before the code existed |
| [The Medium article](publications/medium/README.md) | How the article and its diagrams are built |
| [*Your dashboard is green. Can you prove it?*](publications/medium/your-dashboard-is-green.md) | Nine design ideas, with diagrams and examples |
| [Deck](publications/deck/Prama-Evidence-First-Data-Quality.pptx) | 45 slides for the people who must stand behind a number; built from [`tools/deck/`](../tools/deck/GUIDE.md) and audited as rendered |
| [Adversarial review, 2026-09-11](reviews/2026-09-11-adversarial-review.md) | Five reviewers told to find defects rather than praise, and what was done about each |

## The one-paragraph thesis

Existing tools start from the **physical** estate — crawl the warehouse, monitor the columns —
and so they serve engineers, produce uncalibrated alerts, score every asset in isolation, and
leave no evidence a regulator will accept. Prama starts from the **business** estate: a semantic
layer in which owners declare datasets, attribute meanings, and the relationships between them
(*reconciles-with*, *derives-from*, *feeds*, *same-entity-as*). Those declarations compile into
executable controls; AI proposes and calibrates them but never adjudicates them; a deterministic
engine executes them at the source and emits immutable, replayable evidence; trust propagates
along lineage; and the whole estate is re-examined on an adaptive cadence so no finding is ever
stale. See [02](corpus/02-gap-analysis-and-positioning.md) and [03](corpus/03-business-semantic-layer.md).

## Document conventions

- **FR-<AREA>-###** functional requirement, **NFR-###** non-functional, **CON-###** constraint,
  **ASM-###** assumption, **RSK-###** risk, **DEC-###** open decision, **GAP-#** market gap,
  **S#** superiority criterion.
- Priority: **P0** (must-have for GA), **P1** (competitive parity), **P2** (differentiator, post-GA),
  **P3** (research / long horizon).
- Where an external claim is load-bearing, the source is linked inline.
- **One fact, one home.** See *How the documentation is organised*: a document
  that needs a fact another one owns links to it rather than restating it.
- **Diagrams and screenshots are rebuilt by a command**, never edited by hand:
  `python tools/docs/diagrams.py` (audited by Inkscape; `--check` fails a stale
  one) and `python tools/docs/screenshots.py` (a real server, the case studies,
  headless Chrome).
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
