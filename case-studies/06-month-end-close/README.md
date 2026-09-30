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

## Run it

The study is a client of **your** Prama server. It talks to it only through the SDK
(`prama_sdk`), and it does not start a server or a console of its own.

```bash
prama serve                                   # or python run_prama_web.py, if not running already
cd case-studies/06-month-end-close
python run.py                                 # the server config/application.yaml names
python run.py --config other.yaml             # another server: the one other.yaml describes
python run.py --username ada --password …     # as somebody else (default: the dev admin)
```

The books live in one SQLite file under `workspace/`, which stands in for the ERP. The server
reads it itself, so `case-studies/` must be under the server's `runs.roots`. The shipped
`config/application.yaml` already includes it. Each run creates an estate of its own, named
`acme-finance-<timestamp>`, and a second estate, `…-no-offset`, for the counterfactual (below).
Nothing else needs configuring.

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

The control fails with **5 breaks needing a person**, exactly the planted ones, and a match rate
of 99.64%. Γ's 17 derived controls pass, and the evidence chain (18 records) verifies.

**The break workbench, over the SDK.** The study reads the reconciliation's result with
`client.reconciliation.list()` and its queue with `client.breaks.workbench(definition)`: 3
`genuine`, 1 `missing`, 1 `extra`. It then works the queue as a ledger controller would:

- it assigns the three genuine breaks to `gl-journals` (`client.breaks.assign`);
- it explains the ledger-only account (`client.breaks.explain`);
- it accepts nothing. Accepting carries a difference; it does not make the books agree.

It then asks for the period-end certificate (`client.reconciliation.certify`,
`period_end=2026-09-30`). The certificate is returned, not stored, and states what is
outstanding, what has been accepted and what nobody has explained.

**The counterfactual.** The run reconciles the same books again without `OFFSET BY 1 DAY`, and
reports **9** breaks instead of 5 (3 genuine, 3 missing, 3 extra). Each late entry becomes one
row missing on the last day and one extra row the next day. The timing allowance removes noise,
and it removes nothing real.

The counterfactual runs as a real `RECONCILE`, by the server, in an estate of its own
(`…-no-offset`). In the close's estate its breaks would be filed under the same definition
(`subledger against general_ledger`), mixed into the queue the certificate reads, and it would
leave a failing record beside the real one.

## What converting to the SDK found

The numbers are unchanged: before and after the conversion, 17 pass and 1 fail (5 of 841 rows),
the same 5 breaks, and 9 without the offset. Two things changed in how they are reached:

- **`controls.preview` does not reconcile.** The obvious SDK call for "run this once and record
  nothing" is `client.controls.preview`. For a `RECONCILE` it runs only the control's metric
  query, not the matching engine, and answers `no_data` with zero violations. It does not refuse,
  so a caller that reads `violating_rows` gets 0 breaks, a flattering and wrong answer. The first
  draft of the converted study printed "0 breaks" from it. The in-process study used
  `prama.recon.pql.measure` directly, which has no SDK counterpart. Preview (and backtest) should
  either run RECONCILE through the reconciliation engine or refuse it.
- **A run's `datasets` must name a declared dataset or a control's target.** In the
  counterfactual estate only `subledger` is a control target, so naming `general_ledger` (a
  RECONCILE's counterpart) is refused. The study runs every active control there instead.

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
| `run.py` | Builds the ERP's books; over the SDK, declares the estate and the reconciliation, has the server run it, and works the break workbench |
| `workspace/finance.db` | The subledger, the ledger and the rates: the data being checked |
