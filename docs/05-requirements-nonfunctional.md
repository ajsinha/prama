<img src="assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

> ***pramā*** (Sanskrit **प्रमा**) — *valid knowledge: a cognition that is both true and arrived at
> by a reliable means*. Its companion ***pramāṇa*** (प्रमाण) is *the instrument by which valid
> knowledge is obtained*. Prama is that instrument for an organisation's data — it does not decide
> what is true, it is how a belief about data becomes **justified**.
>
> **Declare it. Prove it. Trust it.**


---
# 05 — Non-Functional Requirements

**Identifier scheme:** `NFR-<AREA>-<nnn>`. Every NFR states a *measurable* target and the method by
which it is verified. Targets marked **(GA)** are release-blocking.

Areas: SCA scale · PRF performance · AVL availability & resilience · SEC security ·
PRV privacy · CMP compliance · OPS operability · COS cost · POR portability · USA usability ·
MNT maintainability · TST testability · DAT data management · AI AI/ML governance

---

## As built

The structural NFRs are implemented and enforced by tests rather than by
convention: `NFR-SEC` (no secrets in tracked configuration, refused by the
pre-commit hook), `NFR-AI-002` (no model output determines a verdict, enforced
by import scanning), `NFR-PRV-005` (erasure by tombstone with hash integrity
preserved), `NFR-TST-001` (advertised numbers derived from a green run, by
`scripts/sync_test_counts.py`).

**The performance NFRs are the ones to read carefully.** A number here is a
target unless this section says it was measured.

Measured: in-flight assertion cost at 4.82 µs/message and 208,000 msg/s per core
on a five-control mix, which is three orders of magnitude inside the latency
budget. The file-length ceiling (1500 code lines) is enforced in the hook and
the gate.

**Not measured:** reconciliation at 10⁸ records per side — measured at 100,000;
streaming p95 detection and added p99 at target throughput; the estate map at
50,000 nodes; and the API at the rates §4 states. None of these has a harness on
a machine large enough to answer it, and `docs/19` records each as outstanding
rather than assumed.

---

## A. Scale (`NFR-SCA`)

| ID | Requirement | Target | Verify |
|---|---|---|---|
| NFR-SCA-001 | Managed assets per tenant | 1,000,000 datasets; 50,000,000 attributes **(GA: 100,000 / 5,000,000)** | Load test |
| NFR-SCA-002 | Active controls per tenant | 5,000,000 assertion instances **(GA: 500,000)** | Load test |
| NFR-SCA-003 | Assertion executions per day | 100,000,000 **(GA: 10,000,000)** | Load test |
| NFR-SCA-004 | Largest single dataset validated | 100 TB / 10^12 rows, via pushdown and partition-parallel execution | Benchmark |
| NFR-SCA-005 | Streaming throughput per validation node | 250,000 msg/s at ≤ 5 ms added p99 latency for schema+format+range checks | Benchmark |
| NFR-SCA-006 | Reconciliation scale | 500,000,000 records per side; 10^9 candidate pairs after blocking | Benchmark |
| NFR-SCA-007 | Lineage graph | 10,000,000 nodes / 50,000,000 edges with interactive traversal | Benchmark |
| NFR-SCA-008 | Evidence store | 10 years retention, 10^11 evidence records, queryable | Load test |
| NFR-SCA-009 | Concurrent console users per tenant | 5,000 **(GA: 500)** | Load test |
| NFR-SCA-010 | Connected sources per tenant | 10,000 connections across ≥ 50 source types | Load test |
| NFR-SCA-011 | Estate map rendering | 50,000 visible nodes with progressive/level-of-detail rendering at 60 fps pan/zoom | Benchmark |
| NFR-SCA-012 | Horizontal scalability | Linear (≥ 0.85 efficiency) throughput scaling to 200 execution workers | Benchmark |

## B. Performance & Latency (`NFR-PRF`)

