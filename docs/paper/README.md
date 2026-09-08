<img src="../assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

> ***pramā*** (Sanskrit **प्रमा**) — *valid knowledge: a cognition that is both true and arrived at
> by a reliable means*. Its companion ***pramāṇa*** (प्रमाण) is *the instrument by which valid
> knowledge is obtained*. Prama is that instrument for an organisation's data — it does not decide
> what is true, it is how a belief about data becomes **justified**.
>
> **Declare it. Prove it. Trust it.**


---
# Academic Paper — Plan & Artefacts

| File | Purpose |
|---|---|
| [`prama-paper.md`](prama-paper.md) | Full manuscript draft (venue-neutral Markdown; LaTeX conversion at submission) |
| [`references.bib`](references.bib) | Bibliography |
| [`experiment-plan.md`](experiment-plan.md) | Detailed experimental protocol, artefact list, and reproducibility package |

## Venue strategy

| Target | Type | Fit | Timing |
|---|---|---|---|
| **ACM JDIQ** (Journal of Data and Information Quality) | Primary | Quarterly, multi-disciplinary: modelling & measurement, cleansing algorithms, organisational management, real-world evaluation. The only venue whose charter covers *all* of our contributions in one paper. | Submit at GA (month ~15) |
| **VLDB Industrial Track** | Companion | Systems contribution: IR, cross-engine equivalence, fusion, scale results | Month ~15–18 |
| **SIGMOD Industry** / **ICDE Industry** | Alternate | Same systems angle | Fallback |
| **CIDR** | Vision paper | "Data quality as a calibrated, evidence-producing control plane" — the argument, short and early | Month ~10 |
| **DEEM / aiDM / QDB workshops** | Focused | Calibration result standalone; benchmark paper standalone | Month ~9 onward |

**Recommended sequence:** a CIDR-style vision paper early (establishes the framing and the term
"risk-controlled data quality alerting"), the benchmark as its own resource paper (maximises
citation and adoption), then the full JDIQ systems-and-method paper at GA.

## Splitting the work

The material supports **three** publishable papers. Attempting one is a mistake — each contribution
is strong enough to stand, and reviewers punish overloaded systems papers.

| # | Paper | Core claim | Venue |
|---|---|---|---|
| **P1** | *Risk-Controlled Alerting for Data Quality Monitoring* | Conformal calibration + hierarchical FDR over the asset×attribute×check lattice gives an operator-declarable false-alarm budget with empirical validity under drift | VLDB / JDIQ / DEEM |
| **P2** | *DQ-Bench: A Defect-Labelled Benchmark for Enterprise Data Quality* | The first public, cross-system, semantically-defect-labelled benchmark, plus a banking instantiation | VLDB resource track / JDIQ |
| **P3** | *Prama: A Declarative, Calibrated, Evidence-First Data Quality Control Plane* | The system: semantic layer → IR → calibrated execution → evidence → trust propagation, with deployment experience | JDIQ (primary) + VLDB Industrial |

## Artefacts to release

1. **DQ-Bench** and **FinDQ-Bench** generators, seeds, defect taxonomy, and labels (open licence).
2. **PQL grammar, IR specification, and the conformance test suite.**
3. A **reference calibration implementation** (weighted conformal + hierarchical BH) as a standalone
   library.
4. Baseline configurations for every compared system, published for challenge.
5. An artefact-evaluation container reproducing every table and figure.

## Authorship & ethics

- Author list: engineering + research contributors by contribution, with an explicit CRediT
  statement.
- **Conflict-of-interest declaration:** the benchmark is authored by the vendor whose system it
  evaluates. Mitigations (published generators, external advisory reviewer, published negative
  results, published baseline configurations) are stated in the paper, not hidden in an appendix.
- **Data statement:** FinDQ-Bench is fully synthetic; no customer or personal data. Live-shadow
  results are reported in aggregate, per-site anonymised, under partner agreement, with an ethics
  note on steward-participation consent.
- **Negative results are in the main body**, not the appendix.

---

<div align="center">
<img src="../assets/prama-mark.svg" width="30" alt=""/><br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.<br/>
See <a href="../../LICENSE">LICENSE</a> and <a href="../../NOTICE">NOTICE</a>. Third-party names and marks are the property of their respective owners.</sub>
</div>
