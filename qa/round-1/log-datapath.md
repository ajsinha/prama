<!--
Prama — QA execution log: the data path, end to end.
Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary. No licence is granted except by separate written agreement.
-->

# QA log — the data path, end to end

Cases: `cases-datapath.md`, written in full before execution began.
Run on 2026-09-12/13, Python 3.13.15, SQLite and DuckDB, on this clone.

**The tree moved under this pass.** At the first command `git rev-parse HEAD` was
`46b4b3c`; part-way through it was `3b82e40`, and nine files under `src/` were modified
in the working tree by a concurrent session. Two consequences are recorded honestly
below: DP-112 produced a 500 against a server holding stale bytecode and was re-run
against the current tree (it passes), and everything marked as a defect was re-confirmed
against the tree as it stood at the end of the pass.

Workspace `/tmp/qa-datapath/`: `build_corpus.py`, `oracle.py`, `suite.pql`, `extra.pql`,
`load_controls.py`, `read_evidence.py`, `export_bundle.py`. Servers ran on 19510/19511
and were stopped; none is left running.

---

## 1. Setup and corpus integrity

### DP-001 — corpus generator's own arithmetic — **PASS**
All four published-identifier assertions held (`US0378331005`, `5493001KJTIIGC8Y1R12`,
`7LTWFZYICNSX8D621K86`, `GB82WEST12345698765432`), as did the round-trips
(`lei_of("5493001KJTIIGC8Y1R") == "5493001KJTIIGC8Y1R12"` etc.). 1,000 rows written.

Two self-inflicted corpus errors were caught by DP-002 before any Prama case ran, and
are recorded because they are the reason DP-002 exists: `notional` was first stored
`round(q*p, 6)`, which made 348 rows differ from `quantity * price` under IEEE-754
equality rather than the 11 planted; and the "shape-invalid" IBANs (`GB1` + 18 digits)
still matched the ISO 13616 screen. Both were fixed in the generator and the whole
corpus rebuilt before execution.

### DP-002 — independent oracle agrees with the plant — **PASS**
```
ORACLE AGREES WITH THE PLANT
```
25 counts recomputed from the written database with plain Python and plain SQLite; every
one equals the planted count.

### DP-003 — `db init` — **PASS**
`schema created: 35 tables, 99 statements from schema/sqlite.sql (digest 5df0746f832e)`

### DP-004 — `db verify` — **PASS**
`schema verified … no drift`

### DP-005 — `tenant create` — **PASS**
`01M2C2BAXWQE9RNSF7Q5Y8993Q`; `tenant list` marks it with `*`.

### DP-006 — the suite loads and is live — **PASS**
35 controls declared and activated as `qa-001` … `qa-035`; the console later reports
`Running 43` after the 8 extras, `Proposed, not running 0`.

---

## 2. Authoring

### DP-007 — `control check` parses the suite — **PASS**
`35 control(s) read from suite.pql.`, exit 0.

### DP-008 — one `unchecked` finding per dataset — **PASS**
Exactly three, one each for `trades`, `trades_empty`, `trades_missing` — not one per
control, as the command's own docstring promises.

### DP-009 — the redundant control is found — **PASS**
> `[warning] this control adds nothing: trades.counterparty_lei IS VALID 'lei' already
> fails on a null, because an unknown counts as a violation`

and separately `this control computes exactly what another already computes` for the
`qa-002`/`qa-035` pair. The four `rate_col_a` controls that differ only in threshold were
correctly *not* flagged.

### DP-010 — `--strict` is a CI gate — **PASS**
exit 1 where plain `check` exits 0.

### DP-011 — syntax error names the clause — **PASS**
```
expected the reason this control exists, in quotes, and found '"double quotes"' (at line 1, column 43)
  CHECK trades.trade_id IS NOT NULL BECAUSE "double quotes"
                                            ^^^^^^^^^^^^^^^
→ Quoted text is written between single quotes: 'like this'.
```

### DP-012 — `TREAT UNKNOWN AS PASS` needs a `BECAUSE` — **PASS**
Refused at parse time, with the remedy naming what to write.

### DP-013 — non-deterministic function refused — **FAIL**
`CURRENT_DATE()` and `NOW()` are refused, with an excellent message. Bare `CURRENT_DATE`
— the ANSI spelling, and the one PostgreSQL accepts — is **not**. It parses as a column
reference and compiles to:
```
CHECK trades SATISFIES trade_date < CURRENT_DATE   →  exit 0, no finding
SELECT … CASE WHEN NOT COALESCE(("trade_date" < "CURRENT_DATE"), 0) …
```
`prama control check` reports nothing and `compile` emits it. On PostgreSQL that query
is valid SQL reading the clock, which is the exact thing the guard exists to prevent; on
SQLite it silently becomes a comparison against the string `'CURRENT_DATE'` (see DP-059
for the same quoting quirk). The parser's `NON_DETERMINISTIC` set is consulted only for
`FunctionCall` nodes.

### DP-014 — `explain` renders 35 sentences — **PASS**
No SQL, no identifiers a business owner would not recognise. e.g.
> *In trades, every counterparty_lei has a value. No violations are allowed. A failure is
> major. This exists because: counterparty is a CDE for EMIR.*

### DP-015 — thresholds are in the sentence — **PASS**
`Up to 5% of rows may violate it.` / `Up to 50 violating rows are tolerated.`

