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

```bash
cd case-studies/03-mixed-estate
python run.py                 # build, run, and serve the console on :8803
python run.py --no-serve      # build and run, print the report, stop
```

## What was planted, and what happened

| # | Defect | Rows | Found? |
|---|---|---|---|
| 1 | Trades naming an instrument not in the master | 37 | ✅ **37 of 4,000** — integrity |
| 2 | Trades naming a counterparty not in the master | 14 | ✅ **14 of 4,000** — integrity |
| 3 | `market_value` missing (a CDE) | 11 | ✅ **11 of 60** — completeness |
| 4 | Ledger adjusted with no matching position move | 1 | ⚠️ declared, not executed here |

Defects 1 and 2 are the ones the first two studies could not touch. They are
found here for one reason: somebody declared what is true between the datasets.

```python
RelationshipDeclaration(
    kind=RelationshipKind.REFERENCES,
    from_dataset_id="trade_feed",
    to_dataset_id="instrument_master",
    match_keys=(MatchKey(left="isin", right="isin"),),
    description="Every trade names an instrument the master knows about.",
)
```

Γ turns that into:

```
CHECK trade_feed.isin REFERENCES instrument_master.isin
  SEVERITY major DIMENSION integrity
  BECAUSE 'records here point at records there'
```

## ⚠️ The reconciliation is declared and not executed

The ledger break needs a reconciliation, and this study **declares** one:
positions against the book of record, matched on book, comparing market value,
within a dollar or a basis point.

Γ turns that into a **comparison specification**, not a control — and that is
correct. A reconciliation is matching, normalisation, tolerance and break
classification; it is not one SQL predicate. The engine that executes it
(`prama.recon`) is not wired into the control runner, so the run prints:

```
DECLARED BUT NOT EXECUTED HERE
  ≈ reconciliation: position_feed against general_ledger
```

The declaration is stored and visible in the console. The finding is not
claimed. That distinction is the whole discipline of these studies.

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

```
warehouse (SQLite)                      instrument_master, counterparty_master, general_ledger
landing zone (CSV + Parquet, DuckDB)    trade_feed, position_feed, + the published masters
```

Scoping each pass matters. Running every control against every source would
produce a table-not-found error for each control that lives elsewhere, and forty
of those bury the findings that are real.

## What to look at in the console

`http://127.0.0.1:8803`

| Page | What is worth seeing here |
|---|---|
| `/relationships` | The four declarations, and which are confirmed |
| `/estate` | Five datasets across two sources, one map |
| `/incidents` | The two orphan findings, with counts |
| `/evidence` | 80 records from **two** passes, one chain, verified |

## Files

| File | What it is |
|---|---|
| `generate.py` | Builds both sources and plants the defects |
| `run.py` | Declares the estate *and the relationships*, runs two passes |
| `workspace/warehouse.db` | The SQLite warehouse |
| `workspace/landing/` | The CSV and Parquet files, including the published masters |
| `workspace/landing.duckdb` | Views over them |
