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
**feeds**, and a feed has a *rhythm*. That is what should turn "the file never
came" from an absence nobody notices into something Prama reports — and, run
through the SDK, this study shows that it does not yet: see
[the arrival report](#the-arrival-report-and-why-this-run-has-none).

> **A feed is not a file; it is a contract about arrival.**
> Three of the nine defects here are invisible to every content check, because
> there is nothing wrong with the rows — there are no rows, or there are twice
> as many as there should be.

## Run it

The study is a client of **your** Prama server: it signs in through the SDK
(`prama_sdk`), creates an estate of its own for the run, and transacts into it.
It starts no server and opens no Prama database.

```bash
prama serve                               # or python run_prama_web.py, if not already running
cd case-studies/02-feeds-csv-parquet
python run.py                             # the server config/application.yaml names
python run.py --config other.yaml         # another server: its server.host and server.port
python run.py --username ada --password … # as somebody else (default: the dev admin)
```

**The server reads the files, not the study**, so the server must be allowed to:
add this checkout's `case-studies` directory to `runs.roots` in the server's
`application.yaml` (or `application.local.yaml`) and restart it. Without that,
the run stops at stage 4 and says which setting to change.

Every run rebuilds the landing zone from the same seed and gets a fresh estate
(`acme-feeds-<timestamp>`), so a rerun starts clean and the numbers below repeat.

## The JSON Lines feed

Settlement instructions arrive as JSON Lines, one record per line. They are declared like any
other feed, and Prama derives their controls from the declaration:

| Planted | Rows | Found by |
|---|---:|---|
| Negative settlement amount (the direction written into the sign) | 9 | the derived `amount >= 0` check: **9 of 600** |
| Status `UNKNOWN`, which the settlement system never sends | 5 | the derived `status IN (…)` check: **5 of 600** |

## How the files are read

The landing zone is registered with Prama as one **`files` connection**, and the
server reads it with an in-memory DuckDB: CSV, Parquet and JSON Lines **in
place**. Nothing is copied and nothing is loaded; the files on disk stay the
source of truth. The connection names each feed's table and the files that make
it up, so a feed that lands one file a day is one table:

```python
TABLES = {
    "trade_feed": "trades/*.csv",
    "position_feed": "positions/*.parquet",
    "instrument_feed": "instruments/*.parquet",
    "counterparty_feed": "counterparties/*.csv",
    "settlement_feed": "settlements/*.jsonl",
}
```

```
workspace/landing/
  trades/       TRADES_20260826_001.csv  …  (+ a .trl trailer beside each)
  positions/    POSITIONS_20260908.parquet
  instruments/  INSTRUMENTS_20260908.parquet
  counterparties/ COUNTERPARTIES_20260908.csv
  settlements/  SETTLEMENTS_20260908.jsonl   (one JSON record per line)
workspace/landing.duckdb     ← five views, built by generate.py; the run does not use it
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
| 5 | A day's file never arrived | 400 | ❌ **not claimed** — the arrival judgement is not reachable through the SDK; see below |
| 6 | A file truncated mid-transfer | 200 | ❌ trailer check not wired to the runner |
| 7 | LEI checksum wrong | 2 | ⚠️ not established — screen only |

The run as a whole: Γ derives **54 controls** from the five declarations (and lists seven it
could not derive), the server runs them against the `files` connection, and the report reads
**39 passing · 7 failing · 8 not established · 0 could not run**, over an evidence chain of 54
records that verifies. The content findings are the same, number for number, as when the study
ran Prama in its own process; only the arrival report is gone.

## The arrival report, and why this run has none

Content controls cannot see a missing file. Arrival is judged from the
**filenames**, against two declarations:

- **A filename pattern.** `TRADES_{YYYYMMDD}_{SEQ:3}.csv`. The business date
  lives in the filename and nowhere else, so a platform that treats the name as
  an opaque string cannot tell a late file from a duplicate from a file for the
  wrong day.
- **A business calendar.** Without one, every Saturday is a missing delivery,
  and a report that cries wolf twice a week is not read by the third week.

Prama has that judgement (`prama.connect.feed`). Before this study drove the
server through the SDK, it ran it in its own process and printed:

```
ok         2026-09-02  TRADES_20260902_001.csv
MISSING    2026-09-03  nothing arrived
ok         2026-09-04  TRADES_20260904_001.csv
DUPLICATE  2026-09-07  2 files: TRADES_20260907_001.csv, TRADES_20260907_002.csv
```

**The server does not expose it.** There is no API endpoint, and so no SDK
method, that takes a feed's pattern and calendar and says which expected
deliveries arrived. The study does not work the answer out itself: a report
computed in the study would be the study's finding presented as Prama's. So the
missing 2026-09-03 file is planted, counted in the planted list, and **not
claimed**, and the run says so at the end:

```
NOT CLAIMED IN THIS RUN — the missing 2026-09-03 delivery.
```

Nor does Γ derive a freshness control for any of these feeds: each declares
when it arrives (`arrival_by`) but no column records the arrival, and Γ says so
in its unsatisfiable list rather than inventing one.

The duplicated 2026-09-07 delivery **is** found, by content: the declared grain
(one row per `trade_id`) sees every trade twice — **400 duplicates in 3,800**.

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

The study ends by printing where to look, in the console of the server it used
(it starts none of its own): sign in with the run's estate, `acme-feeds-<timestamp>`.
The interesting page here is `/controls`: every control shows its **schedule**
derived from the declared rhythm ("at 06:30 on weekdays business days"), and a
schedule Prama cannot read is flagged in red, because a control that silently
stops being scheduled is indistinguishable from one that is passing.

## Files

| File | What it is |
|---|---|
| `generate.py` | Builds the landing zone and plants the defects |
| `run.py` | Declares the five feeds and drives your Prama through the SDK |
| `workspace/landing/` | The actual CSV, Parquet and JSON Lines files |
| `workspace/landing.duckdb` | Five views over them, built by the generator; not used by the run |

Prama's own records are the server's, in the estate the run created; nothing of Prama's is
written to the workspace.
