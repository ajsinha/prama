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
## Wave 2 — Semantic layer  ·  **COMPLETE**

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
| W2.14 | REST API over the semantic layer, with contract tests | ✅ |
| W2.15 | Audit on every mutation, joined to the platform audit trail | ✅ |

### Acceptance criteria

- [x] Declare → amend → correct → read-at-any-instant round-trips on both time axes.
- [x] A correction and an amendment are distinguishable a year later, and an evidence record from
      March resolves the declaration March believed in.
- [x] A dataset can be declared, related and reported on **before it is bound to anything**.
- [x] Exactly one current version per entity, enforced by the database, not by code.
- [x] Semantic conflicts are surfaced rather than silently hosted.
- [x] `prama estate export` → edit YAML → `prama estate diff` detects drift in both directions.
      `apply` is deliberately absent until Wave 4: writing a directory back into a governed record
      belongs behind a pull request, not behind a shell command.
- [x] Estate maturity is computed and trends.
- [x] API contract tests green; every mutation audited.

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

| # | Task | State |
|---|---|---|
| W3.1 | Connector SPI and registry | ✅ |
| W3.2 | Capability matrix, declared and never probed | ✅ |
| W3.3 | **Config schema derived from connector source, with an overlay audit test** | ✅ |
| W3.4 | Credentials by vault reference, never displayed or stored | ✅ `env://` and `file://` providers, caching with TTL, audit trail; external vaults register a scheme |
| W3.5 | Discovery browser ranked by size and recency, not alphabetically | ✅ |
| W3.6 | Snapshot capture per source kind, with an honest `exact` flag | ✅ for the shipped connectors |
| W3.7 | Sampling planner with stated statistical bounds | ✅ |
| W3.8 | Profiler core and bounded-memory sketches | ✅ |
| W3.9 | Segmented and incremental profiling | ✅ exact fold of mergeable sketches; settled segments never re-read |
| W3.10 | Metric history store | ✅ Parquet and in-memory backends |
| W3.11 | The eight GA connectors | ◑ 4 of 8: filesystem, SQLite, PostgreSQL, object store (S3/GCS/Azure). Remaining — Kafka, REST, JDBC/ODBC, Snowflake — each need an SDK and a live service to verify against, so they are deferred rather than written blind |
| W3.12 | Feed subsystem: arrival, manifests, trailers, duplicate delivery | ✅ calendar-aware arrival judgement, trailer and manifest integrity |
| W3.13 | Read policy, budgets and source load ceiling | ✅ paths, hours, sampling, row and byte budgets, and a duty-cycle load ceiling |
| W3.14 | Binding suggestions for declared-but-unbound datasets | ✅ |
| W3.15 | Cost preview before a scan | ✅ from catalogue metadata only, with the basis of every number and the plan that would fit |

### Acceptance criteria

- [x] **Connect → discover → profile → inventory in ≤ 30 min unattended** on a 1,000-table source,
      inside a declared budget, with the source-load ceiling respected and measured (`NFR-OPS-002`).
      Measured against PostgreSQL 16: 1,000 tables discovered from the catalogue in 0.05 s without
      scanning one of them, then 1,000 objects, 229,700 rows and 4,000 columns profiled in 10 s —
      0.6% of the budget — under a 5% load ceiling, a 100,000-row cap and a 200 MB cap.
- [x] A connector's configuration form is derived from its code; a test fails when the curated
      overlay and the code disagree. The deriver walks the MRO, so a field a base class consumes
      is not silently absent from the form.
- [x] A business user configures a connection without ever seeing a credential. The record holds
      `env://…` or `file://…`; the value is resolved at the point of use and never stored, logged
      or serialised.
- [x] Sampling states its confidence; no sampled result is ever presented as exact. A segment
      profile reports itself incomplete even under a full-scan strategy, because its rates are the
      segment's and not the dataset's.
- [x] Feed arrival, lateness, duplicate delivery and truncation are detected, on a business
      calendar, with a severity and a next action on every finding.
- [x] Every connector passes its conformance suite; the capability matrix is published. A test
      fails the build when a registered connector is not accounted for in the suite, so connector
      breadth cannot drift silently.

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

W4.1 grammar and parser ✅ · W4.2 AST ✅ · W4.3 type checker and resolution ✅ ·
W4.4 selector expansion, materialised and versioned ✅ · W4.5 IR model and content addressing ✅ ·
W4.6 SQL backend and dialect adapters ✅ · W4.7 local evaluator ✅ · W4.8 **conformance corpus and
reference interpreter** ✅ · W4.9 property-based equivalence testing ✅ · W4.10 cost estimation ✅ ·
W4.11 linter ✅ · W4.12 formatter ✅ · W4.13 plain-language renderer ✅ · W4.14 LSP ⏳ ·
W4.15 importers for SodaCL, Great Expectations and dbt tests ✅ (ODCS quality blocks ⏳).

