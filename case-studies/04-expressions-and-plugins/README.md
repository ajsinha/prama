# Case study 4 — Excel formulas, and a validator somebody else wrote

<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt;. All rights reserved.<br/>
Proprietary and confidential.</sub>

---

## What this shows

The two halves of the expression layer, on data that makes both matter.

**Seven controls written as formulas**, in the syntax a finance person already uses:

```
=ROUND([quantity] * [price], 2) = [notional]
=ABS(ROUND([quantity] * [price], 2) - [notional]) <= 0.005
=AND([quantity] > 0, [price] > 0)
=[settlement_date] >= [trade_date]
=NOT(ISBLANK([counterparty_lei]))
=IF(ISBLANK([venue]), FALSE, LEN([venue]) = 4)
=UPPER([currency]) = [currency]
```

Every one compiles to SQL that runs **inside the engine**. Nothing is evaluated row by row in
Python — that is the performance decision the function catalogue exists to make possible.

**One plugin validator** for `acme_book`, an identifier scheme Prama has never heard of, loaded
from `acme_validators.py` and admitted only after its purity is checked and its implementation
hashed into the plan.

## Run it

```bash
cd case-studies/04-expressions-and-plugins
python run.py                 # build, run, and serve the console on :8804
python run.py --no-serve      # build and run, print the report, stop
```

## What was planted, and what happened

| # | Defect | Rows | Found |
|---|---|---|---|
| 1 | Blotter rounds half-to-even; settlement rounds half-up | **31** | ✅ 31, by two formulas |
| 2 | Settlement date before trade date | 18 | ✅ 18 |
| 3 | No counterparty LEI | 11 | ✅ 11 |
| 4 | Book code check character wrong | 7 | ⚠️ not established — screen only |
| 5 | Currency in lower case | 9 | ✅ 9, by three controls |

Every detectable count found **exactly**.

## The half-cent

This is the defect nothing else in these studies finds, and it is not a bug in either system:

```
the blotter rounds half to EVEN      2.675 → 2.67
settlement rounds half AWAY FROM 0   2.675 → 2.68
```

One cent, on every tie — and an integer quantity times a four-decimal price lands on a tie often.
Nothing about either number looks wrong in isolation; the disagreement exists only between them.
It is invisible to every completeness, validity and uniqueness control ever written.

Prama's `ROUND` is half away from zero, which is what a settlement system does. It **says so on
the function**, printed by `control explain`, rather than being discovered in a reconciliation six
months later. And it is **refused on SQLite**, which has no exact numeric type and would give a
third answer.

### Two formulas, deliberately

The study runs both the naive equality and a materiality form:

```
=ROUND([quantity] * [price], 2) = [notional]                    exact
=ABS(ROUND([quantity] * [price], 2) - [notional]) <= 0.005      within half a cent
```

Both find 31 here, which is the point: the disagreement is a *full* cent, so a half-cent tolerance
does not absorb it. A tolerance that did absorb it would be hiding the defect, not tolerating it —
which is the conversation a materiality threshold is supposed to force.

## ⚠️ The plugin's control is "not established", and that is correct

`acme_book` is `XX-NNNN-C`: two letters, four digits, and a check character weighted mod 23. SQL
expresses the shape and cannot express the check character — so the control is a **screen**, its
violation count is a lower bound, and seven wrong check characters are reported as *not
established* rather than as a detection:

```
?  trade_blotter   screen only; residual not run: acme_book on book_code
```

That is the same two-stage behaviour ISIN and LEI have always had. The plugin did not need new
machinery; it needed a place to declare itself.

## What the plugin contract enforces

Before `AcmeBookCode` is usable, the study prints:

```
scanning acme_validators.py without importing it…
  clean: no clock, no network, no filesystem, no model
  admitted acme_book — implementation e945943541c46be7f92b582b536ec587
  ran twice on the same inputs and agreed both times
```

Four things are checked, and none is taken on trust:

- **Scanned from source, before import.** Importing a module runs its top-level code, so a gate
  that had to import the thing it was gating would already have run it. It also means a plugin can
  be vetted when its dependencies are not installed — which is the situation a reviewer is in.
- **Determinism, by execution.** Run twice on the same probes including an empty string. Import
  scanning catches the obvious sources; this catches a cached global, a mutable set, a counter.
- **`CON-007`.** A plugin importing a model client is refused: a model output would otherwise
  decide a pass or fail verdict on data.
- **Identity.** The implementation's hash is folded into the plan id of every control naming
  `acme_book`. Edit the check-digit routine and the control changes identity, rather than silently
  changing what last month's evidence meant.

`datetime` is **not** banned — a date validator legitimately parses one. What is banned is asking
it what time it is. A rule that refused the validator it was written to protect would be widened
within a week.

## What building this found in Prama

The first `ROUND` lowering emitted `CAST(x AS NUMERIC)`. That is arbitrary precision in PostgreSQL
and **`DECIMAL(18,3)` in DuckDB** — so rounding through three decimals and then to two is a
*double rounding*:

```
1953193.4649  →  .465  →  .47      two roundings
1953193.4649  →  .46               one rounding
```

It reported **131 extra rows in 3,000** as a cent out when they were not — a false alarm on the
control people trust most, in the direction that makes a clean book look broken. It was invisible
in unit tests and obvious the moment the formula ran against a blotter.

The lowering now states its scale, a regression test pins it on every engine, and this study finds
exactly the 31 rows it planted.

## Files

| File | What it is |
|---|---|
| `acme_validators.py` | The plugin: a check-digit scheme, and nothing else |
| `run.py` | Builds the blotter, admits the plugin, declares the formulas, runs, reports |
| `workspace/landing/blotter/` | The CSV |
| `workspace/blotter.duckdb` | A view over it |
