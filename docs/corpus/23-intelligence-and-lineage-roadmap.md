<!-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE. -->

# 23 — Intelligence and Lineage: the roadmap after Wave 11

> Written 2026-09-27. This extends [19 — Implementation Roadmap](19-implementation-roadmap.md) with Waves
> 12 to 17. Once work starts, 19 records the status markers; this document records the plan and the
> reasons for it.

Three questions are answered here, each with a design note behind it:

| Question | Design note |
|---|---|
| How does Prama shrink the gap to **IBM Manta** (lineage) and **Alation** (catalog) without losing its own thesis? | [design/gap-manta-alation.md](../design/gap-manta-alation.md) |
| How does Prama call **any LLM**? Local (Qwen, Llama and Mistral via vLLM, Ollama, llama.cpp, LM Studio, TGI) or remote (Hugging Face, Anthropic, Amazon Bedrock, OpenAI or Azure), with budgets, residency, redaction and audit. | [design/llm-gateway.md](../design/llm-gateway.md) |
| How does Prama take an **application ZIP or a git location**, infer its ETL lineage, and propose DQ checks? And how do **Prama agents** become persistent AI agents that do this analysis by calling the Prama server? | [design/code-lineage-and-steward-agents.md](../design/code-lineage-and-steward-agents.md) |

---

## As built

**Wave 12, as built so far (2026-09-27):**

- **The three LLM defects** are fixed as Q-123:
  - `grammar_enforced` is recorded only when the server really applies the grammar;
  - hosting is required, and a vendor API cannot be declared self-hosted;
  - prompts are redacted, including Luhn-valid card numbers.
- **LLM gateway, phase 1:**
  - **The five tables**, with every later-phase column declared now, since there are no
    migrations.
  - **Code:** `prama.llm.kinds` (the provider factory and offline mode), `prama.llm.gateway`
    (routing, retry, fallback that never becomes less local, a hash-chained call record, and
    `ProfileProvider`) and `prama.llm.wiring`.
  - **Surfaces:** `prama llm provider|profile|ask|calls` and the **Models** page.
  - **Guard:** an import-graph test that no verdict-producing package can reach `prama.llm`.
- **Real SQL parser** (`sqlglot`, `prama.lineage.parsed`). It follows columns through CTEs and
  subqueries, and parses T-SQL brackets and about twenty dialects. The pattern reader remains the
  declared fallback, and a `regex_fallback` gap says when it was used. Building the store also
  found and fixed a defect in the pattern reader: it read a string literal (`'BOOKED'`) as a
  column.
