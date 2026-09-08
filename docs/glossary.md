<img src="assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

> ***pramā*** (Sanskrit **प्रमा**) — *valid knowledge: a cognition that is both true and arrived at
> by a reliable means*. Its companion ***pramāṇa*** (प्रमाण) is *the instrument by which valid
> knowledge is obtained*. Prama is that instrument for an organisation's data — it does not decide
> what is true, it is how a belief about data becomes **justified**.
>
> **Declare it. Prove it. Trust it.**


---
# Glossary

**Assertion** — the atomic unit of quality checking in Prama: a predicate over a *scope* that
produces a *verdict*, *metrics*, and an *EvidenceRecord*. Rules, monitors, reconciliations, and
contract clauses are all assertions.

**Attribute** — a business-meaningful field of a Dataset, with a definition and interpretation,
bound to one or more physical columns/fields. Distinct from a *column*.

**Attestation** — a signed, immutable artefact in which a control owner affirms, for a period, the
control set in force, its outcomes, and its exceptions.

**BCBS 239 / RDARR** — Basel Committee principles for effective risk data aggregation and risk
reporting; 14 principles, of which 3–6 are directly data quality requirements.

**Binding** — the link between a business Attribute or Dataset and its physical realisation
(table.column, file field, JSON path, message tag), optionally through a transformation.

**Business Concept** — a canonical thing the business talks about (Party, Instrument, Position).
Has Properties, to which Attributes are mapped. A lightweight ontology.

**Business Relationship** — a typed, user-declared, executable statement of how Datasets relate
(`RECONCILES_WITH`, `DERIVES_FROM`, `FEEDS`, `SAME_ENTITY_AS`, …). The mechanism by which a business
declaration becomes a running control.

**CDE (Critical Data Element)** — an attribute whose quality materially affects a regulatory,
financial, or risk outcome. Attracts elevated severity, mandatory attestation, and retention.

**Conformal p-value** — an anomaly score converted, against a calibration set, into a quantity with
a valid false-alarm interpretation. The basis of Prama's calibrated alerting.

**Control** — an approved, versioned, scheduled Assertion with an owner, severity, dimension(s), and
a stated business justification (`BECAUSE`).

**Data Journey** — a named business process expressed as an ordered chain of Datasets and
Relationships (e.g. origination → booking → sub-ledger → GL → FINREP). Provides business lineage
where technical lineage cannot reach.

**Dataset** — Prama's central object: whatever the business calls "a set of data" — a table, a set
of tables, a database, a feed, a set of feeds, a topic, an API, a return, or a query. May be
declared before it is bound.

**Denial constraint (DC)** — an integrity constraint forbidding a combination of predicates across
tuples; strictly more expressive than a functional dependency.

**Dimension** — a named facet of quality: accuracy, completeness, consistency, timeliness,
uniqueness, validity (DAMA-6), extensible per tenant.

**EvidenceRecord** — the immutable, hash-linked, signed record appended by every assertion
execution; the system of record for audit and the substrate for every score.

**FDR (False Discovery Rate)** — the expected proportion of false positives among raised alerts.
Prama controls it hierarchically across the domain → dataset → attribute → check lattice.

**Fellegi–Sunter** — the classical probabilistic record-linkage model, with EM-estimated match/
non-match probabilities and auditable match weights.

**Functional dependency (FD)** — a constraint stating that one set of attributes determines another.
*Approximate* FDs (which hold with a violation budget) are the practically useful variant.

**IR (Intermediate Representation)** — Prama's typed, engine-neutral logical plan. The portability
contract: one semantics, many backends.

**Journey** — see *Data Journey*.

**ODCS (Open Data Contract Standard)** — the Linux Foundation (Bitol) machine-readable data-contract
standard, v3.1.0. Prama is an ODCS-native runtime.

**PQL (Prama Quality Language)** — the declarative language in which all assertions are expressed,
with a YAML surface and an expression surface parsing to one AST.

**Progressive formalisation** — the adoption contract: every declaration pays for itself
immediately and nothing is mandatory; the system proposes, the human confirms.

**Pushdown** — executing a compiled plan inside the source system so that only metrics, verdicts,
and permitted samples return. Prama's default posture.

**Semiring (trust)** — the algebraic structure ⟨⊕, ⊗⟩ over which trust is propagated along the
lineage DAG.

**Snapshot** — an immutable identifier of data state (Iceberg/Delta version, SCN/LSN, file digest,
offset range) recorded on evidence to make replay possible.

**Staleness state** — fresh / ageing / stale / suspended: rendered on every finding so no stale
conclusion is presented as current.

**Trust propagation** — computing a consumer's effective trust from its own controls *and* its
lineage ancestry, with transformation-dependent attenuation.

**UCC (Unique Column Combination)** — a candidate key discovered by profiling.

**Verdict** — pass / fail / error / skipped / **indeterminate**. The last is first-class: an
assertion whose sample was insufficient for the declared confidence is never silently a pass.

---

<div align="center">
<img src="assets/prama-mark.svg" width="30" alt=""/><br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.<br/>
See <a href="../LICENSE">LICENSE</a> and <a href="../NOTICE">NOTICE</a>. Third-party names and marks are the property of their respective owners.</sub>
</div>