**Deferred, with the reason.** The language server (W4.14) is editor tooling with no editor to
serve until the UI arrives in Wave 9, and `prama control check` and `control format` already give
the same answers from a terminal and from CI. Building an LSP now would mean maintaining a second
implementation of diagnostics against no consumer. The ODCS importer waits on the same decision as
the other three: a contract's quality block maps cleanly only where it states a rule Prama has, and
the value of writing it is highest alongside the contract conformance work in Wave 8.

### Acceptance criteria

- [x] 100% of implemented constructs pass conformance on **every** supported backend. Eighteen
      corpus cases run on PostgreSQL 16, DuckDB and SQLite and agree on verdict, metrics and
      per-segment breakdown.
- [x] A construct a backend cannot express fails **at authoring time** with a clear message, never
      silently degrades. SQLite refuses a pattern rather than substituting LIKE, and the refusal
      is itself a conforming outcome.
- [x] The worked example in [07 §10](07-rule-language-spec.md) compiles and runs end to end — the
      CHECK suite, on SQLite and PostgreSQL and the reference interpreter, finding each planted
      fault. MONITOR, RECONCILE and DERIVES FROM are recorded as not yet implemented rather than
      trimmed from the example.
- [x] Every control has a generated plain-language rendering — generated, so it cannot drift from
      what the control does.
- [x] Cost is estimated before execution, counted in scans rather than controls — a scan is what
      the source pays for. Controls sharing a scope share a pass, and identical metrics are
      computed once: nine controls over the corpus run in three scans instead of nine, with
      answers identical to running them separately.
- [ ] ≥ 95% of 500 real design-partner controls express in the portable subset (`ASM-015`).
      **Blocked**: needs design partners. Cannot be simulated — a corpus we wrote ourselves would
      measure our own imagination, not a bank's control estate.

**Demo.** Write one control; run it unchanged on PostgreSQL, DuckDB and SQLite; show the compiled
SQL for each and the identical verdict — `prama control compile suite.pql --dialect …`. Snowflake
stands in for a fourth engine in the original plan and is not connected; the reference interpreter
takes its place as the independent voice, which is a stronger check than a fourth SQL engine
compiled by the same file.

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

W5.1 scheduler and trigger kinds ✅ · W5.2 adaptive cadence policy ✅ · W5.3 assertion fusion ✅ (landed in Wave 4) · W5.4 budget
enforcement and shedding ✅ · W5.5 worker model and lease-based claim ✅ · W5.6 agent mode, outbound-only ✅ (see [22](22-distributed-execution.md)) ·
W5.7 incremental execution and watermarks ✅ · W5.8 **evidence record, hash chain, signing** ✅ ·
W5.9 WORM export and retention tiers ✅ · W5.10 **deterministic replay and divergence report** ✅ ·
W5.11 gate, quarantine and tag actions ✅ · W5.12 streaming seam ✅, DEC-17 benchmark ◑ (evaluation measured; transport open) ·
W5.13 OpenTelemetry and OpenLineage ✅ · W5.14 soak and chaos tests ✅.

### Acceptance criteria

- [x] 10⁶ assertion executions/day sustained on one control plane with N workers. Measured at
      ~1,600 assertions/second in a single process — compile, execute, judge and record, end to
      end — which is 140× the target. **The measurement is of Prama's own overhead**, against an
      in-memory engine; a real warehouse is the bottleneck in any real deployment, and the number
      says only that the platform is not.
- [x] **100% of runs replay to an identical verdict**, or emit a divergence report naming the cause.
      The report distinguishes six causes and refuses to smooth an unexplained divergence into one
      of the ordinary ones. A run whose answer holds while its inputs move is reported as *stable*
      rather than diverged — otherwise a nightly replay against fresh data reports every record as
      diverged and the ones that matter are lost among the ones that do not.
- [x] Fusion demonstrates the `NFR-COS-001` claim: ≤ 50% of a naive per-rule full scan. Measured at
      **40%** on 400 generated controls and **33%** on 2,000 — the saving grows with the suite — adding controls to a
      dataset costs columns, not scans.
