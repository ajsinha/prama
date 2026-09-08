<img src="../assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

> ***pramā*** (Sanskrit **प्रमा**) — *valid knowledge: a cognition that is both true and arrived at
> by a reliable means*. Its companion ***pramāṇa*** (प्रमाण) is *the instrument by which valid
> knowledge is obtained*. Prama is that instrument for an organisation's data — it does not decide
> what is true, it is how a belief about data becomes **justified**.
>
> **Declare it. Prove it. Trust it.**


---
# Prama: A Declarative, Calibrated, and Evidence-First Control Plane for Enterprise Data Quality

**Draft v0.4 — manuscript for ACM JDIQ, with a systems companion for VLDB Industrial**
*(Results marked ⟨TBD⟩ are pending the experimental programme in [`experiment-plan.md`](experiment-plan.md);
the protocol, not the numbers, is what this draft fixes.)*

---

## Abstract

Enterprise data quality management is fragmented across three paradigms — declarative assertion
frameworks, machine-learning observability monitors, and human business judgement — implemented in
disjoint products with disjoint result models. The consequence is that organisations can *detect*
data defects but cannot *prove* control effectiveness, cannot express business meaning in a form
that executes, and cannot interpret the alarm rate of their own monitoring. We present **Prama**, a
data quality control plane organised around four ideas. First, a **business semantic layer** in
which owners declare datasets, attribute interpretations, canonical concepts, and typed
inter-dataset relationships; declarations compile automatically into executable controls. Second,
**PQL**, a declarative quality language compiled to an engine-neutral intermediate representation
(IR) that executes with certified semantic equivalence across SQL engines, Spark, Flink, and a
local Arrow runtime. Third, **risk-controlled alerting**: every statistical monitor emits a
conformal p-value, and alert emission is a hierarchical false-discovery-rate–controlled selection
under an operator-declared false-alarm budget — replacing the uninterpretable "sensitivity" dials
that the literature identifies as the dominant cause of monitoring abandonment. Fourth, an
**evidence ledger** of immutable, hash-linked, deterministically replayable records, enabling
regulatory attestation and enabling **trust propagation**: a semiring-valued quality score that
flows along the column-level lineage DAG with transformation-aware attenuation. We further describe
a neuro-symbolic rule-induction pipeline that fuses algorithmic constraint discovery with
template-constrained LLM authorship under the invariant that **no language model output ever
determines a verdict on data**. We introduce **DQ-Bench** and **FinDQ-Bench**, the first public
defect-labelled benchmarks for cross-system enterprise data quality, and evaluate Prama against
declarative, ML-observability, platform-native, and research baselines, plus a 90-day blind
live-shadow deployment at three financial institutions. ⟨TBD: headline results.⟩

**Keywords:** data quality, data cleaning, conformal prediction, false discovery rate, declarative
constraints, data lineage, provenance, auditability, regulatory compliance, neuro-symbolic systems

---

## 1. Introduction

### 1.1 The problem

Poor data quality is estimated to cost the average enterprise approximately \$12.9M annually
[gartner2020mq], and 15–25% of revenue by other estimates. In regulated finance the cost is not
estimated but assessed: national supervisors have levied fines of ~£95M for MiFID transaction
reporting failures and ~£34.5M for EMIR reporting, including individual penalties exceeding £34M for
220 million reporting errors accumulated over nine years [ateam2024]. Separately, poor data quality
has been identified as the leading obstacle to enterprise generative-AI adoption, repositioning data
quality from an operational hygiene concern to a precondition for AI investment.

Despite more than fifty commercial products and a mature research literature, three failures recur
in practice.

**F1 — Paradigm fragmentation.** Quality knowledge exists in three forms: *declarative assertions*
(constraints authored by engineers), *statistical monitors* (learned baselines over metric history),
and *semantic judgements* (business knowledge about meaning and relationships). Products implement
one well and the others poorly, with incompatible result models, so no unified score, incident, or
evidence trail exists.

**F2 — Uninterpretable alarm rates.** Every deployed ML monitoring product exposes sensitivity as an
opaque control. Operators cannot express, and systems cannot honour, a statement such as "I will
tolerate at most two false alarms per month in this domain." The industrial monitoring literature
identifies excessive false alarms as the mechanism by which monitoring is abandoned
[conformal2026, industrialcps2026].

