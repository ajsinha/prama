<img src="assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

> ***pramā*** (Sanskrit **प्रमा**) — *valid knowledge: a cognition that is both true and arrived at
> by a reliable means*. Its companion ***pramāṇa*** (प्रमाण) is *the instrument by which valid
> knowledge is obtained*. Prama is that instrument for an organisation's data — it does not decide
> what is true, it is how a belief about data becomes **justified**.
>
> **Declare it. Prove it. Trust it.**


---
# 08 — AI & Machine Learning Capabilities

**Governing principle (`CON-007`, `AD-05`, `NFR-AI-002`):**
> **Neural authorship, symbolic execution.** AI observes, proposes, ranks, calibrates, and
> explains. A deterministic engine decides. There is no code path in Prama in which a model output
> becomes a pass/fail verdict on data.

This is not conservatism. It is the only design that is simultaneously *auditable* (a regulator can
replay the decision), *affordable* (10^12 rows cannot pass through a model), and *stable* (the same
data yields the same verdict next quarter).

---

## 1. The AI subsystem map

| # | Capability | Technique family | Output | Human gate |
|---|---|---|---|---|
| 1 | Semantic type inference | Regex + dictionary + statistical + embedding + LLM adjudication | Attribute classification | Confirm/correct |
| 2 | Constraint mining | UCC / FD / approximate-FD / IND / DC discovery | Candidate structural rules | Approve |
| 3 | Relationship discovery | Overlap statistics, containment, embeddings, query-log co-access | Candidate business relationships | Confirm/correct |
| 4 | Rule induction | Template-constrained LLM + RAG over the semantic layer | Candidate PQL | Approve |
| 5 | Rule induction from examples | Weak supervision (Snorkel-style) + active learning | Candidate PQL | Approve |
| 6 | Rule induction from documents | Document parsing + LLM extraction with citations | Candidate PQL + citation | Approve |
| 7 | Anomaly monitoring | Seasonal decomposition, robust statistics, density/forest, deep TS | Anomaly score | — (verdict is thresholded, calibrated) |
| 8 | Calibration | Conformal prediction + hierarchical FDR | p-value, alert decision | Budget declared by user |
| 9 | Drift detection | PSI/KS/Wasserstein/JS/χ², multivariate detectors | Drift finding | Triage |
| 10 | Record-level outlier & error detection | Raha-style detector ensemble, conformance constraints | Suspect records | Triage |
| 11 | Entity resolution | Fellegi–Sunter + active learning + optional transformer reranker | Match/cluster | Review band |
| 12 | Repair suggestion | Baran-style contextual correction, constraint-aware repair | Ranked candidate values | Approve |
| 13 | Incident correlation & RCA | Graph reasoning over lineage + temporal correlation + learned priors | Ranked hypotheses | Confirm |
| 14 | Conversational assistant | LLM agent over the public API with strict tool contracts | Answers, proposals | Confirm all mutations |
| 15 | Narrative reporting | Grounded LLM summarisation with numeric traceability | Draft prose | Review before distribution |

---

## 2. Semantic type inference

A cascade, cheapest-first, with an explicit confidence and an audit trail of which stage decided:

1. **Deterministic validators** — checksum-bearing types are decided outright (ISIN mod-10, LEI
   ISO 17442 mod-97-10, IBAN mod-97, BIC structure, CUSIP/SEDOL check digits, Luhn for PAN).
   A column where ≥ 98% of non-null values pass a checksum is that type; no ML needed.
2. **Dictionary/code-list membership** — ISO 4217, ISO 3166, MIC, NACE/SIC, internal code lists
   registered in the semantic layer.
3. **Pattern and statistical signature** — character-class masks, length distribution, cardinality
   ratio, value-frequency shape.
4. **Column-name and comment evidence** — including multilingual and abbreviation expansion.
5. **Embedding similarity** to previously confirmed columns (within tenant; cross-tenant only as
   abstracted signatures under opt-in).
6. **LLM adjudication** — invoked only for residual ambiguity, given the column name, comments,
   masked value sample, sibling columns, and the concept model; returns a type from a **closed
   vocabulary** with a rationale.

Every classification is a *proposal* until confirmed. Confirmations are the training signal
(`FR-LRN-001`), and re-inference on cadence detects **reclassification** (`FR-REF-009`).

---

## 3. Constraint mining and rule induction

### 3.1 The fusion argument

