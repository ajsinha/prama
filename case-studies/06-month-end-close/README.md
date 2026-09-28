# Case study 6 — month-end close

<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt;. All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.</sub>

---

The month closes when the subledger agrees with the general ledger. They are two systems:

- **The subledger** books every entry in its own currency: EUR, USD or GBP.
- **The general ledger** holds one EUR balance per account, cost centre and day.
- **Timing.** Entries booked on the last evening reach the ledger the next morning.

One `RECONCILE` says all of that. Prama's reconciliation engine does the rest: it matches the
rows, converts currencies, allows for timing, and classifies every difference.

```bash
cd case-studies/06-month-end-close
python run.py                 # build, run, and serve the console on :8806
python run.py --no-serve      # build and run, then stop
```

The books live in one SQLite file under `workspace/`, which stands in for the ERP. Prama's own
records go to the application's database, under a fresh tenant each run.

## The reconciliation

```pql
RECONCILE subledger AGAINST general_ledger
  ON (account, cost_centre, posting_date)
  COMPARING amount = balance_eur WITHIN 0.01 EUR
  NORMALISING currency TO 'EUR' USING RATES fx_rates
  OFFSET BY 1 DAY
  SEVERITY critical DIMENSION accuracy
```

- **`ON`** matches entries to ledger rows. Many entries sum into one ledger row.
- **`COMPARING … = balance_eur`** compares columns that have different names on each side.
- **`NORMALISING`** converts each entry's currency to EUR with the treasury's closing rates,
  which are a dataset (`fx_rates`) like any other.
- **`OFFSET BY 1 DAY`** lets an entry match the ledger row one day later. The ledger catching up
  overnight is not a break.

## What is planted, and what is found

| Planted | Rows | Found |
|---|---:|---|
| A manual journal of 250.00 EUR posted to the ledger only | 3 | 3 `genuine` breaks |
| A day's entries never reached the ledger | 1 | 1 `missing` break |
| A ledger balance on an account the subledger never booked | 1 | 1 `extra` break |
| The last evening's entries booked the next morning | 2 | no break: matched across the offset |

The control fails with **5 breaks needing a person**, exactly the planted ones. Each break lands
in the **break workbench** (Reconciliation page), where it is explained, accepted or fixed by its
owner.

**The counterfactual.** The run reconciles the same books again without `OFFSET BY 1 DAY`, and
reports **9** breaks instead of 5. Each late entry becomes one row missing on the last day and one
extra row the next day. The timing allowance removes noise, and it removes nothing real.

## What building it found

The first version of this study reported 23 extra breaks, all on the USD and GBP accounts. The
generator converted each entry to EUR, rounded it, and summed the rounded amounts. The engine
converts each day's total and rounds once. The two conventions differ by a few cents, which is
more than the one-cent tolerance.

That is a real difference between two systems, and one that finance teams do meet. It was not
the difference this study is about, so the generator now uses the ledger's convention. If your
ledger rounds per entry, widen the tolerance or declare that convention; do not assume it away.

## Files

| File | What it is |
|---|---|
| `run.py` | Builds the ERP's books, declares the estate and the reconciliation, runs it |
| `workspace/finance.db` | The subledger, the ledger and the rates: the data being checked |