- [x] Evidence median ≤ 2 KB; hash chain verifiable without Prama running. Measured at 848 bytes on
      the worked example. The verification algorithm is written out in words, and the test suite
      reimplements it in the standard library alone and requires the two to agree — so the
      description cannot drift from the code, and an auditor following it reaches the same
      conclusion about the same record.
- [x] Execution continues for ≥ 24 h during a control-plane outage, buffering and replaying. A
      thousand findings spooled and delivered intact, including across an agent restart and with
      40% of receipts deliberately lost.
- [ ] `DEC-17` decided on measured throughput, not preference. **Half answered.** Prama's own
      evaluation is measured at 4.82 µs/message and 208,000 msg/s per core on a five-control mix —
      a thousandfold inside the latency budget — so assertion cost is not the constraint and the
      decision does not turn on it. DishtaYantra's transport throughput still needs a multi-node
      harness. See [18 §5](18-technology-stack.md).

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

W6.1 Γ generator for grain, rhythm and value domains ✅ · W6.2 Γ for all 13 relationship kinds ✅ ·
W6.3 semantic-type cascade with deterministic validators first ✅ · W6.4 UCC and FD mining ✅ ·
W6.5 approximate and conditional variants ✅ · W6.6 IND and DC mining ✅ ·
W6.7 relationship discovery ✅ · W6.8 LLM provider abstraction with BYO and self-hosted ✅ ·
W6.9 **grammar-constrained decoding** ✅ ·
W6.10 candidate validation against real data, discarding trivial and unstable rules ✅ ·
W6.11 utility ranking learned from acceptance history ✅ · W6.12 Proposal object and review workflow ✅ ·
W6.13 induction from documents with citation retention ✅ · W6.14 example-driven induction ✅ ·
W6.15 coverage analyser ranking unprotected CDEs by risk ✅.

### Acceptance criteria

- [◑] On a real source, **≥ 80% of columns and ≥ 95% of declared CDEs** under a reviewed control
      after one week of effort (`S5`). **Mechanism proven, on synthetic data.** Coverage is
      measured per *(attribute, dimension)* rather than per column, because a single
      `IS NOT NULL` makes a column "covered" while its format and its domain go unchecked.
      On a realistic Tier 1 declaration the dataset declaration alone reaches **82% of pairs
      and 71% of CDE pairs** — short of the target, and the reason is worth stating: nothing a
      business owner can say about *one* dataset covers a CDE's accuracy, because accuracy
      means comparison against something outside the row. Adding the relationship declarations
      reaches **100% and 100%**. The remaining claim — that a week of a real steward's effort
      produces those declarations on a real source — needs a real source.
- [x] Every declaration in docs/03 §5 generates its stated controls, with provenance naming the
      declaration that produced it. Every generated control round-trips through the parser and
      lowers to a plan, which is asserted rather than assumed — the round-trip found two defects
      the first time it ran.
- [x] 100% of LLM-generated PQL is parsed, type-checked and sandbox-executed before display; the
      generation-failure rate is measured and reported. Enforced by construction: `Validated`
      refuses to be built unless every gate ran, and a fifth gate rejects a control that cannot
      be made to fail. The failure rate counts every attempt, not just the last of a retry —
      an earlier version counted three parse errors as one.
- [◑] Mining + LLM fusion beats either alone on acceptance rate (`RQ5`). **The mechanism is
      built and the comparison needs reviewers.** Two origins reaching the same rule merge into
      one corroborated proposal rather than two, or one with the evidence discarded, and the
      corroborated one ranks higher. The acceptance-rate claim itself is about human decisions
      and cannot be measured without them.
- [x] Zero code paths where a model output reaches a verdict — architecture test green, and the
      guard now carries a counterfactual proving it still fires. It also had to be narrowed:
      bare `prompt` matched a business word in this codebase, and a guard that cries wolf earns
      an exclusion list.
- [x] Induction from ≤ 20 labelled cells produces a usable rule (the Raha result). **Six labels
      yield `IS VALID 'lei'`.** The first implementation yielded an enumeration of the labelled
      values — perfect recall, generalising to nothing — so an enumeration is now offered only
      when the labelled values repeat, which is what separates a closed domain from a sample.

**Demo.** Declare a grain, a rhythm and one relationship; watch eight controls appear, each with the
sentence that justifies it, a backtest and an estimated alert volume; approve them in one click.

**Outcome.** All fifteen tasks complete. The two half-answered criteria are half-answered for
the same reason: both are claims about what real people do with real data, and what this wave
could build and measure was the machinery underneath them.

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

