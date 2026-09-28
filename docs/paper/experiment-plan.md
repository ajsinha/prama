<img src="../assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

> ***pramā*** (Sanskrit **प्रमा**) — *valid knowledge: a cognition that is both true and arrived at
> by a reliable means*. Its companion ***pramāṇa*** (प्रमाण) is *the instrument by which valid
> knowledge is obtained*. Prama is that instrument for an organisation's data — it does not decide
> what is true, it is how a belief about data becomes **justified**.
>
> **Declare it. Prove it. Trust it.**


---
# Experiment Plan & Reproducibility Package

> **This is the plan, not the results.** It was written before most of the code existed, and it
> describes experiments — live-shadow deployments, competitor baselines, design-partner corpora — that
> have **not** been run. What has been measured, and what has not, is in the paper
> ([`data-quality-as-justified-belief.tex`](data-quality-as-justified-belief.tex), [PDF](data-quality-as-justified-belief.pdf)), §11 *Evaluation* and §12 *The claims register*.

Operationalises [15 — Evaluation & Benchmark Methodology](../15-evaluation-benchmark-methodology.md).

---

## 1. Pre-registration

Before any results are collected, the following are recorded in a timestamped, hash-committed
document: hypotheses (RQ1–RQ10), primary and secondary metrics, sample sizes, analysis plan,
stopping rules, and the exclusion criteria for live-shadow alerts. The live-shadow study is
pre-registered with the design partners as a condition of the agreement.

## 2. Experiments

| E | RQ | Design | Primary metric | Baselines |
|---|---|---|---|---|
| E1 | RQ1 | DQ-Bench, all defect families × 4 difficulty tiers × 3 scales, 5 seeds | Defect-level F1 (dataset+column+window must match) | GX, Soda, dbt, Deequ, DQOps, ML-observability, platform-native, Raha, ZeroED |
| E2 | RQ1 | Ablation: rules-only / monitors-only / no semantic layer / no learning | ΔF1 per family | Prama variants |
| E3 | RQ2 | Synthetic drift regimes (stationary, seasonal, level-shift, regime-switch, bursty) × 1,000 monitors | Calibration curve; \|empirical − nominal\|; ECE; coverage under shift | Uncalibrated Prama; static-threshold; commercial "sensitivity" settings |
| E4 | RQ3 | FinDQ-Bench, 10⁴ monitors, sweep target FDR ∈ {0.01,0.05,0.10,0.20} | Precision@alert; recall at fixed budget; alerts/steward-week | Per-monitor thresholding; no correction; flat BH |
| E5 | RQ4 | Induction run at declaration stages 0–6 on the same estate | Acceptance rate; precision of accepted rules; time-to-approval | — |
| E6 | RQ5 | Induction: mining-only / LLM-only / fused | Acceptance rate; coverage; hallucination rate (candidates failing empirical validation) | — |
| E7 | RQ5 | Label-efficiency of example-driven induction | Rules induced per labelled cell; F1 vs. labels (5,10,20,50,100) | Raha |
| E8 | RQ6 | Conformance suite over all supported engines; conversion of 500 real design-partner controls | Pass rate; % expressible in the portable subset; enumerated divergences | — |
| E9 | RQ7 | 10⁹-row estate, equal control coverage across tools | Source compute per 10⁹ rows; marginal cost of the 1,000th control | Naive per-rule full scan; each baseline |
| E10 | RQ8 | Simulated remediation budget on FinDQ-Bench lineage | Trust uplift per unit effort; defect-escape reduction | Severity-ranked; random |
| E11 | RQ9 | 12-month longitudinal at 3 partners, frozen-model control arm | Monthly precision, acceptance, RCA top-1 accuracy, MTTR | Frozen-model Prama |
| E12 | RQ10 | Declaration behaviour at 3 partners | Declarations/week; controls per declaration; estate maturity vs. defect escape | — |
| E13 | S4 | Controlled authoring study, 12 participants × 3 personas × 10 tasks, randomised order | Time to *reviewed* control; correctness; confidence | SodaCL, GX, incumbent UI |
| E14 | S8 | Independent Big-4 RDARR test script | Pass/fail per criterion | Incumbent tool at the same site |
| E15 | S7 | Instrumented injection harness | p50/p95/p99 detection latency, streaming and batch | Each baseline |

## 3. Statistical analysis

- Paired bootstrap (10,000 resamples) confidence intervals on all F1 differences.
- McNemar's test for paired detection outcomes on identical defect sets.
- Holm–Bonferroni correction across the family of primary comparisons.
- Effect sizes (Cliff's δ for ordinal outcomes, Cohen's d where distributional assumptions hold)
  reported alongside every p-value.
- Cohen's κ for inter-rater agreement in live-shadow adjudication; disagreements resolved by a third
  adjudicator and reported, not silently dropped.
- Medians and IQRs across ≥ 5 seeds; single-run numbers are never reported.

## 4. Artefacts released

| Artefact | Contents | Licence |
|---|---|---|
| `dq-bench` | Generators, defect taxonomy, injection code, seeds, labels, loader, leaderboard protocol | Open |
| `findq-bench` | Synthetic bank generator (120 datasets, 90 relationships, 6 journeys), message flows, COBOL feed, recon populations, seeds | Open |
| `pql-spec` | Grammar, IR schema, conformance corpus `Π`, reference interpreter | Open |
| `prama-calibrate` | Weighted conformal + hierarchical BH/BY reference implementation | Open |
| `baselines` | Configuration for every compared system, published for challenge | Open |
| `artifact` | Container reproducing every table and figure end-to-end | Open |

## 5. Hardware and environment

All benchmark runs on a fixed, documented configuration (cloud instance types, engine versions,
warehouse sizes, cluster shapes), with the identical configuration used for every compared system.
Cost metrics are reported in engine-native units (credits, DBUs, slot-seconds) as well as normalised
per-10⁹-rows figures, so readers can re-price against their own contracts.

## 6. Reporting commitments

1. **Negative results in the main body.** Any of S1–S9 that we fail is reported in the results
   section, not an appendix.
2. **Per-family and per-site breakdowns**, never only pooled aggregates.
3. **Guarantee-suspension frequency** reported alongside calibration quality — how often the
   guarantee holds matters as much as how well it holds when it does.
4. **Conflict of interest** stated in the main text: the benchmark is authored by the vendor whose
   system it evaluates, with the mitigations listed.
5. **No cherry-picked operating points**: precision–recall curves, not single thresholds.

---

<div align="center">
<img src="../assets/prama-mark.svg" width="30" alt=""/><br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.<br/>
See <a href="../../LICENSE">LICENSE</a> and <a href="../../NOTICE">NOTICE</a>. Third-party names and marks are the property of their respective owners.</sub>
</div>