| ID | Requirement | Target | Verify |
|---|---|---|---|
| NFR-PRF-001 | Console navigation | p95 ≤ 300 ms, p99 ≤ 800 ms **(GA)** | RUM + synthetic |
| NFR-PRF-002 | Data-backed panels (scorecards, profiles) | p95 ≤ 2 s **(GA)** | Synthetic |
| NFR-PRF-003 | Rule live-preview on a sampled scope | p95 ≤ 5 s for ≤ 10^7 rows | Benchmark |
| NFR-PRF-004 | Rule compile (PQL → IR → SQL) | p99 ≤ 100 ms per assertion | Unit benchmark |
| NFR-PRF-005 | Batch assertion suite over a 1 TB table (fused, pushdown) | ≤ 1 source-engine scan; ≤ 10% overhead vs. a hand-written equivalent query | Benchmark |
| NFR-PRF-006 | Streaming detection latency (defect introduced → alert emitted) | p95 ≤ 60 s **(GA)** | Chaos test |
| NFR-PRF-007 | Batch detection latency | ≤ 1 scheduling interval + 5 min | Chaos test |
| NFR-PRF-008 | Incident correlation & RCA hypothesis generation | ≤ 30 s after triggering failure | Benchmark |
| NFR-PRF-009 | Chat assistant first token | p95 ≤ 1.5 s; full grounded answer p95 ≤ 8 s | Benchmark |
| NFR-PRF-010 | Lineage ancestry query (depth ≤ 10) | p95 ≤ 500 ms | Benchmark |
| NFR-PRF-011 | Evidence replay of a historical run | ≤ 2× original execution time | Benchmark |
| NFR-PRF-012 | Profiling a 10^9-row table at 1% stratified sample | ≤ 5 min wall clock on customer-provisioned compute | Benchmark |
| NFR-PRF-013 | Source-system load ceiling | Prama-attributable load ≤ a configured % of source capacity (default 5%), enforced, measured, reported | Instrumentation |

## C. Availability & Resilience (`NFR-AVL`)

| ID | Requirement | Target | Verify |
|---|---|---|---|
| NFR-AVL-001 | Control-plane availability (SaaS) | 99.9% monthly **(GA)**; 99.95% by GA+12mo | SLO monitoring |
| NFR-AVL-002 | Evidence-write durability | 99.999999999% (11 nines) via replicated, versioned, WORM-capable storage | Design review |
| NFR-AVL-003 | Execution continues during control-plane outage | Agents continue scheduled runs and buffer evidence for ≥ 24 h, replaying on recovery | Chaos test |
| NFR-AVL-004 | RPO / RTO | RPO ≤ 5 min; RTO ≤ 1 h **(GA: RPO 15 min / RTO 4 h)** | DR drill (quarterly) |
| NFR-AVL-005 | Graceful degradation | Loss of the ML subsystem must not stop declarative controls; loss of the LLM must not stop the console | Chaos test |
| NFR-AVL-006 | Source failure isolation | One unreachable/slow source must not delay execution for any other source | Chaos test |
| NFR-AVL-007 | Poison-input resistance | Malformed, adversarial, or pathologically large records must not crash a worker; they are quarantined with evidence | Fuzz test |
| NFR-AVL-008 | Back-pressure | Under overload the system sheds low-priority work first (advisory monitors before Tier-1 controls) and reports what was shed | Load test |
| NFR-AVL-009 | Zero-downtime upgrades | Rolling upgrade of control plane and workers with no dropped executions | Deployment test |
| NFR-AVL-010 | Data-loss-free at-least-once evidence delivery | No evidence record lost under any single-node failure; duplicates detectable and idempotent | Chaos test |

## D. Security (`NFR-SEC`)

Detail: [13 — Security, Governance & Compliance](13-security-governance-compliance.md).

