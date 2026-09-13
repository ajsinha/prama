<!--
Prama — QA test cases: the data path, end to end.
Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary. No licence is granted except by separate written agreement.
-->

# QA cases — the data path, end to end

**Surface:** declare a dataset, author a control, run it against real data, read the
evidence, and check the answer is right.

**These cases were written before any of them was executed.** The expected counts below
come from the corpus generator and from an independent oracle (`oracle.py`) that
recomputes every number with plain Python and plain SQLite, importing nothing from Prama.
Where a case states an expectation that the product's own documentation or docstrings
contradict, the case says which one it is testing.

Results are in `log-datapath.md`.

---

## 0. The corpus

Built by `/tmp/qa-datapath/build_corpus.py` into `/tmp/qa-datapath/data.sqlite`.
Check-digit arithmetic is written from ISO 6166, ISO 17442 and ISO 13616 and is
sanity-checked against published real identifiers (`US0378331005`,
`5493001KJTIIGC8Y1R12`, `7LTWFZYICNSX8D621K86`, `GB82WEST12345698765432`) before a
single row is generated; a wrong implementation would abort the build rather than
produce a corpus whose "expected" numbers are themselves wrong.

**`trades` — 1,000 rows.** Planted, with the defect sets disjoint by construction:

| What | Column | Count |
|---|---|---:|
| NULLs in a CDE | `counterparty_lei` | 7 |
| LEI, shape valid, **check digits wrong** | `counterparty_lei` | 12 |
| LEI, shape invalid (fails the screen) | `counterparty_lei` | 4 |
| LEI, shape valid, check digits wrong, **no nulls, no shape failures in the column** | `lei_shapeok` | 12 |
| ISIN, shape valid, check digit wrong | `isin` | 6 |
| ISIN, shape invalid | `isin` | 3 |
| ISIN, shape valid, check digit wrong, clean column | `isin_shapeok` | 6 |
| IBAN, shape valid, check digits wrong | `iban` | 8 |
| IBAN, shape invalid | `iban` | 2 |
| Value outside the code list | `currency` | 9 |
| NULLs (three-valued logic) | `currency` | 5 |
| NULLs (three-valued logic, numeric) | `qty_check` | 10 |
| Non-positive | `qty_check` | 6 |
| Cross-field rule broken (`notional <> quantity * price`) | — | 11 |
| Out of range (negative) | `quantity` | 4 |
| Outside `('BUY','SELL')` | `side` | 3 |
| Referential orphans against `instruments` | `isin` | 15 |
| Duplicate grain key | `trade_id` | 5 rows (995 distinct) |
| Duplicate alternate key | `alt_key` | 4 rows + 3 NULL keys |
| NULLs, exactly 5.0 % | `rate_col_a` | 50 |
| NULLs, exactly 5.1 % | `rate_col_b` | 51 |
| Functional dependency `book → desk` broken | — | 2 extra pairs |
| `status = 'ACTIVE'` | — | 900 |

**`trades_empty`** — identical schema, zero rows.
**`instruments`** — 985 rows: every `trades.isin` except the 15 designated orphans.
**`trades_missing`** — deliberately does not exist.

## The control suite

`/tmp/qa-datapath/suite.pql`, 35 controls, loaded into the estate as `qa-001` … `qa-035`
in file order.

---

## 1. Setup and corpus integrity

### DP-001 — The corpus generator's own arithmetic is right
**Steps:** run `build_corpus.py`.
**Expected:** the assertions against the four published real identifiers pass; the file
is written. (If the check-digit code were wrong, every "expected" number below would be.)

### DP-002 — An independent oracle agrees with the plant
**Steps:** run `oracle.py`, which recomputes every count from the written database using
plain Python and plain SQLite.
**Expected:** every count equals the planted count. `ORACLE AGREES WITH THE PLANT`.

### DP-003 — `prama db init` applies the schema to a clean file
**Expected:** exit 0; 35 tables reported; a digest printed.

