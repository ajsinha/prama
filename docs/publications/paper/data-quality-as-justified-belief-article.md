<img src="../../assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

> ***pramā*** (Sanskrit **प्रमा**) — *valid knowledge: a cognition that is both true and arrived at
> by a reliable means*. Its companion ***pramāṇa*** (प्रमाण) is *the instrument by which valid
> knowledge is obtained*. Prama is that instrument for an organisation's data — it does not decide
> what is true, it is how a belief about data becomes **justified**.
>
> **Declare it. Prove it. Trust it.**


---

# Data Quality as Justified Belief

### Derived controls, deterministic verdicts, and evidence that verifies without its author

> **What carries each claim.** This is the long-form companion to the paper
> [`data-quality-as-justified-belief.tex`](data-quality-as-justified-belief.tex) ([PDF](data-quality-as-justified-belief.pdf)). The system it was built against is **Prama** 0.1.0. Where
> a section says what a data quality system *should* do, it then says what Prama actually does. Often
> that is less, sometimes it is different, and the differences are marked rather than smoothed over. The
> paper's claims register has seventy-five rows: **fifty-three run** (a named test exercises them),
> **eleven run in part**, **five are mathematics the code does not execute**, and **six are not built**.
> The negative results are in here too: value lineage cannot see a defect that acts through a join (and
> the population edge that now repairs it), and on its own benchmark Prama's declared path finds 10 of 28
> planted defects, none in the relational, temporal or semantic families.

---

There is a question every data owner in a bank is eventually asked, usually by somebody who is not
smiling:

**Why did you believe this data was right?**

Not *was* it right. Why did you *believe* it. The regulatory return went out, the books closed, the
risk number went to the board. Afterwards someone wants to know what that belief rested on.

The honest answer, in most organisations, is some mix of: somebody wrote a SQL check once; it was green;
there is a log somewhere. This article argues that each of those three things is a place where a belief
can be held for no good reason while looking as though it has one, and describes a system built to close
all three.

The standard I am using is an old one. A belief counts as knowledge when it is true *and justified*. A true
belief held for a bad reason is luck. Data quality tooling mostly produces luck with a dashboard.

---

## Three places a belief is held without reason

### 1. The control is typed in

Somebody writes `SELECT count(*) FROM trades WHERE isin IS NULL`. That query encodes a belief about the
dataset — the ISIN is mandatory — but the belief is recorded nowhere except inside the query.

When the dataset's grain changes, nothing connects that change to the query. When an auditor asks why a
critical data element has no accuracy check, the answer is that nobody wrote one, and nothing ever
counted the absence.

A control written by hand is a *second statement* of a rule whose first statement lives in somebody's
head, or a data dictionary, or a regulatory instruction. Two statements of one rule diverge, and they
diverge silently, because only one of them is executed.

### 2. The verdict is decided by something that cannot justify it

A control "passes" because a SQL screen returned zero rows — when the screen could only check the *shape*
of an identifier, not its check digit. A freshness control "passes" because a row count was positive. And,
increasingly, someone asks a language model whether a column "looks right".

In each case a verdict is issued by a mechanism that is not in a position to issue it.

### 3. The evidence certifies itself

The execution log lives in the same database, under the same administrator, as the system whose
correctness it records. A record that only the software that wrote it can verify is testimony, not
evidence.

---

## The thesis, as three constraints

Turn "justified" into engineering and you get three rules, each checkable:

1. **A control derives from a declaration.** An owner says, in business terms, what the data means. The
   controls are *computed* from that, by a deterministic function, and each one can say which declaration
   produced it. What nobody declared is measured, not hidden.
2. **A verdict comes from a deterministic engine.** The same control means the same thing on every
   database it runs on. Where the engine cannot decide, the verdict says so. No model output ever decides
   whether data passed.
3. **Evidence verifies without its author.** The record of every verdict can be checked by a short
   program that shares no code with the system that produced it.

That is what the slogan means. *Declare it. Prove it. Trust it.*

---

## Declare it: controls derived from declarations

### What an owner declares

An owner describes a dataset the way they would describe it to a new colleague:

- **Grain:** "one row per trade, identified by trade id".
- **Rhythm:** "arrives by 06:30 on business days, about 5,000 rows".
- **Attributes:** this column is mandatory; that one is an ISIN; this is a monetary amount whose currency
  is in that column; this one is a *critical data element* for FRTB.
- **Value domains:** currency is in ISO 4217; status is one of four codes.
- **Relationships** to other datasets — thirteen kinds, including *references*, *reconciles-with*,
  *derives-from*, *mirrors* and *same-entity-as*.

Nobody writes SQL.

### What Prama derives

A function the code calls **Γ** turns declarations into controls:

| Declaration | Control |
|---|---|
| Grain | `HAS UNIQUE KEY` over it, and not-null on each member |
| Rhythm | a freshness control with the right calendar, and a volume control |
| Mandatory attribute | `IS NOT NULL` |
| Semantic type | `IS VALID 'isin'`, naming ISO 6166 |
| Value domain | `IN CODELIST 'iso4217'`, or a range |
| Monetary amount | a currency-code check on the column beside it |
| *references* relationship | `REFERENCES`, a correlated `EXISTS` |
| *reconciles-with* relationship | a reconciliation, with keys, tolerance and offset |

Γ has four properties that matter, and each has a test behind it:

- **It is deterministic.** Regenerate from an unchanged declaration and nothing changes — same identities,
  same hashes.
