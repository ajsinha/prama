<img src="assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

> ***pramā*** (Sanskrit **प्रमा**) — *valid knowledge: a cognition that is both true and arrived at
> by a reliable means*. Its companion ***pramāṇa*** (प्रमाण) is *the instrument by which valid
> knowledge is obtained*. Prama is that instrument for an organisation's data — it does not decide
> what is true, it is how a belief about data becomes **justified**.
>
> **Declare it. Prove it. Trust it.**


---
# 20 — Competitive Analysis

**Purpose.** [01](01-landscape-survey.md) surveyed the market to find the gaps. This document does
something harder and more useful: it names the specific companies we will meet in a deal, states
honestly **where each of them is better than us today**, and defines what has to be true for Prama
to win. A competitive document that only lists our advantages is a morale exercise, not an analysis.

**The uncomfortable framing first.** "Better than all of them" is not one claim, it is seven,
because these companies are not in one market. Manta is a lineage scanner. Alation is a catalog.
Monte Carlo is an observability monitor. Collibra is a governance suite. Duco is a reconciliation
engine. We cannot be better than all of them at their own jobs, and any plan that says we will is
a plan to be mediocre at seven things. What we *can* be — and what this document argues for — is
**decisively better at the job all seven are hired for and none of them completes: making a number
trustworthy and proving it.**

---

## 1. The competitive map

Seven adjacent categories converging on one buyer. The convergence is the market's defining fact,
and it means we are compared against different competitors in different deals.

```
                          THE JOB: "can I trust this number, and prove it?"
                                            │
   ┌──────────────┬──────────────┬──────────┴────┬──────────────┬──────────────┬──────────────┐
   ▼              ▼              ▼               ▼              ▼              ▼              ▼
LINEAGE       CATALOG /      OBSERVABILITY   DQ SUITES     RECONCILIATION    MDM /       PLATFORM
SPECIALISTS   GOVERNANCE                                                     MATCHING     NATIVE
   │              │              │               │              │              │              │
Manta (IBM)   Alation       Monte Carlo    Informatica     Gresham        Reltio       Snowflake
Solidatus     Collibra      Anomalo        Ataccama        Duco           Profisee     Databricks
Octopai       Atlan         Bigeye         IBM             Adenza         Semarchy     Microsoft
erwin         Purview       Sifflet        Qlik/Talend     SmartStream    Informatica  AWS/Google
Ab Initio     OpenMetadata  Acceldata      Precisely                      MDM
Quest         DataHub       Soda/GX/dbt    Irion
   │              │              │               │              │              │              │
"where did    "what exists   "did something  "is it clean,  "do these two  "is this the  "free, and
 it come        and what      change?"        and can I      agree?"        same entity?" already
 from?"         does it                       fix it?"                                     here"
                mean?"
                                            ▼
                                    ONLY PRAMA CLAIMS:
                        "declared in business terms, executed at source,
                         calibrated statistically, and provable to a regulator"
```

**Where we meet each competitor:**

| Deal shape | Who we meet | Our posture |
|---|---|---|
| "We need BCBS 239 evidence" | **Solidatus**, Collibra, Manta | **Head-to-head. Must win outright.** |
| "Our reg reporting keeps getting rejected" | Duco, Gresham, in-house | **Head-to-head. Must win outright.** |
| "We need to know when data breaks" | Monte Carlo, Anomalo, Bigeye | **Head-to-head. Must win on precision and evidence.** |
| "We need a catalog" | Alation, Collibra, Atlan | **Do not compete. Integrate, and be the quality engine behind it.** |
| "We need lineage across our legacy ETL" | Manta, Octopai, erwin, Ab Initio | **Partial gap today. Integrate now, close selectively.** |
| "We need a golden customer record" | Reltio, Profisee, Semarchy | **Do not compete. Feed them.** |
| "Our warehouse vendor gives this free" | Snowflake, Databricks | **Consume theirs; win on what they cannot reach.** |

---

## 2. Head-to-head: the four we must beat

### 2.1 Solidatus — the most dangerous competitor in our beachhead