**F3 — Absence of provable control.** Results are stored as mutable state with retention windows.
No product produces immutable, attributable, deterministically replayable evidence per control
execution, which is precisely what supervisory frameworks such as BCBS 239 demand [bcbs239].
Institutions therefore operate an observability tool *and* a parallel manual attestation process.

Underlying all three is a fourth, structural failure: **tools model the physical estate, not the
business estate.** They crawl schemas and monitor columns. The knowledge that would make monitoring
effective — what one row represents, when data is expected, which fields are critical, and how
datasets relate to one another — resides with business owners and is never captured in an executable
form.

### 1.2 Contributions

1. **A business semantic layer with executable declarations** (§3). A small object model —
   Dataset, Attribute, Concept, Relationship, Journey — in which business declarations
   *automatically generate* controls. We formalise the declaration-to-control mapping and show that
   thirteen relationship types generate the control classes that dominate real quality programmes.
2. **PQL and an engine-neutral IR with certified cross-engine equivalence** (§4). A total,
   side-effect-free declarative language compiled to a typed logical plan, executed by pushdown on
   heterogeneous engines, with a conformance suite establishing semantic equivalence.
3. **Risk-controlled data quality alerting** (§5). Conformal calibration of arbitrary anomaly
   scores, made valid under distribution shift by adaptive weighting, combined with hierarchical
   FDR control over the domain → dataset → attribute → check lattice. This converts alert volume
   from an opaque dial into a declared, statistically meaningful budget. To our knowledge no
   deployed data quality system provides a calibrated alarm rate.
4. **Neuro-symbolic rule induction** (§6). A pipeline fusing algorithmic constraint discovery with
   template-constrained LLM authorship, under the architectural invariant that language models
   author and explain but never adjudicate.
5. **Lineage-aware trust propagation** (§7). A semiring formulation of quality over the column-level
   lineage DAG with transformation-dependent attenuation, giving consumers an honest trust value
   that accounts for ancestry.
6. **An evidence model with deterministic replay** (§8), and the systems discipline (content-addressed
   rules, snapshot capture, versioned reference data) that makes replay achievable.
7. **DQ-Bench and FinDQ-Bench** (§10), the first public defect-labelled benchmarks covering
   cross-system, temporal, and *semantic* defect classes, with a banking instantiation including
   message standards, mainframe feeds, and reconciliation.

### 1.3 Non-contributions

Prama is not a data catalog, an ETL engine, a master-data hub, or a BI tool; it integrates with all
four. We do not claim novel anomaly detectors: our contribution is the *calibration and selection*
layer above whatever detector is used. We do not claim novel constraint-discovery algorithms: we
adopt published ones and contribute their fusion with language-model authorship and their embedding
in an approval workflow.

---

## 2. Background and related work

### 2.1 Constraint discovery and profiling

Dependency discovery is mature. Platforms such as Metanome [metanome] host algorithms for unique
column combinations, functional dependencies, inclusion dependencies, and order dependencies, and
comparative evaluations organise FD algorithms into lattice-traversal, difference/agree-set, and
dependency-induction families [fdeval]. High-performance successors extend to probabilistic and
conditional dependencies [desbordante_cfd, desbordante_pfd] and to top-k approximate FDs
[topkafd] — the practically relevant variant, since exact FDs rarely survive real data. Denial
constraints [dcdiscovery] subsume FDs and capture cross-column inequality predicates. Conformance
constraints [conformance] reframe the question as tuple-level trust relative to training
distribution. This literature is essentially unexploited commercially; §6 fuses it with LLM
authorship.

### 2.2 Error detection and repair

HoloClean casts repair as probabilistic inference over a factor graph combining constraints,
statistics, and external signals [holoclean]. HoloDetect addresses label efficiency through
error-generation augmentation. Raha achieves configuration-free error detection via an ensemble of
detectors clustered and propagated from a tiny labelled sample, and Baran performs correction
through a unified context representation with transfer learning [rahabaran]; subsequent engineering
made both tractable [rahaaccel]. Bayesian [bclean] and Markov-logic [mlncleaning] hybrids unify
logical and statistical evidence. Recent work explores zero-shot detection via LLM reasoning
[zeroed] and data-dependent error classes [mechdetect]. Systematic reviews emphasise that cleaning
must be *objective-aware*: a repair improving a dimension score while degrading a downstream
consumer is a regression [dcml_slr, cleaningforml].

### 2.3 Anomaly detection, drift, and calibration

