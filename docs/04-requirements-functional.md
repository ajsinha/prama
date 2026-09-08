<img src="assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

> ***pramā*** (Sanskrit **प्रमा**) — *valid knowledge: a cognition that is both true and arrived at
> by a reliable means*. Its companion ***pramāṇa*** (प्रमाण) is *the instrument by which valid
> knowledge is obtained*. Prama is that instrument for an organisation's data — it does not decide
> what is true, it is how a belief about data becomes **justified**.
>
> **Declare it. Prove it. Trust it.**


---
# 03 — Functional Requirements

**Identifier scheme:** `FR-<AREA>-<nnn>`.
**Priority:** **P0** required for GA · **P1** competitive parity · **P2** differentiator (post-GA) ·
**P3** research horizon.
**Verification:** T = automated test, D = demo/acceptance, A = analysis/inspection, B = benchmark.

Areas: MET business semantic layer & metadata · CON connectivity · PRF profiling & discovery ·
RUL rule authoring · IND rule induction ·
MON statistical/ML monitoring · EXE execution · REC reconciliation · ERM entity resolution ·
REM remediation · INC incident & workflow · SCR scoring & reporting · ALR alerting ·
LRN learning loop · LIN lineage · CTR contracts & shift-left · UIX user interface ·
CHT conversational · UNS unstructured & AI-readiness · EXT extensibility & APIs ·
PCK domain packs · REF continuous re-examination · ADM administration

---

## 0. Constraints and assumptions

| ID | Constraint |
|---|---|
| CON-001 | Prama is **not** a data catalog. It integrates with OpenMetadata, DataHub, Collibra, Alation, Purview, Unity Catalog, and can operate standalone with a minimal internal registry. |
| CON-002 | Prama is **not** an ETL/ingestion engine. It observes, validates, and (optionally) quarantines; it does not own transformation. |
| CON-003 | Prama is **not** a full MDM hub. It performs entity resolution as a *control*; mastering and survivorship remain with MDM tools (though PQL can express survivorship rules for export). |
| CON-004 | Prama does **not** license third-party reference data (postal, sanctions, securities master). It integrates with providers. |
| CON-005 | Prama is **not** a BI tool. It ships scorecards and embeddable views, and exports to BI. |
| CON-006 | Prama is **not** an APM/log observability platform. It emits OpenTelemetry. |
| CON-007 | **No LLM may emit a pass/fail verdict on data.** LLMs author, explain, summarise, and triage-assist only. All verdicts come from deterministic, versioned, replayable executions. |
| CON-008 | **Data must not leave the customer's trust boundary** by default. Pushdown execution and local/BYO models are the default posture; any egress is explicit, logged, and policy-gated. |

| ID | Assumption |
|---|---|
| ASM-001 | Customers have heterogeneous estates (≥ 5 distinct data platforms) including at least one legacy/mainframe or file-feed source. |
| ASM-002 | Customers can grant read access and limited compute to source systems; write access is rare and never assumed. |
| ASM-003 | Some deployments are fully air-gapped; internet-dependent features must degrade gracefully. |
| ASM-004 | A steward's attention is the scarcest resource in the system; every design must optimise for it. |

---

## A0. Business Semantic Layer & Metadata Authoring (`FR-MET`)

Conceptual design: [03 — The Business Semantic Layer & Data Estate Model](03-business-semantic-layer.md).
**This area is the product's centre of gravity: it is what makes Prama a business tool rather than
an administrator's tool.**

### A0.1 Dataset declaration

| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-MET-001 | Allow a user to declare a **Dataset** through the UI as a first-class business object, independent of any physical source, with business name, description, purpose, owner, steward, technical custodian, domain, and criticality tier. | P0 | D |
| FR-MET-002 | Support a Dataset being bound to any of: a single table/view, a set of tables (union/partitioned family), an entire schema or database, a single file feed, a set of related feeds (header/detail/trailer), a stream/topic, an API endpoint, a report/regulatory return, a registered query, or **nothing yet (unbound)**. | P0 | T |
| FR-MET-003 | Support **unbound datasets**: declared, participating in relationships and the estate map, reported as a connectivity/coverage gap, and bindable later without loss of any declaration. | P0 | T |
| FR-MET-004 | Capture Dataset **grain** in structured form ("one record per X per Y per period") and derive uniqueness/completeness controls from it. | P0 | T |
| FR-MET-005 | Capture Dataset **business identity** (business key attributes) distinct from any physical primary key. | P0 | T |
| FR-MET-006 | Capture **temporality**: snapshot / event stream / append-only / slowly-changing (type) / as-of-dated, with the attributes carrying as-of, effective, and knowledge dates. | P0 | T |
| FR-MET-007 | Capture **expected rhythm**: frequency, arrival window, cut-off time, business calendar, expected volume range, and the declared drivers of volume variation (month-end, trading days, campaigns). | P0 | T |
| FR-MET-008 | Capture **authoritativeness**: golden source / derived / replica / extract / vendor-supplied, and the source-of-truth dataset where applicable. | P0 | T |
| FR-MET-009 | Capture retention, jurisdiction/residency, sensitivity classification, and lifecycle state (proposed/active/deprecated/retired) with effective dates. | P0 | T |
| FR-MET-010 | Version every metadata declaration with full history, author, timestamp, and rationale; support maker–checker approval for changes to Tier-1 datasets. | P0 | T |

### A0.2 Attribute declaration and business interpretation

| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-MET-020 | Allow declaration of **Attributes** (business fields) with business name, definition, and **business interpretation** (sign conventions, inclusions/exclusions, calculation basis). | P0 | D |
| FR-MET-021 | Bind each Attribute to one or more physical columns/fields, optionally through a declared transformation (concatenation, unit conversion, code mapping, extraction from a nested path). | P0 | T |
| FR-MET-022 | Capture per Attribute: semantic type, unit/currency/scale/precision, denominating attribute, value domain (enumerated code set with authoritative reference, range, pattern, or free text), optionality (always / conditional with the condition stated in business terms / optional). | P0 | T |
| FR-MET-023 | Mark Attributes as **Critical Data Elements (CDEs)** and link them to the regulatory or financial-reporting obligations they serve. | P0 | T |
| FR-MET-024 | Capture sensitivity classification and masking policy per Attribute, enforced everywhere the value could surface (samples, alerts, chat, exports). | P0 | T |
| FR-MET-025 | Capture expected behaviour per Attribute (stable / slowly changing / volatile; expected distribution; known legitimate spikes) and use it to parameterise monitors. | P1 | T |
| FR-MET-026 | Link Attributes to business glossary terms, importing from and syncing with external glossaries (Collibra, Alation, Atlan, OpenMetadata, Purview). | P1 | T |
| FR-MET-027 | Support attribute-level ownership distinct from dataset ownership. | P1 | T |

### A0.3 Business concepts and canonical model

| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-MET-040 | Support declaration of **Business Concepts** (Party, Account, Instrument, Trade, Position, Transaction, Balance, Exposure, Product, Customer, …) with typed **Properties**. | P0 | T |
| FR-MET-041 | Allow Datasets to be declared as *about* one or more Concepts, and Attributes to be *mapped to* Concept Properties. | P0 | T |
| FR-MET-042 | Auto-propagate concept-level controls to every mapped attribute across the estate (author once, enforce everywhere). | P0 | T |
| FR-MET-043 | Detect and surface **semantic conflicts**: the same Concept Property mapped to attributes with incompatible definitions, units, or value domains in different datasets. | P1 | D |
| FR-MET-044 | Ship starter concept models in Domain Packs, extensible and overridable per tenant. | P1 | T |
| FR-MET-045 | Export the concept model to RDF/OWL + SHACL shapes, and import from existing ontologies, for customers with semantic-web estates. | P2 | T |

### A0.4 Business relationships

| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-MET-060 | Allow users to declare typed **Business Relationships** between Datasets, at minimum: `REFERENCES`, `RECONCILES_WITH`, `DERIVES_FROM`, `FEEDS`, `MIRRORS`/`REPLICATES`, `AGGREGATES`, `ENRICHES`, `SUPERSEDES`, `SAME_ENTITY_AS`, `TEMPORAL_SUCCESSOR`, `PARENT_OF`/`HIERARCHY`, `MUTUALLY_EXCLUSIVE`, `TOGETHER_COMPLETE`. | P0 | T |
| FR-MET-061 | Express relationship join/match conditions in **business attribute** terms, resolved to physical columns at compile time. | P0 | T |
| FR-MET-062 | Capture per relationship: cardinality, tolerance/materiality, timing offset, filter scope, business description, owner, and criticality. | P0 | T |
| FR-MET-063 | **Automatically derive candidate controls from every declared relationship** (RI, reconciliation, aggregate parity, roll-forward, parity/staleness, duplicate detection, population completeness) and present them for approval with backtest and cost estimate. | P0 | D |
| FR-MET-064 | Allow relationship declaration by direct manipulation on the estate map (draw a line, choose a type, pick keys) as well as by form and by PQL. | P0 | D |
| FR-MET-065 | **Propose** candidate relationships automatically from key-overlap statistics, value-set containment, naming similarity, schema-signature similarity, observed technical lineage, and query-log co-access — presented as "confirm or correct", with the evidence shown. | P1 | B |
| FR-MET-066 | Support N-ary relationships (e.g. a three-way reconciliation) and relationship groups. | P1 | T |
| FR-MET-067 | Detect contradictory or cyclic relationship declarations and warn. | P1 | T |
| FR-MET-068 | Support relationships that cross data sources, formats, and physical technologies without restriction. | P0 | T |

### A0.5 Business processes / data journeys

| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-MET-080 | Allow declaration of a **Data Journey**: a named, ordered business process expressed as a chain of Datasets and Relationships. | P0 | D |
| FR-MET-081 | Compute and report end-to-end journey health, latency, and SLA attainment. | P0 | T |
| FR-MET-082 | Use journeys as the default scope for root-cause analysis (walk backwards) and impact analysis (walk forwards), including where technical lineage is unavailable. | P0 | D |
| FR-MET-083 | Support journey-level scorecards, attestation, and ownership. | P0 | T |
| FR-MET-084 | Allow manual/black-box steps in a journey (a vendor system, a mainframe job, a manual upload) to be declared as nodes with declared expected behaviour. | P0 | T |

### A0.6 Estate map and metadata operations

| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-MET-100 | Provide an **Estate Map** as the primary landing surface: an interactive, business-labelled graph of domains → journeys → datasets → relationships, with live quality state rendered on nodes and edges. | P0 | D |
| FR-MET-101 | Support filtering, grouping, and layout of the estate map by domain, criticality, owner, journey, health, and coverage. | P0 | D |
| FR-MET-102 | Support bulk metadata authoring: spreadsheet import/export (round-trippable), templates, inheritance from concepts and packs, and bulk edit with preview. | P0 | T |
| FR-MET-103 | Import existing metadata from catalogs, glossaries, data dictionaries, ERwin/ER Studio models, DDL, dbt docs, ODCS contracts, and Excel inventories, mapping into the semantic model with a review step. | P1 | T |
| FR-MET-104 | Compute and report a **metadata coverage / estate maturity score** per domain (datasets declared, owners assigned, CDEs identified, relationships declared, journeys mapped, bindings connected) and trend it over time. | P0 | T |
| FR-MET-105 | Suggest the next-best metadata action per domain, ranked by expected quality value ("declaring the grain of these 6 Tier-1 datasets would enable 24 controls"). | P1 | D |
| FR-MET-106 | Provide search over the semantic layer in business language, including synonyms and glossary terms. | P0 | T |
| FR-MET-107 | Maintain full audit history and diff view for every semantic-layer object. | P0 | T |
| FR-MET-108 | Support metadata review workflows and periodic recertification of ownership, criticality, and definitions with due dates and escalation. | P1 | T |
| FR-MET-109 | Expose the entire semantic layer through the API, the CLI, GitOps, and the chat assistant, so it can be authored, reviewed, and version-controlled by any surface. | P0 | T |

---

## A. Connectivity & Ingestion (`FR-CON`)

Full catalogue of sources/formats: [09 — Connectivity & Formats](09-connectivity-and-formats.md).

| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-CON-001 | Connect to relational databases via a uniform connector abstraction with per-dialect SQL generation: PostgreSQL, MySQL/MariaDB, Oracle, SQL Server, DB2 (LUW & z/OS), Sybase ASE/IQ, Teradata, Informix, HANA, Netezza, Greenplum, Vertica, Exasol, Firebird, SQLite. | P0 | T |
| FR-CON-002 | Connect to cloud warehouses: Snowflake, BigQuery, Redshift, Databricks SQL, Synapse/Fabric, Athena, Trino/Starburst, Presto, ClickHouse, DuckDB, MotherDuck, Firebolt, Dremio. | P0 | T |
| FR-CON-003 | Connect to lakehouse table formats with snapshot/version awareness: Delta Lake, Apache Iceberg, Apache Hudi, Paimon — including time-travel reads for reproducible evidence. | P0 | T |
| FR-CON-004 | Connect to object stores and filesystems: S3, GCS, ADLS Gen2, MinIO, HDFS, NFS/SMB, local, SFTP/FTPS, Azure Files. | P0 | T |
| FR-CON-005 | Connect to NoSQL/document/wide-column/graph stores: MongoDB, Cassandra/ScyllaDB, DynamoDB, Couchbase, HBase, Elasticsearch/OpenSearch, Redis, Neo4j, Neptune, TigerGraph, ArangoDB. | P1 | T |
| FR-CON-006 | Connect to streaming/messaging systems: Apache Kafka (+ Confluent), Redpanda, AWS Kinesis, Azure Event Hubs, Google Pub/Sub, Apache Pulsar, IBM MQ, TIBCO EMS, Solace, RabbitMQ, ActiveMQ, NATS, ZeroMQ. | P0 | T |
| FR-CON-007 | Connect to CDC streams and consume change events with operation semantics (I/U/D): Debezium, Oracle GoldenGate, Qlik Replicate, AWS DMS, Fivetran/Airbyte logs. | P1 | T |
| FR-CON-008 | Connect to SaaS/business applications via REST/OData/GraphQL/SOAP with pagination, auth, and rate-limit handling: Salesforce, SAP (OData/RFC/BAPI), Workday, ServiceNow, NetSuite, Dynamics, Murex, Calypso, Finastra, Temenos, FIS, Fiserv, Jack Henry, Avaloq, SimCorp, Charles River, Aladdin. | P1 | T |
| FR-CON-009 | Read structured file formats: CSV/TSV/PSV (with dialect inference), fixed-width, Parquet, ORC, Avro, JSON/JSONL/NDJSON, XML, YAML, Excel (XLS/XLSX incl. multi-sheet & merged cells), Protobuf, Thrift, Arrow/Feather, HDF5, SAS7BDAT, SPSS, Stata, dBase. | P0 | T |
| FR-CON-010 | Read mainframe/legacy formats: EBCDIC-encoded files, COBOL copybook-defined records (including OCCURS DEPENDING ON and REDEFINES), packed decimal (COMP-3), zoned decimal, VSAM extracts, IMS segments. | P0 | T |
| FR-CON-011 | Read EDI and interchange formats: ANSI X12, UN/EDIFACT, HL7 v2/FHIR (for healthcare packs), IDoc. | P1 | T |
| FR-CON-012 | Read financial message standards natively with schema-aware parsing and validation hooks: SWIFT MT (all categories), ISO 20022 / SWIFT MX (pacs, pain, camt, sese, semt, setr, auth, remt…), FIX/FIXML (4.2–5.0SP2), FpML, FINOS/ISDA CDM, XBRL/iXBRL, SDMX, NACHA/ACH, SEPA (pain.001/pacs.008), BAI2, MT940/942, CAMT.053, ISO 8583 (card), FIX Orchestra, MISMO (mortgage), ACORD (insurance). | P0 | T |
| FR-CON-013 | Support compressed and archived inputs transparently: gzip, bzip2, zstd, snappy, lz4, zip, tar, 7z; and encrypted inputs: PGP/GPG, age, S/MIME, password-protected zip. | P0 | T |
| FR-CON-014 | Support arrival-driven ingestion: file landing detection (polling, inotify, S3 events, EventBridge, Azure Event Grid, GCS notifications), manifest/control-file semantics, trailer-record checks, and expected-arrival SLAs. | P0 | T |
| FR-CON-015 | Support scheduled and event-driven pulls with incremental watermarking (timestamp, sequence, LSN/SCN, partition, snapshot version) and exactly-once evidence semantics. | P0 | T |
| FR-CON-016 | Provide connection health checks, credential rotation, connection pooling, per-source concurrency and rate limits, and circuit breaking. | P0 | T |
| FR-CON-017 | Support pluggable connector SDK (Python + JVM) so customers/partners can add sources without a platform release. | P1 | D |
| FR-CON-018 | Support "bring your own query" sources: an arbitrary SQL/API query registered as a virtual dataset. | P0 | T |
| FR-CON-019 | Support read of API/event schemas from registries: Confluent Schema Registry, AWS Glue Schema Registry, Apicurio, JSON Schema, OpenAPI/AsyncAPI, Protobuf descriptors. | P1 | T |
| FR-CON-020 | Support ODBC/JDBC generic fallback for any source not natively supported. | P0 | T |
| FR-CON-021 | Detect and report source-side structural drift (added/removed/retyped columns, changed nullability, changed partitioning, changed file layout) independently of any user-authored rule. | P0 | T |
| FR-CON-022 | Support vector stores and embedding indexes as sources for AI-readiness checks: pgvector, Pinecone, Weaviate, Qdrant, Milvus, FAISS indexes, OpenSearch k-NN. | P2 | T |
| FR-CON-023 | Support geospatial and time-series stores: PostGIS, InfluxDB, TimescaleDB, kdb+/q, OneTick, Prometheus. | P2 | T |
| FR-CON-024 | Sample data from any source using deterministic, reproducible sampling (seeded systematic, stratified, reservoir, block, and TABLESAMPLE pushdown where supported). | P0 | T |
| FR-CON-025 | Support multi-region and multi-account source federation with per-region execution locality enforcement (data never crosses a declared boundary). | P1 | A |
| FR-CON-026 | Provide **UI-driven connector configuration** with guided, typed, per-source-family forms (no raw connection strings required), inline help, and validation — usable by a data architect without a DBA. | P0 | D |
| FR-CON-027 | Test a connection and report the result in business language, including precise, actionable diagnosis of permission gaps, with a one-click access-request workflow routed to the responsible team. | P0 | D |
| FR-CON-028 | Allow a business user to configure a connection **without ever seeing the credential**: they select a vault-managed credential or raise a provisioning request; secrets are never displayed or exportable. | P0 | A |
| FR-CON-029 | Capture an explicit **read policy** per connection: permitted schemas/paths, maximum bytes scanned, permitted execution windows, default sampling strategy, whether failing-row samples may be retained, and masking rules. | P0 | T |
| FR-CON-030 | Offer sampling strategy as an explained business choice (full scan, N%, N rows, stratified by declared segment, most-recent partitions) with the statistical implications stated in plain language. | P0 | D |
| FR-CON-031 | Show a **cost and load preview** before any scan, and enforce a standing budget per connection with alerting on burn rate. | P0 | T |
| FR-CON-032 | Provide a **discovery browser** that presents a source in business-relevant order (size, recency, usage, inferred subject matter) rather than an alphabetical object tree, and supports bulk selection into declared datasets. | P0 | D |
| FR-CON-033 | Propose **physical bindings** for declared-but-unbound datasets using name similarity, column-signature matching, and content fingerprinting, with confidence and evidence. | P1 | B |
| FR-CON-034 | Provide feed-shaped configuration for file feeds: landing location, filename pattern with date tokens, expected arrival window, header/trailer conventions, encoding, layout/copybook, decryption keys, archive policy, and duplicate-delivery handling. | P0 | T |
| FR-CON-035 | Support connector templates and cloning so a new source of a known family is configured in minutes. | P1 | D |