Commercial "AI rule generation" is almost entirely LLM-from-schema, which produces plausible rules
that do not hold, and misses rules that do. Academic dependency discovery produces rules that
provably hold but are unreadable and unmotivated. **Fusing them is the differentiator:**

```
 Data ──► constraint miner ──► "attr_A → attr_B holds with 99.97% support (412 violations)"
                                                 │
 Semantic layer ──────────────────────────────►  ├──► LLM: name it, judge business plausibility,
 (concepts, definitions, CDEs, relationships)    │    attach a BECAUSE, propose severity/dimension
                                                 │
 Domain pack ────────────────────────────────►   ▼
 (regulatory catalogue, known patterns)     Candidate PQL → validate on data → rank → propose
```

The LLM never invents the constraint; it **explains and frames** a constraint the data supports.
Conversely, where the LLM proposes a rule from business semantics alone, it must be validated
against real data before it is ever shown (`FR-IND-005`).

### 3.2 Constraint mining algorithms

| Target | Algorithm family | Practical notes |
|---|---|---|
| Unique column combinations | HyUCC-style hybrid | Bounded arity (default 3), sampled candidate generation |
| Exact FDs | HyFD / lattice-traversal | Rarely useful alone on dirty data |
| **Approximate & top-k FDs** | Approximate discovery with violation budget | The practically valuable variant |
| Conditional FDs | CFD discovery (Desbordante-class) | "For EUR trades, settlement is T+2" |
| Inclusion dependencies | Partial-IND with containment scoring | Candidate foreign keys, incl. cross-source |
| Denial constraints | Approximate DC discovery over a bounded predicate space | Cross-column inequality rules |
| Order/sequence dependencies | Monotonicity and roll-forward detection | Balances, sequence numbers, timestamps |
| Conformance constraints | Projection-based tuple-trust models | Feeds the record-level trust score |

All miners run on samples with statistical bounds, then verify survivors on full data, and all are
budget-capped (`FR-PRF-013`).

### 3.3 LLM rule induction — the safety contract

1. **Retrieval, not recall.** The prompt is assembled from the semantic layer (dataset description,
   grain, attribute definitions, concept mappings, declared relationships), the profile, the domain
   pack's regulatory catalogue, and, where policy permits, masked sample values. The model is never
   asked what it "knows" about banking; it is given the customer's own definitions.
2. **Constrained decoding.** Output is restricted to the PQL grammar via template-guided/grammar-
   constrained generation. Free-text output cannot become a rule.
3. **Parse → type-check → sandbox-execute.** 100% of generated PQL is validated before display
   (`NFR-AI-008`). Anything that fails is discarded silently and counted as a generation failure.
4. **Empirical validation.** Compute the candidate's violation rate on real data. Discard
   trivially-true (0 violations on a large sample and no business justification), trivially-false
   (>50% violations), and unstable candidates (violation rate varies wildly across snapshots).
5. **Utility ranking.** `U = w₁·support + w₂·business_relevance + w₃·novelty − w₄·cost − w₅·expected_alert_volume`,
   with weights learned per tenant from acceptance history (`FR-IND-006`, `FR-IND-008`).
6. **Human approval.** Always, in any regulated scope (`FR-IND-013`).

### 3.4 Induction from documents

Parse a data dictionary, an interface specification, or a regulatory instruction (e.g. the AnaCredit
manual, an EMIR validation-rules document) and extract candidate controls **with a citation back to
the source paragraph**. The citation is retained on the rule and appears in the attestation report —
which is precisely what an auditor asks for ("show me where this control comes from").

### 3.5 Induction from examples

A steward marks a handful of records good/bad. Treating each existing rule and heuristic as a
labelling function, a Snorkel-style generative model estimates their accuracies without gold labels;
active learning then requests the most informative additional labels. Target: a usable discriminating
rule from **≤ 20 labelled cells** (the Raha result), which is the difference between a feature people
use and one they don't.

---

## 4. Calibrated monitoring — the core research contribution

### 4.1 The problem with the state of the art

Every commercial monitor answers "is this anomalous?" with an uninterpretable number and a
sensitivity dial. Users cannot reason about the consequence of a setting, so they either drown in
alerts or turn monitoring off. The literature is unambiguous that this — not detection power — is
the binding constraint on adoption.

### 4.2 The Prama approach

**Step 1 — Score.** Any detector may produce the raw score: seasonal-robust decomposition (STL +
robust z), quantile regression bands, isolation forest / LOF for multivariate metrics, matrix-profile
for shape anomalies, or a time-series foundation model's forecast residual. Detector choice is per
metric and per asset, selected by the champion/challenger process (§4.5).