W7.1 monitor fleet over metric history ✅ · W7.2 calendar and seasonality model ✅ ·
W7.3 detector suite ✅ · W7.4 **conformal calibration with adaptive weighting** ✅ ·
W7.5 **hierarchical BH/BY selection** ✅ · W7.6 sensitivity expressed as budget, FDR or power ✅ ·
W7.7 validity monitor and honest degradation ✅ ·
W7.8 changepoint detection and accept-new-normal with permanent annotation ✅ · W7.9 segmented
monitoring with correlated-alert roll-up ✅ · W7.10 cold-start priors ✅ · W7.11 champion/challenger
and promotion gates ✅ · W7.12 model cards ✅ ·
W7.13 calibration benchmark across five drift regimes ✅.

### Acceptance criteria

- [x] **Calibration error ≤ 0.02** across stationary, seasonal, level-shift, regime-switch and bursty
      regimes (`S3`). On synthetic generators of each regime; FinDQ-Bench itself is Wave 10's
      corpus. The benchmark reports a **grid rather than a number**, because no single mechanism
      handles all five and one number would hide that: conditioning repairs seasonality and cannot
      repair a level shift, forgetting repairs a level shift and makes seasonality worse, and
      adaptation handles the regime that switches back. The criterion asserted is that every
      regime has a mechanism whose realised rate matches what it promised — which is the claim
      that is actually true.
- [x] Alert volume tracks the declared budget within tolerance; the dial has a statistical meaning.
      Measured end to end: a monitor declaring 0.05 realises 0.0467 over 300 judged days, with a
      calibration error of 0.0061. A budget the history cannot express is **refused with the
      arithmetic** — two false alarms a month across 4,400 runs needs a level of 0.00045, and a
      hundred comparable observations cannot express one below 0.01.
- [x] When calibration assumptions fail, the monitor **says so** in the UI and in every alert. The
      disclosure travels on the alert, not the status page, because the person reading one at three
      in the morning is not on the status page. The degradation test uses a 99.9% interval rather
      than 95%: it runs against every monitor in the fleet, and the component whose job is
      calibration cannot be the one crying wolf.
- [x] A new asset is usefully monitored on day one from priors, labelled as priors — and a prior
      never promises a false-alarm rate, because printing one beside it would be exactly the lie
      this wave exists to stop telling. The handover to real calibration is announced.
- [x] Every monitor has a model card and a measured precision history. Derived from the running
      monitor rather than written about it, carrying "34 alerts, 29 confirmed" rather than "high
      accuracy", and stating what the detector is blind to.
- [x] The calibration curve — nominal versus empirical — can be plotted, across three orders of
      magnitude with Wilson intervals. No competitor can produce this plot at all, and that is
      itself a result.

**Demo.** Set "no more than two false alarms a month in this domain"; show the resulting thresholds,
the calibration curve, and what happens to the guarantee when a regime shift is injected.

**Outcome.** All thirteen tasks complete. Three defects found by writing the property down and
measuring it rather than asserting it: absolute forecast residuals broke exchangeability on a
growing series; the observation was scored against a different reference set from its own
calibration points; and adapting the level cannot work at all once every p-value has saturated,
which the level's realised rate alone does not reveal.

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

W8.1 reconciliation engine and matchers ✅ · W8.2 normalisation with as-of rate sources ✅ ·
W8.3 break classification and workflow ✅ · W8.4 reconciliation certificate ✅ · W8.5 N-way and
roll-forward ✅ · W8.6 entity resolution with active learning ✅ ·
W8.7 lineage ingestion and graph store ✅ · W8.8 column-level SQL parsing ✅ ·
W8.9 **legacy scanners (the docs/20 G2 gap)** ◑ (SQL dialects verified; ETL shapes configurable
and explicitly unverified against a real export) · W8.10 incident correlation and lifecycle ✅ ·
W8.11 RCA hypothesis ranking ✅ · W8.12 impact analysis ✅ · W8.13 scoring and
materiality weighting ✅ · W8.14 **trust propagation** ✅ · W8.15 alerting and routing ✅ ·
W8.16 learning loop with promotion gates and rollback ✅.

### Acceptance criteria

- [x] A sub-ledger↔GL reconciliation runs end to end with break workflow and a signed certificate.
      On the worked example, 14 breaks classify as 4 sign-convention, 4 duplicates, 4 genuine and
      2 missing — and 8 of the 14 point at the reconciliation's own setup rather than at the data,
      which is routed away from the steward rather than into their queue.