- **Identity is separate from content.** A control's *identity* comes from where it came from (which
  declaration, which rule, which column). Its *hash* comes from its text. Edit a threshold and you get the
  same control with a new hash: it is updated, not orphaned and replaced.
- **Every control says why it exists.** Provenance records the declaration, the rule, the person who
  declared it and when. "Why does this control exist?" has an answer that is data, not recollection.
- **It refuses rather than omits.** A grain naming a column that does not exist is *reported*, not
  silently dropped. A reconciliation with no tolerance is refused with the reason. Every one of the thirteen
  relationship kinds yields either an output or a refusal.

One honest caveat. For several relationship kinds, the code emits *fewer* control families than the design
documents list. *parent-of* produces an orphan-node check and no cycle detection; roll-forward and parity
checks exist as comparison specifications for the reconciliation engine, not yet as PQL you can write
yourself. The paper's table puts the declared and the emitted side by side.

### A worked example

Case study 1 is a trading book in SQLite: six datasets, 5,000 trades, nine planted defects. When I ran it,
Γ produced **59 controls**. It also reported nine declarations that produced *nothing*, each with a reason.
Six declare when a dataset arrives but name no column that records arrival, so there is nothing to measure
freshness on; three name a validator Prama does not have: *"Prama has no validator or code list called
'currency'"*.

The 59 controls gave 44 passes, 5 failures and 10 "not established". The five failures are exactly the
planted defects that a single-dataset declaration *can* see:

- 12 duplicated positions (the grain forbids them),
- 60 missing notionals (a mandatory CDE),
- 7 negative quantities (a declared range),
- 15 currencies of `'EURO'` (a code list — reported twice, as validity and as consistency).

The four it did not find are each named in the run's output, with the reason:

- an ISIN checksum (a screen — more below),
- an orphan instrument and a ledger adjustment (both need a *relationship*, which this study does not
  declare),
- and a settlement date before the trade date.

That last one is the interesting one. No control exists for it because **nothing in the declaration says
how the two dates relate**. That is a gap in the declaration, not in Γ, and the study leaves it in on
purpose. Derivation can only be as good as what was declared — which is also the point: the gap is
*visible*.

### Coverage, and the number that flatters

"Percentage of columns with a control" is a flattering number. One `IS NOT NULL` makes a column
"covered" while its format, domain and accuracy go unchecked.

Prama measures coverage per **(attribute, dimension)** pair instead, and only over dimensions the
declaration makes meaningful: validity only where a type or domain is declared, accuracy only for a CDE,
completeness except where an attribute is optional. It reports both numbers side by side — the honest one
and the flattering one — and every uncovered pair comes with what would close it.

A small piece of logic falls out of this, and it has a test:

> **A dataset cannot vouch for its own accuracy.** Accuracy means *agrees with something else*. The only
> controls that satisfy it compare an attribute with something outside its row, and Γ produces those only
> from *relationships*.

So no amount of careful description of one dataset covers its CDEs' accuracy. You have to draw a line to
another dataset. That is why relationships carry the most weight in Prama's estate-maturity score. (The
roadmap reports 82% of pairs and 71% of CDE pairs from the dataset declaration alone, and 100% of both once
relationships are added. The test asserts the weaker statement — at least 95% of CDE pairs and 80% overall
after relationships — and I did not reproduce the 82/71 figures.)

### Proposals, and who switches a control on

Every candidate control — from a declaration, a document, an import, mining, labelled examples, or a
language model — enters as a **proposal**. Proposals are the only way a control gets into the estate.

Origins are ranked: declaration, then document, import, mining, example, and model induction last. When
two origins reach the same control, they merge into one proposal, held by the stronger origin and marked
*corroborated*. A rejected proposal is not offered again unless the evidence changes materially. Tier-1
datasets need a second person.

The code has a flag saying a *declared* control "may run without review" — unless its backtest fails more
than 20% of rows, because a declaration that would drown the queue is probably wrong about the data. Reading
the code closely, that flag is only *counted*. The one activation path requires an `approved_by` identity
and writes it into provenance. In practice a person switches on every control, including declared ones.
I record the flag as overstating what happens, rather than the other way round.

### Freshness, and the column it needs

A declared rhythm says when data is due. It does not say how anybody would know it arrived, and a plain table
keeps its rows, not when they were loaded. Γ used to generate a freshness control anyway, which **could never
reach a verdict**; the repository pinned that as a strict expected failure until it was fixed.

The fix makes the missing fact declarable. A rhythm names its **arrival column** (a load timestamp), and Γ
generates `CHECK t.loaded_at IS FRESH WITHIN 30 MINUTES OF '06:30' CALENDAR 'TARGET2'`:

- **What is measured.** The newest arrival.
- **What is judged.** The most recent business day whose deadline has passed. It passes if data arrived after
  the previous day's deadline.
- **Replay.** The instant of evaluation is recorded as a metric, so a replay reaches the same verdict.
- **A rhythm without an arrival column** generates no control, and says what to declare instead.

Case study 1's tables declare none, so it now prints that reason rather than a control that can never be red.

---

## Prove it: one language, and a verdict that can say "not known"

### One plan, fingerprinted

Controls are written in **PQL**:

```pql
CHECK trades.notional IS NOT NULL SEVERITY critical DIMENSION completeness
CHECK trades.isin IS VALID 'isin'
CHECK trades HAS UNIQUE KEY (trade_id)
CHECK trades.ccy IN CODELIST 'iso4217'
      TREAT UNKNOWN AS PASS BECAUSE 'optional on internal moves'
```