Benchmarking hygiene is a documented hazard: curated archives were constructed because earlier
benchmarks proved trivially solvable or mislabelled [ucr], and multivariate evaluations show
transformer results to be highly sensitive to window size and label-extraction protocol
[mvbench]. Non-stationarity dominates real deployments, motivating drift-aware architectures
[d3r]. Conformal prediction supplies the missing interpretability: adaptive post-hoc conformal
methods over time-series foundation models produce anomaly scores directly interpretable as
false-alarm probabilities, with weighted-quantile calibration valid under distribution shift
[conformal2026]; libraries now separate scoring from calibration, selection, and weighting to
support FDR-controlled workflows [nonconform, fdrnovelty]. We build directly on this line and, to
our knowledge, are the first to apply it as the alerting substrate of a production data quality
system.

### 2.4 LLMs for data quality

LLM-generated rules achieve high coverage in constrained domains — 97.1% and 99.6% coverage on two
EHR corpora, with 100% coverage of consistency rules [llmdqr]. Three-stage pipelines combine
statistical inlier detection with LLM rule and *code* generation under RAG grounding [llmtabular],
and template-guided generation constrains hallucination [tuwien]. Every credible result places the
model in the authoring seat and a deterministic engine in the execution seat. §6 adopts this
division as an architectural invariant rather than an implementation detail.

### 2.5 Entity resolution and weak supervision

Probabilistic linkage in the Fellegi–Sunter tradition remains the transparent baseline [splink];
active-learning systems dominate at design time because human labelling, not model capacity, is the
binding constraint [zingg, dedupe]; transformer matchers lead benchmarks at the cost of opacity
[ditto]. Snorkel's programmatic labelling — labelling functions combined by a generative model that
learns their accuracies without gold labels [snorkel] — provides the template for converting steward
operational work into training signal (§9.4).

### 2.6 Scoring, contracts, and standards

Scoring frameworks standardise metric matrices before aggregation and use PCA to avoid arbitrary
weights [dqsops]. Dimension taxonomies converge on DAMA's six with ISO/IEC 25012 extensions, while
ISO 8000 addresses cross-organisational verification and exchange; none specify measurement
semantics. The Open Data Contract Standard [odcs] provides a machine-readable contract with schema,
quality, and SLA sections, but analyses observe that most contract tooling does not *enforce*
[contractenforce]. Prama is an ODCS-native runtime, closing that gap. **No prior work propagates
quality along lineage**; §7 is, to our knowledge, the first formulation.

---

## 3. The business semantic layer

### 3.1 Object model

Let a tenant's estate be described by
`E = (D, A, C, R, J, B)` where `D` is a set of Datasets, `A` Attributes, `C` Concepts with
properties `P(C)`, `R` typed Relationships, `J` Journeys, and `B` Bindings from business objects to
physical objects.

A **Dataset** `d ∈ D` carries a declaration
`δ(d) = ⟨grain, key, temporality, rhythm, authoritativeness, criticality, ownership, jurisdiction⟩`,
where `grain` is a tuple of Attributes defining what one record represents, and `rhythm` is
`⟨frequency, arrival window, calendar, cut-off, volume range, volume drivers⟩`.

Crucially, `B` is **partial**: a Dataset may be declared before it is bound to any physical object.
Architects map the estate before connectivity exists, and unbound datasets participate in
relationships, appear on the estate map, and are reported as coverage gaps.

An **Attribute** `a ∈ A` carries
`α(a) = ⟨definition, interpretation, semantic type, unit, value domain, optionality, criticality, sensitivity⟩`
and an optional mapping `μ(a) ∈ P(C)` to a canonical Concept Property. The mapping induces an
equivalence class over attributes across the estate that *ought* to mean the same thing —
enabling estate-wide controls and, equally usefully, the automatic detection of *semantic conflict*
where two mapped attributes carry incompatible definitions, units, or domains.

### 3.2 Relationships as control generators

A **Relationship** `r = ⟨type, d_from, d_to, keys, cardinality, tolerance, offset, filter⟩` where
`type ∈ {REFERENCES, RECONCILES_WITH, DERIVES_FROM, FEEDS, MIRRORS, AGGREGATES, ENRICHES,
SUPERSEDES, SAME_ENTITY_AS, TEMPORAL_SUCCESSOR, HIERARCHY, MUTUALLY_EXCLUSIVE, TOGETHER_COMPLETE}`.

Define the generator `Γ : δ ∪ α ∪ R → 2^Controls`. Examples:

| Declaration | Γ produces |
|---|---|
| `grain(d) = (k₁,…,kₙ)` | `UNIQUE(d, k₁…kₙ)`; duplicate detection; completeness against the key population |
| `rhythm(d).arrival = (t, cal)` | freshness assertion on calendar `cal`; arrival-pattern monitor |
| `rhythm(d).volume_drivers` | seasonality-parameterised volume monitor |
| `α(a).semantic_type = τ` | the validator bundle for `τ` (format, checksum, registry existence) |
| `α(a).value_domain = L` | membership assertion against code list `L`, versioned as-of |
| `r.type = REFERENCES` | referential integrity; orphan monitor; key-coverage monitor |
| `r.type = RECONCILES_WITH` | full reconciliation with tolerance, offset, and break classification |
| `r.type = DERIVES_FROM` | aggregate-parity assertion; a trust-propagation edge (§7) |
| `r.type = TEMPORAL_SUCCESSOR` | roll-forward: opening + movements = closing |
| `r.type = SAME_ENTITY_AS` | entity resolution as a scheduled control; identifier-consistency assertion |
| `r.type = TOGETHER_COMPLETE` | population completeness against the declared universe |

Every generated control carries provenance identifying the declaration that produced it, so an
auditor's question *"why does this control exist?"* is answerable mechanically. Generated controls
are **proposals**: they are backtested, costed, and presented for approval before activation
(§6.4).

### 3.3 Progressive formalisation

A full modelling exercise would be prohibitive. We therefore impose a design constraint: *every
declaration must return value immediately, and none may be mandatory*. Seven stages, from "nothing
declared" (auto-discovery only) to "journeys declared" (end-to-end SLA and business lineage),
each unlock a strictly larger control set. Crucially, the system operates in **propose-and-confirm**
mode at every stage: grain, keys, semantic types, and relationships are *inferred* and presented as
"we believe this is true — confirm or correct", never as empty forms. Confirmations are the training
signal (§9.4).

We treat declaration coverage as a first-class, reported metric (*estate maturity*), which we
observe to be an effective adoption driver in deployment (§11).

---

## 4. PQL and the intermediate representation

### 4.1 Language

PQL is a total, side-effect-free declarative language with two isomorphic surfaces (a YAML form for
GitOps and machine generation; an expression form for editing and conversation). A control is

```
CHECK ⟨target⟩ ⟨assertion⟩ [WHERE φ] [FOR EACH σ] [WITHIN τ]
      [SEVERITY s] [DIMENSION δ*] [BECAUSE ρ] [EVIDENCE ε] [ON FAIL a]
```

Assertions span column predicates, dataset-level properties, multi-column dependencies (FD, CFD,
DC), referential integrity, aggregate and group constraints, temporal and roll-forward constraints,
statistical monitors, reconciliations, and entity resolutions. Rules bind to *business* targets —
attributes, concept properties, or selectors over semantic metadata (`CHECK CONCEPT Instrument.ISIN
IS VALID isin`) — rather than to physical columns; selector expansion is materialised and versioned
so an author always sees exactly which assets a rule will touch.

Two semantic choices differ deliberately from SQL practice:

- **Unknown is a violation by default.** A predicate evaluating to `UNKNOWN` counts as a violation
  unless the author writes `TREAT UNKNOWN AS pass`. Silence about unknowns is, in our field
  experience, the largest source of false confidence in production suites.
- **`indeterminate` is a first-class verdict.** An assertion whose sample was insufficient for the
  declared confidence is never silently reported as passing.

### 4.2 IR and compilation

PQL compiles to a typed logical plan `IR = ⟨assertion, scope, metrics, threshold, evidence spec,
cost hints, provenance⟩`, content-addressed by hash. Backends (SQL with per-dialect adapters, Spark,
Flink, Arrow/DuckDB, and a native scanner for non-tabular feeds) declare a **capability matrix**;
the compiler selects a strategy per capability and *fails at authoring time* where a target cannot
express a construct, rather than degrading silently.

**Assertion fusion.** The scheduler groups all assertions sharing a scope and snapshot into a single
plan, so *n* column-level assertions over a table become one query computing *n* aggregates. This is
the principal source of the cost result in §10.

**Cross-engine equivalence.** Let `⟦·⟧_E` denote evaluation of an IR program on engine `E` over a
snapshot `S`. We maintain a conformance corpus `Π` of PQL programs with golden results and require

  ∀ π ∈ Π, ∀ E, E′ ∈ Engines : ⟦compile(π)⟧_E (S) = ⟦compile(π)⟧_E′ (S)

