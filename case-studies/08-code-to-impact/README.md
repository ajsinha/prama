# Case study 8 — from code to impact

<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt;. All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.</sub>

---

A risk team's ETL repository has three files:

- **`sql/01_stage_trades.sql`** stages the booked trades from the raw feed.
- **`sql/02_mart_positions.sql`** builds positions in USD by account, joining FX rates.
- **`bi/model.bim`** is the Power BI model behind the *Risk Dashboard* and its *Total Exposure*
  measure.

Nobody draws the lineage. Prama's **code intake** reads the repository and turns the parse into
column lineage. It never executes the code. The feed's owner writes two controls on the raw feed,
and the lineage proposes the rest. Two defects planted in the raw feed are then traced to the
dashboard.

```bash
cd case-studies/08-code-to-impact
python run.py                 # build, run, and serve the console on :8808
python run.py --no-serve      # build and run, then stop
```

The warehouse is a DuckDB file under `workspace/`, with schemas `raw`, `ref`, `stg` and `mart`.
It is built by running the same SQL that intake reads, so the lineage and the data cannot
disagree.

## What intake reads

All three files are read: the SQL by `sqlglot`, and the model by the Power BI reader. Together
they produce **12 column edges**, all `parsed`. For example:

```
raw.trades.notional_amt      → stg.trades.notional                         identity
raw.trades.status            → stg.trades.*                                filter
stg.trades.notional          → mart.positions.exposure_usd                 aggregated
mart.positions.exposure_usd  → powerbi.risk_dashboard.positions.exposure   rename
```

## Two controls written, the rest proposed

The owner writes two controls on the raw feed:

```pql
CHECK "raw.trades".notional_amt >= 0 SEVERITY critical DIMENSION validity
CHECK "raw.trades".currency IN ('USD', 'EUR', 'GBP', 'JPY') SEVERITY critical DIMENSION validity
```

The lineage then proposes further controls:

- **Carried downstream.** `stg.trades.notional` and `stg.trades.ccy` are straight copies, so each
  copy must hold its source's control.
- **Referential.** Every key copied from a source must exist in that source.
- **A reconciliation.** The dashboard's `exposure` must agree with the mart's `exposure_usd`.

One proposal is **held**, not accepted: reconciling `stg.trades` against `raw.trades`. The
staging SQL keeps only `BOOKED` trades, and lineage records that as a `filter` edge. A
reconciliation would report all 118 cancelled trades as missing.

## What is planted, and what is found

| Planted in `raw.trades` | Rows | Found on `raw.trades` | Found on `stg.trades` |
|---|---:|---|---|
| A notional carrying the sign of the side | 5 | **5 of 2,000** | **5 of 1,882** (propagated) |
| Currency `'usd'` in lower case | 4 | **4 of 2,000** | **3 of 1,882** (propagated) |

Staging finds 3 lower-case currencies, not 4, because one of those trades is cancelled and never
staged.

## Where the defects go

The **blast radius** of `raw.trades.notional_amt` reaches four columns and ends at the
dashboard's *Total Exposure* measure. The impact weakens at each aggregation:

```
stg.trades.notional                                 100%, 1 hop
mart.positions.exposure_usd                          35%, 2 hops
powerbi.risk_dashboard.positions.exposure            35%, 3 hops
powerbi.risk_dashboard.positions.total exposure      12%, 4 hops
```

The currency defect is the more instructive one:

- **Its blast radius stops at `stg.trades.ccy`.** Column lineage follows values, and the currency
  reaches the mart only through a **join condition**, not as a value.
- **Its effect on the mart is real.** The run measures it directly: the 3 staged trades with no FX
  rate drop out of `mart.positions`, and **605,000,000** of notional is missing from exposure.
  There is no error and no null. The rows are simply gone.
- **Only the control on the raw column sees it.** That is why a control belongs at the source,
  and lineage is used to carry it downstream, not to replace it.

## What building it found

This study found two defects in Prama's lineage proposals, both now fixed:

1. **A proposed `RECONCILE` could not run.** It had no tolerance, and the engine refuses a
   reconciliation with no stated bound. A copy should be exact, so the proposal now says
   `WITHIN 0`.
2. **A filtered copy was reconciled as if it were whole.** The first run reported 118 breaks, one
   per cancelled trade. A reconciliation over a `filter` edge is now held, with the reason, until
   `RECONCILE` can take a `WHERE`.

## Files

| File | What it is |
|---|---|
| `run.py` | Writes the repository, builds the warehouse by running it, reads it into lineage, runs |
| `workspace/risk-etl/` | The ETL repository that intake reads |
| `workspace/warehouse.duckdb` | Raw, reference, staging and mart schemas: the data being checked |