Each control lowers to an engine-neutral **plan**, and the plan's identity is a SHA-256 hash of its
*meaning*: what it asserts, over what scope, with what threshold and unknown policy — and including the
contents of any code list it names and the implementation of any validator it calls. Description, severity
and provenance are not part of it.

So: change the list of allowed currencies and every control that uses it gets a new fingerprint. Edit the
check-digit routine in a validator and the control changes identity, rather than silently changing what
last month's evidence meant. (That code lists and validators are *inside* the hash is tested. That
description and provenance are *outside* it is true by inspection and not tested.)

### Five verdicts, not two

A verdict is one of **pass, fail, indeterminate, error, skipped**. The rule for *indeterminate* is simple and
strict: if the metric the threshold needs is missing, or nothing was scanned, or a rate's denominator is
zero, the answer is indeterminate — never pass.

> An empty scope is not a clean scope.

The one exception is a row-count control, which is a claim *about* the count: on an empty table it fails.

### Unknowns count against you by default

SQL evaluates `amount >= 0` on a null to *unknown*, and a `WHERE` clause drops unknown rows. A check written
as "count the rows where the predicate is false" therefore passes every null, silently.

PQL inverts that. **By default an unknown is a violation.** You can write `TREAT UNKNOWN AS PASS`, but only
with a `BECAUSE` clause saying why. The arithmetic is trivial — the lenient count is never larger than the
strict one — and that is exactly why the strict one is the safe default.

### A screen is not a test

This is the idea in Prama I would most like other tools to copy.

Some validity rules have no faithful SQL. An LEI's check digits are ISO 7064 MOD 97-10 over a
letter-to-number mapping. SQL can check the *shape* — twenty characters, the right alphabet — but not the
arithmetic, portably.

The tempting move is to compile the shape check and call it the control. That control passes every
well-shaped fabricated identifier.

Prama calls the shape check a **screen**: a condition every valid value satisfies, which some invalid values
also satisfy. The logic is one line:

> Every value the screen rejects is genuinely invalid. So the screen's violations are a *subset* of the real
> violations.

Which means:

- If the screen finds violations, **fail** is sound — a subset breaching the threshold means the whole does.
- If the screen finds **zero**, you have learned nothing about the check digits. The only honest verdict is
  **indeterminate**, and Prama reports *"a pass cannot be reported from a screen alone"*.

A fabricated LEI with the right shape and wrong digits passes the screen (zero violations) and fails the
exact validator (one violation); both halves are tested. Across the eight case studies this is the most
frequent "not established" line, including on the column in study 1 where twelve bad ISINs were planted.

> Reporting a screen's silence as a pass is the most expensive lie a data quality tool can tell, because it
> is told about precisely the columns whose correctness SQL cannot express.

The exact validator — the *residual* — runs in Prama's reference interpreter, not as part of a SQL pushdown
run. So on a pure pushdown deployment, checksum columns stay indeterminate until a residual executor is
configured. That is weaker than it should be, and it is the right way round to be weak.

### Same meaning on every engine

Plans compile to **PostgreSQL, DuckDB and SQLite**, and are checked against a fourth evaluator: a reference
interpreter, in Python, that is never given SQL and shares no code with the compiler.

- A **conformance corpus** of 25 cases must give the same verdict and metrics on every engine, with every
  case compared by at least two genuinely different engines. It is built to discriminate: a case where the
  unknown policy changes the count, a duplicate key that counts once, a segment that fails alone, a rate
  judged against the rows actually scanned after a filter.
- A **seeded generator** produces 250 random controls by default and requires every engine to agree on
  each; the set must exercise pass, fail and indeterminate.
- **Refusal is conformance.** Where an engine cannot do something — SQLite has no approximate distinct
  count — the control is refused at compile time with the reason. It never runs a weaker version and
  reports the answer as if it were the same.

DuckDB and SQLite always run; PostgreSQL runs when a connection is configured. I ran the backend suite both
ways, including against a PostgreSQL 16 container: 138 tests, none skipped, all passing.

This is differential testing, not a proof of equivalence. Full equivalence across engines is probably
unattainable for regular-expression flavours, collations and decimals; the response is a portable subset and
refusal at compile time.

Building the case studies found two defects of precisely this "looks right, is wrong" kind:

- `ROUND` **double-rounded on DuckDB**, where a bare `CAST(x AS NUMERIC)` means `DECIMAL(18,3)`. It reported
  131 rows in 3,000 as a cent out when they were not — a false alarm on the control people trust most.
- **An unknown function name compiled straight through to SQL** while the reference interpreter returned
  unknown. The independent check existed. It disagreed silently, because nothing compared the two on that
  input. There is now a function catalogue in which no function can exist without both a lowering and a
  reference implementation.

### Fusion: pay for scans, not controls

A source pays for scans. Controls over the same dataset and scope are fused into one query that computes
every control's metrics in a single pass, and each control gets exactly the answer it would get alone (both
halves tested). The unit suite runs nine controls in three scans; in my run of the soak test, **400 generated
controls ran in 160 scans — 40% of a naive pass**. The test asserts at most half.

### Where PQL stops

Two escape hatches exist, both shaped so the verdict stays with the engine:

- **`CHECK CUSTOM SQL`** — exactly one read-only query, checked at parse time, run only on the engines it
  names. There is deliberately no inline Python.
