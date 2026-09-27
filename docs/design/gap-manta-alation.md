<!-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE. -->

> Design note behind [23 — Intelligence and lineage roadmap](../23-intelligence-and-lineage-roadmap.md). Written 2026-09-27. Where this note and doc 23 disagree, doc 23's reconciliation wins.

# Closing the Manta and Alation gap: a strategy

Written 2026-09-27. Evidence paths are relative to `src/prama/` unless noted. Competitor picture:
IBM Manta ships both standalone and as the lineage engine of watsonx.data intelligence, with 50+
code-level scanners (Informatica, DataStage, Ab Initio, SAS, Cognos, MicroStrategy), OpenLineage
consumption added in 2025–26, and lineage that survives endpoint renames (identity keys). Alation
is now an "Agentic Data Intelligence Platform". It has the Behavioral Analysis Engine, a Data
Quality Agent, Curation Automation, CDE Manager, Agent Studio and, since July 2026, the "AIOS"
agent architecture.

## 0. The finding that reorders everything

Prama's lineage is **a tested library that nothing uses**. `lineage/graph.py` (typed edges,
attenuation, cycles, `blast_radius`), `lineage/sql.py` (a regex-based column extractor that
reports what it could not parse) and `lineage/scan.py` (T-SQL/PL/SQL/DB2 unwrapping, and
configurable XML mapping readers for PowerCenter, DataStage and SSIS) are real and good. But:

- **No persistence.** `schema/sqlite.sql` has no lineage table. The tables are `sem_*`, `ev_*`,
  `ctl_*`, `att_*` and `rec_*`. Only `sem_journey` holds business lineage.
- **No ingestion.** OpenLineage is *emitted* (`telemetry/lineage.py`) but never consumed. The dbt
  importer (`importers/dbt.py`) reads tests, not the `depends_on` graph. Nothing reads warehouse
  access history or query logs.
- **No surface.** No CLI verb, no API route and no console page refers to `prama.lineage`.
  `blast_radius` has no caller outside the package. `score/trust.py` and `incident/rca.py` accept a
  graph, but only tests build one.
- `docs/19` marks W8.7 "lineage ingestion and graph store ✅". Going by the code, that is
  over-claimed.

So Prama's lineage gap to Manta is **not** "45 missing scanners". It is "the product has no lineage
a user can see". Trust propagation, the claim in `docs/21` #4 that no one else has, cannot be
demonstrated in a deal today. Epic 1 below is therefore the precondition for every lineage claim.

## 1. Capability matrix

Gap sizes: none, S, M or L.

