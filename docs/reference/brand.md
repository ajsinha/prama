# Brand — Name, Mark, and Voice

<img src="../assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="420"/>

---

## 1. The name

**Prama** — from Sanskrit **प्रमा** (*pramā*): *valid cognition; knowledge that is true and
justified*. Its companion term **प्रमाण** (*pramāṇa*) means *the instrument by which valid
knowledge is obtained*.

This is the most precise available description of the product. Prama does not create data and does
not decide what is true; it is the **instrument** through which an organisation establishes that
what it believes about its data is *justified*. In Indian epistemology, a belief is *pramā* only if
it is both true **and** arrived at by a reliable means — which is exactly the distinction between
"our dashboard is green" and "we can prove this number is right."

Practical merits: five letters, two syllables, unambiguous pronunciation (**PRAH-muh**), no
collision with an established data-infrastructure vendor, and it works as a verb in the product
(*"pramā the estate"*, *"pramad"* for the daemon) without strain.

---

## 2. The slogan

### Primary
> # Declare it. Prove it. Trust it.

Three words that *are* the product architecture:

| Slogan clause | Product reality |
|---|---|
| **Declare it.** | The business semantic layer — you say what your data means and how it relates ([03](../corpus/03-business-semantic-layer.md)) |
| **Prove it.** | Deterministic, replayable execution producing immutable evidence ([13](../corpus/13-security-governance-compliance.md) §6) |
| **Trust it.** | Calibrated scores and trust that propagates along lineage ([11](../corpus/11-reporting-alerting-learning.md)) |

### Short lockup line
> **Trust, proven.**

For favicon-adjacent contexts, tight lockups, and the boilerplate line under the wordmark where
the three-clause version won't fit.

### Brand-story line (etymological, used once per document/deck)
> **The instrument of valid knowledge.**

### Segment variants
| Context | Line |
|---|---|
| Banking / regulatory | **Every number, defensible.** |
| AI / data platform teams | **AI is only as true as its data.** |
| Executive / board | **Know what your data is worth trusting.** |
| Engineering / developer | **Write the control once. Prove it everywhere.** |

### Rejected, and why
*"Data quality, reimagined"* (says nothing) · *"The future of data trust"* (undated in 18 months) ·
*"AI-powered data quality"* (commodity claim; every competitor says it) ·
*"Clean data, always"* (we do not promise clean data — we promise **proven** data).

---

## 3. The mark — the "Pramāṇa Prism"

<img src="../assets/prama-mark.svg" alt="Prama mark" width="88"/>
&nbsp;&nbsp;
<img src="../assets/prama-seal.svg" alt="Prama attestation seal" width="104"/>

**Concept.** A broken, uncertain beam enters a prism from the left; six clean, ordered rays leave
it on the right.

**Why it is right for this product:**

1. **A prism adds nothing.** It reveals structure that was already present in the light. Prama does
   not alter your data; it reveals what is true about it. This is precisely the honest claim.
2. **The six exit rays are the six quality dimensions** — accuracy, completeness, consistency,
   timeliness, uniqueness, validity. The mark literally depicts decomposition into measurable
   dimensions.
3. **The broken entry beam is unverified data**; the solid exit rays are evidence. The
   before/after is legible in a fraction of a second, at any size.
4. **The triangle is an instrument**, not a badge — it reads as apparatus and measurement rather
   than as a shield or a checkmark, which is the honest positioning: we are a measuring instrument,
   not a guarantee.
5. It carries the Sanskrit etymology without any orientalist ornament, and it is culturally neutral,
   trademark-clean in the category, and legible at 16 px.

**Seal variant.** The mark enclosed in a double ring becomes the **attestation seal** — used on
generated evidence artefacts, attestation reports, certificates, and regulator-facing exports. The
double ring deliberately evokes an assay mark or a notarial seal: *this artefact was produced by a
verified control execution.* It should never be used as the app icon; it is reserved for evidence.

**Asset set.** `assets/prama-mark.svg` (primary) · `assets/prama-seal.svg` (evidence artefacts) ·
`assets/prama-lockup.svg` (horizontal lockup with slogan) · `assets/prama-favicon.svg`
(the console header's mark, three rays, on a tile of the header's crimson-to-indigo gradient —
the only permitted simplification). The favicon is derived, not drawn separately:
`tests/web/test_favicon.py` fails unless its shapes are the header mark's and its tile is the
light theme's header gradient, so a change to either reaches the browser tab.

**Usage rules.**
- Clear space on all sides ≥ the height of the prism.
- Minimum size: 20 px for the mark, 16 px for the favicon variant, 120 px wide for the lockup.
- Never: rotate the prism, recolour the six rays to a single colour, add a drop shadow, place the
  mark on a busy photograph, or stretch the lockup non-uniformly.
- On dark backgrounds, the prism edge switches to `#FFFFFF`; the six rays are unchanged.

---

## 4. Palette

| Role | Name | Hex | Use |
|---|---|---|---|
| Primary | Prama Indigo | `#0E1A46` | Wordmark, headers, primary surfaces |
| Primary light | Refract Blue | `#2B3FA8` | Prism edge, links, active states |
| Neutral | Unverified Grey | `#8A93AD` | The broken input beam; disabled/stale states |
| Ink | Slate | `#5A6480` | Secondary text |
| Spectrum 1 | Accuracy Teal | `#00B3A4` | Dimension colour + "healthy" |
| Spectrum 2 | Completeness Green | `#2FB673` | Dimension colour |
| Spectrum 3 | Consistency Lime | `#8CBF3F` | Dimension colour |
| Spectrum 4 | Timeliness Amber | `#E8B33A` | Dimension colour + "warning" |
| Spectrum 5 | Uniqueness Orange | `#E8823A` | Dimension colour |
| Spectrum 6 | Validity Red | `#D9534F` | Dimension colour + "critical" |

The spectrum doubles as the product's **dimension colour language**: the same six hues identify the
same six dimensions on every scorecard, chart, and report, so a colour is never decorative.
Status semantics reuse the spectrum ends (teal = pass, amber = warning, red = fail) and
**Unverified Grey is reserved exclusively for "stale / not yet examined"** — a state most products
hide and we make visible ([03](../corpus/03-business-semantic-layer.md) §6.3).

Accessibility: all foreground/background pairings meet WCAG 2.2 AA (≥ 4.5:1); the six dimension
hues are additionally distinguishable under deuteranopia and protanopia simulation, and are always
paired with a label or icon — never colour alone.

---

## 5. Voice

**We sound like:** a precise, unhurried expert who shows their working.

| Do | Don't |
|---|---|
| "Counterparty LEI completeness fell 4.2 points this week, concentrated in the EMEA feed." | "Data quality issues detected!" |
| "We estimate this control will fire ~3 times a month. Here is what it would have caught last quarter." | "AI-powered intelligent monitoring." |
| "This finding is 9 days old and the dataset has changed since." | (silently showing a stale number) |
| "I can't determine that from what I have. Here's who can." | Confident speculation |
| Numbers with their provenance | Numbers alone |

**Cardinal rule:** never assert without evidence, and never hide uncertainty. The brand promise is
*proof*, and a single unsupported claim in the product does more damage than a missing feature.

---

<div align="center">
<img src="../assets/prama-mark.svg" width="30" alt=""/><br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.<br/>
See <a href="../../LICENSE">LICENSE</a> and <a href="../../NOTICE">NOTICE</a>. Third-party names and marks are the property of their respective owners.</sub>
</div>