### DP-016 — the unknown policy is in the sentence — **PASS**
`… and a row whose value cannot be determined is allowed to pass.` appears on `qa-004`
and `qa-006` and on neither of their defaults.

### DP-017 — `compile --dialect sqlite` — **PASS**
35 `SELECT`s, 0 refusals.

### DP-018 — the `IS NOT NULL` SQL matches the sentence — **PASS**
```
SELECT COUNT(*) AS "scanned_rows", COALESCE(SUM(CASE WHEN NOT COALESCE(("counterparty_lei" IS NOT NULL), 0) THEN 1 ELSE 0 END), 0) AS "violating_rows"
FROM "trades"
```

### DP-019 — the `WHERE` clause reaches the SQL — **PASS**
`WHERE ("status" = 'ACTIVE')` on `qa-009` only.

### DP-020 — the unknown policy changes the SQL — **PASS**
`NOT COALESCE((pred), 0)` versus `COALESCE(NOT (pred), 0)`. (Whether that is *sufficient*
is DP-064.)

### DP-021 — `IS VALID 'lei'` is a screen and the compiler knows — **PASS**
`is_complete = False`, `residual_validators = (('lei', 'counterparty_lei'),)`; the emitted
predicate is the ISO 17442 shape regex alone.

### DP-022 — `compile` discloses that the query is a screen — **FAIL**
`prama control compile` prints the sentence and the SQL and says nothing about the
residual. The console's `/controls/compile` on the same control *does*:
> *This query does not decide the control on its own. It applies a screen — a necessary
> condition — and the rows that pass must still be checked exactly before a pass may be
> reported: lei on counterparty_lei*

So the fact is available, the CLI surface simply drops it. A DBA who asks for the SQL
before granting access gets a query that looks like the whole test.

### DP-023 — `IN CODELIST iso4217` compiles — **FAIL**
```
-- CHECK trades.currency IN CODELIST 'iso4217'
--   cannot be compiled: the codelist 'iso4217' is not registered
--   Next: Register it before compiling, or write the values out.
```
`iso4217` *is* registered — `prama.classify.codelists.default_registry().names()` and the
module-level `REGISTRY` both list it, and the runner resolves it perfectly (DP-023b). The
cause is that `ControlCompileCommand.run` builds a bare `Lowerer()` instead of calling
`prama.ir.resolve.resolved()`, whose module docstring says in terms:

> *So there is one function that lowers a control properly, and every call site uses it.
> The alternative — each caller remembering — is how three of six call sites end up subtly
> different.*

Consequences: the remedy is false ("register it" — it is registered), `compile` exits 0
anyway so a CI gate built on it would not notice, and **`compile` and `run` disagree about
whether the control is runnable at all.**

**DP-023b (follow-up, run):** loaded as `qb-008` and executed — `fail`, `scanned_rows`
1000, `violating_rows` **14**, which is exactly the 9 bad codes + 5 NULLs, and identical
to the hand-written `IN (…)` list. The runner's plan id matches `resolved()`'s. So the
feature works and only the CLI's compile path is broken.

### DP-024 — `--fuse` — **PASS**
`35 control(s) in 5 scan(s) — 30 fewer passes over the data than running them separately.`

### DP-025 — `format` is idempotent — **PASS**
`diff fmt1.pql fmt2.pql` empty; re-checking the formatted file gives the same findings.

### DP-026 — `control functions` — **PASS**
```
33 function(s) in the catalogue.
  duckdb 33/33 (100%)   postgresql 33/33 (100%)   sqlite 32/33 (97%)  refused: ROUND
```

---

## 3. Execution against real data

One `prama control run --against data.sqlite --dialect sqlite` produced all of these.

| Case | Control | Expected | Actual | |
|---|---|---|---|---|
| DP-027 | `qa-001` trade_id not null | pass, 1000/0 | pass, 1000/0 | **PASS** |
| DP-028 | `qa-002` lei not null | fail, 7 | fail, 7 | **PASS** |
| DP-029 | `qa-003` currency in list | fail, 14 | fail, 14 | **PASS** |
| DP-030 | `qa-004` + unknown-as-pass | fail, 9 | fail, 9 | **PASS** |
| DP-031 | `qa-005` qty_check > 0 | fail, 16 | fail, 16 | **PASS** |
| DP-032 | `qa-006` + unknown-as-pass | fail, 6 | fail, 6 | **PASS** |
| DP-033 | `qa-007` quantity between | fail, 4 | fail, 4 | **PASS** |
| DP-034 | `qa-008` side in list | fail, 3 | fail, 3 | **PASS** |
| DP-035 | `qa-009` + WHERE active | fail, 900 scanned, 3 | fail, 900/3 | **PASS** |
| DP-036 | `qa-010` notional = q × p | fail, 11 | fail, 11 | **PASS** |
| DP-039 | `qa-013` row count 900–1100 | pass, 1000 | pass, 1000 | **PASS** |
| DP-040 | `qa-014` row count 2000–3000 | fail | fail | **PASS** |
| DP-041 | `qa-015` referential integrity | fail, 15 | fail, 15 | **PASS** |
| DP-048 | `qa-022` MATCHES regex | pass, 0 | pass, 0 | **PASS** |
| DP-049 | `qa-023` length 6–6 | pass, 0 | pass, 0 | **PASS** |
| DP-050 | `qa-024` BELOW 5 %, 50 nulls | pass, 50 | pass, 50 | **PASS** |
| DP-051 | `qa-025` BELOW 5 %, 51 nulls | fail, 51 | fail, 51 | **PASS** |
| DP-052 | `qa-026` BELOW 4 % | fail, 50 | fail, 50 | **PASS** |
| DP-053 | `qa-027` AT MOST 50 ROWS | pass, 50 | pass, 50 | **PASS** |
| DP-054 | `qa-028` AT MOST 49 ROWS | fail, 50 | fail, 50 | **PASS** |
| DP-056 | `qa-030` unique key, empty | indeterminate | indeterminate | **PASS** |
| DP-057 | `qa-031` row count, empty | fail, 0 scanned | fail, 0 | **PASS** |