| Capability | Manta | Alation | Prama today (evidence) | Gap | Strategy |
|---|---|---|---|---|---|
| Column-level lineage model | ●● | ● | `lineage/graph.py`, with typed `Transform`, attenuation and cycles. In memory only | M | **Build**: persist it and put a UI on it |
| SQL / view lineage parsing | ●● (many dialects) | ● | `lineage/sql.py`, hand-written. Reports ambiguity and gaps | S–M | **Build**: add a real parser backend (sqlglot) behind the existing `Extraction` contract |
| Stored procedures (T-SQL, PL/SQL, DB2) | ●● | ◐ | `lineage/scan.py::ProceduralSqlScanner`, verified on syntax | S | **Build**: dynamic-SQL and control-flow coverage reporting |
| Legacy ETL (PowerCenter, DataStage, SSIS, Ab Initio, SAS) | ●● | ○ | `XmlMappingScanner`: shapes are configurable, not verified against real exports | L | **Build 3, integrate the rest**. Verify on real exports from design partners |
| BI lineage (Cognos, BO, Power BI, Tableau) | ●● | ● | absent | L | **Integrate** (Manta/Alation/OpenLineage import). Build one semantic layer at most |
| COBOL / mainframe lineage | ● | ○ | COBOL/EBCDIC *reader* in `packs/banking`. No lineage. `sem_journey` holds business-declared chains | M | **Deliberately not compete** on scanning. Journeys plus copybook-level field mapping |
| OpenLineage / dbt / warehouse-history ingestion | ● | ● | Emission only (`telemetry/lineage.py`) | M | **Build**: cheap, and it feeds everything else |
| Import of a competitor's lineage | n/a | n/a | absent | M | **Integrate**: the Manta export/API and Alation lineage become "declared" edges with provenance |
| Impact analysis (downstream blast radius) | ●● | ● | `LineageGraph.blast_radius`, no caller | M | **Build**: the UI and the pre-change check |
| Lineage history / versioning | ● (revisions) | ◐ | `sem_*_version` pattern exists for declarations. None for lineage | M | **Build**: bitemporal edges on the same pattern |
| Business / declared lineage | ○ | ◐ | `sem_journey`, `api/routes/graph.py` `/journeys` | none | Ahead. Keep |
| Trust propagation along lineage | ○ | ○ | `score/trust.py` (semirings) | none (unique) | Wire to persisted lineage |
| Search across assets | ◐ | ●● | Estate map "Find" box only (`web/templates/estate/map.html`) | L | **Build a thin version**: search over what Prama governs, not the estate at large |
| Business glossary | ○ | ●● | a `glossary_term VARCHAR(255)` string on `sem_attribute`. Concepts in `sem_concept` | M | **Integrate** (import the Alation glossary into concepts). Build term↔concept binding |
| Stewardship / ownership | ○ | ●● | `owner_id` on domains and attributes. Four built-in roles | S–M | **Build**: steward assignment and queues on declarations |
| Curation workflows / approvals | ○ | ● | `semantic/policy.py` (SoD for Tier 1), proposals queue (`web/templates/proposals/queue.html`) | S | Ahead on rigour. Add batch approve (already in remaining-work §3) |
| Behavioural analysis / popularity | ○ | ●● | absent. `discover/relationships.py` accepts a `co_access` count nobody supplies | L | **Integrate + narrow build**: query-log ingestion only to rank CDE candidates and control priority |
| Query-log ingestion | ◐ | ●● | absent | M | **Build** (Snowflake, BigQuery, PostgreSQL `pg_stat_statements`, Databricks) |
| Auto-classification / PII | ◐ | ● | `classify/semantic.py` (checksum → codelist → pattern → name → model cascade) | none | Ahead (evidence-backed) |
| Profiling | ◐ | ● | `profile/` | none | Ahead |
| Policy center (access/usage policy) | ○ | ● | `semantic/policy.py` is *approval* policy. `masking_policy` column | M | **Deliberately not compete** on access policy. Integrate with Purview/Immuta |
| Data quality integration | ○ | ● (DQ Agent) | Core product | none | Ahead. Write-back (`integrate/vendors.py`) not live-verified |
| Conversations / comments on assets | ○ | ● | absent (no comment table) | M | **Build narrowly**: threads on declarations, incidents and attestations, audited |
| Connected Sheets (Excel/Sheets live data) | ○ | ● | absent | M | **Deliberately not compete** on data access. Maybe later: a read-only "quality status" add-in |
| AI curation / documentation agent | ◐ (AI Lineage Assistant) | ●● | `llm/spi.py`, `llm/providers.py`, `induce/llm.py`, `assistant/agent.py`, MCP stdio (`mcp/server.py`) | S–M | **Build on the existing SPI**: descriptions, glossary mapping, lineage-gap explanation. Never verdicts |
| Catalog write-back | n/a | n/a | `integrate/catalog.py`, `integrate/vendors.py` (Collibra/Alation/DataHub, never run live) | S | **Integrate**: verify live. This is the distribution channel |
| Connector breadth for metadata | ●● (50+) | ●● (100+) | JDBC dialects mostly unverified (`remaining-work` §4) | L | **Neutralise** through OpenLineage and catalog import |

## 2. Where not to chase parity, and where Prama must

**Do not chase:**

- **Catalog breadth and search as a destination.** Alation's value is a decade of curation UX
  across every asset, whether governed or not. Prama's thesis is that it governs *declared* assets
  with evidence. Searching everything would make Prama a worse Alation and pull the roadmap away
  from controls. Concede this, and write quality back into the catalog (`docs/21`, G4).
