<img src="../assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

> ***pramā*** (Sanskrit **प्रमा**) — *valid knowledge: a cognition that is both true and arrived at
> by a reliable means*. Its companion ***pramāṇa*** (प्रमाण) is *the instrument by which valid
> knowledge is obtained*. Prama is that instrument for an organisation's data — it does not decide
> what is true, it is how a belief about data becomes **justified**.
>
> **Declare it. Prove it. Trust it.**


---
# 21 — How We Win

**Companion to [20 — Competitive Analysis](20-competitive-analysis.md).** That document named seven
gaps. This one answers the only question that matters: *what do we do about them?*

---

## As built

Unlock 1 — **the auditor's validation** — has its mechanism:
`scripts/verify_evidence.py` checks an evidence bundle with no Prama and no
third-party imports, refuted five ways in the test suite. An independent auditor
running it at a client site remains an engagement rather than a build task.

Unlock 2 — **the regulatory catalogue** — ships twenty obligations across nine
regimes, every citation marked *unconfirmed against the published text* until a
compliance function checks it. `prama pack claims` prints that count (currently
0 of 20) rather than leaving a reader to assume. A wrong article number costs
more credibility than an absent one.

Unlock 3 — **the semantic discriminator** — is measured rather than asserted:
every deterministic ablation is blind to the semantic defect family, which is
the claim this strategy rests on, stated as a number in `prama bench`.

**The rest of this document is strategy, not status.** Design-partner counts,
the ninety-day shadow runs and the published benchmarks are commercial work, and
none of it is done.

---

## 0. First principles, not competitors

Before any of the tactics below, the governing rule:

> **Prama is built from a thesis about the problem, not from a list of what competitors have.**

The competitive material in [20](20-competitive-analysis.md) and in this document exists for two
narrow purposes: so that we do not accidentally rebuild something that already exists, and so that
we can answer a buyer who asks about a named alternative. It is **input to decisions, never the
framework for them.** A roadmap assembled from competitor feature grids produces a me-too product
with no opinion, arriving late to every idea it contains.

Three consequences, and they bind:

1. **No feature enters the roadmap because a competitor has it.** It enters because our thesis —
   that a number is trustworthy only when it is declared in business terms, executed at source,
   calibrated statistically and provable afterwards — requires it. Gap G2 (lineage scanners) is in
   the plan because trust propagation needs lineage, not because Manta has fifty scanners.
2. **We concede categories without embarrassment.** We are not building a catalog or an MDM hub.
   Saying so first, unprompted, is a strength: it is what makes the rest of our claims believable.
3. **Where our thesis leads somewhere nobody has been, we go there** and accept that it will not
   appear on anyone's comparison grid for a year or two. Every item in §0.1 was in that position
   when we chose it.

### 0.1 What is original to Prama

Not "better than X" — genuinely ours, arrived at from the problem rather than from the market. As
far as our survey of the commercial landscape and the research literature could establish, no
shipping product does these:

| # | Original to Prama | Why it exists |
|---|---|---|
| 1 | **Business declarations compile into executable controls.** Thirteen typed relationship kinds, a grain, a rhythm and an attribute interpretation each generate real, running, evidenced controls. | Because the knowledge that makes monitoring effective lives with business owners, and no tool has ever let them express it in a form that executes. |
| 2 | **Risk-controlled alerting.** Conformal p-values with hierarchical FDR control over the domain → dataset → attribute → check lattice, under a false-alarm budget the operator declares in operational terms. | Because alert fatigue, not detection power, is what kills monitoring programmes — and an uninterpretable "sensitivity" dial cannot be reasoned about. |
| 3 | **An engine-neutral quality IR** with certified cross-engine semantic equivalence. | Because a bank migrates platforms every few years and should not rewrite its control estate — and its auditor should not have to re-approve it. |
| 4 | **Lineage-aware trust propagation** as a semiring over the column-level lineage DAG with transformation-aware attenuation. | Because a gold table built from a failing bronze table is not trustworthy, and scoring assets in isolation is not merely uninformative but misleading. |
| 5 | **Deterministic replay with a divergence report.** A control either reproduces its verdict exactly or names why it cannot — restated data, expired snapshot, engine upgrade, moved code list. | Because "we ran a control" is not evidence; "here is the control, the data it saw, and the same answer again" is. |
| 6 | **`indeterminate` as a first-class verdict**, and unknown-as-violation by default. | Because silence about unknowns is the largest single source of false confidence in production quality suites. |
| 7 | **Metadata drift as an incident**, routed to the business owner of the declaration. | Because only a platform that holds a declared model can check the model against reality; a physical-first tool has nothing to compare. |
| 8 | **Staleness as a rendered state.** Every finding carries its own freshness, and a stale conclusion is never displayed as current. | Because every other tool shows you a number without telling you when it last looked. |
| 9 | **Sensitivity expressed as a budget**, not a dial: *"no more than two false alarms a month in this domain."* | Because that is the sentence the accountable person actually wants to say. |
| 10 | **Neural authorship, symbolic execution** as an enforced architectural invariant, tested in CI. | Because a verdict a regulator cannot replay is not a verdict, and because it is also the only affordable design at 10¹² rows. |

