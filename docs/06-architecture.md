<img src="assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

> ***pramā*** (Sanskrit **प्रमा**) — *valid knowledge: a cognition that is both true and arrived at
> by a reliable means*. Its companion ***pramāṇa*** (प्रमाण) is *the instrument by which valid
> knowledge is obtained*. Prama is that instrument for an organisation's data — it does not decide
> what is true, it is how a belief about data becomes **justified**.
>
> **Declare it. Prove it. Trust it.**


---
# 06 — Reference Architecture

---

## 1. Architectural principles

| # | Principle | Consequence |
|---|---|---|
| A1 | **Control plane, not data plane** | Prama orchestrates and records; computation happens where the data already is. Raw data is never bulk-copied. |
| A2 | **Declarations are the source of truth** | The business semantic layer is the primary store; controls, schedules, and scores are *derived* from it and can always be regenerated. |
| A3 | **Compile, don't interpret** | Every check is compiled through one IR to a target engine. One semantics, many backends. |
| A4 | **Evidence is the ledger** | Every execution appends an immutable record. The evidence store is the system of record for audit and the substrate for every score. |
| A5 | **Neural authorship, symbolic execution** | LLMs and ML propose, rank, explain, and calibrate. They never adjudicate. (`CON-007`) |
| A6 | **Everything through the public API** | The console, CLI, chat agent, and MCP server are all clients. No privileged internal surface. |
| A7 | **Degrade, don't fail** | Loss of ML, LLM, catalog, or control-plane connectivity reduces capability; it never stops controls from running or evidence from being kept. |
| A8 | **Multi-modal deployment from one codebase** | SaaS, single-tenant, VPC, on-prem, and air-gapped differ by configuration and by which planes are co-located — not by build. |

---

## 2. Plane view

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  EXPERIENCE PLANE                                                            ║
║  Web console · Estate map · Rule studio · Incident workspace · Recon         ║
║  workbench · Scorecards · Chat assistant · CLI · SDKs · MCP server · Embeds  ║
╚═══════════════════════════════════╤══════════════════════════════════════════╝
                                    │  REST (OpenAPI 3.1) / gRPC / events
╔═══════════════════════════════════╧══════════════════════════════════════════╗
║  CONTROL PLANE                                                               ║
║  ┌────────────────┐ ┌────────────────┐ ┌────────────────┐ ┌───────────────┐ ║
║  │ Semantic Layer │ │ Rule Registry  │ │  Scheduler &   │ │  Policy &     │ ║
║  │  Service       │ │  & Compiler    │ │  Orchestrator  │ │  IAM          │ ║
║  │ datasets,      │ │ PQL→IR→plan,   │ │ cadence,       │ │ RBAC/ABAC,    │ ║
║  │ attributes,    │ │ versioning,    │ │ adaptive       │ │ SoD, masking, │ ║
║  │ concepts,      │ │ approval,      │ │ re-examination,│ │ residency,    │ ║
║  │ relationships, │ │ static analysis│ │ budgets,       │ │ approvals     │ ║
║  │ journeys       │ │                │ │ back-pressure  │ │               │ ║
║  └────────────────┘ └────────────────┘ └────────────────┘ └───────────────┘ ║
║  ┌────────────────┐ ┌────────────────┐ ┌────────────────┐ ┌───────────────┐ ║
║  │ Evidence Ledger│ │ Metric History │ │ Incident &     │ │ Scoring &     │ ║
║  │ append-only,   │ │ time series of │ │ Workflow       │ │ Trust Engine  │ ║
║  │ hash-linked,   │ │ every metric,  │ │ correlation,   │ │ dimensions,   │ ║
║  │ WORM export    │ │ per segment    │ │ RCA, routing   │ │ propagation   │ ║
║  └────────────────┘ └────────────────┘ └────────────────┘ └───────────────┘ ║
║  ┌────────────────┐ ┌────────────────┐ ┌────────────────┐ ┌───────────────┐ ║
║  │ Lineage Graph  │ │ Learning       │ │ Notification & │ │ Pack Registry │ ║
║  │ + business     │ │ Service        │ │ Reporting      │ │ signed domain │ ║
║  │   journeys     │ │ feedback→models│ │ channels, docs │ │ bundles       │ ║
║  └────────────────┘ └────────────────┘ └────────────────┘ └───────────────┘ ║
╚═══════════════════════════════════╤══════════════════════════════════════════╝
        ┌───────────────────────────┼───────────────────────────┐
