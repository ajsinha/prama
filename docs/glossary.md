<img src="assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

> ***pramā*** (Sanskrit **प्रमा**) — *valid knowledge: a cognition that is both true and arrived at
> by a reliable means*. Its companion ***pramāṇa*** (प्रमाण) is *the instrument by which valid
> knowledge is obtained*. Prama is that instrument for an organisation's data — it does not decide
> what is true, it is how a belief about data becomes **justified**.
>
> **Declare it. Prove it. Trust it.**


---
# Glossary

**Ablation** — a version of Prama with one claim removed (schema-only,
patterns-only, statistics-only), scored against the same corpus. `docs/15` calls
this the most important comparison, because it answers *which of our claims is
doing the work?* — the question a reviewer and a serious buyer both ask.

**Assertion** — the atomic unit of quality checking in Prama: a predicate over a *scope* that
produces a *verdict*, *metrics*, and an *EvidenceRecord*. Rules, monitors, reconciliations, and
contract clauses are all assertions.

**Attestation** — a signed, immutable artefact in which a control owner affirms, for a period, the
control set in force, its outcomes, and its exceptions.

**Attribute** — a business-meaningful field of a Dataset, with a definition and interpretation,
bound to one or more physical columns/fields. Distinct from a *column*.

**BCBS 239 / RDARR** — Basel Committee principles for effective risk data aggregation and risk
reporting; 14 principles, of which 3–6 are directly data quality requirements.

**Binding** — the link between a business Attribute or Dataset and its physical realisation
(table.column, file field, JSON path, message tag), optionally through a transformation.

**Bound (benchmark)** — a detector that is an axis rather than a contender:
`detect-nothing` and `alert-on-everything`. A recall figure cannot be read until
you know that alerting on every column scores 1.0.

**Break** — a row that failed to match in a reconciliation. Breaks are tracked
over time: *new*, *again* (still unmatched from a previous run), and *cleared*.
A break's `first_seen` never moves, which is what makes ageing mean something.

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

**Dead letter** — where a message rejected by in-flight enforcement goes
*before* it is removed from the stream. Nothing is dropped without being kept. A
full dead letter stops the pipeline rather than falling back to discarding,
because a storage problem is fixable and permanent loss is not.

**Defect family** — one of six classes of planted defect in the benchmark corpus
(structural, content, statistical, relational, temporal, semantic). The

**Denial constraint (DC)** — an integrity constraint forbidding a combination of predicates across
tuples; strictly more expressive than a functional dependency.

**Dimension** — a named facet of quality: accuracy, completeness, consistency, timeliness,
uniqueness, validity (DAMA-6), extensible per tenant.

**Egress point** — a registered place where data leaves Prama: model inference,
catalogue write-back, SIEM export, evidence export, alert delivery, secret fetch,
source read. Each is residency-checked. A module that reaches the network without
being registered fails the build.

**Envelope encryption** — a fresh data key encrypts the payload; the customer's
key wraps the data key; Prama stores the wrapped key and never holds the
customer's. Revoking it makes every envelope unreadable, permanently, with
nothing Prama can do about it — which is the point, and is neither reversible
nor selective.

**EvidenceRecord** — the immutable, hash-linked, signed record appended by every assertion
execution; the system of record for audit and the substrate for every score.

**FDR (False Discovery Rate)** — the expected proportion of false positives among raised alerts.
Prama controls it hierarchically across the domain → dataset → attribute → check lattice.

**Fellegi–Sunter** — the classical probabilistic record-linkage model, with EM-estimated match/
non-match probabilities and auditable match weights.

**Functional dependency (FD)** — a constraint stating that one set of attributes determines another.
*Approximate* FDs (which hold with a violation budget) are the practically useful variant.

**Fusion** — grouping controls that can share one scan of a source, so forty
controls over one table are not forty table scans. `prama control compile --fuse`
shows the grouping.

**Γ generator (gamma)** — the derivation of controls from declarations.
Declaring that an attribute is critical, not-null and drawn from a code list
produces the controls; nobody writes them.

**IR (Intermediate Representation)** — Prama's typed, engine-neutral logical plan. The portability
contract: one semantics, many backends.

**Journey** — see *Data Journey*.

**Kleene logic** — three-valued logic (true, false, unknown) used throughout
evaluation. Prama's default is that **unknown counts as a violation**: a
comparison against a null is not a pass. `TREAT UNKNOWN AS PASS` overrides it,
and the phrase is in the control's text precisely so that choice is visible.

**not_established** — a verdict distinct from both *pass* and *fail*: the control
ran and could not reach a conclusion. A screen that could not execute, a period
with no rows, a lower bound of zero that was never confirmed. **It is not a
pass**, and treating it as one is the single most common misreading of a Prama
report.

**ODCS (Open Data Contract Standard)** — the Linux Foundation (Bitol) machine-readable data-contract
standard, v3.1.0. Prama is an ODCS-native runtime.

**Plan id** — the content-addressed hash of a control's compiled IR. Two controls
with the same plan id mean the same thing; a control whose plan id changed means
something different, and past evidence is evidence about the old one. A validator
plugin's implementation hash is folded in, so editing that code changes the
control's identity rather than silently changing what past evidence meant.

**PQL (Prama Quality Language)** — the declarative language in which all assertions are expressed,
with a YAML surface and an expression surface parsing to one AST.

**Progressive formalisation** — the adoption contract: every declaration pays for itself
immediately and nothing is mandatory; the system proposes, the human confirms.

**Proposal** — anything AI-authored. Proposals land on a queue for a human to
approve; they never become active controls on their own (`CON-007`).

**Purity (plugin)** — a validator plugin may not import a clock, a socket or a
model client. Enforced by scanning its source at registration, not by asking.

**Pushdown** — executing a compiled plan inside the source system so that only metrics, verdicts,
and permitted samples return. Prama's default posture.

**Recognition standing** — the three-state result of matching columns to a
business concept: *recognised*, *possible*, *not recognised*. The third is a
refusal, not a low score — Position, Balance and Exposure share a shape, and a
matcher that counted overlapping properties would call one table all three.

**Residency** — where a tenant's data may be. Refusal is the default and the
reason is always stated. **Undeclared is not unrestricted**: a dataset with no
declared jurisdiction is blocked, which is a deliberate cost and the only safe
direction.

**Screen and residual** — the two stages of validation. The *screen* is a cheap
predicate the engine can push down; the *residual* is the arithmetic it cannot
do faithfully, run over the rows that survived. A screen alone establishes a
lower bound, and **a lower bound of zero is not a pass**.

**semantic family** is the discriminator: those defects pass every format and
range check, and every deterministic ablation is blind to them.

**Semiring (trust)** — the algebraic structure ⟨⊕, ⊗⟩ over which trust is propagated along the
lineage DAG.

**Snapshot** — an immutable identifier of data state (Iceberg/Delta version, SCN/LSN, file digest,
offset range) recorded on evidence to make replay possible.

**Staleness state** — fresh / ageing / stale / suspended: rendered on every finding so no stale
conclusion is presented as current.

**Tombstone** — how a record is erased without breaking the chain. Its content
is gone and its stored `content_hash` is the hash the content had, so its place
in the chain is still verifiable. This is what makes a right-to-erasure request
compatible with an intact audit trail.

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
