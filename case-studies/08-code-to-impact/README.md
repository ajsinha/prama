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
they produce **14 column edges**, all `parsed`. For example:

```
raw.trades.notional_amt      → stg.trades.notional                         identity
raw.trades.status            → stg.trades.*                                filter     WHERE status = 'BOOKED'
stg.trades.ccy               → mart.positions.*                            join_key   inner join: stg.trades.ccy = ref.fx_rates.ccy
stg.trades.notional          → mart.positions.exposure_usd                 aggregated
mart.positions.exposure_usd  → powerbi.risk_dashboard.positions.exposure   rename
```

`dataset.*` stands for a dataset's rows:

- **A filter edge** records the condition, when it is over one table.
- **A join-key edge** records the pairing, and it is read through the CTE `fx` to the real
  table, `ref.fx_rates`.

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
- **Reconciliations.** The dashboard's `exposure` must agree with the mart's `exposure_usd`.
  Staging must agree with the raw feed, over the same rows. The staging SQL keeps only `BOOKED`
  trades, so the proposal carries that filter to the source side:

  ```pql
  RECONCILE "stg.trades" AGAINST "raw.trades" WHERE status = 'BOOKED'
    ON (account_id = acct, trade_id = id) COMPARING notional = notional_amt WITHIN 0
  ```

- **Every row must find its match.** The mart inner-joins staging to the FX rates on currency.
  A trade whose currency has no rate is dropped, and nothing fails. So the join proposes:

  ```pql
  CHECK "stg.trades".ccy REFERENCES "ref.fx_rates".ccy DIMENSION integrity
  ```

## What is planted, and what is found

| Planted in `raw.trades` | Rows | Found on `raw.trades` | Found on `stg.trades` |
|---|---:|---|---|
| A notional carrying the sign of the side | 5 | **5 of 2,000** | **5 of 1,882** (propagated) |
| Currency `'usd'` in lower case | 4 | **4 of 2,000** | **3 of 1,882** (propagated), and **3 of 1,882** at the FX join |

Staging finds 3 lower-case currencies, not 4, because one of those trades is cancelled and never
staged. The filtered reconciliation of staging against the raw feed **passes**: the copy is
faithful, and the defects are in the data it faithfully copied.

## Where the defects go

The **blast radius** of `raw.trades.notional_amt` reaches four columns and ends at the
dashboard's *Total Exposure* measure. The impact weakens at each aggregation:

```
stg.trades.notional                                 100%, 1 hop
mart.positions.exposure_usd                          35%, 2 hops
powerbi.risk_dashboard.positions.exposure            35%, 3 hops
powerbi.risk_dashboard.positions.total exposure      12%, 4 hops
```

The currency defect is the more instructive one. It never travels as a value: it decides **which
rows** the mart holds. The run measures its effect directly: the 3 staged trades with no FX rate
drop out of `mart.positions`, and **605,000,000** of notional is missing from exposure. There is
no error and no null. The rows are simply gone.

The blast radius follows it through the join, to the mart's rows and on to every column computed
over them:

```
stg.trades.ccy                                      100%, 1 hop
mart.positions.*               (the mart's rows)     80%, 2 hops   join key
mart.positions.exposure_usd                          80%, 3 hops
powerbi.risk_dashboard.positions.exposure            80%, 4 hops
powerbi.risk_dashboard.positions.total exposure      28%, 5 hops
```

And the check the join proposed catches it **where it happens**, at staging, not only at the raw
feed.

## What building it found

This study found four defects in Prama's lineage, all now fixed, each with a test that fails on
the old code:

1. **A proposed `RECONCILE` could not run.** It had no tolerance, and the engine refuses a
   reconciliation with no stated bound. A copy should be exact, so the proposal now says
   `WITHIN 0`.
2. **A filtered copy was reconciled as if it were whole.** The first run reported 118 breaks, one
   per cancelled trade. `RECONCILE` now takes a filter on each side
   (`RECONCILE a WHERE … AGAINST b WHERE …`). The filter edge carries its condition, so the
   proposal applies it to the source. A condition that cannot be carried over holds the proposal,
   with the reason.
3. **Column lineage could not see a join.** The blast radius of the currency defect stopped at
   staging, while 605,000,000 of notional left the mart at the FX join. The SQL reader now
   records join keys, the blast radius follows a dataset's rows to its columns, and each join
   proposes a check that every row finds its match.
4. **A CTE was taken for a table.** sqlglot 30 keeps a `WITH` clause under a different key, so
   Prama found no CTEs, and `fx` looked like a dataset. It is now resolved to `ref.fx_rates`.

## Files

| File | What it is |
|---|---|
| `run.py` | Writes the repository, builds the warehouse by running it, reads it into lineage, runs |
| `workspace/risk-etl/` | The ETL repository that intake reads |
| `workspace/warehouse.duckdb` | Raw, reference, staging and mart schemas: the data being checked |