verified in CI for every supported engine, augmented by property-based generation of programs
compared against a reference interpreter. Failures block release. §10 reports the size of `Π`, the
fraction of real-world controls expressible in the portable subset, and the constructs where
equivalence is genuinely unattainable (regex flavours, collation, decimal semantics) — which we
report rather than paper over.

---

## 5. Risk-controlled alerting

### 5.1 Problem

A tenant runs 10⁵–10⁶ monitors. Each emits a score `s` from an arbitrary detector. Two questions
must be answered that no deployed system answers: *what is the probability this alert is spurious?*
and *how do I bound the total number of spurious alerts?*

### 5.2 Conformal calibration

For a monitored series with recent observations judged normal, let `Cal = {s₁,…,s_n}` be a
calibration set of scores. For a new score `s`,

  p(s) = ( |{ i : sᵢ ≥ s }| + 1 ) / ( n + 1 )

Under exchangeability of `Cal ∪ {s}` under the null, `p` is a valid p-value: `P(p ≤ α) ≤ α`
[conformal2026]. Financial and operational series are not exchangeable across regimes, so we adopt
**weighted conformal calibration**: with weights `wᵢ` over the calibration set,

  p_w(s) = ( Σ_i wᵢ · 1[sᵢ ≥ s] + w_new ) / ( Σ_i wᵢ + w_new )

with `w` learned from recent predictive performance, concentrating mass on observations from the
current regime. This preserves approximate coverage under gradual shift.

### 5.3 Hierarchical FDR control

Alerting is a selection problem over the lattice
`L = Domain → Dataset → Attribute → Check`. Given p-values `{p_j}` for the checks evaluated in a
period, and a target FDR `q`, we apply Benjamini–Hochberg within each node's children, allocating
per-node budgets top-down proportional to declared criticality, and using
Benjamini–Yekutieli where dependence among sibling checks cannot be assumed positive (checks on the
same table are strongly dependent). The user declares intent operationally:

```
SENSITIVITY budget(false_alarms <= 2 per month)
SENSITIVITY fdr(0.05)
SENSITIVITY power(detect >= 5% shift in row_count with 90% probability)
```

and the system solves for thresholds. **Alert volume becomes a declared quantity with a statistical
meaning**, which is the practical contribution.

### 5.4 Honest degradation

We continuously test calibration validity (calibration-set staleness, coverage drift, detected
regime change). When validity fails, the monitor's guarantee status becomes *suspended* and this is
surfaced in the UI and in every alert. We consider silently maintaining an invalid guarantee to be
the worst available behaviour, and design accordingly.

### 5.5 Priors and cold start

New assets have no history. We initialise calibration from (i) the semantic type's prior,
(ii) domain-pack priors for the mapped concept, (iii) statistics of sibling assets in the same
domain and journey, and (iv) the **declared** rhythm and volume range from §3. Priors are labelled
as such, with wide bands that tighten as history accrues. The availability of *declared* business
drivers (e.g. "volume triples at month-end") is a direct benefit of the semantic layer that
physical-first systems cannot obtain.

---

## 6. Neuro-symbolic rule induction

### 6.1 Invariant

**No language-model output determines a verdict on data.** Models author, name, explain, rank, and
summarise. A deterministic, versioned engine decides. This is enforced architecturally and tested in
CI. The justification is threefold: reproducibility (a regulator can replay the decision),
economics (10¹² rows cannot pass through a model), and stability (the same data must yield the same
verdict next quarter).

### 6.2 Pipeline

1. **Mine.** Constraint discovery over samples with statistical bounds, verified on full data:
   UCCs, approximate and conditional FDs, partial INDs, approximate DCs, order dependencies.
2. **Ground.** Assemble retrieval context from the semantic layer (dataset declaration, attribute
   definitions and interpretations, concept mappings, declared relationships), the profile, and the
   domain pack's regulatory catalogue.
3. **Author.** Constrained decoding restricted to the PQL grammar produces candidate controls, each
   with a `BECAUSE` justification, proposed severity, and dimension.
4. **Verify.** Parse, type-check, and sandbox-execute every candidate; compute its violation rate;
   discard trivially-true, trivially-false, and snapshot-unstable candidates.
5. **Rank.** `U = w₁·support + w₂·business_relevance + w₃·novelty − w₄·cost − w₅·E[alert volume]`,
   with weights learned per tenant and per domain from acceptance history.
6. **Approve.** Present with evidence, backtest over historical snapshots, estimated alert volume,
   and cost. Human approval is mandatory in regulated scopes.