- **Popularity as truth.** A table's popularity is not evidence of its quality. Use behavioural
  signals only to *prioritise* (which columns are CDE candidates, which controls to write first).
  Never use them as a score input without a calibrated link.
- **Scanner count.** Fifty scanners is a permanent tax. The business-owned answer is Journeys: a
  mainframe job described in one sentence by its owner is lineage no scanner reaches.
- **Access policy / policy center, and Connected Sheets.** These are data-access products, and the
  buyer already owns one.
- **AI-authored lineage as fact.** Alation and IBM both market AI-inferred lineage. In Prama a
  model may *propose* an edge, which lands as a proposal with provenance and is re-validated
  against parsed code or data. It never becomes a trusted edge on model output alone (CLAUDE.md
  rule 6, `CON-007`).

**Must have, to be buyable by a Tier-2 bank.** This is the checklist a Tier-2 data office runs
under BCBS 239 P2, P3 and P6 and SR 11-7-style model inventories:

1. **Visible, persisted, column-level lineage from CDE to regulatory return**, with impact
   analysis. Any buyer will ask for this in the first demo, and today Prama cannot show it.
2. **Lineage ingestion from what they already run**: OpenLineage, dbt, and warehouse access history
   (Snowflake/Databricks at Tier 2), plus import of Manta/Alation/Collibra lineage where it exists.
3. **Stored-procedure lineage verified on real code.** Tier-2 banks live in SQL Server and Oracle
   procedures more than in Ab Initio, so this is the scanner that matters.
4. **Lineage history**, meaning what the path was on the reporting date. An auditor asks about
   *last quarter's* return, not today's.
5. **A glossary that binds to concepts and CDEs**, imported from their catalog, not retyped.
6. **Steward ownership and queues**, so that "business-owned" is visible in the UI.
7. **Proven write-back to Alation or Collibra.** It must run against a live sandbox, not an
   injected transport.

## 3. Ranked gap-closing epics

Two dependencies recur throughout.

- **LLM layer.** `llm/spi.py` already provides hosting classes, residency egress (`security/egress`),
  grammar-constrained requests and provenance. The shortfall is an *orchestration* layer on top of
  it: task templates, an evaluation harness, cost and latency budgets, and a "proposal-only" sink.
  Call it E-LLM. It is a small prerequisite, not a rewrite.
- **Code-to-lineage analysis.** Everything that parses code emits `lineage.sql.Extraction`, a
  graph plus gaps. Every scanner plugs into `lineage.scan.Scanner`, registered through an entry
  point, as CLAUDE.md requires.

### E1. Lineage store and lineage workbench (rank 1, L)
- **Goal.** Make the existing lineage library a product.
- **Scope.** Add `lin_edge` and `lin_source` tables to *both* schema files. They use only the four
  permitted types. Edges are bitemporal (`valid_from` / `valid_to` / `recorded_at`, VARCHAR(32)),
  with provenance: `parsed`, `ingested`, `declared` or `imported:<vendor>`. A coverage/gap row
  exists per source unit. Add a `LineageDao` under `db/`, a service, API routes, and a CLI
  (`prama lineage scan|ingest|show|impact`). Wire `score/trust.py` and `incident/rca.py` to the
  persisted graph.