Every count above is the planted count. The threshold flips between 50 and 51 rows and
between `AT MOST 50` and `AT MOST 49`, exactly where the declaration says it should.

### DP-037 — `qa-011` unique key on trade_id — **FAIL (evidence incomplete)**
Verdict `fail` — correct. `scanned_rows` 1000, `distinct_keys` **995**, `null_key_rows` 0
— all correct. But **`duplicate_rows` and `violating_rows` are not in the record at all.**
`judge()` derives both in `_derive()`; `ControlRun._run_one` passes the *raw* metric dict
into `EvidenceRecord` and discards `result.metrics`. The ledger therefore records that a
uniqueness control failed without recording how many rows offended.

### DP-038 — `qa-012` unique key with NULL keys — **FAIL (same cause)**
`distinct_keys` **993**, `null_key_rows` **3** — both correct, and the derivation from
them (997 identified − 993 distinct = 4 duplicates, + 3 null keys = 7 violations) is the
planted answer. The two derived numbers are absent from the record for the same reason as
DP-037. The *arithmetic* is right; the *evidence* is not complete.

### DP-042 — `qa-016` functional dependency — **FAIL (same cause)**
`distinct_determinants` **5**, `distinct_pairs` **7** — correct; the implied 2 offending
determinants is the planted answer; `violating_rows` is absent from the record.

### DP-043 — `qa-017` `IS VALID 'lei'` — **FAIL**
Expected `fail` with `violating_rows` 11 **and a disclosure that 11 is a lower bound**.
Actual: `fail`, `violating_rows` **11**, `detail` **empty**, `coverage` **"full"**.
The column holds 23 real violations (4 shape, 12 check-digit, 7 null). The record states
11 as a completed measurement of a column the query only screened.

The asymmetry is exact and is in `ControlRun._run_one`: the lower-bound disclosure is
attached **only when the verdict would otherwise be `pass`**. As soon as the screen finds
one violation the verdict becomes `fail` and the caveat is dropped — so the understatement
is disclosed precisely when it is zero and hidden whenever it is not.

### DP-044 — `qa-018` `IS VALID 'isin'` — **FAIL**
`fail`, `violating_rows` **3** of **9** real violations, no disclosure.

### DP-045 — `qa-019` `IS VALID 'iban'` — **FAIL**
`fail`, `violating_rows` **2** of **10** real violations, no disclosure.

### DP-046 — `qa-020` the false-pass test — **PASS**
The case this product most needs to get right, and it gets it right.
1,000 shape-valid LEIs, 12 with wrong check digits, no nulls. The screen returns
`violating_rows` 0 and the verdict is **not** pass:
```
qa-020  indeterminate  1000  0
  the query applied a screen rather than the exact test, so the violation count is a
  lower bound; the residual (lei on lei_shapeok) has not been run, and a pass cannot be
  reported from a screen alone
```

### DP-047 — `qa-021` the same for ISIN — **PASS**
`indeterminate`, `violating_rows` 0, residual `(isin on isin_shapeok)` named.

*Note on DP-043–047 together:* the residual validators exist and work
(`prama.classify.validators`), but **nothing in the CLI data path ever runs them.** The
two-stage design's first stage is implemented and its second is not reachable from
`prama control run`; the product's answer for a check-digit failure is `indeterminate`
forever, or an understated `fail`.

### DP-055 — `qa-029` the empty-scan test — **FAIL**
```
qa-029  pass  scanned_rows 0  violating_rows 0
```
An empty table reported **green**. This contradicts the product's own thesis in four
places it states it itself:

* `execute/run.py` module docstring: *"An incomplete screen cannot report a pass … Zero
  violations from a lower bound is not 'clean'; it is 'not established'."*
* `ir/model.py::Threshold.evaluate`: *"No rows to judge. Not a pass and not a failure: an
  empty scope is a fact about the scope, and calling it a pass is how a broken feed
  reports green."* — but that branch is reached only when `relative_to` is set, i.e. only
  for a **rate** threshold.
* `backend/execute.py::_distinctness_verdict` guards `scanned_rows == 0` explicitly.
* `execute/preview.py::_trial` has a `no_data` verdict for exactly this and uses it.

So three of the four judgement paths refuse an empty scope and the fourth — the plain
absolute threshold, which is what every `IS NOT NULL`, `IN (…)`, `BETWEEN`, `MATCHES`,
`SATISFIES` and `REFERENCES` control lowers to — reports a pass. The backtest screen and
the runner give different answers about the same empty table.

The scorecard then contradicts the ledger about the same records:
> *trades_empty — 0 % — 4 of 4 controls did not run — this describes 0 % of what was
> meant to be checked … nothing has been measured*

while the ledger holds a `pass` for `qa-029` and a `fail` for `qa-031` on that dataset.