- **Lineage store and workbench (E1):**
  - **Tables:** `lin_source`, `lin_run`, `lin_edge` (bitemporal, with provenance; `parsed`
    versus `inferred` versus a person's decision) and `lin_gap`.
  - **Code:** `prama.lineage.store.scan_sql` and `prama lineage scan|show|impact|gaps`.
  - **The Lineage page:** edges, confirm and reject, an impact drawing, recent scans, and gaps.
- **Trust over the persisted graph (E1 acceptance 2).** `prama.lineage.trust` derives local
  trust from the latest verdicts. A 40%-violating upstream control gives 0.60 downstream, and
  rejecting the edge restores 1.00. The incident page lists upstream feeders with their trust.
  The full RCA ranker waits for correlated incidents.
- **Always-on scheduler.**
  - `prama.execute.scheduler` runs inside `prama serve` under the task supervisor, with one
    server per tick by a database lease.
  - It is off unless `scheduler.enabled`, `scheduler.against` and a default tenant are set.
  - The Schedule page shows the recent ticks and has a "run a tick now" button.
- **Wave 12 is complete.**

**Wave 13, as built so far:**

- **E3, the change gate.** `prama lineage impact --diff before.sql after.sql` finds the columns
  whose feeding changed and follows them through the estate's lineage. It names the controls
  and attestations on every affected dataset and exits 3 if any is at risk. `/api/v1/lineage/impact`
  answers the same question over the API. Filter dependents are listed as affected, not waived
  (a dropped column breaks every query filtering on it). This departs from the design note on
  purpose.
- **E2, ingestion.**
  - `POST /api/v1/lineage/openlineage` (`relationship:write`) stores a RunEvent's column-lineage
    facet. There is one source per job, so an event never closes another job's edges, and a
    replay is idempotent.
  - `prama lineage ingest-dbt manifest.json` reads compiled models through the SQL parser. An
    uncompiled model is a gap; Prama never renders a project's Jinja.
  - Warehouse access-history readers (Snowflake, Databricks, BigQuery) wait on those connectors
    meeting a live account (remaining-work §4).
- **LLM phase 2, the core.**
  - `POST /api/v1/llm/chat` needs the new `llm:use` scope, which the owner and steward roles
    hold; admin holds everything. It has a bounded per-principal rate limit.
  - The provider call runs off the event loop.
  - **Pricing** is dated `llm_model` rows in integer micro-units, and a call is costed from the
    price in force when it started.
  - **Budgets** (tenant, profile, principal, API key; day or month; refuse or warn) are checked
    against spend derived from the ledger. A refusal is HTTP 429, and is itself recorded as
    `refused_budget`.
  - The Models page shows this month's spend and sets budgets and prices.
- **Fleet-wide reservation.** The check and an estimate reservation happen under the tenant's
  budget lease, in a committed transaction of their own, so other servers see an in-flight
  call's spend. The reservation is released with the call record.
- **Pattern redactors.** IBANs (withheld only when the mod-97 check passes) and email
  addresses join secrets and card numbers.
- **Response cache.** It is bounded, holds temperature-zero requests only, and is keyed by
  tenant, fingerprint, provider, model and profile version. It is consulted **after** the
  candidate's policy checks, so it is never an oracle for a request that would now be refused
  (tested with a planted entry). Hits are recorded as `served_from: cache`.
- **Streaming.**
  - `ModelProvider.ask_stream` applies the same checks as `ask`. A provider that cannot stream
    yields its answer once.
  - The OpenAI-compatible provider streams server-sent events token by token, skipping
    keep-alives and malformed events.
  - `LlmGateway.run_stream` picks the first candidate the policy allows, before the first token,
    with no mid-answer fallback.
  - `POST /api/v1/llm/chat/stream` serves `text/event-stream`, pulling from a worker thread so a
    slow client slows the model. The call is recorded when the stream ends.
- **Moved to Wave 14:** stored payloads (`llm_payload`), with the template and evaluation
  governance that decides what may be kept.

**Wave 14, as built so far:**

- **Safe intake (P1), `prama.codeintake`.**
  - ZIPs are checked from the central directory before extraction, and sizes are re-checked
    while streaming. Refused: zip-slip, absolute paths, bombs by compression ratio, too many
    entries, oversized files. Symlinks are recorded and never created, and nothing received is
    executable.
  - git accepts `https`/`ssh` only. Refused: private, loopback and metadata addresses, and option
    injection. A host allow-list is optional. Clones are hardened (no hooks, no `file`/`ext`
    transports, no submodules, `fsckObjects`, `symlinks=false`, depth 1), and the token goes via
    `GIT_CONFIG_*` environment variables, never argv.
  - Reading happens in a separate `python -m prama.codeintake.worker` process with CPU, memory,
    file and core limits. The tree is deleted after every run.
  - Tables `code_source`, `code_analysis_run` and `code_unit`, with a tenant on each.
- **Deterministic code lineage (P2, SQL units).** SQL files become `code:<name>` lineage, with
  each edge pointing at its unit. Every other kind of file is inventoried and reported as not yet
  read. Surfaces are `prama code add-zip|add-git|runs` and the Code page.
- **Not a registered egress point:** a git fetch sends no estate data. The reasoning is in
  `prama.codeintake.git`.
- **More readers in the sandbox.**
  - T-SQL, PL/SQL and DB2 stored procedures go through the procedural scanner, with dynamic SQL
    reported as a gap.
  - SSIS and PowerCenter exports go through the XML scanners, stored as `inferred`, because those
    scanners declare themselves unverified against real exports.
- **The gold gate (`tests/codeintake/test_gold_fixture.py`, `tests/fixtures/code/bankco-etl`).**
  - Precision must be ≥ 0.98, and every true edge must be found or sit in a unit reported as
    unread or incomplete.
  - Today: **precision 1.00, recall 1.00** over 18 edges. Recall was 0.83 before the PySpark
    reader. Against today's gold it would be 0.67 without the pandas and Airflow readers, and the
    gate now requires at least 0.95.
- **PySpark reader (`prama.lineage.pyspark`).**
  - It parses the syntax tree and never executes the job.
  - It follows `spark.table`, `select`/`alias`, `withColumn`, `withColumnRenamed`,
    `groupBy().agg()` and `filter` to `saveAsTable`/`insertInto`. A column carried forward keeps
    how it was made.
  - Joins, UDFs and computed names are gaps, never guesses.
- **pandas reader (`prama.lineage.pandas_ast`).**
  - It parses the syntax tree, into function bodies, and never executes the job.
  - It follows `read_sql_table`, and `read_sql` with a literal query (the SQL parser names the
    query's sources), then column lists, `rename`, a column assigned from other columns, and row
    filters, through to `to_sql`.
  - `merge`, `groupby`, `apply`, `inplace=True` and a whole-table copy with unnamed columns are
    gaps.
- **Airflow reader (`prama.lineage.airflow`).**
  - It parses the DAG and never imports it.
  - Every `sql=` string literal is read by the SQL parser, with `produced_by` set to
    `dag-file:task_id`. A `.sql` file reference is left to the file's own reading.
  - Templated SQL, SQL built at run time, and `EXEC`/`CALL` of a procedure are named gaps.
- **Templates and evaluation governance, built** (`llm/templates.py`, `llm/evaluation.py`,
  `llm_template*`, `llm_eval_run`, `llm_payload`).
  - **Templates** are versioned. Rendering fences every untrusted value and takes the highest
    declared sensitivity. A version is approved by someone other than its author, and the call
    ledger records which version produced each call.
  - **Evaluation suites** are YAML with deterministic graders only: `nonempty`, `contains`,
    `absent`, `matches`, `json_valid`, `json_keys`, `pql_parses` and `max_latency_ms`.
  - **The gate.** With `llm.eval.gate_activation`, a profile or template version becomes
    current only after a passing run of that exact version (`prama llm profile activate`,
    `prama llm template approve`).
  - **Payloads** follow `llm.audit.payloads`: `none`, `redacted` (the default when kept) or
    `full`. They are blanked at expiry.
  - **`prama llm verify`** recomputes the call chain. Fields added later are left out of the
    sealed content when empty, so older records still verify.

**Lineage scope (decided 2026-09-27).** Prama adopts the parts of Manta's capability a
modern bank's data platform needs. It does not try to match Manta's breadth.

- **In scope, built:**
  - SQL in about twenty dialects, including stored procedures in T-SQL, PL/SQL and DB2 SQL PL;
  - dbt manifests;
  - OpenLineage events;
  - PySpark and pandas jobs;
  - Airflow DAGs;
  - SSIS and Informatica PowerCenter exports, stored as *inferred* until verified against real
    exports.
- **In scope, built since:** re-analysing only what a new commit changed (P5).
  - A file whose SHA-256, reader version and dialect all match the base run is not re-read.
  - Its unit, gaps and open edges are carried forward, with their method, status and
    confidence (`code_analysis_run.base_run_id`, `coverage_json.reused`).
  - A changed file is re-read, and the edges it no longer produces close.
- **Power BI, built** (`prama.lineage.powerbi`).
  - It reads a `.pbit` or a `model.bim`, and never Power BI itself.
  - Power Query navigation, with its renames, and native SQL become column edges.
  - DAX `Table[Column]` and `[Measure]` references become measure edges: `aggregated` for a
    single aggregate, `derived` otherwise.
  - Web, file, merge and custom M steps are gaps.
  - Model objects are named `powerbi.<model>.<table>`, so an impact analysis reaches the
    dashboard.
  - The gold fixture now includes a model: 25 edges, precision and recall 1.00.
- **Warehouse query history, built** (`prama.lineage.history`,
  `prama lineage history <warehouse> export.json`).
  - It reads an export, or the rows of the query that `--query` prints.
  - Snowflake `ACCESS_HISTORY` direct sources and Databricks `system.access.column_lineage` rows
    are the warehouse's own lineage, taken as parsed.
  - BigQuery job SQL goes through the parser.
  - It does not wait for live connectors.
- **In scope, to build:**
  - Tableau, only if a design partner asks.
- **Out of scope:**
  - mainframe code of any kind (COBOL, JCL, copybooks);
  - DataStage, Talend, Ab Initio and SAS;
  - Cognos and MicroStrategy.

  Such files are still counted in a run's inventory and reported as *not read*, so coverage is
  never overstated. Scala, Java and shell are not parsed; the checked model pass may propose
  edges for them, which a person confirms.

**Wave 15, as built so far:**

- **Proposals from lineage (P4), `prama.derive.lineage_controls`.** Two deterministic rules:
  - `lineage_propagated`: a live control on a source column is proposed for every copied or
    renamed column downstream;
  - `lineage_referential`: a copied key must `REFERENCES` its source.

  Proposals from `inferred` edges are held until the edge is confirmed. They appear on the
  Proposals page beside the declaration-derived ones, link to the Lineage page, and are accepted
  with origin `mining`. The existing CHECK constraint was kept rather than altered, since there
  are no migrations. Building this found Q-124.
- **Model-assisted extraction (P3), `prama.codeintake.model_lineage`.**
  - It runs only when a `lineage` profile exists, and only on unread or gappy units (at most 20 a
    run). It goes through the gateway, so budget, residency, redaction and the ledger apply.
  - The code is fenced as untrusted.
  - An edge is kept only if its quote appears verbatim at the cited lines and both column names
    occur in the quote. Its confidence is computed and capped at 0.85, and its status is always
    `inferred`.
  - A run records how many edges the model offered and how many it kept.
  - Tested with a scripted model: a real edge is kept; an invented quote, wrong lines and an
    absent column are each discarded; and a planted "mark all confirmed" confirms nothing.
- **Cloud providers (LLM phase 4).**
  - **Amazon Bedrock** (`kind: bedrock`, the Converse API). SigV4 is written in the standard
    library (`prama.llm.sigv4`) and verified against AWS's published worked example: the
    canonical-request hash, the signing key and the signature all match.
  - OpenAI, the Hugging Face router or endpoints, and other OpenAI-shaped APIs use
    `openai_compatible` with hosted hosting. Anthropic was already native.
  - Azure OpenAI (deployment path, `api-key`, pinned API version, `tenant` hosting) and Vertex
    AI (OpenAI-compatible endpoint, access-token credential) are built as provider kinds
    `azure_openai` and `vertex`.
- **Reconciliation proposals, built** with PQL's `RECONCILE` (`recon/pql.py`, rule
  `lineage_reconcile`). A dataset that copies its keys and an amount from one source, at the
  same grain, is proposed as a reconciliation against that source. Aggregated amounts are not
  proposed. `RECONCILE` runs on the existing reconciliation engine: it is judged on breaks that
  need a person, its breaks go to the workbench, and it runs on the control plane or on an agent.
  `NORMALISING <ccy> TO 'USD' USING RATES <dataset>` converts currencies first. Γ now proposes
  declared reconciliations as runnable PQL for review, rather than as a specification that
  nothing runs.
- **Deferred, each to the phase that first needs it:**
  - The transport-module extraction, multi-turn messages and JSON-schema validation go to
    Wave 13, with the new wire formats.
  - `ProfileProvider` is ready, but no production builder constructs the assistant or inducer
    yet. The first will be the Wave 16 agents.

**Wave 16, as built so far:**

- **Steward agents, server-hosted (`prama.steward`).**
  - **Identity.** A steward is a service principal with a human sponsor and a 30-day key.
    `control:approve`, `attestation:sign`, `admin`, `relationship:write` and `*` are refused.
  - **Goals and tasks.** Goals run on schedules (`6h`, `1d`) or on request. The runner lives in
    the app's supervisor and re-reads the kill switch from a fresh transaction before each task.
  - **Tools**, which read and propose only: summarise incidents, re-read a git code source's
    lineage, and report lineage proposals.
  - **Model calls** go through the gateway as the steward's principal (surface `steward`), so
    they are costed, budgeted and recorded.
  - **Kill switch.** Pause, stop (open tasks cancelled) and revoke (key revoked, principal
    disabled). A revoked steward stays revoked.
  - **Guard.** An AST scan fails the build if the steward package calls `activate`, `accept`,
    `sign`, `decide`, `approve`, `confirm` or `suppress`.
  - The Agents page and a help guide.
- **Remote protocol (`prama.steward.protocol`, `/api/v1/agents/*`, scope `agent:work`).**
  - Claim leases `agt-task:<id>` and hands out the lease's fencing token. A heartbeat renews it
    or answers `cancel`. A result or approval request carrying a stale token is refused with 409.
  - Abandoned tasks are re-queued with a new token.
  - A paused steward's claims are refused (403), and a key that is not a steward's cannot act as
    one.
- **Approval gates.** A goal with `approve_before_run` parks each task until a person grants it
  (it then runs) or denies it (it fails). Remote agents ask with `/ask`. The console shows open
  approvals. An approval covers the agent's action, never a control.
- **E8, curation assistants (description drafting).** A steward goal, `curation.describe`,
  drafts a description for each dataset that has none, through the gateway under the purpose
  `curate`. Drafts land in `cur_suggestion` and appear on the Agents page. Accepting one amends
  the dataset with the accepting person as its author; the model is named only in the amendment's
  reason. A draft for a gap that has since been filled becomes `stale` and is not applied.
  `src/prama/curation/suggestions.py` makes no model call. Glossary drafting waits for the
  glossary entity (E5).

Before Wave 12, what existed and what these waves build on:

- **Built and tested:**
  - the LLM SPI and providers (`src/prama/llm/spi.py`, `src/prama/llm/providers.py`, with the
    three defects in §1);
  - the lineage library (`src/prama/lineage/`);
  - the distributed execution agents (`src/prama/agent/`);
  - the assistant and MCP server;
  - the proposal queue.
- **Built but never met the real thing:** catalog write-back adapters, Snowflake.
- **Not built:**
  - the LLM gateway and `/api/v1/llm`;
  - lineage persistence and any lineage UI;
  - an always-on scheduler;
  - code intake;
  - steward agents.

Modules named in the design notes that do not exist yet are marked `(planned)` there.

**Wave 18 (requested mid-roadmap), DQ delegates, as built:**

- **What it is.** Python checks the bank writes, named from PQL:
  `CHECK t USING DELEGATE 'acme.x@1' (param = …)`.
- **Where it lives:** `src/prama/delegates/` holds the interface (`DqDelegate`, `Measurement`),
  the admission gate and the sandboxed host.
- **Admission.** Each delegate file is scanned before import, probed twice for determinism, and
  its source hashed.
- **Verdicts.** A delegate returns counts; the control's threshold and the shared `judge()` decide
  the verdict. The delegate, its version and its source hash are recorded on every evidence
  record.
- **Where it runs.** The control-plane run, the scheduler and `prama control run` take a delegate
  host from `delegates:` in configuration. So does each remote execution agent, from its own
  configuration; an agent advertises the delegates it admitted, and `fits()` assigns delegate
  controls only to agents that have them.
- **Tooling and docs:**
  - `prama delegate list | scan | test`;
  - the design, `docs/design/dq-delegates.md`;
  - the console guide *DQ delegates*;
  - case study 5, `case-studies/05-dq-delegates`. There, the settlement-cycle delegate finds the
    36 planted off-cycle trades that a column comparison passes, and a Benford delegate on a PCI
    zone agent fails the ledger with invented invoices while the clean ledger passes.
- **A fix found on the way:** a run's summary called controls on another source "not due".
- **Added afterwards, on request:**
  - `CHECK CUSTOM SQL`: one read-only query, checked on its syntax tree at parse time;
  - large inputs streamed to delegates in cursor batches;
  - the author conformance kit (`prama delegate check`);
  - console uploads, vetted in a sandbox and approved by someone other than the uploader;
  - `prama delegate pull`, for remote agents.
- **Also added:** the mock LLM provider. When no model is configured, the gateway uses a
  placeholder that answers with nothing.

**Semantic search for fitness to purpose, as built** (`semantic/services/fitness.py`,
`sx_vector`, the provider SPI's `embed`):

- **What is ranked.** Each dataset's profile: its declaration, business context, metadata,
  glossary terms and attribute texts.
- **How.** By embeddings when a model is configured for `embed`
  (OpenAI-compatible `/v1/embeddings`, or Azure deployments). Vectors are stored per model and
  re-embedded only when a profile's text changes. Otherwise BM25 with light stemming is used,
  and the answer names the ranking.
- **Evidence and explanation.** Each result names its matching attributes. A `discover` model
  may re-order and explain the top datasets.
- **Scope.** Search stays across datasets; searching inside a dataset was withdrawn by the user.
- **Not built:** Vertex embeddings, whose API is separate from the chat one.

**Wave 17, E7 (usage signals), as built** (`us_usage`, `lineage/usage.py`,
`semantic/services/priorities.py`):

- **Daily usage.** Queries and distinct readers per dataset per day, taken from Snowflake,
  BigQuery or Databricks query-history exports. A re-import replaces the same days.
- **"Most used, least controlled"** orders the work, and lists used datasets nobody has declared.
- **Usage never reaches a score.** A structural test fails if anything under `prama.score`
  imports it.

**Wave 17, E6 (comments and steward queues), as built** (`cm_comment`,
`semantic/services/collaboration.py`):

- **Threads** on datasets, attributes, controls, terms and incidents, with `@mentions` that must
  name a real person. A reply reopens a resolved thread, and every write is audited.
- **My queue** is read from where things already live, not copied:
  - mentions, and open threads on datasets a person owns or stewards;
  - failing controls and metadata inconsistencies on those datasets;
  - curation suggestions for them;
  - for approvers, rules and uploads that someone else proposed.
- **Surfaces:** the Discussion section on each dataset's Metadata page, My queue,
  `prama comment`, `prama queue`, `/api/v1/comments` and `/api/v1/queue`.
- **Search** is the metadata search built earlier.

**Wave 17, metadata and business context, as built** (`semantic/metadata.py`,
`semantic/services/metadata.py`, `md_template`, `md_field`, `md_value`):

- **Business context** is a declared fact. It is a column on `sem_dataset_version` and
  `sem_attribute_version`, versioned with the rest of the declaration, and set by amendment.
- **Metadata templates** hold typed, bank-defined fields for datasets or attributes. Values are
  checked by kind and versioned by closing the previous row.
- **Rules grow from metadata.** A field's rule templates render values as typed literals, so
  metadata cannot inject PQL. They are offered on the Proposals page, and a person accepts them.
- **Hand-written rules** on the dataset page are recorded as proposed and approved by another
  person.
- **Search by meaning** covers business context, definitions, metadata values and the glossary.
  It uses keywords today; the same function is where embedding search will go.
- **Surfaces:** the Metadata pages, `prama metadata`, and `/api/v1/metadata`.
- **Correlation, built** (`semantic/correlate.py`, `prama metadata correlate`,
  `/api/v1/metadata/correlation`). Attributes sharing a concept property or a glossary term are
  grouped. `REFERENCES` checks toward the one dataset keyed by that meaning go to Proposals, and
  consistency findings (type, sensitivity, CDE, allowed values, pattern, description) are shown
  for stewards.
- **Finding data of interest, built** (`semantic/services/finding.py`, `prama metadata ask`,
  `/api/v1/metadata/ask`). Candidates are retrieved by keyword. A `discover` model ranks and
  explains them, may cite only candidates it was given, and falls back to keywords without a
  model.
- **Next:** feed the data-side signals (value overlap and query co-access, `prama.discover`) into
  correlation.

**Wave 17, E5 (glossary and catalog imports), as built:**

- **The glossary.** `gl_term` and `gl_binding` bind terms to concepts, datasets and
  attributes. The Glossary page searches names, synonyms and definitions.
  `sem_attribute_version.glossary_term` stays, for display; removing it would make every
  deployed database fail verification, since there are no migrations.
- **Imports** (`importers/catalog.py`):
  - Alation terms and column lineage;
  - Collibra Business Terms;
  - Manta's graph export.

  Each import lists every item it dropped, and why. Terms bind to same-named concepts
  automatically. Imported edges are stored as `imported:<vendor>`, beside Prama's own parse.
  `prama lineage conflicts` and the Lineage page show where the two disagree.
- **Not verified:** these readers are tested against the vendors' documented export shapes, not
  against a live Alation, Collibra or Manta instance. That verification is part of E9.

## 1. What the analysis found

**1. Prama's lineage is a tested library that nothing uses.** `lineage/graph.py`, `lineage/sql.py`
and `lineage/scan.py` are real and tested.

- No table in either schema file persists lineage.
- No CLI verb, API route or console page constructs the graph.
- OpenLineage is emitted but never consumed.

Roadmap item W8.7 was marked ✅ and is now corrected to ◑. The gap to Manta is therefore not "45
missing scanners"; it is **"there is no lineage a user can see."** Trust propagation, the
differentiator claimed in [21](21-how-we-win.md), cannot be demonstrated until this is fixed.

**2. The LLM SPI is sound, but three defects must be fixed before anyone relies on it:**

- `OpenAiCompatibleProvider` records `grammar_enforced=True` when a server silently ignored the
  grammar.
- It defaults to *self-hosted*, so pointing it at a vendor endpoint would skip residency checks.
- Redaction runs on answers but not on prompts.

**3. Breadth is not the goal.** The owner has accepted that Prama will not match Manta's scanner count or Alation's catalog breadth. The aim is adoption: be excellent at the regulated-bank path from code to evidence. **Alation-style catalog breadth is not where Prama should compete.** Search, popularity as a
quality signal, raw scanner count, access policy, and model-inferred lineage presented as fact are
all deliberately *not* chased. A Tier-2 bank does need these to buy:

- column-level lineage from a critical data element to a regulatory return;
- impact analysis and lineage history;
- stored-procedure lineage;
- glossary import;
- steward ownership;
- catalog write-back proven against a live catalog.

## 2. Principles that hold in every wave below

1. **AI never adjudicates (CON-007).** Models, and agents built on them, only *propose*:
   - A model-derived lineage edge starts `inferred`.
   - A generated control lands in the proposal queue.
   - An agent's key can never carry `control:approve`, `relationship:confirm`, `attestation:sign` or
     `admin`.
   - A guard fails if any row reaches accepted or confirmed with a service principal as the decider.
2. **The Prama server is the only door to a model.** Agents, the assistant, the inducer and the
   code analyser never hold provider credentials. All of them call the LLM gateway, which enforces
   budgets, residency, redaction, rate limits and audit, and records every call in `llm_call`.
3. **Deterministic first, model second, and the model is checked.** On code, the parsers run first.
   A model is asked only about the gaps they report. A model edge survives only if:
   - its quoted code appears verbatim at the cited lines, and
   - the columns it names exist.

   Its confidence is computed, capped at 0.85, and never taken from the model.
4. **Every capability ships with the UI to manage it.** No wave closes on a CLI alone.
5. **Measured, not claimed.** Code lineage is gated by a fixture repository with hand-written gold
   lineage (precision/recall printed on every run). Every other gate in the design notes asserts
   executed behaviour and has a counterfactual.

## 3. Reconciliations between the design notes

The three notes were written independently. Where they overlap:

| Overlap | Decision |
|---|---|
| `llm_usage` (agents note) vs `llm_call` (LLM note) | **One ledger: `llm_call`.** Agent calls are rows in it, with `caller_principal_id` and `agent_id`. |
| `lin_edge` (code note) vs the lineage store of Epic E1 (gap note) | **One store: `lin_edge`,** with a provenance kind covering code parser, code model, OpenLineage, dbt, warehouse history, declared journey, and imports from Manta, Alation or Collibra. Every source writes the same table, so the lineage workbench shows all of them. |
| Server-side agent schedules vs the missing always-on scheduler ([remaining work](remaining-work.md) §2.1) | **One scheduler.** Build it once, supervised and lease-fenced, inside `prama serve`. It runs controls and agent goals alike. |
| Gateway phase 2 vs agents phase P6 | The same work, done once in Wave 13. |
| Legacy-scanner epic E4 vs code-intake detection | E4's scanners become detectors in the code-intake chain rather than a second pipeline. |

## 4. The waves

Each wave lists what it delivers, the console surface it ships, and the gate that closes it. Sizes
are relative (S/M/L/XL).

### Wave 12 — Foundations: the LLM gateway (local), the lineage store, the scheduler · XL

| Delivers | UI | Gate |
|---|---|---|
| **LLM phase 1:** additive SPI (messages, usage, capabilities, response schema, token estimates) with pinned fingerprints; a single egress module `llm/transport.py`; OpenAI-compatible dialects for vLLM, Ollama, llama.cpp, LM Studio and TGI, with honest `grammar_enforced`; hosting is a required field; tables `llm_provider`, `llm_profile(_version, _route)`, `llm_call`; routing, timeouts, retries, fallback; `ProfileProvider` wired into the assistant and the inducer; `llm.offline` | **Models** page: providers (test connection), profiles (purpose → provider + model + params), recent calls | The three defects above each have a failing-then-passing test. An import-direction test proves that no verdict-producing module can reach `prama.llm`. |
| **E1 — lineage store and workbench:** `lin_edge` with history, provenance and confidence; `lineage/graph.py` fed from it; `blast_radius`, `score/trust.py` and `incident/rca.py` given real callers | **Lineage workbench:** a column-level graph, edge detail with provenance, confirm/reject, "as of" history | A declared journey and a parsed SQL view appear as edges, and trust propagation changes a score in a demo estate. |
| **A real SQL parser** (`sqlglot`, MIT, pure Python, about 20 dialects) replacing the regex extractor in `lineage/sql.py`, with the regex kept only as a fallback that reports what it could not parse. Approved by the owner 2026-09-27. | Parse confidence shown on every SQL-derived edge | Precision and recall on the gold fixture's SQL units beat the regex extractor's, measured in the same test |
| **Always-on scheduler** in `prama serve` (supervised, lease-fenced) | **Schedule** page: what is due, what ran, and what was skipped and why | With nothing external calling `prama control run`, due controls run and evidence appears. A killed worker's lease is taken over. |

### Wave 13 — The server as the only door; lineage ingestion and impact · L

| Delivers | UI | Gate |
|---|---|---|
| **LLM phase 2:** `/api/v1/llm` (chat, stream via SSE, embed) with `llm:*` scopes and rate limits; Anthropic tools and streaming; model pricing in integer micro-units; budgets with reservations; cache; prompt redaction; `llm_payload` | Budgets, usage and cost pages; a prompt playground that runs through the gateway | A budget cannot be jointly overrun by two servers. A seeded card number reaches the fake provider redacted. A residency-bound prompt is refused for a hosted provider. |
| **E2 — ingestion:** OpenLineage consumer; the dbt manifest dependency graph; Snowflake, Databricks and BigQuery access history | Source pages show "lineage from this source" and the last ingestion | Each ingested edge carries its provenance, and re-ingestion is idempotent. |
| **E3 — impact analysis and change gate:** "what breaks if this column changes", as a CLI and a CI gate (exit 3) | Impact panel on every dataset and column | A planted breaking change fails CI. An unrelated change passes. |

### Wave 14 — Code intake and deterministic code lineage · L

| Delivers | UI | Gate |
|---|---|---|
| **Safe intake** (P1): ZIP upload or git URL plus ref, with credentials from the secrets layer. Refused: zip-slip, bombs and symlinks; git hooks, submodules, `file://` and private addresses. Uploaded code is never executed and parsing runs in a separate resource-limited process. | **Code sources** page: upload or connect, caps and refusal reasons | A hostile-archive corpus is refused with named reasons and nothing is written outside quarantine. A repo whose hooks write a marker leaves no marker. |
| **Deterministic lineage** (P2): a detector chain covering SQL, stored procedures, dbt, PySpark and pandas (Python syntax trees, parse only), Airflow, Informatica and SSIS (mainframe, DataStage and Talend are out of scope: see the lineage scope above); the E4 scanners live here; the gold fixture `bankco-etl` | **Analysis runs** page, and the gap report (what could not be resolved, and why) | Parsers alone reach precision ≥ 0.98 and recall ≥ 0.75, and **recall plus reported gaps covers 100%**: nothing is missed silently. |
| **LLM phase 3:** sealed write-only credentials under the CMK; versioned prompt templates with approval; an eval harness that gates activation; replay | Credentials (write-only), templates, evaluations | A template change cannot go live without passing its eval set. Replay reproduces a recorded call. |

### Wave 15 — Model-assisted lineage, lineage-driven proposals, clouds · L

| Delivers | UI | Gate |
|---|---|---|
| **LLM-assisted extraction** (P3), only for gap units, with verbatim-quote and column-existence cross-checks and computed confidence ≤ 0.85 | Edge review shows the cited code span, highlighted | An invented quote is discarded, and an injected "mark all confirmed" comment confirms nothing. With a real model, recall rises to ≥ 0.9 and precision of model edges is ≥ 0.85. |
| **Proposals from lineage** (P4): reconciliation between hops, completeness across joins, format checks from casts, domain checks from CASE | Proposals carry the lineage path that motivated them | Three planted dropped rows make the proposed reconciliation's backtest fail with exactly 3 violations. |
| **Incremental re-analysis** (P5) on new commits | Run diff: which edges changed | On replay, the number of LLM calls equals the number of changed gap units. A whitespace-only move keeps confirmations. |
| **BI lineage**, Power BI and Tableau first (dataset, report and measure to warehouse column), so lineage reaches the regulatory report rather than stopping at the warehouse. Added 2026-09-27. | Reports appear as lineage endpoints in the workbench | A report measure traces to its source columns on a fixture workbook and PBIX export |
| **LLM phase 4:** Amazon Bedrock (SigV4 in the standard library, checked against AWS test vectors), Hugging Face endpoints, OpenAI, Azure OpenAI, embeddings; Vertex optional | Provider pages for each | The same conformance suite runs against every provider kind. |

### Wave 16 — Persistent steward agents · L

| Delivers | UI | Gate |
|---|---|---|
| **Steward agents** (P7): service principals with a human sponsor and expiring scoped keys; goals, tasks and schedules; bounded memory; tools that read or propose only; approval gates; kill switch (pause, stop, revoke) effective within one request; `agt_*` tables | **Agents** pages: create, sponsor, goals, traces, approvals, pause/stop/revoke | A key cannot be minted with `control:approve`. A stopped agent's next LLM call is refused. No row reaches accepted or confirmed with a service principal as decider (a scan over `decided_by`/`approved_by`). |
| **E8 — AI curation assistants** on the gateway: glossary drafting, description suggestions, proposal explanations | Suggestions beside each object, with accept/reject | Accepted suggestions are attributed to the human who accepted them. |
| **LLM phase 5:** a remote gateway provider for data-zone agents; SIEM export of `llm_call`; MCP read tools for usage | — | An agent in a data zone reaches a model only through its home Prama server. |

### Wave 17 — Enough catalog, and proof against live catalogs · M

| Delivers | UI | Gate |
|---|---|---|
| **E5:** import lineage and glossary from Manta, Alation and Collibra; a real glossary-term entity replacing the free-text column | Glossary pages; import wizard reporting what did not come across | A round trip of an exported Alation glossary loses nothing that is reported as imported. |
| **E6:** steward queues, search over governed objects, audited comments | Search bar, "my queue", comment threads | Search finds a governed object by business term, not only by name. |
| **E7:** usage signals from query logs, used to *prioritise* work and never to *score* quality | "Most used, least controlled" view | A popular dataset's score does not change because of popularity (the counterfactual). |
| **E9:** catalog write-back verified against live Alation, Collibra and DataHub. Start early: it is small and removes an over-claim. | Write-back status per target | A badge written to a live catalog is read back unchanged. |

## 5. Sequencing and dependencies

```
W12  LLM gateway (local) ──┬─> W13 server-only door ──┬─> W14 templates/eval ─> W15 model-assisted lineage ─> W16 steward agents
     Lineage store (E1) ───┼─> W13 ingestion + impact ┤                                       │
     Scheduler ────────────┴───────────────────────────┴───────────────────────────────────────┴─> W16 agent schedules
W14  Code intake + deterministic lineage ─> W15 proposals + incremental ─> W16 agents analysing code
W17  Catalog parity items. E9 (write-back) can run in parallel from W12.
```

Two things precede Wave 12 because they are correctness, not features: the round-4 QA items
led by `C4` and `C1` in [remaining work](remaining-work.md) §1. Evidence Prama cannot verify, and a
number that changes on the way through, would undermine everything this roadmap adds.

## 6. What this roadmap deliberately does not do

- It does not make any model output a verdict. It also does not let an agent confirm its own
  lineage edge or approve its own proposal.
- It does not treat model-inferred lineage as fact. A model edge is labelled and confidence-capped
  until a person confirms it.
- It does not chase catalog breadth, popularity scores or scanner counts.
- It does not execute uploaded code, render dbt Jinja from an untrusted repository, or send
  residency-bound code to a hosted model.