### DP-004 — `prama db verify` reports no drift immediately after init
**Expected:** exit 0, "no drift".

### DP-005 — `prama tenant create` creates an estate and prints its id
**Expected:** exit 0; a ULID printed; `tenant list` shows it marked as the configured one.

### DP-006 — The 35-control suite loads and every control is live
**Steps:** `load_controls.py suite.pql qa`; then count `status='active'` rows.
**Expected:** 35 controls declared and activated; `prama control run` later reports 35.

---

## 2. Authoring: check, explain, compile

### DP-007 — `control check` parses the whole suite
**Expected:** exit 0; "35 control(s) read".

### DP-008 — `control check` reports the undeclared dataset once, not 35 times
**Expected:** exactly one `unchecked` finding for `trades` (the CLI's own stated
behaviour), not one per control.

### DP-009 — `control check` finds the redundant control
**Corpus:** `qa-002` (`IS NOT NULL`) and `qa-017` (`IS VALID 'lei'`) are on the same column.
**Expected:** a lint warning saying the null check adds nothing, because an unknown
already counts as a violation under `IS VALID`.

### DP-010 — `control check --strict` exits non-zero when only warnings exist
**Expected:** exit non-zero (the CI gate), where plain `check` exits 0.

### DP-011 — A syntax error names the clause and gives a remedy
**Steps:** `CHECK trades.x IS NOT NULL BECAUSE "double quotes"`.
**Expected:** exit non-zero; the caret under the offending token; a remedy naming single
quotes.

### DP-012 — `BECAUSE` is required for `TREAT UNKNOWN AS PASS`
**Steps:** a control with `TREAT UNKNOWN AS PASS` and no `BECAUSE`.
**Expected:** refused at parse time with a remedy, not accepted.

### DP-013 — A non-deterministic function is refused in an expression
**Steps:** `CHECK trades SATISFIES trade_date < CURRENT_DATE BECAUSE 'x'`.
**Expected:** refused, because a verdict that depends on when it ran cannot be replayed.

### DP-014 — `control explain` renders every control as a sentence
**Expected:** 35 sentences, each naming the dataset, the column and what must be true;
no SQL, no identifiers a business owner would not recognise.

### DP-015 — `explain` states the threshold when one is set
**Expected:** `qa-024` explains as "up to 5 % of rows may violate it", not silently.

### DP-016 — `explain` states the unknown policy when it is not the default
**Expected:** `qa-004` and `qa-006` say a row whose value cannot be determined is
allowed to pass; `qa-003` and `qa-005` do not.

### DP-017 — `control compile --dialect sqlite` emits SQL for every compilable control
**Expected:** 35 queries or an explicit refusal per control; no silent omission.

### DP-018 — Compiled SQL for `IS NOT NULL` matches the sentence
**Expected:** `violating_rows` counts rows where `NOT COALESCE(col IS NOT NULL, 0)`.

### DP-019 — The `WHERE` clause reaches the SQL
**Expected:** `qa-009` compiles with `WHERE ("status" = 'ACTIVE')`; `qa-008` does not.

### DP-020 — `TREAT UNKNOWN AS PASS` changes the emitted SQL
**Expected:** the two `currency` controls differ: the default wraps the predicate in
`NOT COALESCE(...)`, the PASS variant in `COALESCE(NOT ..., 0)`.

### DP-021 — `IS VALID 'lei'` compiles to a screen, and the compiler knows it is a screen
**Expected:** the emitted SQL is the ISO 17442 *shape* regex only; the compiled artefact
reports `is_complete = False` and `residual_validators = (('lei', 'counterparty_lei'),)`.

### DP-022 — `compile` output discloses that the query is only a screen
**Expected:** the text a DBA reads before granting access says the query is a necessary
condition, not the test. *(This is the expectation the product's two-stage thesis
implies; recorded as written whether or not it holds.)*