---

## B. Discovery, Profiling & Metadata (`FR-PRF`)

| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-PRF-001 | Auto-discover datasets, schemas, columns, partitions, and physical statistics from any connected source; maintain a versioned asset registry. | P0 | T |
| FR-PRF-002 | Compute column-level profiles: count, null count/rate, distinct count (exact and HLL-approximate), min/max, mean, stddev, variance, skew, kurtosis, quantiles (t-digest/KLL), mode, top-K values with frequencies, empty-string/whitespace counts, and byte/char length distributions. | P0 | T |
| FR-PRF-003 | Compute pattern profiles: regex-class inference, character-class masks (e.g. `AAA-999`), format clustering, and pattern frequency distributions. | P0 | T |
| FR-PRF-004 | Infer semantic types with a hybrid classifier (regex + dictionary + statistical + embedding + LLM-assisted labelling): email, phone, IBAN, BIC, LEI, ISIN, CUSIP, SEDOL, FIGI, MIC, currency code, country code, SSN/NI/PAN/Aadhaar, credit card, postcode, coordinates, timestamps, UUIDs, account numbers, CIF/party IDs, SIC/NAICS, CFI. | P0 | T |
| FR-PRF-005 | Detect PII/sensitive data classes and propose classification tags; integrate with existing classification from catalogs where present. | P0 | T |
| FR-PRF-006 | Discover candidate keys (unique column combinations) using exact and approximate algorithms, with support for composite keys up to a configurable arity. | P1 | B |
| FR-PRF-007 | Discover functional dependencies (exact, approximate/top-k, and conditional), with a minimality guarantee and a confidence/violation-count measure. | P1 | B |
| FR-PRF-008 | Discover inclusion dependencies (candidate foreign keys) within and across data sources, with partial-inclusion scoring. | P1 | B |
| FR-PRF-009 | Discover denial constraints (approximate) over configurable predicate spaces including cross-column inequality predicates. | P2 | B |
| FR-PRF-010 | Discover order dependencies and sequential/monotonic properties (e.g. balances roll forward, timestamps non-decreasing). | P2 | B |
| FR-PRF-011 | Maintain a **metric history store** (Deequ-style) recording every computed metric over time, partitioned by dataset/column/segment, as the substrate for anomaly monitors and trend reporting. | P0 | T |
| FR-PRF-012 | Support **segmented profiling**: profiles computed per declared segment (e.g. per legal entity, per product, per source system, per region) with automatic segment discovery for high-cardinality-but-low-arity columns. | P1 | T |
| FR-PRF-013 | Support incremental profiling on new partitions/snapshots only, with cost budgets and sampling fallbacks for very large assets. | P0 | B |
| FR-PRF-014 | Profile non-relational payloads: JSON/XML path frequency, schema union inference, array-length distributions, nesting depth, field sparsity. | P1 | T |
| FR-PRF-015 | Compute cross-dataset overlap statistics (key overlap, value-set Jaccard) to support reconciliation scoping and FK inference. | P1 | T |
| FR-PRF-016 | Present a **profile diff** between any two profiling runs (or two datasets, or two environments) highlighting statistically significant changes. | P1 | D |
| FR-PRF-017 | Compute business-meaningful derived metrics as first-class profile members (e.g. sum of notional by currency, count by status) declared in PQL. | P0 | T |
| FR-PRF-018 | Support user-controlled profiling cost budget per source (max scanned bytes, max wall clock, max concurrency, allowed windows). | P0 | T |
| FR-PRF-019 | Auto-generate a natural-language dataset summary ("what this table appears to contain, its grain, its keys, its oddities") for human review. | P1 | D |

---

## C. Declarative Rule Authoring (`FR-RUL`)

Language specification: [07 — PQL](07-rule-language-spec.md).

| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-RUL-001 | Provide **PQL** (Prama Quality Language): a declarative, human-readable, version-controllable language for expressing quality assertions, with both a compact YAML surface and an expression/SQL-like surface. | P0 | T |
| FR-RUL-002 | Support all column-level assertion primitives: not-null, unique, in-set, not-in-set, range/between, length, regex/pattern match, type conformance, precision/scale, allowed-characters, case conventions, date-format conformance, monotonic, non-negative, non-zero. | P0 | T |
| FR-RUL-003 | Support dataset-level assertions: row count (absolute, relative, delta), schema conformance, column presence/order, primary-key uniqueness, no full-duplicate rows, partition completeness, freshness/staleness, file-size and record-count vs. trailer. | P0 | T |
| FR-RUL-004 | Support multi-column and cross-row assertions: functional dependency, conditional dependency, denial constraint, aggregate constraints (sum/avg/min/max bounds), group-level constraints (`for each` segment), window/sequence constraints (roll-forward, gaps, overlaps), and referential integrity within and across sources. | P0 | T |
| FR-RUL-005 | Support cross-dataset assertions: row-count parity, aggregate parity with tolerance, set difference/anti-join, key coverage, and full reconciliation (see `FR-REC`). | P0 | T |
| FR-RUL-006 | Support temporal assertions: as-of comparison, T vs. T-1 delta bounds, seasonality-aware expectations, business-calendar awareness (holidays, settlement calendars, month/quarter-end), and late-arrival tolerance. | P0 | T |
| FR-RUL-007 | Support **conditional application**: any assertion may carry a filter/predicate scope (`WHERE`), a segment scope (`FOR EACH`), and an activation window (effective-from/to). | P0 | T |
| FR-RUL-008 | Support parameterised, reusable rule **templates** with typed parameters, and rule **libraries** (packs) that can be imported and versioned. | P0 | T |
| FR-RUL-009 | Support **rule binding by selector**, not just by literal asset: bind a rule to all columns matching a semantic type, tag, naming pattern, or catalog classification across the estate ("every LEI column in every dataset in the Risk domain"). | P0 | T |
| FR-RUL-010 | Support severity levels (info, warning, minor, major, critical/blocking) and per-rule thresholds expressed as absolute counts, rates, or statistical bounds. | P0 | T |
| FR-RUL-011 | Support user-defined SQL/expression checks with a safe evaluation contract (read-only, resource-limited, parameterised, no DDL/DML). | P0 | T |
| FR-RUL-012 | Support user-defined functions in PQL, and registration of engine-native UDFs where available. | P1 | T |
| FR-RUL-013 | Support rule **lifecycle**: draft → proposed → in-review → approved → active → deprecated → retired, with maker-checker approval, effective dating, and full version history. | P0 | T |
| FR-RUL-014 | Support **rule simulation / backtest**: execute a candidate rule against historical snapshots to show what it *would* have flagged, with cost estimate, before activation. | P0 | D |
| FR-RUL-015 | Detect and warn on redundant, subsumed, contradictory, or never-firing rules; propose consolidation. | P1 | D |
| FR-RUL-016 | Support rule import from external formats: SodaCL, Great Expectations suites, dbt tests/dbt-expectations, Deequ constraints, DQX, ODCS `quality` blocks, SQL assertions, and Excel rule inventories. | P1 | T |
| FR-RUL-017 | Support rule export to ODCS `quality`, SQL, dbt tests, and human-readable control documentation. | P1 | T |
| FR-RUL-018 | Support rule annotation with business metadata: owner, steward, control objective, regulatory citation, materiality, dimension(s), CDE linkage, and rationale. | P0 | T |
| FR-RUL-019 | Support rule sets/suites with execution ordering, dependencies, and short-circuiting (e.g. skip content checks if schema check failed). | P0 | T |
| FR-RUL-020 | Support "expected failure" and known-exception registration with expiry, owner, and justification (exception management, not suppression). | P0 | T |
| FR-RUL-021 | Provide static analysis of PQL: type checking, referenced-column existence, dialect capability checking, cost/complexity estimation, and lint rules — all available in CI and in the editor. | P0 | T |
| FR-RUL-022 | Support rules over streaming scopes with windowing semantics (tumbling, sliding, session) and watermark/late-data policies. | P0 | T |
| FR-RUL-023 | Support assertions over *metadata* and *operations*, not only data: job ran, partition landed, schema unchanged, row count within SLA, upstream control passed. | P0 | T |
| FR-RUL-024 | Support rule-level data-access policy: which columns a rule may read, whether failing samples may be persisted, and masking to apply to samples. | P0 | T |

---

## D. Rule Induction & AI Assistance (`FR-IND`)

Design: [08 — AI/ML Capabilities](08-ai-ml-capabilities.md).

| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-IND-001 | Generate candidate rules automatically from profiling and dependency-discovery output (ranges, patterns, cardinalities, keys, FDs, INDs, DCs), each with support, confidence, violation count, and estimated cost. | P0 | B |
| FR-IND-002 | Generate candidate rules from semantic type inference (e.g. a column classified as ISIN inherits ISIN format + check-digit + existence-in-master rules). | P0 | T |
| FR-IND-003 | Generate candidate rules via LLM from schema, profile statistics, sample values (policy-permitting), column/table comments, glossary terms, and retrieved domain documentation (RAG). | P0 | D |
| FR-IND-004 | **Constrain LLM rule output to the PQL grammar via template-guided/constrained decoding**; reject any output that fails to parse, type-check, or execute in a sandbox. | P0 | T |
| FR-IND-005 | Validate every candidate rule against real data before proposing it: compute its violation rate, and suppress candidates that are trivially true, trivially false, or unstable across snapshots. | P0 | T |
| FR-IND-006 | Score candidate rules by an explicit **utility function** combining data support, business relevance (glossary/CDE linkage), non-redundancy versus existing rules, execution cost, and historical steward acceptance. | P0 | B |
| FR-IND-007 | Present candidate rules for human approval with full explanation: why proposed, evidence, sample violations, estimated alert volume, and the exact PQL that will be committed. | P0 | D |
| FR-IND-008 | Learn from accept/reject/edit decisions to re-rank future candidates, per-tenant and per-domain. | P1 | B |
| FR-IND-009 | Support bulk induction across an estate ("propose controls for all 4,000 tables in this domain") with prioritisation by asset criticality, downstream usage, and current coverage gaps. | P1 | D |
| FR-IND-010 | Support natural-language rule authoring: user states an intent in prose; system emits PQL, explains it, shows a backtest, and requests confirmation. | P0 | D |
| FR-IND-011 | Support rule induction from **examples** (steward marks rows as good/bad; system induces a discriminating rule) — Raha/Snorkel-style label-efficient induction. | P1 | B |
| FR-IND-012 | Support rule induction from **documents**: parse a data dictionary, regulatory instruction (e.g. AnaCredit manual), or interface specification and propose the implied validation rules with citations back to the source text. | P1 | D |
| FR-IND-013 | Never auto-activate an induced rule in a production/regulated scope without explicit human approval; support auto-activation only in explicitly designated "advisory" scopes. | P0 | A |
| FR-IND-014 | Provide a rule-coverage analyser: which columns/dimensions/critical data elements have no control, ranked by risk. | P0 | D |
| FR-IND-015 | Support cross-tenant/cross-dataset transfer of induced rules (Baran-style) with privacy-preserving abstraction — transfer the rule shape, never the data. | P2 | B |

---

## E. Statistical & ML Monitoring (`FR-MON`)

| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-MON-001 | Provide unsupervised monitors over the metric history for: row count/volume, null rate, distinct rate, freshness/arrival time, schema, distribution (numeric and categorical), value ranges, and any user-declared derived metric. | P0 | B |
| FR-MON-002 | Model seasonality (intraday, daily, weekly, monthly, quarter-end, business-calendar) explicitly; support user-declared calendars and automatic calendar inference. | P0 | B |
| FR-MON-003 | Detect distributional drift with tests appropriate to type: PSI, KS, Wasserstein, Jensen–Shannon, chi-square, and multivariate detectors; report the contributing columns/segments. | P0 | B |
| FR-MON-004 | Detect changepoints and regime shifts, distinguishing them from point anomalies, and support "accept new normal" with recalibration. | P1 | B |
| FR-MON-005 | **Emit a calibrated conformal p-value for every anomaly score**, valid under distribution shift via weighted/adaptive conformal calibration. | P0 | B |
| FR-MON-006 | Support a user-declared **false-alarm budget** per scope, and apply hierarchical FDR control (Benjamini–Hochberg / BY under dependence) across the domain → dataset → column → check lattice. | P0 | B |
| FR-MON-007 | Report **guarantee status**: whether calibration assumptions currently hold; degrade to "uncalibrated, best effort" visibly rather than silently. | P0 | D |
| FR-MON-008 | Support segmented monitoring: independent monitors per segment, with automatic suppression of segment-explosion and roll-up of correlated segment alerts. | P1 | B |
| FR-MON-009 | Detect multivariate/relational anomalies (records that violate the joint distribution, not any marginal), including conformance-constraint-style trust scoring of individual tuples. | P2 | B |
| FR-MON-010 | Detect record-level outliers and provide per-record explanation (which attributes contributed). | P1 | B |
| FR-MON-011 | Support cold start: produce useful monitoring within one observation using priors from semantic type, similar assets, and domain packs; refine as history accrues. | P0 | B |
| FR-MON-012 | Support monitor sensitivity control expressed in **operational terms** ("no more than N alerts/week for this domain"), automatically translated into thresholds. | P0 | D |
| FR-MON-013 | Support monitors over streaming sources with bounded-memory sketches (HLL, t-digest, count-min, Bloom) and windowed baselines. | P0 | B |
| FR-MON-014 | Detect anomalies in *arrival patterns* and *pipeline behaviour*, not just content: late file, missing file, duplicate delivery, out-of-sequence batch, unexpected volume spike/collapse. | P0 | T |
| FR-MON-015 | Detect duplicate and near-duplicate records probabilistically at scale (LSH/MinHash) as a monitor, distinct from full entity resolution. | P1 | B |
| FR-MON-016 | Support benchmark/challenger monitors: run multiple detectors in shadow mode and report comparative precision/recall against steward feedback before promotion. | P1 | B |
| FR-MON-017 | Provide model cards and reproducibility metadata for every monitor: algorithm, version, training window, hyperparameters, calibration set, and performance history (required for SR 11-7 / EU AI Act evidence). | P0 | A |
| FR-MON-018 | Support user override of any monitor's learned baseline with an explicit, versioned, justified manual baseline. | P0 | T |

