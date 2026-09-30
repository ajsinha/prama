# Case study 3 — a mixed estate, and what only a relationship can see

<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt;. All rights reserved.<br/>
Proprietary and confidential.</sub>

---

## What this shows

The realistic shape: **two sources, one estate**.

- A **warehouse** in SQLite holding the security master, the counterparty master
  and the general ledger — the things somebody queries.
- A **landing zone** of CSV and Parquet holding the daily trade and position
  extracts — the things that arrive.

Two passes, **one evidence ledger**. Each pass runs only the controls whose data
its source holds, and the report counts what it could not reach — because "this
pass covered 12 of the estate's 40 controls" is a fact the reader needs, and a
run that reported 12 and said nothing about the rest reads as an estate of 12.

## The point of this study

Case studies 1 and 2 plant orphans and a ledger break **and decline to claim
them**, because neither is visible from either dataset alone:

> A trade naming an instrument the master has never heard of is not wrong on the
> trade side — the value looks exactly like an ISIN. It is not wrong on the
> master side either — nothing is missing there. Only the **relationship**
> between them sees it, and a join would silently drop the rows.

Here the relationships are declared, and the same defects are found.

## Run it

The study is a client of **your** Prama server: it signs in through the SDK
(`prama_sdk`), creates an estate of its own for the run, and transacts into it —
datasets, relationships, controls, two connections and two runs. It starts no
server and opens no Prama database.

```bash
prama serve                               # or python run_prama_web.py, if not already running
cd case-studies/03-mixed-estate
python run.py                             # the server config/application.yaml names
python run.py --config other.yaml         # another server: its server.host and server.port
python run.py --username ada --password … # as somebody else (default: the dev admin)
```

**The server reads both sources, not the study**, so the server must be allowed
to: add this checkout's `case-studies` directory to `runs.roots` in the server's
`application.yaml` (or `application.local.yaml`) and restart it. Without that,
the run stops at stage 4 and says which setting to change.

Every run rebuilds both sources from the same seed and gets a fresh estate
(`acme-group-<timestamp>`), so a rerun starts clean and the numbers below repeat.

## What was planted, and what happened

| # | Defect | Rows | Found? |
|---|---|---|---|
| 1 | Trades naming an instrument not in the master | 37 | ✅ **37 of 4,000** — integrity |
| 2 | Trades naming a counterparty not in the master | 14 | ✅ **14 of 4,000** — integrity |
| 3 | `market_value` missing (a CDE) | 11 | ✅ **11 of 60** — completeness |
| 4 | Ledger adjusted with no matching position move | 1 | ✅ **1 break** — consistency, by `RECONCILE` |

Defects 1 and 2 are the ones the first two studies could not touch. They are
found here for one reason: somebody declared what is true between the datasets.

```python
Relationship(
    kind="references",
    left="trade_feed",
    right="instrument_master",
    match_keys=(("isin", "isin"),),
    cardinality="many_to_one",
    description="Every trade names an instrument the master knows about.",
)
```

The study declares it with `client.relationships.declare`, the owner confirms
it (`client.relationships.confirm`), and `client.derive.relationship` derives
and accepts what it implies.

Γ turns that into:

```
CHECK trade_feed.isin REFERENCES instrument_master.isin
  SEVERITY major DIMENSION integrity
  BECAUSE 'records here point at records there'
```

## ⚠️ The reconciliation: proposed by Γ, completed and activated by a person

The ledger break needs a reconciliation, and this study **declares** one:
positions against the book of record, matched on book, comparing market value,
within a dollar or a basis point.

Γ proposes that declaration as runnable PQL, and a person completes it. The
positions are in their instruments' currencies and the ledger is in USD, so the
finance controller adds the normalisation before activating it:

```pql
RECONCILE position_feed AGAINST general_ledger ON (book)
  COMPARING market_value = balance_usd WITHIN 1 USD OR 0.01%
  NORMALISING currency TO 'USD' USING RATES fx_rates
  SEVERITY critical DIMENSION consistency
```

The study authors it with `client.controls.declare` and activates it with
`client.controls.activate`; the server's reconciliation engine (`prama.recon`)
runs it like any other control. It
matches positions to ledger rows on the book, sums each book's positions in USD,
compares them within the tolerance, and classifies each difference. Breaks that
need a person fail the control, and each one lands in the break workbench.

It finds **exactly one break**, CREDIT-01: the planted 0.6% adjustment. The same
book also carries the eleven null market values planted below, so the break is
reported once, for both reasons.

Without the normalisation, every book with non-USD positions shows as broken.
That is why Γ proposes the reconciliation instead of activating it: a
declaration does not say how currencies are converted, and a reconciliation that
guesses reports breaks that are only currency.

## A copy, said out loud

A control spanning two datasets has to run *somewhere*, and no single query
reaches both a SQLite file and a Parquet directory. So the masters are
**published** into the analytics zone as Parquet — which is exactly what banks
do, and it is a copy.

A copy that stops agreeing with its origin is itself a defect. Prama has a
relationship kind for precisely that (`mirrors`, which generates row-count
parity, content parity and staleness controls) and **this estate does not
declare one**. That is a real gap in the declaration, left in and named rather
than quietly fixed.

## Two passes, one ledger

Each source is registered as a connection and run by the server
(`client.runs.start`), scoped to the datasets it holds:

```
warehouse (SQLite)                      instrument_master, counterparty_master, general_ledger
landing zone (CSV + Parquet, DuckDB)    trade_feed, position_feed, + the published masters
```

The landing zone is a `duckdb` connection to `workspace/landing.duckdb`, the
catalogue of views over the files, rather than a `files` connection to the
directory: the treasury's rates the reconciliation normalises with (`fx_rates`)
are a view in that catalogue, not a file.

```
warehouse (SQLite)                      22 control(s), 3 indeterminate, 19 pass, 35 on another source
landing zone (CSV + Parquet, via DuckDB) 57 control(s), 4 fail, 9 indeterminate, 44 pass
```

**44 passing · 4 failing · 9 not established · 0 could not run.** The same,
number for number, as when the study ran Prama in its own process.

Scoping each pass matters. Running every control against every source would
produce a table-not-found error for each control that lives elsewhere, and forty
of those bury the findings that are real.

## What to look at in the console

The study ends by printing where to look, in the console of the server it used
(it starts none of its own): sign in with the run's estate, `acme-group-<timestamp>`.

| Page | What is worth seeing here |
|---|---|
| `/relationships` | The four declarations, and which are confirmed |
| `/estate` | Five datasets across two sources, one map |
| `/incidents` | The two orphan findings, with counts |
| `/evidence` | 79 records from **two** passes, one chain, verified |

## Files

| File | What it is |
|---|---|
| `generate.py` | Builds both sources and plants the defects |
| `run.py` | Declares the estate *and the relationships*, runs two passes |
| `workspace/warehouse.db` | The SQLite warehouse |
| `workspace/landing/` | The CSV and Parquet files, including the published masters |
| `workspace/landing.duckdb` | Views over them |