The mining and authoring stages are complementary in a way we quantify in §10: mining supplies
constraints that provably hold but lack motivation; authoring supplies motivation and business
framing but hallucinates constraints. Neither alone reaches acceptable acceptance rates.

### 6.3 Induction from documents and from examples

Regulatory instructions and interface specifications are parsed and mined for implied controls
**with citations to the source paragraph**, retained on the control and surfaced in attestation
reports. Separately, treating each existing rule and heuristic as a labelling function and applying
weak supervision with active learning, a discriminating control can be induced from a small number
of steward-labelled cells; we evaluate the label budget required (§10).

### 6.4 Proposals as the universal mutation channel

Every automated suggestion — mined constraint, authored rule, inferred relationship, threshold
adjustment, retirement recommendation — enters the same **Proposal** object, with the same
evidence, backtest, cost estimate, and approval workflow, whether it originated from a miner, a
model, a declaration, a pack, or the conversational interface. This uniformity is what makes an
AI-assisted system auditable.

---

## 7. Lineage-aware trust propagation

### 7.1 Motivation

Every system we surveyed scores each asset independently. A derived table with perfect intrinsic
controls, built from a source whose primary control has failed for six weeks, is scored as healthy.
In a regulatory context this is not merely uninformative but materially misleading.

### 7.2 Formulation

Let `G = (V, E)` be the column-level lineage DAG. Each node `v` has an **intrinsic** trust
`τ_int(v) ∈ [0,1]` computed from its own controls' evidence. Over a commutative semiring
`⟨T, ⊕, ⊗, 0̄, 1̄⟩` define the **effective** trust

  τ_eff(v) = τ_int(v) ⊗ ⨁_{u ∈ parents(v)} ( α(u→v) ⊗ τ_eff(u) )

where `α(u→v) ∈ [0,1]` is a transformation-dependent attenuation:

| Edge transformation | α behaviour |
|---|---|
| Pass-through, copy, rename | α ≈ 1: defects propagate fully |
| Filter | α computed from whether the filter removes the affected population |
| SUM / COUNT aggregation | α < 1, decreasing in the concentration of the defect |
| AVG / MEDIAN aggregation | α larger: robust statistics attenuate isolated defects |
| Join | τ bounded above by min of inputs; key-coverage failure propagates as completeness loss |
| Derivation with its own validating control | α bounded by that control's coverage — validation *restores* trust |

With `⊕ = min, ⊗ = min` we obtain conservative weakest-ancestor semantics; with the probabilistic
semiring `⟨[0,1], ·, ·⟩` under an independence assumption, `τ` reads as a defect-freeness
probability. Because `G` is acyclic, `τ_eff` is computable in a single topological pass, and
incrementally maintainable under evidence arrival.

### 7.3 Consequences

Three practical results follow. (i) Consumers see honest trust that accounts for ancestry.
(ii) Remediating an upstream defect visibly lifts every descendant, making upstream investment
justifiable. (iii) One can compute the **propagation impact** of each control — the aggregate trust
uplift obtainable by fixing it — yielding a principled answer to *"where should the remediation
budget go?"* We evaluate whether propagation-ranked remediation outperforms severity-ranked
remediation in §10.

A caveat we state plainly: propagation semantics are a modelling choice, not a physical fact.
Prama therefore offers multiple sanctioned semirings, always displays the derivation path, and
always reports intrinsic trust alongside effective trust.

---

## 8. Evidence and reproducibility

Each assertion execution appends an immutable `EvidenceRecord` containing: the rule version and PQL
hash, the IR hash, the rendered natural-language statement, control provenance and approval chain,
the scope with filter and segmentation, the **snapshot identifier** (Iceberg/Delta version, SCN/LSN,
file digest set, offset range) with an explicit `exact` flag, the sampling strategy and coverage,
the engine and engine version, the plan hash, resource consumption, the verdict and metrics, a
reference to any retained masked samples, and integrity fields (previous-record hash, record hash,
signature, daily Merkle root).

**Determinism.** `ir_hash × snapshot × engine_version × seed` determines the verdict. Replay
either reproduces the verdict exactly or emits a **divergence report** naming the cause (data
restated, snapshot expired, engine upgraded, referenced code list moved). Divergence is itself
evidence.

This is achievable only through design decisions taken at the outset — content-addressed rules,
snapshot capture on every read, as-of-versioned reference data and code lists, seeded sampling, and
an append-only ledger. We report the storage cost (target: ≤ 2 KB median per execution) and replay
overhead in §10.

