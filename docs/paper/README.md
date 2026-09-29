<img src="../assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

> ***pramā*** (Sanskrit **प्रमा**) — *valid knowledge: a cognition that is both true and arrived at
> by a reliable means*. Its companion ***pramāṇa*** (प्रमाण) is *the instrument by which valid
> knowledge is obtained*. Prama is that instrument for an organisation's data — it does not decide
> what is true, it is how a belief about data becomes **justified**.
>
> **Declare it. Prove it. Trust it.**


---
# The Paper

**Data Quality as Justified Belief: Derived Controls, Deterministic Verdicts, and Evidence that
Verifies Without Its Author.** Ashutosh Sinha, 2026. 41 pages.

The thesis: a data quality claim is a belief, and it is worth acting on only when it is justified. That
becomes three constraints — a control derives from a declaration, a verdict comes from a deterministic
engine, and evidence verifies without its author — and the paper gives the formal account of each,
together with reconciliation, lineage read from code, the model boundary, trust propagation and
false-alarm budgets.

## Artefacts

| File | What it is |
|---|---|
| [`data-quality-as-justified-belief.tex`](data-quality-as-justified-belief.tex) | The paper: definitions, propositions and proofs, each marked with what enforces it in the code |
| [`data-quality-as-justified-belief.pdf`](data-quality-as-justified-belief.pdf) | The compiled paper |
| [`data-quality-as-justified-belief-article.md`](data-quality-as-justified-belief-article.md) | A long-form article version for engineers and data owners |
| [`references.bib`](references.bib) | Bibliography, used by `data-quality-as-justified-belief.tex` through BibTeX (`plainurl`) |
| [`experiment-plan.md`](experiment-plan.md) | The experimental protocol written before the code existed. **The plan, not results** |

## How the paper keeps itself honest

Every formal claim carries a marker: **Runs** names a test as `tests/path::test_name`; **In part**
says what is weaker in the code than on the page; **Not executed** marks mathematics the code does
not check; **Not in Prama** marks what is not built. Section 12 is a claims register: of seventy-five
rows, **53 run, 11 run in part, 5 are stated without being executed, and 6 are not built**.

Every number is either from a run of the repository or from an assertion in a named test, and the
paper says which. The case-study table, the benchmark table and the calibration grid were produced by
running `case-studies/*/run.py --no-serve`, `prama bench run --seed 42` and
`pytest -s tests/monitor/test_benchmark.py` respectively.

To check that every cited test still exists and passes:

```bash
python3 - <<'EOF' > /tmp/ids.txt
import re
s = open("docs/paper/data-quality-as-justified-belief.tex").read().replace("\\_", "_")
print("\n".join(sorted(set(re.findall(r"(tests/[\w/]+\.py::[\w:]+)", s)))))
EOF
pytest -q $(grep -v casestudies /tmp/ids.txt)
```

A cited test that has been renamed or deleted makes `pytest` report it as not found. The register is
kept in the paper rather than in an executable file, which is weaker than the paper argues for.

## Rebuilding the PDF

```bash
cd docs/paper
latexmk -pdf data-quality-as-justified-belief.tex        # pdflatex + bibtex, rerun until references settle
latexmk -c                    # remove the auxiliary files
rm -f prama.bbl               # latexmk -c keeps the .bbl
```

Requires a TeX Live with `tcolorbox`, `cleveref`, `aliascnt`, `hyphenat`, `xurl` and the `urlbst`
styles. It should build with no errors and no undefined references; the only warnings are font-shape
substitutions. Check the metadata with `pdfinfo data-quality-as-justified-belief.pdf`.

## Venue

The paper is a single systems-and-method manuscript. **ACM JDIQ** remains the natural home: its charter
covers modelling and measurement, organisational practice and real-world evaluation in one journal. A
systems-track submission (VLDB or SIGMOD industrial) would need what the paper says is missing —
deployment at a real site and a comparison against external baselines — and is not realistic until
those exist. The earlier plan to split the work into three papers (calibration, benchmark, system)
presupposed results on real data and on a public benchmark scored across systems; neither exists yet.

## Authorship and ethics

- Sole author. No other contributor.
- **Conflict of interest.** The system, the case studies, the planted defects and the benchmark are all
  written by the author of the system they evaluate. The paper states this in the body, reports what the
  system did *not* find, and makes no claim of detection quality relative to other systems.
- **Data.** Every dataset is fabricated and seeded. No customer or personal data is used.
- **Negative results are in the main body**, not an appendix.

---

<div align="center">
<img src="../assets/prama-mark.svg" width="30" alt=""/><br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.<br/>
See <a href="../../LICENSE">LICENSE</a> and <a href="../../NOTICE">NOTICE</a>. Third-party names and marks are the property of their respective owners.</sub>
</div>