### DP-023 — `IN CODELIST iso4217` compiles
**Corpus:** `iso4217` is in `prama.classify.codelists.default_registry()`.
**Expected:** it compiles to a membership test, or is refused with a remedy that is true.

### DP-024 — `control compile --fuse` groups controls sharing a scope
**Expected:** fewer queries than controls; every control still accounted for.

### DP-025 — `control format` is idempotent and meaning-preserving
**Expected:** formatting twice gives the same text; re-checking the formatted file gives
the same findings.

### DP-026 — `control functions` reports pushdown coverage per engine
**Expected:** a table naming sqlite, duckdb and postgresql and what each refuses.

---

## 3. Execution: one case per control, against real data

Every case below runs `prama control run --against data.sqlite --dialect sqlite` and reads
the evidence record for that control. **Expected verdict and counts are stated before
the run.**

### DP-027 — `qa-001` `trades.trade_id IS NOT NULL`
**Expected:** PASS; `scanned_rows` 1000, `violating_rows` 0.

### DP-028 — `qa-002` `trades.counterparty_lei IS NOT NULL`
**Expected:** FAIL; `scanned_rows` 1000, `violating_rows` **7**.

### DP-029 — `qa-003` `trades.currency IN ('USD','EUR','GBP','CHF','JPY')`
**Expected:** FAIL; `violating_rows` **14** (9 bad codes + 5 NULLs, unknown = violation).

### DP-030 — `qa-004` the same, `TREAT UNKNOWN AS PASS`
**Expected:** FAIL; `violating_rows` **9**. Exactly 5 fewer than DP-029.

### DP-031 — `qa-005` `trades.qty_check > 0`
**Expected:** FAIL; `violating_rows` **16** (6 non-positive + 10 NULLs).

### DP-032 — `qa-006` the same, `TREAT UNKNOWN AS PASS`
**Expected:** FAIL; `violating_rows` **6**. Exactly 10 fewer than DP-031.

### DP-033 — `qa-007` `trades.quantity BETWEEN 0 AND 100000000`
**Expected:** FAIL; `violating_rows` **4**.

### DP-034 — `qa-008` `trades.side IN ('BUY','SELL')`
**Expected:** FAIL; `violating_rows` **3**.

### DP-035 — `qa-009` the same, `WHERE status = 'ACTIVE'`
**Expected:** FAIL; `scanned_rows` **900**, `violating_rows` **3** (all three planted bad
sides are on active rows).

### DP-036 — `qa-010` `trades SATISFIES notional = quantity * price`
**Corpus:** the clean rows store exactly the IEEE-754 product, so equality is meaningful.
**Expected:** FAIL; `violating_rows` **11**.

### DP-037 — `qa-011` `trades HAS UNIQUE KEY (trade_id)`
**Expected:** FAIL; `scanned_rows` 1000, `distinct_keys` **995**, `null_key_rows` 0,
`duplicate_rows` **5**, `violating_rows` **5**.

### DP-038 — `qa-012` `trades HAS UNIQUE KEY (alt_key)` with NULL keys present
**Expected:** FAIL; `distinct_keys` **993**, `null_key_rows` **3**, `duplicate_rows` **4**,
`violating_rows` **7**. A NULL key must be counted once as itself, not charged as a
duplicate.

### DP-039 — `qa-013` `trades HAS ROW COUNT BETWEEN 900 AND 1100`
**Expected:** PASS; `scanned_rows` 1000.

### DP-040 — `qa-014` `trades HAS ROW COUNT BETWEEN 2000 AND 3000`
**Expected:** FAIL; `scanned_rows` 1000.

### DP-041 — `qa-015` `trades.isin REFERENCES instruments.isin`
**Expected:** FAIL; `violating_rows` **15**. (The correlated subquery must qualify the
outer column, or no orphan is ever found.)

