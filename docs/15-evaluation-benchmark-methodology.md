<img src="assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

> ***pramā*** (Sanskrit **प्रमा**) — *valid knowledge: a cognition that is both true and arrived at
> by a reliable means*. Its companion ***pramāṇa*** (प्रमाण) is *the instrument by which valid
> knowledge is obtained*. Prama is that instrument for an organisation's data — it does not decide
> what is true, it is how a belief about data becomes **justified**.
>
> **Declare it. Prove it. Trust it.**


---
# 15 — Evaluation & Benchmark Methodology

> A claim of being "best in the world" that cannot be falsified is marketing. This chapter defines
> how we measure, against whom, on what data, and what result would force us to admit we are not.

Superiority criteria S1–S9 are stated in
[02 §5](02-gap-analysis-and-positioning.md#5-the-best-in-world-claim--how-we-make-it-falsifiable).
This chapter operationalises them and doubles as the experimental protocol for the
[academic paper](paper/).

---

## 1. Why a new benchmark is necessary

There is no accepted benchmark for enterprise data quality management. The nearest neighbours are
inadequate for different reasons:

| Existing resource | What it covers | Why it is insufficient |
|---|---|---|
| Data-cleaning corpora (Hospital, Flights, Beers, Rayyan, Tax) | Cell-level error detection/repair on small tables | Tiny (10³–10⁵ rows), single-table, no cross-system, no temporal dimension, no business semantics |
| UCR Time Series Anomaly Archive | Univariate TS anomaly detection | Not data-quality-shaped; no schema, no rules, no lineage |
| Yahoo / NAB / SMAP / MSL | TS anomaly detection | Documented labelling and difficulty problems; results are protocol artefacts |
| ER benchmarks (Amazon-Google, DBLP-Scholar, WDC) | Entity resolution only | One capability of many |
| TPC-H / TPC-DS | Query performance | No quality semantics |
| Vendor bake-offs | Realistic but bespoke | Not reproducible, not comparable, not public |

The gap is itself a contribution. We propose **DQ-Bench** (general) and **FinDQ-Bench** (banking),
released publicly, with generators, seeds, labels, baselines, and a leaderboard protocol.

---

## 2. The benchmark suite

### 2.1 DQ-Bench — general enterprise data quality

**Construction.** Take real, openly licensed datasets (NYC TLC trips, US Census PUMS, MIMIC-IV
derivatives where licensing permits, OpenStreetMap extracts, GitHub Archive) plus synthetic
generators, and inject **labelled defects** from a documented taxonomy at controlled rates.

**Defect taxonomy (24 classes across 6 families):**

| Family | Classes |
|---|---|
| Structural | column added/removed/renamed/retyped; nullability change; partition missing; grain violation (duplicates) |
| Content | out-of-domain value; format violation; check-digit failure; unit/scale error; sign flip; truncation; encoding corruption |
| Statistical | distribution shift; mean/variance shift; new category; category disappearance; heaping; outlier injection |
| Relational | orphan foreign key; broken functional dependency; aggregate mismatch; duplicate entity |
| Temporal | late arrival; missing period; stale (frozen) values; out-of-order sequence; restatement |
| Semantic | plausible-but-wrong value (passes every format check); mislabelled category; silent business-rule violation |

The **semantic family is the discriminator.** Defects here pass all format and range checks and can
only be caught by declared business relationships or genuine semantic understanding — precisely the
capability we claim.

**Scales:** S (10⁶ rows), M (10⁸), L (10¹⁰), each with 10, 50, and 200 tables and declared
cross-table relationships.

**Difficulty tiers:** *obvious* (detectable by any tool), *ordinary* (needs a rule or a monitor),
*subtle* (needs seasonality, segmentation, or a relationship), *adversarial* (defect co-occurs with
a legitimate change, testing false-positive discipline).

### 2.2 FinDQ-Bench — banking and capital markets

Synthetic but structurally faithful: a generated bank with ~120 datasets across trading, positions,
sub-ledger, GL, payments, client master, and three regulatory returns, connected by ~90 declared
business relationships and 6 data journeys.

Includes: SWIFT MT/MX and FIX message flows with realistic malformation rates; a COBOL/EBCDIC
overnight feed; a T+1 sub-ledger↔GL reconciliation with realistic break populations (timing, FX,
rounding, mapping); month-end and quarter-end volume seasonality on TARGET2/SIFMA calendars; an
MT↔MX translation pair; a corporate-action event that legitimately shifts distributions
(false-positive trap); and defects seeded to mirror published regulatory-reporting failure modes.

Released with a **synthetic-data statement** (no real customer or personal data), generation code,
and a fixed seed.

### 2.3 Live-shadow evaluation

Benchmarks are necessary but insufficient. At three design-partner banks we run Prama in **shadow**
alongside the incumbent tool for 90 days: same sources, same scopes, no production actions. Every
alert from both systems is adjudicated by the customer's stewards **blind to which system raised
it**. This produces the only measurement that matters — precision and recall on real defects, under
real operating conditions, judged by the people who pay for it.

---

## 3. Metrics

### 3.1 Detection quality (S1)
Precision, recall, F1 at the **defect** level (not the alert level), reported per defect family and
difficulty tier. Detection is credited only if the alert identifies the correct dataset **and**
column **and** time window; a generic "something is wrong with this table" scores zero. Report
precision–recall curves, not single operating points, and report per-family breakdowns —
aggregate F1 hides the semantic family, which is where the argument lives.

### 3.2 Alert precision and burden (S2)
Precision@alert over 90 days of live-shadow operation. Also: alerts per steward-week, median
investigation time, and **wasted-hours per week** (false alerts × median investigation time). The
second set is what a buyer actually feels.

### 3.3 Calibration (S3)
For each monitor, the empirical false-alarm rate vs. the nominal declared rate, across drift regimes
(stationary, seasonal, level-shift, regime-switch, bursty). Report the **calibration curve**
(nominal α on x, empirical on y) with a target of |empirical − nominal| ≤ 0.02, plus expected
calibration error and coverage under shift. **No competitor can produce this plot at all**, because
they emit no calibrated quantity — which is itself the finding.

### 3.4 Authoring effort (S4)
Timed, controlled study: 12 participants per persona (business owner, steward, engineer), 10
representative control-authoring tasks, randomised tool order, measuring time-to-*reviewed*-control
(not time-to-typed-rule), plus correctness of the resulting control and self-reported confidence.
Baselines: hand-authored SodaCL, Great Expectations, and the incumbent's UI.

### 3.5 Coverage (S5)
Percentage of columns — and separately of declared CDEs — under at least one *meaningful* control
after 1 day / 1 week / 1 month of effort, holding human effort constant across tools. "Meaningful"
is defined operationally: a control that has a non-degenerate failure mode (it can fail without the
table being catastrophically broken) and is not trivially subsumed by another.

### 3.6 Breadth (S6)
Certified connector count by family, and — the harder test — the number of the *benchmark's* source
types each tool can validate at all. A tool that cannot read the EBCDIC feed scores zero on every
defect in it. Report as a coverage matrix, not a count.

### 3.7 Time-to-detection (S7)
Wall-clock from defect introduction to alert emission, in streaming and batch, at the 50th, 95th,
and 99th percentiles, measured by an instrumented harness that stamps the injection.

### 3.8 Audit readiness (S8)
Percentage of controls that satisfy an independently-authored RDARR test script executed by a Big-4
audit team: can you evidence the control, its version, its approval, its execution, its outcome,
and can you replay it? Scored pass/fail per criterion, with the script published.

### 3.9 Cost (S9)
Source compute (credits/DBUs/slot-seconds) and control-plane compute per billion rows validated,
compared against (a) a naive per-rule full-scan implementation and (b) each competitor at equal
control coverage. Also report the marginal cost of the 1,000th control on a table — the number that
decides whether coverage can grow.

### 3.10 Learning (longitudinal)
Alert precision, proposal acceptance rate, RCA top-hypothesis accuracy, and break-classification
accuracy measured monthly over 12 months at design partners, with a frozen-model control arm to
isolate the effect of learning from the effect of estate maturation.

---

## 4. Baselines

Every headline claim is measured against a named, versioned, honestly-configured baseline:

| Class | Baselines |
|---|---|
| Declarative OSS | Great Expectations, Soda Core, dbt tests + dbt-expectations, Deequ, DQOps |
| ML observability | The leading commercial platform (licence permitting; otherwise a faithful reimplementation of its published method), plus open equivalents (Evidently, Elementary) |
| Platform-native | Snowflake DMFs, Databricks Lakehouse Monitoring + DLT expectations, AWS Glue Data Quality |
| Enterprise DQ | An established augmented-DQ suite via a partner or evaluation licence |
| Research | HoloClean, Raha/Baran, ZeroED (error detection); Splink/Zingg (ER); Metanome/Desbordante (constraint discovery) |
| Ablations of Prama | rules-only · monitors-only · uncalibrated monitors · no semantic layer · no learning loop · LLM-from-schema-only induction |

**Baseline honesty protocol.** Each baseline is configured by someone incentivised to make it look
good — ideally its own documentation's recommended setup, and where possible reviewed by a
practitioner of that tool. Comparisons where licence terms forbid publication are reported as
anonymised ("Vendor A"). We publish the configuration for every baseline.

**Ablations are the most important comparison.** They answer *"which of our claims is actually
doing the work?"* — the question a reviewer and a serious buyer both ask.

---

## 5. Experimental protocol

1. **Pre-registration.** Hypotheses, metrics, and analysis plan are recorded before results are
   collected, for the live-shadow study in particular.
2. **Blinding.** Steward adjudication in live-shadow is blind to the alert's origin.
3. **Repetition.** Every benchmark run is repeated ≥ 5 times with different seeds; report medians
   and interquartile ranges, never single runs.
4. **Statistics.** Paired bootstrap confidence intervals on F1 differences; McNemar for paired
   detection outcomes; Holm–Bonferroni correction across the family of comparisons. Effect sizes,
   not just p-values.
5. **Reproducibility.** Benchmark generators, seeds, configurations, Prama version, baseline
   versions, and hardware specifications published with results; an artefact-evaluation-ready
   container.
6. **Negative results reported.** Any criterion we fail is published alongside the ones we pass.
   The credibility of the whole exercise depends on this.

---

## 6. Threats to validity

| Threat | Mitigation |
|---|---|
| **Benchmark authored by the vendor** | Publish generators and taxonomy; invite external contribution; report competitor-favourable families; recruit an independent advisory reviewer |
| **Injected defects are unrealistically detectable** | Taxonomy derived from real incident post-mortems at design partners; adversarial tier explicitly includes legitimate-change traps |
| **Live-shadow selection bias** | Three institutions of different size and platform mix; report per-site results, not only pooled |
| **Baseline misconfiguration** | Documented protocol above; publish configurations for challenge |
| **Steward adjudication error** | Dual adjudication with disagreement resolution; report inter-rater agreement (Cohen's κ) |
| **Calibration assumptions violated** | Report explicitly where guarantees are suspended; measure how often, not only how well |
| **Overfitting to the benchmark** | Held-out defect families and a rotating hidden set for the leaderboard |
| **Hawthorne effects in the effort study** | Randomised tool order; measure task correctness as well as speed |

---

## 7. Release gates

Failing any of the following blocks GA:

| Gate | Threshold |
|---|---|
| S1 detection F1 vs. best baseline | ≥ +15% overall; ≥ +40% on the semantic defect family |
| S2 alert precision (live-shadow) | ≥ 0.85 at declared FDR ≤ 0.10 |
| S3 calibration error | ≤ 0.02 across all tested regimes |
| S4 authoring time | ≤ 3 min median to a reviewed control (chat/induction route) |
| S5 coverage after 1 week | ≥ 80% of columns, ≥ 95% of declared CDEs |
| S6 connector breadth | ≥ 120 certified, incl. ≥ 12 financial message standards |
| S7 detection latency | p95 ≤ 60 s streaming; ≤ 1 interval + 5 min batch |
| S8 audit readiness | 100% of controls pass the independent RDARR script |
| S9 cost | ≤ 50% of naive full-scan baseline at equal coverage |
| Conformance | 100% of PQL constructs pass on every supported engine |
| Accessibility | WCAG 2.2 AA, zero critical findings |
| Isolation | Zero cross-tenant leakage findings |
| AI safety | Zero code paths where an LLM output reaches a verdict; adversarial injection corpus fully passed |

---

## 8. Continuous benchmarking

The benchmark is not a launch artefact; it is CI. Every release runs the full suite; a >10%
regression on any headline metric blocks the release (`NFR-TST-004`). Results are published per
release so customers can see the trajectory — including the quarters where it flattens.

---

<div align="center">
<img src="assets/prama-mark.svg" width="30" alt=""/><br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.<br/>
See <a href="../LICENSE">LICENSE</a> and <a href="../NOTICE">NOTICE</a>. Third-party names and marks are the property of their respective owners.</sub>
</div>