- [◑] Reconciliation at 10⁸ records per side within budget. **Measured at 100,000 a side and
      extrapolated**: 87,000 rows/second single-threaded, so 10⁸ a side is about 0.6 hours on one
      core and the work partitions by key. What this establishes is the constant, not that a
      hundred million rows fit in memory — they do not, and Wave 5's streaming execution is what
      makes that irrelevant. A run at full scale needs the data.
- [x] One upstream defect produces **one** incident, not four hundred. A feed failure fanning out
      to 48 findings across 12 datasets becomes one incident about the column, and the wave demo's
      5 findings across 4 datasets become one about the sub-ledger — including the lone finding
      whose own column-ancestor resolved to itself, which is exactly the one that most needs
      folding in.
- [x] Trust propagation demonstrably changes remediation ranking versus severity ranking (`RQ8`).
      A mild defect upstream of a regulatory return outranks a severe one in a scratch table:
      severity ranks the finding and trust ranks the consequence, and they disagree exactly where
      the disagreement is worth having. Four semirings are offered because businesses genuinely
      mean different things, and every score carries the path that decided it.
- [ ] Alert precision ≥ 0.85 at declared FDR ≤ 0.10 in live shadow (`S2`). **Not attemptable
      here** — it is a claim about live data and real reviewers, and the shadow machinery that
      would measure it (Wave 7's tournament, Wave 8's control arm) is built and waiting for a
      deployment. Manufacturing a number for it would be the opposite of what this wave is for.
- [x] The learning loop shows measured uplift against a frozen-model control arm (`RQ9`). The
      mechanism is built and behaves correctly in both directions: a real +22% improvement promotes
      with an interval excluding zero, and a loop doing nothing does not, however encouraging its
      point estimate. The *number* for a given deployment needs that deployment.

**Demo.** Break the sub-ledger deliberately; watch one incident open with a ranked cause, an impact
list naming the affected return, a classified break population, and a trust score that drops on
every descendant of the defect.

**Outcome.** Sixteen tasks, fifteen complete and one deliberately partial. Four of six acceptance
criteria met, one measured-and-extrapolated, one requiring a live deployment. The legacy scanners
ship with their verification status in the code: the SQL dialects are tested against real syntax,
the ETL shapes are configurable and say plainly that they have not been run against a customer
export — because a parser written against a guess looks like support and fails on first contact.

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
| `prama.web/design` | Design tokens on Bootstrap 5 + CSS custom properties, six-dimension palette, WCAG 2.2 AA, light/dark, density modes | `NFR-USA-003`, `008` |
| `prama.web/estate` | **Estate map**: Sigma.js WebGL graph, overlays, Cytoscape drag-to-declare canvas | `FR-MET-100`…`102`, `NFR-SCA-011` |
| `prama.web/declare` | Dataset in ≤ 5 min, relationship by drawing, attribute interpretation, propose-and-confirm everywhere | `NFR-OPS-003` |
| `prama.web/studio` | No-code builder, CodeMirror 6 PQL editor with LSP, live preview over SSE, backtest, cost | `FR-UIX-002`…`004` |
| `prama.web/proposals` | Review queue with evidence, backtest, expected alert volume; batch approve | `FR-IND-007` |
| `prama.web/incidents` | Keyboard-first one-screen triage, batch disposition | `FR-UIX-006` |
| `prama.web/recon` | Side-by-side break workbench, grouping, certificate sign-off | `FR-REC-008` |
| `prama.web/scorecards` | Drill-down to evidence; attestation with e-signature and seal | `FR-SCR-007`, `008` |
| `prama.assistant` | Conversational agent: contextual panel, workspace, Slack/Teams | `FR-CHT-001`…`017` |
| `prama.mcp` | MCP server, read and propose tools only by default | `FR-EXT-008` |
| `prama.report.render` | Jinja-rendered PDF and print artefacts | `FR-SCR-009` |

### Tasks

W9.1 ✅ design tokens and the Jinja app shell · W9.2 ✅ estate map with Sigma.js WebGL rendering ·
W9.3 ✅ drag-to-declare canvas ·
W9.4 ✅ declaration flows with inferred-then-confirmed defaults · W9.5 ✅ no-code rule builder ·
W9.6 ✅ CodeMirror PQL editor and LSP integration · W9.7 ✅ live preview and backtest over SSE ·
W9.8 ✅ proposal review queue ·
W9.9 ✅ incident triage workspace · W9.10 ✅ reconciliation workbench · W9.11 ✅ scorecards and drill-down ·
W9.12 ✅ attestation and e-signature · W9.13 ✅ **assistant with the full safety contract** · W9.14 ✅ MCP
server · W9.15 ✅ print rendering · W9.16 ✅ accessibility audit · W9.17 usability study.

