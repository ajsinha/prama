# 00 — Executive Summary

<img src="assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="380"/>

---

## As built

This summary was written before the product existed. It now does.

Eleven waves are complete. The semantic layer, PQL and its engine-neutral IR,
the evidence ledger with deterministic replay, declaration-derived controls,
mining and induction, monitoring and calibration, the console, the banking pack,
six of eight GA connectors, and the enterprise surface — SSO, SCIM, residency,
customer-managed keys, an operator, an offline bundle with publisher signing —
are all in `src/prama/`.

**Every number in this document that is a target remains a target.** Detection
quality, alert precision, time-to-control, connector breadth against the ~45 GA
figure: these are objectives, and `NOTICE §6` governs how they may be quoted.
Where something is built but has not met the real thing — the operator has not
seen a Kubernetes API server, no cloud KMS has been exercised, no disconnected
install has been performed — the document describing it says so in those words.

`docs/19` is the authority on what is done, and it distinguishes *built*,
*built but unverified*, and *not built*.

---

## The proposition

**Prama is a business-owned data quality control plane.** Business owners and data architects
declare, in business terms, what their datasets mean and how they relate to one another. Prama
reaches out through configured connectors, reads the data, re-examines it continuously, and turns
those declarations into calibrated, provable quality conclusions — reachable through a console, a
Git repository, or a conversation.

The name is Sanskrit: *pramā* (प्रमा), **valid knowledge**; *pramāṇa*, **the instrument by which
valid knowledge is obtained**. The slogan states the architecture: **Declare it. Prove it. Trust it.**

---

## Why now

- Poor data quality costs the average enterprise **~$12.9M/year** (Gartner reference-customer
  survey), and 15–25% of revenue by MIT Sloan estimates.
- In banking it is enforced, not estimated: the FCA has fined firms **~£95M** for MiFID
  transaction-reporting failures and **~£34.5M** for EMIR — including **Goldman Sachs >£34M for
  220M+ reporting errors** and **UBS >£27M for 135M+**.
- Gartner's 2024 poll named **poor data quality the #1 obstacle to GenAI**, which moved data quality
  from a hygiene budget to the gate on the AI budget.
- Gartner's 2025 Magic Quadrant re-weighted the entire category toward **AI-driven rule generation,
  anomaly detection, and automated stewardship** — four incumbents dropped out, three newcomers
  entered. The category is in motion.

## Why the incumbents leave a gap

Fifty-plus vendors compete, and DataKitchen's 2026 landscape names the structural problem:
*"catalog vendors added quality checks, observability vendors added testing… observability catches a
load that silently stopped; quality testing catches a load that ran perfectly and delivered wrong
numbers. Neither substitutes for the other."*

Buyers assemble three to five products that share no rule model, no evidence model, no scoring
model, and no incident model. Seven structural gaps follow
([02](02-gap-analysis-and-positioning.md)):

1. **Three disjoint paradigms** — declarative rules, ML monitors, and business judgement live in
   separate products.
2. **Uncalibrated alerting** — no product emits a statistically interpretable alarm rate; alert
   fatigue is the documented cause of abandonment.
3. **Rules locked to an engine** — replatform, rewrite every control, fail the audit again.
4. **Assets scored in isolation** — trust never propagates along lineage, so a "98%" gold table can
   rest entirely on a failing bronze table.
5. **No evidence model** — nothing is immutable, replayable, or attestable, so banks still run
   control attestation in spreadsheets.
6. **Cross-system truth is out of scope** — reconciliation, banking's most expensive quality
   failure, is sold separately at high prices.
7. **The interface serves engineers, not the accountable** — the people who own the numbers cannot
   author or attest to a control without an engineer.

---

## What we build

**A neuro-symbolic, evidence-first control plane over a business semantic layer.**

