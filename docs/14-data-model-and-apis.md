<img src="assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

> ***pramā*** (Sanskrit **प्रमा**) — *valid knowledge: a cognition that is both true and arrived at
> by a reliable means*. Its companion ***pramāṇa*** (प्रमाण) is *the instrument by which valid
> knowledge is obtained*. Prama is that instrument for an organisation's data — it does not decide
> what is true, it is how a belief about data becomes **justified**.
>
> **Declare it. Prove it. Trust it.**


---
# 14 — Canonical Data Model & APIs

Requirements: [`FR-EXT`](04-requirements-functional.md#s-extensibility-apis--integration-fr-ext).

**API-first rule (`A6`):** the console, CLI, chat assistant, and MCP server are all clients of the
same public API. There is no privileged internal surface. If a capability is not in the API, it does
not exist.

---

## As built

`schema/sqlite.sql` and `schema/postgres.sql` are the authority, and they are
**byte-identical apart from their headers** — `tests/db/test_schema.py` fails if
they ever are not. There are **no migrations**: `prama db init` applies the
schema idempotently and `prama db verify` fails loudly on drift rather than
repairing it.

Only four column types are permitted, because only those mean the same thing in
both engines: `VARCHAR(n)`, `TEXT`, `INTEGER`, `REAL`. Timestamps are ISO-8601
UTC text in `VARCHAR(32)`, which sorts chronologically. Identifiers are ULIDs
minted client-side, so a worker needs no round trip and a retry can reuse one.

`prama.db` is the only package that may import SQLAlchemy;
`tests/architecture/test_layering.py` enforces it by import scanning. Everything
else goes through DAOs behind a unit of work, and twenty-two tenant-isolation
tests scan those DAOs **by method signature** rather than by name, so a new one
that forgets its tenant filter fails the build.

`prama.api` is the FastAPI surface with its error taxonomy and schema mapping.

**Not built:** the GraphQL surface in §7, and the API has not been load-tested
at the rates §8 states.

---

## 1. Canonical entities

### 1.1 Semantic layer

| Entity | Key fields | Relationships |
|---|---|---|
| **Domain** | id, name, description, owner, parent | contains Datasets, Concepts, Journeys |
| **Dataset** | id, name, description, purpose, owner, steward, custodian, domain, criticality_tier, grain, business_key[], temporality, rhythm{frequency, arrival_window, calendar, cut_off, volume_range, volume_drivers[]}, authoritativeness, source_of_truth_ref, retention, jurisdiction, classification, lifecycle_state, effective_from/to | has Attributes, Bindings, Relationships, Controls, Incidents, Scores |
| **Attribute** | id, dataset, name, definition, interpretation, semantic_type, unit, currency_ref, scale, precision, value_domain{kind, codelist_ref, range, pattern}, optionality{always\|conditional(expr)\|optional}, is_cde, obligations[], sensitivity, masking_policy, expected_behaviour, owner, glossary_term | maps_to ConceptProperty; bound to PhysicalField |
| **Concept** | id, name, description, domain | has ConceptProperty |
| **ConceptProperty** | id, concept, name, definition, semantic_type, value_domain | mapped_from Attributes |
| **Relationship** | id, type, from_dataset, to_dataset[], match_keys[] (attribute refs), cardinality, tolerance, offset, filter, description, owner, criticality, confidence, status{proposed\|confirmed\|rejected}, derived_controls[] | generates Controls |
| **Journey** | id, name, description, owner, steps[] (dataset + relationship refs, ordered), sla | aggregates health |
| **Binding** | id, dataset\|attribute, connection, physical_ref{schema, object, field, path}, transform, status, confidence, last_verified_at | resolves to physical |
| **Connection** | id, name, source_type, config (typed per family), credential_ref (vault), network, read_policy{scopes, max_bytes, windows, default_sampling, sample_retention, masking}, budget, health, owner | used by Bindings |
| **Codelist** | id, name, standard_ref, version, as_of, values[] | referenced by value domains |
| **Calendar** | id, name, holidays[], conventions | referenced by rhythm and controls |

### 1.2 Control layer

| Entity | Key fields |
|---|---|
| **Control** | id, name, pql_source, pql_hash, ir, ir_hash, rendered_text, kind{check\|monitor\|reconciliation\|resolution\|contract}, scope_ref, severity, dimensions[], threshold, evidence_level, on_fail, schedule, provenance{source, declared_by, induced_by, pack_ref, citation}, lifecycle_state, version, authored_by, approved_by, effective_from/to, owner, obligations[] |
| **ControlSuite** | id, name, controls[], ordering, short_circuit_policy |
| **Monitor** | (a Control of kind=monitor) + baseline_spec, seasonality, detector, calibration_ref, sensitivity{budget\|fdr\|power}, guarantee_status |
| **Proposal** | id, candidate_control, origin{miner\|llm\|declaration\|pack\|example\|document}, evidence, backtest, estimated_alert_volume, estimated_cost, utility_score, status, decided_by, decision_reason |
| **Exception** | id, control, scope, justification, owner, approved_by, expires_at |
| **Contract** | id, odcs_ref, version, schema, quality_clauses[], sla, conformance_status |

### 1.3 Execution & evidence

| Entity | Key fields |
|---|---|
| **Run** | id, trigger{schedule\|event\|manual\|ci}, scope, planned_controls[], started/ended, status, cost, budget_state |
| **EvidenceRecord** | see [13 §6.1](13-security-governance-compliance.md#61-evidencerecord) |
| **Metric** | dataset, attribute, segment, name, value, computed_at, snapshot, sampling, run_ref |
| **Finding** | id, kind{profile\|semantic_type\|constraint\|relationship_candidate\|drift\|trend\|metadata_drift}, subject, content, computed_at, snapshot, sampling, staleness_state, confidence |
| **Sample** | id, evidence_ref, rows (masked), masking_policy, ttl, access_log |

### 1.4 Operations

| Entity | Key fields |
|---|---|
| **Incident** | id, title, severity, state, opened_at, scope, correlated_evidence[], hypotheses[], impact{datasets, reports, models, returns}, owner, sla, disposition, resolution_notes, closed_at |
| **Break** | id, reconciliation_run, side_a_ref, side_b_ref, break_type, amount, currency, ageing, classification{proposed, confirmed}, owner, state, commentary |
| **Alert** | id, incident, channel, recipients, sent_at, acknowledged_by, outcome |
| **Score** | subject{dataset\|domain\|journey\|enterprise}, period, dimension_scores{}, composite, method, weights, intrinsic_trust, effective_trust, derivation_path, stale_fraction |
| **Attestation** | id, period, scope, controls[], exceptions[], attester, signed_at, signature, seal_ref, artefact_ref |
| **FeedbackEvent** | id, kind, subject, actor, value, occurred_at (the learning-loop substrate) |
| **AuditEvent** | id, actor, action, object, before, after, at, ip, session |

---

## 2. REST API (OpenAPI 3.1)

Base: `https://{host}/api/v1` · JSON · cursor pagination · ETags · `Idempotency-Key` on all writes ·
RFC 9457 problem details for errors · rate limits with `RateLimit-*` headers.

```
# Semantic layer
GET    /domains                                   POST /domains
GET    /datasets?domain=&criticality=&owner=&unbound=true
POST   /datasets                                  GET/PATCH/DELETE /datasets/{id}
GET    /datasets/{id}/attributes                  POST /datasets/{id}/attributes
GET    /datasets/{id}/profile?as_of=              GET  /datasets/{id}/findings
GET    /datasets/{id}/lineage?direction=&depth=   GET  /datasets/{id}/score?period=
POST   /datasets/{id}/bindings                    POST /datasets/{id}/re-examine
GET    /concepts  POST /concepts                  GET/POST /concepts/{id}/properties
GET    /relationships  POST /relationships        GET/PATCH /relationships/{id}
GET    /relationships/{id}/derived-controls
GET    /journeys  POST /journeys                  GET /journeys/{id}/health
GET    /estate/graph?overlay=health|coverage|trust|criticality
GET    /estate/maturity?domain=

# Connections
GET    /connections   POST /connections           POST /connections/{id}/test
GET    /connections/{id}/discover?path=&rank=size|recency|usage
POST   /connections/{id}/binding-suggestions      GET  /connections/{id}/budget

# Controls
GET    /controls?dataset=&dimension=&severity=&state=
POST   /controls                                  GET/PATCH /controls/{id}
POST   /controls/compile      (PQL -> IR + plan + cost, no execution)
POST   /controls/backtest     (against historical snapshots)
POST   /controls/{id}/approve | /reject | /retire
GET    /proposals?status=pending&origin=          POST /proposals/{id}/decide
GET    /coverage?domain=&by=cde|dimension|dataset
POST   /contracts/import      (ODCS)              GET  /contracts/{id}/conformance

# Execution & evidence
POST   /runs                  (scope, controls, mode=execute|plan|dry-run)
GET    /runs/{id}                                 GET  /runs/{id}/evidence
GET    /evidence?control=&dataset=&from=&to=      GET  /evidence/{id}
POST   /evidence/{id}/replay                      GET  /evidence/{id}/verify
GET    /metrics?dataset=&attribute=&name=&from=&to=&segment=

# Operations
GET    /incidents?state=&severity=&owner=         POST /incidents/{id}/transition
GET    /incidents/{id}/hypotheses                 POST /incidents/{id}/hypotheses/{h}/confirm
GET    /incidents/{id}/impact
GET    /reconciliations/{id}/breaks?state=&ageing= POST /breaks/{id}/classify
GET    /scores?subject=&period=                   GET  /scores/{id}/derivation
GET    /reports  POST /reports/{id}/generate      POST /attestations/{id}/sign

# Assistant & meta
POST   /assistant/messages    (streaming; returns grounded answer + proposals)
GET    /audit?actor=&object=&from=&to=
GET    /health  /readiness  /version  /capabilities
```

**gRPC** mirrors the high-throughput paths: `EvidenceService.Append`, `MetricService.Ingest`,
`StreamValidation.Validate` (bidirectional streaming for in-flight enforcement).

---

## 3. Events

Published to the customer's bus (Kafka/SNS/Event Hubs/webhook) with at-least-once delivery, a schema
registry entry, and replay by offset/time. CloudEvents envelope.

```
prama.dataset.declared | .updated | .bound | .re_examined
prama.relationship.proposed | .confirmed | .drifted
prama.finding.produced | .stale
prama.control.proposed | .approved | .retired | .executed
prama.assertion.failed | .passed | .indeterminate
prama.incident.opened | .updated | .resolved | .reopened
prama.break.created | .classified | .closed
prama.score.changed | .trust_propagated
prama.contract.violated | .conformant
prama.attestation.signed
prama.platform.degraded | .model_rolled_back
```

Also emitted: **OpenLineage** run events for every dataset Prama reads (`FR-LIN-005`), and
**OpenTelemetry** traces for every run and control, over OTLP when `observability.tracing.exporter: otlp`
(`FR-EXE-021`). Metrics are exported for **Prometheus** at `GET /metrics`, with `/livez` and `/readyz` probes
([operations/observability.md](operations/observability.md)).

---

## 4. SDKs and tooling

- **Python** — first-class: declare semantic objects, author and run controls, pull metrics into
  pandas/Polars, embed validation inside a Spark or Airflow task.
- **Java/Scala** — JVM engines, Flink/Spark embedding, mainframe-adjacent integration.
- **TypeScript** — UI embeds, webhooks, internal portals.
- **CLI** (`prama`) — `login · connect · discover · declare · compile · lint · fmt · test · run ·
  plan · diff · import · export · evidence verify · pack install`.
- **Terraform provider** and **Kubernetes CRDs** for infrastructure-as-code management of
  connections, domains, datasets, and control suites.
- **CI actions** for GitHub, GitLab, Azure DevOps, Jenkins.
- **LSP server** for PQL in any IDE.

---

## 5. GitOps

The semantic layer and control estate serialise to a documented directory layout:

```
prama/
├── domains/credit-risk/
│   ├── domain.yaml
│   ├── datasets/positions_eod.yaml          # declaration + attributes + bindings
│   ├── relationships/R-4472_positions_gl.yaml
│   └── controls/positions_eod.pql
├── concepts/instrument.yaml
├── journeys/frtb.yaml
├── connections/snowflake-risk.yaml          # no secrets; vault references only
└── packs.lock                               # pinned pack versions
```

Bidirectional sync with drift detection: a change made in the UI produces a commit (or a PR);
a change made in Git is applied on merge. Conflicts surface as a reviewable diff. This is how the
business-facing UI and engineering-grade change control coexist (`FR-EXT-009`).

---

## 6. MCP server

Prama exposes an MCP server so the customer's own agents, and developer agents in IDEs, can work
against the quality estate under the same policy controls (`FR-EXT-008`).

| Tool | Class | Description |
|---|---|---|
| `search_estate` | read | Business-language search over datasets, attributes, concepts |
| `describe_dataset` | read | Declaration, profile, controls, health, staleness |
| `get_quality_state` | read | Scores, trust with derivation, open incidents |
| `explain_incident` | read | Hypotheses with evidence, impact |
| `query_evidence` | read | Evidence records for a control/period |
| `propose_control` | propose | Emits PQL + backtest + cost as a Proposal; never activates |
| `propose_relationship` | propose | Creates a relationship Proposal |
| `request_re_examination` | operate | Queues a re-examination within budget, subject to permission |

Read and *propose* tools only by default; any operate tool is opt-in per tenant and always subject
to the invoking user's permissions and the approval workflow.

---

## 7. Compatibility policy

Semver on the API and the IR. No breaking change without a 12-month deprecation window and a
documented migration. `/capabilities` advertises supported features, engines, pack versions, and IR
version so clients can degrade gracefully. Agents remain compatible across N-2 control-plane
versions (`NFR-OPS-005`).

---

<div align="center">
<img src="assets/prama-mark.svg" width="30" alt=""/><br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.<br/>
See <a href="../LICENSE">LICENSE</a> and <a href="../NOTICE">NOTICE</a>. Third-party names and marks are the property of their respective owners.</sub>
</div>