### Where the console stands

Built on the reversed stack: Jinja on FastAPI, Bootstrap 5, jQuery, everything vendored, mounted
onto the same application as the API so the two cannot disagree about the database, the
configuration or the error taxonomy.

| Done | Not done |
|---|---|
| Design tokens: the six-dimension palette, light/dark, comfortable/compact density, Unverified Grey reserved | The chart primitives — server-rendered SVG in Python, which doubles as the PDF renderer |
| App shell: nav that marks where you are, skip link, live region, flash | Sign-in; the caller comes from `tenancy.default_tenant` until Wave 10 |
| Estate map on Sigma/WebGL over graphology, with the same nodes in a keyboard-reachable table | Cytoscape drag-to-declare (W9.3) |
| Dataset page naming the *control* each gap costs, not the null column | Attribute editing and relationship drawing |
| Declaration list and form, organised around questions, approval requirement derived from `ApprovalPolicy` | Attribute-level suggestions — concepts, value domains, CDE marks |
| **Inferred, never confirmed** — the form profiles a table and offers what it found with the evidence attached; a head sample pre-fills nothing, and warnings are kept apart from defaults | Profiling through a connector rather than the console's one local file |
| Control studio: CodeMirror 5, check/explain/compile, residual disclosure on the SQL | Go-to-definition and rename, which need a workspace rather than a document |
| **A real language server** — `prama lsp serve` over stdio, and the console's editor calling the same `LanguageService`, so an editor cannot underline something the compiler accepts | A live catalogue; the server reads an exported file so an editor needs no warehouse credentials |
| **Preview and backtest** — run an unapproved control against real data, one business day per SSE event; empty days counted apart from quiet ones; nothing written to the ledger | A preview against a warehouse rather than a local file, which needs the connector query path wired to the console |
| The no-code builder: eight rules in business terms, always showing the PQL it wrote, refusing to emit anything that will not re-read | More rule shapes — functional dependency, cross-dataset comparison |
| Relationships end to end: declare, confirm, reject; pick-then-pick on the map | Attribute-level relationship editing |
| Charts as server-rendered SVG (`prama.report`), one renderer for screen and print | Wiring them into scorecards, which have no measurements to draw |
| Contrast measured, not eyeballed; every derived colour legible on all three grounds — card, page, striped row | Keyboard-only walkthroughs and a screen-reader pass, which are judgement rather than a rule engine |
| **`axe-core` in Chrome** over sixteen pages and five themes, WCAG 2.2 AA, with a counterfactual proving the audit can fail | Running it in CI, which needs a browser on the runner |
| Print artefacts: declaration pack, control pack and **attestation pack**, self-contained, coverage stated on every one | Batch export of a period's packs as one bundle |
| `prama mcp` — the MCP server on the assistant's own registry, fenced and scanned | Streamable-HTTP transport; stdio only for now |
| Proposal queue with accept and reject, `Unsatisfiable` first, rejections recorded so nothing is re-proposed | Batch approve; backtest and expected alert volume beside each proposal |
| **The evidence ledger, persisted** — hash-chained, append-only, erasure without breaking the chain, verification on a screen | Retention tiering and WORM export wired to the persisted store |
| **Controls, persisted** — bitemporal, idempotent by identity, everything derived from the PQL, suppression that needs an expiry and a reason | A scheduler that runs them; nothing executes on its own yet |
| Incidents, reconciliation and scorecards reading real evidence | Batch disposition across a whole incident queue |
| **Sample drill-down** — the failing rows beside the count they are a sample of, with masked columns named and "never collected" told apart from "no longer held" | Re-querying the source for fresh rows, which needs the connector query path on the console |
| **The break workbench, persisted** — breaks tracked across runs, ageing from first sighting, clearing inferred from absence, ordered by what needs a person rather than by size | The reconciliation certificate signed off from this screen |
| **Attestation** — figures derived from the ledger, not typed; sealed with an HMAC over the content hash; append-only with supersession | An asymmetric signature, which would say something to a reader who does not hold the key |

**The honest limit of this wave.** Controls are stored and evidence is stored, and *nothing runs
them*. There is no scheduler wired to the persisted estate, so every screen above reads evidence
that arrived some other way. What those screens will not do is render an empty list as a clean one,
which is the single most dangerous screen a data quality product can ship.

**Evidence format 1.1.** The record now carries the control's dimensions and the tier it ran under.
`content()` hashes the fields the record's *own* version defines, so a 1.0 chain still verifies
against a 1.1 build — emitting a new field unconditionally would break every hash after the first
and present as an estate-wide tampering alert the morning after a deploy.