- **Delegates** — a registered Python class, named in PQL
  (`USING DELEGATE 'acme.settlement_cycle@1'`), that returns *counts* and never a verdict. The control's
  threshold decides. A delegate importing a network, clock or model client is refused *before it is
  imported* (importing runs its top-level code, so a gate that imported it would already have let it out).
  A delegate that is not deterministic on admission probes is refused; a file changed after admission is
  refused; too many rows are refused, not truncated.

Case study 5 is why delegates exist. It plants 23 US trades still booked T+2 after the move to T+1, 9 EU
trades settling on a TARGET2 holiday, and 4 unreadable dates. The obvious column check
`settlement_date >= trade_date` **passes all 36** — every one of them settles after it trades. A bank-owned
delegate that knows each market's cycle and calendar returns 36 violations, and the threshold turns them into
a failure. A second delegate, run on a remote agent inside a payments zone, applies Benford's first-digit test
to a ledger with 350 invented invoices and fails it (MAD 0.0176, above the 0.015 nonconformity band), while
keeping the example rows inside the zone.

The sandbox is a subprocess with CPU and memory limits and one deadline over both of its pipes:
- **A clean environment.** The database DSN and the provider keys are not in it.
- **A network namespace of its own,** where the host allows one.
- **Always, an audit hook** installed before the delegate is imported. It refuses sockets, processes,
  `exec`, `fork` and `ctypes`, and it cannot be removed.

The evidence records which of these applied. Each is tested with a delegate that passes admission and
misbehaves only when asked.

Building those tests found two holes:
- **A sleeping delegate held the host for ever.** The deadline had covered only the reply, and sleeping uses
  no CPU.
- **The admission scan let an evasion through:** `getattr(len.__self__, "__imp" + "ort__")`.

Both are closed. Admission is sandboxed too. The server never imports delegate code: each configured file
is loaded and probed by its own sealed worker, and a delegate that hangs its admission is refused alone. What
remains is that an audit hook is no boundary against native code already loaded.

---

## Trust it: evidence that verifies without its author

### The chain

Every verdict appends an **evidence record**: control and plan identity, snapshot, verdict, metrics, and a
*hash reference* to any sample rows (the rows are not carried; the tests hold the median record under 2 KB).

Each record has a content hash — SHA-256 over canonical JSON of every non-hash field its format version
defines — and a record hash that chains it to the one before:

```
record_hash[i] = SHA-256( record_hash[i-1] || content_hash[i] ),   record_hash[0] = 0…0
```

If you hold an authentic head, then altering any field, deleting, inserting or reordering any record, or
truncating the chain is detected — unless someone finds a SHA-256 collision. The tests cover each case.

A **Merkle root** over the record hashes promotes an unpaired node rather than duplicating it. The common
alternative — duplicate the last node — gives `[a, b, c]` and `[a, b, c, c]` the same root, which lets a
duplicated record through. That, too, is tested.

### The verifier that shares nothing

`scripts/verify_evidence.py` imports **only the Python standard library**, runs where Prama is not
installed, and checks content hashes, links, contiguity, erasure seals, the manifest, the Merkle root and the
chain head. Tests require it to reach the same conclusion as Prama's own verifier on every case — non-ASCII
text, an added field, a doctored manifest, a truncated file, a removed or reordered record.

The two verifiers once disagreed (QA finding C4, since fixed). That disagreement was a defect in the evidence
layer, found by running the two against each other. A test now holds them together.

An auditor does not have to trust Prama to check Prama's records.

### Anchored outside Prama

Signing a chain does not stop the signer. Somebody holding the key can rebuild a chain from scratch, and the
rebuilt chain verifies perfectly.

What stops that is a witness they do not control. After every run, Prama sends the head's record hash to an
**RFC 3161 time-stamp authority** and keeps the signed token beside the chain. The hash is 32 bytes and names
no record.

The offline verifier checks each receipt against the record at its position. Given the authority's
certificate, it verifies the signature with `openssl ts -verify`. A test rebuilds a chain with one verdict
flipped: the rebuilt chain passes every check on its own, and fails against its receipt.

### Erasure, versions, replay

- **Erasure** replaces a record with a tombstone that keeps the original content hash, so the chain still
  links, and carries its own seal over who erased it and why. Rewriting who erased it is caught.
- **Format versions:** a field added later is hashed only in records whose version defines it, so old and new
  records verify in one chain.
- **Replay** re-executes a record's plan and names the outcome: *identical*; *stable* (the answer held while
  the inputs moved); one of six causes — data, control, engine, parameters, inexact snapshot, coverage; or
  *unexplained*, which is never folded into an ordinary cause. "Stable" matters more than it looks: without
  it, a nightly replay against fresh data reports every record as diverged and the ones that matter are lost.

Every case study ends by verifying its chain and printing its Merkle root. All eight verified in my runs.

### What the evidence does not do

The chain head is signed with HMAC-SHA256, and the code says plainly that this proves nothing to anyone who
does not hold the key. Exported bundles can carry an **Ed25519** signature that verifies with the public key
alone, and an unsigned bundle is reported untrustworthy even when every hash matches. But heads are not
published to any external timestamping service or transparency log. So tamper evidence holds against
everyone *except* a party holding the HMAC key, who could rewrite a chain and re-sign it. That is a real gap,
and it is listed as not built.

---

## Reconciliation: tolerances, and the price of ignoring timing