Half of these came from taking the research literature seriously — conformal prediction,
constraint discovery, weak supervision — which is essentially unexploited commercially. The other
half came from taking the *business owner* seriously as the user. Neither route runs through a
competitor's feature list.

**The test to apply to any future roadmap item:** *which of the ten does this serve, or which
eleventh does it add?* If the honest answer is "a competitor has it", the item needs a better
reason before it is funded.

---

## 1. The strategic error to avoid

The instinctive response to a gap list is to close it. That instinct would lose us the company.

Every gap we identified is a gap against someone's **core strength**, built over 5–15 years by teams
larger than ours. Manta has fifty-plus scanners because IBM bought a company that spent a decade
writing them. Alation's curation UX is a decade of iteration. Monte Carlo's detectors are years of
tuning on real customer estates. If we spend the next 24 months chasing those, we arrive in 2028
having built a worse Manta, a worse Alation and a worse Monte Carlo, with no differentiator left
because we spent the budget catching up instead of pulling ahead.

> **The rule: never spend a dollar competing with a competitor's strength when the same dollar can
> buy ground they cannot follow onto.**

So this plan does three different things to three different kinds of gap:

| Action | Meaning | Applied to |
|---|---|---|
| **Neutralise** | Make the gap *non-decisive* in a deal without closing it — usually by integrating, reframing, or removing it from the evaluation criteria | Lineage scanners, catalog UX, detector maturity |
| **Close** | Genuinely build it, because it decides deals and is finite | Time to first value, references, procurement safety |
| **Concede loudly** | Say we don't do it, first, before they ask — which buys credibility for everything else | Catalog, MDM, recon-ops parity |

---

## 2. Which gaps actually lose deals

Not all gaps cost the same. Ranked by how often each appears in a *lost-deal post-mortem* — which
is different from how large the gap is:

| Rank | Gap | Loses the deal when | Cost to fix | Verdict |
|---|---|---|---|---|
| **1** | **No reference customers** (G1) | Always. Every deal, every stage. | High but finite | **Close. First priority.** |
| **2** | **Time to first value** (G3) | In the POC, before we're heard | Medium — it's a product gate | **Close. Second priority.** |
| **3** | **Procurement safety / brand** (G7) | At legal and security review | Medium | **Close via falsifiability + certifications** |
| 4 | Legacy ETL lineage scanners (G2) | Only in lineage-*led* Tier-1 deals | Very high if built exhaustively | **Neutralise; close selectively** |
| 5 | Detector maturity (G5) | Rarely — precision beats recall in practice | High | **Neutralise via champion/challenger** |
| 6 | Recon operations depth (G6) | Only against Duco head-to-head | High | **Concede scope, win on breadth** |
| 7 | Catalog UX (G4) | Only when the buyer wants a catalog | Enormous | **Concede loudly** |

The top three account for most losses and are the cheapest to address. Ranks 4–7 look larger on a
feature grid and matter far less in a room.

---

## 3. The three asymmetric unlocks

These are the moves where a small amount of our effort produces a large amount of competitive
displacement, because **no incumbent can copy them without harming themselves**. That asymmetry is
what makes them worth doing first.

### Unlock 1 — Make the auditor the reference, not the bank

**The insight.** A bank does not buy a control platform because it likes the UI. It buys what its
**auditor and its regulator will accept**. We are treating the Big-4 RDARR test script
([15 §3.8](15-evaluation-benchmark-methodology.md)) as a release gate. It is far more than that:
it is a **reference we can buy in months rather than earn in years**.

