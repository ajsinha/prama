<!-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE. -->

# 23 — Intelligence and Lineage: the roadmap after Wave 11

> Written 2026-09-27. This extends [19 — Implementation Roadmap](19-implementation-roadmap.md) with Waves
> 12 to 17. Once work starts, 19 records the status markers; this document records the plan and the
> reasons for it.

Three questions are answered here, each with a design note behind it:

| Question | Design note |
|---|---|
| How does Prama shrink the gap to **IBM Manta** (lineage) and **Alation** (catalog) without losing its own thesis? | [design/gap-manta-alation.md](design/gap-manta-alation.md) |
| How does Prama call **any LLM**? Local (Qwen, Llama and Mistral via vLLM, Ollama, llama.cpp, LM Studio, TGI) or remote (Hugging Face, Anthropic, Amazon Bedrock, OpenAI or Azure), with budgets, residency, redaction and audit. | [design/llm-gateway.md](design/llm-gateway.md) |
| How does Prama take an **application ZIP or a git location**, infer its ETL lineage, and propose DQ checks? And how do **Prama agents** become persistent AI agents that do this analysis by calling the Prama server? | [design/code-lineage-and-steward-agents.md](design/code-lineage-and-steward-agents.md) |

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
  - Today: **precision 1.00, recall 0.83**. The two missed edges are in the PySpark job, which is
    reported as unread.
- **Still to do in Wave 14:**
  - a PySpark and pandas reader (Python syntax tree, parse only), which lifts recall on the
    fixture;
  - Airflow task lineage and COBOL/JCL;
  - templates and evaluation governance.
- **Deferred, each to the phase that first needs it:**
  - The transport-module extraction, multi-turn messages and JSON-schema validation go to
    Wave 13, with the new wire formats.
  - `ProfileProvider` is ready, but no production builder constructs the assistant or inducer
    yet. The first will be the Wave 16 agents.

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
| **Deterministic lineage** (P2): a detector chain covering SQL, stored procedures, dbt, PySpark and pandas (Python syntax trees, parse only), Airflow, Informatica, SSIS, DataStage and Talend, COBOL/JCL and shell; the E4 scanners live here; the gold fixture `bankco-etl` | **Analysis runs** page, and the gap report (what could not be resolved, and why) | Parsers alone reach precision ≥ 0.98 and recall ≥ 0.75, and **recall plus reported gaps covers 100%**: nothing is missed silently. |
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
