<img src="assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

> ***pramā*** (Sanskrit **प्रमा**) — *valid knowledge: a cognition that is both true and arrived at
> by a reliable means*. Its companion ***pramāṇa*** (प्रमाण) is *the instrument by which valid
> knowledge is obtained*. Prama is that instrument for an organisation's data — it does not decide
> what is true, it is how a belief about data becomes **justified**.
>
> **Declare it. Prove it. Trust it.**


---
# 19 — Detailed Implementation Roadmap: Ten Waves

**Companion to** [16 — Roadmap & Delivery Plan](16-roadmap-and-delivery-plan.md) (business phases)
and [18 — Technology Stack](18-technology-stack.md) (choices). This document is the *engineering*
plan: what gets built, in what order, and what "done" means for each wave.

---

## 0. Engineering constraints that hold in every wave

These are not preferences. They are enforced by hooks, by architecture tests, and by CI.

| # | Constraint | Enforcement |
|---|---|---|
| C1 | **No database migrations.** Two authoritative schema files: `schema/sqlite.sql`, `schema/postgres.sql`. Applied idempotently; live schema **verified** against them and drift fails loudly. | `prama db verify`, `tests/db/test_schema_parity.py` |
| C2 | **Database chosen in config.** `database.dialect: sqlite \| postgres`, switchable with no code change. | `tests/db/test_dual_dialect.py` |
| C3 | **All DB code in one package.** Only `src/prama/db/**` may import `sqlalchemy`; everything else uses repositories and the unit of work. | `tests/architecture/test_layering.py` |
| C4 | **≤ 1500 lines of code per source file** (comments/docstrings/blanks excluded; UI exempt). | `scripts/check_file_length.py` in pre-commit + CI |
| C5 | **Object-oriented throughout.** Every extension point is an ABC with a registry entry point and its own conformance suite. Concrete types are never named outside their own package. | Architecture tests; plugin conformance suites |
| C6 | **Structured concurrency.** No bare threads, no unbounded queues, no fire-and-forget tasks. Everything through `prama.core.concurrency`. | `tests/architecture/test_concurrency_hygiene.py` |
| C7 | **Scale-out by construction.** Every stateful service is either leased (single-writer, failover-safe) or partitioned by a declared key. No process may assume it is the only one. | Design review + soak tests |
| C8 | **AI never adjudicates.** No path from a model output to a verdict. | `tests/architecture/test_no_model_verdicts.py` |
| C9 | **Secrets never in tracked config.** Shipped session secret is empty; a fresh clone refuses to boot. | pre-commit hook |
| C10 | **No assistant attribution in history.** | `.githooks/commit-msg` |

**Wave exit criteria are uniform:** all tests green, architecture tests green, file-length clean,
`ruff` + `mypy` clean, documentation updated, demo script runs end-to-end, and the wave is merged to
`main` and pushed. Within a wave, commit and push to `develop` freely; `main` moves once, at the end.

---

## Wave map

Each wave below is specified with an objective, a deliverables table naming the modules and the
requirements they satisfy, a numbered task breakdown (`W<n>.<m>`, so work is trackable), testable
acceptance criteria, the demo that closes the wave, and the risks specific to it.

| Wave | Theme | Delivers | Depends on |
|---|---|---|---|
| **1** | **Platform spine** | Config, DB package + dual schema, plugin registry, concurrency, errors, logging, CLI, test harness, hooks/CI | — |
| **2** | **Semantic layer** | Datasets, attributes, concepts, relationships, journeys, bindings, connections; bitemporal store; REST API; GitOps | 1 |
| **3** | **Connectivity & profiling** | Connector SPI + registry + derived config schema; first 8 connectors; discovery, snapshot, sampling; profiler; metric history | 1, 2 |
| **4** | **PQL & IR** | Grammar, parser, type checker, linter, formatter; IR; SQL + Arrow backends; conformance suite; LSP | 1, 2, 3 |
| **5** | **Execution & evidence** | Scheduler, adaptive cadence, budgets, fusion, workers/leases; evidence ledger with deterministic replay; streaming seam | 1–4 |
| **6** | **Derivation & induction** | Γ declaration→control generator; constraint mining; semantic-type cascade; LLM authoring; proposal workflow | 2–5 |
| **7** | **Monitoring & calibration** | Monitor fleet, seasonality/calendars, detectors, conformal calibration, hierarchical FDR, guarantee status | 3, 5 |
| **8** | **Controls at scale** | Reconciliation + breaks, entity resolution, incidents + RCA, scoring + trust propagation, alerting, learning loop | 5–7 |
| **9** | **Experience** | React console, design system, estate map, rule studio, triage, scorecards; chat assistant; MCP server | 2–8 |
| **10** | **Enterprise & GA** | Streaming backend, multi-tenancy/security hardening, Helm/Operator/offline bundle, banking pack, benchmarks, S1–S9 gates | all |

---

## Wave 1 — Platform spine  ·  **COMPLETE**

**Objective.** Build the substrate every later wave stands on, with the hard constraints enforced
from the first commit rather than retrofitted.

**Enables.** Everything. Nothing else can start.

### Deliverables