### DP-058 — `qa-032` a table that does not exist — **PASS**
```
qa-032  error   OperationalError: no such table: trades_missing
run 01M2C2P2PD2CN3GHT5Z6ZVA91T
  35 control(s), 1 error, 23 fail, 3 indeterminate, 8 pass, 1 could not be executed at all
  ! trades_missing: OperationalError: no such table: trades_missing
```
The other 34 controls still produced verdicts; `prama control run` exits **1**.

### DP-059 — `qa-033` a column that does not exist — **FAIL**
```
qa-033  pass  scanned_rows 1000  violating_rows 0
```
A control on a column that is not in the table reported **green on 1,000 rows**.

Root cause, confirmed directly against the corpus:
```
sqlite> SELECT "no_such_column" FROM trades LIMIT 1;            →  ('no_such_column',)
sqlite> SELECT COUNT(*) FROM trades WHERE "no_such_column" IS NOT NULL;  →  1000
```
SQLite resolves a double-quoted identifier that matches no column as a **string literal**.
The compiler quotes every column reference that way, so on SQLite a renamed or dropped
column does not error — it becomes a constant, and every `IS NOT NULL`, `MATCHES`,
`IN (…)` and `IS VALID` control over it passes silently and for ever.

Cross-engine confirmation (DP-059b): the same control, same data, on DuckDB:
```
qa-033  error  BinderException: Referenced column "no_such_column" not found in FROM clause!
```
Two supported engines return a different **verdict** for one control on one dataset, which
is the failure the IR exists to make impossible. `prama control check` cannot catch it
either unless the dataset is declared with its attributes.

### DP-060 — `qa-034` `FOR EACH book` — **FAIL**
Expected a verdict per segment and totals equal to the unsegmented run (1000 scanned, 16
violating). Actual:
```
qa-034  fail  scanned_rows 200  violating_rows 3
```
The compiled SQL is right — `SELECT "book", COUNT(*) …, … GROUP BY "book"` — and returns
five rows. `ControlRun._run_one` then calls `_metrics_from(rows)`, which takes **`rows[0]`
only**, and `judge()` rather than `judge_segments()`. One book of five is judged and the
other four are discarded; the segment key itself is dropped because it is not numeric, so
the record does not even say which book it is about.

The same record contradicts itself: run with `--samples`, `qa-034` stores **16** sample
rows beside metrics that claim 3 violations in 200 rows.

Cross-engine (DP-060b): DuckDB gives `scanned_rows 200, violating_rows 7` for the same
control on the same data — a different answer again, because a different group happens to
come back first.

### DP-061 — `qa-035` the reporting clauses reach the record — **PASS**
`fail`, `violating_rows` 7, `dimensions: ["completeness"]`, `criticality: 1`. With
`--samples` it keeps 7 rows, within its declared `EVIDENCE samples (20)`.

*Observation (not a defect):* `qa-002` and `qa-035` differ only in `SEVERITY`,
`DIMENSION` and `EVIDENCE` and share an identical `plan_id`
(`ir:sha256:d89105e6…`). That is consistent with the plan identifying what is executed
rather than how it is reported, and the differing clauses do reach the record.

---

## 4. Unknown handling

### DP-062 — nulls are violations by default — **PASS**
14 − 9 = **5**, the exact number of NULL currencies.

### DP-063 — the same for a numeric comparison — **PASS**
16 − 6 = **10**, the exact number of NULL `qty_check`.

### DP-064 — `TREAT UNKNOWN AS PASS` reaches `IS VALID` — **FAIL (on SQLite)**
| | violations |
|---|---:|
| `qa-017` `IS VALID 'lei'` (default) | 11 |
| `qb-001` the same `TREAT UNKNOWN AS PASS` | **11** |

Expected 4 — the 7 NULLs are the only unknowns. The policy changes the emitted SQL
(DP-020) and changes nothing about the answer, because the SQLite `REGEXP` hook returns
**`False`** for a NULL value rather than NULL:

```python
def regexp(pattern, value):
    if value is None:
        return False      # ← collapses unknown into false
```
whose own docstring says the opposite:
> *"A None value matches nothing rather than raising: SQL's three-valued logic makes a
> null neither matching nor non-matching, and the control's TREAT UNKNOWN policy — not
> this function — decides what that means."*

Once the UDF has decided, the policy has nothing left to decide.

**DP-064b, cross-engine:** the same control on DuckDB returns **4** — the right answer.
So a control whose declaration explicitly forgives missing values counts them as
violations on one supported engine and not on another.

### DP-065 — `IS NOT NULL` is unaffected by the policy — **PASS**
7 and 7.

### DP-066 — an all-null scope does not pass silently — **PASS**
`qb-003` (`> 0 WHERE qty_check IS NULL`): `scanned_rows` 10, `violating_rows` 10, `fail`.
The classic "rule over an entirely null column passes for years" failure does not occur.

### DP-067 — the same, forgiven on purpose — **PASS**
`qb-004`: `scanned_rows` 10, `violating_rows` 0, `pass`, and the `BECAUSE` that justifies
it is stored with the control.

---

## 5. Thresholds

### DP-068 — a rate comes from one scan — **PASS**
Every predicate record carries `scanned_rows` beside `violating_rows`, so the rate is
recomputable from the evidence alone.

### DP-069 — the denominator is the filtered scope — **PASS**
`qb-005`: `scanned_rows` **900**, `violating_rows` 3, `pass` (0.33 % against 1 %).

