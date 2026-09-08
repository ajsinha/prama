<img src="assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

> ***pramā*** (Sanskrit **प्रमा**) — *valid knowledge: a cognition that is both true and arrived at
> by a reliable means*. Its companion ***pramāṇa*** (प्रमाण) is *the instrument by which valid
> knowledge is obtained*. Prama is that instrument for an organisation's data — it does not decide
> what is true, it is how a belief about data becomes **justified**.
>
> **Declare it. Prove it. Trust it.**


---
# 01 — Landscape Survey: Research, Commercial, and Open Source

**Status:** Baseline survey, September 2026
**Scope:** academic literature, standards bodies, commercial vendors, open-source projects,
cloud-native/platform-embedded capabilities, and adjacent categories (MDM, reconciliation,
observability, catalogs) that shape buyer expectations in the data-quality market.

---

## 1. Why this market exists

### 1.1 The economics

- Gartner's reference-customer survey (16 DQ vendors, 154 customers) puts the **average annual cost
  of poor data quality at ~$12.9M per organisation**; that figure is drawn from enterprises already
  sophisticated enough to be *buying* DQ software, so it is a lower bound on the naive population.
  ([Gartner](https://www.gartner.com/en/data-analytics/topics/data-quality))
- MIT Sloan / Cork University Business School work commonly cited alongside it estimates
  **15–25% of revenue** lost annually to poor data quality.
- In regulated finance the loss is not diffuse — it is enforced. The UK FCA has levied
  **~£95M in MiFID transaction-reporting fines** and **~£34.5M for EMIR reporting**; individual
  cases include **Goldman Sachs (>£34M, 220M+ reporting errors over 9.5 years)** and
  **UBS (>£27M, 135M+ errors)**.
  ([A-Team Insight](https://a-teaminsight.com/blog/emir-and-mifid-transaction-reporting-challenges-continue-to-trouble-firms-and-regulators/))
- Gartner's 2024 IT-leader poll identified **poor data quality as the #1 obstacle to GenAI
  initiatives**, which has re-priced the category: DQ is no longer a back-office hygiene spend,
  it is the gating factor on the AI budget.

**Implication for Prama:** the buying centre has shifted from *data management* to
*risk + AI enablement*. Our value narrative must be denominated in avoided regulatory loss,
avoided P&L error, and AI-readiness — not in "cleaner tables."

### 1.2 The structural failure

DataKitchen's 2026 landscape counts **50+ commercial vendors** in DQ/observability and observes
that *"the count is inflated by category overlap — catalog vendors added quality checks,
observability vendors added testing."* Their sharpest framing:

> *"Observability catches a load that silently stopped; quality testing catches a load that ran
> perfectly and delivered wrong numbers. Neither substitutes for the other."*
> ([DataKitchen, 2026](https://datakitchen.io/blog/the-2026-data-quality-and-data-observability-commercial-software-landscape/))

This is the central structural fact of the market: **buyers must currently assemble 3–5 products**
(catalog + declarative testing + ML observability + reconciliation + MDM matching) that do not
share a rule model, an evidence model, a scoring model, or an incident model. Every integration
seam is a place where audit trails break.

---

## 2. Standards, frameworks, and the vocabulary of quality

### 2.1 Dimension frameworks

| Framework | Contribution | Limitations for our purpose |
|---|---|---|
| **DAMA-DMBOK** | Canonical six dimensions: accuracy, completeness, consistency, timeliness, uniqueness, validity. Widest practitioner adoption. Some derivations add integrity, conformity, reasonableness. | Not prescriptive; no measurement semantics; no machine-readable form |
| **ISO/IEC 25012** | 15 characteristics split into *inherent* (accuracy, completeness, consistency, credibility, currentness) and *system-dependent* (availability, portability, recoverability) | Product-quality lineage (SQuaRE); no execution model |
| **ISO 8000** (esp. 8000-61/-110) | Defines *how to verify and exchange* quality data across organisational boundaries — complements 25012's *what* | Master/transactional data focus; heavy on syntax/semantic encoding |
| **DAMA-NL "How to select the right dimensions"** | Practical mapping of 60+ published dimension names onto a workable core | Advisory |
| **EDM Council DCAM / CDMC** | Capability maturity assessment; the de-facto audit yardstick used by bank data offices and their regulators | Assessment framework, not a measurement system |
| **ODCS v3.1** (Linux Foundation *Bitol*) | Machine-readable **data contract** with `schema`, `quality`, `sla`, `team`, `roles`, `servers`, `pricing` sections; official media type `application/odcs+yaml;version=3.1.0` | Contract format, not an engine; quality expressiveness still thin |
| **W3C SHACL** | Rigorous, standardised constraint language for RDF graphs; node shapes + property shapes; formal semantics | RDF-only; poor fit for columnar/streaming volumes |

**Take:** the dimension frameworks converge; the *measurement* layer is where nothing is standardised.
Prama should adopt DAMA-6 + ISO 25012 extensions as its **public taxonomy**, but define its own
**formal measurement semantics** (see [07](07-rule-language-spec.md)) — this is a genuine gap and
therefore a research contribution.

### 2.2 The contract movement

ODCS v3.1.0 shipped December 2025 under Bitol; the older Data Contract Specification is deprecated,
with tooling support only through end-2026. The enforcement analysis is unflattering: *"most data
contract tools don't enforce contracts"* — the mature, cheap layer is registration-time,
shift-left CI enforcement (`datacontract-cli`, `buf`), not runtime.
([zircote](https://zircote.com/blog/2026/04/most-data-contract-tools-dont-enforce-contracts/))

**Take:** Prama must be an ODCS-native **runtime** — import a contract, compile its `quality` block
into executable assertions, and emit conformance evidence back. That closes the acknowledged gap
in the contract ecosystem and gives us free distribution through an LF standard.

---

## 3. Academic and research landscape

### 3.1 Constraint discovery and data profiling

The dependency-discovery literature is mature and underexploited commercially.

- **Metanome** (HPI) — extensible profiling platform hosting state-of-the-art algorithms for
  unique column combinations (UCCs), functional dependencies (FDs), inclusion dependencies (INDs),
  order dependencies, and conditional variants. The canonical experimental comparison covers seven
  FD-discovery algorithms across three families (lattice-traversal, difference/agree-set,
  dependency-induction).
- **Desbordante** — a C++ high-performance successor; recent extensions cover **probabilistic FDs**
  and **efficient conditional dependency discovery**, plus **top-k approximate FD discovery**
  (important: exact FDs almost never hold on real dirty data; approximate/soft FDs do).
- **Denial constraints (DCs)** — strictly more expressive than FDs (they capture inequality and
  cross-column predicates: *"no employee earns more than their manager"*). Efficient exact
  discovery via **Hydra**; **approximate DC discovery** is the practically relevant variant.
- **Conformance constraints** (Fariha et al.) — reframes the question as *"is this tuple like the
  data the model was trained on?"*, yielding a trust measure for data-driven systems rather than a
  hard integrity predicate. Directly relevant to drift and to AI-readiness scoring.
- **Soft functional dependencies / database repairing** — the repair literature (minimal repairs,
  cost models, the chase) supplies the theory for *what a correct fix is*, which almost no
  commercial product formalises.

**Take:** commercial "AI rule generation" today is overwhelmingly LLM-prompted-from-schema. The
dependency-discovery literature offers *data-derived, provably minimal, explainable* candidate
constraints. Prama should run **both** and fuse them — statistical/algorithmic discovery for
structure, LLM for naming, business framing, and semantic plausibility. This fusion is defensible
IP and a paper contribution.

### 3.2 Error detection and repair

| System | Idea | Relevance |
|---|---|---|
| **HoloClean** | Repair as probabilistic inference over a factor graph fusing integrity constraints, co-occurrence statistics, and external signals | The reference model for *holistic* repair; expensive but principled |
| **HoloDetect** | Few-shot error detection via data augmentation over error-generation policies | Label-efficiency: the central practical constraint |
| **Raha** | *Configuration-free* error detection: an ensemble of rule-based + ML detectors, clustered and propagated from a tiny labelled sample | The right UX shape — steward labels ~20 cells, system generalises |
| **Baran** | Error *correction* via unified context representation + transfer learning across datasets | Transfer across datasets/tenants is the scaling lever |
| **ED2** | Active-learning error detection, two-dimensional (column × row) sampling | Sampling strategy for steward attention |
| **BClean** | Bayesian data cleaning; user-guided network construction | Interpretable priors, tunable by domain experts |
| **Markov-Logic hybrid frameworks** | Unify logical constraints and statistical evidence | Direct ancestor of a neuro-symbolic design |
| **ZeroED** | Hybrid **zero-shot** error detection through LLM reasoning | The 2025 frontier: no labels at all, at a precision cost |
| **MechDetect (2025)** | Detecting *data-dependent* errors (errors whose presence depends on other values) | Captures the failure class rules and univariate stats both miss |
| **Accelerating Raha/Baran** (VLDB QDB 2024) | Engineering work making the semi-supervised approach tractable | Evidence the approach is now deployable, not just publishable |

The systematic literature review *"Data cleaning and machine learning"* (Automated Software
Engineering, 2024) and *"From Cleaning before ML to Cleaning for ML"* both make the same point:
**cleaning must be objective-aware**. A repair that improves a dimension score but degrades the
downstream model or report is a regression. Almost no product measures this.

**Take (P2/P3 differentiator):** Prama should support **utility-aware remediation** — score a
candidate repair by its effect on declared downstream consumers (a report, a regulatory return,
a model), not only by dimension conformance.

### 3.3 Anomaly detection under drift

- The **UCR Time Series Anomaly Archive** (250 curated series) exists specifically because prior
  benchmarks (Yahoo, NAB, SMAP/MSL) were shown to be trivially solvable or mislabelled; benchmark
  hygiene is a real hazard when we claim superiority.
- Multivariate benchmarking (arXiv 2506.20574) shows transformer methods are highly sensitive to
  window size, step size, and the label-extraction rule from multi-dimensional anomaly scores —
  i.e., **reported SOTA is often an artefact of the evaluation protocol.**
- **Drift is the dominant real-world failure mode.** Methods assuming stationarity produce
  false-alarm storms; **D³R** (dynamic decomposition + diffusion reconstruction) explicitly targets
  non-stationary/unstable series.
- **Conformal anomaly detection** is the most important recent thread for us: post-hoc adaptive
  conformal methods over time-series foundation models yield an anomaly score **directly
  interpretable as a p-value / false-alarm rate**, with weighted-quantile calibration that survives
  distribution shift (ICLR 2026 poster; arXiv 2604.20122). The `nonconform` library separates
  scoring from calibration, selection, weighting, and sequential evidence accumulation, supporting
  **FDR-controlled** workflows.
- The industrial-CPS literature is explicit that *"excessive false alarms overwhelm operators… and
  reduce operational efficiency"* — alert fatigue is the documented adoption killer.

**Take (core research contribution):** ship anomaly monitors whose output is a **calibrated
p-value with an explicit, user-set false-alarm budget**, and apply **hierarchical FDR control**
across the asset × column × check lattice. No commercial DQ product does this today; every one of
them ships uncalibrated z-scores or opaque "ML thresholds."

### 3.4 LLMs for data quality

- **LLM-DQR** (J. Biomedical Informatics, 2025) — LLM-generated DQ rules for EHR: **97.1% coverage
  on PIC, 99.6% on MIMIC-IV**, 100% coverage for consistency rules. Evidence that LLM rule
  generation genuinely covers the space.
- **Quality Assessment of Tabular Data using LLMs and Code Generation** (arXiv 2509.10572) —
  three-stage pipeline: statistical inlier detection → LLM rule generation → LLM **code**
  generation of executable validators, with RAG over domain knowledge and consistency safeguards.
- **Template-guided rule generation and evaluation** (TU Wien) — constrains LLM output to templates,
  which is the pragmatic answer to hallucinated rules.
- Industry replications (Databricks/LatentView) confirm the operational pattern: schema + profile
  statistics → prompt → candidate rules → human review.

**Critical observation:** every credible result puts the LLM in the **rule-authoring** seat and a
deterministic engine in the **rule-execution** seat. Nobody credible has an LLM adjudicate
pass/fail per row — it is non-reproducible, unauditable, and unaffordable. This validates a
**neuro-symbolic** architecture and, in regulated finance, is the *only* defensible one.

### 3.5 Entity resolution / record linkage

- **Splink** — scalable Fellegi–Sunter probabilistic linkage with SQL/Spark/DuckDB backends and
  strong interactive diagnostics; the strongest transparent open-source baseline.
- **Zingg** — active-learning ER on Spark for MDM-scale identity resolution.
- **dedupe** — active learning, Python, memory-bound beyond ~10K records.
- **DeepMatcher / Ditto** — deep learning and transformer-based matching (Ditto reframes ER as
  sequence-pair classification with domain-knowledge injection); state of the art on benchmarks
  but opaque and expensive.
- **ZeroER**, LLM-prompting ER (arXiv 2310.06174), and **Resolvi** (a 2025 reference architecture
  for scalable/interoperable ER) show the field moving toward zero-/few-shot and standardisation.
- Recurring finding: **active learning dominates at design time** — the human budget, not the
  model, is the constraint.

**Take:** ER is not optional for banking DQ (client/counterparty/instrument duplication is a
first-order quality defect and an AML/KYC control). We should embed a Fellegi–Sunter core with an
optional transformer reranker, exposing blocking, m/u probabilities, and match weights for audit.

### 3.6 Weak supervision & label efficiency

**Snorkel**'s programmatic labelling (labelling functions + a generative model that learns LF
accuracies from their agreements/disagreements, no gold labels required) plus active learning is
the correct template for the steward feedback loop: a steward's rule *is* a labelling function, and
their triage decisions *are* labels. This is how we convert operational work into training data
without asking anyone to annotate.

### 3.7 Scoring and trust propagation

- **DQSOps** (arXiv 2303.15068) — a data-quality scoring operations framework; standardises the
  metric matrix before aggregation, and uses **PCA** to extract an overall score, avoiding the
  arbitrariness of hand-set weights.
- **Data Trust Index** (TDWI) and vendor "quality scores" (Qualytics, Acceldata) — weighted
  aggregation over dimensions, weights set per use case (a regulatory return weights accuracy;
  a real-time dashboard weights freshness).

**Gap:** nobody propagates trust **through lineage**. A gold table built from a bronze table with a
failing control is not trustworthy, but every product scores each asset independently.
Prama should define a **trust propagation semiring over the lineage DAG** — a clean, novel,
publishable contribution with obvious operational value (see [11](11-reporting-alerting-learning.md)).

### 3.8 Publication venues

**ACM JDIQ** (quarterly; multi-disciplinary — modelling/measurement, cleansing algorithms,
organisational management, real-world evaluation) is the natural home for the systems+method paper.
Alternatives/complements: **VLDB** (industrial track), **SIGMOD** (industry), **ICDE**, **CIDR**
(vision), **EDBT**, and **DEEM/aiDM** workshops for the ML-systems angle.
See [paper/](paper/) for the concrete plan.

---

## 4. Commercial landscape

### 4.1 Augmented Data Quality (the Gartner-defined category)

Gartner's Magic Quadrant for **Augmented Data Quality Solutions** (published 10 March 2025;
a 2026 edition has since run) re-weighted scoring to favour **AI-driven rule generation, anomaly
detection, and automated stewardship**, and added **profiling/remediation of non-tabular assets
(text, image, audio)** as a core criterion. Four incumbents dropped out; three newcomers entered —
*"innovation, not legacy, now influences position."*

Leaders named across the 2025/2026 cycles include **Informatica** (17th time), **Qlik/Talend**
(6th), **Ataccama** (4th consecutive), and **IBM**.

| Vendor | Product | Strengths | Weaknesses / opening for us |
|---|---|---|---|
| **Informatica** | Cloud Data Quality (IDMC), CLAIRE AI | Broadest DQ suite: profiling, cleansing, matching, address validation, monitoring; CLAIRE auto-discovers patterns, suggests rules, classifies sensitive data | Heavy, expensive ($100K+/yr, dedicated team), legacy surface area, cloud-first migration friction, weak streaming/real-time, weak reconciliation |
| **Ataccama** | ONE (+ AI Agent) | Unified DQ + catalog + lineage + observability + MDM; no-code transformation plans; AI agent auto-creates rules and detects duplicates; claims "83% faster to AI-ready data" | Vertical depth in banking regulatory reporting is thin; opaque AI (no calibration/guarantees); on-prem/air-gap story weaker than banks want |
| **Collibra** | Data Intelligence + DQ & Observability (ex-OwlDQ, acq. 2021) | Governance-catalog gravity; DQ embedded where policy lives; strong for orgs already on Collibra | DQ engine is a bolted-on acquisition; pushdown coverage uneven; priced as a suite |
| **IBM** | Knowledge Catalog, InfoSphere QualityStage, Databand | MQ Leader 2026; enterprise matching/standardisation heritage; watsonx tie-in | Fragmented across three products; classic-IBM integration tax |
| **Qlik / Talend** | Talend Data Fabric, Talend Trust Score | Integration + DQ in one; trust score is a good UX primitive | Post-acquisition roadmap churn; ELT-centric |
| **SAP** | Data Services, Information Steward | Deep for SAP estates | Non-SAP breadth limited |
| **Oracle** | Enterprise Data Quality (EDQ) | Profiling, matching, address verification, monitoring | Oracle-estate gravity; dated UX |
| **SAS** | Data Quality | Analytics integration, strong parsing/standardisation | Licensing model; niche |
| **Precisely** | Data Integrity Suite | Quality + enrichment + **best-in-class location/postal**; mainframe heritage (critical in banks) | Suite is federated, not unified; UX inconsistent |
| **Experian / Melissa** | Address, email, phone verification | Reference-data verification depth we should *integrate*, not rebuild | Point solutions |
| **Irion** | Irion EDM | Declarative, SQL-pushdown DQ with strong EU banking regulatory footprint (a close philosophical cousin to our design) | Limited AI/ML; limited outside EU banking |

### 4.2 Data observability (the ML-first challengers)

| Vendor | Position | Notes |
|---|---|---|
| **Monte Carlo** | Most widely deployed; ML learns normal freshness/volume/schema/distribution/lineage, alerts without hand-configured rules; repositioned as **"Data + AI Observability"** covering model inputs, agent behaviour, output drift | Credit/volume-based enterprise pricing; weak on declarative business rules and on regulatory evidence |
| **Anomalo** | ML-first anomaly detection, minimal config, fast setup | Shallow rule expressiveness; limited pushdown breadth |
| **Bigeye** | Precise controls, SLA-driven checks, transparent monitoring logic, lineage-driven RCA | Positioned for teams that want explicit control |
| **Acceldata** | Enterprise data observability + **agentic data management (ADM)**: agents coordinating quality, lineage, profiling, cost | Broad but heavy; agent autonomy raises audit questions |
| **Soda** | Soda Core (OSS, SodaCL YAML checks compiled to SQL) + Soda Cloud control plane | Best-in-class *declarative ergonomics*; a direct benchmark for our DSL |
| **Sifflet** | AI-augmented observability bridging technical/business; cost-efficient positioning, transparent pricing | Mid-market |
| **Metaplane** (Datadog) | ML anomaly detection in warehouses; now inside Datadog | Consolidation signal: observability is being absorbed by APM |
| **Validio** | ML monitoring with **segmented** anomaly detection (per-segment thresholds) + lineage | Segmentation is a feature we must match |
| **Lightup** | Threshold-free anomaly detection on production pipelines | |
| **Datafold** | **Data diff** — value-level regression testing across code changes; CI/CD-native | Different job: change safety, not production monitoring. We need this primitive. |
| **Telmai** | No-code onboarding, automatic profiling/monitoring, open-format friendly | |
| **Qualytics** | Infers rules automatically, guided by business context; validates **at the moment of consumption**; explicit quality-score model | Closest to our thesis among observability vendors |
| **DQLabs**, **Synq**, **Pantomath**, **Kensu**, **Rakuten SixthSense**, **DataKitchen (TestGen)**, **ICEDQ**, **RightData**, **FirstEigen DataBuck** | Long tail; ICEDQ/RightData notable for **ETL/migration testing**, FirstEigen for ML-generated rules | ICEDQ's migration-testing niche matters in banking (core-banking replatforms) |

### 4.3 Platform-embedded quality (the "good enough, free" threat)

This is the most under-appreciated competitive force: the warehouse/lakehouse vendors are giving
away the 60% case.

- **Snowflake Horizon — Data Metric Functions (DMFs):** user-defined and system metrics (null rate,
  uniqueness, freshness) attached to tables, evaluated on a schedule, results in system views.
- **Databricks:** **Lakehouse Monitoring** (auto profiling + drift + generated dashboard, for data
  *and* models), **DLT/Declarative Pipelines Expectations** (inline constraints with
  drop/fail/quarantine actions), **Unity Catalog** integration, and **DQX** (Databricks Labs OSS)
  for rule definition/management.
- **AWS Glue Data Quality:** managed service built on **Deequ**, with **rule recommendation**.
- **Microsoft Purview:** governance/catalog with quality, classification, policy.
- **Confluent / Kafka Schema Registry:** versioned schemas, compatibility checks, producer-side
  validation — structural enforcement *at ingestion*, before anything downstream sees the record;
  Flink adds custom real-time rules (range checks, missing IDs, volume spikes).

**Take:** we must (a) be *better* than free at the 60% case, and (b) be *the only option* for the
40% the platforms structurally cannot do — cross-system reconciliation, cross-platform lineage-aware
scoring, regulatory evidence, mainframe/feed formats, and human workflow. We should also **consume**
native DMFs/expectations as inputs rather than duplicating them.

### 4.4 Adjacent categories that shape the buyer

**Reconciliation & controls (bank-critical, ignored by observability vendors):**
- **Gresham** Control Cloud — enterprise reconciliation for banks, broker-dealers, asset managers,
  insurers, payments; ML for intelligent matching.
- **Duco** — cloud-native reconciliation/data automation for capital markets; **AI match-field
  prediction and an agentic rule builder**, "reconciliations set up in half the time," human-in-the-loop
  validation that trains the models.
- Breaks here create *settlement, reporting, regulatory, and operational risk* — the same evidence
  and workflow substrate as DQ, sold separately at high prices.

**MDM / golden records:**
- **Reltio** (multidomain match/merge/survivorship), **Semarchy xDM** (matchers → duplicate clusters
  → survivorship rules → golden record), **Profisee** (ML matching engine + side-by-side steward
  review), plus **Informatica MDM**, **IBM**, **Ataccama**.
- Survivorship rules are declarative rule systems in their own right; our rule language should be
  expressive enough to host them.

**Catalogs / metadata (where quality gets *displayed*):**
- **OpenMetadata** (OSS; quality tests, incident manager with **root-cause analysis**, ontology/RDF
  projection enabling SPARQL + SHACL + reasoning), **DataHub** (OSS + Acryl), **Atlan**, **Alation**,
  **data.world**, **Select Star** (→ Snowflake), **Stemma** (→ Teradata), **Apache Atlas**, **Amundsen**.
- Lineage is the substrate for RCA: *"organisations with comprehensive lineage reduce resolution time
  by 60%+"*; column-level lineage is generated by SQL parsing across 100+ platforms.

**ML/AI observability:** **Evidently AI** (OSS drift/monitoring), **Deepchecks**, **Arize**,
**WhyLabs** — converging on the same alerting substrate from the model side. Monte Carlo's
repositioning shows the categories are merging.

---

## 5. Open-source landscape

| Project | Model | Strengths | Limits |
|---|---|---|---|
| **Great Expectations (GX)** | Validation-as-code; ~300 expectations + custom; Data Docs; profiling | Unmatched breadth of expectations and integrations; human-readable | Heavy engineering lift; config sprawl; Data Docs is not an enterprise UI; no ML monitoring |
| **Soda Core / SodaCL** | YAML checks compiled to SQL; broad connectors | Best ergonomics in the space; fast adoption; the DSL to beat | Limited expressiveness for cross-dataset/temporal logic; cloud for anything collaborative |
| **Deequ / PyDeequ** | Scala/Spark; analyzers → metrics → constraints; **constraint *suggestion***; metrics repository; anomaly detection on metric history | Scales to massive Spark data without sampling; the metrics-repository pattern is the right architecture | Spark-only; JVM; no UI |
| **dbt tests** (+ **dbt-expectations**, **elementary**) | Tests in the transformation layer | Shift-left, zero extra infra, huge community | Only covers what dbt models; warehouse-only; no runtime/streaming |
| **Databricks DQX** | Rule definition/management for Spark/DLT | Native, quarantine semantics | Databricks-only |
| **Spark-Expectations** | Row/aggregate rules with quarantine in Spark | | Spark-only |
| **DQOps** | OSS DQ + observability platform: **150+ built-in checks**, UI *and* YAML, CI/CD-friendly, incident management, connectors (BigQuery, Snowflake, Postgres, Redshift…) | The most complete OSS *platform* (not library); YAML+UI duality validates our approach | Smaller ecosystem; limited ML sophistication |
| **Apache Griffin** | Batch+streaming DQ on Hadoop/Spark | Streaming heritage | Effectively dormant |
| **MobyDQ**, **Cuallee**, **Piperider**, **datatest**, **Pandera**, **pointblank** | Focused libraries | Cheap to embed | Not platforms |
| **Evidently AI** | OSS drift/data-quality monitoring for ML | Excellent drift reports/tests | ML-dataset shaped |
| **OpenLineage / Marquez** | Lineage event standard + store | The interop standard we should emit | Lineage only |
| **OpenMetadata / DataHub / Amundsen / Atlas** | Metadata platforms with DQ surfaces | Free catalog + incident manager + RCA | Quality engines are secondary |
| **Splink / Zingg / dedupe / DeepMatcher** | Entity resolution | Production-grade linkage | Not integrated with DQ workflow |
| **Metanome / Desbordante** | Research profilers (FD/UCC/IND/DC discovery) | The algorithmic goldmine | Research-grade packaging |
| **datacontract-cli** | ODCS/DCS contract linting + testing in CI | The shift-left enforcement point | Contract scope only |
| **W3C SHACL engines** (TopBraid, pySHACL, Ontotext, Fluree) | Graph constraint validation | Standardised, formal | RDF-only; scale limits |

**Take:** the OSS layer has solved *checking a table against a rule* many times over. Nothing OSS
has solved: cross-source reconciliation, calibrated ML alerting, lineage-aware trust, regulatory
evidence, steward workflow at bank scale, or a genuinely good UI. That is exactly the value gap.

---

## 6. Capability matrix — where everyone actually stands

Legend: ● strong · ◐ partial · ○ absent/weak

| Capability | Informatica | Ataccama | Collibra | Monte Carlo | Soda | GX | Deequ | DQOps | Snowflake/DBX | **Prama target** |
|---|---|---|---|---|---|---|---|---|---|---|
| Declarative rule DSL | ◐ | ● | ◐ | ○ | ● | ● | ◐ | ● | ◐ | **●●** |
| Rules portable across engines | ○ | ◐ | ○ | ○ | ◐ | ◐ | ○ | ◐ | ○ | **●●** |
| Full pushdown, no data movement | ◐ | ● | ◐ | ● | ● | ◐ | ● | ● | ● | **●●** |
| Statistical/ML monitors | ◐ | ● | ● | ●● | ◐ | ○ | ◐ | ◐ | ◐ | **●●** |
| **Calibrated alerts (p-values/FDR)** | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | **●● (novel)** |
| Automated rule induction from data | ◐ | ● | ◐ | n/a | ○ | ○ | ● (suggestions) | ◐ | ◐ | **●●** |
| LLM rule authoring, symbolic execution | ◐ | ● | ◐ | ○ | ◐ | ○ | ○ | ○ | ◐ | **●●** |
| Streaming / in-flight validation | ◐ | ◐ | ○ | ◐ | ◐ | ○ | ◐ | ○ | ◐ | **●●** |
| Files/feeds: fixed-width, COBOL, EDI | ● | ◐ | ○ | ○ | ○ | ◐ | ○ | ○ | ○ | **●●** |
| Financial protocols (MT/MX, FIX, FpML) | ◐ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | **●● (unique)** |
| **Cross-system reconciliation** | ◐ | ◐ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | **●● (unique in DQ)** |
| Entity resolution / matching | ● | ● | ◐ | ○ | ○ | ○ | ○ | ○ | ○ | **●** |
| Lineage-aware RCA | ◐ | ● | ● | ●● | ◐ | ○ | ○ | ◐ | ◐ | **●●** |
| **Trust propagation over lineage** | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | **●● (novel)** |
| Regulatory evidence / attestation | ◐ | ◐ | ● | ○ | ○ | ○ | ○ | ○ | ○ | **●●** |
| Steward workflow & remediation | ● | ● | ● | ◐ | ◐ | ○ | ○ | ◐ | ○ | **●●** |
| Learning from steward feedback | ◐ | ◐ | ◐ | ◐ | ○ | ○ | ○ | ○ | ○ | **●●** |
| Conversational interface | ◐ | ◐ | ◐ | ◐ | ◐ | ○ | ○ | ○ | ◐ | **●●** |
| Air-gapped / on-prem / BYO-LLM | ● | ◐ | ◐ | ○ | ◐ | ● | ● | ● | n/a | **●●** |
| Unstructured/document quality | ◐ | ◐ | ○ | ◐ | ○ | ○ | ○ | ○ | ◐ | **●** |
| Open standards (ODCS, OpenLineage) | ○ | ◐ | ◐ | ◐ | ◐ | ◐ | ○ | ◐ | ◐ | **●●** |

Six cells in the "Prama target" column are marked **unique/novel**. Those six are the product.

---

## 7. Synthesised findings

1. **The category is fragmenting, not consolidating on capability.** Buyers assemble 3–5 tools; the
   seams destroy auditability. A genuinely unified control plane is a structural, not incremental, win.
2. **"AI" in this market means prompted rule suggestions and uncalibrated anomaly scores.** The
   research frontier — conformal calibration, FDR control, dependency discovery, semi-supervised
   detection, utility-aware repair — is essentially unexploited commercially. This is a rare gap:
   defensible, publishable, and immediately valuable.
3. **The platforms will eat the easy 60%.** Our roadmap must not compete with free DMFs; it must
   consume them and own the hard 40%.
4. **Regulated finance is systematically underserved.** Observability vendors have no evidence model,
   no reconciliation, no message-standard awareness, and no air-gap story. Reconciliation vendors
   (Gresham, Duco) have workflow and matching but no DQ breadth or ML depth. Nobody is in the middle.
5. **Alert fatigue is the #1 documented cause of abandonment**, and the literature already supplies
   the fix (calibrated p-values + FDR budgets). Shipping it is a wedge.
6. **Human attention is the scarce resource.** Every credible research line (Raha, ED2, Snorkel,
   active-learning ER, Duco's human-in-the-loop) optimises steward labels, not model FLOPs. Our
   learning loop must be designed around that economy.
7. **Standards give us free distribution.** ODCS runtime conformance, OpenLineage emission, SHACL
   for graph assets, and ISO 8000/25012 vocabulary mapping make us the interoperable choice.

---

## 8. Source index

Landscape & market: [DataKitchen 2026 landscape](https://datakitchen.io/blog/the-2026-data-quality-and-data-observability-commercial-software-landscape/) ·
[Gartner MQ ADQ 2025](https://www.gartner.com/en/documents/6246519) ·
[Ataccama on MQ 2025](https://www.ataccama.com/blog/whats-new-in-the-2025-gartner-magic-quadrant-for-augmented-data-quality-solutions) ·
[IBM MQ 2026](https://www.ibm.com/new/announcements/ibm-named-a-leader-in-the-2026-gartner-magic-quadrant-for-augmented-data-quality-solutions) ·
[Informatica MQ 2025](https://www.informatica.com/about-us/news/news-releases/2025/03/20250313-informatica-named-a-leader-in-the-2025-gartner-magic-quadrant-augmented-data-quality-solutions-for-the-17th-time.html) ·
[Gartner data quality topic](https://www.gartner.com/en/data-analytics/topics/data-quality) ·
[Atlan observability tools](https://atlan.com/know/data-observability-tools/) ·
[DQLabs buyer guide](https://www.dqlabs.ai/blog/top-data-observability-vendors-right-now-a-practitioners-buyer-guide/)

Standards: [ODCS v3.1](https://bitol-io.github.io/open-data-contract-standard/v3.1.0/) ·
[Bitol](https://bitol.io/) ·
[Contract enforcement critique](https://zircote.com/blog/2026/04/most-data-contract-tools-dont-enforce-contracts/) ·
[ISO 8000 summary](https://quality.arc42.org/standards/iso-8000) ·
[DAMA-NL dimension selection](https://dama-nl.org/wp-content/uploads/2020/11/How-to-Select-the-Right-Dimensions-of-Data-Quality-v1.1-d.d.-14-Nov-2020.pdf) ·
[Comparison of DQ frameworks (MDPI 2025)](https://www.mdpi.com/2504-2289/9/4/93) ·
[SHACL for DQ assessment](https://arxiv.org/html/2507.22305v1) ·
[SHACL review](https://arxiv.org/pdf/2112.01441)

Research: [Metanome](https://hpi.de/en/database-group/projects/data-integration-projects/data-profiling-and-analytics/metanome-data-profiling/) ·
[Approximate denial constraints (VLDB)](https://dl.acm.org/doi/10.14778/3368289.3368293) ·
[Desbordante conditional dependencies](https://arxiv.org/html/2607.04030) ·
[Top-k approximate FDs](https://arxiv.org/pdf/2605.24925) ·
[Conformance constraints](https://arxiv.org/pdf/2003.01289) ·
[Raha/Baran (CIDR 2021)](https://vldb.org/cidrdb/papers/2021/cidr2021_paper14.pdf) ·
[Accelerating Raha/Baran (QDB 2024)](https://www.vldb.org/workshops/2024/proceedings/QDB/QDB-1.pdf) ·
[BClean](https://arxiv.org/pdf/2311.06517) ·
[Markov-Logic cleaning](https://arxiv.org/pdf/1903.05826) ·
[ZeroED](https://arxiv.org/pdf/2504.05345) ·
[MechDetect](https://arxiv.org/pdf/2512.04138) ·
[Data cleaning + ML SLR](https://link.springer.com/article/10.1007/s10515-024-00453-w) ·
[UCR anomaly archive benchmarking](https://onlinelibrary.wiley.com/doi/full/10.1111/exsy.13767) ·
[Multivariate AD benchmark](https://arxiv.org/abs/2506.20574) ·
[Adaptive conformal AD](https://arxiv.org/abs/2604.20122) ·
[Conformal AD in Python / nonconform](https://arxiv.org/pdf/2605.13642) ·
[FDR-guaranteed novelty detection](https://arxiv.org/pdf/2208.06685) ·
[LLM-DQR](https://www.sciencedirect.com/science/article/abs/pii/S1532046425001807) ·
[LLM tabular DQ + code gen](https://arxiv.org/abs/2509.10572) ·
[DQSOps scoring](https://arxiv.org/pdf/2303.15068) ·
[Snorkel](https://arxiv.org/pdf/1711.10160) ·
[Awesome Entity Resolution](https://github.com/OlivierBinette/Awesome-Entity-Resolution) ·
[Resolvi ER architecture](https://arxiv.org/html/2503.08087v2) ·
[JDIQ CFP](https://dl.acm.org/journal/jdiq/call-for-papers)

Banking/regulatory: [BCBS 239 (Wikipedia)](https://en.wikipedia.org/wiki/BCBS_239) ·
[Deloitte RDARR](https://www.deloitte.com/us/en/services/consulting/articles/basel-risk-data-aggregation-and-reporting-requirements.html) ·
[FCA fines / reporting quality](https://a-teaminsight.com/blog/emir-and-mifid-transaction-reporting-challenges-continue-to-trouble-firms-and-regulators/) ·
[AnaCredit instructions v4.6](https://www.bcl.lu/en/Regulatory-reporting/Etablissements_credit/AnaCredit/Instructions/AnaCredit_instructions_EN.pdf) ·
[ISO 20022 (Swift)](https://www.swift.com/standards/iso-20022/iso-20022-standards) ·
[FINOS CDM](https://cdm.finos.org/docs/design-principles/) ·
[GLEIF ISIN-to-LEI](https://lei-worldwide.com/isin.html) ·
[DORA + EU AI Act for FIs](https://iomete.com/resources/blog/dora-eu-ai-act-financial-institutions-data-infrastructure)

Platform-native: [Databricks Lakehouse Monitoring](https://docs.databricks.com/aws/en/data-governance/unity-catalog/data-quality-monitoring) ·
[Databricks DQ overview](https://www.databricks.com/discover/pages/data-quality-management) ·
[Confluent streaming DQ](https://www.confluent.io/blog/making-data-quality-scalable-with-real-time-streaming-architectures/) ·
[Schema Registry policy enforcement](https://www.kai-waehner.de/blog/2023/10/16/data-quality-and-policy-enforcement-for-apache-kafka-with-schema-registry/) ·
[DQOps](https://github.com/dqops/dqo) ·
[OpenMetadata RCA](https://docs.open-metadata.org/latest/how-to-guides/data-quality-observability/incident-manager/root-cause-analysis)

Adjacent: [Gresham reconciliation](https://www.greshamtech.com/solutions/reconciliations) ·
[Duco reconciliation](https://du.co/product/reconciliation/) ·
[Reltio match/merge/survivorship](https://docs.reltio.com/en/explore/get-a-crash-course/get-ready-to-turn-your-data-into-action/learn-about-multidomain-mdm/reltio-match-merge-and-survivorship) ·
[Semarchy matching](https://www.semarchy.com/doc/semarchy-xdm/xdm/5.3/Design/matching/matching.html) ·
[Profisee survivorship](https://profisee.com/blog/mdm-survivorship/) ·
[Sifflet RCA](https://www.siffletdata.com/blog/root-cause-analysis) ·
[Acceldata governance agents](https://www.acceldata.io/blog/why-governance-agents-redefine-data-stewardship)

---

<div align="center">
<img src="assets/prama-mark.svg" width="30" alt=""/><br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.<br/>
See <a href="../LICENSE">LICENSE</a> and <a href="../NOTICE">NOTICE</a>. Third-party names and marks are the property of their respective owners.</sub>
</div>