| Module | Contents | Requirements |
|---|---|---|
| `prama.version` | Single authority for product, IR and schema versions | — |
| `prama.core.errors` | Error taxonomy whose constructor *requires* a remedy | `NFR-USA-004` |
| `prama.core.ids` | Monotonic ULIDs, typed identifier wrappers | — |
| `prama.core.clock` | Injectable `Clock`; `FixedClock`, `ManualClock` | `NFR-TST-005` |
| `prama.core.pjson` | One JSON API; canonical encoding for hashing | `NFR-CMP-001` |
| `prama.core.log` | Structured logs, correlation ids, handler-level redaction | `NFR-SEC-011` |
| `prama.core.config` | Layered sources, `${VAR:default}`, coercion, provenance, binding | `FR-ADM-006`, `NFR-SEC-004` |
| `prama.core.registry` | Plugin ABC, capability manifests, entry-point discovery | `NFR-MNT-002`, `FR-EXT-005` |
| `prama.core.concurrency` | Byte-bounded queues, task supervisor, limiters, leases | `NFR-AVL-007`, `NFR-PRF-013` |
| `prama.db` | The one database package: dialects, engines, sessions, unit of work, DAOs, schema bootstrap and verifier, lease provider, credential handling | `C1`–`C3`, `FR-ADM-001` |
| `schema/*.sql` | Two byte-identical authoritative schema files | `C1` |
| `prama.cli` | `version`, `config show`, `db init|verify|info` | `NFR-OPS-006` |
| `tests/architecture` | Layering, dialect branching, migration tooling, concurrency hygiene, model-verdict separation, file length, documentation | `C3`–`C8` |

### Tasks

| # | Task | Done |
|---|---|---|
| W1.1 | Project scaffolding, `pyproject`, ruff/mypy/pytest, src layout | ✅ |
| W1.2 | Error taxonomy, ids, clock, JSON, logging | ✅ |
| W1.3 | Configuration subsystem with provenance, redaction and dataclass binding | ✅ |
| W1.4 | Plugin registry with capability manifests | ✅ |
| W1.5 | Structured concurrency: queues, supervisor, limiters, leases | ✅ |
| W1.6 | Portable type set; both schema files; parity and portability tests | ✅ |
| W1.7 | Dialect abstraction, engine factory, session manager, unit of work | ✅ |
| W1.8 | DAO layer with structural tenant scoping and atomic upserts | ✅ |
| W1.9 | Schema loader, bootstrapper, verifier with blocking/informational drift | ✅ |
| W1.10 | Database-backed leases with monotonic fencing tokens | ✅ |
| W1.11 | Object-oriented CLI with no third-party dependency | ✅ |
| W1.12 | Architecture tests; githooks; file-length checker | ✅ |
| W1.13 | ORM conventions: per-database bases, relationships, co-located credentials | ✅ |

### Acceptance criteria

- [x] `prama db init` then `prama db verify` clean on SQLite, selected only by configuration.
- [x] Drift is **reported and never repaired**; blocking and informational drift distinguished.
- [x] The two schema files are byte-identical apart from their headers.
- [x] Only `prama.db` imports SQLAlchemy — enforced by import scanning.
- [x] No migration tooling; no `metadata.create_all` anywhere.
- [x] 158 tests green; mypy strict clean; ruff and ruff format clean; file-length ceiling clean.

**Demo.** Connect to an empty database, apply the schema, break it deliberately, watch `verify`
name the drift and refuse — then show the same code running against PostgreSQL by changing one
configuration line.

**Risks realised.** Three defects were found by the tests and fixed rather than accommodated: a
schema parser that silently dropped columns whose `CHECK` wrapped onto a second line; role and
setting writes that raced their own pending session state; and fencing tokens that reset on release.

---
## Wave 2 — Semantic layer  ·  **IN PROGRESS**

**Objective.** A business owner can declare a dataset, what it means, and how it relates to other
datasets — through an API — and every change is versioned, attributable and reconstructable.

**Depends on** Wave 1. **Enables** Waves 3 (binding), 4 (rules reference attributes), 6 (derivation).

### Deliverables

| Module | Contents | Requirements |
|---|---|---|
| `prama.semantic.values` | Grain, Rhythm, ValueDomain, Criticality, Sensitivity, Temporality, Authoritativeness, Optionality, LifecycleState | `FR-MET-004`…`007`, `022` |
| `prama.db.temporal` | Bitemporal versioning: valid time + transaction time, `TemporalQuery` | `NFR-DAT-002`, `NFR-CMP-002` |
| `prama.db.models.semantic` | Identity + version tables for domain, dataset, attribute, concept, relationship, journey, binding, connection | `FR-MET-001`…`068` |
| `prama.db.dao.semantic` | DAOs with `current` / `as_of` / `history` access | `FR-MET-107` |
| `prama.semantic.service` | Declaration services: validate, version, approve, supersede | `FR-MET-010`, `FR-MET-108` |
| `prama.semantic.conflict` | Semantic-conflict detection across concept mappings | `FR-MET-043` |
| `prama.semantic.maturity` | Estate maturity scoring and next-best-action ranking | `FR-MET-104`, `105` |
| `prama.semantic.gitops` | Round-trippable YAML serialiser and drift detection | `FR-EXT-009` |
| `prama.api` | FastAPI app, OpenAPI 3.1, problem details, idempotency keys | `FR-EXT-001` |

### Tasks

