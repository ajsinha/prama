<img src="assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

> ***pramā*** (Sanskrit **प्रमा**) — *valid knowledge: a cognition that is both true and arrived at
> by a reliable means*. Its companion ***pramāṇa*** (प्रमाण) is *the instrument by which valid
> knowledge is obtained*. Prama is that instrument for an organisation's data — it does not decide
> what is true, it is how a belief about data becomes **justified**.
>
> **Declare it. Prove it. Trust it.**


---
# 17 — Risk Register & Open Decisions

---

## As built

Several risks here have been settled by building, and saying which is more
useful than restating the list.

**Closed.** Engine divergence (the conformance suite makes it fail loudly rather
than silently). AI authority (`CON-007` is an import scan; the assistant cannot
mutate). Evidence tamper-evidence (hash chain plus an independent verifier).
Secret leakage into tracked configuration (refused by the pre-commit hook).

**Still open, and unchanged.** Whether ≥95% of real controls express in the
portable subset — needs design partners. Whether alert precision holds outside a
synthetic corpus — needs the shadow study. Whether the connector breadth target
is reachable at the quality bar this codebase holds. Eight of eight GA
connectors are written and seven are verified; the eighth, Snowflake, is written
against documented behaviour and has never met an account. That is the first
connector here to ship unverified, and it is worth watching as a precedent — the
guards that keep it labelled are the thing standing between "a reasonable
starting point" and "a source somebody trusted by mistake". ODBC was attempted
and refused: unixODBC cannot be installed here.

**New, and now closed.** Dependency floors have no ceilings, so a rebuild
floated to the newest release of everything and that had held by luck.
`uv.lock` pins the resolution and the gate refuses a lock that has drifted from
`pyproject.toml`. The declaration still floats deliberately, so security fixes
arrive; what changed is that a rebuild is reproducible and a version move is a
visible diff.

---

## 1. Risk register

Scoring: **Impact** 1–5 · **Likelihood** 1–5 · **Exposure** = I × L. Anything ≥ 15 needs an owner
and an active mitigation now, not a plan to plan.

### 1.1 Strategic

| ID | Risk | I | L | E | Mitigation | Early-warning signal |
|---|---|---|---|---|---|---|
| RSK-01 | **Platform absorption** — Snowflake/Databricks/Microsoft ship "good enough" quality free, collapsing the mid-market | 5 | 4 | **20** | Own the cross-system, regulated, feed-based 40%; *consume* their native metrics rather than compete; make multi-platform estates home ground; keep the evidence and semantic layer as the value | Native DMF/LHM feature velocity; customers citing "we get this free" in losses |
| RSK-02 | **Category consolidation** — observability absorbed into APM (Datadog/Metaplane) and governance suites; buyers stop buying point solutions | 4 | 4 | **16** | Position as a *control plane*, not a monitoring tool; sell to Risk/Finance, not only Data Engineering; be the evidence layer beneath GRC | Buyer conversations routed to APM budgets |
| RSK-03 | **Enterprise sales cycle outruns runway** | 5 | 4 | **20** | OSS bottom-up adoption; 6-week single-domain proof; Tier-2 before Tier-1; design-partner revenue | Pipeline stage duration; POC-to-contract conversion |
| RSK-04 | **Incumbent fast-follow** on calibrated alerting once we publish | 3 | 4 | 12 | Publishing is still net-positive (credibility, standard-setting); the moat is the *system* (semantic layer + evidence + calibration + learning), not one algorithm | Competitor marketing adopting "calibrated"/"FDR" language |
| RSK-05 | **Scope creep** into catalog/MDM/ETL under customer pressure | 4 | 4 | **16** | `CON-001…006` enforced in planning; deviations require an explicit executive decision with a written rationale | Roadmap items without a `CON` exemption |
| RSK-06 | **"Best in world" claim fails its own benchmark** | 4 | 2 | 8 | Gates are internal before external; publish negative results; the falsifiability *is* the credibility | Gate misses in CI benchmarking |

### 1.2 Technical