**What they are.** A metadata and lineage platform positioned explicitly at *regulated enterprises*,
with BCBS 239 as a named use case. They filter lineage maps to the risk-reporting datasets in scope
for BCBS 239, tag columns, transformations and reports subject to it, trace every BCBS 239 data
point back to its authoritative source with full transformation history, and provide **bi-temporal
audit trails**. Customers include **LSEG, BNY, HSBC, Deutsche Bank and Royal London** — precisely
our Wave-1 logo list. They have shipped an AI Lineage Assistant.

**Why they are dangerous.** They have chosen the same beachhead, the same regulation, the same
buyer, and the same "manually declared model is more valuable than automated discovery" insight
that underpins our semantic layer. Their bi-temporal store is the same design decision we made.
They are in the room already, with references.

**Where they are genuinely better than us today.**
- Reference customers in exactly our target accounts. We have none.
- A mature, purpose-built lineage modelling UX with years of iteration.
- Manual/declared lineage across black-box systems — the same idea as our Data Journeys, shipped.
- Established credibility with bank data-governance offices and their regulators.

**Where we beat them, and it is structural.**
- **They model; we execute.** Solidatus tells you the LCR return draws from these fourteen sources.
  It does not run a control against those sources, does not know whether the data that flowed today
  was right, and produces no evidence of a control execution. A lineage map is a *claim about
  topology*; it is not a *measurement*. BCBS 239 principle 3 is accuracy and integrity, not
  documentation of where data came from.
- **No calibrated monitoring.** No anomaly detection, no alarm-rate control, no metric history.
- **No reconciliation.** The sub-ledger↔GL break that will actually cost the bank money is
  invisible to them.
- **No verdicts, therefore no attestation.** They evidence *lineage*; we evidence *control
  outcomes*. Only the second is what an auditor signs.

**How we win the deal.** Never argue about lineage. Ask: *"Your lineage map says the FRTB return
draws from these fourteen sources. Which of them passed their controls this morning, what is the
evidence, and can you replay it?"* Then show the evidence record and the replay. If they have
already bought Solidatus, **integrate** — import their lineage as declared business lineage and
attach controls, scores and evidence to it. That is a far easier sale than displacement, and it
makes their investment more valuable, which is the argument their sponsor wants to hear.

**Risk to us.** Solidatus adds control execution. They have the model, the buyer and the
credibility; execution and evidence are a hard but finite build. **This is the single most likely
route by which a competitor reaches our position**, and it argues for shipping evidence and
reconciliation early rather than perfecting the semantic layer first.

---

### 2.2 IBM Manta — the lineage scanner library, and our real capability gap

**What they are.** Automated lineage built on **50+ out-of-the-box scanners** that parse the actual
code of ETL tools, stored procedures, BI semantic layers and reports to build a column-level map
without anyone declaring anything. IBM acquired Manta in October 2023 — its eighth acquisition that
year — to fold the scanner library into watsonx.data intelligence (formerly Watson Knowledge
Catalog) and to give watsonx an audit trail for models.

**Where they are genuinely better than us — and this is a real gap.** Our design derives lineage
from OpenLineage events, dbt manifests, warehouse access history and SQL parsing
([04, `FR-LIN`](04-requirements-functional.md)). That covers the modern stack and **not** the
Informatica PowerCenter mappings, DataStage jobs, SSIS packages, COBOL, stored procedures and
Cognos/BusinessObjects universes where a Tier-1 bank's lineage actually lives. Manta parses those.
We do not. In an estate where 60% of the transformation logic is in legacy ETL, Manta produces a map
and we produce a gap.

**Where we beat them.**
- Lineage is a *substrate*, not an outcome. Manta tells you the topology; it raises no incident,
  runs no control, and produces no verdict.
- Post-acquisition entanglement: the standalone Manta line still ships in 2026 but is increasingly
  bound to the watsonx surface with a slower visible roadmap on standalone features. Buyers notice.
- Buying Manta increasingly means buying into IBM's governance stack; buyers who do not want that
  are our buyers.