╔═══════╧═════════════╗   ╔═════════╧══════════╗   ╔════════════╧════════════╗
║ INTELLIGENCE PLANE  ║   ║  EXECUTION PLANE   ║   ║   INTEGRATION PLANE     ║
║ Profiler & discovery║   ║ Compiler backends: ║   ║ Catalogs · Orchestrators║
║ Semantic classifier ║   ║  SQL(25 dialects), ║   ║ Ticketing · Chat        ║
║ Constraint miner    ║   ║  Spark, Flink,     ║   ║ SIEM · GRC · BI         ║
║ Anomaly monitors    ║   ║  Arrow/DuckDB,     ║   ║ Schema registries       ║
║ Conformal calibrator║   ║  native row scanner║   ║ Reference-data providers║
║ Rule inducer (LLM)  ║   ║ Workers/agents     ║   ║ Identity providers      ║
║ ER / matching       ║   ║ Quarantine & gates ║   ║ OpenLineage/OTel        ║
║ RCA reasoner        ║   ║ Sampling planner   ║   ║                         ║
╚═════════════════════╝   ╚═════════╤══════════╝   ╚═════════════════════════╝
                                    │ pushdown (data never moves)
                          ╔═════════╧══════════════════════════════════════╗
                          ║  CUSTOMER DATA ESTATE                          ║
                          ║  Warehouses · Lakehouses · RDBMS · Mainframe   ║
                          ║  Files/feeds · Streams · APIs · NoSQL · Docs   ║
                          ╚════════════════════════════════════════════════╝