- **Dependencies.** None beyond the existing `prama.lineage`. This epic blocks E2–E6.
- **UI.** A Lineage page with a Cytoscape column-level graph. It has an upstream/downstream toggle,
  edge styling by `Transform` and by provenance, and a gap overlay ("37% of `pkg_finrep` not
  parsed"). There is a per-dataset lineage tab on `estate/dataset.html`, and a Sources admin page
  (scanners run, coverage, last run).
- **Acceptance.**
  1. Scan a fixture T-SQL procedure, restart the server, open the page. The edge `stg.a.amt →
     rpt.finrep.line_23` renders from the database.
  2. Take an upstream control that fails on real rows. The downstream report's trust drops by the
     attenuated amount shown on the page, and the counterfactual (delete the edge) restores it.
  3. Unparsed statements appear as gaps in the UI and the API, never silently.
  4. `prama db verify` passes on SQLite and PostgreSQL.

### E2. Ingestion: OpenLineage, dbt, warehouse history (rank 2, M)
- **Goal.** Get lineage from what the bank already runs, with zero scanning.
- **Scope.** An OpenLineage HTTP receiver (column-lineage facet) and a dbt `manifest.json` /
  `catalog.json` graph reader (`depends_on` plus SQL through `lineage/sql.py`). Also access-history
  readers for Snowflake `ACCESS_HISTORY`, the Databricks Unity lineage system tables, and BigQuery
  `INFORMATION_SCHEMA.JOBS`. Each reader is a plugin behind an ABC with conformance tests.
- **Dependencies.** E1. Connectors (remaining-work §4).
- **UI.** Sources admin: add a source, test it, schedule it, and see the last-ingest edge delta.
- **Acceptance.**
  1. POST a real OpenLineage event captured from Marquez/Airflow, and its column edges appear.
  2. Replay the same event and no duplicate appears (idempotent).
  3. A dbt manifest from jaffle_shop produces the known edge set exactly (golden file).

### E3. Impact analysis and change gate (rank 3, M)
- **Goal.** Answer "what breaks if I change this column", and fail CI on it.
- **Scope.** `blast_radius` via API/CLI/MCP. `prama lineage impact --diff before.sql after.sql`
  lists affected CDEs, controls, attestations and regulatory lines. The contract CI gate
  (`prama contract check`) gains a lineage mode.
- **Dependencies.** E1, and E2 or E4 for coverage.
- **UI.** An impact panel reached from any column: an affected list ranked by attenuation, and the
  Tier-1 CDEs and open attestations it touches. It exports an evidence-sealed impact report.
- **Acceptance.**
  1. Dropping a column feeding FINREP line 23 exits 3 and names the attestation at risk.
  2. A filter-only edge (attenuation 0) is listed as unaffected, with the reason.

### E4. Verified legacy scanners (rank 4, L)
- **Goal.** Close G2 where Tier-2 banks actually live.
- **Scope.**
  1. Stored procedures: add dynamic SQL (`EXEC`/`EXECUTE IMMEDIATE` with a literal, reported
     otherwise), temp tables, `MERGE`, cursors. Swap the regex core for a sqlglot backend behind
     `Extraction`, keeping the gap confession.
  2. SSIS `.dtsx` and PowerCenter XML, verified on real anonymised exports from two design
     partners.
  3. One BI layer, Power BI (`.pbit`/TMDL), because Tier-2 banks run Microsoft.
  4. COBOL copybook field-to-field mapping as a Journey-step enrichment, not a scanner.
- **Dependencies.** E1. A code-to-lineage harness: a corpus of real procedures with hand-labelled
  edges, and precision/recall per construct published with `prama bench`.
- **UI.** The scan results view: per-unit coverage, and click-through to the source line behind
  each edge (provenance to file:line).
- **Acceptance.**
  1. On the labelled corpus, edge precision is ≥ 0.95 and recall is reported with no floor hidden.
  2. Every edge links to a source line that exists.
  3. A deliberately corrupted export produces a loud coverage failure, not an empty graph.

### E5. Competitor lineage and glossary import (rank 5, M)
- **Goal.** Consume Manta, Alation and Collibra instead of losing to them.
- **Scope.** Import Manta through its export and Open Manta API (or OpenLineage from watsonx.data
  intelligence). Import Alation lineage plus glossary terms through its REST API, and Collibra
  likewise. Imported glossary terms bind to `sem_concept` and attributes through a new term
  entity, which *replaces* the free-text `glossary_term` string (in the schema file, no
  migration). Imported edges carry `imported:<vendor>` provenance. Where Prama's own parse
  disagrees, both are kept and the disagreement is surfaced.
- **Dependencies.** E1. Live-verified vendor transports.
- **UI.** An import wizard (source, mapping preview, dropped items listed) and a conflicts view
  (their edge vs our parse).
- **Acceptance.**
  1. The import from a live Alation sandbox round-trips: terms imported, controls compiled from the
     bound concept, and a badge written back to the same Alation object and read back.
  2. The import states what it dropped.

### E6. Stewardship, search and conversations: "enough catalog" (rank 6, M)
- **Goal.** Make business ownership visible without building a catalog.
- **Scope.**
  - Steward assignment per domain, dataset or CDE, with a "my queue" of proposals, drifted
    bindings, incidents and attestations due.
  - Faceted search over *governed* objects (datasets, attributes, concepts, controls, incidents)
    using SQL `LIKE`/FTS through the DAO, dialect-isolated in `db/dialects.py`.
  - Comment threads on declarations, incidents and attestations, written to the audit trail.
  - Batch approve.
- **Dependencies.** Custom roles and groups (remaining-work §3).
- **UI.** The Steward home, a global search bar with facets, and comment panes.
- **Acceptance.**
  1. A steward sees only their queue items.
  2. A comment appears in the audit export with author and time.
  3. Search finds a CDE by concept synonym imported in E5.

### E7. Usage signals from query logs (rank 7, M)
- **Goal.** Get the one piece of behavioural analysis that serves the thesis: priority, not truth.
- **Scope.** Query-log ingestion (the same readers as E2). Per-column read counts and distinct
  consumers feed `discover/relationships.py` co-access (currently unsupplied), CDE-candidate
  ranking, and the ordering of control proposals. They never feed a score.
- **Dependencies.** E2.
- **UI.** A "used by" panel on datasets, and "high-use, no controls" as a coverage gap on
  `estate/gaps.html`.
- **Acceptance.**
  1. Seeded query logs rank the fixture's hot column first.
  2. The architecture test proves no score module imports the usage module.

### E8. AI curation assistants on the LLM layer (rank 8, M, after E-LLM (S))
- **Goal.** Match Alation's documentation/curation agents and Manta's AI Lineage Assistant, as
  proposals only.
- **Scope.** Draft column descriptions from lineage, profile and classification. Propose
  glossary-term bindings. Propose lineage edges for gaps the parser confessed (for example dynamic
  SQL). Explain an impact result in plain language. All output lands in the proposals queue with
  the prompt provenance of `llm/spi.py::Request`. A proposed edge is marked `proposed:model` and
  excluded from trust propagation until a parse or a human confirms it. Expose the tools over MCP
  streamable HTTP.
- **Dependencies.** E-LLM (task templates, an eval set, a residency-tested self-hosted path), plus
  E1 and E5.
- **UI.** Suggestions inline on the dataset and lineage pages, each with "why", accept/reject, and
  the model and prompt hash.
- **Acceptance.**
  1. With `NullProvider`, every feature degrades to "no suggestion" and nothing breaks.
  2. The layering test proves no model-proposed edge reaches `score/trust.py` unconfirmed.
  3. The suggestion accept rate is measured on a labelled set.

### E9. Live-verified write-back (rank 9, S, but do it early; it is cheap)
- **Scope.** Run the adapters in `integrate/vendors.py` against Alation, Collibra and DataHub
  sandboxes. Add Atlan and Purview. Schedule write-back after each run (depends on the scheduler
  in remaining-work §2.1).
- **UI.** An integrations page showing last write, partial-write report, and assets refused.
- **Acceptance.** A failing control is visible in Alation's UI within one schedule tick, dated,
  with an evidence id that resolves in Prama.

**Sequencing.** E9 and E-LLM (small) run in parallel with E1. After E1, do E2 then E3, which is
the demoable "Manta-lite plus verdicts" milestone. Then E5 and E4 in parallel, then E6, E7 and
E8. This closes the gaps that decide Tier-2 deals (visible lineage, impact, SP scanning, glossary
import, stewardship) while leaving the catalog, access policy, Connected Sheets and scanner-count
gaps deliberately open and loudly conceded.