---

## F. Execution Engine, Scheduling & Orchestration (`FR-EXE`)

| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-EXE-001 | Compile every PQL rule to an engine-neutral **Intermediate Representation (IR)**, then to a target-specific plan. | P0 | T |
| FR-EXE-002 | Provide execution backends: ANSI-SQL pushdown (per-dialect), Spark, Flink (streaming), Arrow/DuckDB (local, file, and small-data), and a native streaming row scanner for non-tabular feeds. | P0 | T |
| FR-EXE-003 | Guarantee **semantic equivalence across backends** for the IR, verified by a conformance test suite executed in CI for every supported engine. | P0 | T |
| FR-EXE-004 | Default to **pushdown**: compute executes in the source system; only metrics, verdicts, and policy-permitted samples return to the control plane. | P0 | A |
| FR-EXE-005 | Batch multiple assertions over the same scope into a single scan/query wherever the IR permits (multi-assertion fusion), with a demonstrable reduction in source load. | P0 | B |
| FR-EXE-006 | Support incremental execution over new partitions/snapshots/watermarks only, with correct handling of late-arriving and restated data. | P0 | T |
| FR-EXE-007 | Support sampling-based execution with statistically valid extrapolation and explicit confidence intervals on reported rates; never present a sampled result as exact. | P0 | B |
| FR-EXE-008 | Enforce per-source and per-run resource budgets (bytes scanned, wall clock, slots/credits, concurrency) with graceful degradation and clear reporting when a budget binds. | P0 | T |
| FR-EXE-009 | Support scheduling: cron, interval, calendar-aware (business days, month-end), dependency-triggered, event-triggered (file arrival, table commit, message), and manual/ad-hoc. | P0 | T |
| FR-EXE-010 | Integrate as a task/operator with orchestrators: Airflow, Dagster, Prefect, dbt, Databricks Workflows, Azure Data Factory, Control-M, Autosys, AWS Step Functions, Argo. | P0 | T |
| FR-EXE-011 | Support **gate mode**: a pipeline blocks or proceeds on the verdict of a Prama check, with configurable fail-open/fail-closed and timeout semantics. | P0 | T |
| FR-EXE-012 | Support **quarantine mode**: failing records routed to a quarantine location/topic with full provenance, and a documented re-injection path after remediation. | P0 | T |
| FR-EXE-013 | Support **in-flight/streaming enforcement**: validate messages before publication, with drop/tag/route/dead-letter actions and sub-second added latency at target throughput. | P0 | B |
| FR-EXE-014 | Produce an immutable, hash-linked `EvidenceRecord` for every assertion execution (see [13](13-security-governance-compliance.md) §6). | P0 | T |
| FR-EXE-015 | Support **deterministic replay**: re-execute any historical run against the same data snapshot and rule version and obtain an identical verdict, or explain precisely why not. | P0 | T |
| FR-EXE-016 | Support parallel/distributed execution across thousands of assets with fair scheduling, priority classes, and back-pressure on saturated sources. | P0 | B |
| FR-EXE-017 | Support retry with exponential backoff, partial-failure isolation (one failing rule does not fail the suite), and idempotent re-execution. | P0 | T |
| FR-EXE-018 | Support dry-run/plan mode showing the exact query/plan that will be executed, its cost estimate, and its data access footprint. | P0 | D |
| FR-EXE-019 | Support execution against a specific historical snapshot (time travel) for restatement analysis and audit. | P1 | T |
| FR-EXE-020 | Support agentless execution mode (control plane connects out) and agent mode (a lightweight in-VPC/on-prem worker) including fully air-gapped operation with offline rule/model bundle updates. | P0 | D |
| FR-EXE-021 | Emit OpenTelemetry traces/metrics for every execution and OpenLineage events for every dataset touched. | P1 | T |

---

## G. Reconciliation & Cross-System Controls (`FR-REC`)

| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-REC-001 | Provide reconciliation as a first-class assertion type comparing two or more datasets across *different* sources, engines, and formats. | P0 | T |
| FR-REC-002 | Support match strategies: exact key, composite key, tolerance-based numeric match, fuzzy/probabilistic match, one-to-one, one-to-many, many-to-many, and netted/grouped matching. | P0 | T |
| FR-REC-003 | Support normalisation before comparison: currency conversion with declared rate source and as-of date, unit conversion, sign conventions, date/timezone alignment, string canonicalisation, and code-set mapping. | P0 | T |
| FR-REC-004 | Support tolerance semantics: absolute, relative, per-currency materiality, and rounding conventions with explicit precision/scale rules. | P0 | T |
| FR-REC-005 | Classify differences into **break types** (missing in A, missing in B, value difference, duplicate, timing/late, sign, FX, rounding) and produce a break record per difference. | P0 | T |
| FR-REC-006 | Support time-shifted comparison (T vs. T-1 roll-forward with movement explanation: opening + movements = closing). | P0 | T |
| FR-REC-007 | Support N-way reconciliation (e.g. front office vs. sub-ledger vs. GL vs. custodian) with a consistent break taxonomy. | P1 | T |
| FR-REC-008 | Provide break workflow: assignment, ageing, categorisation, commentary, evidence attachment, escalation, and closure — with full audit trail. | P0 | D |
| FR-REC-009 | Learn break-classification and match-field prediction from historical resolutions (ML-assisted matching), always with human confirmation. | P1 | B |
| FR-REC-010 | Support reconciliation at scale: 10^8+ records per side with partitioned/blocked matching. | P1 | B |
| FR-REC-011 | Produce a reconciliation certificate: totals, matched/unmatched counts and values, break ageing, and sign-off, exportable as regulator-ready evidence. | P0 | D |

---

## H. Entity Resolution & Matching (`FR-ERM`)

| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-ERM-001 | Provide probabilistic record linkage using a Fellegi–Sunter model with EM-estimated m/u probabilities, exposing match weights and thresholds for audit. | P1 | B |
| FR-ERM-002 | Support blocking/indexing strategies (exact, sorted-neighbourhood, phonetic, n-gram, LSH, embedding-ANN) with recall estimation for the blocking step. | P1 | B |
| FR-ERM-003 | Support comparison functions: exact, Levenshtein, Jaro-Winkler, Jaccard, token-set, numeric distance, date proximity, geospatial distance, and embedding cosine similarity. | P1 | T |
| FR-ERM-004 | Support active learning: request the most informative pairs for steward labelling and retrain incrementally. | P1 | B |
| FR-ERM-005 | Support optional transformer-based matcher (Ditto-style) as a reranker over blocked candidates, always with the probabilistic score also reported. | P2 | B |
| FR-ERM-006 | Support clustering of matched pairs into entities with transitivity control and cluster-quality diagnostics. | P1 | T |
| FR-ERM-007 | Support survivorship/golden-value rules expressed in PQL for export to MDM (recency, source priority, completeness, frequency, custom). | P2 | T |
| FR-ERM-008 | Support cross-source duplicate detection as a scheduled *control* producing incidents, not only as a batch job. | P1 | T |
| FR-ERM-009 | Support entity-resolution evaluation against a labelled set with precision/recall/F1 and pairwise + cluster-level metrics. | P1 | B |

---

## I. Remediation & Repair (`FR-REM`)

| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-REM-001 | Support standardisation and cleansing transforms: trim, case normalisation, whitespace/punctuation normalisation, unicode normalisation, date parsing/reformatting, number parsing, code-set mapping, name/address parsing. | P0 | T |
| FR-REM-002 | Propose repairs for detected errors with a ranked candidate list, a confidence, and the evidence supporting each candidate (value co-occurrence, constraint implication, external reference, historical value). | P1 | B |
| FR-REM-003 | Support constraint-aware holistic repair (minimal-repair semantics over the active constraint set) as an *advisory* capability with explicit cost model. | P2 | B |
| FR-REM-004 | Support **utility-aware repair scoring**: rank candidate repairs by their effect on declared downstream consumers (report, return, model), not only on dimension conformance. | P3 | B |
| FR-REM-005 | Never write to a source system without an explicit, per-scope, separately-granted write permission and an approved change record. | P0 | A |
| FR-REM-006 | Support remediation channels: generate a correction file/ticket/API call, publish to a correction topic, open a workflow item in ServiceNow/Jira, or (where permitted) execute an approved update. | P0 | T |
| FR-REM-007 | Track every remediation end-to-end: defect → decision → action → verification re-run → closure, with before/after evidence. | P0 | T |
| FR-REM-008 | Support bulk remediation with preview, simulation, blast-radius analysis, and rollback plan. | P1 | D |
| FR-REM-009 | Support enrichment from reference/authoritative sources (postal, LEI/GLEIF, securities master, sanctions) with provenance recorded per enriched value. | P1 | T |
| FR-REM-010 | Support imputation strategies with explicit labelling of imputed values so they are never mistaken for observed values. | P2 | T |

---

## J. Incident Management & Workflow (`FR-INC`)

| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-INC-001 | Create an **incident** from correlated assertion failures and anomalies, not one per failing check; deduplicate and group by root cause, asset, time window, and lineage proximity. | P0 | T |
| FR-INC-002 | Support incident lifecycle: new → triaged → investigating → identified → remediating → verifying → resolved → closed (+ suppressed / false-positive / known-issue). | P0 | T |
| FR-INC-003 | Assign incidents by ownership rules (asset owner, domain steward, on-call rota) with escalation policies and SLAs per severity. | P0 | T |
| FR-INC-004 | Provide automated root-cause assistance: upstream control status, recent schema/code/pipeline changes, lineage ancestry, correlated incidents, and a ranked hypothesis list with supporting evidence. | P0 | D |
| FR-INC-005 | Provide impact analysis: downstream assets, reports, dashboards, models, and regulatory returns affected, with consumer notification. | P0 | D |
| FR-INC-006 | Support collaboration: comments, mentions, attachments, and bidirectional sync with Jira/ServiceNow/Slack/Teams. | P0 | T |
| FR-INC-007 | Capture structured resolution outcomes (true positive / false positive / duplicate / expected / known issue) — this is the primary training signal for the learning loop. | P0 | T |
| FR-INC-008 | Support post-incident review artefacts and recurring-issue detection ("this is the 7th occurrence of this pattern in 90 days"). | P1 | D |
| FR-INC-009 | Support suppression/maintenance windows with mandatory expiry, owner, and justification. | P0 | T |
| FR-INC-010 | Maintain an immutable incident audit trail suitable for regulatory review. | P0 | A |

---

## K. Scoring, Reporting & Analytics (`FR-SCR`)

| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-SCR-001 | Compute per-dimension scores (accuracy, completeness, consistency, timeliness, uniqueness, validity, + configurable extensions) at column, dataset, domain, and enterprise levels. | P0 | T |
| FR-SCR-002 | Compute a composite quality score with **configurable, documented aggregation** (weighted arithmetic, worst-of, weakest-link, and standardised/PCA-derived options), always exposing the components. | P0 | T |
| FR-SCR-003 | Weight scores by materiality: record counts, monetary value at risk, criticality of the CDE, and downstream consumer importance. | P0 | T |
| FR-SCR-004 | **Propagate trust along column-level lineage**, so a consumer's score reflects its ancestry as well as its own controls; expose the derivation. | P2 | B |
| FR-SCR-005 | Maintain score history with trend, target, and variance reporting; support period-over-period comparison and attribution of score movement. | P0 | T |
| FR-SCR-006 | Support DQ **SLAs/SLOs** with error budgets per dataset/domain and burn-rate reporting. | P1 | T |
| FR-SCR-007 | Provide role-based dashboards: executive/CDO, domain steward, data engineer, control owner, auditor, and consumer-facing "can I trust this dataset?" view. | P0 | D |
| FR-SCR-008 | Provide a **control attestation report** per period, per control, per owner — the artefact required for RDARR/SOX-style sign-off — with electronic sign-off and immutable retention. | P0 | D |
| FR-SCR-009 | Provide scheduled and on-demand report generation and distribution (PDF, XLSX, HTML, CSV, JSON) with per-recipient scoping and redaction. | P0 | T |
| FR-SCR-010 | Provide an issue/defect register with ageing, ownership, root-cause categorisation, and remediation status — exportable to GRC tools (Archer, MetricStream, ServiceNow GRC, OpenPages). | P0 | T |
| FR-SCR-011 | Quantify business impact per issue: records affected, monetary exposure, affected reports/returns, and estimated remediation effort. | P1 | D |
| FR-SCR-012 | Provide a "quality of the quality programme" meta-report: control coverage, control effectiveness, alert precision, MTTD/MTTR, steward workload, false-positive rate. | P1 | D |
| FR-SCR-013 | Expose all metrics via API and a queryable semantic model so customers can build their own BI on top; provide native embeds for Tableau/Power BI/Looker/Superset. | P1 | T |
| FR-SCR-014 | Support benchmark comparison across peer datasets/domains within a tenant (and optionally anonymised cross-tenant, opt-in). | P2 | D |
| FR-SCR-015 | Generate a narrative executive summary (LLM-written, evidence-grounded, with every number traceable to a query) for any scorecard period. | P1 | D |

---

## L. Alerting & Notification (`FR-ALR`)

| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-ALR-001 | Route alerts by rules over severity, domain, asset, owner, time, and business calendar. | P0 | T |
| FR-ALR-002 | Support channels: email, Slack, Microsoft Teams, PagerDuty, Opsgenie, ServiceNow, Jira, webhooks, SNS/SQS/Kafka, SMS, and MS Graph/Outlook actionable messages. | P0 | T |
| FR-ALR-003 | Deduplicate, group, and rate-limit alerts; enforce the per-scope false-alarm budget from `FR-MON-006` at the notification layer as well. | P0 | T |
| FR-ALR-004 | Include in every alert: what failed, how much, since when, what changed upstream, likely cause, downstream impact, suggested next action, and a deep link. | P0 | D |
| FR-ALR-005 | Support digest/summary modes (hourly, daily, weekly) and quiet hours with severity-based override. | P0 | T |
| FR-ALR-006 | Support subscription by consumers to assets they depend on ("tell me when anything I use degrades"). | P1 | T |
| FR-ALR-007 | Support alert acknowledgement, snooze, and escalation from within the notification channel (bidirectional actions). | P1 | T |
| FR-ALR-008 | Support anticipatory alerts: predicted SLA breach, predicted late arrival, degrading trend before threshold breach. | P2 | B |
| FR-ALR-009 | Track alert outcome quality and expose per-monitor precision so noisy monitors are visible and tunable. | P0 | T |

---

## M. Learning Loop (`FR-LRN`)

| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-LRN-001 | Capture every human signal as structured feedback: incident dispositions, rule accept/reject/edit, threshold overrides, break classifications, ER labels, alert acknowledgements, and suppressions. | P0 | T |
| FR-LRN-002 | Recalibrate monitor thresholds and conformal calibration sets from feedback, with scheduled and event-triggered retraining. | P0 | B |
| FR-LRN-003 | Re-rank rule-induction candidates using accepted/rejected history (per tenant, per domain, per semantic type). | P1 | B |
| FR-LRN-004 | Learn incident-to-root-cause associations to improve RCA hypothesis ranking over time. | P1 | B |
| FR-LRN-005 | Learn break classification and match-field selection in reconciliation from resolved breaks. | P1 | B |
| FR-LRN-006 | Detect and report **model degradation** of any learned component, with automatic rollback to the last known-good version. | P0 | T |
| FR-LRN-007 | Maintain a versioned feature/label store for all learned components with lineage from raw signal to trained artefact. | P0 | A |
| FR-LRN-008 | Support tenant-isolated learning by default; cross-tenant learning only via explicitly opted-in, privacy-preserving abstractions (rule shapes and statistics, never data). | P0 | A |
| FR-LRN-009 | Expose the learning loop's own metrics (precision uplift, acceptance rate, MTTR reduction) so the value of learning is auditable. | P1 | D |
| FR-LRN-010 | Support human override of any learned behaviour, with the override itself recorded as a training signal. | P0 | T |

---

## N. Lineage & Impact (`FR-LIN`)

| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-LIN-001 | Ingest lineage from external sources: OpenLineage events, dbt manifests, Spark/Databricks lineage, Unity Catalog, Snowflake ACCESS_HISTORY, catalog APIs (Collibra, Alation, Atlan, OpenMetadata, DataHub, Purview). | P0 | T |
| FR-LIN-002 | Derive column-level lineage by parsing SQL/transformation code where lineage is unavailable, for the major dialects. | P1 | T |
| FR-LIN-003 | Maintain a lineage graph supporting ancestry, descendancy, shortest-path, and blast-radius queries at interactive latency over 10^6+ nodes. | P0 | B |
| FR-LIN-004 | Attach controls, incidents, and scores to lineage nodes and edges; render lineage annotated with quality state. | P0 | D |
| FR-LIN-005 | Emit OpenLineage events for Prama's own executions so Prama is a well-behaved citizen of the customer's lineage graph. | P1 | T |
| FR-LIN-006 | Support manual lineage assertion and correction where automated discovery is impossible (e.g. mainframe jobs, vendor black boxes). | P1 | T |
| FR-LIN-007 | Support lineage-scoped rule propagation: apply a control to an asset and all its declared derivations. | P2 | T |

---

## O. Data Contracts & Shift-Left (`FR-CTR`)

| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-CTR-001 | Import ODCS v3.x contracts and compile their `schema` and `quality` sections into executable PQL assertions. | P0 | T |
| FR-CTR-002 | Export Prama-managed controls as ODCS `quality` blocks so contracts stay authoritative and portable. | P0 | T |
| FR-CTR-003 | Report contract conformance continuously and publish a machine-readable conformance status per contract version. | P0 | T |
| FR-CTR-004 | Provide CI/CD integration (GitHub Actions, GitLab CI, Azure DevOps, Jenkins) that fails a build on contract or rule violation. | P0 | T |
| FR-CTR-005 | Provide **data diff** between environments/branches/versions: schema diff, row-level diff, and distribution diff, with sampling and cost control. | P1 | B |
| FR-CTR-006 | Validate producer-side before publication (pre-commit / pre-publish hooks for Kafka producers, dbt models, file publishers). | P1 | T |
| FR-CTR-007 | Integrate with schema registries to enforce compatibility policy and surface breaking changes as incidents. | P1 | T |
| FR-CTR-008 | Support SLA/SLO declarations in contracts (freshness, availability, completeness) and monitor them as first-class controls. | P0 | T |

---

## P. User Interface (`FR-UIX`)

Detail: [10 — UX & Conversational Interface](10-ux-and-chat-interface.md).

| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-UIX-001 | Provide a web console covering: estate overview, asset explorer, profile viewer, rule studio, monitor studio, incident workspace, reconciliation workbench, scorecards, lineage explorer, and administration. | P0 | D |
| FR-UIX-002 | Provide a **no-code rule builder** (guided, form + expression, with live preview against real data) that emits the same PQL as the text editor — with a visible, always-available "show me the PQL" toggle. | P0 | D |
| FR-UIX-003 | Provide a **PQL text editor** with syntax highlighting, autocomplete over the live schema/glossary, inline type/dialect errors, cost estimates, and one-click backtest. | P0 | D |
| FR-UIX-004 | Provide live preview: any rule under construction shows matched/failing counts and sample failing rows (subject to masking policy) within seconds. | P0 | B |
| FR-UIX-005 | Provide bulk operations across many assets (apply, edit, retire, re-own, re-schedule) with preview and undo. | P0 | D |
| FR-UIX-006 | Provide an incident workspace optimised for triage speed: keyboard-first, one-screen context, batch disposition, and inline evidence. | P0 | D |
| FR-UIX-007 | Provide drill-down from any score or chart to the underlying evidence and, where policy permits, the failing records. | P0 | D |
| FR-UIX-008 | Provide fully responsive layouts and a usable mobile/tablet experience for approve/triage/acknowledge workflows. | P1 | D |
| FR-UIX-009 | Meet **WCAG 2.2 AA** accessibility, full keyboard navigation, screen-reader support, and high-contrast/dark themes. | P0 | T |
| FR-UIX-010 | Support internationalisation and localisation (UI strings, dates, numbers, currencies, RTL), with English, and pack-driven addition of others. | P1 | T |
| FR-UIX-011 | Provide in-product guidance: contextual help, guided onboarding for a first source, and templates for common control patterns. | P0 | D |
| FR-UIX-012 | Provide personalised home surfaces per role, with saved views, filters, and subscriptions. | P1 | D |
| FR-UIX-013 | Ensure P95 interactive latency ≤ 300 ms for navigation and ≤ 2 s for data-backed panels (see NFRs). | P0 | B |
| FR-UIX-014 | Provide an embeddable widget/SDK so quality state can be surfaced inside catalogs, BI tools, and internal portals. | P1 | T |
| FR-UIX-015 | Provide full audit visibility of who changed what, viewable in-context on every object. | P0 | D |

---

## Q. Conversational Interface (`FR-CHT`)

| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-CHT-001 | Provide a conversational assistant available (a) as a panel in every console screen with the screen's context, (b) as a standalone workspace, and (c) in Slack/Teams. | P0 | D |
| FR-CHT-002 | The assistant operates **exclusively through the public API** with the *invoking user's* permissions — never a service account, never elevated. | P0 | A |
| FR-CHT-003 | Support intent classes: ask (explain state), author (create/modify rules & monitors), investigate (RCA/impact), operate (run, schedule, acknowledge), and report (generate/summarise). | P0 | D |
| FR-CHT-004 | Every mutating action is a **proposal**: rendered as a diff of the exact PQL/config, with backtest and cost estimate, requiring explicit confirmation and passing the same approval workflow as UI-authored changes. | P0 | A |
| FR-CHT-005 | Ground every factual answer in retrieved system state and cite the underlying object/query; refuse to answer where grounding is unavailable rather than speculate. | P0 | D |
| FR-CHT-006 | Support multi-turn context including the current screen, selected assets, and the active incident. | P0 | D |
| FR-CHT-007 | Support the full authoring loop conversationally: describe intent → see PQL → see backtest → adjust in prose → approve → deploy. | P0 | D |
| FR-CHT-008 | Support investigative loops: "why did the LCR feed fail last night?" → correlated incidents, upstream changes, lineage, ranked hypotheses, each with evidence links. | P0 | D |
| FR-CHT-009 | Support report generation: "give me the Q3 attestation summary for Credit Risk" → generated artefact with every figure traceable. | P1 | D |
| FR-CHT-010 | Support **BYO-LLM**: Anthropic Claude, Azure OpenAI, AWS Bedrock, Google Vertex, and self-hosted open-weight models (vLLM/Ollama/TGI) — configurable per tenant, with an air-gapped local-model path. | P0 | T |
| FR-CHT-011 | Enforce prompt-injection defences: treat all data content and all retrieved documents as untrusted; never allow data content to trigger tool calls; strict tool allow-lists; output validation against schemas. | P0 | T |
| FR-CHT-012 | Log every conversation turn, tool call, and proposal with the same audit rigour as UI actions; make transcripts exportable and retention-governed. | P0 | A |
| FR-CHT-013 | Redact/mask sensitive values in prompts and responses per data-classification policy; never send masked-class data to an external model. | P0 | T |
| FR-CHT-014 | Report token/compute cost per conversation and enforce per-tenant/per-user budgets. | P1 | T |
| FR-CHT-015 | Provide a voice-optional, keyboard-first interaction model; the assistant must be fully usable without a mouse. | P2 | D |
| FR-CHT-016 | Expose Prama's capabilities as an **MCP server** so the customer's own agents (and Claude Code / IDE agents) can query quality state and propose controls under the same policy controls. | P1 | T |
| FR-CHT-017 | The assistant must be able to say "I don't know" and to escalate to a human owner with context attached. | P0 | D |

---

## R. Unstructured Data & AI-Readiness (`FR-UNS`)

| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-UNS-001 | Profile document corpora: format distribution, language, length, extraction success rate, OCR confidence, encoding issues, and structural anomalies (complex tables, embedded images). | P2 | T |
| FR-UNS-002 | Detect near-duplicate and superseded documents; detect stale/outdated content by recency and reference decay. | P2 | B |
| FR-UNS-003 | Detect PII/sensitive content in unstructured text and flag for redaction before ingestion into AI systems. | P1 | T |
| FR-UNS-004 | Assess **retrieval-corpus quality**: chunk-size distribution, orphan chunks, coverage of expected topics, embedding-space degeneracy, and retrieval-permission consistency. | P2 | B |
| FR-UNS-005 | Produce an **AI-readiness certificate** for a dataset or corpus: completeness, freshness guarantees, provenance, permission coverage, PII posture, and traceability of sources behind AI outputs. | P2 | D |
| FR-UNS-006 | Monitor training/inference data drift for deployed models and link model incidents to upstream data incidents. | P2 | T |
| FR-UNS-007 | Support quality checks on images/audio at the metadata and basic-signal level (resolution, corruption, duration, silence, format conformance). | P3 | T |