| ID | Risk | I | L | E | Mitigation |
|---|---|---|---|---|---|
| RSK-10 | **Conformal guarantees break on real financial data** (exchangeability violated by regimes, bursts, corporate actions) | 5 | 4 | **20** | Weighted/adaptive conformal; regime detection; explicit guarantee-status reporting and visible degradation; never claim a guarantee we cannot evidence (`FR-MON-007`) |
| RSK-11 | **IR semantic equivalence across engines proves impossible** for some constructs (regex flavours, decimal semantics, null ordering, collation) | 4 | 4 | **16** | Capability matrix + compile-time failure rather than silent divergence; a documented "portable subset"; conformance suite as a release gate |
| RSK-12 | **Assertion fusion does not deliver the cost win** at real complexity | 4 | 3 | 12 | Benchmark early (Phase 0); fall back to grouping heuristics; make cost visible so customers can choose |
| RSK-13 | **Connector breadth is a treadmill** we cannot fund | 4 | 4 | **16** | SDK + partner certification tiers; prioritise by design-partner estates; generic JDBC/ODBC/REST fallbacks always available |
| RSK-14 | **Mainframe/COBOL parsing depth** (ODO, REDEFINES, code pages, RDW) underestimated | 3 | 4 | 12 | Standalone component with its own test corpus early; buy expertise; fuzz for safety |
| RSK-15 | **Evidence store cost/scale** at 10^11 records | 3 | 3 | 9 | Columnar + compression; tiering; 2 KB median target as a hard budget (`NFR-COS-006`) |
| RSK-16 | **LLM rule induction quality** insufficient without heavy semantic-layer investment — a chicken-and-egg with adoption | 4 | 3 | 12 | Constraint mining works with zero declarations; progressive formalisation ensures value at stage 0; measure induction quality by declaration stage and publish it |
| RSK-17 | **Prompt injection succeeds** in a customer environment | 5 | 2 | 10 | Untrusted-content contract, tool allow-lists, output validation, adversarial corpus per release, no data-triggered tool calls (`NFR-SEC-010`) |
| RSK-18 | **Trust propagation is disputed** as arbitrary by customers | 3 | 4 | 12 | Multiple sanctioned semirings, full derivation display, opt-in per domain, and it is always *additional* to intrinsic scores, never a replacement |

### 1.3 Operational & organisational

| ID | Risk | I | L | E | Mitigation |
|---|---|---|---|---|---|
| RSK-20 | **Business users do not declare metadata** — the semantic layer stays empty and the thesis fails | 5 | 3 | **15** | Progressive formalisation with value at every stage; system proposes, human confirms (never an empty form); estate-maturity score as a management metric; import from existing catalogs/spreadsheets |
| RSK-21 | **Alert fatigue anyway**, because organisational process not statistics is the real cause | 4 | 3 | 12 | Incident-level correlation; ownership routing; per-monitor precision visibility; measure wasted-hours as a headline metric |
| RSK-22 | **Source teams refuse access or compute** | 4 | 3 | 12 | Read policies and budgets designed for source-owner comfort; load ceiling enforced and reported (`NFR-PRF-013`); access-request workflow built in |
| RSK-23 | **Talent concentration** — few people can do calibration + data systems + banking domain | 4 | 3 | 12 | Document heavily; pair research with engineering; keep the research team small but permanent |
| RSK-24 | **Air-gapped support cost** exceeds the revenue it wins | 3 | 3 | 9 | One codebase (`AD-08`); offline bundle automation; price the tier accordingly |
| RSK-25 | **Design partner concentration** — the product overfits three banks | 4 | 3 | 12 | Deliberate diversity in size/geography/platform; a non-banking partner from Phase 2 |

### 1.4 Legal, regulatory, reputational

| ID | Risk | I | L | E | Mitigation |
|---|---|---|---|---|---|
| RSK-30 | **A customer's regulatory failure is attributed to Prama** ("your tool said it was green") | 5 | 2 | 10 | Evidence honesty by design (staleness, sampling, indeterminate verdicts, guarantee status); contractual clarity that Prama evidences controls, it does not certify data; never overstate in marketing |
| RSK-31 | **EU AI Act classification** of Prama's own ML as a component of a high-risk system | 3 | 3 | 9 | Model cards, data governance, human oversight, and documentation built to Art. 9/10 from the start; legal review before EU GA |
| RSK-32 | **Benchmark accused of vendor bias** | 3 | 4 | 12 | Publish generators, taxonomy, seeds, and baseline configurations; invite external contribution; independent reviewer; publish results where we lose |
| RSK-33 | **Data breach via retained failing-row samples** | 5 | 2 | 10 | Samples opt-in, masked, capped, TTL'd, access-logged; default posture retains none |
| RSK-34 | **Open-source core cannibalises commercial revenue** | 3 | 3 | 9 | Split chosen so the OSS is genuinely useful but the enterprise value (evidence, workflow, learning, packs, scale) is unambiguously commercial |

---

## 2. Open decisions

Each needs an owner and a decision date. Recording them honestly is more useful than pretending
the design is finished.

