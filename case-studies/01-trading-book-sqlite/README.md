# Case study 1 — a trading book, in SQLite

<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt;. All rights reserved.<br/>
Proprietary and confidential.</sub>

---

## What this shows

A front-office trading book in one SQLite database: instruments, counterparties,
5,000 trades over ten business days, end-of-day positions, a general ledger and
FX rates.

Somebody who owns the data describes it — *what one row represents, how often it
arrives, what each field means, how much a defect matters* — and **not one line
of SQL is written by a human**. Prama derives the controls from those sentences,
runs them against the database, and records what it found in a hash-chained
ledger.

Nine defects are planted before Prama is pointed at anything. The run prints the
planted list against what was found, **including the five it does not catch and
why** — which is the part that makes this checkable rather than a brochure.

## Run it

```bash
cd case-studies/01-trading-book-sqlite
python run.py                 # build, run, then serve the console on :8801
python run.py --no-serve      # build and run, print the report, stop
python run.py --port 9000     # serve somewhere else
```

Everything is local. The data being checked is one SQLite file under `workspace/`. Prama's own
records go to the application's database (`config/application.yaml`, or `--config`), under a
fresh tenant each run. Every run rebuilds the data from scratch, seeded, so the numbers are the
same every time.

## The five stages

| | | |
|---|---|---|
| 1 | **Build** | 5,000 trades, seeded, with nine defects planted and logged |
| 2 | **Declare** | Six datasets described in business terms. No SQL. |
| 3 | **Derive (Γ) and accept** | 65 controls follow from the declarations |
| 4 | **Run** | One pass against SQLite; evidence into the ledger |
| 5 | **Report** | Planted against found, and the chain verified |

Then the console at `http://127.0.0.1:8801`.

## What was planted, and what happened

| # | Defect | Rows | Found? |
|---|---|---|---|
| 1 | One book's positions delivered twice | 12 | ✅ **12 duplicates in 72 rows** — the declared grain |
| 2 | `notional` missing (a CDE for FRTB) | 60 | ✅ **60 of 5,000** — completeness |
| 3 | `quantity` negative | 7 | ✅ **7 of 5,000** — the declared range |
| 4 | `currency` = `EURO` | 15 | ✅ **15 of 5,000**, twice — the codelist *and* the semantic type |
| 5 | ISIN checksum wrong | 12 | ⚠️ **not established** — see below |
| 6 | Instrument not in the security master | 23 | ❌ needs a declared relationship |
| 7 | Settlement date before trade date | 4 | ❌ nothing was declared about the two |
| 8 | Ledger adjusted without a position move | 1 | ❌ needs a reconciliation |
| 9 | FX rate three weeks stale | 1 | ⚠️ no arrival column declared, so nothing to measure |

Four of nine caught outright. The other five are the interesting ones.

### ⚠️ "Not established" is not a pass — and not a detection

An ISIN is twelve characters *and* a Luhn-style check digit. SQL can express
the shape; it cannot express the checksum. So the control compiles to a
**screen** — a necessary condition — and its violation count is a **lower
bound**.

Zero violations from a lower bound does not mean clean. It means *not
established*. Prama records `indeterminate` and names the residual that has not
run:

```
?  trades   screen only; residual not run: isin on isin
```

Most tools report this as a pass. That is the single most expensive lie a data
quality tool can tell, because it is told about exactly the columns whose
validation SQL cannot express — identifiers, checksums, formats.

The twelve bad ISINs are **not** claimed as a detection here. The honest
statement is that Prama declined to certify the column, and said why.

### ❌ Three things a declaration cannot imply

Defects 6, 7 and 8 are not Prama failing. They are **gaps in the declaration**,
and the difference matters:

- **The orphan instruments** need a *relationship* — "every trade's instrument
  exists in the security master" is a fact about two datasets, and neither
  declaration alone implies it. Case study 3 declares it and finds all 23.
- **The impossible settlement dates** need somebody to say that settlement
  follows trade. Nobody did. This study leaves the defect in rather than
  quietly declaring the rule, because the gap is the lesson.
- **The ledger break** needs a reconciliation, which again comes from a
  relationship. Case study 3 declares it.

### ⚠️ Freshness with nothing to measure

Each dataset declares when it arrives ("by 06:30") but not which column records the arrival.
A plain table keeps its rows, not when they were loaded, so there is nothing to measure. Prama
does not generate a freshness control that could never be red. It prints the reason instead,
six times, once per dataset:

```
! fx_rates: fx_rates declares when it arrives but not which column records the arrival, so
  there is nothing to measure freshness on
```

Declaring the rhythm's arrival column (a load timestamp) makes it measurable. The newest
arrival is then judged against the due time on the declared business calendar. Case study 2
judges arrival on its feeds.

## What the run prints at the end

```
44 passing · 5 failing · 10 not established · 0 could not run
Evidence chain: 59 record(s), verified
Merkle root: …
```

Ten "not established" is the honest number: they are two-stage semantic types (ISIN, LEI,
ISO dates) whose SQL is a screen, not the exact test. Every one of them is a column Prama will
not certify, and every one is visible.

## What to look at in the console

| Page | What it shows |
|---|---|
| `/estate` | The six datasets, coloured by tier |
| `/controls` | All 65, grouped by whether they actually run |
| `/incidents` | One row per control, not per run |
| `/scorecards` | Decomposed by dimension, with coverage beside the number |
| `/evidence` | The chain, its Merkle root, and whether it verifies |
| `/reports` | The declaration pack and the control pack, print-ready |

On `/reports`, the **control pack** prints every control, why it exists, the SQL
it becomes, and the declarations from which no control could be generated — so
the set cannot look complete when it is not.

## Files

| File | What it is |
|---|---|
| `generate.py` | Builds the SQLite database and plants the defects |
| `run.py` | Declares the estate, drives Prama, prints the report |
| `workspace/trading_book.db` | The fabricated data |

The estate declaration is the top of `run.py`. Read it first — everything Prama
does afterwards follows from those sentences.

## One thing this study found in Prama itself

Building it surfaced a real defect. Γ generated `MATCHES /None/` for every
free-text column — a control that parsed, compiled, ran, and failed every row of
every dataset. The cause was a value domain read back from JSON with its `kind`
still a string, so the `is_constrained` check silently passed for everything.

It is fixed, in two places: the adapter now coerces the enum, and Γ now reports
a pattern domain with no pattern as **unsatisfiable** rather than generating a
control against the literal text `None`.

That is the failure mode this codebase is built to refuse — *an artefact that
builds, validates, and looks right while being wrong* — and a case study that
did not run against real data would never have found it.
