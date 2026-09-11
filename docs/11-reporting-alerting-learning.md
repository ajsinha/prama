<img src="assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

> ***pramā*** (Sanskrit **प्रमा**) — *valid knowledge: a cognition that is both true and arrived at
> by a reliable means*. Its companion ***pramāṇa*** (प्रमाण) is *the instrument by which valid
> knowledge is obtained*. Prama is that instrument for an organisation's data — it does not decide
> what is true, it is how a belief about data becomes **justified**.
>
> **Declare it. Prove it. Trust it.**


---
# 11 — Reporting, Scoring, Alerting & the Learning Loop

Requirements: [`FR-SCR`](04-requirements-functional.md#k-scoring-reporting--analytics-fr-scr),
[`FR-ALR`](04-requirements-functional.md#l-alerting--notification-fr-alr),
[`FR-LRN`](04-requirements-functional.md#m-learning-loop-fr-lrn),
[`FR-INC`](04-requirements-functional.md#j-incident-management--workflow-fr-inc),
[`FR-REF`](04-requirements-functional.md#v-continuous-re-examination--refresh-fr-ref).

---

## As built

`prama.score` — composite scoring and trust propagation along lineage, derived
from evidence rather than assigned. `prama.report` — scorecards, charts, the
RDARR attestation pack, the SOC 2 readiness matrix, and the theme machinery.
`prama.alert` — routing, deduplication, severity, digests, and the quiet period.
`prama.incident` — correlation and root-cause analysis. `prama.learn` — the
feedback loop. `prama.integrate.catalog` — quality badges written back to
Collibra, Alation and DataHub.

Two behaviours worth naming because they are the opposite of the obvious
implementation. An alert with no recipient is **reported, not dropped** — an
alert nobody receives is a finding nobody sees. And an alert that fails
residency is withheld from **everybody or nobody**: delivered to some recipients
and silently withheld from others is worse than either, because the ones who got
it assume everyone did.

A badge cannot be constructed without a date. "Trusted" on a table nobody has
checked since March reads as current, and a reader has no way to tell.

**Not built:** the longitudinal measurements in §6 — alert precision, proposal
acceptance and break-classification accuracy over twelve months — which need
design partners. The vendor adapters are written and **none has been run against
a live server**.

---

## 1. The measurement model

Everything reported derives from four layers, each fully traceable to the one below:

```
      Enterprise / Domain / Journey score
                    ▲  weighted by materiality, propagated along lineage
      Dataset score │
                    ▲  weighted by criticality and consumer importance
      Dimension score (accuracy, completeness, consistency,
                       timeliness, uniqueness, validity, …)
                    ▲  aggregated over the controls tagged to that dimension
      Control outcome (verdict + metrics)
                    ▲
      EvidenceRecord (immutable, replayable, signed)
```

**No score exists without evidence beneath it.** Clicking any number descends this ladder to the
signed records that produced it (`U3`).

### 1.1 Dimension scores

For a dimension *d* over a dataset *D* in period *t*:

```
score_d(D,t) = 1 −  Σ_{c ∈ C_d(D)}  w_c · impact_c(t)
                    ─────────────────────────────────
                          Σ_{c ∈ C_d(D)} w_c
```

where `impact_c` is the control's normalised failure magnitude (violation rate, or monetary value
at risk / total value, or SLA miss fraction), and `w_c` combines the control's severity, the
criticality of the attributes it covers, and the materiality of the records in scope. Both the
formula and every input are visible in the UI — an unexplainable score is worse than no score.

### 1.2 Composite scores — three sanctioned methods

Single-number scores are politically irresistible and statistically treacherous. Prama supports
three, requires the tenant to choose deliberately, and always shows the components:

| Method | Behaviour | Use when |
|---|---|---|
| **Weighted mean** | Smooth, forgiving; a single catastrophic failure is diluted | Broad management reporting |
| **Weakest link** (min, or worst-*k* mean) | Dominated by the worst dimension | Regulatory/critical contexts where one failure invalidates the whole |
| **Standardised composite (PCA)** | Standardises the metric matrix, then extracts the dominant component; avoids arbitrary hand-set weights | Cross-domain comparison where weights would be contested |

The default for a Tier-1 regulatory dataset is **weakest link** — because for a regulatory return,
"98% correct" is not 98% of a pass.

### 1.3 Materiality weighting

Records are not equal. Weighting supports record count, **monetary value at risk**, CDE criticality,
number and importance of downstream consumers, and regulatory obligation. A 0.01% error rate
concentrated in the largest 50 exposures must outrank a 3% error rate in dormant accounts, and the
scoring model must say so.

---

## 2. Trust propagation along lineage *(novel — `FR-SCR-004`)*

Every product on the market scores each asset in isolation. A gold table built from a bronze table
with a failing control is scored green. This is not merely uninformative; in a regulatory context
it is misleading.

**Model.** Let the column-level lineage DAG be *G*. Each node *v* has an **intrinsic** trust
`τ_int(v)` from its own controls. Its **effective** trust is

```
τ_eff(v) = τ_int(v) ⊗ ⊕_{u ∈ parents(v)} ( α(u→v) · τ_eff(u) )
```

with a configurable semiring ⟨⊕, ⊗⟩ and a transformation-dependent attenuation `α`:

| Transformation on edge u→v | Attenuation behaviour |
|---|---|
| Pass-through / copy / rename | α ≈ 1 — defects propagate fully |
| Filter | α depends on whether the filter removes the affected population (computed, not assumed) |
| Aggregation (SUM/COUNT) | Errors accumulate; α < 1 and depends on the error's concentration |
| Aggregation (AVG/MEDIAN) | Robust statistics attenuate; α > for isolated defects |
| Join | Trust ≤ min of inputs; key-coverage failures propagate as completeness loss |
| Derivation with its own validating control | α is bounded by that control's coverage — a validated derivation *restores* trust |

Choosing ⊕ = min and ⊗ = min gives conservative "weakest ancestor" semantics; probabilistic
semirings give a defect-probability interpretation. The tenant chooses; the derivation is always
shown as a path ("this score is 0.71 because ancestor `murex_trades` has a failing LEI control that
your `DERIVES_FROM` relationship carries forward").

**Consequences.** (a) A consumer sees honest trust. (b) Fixing an upstream defect visibly lifts
every descendant. (c) Investment can be targeted where propagation impact is greatest — a defensible
answer to *"where should we spend the remediation budget?"* that no competitor can produce.

---

## 3. Report catalogue

| Report | Audience | Content | Cadence |
|---|---|---|---|
| **Executive scorecard** | CDO, ExCo, board | Domain scores, trend, top movements with named drivers, open critical issues, coverage, estate maturity | Monthly/quarterly |
| **Domain scorecard** | Domain owner | Dataset scores, dimension breakdown, incidents, SLA attainment, remediation status | Weekly |
| **Dataset health** | Steward, consumer | Controls, outcomes, profile trends, freshness, open issues, trust with ancestry | Continuous |
| **Journey report** | Process owner | End-to-end health, stage latency, SLA, where defects originate | Weekly |
| **Control attestation** | Control owner, audit, regulator | Every control, its executions, outcomes, exceptions with justification, e-signature, seal | Monthly/quarterly |
| **Regulatory control coverage** | Compliance | Obligations → controls → outcomes → gaps, with citations | Per reporting cycle |
| **Issue register** | Steward, GRC | Open defects, ageing, root cause, owner, remediation state, business impact | Continuous |
| **Reconciliation certificate** | Finance/Ops control | Matched/unmatched counts and values, break ageing, sign-off | Per run |
| **"What changed in your estate"** | Owners, architects | New datasets, structural changes, reclassifications, proposed relationships and controls, emerging trends (`FR-REF-012`) | Weekly/monthly |
| **Trend & pattern report** | Architect, CDO | Long-horizon movement, seasonality, gradual degradation, coverage movement (`FR-REF-013`) | Quarterly |
| **Programme effectiveness** | Data office | Coverage, control effectiveness, alert precision, MTTD/MTTR, steward workload, false-positive rate | Monthly |
| **AI-readiness certificate** | AI/ML teams | Completeness, freshness, provenance, permissions, PII posture, traceability | On demand |

Every report is available in the console, as a scheduled distribution (PDF/XLSX/HTML/CSV/JSON) with
per-recipient scoping and redaction, via API, and by asking the assistant. **Narrative summaries are
LLM-drafted but numerically grounded** — every figure in generated prose is a live reference, and
drafts are marked as drafts until a human releases them (`FR-SCR-015`).

### 3.1 The attestation, and the four things it must not do

An attestation is a named person saying **"I have reviewed the controls over this scope for this
period"**. It is not a claim that everything passed, and the design has to keep those two apart,
because a system that quietly conflates them turns a sign-off into a rubber stamp. Four rules
follow, each of them a thing the implementation is forbidden to do.

**It must not let the attester type the figures.** Coverage, exceptions and the evidence root are
derived from the ledger at the moment of signing. An attestation whose numbers were typed is a
statement about what the attester *believed*; one whose numbers were derived is a statement about
what *happened*, and only the second is worth anything to a regulator. The consequence is that an
attester cannot round a number in their own favour without editing the evidence ledger, which is
hash-chained and will say so.

**It must not summarise the exceptions.** Every failing and every unestablished control in the
period appears in the pack by name, with its dataset, its verdict and whatever disposition the
attester recorded. Collapsing them into "3 exceptions" would be asking somebody to sign for things
they were not shown. A disposition left blank is permitted and is itself informative: it marks an
exception nobody explained.

**It must not treat a qualified attestation as a failure.** Most real sign-offs are qualified — there
were exceptions, or coverage was incomplete, and the attester signed anyway with the reasons
recorded. A qualified attestation is a valid attestation. What would be a misrepresentation is
*presenting* one as unqualified, so the pack says which it is in its first paragraph.

**It must not overstate what the seal proves.** The seal is an HMAC over the attestation's content
hash. It establishes that the content was sealed by a holder of this deployment's key and that it
has not changed since — and it says nothing at all to a reader who does not hold that key. An
asymmetric signature would say more; this does not, and the pack prints that sentence rather than
letting a reader infer more from the word "seal" than is there. Verification therefore returns
**two** answers, not one: whether the content still hashes to its stored hash, and whether the seal
holds. "Somebody edited this row" and "this came from another deployment" are different incidents
with different responses, and a single boolean would make them indistinguishable.

A control that produced no verdict in the period is counted separately from one that failed. It is
not an exception — there is no verdict to except from — but it is precisely the number that decides
how much of the scope the attestation actually covers, so it is stated on the face of the pack.
Corrections are made by **superseding**, never by editing: both rows survive, the earlier one is
marked as replaced with the reason, and its own seal still verifies. Being replaced does not make
the earlier statement untrue, and the sequence is usually worth more than the correction alone.

---

## 4. Alerting that people keep switched on

### 4.1 The economics of an alert
An alert costs a steward ~7 minutes of attention. At 200 alerts/day and 40% precision, an
organisation spends ~14 hours/day investigating noise. That is why monitoring gets disabled, and
why precision — not recall — is the metric that determines whether a DQ programme survives.

### 4.2 Controls on volume

1. **Calibrated selection.** Alerts are emitted by an FDR-controlled selection procedure over
   conformal p-values, under a **user-declared false-alarm budget** ([08 §4](08-ai-ml-capabilities.md#4-calibrated-monitoring--the-core-research-contribution)).
   Volume is a dial with a statistical meaning.
2. **Incidents, not events.** Correlated failures collapse into one incident by root cause, asset,
   time window, and lineage proximity (`FR-INC-001`). One upstream defect produces one alert, not
   400.
3. **Routing by ownership and materiality**, with business-calendar awareness and quiet hours.
4. **Digests** for anything not time-critical.
5. **Precision feedback.** Every monitor's measured precision is visible; monitors below a threshold
   are flagged for retuning or retirement (`FR-ALR-009`).

### 4.3 Anatomy of a good alert

> **Positions EOD — counterparty LEI completeness breached (critical)**
> **What:** 4,182 of 1.2M active positions (0.35%) have no counterparty LEI. Threshold 0.05%.
> **Since:** first observed in the 06:12 run, 3 consecutive runs.
> **Scale:** €2.4bn notional affected, concentrated in EMEA / Structured Credit.
> **What changed:** upstream `murex_trades` schema changed at 04:50 — `CPTY_LEI` nullability altered.
> **Likely cause (78%):** upstream schema change. Alternatives: source outage (12%), legitimate new
> product (10%). *[evidence]*
> **Downstream impact:** FRTB return (submission Friday), Counterparty Exposure dashboard, 2 models.
> **Suggested next step:** confirm with the Murex change owner (J. Alvarez); block the FRTB feeder.
> **[Acknowledge] [Assign] [False positive] [Open incident] [Ask the assistant]**

Every element is derived, not templated prose: the magnitude from metrics, the money from
materiality weighting, the cause from RCA ranking, the impact from lineage, the owner from the
semantic layer.

### 4.4 Anticipatory alerting (P2)
Predicted late arrival, predicted SLA breach, and degrading-trend warnings before a threshold is
crossed — with the same calibration discipline applied to the prediction.

---

## 5. Incident lifecycle

```
 detection ─► correlation ─► triage ─► investigation ─► remediation ─► verification ─► closure
     │            │            │            │                │              │            │
  evidence    grouping     ownership     RCA + impact     action +      re-run the     outcome
  record      dedupe       routing       hypotheses       approval      control        recorded
                                              │                                            │
                                              └────────────── learning signal ─────────────┘
```

Structured outcomes (true positive / false positive / duplicate / expected / known issue) are
mandatory at closure — they are the **primary training signal** for the whole system (`FR-INC-007`).
Recurring-issue detection surfaces chronic problems ("7th occurrence in 90 days") that individual
incident closure hides.

---

## 6. The learning loop

```
      ┌──────────────────────────── HUMAN SIGNALS ─────────────────────────────┐
      │ rule accept/reject/edit · incident disposition · threshold override    │
      │ break classification · ER labels · "accept new normal" · suppressions  │
      │ metadata confirmations & corrections · relationship confirmations      │
      └───────────────────────────────┬────────────────────────────────────────┘
                                      ▼
                        Feature & label store (versioned, tenant-isolated)
                                      │
   ┌──────────────┬───────────────────┼────────────────────┬──────────────────┐
   ▼              ▼                   ▼                    ▼                  ▼
 Monitor       Rule-induction     RCA hypothesis      Break/match        Semantic-type
 calibration   ranker             ranker              classifier         classifier
 & thresholds  (per tenant,       (learned priors)    (per recon)        (confirmations)
               per domain)
   │              │                   │                    │                  │
   └──────────────┴─────────┬─────────┴────────────────────┴──────────────────┘
                            ▼
              Shadow evaluation → promotion gate → production
              (challenger must beat champion on precision at equal recall)
                            │
                            ▼
              Degradation monitor → automatic rollback to last known-good
```

**Governing rules.**
- **Human signals are never wasted.** Every triage click is a label. Stewards are not asked to
  annotate; their work *is* the annotation.
- **Tenant isolation by default.** Cross-tenant learning only via opt-in abstractions — rule
  *shapes* and aggregate statistics, never data (`FR-LRN-008`).
- **Nothing is promoted silently.** Challengers must demonstrate a statistically significant
  improvement; promotions are logged with their evidence (`FR-MON-016`).
- **Degradation triggers rollback**, automatically, with an incident raised against the platform
  itself (`FR-LRN-006`).
- **The loop reports on itself.** Precision uplift, acceptance rate, MTTR reduction, and coverage
  growth are published so the value of learning is auditable rather than asserted (`FR-LRN-009`).

**What "learning" concretely improves, quarter over quarter:**

| Component | Month 1 | Month 12 (target) |
|---|---|---|
| Alert precision | 0.55 (cold start, prior-driven) | ≥ 0.85 at FDR ≤ 0.10 (`S2`) |
| Rule-proposal acceptance rate | ~35% | ≥ 70% |
| RCA top-hypothesis accuracy | ~40% | ≥ 75% |
| Break auto-classification accuracy | ~60% | ≥ 90% |
| Semantic-type inference precision | ~85% | ≥ 97% |
| Median time-to-resolution | baseline | −50% |

---

## 7. Continuous re-examination and the honesty of findings

Reporting is only as good as the freshness of what it reports. Prama re-examines datasets on an
adaptive cadence and stamps every finding with `computed_at`, the snapshot examined, the sampling
strategy, and a staleness state ([03 §6](03-business-semantic-layer.md#6-continuous-re-examination--findings-that-never-go-stale)).

Reporting consequences:
- Scorecards render stale components in **Unverified Grey**, and a domain's score explicitly
  discloses what fraction of it rests on stale evidence.
- Trend reports distinguish *"the metric changed"* from *"we last looked three weeks ago."*
- Metadata drift (broken binding, violated grain, degraded relationship, reclassified attribute)
  is an incident routed to the **business owner of the declaration**, and appears on the
  estate-maturity report.
- The periodic **"what changed in your estate"** digest is the single most-read artefact for
  architects, because it is the only place that answers *"is my picture of the estate still true?"*

---

<div align="center">
<img src="assets/prama-mark.svg" width="30" alt=""/><br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.<br/>
See <a href="../LICENSE">LICENSE</a> and <a href="../NOTICE">NOTICE</a>. Third-party names and marks are the property of their respective owners.</sub>
</div>