### DP-042 — `qa-016` `trades SATISFIES book DETERMINES desk`
**Expected:** FAIL; `distinct_determinants` **5**, `distinct_pairs` **7**,
`violating_rows` **2** — counted in determinants, not rows.

### DP-043 — `qa-017` `trades.counterparty_lei IS VALID 'lei'`
**Corpus:** 4 shape failures, 12 check-digit failures, 7 NULLs. Exact violations 23;
the screen alone can see 11.
**Expected:** FAIL. `violating_rows` will be **11** because only the screen runs — and
the record **must say the count is a lower bound**, or the number is a false assurance.
This case passes only if the understatement is disclosed.

### DP-044 — `qa-018` `trades.isin IS VALID 'isin'`
**Expected:** FAIL; screen sees **3** of **9** real violations; the shortfall must be
disclosed.

### DP-045 — `qa-019` `trades.iban IS VALID 'iban'`
**Expected:** FAIL; screen sees **2** of **10**; the shortfall must be disclosed.

### DP-046 — `qa-020` `trades.lei_shapeok IS VALID 'lei'` — the false-pass test
**Corpus:** every one of the 1,000 values has a valid LEI shape; 12 have wrong check
digits; there are no NULLs.
**Expected:** the screen returns `violating_rows` 0. The verdict **must not be PASS** —
it must be `indeterminate`, with a detail naming the unrun residual. A PASS here is the
single most serious defect this product can have.

### DP-047 — `qa-021` `trades.isin_shapeok IS VALID 'isin'` — the same, for ISIN
**Expected:** `violating_rows` 0, verdict `indeterminate`, not PASS. (6 real violations.)

### DP-048 — `qa-022` `trades.trade_id MATCHES /^T[0-9]{6}$/`
**Expected:** PASS; `violating_rows` 0. (Also proves SQLite's `REGEXP` hook is registered
the right way round — backwards, it matches nothing and every validity control passes.)

### DP-049 — `qa-023` `trades.book HAS LENGTH BETWEEN 6 AND 6`
**Expected:** PASS; `violating_rows` 0.

### DP-050 — `qa-024` `trades.rate_col_a IS NOT NULL BELOW 5%`
**Corpus:** exactly 50 NULLs in 1,000 rows = 5.000 %.
**Expected:** PASS at the boundary (`0.05 <= 0.05`); `violating_rows` 50.

### DP-051 — `qa-025` `trades.rate_col_b IS NOT NULL BELOW 5%`
**Corpus:** exactly 51 NULLs = 5.1 %.
**Expected:** FAIL; `violating_rows` 51. The threshold flips between 50 and 51 rows.

### DP-052 — `qa-026` `trades.rate_col_a IS NOT NULL BELOW 4%`
**Expected:** FAIL; `violating_rows` 50.

### DP-053 — `qa-027` `trades.rate_col_a IS NOT NULL AT MOST 50 ROWS`
**Expected:** PASS at the boundary; `violating_rows` 50.

### DP-054 — `qa-028` `trades.rate_col_a IS NOT NULL AT MOST 49 ROWS`
**Expected:** FAIL; `violating_rows` 50.

### DP-055 — `qa-029` `trades_empty.trade_id IS NOT NULL` — the empty-scan test
**Corpus:** zero rows.
**Expected:** **not** PASS. `scanned_rows` 0 and `violating_rows` 0 demonstrate nothing;
per the product's own thesis ("an incomplete screen cannot report a pass", "an empty
scope is a fact about the scope, and calling it a pass is how a broken feed reports
green") the verdict must be `indeterminate` or an equivalent non-green state.

### DP-056 — `qa-030` `trades_empty HAS UNIQUE KEY (trade_id)`
**Expected:** `indeterminate` — nothing to be unique.

### DP-057 — `qa-031` `trades_empty HAS ROW COUNT BETWEEN 900 AND 1100`
**Expected:** FAIL; `scanned_rows` 0.

