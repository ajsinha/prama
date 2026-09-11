<img src="assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

> ***pramā*** (Sanskrit **प्रमा**) — *valid knowledge: a cognition that is both true and arrived at
> by a reliable means*. Its companion ***pramāṇa*** (प्रमाण) is *the instrument by which valid
> knowledge is obtained*. Prama is that instrument for an organisation's data — it does not decide
> what is true, it is how a belief about data becomes **justified**.
>
> **Declare it. Prove it. Trust it.**


---
# 09 — Connectivity, Sources & Formats

Requirements: [`FR-CON`](04-requirements-functional.md#a-connectivity--ingestion-fr-con).
Business-grade connector UX: [03 §4](03-business-semantic-layer.md#4-connectors-as-a-business-configurable-resource).

**Design stance.** Breadth of connectivity is a *moat*, not a checkbox. The observability vendors
support ~20 cloud sources; banks run 200+ system types including mainframes, vendor packages, and
file feeds that arrive by SFTP at 04:00. Prama's differentiation in regulated industries is that
**the awkward sources are first-class**, not "coming soon".

---

## 1. Connector architecture

```
┌──────────────────────────────────────────────────────────────────┐
│ Connection (configured once, by a data architect, in the UI)     │
│   identity → vault reference · network → proxy/PrivateLink       │
│   read policy → scopes, budgets, windows, sampling, masking      │
└───────────────────────┬──────────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┬────────────────┐
        ▼               ▼               ▼                ▼
   Discovery       Metadata          Reader          Pushdown
   (what exists)   (schema, stats)   (rows→Arrow)    (compile & execute
                                                      at source)
```

Every connector implements a small SPI: `discover()`, `describe()`, `snapshot()`, `read()`,
`pushdown_capabilities()`, `execute_plan()`, `health()`. A connector that cannot push down still
works — the engine falls back to reading Arrow batches and evaluating the IR locally, with the cost
implication shown to the author. This uniformity is why a rule written for Snowflake also runs on a
COBOL feed.

**Capability matrix.** Each connector declares what the engine may rely on: SQL dialect and version,
window functions, `QUALIFY`, regex flavour, approximate distinct, sampling clause, JSON/XML path,
decimal precision/scale limits, transaction snapshot support, time travel, partition pruning,
predicate pushdown, and parallel read. The compiler consults this matrix; it never guesses.

---

## 2. Relational databases

| Family | Engines | Snapshot mechanism | Notes |
|---|---|---|---|
| PostgreSQL | PostgreSQL, Aurora PG, AlloyDB, CockroachDB, YugabyteDB, Citus | Transaction snapshot / LSN | Full pushdown |
| MySQL | MySQL, MariaDB, Aurora MySQL, TiDB | GTID / binlog position | Full pushdown |
| Oracle | Oracle 11g–23ai, Exadata, Autonomous | SCN + flashback query | SCN gives true point-in-time evidence |
| SQL Server | SQL Server 2014+, Azure SQL, Managed Instance | Snapshot isolation / LSN | |
| DB2 | DB2 LUW, **DB2 for z/OS**, DB2 for i | Commit sequence | z/OS is a differentiator |
| Teradata | Teradata Vantage | Transaction time | Common in Tier-1 banks |
| Sybase | SAP ASE, SAP IQ | — | Legacy capital-markets estates |
| Others | Informix, SAP HANA, Netezza, Greenplum, Vertica, Exasol, Firebird, SQLite, H2 | varies | |

## 3. Cloud warehouses & query engines

Snowflake · Google BigQuery · Amazon Redshift (+ Serverless) · Databricks SQL · Azure Synapse ·
Microsoft Fabric · Amazon Athena · Trino / Starburst · Presto · Apache Drill · ClickHouse ·
DuckDB / MotherDuck · Firebolt · Dremio · SingleStore · Apache Doris · Apache Pinot · Druid.

Native integrations: Snowflake **Data Metric Functions** and Databricks **Lakehouse Monitoring** /
DLT expectations are *consumed as inputs* into the metric history rather than duplicated — Prama
adds cross-system, business-semantic, and evidentiary value on top of what the platform already
computes for free.

## 4. Lakehouse table formats

Delta Lake · Apache Iceberg (v2/v3) · Apache Hudi · Apache Paimon.
Version/snapshot identifiers are captured on every evidence record, enabling exact replay and
time-travel re-execution (`FR-EXE-019`). Catalog integrations: Unity Catalog, AWS Glue Catalog,
Hive Metastore, Polaris, Nessie, Gravitino.

## 5. Object storage & filesystems

S3 (+ S3-compatible: MinIO, Ceph, Wasabi) · Google Cloud Storage · Azure Data Lake Gen2 / Blob ·
HDFS · NFS / SMB / CIFS · local filesystem · **SFTP / FTPS / FTP** · Azure Files ·
Google Drive / SharePoint / OneDrive (for document corpora and the spreadsheets that run banks).

## 6. Streaming & messaging

Apache Kafka (+ Confluent Cloud/Platform, MSK, Aiven) · Redpanda · Apache Pulsar · AWS Kinesis ·
Azure Event Hubs · Google Pub/Sub · **IBM MQ** · **TIBCO EMS / Rendezvous** · **Solace PubSub+** ·
RabbitMQ · ActiveMQ / Artemis · NATS / JetStream · ZeroMQ · MQTT · AMQP 1.0 · JMS generic.

Streaming validation modes: **observe** (sample and monitor), **tag** (annotate a header),
**route** (valid/invalid topics), **block** (reject at the producer via an interceptor), and
**dead-letter**. Schema registries: Confluent, AWS Glue Schema Registry, Apicurio, Azure Schema
Registry, plus plain JSON Schema / Protobuf descriptors / Avro `.avsc` / AsyncAPI.

## 7. Change data capture

Debezium (all connectors) · Oracle GoldenGate · Qlik Replicate · IBM InfoSphere CDC · AWS DMS ·
Google Datastream · Fivetran / Airbyte / Matillion logs · native CDC (SQL Server, Postgres logical
replication, MySQL binlog, MongoDB change streams). Operation semantics (insert/update/delete/
truncate) are preserved so controls can reason about *changes*, not only states.

## 8. NoSQL, search, graph, and specialist stores

**Document:** MongoDB, Couchbase, Amazon DocumentDB, Azure Cosmos DB, Firestore, RavenDB.
**Wide-column:** Cassandra, ScyllaDB, HBase, Google Bigtable, DynamoDB.
**Search:** Elasticsearch, OpenSearch, Solr.
**Key-value:** Redis, Aerospike, etcd.
**Graph:** Neo4j, Amazon Neptune, TigerGraph, JanusGraph, ArangoDB, Stardog, GraphDB (+ SPARQL/SHACL).
**Time series:** InfluxDB, TimescaleDB, Prometheus, **kdb+/q**, OneTick, QuestDB. (kdb+ matters:
it is the tick store in most trading floors.)
**Vector:** pgvector, Pinecone, Weaviate, Qdrant, Milvus, Chroma, FAISS indexes, OpenSearch k-NN.
**Geospatial:** PostGIS, Esri, GeoParquet, Shapefile, GeoJSON.

## 9. Applications & SaaS

**Core banking / capital markets:** Temenos, Finastra, FIS, Fiserv, Jack Henry, Avaloq, Mambu,
Thought Machine, Murex, Calypso, SimCorp Dimension, Charles River IMS, BlackRock Aladdin,
Bloomberg AIM/DL, Broadridge, ION, Adenza/Nasdaq (Calypso/AxiomSL), Moody's, MSCI, SS&C.
**ERP/CRM/HR:** SAP (S/4HANA, ECC, BW) via OData/RFC/BAPI/CDS, Oracle EBS/Fusion, Workday,
Salesforce, Microsoft Dynamics, ServiceNow, NetSuite, Coupa.
**Generic:** REST (OpenAPI-driven), GraphQL, SOAP/WSDL, OData v2/v4, gRPC.
Handled uniformly: auth (OAuth2/JWT/mTLS/API key), pagination, rate limits, retries, and
idempotent windowed extraction.

## 10. File & serialisation formats

**Tabular text:** CSV/TSV/PSV with dialect inference (delimiter, quoting, escaping, embedded
newlines, BOM, encoding detection), ragged-row handling, and multi-character delimiters.
**Fixed-width:** layout-driven, with per-field type/format and filler handling.
**Columnar/binary:** Parquet, ORC, Avro, Arrow/Feather, Protobuf, Thrift, MessagePack, BSON, HDF5.
**Semi-structured:** JSON, JSONL/NDJSON, XML (+ XSD/DTD validation), YAML, TOML, INI.
**Spreadsheets:** XLSX, XLSM, XLS, ODS — multi-sheet, merged cells, formulas-as-values, named
ranges, header detection. (Spreadsheets are a primary regulatory-reporting artefact; ignoring them
is a common vendor blind spot.)
**Statistical:** SAS7BDAT, XPT, SPSS SAV, Stata DTA, R RDS. **Legacy:** dBase/FoxPro DBF.
**Documents:** PDF (text + tables), DOCX, PPTX, TXT, RTF, HTML, EML/MSG, images with OCR.
**Compression:** gzip, bzip2, xz, zstd, snappy, lz4, deflate, zip, tar, 7z, RAR.
**Encryption:** PGP/GPG, age, S/MIME, AES-encrypted zip, KMS-envelope.

## 11. Mainframe & legacy

A deliberate investment, because it is where Tier-1 banks' authoritative data still lives:

- **EBCDIC** code pages (037, 273, 500, 1047, 1140-1149) with correct sign/decimal handling.
- **COBOL copybooks** as layout source: `PIC` clauses, `COMP`/`COMP-3` (packed decimal),
  `COMP-1/2`, zoned decimal, `OCCURS`, **`OCCURS DEPENDING ON`**, `REDEFINES`, `RENAMES`, level-88
  condition names (which become value-domain declarations automatically).
- **VSAM** (KSDS/ESDS/RRDS) extracts, **IMS** segment extracts, **IDMS**, **Adabas** natural files.
- Variable-length records with RDW/BDW, multi-record-type files with record-type discriminators.
- **Datasets from JCL job output**, generation data groups (GDG) with generation-aware freshness.

Copybook import automatically yields Attributes, types, value domains (from level-88s), and
candidate semantic types — turning a legacy artefact directly into semantic-layer content.

## 12. Financial message standards (Domain Pack #1)

| Standard | Coverage | Validation depth |
|---|---|---|
| **ISO 20022 / SWIFT MX** | pacs, pain, camt, sese, semt, setr, acmt, auth, remt, tsmt, colr, reda | XSD structural + ISO business rules + market-practice (CBPR+, HVPS+, SRG) usage guidelines |
| **SWIFT MT** | Categories 1–9 + common group; MT103, 202(COV), 300, 320, 540-548, 900/910, **940/942/950** | Block structure, field format specs, network validated rules (NVR), code-word validation |
| **FIX / FIXML** | 4.2, 4.4, 5.0 SP2, FIX Orchestra | Tag/value, repeating groups, required/conditional fields, enum validation, session vs. app layer |
| **FpML** | 5.x confirmation/reporting views | XSD + FpML validation rules + product-specific checks |
| **FINOS / ISDA CDM** | Trade, product, lifecycle event model | CDM's own prescribed validation logic; Rosetta DSL synonym mapping to FpML/FIX/ISO 20022 |
| **XBRL / iXBRL** | FINREP, COREP, ESEF, SEC filings | Taxonomy conformance, calculation and dimensional consistency, formula linkbase rules |
| **SDMX** | ECB/BIS/IMF statistical exchange | Structure definitions, code lists, series-key validation |
| **ISO 8583** | Card authorisation/clearing | Bitmap, field format, MTI validation |
| **NACHA / ACH**, **SEPA** (pain.001/008, pacs.008), **BACS**, **CHAPS**, **Fedwire**, **CHIPS** | Payment file formats | Layout, control totals, hash totals, routing/IBAN validity |
| **BAI2 / MT940 / camt.053** | Bank statements | Balance continuity, transaction-code validity, opening+movements=closing |
| **MISMO** | Mortgage | Schema + business rules |
| **ACORD** | Insurance | Schema + business rules |
| **DTCC / MarkitWire / TriOptima** feeds, **CLS**, **Euroclear/Clearstream** messages | Post-trade | Layout + reconciliation-oriented checks |
| **Regulatory returns**: FR Y-9C/Y-14/2052a, COREP/FINREP, AnaCredit, MiFIR/EMIR/SFTR/CFTC, Solvency II QRT, IFRS 17 | Return-level | Instruction-derived validation rules with citation ([12](12-banking-domain-pack.md)) |

**Why native parsing matters.** A `pacs.008` that is schema-valid can still be wrong: an IBAN whose
country does not match the BIC, a settlement date on a non-business day, an amount whose currency is
not permitted for the corridor. Format-aware parsing lets PQL assert on *business fields by name*
(`CHECK payment.debtor_agent_bic IS VALID bic`) instead of on XPath expressions — the difference
between a control a business person can read and one they cannot.

## 13. EDI and healthcare (other packs)

ANSI X12 (820, 834, 835, 837, 850, 856, 940, 997) · UN/EDIFACT · TRADACOMS · SAP IDoc ·
HL7 v2.x · HL7 FHIR R4/R5 · CDA · DICOM metadata · NCPDP.

## 14. Feed handling — the operational reality

A "feed" is not a file; it is a contract about arrival. Prama models it explicitly:

- **Landing detection:** polling, inotify, S3 events, EventBridge, Azure Event Grid, GCS
  notifications, MQ triggers.
- **Naming pattern** with date/sequence tokens; timezone-aware business-date derivation.
- **Expected arrival window** with a business calendar; late/missing detection as a first-class
  control (`FR-MON-014`).
- **Manifest / control files:** expected file lists, record counts, hash totals, control totals.
- **Header/trailer conventions:** trailer record count and sum checks compared to the body.
- **Multi-file logical batches:** header + detail + trailer, or split parts, treated as one Dataset.
- **Duplicate and out-of-sequence delivery** detection by content digest and sequence number.
- **Partial/truncated file** detection (size, terminator, decompression failure).
- **Decryption and signature verification** as a pre-parse step with evidence of who signed.
- **Archive and replay:** every accepted feed file is fingerprinted so any historical run replays.

## 15. Reference-data integrations (consumed, not licensed)

GLEIF LEI (+ ISIN-to-LEI relationship files) · ANNA DSB (ISIN/UPI) · OpenFIGI · exchange MICs
(ISO 10383) · ISO 4217 / 3166 / 20022 external code sets · SWIFT BIC directory · IBAN Registry ·
national clearing directories · Experian / Melissa / Loqate address verification · sanctions and PEP
lists (OFAC, EU, UN, HMT) · market/settlement calendars · FX rate sources (ECB, central banks, vendor).

All reference data is **versioned and as-of addressable**, so a control executed in March against
the March GLEIF snapshot replays identically in November (`§9` of [07](07-rule-language-spec.md)).

## 16. Outbound integrations

**Catalogs/governance:** Collibra, Alation, Atlan, OpenMetadata, DataHub, Purview, Unity Catalog,
data.world, Informatica IDMC.
### 16.1 Catalogue write-back, as built

Three adapters ship behind the SPI in `prama.integrate.catalog`: **Collibra**
(an attribute on an asset), **Alation** (a custom field on a data object) and
**DataHub** (an aspect on a dataset URN). The rest of the list above is the
target, not the state.

The three disagree about what a quality state is, and the honest adapter is the
one that says what it had to drop rather than the one that maps everything onto
something. Alation has nowhere to put an **evidence reference** — no field means
"this is the run behind the verdict", and free text makes it look like a comment
somebody typed — so it declares that field unsupported and every write report
names it as dropped. Nobody then reads an absent link as "there was no
evidence".

Shared behaviour, decided once in the base class:

- **An undated badge cannot be constructed at all.** "Trusted" on a table nobody
  has checked since March reads as current, and a reader has no way to tell.
- **A missing asset is refused, never created.** An adapter that created it would
  define the estate in the catalogue, and an estate defined in two places
  disagrees with itself.
- **One bad table does not stop the other thirty-nine.** They would otherwise
  show yesterday's verdict with today's confidence.
- **Every write is residency-checked**, per badge, as a registered egress point.

Two vendor-specific traps, each with a test. Collibra assets are addressed by
**id and never by name**: two systems in one estate can have a table with the
same name, and a name-keyed write puts a trading badge on a finance table.
DataHub URNs carry an **environment segment**, and a URN that differs by it
creates a second, empty dataset rather than failing — the badge lands somewhere
nobody looks.

The transport is injected, so a deployment substitutes a client with its own
mTLS, proxy, retry and rate-limit policy applied — and so all three can be
tested. **None has been run against a live server.** The request shapes are from
each vendor's documented API; what the suite verifies is the adapter's own
behaviour, not that a real Collibra accepts it.

**Orchestration:** Airflow, Dagster, Prefect, dbt Cloud/Core, Databricks Workflows, ADF,
Control-M, Autosys, Step Functions, Argo, Tidal.
**Ticketing/ITSM:** Jira, ServiceNow, Azure DevOps, Zendesk, Remedy.
**Chat/notification:** Slack, Microsoft Teams, PagerDuty, Opsgenie, email/SMTP, SMS, webhooks.
**BI:** Tableau, Power BI, Looker, Qlik, Superset, Metabase, ThoughtSpot (embeds + quality badges).
**GRC:** RSA Archer, MetricStream, ServiceNow GRC, IBM OpenPages, Workiva.
**Observability/SIEM:** Datadog, Grafana, Splunk, Elastic, New Relic, Dynatrace (via OpenTelemetry).
**Standards out:** OpenLineage, OpenTelemetry, ODCS, SHACL/RDF, OpenAPI, MCP.

## 17. Connector delivery plan

| Wave | Count | Contents |
|---|---|---|
| **GA** | ~45 | Top warehouses (8), lakehouse formats (4), major RDBMS (10), object stores/SFTP (6), Kafka family (4), core file formats (12), COBOL/EBCDIC, SWIFT MT/MX, FIX, XBRL, generic REST/JDBC/ODBC |
| **GA + 6mo** | ~85 | NoSQL, CDC, remaining message standards (FpML, CDM, ISO 8583, NACHA/SEPA, BAI2), SaaS/core-banking, EDI, kdb+ |
| **GA + 12mo** | ~120+ | Long-tail applications, vector/geo/time-series, healthcare pack, partner-contributed connectors via the SDK |

**Certification.** Every connector ships with a conformance test suite (discovery, snapshot
correctness, pushdown equivalence, type fidelity, error handling, performance floor) and a published
capability matrix. A connector is not "supported" until it passes; partner connectors are labelled
by certification tier.

---

<div align="center">
<img src="assets/prama-mark.svg" width="30" alt=""/><br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.<br/>
See <a href="../LICENSE">LICENSE</a> and <a href="../NOTICE">NOTICE</a>. Third-party names and marks are the property of their respective owners.</sub>
</div>