**The move.** Commission an independent Big-4 or specialist assurance firm to test the evidence
pack against their own RDARR/SOX control-evidence criteria, and publish the result — including any
criteria we fail. Then make the same firm a channel partner: they encounter the "our client cannot
evidence their controls" problem in every engagement, and they currently have nothing to recommend
but a spreadsheet and a services line.

**Why it is asymmetric.** No incumbent can respond in kind, because none of them would survive the
test. Monte Carlo has mutable alert history. Alation has no verdicts. Solidatus evidences topology,
not outcomes. **An auditor's attestation is a reference that our competitors structurally cannot
obtain**, and it is the exact reference our buyer weights most.

**Cost:** roughly one engagement fee plus engineering time. **Timeline:** 4–6 months.
**Effect:** converts G1 and G7 simultaneously.

---

### Unlock 2 — Compete on being measurable

**The insight.** We are the unknown vendor, so trust is our scarcest asset. The conventional
response is to accumulate logos slowly. The unconventional one is to **make the comparison
falsifiable and invite it**, because an unknown vendor that can be *measured* beats a known vendor
that must be *trusted* — and every incumbent has more to lose from a measured comparison than we do.

**The moves, in order:**

1. **Publish DQ-Bench and FinDQ-Bench** with generators, seeds, defect labels and *baseline
   configurations for every competitor*. A public benchmark is a reference that needs no customer.
2. **Offer the blind shadow bake-off** as a standard commercial term: 90 days beside the incumbent,
   same scopes, no production actions, the customer's own stewards adjudicating every alert **blind
   to which system raised it** ([15 §2.3](15-evaluation-benchmark-methodology.md)).
3. **Publish our failures.** Every criterion we miss, in the main body, next to the ones we pass.
4. **Publish the research** ([paper/](../publications/paper/)). "Peer-reviewed" is a procurement-grade word that no
   other vendor in this market can use.

**Why it is asymmetric.** An incumbent with a strong brand and mediocre alert precision has
everything to lose from a blind evaluation and will decline. **Their refusal is our strongest
argument**, and it costs us nothing to make the offer. Meanwhile a vendor that publishes its own
negative results is doing something no marketing department permits, which is exactly why it reads
as credible.

**Cost:** benchmark engineering, already planned. **Timeline:** ships with GA.
**Effect:** converts G7, and substitutes for G1 while references accumulate.

---

### Unlock 3 — Win day one on their terms, then win day thirty on ours

**The insight.** Our semantic layer is the moat, and in the first hour of a POC it reads as
*homework*. Anomalo monitors in an afternoon; we ask someone to describe a grain. That comparison
happens before any of our differentiators are visible, and it is how we lose deals we should win.

**The reframe:** stop treating declarations as the price of entry. **Deliver Anomalo-grade value at
zero declarations, and make declarations the upgrade that visibly earns its keep.**

**What that requires concretely:**

- **Hour one, zero input:** connect → profile → semantic types inferred → constraints mined →
  calibrated baseline monitors running. All of this works without a single declaration, because
  calibration draws on priors, mined constraints and sibling assets rather than on business context
  ([08 §4.4](08-ai-ml-capabilities.md)). We should be **more precise than Anomalo on day one**, not
  merely comparable, because they ship uncalibrated and we do not.
- **Inverted onboarding.** Never present an empty form. Present a claim: *"We believe this is one
  row per account per business day — correct?"* One click confirms. Propose-and-confirm is not a
  nicety in the onboarding path; it **is** the onboarding path.
- **The Day-One Report.** After 24 hours, generate an artefact the evaluator can take to their
  manager: what we found, what is undeclared, which relationships we suspect, what a week of
  declarations would unlock. That artefact is the moment the POC becomes a project.
- **Declaration ROI made visible.** Every declaration screen states what it will buy —
  *"declaring the grain of these six Tier-1 datasets enables 24 controls"* (`FR-MET-105`). The
  semantic layer must feel like leverage, never like paperwork.

**Why it is asymmetric.** Anomalo and Monte Carlo cannot follow us up the curve: they have no
semantic layer to grow into, so their day thirty looks like their day one. We match them at hour
one and pull away thereafter — which is the only shape of competition where a younger product wins.

**Cost:** it is mostly sequencing, not new scope. **Timeline:** Wave 3 and Wave 6 must land in a
state where this demo works end to end. **Effect:** converts G3, and turns G5 into a non-issue.

