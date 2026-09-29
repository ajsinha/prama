<!-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE. -->

> Design note behind [23 — Intelligence and lineage roadmap](../23-intelligence-and-lineage-roadmap.md). Written 2026-09-27. Where this note and doc 23 disagree, doc 23's reconciliation wins.

# Design — Code-to-Lineage and Persistent Prama Agents

Status: proposal. Builds on `prama.lineage` (graph/sql/scan), `prama.propose`, `prama.derive.relationships`,
`prama.induce`, `prama.agent`, `prama.assistant`, `prama.llm`, `prama.security.egress`, `prama.core.concurrency`.
Nothing here needs a migration: new tables are appended to `schema/sqlite.sql` and `schema/postgres.sql`
byte-identically and applied by `prama db init`.

Governing invariants, restated because both features touch them:

1. **CON-007.** An LLM may author an edge or a proposal. It never marks an edge confirmed, never accepts a
   proposal, never produces a verdict. Confirmation is a human act; verdicts come from the compiled plan.
2. **Inferred is never confirmed.** Same contract as `RelationshipStatus.PROPOSED → CONFIRMED`: a control
   derived from an unconfirmed edge is itself only a proposal and cannot activate.
3. **Coverage is confessed.** Every analysis reports what it could not read (`lineage.sql.Gap`,
   `ScanResult.units_unread`) — a code-lineage graph that looks complete when it is 40% parsed is the
   "looks right while wrong" failure the doctrine exists to prevent.
4. **No uploaded code is executed. Ever.** Not `setup.py`, not `dbt compile`, not a Jinja render with
   user macros, not an import of a Python module to "see what it does".

---

## Part A — Code-to-lineage

### A1. Ingestion (`(planned) prama.codeintake`)

Two sources behind one ABC, `CodeSource` (entry point group `(planned) prama.code_sources`), each yielding a
`Snapshot` = content-addressed tree of files (path → sha256, size) plus an origin descriptor.

**ZipUpload.** Streamed to a quarantine directory, never trusted by name:

- Caps (config `codeintake.limits`): compressed ≤ 200 MB, uncompressed ≤ 1 GB, ≤ 50 000 entries,
  single file ≤ 20 MB, compression ratio per entry ≤ 100 (zip bomb), nesting depth ≤ 32. Totals are
  checked from the *central directory before extraction* and re-checked while streaming (headers lie).
- Path safety: reject absolute paths, drive letters, `..` segments after normalisation, NUL bytes,
  and any entry whose resolved path is not under the extraction root (zip-slip). Symlink entries
  (external attr `S_IFLNK`) are recorded as metadata and **never materialised**. Device files, FIFOs and
  setuid bits dropped. Nested archives (`.zip/.jar/.tar.gz`) are inventoried, not expanded, in v1.
- Encoding: decode as UTF-8, fall back to cp1252/EBCDIC (cp037) for COBOL/JCL by heuristic; binary
  files (NUL density) are inventoried and skipped.

**GitRepository.** URL + ref (branch/tag/sha) + `SecretReference` resolved through `prama.secrets`
(token or SSH key; never stored in `setting`, never logged). Clone is `git` as a subprocess with a hardened
environment: `GIT_TERMINAL_PROMPT=0`, `core.hooksPath=/dev/null`, `protocol.file.allow=never`,
`protocol.ext.allow=never`, `--no-recurse-submodules`, `--filter=blob:limit=20m`, `--depth` configurable,
`transfer.fsckObjects=true`, and `core.symlinks=false`. Only `https`/`ssh` schemes; the host is checked
against an allow-list and resolved IP against private ranges (SSRF). Git fetch is a registered egress
point (`security.egress.point("code.git.fetch")`) so `tests/architecture/test_egress.py` covers it.
After clone the same caps as ZipUpload apply to the working tree.

**Sandbox.** Ingestion and parsing run in a separate worker process (supervised by
`TaskSupervisor`, restart policy `never`) with: rlimits (CPU seconds, address space, open files, no
core dumps), a scratch directory as the only writable path, no network after clone (seccomp/netns where
available, otherwise documented as a residual), and a wall-clock budget per snapshot. Parsers are pure
functions over bytes; the regex engines are guarded against catastrophic backtracking by per-file
timeouts. The quarantine tree is deleted when the analysis run completes; only file hashes and the
spans cited by edges are retained (see A6 — spans are stored as excerpts ≤ 2 KB, which is what a
reviewer needs, not the repository).

**Sensitivity.** Source code is classified `INTERNAL` by default and elevated to `CONFIDENTIAL` by
tenant setting or by secret-scanning (connection strings, keys found in the tree are *redacted in the
retained excerpts* and reported as a finding). That classification is what `ModelProvider.permit` checks
before any code leaves for a hosted model.

### A2. Inventory and detection

