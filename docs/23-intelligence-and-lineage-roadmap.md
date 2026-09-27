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

**Nothing in Waves 12–17 is built yet.** What exists today, and what these waves build on:

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