### DP-058 — `qa-032` a table that does not exist
**Expected:** an `error` evidence record naming the missing table; the run continues and
the other 34 controls still produce verdicts; `prama control run` exits non-zero.

### DP-059 — `qa-033` a column that does not exist
**Expected:** an `error` evidence record naming the missing column, never a PASS.

### DP-060 — `qa-034` `trades.qty_check > 0 FOR EACH book`
**Corpus:** 5 books; the 16 violations are spread across them.
**Expected:** a verdict per segment, and an overall FAIL if any segment fails; the totals
must equal the unsegmented run (`scanned_rows` 1000, `violating_rows` 16).

### DP-061 — `qa-035` the reporting clauses reach the record
**Expected:** FAIL, `violating_rows` 7, and the record carries `criticality`,
`dimensions = ('completeness',)`, and — with `--samples` — at most 20 sample rows.

---

## 4. Unknown handling, stated as differences

### DP-062 — Nulls under the default policy are violations
**Expected:** DP-029 (14) − DP-030 (9) = **5**, the exact number of NULL currencies.

### DP-063 — The same, for a numeric comparison
**Expected:** DP-031 (16) − DP-032 (6) = **10**, the exact number of NULL `qty_check`.

### DP-064 — `TREAT UNKNOWN AS PASS` changes `IS VALID` too
**Steps:** run `CHECK trades.counterparty_lei IS VALID 'lei' TREAT UNKNOWN AS PASS`
against the corpus and compare with `qa-017`.
**Expected:** 7 fewer violations than `qa-017` (11 → **4**), because the 7 NULLs are the
only unknowns. If the two are equal, the policy is not reaching the value.

### DP-065 — `IS NOT NULL` is unaffected by the policy
**Steps:** the same control with and without `TREAT UNKNOWN AS PASS`.
**Expected:** identical counts (7 and 7): `IS NOT NULL` never yields unknown.

### DP-066 — A column that is entirely NULL does not pass silently
**Steps:** a control on `trades_empty`-shaped data where the column is 100 % NULL
(`CHECK trades.all_null_probe > 0` via a view of NULLs — implemented as
`CHECK trades.qty_check > 0 WHERE qty_check IS NULL`).
**Expected:** `scanned_rows` 10, `violating_rows` 10, FAIL — the classic "rule over an
all-null column passes for years" failure must not occur.

### DP-067 — The same under `TREAT UNKNOWN AS PASS`, with the reason recorded
**Expected:** `violating_rows` 0, PASS, and the stored control text still carries the
`BECAUSE` that justifies it.

---

## 5. Thresholds, at the boundary

### DP-068 — A rate threshold is computed from one scan, not two
**Expected:** the record carries both `scanned_rows` and `violating_rows`, so the rate
can be recomputed from the evidence.

### DP-069 — The rate threshold's denominator is the filtered scope
**Steps:** `CHECK trades.side IN ('BUY','SELL') WHERE status = 'ACTIVE' BELOW 1%`.
**Corpus:** 3 of 900 = 0.333 %.
**Expected:** PASS, `scanned_rows` 900 (not 1000).

### DP-070 — A rate threshold on an empty scope is not a pass
**Steps:** `CHECK trades_empty.trade_id IS NOT NULL BELOW 5%`.
**Expected:** `indeterminate` (denominator zero).

### DP-071 — `BELOW 5%` and `BELOW 0.05` mean the same thing
**Expected:** identical verdicts and counts for `rate_col_a`.

### DP-072 — An absolute threshold and a rate threshold agree at the same point
**Expected:** `AT MOST 50 ROWS` (DP-053) and `BELOW 5%` (DP-050) both PASS on the same
data; `AT MOST 49` and `BELOW 4%` both FAIL.

### DP-073 — A threshold is visible in `explain`, `compile` and the record
**Expected:** the same number appears in all three for `qa-024`; no clause is lost
between authoring and execution.

