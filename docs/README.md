# Prama — Documentation Index

<img src="assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="400"/>

> **prama** (Sanskrit *pramā*, प्रमा) — *valid cognition; knowledge that is true and justified*.
> Related: *pramāṇa* (प्रमाण), *the instrument by which valid knowledge is obtained*.

**Prama is a business-owned data quality control plane.** Business owners and data architects
declare what their data means and how it relates; Prama reaches out through configured connectors,
reads the data, re-examines it continuously, and turns those declarations into calibrated,
provable quality conclusions — through a console, a Git repo, or a conversation.

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
| — | [Brand](brand.md) | Name, mark, slogan, palette, voice |
| — | [Glossary](glossary.md) | Terms of art |
| — | [Academic Paper](paper/) | Manuscript, outline, bibliography, experiment plan |

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

---

<div align="center">
<img src="assets/prama-mark.svg" width="30" alt=""/><br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.<br/>
See <a href="../LICENSE">LICENSE</a> and <a href="../NOTICE">NOTICE</a>. Third-party names and marks are the property of their respective owners.</sub>
</div>
