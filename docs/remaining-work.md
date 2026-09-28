<!-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE. -->

# What is left to build

Written 2026-09-27. The forward plan for AI, lineage and agents is [23](23-intelligence-and-lineage-roadmap.md). Collected from `docs/19-implementation-roadmap.md` (the ◑ and ⏳ rows and the
"Not done" column), from `qa/HANDOVER.md`, and from defects found while adopting Maya's console
pages. **The roadmap and the handover remain the authorities.** Where this list and one of them
disagree, the list is the stale one; correct it or delete it, never both.

Ordered by what I would take first. Each item says why it matters.

## 1. Correctness and QA (round 4 left open)

| # | Item | Why it matters |
|---|---|---|
| 1.1 | ~~**Data-stack `C4`: Prama's own evidence verifier disagrees with the independent one**~~ **done** (Q-116/117/118) | Two verifiers disagreeing undermines the evidence ledger's whole credibility |
| 1.2 | ~~**`C1`: `reference._arithmetic` uses `float` where `library._number` uses `Decimal`**~~ **done** (Q-116/117/118) | Sibling of `Q-115`, the only finding that gave a wrong verdict on real data |
| 1.3 | ~~**`C22`: `%g` loses precision on render** (`PQL-141`, P1)~~ **done** (Q-116/117/118) | The same family: a number quietly changing on the way through |
| 1.4 | ~~`C9`: `SqlCompiler` keeps per-call state on the instance (`BE-034`, `BE-037`)~~ **done** (Q-119/120/121) | Correctness risk under any reuse |
| 1.5 | ~~`C20`: unbounded recursion reachable from an HTTP endpoint~~ **done** (Q-119/120/121) | Security-adjacent; must be a bounded refusal, not a `RecursionError` |
| 1.6 | ~~`C23`: the type checker does not walk every expression-bearing field~~ **done** (Q-119/120/121) | A coverage gap in the checker |
| 1.7 | Remaining language-stack batches `C2 C5 C14 C16 C17` | Triaged but not yet worked |
| 1.8 | Interface stack `CLI-081`, `CLI-185` | Never reproduced in round 3; still open |
| 1.9 | The 184-case one-off tail (77 of them P1) | Not yet triaged into batches |
| 1.10 | Then the full QA regression | Closes round 4 |
| 1.11 | ~~**Two guards that do not exist yet:** a differential guard between the Excel surface and the PQL parser (the "same question answered twice" cluster, five findings deep), and a narrowly scoped vacuous-assertion lint~~ **done**: the differential guard found Q-122 on its first run; the vacuous-assertion lint is a ratchet over 33 baselined tests | Building the guard beat fixing the ninth instance by hand last round |
| 1.12 | **New:** `prama control check` on `CHECK CONCEPT …` prints "nothing is known about " with an empty name | A lint that names nothing cannot be acted on |
| 1.13 | `Threshold.render()` drops the comparator for a rate (`<` re-reads as `<=`) | Unreachable from the parser today; reachable from anything building a threshold in code |

## 2. Execution: nothing runs on its own

| # | Item | Why it matters |
|---|---|---|
| 2.1 | ~~**An always-on scheduler inside `prama serve`** (supervised, lease-fenced, using `prama.schedule`)~~ **done** in Wave 12 | Today evidence arrives only when cron or CI calls `prama control run`; that is the biggest functional gap in the product |
| 2.2 | Re-querying the source for fresh failing rows in sample drill-down | Needs the connector query path |
| 2.3 | Previews against a warehouse rather than a local DuckDB/SQLite file | The studio cannot preview on the estate it governs |
| 2.4 | `DEC-17` streaming benchmark: the transport half | The evaluation half is measured; the transport is open |

## 3. Console (Wave 9 "Not done")

- Single sign-on in the console: `prama.security.oidc` verifies ID tokens, but no sign-in flow uses it.
  MFA and custom roles and groups are also absent; there are only four built-in roles. Maya has all three.
- Cytoscape drag-to-declare (W9.3), attribute editing, relationship drawing, attribute-level
  relationship editing.
- Attribute-level suggestions: concepts, value domains, CDE marks.
- Scorecard charts wired to measurements, so they show real numbers.
- Batch work: approving proposals, disposing of incidents, exporting a period's packs as one bundle.
- The reconciliation certificate signed off from the break workbench, and an asymmetric
  signature on attestations.
- A live catalogue for the language server; go-to-definition and rename.
- MCP over streamable HTTP (stdio only today).
- Retention tiering and WORM export wired to the persisted evidence store.
- A keyboard-only walkthrough and a screen-reader pass (these need a person).

## 4. Connectors and integrations

- **ODBC connector:** not built.
- **Snowflake:** written but never run against an account.
- JDBC dialects that are code-complete but unverified: Oracle, SQL Server, DB2, Teradata, Redshift,
  Databricks, Synapse, Trino and BigQuery.
- Catalog write-back adapters (Collibra, Alation, DataHub) never run against a live server.
- SCIM wire endpoints; Vault and CMK never run against a real service.
- W8.9 legacy scanners: the SQL dialects are verified; the ETL shapes are only configurable.

## 5. Enterprise and GA (Wave 10 acceptance, all still open)

- All nine superiority gates (docs/15 §7), each met or explicitly missed.
- An air-gapped install verified end to end, with a local model and no egress.
- Streaming SLOs: p95 detection ≤ 60 s and ≤ 5 ms added p99 at the target throughput.
- The independent RDARR test script passing 100%, at a client site.
- ≥ 45 certified connectors.
- DQ-Bench and FinDQ-Bench published with competitor baselines. External tools are named but not
  run, and the scale datasets are still to come.
- The Kubernetes Operator run against a real API server (today it is tested in memory only).

## 6. Cross-wave

- **Benchmark regression in CI:** nothing compares a run with a stored baseline, so a regression
  cannot block a release.
- Weekly security scanning, SBOM and dependency updates, and parser fuzzing.
- Soak and chaos drills each wave.
- Gates Maya has that Prama does not yet have:
  - a coverage floor;
  - an OpenAPI snapshot lock;
  - an import-cycle check;
  - a SAST (bandit) stage;
  - a ruff complexity and function-length ceiling (C90 and PLR0915).

  Adopting any of these will first need a sweep of existing code to get under the new limit.

## 7. Intelligence roadmap (docs/23), still open

- **Wave 15:** Tableau lineage, only if a design partner asks.
- **PQL:** `CLASSIFY` rules on `RECONCILE` (the engine's built-in classification is used today),
  a `WHERE` on reconciliations, and PQL forms for row-count, aggregate and roll-forward parity,
  which are still specifications.
- **Wave 17:**
  - correlation from data-side signals: value overlap and query co-access fed into the built,
    metadata-based correlation;
  - AI over business context: embedding search and "find data of interest" (keyword search is
    built);
  - E6: steward queues and comments (search is built for metadata);
  - E7: usage signals;
  - E9: write-back verified against live catalogs, which needs live catalogs.
- **Delegates:** Arrow record batches in place of JSON lines.
- **Out of scope by decision (2026-09-27):** mainframe code (COBOL, JCL, copybooks), and DataStage,
  Talend, Ab Initio and SAS.