| # | Task | State |
|---|---|---|
| W2.1 | Value objects with validation and plain-language rendering | ✅ |
| W2.2 | Bitemporal schema: identity + version tables, partial unique index for "one current version" | ✅ |
| W2.3 | `Versioned` mixin and `TemporalQuery` (current / believed-now / as-of / history) | ✅ |
| W2.4 | ORM models for domain, dataset, attribute | ✅ |
| W2.5 | Semantic DAOs: create, amend, correct, retire, read at any point on both axes | ✅ |
| W2.6 | Concept and ConceptProperty; attribute→property mapping | ✅ |
| W2.7 | **Business Relationship**: 13 typed kinds, business-attribute join keys, tolerance, offset | ✅ |
| W2.8 | Journey: ordered chain of datasets and relationships, including black-box steps | ✅ |
| W2.9 | Binding and Connection identity, with unbound datasets first-class | ✅ |
| W2.10 | Declaration services with maker–checker approval for Tier-1 objects | ✅ |
| W2.11 | Semantic-conflict detection: one property, incompatible definitions or units | ✅ |
| W2.12 | Estate maturity score and next-best-action ranking | ✅ |
| W2.13 | GitOps serialiser, deserialiser and drift detection | ✅ |
| W2.14 | REST API over the semantic layer, with contract tests | ◑ datasets, attributes, relationships, estate and meta done; concepts, journeys, connections and bindings remain DAO-only |
| W2.15 | Audit on every mutation, joined to the platform audit trail | ◑ dataset and relationship services audit; the rest follow with their routes |

### Acceptance criteria

- [ ] Declare → amend → correct → read-at-any-instant round-trips on both time axes.
- [ ] A correction and an amendment are distinguishable a year later, and an evidence record from
      March resolves the declaration March believed in.
- [ ] A dataset can be declared, related and reported on **before it is bound to anything**.
- [ ] Exactly one current version per entity, enforced by the database, not by code.
- [ ] Semantic conflicts are surfaced rather than silently hosted.
- [ ] `prama export` → edit YAML → `prama apply` is lossless, and drift between Git and the store
      is detected in both directions.
- [ ] Estate maturity is computed and trends.
- [ ] API contract tests green; every mutation audited.

**Demo.** Declare "Positions EOD" in five minutes with no engineer present; declare that it
reconciles with the GL; show the version history; ask what the grain was on a date before it
changed; export to YAML, edit, re-apply.

**Wave risks.** Bitemporality is easy to get subtly wrong — the mitigation is that
`TemporalQuery` is the *only* place the predicates exist, and history correctness has dedicated
tests. Relationship modelling is the highest-value and least-precedented part of the product; expect
to revise the 13 kinds once against real design-partner estates.

---
## Wave 3 — Connectivity & profiling

**Objective.** Point Prama at a real source and get a profile, semantic types and an inventory in
under thirty minutes, unattended, without writing anything — the zero-declaration day one that
[21 §3](21-how-we-win.md) makes a release gate.

**Depends on** Waves 1–2. **Enables** Waves 4 (pushdown), 5 (execution), 6 (mining), 7 (monitors).

### Deliverables

| Module | Contents | Requirements |
|---|---|---|
| `prama.connect.spi` | Connector ABC: `discover`, `describe`, `snapshot`, `read`, `sample`, `pushdown_capabilities`, `execute_plan`, `health` | `FR-CON-017` |
| `prama.connect.schema` | **Config schema derived from connector source** with a presentation-only overlay | `FR-CON-026`, `FR-CON-029` |
| `prama.connect.registry` | Capability matrix, certification tiers | `FR-EXT-005` |
| `prama.connect.sources.*` | PostgreSQL, SQLite, Snowflake, filesystem/S3 (CSV, Parquet), SFTP feed, Kafka, generic JDBC/ODBC, generic REST | `FR-CON-001`…`020` |
| `prama.connect.feed` | Landing detection, filename patterns, arrival windows, header/trailer, manifests, duplicate and out-of-sequence detection, decryption | `FR-CON-014`, `034` |
| `prama.profile` | Column statistics, sketches (HLL, t-digest, count-min), pattern profiling, segmentation, incremental profiling | `FR-PRF-002`…`018` |
| `prama.profile.sampling` | Sampling planner with statistical bounds and stated confidence | `FR-EXE-007`, `FR-CON-030` |
| `prama.metrics.history` | Metric history store (Parquet/Iceberg + DuckDB) | `FR-PRF-011` |
| `prama.connect.policy` | Read policy, budgets, execution windows, load ceiling | `NFR-PRF-013`, `FR-CON-031` |

### Tasks

W3.1 Connector SPI and registry · W3.2 capability matrix · W3.3 **derived config schema + overlay
audit test** · W3.4 credential handling via vault reference, never displayed · W3.5 discovery
browser ranked by size/recency/usage · W3.6 snapshot capture per source kind · W3.7 sampling planner
· W3.8 profiler core and sketches · W3.9 segmented and incremental profiling · W3.10 metric history
store · W3.11 the eight GA connectors · W3.12 feed subsystem · W3.13 read policy, budgets and load
ceiling · W3.14 binding suggestions for declared-but-unbound datasets · W3.15 cost preview.

### Acceptance criteria