Reconciliation — showing that two systems that should agree do — is banking's most expensive data quality
failure, and it is usually sold as a separate product. In Prama it is one statement:

```pql
RECONCILE subledger AGAINST general_ledger
  ON (account, cost_centre, posting_date)
  COMPARING amount = balance_eur WITHIN 0.01 EUR
  NORMALISING currency TO 'EUR' USING RATES fx_rates
  OFFSET BY 1 DAY
```

**Tolerance is "whichever is larger".** A difference is allowed if it is within the absolute bound *or*
within the relative bound times the magnitude. A break is a difference that breaches *both*. For large
positions the relative bound governs; for small ones, the absolute. Against a zero magnitude, a relative bound
allows only an exact match. All tested.

**Offsets never steal exact matches.** Rows are matched exactly first. Only rows still unmatched are then
probed one, two, … *k* days away on the date part of the key.

That gives a small counting law. If *t* entries reach the ledger up to *k* days late, and nothing else
collides with them:

> **Breaks without the offset = breaks with it + 2t.**

Each late entry, without the offset, becomes one *missing* on its real day and one *extra* on the day it
landed. With the offset, it becomes nothing.

Case study 6 checks it. An ERP with 840 subledger rows, 280 ledger rows and three currencies. Four defects:
a 250.00 EUR manual journal posted to the ledger only, a day's entries that never reached the ledger, a
ledger balance on an account the subledger never booked, and two entries from the last evening that reached
the ledger the next morning.

In my run the reconciliation found **five** breaks needing a person — three *genuine* (the journal, on three
dates), one *missing*, one *extra* — and nothing for the timing difference. Without `OFFSET BY 1 DAY`, the
same books show **nine**: 5 + 2 × 2. (No test asserts either number; the study prints them and the README
states them.)

Breaks are classified — timing, FX, rounding, missing, extra, duplicate, sign, genuine. Only timing is
expected to clear by itself. Sign, duplicate and FX breaks are *configuration* faults and are routed away from
the data steward, because a steward cannot fix a sign convention by looking harder at the data.

Each side of a reconciliation can be filtered, written after the dataset it applies to:
`RECONCILE a WHERE p AGAINST b WHERE q`. A single filter on the whole control is refused, because it would
filter one side only and every row it dropped would look missing on the other.

Not built yet: your own `CLASSIFY` rules on a reconciliation, and a signed reconciliation certificate from
the break workbench.

---

## Lineage from code: what a copy justifies, and what lineage cannot see

### Parsed, never executed

Prama reads SQL with sqlglot, falling back to a pattern reader that records the fallback as a gap. It reads
PySpark, pandas and Airflow with Python's `ast` module — it never imports a DAG file, because importing one
runs it — and it reads Power BI models as JSON. **Uploaded code is never executed.**

Every edge says how the target was computed from the source — identity, rename, derived, aggregated, filter,
join key — and whether it was **parsed** (confidence 1.0) or **inferred** (the fallback, 0.8; a model's
suggestion, capped at 0.85 and kept only if checked against the code). On a gold-fixture ETL repository the
extractor is required to reach precision ≥ 0.98 and recall ≥ 0.95 on value edges.

### Blast radius

Each transform attenuates a defect: a copy passes on 100%, a filter 90%, a join key 80%, a derivation 70%, an
aggregation 35%. The impact on a downstream column is the strongest path to it. These are declared constants,
not measurements — read "35% of the defect" as a ranking, not a statistic.

### What a copy justifies

A lineage edge is a claim about how one column is computed from another. Some controls follow from that claim
and some don't:

- **If staging is a straight copy of the raw feed**, every rule that holds on every raw row holds on every
  staged row too — *even if staging keeps only some of the rows*. So Prama proposes the same rule downstream.
- **If staging keeps only booked trades**, reconciling it against the whole raw feed would report every
  cancelled trade as a break. The filter edge carries its condition, so the proposal applies the same filter
  to the source: `AGAINST raw.trades WHERE status = 'BOOKED'`. A condition that cannot be carried over holds
  the proposal, with the reason.
- **Aggregated columns inherit nothing** row-level. A sum is not a copy of any row.
- **A guess never becomes a control.** Any proposal resting on an *inferred* edge is held until somebody
  confirms the edge.

Case study 8 found both halves of this the hard way. The first run proposed a reconciliation across the filter
and reported 118 breaks — one per cancelled trade — and the proposed reconciliation had no tolerance, so the
engine refused to run it. Both are fixed: the reconciliation carries the filter, and says `WITHIN 0`.

### The negative result: four lower-case currencies, 605 million of notional

Case study 8 builds a warehouse by actually running an ETL repository: raw feed, staging (booked trades only),
and a mart that **joins staging to an FX table on currency** and sums exposure, with a Power BI model on top.
Prama reads three files; when the study was first built, it extracted twelve parsed column edges.

Two defects are planted in the raw feed: five notionals carrying the sign of the side, and four currencies
written in lower case (`'usd'`).

The owner writes two controls on the raw columns. Lineage proposes the rest.

The **notional's** blast radius runs all the way to the dashboard:

```
stg.trades.notional                                 100%, 1 hop
mart.positions.exposure_usd                          35%, 2 hops
powerbi.risk_dashboard.positions.exposure            35%, 3 hops
powerbi.risk_dashboard.positions.total exposure      12%, 4 hops
```

and the propagated control finds the five at staging too.