`Inventory` walks the snapshot and classifies each file by a deterministic `Detector` chain (extension,
filename, shebang, content signatures), each detector a plugin (`(planned) prama.code_detectors`):

| Kind | Signals | Deterministic extractor |
|---|---|---|
| SQL / DDL / views | `.sql`, `CREATE VIEW`, `INSERT … SELECT`, `MERGE` | `SqlLineage` (existing) |
| Stored procs | T-SQL `CREATE PROC`, PL/SQL `PACKAGE BODY`, DB2 `LANGUAGE SQL` | `ProceduralSqlScanner` (existing) |
| dbt | `dbt_project.yml`, `models/**/*.sql`, `ref()`/`source()` | new `DbtScanner`: parses `ref/source` by regex **without rendering Jinja**; resolves names via `schema.yml`/`sources.yml`; bodies with `{% %}` control flow beyond ref/source/config become Gaps; if a `target/manifest.json` is present it is read as data (never generated) and is preferred |
| Spark SQL / PySpark | `from pyspark`, `spark.sql(`, `.write.saveAsTable` | new `PythonDataflowScanner`: Python `ast` (parse only, never exec); string-literal SQL passed to `SqlLineage`; DataFrame chains `read.table→select/withColumn/join→write` modelled symbolically; f-strings and variables resolved by constant propagation within a function, otherwise a Gap |
| pandas | `import pandas`, `read_sql`, `to_sql`, `merge` | same AST scanner, pandas vocabulary |
| Airflow | `from airflow`, `DAG(`, operators | `AirflowScanner`: task graph and operator SQL (`sql=` literals, `.sql` template files) → job-level edges and `produced_by = dag.task` |
| Informatica / SSIS (DataStage and Talend: out of scope) | `.xml` with `POWERMART`, `.dtsx`, `.dsx`, `.item` | `XmlMappingScanner` (existing, configurable `MappingShape`); add a Talend shape |
| COBOL / JCL | — | **Out of scope** (docs/23, "Lineage scope"): inventoried and reported as not read, never analysed. |
| Shell | — | **Not parsed** (docs/23, "Lineage scope"): inventoried; the checked model pass may propose edges a person confirms. |

Detection output is shown to the user before analysis (language mix, frameworks, file counts, skipped
binaries) — the repository's inventory is itself a finding.

**Name resolution.** Extracted columns are raw names (`stg.orders.amt`). A `Resolver` maps them to
`sem_dataset`/`sem_binding` using the tenant's catalogue (the same `cat.json` the LSP uses), config files
in the repo (`profiles.yml`, connection properties — parsed, secrets redacted), and alias tables. An
unresolved name is kept as an *external node* and counted; it is not guessed.

### A3. Layered extraction

```
L0 deterministic parsers ──► edges (confidence 1.0 for exact, 0.9 for alias-resolved) + gaps
L1 schema-assisted re-pass ─► ambiguous columns re-resolved with catalogue schemas (gap closed or kept)
L2 LLM extraction ─────────► only for units with residual gaps; edges tagged origin=llm
L3 cross-check ────────────► every L2 edge validated deterministically (below); failures discarded & logged
```

L2 is a `CodeLineageInducer` modelled on `induce.documents.DocumentInducer`: prompt = the unit's code
span (fenced with `assistant.safety.fence(provenance=path@sha)`, since code is attacker-writable text —
comments saying "ignore previous instructions" are exactly as dangerous as in a table description), the
known schema of referenced tables, and the L0 gaps for that unit. Output is constrained by a `Grammar`
(JSON schema of `{source, target, transform, span:[start_line,end_line], quote}`), temperature 0, seed
fixed; `Request.fingerprint` is stored so the question is reproducible.

**L3 is what makes L2 admissible.** An LLM edge is kept only if: (a) its `quote` occurs verbatim in the
file at the cited span (same rule as `Citation` — unfalsifiable edges are dropped); (b) source and target
columns exist in the catalogue or in L0-extracted DDL, or are explicitly marked external; (c) the target
dataset is actually written in that span per L0's write detection where L0 found one; (d) it does not
contradict a confirmed edge. Confidence = model self-report is **ignored**; confidence is computed:
`0.5 base + 0.15 quote exact + 0.15 both endpoints catalogued + 0.1 corroborated by another unit/L0
dataset edge`, capped at 0.85 so an LLM edge never outranks a parsed one. The formula is a versioned
`EdgeScorer` plugin, and the weights are recorded on each edge.

Every edge — L0 or L2 — carries `EdgeProvenance`: `method` (`parser:<scanner>@<version>` |
`llm:<provider>/<model>` + request fingerprint), `file`, `blob_sha`, `line_start/line_end`, `excerpt`,
`confidence`, `analysis_run_id`. `lineage.graph.Edge` gains an optional `provenance` field (frozen,
default `None`), so `LineageGraph`, `blast_radius` and `merge` are reused unchanged.

