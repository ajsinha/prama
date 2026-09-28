# Case study 2 — daily feeds: CSV, Parquet and JSON Lines

<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt;. All rights reserved.<br/>
Proprietary and confidential.</sub>

---

## What this shows

A landing zone, not a database. Five feeds arrive daily:

- trades and counterparties as **CSV**, written by a vendor or a mainframe;
- positions and instruments as **Parquet**, written by an analytics platform;
- settlement instructions as **JSON Lines** (one record per line), written by the settlement
  system.

Ten business days, 3,800 trade rows, 600 settlement instructions and nine planted defects.

The difference from case study 1 is one word in the declaration: these are
**feeds**, and a feed has a *rhythm*. That is what turns "the file never came"
from an absence nobody notices into something Prama reports.

> **A feed is not a file; it is a contract about arrival.**
> Three of the nine defects here are invisible to every content check, because
> there is nothing wrong with the rows — there are no rows, or there are twice
> as many as there should be.

## Run it

```bash
cd case-studies/02-feeds-csv-parquet
python run.py                 # build, run, and serve the console on :8802
python run.py --no-serve      # build and run, print the report, stop
```

## The JSON Lines feed

Settlement instructions arrive as JSON Lines, one record per line. They are declared like any
other feed, and Prama derives their controls from the declaration:

| Planted | Rows | Found by |
|---|---:|---|
| Negative settlement amount (the direction written into the sign) | 9 | the derived `amount >= 0` check: **9 of 600** |
| Status `UNKNOWN`, which the settlement system never sends | 5 | the derived `status IN (…)` check: **5 of 600** |

## How the files are read

DuckDB reads CSV, Parquet and JSON Lines **in place**. Nothing is copied and
nothing is loaded: the files on disk stay the source of truth, and one small
`.duckdb` file holds five views over them.

```
workspace/landing/
  trades/       TRADES_20260826_001.csv  …  (+ a .trl trailer beside each)
  positions/    POSITIONS_20260908.parquet
  instruments/  INSTRUMENTS_20260908.parquet
  counterparties/ COUNTERPARTIES_20260908.csv
  settlements/  SETTLEMENTS_20260908.jsonl   (one JSON record per line)
workspace/landing.duckdb     ← five views, opened read-only
```

The trailer is a **sidecar** `.trl` file rather than a last line inside the CSV.
Both patterns exist; the sidecar leaves the data file readable by anything that
reads CSV, and an in-band trailer of a different width is why half the loaders
in a bank need a custom parser.

## What was planted, and what happened

| # | Defect | Rows | Found? |
|---|---|---|---|
| 1 | A file resent and both copies loaded | 400 | ✅ **400 duplicates in 3,800** |
| 2 | `market_value` missing (a CDE) | 18 | ✅ **18 of 60** — completeness |
| 3 | `currency` = `US$` | 9 | ✅ **9 of 60**, twice — codelist and semantic type |
| 4 | `price` above the declared cap | 5 | ✅ **5 of 3,800** — the declared range |
| 5 | A day's file never arrived | 400 | ✅ **arrival report** — see below |
| 6 | A file truncated mid-transfer | 200 | ❌ trailer check not wired to the runner |
| 7 | LEI checksum wrong | 2 | ⚠️ not established — screen only |

## The arrival report

Content controls cannot see a missing file. The run ends with a separate pass
that reads the **filenames**:

```
ok         2026-09-02  TRADES_20260902_001.csv
MISSING    2026-09-03  nothing arrived
ok         2026-09-04  TRADES_20260904_001.csv
DUPLICATE  2026-09-07  2 files: TRADES_20260907_001.csv, TRADES_20260907_002.csv
```

Two things make this work, and both are declarations:

- **A filename pattern.** `TRADES_{YYYYMMDD}_{SEQ:3}.csv`. The business date
  lives in the filename and nowhere else, so a platform that treats the name as
  an opaque string cannot tell a late file from a duplicate from a file for the
  wrong day.
- **A business calendar.** Without one, every Saturday is a missing delivery,
  and a report that cries wolf twice a week is not read by the third week. This
  study uses a weekdays calendar; a real one names TARGET2 or its own holiday
  file.

## ❌ The truncated file, and why it is not claimed

Half of one day's file is missing. Every row that *did* arrive is perfectly
valid — so no content control notices, and the trailer count is the only thing
that would.

Prama has that machinery (`prama.connect.feed` — trailer counts, hash totals,
manifests) and it runs at **arrival**, not as SQL over rows that already landed.
It is not wired into the control runner, so this study plants the defect, says
so, and does not claim it. The alternative — quietly omitting the defect — would
make the study look better and mean less.

## What to look at in the console

`http://127.0.0.1:8802` — same pages as case study 1. The interesting one here
is `/controls`: every control shows its **schedule** derived from the declared
rhythm ("at 06:30 on weekdays business days"), and a schedule Prama cannot read
is flagged in red, because a control that silently stops being scheduled is
indistinguishable from one that is passing.

## Files

| File | What it is |
|---|---|
| `generate.py` | Builds the landing zone and plants the defects |
| `run.py` | Declares the five feeds, drives Prama, prints the arrival report |
| `workspace/landing/` | The actual CSV, Parquet and JSON Lines files |
| `workspace/landing.duckdb` | Five views over them, read-only |

Prama's own records go to the application's database, not the workspace.
