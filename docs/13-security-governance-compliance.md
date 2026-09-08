<img src="assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>


---
# 13 — Security, Governance, Compliance & Evidence

Requirements: [`NFR-SEC`](05-requirements-nonfunctional.md#d-security-nfr-sec),
[`NFR-PRV`](05-requirements-nonfunctional.md#e-privacy--data-handling-nfr-prv),
[`NFR-CMP`](05-requirements-nonfunctional.md#f-compliance--auditability-nfr-cmp),
[`FR-ADM`](04-requirements-functional.md#u-administration--operations-fr-adm).

---

## 1. Threat model

| Actor | Capability | Primary mitigations |
|---|---|---|
| External attacker | Internet-facing surface, credential stuffing, supply chain | SSO+MFA, no credentials at rest, signed artefacts + SBOM, network isolation, WAF, pen testing |
| Malicious insider (customer) | Legitimate access misused to hide a defect or falsify an attestation | Immutable evidence, SoD, approval workflows, complete audit log, tamper-evident hash chain |
| Curious insider (Prama staff) | Operator access in SaaS | Break-glass with approval and recording, no standing production data access, customer-managed keys, confidential-computing option |
| Compromised source system | Poisoned data, adversarial content | Data treated as untrusted; no instruction-following from data; parser hardening and fuzzing |
| Prompt-injection adversary | Text in a column comment, document, or record aimed at the LLM agent | Untrusted-content contract, tool allow-lists, output-schema validation, adversarial regression corpus |
| Multi-tenant neighbour | Cross-tenant leakage via cache, model, embedding, or query | Tenant as a first-class key everywhere; automated isolation tests each release |
| Regulator/auditor (adversarial review) | Challenges the integrity of the evidence itself | Deterministic replay, hash chain, external anchoring, signed executions |

---

## 2. Identity, access, and segregation of duties

- **AuthN:** OIDC/SAML SSO, SCIM provisioning, enforced MFA, short-lived service tokens, mTLS
  between planes.
- **AuthZ:** RBAC over ~30 built-in roles composed from fine-grained permissions, plus ABAC over
  attributes of the *object* (domain, criticality tier, classification, jurisdiction) and the
  *subject* (department, clearance, location). Deny by default.
- **Core roles:** Platform Admin · Domain Owner · Data Architect · Steward · Control Author ·
  Control Approver · Connection Admin · Incident Responder · Auditor (read-only, evidence-scoped) ·
  Consumer (read quality state only) · Agent (the chat assistant, always bound to a human identity).
- **Segregation of duties, enforced not advised:** the author of a rule cannot approve it; the
  approver of a control cannot attest to its outcome alone in Tier-1 scopes; a connection admin
  cannot read failing-row samples unless separately granted; a person who suppresses an alert cannot
  also close the resulting incident. Violations are blocked at the policy service, and the SoD
  matrix is exportable for audit.
- **Least privilege at source:** read-only by default. Write access to a source requires a separate,
  explicit, per-scope grant plus an approved change record, and every write is evidenced
  (`FR-REM-005`).

---

## 3. Data protection

**Minimisation is architectural, not procedural.** Because execution is pushdown-first, the only
things that leave a source are metrics, verdicts, and — where explicitly permitted — a bounded
number of masked failing-row samples. There is no Prama-side copy of customer data to protect
(`NFR-PRV-001`).

| Control | Implementation |
|---|---|
| Encryption | TLS 1.3 in transit; AES-256-GCM at rest; CMK/BYOK, and HYOK for the highest tiers |
| Sample governance | Retention opt-in per dataset; count-capped; masked per classification; access-logged; TTL-expired |
| Masking | Deterministic and format-preserving options; applied identically in UI, alerts, exports, chat prompts, and API |
| Classification | Inferred (PII/MNPI/restricted) and declared; drives masking, residency, and LLM-eligibility |
| Residency | Execution and storage locality enforced per declared jurisdiction; cross-border movement is blocked, not warned |
| Erasure | Subject data purged from samples/evidence with a tamper-evident tombstone that preserves hash-chain integrity |
| Key management | External KMS/HSM; per-tenant key hierarchy; documented rotation |

---

## 4. LLM and AI-specific security

1. **No data content ever instructs the system.** All row values, column comments, document text,
   and retrieved passages are wrapped as untrusted content; the system contract forbids following
   instructions found there. Verified by an adversarial corpus regression-tested each release
   (`NFR-SEC-010`).
2. **Closed tool surface.** The agent may call only typed, allow-listed API operations; there is no
   free-form code execution and no direct database access. Read tools and *propose* tools only.
3. **Output validation.** Every model output is schema-validated; generated PQL is parsed,
   type-checked, and sandbox-executed before display (`NFR-AI-008`).
4. **Classification-aware prompting.** Masked-class values never enter a prompt. Tenants may forbid
   external model providers entirely and run local open-weight models.
5. **No training on customer data.** Never used to train shared models; never transmitted to a
   provider for training (`NFR-PRV-006`).
6. **Full auditability.** Every prompt hash, model version, tool call, token count, and cost is
   logged and exportable (`FR-CHT-012`).

---

## 5. Governance operating model

Prama is the execution layer for a governance programme; it must fit the customer's operating model
rather than impose one.

- **Ownership:** every dataset, attribute, relationship, control, and incident has an accountable
  owner, sourced from the semantic layer and synchronised with the IdP/HR feed. Orphaned objects are
  reported, not tolerated.
- **Policy as configuration:** approval requirements, evidence levels, retention, masking, residency,
  cadence floors, and severity floors are set per domain and per criticality tier, inherited by
  every object within.
- **Change control:** every rule and declaration change is versioned, approved, effective-dated, and
  attributable; emergency changes are possible but flagged and reviewed.
- **Exception management, not suppression:** every exception has an owner, a justification, and a
  mandatory expiry. Expired exceptions reopen automatically. The exception register is a standard
  report.
- **Recertification:** periodic re-attestation of ownership, criticality, and definitions with due
  dates and escalation (`FR-MET-108`).
- **Integration with GRC:** issues, controls, and attestations synchronise with Archer,
  MetricStream, ServiceNow GRC, OpenPages, and Workiva so Prama becomes the *evidence engine* behind
  the customer's existing risk framework rather than a competing system of record.

---

## 6. The evidence model — the heart of auditability

### 6.1 EvidenceRecord

Every assertion execution — without exception — appends one immutable record:

```json
{
  "evidence_id": "ev:01J8Z…",
  "tenant": "t:acme-bank",
  "recorded_at": "2026-03-31T06:14:22.481Z",
  "logical_time": {"business_date":"2026-03-31","calendar":"TARGET2","as_of":"2026-03-31T06:00:00Z"},
  "control": {
    "control_id":"ctl:9f21…","version":7,
    "pql_hash":"sha256:1a7b…","ir_hash":"sha256:9c4f…",
    "rendered":"Every active position must have a notional amount.",
    "severity":"critical","dimensions":["completeness"],
    "provenance":{"source":"declaration","declared_by":"rel:R-4471"},
    "authored_by":"user:jsmith","approved_by":"user:aroy","approved_at":"2026-01-14T09:02:11Z"
  },
  "scope": {
    "dataset":"ds:positions_eod","binding":"bind:snowflake/RISK.POSITIONS_EOD",
    "filter":"trade_status = 'ACTIVE'","segment":null,
    "snapshot":{"kind":"iceberg_snapshot","id":"7742901183","exact":true},
    "sampling":{"strategy":"full_scan","seed":null,"coverage":1.0}
  },
  "execution": {
    "engine":"snowflake","engine_version":"8.42.1","plan_hash":"sha256:be07…",
    "started_at":"2026-03-31T06:14:19.902Z","duration_ms":2579,
    "bytes_scanned":41203118080,"cost_units":3.7,
    "worker":"wk:eu-west-1/7","worker_key_id":"key:2026Q1-eu-3"
  },
  "result": {
    "verdict":"fail",
    "metrics":{"scanned_rows":1204418,"violating_rows":4182,"violation_rate":0.003472},
    "threshold":{"metric":"violation_rate","op":"<=","value":0.0005},
    "samples_ref":"sample:8b1c… (50 rows, masked:pii-default, ttl:90d)"
  },
  "integrity": {
    "prev_hash":"sha256:44ad…",
    "record_hash":"sha256:e93c…",
    "signature":"ed25519:…",
    "anchor":{"scheme":"daily-merkle-root","root":"sha256:0fa1…"}
  }
}
```

### 6.2 Properties we guarantee

| Property | How |
|---|---|
| **Immutable** | Append-only store; object-lock/WORM export; no update or delete API exists |
| **Tamper-evident** | Per-record hash chained to its predecessor; daily Merkle root; optional external anchoring |
| **Attributable** | Signed by the executing worker's key; rule authorship and approval carried on the record |
| **Reproducible** | `ir_hash` + `snapshot` + `engine_version` + `seed` fully determine the verdict (`NFR-CMP-002`) |
| **Complete** | Every execution records, including errors, skips, and indeterminates — absence of evidence is itself detectable |
| **Honest about limits** | Where a source cannot supply an exact snapshot, `exact:false` is recorded; sampled results carry their coverage and confidence |
| **Exportable** | Open formats (JSON/Parquet), documented schema, full-tenant export (`NFR-POR-004`) |
| **Retained** | 1–25 years per criticality tier, with legal hold |

### 6.3 Deterministic replay

Any historical execution can be re-run against the same snapshot and rule version. The replay
either (a) reproduces the verdict exactly, or (b) produces a **replay divergence report** naming the
cause — source data was restated, the snapshot expired, the engine version changed, or a referenced
code list moved. Divergence is itself evidence, and it is the honest answer to *"can you prove this
number was right in March?"*

This is the single hardest capability to retrofit and the one competitors cannot easily copy: it
requires snapshot discipline, content-addressed rules, versioned reference data, and an immutable
ledger, designed in from the start (`AD-03`).

### 6.4 Attestation

A period attestation binds: the control set in force, every execution's evidence, exceptions with
justifications and approvals, open issues, and the attester's e-signature with non-repudiation. The
artefact carries the [attestation seal](brand.md#3-the-mark--the-pramāṇa-prism), is immutably
retained, and is exportable as a single self-contained package with its verification instructions —
so a regulator can check the hash chain without access to Prama.

---

## 7. Compliance posture

| Framework | Position |
|---|---|
| **SOC 2 Type II** | Target within 12 months of GA |
| **ISO/IEC 27001**, **27017**, **27018** | Target within 12 months of GA; 27701 (privacy) to follow |
| **GDPR / UK GDPR / CCPA / DPDP** | Data-minimising architecture; DPA and SCCs; residency enforcement; erasure with audit integrity |
| **DORA** | ICT risk-management alignment, incident records, third-party register support, resilience testing evidence; on-prem/air-gap removes concentration risk |
| **EU AI Act** | Prama's learned components are documented to Art. 10/Art. 9 expectations; where a customer's own high-risk AI depends on data, Prama supplies the data-governance evidence |
| **SR 11-7 / TRIM** | Model cards, validation records, versioning, human oversight, challenger evidence |
| **BCBS 239** | See [12 §5.1](12-banking-domain-pack.md#51-bcbs-239--rdarr--the-anchor) |
| **SOX / ICFR** | Control evidence, SoD, change control, attestation |
| **PCI-DSS** | Where card data is in scope: classification, masking, no PAN retention in samples by default |
| **FedRAMP / IRAP / C5** | Considered post-GA subject to segment demand |

**Shared-responsibility model** is published explicitly: what Prama secures, what the customer
secures (source credentials, network, IdP configuration, read policies, classification accuracy),
and the boundary between them.

---

## 8. Secure development

Threat modelling per epic · SAST/DAST/dependency and container scanning as CI gates · SBOM per
release · signed artefacts with SLSA L3 provenance target · secret scanning · mandatory code review
with a security reviewer for privileged paths · fuzzing of every parser (a COBOL/EBCDIC/SWIFT parser
is a memory-safety surface) · annual independent penetration test plus per-major-release automated
testing · a published vulnerability-disclosure policy with Critical ≤ 7 days / High ≤ 30 days
remediation SLAs · and an architecture test in CI that fails the build if any code path allows an
LLM output to reach a verdict (`NFR-AI-002`).

---

<div align="center">
<img src="assets/prama-mark.svg" width="30" alt=""/><br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.<br/>
See <a href="../LICENSE">LICENSE</a> and <a href="../NOTICE">NOTICE</a>. Third-party names and marks are the property of their respective owners.</sub>
</div>