---

## 9. Implementation

### 9.1 Architecture
A control plane (semantic layer, rule registry and compiler, scheduler, evidence ledger, metric
history, incident service, scoring engine, lineage graph, learning service, policy service) with a
stateless execution plane operating by pushdown, and an intelligence plane whose outputs are
exclusively proposals. Deployment spans multi-tenant SaaS to fully air-gapped from a single
codebase; air-gapped operation substitutes self-hosted open-weight models and manually imported
reference data.

### 9.2 Continuous re-examination
Every derived finding — profile, inferred type, mined constraint, candidate relationship, monitor
baseline, calibration set, score — is refreshed on an independent, **adaptive** cadence driven by
criticality × volatility × consumption, bounded by declared cost budgets and permitted execution
windows. Every finding is stamped with `computed_at`, snapshot, sampling strategy, and a staleness
state, and staleness is rendered wherever the finding appears. Because the business declares the
model, the system can additionally detect **metadata drift** — broken bindings, violated grain,
degraded relationship key overlap, attributes departing their declared value domain, reclassified
semantic types — and route it to the owner of the *declaration*. This class of finding is unavailable
to physical-first systems.

### 9.3 Cost control
Pushdown; assertion fusion; incremental execution over new partitions and snapshots; a sampling
planner that selects full-scan, incremental, or statistically-bounded sampling per assertion subject
to budget and required confidence; and enforced per-source load ceilings so that Prama's footprint
on a production source is bounded, measured, and reported.

### 9.4 The learning loop
Human signals — rule accept/reject/edit, incident dispositions, threshold overrides, break
classifications, entity-resolution labels, "accept new normal" events, and metadata confirmations —
are captured as structured feedback into a versioned, tenant-isolated feature/label store. They
drive monitor recalibration, induction re-ranking, RCA hypothesis ranking, break classification, and
semantic-type inference. Challengers are evaluated in shadow and promoted only on a statistically
significant precision improvement at equal recall; degradation triggers automatic rollback. No
customer data trains any cross-tenant model; cross-tenant transfer is limited to abstracted rule
shapes and aggregate statistics, and is opt-in.

---

## 10. Evaluation

Full protocol: [`experiment-plan.md`](experiment-plan.md).

### 10.1 Benchmarks

**DQ-Bench.** Open datasets and synthetic generators with labelled defects injected from a
24-class, 6-family taxonomy (structural, content, statistical, relational, temporal, **semantic**),
at three scales (10⁶/10⁸/10¹⁰ rows) and four difficulty tiers, including an *adversarial* tier in
which defects co-occur with legitimate changes to test false-positive discipline. The semantic
family — plausible-but-wrong values that pass every format and range check — is the discriminating
class, detectable only via declared relationships or genuine business semantics.

**FinDQ-Bench.** A synthetic but structurally faithful bank: ~120 datasets across trading,
positions, sub-ledger, GL, payments, and client master, with ~90 declared relationships, six
journeys, SWIFT MT/MX and FIX flows, a COBOL/EBCDIC overnight feed, T+1 sub-ledger↔GL
reconciliation with realistic break populations, TARGET2/SIFMA seasonality, an MT↔MX translation
pair, and a corporate-action event that legitimately shifts distributions.

### 10.2 Baselines
Declarative OSS (Great Expectations, Soda Core, dbt tests, Deequ, DQOps); ML observability
(leading commercial platform under evaluation licence, reported anonymised where terms require;
plus open equivalents); platform-native (Snowflake DMFs, Databricks Lakehouse Monitoring + DLT
expectations, AWS Glue Data Quality); research systems (HoloClean, Raha/Baran, ZeroED, Splink,
Metanome/Desbordante); and **ablations of Prama** — rules-only, monitors-only, uncalibrated
monitors, no semantic layer, no learning, LLM-from-schema-only induction. Baseline configurations
are published for challenge.

### 10.3 Research questions