---

## 6. Evidence

### DP-074 — A record is written for every control in the run
**Expected:** 35 evidence records for a 35-control run, including the two that errored.

### DP-075 — The run row is opened and closed
**Expected:** one `ev_runs` row, `status = 'complete'`, with a detail naming the verdict
counts; `unfinished()` returns nothing afterwards.

### DP-076 — Each record names the plan it executed
**Expected:** `plan_id` is non-empty and equals the `plan_id` that `compile` reports for
the same control text.

### DP-077 — The record says what was scanned and what violated
**Expected:** `metrics` carries `scanned_rows` and `violating_rows` for every predicate
control; no record has a verdict without the numbers behind it.

### DP-078 — The record names the engine and the dataset
**Expected:** `engine = 'sqlite'`, `dataset` equal to the control's target.

### DP-079 — The record carries a snapshot reference
**Expected:** a `snapshot` naming what was read (kind and identifier), so the run can be
placed in time.

### DP-080 — The chain is intact after a clean run
**Steps:** `evidence.verify(tenant)`.
**Expected:** intact; head equals the last record's `record_hash`; the first record's
`previous_hash` is sixty-four zeros.

### DP-081 — A second run extends the chain rather than restarting it
**Expected:** 70 records, one chain, still intact.

### DP-082 — The same run twice gives the same numbers
**Expected:** every control's `violating_rows` is identical across the two runs.

### DP-083 — A sealed bundle verifies with the standalone script
**Steps:** export a bundle, then `python3 scripts/verify_evidence.py <dir>`.
**Expected:** exit 0, every check passed, no import of Prama.

### DP-084 — Tampering with a record's content is caught
**Steps:** edit one `violating_rows` value directly in the SQLite row.
**Expected:** `evidence.verify` reports a breach naming the sequence; exit non-zero.

### DP-085 — Tampering with a bundle payload is caught by the standalone script
**Steps:** change one digit in `evidence.ndjson`.
**Expected:** exit 1 with a message naming the record.

### DP-086 — Truncating a bundle is caught
**Steps:** delete the last line of `evidence.ndjson`.
**Expected:** exit 1 — the manifest's record count reveals it.

### DP-087 — A re-chained tamper is still caught by the manifest
**Steps:** alter a record and recompute its hashes so the chain is internally consistent.
**Expected:** caught by the payload digest / Merkle root in the manifest.

### DP-088 — Samples are kept only for controls that did not pass
**Steps:** run with `--samples`.
**Expected:** passing controls have `sample_count` 0; failing ones have rows.

### DP-089 — Sample counts respect `EVIDENCE samples (20)`
**Expected:** `qa-035` keeps at most 20 rows although 7 violate — so at most 7.

### DP-090 — Without `--samples` no rows leave the source
**Expected:** every record has `sample_count` 0 and an empty digest.

### DP-091 — An error record is distinguishable from a failing one
**Expected:** verdict `error`, with `detail` naming the cause, and no `violating_rows`
that could be mistaken for a measurement.

### DP-092 — Evidence is readable from the console
**Expected:** `/evidence` renders and lists the run's records with verdicts.

### DP-093 — Evidence is queryable per control
**Expected:** `for_control(control_id)` returns that control's records in order.

### DP-094 — `duration_ms` and the timestamps are consistent
**Expected:** `started_at <= finished_at`, `duration_ms >= 0` for every record.

### DP-095 — A record's own hash is reproducible from its content
**Expected:** recomputing `content_hash` from the stored fields with the algorithm in the
manifest gives the stored value.

---

## 7. Explain, compile and run must agree

### DP-096 — `qa-002`: sentence, SQL and verdict describe the same test
**Expected:** "every counterparty_lei has a value" / a `IS NOT NULL` predicate /
`violating_rows` 7 on a corpus with 7 NULLs.