| ID | Decision | Options | Lean | Needed by |
|---|---|---|---|---|
| DEC-01 | **PQL primary surface** | (a) YAML-first with an expression sub-language, (b) expression-first with YAML as a serialisation, (c) full parity | (b) — better for chat, editor, and readability; YAML remains the GitOps form | Phase 0 |
| DEC-02 | **IR representation** | Custom typed logical plan · Substrait · extended SQL AST | Custom now, evaluate **Substrait** for interop at Phase 2 (it would make third-party backends far easier) | Phase 0 / re-evaluate Phase 2 |
| DEC-03 | **Semantic layer store** | Postgres bitemporal · event-sourced · graph-native | Postgres bitemporal + derived graph projection | Phase 0 |
| DEC-04 | **Default composite scoring method** | Weighted mean · weakest link · PCA composite | Weakest link for Tier-1/regulatory, weighted mean elsewhere; tenant must choose explicitly | Phase 1 |
| DEC-05 | **Trust propagation semiring** default | min/min · probabilistic · fuzzy | min/min (conservative, explainable); probabilistic as an option | Phase 3 |
| DEC-06 | **Where does streaming validation run** | Flink job · Kafka Streams · producer-side library · broker interceptor | Flink for volume, plus a producer-side library for shift-left | Phase 2 |
| DEC-07 | **ER: build vs. integrate Splink** | Integrate · fork · build | Integrate; own the workflow, active learning, and evidence around it | Phase 2 |
| DEC-08 | **Chat agent framework** | Build on a provider SDK · framework (LangGraph-class) · fully custom | Custom thin orchestration over provider SDKs — the tool surface is small and the safety contract is strict | Phase 1 |
| DEC-09 | **Open-source licence** | Apache 2.0 · BSL/SSPL · dual | Apache 2.0 for the declared open components; no source-available games | Phase 1 |
| DEC-10 | **Pricing metric** | Assets · controls executed · users · data volume | Assets + controls; explicitly **not** data volume (it penalises coverage) | Phase 2 |
| DEC-11 | **Multi-tenant vs. single-tenant default for SaaS** | Shared with hard isolation · single-tenant per customer | Shared with hard isolation, single-tenant offered for regulated buyers | Phase 1 |
| DEC-12 | **Do we ship an embedded BI/semantic query surface** | Yes (scorecard query language) · No (export only) | Minimal query API + embeds; resist becoming BI (`CON-005`) | Phase 2 |
| DEC-13 | **Cross-tenant learning** | Never · opt-in on abstracted rule shapes · federated learning | Opt-in on abstracted shapes and statistics only; never data | Phase 3 |
| DEC-14 | **Benchmark governance** | Vendor-owned · advisory board · donate to a foundation | Advisory board at launch, path to donation (LF AI/Bitol-adjacent) | Phase 2 |
| DEC-15 | **Reconciliation depth** — how far into break *operations* do we go | DQ-grade break workflow · full recon-vendor parity | DQ-grade at GA; assess parity after two banking customers | Phase 3 |
| DEC-16 | **Air-gapped LLM** minimum model class | 8B-class · 30B-class · 70B-class | Publish measured capability deltas per class and let the customer choose; support 8B+ with degraded induction quality documented | Phase 2 |

---

## 3. Assumptions to validate early

| ID | Assumption | How we test it | If false |
|---|---|---|---|
| ASM-010 | Business owners *will* declare grain, rhythm, and relationships if the payoff is immediate | Phase 1 design-partner study: measure declarations per week and their control yield | The product must lean far harder on inference-first with confirm/correct, and the "business tool" positioning weakens |
| ASM-011 | Conformal calibration holds well enough on financial series to be a headline claim | FinDQ-Bench in Phase 1 | Reposition calibration as "better-behaved thresholds," keep FDR selection, drop the guarantee language |
| ASM-012 | Evidence and attestation are worth paying for above monitoring | Design-partner willingness-to-pay and procurement routing | Sell into engineering budgets; lead with cost and coverage rather than audit |
| ASM-013 | Reconciliation inside a DQ platform is acceptable to Ops teams | Phase 1 with a real sub-ledger↔GL recon | Position recon as a control type for *data* teams, not a replacement for the Ops recon platform |
| ASM-014 | One codebase can serve SaaS through air-gapped without unacceptable tax | Phase 2 air-gapped install | Accept a supported subset for air-gap, documented honestly |
| ASM-015 | The IR can express ≥ 95% of real-world controls portably | Convert 500 real controls from design partners in Phase 1 | Widen the custom-SQL escape hatch and be explicit about the portable subset |

---

<div align="center">
<img src="assets/prama-mark.svg" width="30" alt=""/><br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.<br/>
See <a href="../LICENSE">LICENSE</a> and <a href="../NOTICE">NOTICE</a>. Third-party names and marks are the property of their respective owners.</sub>
</div>