**No PDF engine, deliberately.** WeasyPrint and its relatives pull in cairo, pango and their system
packages, which is a serious dependency to add to every on-premises install for a job the browser
already does correctly. The packs are self-contained print-ready HTML and the console says so;
Print → Save as PDF, or a headless Chrome in the deployment, produces the file.

**No MCP SDK, deliberately.** `prama.mcp` implements JSON-RPC 2.0 over stdio directly, in about two
hundred lines, because every transitive dependency is a question someone has to answer in an
air-gapped estate. The cost: when MCP's schema moves, this moves by hand. The protocol version is a
pinned constant, reported in the handshake.

**A defect the console surfaced, recorded here because it is not a UI defect.**
`Threshold.render()` drops the comparator for a rate — `BELOW 0.5%` — so a threshold built with
`<` renders identically to one built with `<=` and re-reads as `<=`. No parsed control can reach
it, because the parser only ever produces `<=`; anything constructing a rate threshold
programmatically can. Found by the rule builder's `parse(render(c)) == c` guard.

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

**Wave risks.** Reversing DEC-18 (docs/18 §4) removes the largest single engineering line item and
adds two smaller ones: keyboard-first batch triage and rich selection state are hand-written rather
than inherited from a component library, and the accessibility guarantee is held by `axe-core` in CI
rather than by a component contract. Scope discipline still matters more here than anywhere: every
screen not on the list above is a screen not built.

---

## Wave 11 — The expression layer

**Objective.** A business owner writes the expression they would have written in a
spreadsheet, and it compiles to pushed-down SQL that means exactly one thing on every engine.

**Depends on** Wave 4 (PQL, IR, the conformance suite). **Enables** the controls that today get
written as SQL by somebody else, or not at all.

### Why this wave exists

Two requests keep arriving and they are the same request: *"can I write a formula?"* and *"can I
call my own code?"*. Both are asking for expressiveness the declarative core does not have, and
both have an easy answer that would destroy the product's guarantees.

The easy answer to the first is "we accept Excel formulas". Excel's syntax is a weekend of work;
Excel's *semantics* contradict Prama at half a dozen points — `"1" + 1 = 2`, a blank is `0` in
arithmetic and `""` in concatenation, `#DIV/0!` propagates differently from `NULL`, money is a
float, dates are serial numbers with a 1900 leap-year bug, and `NOW()` makes a plan unreplayable.
Adopting them wholesale would mean the same control giving two answers and nothing noticing.

The easy answer to the second is a `PYTHON("…")` escape hatch. It breaks replay (arbitrary code can
read a clock), breaks versioning (the code is part of the control's meaning and not part of its
hash), removes the reference interpreter's ability to check the compiler, and becomes the place
every hard control goes — so in two years the semantic layer is decoration around a pile of Python.

So this wave does neither. It claims Excel **familiarity**, never Excel **compatibility**, and it
widens the *validator catalogue* rather than the language.

### The hole this closes first

Today an unknown function name passes straight through to SQL. `NONSENSE_FN(b)` parses, lowers,
receives a plan id, and compiles to `WHERE (NONSENSE_FN("b") > 1)`. Meanwhile the reference
interpreter returns `UNKNOWN` for any function it does not recognise. **The compiler and its
independent check silently disagree**, which is precisely the condition the conformance suite
exists to make impossible. There is no function catalogue at all.

### Deliverables

| Module | Contents | Requirements |
|---|---|---|
| `prama.pql.functions` | The function catalogue: one declaration per function carrying its per-dialect lowering, its reference implementation, its unknown-propagation rule, its pushdown requirement and its stated divergence from Excel | `FR-RUL-*`, `CON-004` |
| `prama.pql.excel` | Excel-familiar surface: a hand-written precedence-climbing parser producing the **same** `ast.Expression` tree. No second IR, no second evaluator | `FR-UIX-002` |
| `prama.classify.plugins` | Third-party `SemanticValidator` registration by entry point, with purity enforced by import scanning and the implementation's content hash folded into the plan id | `FR-EXT-*`, `NFR-SEC-*` |
| `bench/expressions` | Pushdown coverage and throughput: which functions compile to SQL and which fall back | `NFR-PER-*` |

### Tasks

