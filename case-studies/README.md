# Prama case studies

<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt;. All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.</sub>

---

Four runnable studies over fabricated banking and trading data. Each builds its
own data, declares an estate in business terms, lets Prama derive the controls,
runs them, and serves the console — all on localhost, nothing external.

| | Study | Sources | What it is for |
|---|---|---|---|
| **1** | [Trading book, in SQLite](01-trading-book-sqlite/) | One SQLite database | The whole loop, end to end, on one source |
| **2** | [Daily feeds, CSV and Parquet](02-feeds-csv-parquet/) | A landing zone of files | Arrival: the defects a content check cannot see |
| **3** | [A mixed estate](03-mixed-estate/) | SQLite **and** files | Relationships: the defects one dataset cannot see |
| **4** | [Expressions and plugins](04-expressions-and-plugins/) | CSV via DuckDB | Excel formulas, and a validator somebody else wrote |

## Run one

```bash
cd case-studies/01-trading-book-sqlite
python run.py                 # build, run, then serve the console
python run.py --no-serve      # build, run, print the report, stop
```

The consoles are on `:8801` to `:8804`, one per study, so all four
can run at once. Everything lives under each study's `workspace/`; delete the
directory to start over. The data is seeded, so two runs produce the same
numbers and the figures in each README are checkable rather than decorative.

Requires the dev install: `pip install -e ".[dev,serve]"`.

## The rule these studies follow

**Every planted defect is declared before Prama is pointed at anything**, in the
generator and in the README. The run prints the planted list against what was
found, including the rows in neither column.

That last part is the discipline. A tool with no false negatives on data it was
tuned against tells you nothing. A tool that says plainly *"these four I did not
catch, and here is why"* tells you what it is. Across the three studies:

- Defects Prama **finds** — duplicates, nulls in a CDE, out-of-range values, bad
  codelist values, orphans, missing and duplicated deliveries.
- Defects it reports as **not established** — checksums, where SQL can express
  the shape and not the standard. Zero violations from a screen is a *lower
  bound*, and reporting one as a pass is the most expensive lie a data quality
  tool can tell, because it is told about exactly the columns whose validation
  SQL cannot express.
- Defects it **does not claim** — a truncated file (the trailer check runs at
  arrival, not as SQL), a reconciliation (a comparison specification, executed
  by the matching engine), and a rule nobody declared. Each is named, with the
  reason, rather than omitted.

## What is *not* here

- **No authentication.** The console takes its tenant from configuration. Real
  deployments do not; that is Wave 10.
- **No scheduler running.** The studies run the controls once, by hand. Prama's
  scheduler exists and is wired, but a case study you have to wait a day for is
  not a case study.
- **No PostgreSQL.** SQLite and DuckDB, because both run from a file with no
  server. The same controls compile for PostgreSQL — `/controls/studio` in any
  console will show you the SQL for it.

## What these studies found in Prama itself

Building them against real data surfaced six genuine defects, all now fixed:

1. **Γ generated `MATCHES /None/`** for every free-text column — a control that
   parsed, compiled, ran and failed every row of every dataset. A value domain
   read back from JSON kept its `kind` as a string, so the "is this
   constrained?" check silently passed for everything.
2. **Controls were lowered without their code lists**, so every `IN CODELIST`
   control refused to compile. Six call sites, each remembering separately;
   there is now one function and a test that forbids the others.
3. **A regular expression would not bind against a `DATE` column** on a strict
   engine — an ordinary "this looks like a date" control could not run.
4. **SQLite could not do regex at all**, when in fact it reserves the `REGEXP`
   operator for a function the host registers. Prama's executor now registers
   one, and the conformance suite confirms SQLite agrees with DuckDB rather than
   approximating.

5. **`ROUND` double-rounded on DuckDB.** A bare `CAST(x AS NUMERIC)` is arbitrary precision in
   PostgreSQL and `DECIMAL(18,3)` in DuckDB, so rounding through three decimals and then to two
   turned `1953193.4649` into `.47` where one correct rounding gives `.46`. It reported 131 rows
   in 3,000 as a cent out when they were not — a false alarm on the control people trust most.
6. **An unknown function name compiled straight through to SQL** while the reference interpreter
   returned `UNKNOWN` for the same expression — so the compiler and the independent check that
   exists to catch the compiler being wrong disagreed silently. There is now a function catalogue,
   and no function can exist without both a lowering and a reference implementation.

Every one is the failure this codebase is built to refuse — *an artefact that
builds, validates, and looks right while being wrong* — and none would have been
found without running against data somebody had to look at.

---

<div align="center">
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt;. All rights reserved.<br/>
Proprietary and confidential. See <a href="../LICENSE">LICENSE</a> and <a href="../NOTICE">NOTICE</a>.</sub>
</div>