| Layer | What it does | Why it is different |
|---|---|---|
| **Business semantic layer** ([03](03-business-semantic-layer.md)) | Owners declare datasets (a table, a database, a feed, many feeds), attribute meanings, business concepts, and typed **relationships** (`reconciles-with`, `derives-from`, `feeds`, `same-entity-as`) | Nobody else lets the business describe the estate in a form that *executes*. A declaration becomes a control automatically. |
| **PQL + engine-neutral IR** ([07](07-rule-language-spec.md)) | One declarative language for rules, monitors, reconciliations, and contracts; compiled to SQL (25 dialects), Spark, Flink, Arrow/DuckDB, and a native feed scanner | Write once, execute at source, prove semantic equivalence by a conformance suite |
| **Calibrated intelligence** ([08](08-ai-ml-capabilities.md)) | Constraint mining + LLM rule authoring fused; every statistical monitor emits a **conformal p-value**; alerting is FDR-controlled under a user-declared false-alarm budget | AI *authors and calibrates*; a deterministic engine *decides*. No product on the market emits a calibrated alarm rate. |
| **Evidence ledger** ([13](13-security-governance-compliance.md)) | Every execution appends an immutable, hash-linked, signed, **deterministically replayable** record | The artefact BCBS 239, SOX, and SR 11-7 actually demand — and the hardest thing to retrofit |
| **Trust propagation** ([11](11-reporting-alerting-learning.md)) | Quality flows along column-level lineage with transformation-aware attenuation | Answers "can I trust this number?" from first principles |
| **Two coequal surfaces** ([10](10-ux-and-chat-interface.md)) | An estate map and control console for business users, **plus a conversational agent** that authors, explains, investigates, and reports — every mutation a reviewable proposal | The accountable owner becomes the author, which is itself an audit improvement |
| **Continuous re-examination** ([03 §6](03-business-semantic-layer.md#6-continuous-re-examination--findings-that-never-go-stale)) | Adaptive cadence per dataset; every finding stamped with freshness; metadata drift raised as an incident to the declaring owner | No finding is ever silently stale |
| **Breadth** ([09](09-connectivity-and-formats.md)) | 120+ certified connectors: warehouses, lakehouses, RDBMS, NoSQL, streams, APIs, files, **COBOL/EBCDIC/VSAM**, and **12+ financial message standards** (ISO 20022, SWIFT MT, FIX, FpML, FINOS CDM, XBRL, ISO 8583, NACHA/SEPA…) | Banks' authoritative data is not in a warehouse |
| **Domain packs** ([12](12-banking-domain-pack.md)) | Banking pack at GA: concepts, validators (LEI/ISIN/IBAN/BIC check digits), calendars, message parsers, reference reconciliations, and a regulatory control catalogue with citations | "Banking-first, industry-general" as architecture, not slogan |

---

## The claim, made falsifiable

Nine superiority criteria are **release gates**, measured against named baselines on a public
benchmark we build and publish (DQ-Bench and FinDQ-Bench), plus a 90-day blind live-shadow
evaluation at three banks ([15](15-evaluation-benchmark-methodology.md)):

| | Criterion | Target |
|---|---|---|
| S1 | Detection F1 vs. best baseline | ≥ +15% overall, ≥ +40% on semantic defects |
| S2 | Alert precision, live production | ≥ 0.85 at declared FDR ≤ 0.10 (baselines: 0.3–0.6) |
| S3 | Calibration error | ≤ 0.02 across all drift regimes |
| S4 | Time to a reviewed control | ≤ 3 min (vs. 25–60 min hand-authored) |
| S5 | Coverage after one week | ≥ 80% of columns, ≥ 95% of CDEs |
| S6 | Certified connectors | ≥ 120, incl. ≥ 12 financial message standards |
| S7 | Detection latency | p95 ≤ 60 s streaming |
| S8 | Audit readiness | 100% pass an independent Big-4 RDARR script |
| S9 | Cost per billion rows validated | ≤ 50% of naive full-scan |

Negative results are published alongside positive ones. The falsifiability is the credibility.

---

## Go to market

**Beachhead:** Tier-1/Tier-2 bank Risk and Finance data offices, on two use cases with existing
budget and direct loss exposure — **BCBS 239 control attestation** and **transaction-reporting
pre-submission validation / sub-ledger↔GL reconciliation**.

**Expansion:** more control types within the same customer, then Insurance, Payments, Healthcare,
Telco, Energy, and Public Sector via Domain Packs — with **no core engineering** per industry.

**Distribution:** an Apache-2.0 core (PQL, IR, compiler, connector SDK, benchmark) for bottom-up
adoption and standards credibility; a commercial control plane (semantic layer at scale, evidence,
workflow, learning, chat, multi-tenancy, packs) as the enterprise purchase.

**Pricing principle:** charge by assets and controls, never by data volume — the value compounds
with coverage and the pricing must not fight it.

---

## Plan and investment

| Phase | Months | Engineering | Outcome |
|---|---|---|---|
| 0 Foundations | 0–4 | 22 | Semantic layer, PQL/IR, evidence ledger, 5 connectors, first replay |
| 1 Private beta | 4–9 | 22→30 | Reconciliation, calibrated monitors, induction, banking pack v1, 3 design partners in shadow |
| 2 **GA** | 9–15 | 45 | 45 connectors, streaming, on-prem/air-gap, security posture, all S1–S9 gates, benchmark + paper published |
| 3 Scale & depth | 15–24 | 64 | 85 connectors, trust propagation, repair, ER, 3 more packs, SOC 2 / ISO 27001 |
| 4 Category leadership | 24–36 | 64+ | Utility-aware remediation, transfer learning, federated deployments, community benchmark |

---

## Research contributions

The work is genuinely novel, and we intend to say so in public
([paper/](paper/)) — targeting **ACM JDIQ** with an industrial-track companion at **VLDB/SIGMOD**:

1. A **unified quality assertion algebra and engine-neutral IR** with formal semantics and a
   cross-engine equivalence result.
2. **Risk-controlled data quality alerting**: conformal calibration plus hierarchical FDR over the
   asset × attribute × check lattice, with adaptive weighting under drift.
3. **Neuro-symbolic rule induction**: fusing algorithmic constraint discovery with template-constrained
   LLM authorship, evaluated on coverage, precision, and steward acceptance.
4. **Lineage-aware trust propagation** as a semiring over the column-level lineage DAG.
5. **DQ-Bench / FinDQ-Bench**: the first public, defect-labelled, cross-system enterprise data
   quality benchmark, with a banking instantiation.

---

## The three things that decide whether this works

1. **Do business owners actually declare?** (`ASM-010`) — the semantic layer is the moat and the
   thesis. Progressive formalisation, inference-first with confirm/correct, and an estate-maturity
   metric are how we make declaring rational rather than dutiful.
2. **Does calibration hold on real financial data?** (`ASM-011`, `RSK-10`) — proven on FinDQ-Bench
   in Phase 1, before it becomes a promise, with visible degradation when assumptions fail.
3. **Can we outrun the platforms and the sales cycle?** (`RSK-01`, `RSK-03`) — by owning the
   cross-system, regulated, feed-based 40% the platforms cannot reach, and by landing bottom-up with
   open source while the enterprise deal matures.

Everything else is execution.

---

<div align="center">
<img src="assets/prama-mark.svg" width="30" alt=""/><br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.<br/>
See <a href="../LICENSE">LICENSE</a> and <a href="../NOTICE">NOTICE</a>. Third-party names and marks are the property of their respective owners.</sub>
</div>