### DP-070 — a rate over an empty scope is not a pass — **PASS**
`qb-006`: `indeterminate`. (Note the contrast with DP-055: the *same* empty table is
`indeterminate` under a rate threshold and `pass` under an absolute one.)

### DP-071 — `BELOW 5%` = `BELOW 0.05` — **PASS**
`qa-024` and `qb-007` both `pass` with `violating_rows` 50.

### DP-072 — absolute and rate agree at the same point — **PASS**
`AT MOST 50 ROWS` and `BELOW 5%` both pass; `AT MOST 49` and `BELOW 4%` both fail.

### DP-073 — the threshold survives to the record — **FAIL**
`explain` states it and the verdict honours it, but the evidence record does not carry it:
```
qa-024  pass  {'scanned_rows': 1000.0, 'violating_rows': 50.0}   ir:sha256:c6a1d293…
qa-026  fail  {'scanned_rows': 1000.0, 'violating_rows': 50.0}   ir:sha256:d5947d9b…
qa-027  pass  {'scanned_rows': 1000.0, 'violating_rows': 50.0}   ir:sha256:a24f5e8d…
qa-028  fail  {'scanned_rows': 1000.0, 'violating_rows': 50.0}   ir:sha256:0f5875af…
```
Four records, identical metrics, two passes and two fails. The sealed record (field list
confirmed from `evidence.ndjson`) holds no threshold and no control text — only
`plan_id`, `control_id` and `control_version`, which are pointers into a store an auditor
holding the bundle does not have. Chain integrity is intact; the record is not
self-explaining.

---

## 6. Evidence

### DP-074 — a record per control — **PASS**
35 records for a 35-control run, including the one that errored. 113 records after three
runs, 247 by the end of the pass.

### DP-075 — the run row is opened and closed — **PASS**
```
run: 01M2C2P2PD2CN3GHT5Z6ZVA91T complete | 35 control(s), 1 error, 23 fail, 3 indeterminate, 8 pass, 1 could not be executed at all
```
`record_count` 35; nothing left `running`.

### DP-076 — each record names its plan — **PASS**
No non-error record is missing a `plan_id`, and every stored `plan_id` equals
`resolved(control).plan_id` recomputed from the source text. Plan ids are stable across
runs.

### DP-077 — the record says what was scanned and what violated — **FAIL**
`scanned_rows` present on every record. `violating_rows` **absent** on `qa-011`, `qa-012`,
`qa-016`, `qa-030` — the uniqueness and functional-dependency controls (DP-037/038/042).
Its absence on `qa-013`, `qa-014`, `qa-031` is correct and by design: a row count has no
per-row violation.

### DP-078 — engine and dataset — **PASS** (`engine: sqlite`, dataset as targeted)

### DP-079 — snapshot reference — **PASS** (`{"kind": "wall_clock", "identifier": "2026-09-13T00:29:12.891074+00:00", "exact": false}`)

*Observation:* `coverage` is the literal string `"full"` on **every** record, including
`qa-020` and `qa-021`, whose own `detail` says the query was a screen and the control was
not established. The one field named for coverage is the one field that does not report
it.

### DP-080 — the chain is intact after a clean run — **PASS**
`35 record(s) verified. Chain head fff1566e4f52c3ec…, Merkle root e42dc83b1a9194a1…`;
first record's `previous_hash` is sixty-four zeros.

### DP-081 — a second run extends the chain — **PASS**
70 records, one chain, intact.

### DP-082 — determinism — **PASS**
`controls whose verdict/metrics changed between runs: none`.

### DP-083 — a sealed bundle verifies with the standalone script — **PASS**
```
$ python3 scripts/verify_evidence.py /tmp/qa-datapath/bundle
  [PASS] every record's content hashes to its stored content_hash
  [PASS] every record links to the one before it
  [PASS] sequence numbers are contiguous
  [PASS] the manifest's record count (113) matches the file (113)
  [PASS] the evidence file is the one the manifest describes
  [PASS] the Merkle root matches the records
  [PASS] the chain head matches the last record
Every check passed.                                        exit 0
```
The script imports nothing outside the standard library, and its closing paragraph
declines to overstate what a green result means.

### DP-084 — tampering with a live record is caught — **PASS**
`UPDATE ev_record SET verdict='pass', metrics_json='{"scanned_rows":1000.0,"violating_rows":0.0}'`
directly in SQLite, then `evidence.verify`:
```
intact: False
113 record(s) checked; 3 problem(s):
  record 1: the content does not match its hash; this record has been altered
  record 1: the record hash does not match its own contents
  record 2: this record does not follow the one before it; the chain is broken here
```

### DP-085 — tampering with a bundle payload is caught — **PASS**
`[FAIL] record 1: content_hash is f70a94a05580…, the bytes give 470e4ce15b5b…`, exit 1.

### DP-086 — truncation is caught — **PASS**
`[FAIL] the manifest's record count (113) matches the file (112)`, exit 1.

### DP-087 — a re-chained forgery is caught — **PASS**
A record flipped `fail → pass` and the whole chain recomputed so that every per-record and
per-link check passes. The manifest still catches it on all three independent anchors:
```
  [PASS] every record's content hashes to its stored content_hash
  [PASS] every record links to the one before it
  [FAIL] the evidence file is the one the manifest describes
  [FAIL] the Merkle root matches the records
  [FAIL] the chain head matches the last record
```

