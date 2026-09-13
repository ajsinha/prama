# The language and the compiler — QA execution log

`prama.pql.tokens` · `prama.pql.errors` · `prama.pql.parser` · `prama.pql.ast` · `prama.pql.types`
· `prama.pql.functions` · `prama.pql.library` · `prama.pql.lint` · `prama.pql.excel` ·
`prama.pql.expand` · `prama.pql.analysis` · `prama.pql.families` · `prama.pql.__init__` ·
`prama.ir.model` · `prama.ir.lower` · `prama.ir.resolve` · `prama.backend.dialect` ·
`prama.backend.sql` · `prama.backend.reference` · `prama.backend.execute` · `prama.backend.fuse`
· `prama.backend.conformance` · `prama.backend.corpus` · `prama.backend.generate` ·
`prama.backend.example`.

All 629 cases in `docs/qa/catalogue/language.md` were executed against the live codebase, split
across ten parallel execution passes (one per catalogue section group), each driving the real
APIs directly: `prama.pql.tokens.tokenise`, `prama.pql.parser.parse`/`parse_control`,
`prama.ir.lower.Lowerer`/`prama.ir.resolve.resolved`, `prama.backend.sql.SqlCompiler`/
`compile_for`, `prama.backend.reference.ReferenceEvaluator`, `prama.pql.types.TypeChecker`,
`prama.pql.lint.Linter`, `prama.pql.excel.parse_formula`, `prama.pql.expand.Expander`,
`prama.pql.analysis.LanguageService`, and the `prama control …` CLI subcommands — plus real
SQLite, DuckDB and PostgreSQL 16 (an ephemeral Docker container) connections wherever a case
named an engine. No case was marked PASS without being run; every FAIL was reproduced a second
time with a minimal, stated repro and classified as defect, not-a-defect, or working-as-designed.

## Counts

| | Count |
|---|---:|
| Total cases | 629 |
| PASS | 500 |
| FAIL | 129 |
| BLOCKED | 0 |
| **Pass rate** | **79.5%** (500/629) |

No case was BLOCKED — every one named in the catalogue could be executed in this environment
(real SQLite/DuckDB in-process, a disposable PostgreSQL 16 container, and pure-Python
construction everywhere else).

## Failures ranked by severity (62 P1, 58 P2, 9 P3)


**P1**
- `BE-006` — Literal rendering per type
- `BE-012` — SQLite's composite key join is injective
- `BE-015` — A pattern using a non-portable regex feature
- `BE-016` — An invalid pattern
- `BE-023` — Modulo takes the sign of the dividend on every engine
- `BE-024` — Modulo by zero
- `BE-029` — A capability set is exactly what each engine can do
- `BE-049` — Aggregates bypass the catalogue
- `BE-054` — Every operator the lowerer can emit has a SQL branch
- `BE-067` — An unknown comparison operator raises rather than returning unknown
- `BE-068` — `x = y` between a number and a numeric string
- `BE-073` — `MATCHES` against a non-string value
- `BE-078` — Arithmetic on a non-numeric value crashes
- `BE-080` — Reference arithmetic is float, the catalogue is Decimal
- `BE-112` — Every assertion kind reaches its own verdict function
- `BE-125` — One unsupported control stops the whole group
- `BE-132` — A refusal is a conforming outcome; a wrong answer is not
- `BE-135` — A case answered by fewer than two engines is not "compared"
- `BE-139` — Two-stage comparison is skipped when the reference did not run
- `BE-143` — The corpus covers no function except LENGTH
- `BE-144` — The corpus has no `IN CODELIST` case
- `BE-146` — The corpus has no parameter case
- `BE-150` — The corpus has no freshness, no `IS UNIQUE`, no Excel and no `HAS FORMAT` case
- `BE-178` — Sealed evidence carries the threshold
- `BE-179` — A control that cannot be replayed cannot be written
- `IR-024` — `as_of` is a parameter name, and a date breaks it
- `IR-037` — A missing `scanned_rows` disables the empty-scope guard
- `PQL-001` — Every token kind the lexer can emit is reachable
- `PQL-036` — A non-ASCII letter cannot crash the word scanner
- `PQL-047` — Every PQL error renders position, excerpt, caret and remedy
- `PQL-055` — `--json` output of a PQL error is valid JSON
- `PQL-075` — The parser's own remedy for `IS VALID` names a spelling that does not resolve
- `PQL-083` — A freshness control cannot be judged
- `PQL-092` — `HAS LENGTH BETWEEN` on a text column must not be a type error
- `PQL-093` — `HAS FORMAT` cannot be executed anywhere
- `PQL-101` — `SATISFIES a DETERMINES b`
- `PQL-140` — `AT LEAST n ROWS` renders as `AT MOST n ROWS`
- `PQL-141` — A large row threshold renders in scientific notation
- `PQL-150` — An amount threshold silently becomes a row count
- `PQL-154` — `HAVING` never reaches the plan
- `PQL-158` — An indeterminate segment beside passing segments
- `PQL-181` — The two volatile lists disagree
- `PQL-187` — `MIN` and `MAX` collide with the scalar catalogue
- `PQL-196` — `parse(render(x)) == x` for every assertion kind
- `PQL-199` — `!=` is missing from `BINDING` and `COMPARISONS`
- `PQL-219` — `prama control format` destroys suites
- `PQL-228` — Column resolution is case-insensitive but compilation is not
- `PQL-241` — `SATISFIES` conditions are never type-checked
- `PQL-264` — `CONCAT` with a NULL argument disagrees between SQL and the reference
- `PQL-266` — `argument_types` is declared and never enforced
- `PQL-268` — Each text function against its reference, including a NULL argument
- `PQL-269` — `LENGTH` of a non-text value
- `PQL-273` — `LEFT`, `RIGHT` and `MID` with a zero, a negative and an over-long length
- `PQL-287` — `MIN`/`MAX` with an unknown argument are unknown
- `PQL-288` — `IF` with an undetermined condition is undetermined
- `PQL-294` — `ISNUMBER` on each engine
- `PQL-300` — Reference arithmetic is exact, SQL arithmetic is not
- `PQL-331` — Excel `<>` produces an operator nothing downstream can handle
- `PQL-335` — Excel errors carry no position
- `PQL-338` — A bracketed column with a dot
- `PQL-366` — A selector on an unknown metadata name matches nothing, silently
- `PQL-384` — Diagnostics ignore every control inside a suite

**P2**
- `BE-005` — A dataset name containing a dot inside quotes is split anyway
- `BE-007` — A non-finite float literal
- `BE-034` — `scan_limit` with a correlated EXISTS
- `BE-037` — `SqlCompiler` carries mutable state between compilations
- `BE-055` — `IN` over an empty list
- `BE-056` — An unresolved codelist is refused, not guessed
- `BE-062` — `prama control compile` exits non-zero when nothing can run
- `BE-075` — A catastrophic pattern
- `BE-079` — Arithmetic on a boolean silently coerces
- `BE-096` — `APPROX_COUNT_DISTINCT` is silently zero
- `BE-097` — `SUM`, `MIN`, `MAX` and `AVG` over no numeric values
- `BE-100` — `run` materialises every row
- `BE-115` — `_round` on a non-numeric metric
- `BE-126` — A fused query produces no evidence samples
- `BE-129` — Two groups with the same description collide
- `BE-140` — `Case.requires` is declared and never consulted
- `BE-142` — Every corpus row is annotated with what it catches
- `BE-149` — The corpus has no arithmetic case beyond `/` and `%`
- `BE-158` — The generator covers a narrow slice of the language
- `BE-160` — A generated `HAS LENGTH BETWEEN` on a text column is type-clean
- `BE-168` — The declarations map one-to-one onto the controls
- `BE-172` — Integer values at the extremes
- `IR-021` — An empty codelist produces `IN ()`
- `PQL-015` — An empty quoted identifier `""`
- `PQL-035` — A non-ASCII identifier is refused with the quoting remedy
- `PQL-037` — Non-ASCII inside a quoted identifier and inside text is accepted
- `PQL-068` — A dangling dot after the dataset
- `PQL-082` — `IS FRESH WITHIN 0 MINUTES` is a zero tolerance, not a missing one
- `PQL-086` — `HAS UNIQUE KEY` with a qualified or duplicated column
- `PQL-089` — Row-count bounds must be whole numbers
- `PQL-099` — The target of a REFERENCES is never resolved
- `PQL-102` — `DETERMINES` with a non-column on either side is refused
- `PQL-112` — A set-level assertion under a selector expands into N copies of one control
- `PQL-128` — An owner containing a quote round-trips
- `PQL-132` — `EVIDENCE full (10)` loses the count on render
- `PQL-149` — `WITHIN n SIGMA` does not produce a sigma threshold
- `PQL-151` — A threshold on an assertion that has no rate
- `PQL-156` — Segment keys are ambiguous when a value contains the separator
- `PQL-159` — Segment totals sum metrics that cannot be summed
- `PQL-171` — `LIKE` and `ILIKE` are expression-only
- `PQL-175` — Deep nesting does not exhaust the stack
- `PQL-176` — An expression with 1,000 OR terms
- `PQL-189` — A parameter used only inside a metric expression is not declared
- `PQL-209` — A percentage round-trips losing precision
- `PQL-222` — `prama control format` discards comments
- `PQL-235` — `x IS NULL` is typed as a number
- `PQL-242` — A `HAVING` expression is never function-checked or type-checked
- `PQL-272` — `TRIM` of other whitespace
- `PQL-276` — `SUBSTITUTE` with an empty search string
- `PQL-280` — `ROUND` with a negative or very large number of places
- `PQL-339` — An empty bracket
- `PQL-346` — A trailing separator
- `PQL-353` — `IFERROR` is refused by name
- `PQL-369` — `tags = 'pii'` does not match
- `PQL-372` — `_is_true` accepts the string "true"
- `PQL-373` — A bare boolean fact under `NOT` and not under it disagree
- `PQL-402` — `from prama.pql import *` succeeds
- `PQL-403` — Every name in `__all__` is importable individually

**P3**
- `BE-095` — A distinct count over an unhashable value
- `BE-141` — `DUPLICATE_KEY` is declared and never used
- `PQL-005` — Nested block comments are not nested
- `PQL-064` — A suite name may be a keyword or quoted
- `PQL-166` — Reversed text bounds are not caught
- `PQL-177` — A control with 500 columns
- `PQL-182` — A quoted column named after a volatile function
- `PQL-341` — A nested bracket is impossible
- `PQL-350` — A column named `AND`

## The catalogue author's flagged likely-defect list, verified by execution

The task briefing named eleven items the catalogue author suspected were defects, to be verified
by running the code rather than trusting the flag. All eleven were executed directly.

| Flagged item | Verified | Case(s) |
|---|---|---|
| `IS UNIQUE` lowers to a null check, not a uniqueness test | **Already fixed — now PASS.** `Lowerer._is_unique` now lowers to a real `assertion_kind="unique_key"` set test; executed over duplicated rows it correctly returns FAIL. | PQL-072/PQL-073 (PASS), re-confirmed at BE-150 |
| `IS VALID ISIN` case-sensitivity in remedies | **Confirmed, real defect (P1).** The parser's own remedy text says `IS VALID ISIN`; the validator registry is a case-sensitive dict keyed lowercase, so the remedy's own literal advice fails with "there is no semantic type called 'ISIN'". | PQL-075 (FAIL) |
| Excel `<>` compiling nowhere | **Confirmed, real defect (P1).** `<>` maps to AST operator `!=`, which is absent from `ast.COMPARISONS`, `ast.BINDING` and `backend.sql.INFIX`; the SQL compiler refuses it and the reference interpreter raises an uncaught `KeyError`. It is the third example in the Excel module's own docstring. | PQL-331, BE-067 (FAIL) |
| Three disagreeing aggregate lists | **Confirmed.** `pql/types.py::_AGGREGATE_TYPES` (spells `MIN_AGG`/`MAX_AGG`), `backend/sql.py::_AGGREGATES` (omits `MIN`/`MAX`/`MEDIAN` entirely, routing them to the scalar catalogue or refusing them), and `ir/model.py::MetricAggregate` (no `STDDEV`) are three genuinely different lists. | PQL-186/PQL-187, BE-049 (FAIL); side observation in G5 |
| Formatter round-trip losses | **Confirmed, repeatedly.** `AT LEAST n ROWS` renders as `AT MOST`; large row thresholds go through `f"{v:g}"` and lose precision; percentages lose precision the same way; `EVIDENCE full (n)` drops its count; a freshness assertion's column is dropped entirely; an owner/suite-name containing a quote or a space is not re-escaped/re-quoted. | PQL-125(P), PQL-128, PQL-132, PQL-140, PQL-141, PQL-149, PQL-150, PQL-196, PQL-209, PQL-064 (FAIL, several) |
| SUITE controls invisible to `analysis.diagnostics` | **Confirmed, real defect (P1).** `diagnostics()` iterates `program.controls` (top-level only); a control wrapped in `SUITE … { }` only appears in `program.all_controls`, so every diagnostic inside a suite is silently missed. | PQL-384 (FAIL) |
| `HAS LENGTH BETWEEN` spurious type errors | **Confirmed, real defect (P1).** `_check_predicate`'s exemption list omits `has_length_between`, so every length control on every text column is flagged as comparing text with a number. Reproduced again with 271/271 generator-produced cases. | PQL-092, BE-160 (FAIL) |
| `WITHIN n SIGMA` unreachable | **Confirmed, real defect (P2).** `Threshold.render`/`.describe` carry a live `sigma` branch the parser can never produce — `SIGMA` tokenises as a plain identifier and is left as a stray token. | PQL-149 (FAIL) |
| Freshness controls permanently indeterminate | **Confirmed, real defect (P1), verified end-to-end.** Lowering drops the predicate; `_metrics` emits only `scanned_rows`; `_verdict` has no freshness branch. A real freshness control run over both obviously-fresh and obviously-stale rows returned INDETERMINATE in every case — the interpreter never reads `tolerance_minutes`, `due_time` or `calendar` at all. | PQL-083, BE-112 (FAIL) |
| `from prama.pql import *` raising | **Confirmed, real defect (P2).** `__all__` lists `Attribute`, `AttributeCatalogue`, `Drift`, `Expander`, `Expansion`, none of which `pql/__init__.py` imports; `import *` raises `AttributeError` in a fresh subprocess. | PQL-402, PQL-403 (FAIL) |
| Conformance corpus having no NULL samples / thin coverage | **Confirmed, and broader than stated.** The 23-row corpus has no `IN CODELIST`, no parameter, no `||`, and covers only 1 of 25 shipped functions; the `plan_for` builder cannot even lower an `IN CODELIST` case without a code change. NULL-in-`NOT IN` behaviour, once added, does agree across engines. | BE-141–BE-146, BE-149, BE-150 (FAIL); BE-148 (PASS — agreement once such a case is added) |


## Per-case results (id order, 629 rows)