| ID | Requirement | Target | Verify |
|---|---|---|---|
| NFR-SEC-001 | Encryption | TLS 1.3 in transit; AES-256 at rest; customer-managed keys (CMK/BYOK/HYOK) supported | Audit |
| NFR-SEC-002 | Authentication | OIDC/SAML SSO, SCIM, MFA enforcement, service accounts with short-lived tokens | Audit |
| NFR-SEC-003 | Authorisation | RBAC + ABAC to asset/domain/rule/evidence granularity; deny-by-default; SoD enforced (author ≠ approver) | Test |
| NFR-SEC-004 | Secrets | No source credentials stored in Prama in default posture; vault-backed references only | Audit |
| NFR-SEC-005 | Least-privilege source access | Read-only by default; write requires a separate, explicit, per-scope grant and an approved change record | Audit |
| NFR-SEC-006 | Tenant isolation | No cross-tenant data, metadata, model, or embedding leakage; verified by automated isolation tests each release | Test |
| NFR-SEC-007 | Supply chain | SBOM per release, signed artefacts, provenance attestation (SLSA L3 target), dependency and container scanning gates | CI gate |
| NFR-SEC-008 | Vulnerability response | Critical ≤ 7 days, High ≤ 30 days from disclosure to patched release | Process metric |
| NFR-SEC-009 | Penetration testing | Independent annual test + per-major-release automated DAST/SAST | Report |
| NFR-SEC-010 | Prompt-injection resistance | Data content and retrieved documents can never trigger tool calls; verified by an adversarial test corpus each release | Red-team suite |
| NFR-SEC-011 | Audit logging | Every read and write of data, metadata, evidence, and configuration logged immutably and exported to SIEM ≤ 5 min | Audit |
| NFR-SEC-012 | Certifications | SOC 2 Type II and ISO 27001 within 12 months of GA; ISO 27701 and PCI-DSS scope where applicable | Certification |

## E. Privacy & Data Handling (`NFR-PRV`)

| ID | Requirement | Target | Verify |
|---|---|---|---|
| NFR-PRV-001 | Data minimisation | Only metrics, verdicts, and policy-permitted samples leave the source; raw data is never bulk-copied into Prama | Design review + audit |
| NFR-PRV-002 | Sample governance | Failing-row retention is opt-in per dataset, masked per classification, retention-capped, and access-logged | Test |
| NFR-PRV-003 | Masking | Deterministic, format-preserving masking available for samples, alerts, chat, and exports | Test |
| NFR-PRV-004 | Residency | Execution and storage locality enforced per declared jurisdiction; cross-border movement blocked, not merely warned | Test |
| NFR-PRV-005 | Right to erasure | Ability to purge identified subject data from samples/evidence with a tamper-evident tombstone preserving audit integrity | Test |
| NFR-PRV-006 | LLM data handling | No masked-class data in any prompt; no customer data used to train any shared model; per-tenant model isolation | Audit |
| NFR-PRV-007 | Air-gap | Full functionality (excluding external reference data and hosted LLMs) with no egress whatsoever | Deployment test |

## F. Compliance & Auditability (`NFR-CMP`)

| ID | Requirement | Target | Verify |
|---|---|---|---|
| NFR-CMP-001 | Evidence immutability | Append-only, hash-linked, optionally externally anchored; any tampering detectable | Audit |
| NFR-CMP-002 | Deterministic replay | 100% of controls replayable to an identical verdict against the same snapshot + rule version **(GA)** | Test |
| NFR-CMP-003 | Retention | Configurable 1–25 years per criticality tier, with legal hold | Test |
| NFR-CMP-004 | Regulatory mapping | Every control traceable to its regulatory citation; coverage reportable per obligation | Test |
| NFR-CMP-005 | Model risk (SR 11-7 / EU AI Act Art. 10) | Model cards, data provenance, validation records, versioning, and human-oversight records for every learned component | Audit |
| NFR-CMP-006 | Change control | All rule and metadata changes versioned, approved, effective-dated, and attributable | Audit |
| NFR-CMP-007 | Auditor access | A read-only auditor role able to browse and export evidence without any source-system access | Test |
| NFR-CMP-008 | Attestation | Electronic sign-off with non-repudiation on periodic control attestations | Test |

## G. Operability (`NFR-OPS`)

