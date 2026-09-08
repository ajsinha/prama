<img src="assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

> ***pramā*** (Sanskrit **प्रमा**) — *valid knowledge: a cognition that is both true and arrived at
> by a reliable means*. Its companion ***pramāṇa*** (प्रमाण) is *the instrument by which valid
> knowledge is obtained*. Prama is that instrument for an organisation's data — it does not decide
> what is true, it is how a belief about data becomes **justified**.
>
> **Declare it. Prove it. Trust it.**


---
# 16 — Roadmap & Delivery Plan

---

## 1. Strategy in one page

**Sequence:** win a *narrow, expensive, evidence-hungry* problem in banking (regulatory control
attestation and reconciliation), then widen along two axes — more control types within the same
customer, and more industries via Domain Packs.

**Distribution:** an open-source core (engine, PQL, IR, connectors) to earn bottom-up adoption and
standards credibility, plus a commercial control plane (semantic layer at scale, evidence,
workflow, learning, chat, multi-tenancy, support) that is what an enterprise actually buys.

**Proof:** publish the benchmark and the research. In a market where every vendor claims "AI-powered
data quality," a falsifiable, reproducible claim is the strongest differentiator available.

---

## 2. Phases

### Phase 0 — Foundations (months 0–4)
*Goal: the thing that makes everything else possible.*

- Semantic layer core: Dataset, Attribute, Concept, Relationship, Journey, Binding, Connection;
  bitemporal store; versioning and approval.
- PQL v0.9: parser, AST, IR, type checker, and **two backends** (ANSI SQL/Postgres + Arrow/DuckDB).
- Evidence ledger with hash chaining and deterministic replay — built now, because it cannot be
  retrofitted (`AD-03`).
- Connectors: Postgres, Snowflake, S3+CSV/Parquet, SFTP feed, Kafka.
- Profiler + metric history store.
- Minimal console: connect → declare → profile → author → run → see evidence.
- CI: IR conformance suite, property-based semantic-equivalence tests.

**Exit:** a real dataset declared by a non-engineer, controls derived from the declaration, evidence
replayed successfully.

### Phase 1 — Private beta (months 4–9)
*Goal: three design partners running real controls in shadow.*

- Backends: Snowflake, Databricks SQL, BigQuery, Spark. Assertion fusion and the sampling planner.
- Reconciliation engine (`FR-REC`) with break workflow — the banking wedge.
- Statistical monitors with **conformal calibration and FDR-controlled alerting** (the research core).
- Rule induction v1: constraint mining + LLM authoring with template-constrained decoding.
- Incident management, RCA v1, alert routing.
- Scorecards, dimension scoring, attestation v1.
- Banking pack v1: semantic types + validators, SWIFT MT/MX, FIX, calendars, BCBS 239 catalogue.
- Estate map v1; no-code rule builder; chat assistant v1 (ask + author).
- Continuous re-examination with adaptive cadence (`FR-REF`).

**Exit:** live-shadow evaluation running at 3 banks; S2/S3 measured; NPS from stewards, not buyers.

### Phase 2 — GA (months 9–15)
*Goal: a product a Tier-2 bank can buy, deploy, and pass an audit with.*