- [ ] **Connect → discover → profile → inventory in ≤ 30 min unattended** on a 1,000-table source,
      inside a declared budget, with the source-load ceiling respected and measured (`NFR-OPS-002`).
- [ ] A connector's configuration form is derived from its code; a test fails when the curated
      overlay and the code disagree.
- [ ] A business user configures a connection without ever seeing a credential.
- [ ] Sampling states its confidence; no sampled result is ever presented as exact.
- [ ] Feed arrival, lateness, duplicate delivery and truncation are detected.
- [ ] Every connector passes its conformance suite; the capability matrix is published.

**Demo.** Connect to a warehouse and a landing-zone feed, walk away, come back to a profiled
inventory with inferred semantic types and a cost report.

**Wave risks.** Connector breadth is a treadmill (`RSK-13`) — the SDK and certification tiers exist
so partners can carry the tail. Source owners may refuse access; the read policy and load ceiling
are designed to be shown to a DBA as reassurance.

---
## Wave 4 — PQL and the IR

**Objective.** A control is written once and executes with identical meaning on two engines, proven
by a conformance suite that blocks the build.

**Depends on** Waves 1–3. **Enables** Waves 5–8. Nothing executes before this.

### Deliverables

| Module | Contents | Requirements |
|---|---|---|
| `prama.pql.grammar` | EBNF, lexer, parser, AST; expression and YAML surfaces | `FR-RUL-001` |
| `prama.pql.types` | Type checker, attribute resolution, selector expansion | `FR-RUL-021` |
| `prama.pql.analysis` | Cost estimation, dialect capability check, subsumption, redundancy, never-fires | `FR-RUL-015`, `021` |
| `prama.pql.render` | Plain-language rendering of every control | `U2` |
| `prama.pql.format` | Canonical formatter so diffs are semantic | — |
| `prama.ir` | Typed logical plan, content addressing, versioning, serialisation | `FR-EXE-001`, `FR-EXT-010` |
| `prama.backend.sql` | Dialect adapters: PostgreSQL, SQLite, Snowflake first | `FR-EXE-002` |
| `prama.backend.arrow` | Local Arrow/DuckDB evaluator | `FR-EXE-002` |
| `prama.pql.conformance` | Golden corpus + property-based generation + reference interpreter | `NFR-TST-002`, `NFR-POR-003` |
| `prama.pql.lsp` | Language server for editor and IDE | — |

### Tasks

W4.1 grammar and parser · W4.2 AST and the two surfaces · W4.3 type checker and resolution ·
W4.4 selector expansion, materialised and versioned · W4.5 IR model and content addressing ·
W4.6 SQL backend and dialect adapters · W4.7 Arrow/DuckDB backend · W4.8 **conformance corpus and
reference interpreter** · W4.9 property-based equivalence testing · W4.10 cost estimation ·
W4.11 linter · W4.12 formatter · W4.13 plain-language renderer · W4.14 LSP · W4.15 importers for
SodaCL, Great Expectations, dbt tests and ODCS quality blocks.

### Acceptance criteria

- [ ] 100% of implemented constructs pass conformance on **every** supported backend.
- [ ] A construct a backend cannot express fails **at authoring time** with a clear message, never
      silently degrades.
- [ ] The worked example in [07 §10](07-rule-language-spec.md) compiles and runs end to end.
- [ ] Every control has a generated plain-language rendering.
- [ ] Cost is estimated before execution and is within 2× of actual on the benchmark corpus.
- [ ] ≥ 95% of 500 real design-partner controls express in the portable subset (`ASM-015`).

**Demo.** Write one control; run it unchanged on PostgreSQL, DuckDB and Snowflake; show the compiled
SQL for each and the identical verdict.

**Wave risks.** `RSK-11` — full semantic equivalence may be unattainable for regex flavours,
collation and decimal semantics. The response is a documented *portable subset* and compile-time
refusal, not a silent difference.

---
## Wave 5 — Execution, scheduling and evidence

**Objective.** Controls run on a schedule, at scale, and leave evidence that replays.

**Depends on** Waves 1–4. **Enables** Waves 6–8, and the entire audit proposition.

### Deliverables

| Module | Contents | Requirements |
|---|---|---|
| `prama.schedule` | Cron, interval, calendar, event and dependency triggers; **adaptive re-examination cadence**; priority classes | `FR-EXE-009`, `FR-REF-001`…`005` |
| `prama.schedule.fusion` | Assertion fusion: many assertions, one scan | `NFR-PRF-005`, `NFR-COS-001` |
| `prama.schedule.budget` | Budget enforcement with prioritised shedding and transparent deferral | `FR-EXE-008` |
| `prama.execute.worker` | Stateless executors, lease-based claim, agent and embedded modes | `FR-EXE-020` |
| `prama.execute.incremental` | Watermarks, late and restated data | `FR-EXE-006` |
| `prama.evidence` | Hash-linked append-only ledger, signing, Merkle roots, WORM export | `FR-EXE-014`, `NFR-CMP-001` |
| `prama.evidence.replay` | Deterministic replay and **divergence reporting** | `NFR-CMP-002` |
| `prama.execute.stream` | Streaming backend seam + DishtaYantra spike + throughput benchmark | `DEC-17`, `NFR-SCA-005` |
| `prama.telemetry` | OpenTelemetry traces, OpenLineage emission | `FR-EXE-021`, `FR-LIN-005` |