W11.1 ✅ function catalogue and registry · W11.2 ✅ type-check function calls, refusing unknown names ·
W11.3 ✅ lowering refuses what the catalogue does not hold · W11.4 ✅ per-dialect rendering from the
catalogue · W11.5 ✅ reference implementation for **every** function, no exceptions ·
W11.6 ✅ **function conformance corpus** — every function's SQL and its reference implementation give
the same answer on the same inputs, on every engine · W11.7 ✅ Excel front end (Pratt parser) ·
W11.8 ✅ `SATISFIES EXCEL '…'` surface · W11.9 ✅ divergence notes rendered by `control explain` ·
W11.10 ✅ volatile functions refused by name · W11.11 ✅ validator plugin registry ·
W11.12 ✅ purity enforcement and implementation hashing · W11.13 ✅ pushdown coverage benchmark.

### Acceptance criteria

- [ ] **No function exists without both a lowering and a reference implementation.** Enforced by
      test, not convention.
- [ ] Every catalogued function agrees between SQL and the reference interpreter on the conformance
      corpus, on every engine that claims it.
- [ ] An unknown function name is refused at type-check time, naming the ones that exist.
- [ ] A function an engine cannot express is **refused**, never approximated.
- [ ] Every divergence from Excel is declared on the function and printed by `control explain`.
- [ ] A volatile function (`NOW`, `RAND`, `INDIRECT`) is refused with the reason: a control must
      replay.
- [ ] A validator plugin's implementation hash is part of the plan id: editing the code changes the
      control's identity rather than silently changing what past evidence meant.
- [ ] A plugin that imports a clock, a socket or a model is refused at registration.
- [ ] ≥ 90% of the catalogue pushes down on PostgreSQL and DuckDB.

**Demo.** A business owner writes `SATISFIES EXCEL '=AND([quantity]>0, [notional]=[quantity]*[price])'`,
sees the SQL it becomes, and sees the one place it differs from what Excel would do — stated on the
control rather than discovered in production.

**Wave risks.** The temptation to add "just one more" Excel function without a reference
implementation, which is how the compiler and its independent check drift apart. The mitigation is
structural: the catalogue makes the reference implementation a required field, so a function
without one does not exist.

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

W10.1 ◐ streaming backend and in-flight enforcement (per-message enforcement with dead-lettering; a Kafka/Flink transport not wired) · W10.2 ✅ tenant isolation test suite ·
W10.3 ◐ SSO/SCIM, vault, CMK (local sign-in and RBAC done; SSO not started) · W10.4 ✅ residency enforcement and SIEM export (five registered egress points, each gated and each refuted by test; the network-reaching module list derived from imports so an unregistered egress fails the build) · W10.5 ✅ Helm chart (lints, renders, refusals tested; not installed on a cluster) ·
W10.6 ◐ Operator and CRDs (the CRD and the reconciliation decision, tested; the control loop needs a cluster) · W10.7 ✅ all-in-one image (builds, runs, serves; verified end to end) · W10.8 ◐ **offline bundle and air-gapped update** (seal, verify, SBOM; image signing and an air-gapped end-to-end run not done) ·
W10.9 ✅ COBOL/EBCDIC reader · W10.10 ✅ financial message parsers (SWIFT MT, pacs.008/camt.053, FIX 4.2-4.4, ISO 8583, FpML 5; `prama pack parse`) · W10.11 ✅ banking concepts, validators
and calendars (17-concept ontology with three-state recognition, calendars as rules, cross-field checks) · W10.12 ✅ regulatory control catalogue with citations (20 obligations across 9 regimes — BCBS 239 P3-P5, ISO 20022, MiFIR, EMIR REFIT, AnaCredit, CRR large exposures, AML, SOX, GDPR; every citation marked unconfirmed until a compliance function checks it) · W10.13 ✅ reference reconciliation
templates · W10.14 ✅ ODCS runtime and CI gates · W10.15 ✅ data diff · W10.16 ◐ catalog write-back (the SPI, badge semantics and a reference target; vendor adapters not written) ·
W10.17 ✅ benchmarks (corpus of 28 defect classes across 6 families, bounds and three ablations, `prama bench`; external-tool baselines named as not run, and scale/real datasets still to come) · W10.18 ✅ live-shadow harness (blinding, adjudication and burden metrics; the ninety-day runs are a customer engagement) · W10.19 ✅ SOC 2 readiness (the matrix, with its gaps; the audit itself is an engagement) ·
W10.20 ✅ **auditor RDARR validation** (the pack generates; `scripts/verify_evidence.py` checks a bundle with no Prama and no third-party imports, run as a subprocess in the tests and refuted five ways — an auditor at a client site is still an engagement) ([21 §3 Unlock 1](21-how-we-win.md)).

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