**Our answer, and it is a roadmap change.** Add a **lineage-scanner capability** to
[Wave 8](19-implementation-roadmap.md#wave-8--controls-at-scale) rather than relying on SQL parsing
alone: stored procedures (T-SQL, PL/SQL, PL/pgSQL, DB2 SQL PL), Informatica PowerCenter XML,
DataStage, SSIS, Talend, Ab Initio, and BI semantic layers. This is unglamorous parser work, it is
exactly the sort of thing that decides Tier-1 deals, and it composes with the COBOL/EBCDIC parsers
we are already committed to building. **Where we do not yet scan, integrate Manta's output** —
consuming a competitor's lineage is cheaper than losing the deal to it.

---

### 2.3 Alation — converging on us from the catalog side

**What they are.** Repositioned in 2025–26 from "data catalog" to **Agentic Data Intelligence
Platform**: cataloguing, governance, lineage and quality in one hub, with Copilot auto-curation and
semantic search, **Agent Studio** for building agents that understand organisational definitions,
a **CDE Manager**, and a **Data Quality Agent**. Base pricing runs roughly **$60,000–$198,000/year**,
with governance, DQ and AI workflows priced as separate add-ons.

**Why they matter.** CDE Manager and the Data Quality Agent are aimed directly at our territory. A
catalog vendor with the business glossary already populated has the same "semantic context makes AI
accurate" insight we do — and they have the glossary already.

**Where they are genuinely better than us.**
- Curation, search and discovery UX, refined over a decade.
- The business glossary is already populated in accounts that own Alation. That is our semantic
  layer's cold-start problem, already solved, in their product.
- Behavioural intelligence from query logs — who actually uses what — which we do not have.

**Where we beat them.**
- **A "Data Quality Agent" that runs inside a catalog inherits the catalog's reach**: what the
  catalog crawls. That is warehouses and modern tools. It is not a SWIFT feed, a COBOL extract, or
  a reconciliation between two systems.
- No calibration, no evidence ledger, no deterministic replay, no reconciliation, no attestation.
- Add-on pricing means quality is a second purchase after a large first one, and steep learning
  curves and long deployments are the consistent customer complaint.

**How we win.** Concede the catalog immediately and completely — it makes everything after it
credible. *"Keep Alation. It is a better catalog than we will ever build. Import its glossary into
Prama's semantic layer and let Prama execute, calibrate and evidence the controls, then publish
quality state back into Alation so your users see it where they already look."* We become an
Alation *multiplier*, which converts their champion into ours.

---

### 2.4 Monte Carlo and Anomalo — the observability incumbents

**What they are.** ML-first monitoring that learns normal freshness, volume, schema and distribution
and alerts on deviation without hand-written rules. Monte Carlo is the most widely deployed and has
repositioned as "Data + AI Observability". Anomalo specialises in deep unsupervised anomaly
detection across large estates with minimal configuration. Both land in the **$50K–$200K+/year**
range on volume-based pricing.

**Where they are genuinely better than us today.**
- Time to first alert. Point at a warehouse, get monitoring in an afternoon. Our semantic layer
  asks for declarations they do not need.
- Breadth and maturity of unsupervised detectors, tuned over years on real customer estates.
- Brand. "Nobody gets fired for buying Monte Carlo" is a real force in a 2026 procurement.

**Where we beat them, and it is the whole thesis.**
- **Uncalibrated alerts.** Neither emits a quantity with a false-alarm interpretation. Neither can
  answer *"how many of this month's alerts were spurious, and can I set that number?"* We can, and
  we can plot the calibration curve they cannot produce at all
  ([08 §4](08-ai-ml-capabilities.md#4-calibrated-monitoring--the-core-research-contribution)).
- **Detection ≠ proof.** Mutable results with retention windows. No hash-linked evidence, no
  deterministic replay, no attestation. Banks buy them *and* keep the spreadsheet.
- **Warehouse-shaped.** The SWIFT feed, the COBOL extract, the GL reconciliation, the trade
  repository ack file — all outside their reach.
- **Volume-based pricing punishes coverage.** Ours is per asset and control, deliberately.

**How we win.** The alert-fatigue conversation, with their own numbers. *"How many alerts did you
get last week? How many were real? What did that cost in steward hours?"* Typical answers are
30–60% precision. Then offer the falsifiable comparison: run both in shadow for 90 days, have their
stewards adjudicate blind ([15 §2.3](15-evaluation-benchmark-methodology.md)). Nobody else in this
market offers to be measured.

---

## 3. The rest of the field

| Vendor | Category | Genuinely better than us at | We beat them on | Posture |
|---|---|---|---|---|
| **Collibra** | Governance suite | Governance workflow depth; policy/regulatory-programme management; incumbency in bank data offices | DQ (an acquired engine bolted on), calibration, evidence, reconciliation, breadth beyond the warehouse. ~$170K/yr, **~6-month implementation, ROI at ~25 months**, with lineage and DQ as separately licensed modules | Integrate. Be the engine behind their programme |
| **Informatica (IDMC/CLAIRE)** | DQ suite | Widest DQ feature surface; profiling, cleansing, matching, address validation; mainframe heritage; CLAIRE rule suggestions | Modern deployment, cost, developer experience, calibration, evidence, git-ops, chat. $100K+/yr with a dedicated team | Displace on new programmes; coexist on old |
| **Ataccama ONE** | Unified DQ+MDM | Genuinely unified DQ/catalog/lineage/MDM; strong no-code; AI agent authoring rules | Opaque AI with no calibration, thin banking regulatory depth, weaker air-gap story, no reconciliation | The closest philosophical competitor. Win on calibration + evidence + banking pack |
| **Atlan** | Catalog | Gartner MQ *and* Forrester Wave Leader 2025; excellent UX; active metadata | Not a control engine. No execution, evidence, calibration or reconciliation | Integrate |
| **Microsoft Purview** | Catalog/governance | Free-ish inside a Microsoft estate; policy integration | Less mature than dedicated catalogs and **limited outside the Microsoft ecosystem** | Integrate; win multi-platform estates |
| **Octopai** (Cloudera Data Lineage) | Lineage | 60+ connectors for legacy ETL (Informatica, SSIS, Talend, DataStage, Ab Initio, SAS DI) and enterprise BI (Cognos, MicroStrategy, BusinessObjects, Qlik) | Lineage and impact analysis only; explicitly not broader governance; no controls, no evidence | Integrate; selectively close the scanner gap |
| **erwin DI / Quest / Ab Initio** | Modelling + lineage | Scanner-driven column-level cross-system lineage with reverse impact; deep modelling heritage | Heavy, dated, no calibrated monitoring, no evidence ledger | Integrate |
| **Gresham / Duco** | Reconciliation | Purpose-built recon ops at scale; Duco's AI match-field prediction and agentic rule builder set recons up in half the time, human-in-the-loop | Recon is one control type among many for us, sharing one rule model, one evidence trail and one score. They have no profiling, no DQ breadth, no semantic layer | Undercut on scope, not on recon depth. Coexist where recon ops are mature |
| **Reltio / Profisee / Semarchy** | MDM | Mastering, survivorship, golden records, steward UI | ER as a *control* rather than a mastering programme | Feed them. Never compete |
| **Soda / GX / dbt tests / Deequ / DQOps** | OSS | Free, engineering-owned, fast to start, huge communities | Everything a control plane provides. We **import their rules**; we are the upgrade path | Adopt-and-extend |
| **Snowflake DMF / Databricks LHM** | Platform-native | Free, zero integration, inside the platform | Cross-system, regulated, feed-based, evidenced. We *consume* their metrics rather than duplicate them | Consume. Never compete on the 60% |

---

## 4. Capability matrix

Legend: ●● decisive strength · ● strong · ◐ partial · ○ absent

| Capability | Solidatus | Manta | Alation | Collibra | Ataccama | Monte Carlo | Anomalo | Duco | Snowflake | **Prama** |
|---|---|---|---|---|---|---|---|---|---|---|
| Business semantic model, user-declared | ● | ○ | ● | ● | ◐ | ○ | ○ | ○ | ○ | **●●** |
| **Declarations compile into controls** | ○ | ○ | ○ | ○ | ◐ | ○ | ○ | ○ | ○ | **●● unique** |
| Automated lineage from legacy ETL | ◐ | **●●** | ◐ | ◐ | ◐ | ◐ | ○ | ○ | ○ | ○ → ◐ (Wave 8) |
| Declared / manual lineage | **●●** | ○ | ◐ | ◐ | ◐ | ○ | ○ | ○ | ○ | ● |
| Bi-temporal metadata | ● | ○ | ◐ | ◐ | ◐ | ○ | ○ | ○ | ○ | ● |
| Declarative rule language | ○ | ○ | ◐ | ◐ | ● | ○ | ○ | ◐ | ◐ | **●●** |
| Rules portable across engines | ○ | ○ | ○ | ○ | ◐ | ○ | ○ | ○ | ○ | **●● unique** |
| Statistical/ML monitoring | ○ | ○ | ◐ | ● | ● | **●●** | **●●** | ◐ | ◐ | ● |
| **Calibrated alerts (p-values, FDR budget)** | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | **●● unique** |
| Cross-system reconciliation | ○ | ○ | ○ | ○ | ◐ | ○ | ○ | **●●** | ○ | **●●** |
| **Immutable evidence + deterministic replay** | ◐ | ○ | ○ | ◐ | ◐ | ○ | ○ | ◐ | ○ | **●● unique** |
| Regulatory attestation artefacts | ◐ | ○ | ◐ | ● | ◐ | ○ | ○ | ● | ○ | **●●** |
| **Trust propagation along lineage** | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | **●● unique** |
| Financial message standards (MT/MX, FIX…) | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ● | ○ | **●● unique** |
| Mainframe / COBOL / EBCDIC | ○ | ● | ○ | ○ | ◐ | ○ | ○ | ◐ | ○ | **●** |
| Learning from steward feedback | ◐ | ○ | ◐ | ◐ | ◐ | ◐ | ◐ | ● | ○ | **●●** |
| Conversational interface | ◐ | ○ | ● | ◐ | ◐ | ◐ | ◐ | ◐ | ◐ | **●●** |
| Catalog / search / curation | ◐ | ○ | **●●** | ● | ● | ◐ | ○ | ○ | ◐ | ○ *(by choice)* |
| MDM / golden records | ○ | ○ | ○ | ◐ | ● | ○ | ○ | ○ | ○ | ○ *(by choice)* |
| Air-gapped / on-prem | ● | ● | ◐ | ◐ | ◐ | ○ | ○ | ◐ | n/a | **●●** |
| Time to first value | ◐ | ● | ◐ | ○ | ◐ | **●●** | **●●** | ◐ | **●●** | ● |
| Reference customers in Tier-1 banks | **●●** | ● | ● | ● | ● | ● | ◐ | **●●** | ● | ○ |

**Read the last two rows honestly.** Time to first value and references are the two columns that
lose deals, and they are the two where we are weakest. Everything else in this document is
irrelevant if a buyer cannot get value in a week and cannot phone a peer who uses us.

---

## 5. Where we are genuinely behind

Stated plainly, because a competitive document that omits this is worthless.

| # | Gap | Severity | Response |
|---|---|---|---|
| G1 | **No reference customers.** Every competitor above has Tier-1 logos. | Critical | Design partners on named, referenceable terms. Accept less revenue for the right to publish. |
| G2 | **Legacy ETL lineage scanners.** Manta has 50+, Octopai 60+ connectors; we have SQL parsing and OpenLineage. | High | Integrate their output now; build scanners for stored procedures, PowerCenter, DataStage and SSIS in Wave 8. |
| G3 | **Time to first value vs. Anomalo/Monte Carlo.** They monitor in an afternoon; our semantic layer asks for declarations. | High | Stage 0 of progressive formalisation must be genuinely excellent: connect → profile → proposed controls in ≤ 30 min with zero declarations (`NFR-OPS-002`). This is a product gate, not a nice-to-have. |
| G4 | **Catalog UX and behavioural intelligence.** Alation and Atlan are years ahead, and we are not building it. | Medium | Deliberate. Integrate and say so early; conceding it is a selling point. |
| G5 | **Unsupervised detector maturity.** Monte Carlo and Anomalo have years of tuning on real estates. | Medium | We compete on *calibration*, not raw detection. Champion/challenger lets us adopt any detector, including open ones. |
| G6 | **Reconciliation operations depth.** Duco and Gresham have decades of break-management workflow. | Medium | DQ-grade recon at GA; parity assessed after two banking customers (`DEC-15`). Do not overclaim. |
| G7 | **Brand and procurement safety.** Every incumbent is the safe choice. | High | Falsifiability is the answer: publish the benchmark, offer the blind shadow evaluation. Be the vendor that can be *measured* rather than the one that must be *trusted*. |

---

## 6. Pricing and total cost of ownership

| Vendor | Typical annual cost | Pricing axis | Hidden costs |
|---|---|---|---|
| Collibra | ~$170K+ | Modules + users | ~6-month implementation, ROI at ~25 months; lineage and DQ licensed separately |
| Alation | ~$60K–$198K | Platform + add-ons | Governance, DQ and AI workflows priced separately; multi-month professional services |
| Informatica IDMC | $100K+ | Consumption units | Dedicated team required |
| Monte Carlo / Anomalo | $50K–$200K+ | **Data volume / tables** | Cost grows with the coverage you want to increase |
| Manta (IBM) | Enterprise, script-count based | Scanned scripts | Entanglement with the watsonx stack |
| Solidatus | Enterprise | Users / models | Modelling effort is the real cost |
| Duco / Gresham | Enterprise | Reconciliations / volume | Ops staffing |
| **Prama** | Positioned below the suites | **Assets + controls, never data volume** | Declaration effort, which returns value at every stage |

**The pricing argument is a product argument.** Volume-based pricing means every new monitored table
costs more, so coverage is rationed — which is why estates monitored by these tools typically cover
5–15% of columns. We charge by assets and controls precisely so that the answer to *"should we add
a control?"* is never *"what will it cost?"* Superiority criterion **S5** (≥ 80% column coverage in
one week) is unreachable under a volume meter, and that is the point.

---

## 7. Win/loss playbook

### The four questions that win against everyone

Asked in this order, they work against a catalog, a lineage tool, an observability platform and a
DQ suite alike, because none of the four can answer all of them:

1. **"Show me the evidence for one control, for one day last quarter — and replay it."**
   *(Nobody else can. This is the demo.)*
2. **"How many alerts did you get last week, and how many were real? Can you set that number?"**
   *(Nobody else can set it.)*
3. **"Your GL and your sub-ledger disagree by £40,000. Which tool tells you?"**
   *(The DQ tools do not. The recon tool does not know why.)*
4. **"Your business owner says positions should tie to the GL within £1. Where does she type that,
   and what happens next?"**
   *(In every other product: nowhere, and nothing.)*

### Per-competitor one-liners

| Against | The line |
|---|---|
| Solidatus | "Your map says where the number comes from. Ours says whether it was right this morning, and proves it." |
| Manta | "Manta finds your lineage. It does not run a single control over it. Keep Manta; let us execute." |
| Alation | "Alation is a better catalog than we will build. Let it stay the catalog and let us be the engine — and publish quality back into it." |
| Collibra | "You bought a governance programme. Six months in, what is executing?" |
| Informatica | "How long would it take you to add a control to that feed today? We do it in three minutes, from a sentence." |
| Ataccama | "Their AI proposes rules and so does ours. Ask them what their false-alarm rate is and whether you can set it." |
| Monte Carlo | "Detection is not proof. Show your auditor an alert history and see what happens." |
| Anomalo | "Excellent detectors. Uncalibrated. We will run beside you for 90 days and let your stewards judge blind." |
| Duco | "Reconciliation is one control type. What about the twelve others feeding the same return?" |
| Snowflake DMF | "Use them — we read them. Now, what about the mainframe feed and the GL?" |

### When we should walk away

Discipline about losing well matters more than an extra deal:

- The buyer wants a **catalog** and nothing else → refer to Atlan or Alation.
- The buyer wants **MDM mastering** → refer to Reltio or Semarchy.
- The buyer is **single-platform, low-criticality, cost-driven** → Snowflake DMFs are genuinely the
  right answer, and saying so buys credibility for the next conversation.
- The buyer wants **lineage documentation for its own sake**, with no intent to execute controls →
  Solidatus or Manta will serve them better than we will.

---

## 8. What would have to be true for us to lose

The honest failure scenarios, in order of probability:

1. **Solidatus adds control execution and evidence.** They have the model, the buyer, the
   references and the regulatory credibility. Execution is a hard but finite build.
   *Mitigation:* ship evidence and reconciliation early; the semantic layer alone is not the moat we
   sometimes talk about it as being.
2. **Calibration fails to survive real financial data.** Our central differentiator rests on
   conformal validity under regimes that violate exchangeability.
   *Mitigation:* prove it on FinDQ-Bench in Phase 1, before it becomes a promise; degrade visibly
   rather than silently (`RSK-10`, `ASM-011`).
3. **Alation or Collibra's quality agent proves good enough** for buyers who already own the
   catalog, and the incremental spend is never approved.
   *Mitigation:* be the engine behind the catalog rather than its rival; win on the 40% they
   structurally cannot reach.
4. **The platforms absorb the 60% and buyers stop assembling.**
   *Mitigation:* consume their metrics; own cross-system, regulated and feed-based work (`RSK-01`).
5. **Time to first value loses to Anomalo before our differentiators are visible.**
   *Mitigation:* `NFR-OPS-002` is a release gate, not an aspiration. G3 above is the highest-leverage
   product investment in this document.
6. **We build seven mediocre products** by trying to beat every category at its own game.
   *Mitigation:* `CON-001…006` are enforced in planning and revisited only by explicit executive
   decision. This document's constraint list is as important as its ambition.

---

## 9. Consequences for the plan

This analysis changes three things in the existing corpus:

| Change | Where | Why |
|---|---|---|
| Add **lineage scanners** for legacy ETL and stored procedures | [19](19-implementation-roadmap.md) Wave 8 | Gap G2 against Manta and Octopai loses Tier-1 deals |
| Promote **time to first value with zero declarations** to a release gate | [05](05-requirements-nonfunctional.md) `NFR-OPS-002` | Gap G3 against Anomalo and Monte Carlo loses deals before we are heard |
| Add **catalog write-back** (publish quality state into Alation, Collibra, Atlan, Purview) | [04](04-requirements-functional.md) `FR-EXT` | Converts the strongest incumbents from rivals into distribution |
| Make **referenceability a contractual term** with design partners | [16](16-roadmap-and-delivery-plan.md) | Gap G1 is the single largest commercial risk |

---

## 10. Sources

[IBM acquires Manta](https://newsroom.ibm.com/IBM-acquires-Manta-Software-Inc-to-complement-data-and-AI-governance-capabilities) ·
[Constellation on the Manta deal](https://www.constellationr.com/insights/news/ibm-buys-manta-adds-data-lineage-tools-watsonx) ·
[MANTA for Cloud Pak for Data](https://www.ibm.com/docs/en/software-hub/5.1.x?topic=services-manta-automated-data-lineage) ·
[IBM Manta on Data Stack Index](https://datastackindex.com/data-observability/tools/ibm-manta/) ·
[Solidatus BCBS 239](https://www.solidatus.com/resource/mastering-bcbs-239-enhancing-compliance-with-data-lineage/) ·
[Solidatus lineage platform](https://www.solidatus.com/product/data-lineage/) ·
[Solidatus AI Lineage Assistant](https://www.solidatus.com/news/solidatus-launches-ai-lineage-assistant/) ·
[Alation Agentic Data Intelligence Platform](https://www.alation.com/product/agentic-data-intelligence-platform/) ·
[TechTarget on Alation's agentic suite](https://www.techtarget.com/searchdatamanagement/news/366634209/Alation-unveils-agentic-AI-suite-for-governing-critical-data) ·
[Alation pricing](https://atlan.com/alation-pricing/) ·
[Collibra pricing and implementation](https://atlan.com/collibra/pricing/) ·
[Collibra reviews](https://www.selecthub.com/p/data-governance-tools/collibra/) ·
[Octopai / Cloudera Data Lineage](https://datastackindex.com/data-observability/tools/cloudera-octopai/) ·
[Data lineage tools compared](https://www.decube.io/post/best-data-lineage-tools) ·
[Data catalog buyer's guide 2026](https://atlan.com/data-catalog-tools/) ·
[Gartner data catalog research 2026](https://atlan.com/gartner-data-catalog/) ·
[Data observability cost 2026](https://blog.anomalyarmor.ai/how-much-does-data-observability-cost-in-2026/) ·
[Anomalo vs Monte Carlo](https://www.peerspot.com/products/comparisons/anomalo_vs_monte-carlo) ·
[DataKitchen 2026 landscape](https://datakitchen.io/blog/the-2026-data-quality-and-data-observability-commercial-software-landscape/) ·
[Duco reconciliation](https://du.co/product/reconciliation/) ·
[Gresham reconciliation](https://www.greshamtech.com/solutions/reconciliations)

---

<div align="center">
<img src="assets/prama-mark.svg" width="30" alt=""/><br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.<br/>
See <a href="../LICENSE">LICENSE</a> and <a href="../NOTICE">NOTICE</a>. Third-party names and marks are the property of their respective owners.</sub>
</div>