### Tasks

W5.1 scheduler and trigger kinds · W5.2 adaptive cadence policy · W5.3 assertion fusion · W5.4 budget
enforcement and shedding · W5.5 worker model and lease-based claim · W5.6 agent mode, outbound-only ·
W5.7 incremental execution and watermarks · W5.8 **evidence record, hash chain, signing** ·
W5.9 WORM export and retention tiers · W5.10 **deterministic replay and divergence report** ·
W5.11 gate, quarantine and tag actions · W5.12 streaming seam and the DEC-17 benchmark ·
W5.13 OpenTelemetry and OpenLineage · W5.14 soak and chaos tests.

### Acceptance criteria

- [ ] 10⁶ assertion executions/day sustained on one control plane with N workers.
- [ ] **100% of runs replay to an identical verdict**, or emit a divergence report naming the cause.
- [ ] Fusion demonstrates the `NFR-COS-001` claim: ≤ 50% of a naive per-rule full scan.
- [ ] Evidence median ≤ 2 KB; hash chain verifiable without Prama running.
- [ ] Execution continues for ≥ 24 h during a control-plane outage, buffering and replaying.
- [ ] `DEC-17` decided on measured throughput, not preference.

**Demo.** Run a suite; open an evidence record; verify its hash chain offline; replay a run from
last month and get the same verdict; restate the source data and watch the divergence report name it.

**Wave risks.** `RSK-12` (fusion may not deliver), `RSK-15` (evidence storage cost). Both are
measured early rather than assumed.

---

## Wave 6 — Declaration-derived controls, mining and induction

**Objective.** A business declaration produces reviewed, running controls with no SQL written by
anyone — the claim that makes Prama a business tool rather than an engineer's tool.

**Depends on** Waves 2–5. **Enables** Wave 7 (monitors need mined structure) and Wave 9 (the
proposal queue is a major UI surface).

### Deliverables

| Module | Contents | Requirements |
|---|---|---|
| `prama.derive.generator` | **Γ**: the declaration → control mapping for grain, rhythm, value domains, semantic types and all 13 relationship kinds | `FR-MET-063`, docs/03 §5 |
| `prama.mine.keys` | Unique column combinations, bounded arity | `FR-PRF-006` |
| `prama.mine.dependencies` | Exact, approximate and conditional functional dependencies; partial inclusion dependencies | `FR-PRF-007`, `008` |
| `prama.mine.constraints` | Approximate denial constraints, order dependencies | `FR-PRF-009`, `010` |
| `prama.classify.semantic` | Inference cascade: checksums → code lists → patterns → names → embeddings → LLM adjudication over a closed vocabulary | `FR-PRF-004`, `FR-REF-009` |
| `prama.discover.relationships` | Candidate relationships from key overlap, containment, naming, schema signature, query-log co-access | `FR-MET-065` |
| `prama.induce.llm` | Retrieval from the semantic layer, grammar-constrained decoding, parse/type-check/sandbox-execute, empirical validation | `FR-IND-003`…`006` |
| `prama.induce.documents` | Rules extracted from data dictionaries and regulatory instructions, **with citations** | `FR-IND-012` |
| `prama.induce.examples` | Weak supervision plus active learning from a handful of labelled cells | `FR-IND-011` |
| `prama.propose` | The single mutation channel: Proposal object, utility ranking, review workflow | `FR-IND-007`, `FR-CHT-004` |
| `prama.llm` | Provider abstraction: Anthropic, Azure OpenAI, Bedrock, Vertex, self-hosted | `FR-CHT-010` |

### Tasks

W6.1 Γ generator for grain, rhythm and value domains · W6.2 Γ for all 13 relationship kinds ·
W6.3 semantic-type cascade with deterministic validators first · W6.4 UCC and FD mining ·
W6.5 approximate and conditional variants · W6.6 IND and DC mining · W6.7 relationship discovery ·
W6.8 LLM provider abstraction with BYO and self-hosted · W6.9 **grammar-constrained decoding** ·
W6.10 candidate validation against real data, discarding trivial and unstable rules ·
W6.11 utility ranking learned from acceptance history · W6.12 Proposal object and review workflow ·
W6.13 induction from documents with citation retention · W6.14 example-driven induction ·
W6.15 coverage analyser ranking unprotected CDEs by risk.

### Acceptance criteria

- [ ] On a real source, **≥ 80% of columns and ≥ 95% of declared CDEs** under a reviewed control
      after one week of effort (`S5`).
- [ ] Every declaration in docs/03 §5 generates its stated controls, with provenance naming the
      declaration that produced it.
- [ ] 100% of LLM-generated PQL is parsed, type-checked and sandbox-executed before display; the
      generation-failure rate is measured and reported.
- [ ] Mining + LLM fusion beats either alone on acceptance rate (`RQ5`).
- [ ] Zero code paths where a model output reaches a verdict — architecture test green.
- [ ] Induction from ≤ 20 labelled cells produces a usable rule (the Raha result).

**Demo.** Declare a grain, a rhythm and one relationship; watch eight controls appear, each with the
sentence that justifies it, a backtest and an estimated alert volume; approve them in one click.

**Wave risks.** `RSK-16` — induction quality depends on semantic-layer richness, which is a
chicken-and-egg with adoption. Mitigated because mining works with zero declarations, and because
induction quality is measured *by declaration stage* and published (`RQ4`).