| ID | Requirement | Target | Verify |
|---|---|---|---|
| NFR-OPS-001 | Observability of Prama itself | OpenTelemetry traces/metrics/logs; golden signals per service; per-tenant SLO dashboards | Inspection |
| NFR-OPS-002 | Time to first value | Connect a source → first profile + first proposed controls in ≤ 30 min unattended **(GA)** | Timed acceptance |
| NFR-OPS-003 | Time to first business declaration | Declare a dataset with owner, grain, and rhythm in ≤ 5 min by an untrained business user | Usability test |
| NFR-OPS-004 | Installation (self-hosted) | Helm/Operator install on a conformant Kubernetes cluster in ≤ 2 h | Timed acceptance |
| NFR-OPS-005 | Upgrade | Backward-compatible schema migrations; N-2 version compatibility for agents | Test |
| NFR-OPS-006 | Diagnostics | One-command support bundle with redaction; every failure surfaces an actionable message and a stable error code | Inspection |
| NFR-OPS-007 | Capacity guidance | Documented sizing model with measured coefficients per workload class | Documentation |
| NFR-OPS-008 | Runbooks | A runbook for every alert the platform can raise about itself | Inspection |

## H. Cost & Efficiency (`NFR-COS`)

| ID | Requirement | Target | Verify |
|---|---|---|---|
| NFR-COS-001 | Source compute efficiency | ≤ 50% of the compute of a naive per-rule full-scan implementation, via fusion, incremental execution, and sampling **(GA)** | Benchmark |
| NFR-COS-002 | Cost transparency | Per-run, per-rule, per-dataset, per-domain cost attribution, visible before and after execution | Test |
| NFR-COS-003 | Budget enforcement | Hard budgets per connection/domain/tenant with prioritised degradation, never silent overrun | Test |
| NFR-COS-004 | LLM cost | Per-tenant token budgets; caching of induction/summary results; ≤ $0.02 median per rule-induction proposal | Instrumentation |
| NFR-COS-005 | Control-plane footprint | ≤ 16 vCPU / 64 GB for a 100,000-asset tenant at steady state | Benchmark |
| NFR-COS-006 | Storage efficiency | Evidence ≤ 2 KB median per assertion execution (compressed, columnar) | Benchmark |

## I. Portability & Openness (`NFR-POR`)

| ID | Requirement | Target | Verify |
|---|---|---|---|
| NFR-POR-001 | Deployment targets | SaaS (multi-tenant), single-tenant cloud, customer VPC, on-premises, and fully air-gapped — from one codebase | Deployment test |
| NFR-POR-002 | Cloud neutrality | AWS, Azure, GCP, and on-prem Kubernetes; no unavoidable dependency on a single cloud's proprietary service | Design review |
| NFR-POR-003 | Backend neutrality | The PQL IR executes semantically identically on every supported engine, certified by a conformance suite **(GA)** | Conformance suite |
| NFR-POR-004 | Data export | Complete export of semantic layer, rules, evidence, and history in documented open formats; no lock-in | Test |
| NFR-POR-005 | Standards | ODCS v3 in/out, OpenLineage out, OpenTelemetry out, OpenAPI 3.1, SHACL/RDF export, MCP server | Test |
| NFR-POR-006 | BYO-LLM | Anthropic, Azure OpenAI, Bedrock, Vertex, and self-hosted open-weight models, switchable per tenant without feature loss beyond documented quality deltas | Test |

## J. Usability & Accessibility (`NFR-USA`)

| ID | Requirement | Target | Verify |
|---|---|---|---|
| NFR-USA-001 | Business-user task success | ≥ 90% unaided completion for the eight core business tasks (declare dataset, declare relationship, approve control, triage incident, read scorecard, request access, ask a question, attest) | Usability study, n ≥ 12 per persona |
| NFR-USA-002 | Median time to author a reviewed control | ≤ 3 min via chat/induction; ≤ 10 min via the no-code builder **(GA)** | Timed study |
| NFR-USA-003 | Accessibility | WCAG 2.2 AA, full keyboard operability, screen-reader tested (NVDA/JAWS/VoiceOver) **(GA)** | Audit |
| NFR-USA-004 | Error messages | Every error states what happened, why, and the next action; no stack traces or internal identifiers in the UI | Inspection |
| NFR-USA-005 | Progressive disclosure | No physical/technical detail on any default business surface; always reachable in ≤ 2 clicks | Design review |
| NFR-USA-006 | Learnability | A business owner completes onboarding to first declared dataset with no training material other than in-product guidance | Usability study |
| NFR-USA-007 | Internationalisation | Full i18n framework, locale-aware formats, RTL-capable layout | Test |
| NFR-USA-008 | Consistency | One design system; identical semantics for colour, severity, and staleness across every surface including generated reports | Design review |