```

---

## 3. Services

### 3.1 Semantic Layer Service
Owns Datasets, Attributes, Concepts, Properties, Relationships, Journeys, Domains, Bindings, and
Connections. Bitemporal (valid-time + transaction-time) so any past state is reconstructable.
Emits change events that trigger control regeneration and re-examination. Exposes a graph query
interface for the estate map. **This is the most valuable store in the system**; it is the
customer's accumulated knowledge, and it is exportable in full (`NFR-POR-004`).

### 3.2 Rule Registry & Compiler
Stores PQL source, its parsed AST, the compiled IR, and the per-backend plans, all content-addressed
by hash. Provides static analysis (types, column existence, dialect capability, cost estimate,
lint), rule lifecycle and approval, subsumption/redundancy analysis, and derivation provenance
("this control exists because relationship R-4471 was declared"). Regenerates derived controls when
declarations change, always as proposals.

### 3.3 Scheduler & Orchestrator
Turns cadence policy into a work plan. Responsibilities: schedule resolution (cron/calendar/event/
adaptive), dependency ordering and short-circuiting, **assertion fusion** (grouping many assertions
over one scope into one scan), budget enforcement and prioritised shedding, back-pressure from
sources, retry/idempotency, and lease management for distributed workers. Adaptive re-examination
(`FR-REF-004`) lives here.

### 3.4 Execution Plane
Stateless workers that fetch a compiled plan, execute it against a source, and stream results back.
Backends:

| Backend | Used for | Notes |
|---|---|---|
| **SQL pushdown** | Warehouses, RDBMS, lakehouse SQL engines | Per-dialect adapter; capability matrix drives compilation choices |
| **Spark** | Very large lake data, complex multi-pass, reconciliation at 10^8+ | Runs on the customer's cluster |
| **Flink** | Streaming assertions, in-flight enforcement, windowed monitors | Sub-5 ms added p99 |
| **Arrow/DuckDB** | Files, feeds, small/medium data, local execution, agent-side | Zero external dependency; the air-gap workhorse |
| **Native row scanner** | Fixed-width, COBOL/EBCDIC, SWIFT/FIX/FpML, EDI, XML/JSON streams | Format plugins produce Arrow batches consumed by the same IR evaluator |

Deployment modes: **connect-out** (control plane initiates), **agent** (customer-hosted worker,
outbound-only connection), and **embedded** (a library invoked inside the customer's Spark/Flink job
or dbt run).

#### 3.4.1 The broker seam, and commit ordering

`prama.execute.stream` evaluates a control against one message.
`prama.execute.inflight` decides what happens to it. `prama.execute.transport`
decides **when it is safe to say the message has been dealt with** — which on a
stream means when to commit the offset, and that is the whole substance of the
module.

**Commit after enforcement, never before.** A consumer that commits and then
enforces has told the broker it is finished with a message it has not finished
with. Crash in between and the message is never redelivered and never
dead-lettered: it is gone, with nothing anywhere recording that it existed. That
is the failure `inflight` exists to prevent, moved one layer out. Four tests fail
if the two lines are swapped.

**At-least-once, and said out loud.** Committing after enforcement means a crash
between the two replays the batch, so a message can be dead-lettered twice. The
trade is deliberate: duplicate evidence is a reconciliation problem, lost data is
not one anybody can solve afterwards. Nothing claims exactly-once, because
without a transaction spanning the broker *and* the dead letter nothing can
deliver it.

**A halted batch commits what completed, not what was polled.** When the dead
letter fills, the pipeline stops part-way. Committing the batch's last offset
skips every message after the halt; committing nothing replays what was already
dead-lettered. Committing through the last *enforced* message is the only choice
that loses nothing — which is why positions are tracked per message rather than
per batch.

**Offsets are per partition.** A batch spans partitions, and a single "last
offset" across them is meaningless; committing one partition's offset against
another's is how a consumer group silently skips a partition's worth of data.

**No broker client ships.** The transport is an ABC with an in-memory reference
implementation, and a test asserts that no Kafka or Flink package is imported.
The transport that talks to a real broker belongs to the deployment, where the
organisation's security, retry and partition-assignment policy already lives —
and keeping it out is what lets the commit ordering, the property that matters,
be tested at all. **The loop has not been run against a real broker.**

The seam is consume-only: a transport that could also produce would invite the
enforcement loop to republish, and a loop that consumes and produces on the same
broker is one topology change away from feeding itself.

---

### 3.5 Evidence Ledger
Append-only, hash-linked (Merkle) store of `EvidenceRecord`s. Partitioned by tenant/date, columnar,
compressed, with WORM export (S3 Object Lock / Azure immutable blobs) and optional external
anchoring. Signed by the executing worker's key. Deterministic replay reconstructs the exact plan
and snapshot. Median record ≤ 2 KB (`NFR-COS-006`). Nothing in the system may mutate or delete a
record; erasure is via tombstone with preserved hash integrity (`NFR-PRV-005`).

### 3.6 Metric History Store
Time-series of every computed metric, keyed by (dataset, attribute, segment, metric, time), with
retention tiering. This is the substrate for anomaly monitors, trend and pattern reporting
(`FR-REF-013`), and score history. Deequ's metrics-repository pattern, generalised and made
multi-tenant.

### 3.7 Intelligence Plane
Profiler, semantic classifier, constraint miner (UCC/FD/IND/DC), anomaly monitor fleet, conformal
calibrator, rule inducer (LLM + template-constrained decoding), entity resolver, and RCA reasoner.
All are *proposal generators*; none can write an active control or a verdict. Detailed in
[08](08-ai-ml-capabilities.md).

### 3.8 Scoring & Trust Engine
Computes dimension scores, composite scores, materiality weighting, SLO/error budgets, and
**lineage-aware trust propagation**. Recomputed incrementally on evidence arrival and fully on a
nightly roll-up. Fully explainable: every score decomposes to the evidence records that produced it.

### 3.9 Incident & Workflow Service
Correlation and deduplication into incidents, lifecycle state machine, ownership routing and
escalation, RCA hypothesis assembly, impact analysis, break management for reconciliation,
exception register, and bidirectional integration with Jira/ServiceNow/Slack/Teams.

### 3.10 Lineage & Journey Graph
Merges *technical* lineage (OpenLineage, dbt manifests, SQL parsing, warehouse access history) with
*business* lineage (declared Journeys and Relationships). Business declarations take precedence
where they conflict, with the conflict surfaced. Backed by a property-graph store; supports
ancestry, descendancy, blast radius, and trust propagation traversals at interactive latency.

### 3.11 Learning Service
Collects every human signal (`FR-LRN-001`), maintains the feature/label store, retrains and
recalibrates on schedule and on trigger, evaluates challengers in shadow mode, and manages
promotion/rollback. Strictly tenant-isolated by default.

### 3.12 Policy & IAM
Central decision point for RBAC/ABAC, segregation of duties, masking, residency, retention, budget,
and approval requirements. **Every plane calls the policy service; none re-implements policy.**
The chat agent and MCP server pass through it with the invoking user's identity.

---

## 4. The compilation pipeline

```
 Business declaration ──┐
 (grain, rhythm,        │
  relationship, CDE)    │  derivation
                        ▼
                 ┌─────────────┐   parse    ┌───────┐  normalise  ┌──────────┐
 PQL source ────►│   Parser    ├───────────►│  AST  ├────────────►│    IR    │
 (text or UI     └─────────────┘            └───────┘             │ (typed,  │
  or chat)                                       ▲                │  engine- │
                                                 │ template       │  neutral)│
                 LLM induction ──────────────────┘ constrained    └────┬─────┘
                 (proposal only)                    decoding            │
                                                                        │ plan
        ┌───────────────┬───────────────┬───────────────┬───────────────┤
        ▼               ▼               ▼               ▼               ▼
   SQL (dialect)      Spark           Flink        Arrow/DuckDB    Row scanner
        │               │               │               │               │
        └───────────────┴───────┬───────┴───────────────┴───────────────┘
                                ▼
                    Execute at source (pushdown)
                                │
                ┌───────────────┼────────────────┐
                ▼               ▼                ▼
          Metrics ──►     Verdict ──►      EvidenceRecord
        (history store)  (incidents)       (ledger, signed)
                                │
                                ▼
                          Scores & trust ──► Reports, alerts, attestation
                                │
                                ▼
                        Human disposition ──► Learning service ──► recalibration