### DP-097 — `qa-011`: the sentence says "at most one row for each combination"
**Expected:** and the SQL counts distinct keys, and the verdict fails with 5.

### DP-098 — `qa-024`: the sentence's 5 % is the SQL's denominator and the record's rate
**Expected:** all three agree.

### DP-099 — `qa-020`: the sentence claims more than the SQL can test
**Expected:** `explain` says "every lei_shapeok is a well-formed lei". The SQL tests only
the shape. **This is the divergence to look for deliberately** — either `explain`
discloses the two-stage nature, or the run refuses to report a pass, or the product
claims something it did not test.

### DP-100 — A control whose explanation and execution disagree exists nowhere else
**Steps:** for all 35 controls, compare the `describe()` sentence against the compiled
predicate and the executed verdict.
**Expected:** no other control where the sentence asserts something the SQL does not test.

---

## 8. Console and API

### DP-101 — The server starts and refuses without a session secret
**Expected:** with an empty secret it refuses and says so; with one set it starts.

### DP-102 — `/estate` renders
**Expected:** HTTP 200.

### DP-103 — `/controls` lists live, proposed and suppressed separately
**Expected:** HTTP 200; 35 live; 0 proposed.

### DP-104 — `/evidence` shows the run
**Expected:** HTTP 200; the verdict counts visible.

### DP-105 — A control authored in the console reaches the estate as a proposal
**Steps:** `POST /controls/save` with PQL.
**Expected:** 303 to `/controls`; the control appears under proposed, not live.

### DP-106 — A proposal does not run
**Steps:** `prama control run` before accepting it.
**Expected:** the control count is unchanged; a proposal produces no evidence.

### DP-107 — Accepting it in the console makes it run
**Steps:** `POST /controls/{id}/activate`, then run.
**Expected:** one more control executed, with the right count for its assertion.

### DP-108 — `/controls/check` in the console gives the same findings as the CLI
**Expected:** the same diagnostics for the same text.

### DP-109 — `/controls/compile` in the console gives the same SQL as the CLI
**Expected:** byte-identical SQL for the same control and dialect.

### DP-110 — `/api/v1/health` answers
**Expected:** HTTP 200.

### DP-111 — A dataset declared through the API appears in the estate
**Steps:** `POST /api/v1/datasets`.
**Expected:** 200/201; the dataset is listed by `GET /api/v1/datasets` and on `/estate`.

### DP-112 — The console's catalogue is derived from declarations, not restated
**Expected:** after DP-111, `/controls/check` no longer reports `trades` as unknown if
the declared dataset is `trades`.

---

## 9. Scorecards, reconciliation and the rest

### DP-113 — `/scorecards` renders and its score derives from the evidence
**Expected:** HTTP 200; the score reflects the run's verdicts rather than a stored number.

### DP-114 — `prama estate maturity` scores the declared estate
**Expected:** exit 0; a score that is low for an estate with one declared dataset.

### DP-115 — `prama estate export` writes reviewable YAML
**Expected:** exit 0; a directory of YAML naming the declared datasets.

### DP-116 — `prama control run --due-only` respects the schedule
**Expected:** with `schedule: daily` and a run already done today, fewer controls run
than without the flag, and the skipped ones are named.

### DP-117 — Reconciliation between two datasets
**Steps:** drive the matching engine over `trades` and a copy with known breaks.
**Expected:** the break count equals what was planted — or, if the recon engine is not
reachable from the CLI or the console, the case is BLOCKED and says so.

### DP-118 — `prama contract check` gates on the corpus
**Expected:** exit 3 on a breach, 0 on a clean contract.

### DP-119 — `prama bench run --seed 42` scores the labelled corpus
**Expected:** exit 0; bounds and ablations printed.

### DP-120 — The case study runs end to end
**Steps:** `python case-studies/01-trading-book-sqlite/run.py --no-serve`.
**Expected:** it builds, declares, derives, runs and prints planted-versus-caught.