**Step 2 — Calibrate.** Convert the score `s` to a **conformal p-value** against a calibration set
of recent, human-vetted-normal observations:

```
p = ( |{ sᵢ ∈ Cal : sᵢ ≥ s }| + 1 ) / ( |Cal| + 1 )
```

Under exchangeability this is a valid p-value: `P(p ≤ α) ≤ α` under the null. Financial data is not
exchangeable across regimes, so Prama uses **weighted/adaptive conformal calibration**, learning
weights over the calibration window so recent, similar-regime observations dominate — the
construction that preserves coverage under distribution shift.

**Step 3 — Select.** Alerting is a *multiple-testing* problem: a tenant runs 10^5–10^6 monitors.
Prama applies **hierarchical Benjamini–Hochberg** over the domain → dataset → attribute → check
lattice, with per-scope budgets. The user declares intent operationally:

```pql
SENSITIVITY budget(false_alarms <= 2 per month)   -- or
SENSITIVITY fdr(0.05)                             -- or
SENSITIVITY power(detect >= 5% shift in row_count with 90% probability)
```

and Prama solves for the thresholds. **Alert volume becomes a dial the business sets, with a
statistical meaning.**

**Step 4 — Be honest.** A validity monitor continuously tests calibration assumptions (calibration-set
staleness, regime change, coverage drift). When they fail, the monitor's state changes to
**"uncalibrated — best effort"** and says so in the UI and in the alert (`FR-MON-007`,
`NFR-AI-001`). We would rather show a degraded guarantee than a false one.

### 4.3 Seasonality and calendars

Financial series are dominated by calendar effects. Prama models: intraday, day-of-week,
day-of-month, month-end/quarter-end/year-end, holiday calendars (TARGET2, SIFMA, JPX, per-market
settlement calendars), month-end proximity, and declared business drivers from the semantic layer
(`FR-MET-007`). Declared drivers beat inferred ones — the business owner's *"3× at month-end"* is
prior knowledge no detector should have to rediscover.

### 4.4 Cold start

New assets get useful monitoring on day one from: the semantic type's prior, the domain pack's
prior for that concept, statistics from sibling assets in the same domain and journey, and the
declared expected rhythm and volume range. The prior is explicitly labelled as such, with wide
bands that tighten as history accrues.

### 4.5 Champion / challenger

Multiple detectors run in shadow for each monitored metric. Promotion requires a statistically
significant improvement in precision at equal recall against steward dispositions
(`FR-MON-016`). Every promotion, and every model's precision history, is recorded in its model card.

### 4.6 Regime change vs. anomaly

A one-off spike and a permanent level shift require different responses. Prama runs changepoint
detection alongside anomaly detection; on a detected changepoint it proposes **"accept new normal"**,
which recalibrates the baseline, records the acceptance with a reason, and annotates the trend chart
permanently — so a year later the chart explains itself.

---

## 5. Record-level detection and repair

- **Detector ensemble (Raha-shaped):** outlier detectors, pattern violations, constraint violations,
  knowledge-base violations, and cross-column implausibility, clustered and propagated from a small
  labelled sample.
- **Conformance-constraint trust:** a per-record trust score answering "does this record look like
  the data our controls were built on?" — a cheap, powerful screen for structurally-novel records
  that violate no explicit rule.
- **Repair candidates (Baran-shaped):** value-frequency priors, co-occurrence models, external
  reference lookups, historical values for the same key, and constraint implication. Each candidate
  carries its evidence.
- **Constraint-aware holistic repair:** minimal-repair semantics over the active constraint set,
  offered as an *advisory* with an explicit cost model — never applied automatically (`FR-REM-005`).
- **Utility-aware repair (P3):** score candidate repairs by their effect on declared downstream
  consumers, following the "cleaning *for* ML" line of research rather than cleaning as an end.

---

## 6. RCA and impact reasoning

Given an incident, assemble and rank hypotheses over a graph of evidence:

| Hypothesis class | Signals |
|---|---|
| Upstream data defect | Ancestor control failures within the window; ancestor freshness/volume anomalies |
| Pipeline/job failure | Orchestrator status, run duration, partition absence, OpenLineage events |
| Schema/code change | Schema-drift findings, dbt/Git commit correlation, contract version change |
| Source-system event | Correlated anomalies across all assets of one source; connection health |
| Legitimate business change | Calendar events, declared drivers, product launches, correlated volume across the domain |
| Control defect | Rule recently changed; identical failures across unrelated assets; threshold too tight for observed variance |