---

## Wave 7 — Monitoring and calibration

**Objective.** Alerts with a declared, honoured false-alarm budget — the differentiator no deployed
competitor has.

**Depends on** Waves 3 (metric history) and 5 (execution). **Enables** Wave 8 and the `S2`/`S3` gates.

### Deliverables

| Module | Contents | Requirements |
|---|---|---|
| `prama.monitor.fleet` | Volume, nulls, distincts, freshness, schema, distribution, derived business metrics; segmented monitors | `FR-MON-001`, `008` |
| `prama.monitor.season` | Intraday, daily, weekly, month/quarter-end; business and settlement calendars; **declared** volume drivers | `FR-MON-002` |
| `prama.monitor.detect` | Robust seasonal decomposition, quantile bands, isolation forest/LOF, matrix profile, forecast residual | `FR-MON-001` |
| `prama.calibrate.conformal` | Weighted/adaptive conformal p-values valid under drift | `FR-MON-005` |
| `prama.calibrate.select` | **Hierarchical FDR** over domain → dataset → attribute → check; budget/FDR/power sensitivity | `FR-MON-006`, `012` |
| `prama.calibrate.validity` | Continuous validity testing; visible degradation to "uncalibrated — best effort" | `FR-MON-007` |
| `prama.monitor.drift` | PSI, KS, Wasserstein, JS, χ²; changepoint detection; "accept new normal" | `FR-MON-003`, `004` |
| `prama.monitor.coldstart` | Priors from semantic type, pack, siblings and declared rhythm | `FR-MON-011` |
| `prama.monitor.tournament` | Champion/challenger in shadow, promotion gates, degradation rollback | `FR-MON-016`, `FR-LRN-006` |
| `prama.monitor.cards` | Model cards and reproducibility metadata | `FR-MON-017`, `NFR-CMP-005` |

### Tasks

W7.1 monitor fleet over metric history · W7.2 calendar and seasonality model · W7.3 detector suite ·
W7.4 **conformal calibration with adaptive weighting** · W7.5 **hierarchical BH/BY selection** ·
W7.6 sensitivity expressed as budget, FDR or power · W7.7 validity monitor and honest degradation ·
W7.8 changepoint detection and accept-new-normal with permanent annotation · W7.9 segmented
monitoring with correlated-alert roll-up · W7.10 cold-start priors · W7.11 champion/challenger and
promotion gates · W7.12 model cards · W7.13 calibration benchmark across five drift regimes.

### Acceptance criteria

- [ ] **Calibration error ≤ 0.02** across stationary, seasonal, level-shift, regime-switch and bursty
      regimes on FinDQ-Bench (`S3`).
- [ ] Alert volume tracks the declared budget within tolerance; the dial has a statistical meaning.
- [ ] When calibration assumptions fail, the monitor **says so** in the UI and in every alert.
- [ ] A new asset is usefully monitored on day one from priors, labelled as priors.
- [ ] Every monitor has a model card and a measured precision history.
- [ ] The calibration curve — nominal versus empirical — can be plotted. No competitor can produce
      this plot at all, and that is itself a result.

**Demo.** Set "no more than two false alarms a month in this domain"; show the resulting thresholds,
the calibration curve, and what happens to the guarantee when a regime shift is injected.

**Wave risks.** `RSK-10` and `ASM-011` — the central research claim. Proven on FinDQ-Bench *before*
it becomes a marketing promise; degrade visibly rather than silently.

---

## Wave 8 — Controls at scale

**Objective.** The control types that make banks buy, plus the loop that makes the system improve.

**Depends on** Waves 5–7. **Enables** Wave 10's beachhead use cases.

### Deliverables

| Module | Contents | Requirements |
|---|---|---|
| `prama.recon` | Match strategies, FX/unit/code-set/timezone normalisation, tolerances, break classification, N-way, roll-forward | `FR-REC-001`…`011` |
| `prama.recon.workflow` | Break assignment, ageing, commentary, escalation, certificate | `FR-REC-008`, `011` |
| `prama.er` | Blocking, Fellegi–Sunter with EM, comparison functions, active learning, clustering, evaluation | `FR-ERM-001`…`009` |
| `prama.incident` | Correlation and deduplication, lifecycle, ownership routing, escalation | `FR-INC-001`…`010` |
| `prama.incident.rca` | Hypothesis ranking over lineage, temporal correlation, change events and learned priors | `FR-INC-004` |
| `prama.lineage` | OpenLineage/dbt/warehouse ingestion, SQL parsing, graph store, blast radius | `FR-LIN-001`…`007` |
| `prama.lineage.scan` | **Legacy scanners**: T-SQL, PL/SQL, DB2 SQL PL, PowerCenter, DataStage, SSIS, one BI semantic layer | docs/20 G2 |
| `prama.score` | Dimension scores, three composite methods, materiality weighting, SLOs and error budgets | `FR-SCR-001`…`006` |
| `prama.score.trust` | **Lineage-aware trust propagation** over a configurable semiring | `FR-SCR-004` |
| `prama.alert` | Routing, channels, dedup, digests, alert composition, per-monitor precision | `FR-ALR-001`…`009` |
| `prama.learn` | Feedback capture, feature/label store, recalibration, re-ranking, shadow evaluation, promotion, rollback | `FR-LRN-001`…`010` |