The **currency's** blast radius *stops at staging*. The mart never copies, transforms or aggregates the
currency — it uses it only in the join condition. Column lineage follows values, and the currency never
reaches the mart as a value.

But its effect on the mart is real, and the run measures it: three staged trades with no matching FX rate
drop out of the mart, and **605,000,000 of notional goes with them**. No error. No null. No count anywhere
that changes. The rows are simply gone.

> Column lineage models *value* dependence. A join predicate creates *population* dependence — it decides
> which rows exist — and no amount of value lineage will see it.

### The repair: an edge into the rows

The fix is not a better value edge but a different kind of node. The SQL reader now records each equality
in a join's `ON` clause as a `join_key` edge from each side's key into the view's **rows**, written
`mart.positions.*`. That is the same node a `WHERE` column already fed. It also reads a CTE through to its
real table, which exposed a latent bug: sqlglot 30 keeps `WITH` under a different key, so Prama had been
finding no CTEs at all.

The blast radius treats the rows as a population: a change in which rows exist reaches every column
computed over them, and the path says so. Rerun, the currency's blast radius reads:

```
stg.trades.ccy                                      100%, 1 hop
mart.positions.*               (the mart's rows)     80%, 2 hops
mart.positions.exposure_usd                          80%, 3 hops
powerbi.risk_dashboard.positions.exposure            80%, 4 hops
powerbi.risk_dashboard.positions.total exposure      28%, 5 hops
```

The 80% is still a declared weight, not a measurement. What changed is that the report names the rows as
the thing affected, not a value.

The join also justifies a control. A staged trade whose currency has no rate is dropped by the inner join,
and nothing fails, so lineage proposes `CHECK "stg.trades".ccy REFERENCES "ref.fx_rates".ccy`. Rerun, that
check fails on **3 of 1,882** staged trades, where the defect happens and not only where it entered.

The lesson about where controls belong still stands. **Controls belong at the source; lineage carries them
downstream**, and now it carries them across a join too, in SQL and in PySpark. The pandas reader still
reports a `merge` as a gap.

**Before it merges.** `prama code review --base origin/main` runs the same comparison on a pull request.
It reports the lineage the change adds, removes or retypes, what that reaches, and the controls it implies.
Its exit code fails continuous integration when a live control loses the lineage it rests on.

---

## Models author; the engine decides

Language models are good at drafting a rule from a data dictionary, ranking datasets for a question put in
plain words, and explaining a failure. They are not accountable for a verdict, and their output is not
reproducible in the way evidence has to be.

Prama's rule: a model may **author, rank, explain, calibrate and summarise**. No code path lets a model's
output decide whether data passed.

### How that is enforced

- **An architecture test** fails the build if any module both refers to a model (`llm`, `openai`,
  `completion`, `build_prompt`, …) and produces a verdict. It carries a *counterfactual* — a synthetic module
  that calls a model and returns a verdict must make it fire — so the guard is proven to still work.

  I should be precise about what that guard is: a *syntactic* necessary condition. It would not catch a
  model's output laundered through neutral names across two modules. The stronger argument is structural. A
  verdict is a function of an engine's metrics and a plan's threshold; a plan comes from PQL that a person
  activated. The only way a model can influence a verdict is by authoring PQL that a *person* then switches
  on — and then the evidence names that person.

- **Induced controls must be able to fail.** A model asked for a rule can return one that is well formed,
  type-correct, compiles, runs — and cannot fail: `CHECK trades.side MATCHES /.*/`, or `qty >= -1e308`.
  Before anyone is shown a model's suggestion, Prama tries to make it fail. Five gates — parse, type-check,
  compile, sandbox-run on up to 2,000 rows, and a *counterfactual* gate — and the `Validated` type cannot be
  constructed unless all five passed. A check that cannot fail never reaches a reviewer.

- **One gateway.** Callers ask for a *purpose* (author, explain, discover, embed), never a model. A purpose
  with no configured route goes to a mock provider that answers with nothing — so a fresh install uses no
  model at all, and still records the call.

- **A hash-chained call ledger**, redacted by default (secrets, card numbers, IBANs), with payloads that can
  expire while the chain still verifies.

- **Evaluation gates activation.** A new prompt template is approved only after a passing evaluation run, and
  not by its author; a new profile version waits for its own passing run; with no model configured, nothing
  can pass. Personal data may not go to a hosted model. A spent budget refuses with HTTP 429.

### What is not measured

Whether model-authored rules are any *good* — acceptance rates, precision, whether fusing mining with model
induction beats either alone — is not measured. The machinery for merging corroborated proposals exists; the
claim that fusion helps is a claim about reviewers' decisions, and there were no reviewers.

---

## Trust scores and false alarms

### Trust along lineage

A derived column should score no better than what it is derived from. *How* it depends is a choice, and
Prama exposes four:

| Choice | Along a path | Across paths | When it is right |
|---|---|---|---|
| All inputs matter (default) | multiply | worst | a position needs both the amount and the rate |
| Redundant sources | multiply | best | two independent feeds of the same fact |
| Weakest link | worst | worst | what a risk team usually asks for |
| Product–mean | multiply | average | sources contributing in proportion |

The code calls these "semirings". Strictly, only *redundant sources* is one (it is the Viterbi semiring). The
default and weakest-link are well-behaved but lack the annihilating zero, and product–mean isn't associative
across paths at all. Nothing depends on the missing laws, so this is a naming gap, and I record it rather than
dress it up. The reason all four are offered is that they genuinely disagree on the same graph — and the
classic error, taking the *best* across complementary inputs, produces the most reassuring numbers.