### DP-088 — samples only for controls that did not pass — **PASS**
Every `pass`, `indeterminate` and `error` record has `sample_count` 0; every `fail` with a
sample query has rows.

### DP-089 — `EVIDENCE samples (20)` respected — **PASS**
`qa-035` keeps 7.

### DP-090 — no `--samples`, no rows leave the source — **PASS**
All 70 records of the first two runs have `sample_count` 0 and an empty digest.

### DP-091 — an error record is distinguishable — **PASS**
`verdict: "error"`, `metrics: {}`, `detail` naming the cause, empty `plan_id`. No number
that could be mistaken for a measurement.

### DP-092 — evidence readable from the console — **PASS**
`/evidence` renders the chain state, the three runs and the records, and explains what a
published Merkle root would buy.

### DP-093 — evidence queryable per control — **PASS**
6 records for `qa-002` at sequences 1, 36, 71, 114, 157, 203; all `fail`; all
`violating_rows` 7.

### DP-094 — timestamps consistent — **PASS** (`records with inconsistent timestamps: none`)

### DP-095 — content hash reproducible — **PASS** (DP-083's first check, computed outside Prama)

---

## 7. Explain, compile and run must agree

### DP-096 — `qa-002` — **PASS**
Sentence *"every counterparty_lei has a value"*, SQL `("counterparty_lei" IS NOT NULL)`,
verdict `fail` with 7 on a corpus with 7 NULLs.

### DP-097 — `qa-011` — **PASS (with DP-037's caveat)**
Sentence *"there is at most one row for each combination of trade_id"*, SQL counting
distinct keys, verdict `fail`. The three agree; the count is missing from the record.

### DP-098 — `qa-024` — **PASS (with DP-073's caveat)**
5 % in the sentence; `scanned_rows`/`violating_rows` in the SQL and the record; 50/1000 =
5.0 % judged as a pass at the boundary. The bound itself is not in the record.

### DP-099 — `qa-020`: the sentence claims more than the SQL tests — **PASS**
`explain` says *"every lei_shapeok is a well-formed lei"* while the SQL tests only the
shape — and the product resolves the divergence the right way: it refuses to report a
pass, names the unrun residual in the record, and the console's compile panel says so on
the authoring screen. This is the case the design was built for and it holds.

### DP-100 — no other control where sentence and execution disagree — **FAIL**
A sweep over all 43 controls found six whose SQL is a screen only, and four of them
resolved the divergence the *wrong* way:
```
incomplete-screen controls that did NOT report indeterminate:
  qa-017  verdict=fail  detail_present=False
  qa-018  verdict=fail  detail_present=False
  qa-019  verdict=fail  detail_present=False
  qb-001  verdict=fail  detail_present=False
```
Plus the two engine-dependent disagreements found separately (DP-059, DP-060) and the
policy that does not reach the value (DP-064). Full cross-engine sweep, same data, same
controls:
```
id        sqlite         duckdb         sqlite metrics -> duckdb metrics
qa-033    pass           error          {scanned 1000, violating 0} -> {}
qa-034    fail           fail           {scanned 200, violating 3}  -> {scanned 200, violating 7}
qb-001    fail           fail           {scanned 1000, violating 11} -> {scanned 1000, violating 4}

3 control(s) out of 43 disagree between the two engines
```

---

## 8. Console and API

### DP-101 — refuses without a session secret — **PASS**
```
error: security.session_secret is empty, and Prama will not start without it
  code: CONFIG.SECRET_MISSING
  next: Set security.session_secret in config/application.local.yaml (git-ignored), or
        export PRAMA_SECURITY__SESSION_SECRET. Never put it in a tracked file.
```
exit 1. *Cosmetic:* the banner with the console and API URLs is printed **after** the
refusal, so the last thing on screen is three URLs for a server that did not start.

### DP-102 — `/estate` — **PASS** (200)
### DP-103 — `/controls` groups by whether they run — **PASS**
`Running 43 · Proposed, not running 0 · Silenced 0 · Retired 0`, each with its schedule
rendered through the parser.
### DP-104 — `/evidence` — **PASS** (200, chain state and runs visible)

### DP-105 — a console-authored control becomes a proposal — **PASS**
`POST /controls/save` → 303 to `/controls`, flash *"Saved as a proposal. Accept it on this
page to start running it (a9d137a81b5e…)."*, and the page shows `Proposed, not running 1`.

### DP-106 — a proposal does not run — **PASS**
`prama control run` immediately afterwards: still `43 control(s)`.

### DP-107 — accepting it makes it run — **PASS**
`POST /controls/{id}/activate` → 303; the next run reports `44 control(s)` and the new
record is `fail`, `scanned_rows` 1000, `violating_rows` **3** — the planted number for
`side IN ('BUY','SELL')`.

### DP-108 — console `check` = CLI `check` — **PASS**
Same finding, same remedy: *"nothing is known about trades — Declare trades, or bind it
to a source…"*.

### DP-109 — console `compile` = CLI `compile` — **PASS**
Byte-identical `metric_query`, and the plan id shown
(`ir:sha256:bfb3a60d6fb61cb6…`) is the one in the evidence record. The console additionally
shows the sample query and the residual disclosure the CLI omits (DP-022).

### DP-110 — `/api/v1/health` — **PASS** (200)