---

## S. Extensibility, APIs & Integration (`FR-EXT`)

Detail: [14 — Data Model & APIs](14-data-model-and-apis.md).

| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-EXT-001 | Provide a complete, versioned REST API (OpenAPI 3.1) covering 100% of console functionality — the console consumes only public APIs. | P0 | T |
| FR-EXT-002 | Provide gRPC APIs for high-throughput paths (evidence ingest, metric ingest, streaming verdicts). | P1 | T |
| FR-EXT-003 | Provide official SDKs: Python, Java/Scala, TypeScript, and a CLI. | P0 | T |
| FR-EXT-004 | Provide a webhook/event bus publishing domain events (run completed, assertion failed, incident opened/closed, score changed, contract violated) with at-least-once delivery and replay. | P0 | T |
| FR-EXT-005 | Provide plugin points: connectors, assertion types, monitors, notifiers, remediation actions, semantic-type classifiers, and scoring functions. | P1 | D |
| FR-EXT-006 | Provide a **Domain Pack SDK** and packaging format (versioned, signed, dependency-aware). | P1 | D |
| FR-EXT-007 | Provide Terraform provider and Kubernetes CRDs for infrastructure-as-code management of Prama objects. | P1 | T |
| FR-EXT-008 | Provide an MCP server exposing read and propose-only tools by default. | P1 | T |
| FR-EXT-009 | Support GitOps: rules, monitors, contracts, and pack configurations stored in Git as the source of truth, with bidirectional sync and drift detection. | P0 | T |
| FR-EXT-010 | Provide a stable, documented, semver'd IR so third parties can build alternative compilers/backends. | P2 | A |

---

## T. Domain Packs (`FR-PCK`)

| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-PCK-001 | Package domain content as versioned, signed bundles containing: semantic types + validators, message-format parsers, rule libraries, glossary/ontology fragments, dimension weightings, scorecard templates, control catalogues with regulatory citations, and sample data. | P1 | D |
| FR-PCK-002 | Ship a **Banking & Capital Markets** pack at GA (see [12](12-banking-domain-pack.md)). | P0 | D |
| FR-PCK-003 | Ship packs for Insurance, Payments, Healthcare, Telco, Retail/CPG, Energy, and Public Sector post-GA. | P2 | D |
| FR-PCK-004 | Allow customers to fork, extend, and privately publish packs; support pack inheritance and override. | P1 | T |
| FR-PCK-005 | Version packs independently of the platform, with compatibility ranges and safe upgrade/rollback. | P1 | T |
| FR-PCK-006 | Provide a pack marketplace/registry (internal for air-gapped deployments). | P2 | D |

---

## U. Administration & Operations (`FR-ADM`)

Security detail: [13](13-security-governance-compliance.md).

| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-ADM-001 | Multi-tenancy with hard isolation of data, metadata, models, and learned artefacts. | P0 | T |
| FR-ADM-002 | SSO via OIDC/SAML, SCIM provisioning, and group/role mapping from the IdP. | P0 | T |
| FR-ADM-003 | RBAC + ABAC with fine-grained permissions down to asset, domain, rule, and evidence level; segregation of duties enforced (author ≠ approver). | P0 | T |
| FR-ADM-004 | Secrets management integration: HashiCorp Vault, AWS/Azure/GCP secret managers, CyberArk; no credentials at rest in Prama's own store in default posture. | P0 | T |
| FR-ADM-005 | Complete audit logging of every read and write, exportable to SIEM. | P0 | T |
| FR-ADM-006 | Configuration and object lifecycle management across environments (dev/UAT/prod) with promotion workflows. | P0 | T |
| FR-ADM-007 | Backup/restore, disaster recovery, and documented RPO/RTO. | P0 | T |
| FR-ADM-008 | Usage metering and cost attribution per tenant/domain/team (compute consumed at source, control-plane usage, LLM tokens). | P1 | T |
| FR-ADM-009 | Health/self-monitoring dashboard for the platform itself, with its own SLOs. | P0 | T |
| FR-ADM-010 | Offline/air-gapped installation and update path with signed bundles. | P0 | D |


---

## V. Continuous Re-examination & Refresh (`FR-REF`)

Prama's findings must never go stale. Everything it concludes — profiles, inferred types, proposed
rules, baselines, relationships, scores — is re-derived on a configured cadence, and every finding
carries its own freshness.

| ID | Requirement | Pri | Ver |
|---|---|---|---|
| FR-REF-001 | Support a **re-examination schedule per dataset** (and per connection, per domain, and per criticality tier as inherited defaults) governing how often Prama re-reads and re-derives its findings. | P0 | T |
| FR-REF-002 | Support independent cadences for each activity class: re-profiling, semantic-type re-inference, dependency/key re-discovery, relationship re-proposal, rule re-induction, monitor baseline re-fit, conformal re-calibration, and score recomputation. | P0 | T |
| FR-REF-003 | Support cadence expressed as schedule (cron/interval/calendar), as event trigger (new partition, new file, schema change, upstream incident, contract change), or as adaptive policy (more often when volatile, less often when stable). | P0 | T |
| FR-REF-004 | Apply **adaptive cadence** by default: increase frequency for assets that are high-criticality, recently changed, historically unstable, or heavily consumed; decrease for stable, low-criticality, rarely used assets. Always show the user the chosen cadence and why. | P1 | B |
| FR-REF-005 | Enforce refresh cost budgets per connection/domain/tenant, with prioritisation by criticality when the budget binds, and transparent reporting of what was deferred. | P0 | T |
| FR-REF-006 | Stamp every finding (profile, inferred type, candidate rule, baseline, score, relationship suggestion) with `computed_at`, the data snapshot examined, the sampling strategy used, and a **staleness state** (fresh / ageing / stale / suspended). | P0 | T |
| FR-REF-007 | Surface staleness in the UI and API wherever a finding is displayed; never present a stale conclusion as current. | P0 | D |
| FR-REF-008 | Detect and report **metadata drift**: physical schema changes that invalidate declared bindings, attributes that no longer match their declared value domain, grain violations, and relationships whose key overlap has degraded. Raise these as incidents against the metadata owner. | P0 | T |
| FR-REF-009 | Re-run semantic-type inference and flag **reclassification** (a column that was IBAN-shaped is now free text) as a first-class finding. | P0 | T |
| FR-REF-010 | Re-run rule induction periodically and propose (a) new controls for newly-observed structure, (b) retirement of controls that no longer fire or are now subsumed, and (c) threshold adjustments — always as reviewable proposals. | P0 | D |
| FR-REF-011 | Re-fit monitor baselines and conformal calibration sets on a rolling window, with change reporting ("this monitor's expected volume band widened by 18% after the July regime shift"). | P0 | B |
| FR-REF-012 | Produce a periodic **"what changed in your estate"** digest per domain: new datasets discovered, structures changed, types reclassified, relationships proposed, controls suggested or retired, trends emerging. | P0 | D |
| FR-REF-013 | Compare successive examinations and report **trend and pattern findings** over the long horizon (quarter-over-quarter drift in completeness, seasonal patterns, gradual degradation), not only point-in-time anomalies. | P0 | D |
| FR-REF-014 | Support on-demand re-examination of any dataset, domain, or journey from the UI, API, and chat, with progress and cost visible. | P0 | D |
| FR-REF-015 | Retain a full history of examinations so any finding can be replayed and any trend can be re-derived; retention configurable per criticality tier. | P0 | T |
| FR-REF-016 | Pause and resume re-examination per scope (e.g. during a source outage or a migration freeze) with an audit record and automatic resumption. | P1 | T |
| FR-REF-017 | Respect source-system load: schedule re-examinations in permitted windows, back off on detected contention, and never exceed the declared read policy. | P0 | T |
| FR-REF-018 | Report the **cost and value of re-examination**: compute consumed versus findings produced and incidents prevented, so cadence can be tuned on evidence. | P2 | D |

---

<div align="center">
<img src="assets/prama-mark.svg" width="30" alt=""/><br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.<br/>
See <a href="../LICENSE">LICENSE</a> and <a href="../NOTICE">NOTICE</a>. Third-party names and marks are the property of their respective owners.</sub>
</div>
