<img src="../assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>


---
# 13 — Security, Governance, Compliance & Evidence

Requirements: [`NFR-SEC`](05-requirements-nonfunctional.md#d-security-nfr-sec),
[`NFR-PRV`](05-requirements-nonfunctional.md#e-privacy--data-handling-nfr-prv),
[`NFR-CMP`](05-requirements-nonfunctional.md#f-compliance--auditability-nfr-cmp),
[`FR-ADM`](04-requirements-functional.md#u-administration--operations-fr-adm).

---

## As built

See §2.1 (single sign-on), §2.2 (SCIM), §2.3 (customer-managed keys), §3.0
(secrets), §3.1 (residency and egress) and §6.2a (verifying evidence without
Prama), each of which states what exists and what does not in its own place
rather than in a summary here that would drift from them.

The headline: the security surface is implemented, and three parts of it have
**not met the real thing** — no cloud KMS has been exercised, the Vault provider
has not been run against a live server, and no disconnected install has been
performed on a host with no route out. Each module says so in its own docstring,
and a test asserts the docstring still says so.

Segregation of duties reaches the rule as well as the declaration: every control
activation goes through `prama.controls.approval`, so a Tier-1 control a person
wrote must be switched on by somebody else.

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

### 2.1 Single sign-on

`prama.security.oidc` verifies an OIDC ID token and maps its claims to a
principal. It needs the `sso` extra (`pip install -e ".[sso]"`), and without it
every entry point refuses **by name** rather than falling back to something
weaker — a deployment that cannot verify signatures must refuse to do SSO, not
do it badly. That extra exists because verifying an RS256 signature needs real
asymmetric cryptography, and hand-rolling the PKCS#1 v1.5 padding check is how
forged signatures get accepted.

The whole security of SSO is *verify the signature before believing a single
claim*. A verifier that parses the payload first has already chosen a key, an
issuer and a tenant from attacker-controlled data. The refusals, each a real
attack rather than a hypothetical, and each with a test that forges the token:

| Refused | Why it is an attack |
|---|---|
| `alg: none` | A token asserting it is unsigned; a verifier dispatching on the token's own `alg` verifies nothing |
| HMAC algorithms | Algorithm confusion: sign with HS256 using the provider's *public* RSA key, which is public |
| Unknown `kid` | Trying every key until one works turns a rotated-out key into a valid signer forever |
| No `kid`, several keys | Guessing is not verification |
| Wrong audience | Genuinely signed, genuinely current, and issued for a different client of the same provider |
| Wrong issuer | Genuinely signed by somebody else |
| Expired / future `iat` / future `nbf` | A future `iat` extends the token's usable life by however far ahead it claims |
| Missing or replayed nonce | The only thing a nonce is for |
| Empty `sub` | The subject is the identity; an empty one identifies nobody |
| `use: enc` keys in the JWKS | A key the provider never signs with would verify a token |

Clock skew is tolerated to sixty seconds in both directions and no further.

Group-to-role mapping is **declared**, and a group with no mapping grants
nothing — an unmapped group silently conferring a default role is how everybody
in the directory becomes an owner. `ClaimMapping.unmapped()` reports the groups
that granted nothing, because somebody who signs in successfully and can see
nothing has a configuration problem that looks exactly like a permissions bug.

Local identity is keyed on **issuer *and* subject**: a subject is unique within
its issuer and nowhere else, so keying on subject alone lets two providers
collide onto one account.

The JWKS is **passed in, not fetched**. Fetching is an egress and a caching
problem; mixing either into a verifier makes it untestable offline.

### 2.2 SCIM provisioning

`prama.security.scim` decides what the directory's view means for an account.
The protocol is tedious and the decisions are not, so this is the decisions.
**The HTTP endpoints that speak SCIM's wire format are not written** — what is
here is the part where being wrong is expensive.

**Nobody is ever deleted.** A SCIM `DELETE` deactivates. The person signed
things — approved a control, attested a period — and deleting the account leaves
an attestation signed by a principal that does not exist. That is a hole in the
audit trail, not a tidy-up. There is no `DELETE` outcome in the enum at all.

**Demotion and deprovisioning are different, and both happen.** Someone who
leaves the owners group loses the role and keeps the account; someone who leaves
the company keeps neither. The directory expresses these differently — a group
change versus `active: false` — and conflating them either locks out somebody
who moved desk or leaves a leaver signed in.

**Roles are replaced, never merged.** The directory is authoritative for group
membership. A union means a role granted once is granted forever, and the group
somebody was removed from six months ago still confers it.

**The last active administrator cannot be deprovisioned.** A directory
misconfiguration that deactivates every admin locks everybody out of the tenant
with no way back that does not involve the database. A batch counts the admin
pool once across the whole sync and decrements it as it goes, so a sync
deactivating three of four refuses on the one that would leave none — not on the
first one it reaches.

**An absent field is not a request to blank one.** SCIM PATCH omits what it is
not changing, and treating omission as deletion wipes an email address on every
sync.

`REFUSED` is distinct from `NONE`: nothing changed, and something should have.

### 2.3 Customer-managed keys

`prama.security.cmk`. The promise a regulated buyer wants is not "your data is
encrypted" — it is **"we can take the key away and you cannot read it any
more"**, which is a claim about who holds what.

A fresh AES-256 data key encrypts each payload; the customer's key (their KMS,
HSM or Vault) wraps the data key; Prama stores the wrapped key beside the
ciphertext and never holds the customer key. Revoke it and every envelope it
wrapped is unreadable, permanently, with no action needed on Prama's side and
none possible.

That last property is the product, and its cost is stated rather than
discovered: **revocation is neither reversible nor selective.** A customer who
revokes to satisfy an erasure request has also made every backup of that data
unreadable, including the ones taken for their own recovery obligations. The
error message says so, because `KeyRevoked` is usually not a fault and an
operator who reads "decryption failed" opens a ticket about a bug that does not
exist.

Three things that are silent when wrong, each with a test:

- **The nonce is fresh per encryption and never supplied.** Reusing one under a
  single key in GCM does not merely weaken it: it leaks the XOR of the
  plaintexts and permits forgery.
- **The context is authenticated, not merely stored.** Tenant and purpose go
  into the AAD, so an envelope moved between tenants *fails* to decrypt.
  Recording the tenant alongside would let it decrypt cleanly into the wrong
  one — the failure that looks like nothing at all.
- **The provider cannot generate the customer key.** A provider that could would
  mean Prama held it at some point, and "we never had it" is the claim the whole
  arrangement exists to make.

The reference provider is called `LocalTestKeyProvider` and its docstring says
*never for production*: a class named `LocalKeyProvider` ends up in somebody's
deployment, and a customer-managed key held by Prama is not one.

**No cloud KMS has been exercised.** `KeyProvider` is an ABC and no AWS, Azure
or GCP client is imported; a test asserts that. Those clients belong to the
deployment, and keeping them out is what lets the envelope logic be tested.

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

### 3.0 Secrets

References are stored, values are resolved at the point of use. Three providers
ship: `env://`, `file://` and `vault://` (HashiCorp KV v2).

Vault is configured by `secrets.vault.*` (`address`, and `token_ref`, a
reference to the token) and is **registered but unconfigured** by default, which
is not the same as absent: a reference then fails with *what to set* rather than with "no provider
for scheme 'vault'", and the second message sends somebody looking for a plugin
that is already installed. A provider supplies its own unavailability remedy —
the resolver knows a provider said no, but only the provider knows which setting
is missing.

Four things about KV v2 that look fine and are not, each with a test:

- **The envelope nests twice.** A read returns `{"data": {"data": …}}`. Reading
  the outer `data` returns the *metadata* — version numbers and timestamps —
  which is not the secret and does not look like an error either.
- **A soft-deleted version is not a value.** Vault returns it with empty data
  and no HTTP error. Handing that back as an empty string reaches the driver as
  an authentication failure and sends somebody to check a password that was
  never read.
- **A secret is a document.** A reference must name its field; guessing which
  one is the credential is how a username gets used as a password. When a field
  is absent the error lists the field *names* that are present — they are not
  values, and they make it fixable in one step.
- **The Vault token is itself a credential**, so it is given as a reference
  (`env://VAULT_TOKEN`) and never as a literal.

The transport is injected, which is what lets the whole of it be tested without
a Vault and lets a deployment substitute its own client with the organisation's
mTLS, proxy and retry policy applied. **It has not been run against a live Vault
server**; the request and response shapes are from the documented API.

---

### 3.1 Residency, and where the question gets asked

`prama.security.residency` decides whether a movement is allowed;
`prama.security.egress` decides **where the question gets asked**, which is the
part that goes wrong. A policy engine nothing calls permits everything, and it
fails silently — the worst way for a control to fail.

Five egress points are registered, each naming what leaves, where the
destination comes from, and where the subject's jurisdiction comes from:

| Point | What leaves |
|---|---|
| `model-inference` | prompts, which carry column names, samples and business language |
| `catalog-write-back` | quality badges: standing, coverage, evidence reference |
| `siem-export` | audit events: who did what to which tenant's estate |
| `evidence-export` | the evidence ledger for a period, including sample digests |
| `alert-delivery` | alert bodies, which quote failing values |

The third column is the one that gets forgotten. An egress that knows its
destination and not its subject's home answers the wrong question confidently,
so `Badge`, `Alert` and the export calls all carry a jurisdiction.

**Two guards, because the registry is only worth having if something checks it
is true.** `tests/architecture/test_egress.py` requires every registered module
to consult residency — a registered point that does not is a build failure, not
a note. And it derives the list of modules that *can* reach the network from
their imports rather than from a list somebody maintains, so a new module that
opens a socket without being registered fails. The list is the thing that rots;
the imports are the thing that is true. There is one accepted exception
(`db/schema/bootstrap.py` imports `socket` for `gethostname`), and a second test
asserts the exception still applies, because a waiver whose reason has expired
is how the next module inherits it.

**The gate raises.** `Gate.require` is the normal way in; `Gate.decide` returns
a decision and is for reporting. A returned decision can be ignored, and the one
call site where somebody forgets is the one that matters. `ResidencyRefused` is
its own error type so an operator triaging a failed export can tell "the data
may not go there" from "the request was malformed".

**Refusal granularity is decided per point, not uniformly.** Catalogue
write-back refuses *per badge* and lets the rest land — a residency breach is
not a reason to leave forty tables stale. SIEM and evidence export refuse
*wholesale* — an audit export missing the records that could not cross is an
export with a hole in it and nothing in the file says so. Alert delivery is
withheld from **everybody or nobody**: an alert some recipients received and
others silently did not is worse than either, because the ones who got it assume
everyone did.

**The gate is optional at every call site.** Most deployments are in one region
with no residency obligation at all, and a required argument is one that every
caller passes `None` to — which is a control in name only.

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

### 6.2a Verifying without us — `scripts/verify_evidence.py`

An audit trail that can only be checked by the tool that produced it is that
tool's own account of itself, which is the one thing an auditor is there not to
accept. So the chain algorithm is written out in prose in every bundle's
`manifest.json`, and `scripts/verify_evidence.py` is an implementation of that
prose which **imports nothing from Prama and nothing outside the Python standard
library**. A test asserts both facts by parsing the script's imports, and runs
it as a subprocess with `PYTHONPATH` emptied — an auditor's actual situation.

```
python3 verify_evidence.py <bundle-directory>

exit 0   every check passed
exit 1   at least one check failed
exit 2   the bundle could not be read at all
```

The third code exists because "I could not read it" and "it is wrong" are
different findings: the first is a broken transfer, the second a broken claim.

Seven checks: content hashes, chain links, contiguous sequence numbers, the
manifest's record count against the file, the payload digest, the Merkle root,
and the chain head. The count is the one that catches what archives actually
suffer — a **truncated file**, whose remaining chain is perfectly valid.

**What a green result does not mean.** The script prints this on success, where
the overstatement happens; nobody misreads a failure:

> This says the records have not been altered since they were written, and that
> this file is the one the manifest describes. It does not say the records are
> true: a false record, honestly written and correctly chained, produces a
> bundle that verifies exactly like this one.

Chain integrity answers *has this been altered since it was written*, not *was
it right when it was written*. The second question is what controls, replay and
the two-stage engine are for.

The verifier's counterfactual is tested five ways — an altered field, a
truncated file, a removed middle record, a reordered pair, and a manifest
doctored to match a doctored payload — plus a sixth asserting the untouched
bundle still passes, so the five failures are not vacuous.

---

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
artefact carries the [attestation seal](../reference/brand.md#3-the-mark--the-pramāṇa-prism), is immutably
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
<img src="../assets/prama-mark.svg" width="30" alt=""/><br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.<br/>
See <a href="../../LICENSE">LICENSE</a> and <a href="../../NOTICE">NOTICE</a>. Third-party names and marks are the property of their respective owners.</sub>
</div>