### A4. Human confirmation

Edge status: `inferred → confirmed | rejected | retired`, mirroring `RelationshipStatus`. Rules:

- L0 exact edges may be **bulk-confirmed** by a human per file or per unit ("confirm all 42 parsed
  edges in `load_positions.sql`"); L2 edges are confirmed individually or per unit only after being
  opened. No edge is auto-confirmed, including parser edges — confirmation is cheap, not skipped.
- A rejection is remembered keyed on `(source, target, transform, blob_sha)` like `ctl_rejection`, so
  re-analysis of the same code does not re-ask; a changed blob re-asks *saying what changed*.
- Impact analysis (`blast_radius`) is offered in two modes, confirmed-only (default) and
  confirmed+inferred (labelled), so the console never presents an inferred path as fact.
- Scope: `lineage:read`, `lineage:confirm` added to `security.scopes.SCOPES` (and to roles, per
  `test_scopes.py`).

### A5. Lineage → control proposals

A deterministic `LineageControlGenerator` (in `prama.derive`, next to `relationships.py`) reads the
graph and emits `Proposal`s through `propose.adapt`, provenance `Origin.INDUCTION` for anything touching
an LLM edge and a new `Origin.LINEAGE` (authority between MINING and IMPORT) for parser-only paths,
with `source_ref = analysis_run_id/edge_ids`. It emits nothing from rejected edges; from inferred edges
it emits proposals that are `deferred_because="edge unconfirmed"` until the edge is confirmed —
the same gate as relationship-derived controls.

| Pattern in graph | Proposal |
|---|---|
| IDENTITY/RENAME hop `A.x → B.x`, full-row copy job | **Reconciliation**: `ComparisonSpec` between A and B on the inferred key, row count + sum of numeric measures, tolerance 0 |
| AGGREGATED hop `sum(A.amt) group by k → B.total` | **Aggregate reconciliation**: `SUM(A.amt) BY k` equals `B.total` within declared tolerance |
| FILTER on hop | Population control: `count(B) = count(A where <predicate>)` — predicate copied from the excerpt, only if L0 parsed it. *Built as:* the copy's reconciliation carries the predicate to the source side (`RECONCILE B AGAINST A WHERE <predicate>`), when the filter edge holds a condition over one table |
| JOIN_KEY inner join | **Completeness across join**: orphan-rate of A.k not in C.k (rows silently dropped), and uniqueness of C.k (fan-out). *Built:* the orphan half, as `lineage_join` (`CHECK A.k REFERENCES C.k`), for inner and left joins read by the SQL reader. *Built:* the fan-out half too, as `lineage_join_unique` (`CHECK C HAS UNIQUE KEY (…)`). Its key is every column one statement joins C on, so a composite key is checked as one. |
| RENAME with `CAST/CONVERT/TO_DATE` | **Type/format**: target column conforms to the cast target type; source values parseable (backtest shows would-be failures) |
| DERIVED `CASE`/`COALESCE` | Domain control on target: value set ⊆ CASE branch literals; not-null if COALESCE default is a literal |
| Source feeding many targets (high blast radius) | Raise criticality in `utility.Context` for existing proposals on that source |

Each proposal is then backtested exactly as every other proposal (`Backtest`) — the executed verdict on
real data, not the SQL's plausibility. PQL is produced by templates in the generator, never by the model.

### A6. Incremental re-analysis

Snapshots are content-addressed; units are keyed `(path, blob_sha, scanner_version)`. On a new commit
(webhook to `POST /api/v1/code/sources/{id}/refresh` with HMAC signature, or poll on a schedule):
`git diff --name-status old..new` → re-parse only changed/added units and units whose *dependencies*
changed (dbt `ref` graph, included `.sql` templates, copybooks); deleted units retire their edges.
Edge identity is `hash(source, target, transform, produced_by)` independent of line numbers, so a
moved-but-unchanged edge keeps its confirmation; a changed excerpt at the same identity flips a
confirmed edge to `inferred(re-review)` with a diff shown. L2 is re-asked only for units whose blob
changed (cache by `Request.fingerprint`). Scanner version bump invalidates that scanner's units.

### A7. Storage (append to both schema files; only VARCHAR(n)/TEXT/INTEGER/REAL)

```sql
CREATE TABLE IF NOT EXISTS code_source (
    id              VARCHAR(26)   NOT NULL PRIMARY KEY,
    tenant_id       VARCHAR(26)   NOT NULL REFERENCES tenant (id) ON DELETE CASCADE,
    name            VARCHAR(128)  NOT NULL,
    kind            VARCHAR(16)   NOT NULL,
    url             VARCHAR(1024),
    ref             VARCHAR(255),
    secret_ref      VARCHAR(255),          -- a SecretReference, never the secret
    sensitivity     VARCHAR(16)   NOT NULL DEFAULT 'internal',
    auto_refresh    INTEGER       NOT NULL DEFAULT 0,
    created_at      VARCHAR(32)   NOT NULL,
    created_by      VARCHAR(26),
    CONSTRAINT uq_code_source_name UNIQUE (tenant_id, name),
    CONSTRAINT ck_code_source_kind CHECK (kind IN ('zip', 'git')),
    CONSTRAINT ck_code_source_auto CHECK (auto_refresh IN (0, 1))
);
CREATE TABLE IF NOT EXISTS code_analysis_run (
    id              VARCHAR(26)   NOT NULL PRIMARY KEY,
    source_id       VARCHAR(26)   NOT NULL REFERENCES code_source (id) ON DELETE CASCADE,
    commit_sha      VARCHAR(64),
    snapshot_hash   VARCHAR(64)   NOT NULL,
    base_run_id     VARCHAR(26),           -- incremental parent
    status          VARCHAR(16)   NOT NULL,
    started_at      VARCHAR(32)   NOT NULL,
    finished_at     VARCHAR(32),
    inventory_json  TEXT          NOT NULL DEFAULT '{}',
    coverage_json   TEXT          NOT NULL DEFAULT '{}',   -- units found/unread, gaps by kind
    llm_calls       INTEGER       NOT NULL DEFAULT 0,
    error           TEXT,
    CONSTRAINT ck_code_run_status CHECK (status IN ('queued','running','succeeded','partial','failed','cancelled'))
);
CREATE INDEX IF NOT EXISTS ix_code_run_source ON code_analysis_run (source_id, started_at);
CREATE TABLE IF NOT EXISTS code_unit (
    id              VARCHAR(26)   NOT NULL PRIMARY KEY,
    run_id          VARCHAR(26)   NOT NULL REFERENCES code_analysis_run (id) ON DELETE CASCADE,
    path            VARCHAR(1024) NOT NULL,
    blob_sha        VARCHAR(64)   NOT NULL,
    kind            VARCHAR(32)   NOT NULL,
    scanner         VARCHAR(64)   NOT NULL,
    scanner_version VARCHAR(32)   NOT NULL,
    statements      INTEGER       NOT NULL DEFAULT 0,
    gaps_json       TEXT          NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS ix_code_unit_blob ON code_unit (blob_sha, scanner, scanner_version);
CREATE TABLE IF NOT EXISTS lin_edge (
    id              VARCHAR(26)   NOT NULL PRIMARY KEY,
    tenant_id       VARCHAR(26)   NOT NULL REFERENCES tenant (id) ON DELETE CASCADE,
    identity        VARCHAR(64)   NOT NULL,
    source_column   VARCHAR(512)  NOT NULL,
    target_column   VARCHAR(512)  NOT NULL,
    transform       VARCHAR(16)   NOT NULL,
    produced_by     VARCHAR(512)  NOT NULL DEFAULT '',
    status          VARCHAR(16)   NOT NULL DEFAULT 'inferred',
    method          VARCHAR(128)  NOT NULL,
    confidence      REAL          NOT NULL,
    unit_id         VARCHAR(26)   REFERENCES code_unit (id) ON DELETE SET NULL,
    line_start      INTEGER,
    line_end        INTEGER,
    excerpt         TEXT          NOT NULL DEFAULT '',
    llm_fingerprint VARCHAR(64),
    scoring_json    TEXT          NOT NULL DEFAULT '{}',
    decided_by      VARCHAR(26),
    decided_at      VARCHAR(32),
    decision_note   TEXT,
    first_seen_run  VARCHAR(26)   NOT NULL,
    last_seen_run   VARCHAR(26)   NOT NULL,
    CONSTRAINT uq_lin_edge_identity UNIQUE (tenant_id, identity),
    CONSTRAINT ck_lin_edge_status CHECK (status IN ('inferred','confirmed','rejected','retired')),
    CONSTRAINT ck_lin_edge_transform CHECK (transform IN ('identity','rename','derived','aggregated','filter','join_key')),
    CONSTRAINT ck_lin_edge_conf CHECK (confidence >= 0 AND confidence <= 1)
);
CREATE INDEX IF NOT EXISTS ix_lin_edge_target ON lin_edge (tenant_id, target_column);
```

Current proposal persistence (`ctl_control_version`, `ctl_rejection`) is reused; the proposal's
`provenance_json` carries edge ids. A test asserts `ck_lin_edge_transform` equals `Transform` members
(the same pattern as the RejectionReason check). ORM: `CodeSourceDao`, `CodeAnalysisDao`, `LineageEdgeDao`
in `prama/db`.

### A8. Console pages (Jinja, `web/routes/code_routes.py`, `lineage_routes.py`)

1. **Code sources** — list; "Upload ZIP" (streamed, progress, caps shown up front) and "Connect repository"
   (URL, ref, secret picker from the secrets layer, test-connection = `ls-remote` only).
2. **Source detail / runs** — inventory (language/framework mix), per-run coverage bar ("parsed 812/900
   statements; 63 units with gaps; 41 LLM-assisted edges, 9 discarded by cross-check"), diff vs base run.
3. **Lineage review** — graph (reusing the estate-map renderer) with inferred edges dashed and coloured by
   method; side panel: excerpt with highlighted span, file@sha link (git web URL if known), method,
   confidence and its scoring breakdown, "Confirm / Reject(reason)" buttons; bulk confirm per unit for
   parser edges; filter "LLM edges only", "unconfirmed on critical datasets first".
4. **Gaps** — every unparsed construct, grouped by kind, so a scanner improvement is prioritised by count.
5. **Proposals** — existing proposal queue filtered by `origin in (lineage, induction) & source=code`,
   each linking back to the edges that justify it.

---

## Part B — Persistent Prama agents

### B1. Two kinds of agent, one identity model

Today's `prama.agent` is an **execution agent**: zone-bound, outbound-only, runs compiled plans, signs
evidence. That stays exactly as is. A **persistent AI agent** ("steward agent") is a new, separate
runtime (`(planned) prama.steward`) that shares the identity and transport discipline but never executes controls
and never produces evidence records. Keeping them separate is deliberate: an execution agent's verdict
must equal the control plane's, and nothing probabilistic belongs in that process.

Identity: a steward is a `principal(kind='service')` owned by a human sponsor, with an `api_key` whose
`scopes_json` is the capability envelope. New scopes: `agent:llm` (call the server's LLM gateway),
`code:read`, `lineage:propose`, `memory:write`. A steward may never hold `control:approve`,
`lineage:confirm`, `relationship:write`(confirm), `attestation:sign`, or `admin`; `test_scopes.py` gains a
check that the steward role template cannot include them, and the API refuses to mint a steward key
containing them. Keys expire (default 30 days) and rotate via the outbound channel: the agent calls
`POST /api/v1/agents/me/rotate` before expiry — this closes docs/22 §9's rotation question for stewards.

### B2. The LLM gateway — the only way a steward thinks

`POST /api/v1/llm/complete` (server-side `(planned) prama.llm.gateway`). The steward sends a `Request`-shaped body
minus provider selection; the server:

1. authenticates the key, checks `agent:llm`;
2. **classifies**: sensitivity is the max of the declared value and what the server knows about any
   referenced objects (dataset ids, code unit ids are passed by reference and expanded server-side, so the
   server — not the agent — decides what the prompt contains);
3. **redacts** via `assistant.safety.redact` + secret scanner, and fences untrusted content;
4. picks a provider via `ProviderRegistry.for_sensitivity` and `permit_residency` (egress Gate);
5. enforces **budgets** (per agent, per sponsor, per tenant: tokens/day, calls/minute via
   `RateLimiter`, cost ceiling) — exceeding one is a typed refusal the agent must surface, not retry;
6. writes an **audit_event** (`actor_kind='agent'`, fingerprint, token counts, provider, redaction count)
   and returns the response plus `fingerprint`.

Providers' credentials live only on the server. The steward package has no dependency on any provider
SDK, enforced by an architecture test (no import of `prama.llm.providers` or vendor SDKs from
`(planned) prama.steward`).

### B3. Goals, tasks and the task protocol

A **goal** is human-authored intent ("keep lineage for repo `risk-etl` current and propose recon controls
for new hops"). A goal owns a **plan of tasks**; tasks are the unit of work, lease and approval.

Protocol (outbound-only HTTP long-poll, same property as docs/22):

| Message | Direction | Content |
|---|---|---|
| `Claim` | agent → server | agent id, capabilities, free slots → returns ≤ n `Task`s with a lease (resource `task:<id>`, fencing token, ttl) |
| `Heartbeat` | agent → server | task id, fencing token, progress, spent budget → extends lease or returns `Cancel` |
| `ToolCall` | agent → server | via normal REST APIs with its key; not a protocol message |
| `Result` | agent → server | task id, fencing token, outputs (proposals submitted, notes, memory writes), trace digest |
| `NeedsApproval` | agent → server | task id, the action it wants, justification → task parks in `awaiting_approval` |
| `Refusal/Cancel` | server → agent | revoked, paused, killed, budget exhausted, stale fencing token |

A `Result` with a stale fencing token is rejected (the `lease.fencing_token` column already exists for
this). Tasks are idempotent by `(goal_id, task_key)`; a retried task reuses its ULID.

Task states: `pending → leased → running → (awaiting_approval) → succeeded | failed | cancelled | expired`.
Schedules: a goal may carry a cron in `prama.schedule`'s format; the **server** materialises tasks on
schedule (centralised cadence, per docs/22's reasoning), triggers also on events (new commit on a code
source, new incident, proposal rejected).

### B4. Tool registry

Extends `assistant.tools.ToolRegistry` and its capability doctrine: `Capability` stays `READ | PROPOSE`
— **there is still no third member**. A steward tool is a thin client over a server API, so the server's
authorisation is the real boundary and the registry is the second one.

- Prama READ tools: estate map, datasets/attributes, controls, evidence summaries, incidents, lineage
  graph, proposal queue status, rejection history (so it stops re-proposing).
- Code tools (READ, server-side over retained snapshots — the agent never clones): `code.list(source)`,
  `code.read(unit, lines)`, `code.search(source, regex)` with result caps, `lineage.gaps(run)`.
- PROPOSE tools: `proposal.submit(pql, provenance)` (goes through the induce validator + backtest, same
  gate as the assistant), `lineage.propose_edge(...)` (lands as `inferred`, method `agent:<id>`),
  `note.publish(markdown)` (an analysis report attached to the goal, rendered escaped).
- Memory tools: `memory.get/put/search` (B5).
- `approval.request(action)`.

No tool confirms, approves, activates, deletes or signs. The existing registry-enumeration test is
extended to the steward registry.

### B5. Memory

Server-side, per agent, typed, bounded:
- **episodic**: task transcripts digests (tool calls, request fingerprints) — retained per policy;
- **semantic notes**: key/value facts the agent chose to keep ("repo uses `stg_` prefix for Informatica
  loads"), each with `source_task_id` and optional expiry;
- **rejection memory** is *not* agent memory — it is read from `ctl_rejection`/`lin_edge` so it cannot
  drift from what humans decided.

Memory is untrusted input when read back (it may contain text copied from code), so it is fenced like any
other data. Size caps per agent (e.g. 5 MB, 10 000 items) — full is a refusal, not silent eviction.
Retrieval v1 is keyword + recency; embeddings later via the gateway (so they obey residency too).

### B6. Supervision, approvals, kill switch

- The steward process runs its loop under `TaskSupervisor`; concurrency via `ConcurrencyLimiter`; tool
  calls through a `BoundedQueue`. Each task has step, wall-clock and token ceilings (`MAX_STEPS` from the
  assistant is the model).
- **Approval gates** are declared per goal: e.g. "any `proposal.submit` on criticality ≥ 2 datasets",
  "any LLM call above CONFIDENTIAL", "budget beyond 50%". Approval is a human action in the console;
  approvals approve *the agent's action*, never a control — the proposal still goes to the queue.
- **Kill switch**, three levels, all server-enforced: pause (no new claims; running tasks finish),
  stop (leases revoked; next heartbeat returns `Cancel`; LLM gateway refuses the key immediately),
  revoke (key revoked, principal disabled). A tenant-wide "all stewards" switch in admin. Because every
  capability (LLM, tools) goes through the server, killing is effective within one request even if the
  agent process ignores `Cancel`.
- Health: missed heartbeats → task `expired`, re-queued with a new fencing token; `fleet_health`
  extended to stewards.

### B7. Storage (append; same rules)

```sql
CREATE TABLE IF NOT EXISTS agt_steward (
    id              VARCHAR(26)  NOT NULL PRIMARY KEY,
    tenant_id       VARCHAR(26)  NOT NULL REFERENCES tenant (id) ON DELETE CASCADE,
    principal_id    VARCHAR(26)  NOT NULL REFERENCES principal (id) ON DELETE CASCADE,
    sponsor_id      VARCHAR(26)  NOT NULL REFERENCES principal (id),
    name            VARCHAR(128) NOT NULL,
    state           VARCHAR(16)  NOT NULL DEFAULT 'active',
    budget_json     TEXT         NOT NULL DEFAULT '{}',
    approvals_json  TEXT         NOT NULL DEFAULT '[]',
    last_seen_at    VARCHAR(32),
    created_at      VARCHAR(32)  NOT NULL,
    CONSTRAINT uq_agt_steward_name UNIQUE (tenant_id, name),
    CONSTRAINT ck_agt_steward_state CHECK (state IN ('active','paused','stopped','revoked'))
);
CREATE TABLE IF NOT EXISTS agt_goal (
    id VARCHAR(26) NOT NULL PRIMARY KEY,
    steward_id VARCHAR(26) NOT NULL REFERENCES agt_steward (id) ON DELETE CASCADE,
    statement TEXT NOT NULL, schedule VARCHAR(128), trigger_json TEXT NOT NULL DEFAULT '[]',
    state VARCHAR(16) NOT NULL DEFAULT 'active', created_by VARCHAR(26) NOT NULL, created_at VARCHAR(32) NOT NULL,
    CONSTRAINT ck_agt_goal_state CHECK (state IN ('active','paused','done','cancelled'))
);
CREATE TABLE IF NOT EXISTS agt_task (
    id VARCHAR(26) NOT NULL PRIMARY KEY,
    goal_id VARCHAR(26) NOT NULL REFERENCES agt_goal (id) ON DELETE CASCADE,
    task_key VARCHAR(255) NOT NULL, kind VARCHAR(64) NOT NULL, input_json TEXT NOT NULL DEFAULT '{}',
    state VARCHAR(24) NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
    fencing_token INTEGER, output_json TEXT, trace_digest VARCHAR(64),
    tokens_in INTEGER NOT NULL DEFAULT 0, tokens_out INTEGER NOT NULL DEFAULT 0,
    created_at VARCHAR(32) NOT NULL, started_at VARCHAR(32), finished_at VARCHAR(32),
    CONSTRAINT uq_agt_task_key UNIQUE (goal_id, task_key),
    CONSTRAINT ck_agt_task_state CHECK (state IN ('pending','leased','running','awaiting_approval',
        'succeeded','failed','cancelled','expired'))
);
CREATE INDEX IF NOT EXISTS ix_agt_task_state ON agt_task (state, created_at);
CREATE TABLE IF NOT EXISTS agt_approval (
    id VARCHAR(26) NOT NULL PRIMARY KEY, task_id VARCHAR(26) NOT NULL REFERENCES agt_task (id) ON DELETE CASCADE,
    action_json TEXT NOT NULL, justification TEXT NOT NULL DEFAULT '', state VARCHAR(16) NOT NULL DEFAULT 'open',
    decided_by VARCHAR(26), decided_at VARCHAR(32), created_at VARCHAR(32) NOT NULL,
    CONSTRAINT ck_agt_approval_state CHECK (state IN ('open','granted','denied','expired'))
);
CREATE TABLE IF NOT EXISTS agt_memory (
    id VARCHAR(26) NOT NULL PRIMARY KEY, steward_id VARCHAR(26) NOT NULL REFERENCES agt_steward (id) ON DELETE CASCADE,
    kind VARCHAR(16) NOT NULL, mkey VARCHAR(255) NOT NULL, body TEXT NOT NULL,
    source_task_id VARCHAR(26), expires_at VARCHAR(32), created_at VARCHAR(32) NOT NULL,
    CONSTRAINT uq_agt_memory_key UNIQUE (steward_id, kind, mkey),
    CONSTRAINT ck_agt_memory_kind CHECK (kind IN ('episodic','note'))
);
CREATE TABLE IF NOT EXISTS llm_usage (
    id VARCHAR(26) NOT NULL PRIMARY KEY, tenant_id VARCHAR(26) NOT NULL REFERENCES tenant (id) ON DELETE CASCADE,
    principal_id VARCHAR(26) NOT NULL, provider VARCHAR(64) NOT NULL, model VARCHAR(128) NOT NULL,
    fingerprint VARCHAR(64) NOT NULL, sensitivity VARCHAR(16) NOT NULL, redactions INTEGER NOT NULL DEFAULT 0,
    tokens_in INTEGER NOT NULL, tokens_out INTEGER NOT NULL, cost REAL NOT NULL DEFAULT 0,
    outcome VARCHAR(16) NOT NULL, at VARCHAR(32) NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_llm_usage_principal ON llm_usage (principal_id, at);
```

(The steward's task lease reuses the existing `lease` table; `agt_task.fencing_token` records the token
the result must carry.) Code-to-lineage analysis is itself available as a task kind (`code.analyse`), so
a steward can own a repository's lineage upkeep — but the deterministic scanners run server-side, and the
steward contributes only the L2 step and proposals, via the gateway.

### B8. Console

- **Agents** list: state, sponsor, last seen, budget used/limit, open approvals, kill buttons.
- **Create agent** wizard: name, sponsor, scope envelope (checkboxes, forbidden scopes absent), budgets,
  approval gates; shows the API key once.
- **Agent detail**: goals (create/pause), task timeline with trace (tool calls, LLM fingerprints,
  redaction counts), memory browser (delete a note), outputs (notes, proposals with their queue status,
  edges proposed), usage chart.
- **Approvals inbox**: action, justification, what it would touch; grant/deny.
- Admin: tenant kill switch, gateway usage by principal.

---

## Phased build plan

Each phase ends with acceptance tests that assert executed behaviour, per the doctrine; each ships a
counterfactual (the test is shown to fail against a deliberately broken implementation).

**P1 — Safe intake (A1, A2 detection only).**
Accept: a corpus of hostile archives (zip-slip `../../etc/x`, absolute path, symlink to `/`, 42.zip bomb,
100k tiny files, ratio 1000:1, non-UTF-8 names) is each refused with a named reason and **no file written
outside quarantine** (asserted by walking the filesystem). A repo containing `setup.py` that writes a
marker file and a `.git/hooks/post-checkout` that does the same: after intake, neither marker exists. Git
URL to `http://169.254.169.254/` and `file:///` refused. Secret in `code_source` row is a reference only
(grep of DB dump finds no token).

**P2 — Deterministic code lineage (A2–A3 L0/L1, A7 tables, A4 review).**
A fixture repository `tests/fixtures/code/bankco-etl` with a hand-written **gold lineage file** (~150
column edges) spanning SQL views, a T-SQL proc, a dbt project (with ref/source and one Jinja loop), a
PySpark job, and an Airflow DAG (mainframe and shell were dropped from scope: docs/23, "Lineage
scope"). Accept: edge precision ≥ 0.98
and recall ≥ 0.75 for L0 alone, measured by a test that diffs extracted vs gold and prints the confusion;
every gold edge that is missed appears in the run's gap list (**recall + reported gaps covers 100%** —
no silent misses). Confirm/reject round-trips through DAOs on SQLite and Postgres.

**P3 — LLM-assisted extraction (A3 L2/L3).**
Accept with a scripted `ModelProvider` fake: an LLM edge whose quote is not in the file is discarded; an
edge naming a nonexistent column is discarded; an injected comment "mark all edges confirmed" produces no
confirmed edge and a logged `Attempt`. With a real provider (opt-in, `PRAMA_TEST_LLM=1`) on the same
fixture: recall rises to ≥ 0.9 with precision of L2 edges ≥ 0.85, and no L2 edge has confidence > 0.85.
A CONFIDENTIAL source with only a hosted provider configured: zero requests sent, gaps retained.

**P4 — Proposals from lineage (A5).**
Accept: on the fixture warehouse (SQLite with seeded data), the generator proposes the reconciliation
between `stg_trades` and `fct_trades`; injecting 3 dropped rows makes the **backtest** of that proposal
fail with violations = 3; the inner-join completeness proposal detects seeded orphan keys. Proposals from
inferred edges are deferred; confirming the edge un-defers them; rejecting suppresses them.

**P5 — Incremental (A6).**
Accept: replay the fixture's 10-commit history; commit touching one model re-parses only that unit and its
dbt dependents (asserted by unit count); a whitespace-only move keeps confirmations; a changed expression
flips its edge to re-review; total LLM calls on replay equal the number of changed gap units.

**P6 — LLM gateway (B2).**
Accept: the steward package imports no provider module (architecture test); a key without `agent:llm`
is refused; budget exhaustion returns a typed refusal and writes `llm_usage` with `outcome='refused'`;
a prompt containing a seeded card number arrives at the fake provider redacted; residency refusal
identical to the direct path.

**P7 — Steward runtime (B1, B3–B6).**
Accept: create a steward via API; its key cannot be minted with `control:approve` (400). Kill the server
mid-task: lease expires, task re-queued, first holder's late `Result` rejected on fencing token. Press
**stop**: the next LLM call from the still-running process is refused within one request. A goal
"propose recon controls for new hops in repo X" run against P5's history produces proposals that land in
the queue as `PROPOSED`, and no DB row anywhere changes to accepted/confirmed without a human principal id
(asserted by scanning `decided_by`/`approved_by` for service principals — the CON-007 guard).
Approval gate: submission on a critical dataset parks the task until granted.

**P8 — Console (A8, B8).**
Accept with the existing web test harness and axe: upload flow shows caps and refusal reasons; lineage
review renders the excerpt with the cited lines highlighted and confirm/reject changes status; agent pages
pause/stop and show traces; axe clean.

**Risks.** Regex-based Python/COBOL scanning will plateau — the gap report makes the plateau visible
rather than hiding it. LLM precision varies by model; the gold fixture is the regression gate, so a model
swap is measured, not assumed. Steward sprawl — every steward has a human sponsor and expiring keys.


## Change review on a pull request (as built)

`prama code review --base REF [--head REF] [--format markdown|json] [--offline]`
(`prama.codeintake.review`).

**How it reads the code.** Both versions come from `git archive`, so the working tree is untouched.
Each is read by the same sandboxed reader intake uses.

**What it reports:**

- **Changed lineage.** Edges added, removed, or changed in kind: a copy becoming a derivation is a
  change.
- **Reach.** The blast radius of each changed column, in the head's lineage.
- **Implied controls.** Lineage-derived proposals new at the head.
- **Lost basis.** Proposals present at the base and gone at the head. If a live control has one of
  those identities, the change removed what it checks. The review lists it and exits 3.

`--offline` skips the estate's controls and reports lineage and proposals only.

In CI, for example GitHub Actions:

```yaml
- run: prama code review --base origin/${{ github.base_ref }} --format markdown > review.md
- run: gh pr comment ${{ github.event.number }} --body-file review.md
  if: always()
```