---

## 4. Gap by gap

| Gap | Do this | Do **not** do this |
|---|---|---|
| **G1 References** | Make publication rights a **contractual term**, not a favour. Price the first three deployments to buy the right to name them with numbers. Add the auditor attestation (Unlock 1) and OSS adoption metrics as reference substitutes. | Wait for organic references. Give free POCs without publication rights. |
| **G2 Lineage scanners** | Integrate Manta, Octopai, erwin and Solidatus output as declared lineage on day one. Then build only the five scanners banks actually need: stored procedures (T-SQL, PL/SQL, DB2 SQL PL), PowerCenter, DataStage, SSIS, and one BI semantic layer. **Reframe the gap:** a scanner is what you need when only code can tell you the lineage; a business owner can describe a mainframe job in one sentence, and our Journeys capture what no scanner reaches. | Chase fifty scanners. That is a permanent tax paid to every technology that has ever existed. |
| **G3 Time to value** | Unlock 3. Treat `NFR-OPS-002` as a hard release gate with a stopwatch, re-measured every release. | Ask for declarations before showing value. |
| **G4 Catalog UX** | Concede in the first meeting, before being asked. Build **write-back** so quality state appears inside Alation, Collibra, Atlan and Purview — their UI becomes our distribution. | Build a catalog. It is a decade of work for a commoditised outcome. |
| **G5 Detector maturity** | Champion/challenger means any detector — including open-source ones — can be adopted without changing the product. Compete on the **calibration layer above** the detector, where nobody else is. | Try to out-tune Anomalo on unsupervised detection. |
| **G6 Recon operations** | Ship DQ-grade recon: matching, tolerance, break classification, ageing, certificate. Say plainly that Duco is deeper on ops. Win on *"recon is one of twelve controls feeding this return, sharing one evidence trail."* | Claim recon-vendor parity. It invites a comparison we lose. |
| **G7 Procurement safety** | Unlock 2, plus SOC 2 and ISO 27001 early — they are gates, not differentiators, and being blocked at security review is the most avoidable loss there is. | Compete on brand. |

---

## 5. The moats, honestly rated

A moat is only worth planning around if we know how long it lasts. Rating our five differentiators
by **how long before a well-resourced competitor could match them**:

| Differentiator | Who could copy it | Time to copy | Why |
|---|---|---|---|
| **Evidence ledger + deterministic replay** | Anyone, in principle | **24–36 months** | Requires snapshot capture on every read, content-addressed rules, versioned reference data and an append-only store — designed in from commit one. Monte Carlo has six years of mutable results tables; retrofitting means rewriting the core. **Our deepest moat.** |
| **Engine-neutral IR** | Ataccama, Informatica | **18–30 months** | Nobody else has an IR at all. Retrofitting one under an existing rule engine is a rewrite, not a feature. |
| **Declarations compile into controls** | **Ataccama**, possibly Alation | **12–24 months** | Needs a semantic layer *and* an execution engine in one product. Catalogs have the first, DQ tools the second. Ataccama has both and is the real risk here. |
| **Calibrated alerting (conformal + FDR)** | Monte Carlo, Anomalo | **9–18 months** | Technically imitable. What holds them back is positioning, not engineering: publishing an alarm rate means admitting the current one. **Our shallowest moat — and therefore the one to establish as the category standard fastest, so that arriving second looks like following.** |
| **Financial message standards + mainframe** | Anyone willing to do dull work | **12–24 months** | Not clever, just unglamorous. Most competitors will not do it, which is exactly why it holds. |

**What this rating implies.** Lead with evidence and the IR, because they are the durable ones. Push
calibration into public discourse **now** — the benchmark, the paper, the term "risk-controlled
alerting" — so that when a competitor ships it, they are visibly implementing our idea. And watch
Ataccama more carefully than the noisier names.

---

## 6. Sequenced plan

### Months 0–6 — earn the right to be evaluated
- Zero-declaration day one working end to end (Unlock 3) — **the highest-leverage engineering item in this document**.
- DQ-Bench and FinDQ-Bench published with baseline configurations.
- Auditor engagement commissioned (Unlock 1).
- Three design partners signed **with publication rights in the contract**.
- CIDR-style vision paper submitted: establishes "risk-controlled data quality alerting" as our term.
- Catalog write-back to Alation and Collibra — cheap, and it converts the strongest incumbents into distribution.