- ~45 certified connectors incl. COBOL/EBCDIC, XBRL, FpML, ISO 8583, NACHA/SEPA.
- Flink streaming backend; in-flight enforcement; quarantine and gate modes.
- Full security posture: SSO/SCIM, RBAC+ABAC, SoD, vault integration, audit export, SOC 2 readiness.
- On-prem and air-gapped deployment; BYO-LLM incl. self-hosted.
- Learning loop in production; challenger/champion promotion; degradation rollback.
- Entity resolution v1 (Fellegi–Sunter + active learning).
- Contracts: ODCS import/export, CI/CD gates, data diff.
- GitOps, Terraform provider, MCP server, Python/Java/TS SDKs.
- Reporting suite, GRC integrations, attestation with seal.
- **All S1–S9 gates met** ([15 §7](15-evaluation-benchmark-methodology.md#7-release-gates)).
- DQ-Bench + FinDQ-Bench published; paper submitted.

### Phase 3 — Scale & depth (months 15–24)
- Connector count to ~85; SaaS core-banking and capital-markets applications.
- **Trust propagation over lineage** in production (`FR-SCR-004`).
- Repair suggestion and constraint-aware advisory repair.
- Multivariate/relational anomaly detection; record-level trust.
- Unstructured & AI-readiness certification (`FR-UNS`).
- Domain packs: Insurance, Payments, Healthcare.
- Marketplace/registry for packs and connectors; partner SDK GA.
- SOC 2 Type II, ISO 27001 achieved.

### Phase 4 — Category leadership (months 24–36)
- Utility-aware remediation (research → product).
- Cross-tenant transfer learning on abstracted rule shapes (opt-in).
- Autonomous *proposal* agents operating continuously across the estate (still human-gated).
- Federated deployments across legal entities and jurisdictions.
- Packs: Telco, Energy, Public Sector, Manufacturing, Retail.
- Second and third research publications; benchmark becomes a community leaderboard.

---

## 3. Milestones

| # | Milestone | Phase | Success criterion |
|---|---|---|---|
| M1 | First evidence record replayed | 0 | Byte-identical verdict on re-execution |
| M2 | Business-declared dataset generates 8+ controls | 0 | Non-engineer completes it in ≤ 5 min |
| M3 | IR conformance green on 4 backends | 1 | 100% of constructs |
| M4 | First reconciliation break workflow closed end-to-end | 1 | At a design partner, on real data |
| M5 | Calibration within ±0.02 across 5 drift regimes | 1 | S3 met on DQ-Bench |
| M6 | Live-shadow precision ≥ 0.85 | 1→2 | Blind steward adjudication at ≥ 2 sites |
| M7 | Independent RDARR audit script passes 100% | 2 | Big-4 executed |
| M8 | Air-gapped install with local LLM | 2 | Full feature parity minus documented deltas |
| M9 | First paying Tier-2 bank in production | 2 | Signed, deployed, attesting |
| M10 | Benchmark + paper public | 2 | Submitted to JDIQ/VLDB industrial |
| M11 | 100k assets / 500k controls at one tenant | 3 | Within SLOs |
| M12 | Second industry pack sold | 3 | Proves the generalisation thesis commercially |

---

## 4. Team shape

| Team | Phase 0–1 | Phase 2 | Phase 3 | Charter |
|---|---|---|---|---|
| Language & Engine | 4 | 6 | 8 | PQL, IR, compiler, backends, conformance |
| Connectivity | 3 | 7 | 10 | Connectors, formats, feed handling, mainframe |
| Intelligence | 3 | 6 | 9 | Profiling, mining, monitors, calibration, induction, ER, RCA |
| Semantic Layer & Platform | 3 | 6 | 8 | Semantic model, scheduling, evidence, scoring, multi-tenancy |
| Experience | 3 | 6 | 9 | Console, estate map, chat, design system, accessibility |
| Domain (Banking) | 2 | 4 | 6 | Packs, regulatory catalogues, message standards, customer proof |
| Security & Compliance | 1 | 3 | 4 | Posture, certifications, model risk, evidence integrity |
| Research | 1 | 2 | 3 | Benchmark, papers, calibration theory, trust propagation |
| SRE / Delivery | 2 | 5 | 7 | SLOs, deployment modes, air-gap, customer delivery |
| **Total engineering** | **22** | **45** | **64** | |

Plus product (3→6), design (2→4), technical writing (1→3), and a field/solutions team from Phase 2.

**Non-obvious hires that matter disproportionately:** a former bank data-controls practitioner (not
a salesperson) to own the regulatory catalogue; a statistician who owns calibration and will refuse
to ship an uncalibrated number; and a technical writer from day one, because "explainable" is a
documentation property as much as an engineering one.

---

## 5. Build / buy / integrate

| Capability | Decision | Rationale |
|---|---|---|
| Rule language, IR, compiler | **Build** | The core moat; nothing existing is engine-neutral |
| Semantic layer | **Build** | The product thesis; no adequate primitive exists |
| Evidence ledger | **Build** (on object storage + Postgres) | Requirements are specific; blockchain products are overkill and operationally hostile |
| Connectors | **Build** core 45; **SDK + partners** for the tail; **integrate** Airbyte/Singer where licensing permits | Breadth is a moat but not all of it must be first-party |
| Constraint mining | **Adopt & harden** published algorithms (Metanome/Desbordante lineage) | Well-studied; reimplementation risk is low, value is in productisation |
| Anomaly detection | **Integrate** established libraries; **build** the calibration and selection layer | The calibration layer is the differentiator, not the detector |
| Entity resolution | **Integrate Splink** (Fellegi–Sunter) initially; build the workflow and active learning around it | Excellent, transparent, permissively licensed |
| LLM | **Integrate**, BYO, never train a foundation model | Table stakes to be model-agnostic |
| Catalog / lineage | **Integrate** (OpenMetadata, DataHub, Collibra, Purview, Unity) | Explicit non-goal (`CON-001`) |
| Address/reference data | **Integrate** (Experian, Melissa, GLEIF, OpenFIGI) | Explicit non-goal (`CON-004`) |
| Workflow/ticketing | **Integrate** (Jira, ServiceNow) with a native fallback | Enterprises will not move their workflow |
| BI | **Integrate + embed** | Explicit non-goal (`CON-005`) |

---

## 6. Open source strategy

**Open (Apache 2.0):** PQL grammar and reference implementation, the IR specification, the
compiler for SQL and Arrow/DuckDB backends, the connector SDK and ~20 connectors, the profiler,
the CLI, DQ-Bench and FinDQ-Bench.

**Commercial:** the semantic-layer control plane at scale, evidence ledger and attestation,
incident/reconciliation workflow, calibrated monitor fleet and learning loop, chat assistant,
multi-tenancy, air-gap tooling, domain packs, and support.

**Why this split:** the open half seeds adoption and makes the IR a credible standard that others
may target (`FR-EXT-010`); the closed half is what enterprises pay for and what is genuinely hard to
replicate (evidence discipline, calibration, workflow, packs). It also matches how buyers evaluate:
engineers try the OSS, the CDO buys the control plane.

---

## 7. Commercial model (outline)

- **Platform fee** by deployment tier (SaaS / VPC / on-prem / air-gapped).
- **Capacity** by managed assets and controls executed — never by rows scanned, because that
  penalises exactly the coverage we want customers to build.
- **Domain packs** licensed separately (banking, insurance, healthcare…).
- **Open-source core** free forever, with a documented, honest upgrade path.

Pricing principle: **never charge in a way that discourages more controls or more datasets.** The
product's value compounds with coverage; the pricing must not fight it.

---

## 8. Delivery risks and dependencies

| Risk | Impact | Mitigation |
|---|---|---|
| Connector breadth underestimated | Slips GA; breadth is a headline claim | Connector SDK early; parallel team; certification tiers so partners can contribute |
| Calibration under-delivers on real financial data | Undermines the central research claim | Prove on FinDQ-Bench in Phase 1, before it is a marketing promise; honest degradation path is designed in |
| Design partners slow to grant data access | Blocks live-shadow evaluation | Start with synthetic + air-gapped on-site deployment; contract access in the partnership agreement |
| Enterprise sales cycle (9–18 months) outruns runway | Existential | OSS bottom-up motion; land in one control domain with a 6-week proof; Tier-2 before Tier-1 |
| Mainframe/COBOL work is deeper than scoped | Delays a key differentiator | Timebox and buy expertise; treat copybook parsing as a standalone, testable component early |
| Scope creep into catalog/MDM/ETL | Dilutes the product; loses the wedge | `CON-001…006` are enforced in planning, and revisited only with explicit executive decision |

---

<div align="center">
<img src="assets/prama-mark.svg" width="30" alt=""/><br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.<br/>
See <a href="../LICENSE">LICENSE</a> and <a href="../NOTICE">NOTICE</a>. Third-party names and marks are the property of their respective owners.</sub>
</div>