### A false-alarm budget with a guarantee

A statistical monitor raises an alert when an observation is unusual. "Unusual" needs a false-alarm rate, and a
rate needs a guarantee. Prama uses **conformal p-values**:

```
p = (1 + #{calibration scores ≥ this score}) / (n + 1)
```

If the scores are exchangeable, alerting at `p ≤ α` fires at most α of the time — for any distribution. The
tests check it at four levels over 2,000 trials, and on heavy-tailed data a z-score would mishandle.

Two consequences are handled honestly:

- **A budget the history cannot express is refused.** With *n* calibration points the smallest possible *p* is
  1/(n+1). "Two false alarms over ten thousand runs" asks for α = 0.0002; if the history cannot express that,
  Prama says so, with the arithmetic, instead of quietly alerting more often.
- **Drift breaks exchangeability.** Prama offers three responses and states each one's price: recency weighting
  (no longer exact, and it says so, and reports the reduced effective sample size); an *adaptive* level that
  controls the long-run alert rate rather than each test; and conditioning on a declared seasonal calendar.

Here is the result as a grid, from my run of the calibration benchmark (synthetic generators, 500 observations
per regime, calibration error = mean gap between promised and realised alert rates; target ≤ 0.02):

| Regime | plain | seasonal | weighted | adaptive | changepoint |
|---|---:|---:|---:|---:|---:|
| stationary | 0.0040 | 0.0152 | 0.0096 | **0.0016** | 0.0040 |
| seasonal | 0.0672 | 0.0232 | 0.0696 | **0.0152** | 0.0672 |
| level shift | 0.1112 | 0.0904 | 0.0208 | **0.0168** | 0.0784 |
| regime switch | 0.0112 | 0.0520 | 0.0136 | **0.0080** | 0.0112 |
| bursty | 0.0104 | 0.0192 | 0.0080 | **0.0064** | 0.0104 |

A grid rather than a number, because no single mechanism is the answer and one number would hide that.
Seasonal conditioning fixes seasonality and cannot fix a level shift; forgetting nearly fixes a level shift and
makes seasonality worse. In this run the adaptive level met the target everywhere. The test asserts less — that
*some* mechanism meets it in every regime.

End to end, a monitor declaring a 0.05 budget realised **0.0467 over 300 judged days** in my run. The test
asserts only that the rate is within 0.03 of the budget.

Across many monitors, Prama selects which alerts to raise with Benjamini–Hochberg (or Benjamini–Yekutieli under
arbitrary dependence) over a hierarchy — domain, dataset, attribute, check — and rolls a wholesale failure of
400 checks under one parent into **one** finding. BH's false-discovery control is tested; a guarantee for the
hierarchical procedure as a whole is not claimed.

**Every number in this section is synthetic.** Whether the guarantees hold on a bank's real metric history is
the central open question here, and it is listed as not built.

---

## Metadata, correlation and fitness for purpose

Owners don't only declare structure. They write descriptions, tag fields — *mandatory*, *allowed values*,
*PII* — and map columns to glossary terms. Prama gets two more derivations out of that.

**Metadata implies rules.** A template field can carry a rule pattern. Set `allowed_values = RETAIL, SME,
CORPORATE` on a column and a proposal appears: `CHECK customers.segment IN ('RETAIL', 'SME', 'CORPORATE')`.
Change the value and the old proposal is retracted, with history kept. The value is inserted as a *typed
literal*, so a value like `x') OR (1=1` stays a string and cannot change the predicate — tested.

**Correlation.** Columns are grouped by shared meaning — business concept first, then glossary term, then
semantic type. Within a group, if exactly one dataset owns the value as a unique key, every other member is
proposed a `REFERENCES` check to it. If nobody, or two datasets, claim ownership, nothing is proposed: Prama can't
tell which way the check should point. Generic types like currency and dates group for consistency only.

**Fitness search** answers a question in plain words — *"who is the customer and where are they registered, for
sanctions screening"* — by ranking **datasets**, not rows, over their descriptions, metadata and profiles. It
uses BM25 when no embedding model is configured and embeddings when one is, and it names the evidence (which
columns and fields matched) so the ranking can be checked. A model may re-rank and explain; it doesn't decide
what exists. No retrieval-quality measurement exists yet.

Case study 7 runs all of it. Owners describe three datasets; nine rules follow as proposals; correlation adds
the reference from `accounts.customer_lei` to `customers.lei` and notices the two LEI columns disagree about
whether they are PII. All four planted defects are found — six segments of `'SME '` with a trailing space, four
accounts with no LEI and three with an LEI no customer has, five negative payments. The sanctions-screening
question returns *Customers*, citing `legal_name`, `customer_id` and `lei`.

---

## What was measured, and what was not

### Eight case studies

Each study fabricates seeded banking data, declares an estate, lets Γ derive the controls, runs them, and prints
**what was planted against what was found** — both columns. Every planted defect is written down before Prama is
pointed at anything, including the ones Prama won't find. From my runs:

| Study | Planted | Found | Not established | Not claimed |
|---|---:|---:|---:|---:|
| 1 Trading book (SQLite) | 9 | 4 | 2 | 3 |
| 2 Feeds: CSV, Parquet, JSON Lines | 9 | 7 | 1 | 1 |
| 3 Mixed estate, relationships | 4 | 4 | 0 | 0 |
| 4 Expressions and plugins | 5 | 4 | 1 | 0 |
| 5 DQ delegates | 4 | 4 | 0 | 0 |
| 6 Month-end close | 4 | 3 | 0 | 0 |
| 7 Governance from metadata | 4 | 4 | 0 | 0 |
| 8 From code to impact | 2 | 2 | 0 | 0 |
| **Total** | **41** | **32** | **4** | **4** |

(Study 6's fourth item is the timing difference, which is correctly *not* a break.)

Every defect a declared control can see was found, with counts that match the planted rows. The four "not
established" are screens and the freshness gap; in none of them did Prama report a pass. The four "not claimed"
are two relationships study 1 deliberately does not declare, the undeclared date relation, and a truncated file
whose trailer check isn't yet wired into the control runner.

**What this does not show:** detection quality. The defects were planted by the person who built the system, in
data generated for the purpose. The most useful columns are the last two. A tool with no false negatives on data it
was built against tells you nothing. A tool that names what it didn't catch, and why, tells you what it is.

The test suite asserts that each study runs to completion; it doesn't assert the counts.

### The benchmark — and what is missing from it

`prama bench run --seed 42` builds 28 labelled scenarios across six defect families and four difficulties, and a
detection counts only if dataset, column *and* window all match. My run:

| Detector | Kind | Found | Precision | Recall | F1 |
|---|---|---:|---:|---:|---:|
| detect-nothing | bound | 0/28 | — | 0.00 | — |
| alert-on-everything | bound | 28/28 | 0.08 | 1.00 | 0.14 |
| schema-only | ablation | 2/28 | 0.67 | 0.07 | 0.13 |
| patterns-only | ablation | 5/28 | 0.83 | 0.18 | 0.29 |
| statistics-only | ablation | 7/28 | 0.88 | 0.25 | 0.39 |
| **prama-declared** | **system** | **10/28** | **0.77** | **0.36** | **0.49** |

The blind spots matter more than the F1s: statistics-only found nothing relational; patterns-only found nothing
statistical, relational, temporal or semantic.

The last row is **Prama's declared path**: controls derived from an owner's declaration of the dataset, run on
each window. The declaration was written from the schema's domain, not from the defect list, and wasn't
revised to catch what it misses.

- **What it finds:** every structural defect, four of seven content defects and one statistical one.
- **What it misses:** everything relational, temporal and semantic. Those need a second dataset, a clock, or
  a meaning the schema doesn't state.
- **What its fairness test found.** The test (clean windows must raise nothing) caught a bug in the corpus:
  its IBANs had made-up check digits, so a *correct* validator alerted everywhere.

None of the fifteen external systems it names was run. So the claim is narrow: the declared path beats every
single technique here, and **nothing is claimed relative to any other product.**

---

## Laws, or it didn't happen

An argument that beliefs about data must be justified owes the same to its own claims. So every formal claim in
the paper carries a marker saying what enforces it in the code — a named test, prose, or nothing — and every test
it cites was located and run. The register at the end counts them:

| State | Count |
|---|---:|
| Runs — a named test exercises it | 45 |
| Runs in part — something weaker runs, stated at the claim | 11 |
| Stated — mathematics the code does not execute | 5 |
| Not built | 9 |
| **Total** | **70** |

The claims that run cluster where the thesis lives: derivation, verdict semantics and evidence. The ones that
don't cluster where a claim is about the *world* rather than the code — detection quality against other systems,
calibration on real data, whether reviewers accept what models propose. Those need a bank, a steward and time,
and a test suite supplies none of them.

---

## How this could be wrong

- **Owners may not declare.** Everything rests on business owners writing declarations. The case studies declare
  on their behalf. If real stewards don't, Γ has nothing to derive from, and the system falls back to mining and
  model induction — the proposals this work ranks lowest.
- **Planted defects aren't defects.** See above.
- **Calibration is synthetic.** A bank's metric history may break the assumptions in ways none of the five regimes
  represents.
- **Scale is untested.** No estate of thousands of datasets; the throughput numbers measure Prama's own overhead,
  not a warehouse.
- **Engines beyond three are unverified.** JDBC dialects are code-complete but untested against live services;
  the Snowflake connector has never met an account.
- **The model guard is syntactic** (see above), and **the evidence trusts its anchors**: records written since the last anchor stay rewritable until the next,
and an anchor is only as independent as the authority chosen.

What would falsify the thesis? A declared estate where derived controls miss defects that hand-written ones catch,
at comparable effort. A deployment where *indeterminate* is so common that operators learn to read it as a pass. A
replay that says *identical* for a run whose data changed. The first two need real users.

---

## For the practitioner

If you take one thing from this: **make your tools say "not established".** A SQL shape check that finds nothing,
a freshness check on a table with no arrival column, a reconciliation across a filtered copy — each is a place where
"green" means "didn't look". A verdict set with only pass and fail forces those into pass.

If you take two: **write the belief down once, and derive the check from it.** The check will then change when the
belief does, and when an auditor asks why a check exists, the answer will be data.

If you take three: **let someone else verify your evidence** — with a script that shares none of your code.

---

<div align="center">
<img src="../../assets/prama-mark.svg" width="30" alt=""/><br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.<br/>
See <a href="../../../LICENSE">LICENSE</a> and <a href="../../../NOTICE">NOTICE</a>. Third-party names and marks are the property of their respective owners.</sub>
</div>