Ranking uses temporal proximity, lineage distance, historical resolution priors (learned per tenant),
and the strength of each signal. Every hypothesis is presented **with its evidence and a one-click
"confirm/reject"**, which is a labelled training example (`FR-LRN-004`). The LLM composes the
narrative; it never invents a hypothesis outside the enumerated classes.

---

## 7. The conversational agent

Architecture and UX in [10](10-ux-and-chat-interface.md). The AI-governance essentials:

- **Tool-constrained.** A closed set of typed tools mapping to public API operations; no free-form
  code execution; read tools and *propose* tools only — no tool mutates state directly.
- **Identity-bound.** Runs as the invoking user (`FR-CHT-002`). It cannot see or do anything the
  user could not.
- **Grounded.** Every factual claim carries a link to the object or query that produced it.
  Ungrounded answers are refused (`FR-CHT-005`).
- **Injection-hardened.** Data content, document text, column comments, and retrieved rows are
  *untrusted input*; the system prompt establishes that no instruction found in data is ever
  followed. Tool allow-lists, output schema validation, and an adversarial regression corpus
  enforce it each release (`NFR-SEC-010`).
- **Proposal-only mutation.** Every change renders as a PQL/config diff with backtest and cost, and
  enters the same approval workflow as any UI change (`FR-CHT-004`).
- **BYO-LLM.** Anthropic, Azure OpenAI, Bedrock, Vertex, or self-hosted open-weight models;
  air-gapped deployments run local models with documented capability deltas (`FR-CHT-010`).

---

## 8. AI governance, model risk, and MLOps

Regulated buyers will subject every learned component to model-risk review (SR 11-7) and, in the EU,
to AI Act Article 10 data-governance obligations for high-risk systems. Prama is built to pass that
review out of the box.

| Requirement | Implementation |
|---|---|
| Inventory | Every model (detector, calibrator, classifier, matcher, ranker) is registered with version, owner, and purpose |
| Model cards | Algorithm, intended use, training window, features, hyperparameters, calibration set, known limitations, performance history (`FR-MON-017`) |
| Data provenance | Training/calibration data identified by snapshot; lineage from raw signal to artefact (`FR-LRN-007`) |
| Validation | Held-out and temporal-split evaluation; challenger comparison; documented acceptance criteria |
| Monitoring | Precision/recall tracked against steward dispositions; degradation triggers rollback (`FR-LRN-006`) |
| Human oversight | Approval gates on every proposal; override always available and always recorded (`NFR-AI-006`) |
| Explainability | Contributing features/segments on every ML alert; rationale and evidence on every LLM proposal |
| Reproducibility | Model version recorded per inference; fixed seeds; replayable (`NFR-AI-004`) |
| Isolation | Tenant-isolated training by default; cross-tenant learning only on abstracted rule shapes and statistics, opt-in (`FR-LRN-008`) |
| Non-training guarantee | Customer data is never used to train any model shared across tenants, and never sent to a model provider for training (`NFR-PRV-006`) |

**LLM operational discipline:** prompt templates are versioned artefacts under change control;
outputs are cached and content-addressed so an identical request is not re-billed; per-tenant token
budgets are enforced (`NFR-COS-004`); every call is logged with the prompt hash, model version, and
cost; and an offline evaluation suite (golden prompts with expected structural properties) gates
every prompt or model change.

---

## 9. What we deliberately do not do with AI

| Not done | Why |
|---|---|
| LLM adjudicating row-level correctness | Non-reproducible, unauditable, unaffordable (`CON-007`) |
| Auto-activating induced rules in regulated scopes | Removes the human control point regulators require (`FR-IND-013`) |
| Auto-writing repairs to source systems | Blast radius; requires separate explicit grant (`FR-REM-005`) |
| Training shared models on customer data | Confidentiality and competitive-information risk (`NFR-PRV-006`) |
| Opaque "AI sensitivity" dials | The exact failure we are attacking (GAP-2) |
| Claiming guarantees when assumptions fail | Reputationally fatal; we degrade visibly instead (`FR-MON-007`) |

---

<div align="center">
<img src="assets/prama-mark.svg" width="30" alt=""/><br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.<br/>
See <a href="../LICENSE">LICENSE</a> and <a href="../NOTICE">NOTICE</a>. Third-party names and marks are the property of their respective owners.</sub>
</div>
