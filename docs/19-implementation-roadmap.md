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

## Wave 1 — Platform spine

**Goal:** the substrate every later wave stands on, with the hard constraints enforced from commit one.

| Module | Contents |
|---|---|
| `prama.core.config` | Layered configurator: defaults → `application.yaml` → `application.local.yaml` → env → CLI. `${VAR:default}` substitution. YAML and `.properties`. Typed, validated accessors bound to dataclasses. Redaction on display. |
| `prama.core.errors` | Error taxonomy with stable codes; every error states what happened, why, and the next action. |
| `prama.core.logging` | Structured logging, correlation ids, redaction filter. |
| `prama.core.ids` | Sortable, time-prefixed identifiers; typed id classes per entity. |
| `prama.core.clock` | Injectable `Clock` (UTC, monotonic, business-date placeholder) so time is testable. |
| `prama.core.json` | `orjson` with stdlib fallback — one JSON API. |
| `prama.core.registry` | Plugin registry: entry points + capability manifests + conformance-suite discovery. |
| `prama.core.concurrency` | `TaskSupervisor` (structured task groups, cancellation, back-pressure), `BoundedQueue` (byte-bounded), `RateLimiter`, `LeaseManager` ABC + in-memory and DB providers. |
| `prama.db` | **The only package that imports SQLAlchemy.** `DbSettings`, `Dialect` abstraction, `EngineFactory`, `SessionManager`, `UnitOfWork`, `Repository[T]` base, schema `Bootstrapper` and `Verifier`, portable column types. |
| `schema/` | `sqlite.sql` + `postgres.sql` — platform tables only in this wave. |
| `prama.cli` | `prama config show`, `prama db init|verify|info`, `prama version`. |
| `tests/architecture` | Layering, file length, concurrency hygiene, model-verdict guards. |

**Exit:** `prama db init` + `prama db verify` both green on SQLite *and* Postgres from the same
code, selected only by config; architecture tests enforce C3–C6; ≥ 90% coverage on `prama.core` and
`prama.db`.

---

## Wave 2 — Semantic layer

**Goal:** a business user can declare a dataset, its attributes, and a relationship, through the API,
and the system versions and audits every change.

- Domain model as OO aggregates: `Domain`, `Dataset`, `Attribute`, `Concept`, `ConceptProperty`,
  `Relationship`, `Journey`, `Binding`, `Connection`, `Codelist`, `Calendar`.
- **Bitemporal** persistence (valid time + transaction time) so any past state is reconstructable;
  no row is ever updated in place.
- Declaration value objects: `Grain`, `Rhythm`, `Temporality`, `Authoritativeness`, `ValueDomain`,
  `Optionality`, `Criticality`, `Sensitivity`.
- Unbound datasets as a first-class state (`FR-MET-003`).
- Repositories + services + validation; semantic-conflict detection (`FR-MET-043`).
- REST API (FastAPI, OpenAPI 3.1) for the whole semantic layer; idempotency keys; problem details.
- Approval workflow and maker–checker for Tier-1 objects; audit trail on every mutation.
- GitOps serialiser/deserialiser and drift detection.
- Estate-maturity scoring (`FR-MET-104`).

**Exit:** declare→version→audit→export→re-import round-trips losslessly; estate maturity computed;
API contract tests green.

---

## Wave 3 — Connectivity & profiling

**Goal:** point Prama at a real source and get a profile, semantic types, and an inventory without
writing anything.

- **Connector SPI:** `discover()`, `describe()`, `snapshot()`, `read()`, `sample()`,
  `pushdown_capabilities()`, `execute_plan()`, `health()`. ABC + registry + capability matrix.