### Tasks

W8.1 reconciliation engine and matchers · W8.2 normalisation with as-of rate sources ·
W8.3 break classification and workflow · W8.4 reconciliation certificate · W8.5 N-way and
roll-forward · W8.6 entity resolution with active learning · W8.7 lineage ingestion and graph store ·
W8.8 column-level SQL parsing · W8.9 **legacy scanners (the docs/20 G2 gap)** · W8.10 incident
correlation and lifecycle · W8.11 RCA hypothesis ranking · W8.12 impact analysis · W8.13 scoring and
materiality weighting · W8.14 **trust propagation** · W8.15 alerting and routing · W8.16 learning
loop with promotion gates and rollback.

### Acceptance criteria

- [ ] A sub-ledger↔GL reconciliation runs end to end with break workflow and a signed certificate.
- [ ] Reconciliation at 10⁸ records per side within budget.
- [ ] One upstream defect produces **one** incident, not four hundred.
- [ ] Trust propagation demonstrably changes remediation ranking versus severity ranking (`RQ8`).
- [ ] Alert precision ≥ 0.85 at declared FDR ≤ 0.10 in live shadow (`S2`).
- [ ] The learning loop shows measured uplift against a frozen-model control arm (`RQ9`).

**Demo.** Break the sub-ledger deliberately; watch one incident open with a ranked cause, an impact
list naming the affected return, a classified break population, and a trust score that drops on
every descendant of the defect.

**Wave risks.** `RSK-18` — trust propagation may be disputed as arbitrary; multiple sanctioned
semirings and an always-visible derivation path are the answer. Legacy scanners are unglamorous and
time-consuming; scope to the five that matter.

---

## Wave 9 — Experience

**Objective.** The product a business owner will actually use — and the surface on which the
semantic layer stops being a theory.

**Depends on** Waves 2–8. **Enables** the usability gates and, realistically, every sale.

### Deliverables

| Module | Contents | Requirements |
|---|---|---|
| `prama-web/design` | Design system on Radix + Tailwind, six-dimension palette, WCAG 2.2 AA from the first component, light/dark, density modes | `NFR-USA-003`, `008` |
| `prama-web/estate` | **Estate map**: WebGL graph, overlays, drag-to-declare relationships | `FR-MET-100`…`102`, `NFR-SCA-011` |
| `prama-web/declare` | Dataset in ≤ 5 min, relationship by drawing, attribute interpretation, propose-and-confirm everywhere | `NFR-OPS-003` |
| `prama-web/studio` | No-code builder, CodeMirror PQL editor with LSP, live preview, backtest, cost | `FR-UIX-002`…`004` |
| `prama-web/proposals` | Review queue with evidence, backtest, expected alert volume; batch approve | `FR-IND-007` |
| `prama-web/incidents` | Keyboard-first one-screen triage, batch disposition | `FR-UIX-006` |
| `prama-web/recon` | Side-by-side break workbench, grouping, certificate sign-off | `FR-REC-008` |
| `prama-web/scorecards` | Drill-down to evidence; attestation with e-signature and seal | `FR-SCR-007`, `008` |
| `prama.assistant` | Conversational agent: contextual panel, workspace, Slack/Teams | `FR-CHT-001`…`017` |
| `prama.mcp` | MCP server, read and propose tools only by default | `FR-EXT-008` |
| `prama.report.render` | Jinja-rendered PDF and print artefacts | `FR-SCR-009` |

### Tasks

W9.1 design system and tokens · W9.2 estate map with WebGL rendering · W9.3 drag-to-declare canvas ·
W9.4 declaration flows with inferred-then-confirmed defaults · W9.5 no-code rule builder ·
W9.6 PQL editor and LSP integration · W9.7 live preview and backtest · W9.8 proposal review queue ·
W9.9 incident triage workspace · W9.10 reconciliation workbench · W9.11 scorecards and drill-down ·
W9.12 attestation and e-signature · W9.13 **assistant with the full safety contract** · W9.14 MCP
server · W9.15 print/PDF rendering · W9.16 accessibility audit · W9.17 usability study.

### Acceptance criteria

- [ ] `NFR-USA-001`…`008` met in a study with **≥ 12 participants per persona**.
- [ ] ≥ 90% unaided task success on the eight core business tasks.
- [ ] ≤ 3 min median to a reviewed control via chat or induction (`S4`).
- [ ] Estate map: 50,000 nodes at 60 fps pan/zoom.
- [ ] WCAG 2.2 AA, zero critical findings, screen-reader tested.
- [ ] Every assistant mutation is a reviewable diff passing the standard approval workflow.
- [ ] Adversarial prompt-injection corpus fully passed.

**Demo.** A business owner who has never seen the product declares a dataset, draws a relationship,
approves the generated controls, and asks the assistant why last night's feed was late.

**Wave risks.** The largest single engineering line item (docs/18 §4). Scope discipline matters more
here than anywhere: every screen not on the list above is a screen not built.

---

## Wave 10 — Enterprise and GA

**Objective.** A Tier-2 bank can buy it, deploy it on-premises, and pass an audit with it.

**Depends on** everything. **Enables** revenue.

### Deliverables