### DP-111 — a dataset declared through the API reaches the estate — **FAIL**
Marked failed because the case could not be completed by any supported means — only by
reaching past the product's own interface. The endpoint itself works and the maker-checker controls around it are good: Tier-1 requires
approval (422), self-approval is refused (422, *"Segregation of duties on Tier-1
declarations is a control, not a formality"*), and with a second principal it returns 201
and the dataset appears on `/estate` and in `GET /api/v1/datasets`.

**Defect — there is no supported way to obtain an API key.** Every endpoint requires one,
and the refusal says:
> *"Send `Authorization: Bearer pk_live_…`, or the X-Prama-API-Key header. Create one with
> `prama apikey create`."*

```
$ prama apikey create
prama: error: argument <command>: invalid choice: 'apikey'
  (choose from 'version','config','connect','connectors','bundle','contract','control',
   'db','estate','lsp','mcp','pack','bench','principal','serve','tenant')
```
There is no `apikey` command, no console page, and no API endpoint that mints one;
`ApiKeyIssuer` and `ApiKeyDao.create` exist only as library code. The second refusal
message names `prama apikey list` as well. This pass got past it by minting a key through
the DAO, which is not a product path. **The HTTP API is unreachable from a clean install.**
This is the same shape as the release blocker the previous pass recorded — one component
naming a command another does not provide.

Scope discovery is also trial-and-error: a key with `admin,read,write` is refused for
`declaration:write`, then again for `relationship:write`, with no command that lists the
scope names.

### DP-112 — the console's catalogue is derived, not restated — **PASS**
After `trades` was declared, `/controls/check` on a control over it stopped saying the
dataset was unknown and started checking columns against the declaration:
> *error — control 1: trades has no column called counterparty_lei (line 1). Columns
> available:*

which is right, since the dataset had been declared without attributes.

*Recorded for honesty:* the first attempt returned a 500
(`AttributeDao.for_dataset() missing 1 required keyword-only argument: 'tenant_id'`). The
running server held bytecode from before a concurrent session's edit to that DAO; against
the tree as it stood at the end of the pass the request succeeds. **Not counted as a
product defect.**

**Also verified while here — declare → derive → accept → run, end to end.** Two attributes
declared through the API produced three proposals from Γ deterministically
(`/proposals`: *"Generated by Γ from the declarations… Nothing here was decided by a
model"*), including `CHECK trades.counterparty_lei IS VALID 'lei' SEVERITY critical
DIMENSION validity`. Accepting one through the console and re-running gave `45 control(s)`
and a record of `fail`, `scanned_rows` 1000, `violating_rows` **7** — the planted number.
The headline flow works and gets the right answer.

---

## 9. Scorecards, reconciliation and the rest

### DP-113 — `/scorecards` derives from the evidence — **PASS**
```
trades  98.7%   2 of 39 controls did not run — this describes 95% of what was meant to be checked
  completeness 99.3%   conformity 98.7%
  trades: completeness 99.3% (7 of 1,000 rows across 1 control),
          conformity 98.7% (456 of 33,020 rows across 36 controls)
43 measurement(s) come from records written before the evidence format carried a
dimension. They are counted in the totals and grouped under conformity rather than
spread across the six by guesswork, so the breakdown below is incomplete rather than
invented.
```
The score is derived, the coverage shortfall is stated in the same breath as the number,
and the dimension gap is disclosed rather than papered over. This is the standard the
rest of the evidence path should be held to — and it is the surface that exposes DP-055,
by reporting `trades_empty` as *"nothing has been measured"* while the ledger holds a
`pass` for it.

### DP-114 — `estate maturity` — **PASS**
`estate: 0% — reached stage 'discovered'`, with the next steps ranked by controls
unlocked per unit of effort. *Minor:* `--tenant` is required even though
`tenancy.default_tenant` is set and `control run` honours it.

### DP-115 — `estate export` — **PASS** (`wrote 1 file(s) under estate_out`, `datasets/trades.yaml`)

### DP-116 — `--due-only` respects the schedule — **PASS**
`2 control(s), 1 fail, 1 indeterminate, 42 not due` — only the two controls with no prior
run fired, and the 42 that did not are counted rather than dropped.

### DP-117 — reconciliation — **FAIL**
`/reconciliation` says:
> *"Controls have run, but none of them was a reconciliation. Declare a reconciles-with
> relationship between two datasets and one will be generated."*

So that was done: a second dataset declared, and a `reconciles_with` relationship created
through the API with match keys, compared columns and a tolerance — accepted with 201 and
returning `"generates": ["reconciliation","break_workflow","certificate"]`, status
`confirmed`, and visible on `/relationships`.

Nothing was generated. `/reconciliation` is unchanged and repeats the same instruction;
`/proposals` says *"Proposed controls 0 … Nothing was derived."* Derivation itself is
working — declaring two **attributes** on the same dataset produced three proposals
immediately — so the gap is specific to the relationship. The matching engine exists
(`prama/recon/`) and is reachable from no surface in this build, while the console
instructs the operator to perform an action that does not have the advertised effect.

### DP-118 — `contract check` gates a build — **PASS**
```
$ prama contract check contract.json --data rows_bad.json     # column removed
BREACH — promised column(s) absent: counterparty_lei                    exit 3
$ prama contract check contract.json --data rows_ok.json      # 50 rows incl. NULL LEIs
BREACH — column(s) promised as required hold empty values: counterparty_lei   exit 3
$ prama contract check contract.json --data rows_clean.json
The contract holds over 50 row(s): every promised column is present and every required
one is populated.                                                        exit 0
```
The middle case was my error, not the product's: the corpus has 7 NULL LEIs and the
contract exported from the declaration marks the column required, so a breach is right.

### DP-119 — `bench run --seed 42` — **PASS**
28 scenarios, 28 planted defects, two bounds and three ablations, blind spots per family,
and a list of the 15 named baselines it has **not** run with the reason why. Exit 0.

### DP-120 — the case studies run end to end — **FAIL**
All four are broken, on committed code, at the stage the QUICKSTART points a new user to
("See it actually do something"):
```
case-studies/01-trading-book-sqlite   TypeError: VersionedDao.require_current() missing 1 required keyword-only argument: 'tenant_id'
case-studies/02-feeds-csv-parquet     TypeError: VersionedDao.require_current() missing 1 required keyword-only argument: 'tenant_id'
case-studies/03-mixed-estate          TypeError: ControlDao.activate() missing 1 required keyword-only argument: 'tenant_id'
case-studies/04-expressions-and-plugins  TypeError: ControlDao.activate() missing 1 required keyword-only argument: 'tenant_id'
```
`require_current` and `activate` gained a required `tenant_id` in commit `6226854`
("Adversarial review: close the two critical holes") — a correct security fix — and
`case-studies/_common/harness.py` was not updated with them. `git diff HEAD` on both files
is empty, so this is committed state and not the concurrent session's working tree. Each
study fails at stage 3 of 5, after printing the estate it declared. `pytest` does not
cover the case studies, which is why 4,666 tests are green while all four are dead.

---

## Summary

| | |
|---|---:|
| Total cases | **120** |
| Passed | **101** |
| Failed | **19** |
| Blocked | **0** |
| Not run | **0** |

### Failures, ranked

| Rank | Case(s) | What |
|---|---|---|
| 1 | DP-059 | A control on a **non-existent column** reports `pass` on 1,000 rows under SQLite (unknown quoted identifier becomes a string literal). The same control is an `error` on DuckDB. A dropped or renamed column reports green for ever. |
| 2 | DP-055 | An **empty table** reports `pass`. The absolute-threshold path — which every predicate control uses — is the one judgement path with no empty-scope guard, while three others have one and the scorecard says "nothing has been measured" about the same records. |
| 3 | DP-043, DP-044, DP-045, DP-100 | An `IS VALID` screen that finds any violation reports that count as fact. The lower-bound disclosure is attached **only when the verdict would be `pass`**, so the understatement is disclosed when it is zero (11 of 23, 3 of 9, 2 of 10 shown with no caveat). |
| 4 | DP-060 | `FOR EACH` is compiled correctly and judged on **`rows[0]` only**. 1 segment of 5 decides the verdict; 3 (SQLite) or 7 (DuckDB) violations reported instead of 16; samples in the same record contradict the metrics. |
| 5 | DP-064 | `TREAT UNKNOWN AS PASS` does not reach `IS VALID` on SQLite — the `REGEXP` hook returns `False` for NULL, against its own docstring. Same control, same data: 11 on SQLite, 4 on DuckDB. |
| 6 | DP-120 | All four case studies crash at stage 3. The QUICKSTART's own "see it work" path is dead on committed code. |
| 7 | DP-111 | No supported way to mint an API key; the refusal names `prama apikey create`, which does not exist. The HTTP API is unreachable from a clean install. |
| 8 | DP-037, DP-038, DP-042, DP-077 | Uniqueness and functional-dependency records carry no `violating_rows` — `judge()` derives it and `ControlRun` discards it. |
| 9 | DP-023 | `prama control compile` refuses every `IN CODELIST` control with a false remedy, because it lowers with a bare `Lowerer()` instead of `resolved()`. `compile` and `run` disagree about whether the control is runnable. |
| 10 | DP-073 | The sealed evidence record does not carry the threshold. Four records with identical metrics, two `pass` and two `fail`, indistinguishable to an auditor holding only the bundle. |
| 11 | DP-013 | Bare `CURRENT_DATE` is accepted and compiled as a column reference; only the parenthesised spelling is refused. |
| 12 | DP-022 | `prama control compile` omits the residual disclosure the console shows for the same control. |
| 13 | DP-117 | Declaring a `reconciles_with` relationship generates nothing, although the console instructs the operator to do exactly that and the relationship advertises `generates: ["reconciliation", …]`. |

### What held up

The thing this product exists to prevent — a pass reported from a screen — **does not
happen** where the screen is the only signal: 12 fabricated LEIs and 6 fabricated ISINs
with valid shape and wrong check digits produced `indeterminate` with the unrun residual
named, not a green tick. Counts are right wherever the assertion is complete: 7, 14, 9,
16, 6, 4, 3, 11, 15, 50, 51, 995, 993 — every one the planted number, on the nose, and the
thresholds flip at exactly the row the declaration names. The evidence chain resists
record tampering, payload tampering, truncation and a fully re-chained forgery. The
declare → derive → accept → run flow works end to end through the console and returns the
right answer. `explain` produces sentences a data owner can read, and they match the SQL.

The failures cluster into one shape: **the paths that decide "nothing to report" are
weaker than the paths that decide "something to report."** An empty table, a column that
is not there, a segment that was not looked at, an unknown the policy never reached, a
violation count that is a floor — each is a place where the absence of a finding is
reported as a finding of absence.