## K. Maintainability & Testability (`NFR-MNT`, `NFR-TST`)

| ID | Requirement | Target | Verify |
|---|---|---|---|
| NFR-MNT-001 | API stability | Semver; no breaking change without a 12-month deprecation window | Policy audit |
| NFR-MNT-002 | Modularity | Connectors, assertion types, monitors, notifiers, and packs are plugins with stable SPIs; adding a connector requires no core change | Design review |
| NFR-MNT-003 | Documentation | Every public API, PQL construct, assertion type, and configuration option documented with examples; docs built and tested in CI | CI gate |
| NFR-TST-001 | Automated coverage | ≥ 85% line / ≥ 75% branch on core engine; 100% of PQL constructs covered by conformance tests | CI gate |
| NFR-TST-002 | Backend conformance | Every supported engine passes the full IR conformance suite each release; failures block the release **(GA)** | CI gate |
| NFR-TST-003 | Property-based testing | Semantic equivalence of IR compilation verified by generative/property tests against a reference interpreter | CI gate |
| NFR-TST-004 | Performance regression | Benchmark suite in CI; > 10% regression on any headline benchmark blocks the release | CI gate |
| NFR-TST-005 | Reproducibility | Fixed-seed determinism for all sampling and all learned components' inference paths | Test |

## L. Data Management (`NFR-DAT`)

| ID | Requirement | Target | Verify |
|---|---|---|---|
| NFR-DAT-001 | Metric history retention | ≥ 3 years at full granularity, ≥ 10 years downsampled | Test |
| NFR-DAT-002 | Metadata history | Unlimited version history for semantic-layer objects with efficient diff | Test |
| NFR-DAT-003 | Time-travel correctness | Evidence references an immutable snapshot identifier wherever the source supports one; where it does not, the limitation is recorded on the evidence | Design review |
| NFR-DAT-004 | Idempotency | Re-execution of any run is idempotent with respect to evidence and incidents | Test |
| NFR-DAT-005 | Clock discipline | All timestamps UTC with recorded source-clock offset; business dates carry an explicit calendar reference | Test |

## M. AI/ML Governance (`NFR-AI`)

Detail: [08 — AI/ML Capabilities](08-ai-ml-capabilities.md) §8.

| ID | Requirement | Target | Verify |
|---|---|---|---|
| NFR-AI-001 | Calibration | Empirical false-alarm rate within ±0.02 of nominal across all tested drift regimes **(GA)** | Benchmark |
| NFR-AI-002 | No autonomous verdicts | Zero code paths in which an LLM output determines a pass/fail verdict; enforced by architecture test | Architecture test |
| NFR-AI-003 | Explainability | Every ML-derived alert states its contributing features/segments and its baseline; every LLM-authored rule shows its rationale and evidence | Inspection |
| NFR-AI-004 | Reproducibility | Model version, training window, hyperparameters, and calibration set recorded per inference and replayable | Test |
| NFR-AI-005 | Degradation detection | Automatic detection of monitor precision decay with rollback to last known-good | Test |
| NFR-AI-006 | Human oversight | Every AI proposal requires human approval in regulated scopes; overrides always available and always recorded | Audit |
| NFR-AI-007 | Bias & fairness | Where controls affect populations (e.g. suppression of alerts by segment), monitor for systematic under-coverage of segments | Analysis |
| NFR-AI-008 | LLM output validation | 100% of LLM-generated PQL parsed, type-checked, and sandbox-executed before it is shown to a user | Test |

---

<div align="center">
<img src="assets/prama-mark.svg" width="30" alt=""/><br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.<br/>
See <a href="../LICENSE">LICENSE</a> and <a href="../NOTICE">NOTICE</a>. Third-party names and marks are the property of their respective owners.</sub>
</div>