| Module | Contents | Requirements |
|---|---|---|
| `prama.stream` | Streaming validation backend (DishtaYantra default per `DEC-17`; Flink pluggable): drop/tag/route/dead-letter, windowed monitors | `FR-EXE-013`, `NFR-SCA-005` |
| `prama.security` | Tenant isolation tests, RBAC/ABAC, SoD, SSO/SCIM, vault, CMK/BYOK, residency, SIEM export | `NFR-SEC-*` |
| `deploy/helm`, `deploy/operator` | Helm chart, Kubernetes Operator with CRDs, single-container all-in-one, **signed offline bundle** | `NFR-POR-001`, `FR-ADM-010` |
| `packs/banking` | Concepts, validators, calendars, message parsers (ISO 20022, SWIFT MT, FIX, FpML, XBRL, ISO 8583, NACHA/SEPA), COBOL/EBCDIC reader, reference reconciliations, regulatory control catalogue with citations | `FR-PCK-002`, docs/12 |
| `prama.contract` | ODCS import/export, CI/CD gates, data diff | `FR-CTR-001`…`008` |
| `bench/` | DQ-Bench and FinDQ-Bench published; live-shadow harness | docs/15 |
| `prama.integrate.catalog` | **Write-back** of quality state into Alation, Collibra, Atlan, Purview | docs/20 §9 |

### Tasks

W10.1 streaming backend and in-flight enforcement · W10.2 tenant isolation test suite ·
W10.3 SSO/SCIM, vault, CMK · W10.4 residency enforcement and SIEM export · W10.5 Helm chart ·
W10.6 Operator and CRDs · W10.7 all-in-one image · W10.8 **offline bundle and air-gapped update** ·
W10.9 COBOL/EBCDIC reader · W10.10 financial message parsers · W10.11 banking concepts, validators
and calendars · W10.12 regulatory control catalogue with citations · W10.13 reference reconciliation
templates · W10.14 ODCS runtime and CI gates · W10.15 data diff · W10.16 catalog write-back ·
W10.17 benchmarks published · W10.18 live-shadow harness · W10.19 SOC 2 readiness ·
W10.20 **auditor RDARR validation** ([21 §3 Unlock 1](21-how-we-win.md)).

### Acceptance criteria

- [ ] **All nine superiority gates** in [15 §7](15-evaluation-benchmark-methodology.md) met, or
      explicitly and publicly missed.
- [ ] Air-gapped install verified end to end with a local model and no egress whatsoever.
- [ ] Streaming: p95 ≤ 60 s detection, ≤ 5 ms added p99 at target throughput.
- [ ] Independent RDARR test script: 100% pass.
- [ ] ≥ 45 certified connectors including COBOL/EBCDIC and ≥ 6 financial message standards.
- [ ] Zero cross-tenant leakage findings; adversarial injection corpus passed.
- [ ] DQ-Bench and FinDQ-Bench public, with baseline configurations for every competitor.

**Demo.** The one that closes deals: a BCBS 239 attestation pack for one risk domain, generated —
every control, its executions, its exceptions, its sign-off — with one control replayed live in
front of the auditor.

**Wave risks.** `RSK-24` (air-gap support cost), `RSK-30` (misattributed regulatory failure), and the
sheer breadth of the wave. Mitigate by starting the pack, the packaging and the certifications in
Wave 8 rather than treating Wave 10 as a container for everything deferred.

---

## Cross-wave workstreams

Run continuously rather than inside a wave:

| Workstream | Cadence | Owner |
|---|---|---|
| Architecture tests: layering, dialect branching, migrations, concurrency, model verdicts, file length | Every commit | All |
| Benchmark suite in CI; > 10% regression blocks release | Every release | Research |
| Documentation kept in step with code; docs build and link-check in CI | Every commit | All |
| Security scanning, SBOM, dependency updates, parser fuzzing | Weekly | Security |
| Soak tests and chaos drills: source failure, control-plane outage, poison input | Per wave | SRE |
| DishtaYantra provenance audit — ported files re-checked against upstream | Per wave | Platform |
| Design-partner feedback loop feeding wave scope | Fortnightly | Product |

---

## Dependency graph

```
W1 Platform spine
 +-> W2 Semantic layer ----------------+
      +-> W3 Connectivity -------------+
           +-> W4 PQL & IR ------------+
                +-> W5 Execution ------+--> W6 Derivation & induction --+
                     |                 |         |                      |
                     +-----------------+--> W7 Monitoring & calibration-+
                                                 |                      |
                                                 +--> W8 Controls at scale
                                                           |
                                                           +--> W9 Experience
                                                                    |
                                                                    +--> W10 Enterprise & GA
```

**The critical path is W1 → W2 → W3 → W4 → W5.** Nothing can be demonstrated to a buyer until
Wave 5 produces evidence, and nothing can be *sold* until Wave 8 produces a reconciliation and
Wave 9 produces a screen a business owner can use. Waves 6 and 7 proceed in parallel once Wave 5
lands, and Wave 10's domain-pack and packaging work should start during Wave 8 rather than waiting.

---

<div align="center">
<img src="assets/prama-mark.svg" width="30" alt=""/><br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.<br/>
See <a href="../LICENSE">LICENSE</a> and <a href="../NOTICE">NOTICE</a>. Third-party names and marks are the property of their respective owners.</sub>
</div>
