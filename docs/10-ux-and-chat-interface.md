<img src="assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>


---
# 10 — User Experience & the Conversational Interface

Requirements: [`FR-UIX`](04-requirements-functional.md#p-user-interface-fr-uix),
[`FR-CHT`](04-requirements-functional.md#q-conversational-interface-fr-cht).
Personas: [03 §7](03-business-semantic-layer.md#7-personas--who-this-is-for).

---

## As built

The console is server-rendered Jinja on FastAPI with Bootstrap 5 and jQuery,
everything vendored, no build step: `prama.web`. Sign-in, the estate map,
declaration and relationship editing, the control workbench, triage drill-down,
the break workbench, attestation, and the preview/backtest surface all exist.

The shell speaks **Maya's design language**, so the two products read as one family on the same
desk: a fixed gradient top bar whose menus (Estate, Controls, Assurance, Admin, Help) open into
mega-menu panels of titled columns, defined as data in `prama.web.rendering.MENU`; Maya's brand
block, search box, queue, theme and user menus; Maya's cards, forms and footer
(`static/css/shell.css`); and exactly Maya's four themes under Maya's names — Crimson (the
default), Dark, Blue and Green. A fresh installation seeds an `admin` account with the password
`prama-dev-admin`, bannered until changed and refused outside development
(`prama.security.bootstrap`).

Colour is **derived, not picked**. `prama.report.themes` computes WCAG 2.2 AA
contrast against three grounds — surface, body and raised — and
`scripts/generate_themes.py` emits the variants; a hand-chosen colour that fails
contrast cannot get in. axe-core runs in a real Chrome over the console
(`tests/web/test_axe.py`), currently twenty-six checks with **zero critical
findings**.

The chat assistant is here and is deliberately unable to change anything — see
`docs/08`.

**Not built, and it is not code:** every number in §8. Twelve participants per
persona, ≥90% unaided task success, ≤3 min to a reviewed control — those are a
study. And **screen-reader testing has not been done**: an automated pass is not
evidence of it, and ticking that line would claim an accessibility guarantee to
the people who most depend on it being true. The estate map **has now been measured**, and misses its target by more than an
order of magnitude: 500 nodes take **5.3 s** to first draw, 2,000 take **15.5 s**, and 4,000 do not
draw at all within 60 s — the browser's main thread is blocked throughout, so the
page is unresponsive rather than merely slow. Pan and zoom do hold 60 fps, but
only once the map has appeared. See §1 and `tests/web/test_estate_map_scale.py`.

---

## 1. Design principles

| # | Principle | Test of compliance |
|---|---|---|
| U1 | **Business language first** | No default screen shows a physical schema, table name, or SQL. Physical detail is ≤ 2 clicks away, never in the way. |
| U2 | **Every technical artefact has a business rendering** | Every rule has a generated English sentence; every break has a business explanation; every score decomposes into named dimensions. |
| U3 | **Show the reasoning** | Any number can be expanded to the evidence that produced it. "Why?" is always answerable in-product. |
| U4 | **Uncertainty is visible** | Staleness, sampling, and suspended guarantees are rendered, never hidden. Unverified Grey is a real state. |
| U5 | **No dead ends** | Every screen a business user can reach offers an action they are permitted to take — approve, comment, assign, ask, request access. |
| U6 | **Progressive disclosure and progressive formalisation** | The product is useful at declaration stage 0 and better at every subsequent stage ([03 §3](03-business-semantic-layer.md#3-progressive-formalisation--the-adoption-contract)). |
| U7 | **Two surfaces, one truth** | Anything doable in the UI is doable in PQL/API/chat, and vice versa. The "show me the PQL" toggle is always present. |
| U8 | **Speed is a feature** | p95 ≤ 300 ms navigation; live preview in seconds. Triage is keyboard-first. |
| U9 | **Accessible by default** | WCAG 2.2 AA, keyboard-complete, colour never the sole carrier of meaning. |

---

## 2. Information architecture

```
Home (role-adaptive)
├── Estate                     ← the map: domains → journeys → datasets → relationships
│   ├── Dataset                  overview · attributes · profile · controls · incidents ·
│   │                            relationships · lineage · evidence · settings
│   ├── Relationship             definition · derived controls · health · breaks
│   ├── Journey                  end-to-end health, latency, SLA, RCA path
│   └── Concept model            concepts, properties, mappings, conflicts
├── Controls
│   ├── Studio                   no-code builder · PQL editor · backtest · cost
│   ├── Proposals                AI-induced & declaration-derived candidates awaiting review
│   ├── Coverage                 what is unprotected, ranked by risk
│   └── Approvals                maker–checker queue
├── Monitoring                   monitor fleet, calibration status, alert budgets, precision
├── Incidents                    triage workspace · investigation · impact · resolution
├── Reconciliation               recon inventory · break workbench · certificates
├── Scorecards                   executive · domain · dataset · journey · trend · attestation
├── Reports                      scheduled & ad-hoc, distribution, exports
├── Connections                  sources, health, read policy, budgets, discovery browser
├── Assistant                    full-screen conversational workspace
└── Admin                        users, roles, policies, packs, audit, platform health
```

---

## 3. The Estate Map — the landing surface

The first screen is not a list of failing tests. It is **the business's own picture of its data**.

- **Nodes** are domains, journeys, and datasets, labelled in business language, sized by materiality,
  coloured by health, and shaded by staleness.
- **Edges** are declared business relationships, styled by type (`reconciles-with` is visually
  distinct from `derives-from`), and coloured by the health of the control they generate.
- **Direct manipulation:** drag between two datasets to declare a relationship; a typed panel opens,
  keys are proposed from overlap statistics, and the derived controls are previewed before saving.
- **Overlays:** health, coverage, criticality, ownership, freshness, metadata maturity,
  regulatory obligation, trust propagation (showing where a green asset inherits a red ancestor).
- **Level-of-detail rendering** aggregates to domains when zoomed out and reveals attributes when
  zoomed in. `NFR-SCA-011` asks for 50,000 nodes at 60 fps pan/zoom. **Measured**
  (`tests/web/estate-map-scale.json`): 500 nodes draw in 5.3 s, 2,000 in 15.5 s, and 4,000 do not
  draw within 60 s. Pan and zoom hold 60 fps once the map exists — the frame rate was never the
  problem. What binds is `relax()` in `estate-map.js`: an all-pairs O(n²) force loop, run 60 times,
  **synchronously before Sigma is constructed**, so nothing is on screen and nothing responds until
  it finishes. Its own comment says Barnes-Hut would be the right answer above a few thousand
  nodes; the measurement puts the cliff below four thousand. The target stands and the
  implementation is nowhere near it.
- **The map is also the empty state:** a new tenant sees a canvas with "declare your first domain"
  and an import path from an existing catalog or spreadsheet.

**Why this is the landing surface:** it is the only screen in the category that a CDO can put on a
slide. It reframes the product from *"a testing tool"* to *"the picture of our data estate"*, which
is what the buyer actually wants to own.

---

## 4. Key workflows

### 4.1 Declare a dataset (business owner, target ≤ 5 min — `NFR-OPS-003`)
A single progressive form, not a wizard maze: name → owner → domain & criticality → *"what does one
row represent?"* (grain, in plain words, with examples) → *"when does it arrive and how much?"* →
optional binding. Every field explains what it will enable ("declaring the grain will create a
uniqueness control"). Save produces immediate value: the dataset appears on the map, controls are
proposed, and the coverage score moves.

### 4.2 Declare a relationship (data architect)
Draw it on the map or use the form. Choose a type from plain-language options
(*"these two should agree"* → `RECONCILES_WITH`; *"this one is calculated from that one"* →
`DERIVES_FROM`). Prama proposes join keys with overlap evidence ("account_id matches for 99.6% of
rows"), the user sets tolerance in business terms ("within €1"), and the derived controls are shown
with a backtest before approval.

### 4.3 Author a control (three routes, one result)
| Route | Who | Flow |
|---|---|---|
| **No-code builder** | Steward, business analyst | Pick a dataset/attribute → pick an assertion from a plain-language list → set the threshold with a live histogram showing where it falls → live preview of matching/failing rows → save |
| **PQL editor** | Engineer, architect | Type with autocomplete over the semantic layer; inline errors, cost estimate, backtest, plain-language rendering pane |
| **Chat** | Anyone | Describe it; get PQL + backtest + estimated alert volume; refine in prose; approve |

All three converge on the same review screen: the PQL, the English rendering, the backtest, the
estimated alert volume, the cost, and the approval workflow.

#### 4.3.1 The backtest, and the three ways it lies

The backtest is the number an author actually decides on: not "is this control sound" but "how
often will it fire, and can we live with that". It is also the number easiest to make flattering,
in three specific ways — each of which the implementation is built to prevent rather than to warn
about.

**A day with no rows in it is not a quiet day.** A control over an empty slice violates nothing and
would be judged a pass. Averaged into thirty days, ten empty days cut the apparent alert rate by a
third — and the empty days are usually a retention boundary, which means the backtest is most
wrong precisely where the author trusts it most. Empty days are counted and reported separately,
excluded from the rate rather than folded into it, and the count of excluded days is stated beside
the answer.

**A day that could not be read is not a quiet day either.** A source that refuses is a gap in the
evidence, not evidence of calm. Errored days are excluded from the rate and named; a backtest in
which nothing could be evaluated reports *no rate at all* rather than zero, because zero is the
number that gets a control approved on the strength of an outage.

**An incomplete screen makes the whole count a floor.** When the compiled SQL applies a necessary
condition rather than the exact test, its violation count is a lower bound — so a backtest
containing any screened day reports "at least *n* alerts" and says why. The same applies when a
scan ceiling bound the query: a floor presented as a total is the single most dangerous number this
system can emit.

Two smaller honesty rules follow. A rate quoted from fewer than five evaluated days says so, since
one noisy day dominates the answer. And the studio refuses to guess which column carries the
business date: a backtest of the wrong slices is indistinguishable, on screen, from a backtest of
the right ones.

Each day streams as its own event over SSE, so the table fills as the answer is computed rather
than after it. A stream that stops mid-way says so and states how many days it managed — "the
result so far" and "the result" are different claims, and a progressive display that cannot tell
them apart is worse than a spinner.

**A preview is not evidence.** Running a control from the studio writes nothing to the ledger, does
not count towards coverage, and does not appear on a scorecard. It runs an unapproved control,
frequently over a bounded scan; evidence a regulator may read has to be the record of a control the
estate agreed to, run in full. The two are separate types in separate modules, and the preview
module imports nothing that can persist.

### 4.4 Review proposals
A dedicated queue, designed for speed: each candidate shows the rule, why it was proposed
(data evidence / declaration / document citation / pack), sample violations, what it would have
caught in the last 90 days, expected alert volume, and cost. Actions: **Approve · Approve with edit
· Reject (with reason) · Snooze**. Batch approve for low-risk classes. Every decision trains the
ranker (`FR-IND-008`).

### 4.5 Triage an incident (steward, keyboard-first)
One screen, no tab-hunting: what failed and by how much; the trend with the anomaly marked and the
baseline shaded; what changed upstream; ranked RCA hypotheses each with evidence and confirm/reject;
downstream impact including affected reports and returns; sample failing records (masked per policy);
and one-click actions — assign, comment, create ticket, mark false positive, accept new normal,
suppress with expiry, open remediation. `j/k` to move through the queue, `1–5` to disposition.

### 4.6 Work a reconciliation break
Side-by-side record comparison with differing fields highlighted; break classification (proposed by
the learned classifier, confirmed by the human); ageing and materiality; bulk actions on
same-cause groups; commentary and evidence attachment; escalation; and a running certificate
showing matched/unmatched counts and values with sign-off state.

### 4.7 Read a scorecard, then prove it
Executive view: domains as tiles with score, trend, and the top three drivers of movement, in
business language. Every tile drills to dimensions → controls → executions → evidence records →
(policy permitting) failing rows. The chain from a board-level number to a signed evidence record
is never broken — that chain *is* the product.

### 4.8 Attest
A control owner sees their controls for the period, their outcomes, exceptions with justifications,
and open issues, then signs electronically. The result is an immutable attestation artefact bearing
the [attestation seal](brand.md#3-the-mark--the-pramāṇa-prism), exportable for the regulator.

---

## 5. Visual language

- **Colour = meaning, always labelled.** The six dimension hues from
  [brand.md](brand.md#4-palette) identify the same six dimensions everywhere. Status uses the
  spectrum ends (teal pass, amber warning, red fail) and **Unverified Grey exclusively for
  stale/not-yet-examined**.
- **Charts** follow one system: time series with baseline bands and marked anomalies; distribution
  comparisons as overlaid densities with the divergence stated; scorecards as small multiples;
  lineage and estate as force-directed graphs with orthogonal routing for declared relationships.
- **Density with discipline.** Operators get compact tables; executives get generous space.
  Both come from the same components with a density setting, not from separate designs.
- **Empty and loading states teach.** Every empty state says what to do next and why it helps.
- **Numbers carry provenance.** Any figure can reveal its as-of time, sampling basis, and evidence
  link on hover.

---

## 6. The conversational interface

### 6.1 Where it lives

1. **Contextual panel** — a side panel on every screen, seeded with that screen's context (the
   dataset you are viewing, the incident you are triaging, the selection you have made).
2. **Full workspace** — a standalone surface for extended investigation, with artefacts (tables,
   charts, generated PQL) rendered inline and pinnable into a report.
3. **Slack / Teams** — the same agent, same identity, same permissions, for people who live there.
4. **MCP server** — the same tools exposed to the customer's own agents and IDEs (`FR-EXT-008`).

### 6.2 What it can do

| Intent | Example | Behaviour |
|---|---|---|
| **Ask** | *"Which Tier-1 datasets in Credit Risk have no completeness control?"* | Queries the API, answers with a table, links every row |
| **Explain** | *"Why is the FRTB journey amber?"* | Walks the journey, names the failing control, shows the trend, cites evidence |
| **Author** | *"Positions notional should never be null for active trades, critical."* | Emits PQL, shows the English rendering, backtests, estimates alert volume, requests approval |
| **Declare** | *"The sub-ledger reconciles with the GL on account and cost centre to within €1, one day behind."* | Creates a relationship proposal + derived reconciliation control, previewed before saving |
| **Investigate** | *"Why did the positions feed fail last night?"* | Ranked hypotheses with evidence, upstream changes, lineage path, affected consumers |
| **Operate** | *"Re-examine the Treasury domain now."* | Shows cost estimate, asks confirmation, runs, reports progress |
| **Report** | *"Draft the Q3 attestation summary for Credit Risk."* | Generates the artefact; every figure traceable; marked as draft until reviewed |
| **Learn** | *"What does 'exposure' mean in this dataset and who owns it?"* | Answers from the semantic layer, with the definition's author and date |

### 6.3 The safety contract (non-negotiable)

1. **The agent is an API client running as you.** No service account, no elevation. If you cannot
   see a dataset, neither can the agent when you ask (`FR-CHT-002`).
2. **Mutations are proposals.** Every change renders as a diff of the exact PQL/config, with
   backtest and cost, and enters the standard approval workflow. There is no path from a sentence
   to production without a human approving a visible artefact (`FR-CHT-004`).
3. **Grounding or refusal.** Every factual claim links to the object or query behind it. Where
   grounding is unavailable the agent says so and offers to escalate to a named owner — it does not
   speculate (`FR-CHT-005`, `FR-CHT-017`).
4. **Data is untrusted input.** Column comments, document text, and sampled rows can contain
   adversarial instructions; the agent may never act on instructions found in data. Enforced by
   tool allow-lists, output-schema validation, and an adversarial regression corpus run each release
   (`FR-CHT-011`, `NFR-SEC-010`).
5. **Classification-aware.** Masked-class values never enter a prompt; nothing sensitive leaves the
   trust boundary; air-gapped deployments run a local model (`FR-CHT-013`, `FR-CHT-010`).
6. **Fully audited.** Every turn, tool call, and proposal is logged with the same rigour as a UI
   action, and transcripts are exportable and retention-governed (`FR-CHT-012`).
7. **Budgeted.** Per-tenant and per-user token budgets, with cost visible (`FR-CHT-014`).

### 6.4 Why chat is not a gimmick here

Three concrete, measurable reasons:

- **It collapses the authoring bottleneck.** Median time to a reviewed control drops from tens of
  minutes to under three (`S4`, `NFR-USA-002`) — which is the difference between 10% and 80% control
  coverage across a 5,000-table estate (`S5`).
- **It is the accessibility ramp for the accountable persona.** A Head of Credit Risk Data will not
  learn a rule syntax, but will type a sentence. Chat is how the *owner* of a control becomes its
  *author* — which is itself an audit improvement.
- **It has the right substrate.** Conversational interfaces over enterprise data fail when there is
  no semantic layer; with a business glossary, semantic model, and quality monitoring in place,
  accuracy rises dramatically. Prama's semantic layer ([03](03-business-semantic-layer.md)) is
  exactly that substrate, which is why our chat can be accurate where a bolt-on cannot.

### 6.5 Failure behaviour

The assistant must be excellent at not knowing. It distinguishes: *I don't have permission*
(offers a request), *the data isn't there* (offers to declare it), *the finding is stale* (offers to
re-examine), *this is ambiguous* (asks one clarifying question, not five), and *this needs a human*
(names the owner and offers to send context).

---

## 7. Reporting surfaces

Beyond the console: scheduled PDF/XLSX/HTML packs with per-recipient scoping and redaction;
embeddable widgets and quality badges for catalogs, BI tools, and internal portals
(`FR-UIX-014`); an auditor-facing read-only evidence browser requiring no source access
(`NFR-CMP-007`); and a public-style status view a data producer can share with their consumers.

---

## 8. Measuring the UX

We hold the interface to numbers, not opinions (`NFR-USA-001…008`):
≥ 90% unaided task success for the eight core business tasks across ≥ 12 participants per persona;
≤ 3 min median to a reviewed control; ≤ 5 min to a first declared dataset by an untrained business
user; ≤ 30 min from connecting a source to first proposed controls. These are release gates, and
they are re-measured every major version.

---

<div align="center">
<img src="assets/prama-mark.svg" width="30" alt=""/><br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.<br/>
See <a href="../LICENSE">LICENSE</a> and <a href="../NOTICE">NOTICE</a>. Third-party names and marks are the property of their respective owners.</sub>
</div>