| Id | Result | Observed |
|---|---|---|
| PQL-001 | FAIL | tokens produced: `end, identifier, keyword, number, operator, parameter, punctuation, regex` — no `string` kind appears (the example's only quoted text is `"odd name"`, a quoted identifier, not a `'...'` string literal) |
| PQL-002 | PASS | `[Token(end, '', line 1, column 1)]`, offset=0, length=1 |
| PQL-003 | PASS | one END token at line 4, column 1 |
| PQL-004 | PASS | `PqlSyntaxError: "a comment is opened with /* and never closed"`, position offset=22 (the `/*`), remedy names `*/` and `--` |
| PQL-005 | FAIL | raises `PqlSyntaxError: "a pattern is opened with / and never closed"` at the trailing `/` — not "a lexical error on `*`" as the catalog predicted |
| PQL-006 | PASS | first real token `CHECK` at line 2 |
| PQL-007 | PASS | ends cleanly with END, 8 tokens total, no exception |
| PQL-008 | PASS | `PqlSyntaxError: "a piece of text is opened with ' and never closed"`, remedy explains `''` doubling |
| PQL-009 | PASS | refused at the opening quote (line 1), not continued into line 2 |
| PQL-010 | PASS | `Token(string, "'O''Brien'")`, value=`"O'Brien"` |
| PQL-011 | PASS | one STRING token, `value == "'"` |
| PQL-012 | PASS | `text == "''"`, `value == ""` |
| PQL-013 | PASS | `PqlSyntaxError: "a quoted name is opened and never closed"`, remedy shows `"risk positions"` |
| PQL-014 | PASS | `Token(identifier, '"a""b"')`, `value == 'a"b'` |
| PQL-015 | FAIL | `parse_control('CHECK "".a IS NOT NULL')` parses; `target == '""'` — literally two quote characters |
| PQL-016 | PASS | `qualify` splits the quoted `"schema.table"` name into `"schema"."table"` in the compiled SQL, as documented |
| PQL-017 | PASS | `MATCHES`, `LIKE`, `ILIKE` all produce a REGEX token for the following `/…/` |
| PQL-018 | PASS | `a / b`, `1 / 2`, `(a) / 2`, `f(x) / 2` all lex `/` as OPERATOR, never REGEX |
| PQL-019 | PASS | `tokenise("/abc/")` → REGEX (cursor<0 branch) |
| PQL-020 | PASS | `PqlSyntaxError: "a pattern is opened with / and never closed"`, remedy gives `/^[A-Z]{2}[0-9]{10}$/` |
| PQL-021 | PASS | REGEX token, `value == "a\\/b"` — backslash kept, not resolved |
| PQL-022 | PASS | refused at the opening `/` (line 1) |
| PQL-023 | PASS | clean `PqlSyntaxError`, no `IndexError` |
| PQL-024 | PASS | `$ 1`, `$1`, `$` all raise `"$ must be followed by a parameter name"`, remedy names `$business_date` |
| PQL-025 | PASS | `Token(parameter, '$business_date')`, `value == "business_date"` |
| PQL-026 | PASS | all ten number forms lex as one NUMBER token, text preserved exactly |
| PQL-027 | PASS | each of `.5`,`1.`,`1_000`,`0x1F`,`1e`,`1%%` lexes as multiple tokens, and the parser refuses every one with a located `PqlSyntaxError`; none silently becomes a different number |
| PQL-028 | PASS | `-10` → OPERATOR `-` then NUMBER `10` |
| PQL-029 | PASS | `check`/`Check`/`CHECK` all KEYWORD, `text` preserves casing, `upper` is `CHECK` |
| PQL-030 | PASS | all 116 entries in `KEYWORDS` tokenise as KEYWORD |
| PQL-031 | PASS | `trades.on`, `trades.severity`, `trades.source`, `trades.count` all parse; `ColumnRef(name=…, dataset='trades')` with the exact column names |
| PQL-032 | PASS | `schema.a`, `record.a`, `key.a` all parse; `target` is the keyword's spelling |
| PQL-033 | PASS | `CHECK t.a IS NOT NULL WHERE where = 1` parses; `CHECK t.where IS NOT NULL` parses — no crash |
| PQL-034 | PASS | `PqlSyntaxError: "expected a column name after the dot and found '2'"`, remedy names double-quoting |
| PQL-035 | FAIL | raises `AssertionError` (bare, no message) — not a `PqlSyntaxError` |
| PQL-036 | FAIL | `tokenise("é")` raises `AssertionError: assert match is not None` |
| PQL-037 | FAIL | parses correctly and `because` value is preserved, but `ctrl.render()` drops the double quotes around `montànt`, producing unparseable output — reparsing the rendered text raises `AssertionError` |
| PQL-038 | PASS | `@ # & ! ~ ^` `` ` `` each raise `"'<ch>' does not belong in a control"`, `length=1` |
| PQL-039 | PASS | `>=` and `||` each lex as one token in isolation and inside `a>=b`/`a||b`; every other single-symbol operator lexes standalone too |
| PQL-040 | PASS | `a \| b` → `"'\|' does not belong in a control"` |
| PQL-041 | PASS | all ten punctuation marks emit PUNCTUATION |
| PQL-042 | PASS | every token's offset/line/column verified against source text; no mismatches |
| PQL-043 | PASS | `CHECK` after `-- comment\n  ` reports `line=2, column=3` |
| PQL-044 | PASS | identical `(kind, text, line, column)` sequence for LF and CRLF versions of the same source |
| PQL-045 | PASS | `C`,`(`,`'`,`/`,`$`,`1`,`-` each raise a located `PqlError` subclass; no crash |
| PQL-046 | PASS | 10,000-char identifier lexes as one IDENTIFIER token; forcing an unterminated-string error near it produces an excerpt windowed to ~64-76 chars, not the full 10,000 |
| PQL-047 | FAIL | `PqlSyntaxError` and `PqlTypeError` both render `message (at position)` + blank + excerpt + caret + blank + `→ remedy`; a genuine `PqlUnsupportedError` renders as `"sqlite cannot run ROUND (at line 1, column 1)\n\n→ …"` — no excerpt, no caret |
| PQL-048 | PASS | 5-character offending token → 5 `^` carets, aligned under the token |
| PQL-049 | PASS | error at column 316 of a long WHERE clause: window is `…`-prefixed, ≤64 chars wide, caret offset matches exactly |
| PQL-050 | PASS | `PqlSyntaxError("x", remedy="y")` (no source) renders `"x (at line 1, column 1)\n\n→ y"` — no excerpt block, no crash |
| PQL-051 | PASS | `Position(line=99)` over a 3-line source → `excerpt() == []`; `render()` still names `"at line 99, column 1"` |
| PQL-052 | PASS | `"position"` present in `.context` only when a `Position` was supplied |
| PQL-053 | PASS | `PqlError.code == "PQL.INVALID"`, `PqlSyntaxError == "PQL.SYNTAX"`, `PqlTypeError == "PQL.TYPE"`, `PqlUnsupportedError == "PQL.UNSUPPORTED"` — all four distinct |
| PQL-054 | PASS | all 9 real `raise PqlUnsupportedError` sites sit inside reachable-only-from-`compile`/`fuse` methods — none in a row-iteration/result path |
| PQL-055 | FAIL | `prama control check bad.pql --json` (exact catalog invocation) fails outright with argparse `"unrecognized arguments: --json"` (exit 2); run correctly as `prama --json control check bad.pql`, it still emits rendered prose, not JSON |
| PQL-056 | PASS | `Control(target='positions', assertion.operator='is_not_null', subject=(account_id,positions), severity=MAJOR, threshold=(rows,<=,0.0), unknown=VIOLATION)` |
| PQL-057 | PASS | parsed cleanly, `because=''`; lint reports `[('no-justification','info')]` |
| PQL-058 | PASS | `parse_control` on two controls raises "there is more text after the control: 'CHECK'"; `parse()` returns 2 controls |
| PQL-059 | PASS | all three inputs raise "expected a control and found …", remedy names CHECK and SUITE with a full example |
| PQL-060 | PASS | `Suite(name='core')` with 2 controls; `Program.controls=0`, `all_controls=2` |
| PQL-061 | PASS | `SUITE core { }` → `Suite` with 0 controls, no error |
| PQL-062 | PASS | "the suite 'core' is opened and never closed", remedy "Close it with }." |
| PQL-063 | PASS | "expected CHECK and found 'SUITE'" |
| PQL-064 | FAIL | `SUITE "core suite" { }` parses (`name='core suite'`); `.render()` → `'SUITE core suite {\n\n}'`; re-parsing that raises `expected '{' and found 'suite'` — round-trip broken |
| PQL-065 | PASS | two `SUITE core { }` blocks parse cleanly into 2 suites named `core`, no refusal |
| PQL-066 | PASS | `target='positions'`, `subject.name='notional'` |
| PQL-067 | PASS | `warehouse.risk.positions` raises a located "expected something to check about warehouse and found '.'" |
| PQL-068 | FAIL | `CHECK positions. IS NOT NULL` does not refuse at the dot; `IS` is consumed as the column name (since `_name` accepts keywords), producing a later, confusing error: "expected a comparison after positions.IS, found 'NULL'" |
| PQL-069 | PASS | "expected something to check about positions and found the end of the control", remedy lists all six constructs |
| PQL-070 | PASS | "this check is about a column, but no column was named", remedy names HAS ROW COUNT / HAS UNIQUE KEY |
| PQL-071 | PASS | `IS NOT NULL`→`operator='is_not_null'`, `IS NULL`→`operator='is_null'`; `negated=False` on both |
| PQL-072 | PASS | `IS NOT UNIQUE` → `operator='is_unique'`, `negated=True`; AST differs from plain `IS UNIQUE` |
| PQL-073 | PASS | `IS UNIQUE` lowers to `assertion_kind='unique_key'`, `predicate=None`; executed over duplicated `uti` rows → `Verdict.FAIL`, `duplicate_rows=1.0` — already fixed |
| PQL-074 | PASS | `isin`, `'isin'`, `ISIN` → literal values `'isin'`, `'isin'`, `'ISIN'` respectively, no case normalisation |
| PQL-075 | FAIL | `CHECK t.isin IS VALID ISIN` fails to lower: `ValidationError: there is no semantic type called 'ISIN'`; `VALIDATORS.find('isin')` resolves, `VALIDATORS.find('ISIN')` returns `None` |
| PQL-076 | PASS | resolves to `Expr.operation('IN', …)` containing shipped ISO 4217 values (`'USD'` present) |
| PQL-077 | PASS | `ValidationError: the codelist 'nosuchlist' is not registered` |
| PQL-078 | PASS | all four shapes parse; unset clauses default to `""` |
| PQL-079 | PASS | 30,1,240,60,2880,1440 minutes for the six spellings |
| PQL-080 | PASS | both `SECONDS` and `WEEKS` raise "expected MINUTES, HOURS or DAYS and found …" |
| PQL-081 | PASS | `1.5 HOURS` → "expected how long as a whole number and found '1.5'"; `-5 MINUTES` → located refusal "expected how long and found '-'" |
| PQL-082 | FAIL | `tolerance_minutes=0`, `due_time='06:30'`, but `describe()` returns `'the data arrives on time'` — due time dropped |
| PQL-083 | FAIL | lowers to `predicate=None`, `metrics=['scanned_rows']`; executed → `Verdict.INDETERMINATE` (no verdict is ever derived from arrival time) |
| PQL-084 | PASS | 1/3/50-column keys preserve order; `is_structural=True`; default threshold strict |
| PQL-085 | PASS | `HAS UNIQUE KEY ()` → located "expected a column name and found ')'" |
| PQL-086 | FAIL | `(t.a, t.a)` parses with both duplicate columns kept (`['t.a','t.a']`) — neither refused nor de-duplicated; `(other.a)` is correctly flagged by the type checker |
| PQL-087 | PASS | `(1,8)`, `(7,None)`, `(None,100)` |
| PQL-088 | PASS | both `> 100` and bare `100` raise "expected BETWEEN or AT LEAST/MOST after ROW COUNT" |
| PQL-089 | FAIL | `AT LEAST 1e6` raises a bare `ValueError: invalid literal for int() with base 10: '1e6'`, not a `PqlSyntaxError` |
| PQL-090 | PASS | `HAS ROW COUNT BETWEEN 0 AND 0` over 0 rows → `Verdict.PASS` |
| PQL-091 | PASS | `operator='has_length_between'`, `argument=12`, `upper=12` |
| PQL-092 | FAIL | type-checking `t.isin HAS LENGTH BETWEEN 12 AND 12` against `isin VARCHAR(12)` produces 2 findings: "t.isin holds text, and it is being compared with 12, which is number" |
| PQL-093 | FAIL | parses and lowers fine (no authoring-time refusal); `compile_for(…, "sqlite")` raises a proper `PqlUnsupportedError`; `ReferenceEvaluator().run` raises a bare `KeyError: 'HAS FORMAT'` — contradicts its own remedy's claim that "the local engine … evaluates anything the language can express" |
| PQL-094 | PASS | no spelling of `IS OF TYPE` parses; both attempts refused with "expected NULL, UNIQUE, VALID, FRESH or IN after IS, found 'OF'" |
| PQL-095 | PASS | `PRECISION`/`SCALE`/`DUPLICATE` all raise "expected UNIQUE KEY, ROW COUNT, LENGTH or FORMAT after HAS, found …" |
| PQL-096 | PASS | `INCREASING`/`NON`/`TRUE` all raise "expected NULL, UNIQUE, VALID, FRESH or IN after IS, found …" |
| PQL-097 | PASS | `ReferenceAssertion(column='account_id', target_dataset='accounts', target_column='account_id')` |
| PQL-098 | PASS | `REFERENCES accounts` (no dot) → "expected '.' and found the end of the control" |
| PQL-099 | FAIL | type-checking `REFERENCES accounts.nosuchcolumn` and `REFERENCES nosuchdataset.x` both produce **no findings** — the target is never validated against the catalogue |
| PQL-100 | PASS | `ExpressionAssertion`, `source_syntax='pql'` |
| PQL-101 | FAIL | `SATISFIES account_id DETERMINES legal_entity_id` parses correctly, but composite `(a, b) DETERMINES (c, d)` does not parse: `expected ')' and found ','` |
| PQL-102 | FAIL | `UPPER(a) DETERMINES b` and `a DETERMINES 1` correctly raise the DETERMINES-specific message; `(a, 1) DETERMINES b` instead raises the generic `expected ')' and found ','` |
| PQL-103 | PASS | unquoted `EXCEL =AND(...)` → "EXCEL must be followed by the formula in quotes" |
| PQL-104 | PASS | `a = 1` → `source_syntax='pql'`; `EXCEL '=[a]=1'` → `source_syntax='excel'` |
| PQL-105 | PASS | `Selector(kind='attribute', where=None)`, `is_template=True`, subject is `SelectedAttribute` |
| PQL-106 | PASS | condition is bare `ColumnRef('is_cde')`; assertion is `is_not_null` |
| PQL-107 | PASS | both `tags IN ('pii')` and `criticality IN (...)` bind to the condition; assertion is `is_not_null` |
| PQL-108 | PASS | `domain = ''` workaround parses; `domain IS NULL IS NOT NULL` is refused ("there is more text after the control: 'IS'") |
| PQL-109 | PASS | `Selector(kind='concept', concept='Instrument', concept_property='ISIN')` |
| PQL-110 | PASS | `CONCEPT Instrument IS VALID isin` → "expected '.' and found 'IS'" |
| PQL-111 | PASS | selector + `REFERENCES` → "a reference names one column on each side, so it cannot be written against a selector" |
| PQL-112 | FAIL | both `HAS ROW COUNT AT LEAST 1` and `SATISFIES a > 0` under a 5-attribute selector expand to 5 controls with identical (`==`) assertion objects — neither refused nor deduplicated |
| PQL-113 | PASS | `parse_control(A) == parse_control(B)` is `True` for the two clause orders |
| PQL-114 | PASS | all ten clauses landed on the correct `Control` field (where, segmentation, severity, dimensions, because, evidence, owner, unknown_policy, on_fail, threshold) |
| PQL-115 | PASS | each of the ten clause names, given twice, raised `"<clause> is given twice for this control"` with the stated remedy |
| PQL-116 | PASS | `AT MOST 5 ROWS BELOW 10%` → `PqlSyntaxError: threshold is given twice for this control` |
| PQL-117 | PASS | `PqlSyntaxError: there is more text after the control: 'SEVERTIY'`, positioned at column 23 — names the stray word, not "expected a control" |
| PQL-118 | PASS | all five values in lower/upper/mixed case resolved to the matching `Severity` member |
| PQL-119 | PASS | `'high'`/`'p1'`/`'3'` → `"'<x>' is not a severity"`, remedy `"Use one of: info, warning, minor, major, critical."` |
| PQL-120 | PASS | `SEVERITY` at EOF → located `PqlSyntaxError: '' is not a severity` at column 31; process terminates normally (no loop) |
| PQL-121 | PASS | all eight `Dimension` members resolve; `DIMENSION validity, consistency, accuracy` preserves order `['validity','consistency','accuracy']` |
| PQL-122 | PASS | `DIMENSION correctness` → `"'correctness' is not a quality dimension"`, remedy lists all eight |
| PQL-123 | PASS | `DIMENSION validity, validity` kept as written: `dimensions=(VALIDITY, VALIDITY)`, renders `DIMENSION validity, validity` |
| PQL-124 | PASS | unquoted → `"expected the reason…and found 'it'"`; double-quoted → same template, `found '"it matters"'`; both name single quotes in the remedy |
| PQL-125 | PASS | parsed `because == "the desk's own rule"`; rendered `BECAUSE 'the desk''s own rule'`; re-parsed value identical; `c == c2` is `True` |
| PQL-126 | PASS | `because == ''`; render omits the `BECAUSE` clause entirely; `Linter().check(c)` reports `('no-justification', 'info')` |
| PQL-127 | PASS | owner preserved as `'Head of Market Risk Data'`; renders `OWNER 'Head of Market Risk Data'`; re-parses identically |
| PQL-128 | FAIL | see below |
| PQL-129 | PASS | `counts`/`samples`/`full` map to the right `EvidenceLevel`; `EVIDENCE samples (10)` → `max_samples=10`; default is 50 |
| PQL-130 | PASS | `'all'`/`'rows'` → `"'<x>' is not an evidence level"`, remedy `"Use counts, samples, or full."` |
| PQL-131 | PASS | `EVIDENCE samples (0)` compiles a `sample_query` ending `LIMIT 0`; `(1000000)` ends `LIMIT 1000000` — no upper bound applied either way |
| PQL-132 | FAIL | see below |
| PQL-133 | PASS | `TREAT UNKNOWN AS PASS` with no BECAUSE → `PqlSyntaxError: TREAT UNKNOWN AS PASS needs a BECAUSE` |
| PQL-134 | PASS | both `VIOLATION` and `FAIL` parse to `UnknownPolicy.VIOLATION` with no BECAUSE required |
| PQL-135 | PASS | `AS NULL`/`AS IGNORE` → `"expected PASS or VIOLATION after TREAT UNKNOWN AS, found '<x>'"`, remedy explains the inverted default |
| PQL-136 | PASS | both orderings (`BECAUSE` before/after `TREAT UNKNOWN AS PASS`) parse identically to `policy=PASS, because='x'` |
| PQL-137 | PASS | `alert`/`block`/`quarantine`/`tag` → matching `FailAction` members |
| PQL-138 | PASS | `stop`/`page` → `"'<x>' is not something to do on failure"`, remedy lists all four |
| PQL-139 | PASS | `AT MOST 5 ROWS` → `comparator='<='`; `AT LEAST 5 ROWS` → `comparator='>='` |
| PQL-140 | FAIL | see below |
| PQL-141 | FAIL | see below |
| PQL-142 | PASS | `AT MOST 0.5 ROWS` parses to `Threshold(unit='rows', value=0.5, comparator='<=')`, i.e. accepted and judged as `violating_rows <= 0.5` (the documented second alternative) |
| PQL-143 | PASS | `AT MOST 5 ROWS` / `1 ROW` / bare `5` all yield `unit='rows'` |
| PQL-144 | PASS | `BELOW 0.5%` → `value=0.005`; `BELOW 0.5` → `value=0.5` — a hundredfold apart, as claimed |
| PQL-145 | PASS | `BELOW 100%` parses to `value=1.0`; `Linter().check` reports `('never-fires', 'error', 'a threshold of 100% cannot be exceeded…')` |
| PQL-146 | PASS | `BELOW 0%` → `is_strict=True`; render still emits `BELOW 0%` (unit is not `rows`) |
| PQL-147 | PASS | `WITHIN 100 USD`/`0.01 GBP`/`100` → `unit='amount'`, currency `'USD'`/`'GBP'`/`''` |
| PQL-148 | PASS | `WITHIN 100 SUM/MIN/KEY/ROW` each → `PqlSyntaxError: there is more text after the control: '<KEYWORD>'` — confirmed these are `KEYWORD`-kind tokens, not `IDENTIFIER`, so the currency branch never fires |
| PQL-149 | FAIL | see below |
| PQL-150 | FAIL | see below |
| PQL-151 | FAIL | see below |
| PQL-152 | PASS | `FOR EACH t.entity` → one column, `having=None`; `FOR EACH t.entity, t.ccy` → both columns in order |
| PQL-153 | PASS | `FOR EACH t.entity HAVING COUNT(*) > 100` parses the `having` expression into `Segmentation.having`, and it renders back correctly |
| PQL-154 | FAIL | see below |
| PQL-155 | PASS | reference evaluator and compiled SQLite both produced segment keys `{'None','X'}` with matching per-segment verdicts (`None`→FAIL, `X`→PASS) — they coincide |
| PQL-156 | FAIL | see below |
| PQL-157 | PASS | 5 segments produced (`e0`…`e4`), overall verdict `FAIL` because `e4` fails — Q-11 regression does not reproduce; already fixed |
| PQL-158 | FAIL | see below |
| PQL-159 | FAIL | see below |
| PQL-160 | PASS | `a OR b AND c` -> OR(a, AND(b,c)); precedence confirmed |
| PQL-161 | PASS | `NOT side = 'BUY'` -> NOT (side='BUY') |
| PQL-162 | PASS | double NOT renders/re-parses correctly |
| PQL-163 | PASS | `BETWEEN 1 AND 100 SEVERITY minor` -> bounds and severity correct |
| PQL-164 | PASS | `WHERE n BETWEEN 1 AND 100 AND status='ACTIVE'` -> correct AND/BETWEEN tree |
| PQL-165 | PASS | lint() -> always-fires, error, correct remedy |
| PQL-166 | FAIL | lint() on reversed text bounds -> only no-justification; no always-fires |
| PQL-167 | PASS | 1000-value IN list compiles fine, no recursion issue |
| PQL-168 | PASS | empty IN () -> PqlSyntaxError naming IS NULL |
| PQL-169 | PASS | trailing comma in IN list -> located refusal naming ')' |
| PQL-170 | PASS | NOT IN/BETWEEN/MATCHES/LIKE/ILIKE all parse to correct BinaryOp |
| PQL-171 | FAIL | assertion-form LIKE refused with different message than expected (not-a-defect, see below) |
| PQL-172 | PASS | LIKE on postgresql -> PqlUnsupportedError; reference -> bare KeyError |
| PQL-173 | PASS | `(a OR b) AND c` round-trips |
| PQL-174 | PASS | unclosed paren -> PqlSyntaxError naming end of control |
| PQL-175 | FAIL | 1000 nested parens -> uncaught RecursionError, not a located refusal |
| PQL-176 | FAIL | 1000 OR terms parses fine but resolved() raises uncaught RecursionError |
| PQL-177 | FAIL | 500-column unique key parses/lowers but compile_for raises uncaught RecursionError on all 3 dialects |
| PQL-178 | PASS | COUNT(*).arguments == (); distinct flag correct |
| PQL-179 | PASS | all ten non-deterministic names refused with $business_date remedy |
| PQL-180 | PASS | NOW()/RANDOM()/UUID() refused with same remedy |
| PQL-181 | FAIL | volatile lists overlap size 2 not 1; CURRENT_DATE/SYSDATE/UUID parse as plain ColumnRef in Excel — not refused at all |
| PQL-182 | FAIL | quoted AND unquoted `t.current_date` both parse fine (not-a-defect, see below) |
| PQL-183 | PASS | LENGTH/COUNT/MIN inside WHERE all parse as FunctionCall |
| PQL-184 | PASS | `CHECK LENGTH(t.isin) = 12` -> refused, remedy lists SATISFIES |
| PQL-185 | PASS | `count(a)` -> name normalised to COUNT; `upper(a)` -> stays lowercase |
| PQL-186 | PASS | MEDIAN absent from types/sql/library -> refused with clear message at both type-check and compile |
| PQL-187 | FAIL | `MIN(notional) > 0` as aggregate -> spurious arity finding "MIN takes at least 2 arguments" |
| PQL-188 | PASS | all three parameter forms appear in both plan.parameters() and CompiledControl.parameters |
| PQL-189 | FAIL | parameter used only inside a Metric expression -> plan.parameters() == frozenset() (not listed) |
| PQL-190 | PASS | `a = NULL` evaluates to None (UNKNOWN sentinel), never False |
| PQL-191 | PASS | `rate > 10%` round-trips through render/re-parse at value 0.1 |
| PQL-192 | PASS | unary minus never dropped in compiled SQL |
| PQL-193 | PASS | double-negative literal correctly means positive value, confirmed by evaluation |
| PQL-194 | PASS | `BETWEEN -10 AND 10` and `BETWEEN - 10 AND 10` -> identical plan_id |
| PQL-195 | PASS | `-TRUE` not folded to literal -1; stays a nested unary op |
| PQL-196 | FAIL | freshness assertion's `.a` column silently dropped on render — round-trip broken |
| PQL-197 | PASS | 207 controls (worked example + generated) all satisfy render(parse(render(x)))==render(x) |
| PQL-198 | PASS | PRECEDENCE-derived BINDING ordering strictly increasing, NOT correctly placed |
| PQL-199 | FAIL | `!=` missing from BINDING/COMPARISONS -> wrong bracketing when rendered |
| PQL-200 | PASS | redundant-paren removal correct across OR/AND/subtraction/division |
| PQL-201 | PASS | BETWEEN upper bound with AND inside correctly bracketed |
| PQL-202 | PASS | `CHECK positions.lei IS NOT NULL` round-trips exactly |
| PQL-203 | PASS | selector control round-trips exactly |
| PQL-204 | PASS | lowering un-expanded selector -> ValidationError |
| PQL-205 | PASS | default threshold omitted from render; explicit ones shown |
| PQL-206 | PASS | no explicit severity -> renders SEVERITY major |
| PQL-207 | PASS | Control.name always empty, never rendered |
| PQL-208 | PASS | dataclasses.replace with derived_from still equal (== True) |
| PQL-209 | FAIL | percentage literal loses precision on round-trip |
| PQL-210 | PASS | extreme float literals all round-trip exactly |
| PQL-211 | PASS | integer literal renders without trailing .0 |
| PQL-212 | PASS | quote/backslash/tab/NUL/emoji all round-trip through PQL; literal newline refused at parse |
| PQL-213 | PASS | 23 controls across all assertion kinds -> describe() always ends in '.' |
| PQL-214 | PASS | TREAT UNKNOWN AS PASS correctly reflected in describe() text |
| PQL-215 | PASS | threshold tolerance correctly reflected in describe() text |
| PQL-216 | PASS | BECAUSE punctuation never doubled across 5 variants |
| PQL-217 | PASS | selector describe() text correct for attribute and concept forms |
| PQL-218 | PASS | mixed suites+top-level document round-trips through render/re-parse |
| PQL-219 | FAIL | `prama control format --write` strips SUITE wrapper entirely |
| PQL-220 | PASS | format on unparseable file: exit 1, file left byte-identical |
| PQL-221 | PASS | first --write reports rewritten; second reports already canonical |
| PQL-222 | FAIL | format --write silently deletes comments, no warning printed |
| PQL-223 | PASS | expanded-selector BECAUSE with escaped quote round-trips through format --write |
| PQL-224 | PASS | `[]` — no findings for a correct control against a declared schema |
| PQL-225 | PASS | "positions has no column called acount_id", remedy "Did you mean account_id?" |
| PQL-226 | PASS | remedy lists 12 names then "…", for a 20-column schema |
| PQL-227 | PASS | ACCOUNT_ID/accountid/account_ids -> account_id; acct_id -> account_id too |
| PQL-228 | FAIL | checker accepts `positions.ACCOUNT_ID` ([] findings); dialect.quote emits "ACCOUNT_ID" verbatim — inconsistent |
| PQL-229 | PASS | one unchecked finding naming `t`, remedy about declaring/binding |
| PQL-230 | PASS | arity finding for UPPER(b,c) survives alongside the unchecked finding |
| PQL-231 | PASS | "accounts.b belongs to accounts, but this control is about positions" + relationship remedy |
| PQL-232 | PASS | all 25 ordered pairs of {number,text,boolean,temporal,unknown} match declared comparable set exactly |
| PQL-233 | PASS | VARCHAR(255)->text, NUMERIC(18,2)->number, TIMESTAMP WITH TIME ZONE->temporal, etc; 35 TYPE_FAMILIES entries mapped |
| PQL-234 | PASS | HUGEINT/JSONB/ARRAY<INT>/GEOGRAPHY vs number and text: no findings in any of 8 combos |
| PQL-235 | FAIL | `(b IS NULL) = TRUE` produces "t.b IS NULL holds number, ... compared with TRUE, which is boolean" |
| PQL-236 | PASS | `WHERE a = NULL` — no finding |
| PQL-237 | PASS | `WHERE text_col > $threshold` — no finding |
| PQL-238 | PASS | `IN ('GBP', 2, 'EUR')` -> exactly one finding naming 2 |
| PQL-239 | PASS | `notional MATCHES /.../` -> "a pattern cannot be matched against a number", remedy names BETWEEN |
| PQL-240 | PASS | IS VALID/IN CODELIST/HAS FORMAT/MATCHES on text and numeric columns: no spurious findings in 7 combos |
| PQL-241 | FAIL | `SATISFIES notional > 'ACTIVE'` -> []; equivalent WHERE clause -> one finding |
| PQL-242 | FAIL | `FOR EACH e HAVING NONSENSE(b) > 1` -> [] (no "no function called NONSENSE") |
| PQL-243 | PASS | "there is no function called UPPERR" plus the unchecked finding, both present |
| PQL-244 | PASS | UPPER(a,b)->"exactly 1", LEFT(a)->"exactly 2", CONCAT()->"at least 1", IF(a,b)->"exactly 3" |
| PQL-245 | PASS | TODAY()->"TODAY is refused..."; TODAYY()->"there is no function called TODAYY" |
| PQL-246 | PASS | `require` on unchecked-only returns; on bad-function control raises PqlTypeError |
| PQL-247 | PASS | 7 findings from one check() call |
| PQL-248 | PASS | `Finding(position=None).to_dict()` -> position: None, no exception |
| PQL-249 | PASS | get("positions")->None-like case sensitivity confirmed |
| PQL-250 | PASS | 1 column, family number, nullable=True, control checks clean |
| PQL-251 | PASS | `prama control functions`: 33 functions listed, per-engine share, ROUND refused on sqlite; flags work |
| PQL-252 | PASS | `--engine oracle` -> "no engine called 'oracle'", remedy lists duckdb/postgresql/sqlite |
| PQL-253 | PASS | all 25 base functions have callable evaluate |
| PQL-254 | PASS | Function with no sql/sql_by_engine -> ValidationError "has no SQL form" |
| PQL-255 | PASS | function refused on all 3 engines constructs and renders as refused |
| PQL-256 | PASS | registering NOW/TODAY/RAND/RANDBETWEEN/INDIRECT/OFFSET all raise ValidationError |
| PQL-257 | PASS | OFFSET -> "returns a reference resolved at evaluation time" |
| PQL-258 | PASS | VLOOKUP -> "there is no function called VLOOKUP", remedy lists all 25 |
| PQL-259 | PASS | `find("NOPE")` -> None; confirmed all callers guard with is None/is not None |
| PQL-260 | PASS | get("upper") is get("Upper") is get("UPPER") |
| PQL-261 | PASS | ROUND.render("sqlite") -> ValidationError "sqlite cannot express ROUND" |
| PQL-262 | PASS | CONCAT(a,b,c) -> function form on postgresql/duckdb, || chain on sqlite |
| PQL-263 | PASS | CONCAT(a) on sqlite executes to 'a' |
| PQL-264 | FAIL | reference/sqlite CONCAT(a,NULL)->None(UNKNOWN); postgresql and duckdb -> 'a' |
| PQL-265 | PASS | CONCAT.expected_type at various positions -> text |
| PQL-266 | FAIL | UPPER(notional) against a numeric column -> [] findings (no family check) |
| PQL-267 | PASS | ROUND engines=[postgresql,duckdb]; UPPER engines=all 3 |
| PQL-268 | FAIL | most text functions agree (NULL); CONCAT disagrees with no documented note |
| PQL-269 | FAIL | LENGTH(123.45): reference=6, sqlite=6, postgresql/duckdb raise |
| PQL-270 | PASS | LENGTH('日本語')=3, LENGTH('café')=4 everywhere |
| PQL-271 | PASS | TRIM('  a   b  ') -> 'a   b' everywhere |
| PQL-272 | FAIL | TRIM of tab/newline/nbsp: reference strips all; engines leave most untouched |
| PQL-273 | FAIL | LEFT/MID with zero/negative/over-long args disagree across engines and reference |
| PQL-274 | PASS | MID('abcdef',1,3)->'abc', MID('abcdef',3,2)->'cd' everywhere |
| PQL-275 | PASS | SUBSTITUTE with 4 args -> "exactly 3 argument(s), and was given 4" |
| PQL-276 | FAIL | SUBSTITUTE with empty search string: reference inserts between every char; engines leave unchanged |
| PQL-277 | PASS | ROUND(2.675,2)->2.68 etc, matching banker's-adjacent behaviour on postgresql/duckdb/reference |
| PQL-278 | PASS | ROUND(1953193.4649,2) on duckdb -> 1953193.46 (no double rounding) |
| PQL-279 | PASS | compiling ROUND for sqlite -> PqlUnsupportedError |
| PQL-280 | FAIL | ROUND(1.5,40) crashes with decimal.InvalidOperation |
| PQL-281 | PASS | INT(-7.5)->-8 everywhere |
| PQL-282 | PASS | INT(7.5) executes fine on this SQLite build; no crash observed |
| PQL-283 | PASS | MOD(5,0) -> NULL/UNKNOWN everywhere |
| PQL-284 | PASS | MOD(-10,3)->-1, MOD(10,-3)->1 everywhere |
| PQL-285 | PASS | SIGN(0)->0, SIGN(-7.5)->-1, SIGN(NULL)->UNKNOWN everywhere |
| PQL-286 | PASS | MIN(a) -> arity finding; MIN(a,b,c) -> LEAST on postgresql/duckdb, MIN on sqlite |
| PQL-287 | FAIL | MIN(3,NULL): reference/sqlite -> NULL; postgresql/duckdb LEAST(3,NULL) -> 3 |
| PQL-288 | FAIL | IF(NULL,1,2): reference -> UNKNOWN; compiled CASE WHEN NULL -> 2 on all engines |
| PQL-289 | PASS | IF(TRUE,1,NULL)->1, IF(FALSE,NULL,2)->2 |
| PQL-290 | PASS | COALESCE(NULL,NULL,3)->3, COALESCE(NULL,NULL)->UNKNOWN, IFBLANK(NULL,'x')->'x' |
| PQL-291 | PASS | COALESCE('','x')->''; ISBLANK('')->True |
| PQL-292 | PASS | NULL/''/whitespace->True, 0/FALSE->False everywhere |
| PQL-293 | PASS | ISBLANK(EXPENSIVE(x)) renders the argument twice |
| PQL-294 | FAIL | ISNUMBER('  7 '): reference True, engines False; ISNUMBER(NULL): reference False, engines NULL |
| PQL-295 | PASS | compiling ISNUMBER on regex-less dialect -> PqlUnsupportedError naming pushdown.regex |
| PQL-296 | PASS | YEAR/MONTH/DAY over 3 ISO dates: reference and all 3 engines agree |
| PQL-297 | PASS | YEAR('not a date') divergence documented as described (duckdb now raises rather than NULL) |
| PQL-298 | PASS | YEAR(d) over a real DATE column: all agree at 2026 |
| PQL-299 | PASS | ABS(TRUE), ROUND(TRUE,0), MIN(TRUE,1) all -> UNKNOWN via reference |
| PQL-300 | FAIL | catalogue-function Decimal path gives exact 0.3; reference float arithmetic gives 0.30000000000000004; sqlite raw SQL also imprecise |
| PQL-301 | PASS | all 12 non-empty excel_divergence notes mention both Excel's and Prama's behaviour |
| PQL-302 | PASS | control using TRIM/ROUND/CONCAT -> 4 divergence/refusal lines |
| PQL-303 | PASS | TRIM inside HAVING found by _function_names, divergence printed |
| PQL-304 | PASS | 25 declared, 25 unique names, len(default_registry())==25 |
| PQL-305 | PASS | custom DOUBLEIT function registered at runtime found by check_calls, compiles and interprets correctly |
| PQL-306 | PASS | `BELOW 100%`, `BELOW 150%`, `BELOW 1` all produce `never-fires` at `error` severity |
| PQL-307 | PASS | `BELOW 99.9%` produces no findings |
| PQL-308 | PASS | no-bounds `RowCountAssertion` -> "a row count with no bounds asserts nothing" (error); `AT LEAST 0` -> "every dataset has at least zero rows" (error) |
| PQL-309 | PASS | `BETWEEN 100 AND 1` -> `always-fires`, error |
| PQL-310 | PASS | `HAS ROW COUNT BETWEEN 100 AND 1` -> "the row count range is empty, so this can never pass" |
| PQL-311 | PASS | `HAS LENGTH BETWEEN 12 AND 12` -> no finding |
| PQL-312 | PASS | missing BECAUSE -> `no-justification` at `info`; `prama control check` exit 0, `--strict` exit 1 |
| PQL-313 | PASS | two controls differing in clause order/severity/owner/BECAUSE -> one `duplicate` finding naming the other |
| PQL-314 | PASS | `AT MOST 0 ROWS` vs `AT MOST 5 ROWS` -> no duplicate finding |
| PQL-315 | PASS | `ON FAIL BLOCK` vs `ON FAIL ALERT`, same assertion -> reported as `duplicate` |
| PQL-316 | PASS | 1000-literal `IN` list + pattern-literal `MATCHES` control -> no `TypeError`, lints cleanly |
| PQL-317 | PASS | `t.n > 0` beside `t.n IS NOT NULL` -> `subsumed`, "already fails on a null" |
| PQL-318 | PASS | same pair with `TREAT UNKNOWN AS PASS` -> no subsumption finding |
| PQL-319 | PASS | every member of `NULL_SENSITIVE` is a violation on a null row via `ReferenceEvaluator.is_violation` |
| PQL-320 | PASS | different `WHERE` -> no finding; different `FOR EACH` -> no finding |
| PQL-321 | PASS | weaker control with `AT MOST 5 ROWS` -> no finding |
| PQL-322 | PASS | `IN ('GBP')` beside `IN ('GBP','USD')` -> `subsumed` |
| PQL-323 | PASS | `IN ($a, 'GBP')` vs `IN ('GBP','USD')` -> no finding |
| PQL-324 | PASS | three controls, two subsuming a third -> exactly one finding on the third |
| PQL-325 | PASS | null-sensitive pair -> exactly 1 subsumed finding, not 2 |
| PQL-326 | PASS | 5,000 controls linted in 7.58s, 0 findings, no crash |
| PQL-327 | PASS | no `related` -> rendered text omits "related:" line; with `related` -> both present |
| PQL-328 | PASS | `CHECK EVERY ATTRIBUTE HAS ROW COUNT AT LEAST 0` lints without crashing |
| PQL-329 | PASS | Excel `AND([quantity]>0,...)` and PQL `quantity>0 AND ...` produce structurally equal trees |
| PQL-330 | PASS | `'=[a] > 0'` and `'[a] > 0'` produce equal trees |
| PQL-331 | FAIL | see below |
| PQL-332 | PASS | `'=[a] & [b] = "xy"'` -> `BinaryOp('=', CONCAT(a,b), 'xy')` |
| PQL-333 | PASS | nested `CONCAT` compiles correctly on sqlite/postgresql/duckdb and interprets correctly via reference |
| PQL-334 | PASS | `'=[a]^2 > 4'` -> `PqlSyntaxError: ^ is not supported`, remedy about engine disagreement |
| PQL-335 | FAIL | see below |
| PQL-336 | PASS | `''`, `'='`, `'   '` all -> "the formula is empty", no `IndexError` |
| PQL-337 | PASS | `'=[a] > 0 [b]'` -> "unexpected '[b]' after the formula" |
| PQL-338 | FAIL | see below (not-a-defect) |
| PQL-339 | FAIL | see below |
| PQL-340 | PASS | `[notional amount]`, `[a-b]`, `[日本]`, `[  notional amount  ]` all become correctly named/stripped columns |
| PQL-341 | FAIL | see below |
| PQL-342 | PASS | `'=[a] = "say ""hi"""'` -> `Literal(value='say "hi"')` |
| PQL-343 | PASS | `"=[a] = 'USD'"` -> refusal naming `'` |
| PQL-344 | PASS | comma- and semicolon-separated `IF(...)` produce identical trees |
| PQL-345 | PASS | `'=IF([a]>0, 1; 2)'` parses successfully |
| PQL-346 | FAIL | see below |
| PQL-347 | PASS | `AND([a]>0,[b]>0)` and `[a]>0 AND [b]>0` produce the same chain |
| PQL-348 | PASS | `'=AND([a]>0)'` -> "AND takes at least two arguments" |
| PQL-349 | PASS | `NOT([a]>0)` -> `UnaryOp(NOT, [a]>0)`; `NOT [a]>0` -> `(NOT [a]) > 0` |
| PQL-350 | FAIL | see below (not-a-defect) |
| PQL-351 | PASS | `VLOOKUP(...)` -> "there is no function called VLOOKUP" |
| PQL-352 | PASS | `TODAY()`,`NOW()`,`RAND()`,`RANDBETWEEN()`,`INDIRECT()`,`OFFSET()` all refused with a "has to replay" remedy |
| PQL-353 | FAIL | see below |
| PQL-354 | PASS | Excel `LEFT([a])` and PQL `LEFT(a)` both give "LEFT takes exactly 2 argument(s), and was given 1" |
| PQL-355 | PASS | `'=A1 > 0'` -> `ColumnRef('A1')`; `'=SUM(A1:B2)'` -> refused on `':'` |
| PQL-356 | PASS | Excel control renders as `SATISFIES EXCEL '=AND([a]>0, [b]>0)'`, re-parses equal |
| PQL-357 | PASS | `SATISFIES EXCEL '=[a] = "it''s"'` round-trips |
| PQL-358 | PASS | `describe()` -> "every row satisfies the formula =AND([a]>0, [b]>0)" |
| PQL-359 | PASS | `CHECK EVERY ATTRIBUTE WHERE is_cde IS NOT NULL` over 3 CDEs -> 3 concrete controls |
| PQL-360 | PASS | each expanded control renders and re-parses equal |
| PQL-361 | PASS | expansion with no BECAUSE -> `because == "Selected by EVERY ATTRIBUTE WHERE is_cde"` |
| PQL-362 | PASS | selector matching nothing -> `expand()` returns `[]` |
| PQL-363 | PASS | `expand()` on a concrete control -> `ValidationError` |
| PQL-364 | PASS | mixed list of templates + concrete controls -> concrete ones pass through by identity unchanged |
| PQL-365 | PASS | all 11 facts match via their respective selectors |
| PQL-366 | FAIL | see below |
| PQL-367 | PASS | `tags IN ('pii')` matches both pii-tagged attributes |
| PQL-368 | PASS | `tags NOT IN ('pii')` matches exactly the non-pii attributes |
| PQL-369 | FAIL | see below |
| PQL-370 | PASS | empty-domain attribute: `domain = 'Credit Risk'` excludes it; `NOT (domain = 'Credit Risk')` includes it |
| PQL-371 | PASS | `_value(IS NULL, {"domain": ""})` -> `True`; `_value(IS NULL, {"domain": None})` -> `True` |
| PQL-372 | FAIL | see below (not-a-defect) |
| PQL-373 | FAIL | see below (not-a-defect) |
| PQL-374 | PASS | `CONCEPT Instrument.ISIN` matches; `CONCEPT instrument.isin` matches 0 (case-sensitive) |
| PQL-375 | PASS | same 3 attributes in two orders -> identical digest |
| PQL-376 | PASS | full set vs set-minus-one -> different digests |
| PQL-377 | PASS | empty expansion -> digest of empty string, `count==0` |
| PQL-378 | PASS | approved snapshot losing 1 / gaining 4 -> `Drift.render()` names both |
| PQL-379 | PASS | unchanged catalogue -> "covers exactly what it covered when approved" |
| PQL-380 | PASS | 20 new attributes -> render lists 5 names + "…, 20 more" |
| PQL-381 | PASS | resolving an unexpanded selector raises `ValidationError`; `Expander`/`expand_all` referenced nowhere in any run/CLI path |
| PQL-382 | PASS | `diagnostics("")` -> `[]`; `diagnostics("   \n")` -> `[]` |
| PQL-383 | PASS | `diagnostics("CHECK positions")` -> one error-level diagnostic, remedy present |
| PQL-384 | FAIL | `diagnostics("SUITE core { CHECK positions.nosuchcolumn IS NOT NULL }")` -> `[]` (no diagnostics at all) |
| PQL-385 | PASS | `LintFinding` severities: never-fires=error, no-justification=info; both rendered as Diagnostic(level="warning") |
| PQL-386 | PASS | Two controls both naming unknown dataset -> only one diagnostic emitted (documented dedup) |
| PQL-387 | PASS | Undeclared-dataset finding -> level="unchecked", severity==3 |
| PQL-388 | PASS | `_at(None)` -> zeros; has_position -> False |
| PQL-389 | PASS | `CHECK positions.` -> completions of declared columns with type+nullability detail |
| PQL-390 | PASS | Unknown dataset with empty catalogue -> `[]` |
| PQL-391 | PASS | Prefix match returns dataset/function/keyword kinds together |
| PQL-392 | PASS | Dataset name matched case-insensitively for completions |
| PQL-393 | PASS | Hover on column -> title+type+nullability+family |
| PQL-394 | PASS | Hover on dataset half -> dataset hover with column list |
| PQL-395 | PASS | Hover on undeclared dataset -> "not declared...will not be verified" |
| PQL-396 | PASS | Hover on typo column -> "Did you mean account_id?" |
| PQL-397 | PASS | Hover on function/keyword -> summary/remedy info |
| PQL-398 | PASS | Column-position boundary cases at 0/1/3/4/5 all correct |
| PQL-399 | PASS | Out-of-range hover positions -> empty Hover, no exception |
| PQL-400 | PASS | Direct LanguageService calls vs JSON-RPC server produced identical results |
| PQL-401 | PASS | AST import-scan of pql/** -> no reference to ir or backend |
| PQL-402 | FAIL | `from prama.pql import *` in a fresh subprocess -> `AttributeError: module 'prama.pql' has no attribute 'Attribute'`, exit code 1 |
| PQL-403 | FAIL | `getattr(prama.pql, name)` for each of `__all__` (38 names) -> 5 missing: Attribute, AttributeCatalogue, Drift, Expander, Expansion |
| PQL-404 | PASS | Every TYPE_FAMILIES value and shipped Function type is a member of FAMILIES |
| PQL-405 | PASS | Column of undeclared type compared with >, =, IS NOT NULL -> no findings in any case |
| IR-001 | PASS | Same control lowered twice in-process and once in a fresh subprocess -> identical plan id |
| IR-002 | PASS | Whitespace/clause-reordering variants -> same id |
| IR-003 | PASS | Differing SEVERITY/DIMENSION/BECAUSE/OWNER -> identical plan id |
| IR-004 | PASS | EVIDENCE COUNTS vs FULL -> identical plan id |
| IR-005 | PASS | Threshold/filter/policy/predicate/segment changed one at a time -> 6 distinct ids |
| IR-006 | PASS | Same control, two `binding` values -> two different ids |
| IR-007 | PASS | `meaning()["ir_version"] == IR_VERSION`; patching IR_VERSION and re-lowering -> different id |
| IR-008 | PASS | `canonical()` insensitive to nested-key insertion order; detail with None/float/bool/list hashes fine |
| IR-009 | PASS | `IS VALID 'lei'` carries residual_validators; `IS VALID 'uuid'` does not; ids differ |
| IR-010 | PASS | Swapping recorded implementation_hash for a plugin validator changes the plan id |
| IR-011 | PASS | Same validator/column dedups to one residual; different validators give deterministic sorted list |
| IR-012 | PASS | `is_two_stage == bool(residual_validators)` held for all 23 corpus plans |
| IR-013 | PASS | `IS VALID 'lei'` over a FunctionCall subject -> ValidationError |
| IR-014 | PASS | uuid, ulid, email, bic, mic, uti, upi, hex_colour -> no residual for any |
| IR-015 | PASS | `IS VALID 'nosuchtype'` -> ValidationError naming it |
| IR-016 | PASS | One control per kind -> assertion_kind = predicate, unique_key, row_count, reference, freshness, functional_dependency |
| IR-017 | PASS | Bare `ast.Assertion()` -> ValidationError |
| IR-018 | PASS | 10 textual operator forms + is_of_type -> violating_rows uniformly count_if(NOT predicate) |
| IR-019 | PASS | NOT IN/NOT BETWEEN/NOT MATCHES -> outer NOT wraps the positive form |
| IR-020 | PASS | IN CODELIST 'iso4217' resolved -> literal IN list of 179 values; list change changes plan id |
| IR-021 | FAIL | Empty codelist lowers without refusal to IN over an empty list; compiles to `"x" IN ()` |
| IR-022 | PASS | Different as_of dates -> different resolved codelist members and different ids |
| IR-023 | PASS | `resolved(control).plan_id == Lowerer(codelists=CODELISTS.resolve(None)).control(control).plan_id` |
| IR-024 | FAIL | `resolved(ctrl, as_of=date(...))` on a control with real parameter `$other_param` -> Scope.as_of holds a date object; SqlCompiler.compile raises unhandled `TypeError` |
| IR-025 | PASS | `Lowerer(` used outside resolve.py/lower.py only in conformance.py and induce/validate.py, matching the catalogue's claim |
| IR-026 | PASS | Predicate control -> 2 metrics; applies_unknown_policy True/False correctly split |
| IR-027 | PASS | HAS UNIQUE KEY (a,b) -> scanned_rows, distinct_keys, null_key_rows; null condition is OR chain |
| IR-028 | PASS | HAS UNIQUE KEY (a) -> single IS NULL, not an OR chain |
| IR-029 | PASS | SATISFIES a DETERMINES b over rows with a repeated determinant -> PASS |
| IR-030 | PASS | HAS ROW COUNT BETWEEN 1 AND 8 -> one metric, predicate is None, detail carries bounds |
| IR-031 | PASS | REFERENCES -> predicate is EXISTS operation, assertion_kind == "reference" |
| IR-032 | PASS | Compiling a reference plan against a dialect lacking cross_object_join -> PqlUnsupportedError naming the capability |
| IR-033 | PASS | Regex, aggregation, approx-distinct, cross-object-join all surface in plan.requires |
| IR-034 | PASS | columns() found predicate/filter/segment/key/determinant/dependent columns correctly |
| IR-035 | PASS | Threshold with missing metric -> INDETERMINATE |
| IR-036 | PASS | scanned_rows=0 -> INDETERMINATE for absolute and relative_to thresholds |
| IR-037 | FAIL | `Threshold(...).evaluate({"violating_rows": 0})` with no scanned_rows key at all -> Verdict.PASS |
| IR-038 | PASS | relative_to threshold with denominator 0 or absent -> INDETERMINATE in both |
| IR-039 | PASS | All six comparators correct at, just below, and just above the boundary |
| IR-040 | PASS | is_actionable: FAIL/ERROR/INDETERMINATE True; PASS/SKIPPED False |
| IR-041 | PASS | lit(None) vs lit(0) vs lit(False) all serialise distinctly |
| IR-042 | PASS | All 23 corpus plans -> to_json() round-trips, embedded id matches plan_id |
| IR-043 | PASS | detail with Decimal/date/set/NaN each hashes without exception |
| IR-044 | PASS | AST import-scan of backend/** -> no reference to pql.ast |
| BE-001 | PASS | dialect("postgresql")->PostgresDialect, dialect("duckdb")->DuckDbDialect, dialect("sqlite")->SqliteDialect |
| BE-002 | PASS | "oracle"/""/"POSTGRESQL" all raise RegistryError, remedy lists all three |
| BE-003 | PASS | every embedded quote doubled correctly, all six inputs valid |
| BE-004 | PASS | 1/2/3-part qualified names all correct |
| BE-005 | FAIL | dotted single-part name always split, no escape hatch |
| BE-006 | FAIL | `literal(Decimal("1.5"))` -> `'1.5'` (string, not number) |
| BE-007 | FAIL | `literal(nan)`/`literal(inf)` -> bare invalid SQL tokens |
| BE-008 | PASS | FALSE on postgresql/duckdb, 0 on sqlite |
| BE-009 | PASS | FILTER form on postgresql/duckdb, CASE WHEN on sqlite |
| BE-010 | PASS | all three engines return 0 (not NULL) over empty scope |
| BE-011 | PASS | count_distinct agrees across all three constructions and engines |
| BE-012 | FAIL | composite key separator collision on SQLite: count_distinct returns 1 not 2 |
| BE-013 | PASS | FILTER and CASE WHEN forms agree exactly over null key parts |
| BE-014 | PASS | ~/regexp_matches/REGEXP all match correctly |
| BE-015 | FAIL | non-portable regex features (lookbehind, inline flags) disagree across engines with raw driver errors, no flavour-naming refusal |
| BE-016 | FAIL | `MATCHES /[/ ` compiles with no error at all; `/*/ ` rejected only by comment-tokenizer confusion, not regex validation |
| BE-017 | PASS | `regex_match` on base dialect -> Unsupported with exact expected message |
| BE-018 | PASS | dialect declares REGEX unconditionally; unregistered sqlite connection fails at execution |
| BE-019 | PASS | MATCHES on DATE/NUMERIC casts correctly and matches on DuckDB |
| BE-020 | PASS | CAST(...AS VARCHAR) on DATE/TIMESTAMP identical across engines and Python str() |
| BE-021 | PASS | integer division control agrees pass across all engines and reference |
| BE-022 | PASS | DOUBLE PRECISION on postgresql/duckdb, REAL on sqlite |
| BE-023 | FAIL | bare `%` on PostgreSQL fails to execute at all (UndefinedFunction); other engines/reference agree |
| BE-024 | FAIL | modulo-by-zero: PostgreSQL raises (aborts query), DuckDB/SQLite silently NULL, reference UNKNOWN — no agreement |
| BE-025 | PASS | referential control compiles to EXISTS, never IN (SELECT ...) |
| BE-026 | PASS | null-FK row: SQL and reference agree in both default and TREAT UNKNOWN AS PASS policies |
| BE-027 | PASS | null-safe equality forms correct per engine |
| BE-028 | PASS | scan_limit wraps source correctly, no trailing LIMIT on aggregate |
| BE-029 | FAIL | PostgreSQL declares pushdown.approx_distinct but APPROX_COUNT_DISTINCT fails to execute (no such builtin) |
| BE-030 | PASS | basic metric query structure correct on all three engines |
| BE-031 | PASS | FOR EACH compiles to GROUP BY correctly |
| BE-032 | PASS | MATCHES against regex-less dialect -> PqlUnsupportedError naming pushdown.regex before any SQL emitted |
| BE-033 | PASS | scan_limit=100 executes cleanly on real PostgreSQL 16; no alias required (catalogue's claim conflates with MySQL) |
| BE-034 | FAIL | scan_limit + correlated EXISTS fails on DuckDB: BinderException, unaliased subquery column resolution broken |
| BE-035 | PASS | same-name-both-sides REFERENCES correctly finds orphan rows |
| BE-036 | PASS | fused and unfused metric SQL byte-identical |
| BE-037 | FAIL | SqlCompiler carries stale `_source` state between compilations when `.expression()` called directly |
| BE-038 | PASS | NOT COALESCE / COALESCE NOT correctly reflect unknown policy |
| BE-039 | PASS | comparison/MATCHES/IN/BETWEEN/REFERENCES agree across all engines+reference under TREAT UNKNOWN AS PASS |
| BE-040 | PASS | row_count/unique_key/FD/freshness plans all have predicate=None, violation FALSE, empty sample query |
| BE-041 | PASS | sample query bounded by max_samples, projects plan.columns() |
| BE-042 | PASS | sample_query empty for EVIDENCE counts, non-empty for samples/full |
| BE-043 | PASS | empty columns() -> SELECT * in sample query |
| BE-044 | PASS | all Expr kinds compile correctly; expression(None) -> TRUE |
| BE-045 | PASS | parameters render correctly, sorted and complete |
| BE-046 | PASS | unknown function -> PqlUnsupportedError listing full catalogue |
| BE-047 | PASS | ROUND on sqlite -> clean refusal, no substitution offered |
| BE-048 | PASS | ISNUMBER on regex-less dialect -> clean refusal naming pushdown.regex |
| BE-049 | FAIL | MIN/MAX fall through to scalar LEAST/GREATEST (wrong arity); MEDIAN refused outright |
| BE-050 | PASS | all 14 INFIX operators render correctly, / and % route through dialect hooks |
| BE-051 | PASS | malformed Expr.operation with 1 arg -> PqlUnsupportedError naming it a compiler defect |
| BE-052 | PASS | unary minus on column renders correctly |
| BE-053 | PASS | NOT/IS NULL/IS NOT NULL/IN/NOT IN/BETWEEN/NOT BETWEEN/EXISTS/MATCHES/NOT MATCHES all correct |
| BE-054 | FAIL | LIKE/ILIKE/NOT LIKE/NOT ILIKE/HAS FORMAT (all real, reachable syntax) raise "has no SQL form" |
| BE-055 | FAIL | `IN` over empty list compiles with no refusal to `("a" IN ())`, engine then rejects it |
| BE-056 | FAIL | unresolved codelist refuses cleanly; malformed 1-arg IN CODELIST node raises bare IndexError |
| BE-057 | PASS | MATCHES on DATE column casts first and executes on DuckDB |
| BE-058 | PASS | IS VALID 'lei' plan compiles with is_complete=False, residual_validators set |
| BE-059 | PASS | full ControlRun/evidence pipeline on failing screened control: caveat attached correctly on failing branch too |
| BE-060 | PASS | all 23 corpus-conformance plans compile and round-trip through JSON |
| BE-061 | PASS | `prama control compile mixed.pql` emits SQL for runnable control, refusal comment for the other, correct summary line |
| BE-062 | FAIL | `prama control compile allbad.pql` where both controls are refused still exits 0 |
| BE-063 | PASS | AND/OR/NOT truth tables over all 9/3 combos of {T,F,U} exactly match Kleene logic |
| BE-064 | PASS | AND/OR/NOT over 9 combos: reference and sqlite compiled SQL gave identical violation counts (8/4/6) |
| BE-065 | PASS | `notional > 0` on a null row -> `None` (UNKNOWN) |
| BE-066 | PASS | `_compare('>', 'abc', 5)` -> `None` (UNKNOWN) |
| BE-067 | FAIL | `CHECK t SATISFIES EXCEL '=[a]<>5'` lowers to `Expr.operation("!=",...)`; `ReferenceEvaluator.evaluate` raises untyped `KeyError: '!='` |
| BE-068 | FAIL | `a='1'` (TEXT), `b=1` (INTEGER): reference verdict `FAIL`, sqlite verdict `PASS` — disagree |
| BE-069 | PASS | `IN`: x=1->True, x=3->UNKNOWN; `NOT IN`: x=1->False, x=3->UNKNOWN |
| BE-070 | PASS | `NULL IN ('a')` -> UNKNOWN; `NULL NOT IN ('a')` -> UNKNOWN |
| BE-071 | PASS | BETWEEN: 0->T,1000->T,-1->F,1001->F,NULL->U; NOT BETWEEN is the Kleene negation in every case |
| BE-072 | PASS | `MATCHES /A/` on `'BAB'` -> True (search semantics, not fullmatch) |
| BE-073 | FAIL | Same value 1.10, pattern `/^[0-9]+\.[0-9]{2}$/`: reference (`str(1.10)='1.1'`) -> FAIL; duckdb DECIMAL cast -> `'1.10'` -> PASS — disagree |
| BE-074 | PASS | Pattern cache holds 1 entry after 1000 rows of one literal pattern (bounded for literals) |
| BE-075 | FAIL | `MATCHES /(a+)+b/` against 40 `a`s did not complete within 8s and was not refused |
| BE-076 | PASS | `+ - * / %` with a null operand -> UNKNOWN in every case |
| BE-077 | PASS | `a/0` -> UNKNOWN, `a%0` -> UNKNOWN |
| BE-078 | FAIL | `SATISFIES (a + b) > 0` over two text columns raises uncaught `ValueError: could not convert string to float: 'hello'` |
| BE-079 | FAIL | `flag + 1 = 2` (flag=True) -> `True` (silently coerces); `ABS(flag) = 1` -> `UNKNOWN` (refuses) — two different answers to the same mistake |
| BE-080 | FAIL | `a=0.1,b=0.2,c=0.3`: `(a+b)=c` -> False; `ROUND(a+b,2)=c` -> also False (`Decimal('0.30') == 0.3` is False) — rounding does not reconcile |
| BE-081 | PASS | `-NULL` -> UNKNOWN; `-'abc'` -> UNKNOWN |
| BE-082 | PASS | All 20 strict functions in the registry return UNKNOWN when given an unknown argument |
| BE-083 | PASS | `ISBLANK(NULL)=True, IF(TRUE,1,NULL)=1, COALESCE(NULL,1)=1, IFBLANK(NULL,1)=1, ISNUMBER(NULL)=False`; registry has 5 non-strict functions, not 4 |
| BE-084 | PASS | `COUNT(x)` as a row expression -> UNKNOWN |
| BE-085 | PASS | `MOD(5,0)` -> `None`, and `is UNSET` is False (never leaks the singleton) |
| BE-086 | PASS | `bool(UNSET)` raises `TypeError` with the exact documented message |
| BE-087 | PASS | `UnknownValue() is UnknownValue() is UNSET` -> True |
| BE-088 | PASS | true->not-violation, false->violation, unknown(default)->violation, unknown(TREAT AS PASS)->not-violation |
| BE-089 | PASS | `IS VALID 'lei'` over the corpus -> 3 violations total; row 6 is a violation |
| BE-090 | PASS | `is_violation` (batch) and manual screen+`fails_residual` (simulated streaming) agree exactly |
| BE-091 | PASS | A row with `lei=None`: `fails_residual` returns False (skipped), confirming the null-skip |
| BE-092 | PASS | A plan carrying an unknown validator name raises typed `ValidationError` naming it |
| BE-093 | PASS | A row with an unknown filter is excluded from both numerator and denominator identically on reference and sqlite |
| BE-094 | PASS | `distinct_keys`/`null_key_rows` identical between reference (7.0/0.0) and sqlite (7/0) over the corpus |
| BE-095 | FAIL | A unique-key control over a list-valued column raises a bare untyped `TypeError: unhashable type: 'list'` |
| BE-096 | FAIL | `APPROX_COUNT_DISTINCT(x)` metric over 3 distinct values -> `0.0` |
| BE-097 | FAIL | `SUM`/`MIN` over 0 rows and over all-null rows -> `0.0` in every case (SQL would say NULL) |
| BE-098 | PASS | A referential control with no related dataset raises `MissingRelatedDataset` naming `'accounts'` |
| BE-099 | PASS | `_value_sets` cache has exactly 1 entry after 5000x2000-row referential run (0.01s, not quadratic) |
| BE-100 | FAIL | Running over a 200,000-row generator: `[dict(r) for r in rows]` fully materialises it (46MB peak); no documented limit found in source |
| BE-101 | PASS | 3 rows / 2 violations with `EVIDENCE samples (10)`: `ControlResult.samples` is `()` |
| BE-102 | PASS | `backend/reference.py` imports neither `backend.sql` nor `backend.dialect`; it does import `pql.library` (the shared catalogue) |
| BE-103 | PASS | Identical metrics judged for 4 different `engine=` labels -> identical verdict |
| BE-104 | PASS | Corpus unique-key: `duplicate_rows=1.0`, `violating_rows=1.0` (not 2) |
| BE-105 | PASS | Synthetic rows: `violating_rows(3.0) == duplicates(1.0) + null_key_rows(2.0)` |
| BE-106 | PASS | Corpus `ccy DETERMINES entity`: `violating_rows(2.0) == pairs(7.0) - determinants(5.0)` |
| BE-107 | PASS | Metrics missing `distinct_keys` -> no `violating_rows` invented, verdict INDETERMINATE |
| BE-108 | PASS | Empty table: both unique-key and functional-dependency verdicts are INDETERMINATE |
| BE-109 | PASS | Empty table, `HAS ROW COUNT BETWEEN 1 AND 8` -> FAIL |
| BE-110 | PASS | `_row_count_verdict` with no `scanned_rows` -> INDETERMINATE |
| BE-111 | PASS | Row counts 0,1,8,9 against `BETWEEN 1 AND 8` -> fail, pass, pass, fail |
| BE-112 | FAIL | Other 5 assertion kinds each reach PASS and FAIL. Freshness (`IS FRESH WITHIN 30 MINUTES OF '06:30'`), run end-to-end over both "obviously fresh" and "obviously stale" rows, produced INDETERMINATE in every case |
| BE-113 | PASS | `comparable()` for two `ControlResult`s differing only in `engine`/`samples`/`detail` are equal; keys are exactly `{verdict, metrics, segments}` |
| BE-114 | PASS | Raw floats `0.1+0.2 != 0.3`, but `comparable()` (rounds to 9dp) reports them equal |
| BE-115 | FAIL | `_round(Decimal('1.5'))` works fine, but `_round(None)` and `ControlResult(metrics={'sum_x': None}).comparable()` both raise uncaught `TypeError: float() argument must be a string or a real number, not 'NoneType'` |
| BE-116 | PASS | 20 controls over one scope grouped into 1 group of size 20 |
| BE-117 | PASS | 4 controls differing in filter/binding/segmentation each produced their own group: 4 groups |
| BE-118 | PASS | Two controls differing only in threshold/severity grouped into 1 group |
| BE-119 | PASS | Two filters compiling to identical SQL text grouped into 1 group |
| BE-120 | PASS | Grouping+fusing the same plan list twice produced byte-identical SQL |
| BE-121 | PASS | 20 controls sharing scanned_rows: exactly one shared column, owned by all 20 |
| BE-122 | PASS | unpack on 5 controls returned 5 ControlResults with independent verdicts |
| BE-123 | PASS | unpack([]) returned 5 results, all INDETERMINATE, no IndexError |
| BE-124 | PASS | 3 segmented controls fused: each result carries the same 3 segment keys |
| BE-125 | FAIL | PqlUnsupportedError raised for the whole group, stopping the ordinary control too |
| BE-126 | FAIL | FusedQuery has no sample_query field; EVIDENCE samples produces zero samples when fused |
| BE-127 | PASS | 20 controls in 3 scans rendered correct summary sentence |
| BE-128 | PASS | rows_read is None and "reading about" absent when a dataset's size is None |
| BE-129 | FAIL | Two groups differing only in binding produced 2 groups but rows_per_scan had only 1 entry (keyed on describe(), omits binding) |
| BE-130 | PASS | cost([]) handled cleanly, no ZeroDivisionError |
| BE-131 | PASS | All 23 corpus cases run on duckdb+sqlite+reference: conforming=True, 0 disagreements |
| BE-132 | FAIL | see below (not-a-defect) |
| BE-133 | PASS | A runner raising RuntimeError produced status="failed", reported as a disagreement |
| BE-134 | PASS | Patched sqlite compiler to always refuse: sqlite correctly dropped from engines_that_ran |
| BE-135 | FAIL | compare() on reference-only case returns [], indistinguishable from genuine agreement |
| BE-136 | PASS | Neutered two-stage screen correctly flagged as a disagreement |
| BE-137 | PASS | Undeclared screen_violations produced a disagreement naming it |
| BE-138 | PASS | Over-large declared screen_violations produced a disagreement |
| BE-139 | FAIL | No corpus rows: _compare_two_stage returns [] (silence) rather than a failure |
| BE-140 | FAIL | Case.requires never consulted anywhere in conformance.py |
| BE-141 | FAIL | DUPLICATE_KEY declared and never used; unique_key case hardcodes columns directly |
| BE-142 | FAIL | Rows 1, 2 and 7 of ROWS have no entry in ROW_NOTES |
| BE-143 | FAIL | Only LENGTH exercised (indirectly); other 24 shipped functions appear in zero corpus cases |
| BE-144 | FAIL | Adding an IN CODELIST case raises ValidationError; plan_for builds a bare Lowerer() |
| BE-145 | PASS | REFERENCES case (built manually) agreed across reference+sqlite+duckdb |
| BE-146 | FAIL | Runner type has no parameter-binding channel at all; a $threshold case cannot be run |
| BE-147 | PASS | All 23 cases over empty corpus: non-row-count cases INDETERMINATE, row-count cases correct |
| BE-148 | PASS | NULL-in-NOT-IN-list case agreed identically on duckdb, sqlite and reference |
| BE-149 | FAIL | +,-,* agree; || crashes the reference interpreter with KeyError |
| BE-150 | FAIL | see below (partial not-a-defect on IS UNIQUE) |
| BE-151 | PASS | Quoted identifiers (reserved word, space, quote, non-ASCII) all correct on 3 dialects |
| BE-152 | PASS | create_table DDL accepted by sqlite and duckdb |
| BE-153 | PASS | insert_rows placeholder styles both correct |
| BE-154 | PASS | Seed 42 generated identically across two processes |
| BE-155 | PASS | Seed 42 identical on Python 3.13 and 3.14 |
| BE-156 | PASS | 1000 generated controls: 0 parse/lowering failures |
| BE-157 | PASS | 250 generated controls against duckdb: 150 fail, 66 pass, 34 indeterminate |
| BE-158 | FAIL | No comment/docstring states the emitted-shapes or exclusion lists |
| BE-159 | PASS | Seed 2 TREAT UNKNOWN AS PASS control parsed; threshold is the default (no actual threshold) |
| BE-160 | FAIL | 271/271 generated HAS LENGTH BETWEEN controls produced a spurious type-checker finding |
| BE-161 | PASS | Worked example suite has exactly 7 controls |
| BE-162 | PASS | All 7 controls lower and compile on sqlite, duckdb, postgresql |
| BE-163 | PASS | All 7 verdicts matched EXPECTED exactly |
| BE-164 | PASS | Row-count control passed with scanned_rows=7 |
| BE-165 | PASS | Linter reported one subsumed finding as expected |
| BE-166 | PASS | 3-column unique key control agreed across sqlite/duckdb/reference |
| BE-167 | PASS | MONITOR/RECONCILE/DERIVES all raise comprehensible PqlSyntaxError |
| BE-168 | FAIL | Declarations and controls do not correspond 1:1 |
| BE-169 | PASS | One control per kind through the full pipeline on all engines agreed |
| BE-170 | PASS | 500 controls over 10 datasets: lowered in 0.03s, 15 scans |
| BE-171 | PASS | ~1MB control with 90,000-item IN list parsed in 1.1s |
| BE-172 | FAIL | 100-digit integer: plan.plan_id raises raw TypeError from orjson |
| BE-173 | PASS | 20% threshold: sqlite/duckdb/reference all agree PASS |
| BE-174 | PASS | 7 operators x 2 unknown policies: all 14 combinations agree across 3 paths |
| BE-175 | PASS | Comparisons/arithmetic/ABS/SIGN/INT/MOD/ROUND all agree or correctly documented as refused |
| BE-176 | PASS | LENGTH/MATCHES/IN over non-ASCII agreed on all 3 paths |
| BE-177 | PASS | plan_id identical end to end across plan/compiled/result/evidence |
| BE-178 | FAIL | Identical metrics + different thresholds -> different verdicts but no threshold field on evidence record |
| BE-179 | FAIL | Plugin implementation-hash freezing never fires; PLUGINS is always empty |
| BE-180 | PASS | No leakage of prama.llm/prama.assistant into execute.py/ir; layering test passes |

## Failures

### PQL-001 · Every token kind the lexer can emit is reachable
- **Expected:** one token of each of KEYWORD, IDENTIFIER, NUMBER, STRING, REGEX, PARAMETER, OPERATOR, PUNCTUATION, and a terminating END
- **Observed:** no `string` kind appears in the tokenisation of the catalog's own example sentence
- **Reproduce:** `python3 -c "from prama.pql.tokens import tokenise; print(sorted(t.kind.value for t in tokenise('CHECK t.\"odd name\" MATCHES /^A/ AND n > \$d, 1.5e3 -- tail')))"`
- **Severity:** P1
- **Assessment:** not-a-defect — the example sentence contains only a double-quoted identifier (`"odd name"`), never a single-quoted `'...'` string literal, so this input cannot exercise the STRING kind. The lexer does emit STRING correctly for genuine string literals (PQL-010/011/012 all pass) — the gap is in the chosen example text, not in `Lexer._next`.

### PQL-005 · Nested block comments are not nested
- **Expected:** the comment ends at the first `*/`; the trailing `*/` is then a lexical error on `*`
- **Observed:** `PqlSyntaxError: "a pattern is opened with / and never closed"` raised at the trailing `/`, not an error on `*`
- **Reproduce:** `python3 -c "from prama.pql.tokens import tokenise; tokenise('/* a /* b */ CHECK t.a IS NOT NULL */')"`
- **Severity:** P3
- **Assessment:** not-a-defect — `*` lexes cleanly as `OPERATOR '*'` (multiplication); since the previous token is an operator, `_previous_allows_division` returns `False`, so the following `/` is read as opening a new (never-closed) pattern. The catalog under-traced what `*` does on its own.

### PQL-015 · An empty quoted identifier `""`
- **Expected:** either a refusal naming the empty name, or a dataset whose name is genuinely `""` — never a dataset literally called `""` including its quotes
- **Observed:** `parse_control('CHECK "".a IS NOT NULL').target == '""'`
- **Reproduce:** `python3 -c "from prama.pql.parser import parse_control; print(repr(parse_control('CHECK \"\".a IS NOT NULL').target))"`
- **Severity:** P2
- **Assessment:** defect — `_name` returns `token.value or token.text`, and an empty `value` falls through to the raw quoted text, so the dataset name silently becomes the two-character string `""`.

### PQL-035 · A non-ASCII identifier is refused with the quoting remedy
- **Expected:** `PqlSyntaxError` on the accented character
- **Observed:** bare `AssertionError` (no message) from `Lexer._word`
- **Reproduce:** `python3 -c "from prama.pql.parser import parse_control; parse_control('CHECK t.montànt IS NOT NULL')"`
- **Severity:** P2
- **Assessment:** defect — `_IDENTIFIER` matches only `"mont"`; the next lexer call starts on `à`, where `character.isalpha()` is `True` (Unicode-aware) so `_next` dispatches to `_word()` again, but `_IDENTIFIER.match` fails there and `assert match is not None` fires, crashing with `AssertionError` instead of a located `PqlSyntaxError`.

### PQL-036 · A non-ASCII letter cannot crash the word scanner
- **Expected:** a `PqlSyntaxError`, never `AssertionError: match is not None`
- **Observed:** `tokenise("é")` raises `AssertionError`
- **Reproduce:** `python3 -c "from prama.pql.tokens import tokenise; tokenise('é')"`
- **Severity:** P1
- **Assessment:** defect — same root cause as PQL-035.

### PQL-037 · Non-ASCII inside a quoted identifier and inside text is accepted
- **Expected:** both accepted, values preserved exactly, and the rendered control re-parses
- **Observed:** parses correctly, but `ctrl.render()` emits `montànt` without its double quotes; re-parsing raises `AssertionError` (same crash as PQL-036)
- **Reproduce:** `python3 -c "from prama.pql.parser import parse_control; c = parse_control('CHECK \"montànt\".x IS NOT NULL BECAUSE \'x\''); r = c.render(); print(r); parse_control(r)"`
- **Severity:** P2
- **Assessment:** defect — the formatter fails to re-quote an identifier that needs quoting (contains a non-ASCII character), producing round-trip output that cannot be re-parsed.

### PQL-047 · Every PQL error renders position, excerpt, caret and remedy
- **Expected:** the full five-part format for one error of each of the three subclasses
- **Observed:** `PqlSyntaxError`/`PqlTypeError` render fully; a genuine `PqlUnsupportedError` (via `compile_for`) renders only message + remedy — no excerpt, no caret
- **Reproduce:** `python3 -c "from prama.pql.parser import parse_control; from prama.ir.resolve import resolved; from prama.backend.sql import compile_for; plan = resolved(parse_control('CHECK t.a IS NOT NULL WHERE ROUND(t.a, 2) > 1')); compile_for(plan, 'sqlite', table='t')"`
- **Severity:** P1
- **Assessment:** not-a-defect — none of the 9 real `raise PqlUnsupportedError` sites ever pass `position=`/`source=`, since this error class operates on the already-lowered plan, not source text; `PqlError.excerpt()` is explicitly designed to degrade gracefully with no source (exactly what PQL-050 verifies and expects). The catalog assumed uniform excerpt behaviour without checking whether any real site supplies a source.

### PQL-055 · `--json` output of a PQL error is valid JSON
- **Expected:** a JSON document carrying message, remedy, code and position
- **Observed:** the catalog's literal invocation fails with `unrecognized arguments: --json` (exit 2) since `--json` is a top-level flag; run correctly as `prama --json control check bad.pql`, it still prints rendered prose, not JSON, exit 1
- **Reproduce:** `echo "CHECK t.a IS NOT NULL /* forgot" > bad.pql && prama --json control check bad.pql`
- **Severity:** P1
- **Assessment:** defect — `ControlCheckCommand`'s `_read()` helper catches `PqlError` itself and calls `ctx.emit(exc.render())` unconditionally, returning `EXIT_ERROR` directly, so the exception never reaches the `Application.run` handler that would call `ctx.emit_json`.

### PQL-064 · A suite name may be a keyword or quoted
- **Expected:** both parse; `Suite.render()` re-emits them and the result re-parses
- **Observed:** `SUITE "core suite" { }` parses fine, but `render()` emits `SUITE core suite {\n\n}` (unquoted), and re-parsing that raises `expected '{' and found 'suite'`
- **Reproduce:** `python3 -c "from prama.pql.parser import parse; p=parse('SUITE \"core suite\" { }'); r=p.suites[0].render(); print(r); parse(r)"`
- **Severity:** P3
- **Assessment:** defect — `Suite.render` does not re-quote a name containing a space, exactly as the catalogue's own Why predicts, breaking the round-trip.

### PQL-068 · A dangling dot after the dataset
- **Expected:** "expected a column name after the dot and found 'IS'"
- **Observed:** parses `IS` as the column name (since `_name` accepts keywords with no dot-specific guard), then fails much later with "expected a comparison after positions.IS, found 'NULL'"
- **Reproduce:** `python3 -c "from prama.pql.parser import parse_control; parse_control('CHECK positions. IS NOT NULL')"`
- **Severity:** P2
- **Assessment:** defect — `_target` has no guard preventing a keyword like `IS` from being silently accepted as a dangling-dot's column name.

### PQL-075 · The parser's own remedy for `IS VALID` names a spelling that does not resolve
- **Expected:** the control lowers
- **Observed:** `lower(parse_control("CHECK t.isin IS VALID ISIN"))` raises `ValidationError: there is no semantic type called 'ISIN'`; `VALIDATORS.find('isin')` succeeds, `VALIDATORS.find('ISIN')` returns `None`
- **Reproduce:** `python3 -c "from prama.pql.parser import parse_control; from prama.ir.lower import lower; lower(parse_control(\"CHECK t.isin IS VALID ISIN\"))"`
- **Severity:** P1
- **Assessment:** defect — still present. `ValidatorRegistry.find` is a case-sensitive dict lookup; every shipped validator is registered lowercase.

### PQL-082 · `IS FRESH WITHIN 0 MINUTES` is a zero tolerance, not a missing one
- **Expected:** "the data arrives on time"; the due time is not lost
- **Observed:** `describe()` returns exactly `'the data arrives on time'` with `due_time='06:30'` present on the object but omitted from the sentence
- **Reproduce:** `python3 -c "from prama.pql.parser import parse_control; print(parse_control(\"CHECK t IS FRESH WITHIN 0 MINUTES OF '06:30'\").assertion.describe())"`
- **Severity:** P2
- **Assessment:** defect — `FreshnessAssertion.describe()` branches on `tolerance_minutes == 0` and drops `due_time` from the sentence entirely.

### PQL-083 · A freshness control cannot be judged
- **Expected:** a verdict derived from the arrival time
- **Observed:** lowers to `predicate=None`, `metrics=['scanned_rows']`; `ReferenceEvaluator.run` returns `Verdict.INDETERMINATE`
- **Reproduce:** `python3 -c "from prama.pql.parser import parse_control; from prama.ir.lower import lower; from prama.backend.reference import ReferenceEvaluator; p=lower(parse_control(\"CHECK t IS FRESH WITHIN 30 MINUTES OF '06:30'\")); print(ReferenceEvaluator().run(p,[{'a':1}]).verdict)"`
- **Severity:** P1
- **Assessment:** defect — confirmed still present; `_verdict` has no "freshness" branch and falls to `threshold.evaluate`, which finds no `violating_rows` metric and returns `INDETERMINATE` unconditionally.

### PQL-086 · `HAS UNIQUE KEY` with a qualified or duplicated column
- **Expected:** the duplicate is either refused or de-duplicated; a foreign qualifier is refused by the type checker
- **Observed:** `HAS UNIQUE KEY (t.a, t.a)` parses with both columns kept verbatim — neither refused nor de-duplicated. `HAS UNIQUE KEY (other.a)` is correctly caught by the type checker.
- **Reproduce:** `python3 -c "from prama.pql.parser import parse_control; c=parse_control('CHECK t HAS UNIQUE KEY (t.a, t.a)'); print([(x.dataset,x.name) for x in c.assertion.columns])"`
- **Severity:** P2
- **Assessment:** defect — `_column_list`/`_columns_of` has no de-duplication or repeat check.

### PQL-089 · Row-count bounds must be whole numbers
- **Expected:** `1e6` accepted by `_integer`'s spelling guard, then `int("1e6")` raises a located error, not a bare `ValueError`
- **Observed:** `HAS ROW COUNT AT LEAST 1e6` raises a bare `ValueError: invalid literal for int() with base 10: '1e6'` that propagates out of the parser uncaught
- **Reproduce:** `python3 -c "from prama.pql.parser import parse_control; parse_control('CHECK t HAS ROW COUNT AT LEAST 1e6')"`
- **Severity:** P2
- **Assessment:** defect — `_integer` guards only on `.` and `%` and then calls `int(token.text)` unguarded; an exponent form escapes as a raw `ValueError`.

### PQL-092 · `HAS LENGTH BETWEEN` on a text column must not be a type error
- **Expected:** no findings
- **Observed:** type-checking `CHECK t.isin HAS LENGTH BETWEEN 12 AND 12` against `isin VARCHAR(12)` produces 2 findings: "t.isin holds text, and it is being compared with 12, which is number"
- **Reproduce:** `python3 -c "
from prama.pql.parser import parse_control
from prama.pql.types import TypeChecker, DatasetSchema, Column, Catalogue
c = parse_control('CHECK t.isin HAS LENGTH BETWEEN 12 AND 12')
tc = TypeChecker(Catalogue(datasets={'t': DatasetSchema(name='t', columns=(Column(name='isin', type_name='VARCHAR(12)'),))}))
print(tc.check(c))"`
- **Severity:** P1
- **Assessment:** defect — `_check_predicate`'s skip-list (`in_codelist`, `is_valid`, `has_format`, `matches`) omits `has_length_between`, so every length control on every text column reports a spurious type error.

### PQL-093 · `HAS FORMAT` cannot be executed anywhere
- **Expected:** a working control, or a refusal at authoring time naming the gap
- **Observed:** parses and lowers without any refusal; `compile_for(plan, "sqlite")` raises a well-formed `PqlUnsupportedError`, but `ReferenceEvaluator().run(...)` raises a bare, uncaught `KeyError: 'HAS FORMAT'`
- **Reproduce:** `python3 -c "
from prama.pql.parser import parse_control
from prama.ir.lower import lower
from prama.backend.reference import ReferenceEvaluator
p = lower(parse_control('CHECK t.iban HAS FORMAT iban'))
ReferenceEvaluator().run(p, [{'iban':'GB29NWBK60161331926819'}])"`
- **Severity:** P1
- **Assessment:** defect — nothing refuses this control at authoring/lowering time, and the two execution paths fail two different ways.

### PQL-099 · The target of a REFERENCES is never resolved
- **Expected:** a finding naming the unknown target
- **Observed:** type-checking `REFERENCES accounts.nosuchcolumn` and `REFERENCES nosuchdataset.x` both produce `findings=[]`
- **Reproduce:** `python3 -c "
from prama.pql.parser import parse_control
from prama.pql.types import TypeChecker, DatasetSchema, Column, Catalogue
tc = TypeChecker(Catalogue(datasets={'accounts': DatasetSchema(name='accounts', columns=(Column(name='account_id'),)), 'positions': DatasetSchema(name='positions', columns=(Column(name='account_id'),))}))
print(tc.check(parse_control('CHECK positions.account_id REFERENCES accounts.nosuchcolumn')))
print(tc.check(parse_control('CHECK positions.account_id REFERENCES nosuchdataset.x')))"`
- **Severity:** P2
- **Assessment:** defect — `_columns_of` appends only `assertion.column` for a `ReferenceAssertion`; the target dataset/column are never checked against the catalogue.

### PQL-101 · `SATISFIES a DETERMINES b`
- **Expected:** a `FunctionalDependencyAssertion` with the columns in order, for both the single-column and parenthesised composite forms
- **Observed:** the single form parses correctly. The composite form, `SATISFIES (a, b) DETERMINES (c, d)`, fails to parse at all: `expected ')' and found ','`
- **Reproduce:** `python3 -c "from prama.pql.parser import parse_control; parse_control('CHECK t SATISFIES (a, b) DETERMINES (c, d)')"`
- **Severity:** P1
- **Assessment:** defect — `_primary`'s `(` handling parses exactly one inner expression before requiring `)`; it never builds an `ast.ListExpression` from a parenthesised comma list, so the composite `DETERMINES` form is unreachable from any actual grammar production.

### PQL-102 · `DETERMINES` with a non-column on either side is refused
- **Expected:** "the left/right of DETERMINES must be one or more columns" for all three inputs
- **Observed:** `UPPER(a) DETERMINES b` and `a DETERMINES 1` correctly raise the DETERMINES-specific message; `(a, 1) DETERMINES b` instead raises the generic `expected ')' and found ','`
- **Reproduce:** `python3 -c "from prama.pql.parser import parse_control; parse_control('CHECK t SATISFIES (a, 1) DETERMINES b')"`
- **Severity:** P2
- **Assessment:** defect — direct consequence of PQL-101's root cause.

### PQL-112 · A set-level assertion under a selector expands into N copies of one control
- **Expected:** a refusal, or one control — not five identical ones the linter will then report as duplicates
- **Observed:** both `HAS ROW COUNT AT LEAST 1` and `SATISFIES a > 0` under a selector matching 5 attributes expand into 5 controls whose assertions compare equal (`==`) to each other
- **Reproduce:** harness `/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/lang/g2/harness.py`, case PQL-112; minimal form: build a 5-attribute `AttributeCatalogue` all `is_cde=True`, `Expander(catalogue).expand(parse_control("CHECK EVERY ATTRIBUTE WHERE is_cde HAS ROW COUNT AT LEAST 1"))` returns 5 controls with identical assertions
- **Severity:** P2
- **Assessment:** defect — `_rebind` only substitutes into a `PredicateAssertion` whose subject is the `SelectedAttribute` placeholder; every other assertion kind is copied unchanged.

### PQL-128 · An owner containing a quote round-trips
- **Expected:** the same value twice
- **Observed:** parsed `owner == "O'Brien"`; `render()` emits `OWNER 'O'Brien'` (unescaped); re-parsing that raises `PqlSyntaxError: a piece of text is opened with ' and never closed`
- **Reproduce:** `python3 -c "from prama.pql.parser import parse_control; c=parse_control(\"CHECK t.a IS NOT NULL OWNER 'O''Brien'\"); r=c.render(); print(r); parse_control(r)"`
- **Severity:** P2
- **Assessment:** defect — `Control.render` (src/prama/pql/ast.py:764) escapes `because` (`.replace("'", "''")`, line 766) but emits `OWNER '{self.owner}'` with no equivalent escaping, exactly as the catalogue's Why states.

### PQL-132 · `EVIDENCE full (10)` loses the count on render
- **Expected:** `parse(render(x)) == x`
- **Observed:** parsed `EvidenceSpec(level=FULL, max_samples=10)`; rendered as `EVIDENCE full` (count dropped); re-parsed gives `max_samples=50`; `c == c2` is `False`
- **Reproduce:** `python3 -c "from prama.pql.parser import parse_control; c=parse_control('CHECK t.a IS NOT NULL EVIDENCE full (10)'); r=c.render(); c2=parse_control(r); print(c.evidence, c2.evidence, c==c2)"`
- **Severity:** P2
- **Assessment:** defect — `EvidenceSpec.render` (src/prama/pql/ast.py:665-668) emits the parenthesised count only when `level is SAMPLES`.

### PQL-140 · `AT LEAST n ROWS` renders as `AT MOST n ROWS`
- **Expected:** equality after round-trip
- **Observed:** rendered text is `AT MOST 5 ROWS` (comparator dropped); re-parsed control has `comparator='<='` instead of the original `'>='`; `c == c2` is `False`
- **Reproduce:** `python3 -c "from prama.pql.parser import parse_control; c=parse_control('CHECK t.a IS NOT NULL AT LEAST 5 ROWS'); r=c.render(); c2=parse_control(r); print(r); print(c.threshold, c2.threshold)"`
- **Severity:** P1
- **Assessment:** defect — `Threshold.render` (src/prama/pql/ast.py:634-635) emits `AT MOST` unconditionally for `unit == "rows"`, ignoring `comparator`.

### PQL-141 · A large row threshold renders in scientific notation
- **Expected:** equality after round-trip (1234567 both times)
- **Observed:** rendered `AT MOST 1.23457e+06 ROWS`; re-parsed value is `1234570.0`, not `1234567.0`
- **Reproduce:** `python3 -c "from prama.pql.parser import parse_control; c=parse_control('CHECK t.a IS NOT NULL AT MOST 1234567 ROWS'); r=c.render(); print(r); print(parse_control(r).threshold.value)"`
- **Severity:** P1
- **Assessment:** defect — `f"{value:g}"` in `Threshold.render` gives six significant figures; reproducible here and not fixed.

### PQL-149 · `WITHIN n SIGMA` does not produce a sigma threshold
- **Expected:** `Threshold(unit="sigma", value=2)`
- **Observed:** raises `PqlSyntaxError: there is more text after the control: 'SIGMA'` (position line 1, column 32) — no `Threshold` is ever produced; `2` is consumed as a bare `amount` threshold (`unit="amount", value=2.0, currency=""`) and `SIGMA`, being a plain 5-character `IDENTIFIER` token (confirmed absent from `tokens.KEYWORDS`), is left as a stray token that ends the control
- **Reproduce:** `python3 -c "from prama.pql.parser import parse_control; parse_control('CHECK t.a IS NOT NULL WITHIN 2 SIGMA')"`
- **Severity:** P2
- **Assessment:** defect — `ast.Threshold.render`/`.describe` (src/prama/pql/ast.py:640, 653) both carry a live `sigma` branch that `Parser._threshold` (src/prama/pql/parser.py:641-656) has no code path to ever construct; the branches are dead, and `WITHIN … SIGMA` cannot be authored at all despite being renderable.

### PQL-150 · An amount threshold silently becomes a row count
- **Expected:** the amount and currency reach the plan
- **Observed:** `resolved(parse_control("CHECK t.a IS NOT NULL WITHIN 100 USD"))` produces `plan.threshold == Threshold(metric='violating_rows', comparator=LE, value=100.0, relative_to='')` — no currency field at all in the IR `Threshold`; the USD amount is compiled as "at most 100 violating rows"
- **Reproduce:** `python3 -c "from prama.pql.parser import parse_control; from prama.ir.resolve import resolved; print(resolved(parse_control('CHECK t.a IS NOT NULL WITHIN 100 USD')).threshold)"`
- **Severity:** P1
- **Assessment:** defect — `Lowerer._threshold` (src/prama/ir/lower.py:475-488) special-cases only `rate`/`percent`; everything else (`amount`) falls through to a plain row-count `Threshold`, discarding `currency` with no error or warning.

### PQL-151 · A threshold on an assertion that has no rate
- **Expected:** refused at authoring time (per the parser module's own docstring)
- **Observed:** `CHECK t HAS ROW COUNT AT LEAST 1 BELOW 10%` parses without error; lowered plan's metrics are only `(scanned_rows,)` — no `violating_rows` metric exists to divide; when judged, `_verdict` dispatches on `assertion_kind == "row_count"` to `_row_count_verdict`, which ignores `plan.threshold` entirely and returned `Verdict.PASS` from `scanned_rows=5.0` alone (not `INDETERMINATE` as the catalogue's narrative guesses, but the rate threshold is confirmed silently inert either way)
- **Reproduce:** `python3 -c "
from prama.pql.parser import parse_control
from prama.ir.resolve import resolved
from prama.backend.execute import judge
c = parse_control('CHECK t HAS ROW COUNT AT LEAST 1 BELOW 10%')
plan = resolved(c)
print(plan.metrics)
print(judge(plan, {'scanned_rows': 5.0}).verdict)
"`
- **Severity:** P2
- **Assessment:** defect — the parser's own module docstring (src/prama/pql/parser.py, lines 8-11) lists "a threshold on an assertion that has no rate" as something it refuses; no such refusal exists in `_finish` or elsewhere in `Parser`.

### PQL-154 · `HAVING` never reaches the plan
- **Expected:** the HAVING condition appears in the plan and in the emitted SQL
- **Observed:** `plan.scope` (`Scope(dataset='t', binding='', filter=None, segment_by=('entity',), as_of='', window='')`) has no `having` field at all; compiled SQLite query is `SELECT "entity", COUNT(*) AS "scanned_rows", … GROUP BY "entity"` with no `HAVING` clause
- **Reproduce:** `python3 -c "
from prama.pql.parser import parse_control
from prama.ir.resolve import resolved
from prama.backend.sql import SqlCompiler
plan = resolved(parse_control('CHECK t.a IS NOT NULL FOR EACH t.entity HAVING COUNT(*) > 100'))
print(plan.scope)
print(SqlCompiler('sqlite').compile(plan, table='t').metric_query)
"`
- **Severity:** P1
- **Assessment:** defect — `Lowerer.control` (src/prama/ir/lower.py:95-103) reads only `control.segmentation.columns` into `Scope.segment_by`; `control.segmentation.having` is parsed and rendered but never consulted anywhere in lowering.

### PQL-156 · Segment keys are ambiguous when a value contains the separator
- **Expected:** two distinct segments
- **Observed:** rows `("x|y","z")` and `("x","y|z")` segmented by `(p, q)` both hash to the identical key `"x|y|z"` — `ReferenceEvaluator().run(...)` returns exactly **one** segment, not two
- **Reproduce:** `python3 -c "
from prama.pql.parser import parse_control
from prama.ir.resolve import resolved
from prama.backend.reference import ReferenceEvaluator
plan = resolved(parse_control('CHECK t.a IS NOT NULL FOR EACH t.p, t.q'))
rows = [{'a':1,'p':'x|y','q':'z'}, {'a':2,'p':'x','q':'y|z'}]
r = ReferenceEvaluator().run(plan, rows)
print([s.key for s in r.segments])
"`
- **Severity:** P2
- **Assessment:** defect — `ReferenceEvaluator._by_segment` (src/prama/backend/reference.py:121) joins segment columns with the literal `"|"` with no escaping; the same unescaped `"|".join(...)` pattern also appears in `backend/conformance.py::ConformanceRun._judge` and `backend/fuse.py::FusedQuery._unpack_segmented`, so the collision is not specific to one backend.

### PQL-158 · An indeterminate segment beside passing segments
- **Expected:** the overall verdict is not a clean `PASS`
- **Observed:** three segments — two `PASS` (`scanned_rows=10`, no violations) and one `INDETERMINATE` (`scanned_rows=0`) — produced an overall verdict of `Verdict.PASS`
- **Reproduce:** `python3 -c "
from prama.pql.parser import parse_control
from prama.ir.resolve import resolved
from prama.backend.execute import judge_segments
plan = resolved(parse_control('CHECK t.a > 0 FOR EACH t.entity'))
rows = [('e1',{'scanned_rows':10.0,'violating_rows':0.0}),
        ('e2',{'scanned_rows':10.0,'violating_rows':0.0}),
        ('e3',{'scanned_rows':0.0,'violating_rows':0.0})]
r = judge_segments(plan, rows)
print([s.verdict for s in r.segments], r.verdict)
"`
- **Severity:** P1
- **Assessment:** defect — `judge_segments` (src/prama/backend/execute.py:160-166) computes `overall = FAIL if any FAIL else INDETERMINATE if all INDETERMINATE else PASS`; one indeterminate segment among passing ones falls through to `PASS`.

### PQL-159 · Segment totals sum metrics that cannot be summed
- **Expected:** either no aggregate `distinct_keys`, or one computed correctly
- **Observed:** a `HAS UNIQUE KEY (id)` control segmented by `entity`, with segment A having 2 distinct ids and segment B having 2 distinct ids (one id value, `1`, reused across segments) — `ControlResult.metrics['distinct_keys']` on the overall result is `4.0`, the naive sum of per-segment counts, which is not a meaningful overall distinct-key count
- **Reproduce:** `python3 -c "
from prama.pql.parser import parse_control
from prama.ir.resolve import resolved
from prama.backend.reference import ReferenceEvaluator
plan = resolved(parse_control('CHECK t HAS UNIQUE KEY (t.id) FOR EACH t.entity'))
rows = [{'id':1,'entity':'A'},{'id':2,'entity':'A'},{'id':1,'entity':'B'},{'id':3,'entity':'B'}]
r = ReferenceEvaluator().run(plan, rows)
print(r.metrics)
"`
- **Severity:** P2
- **Assessment:** defect — `judge_segments`'s `totals` (src/prama/backend/execute.py:156-159) sums every metric name across segments unconditionally, including `distinct_keys`, whose per-segment values are not additive.

### PQL-166 · Reversed text bounds are not caught
- **Expected:** the same always-fires finding as the numeric case
- **Observed:** `lint()` on `CHECK t.code BETWEEN 'Z' AND 'A'` returns only a no-justification finding
- **Reproduce:** `python3 -c "from prama.pql.parser import parse_control; from prama.pql.lint import lint; print([f.rule for f in lint([parse_control(\"CHECK t.code BETWEEN 'Z' AND 'A'\")])])"`
- **Severity:** P3
- **Assessment:** defect — `Linter._always_fires` requires both BETWEEN literals to be int|float, so a reversed text range ships silently as an always-failing control.

### PQL-171 · `LIKE` and `ILIKE` are expression-only
- **Expected:** the assertion form is refused with "expected a comparison after t.a"
- **Observed:** refused, but with "expected something to check about t and found 'LIKE'"; WHERE form parses correctly
- **Severity:** P2
- **Assessment:** not-a-defect — LIKE never reaches `_predicate` (not one of the tokens routing there); the real asymmetry (assertion refused, WHERE accepted) holds, only the exact quoted message was misread by the catalogue.

### PQL-175 · Deep nesting does not exhaust the stack
- **Expected:** either a parse or a located refusal, never a RecursionError traceback
- **Observed:** 1000 nested parens raises uncaught RecursionError
- **Reproduce:** `python3 -c "from prama.pql.parser import parse_control; parse_control('CHECK t.a IS NOT NULL WHERE ' + '('*1000 + 'a' + ')'*1000)"`
- **Severity:** P2
- **Assessment:** defect — `Parser._expression`/`_primary` is unbounded recursive descent with no depth check.

### PQL-176 · An expression with 1,000 OR terms
- **Expected:** completes cleanly and compiles
- **Observed:** parses fine, `resolved()` raises uncaught RecursionError in `ir/lower.py::Lowerer._expression`
- **Severity:** P2
- **Assessment:** defect — recursion moved downstream from the parser to the lowerer rather than being absent.

### PQL-177 · A control with 500 columns
- **Expected:** SQL emitted successfully
- **Observed:** parses/lowers, but `compile_for` raises uncaught RecursionError on all 3 dialects walking the 500-way null-check OR chain
- **Severity:** P3
- **Assessment:** defect.

### PQL-181 · The two volatile lists disagree
- **Expected:** every volatile name refused on both surfaces
- **Observed:** NON_DETERMINISTIC(10) and VOLATILE(6) overlap is 2 names not 1; `CURRENT_DATE`/`SYSDATE`/`UUID` parse as a plain ColumnRef in Excel formulas — not refused at all
- **Reproduce:** `python3 -c "from prama.pql.excel import parse_formula; print(parse_formula('=CURRENT_DATE').render())"`
- **Severity:** P1
- **Assessment:** defect — a bare volatile name in an Excel formula silently becomes a column reference instead of being refused.

### PQL-182 · A quoted column named after a volatile function
- **Expected:** documented as currently refused too
- **Observed:** both quoted and unquoted `t.current_date` parse without error
- **Severity:** P3
- **Assessment:** not-a-defect — the catalogue misidentified which function parses a CHECK subject; `_target`/`_column`/`_name` never call `_identifier_expression` (the only place NON_DETERMINISTIC is checked), so there is no guard to escape here in the first place.

### PQL-187 · `MIN` and `MAX` collide with the scalar catalogue
- **Expected:** no finding
- **Observed:** `MIN(notional) > 0` as an aggregate use produces "MIN takes at least 2 argument(s), and was given 1"
- **Severity:** P1
- **Assessment:** defect — `types._AGGREGATE_TYPES` spells the aggregate `MIN_AGG`, which the parser never produces (it emits plain MIN), so `check_calls` falls through to the scalar `library.MIN` and reports a spurious arity error on valid syntax.

### PQL-189 · A parameter used only inside a metric expression is not declared
- **Expected:** the parameter is listed
- **Observed:** `plan.parameters() == frozenset()` for a plan whose only reference is inside a `Metric.expression`
- **Severity:** P2
- **Assessment:** defect — `ControlPlan.parameters()` walks only `scope.filter`, `predicate`, and `scope.as_of`; metric expressions are never consulted.

### PQL-196 · `parse(render(x)) == x` for every assertion kind
- **Expected:** equality for all nine kinds
- **Observed:** freshness breaks it: `CHECK t.a IS FRESH WITHIN 30 MINUTES OF '06:30'` renders as `CHECK t IS FRESH ...` — the `.a` disappears
- **Reproduce:** `python3 -c "from prama.pql.parser import parse_control; print(parse_control(\"CHECK t.a IS FRESH WITHIN 30 MINUTES OF '06:30'\").render())"`
- **Severity:** P1
- **Assessment:** defect — `FreshnessAssertion.render()` never references `self.column`.

### PQL-199 · `!=` is missing from `BINDING` and `COMPARISONS`
- **Expected:** correct bracketing
- **Observed:** `BinaryOp('*', BinaryOp('!=',a,1), b).render()` -> `'a != (1) * b'` — wrong; `!=` sub-expression not bracketed at all
- **Severity:** P1
- **Assessment:** defect — `BINDING.get("!=")` misses and falls back to `ATOM_BINDING`; `COMPARISONS` also omits `"!="`, so the type checker silently skips checking it too. Directly relevant to Excel's `<>` producing `!=`.

### PQL-209 · A percentage round-trips losing precision
- **Expected:** equality
- **Observed:** `0.1234567%` -> rendered `'0.123457%'` -> re-parsed to a different value
- **Severity:** P2
- **Assessment:** defect — `Literal.render()` formats a percentage with 6 significant figures via `:g`.

### PQL-219 · `prama control format` destroys suites
- **Expected:** the suite survives
- **Observed:** `--write` on a file with `SUITE risk_suite { ... }` removes the wrapper entirely
- **Severity:** P1
- **Assessment:** defect — `cli/control.py::_read` returns `parse(source).all_controls`, flattening suite membership; `ast.Suite.render` is never invoked by the CLI.

### PQL-222 · `prama control format` discards comments
- **Expected:** documented behaviour and a warning before deletion
- **Observed:** `--write` on a file with comments prints only "c.pql: rewritten" — no warning; comments are gone afterward
- **Severity:** P2
- **Assessment:** defect — the lexer discards comments at tokenisation and the AST has no field to carry them; `--write` silently and irreversibly deletes comments.

### PQL-228 · Column resolution is case-insensitive but compilation is not
- **Expected:** consistent behaviour — either both accept it or both refuse it
- **Observed:** `TypeChecker` accepts `positions.ACCOUNT_ID` against a schema declaring `account_id` ([] findings); `PostgresDialect().quote("ACCOUNT_ID")` emits `"ACCOUNT_ID"` verbatim — which PostgreSQL would report as a missing column at run time
- **Reproduce:** `python3 -c "
from prama.pql.types import Catalogue, TypeChecker
from prama.pql.parser import parse_control
print(TypeChecker(Catalogue.of(positions={'account_id':'varchar'})).check(parse_control('CHECK positions.ACCOUNT_ID IS NOT NULL WHERE TRUE')))"`
- **Severity:** P1
- **Assessment:** defect — `column()` lower-cases both sides while `quote()` does not.

### PQL-235 · `x IS NULL` is typed as a number
- **Expected:** no finding — IS NULL yields a boolean
- **Observed:** `CHECK t.a IS NOT NULL WHERE (t.b IS NULL) = TRUE` produces "t.b IS NULL holds number, and it is being compared with TRUE, which is boolean"
- **Severity:** P2
- **Assessment:** defect — `UnaryOp.type_of` uses `operator.isalpha()`, and `"IS NULL"` contains a space, so it falls through to NUMBER.

### PQL-241 · `SATISFIES` conditions are never type-checked
- **Expected:** a finding — the same one WHERE would produce
- **Observed:** `CHECK t SATISFIES notional > 'ACTIVE'` -> []; the equivalent rewritten as WHERE produces a finding
- **Severity:** P1
- **Assessment:** defect — `_type_check` calls `_check_expression` only on `control.where`, never on an `ExpressionAssertion.condition` for SATISFIES.

### PQL-242 · A `HAVING` expression is never function-checked or type-checked
- **Expected:** "there is no function called NONSENSE"
- **Observed:** `FOR EACH e HAVING NONSENSE(b) > 1` -> [] findings
- **Severity:** P2
- **Assessment:** defect — `_expressions_of` never includes `segmentation.having`.

### PQL-264 · `CONCAT` with a NULL argument disagrees between SQL and the reference
- **Expected:** agreement
- **Observed:** reference and sqlite -> None (UNKNOWN); postgresql and duckdb -> 'a'
- **Severity:** P1
- **Assessment:** defect — PostgreSQL/DuckDB's CONCAT treats NULL as empty string, SQLite's `||` propagates NULL.

### PQL-266 · `argument_types` is declared and never enforced
- **Expected:** a finding that UPPER expects text
- **Observed:** `WHERE UPPER(notional) = 'X'` against a numeric column -> [] findings; confirmed UPPER(numeric) fails on real PostgreSQL
- **Severity:** P1
- **Assessment:** defect — `check_calls` verifies only name and arity, never `Function.argument_types`.

### PQL-268 · Each text function against its reference, including a NULL argument
- **Expected:** agreement, or a documented divergence per function
- **Observed:** most functions agree; CONCAT disagrees with no code comment documenting that specific disagreement
- **Severity:** P1
- **Assessment:** defect — same root cause as PQL-264, surfaced by the full sweep.

### PQL-269 · `LENGTH` of a non-text value
- **Expected:** agreement
- **Observed:** LENGTH(123.45): reference=6, sqlite=6, postgresql raises UndefinedFunction, duckdb raises BinderException
- **Severity:** P1
- **Assessment:** defect — nothing casts before LENGTH.

### PQL-272 · `TRIM` of other whitespace
- **Expected:** agreement
- **Observed:** value with tab/newline/NBSP: reference strips all to 'a'; SQL engines leave most untouched
- **Severity:** P2
- **Assessment:** defect — SQL TRIM strips only literal spaces; Python's `.strip()` strips all Unicode whitespace.

### PQL-273 · `LEFT`, `RIGHT` and `MID` with a zero, a negative and an over-long length
- **Expected:** agreement
- **Observed:** multiple boundary disagreements across engines and reference (see full detail in harness output)
- **Severity:** P1
- **Assessment:** defect — the negative/zero space is untested and is exactly where SUBSTR semantics diverge from Python slicing.

### PQL-276 · `SUBSTITUTE` with an empty search string
- **Expected:** agreement
- **Observed:** reference inserts the replacement between every character; all 3 engines leave the string unchanged
- **Severity:** P2
- **Assessment:** defect — undocumented silent divergence.

### PQL-280 · `ROUND` with a negative or very large number of places
- **Expected:** a defined answer, never an uncaught exception
- **Observed:** ROUND(1.5,40) raises `decimal.InvalidOperation`, uncaught
- **Severity:** P2
- **Assessment:** defect — `Decimal.quantize` exceeds context precision and the exception escapes the interpreter.

### PQL-287 · `MIN`/`MAX` with an unknown argument are unknown
- **Expected:** agreement
- **Observed:** MIN(3,NULL): reference/sqlite -> NULL/UNKNOWN; postgresql/duckdb LEAST(3,NULL) -> 3
- **Severity:** P1
- **Assessment:** defect — PostgreSQL/DuckDB's LEAST ignores NULLs by design, contradicting the language's stated unknown-propagation rule.

### PQL-288 · `IF` with an undetermined condition is undetermined
- **Expected:** UNKNOWN/NULL everywhere
- **Observed:** reference -> UNKNOWN; compiled `CASE WHEN NULL THEN 1 ELSE 2 END` -> 2 on all 3 engines
- **Severity:** P1
- **Assessment:** defect — the compiler's own IF template takes the branch that "invents an answer" from a NULL condition.

### PQL-294 · `ISNUMBER` on each engine
- **Expected:** agreement
- **Observed:** ISNUMBER('  7 '): reference True (Python strips), engines False (regex doesn't); ISNUMBER(NULL): reference False, engines NULL
- **Severity:** P1
- **Assessment:** defect — whitespace and NULL-handling both disagree.

### PQL-300 · Reference arithmetic is exact, SQL arithmetic is not
- **Expected:** one documented arithmetic model
- **Observed:** Decimal-based catalogue path computes 0.1+0.2 exactly as 0.3; `backend.reference._arithmetic` computes float 0.30000000000000004; sqlite raw SQL is also imprecise while postgresql/duckdb numeric-literal arithmetic is exact
- **Severity:** P1
- **Assessment:** defect — at least two arithmetic models coexist in one interpreter.

### PQL-331 · Excel `<>` produces an operator nothing downstream can handle
- **Expected:** working SQL and a working reference evaluation
- **Observed:** parsing `SATISFIES EXCEL '=[currency] <> "USD"'` produces `BinaryOp(operator='!=', ...)`. Compiling for all three dialects raises `PqlUnsupportedError: != has no SQL form on sqlite/postgresql/duckdb`. The reference interpreter raises uncaught `KeyError: '!='` from `_compare`, both from `is_violation()` and `run()`. `<>` is indeed the third example in the module's own docstring.
- **Reproduce:** `python3 -c "
from prama.pql.parser import parse_control
from prama.ir.resolve import resolved
from prama.backend.sql import compile_for
c = parse_control('CHECK t.currency SATISFIES EXCEL \'=[currency] <> \"USD\"\' BECAUSE \'x\'')
compile_for(resolved(c), 'sqlite')"`
- **Severity:** P1
- **Assessment:** defect — `OPERATORS["<>"] = "!="` in `pql/excel.py` maps to a spelling absent from `ast.COMPARISONS`, `ast.BINDING`, and `backend/sql.py::INFIX`, and `_compare`'s dict has no `"!="` key and no `except KeyError` guard. The module's own documented example does not run on any backend.

### PQL-335 · Excel errors carry no position
- **Expected:** either a real position or an explicitly unlocated diagnostic
- **Observed:** every `PqlSyntaxError` from `pql/excel.py` passes the true offset only inside `context={"position": ...}`, never as the `position=` constructor keyword; `PqlError.__init__` defaults `self.position` to `Position(line=1, column=1, offset=0, length=1)` — a specific, wrong location, not "explicitly unlocated"
- **Reproduce:** `python3 -c "from prama.pql.excel import parse_formula; parse_formula('=[a] +')" ` then inspect `e.position`
- **Severity:** P1
- **Assessment:** defect — every raise site in `excel.py` omits `position=`.

### PQL-338 · A bracketed column with a dot
- **Expected:** `ColumnRef(name="notional", dataset="positions")`
- **Observed:** `parse_formula('=positions.notional > 0')` produces `ColumnRef(name='positions.notional', dataset='')` — dot swallowed whole
- **Severity:** P1
- **Assessment:** not-a-defect — the catalogue's own "Why" field correctly predicts exactly this behaviour; only its "Expected" line states a naively-hoped-for split. The code matches its own documented design; no discrepancy exists between code and its own stated behaviour.

### PQL-339 · An empty bracket
- **Expected:** a refusal
- **Observed:** `parse_formula('=[] > 0')` parses successfully to `BinaryOp('>', ColumnRef(name=''), Literal(0))` — no exception
- **Reproduce:** `python3 -c "from prama.pql.excel import parse_formula; print(parse_formula('=[] > 0'))"`
- **Severity:** P2
- **Assessment:** defect — `token.text[1:-1].strip()` yields `""` and `primary()` accepts it unconditionally.

### PQL-341 · A nested bracket is impossible
- **Expected:** a located refusal
- **Observed:** raises `PqlSyntaxError: ']' is not something a formula can contain` (correct refusal), but `.position` is the hardcoded default regardless of real offset
- **Severity:** P3
- **Assessment:** defect — same root cause as PQL-335.

### PQL-346 · A trailing separator
- **Expected:** a located refusal
- **Observed:** `'=CONCAT([a], [b],)'` raises `PqlSyntaxError: unexpected ')'` (correct refusal) but `.position` is again the hardcoded default
- **Severity:** P2
- **Assessment:** defect — same root cause as PQL-335/341.

### PQL-350 · A column named `AND`
- **Expected:** the bracketed form works; the bare form is read as an operator
- **Observed:** `'=[and] > 0'` and `'=and > 0'` both produce the identical `BinaryOp('>', ColumnRef('and'), 0)` — the bare form is not read as an operator here
- **Severity:** P3
- **Assessment:** not-a-defect — the catalogue's "Why" is correct in principle (the operator-lookahead loop tests token text regardless of kind), but that loop only runs after a left operand is parsed; "and" as the very first token is consumed by `primary()` before the loop runs, so this specific input never triggers the ambiguity. (Real for a name in operator position, e.g. after another operand — but not the example tested.)

### PQL-353 · `IFERROR` is refused by name
- **Expected:** a message naming the reason there's nothing to catch
- **Observed:** message is correct ("there is no function called IFERROR") but remedy is byte-identical generic boilerplate to `VLOOKUP`'s; the `IFBLANK` divergence explanation exists only in `pql/library.py`'s `excel_divergence` field, surfaced only via `control explain` on an `IFBLANK`-using control, never when a user types `IFERROR`
- **Severity:** P2
- **Assessment:** defect — matches the catalogue's own diagnosis: `IFERROR` gets the generic list unlike `VOLATILE` functions which get a dedicated reason-carrying remedy.

### PQL-366 · A selector on an unknown metadata name matches nothing, silently
- **Expected:** a refusal, or a warning naming the unrecognised field
- **Observed:** `expand()` on `WHERE is_cdee IS NOT NULL` (typo) returns `[]` silently, no warning naming `is_cdee`
- **Reproduce:** `python3 -c "
from prama.pql.parser import parse_control
from prama.pql.expand import Attribute, AttributeCatalogue, Expander
cat = AttributeCatalogue(attributes=(Attribute(dataset='d', name='a', is_cde=True),))
print(Expander(cat).expand(parse_control(\"CHECK EVERY ATTRIBUTE WHERE is_cdee IS NOT NULL BECAUSE 'x'\")))"`
- **Severity:** P1
- **Assessment:** defect — `facts.get(name)` returns `None` for any unrecognised key; every comparison against `None` is `False`; the typo silently produces a covered-looking, zero-control expansion.

### PQL-369 · `tags = 'pii'` does not match
- **Expected:** a refusal or a match — not a silent non-match
- **Observed:** `expand()` on `WHERE tags = 'pii'` against an attribute carrying `tags=("pii",)` returns `[]` silently
- **Severity:** P2
- **Assessment:** defect — `_binary`'s surrounding `try/except TypeError` swallows any raised comparison error between list and str and returns `False`, so the mismatch is silent.

### PQL-372 · `_is_true` accepts the string "true"
- **Expected:** it matches
- **Observed:** with `is_cde='True'` (string), the bare `WHERE is_cde` does NOT match (`_truth` uses `is True`, and Python `'True' is True` is `False`); `_is_true`'s string acceptance is only reached from the `NOT` branch, never from a bare reference
- **Severity:** P2
- **Assessment:** not-a-defect — the catalogue's own "Why" field already states this correctly; its "Expected: it matches" contradicts its own accurate Why and the confirmed code behaviour.

### PQL-373 · A bare boolean fact under `NOT` and not under it disagree
- **Expected:** exactly one of the two matches
- **Observed:** with `is_cde='True'` (string), both `WHERE is_cde` and `WHERE NOT is_cde` produce zero matches — they agree (both exclude), they do not disagree
- **Severity:** P2
- **Assessment:** not-a-defect — the catalogue's own "Why" field states, correctly, "both exclude the attribute," which is exactly what execution shows; the catalogue's "Expected" line contradicts its own accurate Why.

### PQL-384 · Diagnostics ignore every control inside a suite
- **Expected:** a diagnostic naming the unknown column
- **Observed:** `[]` — no diagnostics produced at all for a control wrapped in `SUITE core { ... }`
- **Reproduce:** `python3 -c "
from prama.pql.analysis import LanguageService
from prama.pql.types import Catalogue
svc = LanguageService(Catalogue.of(positions={'account_id': 'text'}))
print(svc.diagnostics('SUITE core { CHECK positions.nosuchcolumn IS NOT NULL }'))"`
- **Severity:** P1
- **Assessment:** defect — `parse(text).controls` is top-level only for this text; the control only appears in `program.all_controls`, which `diagnostics()` never consults (iterates `program.controls`).

### PQL-402 · `from prama.pql import *` succeeds
- **Expected:** no error
- **Observed:** `AttributeError: module 'prama.pql' has no attribute 'Attribute'`, subprocess exit code 1
- **Reproduce:** `python3 -c "from prama.pql import *"`
- **Severity:** P2
- **Assessment:** defect — `__all__` lists `Attribute`, `AttributeCatalogue`, `Drift`, `Expander`, `Expansion`, none of which `pql/__init__.py` imports.

### PQL-403 · Every name in `__all__` is importable individually
- **Expected:** all resolve
- **Observed:** 5 of 38 entries in `__all__` missing: Attribute, AttributeCatalogue, Drift, Expander, Expansion
- **Reproduce:** `python3 -c "import prama.pql as pql; print([n for n in pql.__all__ if not hasattr(pql, n)])"`
- **Severity:** P2
- **Assessment:** defect — same root cause as PQL-402.

### IR-021 · An empty codelist produces `IN ()`
- **Expected:** a refusal, not `IN ()`
- **Observed:** lowers cleanly to `Expr.operation("IN", subject, Expr.values())` and compiles to `... "x" IN () ...` — no refusal at either stage; a hand-written `IN ()` IS refused by the parser, but `Lowerer._codelist` has no equivalent guard
- **Reproduce:** `python3 -c "
from prama.ir.lower import Lowerer
from prama.pql.parser import parse_control
from prama.backend.sql import SqlCompiler
p = Lowerer(codelists={'emptylist': ()}).control(parse_control(\"CHECK t.x IN CODELIST 'emptylist'\"))
print(SqlCompiler('sqlite').compile(p).metric_query)"`
- **Severity:** P2
- **Assessment:** defect.

### IR-024 · `as_of` is a parameter name, and a date breaks it
- **Expected:** a coherent result or a typed refusal
- **Observed:** `resolved(parse_control("CHECK t.n > $other_param"), as_of=date(2026,1,1))` lowers without error, but `Scope.as_of` ends up holding the literal `date` object; `SqlCompiler.compile()` raises an unhandled stdlib `TypeError: '<' not supported between instances of 'datetime.date' and 'str'`
- **Reproduce:** `python3 -c "
from datetime import date
from prama.pql.parser import parse_control
from prama.ir.resolve import resolved
from prama.backend.sql import SqlCompiler
p = resolved(parse_control('CHECK t.n > \$other_param'), as_of=date(2026, 1, 1))
SqlCompiler('sqlite').compile(p)"`
- **Severity:** P1
- **Assessment:** defect — `resolved()` forwards its `as_of: date` straight into `Lowerer`'s `as_of` argument, which becomes `Scope.as_of` verbatim, conflating "codelist freeze date" with "parameter name holding the run's business date."

### IR-037 · A missing `scanned_rows` disables the empty-scope guard
- **Expected:** not a clean PASS
- **Observed:** `Threshold(metric="violating_rows", comparator=Comparator.LE, value=0.0).evaluate({"violating_rows": 0})` (no `scanned_rows` key at all) -> `Verdict.PASS`
- **Reproduce:** `python3 -c "
from prama.ir.model import Threshold, Comparator
print(Threshold(metric='violating_rows', comparator=Comparator.LE, value=0.0).evaluate({'violating_rows': 0}))"`
- **Severity:** P1
- **Assessment:** defect — the guard is `metrics.get("scanned_rows", -1.0) == 0.0`; when the key is absent entirely, the sentinel `-1.0` slips past the guard and the empty-scope case recurs for the absent-key case.

### BE-005 · A dataset name containing a dot inside quotes is split anyway
- **Expected:** a way to express a single-part table name that itself contains a literal dot
- **Observed:** `SqlDialect().qualify('risk.positions')` -> always split on every `.`; pre-quoting doesn't help either
- **Reproduce:** `python3 -c "from prama.backend.dialect import SqlDialect; print(SqlDialect().qualify('risk.positions'))"`
- **Severity:** P2
- **Assessment:** defect — `qualify` splits unconditionally with no escape mechanism.

### BE-006 · Literal rendering per type
- **Expected:** a defined numeric answer for `Decimal("1.5")`
- **Observed:** `literal(Decimal("1.5"))` -> `"'1.5'"` — a quoted string literal
- **Reproduce:** `python3 -c "from decimal import Decimal; from prama.backend.dialect import SqlDialect; print(SqlDialect().literal(Decimal('1.5')))"`
- **Severity:** P1
- **Assessment:** defect — `isinstance(value, int | float)` excludes Decimal.

### BE-007 · A non-finite float literal
- **Expected:** a refusal or an engine-valid spelling
- **Observed:** `literal(nan)` -> `nan`; `literal(inf)` -> `inf` — invalid SQL tokens
- **Severity:** P2
- **Assessment:** defect — neither refuses nor produces valid SQL.

### BE-012 · SQLite's composite key join is injective
- **Expected:** two distinct keys
- **Observed:** rows containing the sentinel separator character collide; count_distinct over (a,b) returns 1 not 2
- **Severity:** P1
- **Assessment:** defect — the CHAR(31)/CHAR(30) separator is not actually unrepresentable in real data.

### BE-015 · A pattern using a non-portable regex feature
- **Expected:** agreement, or a refusal naming the flavour
- **Observed:** lookbehind/backreference: PostgreSQL/SQLite execute, DuckDB (RE2) raises raw error; inline flag: PostgreSQL/SQLite/reference raise, DuckDB runs. No refusal ever names the flavour.
- **Severity:** P1
- **Assessment:** defect — nothing validates a pattern against `regex_flavour` before emitting SQL.

### BE-016 · An invalid pattern
- **Expected:** a refusal at authoring time
- **Observed:** `MATCHES /[/` parses/lowers/compiles with no error at all; `/*/ ` is rejected only by comment-tokenizer confusion
- **Severity:** P1
- **Assessment:** defect — `re.compile` happens lazily per-row inside the reference interpreter; no stage validates pattern syntax up front.

### BE-023 · Modulo takes the sign of the dividend on every engine
- **Expected:** agreement on all three engines and reference
- **Observed:** PostgreSQL fails to execute at all (`UndefinedFunction: operator does not exist: double precision % integer`); DuckDB/SQLite/reference agree
- **Severity:** P1
- **Assessment:** defect — bare `%` is not portable to real PostgreSQL for a floating-point column.

### BE-024 · Modulo by zero
- **Expected:** agreement (reference UNKNOWN, PostgreSQL error)
- **Observed:** PostgreSQL raises (aborts query); DuckDB/SQLite silently return NULL; reference returns UNKNOWN — no agreement
- **Severity:** P1
- **Assessment:** defect — only the catalogued `MOD()` function is guarded; bare `%` is not.

### BE-029 · A capability set is exactly what each engine can do
- **Expected:** no engine declares a capability it lacks
- **Observed:** PostgreSQL declares `pushdown.approx_distinct` but the emitted SQL (`APPROX_COUNT_DISTINCT(...)`) fails — no such builtin exists
- **Severity:** P1
- **Assessment:** defect.

### BE-034 · `scan_limit` with a correlated EXISTS
- **Expected:** valid SQL
- **Observed:** `BinderException` on DuckDB — unaliased LIMIT subquery breaks column resolution
- **Severity:** P2
- **Assessment:** defect.

### BE-037 · `SqlCompiler` carries mutable state between compilations
- **Expected:** each result reflects its own source
- **Observed:** calling `.expression()` directly on a second plan reuses the first plan's stale `_source`
- **Severity:** P2
- **Assessment:** defect — `_source` is instance state written only by `compile()`.

### BE-049 · Aggregates bypass the catalogue
- **Expected:** consistent treatment of COUNT/SUM/MIN/MAX/MEDIAN
- **Observed:** MIN/MAX render as scalar LEAST/GREATEST (wrong, single-argument); MEDIAN refused outright
- **Severity:** P1
- **Assessment:** defect — `_AGGREGATES` in sql.py omits MIN/MAX/MEDIAN even though the parser's AGGREGATES set includes them.

### BE-054 · Every operator the lowerer can emit has a SQL branch
- **Expected:** no "has no SQL form" refusals for anything the grammar accepts
- **Observed:** LIKE/ILIKE/NOT LIKE/NOT ILIKE/HAS FORMAT (all real, reachable) raise "has no SQL form"
- **Severity:** P1
- **Assessment:** defect, with two corrections: `!=` is normalised to `<>` before reaching the AST/IR (never reaches the compiler); `IS OF TYPE` has no parser support at all (unreachable dead code, not a live gap). The real live gap is LIKE/ILIKE/NOT LIKE/NOT ILIKE/HAS FORMAT.

### BE-055 · `IN` over an empty list
- **Expected:** a refusal
- **Observed:** compiles with no error to `("a" IN ())`; only the engine rejects it at execution
- **Severity:** P2
- **Assessment:** defect.

### BE-056 · An unresolved codelist is refused, not guessed
- **Expected:** a clean refusal, no crash on malformed input
- **Observed:** normal case refuses cleanly; a hand-built 1-arg IN CODELIST node raises bare IndexError
- **Severity:** P2
- **Assessment:** defect.

### BE-062 · `prama control compile` exits non-zero when nothing can run
- **Expected:** non-zero exit
- **Observed:** both controls refused, but exits 0
- **Severity:** P2
- **Assessment:** defect — `ControlCompileCommand.run` unconditionally returns EXIT_OK regardless of refused count.

### BE-067 · An unknown comparison operator raises rather than returning unknown
- **Expected:** a typed refusal, or the comparison
- **Observed:** `predicate=Expr(kind='op', name='!=', ...)`; `ReferenceEvaluator.evaluate` raises untyped `KeyError: '!='`
- **Reproduce:** `python3 -c "
from prama.pql.parser import parse_control
from prama.ir.lower import Lowerer
from prama.backend.reference import ReferenceEvaluator
plan = Lowerer().control(parse_control(\"CHECK t SATISFIES EXCEL '=[a]<>5'\"))
ReferenceEvaluator().evaluate(plan.predicate, {'a': 3})"`
- **Severity:** P1
- **Assessment:** defect — the excel parser's `<>` maps to AST operator `"!="`, which lowers straight through to `Expr.operation("!=", ...)`; `_compare`'s dict has no `!=` key and the `except TypeError` guard never fires for a `KeyError`.

### BE-068 · `x = y` between a number and a numeric string
- **Expected:** agreement between engines and the reference
- **Observed:** reference verdict `FAIL`, sqlite verdict `PASS` for the identical row `a='1'` (TEXT), `b=1` (INTEGER)
- **Reproduce:** `python3 -c "
from prama.pql.parser import parse_control
from prama.ir.lower import Lowerer
from prama.backend.reference import ReferenceEvaluator
plan = Lowerer().control(parse_control('CHECK t SATISFIES a = b'))
print(ReferenceEvaluator().run(plan, [{'a': '1', 'b': 1}]).verdict)"`
- **Severity:** P1
- **Assessment:** defect — sharper root cause than the catalogue states: `_compare` builds `{"=":left==right, "<>":..., ">":left>right, ...}` as one dict literal, so all six comparisons are evaluated eagerly before the requested key is looked up; `"1" > 1` raises `TypeError` during that construction even when the operator asked for is `"="`, so every ordering-incomparable pair collapses to UNKNOWN even though `"1"=="1"` alone would not have raised.

### BE-073 · `MATCHES` against a non-string value
- **Expected:** agreement between engines and the reference
- **Observed:** same value `1.10`: reference (`str(1.10)`->`'1.1'`) -> FAIL; duckdb (`CAST` on DECIMAL(10,2) -> `'1.10'`) -> PASS
- **Reproduce:** `python3 -c "
from prama.pql.parser import parse_control
from prama.ir.lower import Lowerer
from prama.backend.reference import ReferenceEvaluator
plan = Lowerer().control(parse_control(r'CHECK t SATISFIES v MATCHES /^[0-9]+\.[0-9]{2}\$/'))
print(ReferenceEvaluator().run(plan, [{'v': 1.10}]).verdict)"` (compare against a duckdb table with column `v DECIMAL(10,2)`)
- **Severity:** P1
- **Assessment:** defect — `str()` on a Python float drops a trailing zero that `CAST(... AS VARCHAR)` on a SQL DECIMAL keeps.

### BE-075 · A catastrophic pattern
- **Expected:** it completes, or the pattern is refused
- **Observed:** `MATCHES /(a+)+b/` against `"a"*40` neither completed within 8 seconds nor was refused
- **Reproduce:** `python3 -c "import re; re.compile(r'(a+)+b').search('a'*40)"` (hangs)
- **Severity:** P2
- **Assessment:** defect — Python's `re` backtracks catastrophically; nothing in `_matches` guards against it.

### BE-078 · Arithmetic on a non-numeric value crashes
- **Expected:** UNKNOWN
- **Observed:** uncaught `ValueError: could not convert string to float: 'hello'`
- **Reproduce:** `python3 -c "
from prama.pql.parser import parse_control
from prama.ir.lower import Lowerer
from prama.backend.reference import ReferenceEvaluator
plan = Lowerer().control(parse_control('CHECK t SATISFIES (a + b) > 0'))
ReferenceEvaluator().evaluate(plan.predicate, {'a': 'hello', 'b': 'world'})"`
- **Severity:** P1
- **Assessment:** defect — `_arithmetic` does `float(values[0])` with no try/except.

### BE-079 · Arithmetic on a boolean silently coerces
- **Expected:** one consistent answer
- **Observed:** `flag + 1 = 2` (flag=True) -> `True` (silently coerced); `ABS(flag) = 1` -> `UNKNOWN` (refused)
- **Reproduce:** as in report body above
- **Severity:** P2
- **Assessment:** defect — the operator path and the function path enforce opposite policies for the identical mistake.

### BE-080 · Reference arithmetic is float, the catalogue is Decimal
- **Expected:** the same answer from both `(a+b)=c` and `ROUND(a+b,2)=c`
- **Observed:** with `a=0.1, b=0.2, c=0.3`, both forms return `False` — `ROUND(a+b,2)` returns `Decimal('0.30')`, and `Decimal('0.30') == 0.3` is `False`
- **Reproduce:** `python3 -c "
from prama.pql.parser import parse_control
from prama.ir.lower import Lowerer
from prama.backend.reference import ReferenceEvaluator
plan = Lowerer().control(parse_control('CHECK t SATISFIES ROUND(a + b, 2) = c'))
print(ReferenceEvaluator().evaluate(plan.predicate, {'a': 0.1, 'b': 0.2, 'c': 0.3}))"`
- **Severity:** P1
- **Assessment:** defect — worse than the catalogue's framing: even the "fix" of wrapping in ROUND fails, because the arithmetic result becomes Decimal while the compared value stays float.

### BE-095 · A distinct count over an unhashable value
- **Expected:** a typed refusal
- **Observed:** bare `TypeError: unhashable type: 'list'`
- **Reproduce:** `python3 -c "
from prama.pql.parser import parse_control
from prama.ir.lower import Lowerer
from prama.backend.reference import ReferenceEvaluator
plan = Lowerer().control(parse_control('CHECK t HAS UNIQUE KEY (tags)'))
ReferenceEvaluator().run(plan, [{'tags': ['a','b']}, {'tags': ['c']}])"`
- **Severity:** P3
- **Assessment:** defect — `_distinct` calls `seen.add(key)` with no guard.

### BE-096 · `APPROX_COUNT_DISTINCT` is silently zero
- **Expected:** an approximation, or a refusal
- **Observed:** `0.0` for a metric over 3 genuinely distinct values
- **Severity:** P2
- **Assessment:** defect — `_metrics` only special-cases COUNT/COUNT_IF/COUNT_DISTINCT and routes everything else through `_aggregate`, whose dict has no `APPROX_COUNT_DISTINCT` entry, defaulting to `0.0`.

### BE-097 · `SUM`, `MIN`, `MAX` and `AVG` over no numeric values
- **Expected:** agreement with SQL (SUM/MIN of no rows is NULL)
- **Observed:** `SUM` over 0 rows -> `0.0`; `MIN` over 0 rows -> `0.0`; `SUM` over all-null rows -> `0.0`
- **Severity:** P2
- **Assessment:** defect — `_aggregate` returns `0.0` on `if not numbers: return 0.0` for every aggregate, conflating "sum is zero" with "sum of nothing".

### BE-100 · `run` materialises every row
- **Expected:** bounded memory, or a documented limit
- **Observed:** running over a 200,000-row generator peaked at 46MB traced memory; `run` does `[dict(r) for r in rows]`, fully consuming the input before evaluating anything
- **Severity:** P2
- **Assessment:** defect — the docstring calls this the "engine of last resort" for mainframe extracts, which is exactly where a 10M-row input is plausible, and nothing bounds or streams the materialisation.

### BE-112 · Every assertion kind reaches its own verdict function
- **Expected:** each of the six assertion kinds reaches a verdict rule that can produce PASS and FAIL
- **Observed:** predicate, unique_key, row_count, reference, and functional_dependency can each be driven to both PASS and FAIL. freshness, executed end-to-end over both fresh and stale row sets, returned INDETERMINATE in every case
- **Reproduce:** `python3 -c "
from prama.pql.parser import parse_control
from prama.ir.lower import Lowerer
from prama.backend.reference import ReferenceEvaluator
plan = Lowerer().control(parse_control(\"CHECK t IS FRESH WITHIN 30 MINUTES OF '06:30'\"))
print(ReferenceEvaluator().run(plan, [{'row_id': i} for i in range(5)]).verdict)"`
- **Severity:** P1
- **Assessment:** defect — confirmed by actual execution: `Lowerer._assertion` lowers freshness to `predicate=None`, `Lowerer._metrics` emits only `scanned_rows`, and `execute.py::_verdict` has no freshness branch, falling to `threshold.evaluate` whose metric is never supplied. Every freshness control in the product is permanently indeterminate, on any data, by construction.

### BE-115 · `_round` on a non-numeric metric
- **Expected:** a defined answer, not a `TypeError`
- **Observed:** `_round(None)` and `ControlResult(metrics={'sum_x': None}).comparable()` both raise `TypeError: float() argument must be a string or a real number, not 'NoneType'`
- **Reproduce:** `python3 -c "from prama.backend.execute import _round; _round(None)"`
- **Severity:** P2
- **Assessment:** defect — a SUM over an empty PostgreSQL result genuinely returns SQL NULL (Python `None`); `comparable()` then crashes instead of comparing.

### BE-125 · One unsupported control stops the whole group
- **Expected:** one control that cannot be expressed must not stop the rest
- **Observed:** `PqlUnsupportedError` raised for the entire fused group, so the one ordinary control in the same group is also stopped
- **Reproduce:** `Fuser("sqlite").fuse(group_containing([ordinary_plan, plan_needing_approx_distinct]), table="corpus")` raises, taking `ordinary_plan` down with it
- **Severity:** P1
- **Assessment:** defect — `Fuser.fuse` raises on the first unsupported metric rather than reporting the one bad control while still answering the rest of the group.

### BE-126 · A fused query produces no evidence samples
- **Expected:** samples for the failing controls
- **Observed:** `FusedQuery` has only `group, sql, columns` fields; no sample query is ever built or run
- **Severity:** P2
- **Assessment:** defect — `--fuse` silently trades every sample row in a group for one scan.

### BE-129 · Two groups with the same description collide
- **Expected:** two entries in `rows_per_scan`
- **Observed:** two distinct groups (differing only in binding) produced one `rows_per_scan` entry, keyed on `describe()`, which never mentions binding
- **Severity:** P2
- **Assessment:** defect — `rows_read` under-counts by a whole scan.

### BE-132 · A refusal is a conforming outcome; a wrong answer is not
- **Expected:** status refused, run still conforms
- **Observed:** with a bare sqlite3 connection (no register_regexp), the regex case compiles fine and fails at execution; `compare()` correctly reports it as a disagreement
- **Severity:** P1
- **Assessment:** not-a-defect — the catalogue's precondition describes SQLite's pre-fix state; Prama's executor now always registers the REGEXP function, so this configuration is not one Prama ships, and nothing is silently green.

### BE-135 · A case answered by fewer than two engines is not "compared"
- **Expected:** it is not counted as agreement
- **Observed:** `compare()` on a reference-only case returns `[]`, identical to a genuinely-agreeing case
- **Severity:** P1
- **Assessment:** defect — `compare()` has no signal distinguishing "nothing was compared" from "everything agreed"; that distinction lives only in `summarise()`'s separate counter, never consulted by `compare()`.

### BE-139 · Two-stage comparison is skipped when the reference did not run
- **Expected:** a failure, not silence
- **Observed:** `_compare_two_stage` returns `[]`
- **Severity:** P1
- **Assessment:** defect — every two-stage case is excused whenever the interpreter is not among the runners.

### BE-140 · `Case.requires` is declared and never consulted
- **Expected:** used to decide which engines may legitimately refuse a case
- **Observed:** `grep -n "case.requires" src/prama/backend/conformance.py` returns nothing
- **Severity:** P2
- **Assessment:** defect.

### BE-141 · `DUPLICATE_KEY` is declared and never used
- **Expected:** the unique-key case is built from it, or it is deleted
- **Observed:** `grep -rn DUPLICATE_KEY src/` finds only its own declaration; the case hardcodes columns directly
- **Severity:** P3
- **Assessment:** defect.

### BE-142 · Every corpus row is annotated with what it catches
- **Expected:** each row has a note or is provably ordinary
- **Observed:** rows 1, 2 and 7 have no entry in `ROW_NOTES`
- **Severity:** P2
- **Assessment:** defect.

### BE-143 · The corpus covers no function except LENGTH
- **Expected:** every catalogue function appears in at least one end-to-end case
- **Observed:** only LENGTH is exercised; the other 24 shipped functions appear in zero corpus cases
- **Severity:** P1
- **Assessment:** defect — matches the catalogue's own count exactly.

### BE-144 · The corpus has no `IN CODELIST` case
- **Expected:** it lowers and runs on every engine
- **Observed:** `ConformanceRun.plan_for` builds a bare `Lowerer()`, so adding an IN CODELIST case raises immediately
- **Severity:** P1
- **Assessment:** defect.

### BE-146 · The corpus has no parameter case
- **Expected:** the named parameter binds on every driver
- **Observed:** `Runner` type has no channel for parameter values at all
- **Severity:** P1
- **Assessment:** defect.

### BE-149 · The corpus has no arithmetic case beyond `/` and `%`
- **Expected:** agreement for +, -, *, ||
- **Observed:** +,-,* agree; `||` crashes the reference interpreter with `KeyError: '||'`
- **Severity:** P2
- **Assessment:** defect — `_arithmetic` only implements `+ - * / %`; `||` compiles fine on every SQL engine but isn't in the interpreter's dispatch.

### BE-150 · The corpus has no freshness, no `IS UNIQUE`, no Excel and no `HAS FORMAT` case
- **Expected:** each lowers, compiles and runs
- **Observed:** freshness and IS UNIQUE do; Excel and HAS FORMAT both raise PqlUnsupportedError on duckdb
- **Severity:** P1
- **Assessment:** defect for Excel/HAS FORMAT (confirmed). The catalogue's specific claim that IS UNIQUE "lowers to a null check" is not-a-defect/stale — already fixed and confirmed by execution (matches G2's PQL-073 finding).

### BE-158 · The generator covers a narrow slice of the language
- **Expected:** a stated list, and a stated exclusion list
- **Observed:** no comment or docstring in generate.py states either list
- **Severity:** P2
- **Assessment:** defect.

### BE-160 · A generated `HAS LENGTH BETWEEN` on a text column is type-clean
- **Expected:** no findings
- **Observed:** 271/271 generated HAS LENGTH BETWEEN controls produced a type-checker finding
- **Severity:** P2
- **Assessment:** defect — matches G2/G4/G5's `has_length_between` exemption-list finding.

### BE-168 · The declarations map one-to-one onto the controls
- **Expected:** a complete mapping
- **Observed:** two declarations match no control; one declaration is the basis for 3 controls; one control traces to no declaration
- **Severity:** P2
- **Assessment:** defect.

### BE-172 · Integer values at the extremes
- **Expected:** the plan hashes, SQL emits, and each engine accepts or refuses cleanly
- **Observed:** int64-boundary values fine; a 100-digit integer parses/lowers but `plan.plan_id` raises a raw `TypeError: Integer exceeds 64-bit range` from orjson inside `canonical()`
- **Severity:** P2
- **Assessment:** defect — happens at the plan-identity stage, breaking compilation/evidence/caching alike.

### BE-178 · Sealed evidence carries the threshold
- **Expected:** the threshold is on the record
- **Observed:** identical metrics with different thresholds produce different verdicts; `EvidenceRecord.to_dict()` has no threshold field
- **Severity:** P1
- **Assessment:** defect — `Recorder.record` never passes `plan.threshold` into the record.

### BE-179 · A control that cannot be replayed cannot be written
- **Expected:** five refusals/freezes and no sixth way in
- **Observed:** four of five mechanisms refuse correctly; the fifth (implementation hash freezing) never fires because `PLUGINS` is always empty (`load_entry_points` is never called anywhere in `src/`)
- **Severity:** P1
- **Assessment:** defect — editing the shipped LEI validator's implementation today would not change any control's plan_id.


---

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
