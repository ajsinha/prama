<img src="../assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

> ***pramā*** (Sanskrit **प्रमा**) — *valid knowledge: a cognition that is both true and arrived at
> by a reliable means*. Its companion ***pramāṇa*** (प्रमाण) is *the instrument by which valid
> knowledge is obtained*. Prama is that instrument for an organisation's data — it does not decide
> what is true, it is how a belief about data becomes **justified**.
>
> **Declare it. Prove it. Trust it.**


---
# 18 — Technology Stack & Reuse from DishtaYantra

**Status:** Recommendation for decision · **Companion to:** [06 — Reference Architecture](06-architecture.md)
**Constraints this must satisfy:** modular, maintainable, cloud **and** on-prem **and** air-gapped
from one codebase ([`NFR-POR-001`](05-requirements-nonfunctional.md#i-portability--openness-nfr-por)),
world-class UI ([`FR-UIX`](04-requirements-functional.md#p-user-interface-fr-uix),
[`NFR-USA`](05-requirements-nonfunctional.md#j-usability--accessibility-nfr-usa)).

---

## As built

The stack is as chosen. Python 3.13 from a standalone CPython under
`~/.local/share/uv/python/` rather than from the OS — a decision the repository
records because an Ubuntu upgrade removed `/usr/bin/python3.12` mid-build and
orphaned the venv. FastAPI, SQLAlchemy 2.0, Jinja2, pyarrow, DuckDB, and nothing
in the console that needs a build step.

Optional extras rather than hard dependencies, each refusing **by name** when
absent rather than falling back to something weaker: `serve`, `postgres`,
`fast`, `audit`, `sso`, `kafka`, `rest`.

**Two departures from §1.** Work distribution uses leases held as a conditional row on the
`lease` table (`prama.db.lease_provider`), on SQLite and PostgreSQL alike, rather than PostgreSQL
advisory locks, and DishtaYantra's ZooKeeper, Redis and S3 lease providers were not ported. The
package layout is four distributions rather than the dozen of §8; see
[architecture/packages.md](../architecture/packages.md).

**Dependency floors have no ceilings, and `uv.lock` pins what they resolved
to.** Every requirement is a `>=`, so the declaration floats to the newest
release — and the lock file records the 62 packages that actually resolved,
across every extra, so a rebuild is reproducible. The gate runs
`uv lock --check`: a lock that has drifted from `pyproject.toml` is worse than
none, because it looks like a reproducible build and is not one.

§3.2's `sync_test_counts.py` — named here as DishtaYantra's discipline worth
porting — now exists, and the gate runs it. Numbers in prose are derived from a
green run rather than typed.

---

## 1. Summary of the recommendation

| Layer | Choice | Reuse from DishtaYantra |
|---|---|---|
| Control-plane language | **Python 3.12+** (FastAPI, async) | ✅ Same stack, proven |
| Hot-path language | **Rust** via PyO3 — format parsers, local IR evaluator, streaming validator | ⚠️ Pattern exists (`core/rust`), code does not |
| Web framework | **FastAPI + uvicorn** | ✅ Adopt wholesale |
| **UI** | **Jinja2 on FastAPI + HTMX + Alpine + Bootstrap 5**, all assets vendored, no build step | ✅ **Same as DishtaYantra** — the Phase-0 divergence to React was reversed; see §4 |
| Local compute | **Apache Arrow + Polars + DuckDB** | ✅ Already the stack |
| Pushdown compute | Generated SQL per dialect; Spark via job submission | ⚠️ Spark submission pattern exists |
| **Streaming validation** | **DishtaYantra as the streaming engine** — not Flink | ✅ **The biggest win. See §5** |
| Connectors | Extend DishtaYantra's `core/pubsub` SPI to a read/profile-oriented SPI | ✅ ~40 transports already written |
| Connector config UI | **Derive form schema from connector code** (AST), curated presentation overlay | ✅ `core/pubsub/connector_schema.py` — port verbatim in spirit |
| Metadata store | **PostgreSQL 16+** (bitemporal), SQLAlchemy 2.0 | ✅ SQLAlchemy + DAO layer reusable |
| Evidence & metrics | **Object storage + Parquet/Iceberg**, queried by DuckDB | ⚠️ Iceberg/Delta/Hudi connectors exist |
| Graph | Postgres + **Apache AGE** initially; Neo4j only if measured need | ❌ New |
| Config | YAML/`.properties`, `${VAR:default}`, git-ignored local overlays, secrets never tracked | ✅ **Adopted** (`core/properties_configurator.py`, `core/config_parsers.py`) as `prama/core/config/properties.py` and `parsers.py`: every file is parsed, and every `${...}` resolved (nested ones included), by DishtaYantra's engine, and `config.properties()` gives its API. Adapted, with reasons in the modules: no singleton and no reload thread (`changed()`/`reload()` instead), an unresolved placeholder is an error rather than left literal, and environment overrides carry the `PRAMA_` prefix |
| AuthN/Z | OIDC/SAML + API keys + RBAC/ABAC | ✅ `core/auth`, `core/db/models.py` reusable |
| HA | Lease-based (Postgres advisory lock / Zookeeper / Redis / S3) | ✅ `core/ha` reusable |
| Observability | Prometheus + OpenTelemetry + structured logs | ✅ `core/metrics`, `core/observability` reusable |
| Audit | Append-only audit log with retention | ✅ `core/audit_log.py` reusable |
| Packaging | **Kubernetes (Helm + Operator)** + single-container all-in-one + offline bundle | ❌ **Divergence** — DY is Docker Compose |
| Work distribution | **Postgres-backed durable leases** (own it; no extra infra) | ⚠️ Different problem shape |

**Headline:** roughly **40–50% of Prama's non-differentiating platform** already exists in
DishtaYantra in a form we own outright. The two places to deliberately *not* reuse are the UI
(Prama's requirements exceed server-rendered Jinja) and the packaging (Prama needs Kubernetes).
The one place where DishtaYantra is *better* than what [06](06-architecture.md) specified is
streaming validation, where it should replace Flink.

---

## 2. What DishtaYantra is, and why it matters here

DishtaYantra (v9.3.0, 3,376 passing tests) is a single-process reactive value-graph compute engine
with: a FastAPI web layer with fully self-hosted assets (renders air-gapped), ~40 pub/sub
transports behind one SPI, exactly-once egress with a WAL, HA via pluggable lease providers,
Arrow/Polars data plane with spill-to-disk, polyglot operators (JVM/C++/Rust/WASM/Julia/Mojo),
market-session windows with calendar-aware watermarks, Prometheus/OTel observability, RBAC + API
keys + OIDC, an audit log, OTA deployment, and a lineage/replay subsystem.

Three things make it unusually relevant to Prama:

1. **The same non-functional envelope.** Air-gapped rendering, self-hosted assets, on-prem-first,
   YAML config with env substitution, secrets never in tracked files. Prama's
   `NFR-POR-001`/`NFR-PRV-007` are DishtaYantra's existing operating conditions, already solved.
2. **The same domain.** Market calendars, holiday tables, session windows, calendar-aware
   watermarks, exactly-once semantics against Kafka and ActiveMQ. Prama's banking pack needs
   exactly these ([12 §7](12-banking-domain-pack.md#7-calendars-conventions-and-normalisation),
   `FR-MON-002`).
3. **The engineering doctrine.** `CLAUDE.md` encodes a failure model — *"artifacts that build,
   validate, and look right while being wrong"* — and three habits: **assert the rendered artefact,
   write the counterfactual, derive never restate**. Prama's entire evidence thesis is that same
   idea applied to data. Adopting the doctrine matters more than adopting any library.

---

## 3. The reuse map

### 3.1 Adopt wholesale (copy-adapt, low risk, high value)

| DishtaYantra asset | Prama use | Requirement satisfied |
|---|---|---|
| `core/properties_configurator.py` + `properties_accessors.py` | Config: YAML/`.properties`, `${VAR:default}`, env/CLI override, `*.local.*` overlays, secrets never tracked | `NFR-SEC-004`, `FR-ADM-006` |
| `core/auth/` (OIDC, providers), `core/db/models.py`, `dao.py`, `trusted_dao.py` | Users, roles, API keys, SSO | `FR-ADM-002/003` |
| `core/db/db_connection_pool*.py` | Per-source connection pooling with configurable limits | `FR-CON-016` |
| `core/metrics/` + `core/observability/otel_export.py` | Self-monitoring, Prometheus, OTel | `NFR-OPS-001`, `FR-EXE-021` |
| `core/audit_log.py`, `audit_retention.py` | Audit trail with retention | `NFR-SEC-011`, `FR-ADM-005` |
| `core/ha/` (Zookeeper / Redis / S3-lease / socket providers) | Control-plane HA, scheduler leader election | `NFR-AVL-001` |
| `core/alerts.py`, alert routing, `docker/alert_rules.yml` | Notification plumbing | `FR-ALR-002` |
| `core/egress/wal.py`, `drainer.py`, `async_publisher.py` | Durable, crash-safe evidence and event emission | `NFR-AVL-010` |
| `core/djson.py` (orjson with stdlib fallback) | One JSON API, fast paths, air-gap-safe fallback | — |
| `config/holidays/`, `docs/design/F1-market-calendar.md` | Market/settlement calendars | `FR-RUL-006`, `FR-MON-002` |
| `web/static/vendor/` discipline (everything self-hosted, incl. fonts) | Air-gapped UI rendering | `NFR-PRV-007` |
| `scripts/sync_test_counts.py` + `.githooks` | Advertised numbers derived from a green suite, enforced | `NFR-TST-001`, and directly the [`NOTICE §6`](../../NOTICE) discipline |

### 3.2 Adopt the *pattern*, rewrite the code

**`core/pubsub/connector_schema.py` is the single most valuable idea to port.**

It derives each connector's configuration form **from the connector's own source** — parsing the
scheme→class mapping out of the factory and the fields out of every `config.get("name", default)`
the connector reads — with a curated overlay that may only add *presentation* (secret? required?
input type? help text?), never invent a field. A test fails when overlay and code disagree.

This is precisely what [`FR-CON-026`](04-requirements-functional.md#a-connectivity--ingestion-fr-con)
(guided, typed, per-source-family forms, no raw connection strings) needs, and it solves the failure
mode that kills every hand-maintained connector-config UI: the form drifts from the code silently,
in the direction of being unable to express what the engine supports. Port the technique; the
Prama connector SPI is read/profile/pushdown-shaped rather than publish/subscribe-shaped, so the
code itself is new.

Also port-by-pattern: `core/pubsub/backpressure.py` (credit-based back-pressure → source load
ceilings, `NFR-PRF-013`), `core/lineage.py` + `replay.py` (lineage capture and replay → evidence
replay, `NFR-CMP-002`), and `core/dag/stateful_nodes.py` window/watermark handling.

### 3.3 Reuse the transports, replace the semantics

DishtaYantra's ~40 `*_datapubsub.py` modules already cover Kafka (both clients), ActiveMQ/STOMP,
Pulsar, NATS JetStream, MQTT, Kinesis, Event Hubs, GCS, Azure Blob, Iceberg, Hudi, Delta Lake,
ClickHouse, Aerospike, Redis, gRPC, LMDB, files, and the `filegrabber://` landing-zone trigger
source with commit-on-drain-by-rename and atomic HA claim.

That last one matters more than it looks: **`file_grabber.py` is 70% of Prama's feed-arrival
subsystem** ([`FR-CON-014`](04-requirements-functional.md#a-connectivity--ingestion-fr-con),
[09 §14](09-connectivity-and-formats.md#14-feed-handling--the-operational-reality)) — landing
detection, atomic claim, duplicate handling, HA-safe processing.

What must be added for Prama: the *read/profile/pushdown* half of the SPI —
`discover()`, `describe()`, `snapshot()`, `pushdown_capabilities()`, `execute_plan()` — plus the
warehouse/RDBMS connectors DishtaYantra does not need (Snowflake, BigQuery, Databricks SQL,
Redshift, Oracle, DB2 z/OS, Teradata…) and the format parsers (COBOL/EBCDIC, SWIFT, FIX, FpML,
XBRL).

### 3.4 Do not reuse

| Asset | Why not |
|---|---|
| The DAG execution model as Prama's *control* model | Prama's controls are declarative assertions compiled to an IR, not a reactive value graph. Different abstraction; forcing one onto the other would corrupt both. |
| Jinja/Bootstrap UI for the main console | §4 |
| LMDB / Aerospike / Redis-clone stores | Solve DishtaYantra's low-latency value-graph problem; Prama's problem is bitemporal metadata + immutable columnar evidence |
| Docker Compose as the deployment model | §6 |
| Single-tenant assumptions throughout | Prama needs tenant as a first-class key from commit one (`NFR-SEC-006`); this is the one thing that must never be retrofitted |

---

## 4. The UI — the divergence, reconsidered and reversed

> **DEC-18 was reversed in September 2026.** Prama's UI is server-rendered Jinja on FastAPI, with
> Bootstrap 5, vendored assets and CSS-custom-property theming — the same stack as DishtaYantra —
> plus two framework-agnostic JavaScript islands where the requirements genuinely need them. The
> original argument and what survives of it are both kept below, because a decision reversed
> without its reasoning is a decision that gets reversed back.

DishtaYantra's UI is server-rendered Jinja + Bootstrap 5 + jQuery + Cytoscape.js, with every asset
vendored locally, CSS-custom-property theming, and light/dark modes. For its purpose — 138 admin,
monitoring, and help pages — that is a *correct* and unusually well-executed choice: it renders
air-gapped, it has no build step, and it is maintainable by one person.

### 4.1 The original objection

Seven of Prama's interface requirements were judged to need a component framework:

| Prama requirement | The objection to Jinja+Bootstrap+jQuery |
|---|---|
| Estate map, 50,000 nodes at 60 fps pan/zoom (`NFR-SCA-011`) | Cytoscape's default renderer is canvas/SVG and degrades past ~5–10k elements |
| PQL editor with autocomplete, inline type errors, cost estimates (`FR-UIX-003`) | This is an IDE surface, not a form |
| Live preview of a rule against real data in ≤ 5 s (`FR-UIX-004`) | Requires optimistic, incremental, cancellable client state |
| Keyboard-first triage with batch disposition (`FR-UIX-006`) | Requires client-side selection/undo state across a virtualised list |
| Streaming chat with inline artefacts (`FR-CHT-001`) | A server round-trip per interaction is unusable |
| WCAG 2.2 AA with a real component contract (`NFR-USA-003`) | Achievable in Jinja, but only by hand-auditing 100+ pages forever |
| p95 ≤ 300 ms navigation (`NFR-PRF-001`) | Full-page reloads cannot hold this over a WAN |

### 4.2 What survives, and what does not

**Two of the seven rested on a false premise.** CodeMirror 6 and Sigma.js are framework-agnostic
JavaScript libraries: neither needs React, and both mount into a `<div>` on a server-rendered page.
The two hardest requirements — the IDE surface and the 50,000-node WebGL map — are therefore
answered by *choosing the right library*, which was always the real requirement, rather than by
choosing a framework to host it. Attributing them to React was a category error.

**One correction, from measurement.** The objection above predicted that a canvas renderer would
"degrade past ~5–10k elements". The built map stops drawing below 4,000 nodes
([10 §3](10-ux-and-chat-interface.md#3-the-estate-map--the-landing-surface) has the numbers): a
cliff an order of magnitude *below* the prediction. The prediction was directionally right, but it
mislocated the cost: what binds is not the renderer at all but an all-pairs layout pass run before
the renderer is constructed, a cost that would be paid identically under React.

**Three are answered by HTMX.** Live preview, sub-300 ms navigation and streaming chat are
partial-page updates over a persistent connection, which is exactly what HTMX and server-sent
events do. A full-page reload was never the only alternative to a single-page app.

**Two are real costs, and are accepted.** Keyboard-first batch triage with undo across a
virtualised list, and rich client-side selection state, are genuinely more code without a component
framework — a few hundred lines of vanilla JavaScript per surface rather than a library call. The
accessibility contract is likewise hand-held rather than inherited from Radix, and the answer is
`axe-core` in CI over every rendered page, which is a weaker guarantee than a component contract and
a stronger one than an annual audit.

### 4.3 Why the reversal is right anyway

The objection was written as though the only cost of React were engineering hours. It is not.

- **One language.** The rest of Prama is Python. A TypeScript app is a second toolchain, a second
  dependency tree, a second supply chain to vendor for an air-gapped install, and a second set of
  people. For a product whose differentiator is statistical and semantic rather than visual, that
  is a large permanent tax on the wrong axis.
- **No build step is an air-gap feature.** DishtaYantra renders in a restricted-egress deployment
  because there is nothing to build and nothing to fetch. Prama's buyers are the same buyers.
- **It is proven here.** The same author maintains a well-executed instance of this stack, and
  "maintainable by one person" is not a limitation to design around — it is the operating reality.
- **The estimate that justified the divergence was the Experience team growing from three to nine
  engineers.** That is the single largest line item in the plan, spent on a framework rather than
  on the product.

**Recommended front-end:**

| Concern | Choice | Why |
|---|---|---|
| Rendering | **Jinja2 on FastAPI**, server-rendered | One language, no build step, air-gapped by construction |
| Interactivity | **HTMX** for partial updates, **Alpine.js** for local component state | Partial-page updates and small client state without a framework |
| Components | **Bootstrap 5** + CSS custom properties, light/dark, density modes | Proven in DishtaYantra; the six-dimension palette lives in tokens |
| Editor | **CodeMirror 6**, vanilla, speaking to the PQL language server | Framework-agnostic; the same LSP serves IDEs |
| Estate map | **Sigma.js v3 (WebGL)** for scale; **Cytoscape.js** for the small editable canvas | Two different jobs, as before — and neither needs React |
| Charts | **ECharts**, themed to the six-dimension palette | Vendored, no build step, adequate at this complexity |
| Streaming | **Server-sent events** for chat and live preview | Simpler than websockets and enough for one-directional streaming |
| Tables | Server-rendered with HTMX paging; virtualised only where 10⁵ rows are real | Most tables are not that big, and the ones that are get the extra code |
| Build/serve | No build. **All assets vendored**, no CDN, no external fonts | Preserves the air-gap property outright rather than by discipline |
| a11y | `axe-core` in CI over every rendered page | Weaker than a component contract, stronger than an audit |

**Keep Jinja for PDF and print artefacts too** — server-side, JS-free rendering was already the
right answer there, and now it is the same renderer as everything else.

**Cost honesty, revised.** This removes the largest single engineering line item in the plan. What
it costs instead is a few hundred lines of hand-written JavaScript on the two most interactive
surfaces, and an accessibility guarantee held by CI rather than by a component library. Both are
real; neither is nine engineers.

---

## 5. The best idea: DishtaYantra as Prama's streaming validation engine

[06 §3.4](06-architecture.md#34-execution-plane) specifies **Apache Flink** for streaming
assertions and in-flight enforcement. On review, that is the wrong call.

| Criterion | Flink | DishtaYantra |
|---|---|---|
| Ownership | Third party; JVM operational burden on every on-prem install | **Owned outright** |
| Air-gap install | JobManager/TaskManager cluster, JVM tuning, checkpoint storage | Single Python process |
| Exactly-once | Yes | **Yes — verified end-to-end against live Kafka (3 partitions) and non-rewindable ActiveMQ** |
| Back-pressure | Yes | Credit-based, byte-bounded queues |
| **Market-session windows, calendar-aware watermarks** | Build it yourself | **Already implemented** — and it is precisely what the banking pack needs |
| Retraction-aware aggregates | Build it yourself | Already implemented |
| Connectors | Flink connectors | ~40, already written, same SPI as batch |
| HA | ZK/K8s | Pluggable lease providers, already written |
| Throughput ceiling | Higher | Lower — must be measured against `NFR-SCA-005` (250k msg/s/node) |
| Team cost | New JVM competency + ops | Existing competency |

**Recommendation:** make **DishtaYantra the default streaming validation backend**, with the PQL IR
compiled to a DishtaYantra DAG (a validation operator per assertion, a routing operator per
`ON FAIL` action). Keep the Flink backend as a *pluggable alternative* for customers who already run
Flink at scale or who exceed the measured throughput ceiling — the engine-neutral IR
([`AD-01`](06-architecture.md#8-key-architectural-decisions)) is precisely what makes that
substitution cheap.

**The one thing to verify first:** benchmark DishtaYantra against `NFR-SCA-005` (250,000 msg/s per
node at ≤ 5 ms added p99) on a realistic assertion mix. If it lands materially short, the decision
inverts to "DishtaYantra for the on-prem/air-gap tier, Flink for the high-volume tier" — which is
still better than Flink-only, because it removes the JVM from the deployments where it hurts most.

**Measured, 2026-09.** The benchmark decomposes, and half of it is now answered.
`NFR-SCA-005`'s "≤ 5 ms *added*" is Prama's own evaluation cost, and that is measured rather than
estimated: a realistic five-control mix (null, sign, codelist, range, compound expression) evaluated
against the IR costs **4.82 µs per message single-threaded** — a thousandfold inside the latency
budget — at **208,000 msg/s on one core**, so the 250,000 target needs 1.2 cores of evaluation and
parallelises across partitions trivially.

The finding that matters: **assertion evaluation is not the constraint, so DEC-17 does not turn on
it.** The decision rests on the transport — its partitioning, its backpressure, its operational
footprint — and should be made on those grounds. In particular the argument for DishtaYantra was
never that it evaluates faster; it is that it removes a JVM from air-gapped and on-premise
deployments, and that argument is unaffected by throughput.

Still to measure: DishtaYantra's own transport throughput under the same mix, which needs a
multi-node harness rather than a process. Recorded as open in [17](17-risks-and-open-questions.md).

One optimisation came out of the measurement. The first implementation allocated a verdict object
per message per assertion, and that bookkeeping cost 4.7 µs of the original 7.07 µs — the object
describing the work outweighing the work. Removing it on the windowed path took the mix from
141,000 to 208,000 msg/s. The per-message enforcement path still returns a verdict, because there
the caller needs the answer and the allocation is the point.

This should be a Phase-0 spike, and it is added to [17](17-risks-and-open-questions.md) as
**DEC-17** below.

---

## 6. Deployment and packaging

DishtaYantra ships a `DOCKERFILE` + `docker_compose.yml` + Prometheus/Grafana config. That is right
for a single-process engine and wrong for Prama, which must run a control plane plus a fleet of
stateless execution workers across five topologies ([06 §6](06-architecture.md#6-deployment-topologies)).

| Artefact | Purpose |
|---|---|
| **Helm chart** (primary) | Control plane + workers + Postgres + object storage bindings; the on-prem and cloud default |
| **Kubernetes Operator** (Phase 3) | CRDs for Connection/Domain/Dataset/ControlSuite (`FR-EXT-007`), reconciliation, upgrades |
| **Single-container all-in-one** | Evaluation, CI, demo, and the smallest air-gapped installs. Postgres + DuckDB + control plane + worker in one image |
| **Offline bundle** | Signed tar of images + Helm chart + packs + model weights for air-gapped install/update (`FR-ADM-010`) |
| **Terraform provider** | IaC management of Prama objects (`FR-EXT-007`) |
| **Managed SaaS** | Same Helm chart, Prama-operated |

**Build Kubernetes in from Phase 0.** Retrofitting k8s onto a Compose-shaped process (shared local
filesystem, in-process scheduling, single-node assumptions) is one of the more expensive rewrites in
this class of software, and it is exactly the kind of thing that looks fine until the first Tier-1
bank asks for it.

---

## 7. Language boundaries

**Python 3.12+ for the control plane.** Correct because 95% of Prama's work is orchestration, SQL
generation, and API serving — none of it CPU-bound — and because it puts Prama in the same
ecosystem as its users' data teams (SDK, embedding in Airflow/Spark/dbt, `FR-EXT-003`).

**Rust for four hot paths**, exposed through PyO3 and returning Arrow:

1. **Format parsers** — fixed-width, COBOL/EBCDIC with COMP-3 and `OCCURS DEPENDING ON`, SWIFT MT,
   FIX, ISO 8583. These are byte-level, GB/s-class, and are a memory-safety surface that will be fed
   hostile input; `NFR-SEC` requires fuzzing them, and Rust makes the fuzzing findings boring.
2. **The local IR evaluator** over Arrow record batches, for the Arrow/DuckDB backend and for
   sources with no pushdown.
3. **The streaming validator** operator, if the §5 benchmark demands it.
4. **Sketches** — HLL, t-digest, count-min, MinHash/LSH at streaming rates (`FR-MON-013`).

DishtaYantra already has a Rust bridge (`core/rust`, `rust_config.json`, `rust_arrow.py`) and a C++
one, so the calling convention and build integration are solved problems here — a real accelerator.

**Nothing else.** No JVM in the default install (that is half the point of §5); C++/WASM/Julia/Mojo
bridges are DishtaYantra features Prama does not need.

---

## 8. Modularity contract

Prama's requirement is that a connector, an assertion type, a monitor, a notifier, a scoring
function, or a domain pack can be added **without a core change** (`NFR-MNT-002`, `FR-EXT-005`).

This section originally proposed a dozen distributions (`prama-core`, one per engine, per
connector family, per format, `prama-intel`, `prama-server`, SDKs in three languages). What was
built is four: the server, a standard-library **kernel** that plays the proposed `prama-core`'s
role (no I/O, so the same verdict can be judged anywhere), the Python SDK, and the agent daemon.
Connectors, backends and packs are modules inside the server, registered behind ABCs, rather than
separate distributions. The layout, the import rules and the tests that enforce them are in
[architecture/packages.md](../architecture/packages.md).

The rules that survive from the proposal: the kernel imports nothing above it and performs no
I/O, which is what makes the IR conformance suite possible; plugins are classes behind an ABC with
a declared capability manifest; and every plugin ships its own conformance tests, so one that
fails them is not "supported" ([09 §17](09-connectivity-and-formats.md#17-connector-delivery-plan)).

---

## 9. Sharing code between the two projects

Both repositories are owned by Ashutosh Sinha, which removes the licensing question but not the
engineering one.

| Option | Verdict |
|---|---|
| Git submodule / monorepo | ❌ Couples release cycles of two products with very different cadences |
| Extract a shared `yantra-commons` package now | ⚠️ Right eventually; premature at two consumers. Extraction with one real consumer produces an API shaped like that consumer. |
| **Copy-adapt with a provenance header** | ✅ **Recommended for Phase 0–1.** Each ported file carries `Ported from DishtaYantra <path> @ <version>` so drift is visible and a future extraction is mechanical. |
| Extract at the third consumer | ✅ The trigger condition. `maya` or a future project makes it real. |

Candidates for eventual extraction, in order of confidence: the config system, the auth/DAO layer,
the metrics/OTel layer, the HA lease providers, the audit log, and `djson`.

---

## 10. Adopt the doctrine, not just the code

The most valuable thing in `../dishtayantra` is not a library. It is
[`CLAUDE.md`](../../../dishtayantra/CLAUDE.md)'s statement of the failure mode this class of system
keeps producing — *"artifacts that build, validate, and look right while being wrong"* — and the
three habits that follow. All three are load-bearing for Prama specifically:

1. **Assert the rendered artefact, not the intent.** For Prama this means: assert the *executed
   verdict on real data*, not that the compiler emitted plausible SQL. The IR conformance suite
   ([07 §7](07-rule-language-spec.md#7-the-intermediate-representation)) is this habit as a release
   gate.
2. **Write the counterfactual.** A control that cannot fail is worth nothing — which is exactly why
   [15 §3.5](15-evaluation-benchmark-methodology.md#35-coverage-s5) defines a "meaningful" control
   as one with a non-degenerate failure mode, and why induction discards trivially-true candidates
   ([08 §6.2](08-ai-ml-capabilities.md#62-pipeline)).
3. **Derive, never restate.** This is `connector_schema.py`, and it is also Prama's whole thesis:
   scores derive from evidence, controls derive from declarations, forms derive from code. Anything
   restated in a second place will drift, silently, in the flattering direction.

Two concrete mechanisms worth copying immediately: **advertised numbers enforced by a hook against
a green suite** (`scripts/sync_test_counts.py`), which is the practical enforcement of
[`NOTICE §6`](../../NOTICE); and **`config/application.local.yaml` git-ignored with an empty shipped
secret so a fresh clone refuses to boot**, which is a better default than any amount of
documentation.

---

## 11. New open decisions

| ID | Decision | Options | Lean | Needed by |
|---|---|---|---|---|
| DEC-17 | **Streaming backend** | DishtaYantra · Flink · both | **DishtaYantra default, Flink pluggable** — subject to the `NFR-SCA-005` benchmark | Phase 0 spike, Phase 2 commit |
| DEC-18 | **Front-end framework** | React+TS · Jinja+HTMX (DY-style) · SvelteKit | **Jinja + HTMX + Alpine, Bootstrap 5, vendored** — reversed Sep 2026. Two of the seven objections to it rested on a false premise (CodeMirror and Sigma need no framework), three are answered by HTMX, and two are accepted costs. One language and no build step outweigh them — see §4 | Phase 0, reversed Wave 9 |
| DEC-19 | **Estate-map renderer** | Sigma.js (WebGL) · Cytoscape · deck.gl · Cosmograph | **Sigma.js v3** for scale + **React Flow** for the editable relationship canvas | Phase 1 |
| DEC-20 | **Rust scope** | Parsers only · parsers + evaluator · parsers + evaluator + streaming | **Parsers first**, extend on measurement | Phase 1 |
| DEC-21 | **Shared code with DishtaYantra** | Submodule · shared package now · copy-adapt with provenance | **Copy-adapt**, extract at the third consumer | Phase 0 |
| DEC-22 | **Work queue** | Postgres leases · Celery/Redis · Temporal | **Postgres advisory-lock leases** — no extra infra, matches [`AD-07`](06-architecture.md#8-key-architectural-decisions) | Phase 0 |
| DEC-23 | **Graph store** | Postgres + AGE · Neo4j · Neptune | **AGE** until measured need; the lineage graph is read-heavy and bounded | Phase 1 |

---

## 12. What this changes in the existing corpus

| Document | Change |
|---|---|
| [06 §3.4](06-architecture.md#34-execution-plane) | Flink is no longer the default streaming backend; DishtaYantra is, with Flink pluggable (DEC-17) |
| [06 §5](06-architecture.md#5-storage-choices) | Confirmed: Postgres + object storage + DuckDB; AGE for graph |
| [16 §5](16-roadmap-and-delivery-plan.md#5-build--buy--integrate) | "Connectors: build core 45" is now partly *port* — a material schedule saving |
| [16 §2](16-roadmap-and-delivery-plan.md#2-phases) | Phase 0 gains a DishtaYantra streaming benchmark spike and the k8s-from-day-one commitment |
| [17](17-risks-and-open-questions.md) | DEC-17…DEC-23 added; `RSK-13` (connector treadmill) exposure reduced by the ported transport layer |

---

<div align="center">
<img src="../assets/prama-mark.svg" width="30" alt=""/><br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.<br/>
See <a href="../../LICENSE">LICENSE</a> and <a href="../../NOTICE">NOTICE</a>. Third-party names and marks are the property of their respective owners.</sub>
</div>