| RQ | Question | Metric |
|---|---|---|
| RQ1 | Does unifying declarative, statistical, and semantic assertion improve detection? | F1 per defect family; ablation deltas |
| RQ2 | Does conformal calibration deliver valid alarm rates under real drift? | Calibration curve; \|empirical − nominal\|; coverage under shift |
| RQ3 | Does hierarchical FDR control reduce alert burden without losing recall? | Precision@alert; alerts/steward-week; recall at fixed budget |
| RQ4 | Does the semantic layer improve induction quality? | Acceptance rate and precision by declaration stage |
| RQ5 | Does mining+LLM fusion beat either alone? | Acceptance rate; coverage; hallucination rate |
| RQ6 | Is cross-engine equivalence achievable in practice? | Conformance-suite pass rate; % of real controls in the portable subset |
| RQ7 | Does fusion + sampling deliver the cost claim? | Compute per 10⁹ rows vs. naive and vs. baselines at equal coverage |
| RQ8 | Does trust propagation improve remediation decisions? | Trust uplift per unit remediation effort, propagation- vs. severity-ranked |
| RQ9 | Does the learning loop compound? | Monthly precision, acceptance, RCA accuracy over 12 months, with a frozen-model control arm |
| RQ10 | Do business users declare, and does it pay? | Declarations/week; controls generated per declaration; estate maturity vs. defect escape rate |

### 10.4 Live-shadow deployment
At three institutions, Prama runs alongside the incumbent for 90 days on identical scopes with no
production actions. Every alert from both systems is adjudicated by the customer's stewards
**blind to origin**, with dual adjudication and reported inter-rater agreement. This yields the only
measurement that matters: precision and recall on real defects under real operating conditions.

### 10.5 Results
⟨TBD⟩ — Tables 1–9 and Figures 1–6 per `experiment-plan.md`. Negative results appear in the main
body.

---

## 11. Deployment experience

⟨TBD — to be written from design-partner deployments. Anticipated themes, stated now as hypotheses
so they can be falsified:

- **H1.** Declaration effort concentrates in the first two stages (naming/ownership and grain/rhythm),
  and the marginal control yield per declaration is highest at the *relationship* stage.
- **H2.** Propose-and-confirm interaction yields materially higher metadata coverage than form-filling.
- **H3.** Alert precision, not recall, determines continued use.
- **H4.** Reconciliation is the highest-value first control class in banking, and its break workflow
  is the feature that converts evaluation into purchase.
- **H5.** Deterministic replay is rarely *used* but decisively affects procurement.⟩

---

## 12. Limitations and threats to validity

- **Exchangeability.** Conformal validity rests on assumptions that regime-switching financial data
  violates. Adaptive weighting mitigates but does not eliminate this; we report the frequency with
  which guarantees are suspended, not only their quality when active.
- **Vendor-authored benchmark.** We publish generators, taxonomy, seeds, and baseline
  configurations, recruit an independent reviewer, and report competitor-favourable results; the
  conflict is stated in the main text.
- **Cross-engine equivalence is not total.** Regex flavours, collation, decimal semantics, and null
  ordering admit genuine divergence; we define a portable subset and fail at compile time rather
  than degrade silently, and we report what falls outside it.
- **Trust propagation is a modelling choice**, not a measurement. Multiple semirings are offered and
  derivations always displayed.
- **Semantic layer dependency.** Several results are conditioned on business declarations that
  organisations may not make; RQ10 measures precisely this, and a negative result would materially
  weaken the paper's central claim.
- **Live-shadow generalisability.** Three institutions, all in banking; per-site results are
  reported separately.
- **LLM variability.** Induction quality depends on the model; we report results across model
  classes including small self-hosted models required by air-gapped deployments.

---

## 13. Conclusion

Data quality tooling has fragmented into products that detect without proving, prove without
learning, and monitor without meaning. We have argued that the missing substrate is a **business
semantic layer whose declarations execute**, and that on top of it three properties are both
achievable and necessary: **engine-neutral compilation**, so controls outlive platforms;
**statistical calibration**, so alerts have an interpretable and budgetable false-alarm rate; and
**immutable, replayable evidence**, so control effectiveness can be proved rather than asserted. We
have shown how quality can propagate along lineage, how language models can be given a genuinely
useful role without ever being trusted with a verdict, and how the whole can be evaluated on a
public benchmark we believe the field has lacked. Prama is our attempt to build the instrument
implied by its name: not a system that decides what is true, but one through which an organisation's
belief about its data becomes *justified*.

---

## Acknowledgements
⟨TBD — design partners, advisory reviewer, open-source projects on which the work builds.⟩

## References
See [`references.bib`](references.bib).

---

<div align="center">
<img src="../assets/prama-mark.svg" width="30" alt=""/><br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.<br/>
See <a href="../../LICENSE">LICENSE</a> and <a href="../../NOTICE">NOTICE</a>. Third-party names and marks are the property of their respective owners.</sub>
</div>