- **Derived connector config schema** — fields parsed from the connector's own code with a
  presentation-only overlay, and a test that fails when they disagree ([18 §3.2](18-technology-stack.md#32-adopt-the-pattern-rewrite-the-code)).
- Connectors: PostgreSQL, SQLite, Snowflake, filesystem/S3 CSV+Parquet, SFTP feed, Kafka, generic
  JDBC/ODBC, generic REST.
- Feed subsystem: landing detection, filename patterns with date tokens, arrival windows,
  header/trailer, manifests, duplicate/out-of-sequence detection, decryption.
- Snapshot capture per source kind; sampling planner with statistical bounds.
- Profiler: column statistics, sketches (HLL, t-digest, count-min), pattern profiling,
  segmented profiling, incremental profiling, cost budgets.
- **Metric history store** (Parquet/Iceberg + DuckDB) — the substrate for Waves 7 and 8.
- Read policy and per-source load ceiling enforcement.

**Exit:** connect → discover → profile → inventory in ≤ 30 min unattended on a 1,000-table source,
within a declared budget, with load ceiling respected.

---

## Wave 4 — PQL and the IR

**Goal:** a control can be written once and executed identically on two backends.

- Grammar (EBNF → parser), AST, and the two isomorphic surfaces (expression + YAML).
- Type checker; column/attribute resolution against the semantic layer; selector expansion.
- Static analysis: cost estimation, dialect capability checking, subsumption/redundancy/contradiction,
  never-fires/always-fires lint.
- Formatter (`prama fmt`), linter (`prama lint`), LSP server.
- **IR**: typed logical plan, content-addressed, versioned, serialisable.
- Backends: ANSI SQL with dialect adapters (Postgres, SQLite, Snowflake first) and Arrow/DuckDB.
- **Conformance suite** `Π`: golden PQL programs executed on every backend against a reference
  interpreter, plus property-based generation. Failure blocks the build.
- Plain-language rendering of every control.

**Exit:** 100% of implemented constructs pass conformance on all backends; the
[07 §10](07-rule-language-spec.md) worked example compiles and runs.

---

## Wave 5 — Execution, scheduling and evidence

**Goal:** controls run on a schedule, at scale, and leave evidence that replays.

- Scheduler: cron/interval/calendar/event/dependency triggers; **adaptive re-examination cadence**;
  priority classes; budget enforcement with prioritised shedding; back-pressure.
- **Assertion fusion** — many assertions over one scope become one scan.
- Worker model: stateless executors, lease-based work claim, agent mode (outbound-only), embedded
  mode; horizontal scale-out with fair scheduling.
- Incremental execution, watermarks, late/restated data handling.
- **Evidence ledger:** hash-linked append-only records, signing, daily Merkle root, WORM export,
  storage budget, and **deterministic replay** with divergence reporting.
- Run/verdict/metric pipeline into the metric history and the evidence store.
- Streaming execution **seam**: the backend interface plus the DishtaYantra spike and the
  `NFR-SCA-005` benchmark that decides DEC-17.
- OpenTelemetry traces, OpenLineage emission.

**Exit:** 10⁶ assertion executions/day sustained on a single-node control plane with N workers;
100% of runs replay to identical verdicts; fusion demonstrates the `NFR-COS-001` cost claim.

---

## Wave 6 — Declaration-derived controls, mining and induction

**Goal:** a business declaration produces reviewed, running controls with no SQL written.

- **Γ generator**: the declaration→control mapping ([03 §5](03-business-semantic-layer.md#5-from-declarations-to-conclusions),
  [prama-paper §3.2](paper/prama-paper.md)) — grain, rhythm, value domains, semantic types, and all
  13 relationship types.
- Constraint mining: UCC, approximate and conditional FDs, partial INDs, approximate DCs, order
  dependencies — sampled with bounds, verified on full data, budget-capped.
- Semantic-type inference cascade: validators (checksums) → code lists → patterns → names →
  embeddings → LLM adjudication over a closed vocabulary.
- Relationship discovery: overlap, containment, naming, schema signature, query-log co-access.
- **LLM rule authoring**: retrieval from the semantic layer, grammar-constrained decoding,
  parse/type-check/sandbox-execute, empirical validation, utility ranking.
- Induction from documents (with citations) and from examples (weak supervision + active learning).
- **Proposal** object and workflow — the single mutation channel for everything automated.
- BYO-LLM provider abstraction (Anthropic, Azure OpenAI, Bedrock, Vertex, self-hosted).

**Exit:** on a real source, ≥ 80% column coverage with reviewed controls in one week of effort;
proposal acceptance rate measured and reported; zero paths from a model to a verdict.

---

## Wave 7 — Monitoring and calibration

**Goal:** alerts with a declared, honoured false-alarm budget.

- Monitor fleet over the metric history: volume, nulls, distincts, freshness, schema, distribution,
  derived business metrics; segmented monitors.
- Seasonality: intraday/daily/weekly/month-end/quarter-end, business and settlement calendars,
  declared volume drivers from the semantic layer.
- Detectors: robust seasonal decomposition, quantile bands, isolation forest/LOF, matrix profile,
  forecast-residual; champion/challenger in shadow.
- **Conformal calibration** with adaptive weighting; **hierarchical FDR** over the
  domain→dataset→attribute→check lattice; sensitivity expressed as budget/FDR/power.
- Guarantee-validity monitor and visible degradation.
- Changepoint detection and "accept new normal" with permanent annotation.
- Cold-start priors from semantic type, pack, siblings, and declared rhythm.
- Model cards, reproducibility metadata, degradation detection and rollback.

**Exit:** calibration error ≤ 0.02 across five drift regimes on FinDQ-Bench; alert volume tracks the
declared budget within tolerance.

---

## Wave 8 — Controls at scale

**Goal:** the control types that make banking buy, plus the loop that makes the system improve.

- **Reconciliation engine**: match strategies, normalisation (FX/unit/code-set/timezone),
  tolerances, break classification, N-way, time-shifted roll-forward, 10⁸-record scale, break
  workflow, reconciliation certificate.
- **Entity resolution**: blocking, Fellegi–Sunter with EM, comparison functions, active learning,
  clustering, evaluation harness.
- **Incidents**: correlation and deduplication, lifecycle, ownership routing, escalation, RCA
  hypothesis ranking over the lineage/temporal/change graph, impact analysis, exception register.
- **Scoring**: dimension scores, three composite methods, materiality weighting, SLOs and error
  budgets, and **lineage-aware trust propagation** over the semiring.
- **Lineage**: ingestion (OpenLineage, dbt, warehouse history, catalogs), SQL-parsed column-level
  derivation, graph store, blast radius.
- **Alerting**: routing, channels, dedup, digests, anatomy-of-a-good-alert composition, per-monitor
  precision reporting.
- **Learning loop**: feedback capture, feature/label store, recalibration, re-ranking, shadow
  evaluation, promotion gates, rollback, self-reporting metrics.

**Exit:** a sub-ledger↔GL reconciliation runs end-to-end with break workflow and a certificate;
trust propagation demonstrably changes remediation ranking; the learning loop shows measured uplift.

---

## Wave 9 — Experience

**Goal:** the product a business owner will actually use.

- Design system on Radix + Tailwind with the six-dimension palette; WCAG 2.2 AA from the first
  component; light/dark; density modes.
- **Estate map** (Sigma.js/WebGL) with overlays and direct-manipulation relationship declaration
  (React Flow canvas).
- Declaration flows: dataset in ≤ 5 min, relationship by drawing, attribute interpretation.
- **Rule studio**: no-code builder, CodeMirror PQL editor with LSP, live preview, backtest, cost.
- **Proposal review queue**, batch approve, decision capture.
- **Incident workspace**: keyboard-first, one-screen triage, batch disposition.
- **Reconciliation workbench**: side-by-side, break grouping, certificate sign-off.
- **Scorecards** with full drill-down to evidence; attestation with e-signature and seal.
- **Conversational assistant**: contextual panel, full workspace, Slack/Teams; tool-constrained,
  identity-bound, grounded, proposal-only mutation, injection-hardened.
- **MCP server**; embeddable widgets; Jinja-rendered PDF/print artefacts.

**Exit:** `NFR-USA-001…008` met in a usability study with ≥ 12 participants per persona.

---

## Wave 10 — Enterprise and GA

**Goal:** a Tier-2 bank can buy it, deploy it on-prem, and pass an audit with it.

- **Streaming validation backend** (DishtaYantra default per DEC-17; Flink pluggable): in-flight
  enforcement, drop/tag/route/dead-letter, windowed monitors, sub-5 ms added p99.
- **Multi-tenancy and security hardening**: tenant isolation tests, RBAC/ABAC, SoD, SSO/SCIM, vault
  integration, CMK/BYOK, residency enforcement, SIEM export, prompt-injection corpus.
- **Packaging**: Helm chart, Kubernetes Operator with CRDs, single-container all-in-one, signed
  offline bundle, Terraform provider, air-gapped install and update.
- **Banking domain pack**: concepts, validators, calendars, message parsers (ISO 20022, SWIFT MT,
  FIX, FpML, XBRL, ISO 8583, NACHA/SEPA), COBOL/EBCDIC reader, reference reconciliations, regulatory
  control catalogue with citations.
- **Contracts**: ODCS import/export, CI/CD gates, data diff.
- **Benchmarks**: DQ-Bench and FinDQ-Bench published; the S1–S9 gates measured; live-shadow harness.
- Compliance artefacts: SOC 2 readiness, model cards, attestation packs, shared-responsibility doc.

**Exit:** all nine superiority gates in [15 §7](15-evaluation-benchmark-methodology.md#7-release-gates)
met or explicitly and publicly missed; air-gapped install verified; first production deployment.

---

## Cross-wave workstreams

Run continuously rather than in a wave:

| Workstream | Cadence |
|---|---|
| Architecture tests (layering, file length, concurrency, no-model-verdict) | Every commit |
| Benchmark suite in CI; > 10% regression blocks release | Every release |
| Documentation kept in step with code (docs build and link-check in CI) | Every commit |
| Security scanning, SBOM, dependency updates, parser fuzzing | Weekly |
| Soak tests and chaos drills (source failure, control-plane outage, poison input) | Per wave |
| DishtaYantra provenance audit — ported files re-checked against upstream | Per wave |

---

<div align="center">
<img src="assets/prama-mark.svg" width="30" alt=""/><br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.<br/>
See <a href="../LICENSE">LICENSE</a> and <a href="../NOTICE">NOTICE</a>. Third-party names and marks are the property of their respective owners.</sub>
</div>
