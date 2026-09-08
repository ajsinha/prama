<img src="assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

> ***pramā*** (Sanskrit **प्रमा**) — *valid knowledge: a cognition that is both true and arrived at
> by a reliable means*. Its companion ***pramāṇa*** (प्रमाण) is *the instrument by which valid
> knowledge is obtained*. Prama is that instrument for an organisation's data — it does not decide
> what is true, it is how a belief about data becomes **justified**.
>
> **Declare it. Prove it. Trust it.**


---
# 03 — The Business Semantic Layer & Data Estate Model

> **This is the conceptual heart of Prama.**
> Prama is not a DBA tool and not a pipeline-monitoring tool. It is the place where **business
> owners and data architects describe their data estate in business terms**, declare how the
> parts relate to each other, and then let the platform reach out through configured connectors,
> read the data, and turn those declarations into quality conclusions, patterns, trends, and
> reports.

Everything in [04 — Functional Requirements](04-requirements-functional.md) area `FR-MET` is the
requirements form of this chapter.

---

## 1. The problem this solves

Every existing tool in the landscape starts from the **physical** world: connect to a warehouse,
crawl tables, monitor columns. The organisational chart of the tool matches the organisational
chart of the *infrastructure*, not the *business*.

The consequences are severe and universal:

| Symptom | Root cause |
|---|---|
| "We have 40,000 monitored columns and no idea which matter." | No business criticality model; every column is equal |
| "The tool says `T_CPTY_EXP_D` is 97% healthy. Is our counterparty exposure right?" | No mapping from physical artefacts to business concepts |
| "Finance and Risk disagree on what 'exposure' means and both have controls." | No shared semantic definition; controls encode two different meanings |
| "The GL doesn't tie to the sub-ledger and no tool noticed." | Relationships between datasets are never declared, so never checked |
| "Lineage is broken because the mainframe job is a black box." | Technical lineage discovery cannot cross system boundaries a human can describe in one sentence |
| "Only three people can author a control, and they're all engineers." | Authoring requires knowledge of physical schemas |

The declarations a business owner can make in five minutes — *"this feed is the daily positions
extract from the front office; it should tie to the sub-ledger at the account level with a €1
tolerance; it arrives by 06:30 on business days; the notional field is in trade currency"* —
encode more useful quality knowledge than a month of automated column profiling. **No product on
the market lets them say it.**

---

## 2. The model

Prama's semantic layer is a small, deliberately opinionated set of objects. Small enough that a
business person can learn it in an afternoon; expressive enough to generate real controls.

```
                    ┌───────────────────┐
                    │  Business Domain  │  (Risk, Finance, Treasury, Client)
                    └─────────┬─────────┘
                              │ contains
        ┌─────────────────────┼──────────────────────┐
        ▼                     ▼                      ▼
┌───────────────┐    ┌─────────────────┐    ┌─────────────────┐
│Business Concept│◄──│    Dataset      │───►│ Business Process│
│ (Party, Trade, │ is│  (logical unit  │part│  (Data Journey) │
│  Position, …)  │about│  of data)     │ of │                 │
└───────┬───────┘    └────────┬────────┘    └─────────────────┘
        │ has                 │ has              │ steps are
        ▼                     ▼                  │ Datasets
┌───────────────┐    ┌─────────────────┐         │
│   Property    │◄───│   Attribute     │         │
│  (canonical)  │maps│ (business field)│         │
└───────────────┘    └────────┬────────┘         │
                              │ bound to         │
                              ▼                  │
                     ┌─────────────────┐         │
                     │Physical Binding │◄────────┘
                     │ (table.column,  │
                     │  file field, …) │
                     └────────┬────────┘
                              │ reached via
                              ▼
                     ┌─────────────────┐
                     │   Connector     │
                     └─────────────────┘

        Datasets ──── Business Relationship ────► Datasets
                 (reconciles-with, derives-from,
                  references, feeds, mirrors, …)
```

### 2.1 Dataset — the central object

A **Dataset** is *whatever a business person calls "a set of data"*. It is explicitly **not**
"a table". Its physical realisation is a separate, changeable concern.

A Dataset may be bound to:

| Shape | Example |
|---|---|
| A single table/view | `RISK.POSITIONS_EOD` |
| A set of tables (union) | 12 regional position tables that together form "Global Positions" |
| An entire schema or database | "The Murex trade store" |
| A single file feed | `POS_EXTRACT_YYYYMMDD.txt` from the front office, daily |
| A set of related feeds | Header + detail + trailer files delivered as one logical batch |
| A stream / topic | `trades.executed.v3` on Kafka |
| An API endpoint | `GET /v2/accounts` on the core banking platform |
| A report or return | The FR Y-14Q schedule as submitted |
| A query | A registered SQL/API query treated as a virtual dataset |
| Nothing yet | A *declared but unbound* dataset — the business knows it exists before IT connects it |

**A dataset can be declared before it can be read.** This is essential: architects map the estate
first, connectivity follows. An unbound dataset still participates in relationships, still appears
on the estate map, and still shows as a *coverage gap* on the metadata scorecard.

**Dataset properties (business-declared):**

- Name, business description, purpose ("why does this exist")
- Owner (accountable business person), steward (operational), technical custodian
- Domain, criticality tier (e.g. Tier 1 = regulatory/financial reporting)
- **Grain**: what one record represents ("one position per account per instrument per day")
- **Identity**: the business key(s) that make a record unique
- **Temporality**: point-in-time snapshot / event stream / slowly-changing / append-only /
  as-of-dated, plus the as-of and effective-date attributes
- **Expected rhythm**: arrival schedule, frequency, business calendar, cut-off time, expected volume
  range and its drivers ("volume tracks trading days; month-end is 3× normal")
- **Authoritativeness**: golden source / derived copy / replica / extract / vendor-supplied
- Retention, jurisdiction/residency, sensitivity classification
- Lifecycle state: proposed / active / deprecated / retired, with dates

Every one of these is a *quality assertion generator*. Declaring a grain generates a uniqueness
control. Declaring a cut-off generates a timeliness control. Declaring a volume driver generates a
seasonality-aware volume monitor. **Metadata authored here is not documentation — it is executable.**

### 2.2 Attribute — the business field

An **Attribute** is a business-meaningful field of a Dataset. It is bound to one or more physical
columns/fields, possibly with a transformation.

- Business name and definition (prose, written by a human, reviewed)
- Business **interpretation**: what the value *means*, including sign conventions, inclusions and
  exclusions ("gross of collateral", "excludes intercompany")
- **Semantic type**: ISIN, LEI, IBAN, currency code, monetary amount, rate, percentage, date, …
- **Unit / currency / scale / precision**, and whether it is denominated (and in which attribute)
- **Value domain**: enumerated code set (with the authoritative code list reference), range,
  pattern, or free text
- **Optionality**: mandatory always / mandatory conditionally (with the condition in business
  terms) / optional
- **Criticality**: is this a **Critical Data Element (CDE)**? Linked to which regulatory or
  financial reporting obligation?
- **Sensitivity**: PII / MNPI / restricted, with masking policy
- **Expected behaviour**: stable / slowly changing / volatile; expected distribution shape;
  known legitimate spikes
- Source-of-truth attribute elsewhere in the estate (if this is a copy)
- Glossary term linkage

### 2.3 Business Concept — the shared vocabulary

A **Business Concept** is a canonical thing the business talks about: *Party, Counterparty,
Legal Entity, Account, Instrument, Trade, Position, Transaction, Balance, Exposure, Collateral,
Product, Customer, Employee, Branch*. Concepts have **Properties**.

Datasets are declared to be **about** one or more Concepts; Attributes **map to** Concept
Properties. This is a lightweight ontology — deliberately not OWL, but exportable to RDF/SHACL
for customers who want it.

Why it matters:

1. **Cross-dataset consistency becomes expressible.** If `Party.LEI` is a Concept Property mapped
   in 23 datasets, a single control ("every LEI is valid, active in GLEIF, and consistent for the
   same party across all datasets") applies estate-wide.
2. **Semantic-type inheritance.** A dataset attribute mapped to `Instrument.ISIN` automatically
   inherits ISIN format, check-digit, and master-existence controls from the domain pack.
3. **Disagreement becomes visible.** When Finance and Risk map different attributes to
   `Exposure.GrossNotional` with different definitions, the platform *shows the conflict* instead
   of silently hosting two truths.
4. **AI grounding.** The concept model is the retrieval context that makes LLM rule induction and
   the chat assistant accurate rather than plausible.

### 2.4 Business Relationship — the declaration that makes the estate a map

This is the most valuable and most novel object. A **Business Relationship** is a *typed,
user-declared, executable* statement about how two (or more) Datasets relate.

| Relationship type | Business meaning | What Prama derives from it |
|---|---|---|
| `REFERENCES` | Records in A point at records in B (business FK) | Referential-integrity control; orphan detection; key-coverage monitor |
| `RECONCILES_WITH` | A and B should agree, on these keys, within this tolerance | Full reconciliation control with break workflow ([FR-REC](04-requirements-functional.md#g-reconciliation--cross-system-controls-fr-rec)) |
| `DERIVES_FROM` | B is computed from A (aggregation, filter, transformation) | Aggregate-parity control; trust propagation edge; impact analysis |
| `FEEDS` | A is delivered into B by a process | Business lineage edge; latency/arrival chain; RCA path |
| `MIRRORS` / `REPLICATES` | B is a copy of A (replica, extract, cache) | Row-count and content-parity control; staleness monitor |
| `AGGREGATES` | B is a summarisation of A at a coarser grain | Sum/count roll-up control with tolerance |
| `ENRICHES` | B adds attributes to A from a reference source | Enrichment-coverage and provenance control |
| `SUPERSEDES` | B replaces A from a date | Migration-parity control; dual-run comparison |
| `SAME_ENTITY_AS` | A and B describe the same real-world entities | Entity-resolution / duplicate control; identifier-consistency control |
| `TEMPORAL_SUCCESSOR` | B is the next period of A | Roll-forward control (opening + movements = closing) |
| `PARENT_OF` / `HIERARCHY` | Organisational or product hierarchy between datasets | Hierarchy completeness, cycle detection, orphan-node detection |
| `MUTUALLY_EXCLUSIVE` | A record should appear in A or B, never both | Overlap detection |
| `TOGETHER_COMPLETE` | A ∪ B should cover the full population | Population-completeness control against a declared universe |

Each relationship carries: join/match keys (in **business attribute** terms, not columns),
cardinality, tolerance and materiality, timing offset (B is A+1 day), a filter scope, a business
description, and an owner.

**This is the mechanism by which a business declaration becomes a running control.** The user says
*"the sub-ledger reconciles with the GL by account and cost centre, in reporting currency, to
within €1, one day in arrears"*. Prama emits a reconciliation assertion, schedules it, runs it via
the configured connectors, classifies the breaks, routes them, scores the result, and reports it.
No SQL was written by anyone.

### 2.5 Business Process / Data Journey

A **Data Journey** is an ordered chain of Datasets and the Relationships between them, named after
a business process: *"Loan origination → booking → sub-ledger → GL → FINREP"*,
*"Trade capture → confirmation → settlement → position → risk → FRTB return"*.

Journeys give:

- **Business lineage that does not depend on technical lineage discovery** — it works across
  mainframes, vendor packages, manual steps, and spreadsheets, because a human declared it.
- **End-to-end SLA and latency measurement** across the whole chain.
- **A natural unit of ownership and reporting**: "the health of the FRTB journey" is a sentence a
  CRO understands. "The health of `dw_prd.fct_pos_v2`" is not.
- **The right RCA scope**: when the return is wrong, walk the journey backwards.

### 2.6 Domain, ownership, and the estate map

Domains group datasets, concepts, and journeys under an accountable owner. The **Estate Map** is
the primary landing surface of the product: a navigable, business-labelled graph of domains →
journeys → datasets → relationships, with quality state rendered directly on it.

---

## 3. Progressive formalisation — the adoption contract

The model above could be a two-year modelling project. It must never be. The design rule:

> **Every declaration must pay for itself immediately, and nothing may be mandatory.**

| Stage | User effort | What they get back |
|---|---|---|
| **0. Nothing declared** | Configure a connector, point at a source | Auto-discovery, profiling, semantic-type inference, baseline anomaly monitors, an estate inventory |
| **1. Name and own** | Name a dataset, set owner, criticality, description | It appears on the estate map; ownership routing works; it enters the scorecard |
| **2. Declare grain & rhythm** | One sentence each | Uniqueness control, freshness control, volume monitor with the right seasonality |
| **3. Interpret attributes** | Mark CDEs, set semantic types, define value domains | Semantic-type control packs auto-apply; induction gets sharply more accurate |
| **4. Declare relationships** | Draw a line between two datasets, pick a type | Referential integrity, reconciliation, roll-forward, parity controls — the highest-value checks in the product |
| **5. Map to concepts** | Map attributes to canonical properties | Estate-wide consistency controls; conflict detection; the chat assistant becomes genuinely accurate |
| **6. Declare journeys** | Order the datasets in a business process | End-to-end SLA, business lineage, journey-level RCA and reporting |

**The system meets the user at every stage.** It also *proposes* the next stage: inferred grain,
inferred keys, inferred relationships (from key overlap statistics, naming similarity, value-set
containment, and observed lineage) are presented as **"we think this is true — confirm or
correct"**, never as an empty form. Confirmation is one click; correction teaches the system.

**Metadata coverage is itself scored and reported.** A domain with 4% of CDEs defined and no
declared relationships gets a low *estate maturity* score, which is a legitimate management metric
and a natural driver of adoption.

---

## 4. Connectors as a business-configurable resource

The user's requirement is explicit: *define a dataset, add metadata and dependencies, then via a
configured connector Prama reaches out, reads the data (full or sampled), and starts constructing
DQ conclusions.* The flow:

```
 1. CONFIGURE CONNECTION        2. DECLARE DATASET           3. BIND
 ┌────────────────────┐        ┌────────────────────┐      ┌────────────────────┐
 │ Pick source type   │        │ Business name      │      │ Browse the source  │
 │ Credentials (vault)│        │ Owner, domain      │      │ Prama proposes     │
 │ Network/proxy      │  ───►  │ Grain, rhythm      │ ───► │ matching physical  │
 │ Test connection    │        │ Criticality        │      │ objects; user      │
 │ Read scope & limits│        │ Attributes (or     │      │ confirms binding   │
 │ Sampling policy    │        │  discover them)    │      │ + any transform    │
 └────────────────────┘        └────────────────────┘      └────────────────────┘
                                                                     │
 6. CONCLUDE                   5. PROFILE                   4. READ  ▼
 ┌────────────────────┐        ┌────────────────────┐      ┌────────────────────┐
 │ Candidate controls │        │ Statistics, patterns│     │ Full scan / sample │
 │ Anomalies, trends  │  ◄───  │ semantic types,     │◄─── │ per policy & budget│
 │ Issues & scores    │        │ keys, dependencies  │     │ Pushdown by default│
 │ All explained      │        │ Relationship hints  │     │ Evidence recorded  │
 └────────────────────┘        └────────────────────┘      └────────────────────┘
```

**Design requirements for the connector experience (business-user grade):**

- **Guided, typed forms per source family** — not a JDBC URL box. "Which Snowflake account?
  Which warehouse? Which role?" with validation and inline help.
- **Credential handling never exposes secrets to the business user.** They select a
  pre-provisioned credential from the vault, or request one via a workflow that routes to IT.
  Separation of duties is built in: a business owner can *configure* a connection they cannot
  *see the password for*.
- **Test-and-explain**: connection tests report in business language ("connected, but this role
  cannot read the RISK schema — request access?"), with a one-click access-request workflow.
- **Explicit read policy per connection**: allowed schemas/paths, maximum scan size, permitted
  hours, sampling default, whether failing-row samples may be retained, and masking rules.
- **Sampling as a first-class, explained choice**: full scan / deterministic sample at N% /
  N rows / stratified by a declared segment / most-recent-partitions-only — with the confidence
  implications stated ("at 1% sample we can detect a defect rate above 0.4% with 95% confidence").
- **Cost preview before every scan**, and a standing budget per connection.
- **Discovery browser**: after connecting, the user browses the source *as a business person*:
  tables ranked by size/recency/usage, with inferred subject matter, not an alphabetical tree of
  4,000 objects.
- **Binding suggestions**: when a dataset is declared before binding, Prama proposes candidate
  physical objects by name similarity, column-signature match, and content fingerprint.
- **Feed connectors** get feed-shaped configuration: landing location, filename pattern with date
  tokens, expected arrival window, header/trailer conventions, encoding, delimiter/layout or
  copybook, PGP key, archive policy, and duplicate-delivery handling.

---

## 5. From declarations to conclusions

The value proposition compresses to one sentence: **business declarations become executable
controls, and executed controls become business conclusions.** The mapping is explicit and
auditable — the user can always ask "why does this control exist?" and get "because you declared
X on 4 March."

| Declaration | Auto-derived controls (proposed, never silently activated) |
|---|---|
| Grain = "one row per account per day" | Uniqueness on (account, date); duplicate detection; completeness vs. account master |
| Arrival by 06:30 on business days | Freshness/timeliness control with the right calendar; late-arrival alert; arrival-pattern monitor |
| Volume tracks trading days, 3× at month-end | Seasonality-aware volume monitor with the correct baseline model |
| Attribute is a CDE tied to FR Y-14Q | Elevated severity, mandatory attestation, blocking gate before submission, retention of evidence |
| Attribute is `Instrument.ISIN` | Format + check digit + GLEIF/master existence + cross-dataset consistency |
| Attribute is a monetary amount in `CCY` | Sign convention, precision, currency-code validity, FX-normalised aggregate checks |
| Value domain = code list `ISO 4217` | Membership control that updates when the code list updates |
| `RECONCILES_WITH` GL on (account, cost centre), €1 | Full reconciliation, break classification, ageing, certificate |
| `DERIVES_FROM` positions by aggregation | Aggregate parity; trust propagation edge; downstream impact on incident |
| `TEMPORAL_SUCCESSOR` of yesterday | Roll-forward control: opening + movements = closing |
| `SAME_ENTITY_AS` CRM party file | Entity resolution; duplicate parties; identifier consistency |
| Journey: origination → … → FINREP | End-to-end SLA, journey scorecard, backward RCA, forward impact |
| Authoritativeness = "replica of X" | Parity + staleness controls; demotion of its independent trust score |

**Pattern detection, trends, and reporting** then operate over this business-labelled structure,
which is what makes the output legible: not *"column 27 null rate rose"* but *"Counterparty LEI
completeness in the Credit Risk domain has declined for three consecutive weeks, concentrated in
the EMEA feed, affecting 4 CDEs used by the FRTB return."*

---

## 6. Continuous re-examination — findings that never go stale

A declaration made once and a profile computed once are both liabilities. Estates change: schemas
drift, feeds are re-cut, volumes shift regime, a column that held IBANs starts holding free text,
a relationship that held 99.8% key overlap degrades to 94%. **Prama re-examines its datasets on a
configured cadence and refreshes every conclusion it has drawn.**

### 6.1 What gets refreshed, and independently

Each activity has its own cadence, because each has a different cost and a different rate of change:

| Activity | Typical cadence | Trigger conditions |
|---|---|---|
| Metric collection for active controls | Per run (minutes–daily) | Schedule, pipeline event, file arrival |
| Re-profiling (statistics, patterns) | Daily–weekly | New partitions, volume change, schema change |
| Semantic-type re-inference | Weekly–monthly | Profile shift, new columns, pack update |
| Key / dependency re-discovery | Monthly | Structure change, grain violation detected |
| Relationship re-proposal | Monthly | New datasets in the domain, overlap change |
| Rule re-induction & retirement review | Monthly–quarterly | Coverage gaps, never-firing rules, pack update |
| Monitor baseline re-fit | Weekly (rolling window) | Regime change, accepted "new normal" |
| Conformal re-calibration | Weekly, plus on drift | Calibration-validity check fails |
| Score & trust recomputation | Per run + nightly roll-up | Any component change |
| Metadata recertification | Quarterly–annual | Ownership change, regulatory cycle |

### 6.2 Adaptive cadence

Fixed schedules are wasteful at one end and negligent at the other. Prama's default is adaptive:
cadence rises with **criticality × volatility × consumption** and falls for stable, low-tier,
rarely-consumed assets — bounded by the declared cost budget and the source's permitted execution
windows. The chosen cadence and its reasoning are always visible and always overridable.

### 6.3 Every finding carries its freshness

There is no such thing as an undated conclusion in Prama. Each finding records `computed_at`, the
exact data snapshot examined, the sampling strategy used, and a staleness state
(**fresh / ageing / stale / suspended**). The UI renders staleness wherever a finding appears; a
stale profile is visibly stale, not silently wrong.

### 6.4 Metadata drift is an incident

Because the business declares the model, the platform can check the *model* against reality — a
capability no physical-first tool has:

- A binding points at a column that no longer exists → binding-drift incident to the metadata owner.
- Declared grain is violated (duplicates appear at the declared key) → grain-drift incident.
- An attribute declared as `ISO 4217` now contains values outside the code list → domain-drift.
- A `RECONCILES_WITH` relationship's key overlap falls from 99.8% to 94% → relationship-drift.
- A dataset declared to arrive daily has not arrived for three cycles → rhythm-drift.
- A column previously classified IBAN is now free text → reclassification finding.

These route to the **business owner of the declaration**, not to an engineer, because the
declaration is theirs.

### 6.5 From point-in-time to pattern

Successive examinations are the raw material for the trend and pattern reporting that business
owners actually want. Prama compares examinations over long horizons to report gradual degradation,
seasonality, structural change, and coverage movement — and issues a periodic
**"what changed in your estate"** digest per domain: datasets discovered, structures changed, types
reclassified, relationships proposed, controls suggested or retired, trends emerging.

Requirements: [`FR-REF`](04-requirements-functional.md#v-continuous-re-examination--refresh-fr-ref).

---

## 7. Personas — who this is for

| Persona | What they do in Prama | What they must never be asked to do |
|---|---|---|
| **Business Data Owner** (e.g. Head of Credit Risk Data) | Declares datasets and their meaning, owns criticality and CDEs, attests to controls, reads scorecards, approves rules | Write SQL, know a table name, understand a partition |
| **Data Architect** | Models concepts, declares relationships and journeys, designs the estate map, sets standards, reviews coverage | Operate a database, tune a query |
| **Data Steward** | Triages incidents, classifies breaks, confirms/corrects proposals, manages exceptions | Deploy code |
| **Business Analyst / Controller** | Asks questions, runs reports, investigates specific figures, uses the chat interface | Learn a rule syntax |
| **Data Engineer** (supporting cast) | Configures connectors, handles bindings for awkward sources, integrates CI/CD and orchestration | — |
| **Auditor / Regulator** | Reads evidence, replays controls, reviews attestations | Anything requiring a login to a source system |

**Design consequences:**

1. Physical detail is **progressively disclosed**, never the default view. The estate map shows
   business names; the physical binding is one click away, behind an "advanced" affordance.
2. **Every technical artefact has a business rendering.** A rule always has a plain-English
   statement; a break always has a business explanation; a score always decomposes into named
   business dimensions.
3. **No dead ends.** Any screen a business user can reach has an action they can take — approve,
   comment, assign, ask, request access — never "contact your administrator".
4. The **chat interface** ([10](10-ux-and-chat-interface.md)) is the accessibility ramp: a business
   owner who cannot navigate to the right screen can simply ask, and every answer links back into
   the console.

---

## 8. Why this is defensible

The semantic layer is the moat, more than any single algorithm:

1. **It accumulates.** Every declaration, confirmation, and correction makes the estate model
   richer and the AI more accurate. Switching cost grows monotonically and is owned by the
   business, not by IT.
2. **It is the missing input to AI.** LLM rule induction is mediocre from schema alone and
   excellent from schema + business definition + concept mapping + declared relationships. Our
   AI is better because our *context* is better, not because our model is bigger.
3. **Nobody else has it in the right place.** Catalogs hold glossaries but do not execute controls.
   DQ tools execute controls but hold no business model. MDM holds concepts but only for master
   data. Prama unifies the declaration and the execution in one object model, with one evidence
   trail.
4. **It generalises the product across industries at zero engineering cost.** A new industry is a
   new set of Concepts, semantic types, and relationship templates in a Domain Pack
   ([12](12-banking-domain-pack.md) is the reference implementation) — not a new codebase.

---

<div align="center">
<img src="assets/prama-mark.svg" width="30" alt=""/><br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.<br/>
See <a href="../LICENSE">LICENSE</a> and <a href="../NOTICE">NOTICE</a>. Third-party names and marks are the property of their respective owners.</sub>
</div>