```

**Assertion fusion.** The orchestrator groups all assertions sharing a scope and a snapshot into a
single compiled plan. 400 column-level checks on one table become one query computing 400
aggregates, not 400 queries (`NFR-PRF-005`, `NFR-COS-001`). This is the single largest source of
cost advantage over per-rule tools.

**Sampling planner.** For each assertion the planner chooses full scan, incremental (new partitions
only), or statistical sample, based on the declared read policy, the budget, the criticality tier,
and the required confidence — and records the choice on the evidence so no sampled result is ever
mistaken for exact (`FR-EXE-007`).

---

## 5. Storage choices

| Store | Technology (reference) | Rationale |
|---|---|---|
| Semantic layer, rules, config | PostgreSQL (bitemporal schema) | Relational integrity, transactional approval workflows, mature ops |
| Lineage & journey graph | PostgreSQL + Apache AGE, or Neo4j/Neptune at scale | Property graph traversals |
| Evidence ledger | Object storage (Parquet/Iceberg) + Merkle index in Postgres | Cheap, immutable, WORM-capable, queryable, exportable |
| Metric history | Time-series-optimised columnar (Iceberg/Parquet + DuckDB, or ClickHouse/Timescale) | High-cardinality series, fast range scans |
| Search | OpenSearch | Business-language search over the semantic layer |
| Cache / queues | Redis + Kafka (or NATS in small deployments) | Events, work distribution, back-pressure |
| Model artefacts | Object storage + MLflow-compatible registry | Versioning, provenance |
| Secrets | External vault only | `NFR-SEC-004` |

Every choice has a documented substitute for air-gapped and restricted environments; nothing depends
on a proprietary managed cloud service (`NFR-POR-002`).

---

## 6. Deployment topologies

| Topology | Control plane | Execution | Evidence | Typical buyer |
|---|---|---|---|---|
| **SaaS multi-tenant** | Prama-operated | Connect-out or customer agent | Prama-operated, per-tenant encrypted | Mid-market, fast start |
| **Single-tenant cloud** | Prama-operated, dedicated | Customer agent | Dedicated | Regulated but cloud-comfortable |
| **Customer VPC** | Customer's cloud account, Prama-managed | In-VPC workers | Customer's storage, CMK | Tier-2/3 banks |
| **On-premises** | Customer Kubernetes | On-prem workers | Customer storage | Tier-1 banks, insurers |
| **Air-gapped** | Customer Kubernetes, no egress | On-prem workers | Customer storage | Central banks, defence, sensitive regulators |

Air-gapped mode: signed offline bundles for platform, packs, and models; self-hosted open-weight
LLM via vLLM/Ollama; reference-data updates by manual import; no telemetry. Every feature except
hosted-LLM quality and external reference data is preserved (`NFR-PRV-007`).

---

## 7. Cross-cutting concerns

- **Multi-tenancy.** Tenant is a first-class dimension in every store, every cache key, every model,
  and every embedding index. Isolation verified by automated tests each release (`NFR-SEC-006`).
- **Idempotency.** Every write API takes an idempotency key; every execution is idempotent with
  respect to evidence and incidents (`NFR-DAT-004`).
- **Time.** All timestamps UTC with recorded source-clock offset; every business date carries an
  explicit calendar reference (`NFR-DAT-005`). Bitemporality throughout — *what we believed* and
  *when it was true* are always separable.
- **Versioning.** Semantic-layer objects, rules, IR, models, packs, and APIs are independently
  versioned with explicit compatibility ranges.
- **Failure isolation.** One slow source, one pathological rule, or one failing model degrades only
  its own scope (`NFR-AVL-006`).
- **Observability.** Prama instruments itself with OpenTelemetry and holds itself to published SLOs
  (`NFR-OPS-001`).

---

## 8. Key architectural decisions

| ID | Decision | Alternatives rejected | Rationale |
|---|---|---|---|
| AD-01 | Engine-neutral IR with pluggable backends | Per-engine rule dialects; single-engine (Spark-only) | Portability is a bank requirement (10-year platform migrations) and a market gap (GAP-3) |
| AD-02 | Pushdown-first, control plane only | Central ingestion into a Prama data lake | Residency, cost, DORA, air-gap; also removes the largest scaling bottleneck |
| AD-03 | Evidence ledger as system of record | Mutable results tables with retention | Auditability is the wedge (GAP-5); mutable state cannot be attested |
| AD-04 | Business semantic layer as primary store | Physical-first catalog crawl | The product thesis (03); enables derivation of controls from declarations |
| AD-05 | LLM constrained to authorship | LLM-as-judge on rows | Reproducibility, cost, regulation (`CON-007`, `NFR-AI-002`) |
| AD-06 | Conformal calibration for all statistical monitors | Static thresholds; vendor-tuned "sensitivity" | Alert fatigue is the documented adoption killer (GAP-2) |
| AD-07 | Postgres + object storage core; graph/TS stores optional | Bespoke distributed store | Operability in customer-run environments outranks peak performance |
| AD-08 | One codebase across SaaS→air-gapped | Separate on-prem edition | Feature parity is a sales requirement; forked editions rot |
| AD-09 | Domain packs as the vertical mechanism | Per-industry forks or professional services | "Banking-first, industry-general" must be architecture, not intention |
| AD-10 | Chat agent as an API client with user identity | Privileged agent backend | Security, auditability, and the guarantee that chat can never exceed UI permissions |

---

<div align="center">
<img src="assets/prama-mark.svg" width="30" alt=""/><br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.<br/>
See <a href="../LICENSE">LICENSE</a> and <a href="../NOTICE">NOTICE</a>. Third-party names and marks are the property of their respective owners.</sub>
</div>