### Months 6–12 — convert evaluation into proof
- Blind shadow bake-offs running at all three partners; publish the aggregate, including losses.
- Auditor attestation published, failures included.
- Evidence + deterministic replay demonstrable in a five-minute demo. **This is the demo.**
- Sub-ledger↔GL reconciliation live at one partner, end to end with a certificate.
- SOC 2 Type II started.
- First two lineage scanners (stored procedures, PowerCenter).

### Months 12–24 — turn proof into position
- Three named references with published numbers.
- JDIQ paper accepted; benchmark handed to an advisory board.
- Remaining scanners; trust propagation in production; second domain pack.
- Partner channel with the audit firm producing pipeline.

---

## 7. The traps we set

Competitive positions worth engineering deliberately, because they cost us little and cost a
competitor a great deal to answer:

| Trap | How it works |
|---|---|
| **The replay demo** | Ask any competitor to show the evidence for one control on one day last quarter and replay it. There is no good answer, and the question is entirely reasonable. |
| **The alarm-rate question** | *"How many of last week's alerts were false, and can you set that number?"* Answering honestly damages them; answering vaguely damages them differently. |
| **The declined bake-off** | Offering a blind evaluation costs us nothing. Declining costs them credibility with the buyer who heard the offer. |
| **Published failures** | Publishing our own negative results makes competitor marketing look like marketing. It is very hard to respond to without doing the same. |
| **Conceding the catalog first** | Volunteering what we do not do, unprompted, makes every subsequent claim more believable — and puts the incumbent in the position of over-claiming. |
| **Pricing by control, not volume** | Their meter punishes the coverage their own buyer wants. We can raise this as a customer-interest point rather than a price attack. |

---

## 8. Response playbook

| If this happens | Then |
|---|---|
| **Solidatus adds control execution** | The scenario we most fear. Compete on calibration, reconciliation and the IR, which are further from their model. Accelerate the auditor reference so that "evidences outcomes, not topology" is already established as the standard. |
| **Monte Carlo ships calibration** | Good for the category, and we still hold evidence, reconciliation, breadth and the semantic layer. Ensure the public record shows the idea was ours: publish first, name it, benchmark it. |
| **Ataccama ships declaration-derived controls** | The most credible fast-follow. Differentiate on calibration, evidence, air-gap and banking depth; compete hard on time to value where they are heavier. |
| **Alation's Data Quality Agent gets good** | Lean harder into write-back and partnership. Their agent cannot reach a SWIFT feed or a GL reconciliation; make that the comparison. |
| **A platform ships free evidence** | Unlikely — it is cross-system by nature. If it happens, move up to attestation, workflow and the regulatory catalogue. |
| **We fail a published benchmark criterion** | Publish it, fix it, publish the fix. Credibility survives a miss; it does not survive concealment. |

---

## 9. Are we winning?

Leading indicators, checked quarterly. Vanity metrics deliberately excluded.

| Measure | Target by month 12 | What it tells us |
|---|---|---|
| Time from connect to first proposed control | ≤ 30 min unattended | G3 closed |
| Blind shadow precision vs. incumbent | ≥ 2× | The core claim holds in reality |
| Bake-offs offered / accepted | ≥ 6 / ≥ 3 | The trap is working; declines are also a result |
| Named references with published numbers | 3 | G1 closing |
| Auditor attestation published | Yes | G7 converted |
| Deals lost to "no references" | Declining quarter on quarter | The unlocks are landing |
| Deals lost on catalog or MDM scope | Near zero | We are qualifying correctly, not losing on scope we conceded |
| Competitor marketing adopting "calibrated" or "FDR" | Any occurrence | We set the category vocabulary — a win, not a threat |

---

## 10. The one-sentence strategy

> **Build from our own thesis, and change the yardstick.**
> Make *"can you prove it, and will you be measured?"* the question every buyer asks — because we
> are the only ones with an answer, and because every incumbent has more to lose from that question
> than we do.

The competitive tactics in this document are how we get heard. The ten originals in §0.1 are why
we deserve to be. Neither works without the other, and if the two ever conflict, §0 wins.

---

<div align="center">
<img src="../assets/prama-mark.svg" width="30" alt=""/><br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.<br/>
See <a href="../../LICENSE">LICENSE</a> and <a href="../../NOTICE">NOTICE</a>. Third-party names and marks are the property of their respective owners.</sub>
</div>
