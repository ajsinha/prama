# Controls, proposals, derivation and runs from Python

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.

These namespaces are the stages a case study walks — declare, derive (Γ),
accept, run, read — and everything around them the console's control pages
and `prama control …` offer:

| Namespace | What it does | Scope |
|---|---|---|
| `client.controls` | The estate of controls: list, read, history, author, activate, suppress, retire; preview and backtest; the rule builder; imports | `control:read`, `control:propose` to author, `control:approve` to decide |
| `client.pql` | The language: check, explain, compile (optionally fused), format, completions, hover, function coverage. Stores nothing | `control:read` |
| `client.derive` | Γ over a declared dataset or relationship: the controls, what could not be derived and why, comparison specs | `control:read` to look, `control:propose` to declare, `control:approve` to accept |
| `client.proposals` | The proposal queue: list, accept, reject, past rejections | `control:read`, `control:approve` to decide |
| `client.runs` | Runs the **server** performs against a registered connection, and their evidence | `control:approve` to run, `evidence:read` to read |
| `client.schedule` | Each active control's schedule, what is due, and a scheduler tick on demand | `control:read`, `control:approve` to tick |

Every method works on `Client` and `AsyncClient`; the examples use the
synchronous client. The server-side logic is `prama.controls`, which the
console and the CLI call too, so all three give the same answers.

## Declare, derive, accept

A dataset is described in business terms. A code list or a range on an
attribute is a *value domain*, and Γ turns it into a control:

```python
import prama_sdk as prama

client = prama.connect()
estate = client.as_key(client.tenants.create("acme-trades", "Acme Trades")["credentials"]["api_key"])

trades = estate.datasets.declare(
    "trades",
    criticality=3,
    shape="table",
    grain={"attributes": ["trade_id"], "statement": "one row per executed trade"},
    rhythm={"frequency": "daily", "arrival_by": "07:00"},
    tags=["MiFIR"],
)
estate.datasets.add_attribute(trades["id"], "trade_id", optionality="mandatory")
estate.datasets.add_attribute(trades["id"], "ccy", codelist=["USD", "EUR", "GBP"])
estate.datasets.add_attribute(trades["id"], "quantity", minimum=0, maximum=1_000_000)
```

Look at what Γ derives before anything is stored, then declare and accept it:

```python
seen = estate.derive.preview_dataset(trades["id"])
for item in seen["unsatisfiable"]:
    print("not derived:", item["reason"])       # always read this list too

made = estate.derive.dataset(trades["id"], accept=True, schedule="daily")
print(made["declared"], "declared,", made["active"], "active")
```

`declare=True` stores the controls as proposals for somebody else to accept;
`accept=True` also activates them, and needs `control:approve`. Each derived
control in the answer carries `control` — the stored control, with its `id`.

A relationship derives the controls only it implies. Its comparison specs come
back with runnable `pql` where PQL can say them, and are never declared for
you: a reconciliation needs a reviewer to say how amounts are normalised.

```python
link = estate.relationships.declare(
    "references", trades["id"], accounts["id"],
    match_keys=[{"left": "account_id", "right": "account_id"}],
)
estate.derive.relationship(link["id"], accept=True)   # refused unless confirmed
```

## Run, on the server

Register where the data is, then run. The server opens the source itself; no
rows travel from your process.

```python
book = estate.connections.create("trading book", "sqlite", config={"path": "/data/book.db"})
report = estate.runs.start(book["id"], datasets=["trades"])
print(report["summary"])
for outcome in report["outcomes"]:
    print(outcome["verdict"], outcome["dataset"], outcome["metrics"])
```

Three kinds of connection can be run this way:

| `source_type` | `config` | Reads |
|---|---|---|
| `sqlite` | `{"path": "…/book.db"}` | one SQLite file, read-only |
| `duckdb` | `{"path": "…/landing.duckdb"}` | one DuckDB file — often views over CSV and Parquet |
| `files` | `{"path": "…/landing"}`, optionally `{"tables": {"name": "sub/file.csv"}}` | a directory: each `.csv`, `.parquet`, `.jsonl` file a table named after it, each sub-directory of like files a table named after the directory |

`datasets` scopes a pass to what this source holds, as a case study does one
pass per source; other controls are reported under `not_run` as on another
source rather than run and failed. `samples=True` keeps failing rows as
evidence (they are personal data on a retention clock); `due_only=True` runs
only what each control's schedule says is due.

**What the server will read is the operator's decision, not the connection's.**
A connection's path is data that anybody with `declaration:write` can set, so
a run only opens paths under `runs.roots` in the server's configuration, and
refuses outright if a root contains Prama's own database. With no roots set,
nothing is opened. The engine is fenced as well as the path: a DuckDB source
cannot read files outside the roots even from a `CUSTOM SQL` control, and every
statement must be a single read-only query. See
`src/prama/connect/sources/confined.py`.

The run is recorded exactly as `prama control run` records it — one evidence
record per control in the hash-chained ledger — and can be read back:

```python
run = estate.runs.get(report["run_id"])
print(run["verdicts"], [r["record_hash"] for r in run["records"]])
estate.runs.list(unfinished=True)            # runs that started and never reported
```

Before approving a control, try it against the same connection. A preview or
backtest records nothing:

```python
tried = estate.controls.preview(pql, book["id"])
history = estate.controls.backtest(pql, book["id"], "as_of_date", days=20)
print(history["summary"])
```

## A control's life

```python
c = estate.controls.declare(
    "CHECK positions HAS UNIQUE KEY (account_id) SEVERITY minor", schedule="06:30"
)                                                    # a proposal
estate.controls.activate(c["id"], reason="reviewed")  # control:approve
estate.controls.suppress(c["id"], until="2030-01-01T00:00:00+00:00", because="vendor outage")
estate.controls.retire(c["id"], reason="replaced")
[v["status"] for v in estate.controls.history(c["id"])]
# ['proposed', 'active', 'suppressed', 'retired']
```

Declaring the same `identity` again amends that control; identical text
changes nothing. An unreadable schedule is refused at declaration, because it
is a control that would never run.

## The proposal queue

```python
queue = estate.proposals.list(dataset_id=trades["id"])
p = queue["proposals"][0]
estate.proposals.accept(p["identity"], p["pql"], rule=p["rule"], dataset_id=trades["id"])
estate.proposals.reject(other["identity"], other["content_hash"], reason="not_material")
```

The queue also lists `unsatisfiable` and `deferred` items and counts what was
already accepted or rejected. A rejection is keyed on the text, so the same
proposal is not offered again, and a materially different rewrite is.

## The language

```python
estate.pql.check(text)                     # findings, against the estate's datasets
estate.pql.check(text, catalogue=cat)      # or against `prama lsp catalogue` output
estate.pql.explain(text)                   # sentences, and spreadsheet divergences
estate.pql.compile(text, dialect="duckdb", fuse=True)
estate.pql.functions(engine="sqlite")      # what share of the functions runs there
estate.controls.build("positions", "in_list", column="currency", values="GBP, USD",
                      because="the currencies we settle in")
estate.controls.import_(open("schema.yml").read(), "dbt", declare=True)
```

`compile` names every control it could not compile and why, and each plan
carries its residual — what the SQL screened but did not decide. An import
lists what did not come across one by one.

## The schedule

`estate.schedule.get()` lists every active control's schedule, whether it is
due, and — for the estate the server's scheduler runs — its recent ticks.
`estate.schedule.run_now()` runs one tick; it is refused when the scheduler is
off, or runs a different estate.
