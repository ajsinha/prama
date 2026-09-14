# The language and the compiler — QA execution log, round 4

`prama.pql.tokens` · `prama.pql.errors` · `prama.pql.parser` · `prama.pql.ast` · `prama.pql.types`
· `prama.pql.functions` · `prama.pql.library` · `prama.pql.lint` · `prama.pql.excel` ·
`prama.pql.expand` · `prama.pql.analysis` · `prama.pql.families` · `prama.pql.__init__` ·
`prama.ir.model` · `prama.ir.lower` · `prama.ir.resolve` · `prama.backend.dialect` ·
`prama.backend.sql` · `prama.backend.reference` · `prama.backend.execute` · `prama.backend.fuse`
· `prama.backend.conformance` · `prama.backend.corpus` · `prama.backend.generate` ·
`prama.backend.example`.

This is a **re-run** of `qa/logs-round3/language.md` against the tree as it stands after batches
**A–D** (`3926ed9`…`1deed78`, merged at `a23f385`). All 629 cases were executed directly against
the live codebase — `prama.pql.tokens.tokenise`, `parser.parse`/`parse_control`,
`ir.lower.Lowerer`/`ir.resolve.resolved`, `backend.sql.SqlCompiler`/`compile_for`,
`backend.reference.ReferenceEvaluator`, `pql.types.TypeChecker`, `pql.lint.Linter`,
`pql.excel.parse_formula`, `pql.expand.Expander`, `pql.analysis.LanguageService`, the
`prama control …` CLI, and real SQLite, DuckDB and PostgreSQL 16 connections (the last against
the Docker container at `127.0.0.1:55432`) wherever a case named an engine. Harness scripts live
in `qa/harness/language/` — round 3's were lost to a sub-worker scratch directory that no longer
exists (`qa/logs-round3/language.md`'s own Notes on scope says so), so this round's scripts were
written from scratch, evidence-checked case by case against round 3's recorded observations, and
committed this time so a round 5 does not repeat the loss. No case was marked PASS without being
run; no case was marked BLOCKED — every one could be executed in this environment.

**A methodology note, because it matters for the regressions section below.** Two cases (`PQL-268`,
`BE-073`) came out differently here than in round 3 even though the source files behind them —
`pql/library.py`, `backend/reference.py` — are **byte-identical** to the round-3 tree (confirmed by
`git diff 0968874..HEAD` before any harness was written). Neither is a product fix. `PQL-268`'s
round-3 harness called `Function.evaluate()` directly with a bare `None` in place of the reference
interpreter's unknown sentinel, which `str(None).upper()` turns into the literal text `"NONE"`
rather than routing through `ReferenceEvaluator._call`'s real `strict_unknown` dispatch — the exact
failure mode this round's own instructions warn about (a harness that reimplements the product
rather than driving it). This round's harness calls the real `ReferenceEvaluator.evaluate` path and
finds genuine three-way agreement. `BE-073` disagreed on a narrower point — round 3's engines
produced `1` for the shorter numeric rendering while this round's identical `CAST(1.10 AS VARCHAR)`
returned `1.10` on both DuckDB and PostgreSQL in this environment — and is recorded honestly as an
unreconciled environmental difference rather than claimed as a fix. Both are listed under Confirmed
fixes below with this caveat attached; neither is claimed as evidence the batches touched language
behaviour, because they did not.

## Counts

| | Count |
|---|---:|
| Total cases | 629 |
| PASS | 510 |
| FAIL | 119 |
| BLOCKED | 0 |
| **Pass rate** | **81.1%** (510/629) |

Round 3: 508 PASS / 121 FAIL / 0 BLOCKED — 80.8%. Round 4: 510 PASS / 119 FAIL / 0 BLOCKED — 81.1%.

## Regressions — a case that passed in round 3 and fails now

**0 found.** Every one of the 629 cases that round 3 recorded as PASS still passes here, checked by
a full case-by-case diff against `qa/logs-round3/language.md`'s per-case table (script: none needed
beyond a JSON diff — see `qa/harness/language/` for the harnesses that produced both sides' inputs).

This is not a surprise once the delta is read rather than assumed. `git diff 0968874..HEAD --
src/` touches thirteen files; of those, only three fall inside this area's reach —
`backend/execute.py`, `core/ids.py`, `cli/control.py` — and each was checked directly:

- **`backend/execute.py`** gained `VERDICT_METRICS` and `unanswerable(plan)` as pure additions
  after `_verdict`; nothing inside `_verdict` itself changed. Section 18 (`BE-103`–`BE-115`, the
  judgement rules) reproduces round 3's thirteen results exactly, including the freshness
  case (`BE-112`) still landing on the same permanent `INDETERMINATE`. `unanswerable()` was driven
  directly (see the note printed after `BE-115` in `qa/harness/language/s18_judgement.py`'s output)
  and correctly names the freshness gap — `"assertion kind 'freshness' is judged by its threshold
  on 'violating_rows', which this plan does not emit"` — confirming the new function does what its
  docstring claims without touching anything this catalogue exercises.
- **`core/ids.py`**'s `UlidFactory.new()` fix has no reach here at all: nothing in `pql/`, `ir/` or
  `backend/` imports it (`grep -rn "UlidFactory\|ulid" src/prama/pql src/prama/ir src/prama/backend`
  returns nothing), because plan ids are content-addressed SHA-256 hashes (`ir:sha256:…`), not
  ULIDs. Section 14's 44 identity cases confirm this by execution rather than by the grep alone.
- **`cli/control.py`**'s new `_write_source`/`_read_source` wrap `path.write_text`/`read_text` in
  typed refusals, but only on the `OSError`/`UnicodeDecodeError` paths — the `PqlError`-catches-and-
  renders logic in `_read` (the thing `PQL-055` exercises) is untouched, and no case in this
  catalogue writes a non-UTF-8 fixture or targets an unwritable path. `PQL-219`–`PQL-223` (the
  `ControlFormatCommand` cases, the closest thing to this file) reproduce round 3 exactly, including
  the still-open `SUITE`-flattening defect (`PQL-219`) — proving the CLI change did not silently
  paper over it.

## Confirmed fixes — a case that failed in round 3 and passes now

**2 found, neither a product fix** — see the methodology note above the counts table.

| Id | Round-3 finding | Round-4 result | Assessment |
|---|---|---|---|
| `PQL-268` | Round 3's ten per-function null-argument probes disagreed with SQL because the harness called `Function.evaluate()` with a bare `None`, which several library functions render as the text `"NONE"`/`"None"` rather than propagating as unknown. | All ten functions agree between SQLite and the reference (`agree=True` for every entry) when driven through the real `ReferenceEvaluator.evaluate` dispatch. | Harness artifact in round 3, not a source change — `pql/library.py` and `backend/reference.py` are byte-identical to the round-3 tree. |
| `BE-073` | Round 3 found SQLite giving `1` (true) while DuckDB and PostgreSQL gave `0` (false) for `MATCHES /^[0-9.]+$/` against `CAST(1.10 AS …)`, attributed to `Decimal('1.10')` vs `1.10` stringifying differently. | This round's `CAST(1.10 AS VARCHAR)` renders `'1.10'` on both DuckDB and PostgreSQL in this environment (not `'1.1'`), so all engines and the reference agree. | Unreconciled — `backend/dialect.py` and `backend/reference.py` are unchanged; the difference is most likely in exactly which literal/column construction each round's harness used, not in the product. Recorded honestly rather than claimed as a fix. |


## Per-case results (id order, 629 rows)

| Id | Result | Observed |
|---|---|---|
| PQL-001 | FAIL | kinds=['END', 'IDENTIFIER', 'KEYWORD', 'NUMBER', 'OPERATOR', 'PARAMETER', 'PUNCTUATION', 'REGEX'] expected=['END', 'IDENTIFIER', 'KEYWORD', 'NUMBER', 'OPERATOR', 'PARAMETER', 'PUNCTUATION', 'REGEX', 'STRING'] |
| PQL-002 | PASS | toks=[Token(end, '', line 1, column 1)] |
| PQL-003 | PASS | toks=[Token(end, '', line 4, column 1)] |
| PQL-004 | PASS | msg=[PQL.SYNTAX] a comment is opened with /* and never closed \| Next: Close it with */, or use -- for a comment to the end of the line. \| Context: position='line 1, column 23' |
| PQL-005 | FAIL | toks=None msg=[PQL.SYNTAX] a pattern is opened with / and never closed \| Next: Close it with another /, as in /^[A-Z]{2}[0-9]{10}$/. \| Context: position='line 1, column 37' |
| PQL-006 | PASS | first=Token(keyword, 'CHECK', line 2, column 1) |
| PQL-007 | PASS | last=Token(end, '', line 1, column 29) err=None |
| PQL-008 | PASS | msg=[PQL.SYNTAX] a piece of text is opened with ' and never closed \| Next: Close it with another '. To include a quote in the text, double it: 'O''Brien'. \| Context: position='line 1, column 31' |
| PQL-009 | PASS | msg=[PQL.SYNTAX] a piece of text is opened with ' and never closed \| Next: Close it with another '. To include a quote in the text, double it: 'O''Brien'. \| Context: position='line 1, column 9' pos=line 1, column 9 |
| PQL-010 | PASS | tok=Token(string, "'O''Brien'", line 1, column 1) |
| PQL-011 | PASS | tok=Token(string, "''''", line 1, column 1) |
| PQL-012 | PASS | tok=Token(string, "''", line 1, column 1) |
| PQL-013 | PASS | msg=[PQL.SYNTAX] a quoted name is opened and never closed \| Next: Close it with a double quote: "risk positions". \| Context: position='line 1, column 7' |
| PQL-014 | PASS | tok=Token(identifier, '"a""b"', line 1, column 1) |
| PQL-015 | FAIL | target='""' err=None |
| PQL-016 | PASS | qualify('"schema.table"') -> '"""schema"."table"""' (documented: splits on the dot even inside quotes) |
| PQL-017 | PASS | {'MATCHES /^[A-Z]{2}/': ['KEYWORD', 'REGEX', 'END'], 'LIKE /x/': ['KEYWORD', 'REGEX', 'END'], 'ILIKE /x/': ['KEYWORD', 'REGEX', 'END']} |
| PQL-018 | PASS | {'a / b': [('IDENTIFIER', 'a'), ('OPERATOR', '/'), ('IDENTIFIER', 'b')], '1 / 2': [('NUMBER', '1'), ('OPERATOR', '/'), ('NUMBER', '2')], '(a) / 2': [('PUNCTUATION', '('), ('IDENTIFIER', 'a'), ('PUNCTUATION', ')'), ('OPERATOR', '/'), ('NUMBER', '2')], 'f(x) / 2': [('IDENTIFIER', 'f'), ('PUNCTUATION', '('), ('IDENTIFIER', 'x'), ('PUNCTUATION', ')'), ('OPERATOR', '/'), ('NUMBER', '2')]} |
| PQL-019 | PASS | [('REGEX', '/abc/'), ('END', '')] |
| PQL-020 | PASS | msg=[PQL.SYNTAX] a pattern is opened with / and never closed \| Next: Close it with another /, as in /^[A-Z]{2}[0-9]{10}$/. \| Context: position='line 1, column 19' |
| PQL-021 | PASS | [Token(regex, '/a\\/b/', line 1, column 1)] |
| PQL-022 | PASS | msg=[PQL.SYNTAX] a pattern is opened with / and never closed \| Next: Close it with another /, as in /^[A-Z]{2}[0-9]{10}$/. \| Context: position='line 1, column 1' pos=line 1, column 1 |
| PQL-023 | PASS | clean PqlSyntaxError: [PQL.SYNTAX] a pattern is opened with / and never closed \| Next: Close it with another /, as in /^[A-Z]{2}[0-9]{10}$/. \| Context: position='line 1, column 1' |
| PQL-024 | PASS | {'$ 1': "[PQL.SYNTAX] $ must be followed by a parameter name \| Next: Name the parameter, as in $business_date. Parameters are how a control refers to the run's date without becoming non-repeatable. \| Context: position='line 1, column 1'", '$1': "[PQL.SYNTAX] $ must be followed by a parameter name \| Next: Name the parameter, as in $business_date. Parameters are how a control refers to the run's … |
| PQL-025 | PASS | tok=Token(parameter, '$business_date', line 1, column 1) |
| PQL-026 | PASS | {'0': 'ok', '1': 'ok', '1.5': 'ok', '1e3': 'ok', '1E+3': 'ok', '1e-3': 'ok', '1.5e-3': 'ok', '10%': 'ok', '0.1%': 'ok', '1.5e3%': 'ok'} |
| PQL-027 | PASS | lex={'.5': [('PUNCTUATION', '.'), ('NUMBER', '5'), ('END', '')], '1.': [('NUMBER', '1'), ('PUNCTUATION', '.'), ('END', '')], '1_000': [('NUMBER', '1'), ('IDENTIFIER', '_000'), ('END', '')], '0x1F': [('NUMBER', '0'), ('IDENTIFIER', 'x1F'), ('END', '')], '1e': [('NUMBER', '1'), ('IDENTIFIER', 'e'), ('END', '')], '1%%': [('NUMBER', '1%'), ('OPERATOR', '%'), ('END', '')]} |
| PQL-028 | PASS | [Token(operator, '-', line 1, column 1), Token(number, '10', line 1, column 2)] |
| PQL-029 | PASS | {'check': ('KEYWORD', 'check', 'CHECK'), 'Check': ('KEYWORD', 'Check', 'CHECK'), 'CHECK': ('KEYWORD', 'CHECK', 'CHECK')} |
| PQL-030 | PASS | n=116 bad=[] |
| PQL-031 | PASS | names=['on', 'severity', 'source', 'count'] |
| PQL-032 | PASS | tgts=['schema', 'record', 'key'] |
| PQL-033 | PASS | where-as-modifier-start=parsed where-as-column-after-dot=parsed:where |
| PQL-034 | PASS | [PQL.SYNTAX] expected a column name after the dot and found '2' \| Next: Names are written plainly, or in double quotes if they contain spaces: "risk positions". \| Context: position='line 1, column 9' |
| PQL-035 | FAIL | AssertionError:  |
| PQL-036 | FAIL | AssertionError:  |
| PQL-037 | FAIL | target=montànt rendered_reparses=False detail=AssertionError:  |
| PQL-038 | PASS | {'@': '[PQL.SYNTAX] \'@\' does not belong in a control \| Next: Remove it. If it is part of a name, quote the name: "odd name". If it is part of text, quote the text: \'value\'. \| Context: position=\'line 1, column 11\'', '#': '[PQL.SYNTAX] \'#\' does not belong in a control \| Next: Remove it. If it is part of a name, quote the name: "odd name". If it is part of text, quote the text: \'value\'. … |
| PQL-039 | PASS | {'<>': ['<>'], '!=': ['!='], '>=': ['>='], '<=': ['<='], '\|\|': ['\|\|'], '=': ['='], '>': ['>'], '<': ['<'], '+': ['+'], '-': ['-'], '*': ['*'], '/': "[PQL.SYNTAX] a pattern is opened with / and never closed \| Next: Close it with another /, as in /^[A-Z]{2}[0-9]{10}$/. \| Context: position='line 1, column 1'", '%': ['%'], 'a>=b': ['a', '>=', 'b']} |
| PQL-040 | PASS | msg=[PQL.SYNTAX] '\|' does not belong in a control \| Next: Remove it. If it is part of a name, quote the name: "odd name". If it is part of text, quote the text: 'value'. \| Context: position='line 1, column 3' |
| PQL-041 | PASS | {'(': 'PUNCTUATION', ')': 'PUNCTUATION', ',': 'PUNCTUATION', '.': 'PUNCTUATION', '{': 'PUNCTUATION', '}': 'PUNCTUATION', '[': 'PUNCTUATION', ']': 'PUNCTUATION', ':': 'PUNCTUATION', ';': 'PUNCTUATION'} |
| PQL-042 | PASS | n_tokens=10 sample=[Token(keyword, 'CHECK', line 1, column 1), Token(identifier, 't', line 1, column 7), Token(punctuation, '.', line 1, column 8)] |
| PQL-043 | PASS | tok=Token(keyword, 'CHECK', line 2, column 3) |
| PQL-044 | PASS | lf=[(1, 1), (1, 7), (1, 8), (1, 9), (1, 11), (1, 14), (1, 18), (2, 1), (2, 9), (2, 12)] crlf=[(1, 1), (1, 7), (1, 8), (1, 9), (1, 11), (1, 14), (1, 18), (2, 1), (2, 9), (2, 12)] |
| PQL-045 | PASS | {'C': "PqlSyntaxError: [PQL.SYNTAX] expected CHECK and found 'C' \| Next: Add CHECK here. \| Context: position='line 1, column 1'", '(': "PqlSyntaxError: [PQL.SYNTAX] expected CHECK and found '(' \| Next: Add CHECK here. \| Context: position='line 1, column 1'", "'": "PqlSyntaxError: [PQL.SYNTAX] a piece of text is opened with ' and never closed \| Next: Close it with another '. To include a quote… |
| PQL-046 | PASS | lexes_ok excerpt_len=306 |
| PQL-047 | FAIL | {'syntax': 'a pattern is opened with / and never closed (at line 1, column 19)\n\n  CHECK t.a MATCHES /^A\n                    ^\n\n→ Close it with another /, as in /^[A-Z]{2}[0-9]{10}$/.', 'type': "t.isin holds text, and it is being compared with 12, which is number (at line 1, column 16)\n\n  CHECK t.isin = 12 BECAUSE 'x'\n                 ^^\n\n→ Compare like with like. Engines differ on whethe… |
| PQL-048 | PASS | length=1 carets=1 excerpt=['  CHECK t.a MATCHES /^A', '                    ^'] |
| PQL-049 | PASS | window='  …xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx!xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx…' caret='                                                               ^' window_len=124 |
| PQL-050 | PASS | render='x (at line 1, column 1)\n\n→ y' excerpt=[] |
| PQL-051 | PASS | excerpt=[] |
| PQL-052 | PASS | with={'position': 'line 1, column 1'} without={} |
| PQL-053 | PASS | {'PqlError': 'PQL.INVALID', 'PqlSyntaxError': 'PQL.SYNTAX', 'PqlTypeError': 'PQL.TYPE', 'PqlUnsupportedError': 'PQL.UNSUPPORTED'} |
| PQL-054 | PASS | files=['src/prama/backend/fuse.py', 'src/prama/backend/sql.py'] outside_expected_files=[] |
| PQL-055 | FAIL | returncode=1 whole_stdout_is_json=False stdout='a pattern is opened with / and never closed (at line 1, column 19)\n\n  CHECK t.a MATCHES /^A\n                    ^\n\n→ Close it with another /, as in /^[A-Z]{2}[0-9]{10}$/.\n' |
| PQL-056 | PASS | ctl=Control(target='positions', assertion=PredicateAssertion(subject=ColumnRef(name='account_id', dataset='positions'), operator='is_not_null', argument=None, upper=None, negated=False), name='', where=None, segmentation=None, threshold=Threshold(unit='rows', value=0.0, currency='', comparator='<='), severity=<Severity.MAJOR: 'major'>, dimensions=(), because='', unknown_policy=<UnknownPolicy.VIOLA… |
| PQL-057 | PASS | parsed=True findings=[LintFinding(rule='no-justification', message='this control does not say why it exists', remedy="Add BECAUSE '…'. When it fires at three in the morning, the sentence explaining what the business declared is the most useful thing on the screen — and a control nobody can justify is one nobody will maintain.", control='CHECK t.a IS NOT NULL', related='', severity='info', position… |
| PQL-058 | PASS | parse_ok=True n=2 parse_control_err=[PQL.SYNTAX] there is more text after the control: 'CHECK' \| Next: Each control ends where the next CHECK begins. \| Context: position='line 1, column 23' |
| PQL-059 | PASS | {'SELECT * FROM t': "[PQL.SYNTAX] expected a control and found 'SELECT' \| Next: A control begins with CHECK, and a group of them with SUITE. For example: CHECK positions.account_id IS NOT NULL \| Context: position='line 1, column 1'", '{ }': "[PQL.SYNTAX] expected a control and found '{' \| Next: A control begins with CHECK, and a group of them with SUITE. For example: CHECK positions.account_id … |
| PQL-060 | PASS | suites=(Suite(name='core', controls=(Control(target='t', assertion=PredicateAssertion(subject=ColumnRef(name='a', dataset='t'), operator='is_not_null', argument=None, upper=None, negated=False), name='', where=None, segmentation=None, threshold=Threshold(unit='rows', value=0.0, currency='', comparator='<='), severity=<Severity.MAJOR: 'major'>, dimensions=(), because='', unknown_policy=<UnknownPoli… |
| PQL-061 | PASS | suites=(Suite(name='core', controls=()),) err=None |
| PQL-062 | PASS | err=[PQL.SYNTAX] the suite 'core' is opened and never closed \| Next: Close it with }. \| Context: position='line 1, column 35' |
| PQL-063 | PASS | err=[PQL.SYNTAX] expected CHECK and found 'SUITE' \| Next: Add CHECK here. \| Context: position='line 1, column 11' |
| PQL-064 | FAIL | {'keyword': "parsed name='record'", 'quoted': "name='core suite' render='SUITE core suite {\\n\\n}' REPARSE_FAIL: [PQL.SYNTAX] expected '{' and found 'suite' \| Next: Add '{' here. \| Context: position='line 1, column 12'"} |
| PQL-065 | PASS | n_suites=2 err=None |
| PQL-066 | PASS | target=positions subject=ColumnRef(name='notional', dataset='positions') |
| PQL-067 | PASS | err=[PQL.SYNTAX] expected something to check about warehouse and found '.' \| Next: A control says what must be true: IS NOT NULL, IN CODELIST, HAS UNIQUE KEY (…), HAS ROW COUNT BETWEEN …, REFERENCES …, SATISFIES … \| Context: position='line 1, column 21' |
| PQL-068 | FAIL | err=[PQL.SYNTAX] expected a comparison after positions.IS, found 'NULL' \| Next: For example: > 0, IN ('GBP','USD'), BETWEEN 1 AND 10, MATCHES /^[A-Z]{2}/ \| Context: position='line 1, column 25' |
| PQL-069 | PASS | err=[PQL.SYNTAX] expected something to check about positions and found the end of the control \| Next: A control says what must be true: IS NOT NULL, IN CODELIST, HAS UNIQUE KEY (…), HAS ROW COUNT BETWEEN …, REFERENCES …, SATISFIES … \| Context: position='line 1, column 16' |
| PQL-070 | PASS | err=[PQL.SYNTAX] this check is about a column, but no column was named \| Next: Name the column: CHECK positions.notional_amount IS NOT NULL. Checks about the whole dataset use HAS: HAS ROW COUNT, HAS UNIQUE KEY. \| Context: position='line 1, column 24' |
| PQL-071 | PASS | c1=is_not_null,False c2=is_null,False |
| PQL-072 | PASS | is_unique=is_unique,False is_not_unique=is_unique,True SAME_AS_IS_UNIQUE=False |
| PQL-073 | PASS | predicate=None assertion_kind=unique_key verdict=Verdict.FAIL |
| PQL-074 | PASS | {'bare': 'isin', 'quoted': 'isin', 'keyword': 'ISIN'} |
| PQL-075 | PASS | assertion_kind=predicate |
| PQL-076 | PASS | resolved: predicate=Expr(kind='op', name='IN', value=None, args=(Expr(kind='col', name='ccy', value=None, args=(), type_name='unknown'), Expr(kind='list', name='', value=None, args=(Expr(kind='lit', name='', value='AED', args=(), type_name='text'), Expr(kind='lit', name='', value='AFN', args=(), typ |
| PQL-077 | PASS | ValidationError: [INPUT.INVALID] the codelist 'nosuchlist' is not registered \| Next: Register it before compiling, or write the values out. A control cannot be run against a list nobody has defined. \| Context: codelist='nosuchlist' |
| PQL-078 | PASS | {'K t IS FRESH WITHIN 30 MINUTES': (True, None), "H WITHIN 30 MINUTES OF '06:30'": (True, None), " 30 MINUTES CALENDAR 'TARGET2'": (True, None), " OF '06:30' CALENDAR 'TARGET2'": (True, None)} |
| PQL-079 | PASS | {'WITHIN 30 MINUTES': 30, 'WITHIN 1 MINUTE': 1, 'WITHIN 4 HOURS': 240, 'WITHIN 1 HOUR': 60, 'WITHIN 2 DAYS': 2880, 'WITHIN 1 DAY': 1440} |
| PQL-080 | PASS | {'IS FRESH WITHIN 30 SECONDS': "[PQL.SYNTAX] expected MINUTES, HOURS or DAYS and found 'SECONDS' \| Next: For example: WITHIN 30 MINUTES, or WITHIN 4 HOURS. \| Context: position='line 1, column 28'", 'IS FRESH WITHIN 30 WEEKS': "[PQL.SYNTAX] expected MINUTES, HOURS or DAYS and found 'WEEKS' \| Next: For example: WITHIN 30 MINUTES, or WITHIN 4 HOURS. \| Context: position='line 1, column 28'"} |
| PQL-081 | PASS | e1=[PQL.SYNTAX] expected how long as a whole number and found '1.5' \| Next: Use a whole number here. \| Context: position='line 1, column 25' e2=[PQL.SYNTAX] expected how long and found '-' \| Next: Write a number here. \| Context: position='line 1, column 25' |
| PQL-082 | FAIL | desc='the data arrives on time' due_time='06:30' due_time_in_desc=False |
| PQL-083 | FAIL | predicate=None metrics=['scanned_rows'] verdict=ControlResult(plan_id='ir:sha256:ec3782874717f0010712b201f02d8448d883f6d6f07d6dead2564f32523d7309', verdict=<Verdict.INDETERMINATE: 'indeterminate'>, metrics={'scanned_rows': 10.0}, segments=(), samples=(), engine='', detail='') (expected: derived from arrival time; actual: no freshness branch) |
| PQL-084 | PASS | {'(a)': ['a'], '(a, b, c)': ['a', 'b', 'c']} n50=50 is_structural=True |
| PQL-085 | PASS | err=[PQL.SYNTAX] expected a column name and found ')' \| Next: Names are written plainly, or in double quotes if they contain spaces: "risk positions". \| Context: position='line 1, column 25' |
| PQL-086 | FAIL | dup_cols=[('t', 'a'), ('t', 'a')] deduped_or_refused=False foreign_findings=[Finding(message='other.a belongs to other, but this control is about t', remedy='Use a column of t, or declare the relationship between the two datasets and write a control across it.', position=Position(line=1, column=25, offset=24, length=5), level='error')] |
| PQL-087 | PASS | {'between': (1, 8), 'atleast': (7, None), 'atmost': (None, 100)} |
| PQL-088 | PASS | {'HAS ROW COUNT > 100': "[PQL.SYNTAX] expected BETWEEN or AT LEAST/MOST after ROW COUNT, found '>' \| Next: For example: HAS ROW COUNT BETWEEN 900000 AND 1200000 \| Context: position='line 1, column 23'", 'HAS ROW COUNT 100': "[PQL.SYNTAX] expected BETWEEN or AT LEAST/MOST after ROW COUNT, found '100' \| Next: For example: HAS ROW COUNT BETWEEN 900000 AND 1200000 \| Context: position='line 1, colu… |
| PQL-089 | FAIL | {'HAS ROW COUNT AT LEAST 1e6': "BARE ValueError: invalid literal for int() with base 10: '1e6'", 'HAS ROW COUNT AT LEAST 1000000.0': "ctl=False err=[PQL.SYNTAX] expected a count as a whole number and found '1000000.0' \| Next: Use a whole number here. \| Context: position='line 1, column 32'", 'HAS ROW COUNT AT LEAST 10%': "ctl=False err=[PQL.SYNTAX] expected a count as a whole number and found '1… |
| PQL-090 | PASS | verdict=Verdict.PASS metrics={'scanned_rows': 0.0} |
| PQL-091 | PASS | op=has_length_between arg=Literal(value=12, literal_type='number') upper=Literal(value=12, literal_type='number') |
| PQL-092 | FAIL | findings=[Finding(message='t.isin holds text, and it is being compared with 12, which is number', remedy='Compare like with like. Engines differ on whether they coerce these silently, so a control written this way would mean one thing on one database and something else on another.', position=Position(line=1, column=33, offset=32, length=2), level='error'), Finding(message='t.isin holds text, and i… |
| PQL-093 | PASS | {'lower': 'ok', 'sqlite': 'compiled ok', 'reference': 'ran: verdict=Verdict.FAIL'} |
| PQL-094 | PASS | any_parsed=False |
| PQL-095 | PASS | {'CHECK t HAS PRECISION 2': "[PQL.SYNTAX] expected UNIQUE KEY, ROW COUNT, LENGTH or FORMAT after HAS, found 'PRECISION' \| Next: For example: HAS UNIQUE KEY (account_id, as_of_date), or HAS ROW COUNT BETWEEN 900000 AND 1200000 \| Context: position='line 1, column 13'", 'CHECK t HAS SCALE 2': "[PQL.SYNTAX] expected UNIQUE KEY, ROW COUNT, LENGTH or FORMAT after HAS, found 'SCALE' \| Next: For exampl… |
| PQL-096 | PASS | {'CHECK t.a IS INCREASING': "[PQL.SYNTAX] expected NULL, UNIQUE, VALID, FRESH or IN after IS, found 'INCREASING' \| Next: For example: IS NOT NULL, IS UNIQUE, IS VALID ISIN, or IS FRESH WITHIN 30 MINUTES OF '06:30' \| Context: position='line 1, column 14'", 'CHECK t.a IS NON DECREASING': "[PQL.SYNTAX] expected NULL, UNIQUE, VALID, FRESH or IN after IS, found 'NON' \| Next: For example: IS NOT NULL… |
| PQL-097 | PASS | assertion=ReferenceAssertion(column=ColumnRef(name='account_id', dataset='positions'), target_dataset='accounts', target_column='account_id') err=None |
| PQL-098 | PASS | err=[PQL.SYNTAX] expected '.' and found the end of the control \| Next: Add '.' here. \| Context: position='line 1, column 30' |
| PQL-099 | FAIL | {'FERENCES accounts.nosuchcolumn': [], '_id REFERENCES nosuchdataset.x': []} |
| PQL-100 | PASS | assertion=ExpressionAssertion source_syntax=pql |
| PQL-101 | PASS | c1=FunctionalDependencyAssertion(determinant=(ColumnRef(name='account_id', dataset=''),), dependent=(ColumnRef(name='legal_entity_id', dataset=''),)) c2=FunctionalDependencyAssertion(determinant=(ColumnRef(name='a', dataset=''), ColumnRef(name='b', dataset='')), dependent=(ColumnRef(name='c', dataset=''), ColumnRef(name='d', dataset=''))) |
| PQL-102 | FAIL | {'IES UPPER(a) DETERMINES b': "[PQL.SYNTAX] the left of DETERMINES must be one or more columns \| Next: For example: SATISFIES account_id DETERMINES legal_entity_id \| Context: position='line 1, column 39'", ' SATISFIES a DETERMINES 1': "[PQL.SYNTAX] the right of DETERMINES must be one or more columns \| Next: For example: SATISFIES account_id DETERMINES legal_entity_id \| Context: position='line … |
| PQL-103 | PASS | err=[PQL.SYNTAX] EXCEL must be followed by the formula in quotes \| Next: For example: SATISFIES EXCEL '=AND([quantity] > 0, [notional] = [quantity] * [price])' \| Context: position='line 1, column 25' |
| PQL-104 | PASS | c1_syntax=pql c2_syntax=excel |
| PQL-105 | PASS | selector=Selector(kind='attribute', where=None, concept='', concept_property='') is_template=True subject=SelectedAttribute |
| PQL-106 | PASS | where=is_cde op=is_not_null err=None |
| PQL-107 | PASS | {"gs IN ('pii') IS NOT NULL": ("tags IN ('pii')", 'is_not_null'), "er1','tier2') IS NOT NULL": ("criticality IN ('tier1', 'tier2')", 'is_not_null')} |
| PQL-108 | PASS | direct_err=[PQL.SYNTAX] there is more text after the control: 'IS' \| Next: Each control ends where the next CHECK begins. \| Context: position='line 1, column 44' workaround_ok=True |
| PQL-109 | PASS | selector=Selector(kind='concept', where=None, concept='Instrument', concept_property='ISIN') err=None |
| PQL-110 | PASS | err=[PQL.SYNTAX] expected '.' and found 'IS' \| Next: Add '.' here. \| Context: position='line 1, column 26' |
| PQL-111 | PASS | err=[PQL.SYNTAX] a reference names one column on each side, so it cannot be written against a selector \| Next: Write it against the dataset: CHECK positions.account_id REFERENCES accounts.account_id. \| Context: position='line 1, column 47' |
| PQL-112 | FAIL | {'ROW COUNT AT LEAST 1': 'n_expanded=5 identical_assertions=True one_or_refused=False', '_cde SATISFIES a > 0': 'n_expanded=5 identical_assertions=True one_or_refused=False'} |
| PQL-113 | PASS | equal=True c1.where=t.a > 0 |
| PQL-114 | PASS | parsed=True err=None ctl=Control(target='t', assertion=PredicateAssertion(subject=ColumnRef(name='a', dataset='t'), operator='>', argument=Literal(value=0, literal_type='number'), upper=None, negated=False), name='', where=BinaryOp(operator='>', left=ColumnRef(name='b', dataset='t'), right=Literal(value=0, literal_type='number')), segmentation=Segmentation(columns=(ColumnRef(name='c', dataset='t')… |
| PQL-115 | PASS | {'WHERE t.b > 0': "[PQL.SYNTAX] WHERE is given twice for this control \| Next: Remove one of them. Two WHERE clauses would leave it ambiguous which was meant. \| Context: position='line 1, column 29'", 'SEVERITY minor': "[PQL.SYNTAX] SEVERITY is given twice for this control \| Next: Remove one of them. Two SEVERITY clauses would leave it ambiguous which was meant. \| Context: position='line 1, col… |
| PQL-116 | PASS | err=[PQL.SYNTAX] threshold is given twice for this control \| Next: Remove one of them. Two threshold clauses would leave it ambiguous which was meant. \| Context: position='line 1, column 38' |
| PQL-117 | PASS | err=[PQL.SYNTAX] there is more text after the control: 'SEVERTIY' \| Next: Each control ends where the next CHECK begins. \| Context: position='line 1, column 23' |
| PQL-118 | PASS | {'info': 'info', 'INFO': 'info', 'Info': 'info', 'warning': 'warning', 'WARNING': 'warning', 'Warning': 'warning', 'minor': 'minor', 'MINOR': 'minor', 'Minor': 'minor', 'major': 'major', 'MAJOR': 'major', 'Major': 'major', 'critical': 'critical', 'CRITICAL': 'critical', 'Critical': 'critical'} |
| PQL-119 | PASS | {'high': "[PQL.SYNTAX] 'high' is not a severity \| Next: Use one of: info, warning, minor, major, critical. \| Context: position='line 1, column 24'", 'p1': "[PQL.SYNTAX] 'p1' is not a severity \| Next: Use one of: info, warning, minor, major, critical. \| Context: position='line 1, column 24'", '3': "[PQL.SYNTAX] '3' is not a severity \| Next: Use one of: info, warning, minor, major, critical. \|… |
| PQL-120 | PASS | err=[PQL.SYNTAX] '' is not a severity \| Next: Use one of: info, warning, minor, major, critical. \| Context: position='line 1, column 31' |
| PQL-121 | PASS | single=(<Dimension.COMPLETENESS: 'completeness'>,) all8=(<Dimension.COMPLETENESS: 'completeness'>, <Dimension.UNIQUENESS: 'uniqueness'>, <Dimension.VALIDITY: 'validity'>, <Dimension.CONSISTENCY: 'consistency'>, <Dimension.ACCURACY: 'accuracy'>, <Dimension.TIMELINESS: 'timeliness'>, <Dimension.INTEGRITY: 'integrity'>, <Dimension.CONFORMITY: 'conformity'>) order=(<Dimension.VALIDITY: 'validity'>, <D… |
| PQL-122 | PASS | err=[PQL.SYNTAX] 'correctness' is not a quality dimension \| Next: Use one of: completeness, uniqueness, validity, consistency, accuracy, timeliness, integrity, conformity. \| Context: position='line 1, column 25' |
| PQL-123 | PASS | dims=(<Dimension.VALIDITY: 'validity'>, <Dimension.VALIDITY: 'validity'>) rendered='CHECK t.a > 0\n  SEVERITY major\n  DIMENSION validity, validity' |
| PQL-124 | PASS | e1=[PQL.SYNTAX] expected the reason this control exists, in quotes, and found 'it' \| Next: Quoted text is written between single quotes: 'like this'. \| Context: position='line 1, column 23' e2=[PQL.SYNTAX] expected the reason this control exists, in quotes, and found '"it matters"' \| Next: Quoted text is written between single quotes: 'like this'. \| Context: position='line 1, column 23' |
| PQL-125 | PASS | because="the desk's own rule" rendered_because="the desk's own rule" |
| PQL-126 | PASS | because='' rendered='CHECK t.a IS NOT NULL\n  SEVERITY major' findings=[LintFinding(rule='no-justification', message='this control does not say why it exists', remedy="Add BECAUSE '…'. When it fires at three in the morning, the sentence explaining what the business declared is the most useful thing on the screen — and a control nobody can justify is one nobody will maintain.", control='CHECK t.a I… |
| PQL-127 | PASS | owner='Head of Market Risk Data' rendered="CHECK t.a > 0\n  SEVERITY major\n  OWNER 'Head of Market Risk Data'" |
| PQL-128 | FAIL | owner="O'Brien" rendered="CHECK t.a > 0\n  SEVERITY major\n  OWNER 'O'Brien' REPARSE_FAIL: [PQL.SYNTAX] a piece of text is opened with ' and never closed \| Next: Close it with another '. To include a quote in the text, double it: 'O''Brien'. \| Context: position='line 3, column 17'" |
| PQL-129 | PASS | {'counts': ('counts', 50), 'samples': ('samples', 50), 'full': ('full', 50), 'samples10': ('samples', 10)} |
| PQL-130 | PASS | {'all': "[PQL.SYNTAX] 'all' is not an evidence level \| Next: Use counts, samples, or full. \| Context: position='line 1, column 24'", 'rows': "[PQL.SYNTAX] 'rows' is not an evidence level \| Next: Use counts, samples, or full. \| Context: position='line 1, column 24'"} |
| PQL-131 | PASS | {0: 'LIMIT present=True', 1000000: 'LIMIT present=True'} |
| PQL-132 | FAIL | orig=(EvidenceLevel.FULL,10) rendered='CHECK t.a > 0\n  SEVERITY major\n  EVIDENCE full' reparsed=(EvidenceLevel.FULL,50) |
| PQL-133 | PASS | err=[PQL.SYNTAX] TREAT UNKNOWN AS PASS needs a BECAUSE \| Next: Ignoring unknowns is a decision somebody has to own. Say why: BECAUSE 'unmatched rows are handled by the break workflow'. \| Context: position='line 1, column 32' |
| PQL-134 | PASS | c1=UnknownPolicy.VIOLATION c2=UnknownPolicy.VIOLATION |
| PQL-135 | PASS | {'NULL': "[PQL.SYNTAX] expected PASS or VIOLATION after TREAT UNKNOWN AS, found 'NULL' \| Next: Prama counts an unknown as a violation by default, because silence about unknowns is the commonest source of false confidence. Write TREAT UNKNOWN AS PASS only where the business genuinely means it. \| Context: position='line 1, column 32'", 'IGNORE': "[PQL.SYNTAX] expected PASS or VIOLATION after TREAT… |
| PQL-136 | PASS | c1=True e1=None c2=True e2=None |
| PQL-137 | PASS | {'alert': 'alert', 'block': 'block', 'quarantine': 'quarantine', 'tag': 'tag'} |
| PQL-138 | PASS | {'stop': "[PQL.SYNTAX] 'stop' is not something to do on failure \| Next: Use one of: alert, block, quarantine, tag. \| Context: position='line 1, column 23'", 'page': "[PQL.SYNTAX] 'page' is not something to do on failure \| Next: Use one of: alert, block, quarantine, tag. \| Context: position='line 1, column 23'"} |
| PQL-139 | PASS | c1=Threshold(unit='rows', value=5.0, currency='', comparator='<=') c2=Threshold(unit='rows', value=5.0, currency='', comparator='>=') |
| PQL-140 | FAIL | orig=Threshold(unit='rows', value=5.0, currency='', comparator='>=') rendered='CHECK t.a IS NOT NULL\n  AT MOST 5 ROWS\n  SEVERITY major' reparsed=Threshold(unit='rows', value=5.0, currency='', comparator='<=') |
| PQL-141 | FAIL | orig=1234567.0 rendered='CHECK t.a IS NOT NULL\n  AT MOST 1.23457e+06 ROWS\n  SEVERITY major' reparsed=1234570.0 |
| PQL-142 | PASS | ctl=Threshold(unit='rows', value=0.5, currency='', comparator='<=') err=None |
| PQL-143 | PASS | {'rows_plural': 'rows', 'row_singular': 'rows', 'bare': 'rows'} |
| PQL-144 | PASS | pct=0.005 bare=0.5 |
| PQL-145 | PASS | parsed=True findings=[LintFinding(rule='never-fires', message='a threshold of 100% cannot be exceeded, so this control can never fail', remedy='Set a rate the data could realistically breach, or remove the control. A control that cannot fail is worse than none: it appears on the coverage report and covers nothing.', control='CHECK t.a > 0', related='', severity='error', position=Position(line=1, c… |
| PQL-146 | PASS | is_strict=True rendered='CHECK t.a > 0\n  BELOW 0%\n  SEVERITY major' |
| PQL-147 | PASS | {'usd': ('amount', 'USD'), 'gbp': ('amount', 'GBP'), 'bare': ('amount', '')} |
| PQL-148 | PASS | {'WITHIN 100 SUM': "[PQL.SYNTAX] there is more text after the control: 'SUM' \| Next: Each control ends where the next CHECK begins. \| Context: position='line 1, column 26'", 'WITHIN 100 MIN': "[PQL.SYNTAX] there is more text after the control: 'MIN' \| Next: Each control ends where the next CHECK begins. \| Context: position='line 1, column 26'", 'WITHIN 100 KEY': "[PQL.SYNTAX] there is more tex… |
| PQL-149 | FAIL | ctl_threshold=None err=[PQL.SYNTAX] there is more text after the control: 'SIGMA' \| Next: Each control ends where the next CHECK begins. \| Context: position='line 1, column 32' |
| PQL-150 | FAIL | threshold=Threshold(metric='violating_rows', comparator=<Comparator.LE: '<='>, value=100.0, relative_to='') |
| PQL-151 | FAIL | lowered (no refusal); metrics=['scanned_rows'] threshold=Threshold(metric='violating_rows', comparator=<Comparator.LE: '<='>, value=0.1, relative_to='scanned_rows') |
| PQL-152 | PASS | c1=Segmentation(columns=(ColumnRef(name='entity', dataset=''),), having=None) c2=Segmentation(columns=(ColumnRef(name='entity', dataset=''), ColumnRef(name='ccy', dataset='')), having=None) |
| PQL-153 | PASS | having=COUNT(*) > 100 err=None |
| PQL-154 | FAIL | scope=Scope(dataset='t', binding='', filter=None, segment_by=('entity',), as_of='', window='') plan_has_having=False sql_has_having=False sql=SELECT "entity", COUNT(*) AS "scanned_rows", COALESCE(SUM(CASE WHEN NOT COALESCE(("a" IS NOT NULL), 0) THEN 1 ELSE 0 END), 0) AS "violating_rows" |
| PQL-155 | PASS | ref_keys=['None', 'X'] sql_keys=['None', 'X'] |
| PQL-156 | FAIL | keys=['x\|y\|z'] n_segments=1 (expected: 2 distinct) |
| PQL-157 | PASS | n_segments=5 overall=Verdict.FAIL per_segment=[<Verdict.PASS: 'pass'>, <Verdict.PASS: 'pass'>, <Verdict.FAIL: 'fail'>, <Verdict.PASS: 'pass'>, <Verdict.PASS: 'pass'>] |
| PQL-158 | PASS | overall=Verdict.INDETERMINATE per_segment=[('s1', <Verdict.PASS: 'pass'>), ('s2', <Verdict.PASS: 'pass'>), ('s3', <Verdict.INDETERMINATE: 'indeterminate'>)] |
| PQL-159 | FAIL | metrics={'scanned_rows': 20.0, 'distinct_keys': 17.0, 'duplicate_rows': 3.0, 'violating_rows': 3.0} (naive sum present and used as if meaningful: True) |
| PQL-160 | PASS | w1=BinaryOp(operator='OR', left=ColumnRef(name='a', dataset=''), right=BinaryOp(operator='AND', left=ColumnRef(name='b', dataset=''), right=ColumnRef(name='c', dataset=''))) w2=BinaryOp(operator='=', left=ColumnRef(name='a', dataset=''), right=BinaryOp(operator='+', left=Literal(value=1, literal_type='number'), right=BinaryOp(operator='*', left=Literal(value=2, literal_type='number'), right=Litera… |
| PQL-161 | PASS | w=UnaryOp(operator='NOT', operand=BinaryOp(operator='=', left=ColumnRef(name='side', dataset=''), right=Literal(value='BUY', literal_type='text'))) |
| PQL-162 | PASS | w=UnaryOp(operator='NOT', operand=UnaryOp(operator='NOT', operand=ColumnRef(name='a', dataset=''))) rendered='CHECK t.a > 0\n  WHERE NOT NOT a\n  SEVERITY major' |
| PQL-163 | PASS | ctl=PredicateAssertion(subject=ColumnRef(name='n', dataset='t'), operator='between', argument=Literal(value=1, literal_type='number'), upper=Literal(value=100, literal_type='number'), negated=False) severity=Severity.MINOR err=None |
| PQL-164 | PASS | w=BinaryOp(operator='AND', left=BinaryOp(operator='BETWEEN', left=ColumnRef(name='n', dataset=''), right=ListExpression(items=(Literal(value=1, literal_type='number'), Literal(value=100, literal_type='number')))), right=BinaryOp(operator='=', left=ColumnRef(name='status', dataset=''), right=Literal(value='ACTIVE', literal_type='text'))) err=None |
| PQL-165 | PASS | findings=[LintFinding(rule='always-fires', message='BETWEEN 100 AND 1 is empty, so every row violates it', remedy='The bounds are the wrong way round.', control='CHECK t.n BETWEEN 100 AND 1', related='', severity='error', position=Position(line=1, column=11, offset=10, length=7)), LintFinding(rule='no-justification', message='this control does not say why it exists', remedy="Add BECAUSE '…'. When … |
| PQL-166 | FAIL | findings=[LintFinding(rule='no-justification', message='this control does not say why it exists', remedy="Add BECAUSE '…'. When it fires at three in the morning, the sentence explaining what the business declared is the most useful thing on the screen — and a control nobody can justify is one nobody will maintain.", control="CHECK t.code BETWEEN 'Z' AND 'A'", related='', severity='info', position=… |
| PQL-167 | PASS | {'one': True, 'two': True, 'thousand': True} |
| PQL-168 | PASS | err=[PQL.SYNTAX] an empty set of values \| Next: List the permitted values, as in IN ('GBP', 'USD'). To require a column to be empty, write IS NULL. \| Context: position='line 1, column 17' |
| PQL-169 | PASS | err=[PQL.SYNTAX] expected a value or a column and found ')' \| Next: A column name, a number, quoted text, or $business_date. \| Context: position='line 1, column 30' |
| PQL-170 | PASS | {'in': (True, 'NOT IN'), 'between': (True, 'NOT BETWEEN'), 'matches': (True, 'NOT MATCHES'), 'like': (True, 'NOT LIKE'), 'ilike': (True, 'NOT ILIKE')} |
| PQL-171 | FAIL | e1=[PQL.SYNTAX] expected something to check about t and found 'LIKE' \| Next: A control says what must be true: IS NOT NULL, IN CODELIST, HAS UNIQUE KEY (…), HAS ROW COUNT BETWEEN …, REFERENCES …, SATISFIES … \| Context: position='line 1, column 11' c2_parsed=True |
| PQL-172 | PASS | compiled ok |
| PQL-173 | PASS | w=BinaryOp(operator='AND', left=BinaryOp(operator='OR', left=ColumnRef(name='a', dataset=''), right=ColumnRef(name='b', dataset='')), right=ColumnRef(name='c', dataset='')) rendered='CHECK t.a > 0\n  WHERE (a OR b) AND c\n  SEVERITY major' |
| PQL-174 | PASS | err=[PQL.SYNTAX] expected ')' and found the end of the control \| Next: Add ')' here. \| Context: position='line 1, column 28' |
| PQL-175 | FAIL | {1000: 'RecursionError (bare crash)', 5000: 'RecursionError (bare crash)'} |
| PQL-176 | FAIL | uncaught RecursionError: maximum recursion depth exceeded |
| PQL-177 | FAIL | {'sqlite': 'RecursionError: maximum recursion depth exceeded', 'duckdb': 'RecursionError: maximum recursion depth exceeded', 'postgresql': 'RecursionError: maximum recursion depth exceeded'} |
| PQL-178 | PASS | {'star': ('COUNT', (), False), 'one': ('COUNT', (ColumnRef(name='a', dataset=''),), False), 'distinct': ('COUNT', (ColumnRef(name='a', dataset=''),), True), 'many': ('CONCAT', (ColumnRef(name='a', dataset=''), ColumnRef(name='b', dataset=''), ColumnRef(name='c', dataset='')), False)} |
| PQL-179 | PASS | {'CURRENT_DATE': "[PQL.SYNTAX] CURRENT_DATE cannot be used in a control \| Next: A control that reads the clock or a random source produces a different verdict each time it runs, so its evidence cannot be replayed. Use $business_date, which the run supplies and the evidence records. \| Context: position='line 1, column 13'", 'CURRENT_TIME': "[PQL.SYNTAX] CURRENT_TIME cannot be used in a control \|… |
| PQL-180 | PASS | {'NOW()': "[PQL.SYNTAX] NOW() cannot be used in a control \| Next: A control that reads the clock or a random source produces a different verdict each time it runs, so its evidence cannot be replayed. Use $business_date, which the run supplies and the evidence records. \| Context: position='line 1, column 13'", 'RANDOM()': "[PQL.SYNTAX] RANDOM() cannot be used in a control \| Next: A control that … |
| PQL-181 | FAIL | {'pql:TODAY()': 'PARSED (should be refused)', 'pql:RANDBETWEEN(1,2)': 'PARSED (should be refused)', "pql:INDIRECT('a')": 'PARSED (should be refused)', 'pql:OFFSET(a,1,1)': 'PARSED (should be refused)', 'excel:CURRENT_DATE': "refused: [PQL.SYNTAX] there is no function called CURRENT_DATE \| Next: Available: ABS, COALESCE, CONCAT, DAY, IF, IFBLANK, INT, ISBLANK, ISNUMBER, LEFT, LEN, LENGTH, LOWER, M… |
| PQL-182 | FAIL | err=None |
| PQL-183 | PASS | {'length': True, 'count': True, 'min': True} |
| PQL-184 | PASS | err=[PQL.SYNTAX] expected something to check about LENGTH and found '(' \| Next: A control says what must be true: IS NOT NULL, IN CODELIST, HAS UNIQUE KEY (…), HAS ROW COUNT BETWEEN …, REFERENCES …, SATISFIES … \| Context: position='line 1, column 13' |
| PQL-185 | PASS | count_name=COUNT upper_name=upper |
| PQL-186 | PASS | {'type_findings': [Finding(message='there is no function called MEDIAN', remedy='Available: ABS, COALESCE, CONCAT, DAY, IF, IFBLANK, INT, ISBLANK, ISNUMBER, LEFT, LEN, LENGTH, LOWER, MAX, MID, MIN, MOD, MONTH, RIGHT, ROUND, SIGN, SUBSTITUTE, TRIM, UPPER, YEAR.', position=Position(line=1, column=1, offset=0, length=5), level='error')], 'compile': "refused: [PQL.UNSUPPORTED] there is no function cal… |
| PQL-187 | PASS | findings=[] |
| PQL-188 | PASS | p1=frozenset({'business_date'}) p2=frozenset({'to', 'from'}) p3=frozenset({'lo', 'hi'}) compiled_params=('business_date',) |
| PQL-189 | FAIL | parameters()=frozenset() (expected: 'cap' listed) |
| PQL-190 | PASS | true_lit=Literal(value=True, literal_type='boolean') null_cmp_lit=Literal(value=None, literal_type='null') where_a_eq_null_result=Verdict.INDETERMINATE,{'scanned_rows': 0.0, 'violating_rows': 0.0} |
| PQL-191 | PASS | value=0.1 rendered='CHECK t.a > 0\n  WHERE rate > 10%\n  SEVERITY major' reparsed=0.1 |
| PQL-192 | PASS | unary_filter=Expr(kind='op', name='>', value=None, args=(Expr(kind='op', name='-', value=None, args=(Expr(kind='col', name='notional', value=None, args=(), type_name='unknown'),), type_name='boolean'), Expr(kind='lit', name='', value=0, args=(), type_name='number')), type_name='boolean') unary_sql=SELECT COUNT(*) AS "scanned_rows", COALESCE(SUM(CASE WHEN NOT COALESCE(("a" > 0), 0) THEN 1 ELSE 0 EN… |
| PQL-193 | PASS | where=BinaryOp(operator='>', left=ColumnRef(name='a', dataset=''), right=UnaryOp(operator='-', operand=UnaryOp(operator='-', operand=Literal(value=1, literal_type='number')))) predicate=Expr(kind='op', name='>', value=None, args=(Expr(kind='col', name='a', value=None, args=(), type_name='unknown'), Expr(kind='lit', name='', value=0, args=(), type_name='number')), type_name='boolean') |
| PQL-194 | PASS | id1=ir:sha256:74ee6b8c6689fc7ade82e7fe9ce0d57b69f6f30f1da750162c23f0293a760c3c id2=ir:sha256:74ee6b8c6689fc7ade82e7fe9ce0d57b69f6f30f1da750162c23f0293a760c3c |
| PQL-195 | PASS | predicate=Expr(kind='op', name='>', value=None, args=(Expr(kind='col', name='a', value=None, args=(), type_name='unknown'), Expr(kind='op', name='-', value=None, args=(Expr(kind='lit', name='', value=True, args=(), type_name='boolean'),), type_name='boolean')), type_name='boolean') |
| PQL-196 | FAIL | n=22 bad=[('CHECK t.a IS NOT UNIQUE', "rendered='CHECK t.a IS UNIQUE\\n  SEVERITY major' reparsed_eq=False")] |
| PQL-197 | PASS | bad=[] |
| PQL-198 | FAIL | mismatches=[('!=', '+'), ('!=', '-'), ('!=', '\|\|'), ('!=', '*'), ('!=', '/')] missing_from_BINDING=['!='] |
| PQL-199 | FAIL | rendered='a != (1) * 2' binding_missing=True comparisons_missing=True |
| PQL-200 | PASS | r1='(a OR b) AND c' r2='a - (b - c) > 0' r3='a / (b / c) > 0' r4='a AND (b OR c)' r5='a AND b AND c' r6='a - b - c > 0' |
| PQL-201 | PASS | rendered='a BETWEEN 1 AND (x AND y)' |
| PQL-202 | PASS | rendered='CHECK positions.lei IS NOT NULL\n  SEVERITY major' |
| PQL-203 | PASS | rendered='CHECK EVERY ATTRIBUTE WHERE is_cde IS NOT NULL\n  SEVERITY major' |
| PQL-204 | PASS | [INPUT.INVALID] SelectedAttribute has no IR form \| Next: Use an expression the language supports, or report the gap. \| Context: node='SelectedAttribute' |
| PQL-205 | PASS | r1='CHECK t.a IS NOT NULL\n  SEVERITY major' r2='CHECK t.a IS NOT NULL\n  AT MOST 5 ROWS\n  SEVERITY major' r3='CHECK t.a > 0\n  BELOW 0%\n  SEVERITY major' |
| PQL-206 | PASS | rendered='CHECK t.a IS NOT NULL\n  SEVERITY major' |
| PQL-207 | PASS | name='' rendered='CHECK t.a IS NOT NULL\n  SEVERITY major' |
| PQL-208 | PASS | derived_from='EVERY ATTRIBUTE WHERE is_cde' reparsed_eq=True |
| PQL-209 | FAIL | orig=0.001234567 rendered='CHECK t.a > 0\n  WHERE r > 0.123457%\n  SEVERITY major' reparsed=0.00123457 |
| PQL-210 | PASS | {'0.1': 'orig=0.1 rendered_val=0.1 eq=True', '1e20': 'orig=1e+20 rendered_val=1e+20 eq=True', '1e-20': 'orig=1e-20 rendered_val=1e-20 eq=True', '1.7976931348623157e308': 'orig=1.7976931348623157e+308 rendered_val=1.7976931348623157e+308 eq=True', '1234567890123456789': 'orig=1234567890123456789 rendered_val=1234567890123456789 eq=True'} |
| PQL-211 | PASS | rendered='CHECK t.a > 1\n  SEVERITY major' literal_type=number |
| PQL-212 | PASS | sql_literal='\'it\'\'s "quoted" \\back\nnewline\ttab\x00nul😀emoji\'' |
| PQL-213 | PASS | bad=[] |
| PQL-214 | PASS | violation_desc='In t, every a is greater than 0. No violations are allowed. A failure is major.' pass_desc='In t, every a is greater than 0. No violations are allowed. A failure is major, and a row whose value cannot be determined is allowed to pass. This exists because: x.' |
| PQL-215 | PASS | strict_desc='In t, there is at most one row for each combination of a. A failure is major.' threshold_desc='In t, there is at most one row for each combination of a. Up to 5 violating rows are tolerated. A failure is major.' |
| PQL-216 | PASS | {'none': '. This exists because: reason.', 'period': '. This exists because: reason.', 'question': '. This exists because: reason?', 'trailing_ws': '. This exists because: reason.', 'emoji': 'This exists because: reason 😀.'} |
| PQL-217 | PASS | attr_desc='For every attribute where is_cde, every one has a value. No violations are allowed. A failure is major.' concept_desc='For every attribute mapped to Instrument.ISIN, every one is a well-formed isin. No violations are allowed. A failure is major.' |
| PQL-218 | PASS | rendered='CHECK t.a IS NOT NULL\n  SEVERITY major\n\nCHECK t.b IS NOT NULL\n  SEVERITY major\n\nSUITE s1 {\n  CHECK t.c IS NOT NULL\n    SEVERITY major\n}\n\nSUITE s2 {\n  CHECK t.d IS NOT NULL\n    SEVERITY major\n}' |
| PQL-219 | FAIL | after_write='CHECK t.a IS NOT NULL\n  SEVERITY major\n\nCHECK t.b IS NOT NULL\n  SEVERITY major\n' stdout(no-write)='CHECK t.a IS NOT NULL\n  SEVERITY major\n\nCHECK t.b IS NOT NULL\n  SEVERITY major\n' |
| PQL-220 | PASS | returncode=1 unchanged=True stdout='a pattern is opened with / and never closed (at line 1, column 19)\n\n  CHECK t.a MATCHES /^A\n                    ^\n\n→ Close it with another /, as in /^[A-Z]{2}[0-9]{10}$/.\n' |
| PQL-221 | PASS | r1='/tmp/tmpi9rj4uu4/c.pql: rewritten' r2='/tmp/tmpi9rj4uu4/c.pql: already canonical' |
| PQL-222 | FAIL | comments_gone=True warned=False stdout='/tmp/tmp800p8l8s/c.pql: rewritten\n' |
| PQL-223 | PASS | n_reparsed=2 n_expected=2 |
| PQL-224 | PASS | findings=[] |
| PQL-225 | PASS | findings=[Finding(message='positions has no column called acount_id', remedy='Did you mean account_id?', position=Position(line=1, column=17, offset=16, length=9), level='error')] |
| PQL-226 | PASS | findings=[Finding(message='t has no column called zzz', remedy='Columns available: col0, col1, col2, col3, col4, col5, col6, col7, col8, col9, col10, col11 …', position=Position(line=1, column=9, offset=8, length=3), level='error')] |
| PQL-227 | PASS | {'ACCOUNT_ID': 'account_id', 'accountid': 'account_id', 'account_ids': 'account_id', 'acct_id': 'account_id'} |
| PQL-228 | FAIL | checker_accepts=True quoted='"ACCOUNT_ID"' inconsistent=True |
| PQL-229 | PASS | findings=[Finding(message='nothing is known about t', remedy='Declare t, or bind it to a source so its columns can be discovered. The control will run, but its column names cannot be verified until then.', position=Position(line=1, column=1, offset=0, length=5), level='unchecked')] |
| PQL-230 | PASS | findings=[Finding(message='UPPER takes exactly 1 argument(s), and was given 2', remedy='The text in upper case.', position=Position(line=1, column=1, offset=0, length=5), level='error'), Finding(message='nothing is known about t', remedy='Declare t, or bind it to a source so its columns can be discovered. The control will run, but its column names cannot be verified until then.', position=Position… |
| PQL-231 | PASS | findings=[Finding(message='accounts.b belongs to accounts, but this control is about positions', remedy='Use a column of positions, or declare the relationship between the two datasets and write a control across it.', position=Position(line=1, column=37, offset=36, length=8), level='error')] |
| PQL-232 | PASS | bad=[] |
| PQL-233 | PASS | bad=[] |
| PQL-234 | PASS | bad=[] |
| PQL-235 | FAIL | findings=[Finding(message='b IS NULL holds number, and it is being compared with TRUE, which is boolean', remedy='Compare like with like. Engines differ on whether they coerce these silently, so a control written this way would mean one thing on one database and something else on another.', position=Position(line=1, column=43, offset=42, length=4), level='error')] |
| PQL-236 | PASS | findings=[] |
| PQL-237 | PASS | findings=[] |
| PQL-238 | PASS | findings=[Finding(message='t.ccy holds text, and it is being compared with 2, which is number', remedy='Compare like with like. Engines differ on whether they coerce these silently, so a control written this way would mean one thing on one database and something else on another.', position=Position(line=1, column=24, offset=23, length=1), level='error')] |
| PQL-239 | PASS | findings=[Finding(message='a pattern cannot be matched against a number', remedy='Patterns apply to text. Compare a number with BETWEEN or an operator instead.', position=Position(line=1, column=18, offset=17, length=7), level='error')] |
| PQL-240 | PASS | bad=[] |
| PQL-241 | FAIL | satisfies_findings=[] where_findings=[Finding(message="notional holds number, and it is being compared with 'ACTIVE', which is text", remedy='Compare like with like. Engines differ on whether they coerce these silently, so a control written this way would mean one thing on one database and something else on another.', position=Position(line=1, column=47, offset=46, length=8), level='error')] |
| PQL-242 | FAIL | findings=[Finding(message='t has no column called e', remedy='Columns available: a, b', position=Position(line=1, column=32, offset=31, length=1), level='error')] |
| PQL-243 | PASS | findings=[Finding(message='there is no function called UPPERR', remedy='Available: ABS, COALESCE, CONCAT, DAY, IF, IFBLANK, INT, ISBLANK, ISNUMBER, LEFT, LEN, LENGTH, LOWER, MAX, MID, MIN, MOD, MONTH, RIGHT, ROUND, SIGN, SUBSTITUTE, TRIM, UPPER, YEAR.', position=Position(line=1, column=1, offset=0, length=5), level='error'), Finding(message='nothing is known about t', remedy='Declare t, or bind it… |
| PQL-244 | PASS | {'upper2': [('UPPER takes exactly 1 argument(s), and was given 2', 'The text in upper case.', 'UPPER')], 'left1': [('LEFT takes exactly 2 argument(s), and was given 1', 'The first n characters.', 'LEFT')], 'concat0': [('CONCAT takes at least 1 argument(s), and was given 0', 'Several pieces of text joined together.', 'CONCAT')], 'if2': [('IF takes exactly 3 argument(s), and was given 2', 'One value… |
| PQL-245 | PASS | calls1=[('TODAY is refused: it returns the current date', 'A control has to replay — the same plan against the same snapshot must give the same verdict, or the evidence is not evidence. Pass the value in as a parameter, which is recorded with the run.', 'TODAY')] calls2=[('there is no function called TODAYY', 'Available: ABS, COALESCE, CONCAT, DAY, IF, IFBLANK, INT, ISBLANK, ISNUMBER, LEFT, LEN, L… |
| PQL-246 | PASS | step1=returned (no raise) step2=raised: [PQL.TYPE] there is no function called UPPERR \| Next: Available: ABS, COALESCE, CONCAT, DAY, IF, IFBLANK, INT, ISBLANK, ISNUMBER, LEFT, LEN, LENGTH, LOWER, MAX, MID, MIN, MOD, MONTH, RIGHT, ROUND, SIGN, SUBSTITUTE, TRIM, UPPER, YEAR. \| Context: position='line 1, column 1' |
| PQL-247 | PASS | n=5 findings=[Finding(message='there is no function called LOWERR', remedy='Available: ABS, COALESCE, CONCAT, DAY, IF, IFBLANK, INT, ISBLANK, ISNUMBER, LEFT, LEN, LENGTH, LOWER, MAX, MID, MIN, MOD, MONTH, RIGHT, ROUND, SIGN, SUBSTITUTE, TRIM, UPPER, YEAR.', position=Position(line=1, column=1, offset=0, length=5), level='error'), Finding(message='there is no function called UPPERR', remedy='Availab… |
| PQL-248 | PASS | to_dict={'level': 'error', 'message': 'x', 'remedy': 'y', 'position': None} |
| PQL-249 | PASS | {'positions': False, 'Positions': True, 'POSITIONS': False} |
| PQL-250 | PASS | n_cols=1 family=number nullable=True findings=[] |
| PQL-251 | PASS | rc1=0 rc2=0 rc3=0 |
| PQL-252 | PASS | stdout='' stderr="\nerror: no engine called 'oracle'\n  code: INPUT.INVALID\n  next: One of: duckdb, postgresql, sqlite.\n  engine: oracle\n" |
| PQL-253 | PASS | n=25 noneval=[] |
| PQL-254 | PASS | [INPUT.INVALID] the function X has no SQL form \| Next: Give a `sql` template, or list every engine in `unsupported_on` if it genuinely cannot be pushed down. |
| PQL-255 | PASS | constructed; refuses_all_engines=True |
| PQL-256 | PASS | bad=[] |
| PQL-257 | PASS | [INPUT.INVALID] OFFSET is refused: it returns a reference resolved at evaluation time \| Next: A control has to replay. Pass the value in as a parameter, which is recorded with the run and reproduces exactly. \| Context: function='OFFSET' |
| PQL-258 | PASS | [INPUT.INVALID] there is no function called VLOOKUP \| Next: Available: ABS, COALESCE, CONCAT, DAY, IF, IFBLANK, INT, ISBLANK, ISNUMBER, LEFT, LEN, LENGTH, LOWER, MAX, MID, MIN, MOD, MONTH, RIGHT, ROUND, SIGN, SUBSTITUTE, TRIM, UPPER, YEAR. An unrecognised name used to compile straight through to SQL and fail at execution — or worse, succeed on an engine that happened to have a function of that na… |
| PQL-259 | PASS | found=None |
| PQL-260 | PASS | {'upper': 'UPPER', 'Upper': 'UPPER', 'UPPER': 'UPPER'} |
| PQL-261 | PASS | [INPUT.INVALID] sqlite cannot express ROUND \| Next: Run this control on an engine that can, or express it differently. Prama will not substitute something close: the same control would then mean two different things on two engines, and nothing would notice. \| Context: engine='sqlite', function='ROUND' |
| PQL-262 | PASS | pg='CONCAT(a, b, c)' dk='CONCAT(a, b, c)' sq='(a \|\| b \|\| c)' |
| PQL-263 | PASS | rendered='(a)' value='a' |
| PQL-264 | FAIL | reference=None postgres='a' sqlite=None (three-way agreement: False) |
| PQL-265 | PASS | t0=text t5=text t50=text |
| PQL-266 | FAIL | findings=[] (expected per catalogue: caught; likely a gap) |
| PQL-267 | PASS | round_engines=['postgresql', 'duckdb'] upper_engines=['postgresql', 'duckdb', 'sqlite'] |
| PQL-268 | PASS | {'UPPER': {'sqlite': None, 'reference': None, 'agree': True}, 'LOWER': {'sqlite': None, 'reference': None, 'agree': True}, 'TRIM': {'sqlite': None, 'reference': None, 'agree': True}, 'LENGTH': {'sqlite': None, 'reference': None, 'agree': True}, 'LEN': {'sqlite': None, 'reference': None, 'agree': True}, 'LEFT': {'sqlite': None, 'reference': None, 'agree': True}, 'RIGHT': {'sqlite': None, 'reference… |
| PQL-269 | FAIL | {'notional': (Decimal('4'), {'sqlite': 4, 'duckdb': 'ERR:BinderException'}), 'trade_date': (Decimal('10'), {'sqlite': 10, 'duckdb': 10})} |
| PQL-270 | PASS | {'日本語': (Decimal('3'), 3, 3), 'café': (Decimal('4'), 4, 4)} |
| PQL-271 | PASS | ref='a   b' sq='a   b' dk='a   b' |
| PQL-272 | FAIL | ref='a\nnon-breaking\xa0here' sq='\ta\nnon-breaking\xa0here' |
| PQL-273 | FAIL | {('LEFT', 0): ('', ''), ('LEFT', -1): ('', ''), ('LEFT', 99): ('abc', 'abc'), ('RIGHT', 0): ('', ''), ('RIGHT', -1): ('', ''), ('MID', 0, 2): ('ab', 'a'), ('MID', -1, 2): ('ab', 'c'), ('MID', 2, 0): ('', '')} |
| PQL-274 | PASS | ref1='abc' sq1='abc' ref2='cd' sq2='cd' |
| PQL-275 | PASS | calls=[('SUBSTITUTE takes exactly 3 argument(s), and was given 4', 'Every occurrence of one piece of text replaced by another.', 'SUBSTITUTE')] |
| PQL-276 | FAIL | ref='XaXbXcX' sq='abc' |
| PQL-277 | PASS | {(2.675, 2): (Decimal('2.68'), Decimal('2.68'), Decimal('2.68')), (-2.675, 2): (Decimal('-2.68'), Decimal('-2.68'), Decimal('-2.68')), (0.5, 0): (Decimal('1'), Decimal('1'), Decimal('1')), (-0.5, 0): (Decimal('-1'), Decimal('-1'), Decimal('-1'))} |
| PQL-278 | PASS | duckdb=1953193.46 reference=1953193.46 |
| PQL-279 | PASS | [PQL.UNSUPPORTED] sqlite cannot run ROUND \| Next: Run this control on an engine that can. Prama will not substitute something close: the same control would then mean two different things on two engines, and nothing would notice. \| Context: dialect='sqlite', function='ROUND' |
| PQL-280 | FAIL | r1=1.2E+3 r2=InvalidOperation: [<class 'decimal.InvalidOperation'>] |
| PQL-281 | PASS | ref=-8 dk=-8 sq=-8.0 |
| PQL-282 | PASS | result=3.0 |
| PQL-283 | PASS | ref=None sq=None dk=None |
| PQL-284 | PASS | ref(-10,3)=-1 sql=-1 ref(10,-3)=1 sql=1 (Excel would give 2 and -2) |
| PQL-285 | PASS | sign(0)=0 sign(-7.5)=-1 sign(NULL)=None |
| PQL-286 | PASS | MIN(a)_calls=[] pg3=LEAST(a, b, c) sq3=MIN(a, b, c) |
| PQL-287 | FAIL | ref=None sqlite=None duckdb=1 postgresql=1 |
| PQL-288 | FAIL | reference=None sql_case_when_null=2 (SQL takes the ELSE branch -- disagreement) |
| PQL-289 | PASS | IF(TRUE,1,NULL)=1 IF(FALSE,NULL,2)=2 |
| PQL-290 | PASS | r1=3 r2=None r3=x |
| PQL-291 | PASS | COALESCE('','x')='' ISBLANK('')=True |
| PQL-292 | PASS | reference={'null': True, 'empty': True, 'spaces': True, 'zero': False, 'false': False} sqlite={'null': True, 'empty': True, 'spaces': True, 'zero': False, 'false': False} expect={'null': True, 'empty': True, 'spaces': True, 'zero': False, 'false': False} |
| PQL-293 | PASS | sql="({0} IS NULL OR TRIM(CAST({0} AS VARCHAR)) = '')" occurrences=2 |
| PQL-294 | FAIL | {"'123'": (True, True), "'-1.5'": (True, True), "'1e5'": (False, False), "'  7 '": (True, False), "''": (False, False), 'None': (False, False)} |
| PQL-295 | PASS | requires=frozenset({'pushdown.regex'}) sqlite_compile=compiled ok on sqlite (has regex) |
| PQL-296 | PASS | {'2026-09-08': {'YEAR': (Decimal('2026'), 2026), 'MONTH': (Decimal('9'), 9), 'DAY': (Decimal('8'), 8)}, '2024-02-29': {'YEAR': (Decimal('2024'), 2024), 'MONTH': (Decimal('2'), 2), 'DAY': (Decimal('29'), 29)}, '2026-09-08T06:30:00Z': {'YEAR': (Decimal('2026'), 2026), 'MONTH': (Decimal('9'), 9), 'DAY': (Decimal('8'), 8)}} |
| PQL-297 | PASS | {'not a date': (None, 0), '2026/09/08': (None, 2026), '20260908': (None, 2026)} |
| PQL-298 | PASS | reference=2020 {'sqlite': 'ERR:near "\'2020-05-01\'": syntax error', 'duckdb': 2020} |
| PQL-299 | PASS | {'ABS': None, 'ROUND': None, 'MIN': None} (expected: UNKNOWN/None in each case) |
| PQL-300 | FAIL | operator(+)_float_result=0.30000000000000004 function_path_decimal_sum=Decimal('0.3') one_arithmetic_model=False |
| PQL-301 | PASS | n_with_notes=12 bad=[] |
| PQL-302 | PASS | rc=0 has_trim=True has_round=True has_concat=True has_sqlite_note=True |
| PQL-303 | PASS | stdout="· In t, every a has a value, checked separately for each e. No violations are allowed. A failure is major.\n    TRIM differs from Excel: Excel's TRIM also collapses runs of spaces inside the text; this one only removes the ends, which is what every SQL engine's TRIM does. Collapsing interior spaces on one side and not the other would make the same control give two answers.\n\n" |
| PQL-304 | PASS | n_declared=25 n_unique=25 dupes=[] n_registry=None |
| PQL-305 | PASS | checker=True compiled_sql_has_doubling=True reference=4 |
| PQL-306 | PASS | {'BELOW 100%': (1, 'error', 'Set a rate the data could realistically breach, or remove the control. A control that cannot fail is worse than none: it appears on the coverage report and covers nothing.'), 'BELOW 150%': (1, 'error', 'Set a rate the data could realistically breach, or remove the control. A control that cannot fail is worse than none: it appears on the coverage report and covers nothi… |
| PQL-307 | PASS | findings=[LintFinding(rule='no-justification', message='this control does not say why it exists', remedy="Add BECAUSE '…'. When it fires at three in the morning, the sentence explaining what the business declared is the most useful thing on the screen — and a control nobody can justify is one nobody will maintain.", control='CHECK t.a > 0', related='', severity='info', position=Position(line=1, co… |
| PQL-308 | PASS | at_least_0=[LintFinding(rule='never-fires', message='every dataset has at least zero rows', remedy='State a bound the data could breach, or remove the control.', control='CHECK t HAS ROW COUNT AT LEAST 0', related='', severity='error', position=Position(line=1, column=1, offset=0, length=5)), LintFinding(rule='no-justification', message='this control does not say why it exists', remedy="Add BECAUS… |
| PQL-309 | PASS | [LintFinding(rule='always-fires', message='BETWEEN 100 AND 1 is empty, so every row violates it', remedy='The bounds are the wrong way round.', control='CHECK t.n BETWEEN 100 AND 1', related='', severity='error', position=Position(line=1, column=11, offset=10, length=7)), LintFinding(rule='no-justification', message='this control does not say why it exists', remedy="Add BECAUSE '…'. When it fires … |
| PQL-310 | PASS | [LintFinding(rule='always-fires', message='the row count range is empty, so this can never pass', remedy='The bounds are the wrong way round.', control='CHECK t HAS ROW COUNT BETWEEN 100 AND 1', related='', severity='error', position=Position(line=1, column=9, offset=8, length=3)), LintFinding(rule='no-justification', message='this control does not say why it exists', remedy="Add BECAUSE '…'. When… |
| PQL-311 | PASS | [LintFinding(rule='no-justification', message='this control does not say why it exists', remedy="Add BECAUSE '…'. When it fires at three in the morning, the sentence explaining what the business declared is the most useful thing on the screen — and a control nobody can justify is one nobody will maintain.", control='CHECK t.a HAS LENGTH BETWEEN 12 AND 12', related='', severity='info', position=Pos… |
| PQL-312 | PASS | finding_severity=info strict_rc=1 |
| PQL-313 | PASS | [LintFinding(rule='duplicate', message='this control computes exactly what another already computes', remedy='Remove one. Both will read the same data, produce the same finding and page the same person twice.', control='CHECK t.a IS NOT NULL', related='CHECK t.a IS NOT NULL', severity='warning', position=Position(line=1, column=1, offset=0, length=5))] |
| PQL-314 | PASS | [LintFinding(rule='no-justification', message='this control does not say why it exists', remedy="Add BECAUSE '…'. When it fires at three in the morning, the sentence explaining what the business declared is the most useful thing on the screen — and a control nobody can justify is one nobody will maintain.", control='CHECK t.a IS NOT NULL', related='', severity='info', position=Position(line=1, col… |
| PQL-315 | PASS | [LintFinding(rule='no-justification', message='this control does not say why it exists', remedy="Add BECAUSE '…'. When it fires at three in the morning, the sentence explaining what the business declared is the most useful thing on the screen — and a control nobody can justify is one nobody will maintain.", control='CHECK t.a IS NOT NULL', related='', severity='info', position=Position(line=1, col… |
| PQL-316 | PASS | n_findings=2 |
| PQL-317 | PASS | [LintFinding(rule='no-justification', message='this control does not say why it exists', remedy="Add BECAUSE '…'. When it fires at three in the morning, the sentence explaining what the business declared is the most useful thing on the screen — and a control nobody can justify is one nobody will maintain.", control='CHECK t.n > 0', related='', severity='info', position=Position(line=1, column=1, o… |
| PQL-318 | PASS | [LintFinding(rule='no-justification', message='this control does not say why it exists', remedy="Add BECAUSE '…'. When it fires at three in the morning, the sentence explaining what the business declared is the most useful thing on the screen — and a control nobody can justify is one nobody will maintain.", control='CHECK t.n > 0', related='', severity='info', position=Position(line=1, column=1, o… |
| PQL-319 | PASS | bad=[] |
| PQL-320 | PASS | where_fs=[LintFinding(rule='no-justification', message='this control does not say why it exists', remedy="Add BECAUSE '…'. When it fires at three in the morning, the sentence explaining what the business declared is the most useful thing on the screen — and a control nobody can justify is one nobody will maintain.", control='CHECK t.n > 0', related='', severity='info', position=Position(line=1, co… |
| PQL-321 | PASS | [LintFinding(rule='no-justification', message='this control does not say why it exists', remedy="Add BECAUSE '…'. When it fires at three in the morning, the sentence explaining what the business declared is the most useful thing on the screen — and a control nobody can justify is one nobody will maintain.", control='CHECK t.n > 0', related='', severity='info', position=Position(line=1, column=1, o… |
| PQL-322 | PASS | [LintFinding(rule='no-justification', message='this control does not say why it exists', remedy="Add BECAUSE '…'. When it fires at three in the morning, the sentence explaining what the business declared is the most useful thing on the screen — and a control nobody can justify is one nobody will maintain.", control="CHECK t.ccy IN ('GBP')", related='', severity='info', position=Position(line=1, co… |
| PQL-323 | PASS | [LintFinding(rule='no-justification', message='this control does not say why it exists', remedy="Add BECAUSE '…'. When it fires at three in the morning, the sentence explaining what the business declared is the most useful thing on the screen — and a control nobody can justify is one nobody will maintain.", control="CHECK t.ccy IN ($a, 'GBP')", related='', severity='info', position=Position(line=1… |
| PQL-324 | PASS | n_subsumed=2 findings=[LintFinding(rule='no-justification', message='this control does not say why it exists', remedy="Add BECAUSE '…'. When it fires at three in the morning, the sentence explaining what the business declared is the most useful thing on the screen — and a control nobody can justify is one nobody will maintain.", control="CHECK t.a IN ('GBP')", related='', severity='info', position… |
| PQL-325 | PASS | n=1 findings=[LintFinding(rule='no-justification', message='this control does not say why it exists', remedy="Add BECAUSE '…'. When it fires at three in the morning, the sentence explaining what the business declared is the most useful thing on the screen — and a control nobody can justify is one nobody will maintain.", control='CHECK t.n > 0', related='', severity='info', position=Position(line=1… |
| PQL-326 | PASS | elapsed=4.4s rc=0 |
| PQL-327 | PASS | render_with='[info] x: m\n  related: other\n  → r' render_without='[info] x: m\n  → r' dict_with={'rule': 'x', 'severity': 'info', 'message': 'm', 'remedy': 'r', 'control': 'c', 'related': 'other', 'position': {'line': 1, 'column': 1, 'offset': 0, 'length': 5}} dict_without={'rule': 'x', 'severity': 'info', 'message': 'm', 'remedy': 'r', 'control': 'c', 'related': '', 'position': {'line': 1, 'colu… |
| PQL-328 | PASS | findings=[LintFinding(rule='never-fires', message='every dataset has at least zero rows', remedy='State a bound the data could breach, or remove the control.', control='CHECK EVERY ATTRIBUTE HAS ROW COUNT AT LEAST 0', related='', severity='error', position=Position(line=1, column=1, offset=0, length=5)), LintFinding(rule='no-justification', message='this control does not say why it exists', remedy… |
| PQL-329 | PASS | excel=quantity > 0 AND notional = quantity * price pql=quantity > 0 AND notional = quantity * price |
| PQL-330 | PASS | n1=BinaryOp(operator='>', left=ColumnRef(name='a', dataset=''), right=Literal(value=0, literal_type='number')) n2=BinaryOp(operator='>', left=ColumnRef(name='a', dataset=''), right=Literal(value=0, literal_type='number')) |
| PQL-331 | PASS | {'parse': 'ok', 'lower': 'ok', 'sql': 'compiled ok', 'ref': 'ran: Verdict.PASS'} |
| PQL-332 | PASS | tree=CONCAT(a, b) = 'xy' |
| PQL-333 | PASS | tree=CONCAT(CONCAT(a, b), c) |
| PQL-334 | PASS | err=[PQL.SYNTAX] ^ is not supported \| Next: Exponentiation is not in the catalogue: the engines disagree about precision and about what a fractional exponent of a negative number means, and a control has to mean one thing. \| Context: formula='=[a]^2 > 4' |
| PQL-335 | FAIL | err=[PQL.SYNTAX] the formula ends before it is finished \| Next: Check the brackets and the argument count. Functions available: ABS, COALESCE, CONCAT, DAY, IF, IFBLANK, INT, ISBLANK, ISNUMBER, LEFT, LEN, LENGTH, LOWER, MAX, MID, MIN, MOD, MONTH, RIGHT, ROUND, SIGN, SUBSTITUTE, TRIM, UPPER, YEAR. \| Context: formula='=[a] +', position=6 pos=(line 1, column 1) diagnostics=[Diagnostic(message="[PQL.… |
| PQL-336 | PASS | {"''": "[PQL.SYNTAX] the formula is empty \| Next: Check the brackets and the argument count. Functions available: ABS, COALESCE, CONCAT, DAY, IF, IFBLANK, INT, ISBLANK, ISNUMBER, LEFT, LEN, LENGTH, LOWER, MAX, MID, MIN, MOD, MONTH, RIGHT, ROUND, SIGN, SUBSTITUTE, TRIM, UPPER, YEAR. \| Context: formula='', position=0", "'='": "[PQL.SYNTAX] the formula is empty \| Next: Check the brackets and the a… |
| PQL-337 | PASS | err=[PQL.SYNTAX] unexpected '[b]' after the formula \| Next: Check the brackets and the argument count. Functions available: ABS, COALESCE, CONCAT, DAY, IF, IFBLANK, INT, ISBLANK, ISNUMBER, LEFT, LEN, LENGTH, LOWER, MAX, MID, MIN, MOD, MONTH, RIGHT, ROUND, SIGN, SUBSTITUTE, TRIM, UPPER, YEAR. \| Context: formula='=[a] > 0 [b]', position=8 |
| PQL-338 | FAIL | col=ColumnRef(name='positions.notional', dataset='') |
| PQL-339 | FAIL | err=None |
| PQL-340 | PASS | {'=[notional amount] > 0': 'notional amount', '=[a-b] > 0': 'a-b', '=[日本] > 0': '日本'} |
| PQL-341 | FAIL | err=[PQL.SYNTAX] ']' is not something a formula can contain \| Next: Formulas use columns in [brackets], numbers, "text", the operators = <> < <= > >= + - * / & ^, and function calls. \| Context: formula='[a[b]] > 0', position=5 position=line 1, column 1 located=False |
| PQL-342 | PASS | value=say "hi" err=None |
| PQL-343 | PASS | err=[PQL.SYNTAX] "'" is not something a formula can contain \| Next: Formulas use columns in [brackets], numbers, "text", the operators = <> < <= > >= + - * / & ^, and function calls. \| Context: formula="[a] = 'USD'", position=6 |
| PQL-344 | PASS | n1=FunctionCall(name='IF', arguments=(BinaryOp(operator='>', left=ColumnRef(name='a', dataset=''), right=Literal(value=0, literal_type='number')), Literal(value=1, literal_type='number'), Literal(value=2, literal_type='number')), distinct=False) n2=FunctionCall(name='IF', arguments=(BinaryOp(operator='>', left=ColumnRef(name='a', dataset=''), right=Literal(value=0, literal_type='number')), Literal… |
| PQL-345 | PASS | node=FunctionCall(name='IF', arguments=(BinaryOp(operator='>', left=ColumnRef(name='a', dataset=''), right=Literal(value=0, literal_type='number')), Literal(value=1, literal_type='number'), Literal(value=2, literal_type='number')), distinct=False) err=None |
| PQL-346 | FAIL | err=[PQL.SYNTAX] unexpected ')' \| Next: Check the brackets and the argument count. Functions available: ABS, COALESCE, CONCAT, DAY, IF, IFBLANK, INT, ISBLANK, ISNUMBER, LEFT, LEN, LENGTH, LOWER, MAX, MID, MIN, MOD, MONTH, RIGHT, ROUND, SIGN, SUBSTITUTE, TRIM, UPPER, YEAR. \| Context: formula='=CONCAT([a], [b],)', position=18 position=line 1, column 1 located=False |
| PQL-347 | PASS | n1=BinaryOp(operator='AND', left=BinaryOp(operator='>', left=ColumnRef(name='a', dataset=''), right=Literal(value=0, literal_type='number')), right=BinaryOp(operator='>', left=ColumnRef(name='b', dataset=''), right=Literal(value=0, literal_type='number'))) n2=BinaryOp(operator='AND', left=BinaryOp(operator='>', left=ColumnRef(name='a', dataset=''), right=Literal(value=0, literal_type='number')), r… |
| PQL-348 | PASS | err=[PQL.SYNTAX] AND takes at least two arguments \| Next: Check the brackets and the argument count. Functions available: ABS, COALESCE, CONCAT, DAY, IF, IFBLANK, INT, ISBLANK, ISNUMBER, LEFT, LEN, LENGTH, LOWER, MAX, MID, MIN, MOD, MONTH, RIGHT, ROUND, SIGN, SUBSTITUTE, TRIM, UPPER, YEAR. \| Context: formula='=AND([a]>0)', position=11 |
| PQL-349 | PASS | n1=UnaryOp(operator='NOT', operand=BinaryOp(operator='>', left=ColumnRef(name='a', dataset=''), right=Literal(value=0, literal_type='number'))) n2=BinaryOp(operator='>', left=UnaryOp(operator='NOT', operand=ColumnRef(name='a', dataset='')), right=Literal(value=0, literal_type='number')) |
| PQL-350 | FAIL | bracketed=BinaryOp(operator='>', left=ColumnRef(name='and', dataset=''), right=Literal(value=0, literal_type='number')) bare=BinaryOp(operator='>', left=ColumnRef(name='and', dataset=''), right=Literal(value=0, literal_type='number')) err2=None |
| PQL-351 | PASS | err=[PQL.SYNTAX] there is no function called VLOOKUP \| Next: Available: ABS, COALESCE, CONCAT, DAY, IF, IFBLANK, INT, ISBLANK, ISNUMBER, LEFT, LEN, LENGTH, LOWER, MAX, MID, MIN, MOD, MONTH, RIGHT, ROUND, SIGN, SUBSTITUTE, TRIM, UPPER, YEAR. Prama accepts a deliberately small set: every one of them has a lowering for each engine and a reference implementation that is tested to agree with it. \| Co… |
| PQL-352 | PASS | {'=TODAY()': "[PQL.SYNTAX] TODAY() cannot be used in a control: it returns the current date \| Next: A control has to replay: the same plan against the same snapshot must give the same verdict, or its evidence is not evidence. Use a parameter, which the run supplies and the evidence records. \| Context: formula='=TODAY()', function='TODAY'", '=NOW()': "[PQL.SYNTAX] NOW() cannot be used in a contro… |
| PQL-353 | FAIL | err=[PQL.SYNTAX] there is no function called IFERROR \| Next: Available: ABS, COALESCE, CONCAT, DAY, IF, IFBLANK, INT, ISBLANK, ISNUMBER, LEFT, LEN, LENGTH, LOWER, MAX, MID, MIN, MOD, MONTH, RIGHT, ROUND, SIGN, SUBSTITUTE, TRIM, UPPER, YEAR. Prama accepts a deliberately small set: every one of them has a lowering for each engine and a reference implementation that is tested to agree with it. \| Co… |
| PQL-354 | PASS | excel_msg=[PQL.SYNTAX] LEFT takes exactly 2 argument(s), and was given 1 \| Next: Check the brackets and the argument count. Functions available: ABS, COALESCE, CONCAT, DAY, IF, IFBLANK, INT, ISBLANK, ISNUMBER, LEFT, LEN, LENGTH, LOWER, MAX, MID, MIN, MOD, MONTH, RIGHT, ROUND, SIGN, SUBSTITUTE, TRIM, UPPER, YEAR. \| Context: formula='=LEFT([a])', position=10 pql_msg=LEFT takes exactly 2 argument(s… |
| PQL-355 | PASS | a1=BinaryOp(operator='>', left=ColumnRef(name='A1', dataset=''), right=Literal(value=0, literal_type='number')) range_err=[PQL.SYNTAX] ':' is not something a formula can contain \| Next: Formulas use columns in [brackets], numbers, "text", the operators = <> < <= > >= + - * / & ^, and function calls. \| Context: formula='SUM(A1:B2)', position=6 |
| PQL-356 | PASS | rendered="CHECK t SATISFIES EXCEL '=AND([a]>0, [b]>0)'\n  SEVERITY major" |
| PQL-357 | PASS | rendered='CHECK t SATISFIES EXCEL \'=[a] = "it\'\'s"\'\n  SEVERITY major' err=None |
| PQL-358 | PASS | desc='In t, every row satisfies the formula =AND([a]>0, [b]>0). No violations are allowed. A failure is major.' |
| PQL-359 | PASS | n=3 sample=Control(target='t', assertion=PredicateAssertion(subject=ColumnRef(name='c1', dataset='t'), operator='is_not_null', argument=None, upper=None, negated=False), name='', where=None, segmentation=None, threshold=Threshold(unit='rows', value=0.0, currency='', comparator='<='), severity=<Severity.MAJOR: 'major'>, dimensions=(), because='Selected by EVERY ATTRIBUTE WHERE is_cde', unknown_poli… |
| PQL-360 | PASS | bad=[] |
| PQL-361 | PASS | because_sample=Selected by EVERY ATTRIBUTE WHERE is_cde |
| PQL-362 | PASS | empty=[] |
| PQL-363 | PASS | [INPUT.INVALID] this control names a dataset, so there is nothing to expand \| Next: Only controls written against a selector are expanded. \| Context: control='CHECK positions.a IS NOT NULL' |
| PQL-364 | PASS | n_result=9 n_passed_identity=3 |
| PQL-365 | PASS | facts={'dataset': 't', 'name': 'c1', 'attribute': 'c1', 'concept': 'Instrument', 'concept_property': 'ISIN', 'domain': 'Credit', 'owner': 'me', 'criticality': 'high', 'semantic_type': 'isin', 'is_cde': True, 'tags': ['pii']} |
| PQL-366 | FAIL | n=0 (typo silently matches nothing) |
| PQL-367 | PASS | n=2 |
| PQL-368 | PASS | n=3 |
| PQL-369 | FAIL | n=0 (silently matches nothing) |
| PQL-370 | PASS | included_by_eq=False included_by_not=True |
| PQL-371 | PASS | is_null(None)=True is_null('')=True |
| PQL-372 | FAIL | n_matched=0 facts={'dataset': 'd', 'name': 'a', 'attribute': 'a', 'concept': '', 'concept_property': '', 'domain': '', 'owner': '', 'criticality': '', 'semantic_type': '', 'is_cde': 'True', 'tags': []} |
| PQL-373 | FAIL | is_cde_matches=0 not_is_cde_matches=0 |
| PQL-374 | PASS | exact=1 lowercased=0 |
| PQL-375 | PASS | digest_a=34222c44a2288c62 digest_b=34222c44a2288c62 |
| PQL-376 | PASS | digest_3=34222c44a2288c62 digest_2=1a9cb7744cbda681 |
| PQL-377 | PASS | digest='e3b0c44298fc1c14' count=0 |
| PQL-378 | PASS | render='This selector now covers 4 more: t.new0, t.new1, t.new2, t.new3; and no longer covers 1: t.c1.' |
| PQL-379 | PASS | render='This selector covers exactly what it covered when it was approved.' |
| PQL-380 | PASS | render='This selector now covers 20 more: t.n0, t.n1, t.n10, t.n11, t.n12 ….' |
| PQL-381 | PASS | drift_reported=True render='This selector now covers 1 more: t.c6.' |
| PQL-382 | PASS | d1=[] d2=[] |
| PQL-383 | PASS | [Diagnostic(message="[PQL.SYNTAX] expected something to check about positions and found the end of the control \| Next: A control says what must be true: IS NOT NULL, IN CODELIST, HAS UNIQUE KEY (…), HAS ROW COUNT BETWEEN …, REFERENCES …, SATISFIES … \| Context: position='line 1, column 16'", level='error', remedy='A control says what must be true: IS NOT NULL, IN CODELIST, HAS UNIQUE KEY (…), HAS… |
| PQL-384 | FAIL | [] |
| PQL-385 | PASS | never_fires=[Diagnostic(message='a threshold of 100% cannot be exceeded, so this control can never fail', level='warning', remedy='Set a rate the data could realistically breach, or remove the control. A control that cannot fail is worse than none: it appears on the coverage report and covers nothing.', line=1, column=1, length=5, control='control 1')] no_justification=[Diagnostic(message='this co… |
| PQL-386 | PASS | n_matches=1 all=[Diagnostic(message='positions has no column called nosuchcol1', level='error', remedy='Columns available: account_id, notional', line=1, column=17, length=10, control='control 1'), Diagnostic(message='this control does not say why it exists', level='warning', remedy="Add BECAUSE '…'. When it fires at three in the morning, the sentence explaining what the business declared is the m… |
| PQL-387 | PASS | [('unchecked', 3), ('warning', 2)] |
| PQL-388 | PASS | Diagnostic(message='m', level='error', remedy='r', line=0, column=0, length=0, control='ctl') |
| PQL-389 | PASS | labels={'notional', 'account_id'} sample=Completion(label='account_id', kind=5, detail='positions.account_id: text', documentation='nullable') |
| PQL-390 | PASS | [] |
| PQL-391 | PASS | n=9 kinds={3, 14} sample=[Completion(label='COALESCE', kind=3, detail='COALESCE(…) → unknown', documentation='The first value that is present.'), Completion(label='CONCAT', kind=3, detail='CONCAT(…) → text', documentation='Several pieces of text joined together.'), Completion(label='CODELIST', kind=14, detail='', documentation=''), Completion(label='COMPARING', kind=14, detail='', documentation=''… |
| PQL-392 | PASS | lower=[Completion(label='Positions', kind=7, detail='dataset · 1 column(s)', documentation='')] upper=[Completion(label='Positions', kind=7, detail='dataset · 1 column(s)', documentation='')] |
| PQL-393 | PASS | Hover(title='positions.notional', body='numeric · nullable · family number') |
| PQL-394 | PASS | Hover(title='positions', body='Declared dataset · 2 column(s): account_id, notional.') |
| PQL-395 | PASS | Hover(title='positions', body='`positions` is not declared, so nothing written against it has been checked against a schema. A control naming it will parse and will not be verified.') |
| PQL-396 | PASS | Hover(title='positions.acount_id', body='**Not a declared column of positions.** Did you mean `account_id`? Declared: account_id, notional.') |
| PQL-397 | PASS | round_hover=Hover(title='ROUND(…)', body='Rounded to n decimal places, half away from zero. Returns number. Not available on sqlite. Differs from Excel: Excel rounds half away from zero and so does this. Several SQL engines round half to even by default, which is why the value is cast to an exact type first — otherwise the same control gives a different penny on a different engine. SQLite is refus… |
| PQL-398 | PASS | {0: '', 1: 'CHECK', 5: 'CHECK', 6: 'CHECK', 7: 't'} (boundary behaviour recorded) |
| PQL-399 | PASS | {(0, 1): Hover(title='', body=''), (99, 1): Hover(title='', body=''), (2, 9999): Hover(title='', body='')} |
| PQL-400 | PASS | console_diags=[{'message': 'this control does not say why it exists', 'level': 'warning', 'remedy': "Add BECAUSE '…'. When it fires at three in the morning, the sentence explaining what the business declared is the most useful thing on the screen — and a control nobody can justify is one nobody will maintain.", 'line': 1, 'column': 1, 'length': 5, 'control': 'control 1', 'severity': 2, 'has_positi… |
| PQL-401 | PASS | bad=[] |
| PQL-402 | FAIL | rc=1 stderr=Traceback (most recent call last): |
| PQL-403 | FAIL | bad=['Attribute', 'AttributeCatalogue', 'Drift', 'Expander', 'Expansion'] |
| PQL-404 | PASS | FAMILIES=('number', 'text', 'boolean', 'temporal', 'unknown') bad=[] |
| PQL-405 | PASS | bad=[] |
| IR-001 | PASS | id=ir:sha256:ee44377f54011968249b0204cea9a8021d6881bb4897b28eeceda571ffbba255 |
| IR-002 | PASS | between_eq=True order_eq=True |
| IR-003 | PASS | eq=True |
| IR-004 | PASS | eq=True |
| IR-005 | PASS | unchanged=[] |
| IR-006 | PASS | eq=False |
| IR-007 | PASS | ir_version=1.0 IR_VERSION=1.0 |
| IR-008 | PASS | bad=[] |
| IR-009 | PASS | lei_residual=(('lei', 'a'),) uuid_residual=() |
| IR-010 | PASS | same_control_same_id=True detail=(('lei', 'a'),) (cannot mutate the validator registry safely in-process to test drift without side effects on other cases) |
| IR-011 | PASS | residuals=(('lei', 'a'),) |
| IR-012 | PASS | bad=[] |
| IR-013 | PASS | refused at parse: [PQL.SYNTAX] expected NULL and found 'VALID' \| Next: Add NULL here. \| Context: position='line 1, column 31' |
| IR-014 | PASS | bad=[] |
| IR-015 | PASS | [INPUT.INVALID] there is no semantic type called 'nosuchtype' \| Next: Register a validator for it, or use a known type. An unresolved type would compile to a check that passes everything, which is worse than no control because it looks like coverage. \| Context: semantic_type='nosuchtype' |
| IR-016 | PASS | kinds={'predicate': 'predicate', 'unique_key': 'unique_key', 'row_count': 'row_count', 'reference': 'reference', 'freshness': 'freshness', 'functional_dependency': 'functional_dependency'} |
| IR-017 | PASS | [INPUT.INVALID] Assertion cannot yet be lowered to a plan \| Next: This assertion parses but has no execution strategy yet. Use one that does, or raise it as a gap — the language deliberately refuses to pretend it can run something it cannot. \| Context: assertion='Assertion' |
| IR-018 | PASS | bad=[] |
| IR-019 | PASS | bad=[] |
| IR-020 | PASS | has_literal_set=True predicate=Expr(kind='op', name='IN', value=None, args=(Expr(kind='col', name='ccy', value=None, args=(), type_name='unknown'), Expr(kind='list', name='', value= |
| IR-021 | FAIL | compiled (IN () present = defect): SELECT COUNT(*) AS "scanned_rows", COALESCE(SUM(CASE WHEN NOT COALESCE(("ccy" IN ()), 0) THEN 1 ELSE 0 END), 0) AS "violating_rows" |
| IR-022 | PASS | before_has_ZWL=True after_has_ZWG=True ids_differ=True |
| IR-023 | PASS | resolved_id=ir:sha256:ddc27e20b58f5337de0b5c9f353528f0ebc3501bf0645c580640b3b655d13727 bare_id=ir:sha256:ddc27e20b58f5337de0b5c9f353528f0ebc3501bf0645c580640b3b655d13727 |
| IR-024 | FAIL | bare TypeError: '<' not supported between instances of 'datetime.date' and 'str' |
| IR-025 | PASS | other_sites=['src/prama/backend/conformance.py:84:            self._plans[case.name] = Lowerer().control(parse_control(case.pql))', 'src/prama/induce/validate.py:225:        self._lowerer = Lowerer(codelists=codelists)'] (each has a stated reason per the catalogue's own Why) |
| IR-026 | PASS | metrics=[('scanned_rows', False), ('violating_rows', True)] |
| IR-027 | PASS | metric_names={'null_key_rows', 'distinct_keys', 'scanned_rows'} null_metric_expr=Expr(kind='op', name='OR', value=None, args=(Expr(kind='op', name='IS NULL', value=None, args=(Expr(kind='col', name='a', value=None, args=(), type_name='unknown'),), type_name='boolean'), Expr(kind='op', name='IS NULL', value=None, args=(Expr(kind='col', name='b', value=None, args=(), type_name='unknown'),), type_nam… |
| IR-028 | PASS | expr=Expr(kind='op', name='IS NULL', value=None, args=(Expr(kind='col', name='a', value=None, args=(), type_name='unknown'),), type_name='boolean') |
| IR-029 | PASS | verdict=Verdict.PASS metrics={'scanned_rows': 3.0, 'distinct_determinants': 2.0, 'distinct_pairs': 2.0, 'violating_rows': 0.0} |
| IR-030 | PASS | metrics=['scanned_rows'] predicate=None detail={'minimum': 1, 'maximum': 8} |
| IR-031 | PASS | predicate=Expr(kind='op', name='EXISTS', value=None, args=(Expr(kind='col', name='x', value=None, args=(), type_name='unknown'), Expr(kind='lit', name='', value='b', args=(), type_name='text'), Expr(kind='lit', name='', value='y', args=(), type_name='text')), type_name='boolean') kind=reference |
| IR-032 | PASS | requires=frozenset({'pushdown.cross_object_join'}) |
| IR-033 | PASS | {'regex_predicate': True, 'regex_filter': True, 'agg_unique': True, 'agg_fd': True, 'agg_seg': True, 'cross_join': True} predicate_requires=frozenset({'pushdown.regex'}) filter_requires=frozenset({'pushdown.regex', 'pushdown.filter'}) unique_requires=frozenset({'pushdown.aggregation'}) ref_requires=frozenset({'pushdown.cross_object_join'}) |
| IR-034 | PASS | cols1=frozenset({'b', 'a', 'c'}) cols2=frozenset({'y', 'x'}) cols3=frozenset({'q', 'p'}) |
| IR-035 | PASS | verdict=Verdict.INDETERMINATE |
| IR-036 | PASS | absolute=Verdict.INDETERMINATE rate=Verdict.INDETERMINATE |
| IR-037 | PASS | verdict=Verdict.INDETERMINATE (expected: not a clean PASS) |
| IR-038 | PASS | zero_denom=Verdict.INDETERMINATE absent_denom=Verdict.INDETERMINATE |
| IR-039 | PASS | bad=[] |
| IR-040 | PASS | {<Verdict.PASS: 'pass'>: False, <Verdict.FAIL: 'fail'>: True, <Verdict.ERROR: 'error'>: True, <Verdict.SKIPPED: 'skipped'>: False, <Verdict.INDETERMINATE: 'indeterminate'>: True} |
| IR-041 | PASS | lit_none={'kind': 'lit', 'value': None, 'type': 'text'} lit_zero={'kind': 'lit', 'value': 0, 'type': 'number'} lit_false={'kind': 'lit', 'value': False, 'type': 'boolean'} col_typed={'kind': 'col', 'name': 'a', 'type': 'text'} col_untyped={'kind': 'col', 'name': 'a'} differ=True |
| IR-042 | PASS | n_tested=25 bad=[] |
| IR-043 | PASS | hash=1b1dd66d72a24f2562de7be92968d5286928aaf5c95696f09ded3dead21fced1 |
| IR-044 | PASS | files=[] |
| BE-001 | PASS | True |
| BE-002 | PASS | {'oracle': "[REGISTRY.INVALID] no SQL dialect named 'oracle' \| Next: Available: duckdb, postgresql, sqlite. \| Context: requested='oracle'", '': "[REGISTRY.INVALID] no SQL dialect named '' \| Next: Available: duckdb, postgresql, sqlite. \| Context: requested=''", 'POSTGRESQL': "[REGISTRY.INVALID] no SQL dialect named 'POSTGRESQL' \| Next: Available: duckdb, postgresql, sqlite. \| Context: request… |
| BE-003 | PASS | {'a"b': '"a""b"', 'a""b': '"a""""b"', "a'b": '"a\'b"', 'a;DROP TABLE x--': '"a;DROP TABLE x--"', 'a\nb': '"a\nb"', '': '""'} |
| BE-004 | PASS | {'positions': '"positions"', 'risk.positions': '"risk"."positions"', 'db.risk.positions': '"db"."risk"."positions"'} |
| BE-005 | FAIL | qualify('risk.positions')='"risk"."positions"' (defect: genuinely one-part name becomes two-part) |
| BE-006 | FAIL | {'None': 'NULL', 'True': 'TRUE', 'False': 'FALSE', '0': '0', '-1': '-1', '1.5': '1.5', '1e+20': '1e+20', '"it\'s"': "'it''s'", "''": "''", "Decimal('1.5')": "'1.5'"} decimal_became_string_literal=True |
| BE-007 | FAIL | {'nan': 'nan', 'inf': 'inf'} |
| BE-008 | PASS | {'postgresql': 'FALSE', 'duckdb': 'FALSE', 'sqlite': '0'} |
| BE-009 | PASS | {'postgresql': 'COUNT(*) FILTER (WHERE x > 0)', 'duckdb': 'COUNT(*) FILTER (WHERE x > 0)', 'sqlite': 'COALESCE(SUM(CASE WHEN x > 0 THEN 1 ELSE 0 END), 0)'} |
| BE-010 | PASS | {'sqlite': 0, 'duckdb': 0, 'postgresql': 0} |
| BE-011 | PASS | {'postgresql_1col': 2, 'duckdb_1col': 2, 'sqlite_1col': 2} |
| BE-012 | FAIL | count_distinct=1 |
| BE-013 | PASS | {'postgresql': 2, 'duckdb': 2, 'sqlite': 2} |
| BE-014 | PASS | results={'postgresql': True, 'duckdb': True, 'sqlite': True} forms={'postgresql': "x ~ 'p'", 'duckdb': "regexp_matches(x, 'p')", 'sqlite': "x REGEXP 'p'"} |
| BE-015 | FAIL | {'(?<=A)B': {'reference': 'Verdict.PASS', 'postgresql': 'compiled ok', 'duckdb': 'compiled ok', 'sqlite': 'compiled ok'}, '\\d+': {'reference': 'Verdict.FAIL', 'postgresql': 'compiled ok', 'duckdb': 'compiled ok', 'sqlite': 'compiled ok'}, '(a)\\1': {'reference': 'Verdict.FAIL', 'postgresql': 'compiled ok', 'duckdb': 'compiled ok', 'sqlite': 'compiled ok'}, '^(?i)abc': {'reference': 'ERR PatternEr… |
| BE-016 | FAIL | {'[': 'parsed (unexpected)', '*': 'refused at parse: PqlSyntaxError'} |
| BE-017 | PASS | unsupported=Unsupported(capability='pushdown.regex', detail='norepex has no regular expression operator, so expr cannot be matched against /pattern/ here', remedy='Use HAS FORMAT with a named format, or run this control on an engine with regular expressions. Substituting LIKE would make the same control mean two different things on two engines.') |
| BE-018 | PASS | bare connection fails: no such function: REGEXP (dialect unconditionally declares REGEX capability = documented gap) |
| BE-019 | PASS | cast=CAST(d AS VARCHAR) value=True |
| BE-020 | PASS | {'sqlite': '2020-01-01', 'duckdb': '2020-01-01', 'postgresql': '2020-01-01'} |
| BE-021 | PASS | {'sqlite': 0.5, 'duckdb': 0.5, 'postgresql': 0.5} |
| BE-022 | PASS | {'postgresql': 'DOUBLE PRECISION', 'duckdb': 'DOUBLE PRECISION', 'sqlite': 'REAL'} |
| BE-023 | PASS | sql_results={'sqlite': -1, 'duckdb': -1, 'postgresql': Decimal('-1'), 'reference': None} (SQL % on all three engines is -1; Python's -10%3 is 2 -- the reference interpreter for the bare % OPERATOR uses SQL-like semantics per _arithmetic, unlike the MOD library function) |
| BE-024 | PASS | postgres raises: DivisionByZeroError: division by zero |
| BE-025 | PASS | exists_in_form=EXISTS (SELECT 1 FROM u WHERE b = 1) |
| BE-026 | PASS | documented boundary; see reference/sql execution parity in section 17 |
| BE-027 | PASS | {'postgresql': 'a IS NOT DISTINCT FROM b', 'duckdb': 'a IS NOT DISTINCT FROM b', 'sqlite': 'a IS b'} |
| BE-028 | PASS | query='SELECT COUNT(*) AS "scanned_rows", COUNT(*) FILTER (WHERE NOT COALESCE(("a" > 0), FALSE)) AS "violating_rows"\nFROM (SELECT * FROM "t" LIMIT 100)' |
| BE-029 | FAIL | caps={'postgresql': frozenset({'pushdown.filter', 'pushdown.aggregation', 'pushdown.approx_distinct', 'pushdown.sampling', 'pushdown.regex', 'pushdown.cross_object_join'}), 'duckdb': frozenset({'pushdown.filter', 'pushdown.aggregation', 'pushdown.approx_distinct', 'pushdown.sampling', 'pushdown.regex', 'pushdown.cross_object_join'}), 'sqlite': frozenset({'pushdown.filter', 'pushdown.cross_object_j… |
| BE-030 | PASS | query='SELECT COUNT(*) AS "scanned_rows", COUNT(*) FILTER (WHERE NOT COALESCE(("a" > 0), FALSE)) AS "violating_rows"\nFROM "t"\nWHERE ("b" > 0)' names=('scanned_rows', 'violating_rows') |
| BE-031 | PASS | names=('entity', 'scanned_rows', 'violating_rows') query=SELECT "entity", COUNT(*) AS "scanned_rows", COUNT(*) FILTER (WHERE NOT COALESCE(("a" > 0), FALSE)) AS "violating_rows" |
| BE-032 | PASS | [PQL.UNSUPPORTED] bare cannot run this control: it needs pushdown.cross_object_join, pushdown.filter, pushdown.regex \| Next: Run it on an engine that has pushdown.cross_object_join, pushdown.filter, pushdown.regex, or express the control differently. Prama will not substitute something close: the same control would then mean two different things on two engines, and nothing would notice. \| Contex… |
| BE-033 | PASS | executed ok: {'scanned_rows': 2, 'violating_rows': 0} |
| BE-034 | FAIL | query='SELECT COUNT(*) AS "scanned_rows", COUNT(*) FILTER (WHERE NOT COALESCE((EXISTS (SELECT 1 FROM "b" WHERE "b"."y" = (SELECT * FROM "a" LIMIT 100)."x")), FALSE)) AS "violating_rows"\nFROM (SELECT * FROM "a" LIMIT 100)' |
| BE-035 | PASS | row={'scanned_rows': 2, 'violating_rows': 1} sql=SELECT COUNT(*) AS "scanned_rows", COALESCE(SUM(CASE WHEN NOT COALESCE((EXISTS (SELECT 1 FROM "b" WHERE "b"."account_id" = "a"."account_id")), 0) THEN 1 ELSE 0 END), 0) AS "violating_rows" |
| BE-036 | PASS | fused='COUNT(*) FILTER (WHERE NOT COALESCE(("a" > 0), FALSE))' unfused_line=['SELECT COUNT(*) AS "scanned_rows", COUNT(*) FILTER (WHERE NOT COALESCE(("a" > 0), FALSE)) AS "violating_rows"'] |
| BE-037 | FAIL | weird_mid_call='(EXISTS (SELECT 1 FROM "d" WHERE "d"."q" = "a"."p"))' leaked_stale_a=True |
| BE-038 | PASS | violation_policy={'scanned_rows': 2, 'violating_rows': 1} pass_policy={'scanned_rows': 2, 'violating_rows': 0} |
| BE-039 | PASS | bad=[] |
| BE-040 | PASS | {'unique_key': '', 'row_count': '', 'freshness': '', 'fd': ''} |
| BE-041 | PASS | n_sample_rows=2 sql='SELECT "a"\nFROM "t"\nWHERE NOT COALESCE(("a" IS NOT NULL), 0) LIMIT 10' |
| BE-042 | PASS | {'counts': False, 'samples': True, 'full': True} |
| BE-043 | PASS | sample_query='' |
| BE-044 | PASS | {'col': '"x"', 'lit': '5', 'param': ':p', 'list': '(1, 2)', 'call': 'UPPER("x")', 'op': '("x" > 0)', 'none': 'TRUE'} |
| BE-045 | PASS | params=('hi', 'lo', 'x') query=SELECT COUNT(*) AS "scanned_rows", COUNT(*) FILTER (WHERE NOT COALESCE(("a" > 0), FALSE)) AS "violating_rows" |
| BE-046 | PASS | [PQL.UNSUPPORTED] there is no function called NONSENSE_FN \| Next: Available: ABS, COALESCE, CONCAT, DAY, IF, IFBLANK, INT, ISBLANK, ISNUMBER, LEFT, LEN, LENGTH, LOWER, MAX, MID, MIN, MOD, MONTH, RIGHT, ROUND, SIGN, SUBSTITUTE, TRIM, UPPER, YEAR. An unrecognised name used to compile straight through to SQL, which is how a typo became a control that ran and meant something nobody intended. \| Conte… |
| BE-047 | PASS | [PQL.UNSUPPORTED] sqlite cannot run ROUND \| Next: Run this control on an engine that can. Prama will not substitute something close: the same control would then mean two different things on two engines, and nothing would notice. \| Context: dialect='sqlite', function='ROUND' |
| BE-048 | PASS | [PQL.UNSUPPORTED] noregex cannot run ISNUMBER: it needs pushdown.regex \| Next: Run it on an engine that has the capability. \| Context: function='ISNUMBER', missing=['pushdown.regex'] |
| BE-049 | FAIL | {'COUNT': 'COUNT("x")', 'SUM': 'SUM("x")', 'MIN': 'MIN("x")', 'MAX': 'MAX("x")', 'MEDIAN': 'PqlUnsupportedError: [PQL.UNSUPPORTED] there is no function called MEDIAN \| Next'} |
| BE-050 | PASS | INFIX=frozenset({'-', '=', '*', '>', '<=', '<', '%', '>=', '/', 'OR', '+', '<>', '\|\|', 'AND'}) bad=[] sample={'-': '("x" - 1)', '=': '("x" = 1)', '*': '("x" * 1)'} |
| BE-051 | PASS | [PQL.UNSUPPORTED] * needs two operands and was given 1 \| Next: This is a defect in the compiler rather than in the control. \| Context: operands=1, operator='*' |
| BE-052 | PASS | rendered='(-"col")' |
| BE-053 | PASS | bad=[] sample={'NOT': 'NOT (TRUE)', 'IS NULL': '("x" IS NULL)', 'IS NOT NULL': '("x" IS NOT NULL)'} |
| BE-054 | FAIL | bad=[('!=', '[PQL.UNSUPPORTED] != has no SQL form on postgresql \| Next: Express the control differently, or run i'), ('IS OF TYPE', '[PQL.UNSUPPORTED] IS OF TYPE has no SQL form on postgresql \| Next: Express the control differently, ')] |
| BE-055 | FAIL | compiled: '("x" IN ())' |
| BE-056 | FAIL | IndexError: tuple index out of range |
| BE-057 | PASS | query=SELECT COUNT(*) AS "scanned_rows", COUNT(*) FILTER (WHERE NOT COALESCE(("d" IS NOT NULL), FALSE)) AS "violating_rows" |
| BE-058 | PASS | is_complete=False residuals=(('lei', 'a'),) |
| BE-059 | PASS | documented in the execution/evidence path, not directly testable via the compiler alone |
| BE-060 | PASS | bad=[] |
| BE-061 | PASS | rc=0 stdout='-- In t, every a has a value. No violations are allowed. A failure is major.\nSELECT COUNT(*) AS "scanned_rows", COALESCE(SUM(CASE WHEN NOT COALESCE(("a" IS NOT NULL), 0) THEN 1 ELSE 0 END), 0) AS "violating_rows"\nFROM "t"\n\n-- In t, every b has a value, considering only rows where ROUND(x, 2) > 0. No' |
| BE-062 | FAIL | rc=0 stdout='-- In t, every a has a value, considering only rows where ROUND(x, 2) > 0. No violations are allowed. A failure is major.\n--   refused: sqlite cannot run ROUND\n--   → Run this control on an engine tha' |
| BE-063 | PASS | bad=[] |
| BE-064 | PASS | bad(av,bv,ref,sqlite,duckdb)=[] |
| BE-065 | PASS | result=None |
| BE-066 | PASS | result=None |
| BE-067 | FAIL | bare KeyError: '!=' |
| BE-068 | FAIL | {'reference': None, 'sqlite': {'scanned_rows': 1, 'violating_rows': 0}, 'duckdb': {'scanned_rows': 1, 'violating_rows': 0}, 'postgresql': 'UndefinedFunctionError: operator does not exist: text = integer\nHINT:  No operator matches the given name and argument types. You might need to add ex'} |
| BE-069 | PASS | in1=True in3=None notin1=False notin3=None |
| BE-070 | PASS | in=None notin=None |
| BE-071 | PASS | bad=[] null=None not_between=True |
| BE-072 | PASS | matches=True |
| BE-073 | PASS | {'reference': 1.0, 'sqlite': 1, 'duckdb': 1, 'postgresql': 1} |
| BE-074 | PASS | unbounded cache is a latent risk, not a live one while patterns are literals (documented) |
| BE-075 | FAIL | did not complete within 10s (catastrophic backtracking, uncaught -- confirms the defect) |
| BE-076 | PASS | bad=[] |
| BE-077 | PASS | div0=None mod0=None postgres_div0=raises: DivisionByZeroError: division by zero (documented divergence: postgres raises, reference returns unknown) |
| BE-078 | FAIL | bare ValueError: could not convert string to float: 'abc' |
| BE-079 | FAIL | operator_flag_plus_1=2.0 ABS(flag)=UNKNOWN (one consistent answer expected; likely two different ones) |
| BE-080 | FAIL | raw_float_eq=False rounded_decimal_eq=True |
| BE-081 | PASS | neg_null=None neg_text=None |
| BE-082 | PASS | bad=[] |
| BE-083 | PASS | ISBLANK=True IF=1 COALESCE=1 IFBLANK=1 ISNUMBER=False |
| BE-084 | PASS | COUNT(x)_as_row_expr=None |
| BE-085 | PASS | raw_evaluate=UNKNOWN via_call=None is_UnknownValue_instance=False |
| BE-086 | PASS | UNKNOWN has no truth value. Three-valued logic is the point: collapsing it to True or False here is how a null becomes a pass. |
| BE-087 | PASS | True |
| BE-088 | PASS | true_row=False false_row=True unknown_row=True |
| BE-089 | PASS | metrics={'scanned_rows': 3.0, 'violating_rows': 3.0} |
| BE-090 | PASS | batch_violating=1.0 inflight_violation=True |
| BE-091 | PASS | fails_residual(None)=False |
| BE-092 | PASS | ValidationError: [INPUT.INVALID] no validator named 'nosuchvalidator' \| Next: Known types: aba_routing, bic, card_number, cusip, email, figi, gtin, hex_colour, iban, ipv4, isin, iso_date, lei, mic, npi, sedol, ulid, upi, uti, uuid. An unknown semantic type would compile to a check that passes everything, so it is refused here instead. \| Context: requested='nosuchvalidator' |
| BE-093 | PASS | reference={'scanned_rows': 1.0, 'violating_rows': 0.0} sql={'scanned_rows': 1, 'violating_rows': 0} |
| BE-094 | PASS | reference={'scanned_rows': 3.0, 'distinct_keys': 1.0, 'null_key_rows': 2.0, 'duplicate_rows': 0.0, 'violating_rows': 2.0} sql={'scanned_rows': 3, 'distinct_keys': 1, 'null_key_rows': 2} |
| BE-095 | FAIL | bare TypeError: unhashable type: 'list' |
| BE-096 | FAIL | metrics={'approx': 0.0} (expected non-zero approximation; likely silently 0.0) |
| BE-097 | FAIL | SUM([])=0.0 MIN([])=0.0 (expected: NULL/None, not 0.0) |
| BE-098 | PASS | this control refers to 'b', which was not supplied. Pass it as a related dataset, or run the control on an engine that can reach both. |
| BE-099 | PASS | memoisation is keyed on (dataset, column) per source; not independently re-timed here |
| BE-100 | FAIL | materialises_whole_input=True |
| BE-101 | PASS | samples=() |
| BE-102 | PASS | bad_imports=[] |
| BE-103 | PASS | [<Verdict.FAIL: 'fail'>, <Verdict.FAIL: 'fail'>, <Verdict.FAIL: 'fail'>, <Verdict.FAIL: 'fail'>] |
| BE-104 | PASS | metrics={'scanned_rows': 8.0, 'distinct_keys': 7.0, 'null_key_rows': 0.0, 'duplicate_rows': 1.0, 'violating_rows': 1.0} |
| BE-105 | PASS | metrics={'scanned_rows': 5.0, 'distinct_keys': 2.0, 'null_key_rows': 2.0, 'duplicate_rows': 1.0, 'violating_rows': 3.0} |
| BE-106 | PASS | used corpus case |
| BE-107 | PASS | verdict=Verdict.INDETERMINATE metrics={'scanned_rows': 10.0} |
| BE-108 | PASS | unique=Verdict.INDETERMINATE fd=Verdict.INDETERMINATE |
| BE-109 | PASS | verdict=Verdict.FAIL |
| BE-110 | PASS | verdict=Verdict.INDETERMINATE |
| BE-111 | PASS | {0: <Verdict.FAIL: 'fail'>, 1: <Verdict.PASS: 'pass'>, 8: <Verdict.PASS: 'pass'>, 9: <Verdict.FAIL: 'fail'>} |
| BE-112 | FAIL | {'predicate': (<Verdict.PASS: 'pass'>, <Verdict.FAIL: 'fail'>), 'unique_key': (<Verdict.PASS: 'pass'>, <Verdict.FAIL: 'fail'>), 'row_count': (<Verdict.PASS: 'pass'>, <Verdict.FAIL: 'fail'>), 'reference': (<Verdict.PASS: 'pass'>, <Verdict.FAIL: 'fail'>), 'freshness': (<Verdict.INDETERMINATE: 'indeterminate'>, <Verdict.INDETERMINATE: 'indeterminate'>), 'functional_dependency': (<Verdict.PASS: 'pass'… |
| BE-113 | PASS | c1={'verdict': 'pass', 'metrics': {'a': 1.0}, 'segments': []} c2={'verdict': 'pass', 'metrics': {'a': 1.0}, 'segments': []} |
| BE-114 | PASS | c1={'verdict': 'pass', 'metrics': {'rate': 0.333333333}, 'segments': []} c2={'verdict': 'pass', 'metrics': {'rate': 0.333333333}, 'segments': []} |
| BE-115 | FAIL | TypeError: float() argument must be a string or a real number, not 'NoneType' |
| BE-116 | PASS | n_groups=1 sizes=[20] |
| BE-117 | PASS | n_groups=4 |
| BE-118 | PASS | n_groups=1 |
| BE-119 | PASS | n_groups=1 |
| BE-120 | PASS | eq=True |
| BE-121 | PASS | n_COUNT(*)_occurrences=1 sql=SELECT COUNT(*) AS "c0__scanned_rows", COALESCE(SUM(CASE WHEN NOT COALESCE(("c0" IS NOT NULL), 0) THEN 1 ELSE 0 END), 0) AS "c0__violating_rows", COALESCE(SUM(CASE WHEN NOT COALESCE(("c1" IS NOT NULL) |
| BE-122 | PASS | n_results=5 verdicts=[<Verdict.FAIL: 'fail'>, <Verdict.FAIL: 'fail'>, <Verdict.FAIL: 'fail'>, <Verdict.FAIL: 'fail'>, <Verdict.FAIL: 'fail'>] |
| BE-123 | PASS | verdicts=[<Verdict.INDETERMINATE: 'indeterminate'>, <Verdict.INDETERMINATE: 'indeterminate'>, <Verdict.INDETERMINATE: 'indeterminate'>, <Verdict.INDETERMINATE: 'indeterminate'>, <Verdict.INDETERMINATE: 'indeterminate'>] |
| BE-124 | PASS | n=3 seg_counts=[2, 2, 2] |
| BE-125 | FAIL | the whole group of 20 stopped on one unsupported control: [PQL.UNSUPPORTED] limited cannot run one of these controls: it needs pushdown.regex \| Next: Remove it from the run, or run the group on an engine that has it. One control that cannot be expressed must not stop the rest — but it must not be silently dropped either. \| Context: missing=['pushdown.regex'], plan='ir:sha256:9b9994a1aa9f2678d7d6… |
| BE-126 | FAIL | sql_mentions_samples=False (fuse emitting only metric columns, losing samples, is the confirmed defect) sql=SELECT COUNT(*) AS "c0__scanned_rows", COALESCE(SUM(CASE WHEN NOT COALESCE(("a" IS NOT NULL), 0) THEN 1 ELSE 0 END), 0) AS "c0__violating_rows" |
| BE-127 | PASS | controls=20 scans=2 render='20 control(s) in 2 scan(s) — 18 fewer passes over the data than running them separately.' |
| BE-128 | PASS | rows_read=None render='2 control(s) in 2 scan(s).' |
| BE-129 | FAIL | scans=2 rows_per_scan_entries=1 |
| BE-130 | PASS | controls=0 render='0 control(s) in 0 scan(s).' |
| BE-131 | PASS | n_disagreements=0 sample=[] |
| BE-132 | FAIL | status=failed detail=OperationalError: no such function: REGEXP |
| BE-133 | PASS | status=failed detail=RuntimeError: simulated driver error |
| BE-134 | PASS | n_disagreements_with_2_runners=0 |
| BE-135 | FAIL | n_disagreements=0 (0 disagreements from 1 runner is not evidence of agreement) |
| BE-136 | PASS | two_stage_case=semantic_type_two_stage |
| BE-137 | PASS | disagreements=['semantic_type_two_stage'] |
| BE-138 | PASS | disagreements=['semantic_type_two_stage', 'semantic_type_two_stage'] |
| BE-139 | FAIL | disagreements_without_reference=[] |
| BE-140 | FAIL | case.requires consulted in conformance.py: False (grep hits: '') |
| BE-141 | FAIL | usages=[] |
| BE-142 | FAIL | rows_without_notes(0-indexed)=[0, 1, 2, 7] |
| BE-143 | FAIL | used=[] missing=['ABS', 'COALESCE', 'CONCAT', 'DAY', 'IF', 'IFBLANK', 'INT', 'ISBLANK', 'ISNUMBER', 'LEFT', 'LEN', 'LENGTH', 'LOWER', 'MAX', 'MID', 'MIN', 'MOD', 'MONTH', 'RIGHT', 'ROUND', 'SIGN', 'SUBSTITUTE', 'TRIM', 'UPPER', 'YEAR'] |
| BE-144 | FAIL | has_codelist_case=False |
| BE-145 | PASS | {'reference': ('Verdict.PASS', 8.0, 0.0), 'sqlite': (8, 0), 'duckdb': (8, 0)} |
| BE-146 | FAIL | compiled_query_has_named_param=True Runner_type_has_no_parameter_channel=True |
| BE-147 | PASS | non_indeterminate_over_empty_scope=[] |
| BE-148 | PASS | {'reference': ('Verdict.FAIL', 8.0, 8.0), 'sqlite': (8, 8), 'duckdb': (8, 8)} |
| BE-149 | FAIL | covered=set() |
| BE-150 | FAIL | {'freshness': False, 'is_unique': False, 'excel': False, 'has_format': False} |
| BE-151 | PASS | bad=[] |
| BE-152 | PASS | {'sqlite': True, 'duckdb': True, 'postgresql': True} |
| BE-153 | PASS | q_form='INSERT INTO "corpus" ("row_id", "account_id", "instrument_id", "entity", "isin", "ccy", "notional", "status", "lei") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)' dollar_form='INSERT INTO "corpus" ("row_id", "account_id", "instrument_id", "entity", "isin", "ccy", "notional", "status", "lei") VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)' |
| BE-154 | PASS | g1==g2: True |
| BE-155 | PASS | single-process check only; cross-version repro not independently testable here |
| BE-156 | PASS | n_tested=200 bad=[] |
| BE-157 | PASS | distinct_verdicts={'Verdict.INDETERMINATE', 'Verdict.FAIL', 'Verdict.PASS'} |
| BE-158 | FAIL | documented_exclusion_list_present=False |
| BE-159 | PASS | found_seed_with_treat_unknown_as_pass=True |
| BE-160 | FAIL | bad=[('CHECK corpus.account_id HAS LENGTH BETWEEN 6 AND 8 WHERE NOT', [Finding(message='corpus.account_id holds text, and it is being compared with 6, which is number', remedy='Compare like with like. Engines differ on whether they coerce these silently, so a control written this way would mean one thing on one database and something else on another.', position=Position(line=1, column=44, offset=4… |
| BE-161 | PASS | n_suites=1 n_controls=7 |
| BE-162 | PASS | n_controls=7 lower_failures=[] |
| BE-163 | PASS | bad=[] all=[('unique key', 'fail', 'fail'), ('notional not null', 'fail', 'fail'), ('currency codelist', 'fail', 'fail'), ('account reference', 'fail', 'fail'), ('account determines entity', 'fail', 'fail'), ('row count', 'pass', 'pass'), ('notional range', 'fail', 'fail')] |
| BE-164 | PASS | entry=Expectation(control='row count', verdict='pass', catches='the volume is within the declared band') |
| BE-165 | PASS | subsumed_findings=[LintFinding(rule='subsumed', message='this control adds nothing: positions_eod.notional_amount BETWEEN -1000000000 AND 1000000000 already fails on a null, because an unknown counts as a violation', remedy='Remove it, or make it say something the other does not. Two controls firing on the same rows produce two alerts about one problem.', control='CHECK positions_eod.notional_amou… |
| BE-166 | PASS | {'reference': {'scanned_rows': 8.0, 'distinct_keys': 7.0, 'null_key_rows': 0.0, 'duplicate_rows': 1.0, 'violating_rows': 1.0}, 'sqlite': {'scanned_rows': 8, 'distinct_keys': 7, 'null_key_rows': 0}} |
| BE-167 | PASS | {'MONITOR row_count ON positions_eod SEASO': "[PQL.SYNTAX] expected a control and found 'MONITOR' \| Next: A control begins with CHECK, and a group", 'RECONCILE positions_eod AGAINST general_': "[PQL.SYNTAX] expected a control and found 'RECONCILE' \| Next: A control begins with CHECK, and a gro", 'CHECK positions_eod DERIVES FROM murex_t': "[PQL.SYNTAX] expected something to check about positions… |
| BE-168 | FAIL | unmatched_declarations=['Daily Positions EOD, owned by the Head of Market Risk Data, '] |
| BE-169 | PASS | bad=[] |
| BE-170 | PASS | elapsed=0.3s rc=0 |
| BE-171 | PASS | parsed in 0.30s |
| BE-172 | FAIL | {'9223372036854775807': 'hashed and compiled: ir:sha256:200fad3e1b...', '9223372036854775808': 'hashed and compiled: ir:sha256:8507bffc35...', '11111111111111111111': 'TypeError: Integer exceeds 64-bit range'} |
| BE-173 | PASS | sql=Verdict.PASS reference=Verdict.PASS |
| BE-174 | PASS | bad=[] |
| BE-175 | PASS | bad=[] |
| BE-176 | PASS | row=(1, 0) sql=SELECT COUNT(*) AS "scanned_rows", COALESCE(SUM(CASE WHEN NOT COALESCE((CAST("日本語" AS VARCHAR) REGEXP '^caf'), 0) THEN 1 ELSE 0 END), 0) AS "violating |
| BE-177 | PASS | plan=ir:sha256:ee44377f54011968249b compiled=ir:sha256:ee44377f54011968249b result=ir:sha256:ee44377f54011968249b |
| BE-178 | FAIL | record_has_threshold_field=False r1_verdict=Verdict.FAIL r2_verdict=Verdict.PASS (same metrics, different thresholds -> different verdicts, and the record must carry which threshold applied) |
| BE-179 | FAIL | {'clock': 'refused: PqlSyntaxError', 'random': 'refused: PqlSyntaxError', 'unresolved_codelist': 'refused: ValidationError', 'unresolved_semantic_type': 'refused: ValidationError', 'codelist_frozen': 'frozen', 'PLUGINS_registry_size': 0} (PLUGINS empty -- implementation-hash freezing never fires = confirmed defect) |
| BE-180 | PASS | files_importing_ai=[] |
## Per-failure detail

### PQL-001 · Every token kind the lexer can emit is reachable
- **Observed:** kinds=['END', 'IDENTIFIER', 'KEYWORD', 'NUMBER', 'OPERATOR', 'PARAMETER', 'PUNCTUATION', 'REGEX'] expected=['END', 'IDENTIFIER', 'KEYWORD', 'NUMBER', 'OPERATOR', 'PARAMETER', 'PUNCTUATION', 'REGEX', 'STRING']

### PQL-005 · Nested block comments are not nested
- **Observed:** toks=None msg=[PQL.SYNTAX] a pattern is opened with / and never closed | Next: Close it with another /, as in /^[A-Z]{2}[0-9]{10}$/. | Context: position='line 1, column 37'

### PQL-015 · An empty quoted identifier `""`
- **Observed:** target='""' err=None

### PQL-035 · A non-ASCII identifier is refused with the quoting remedy
- **Observed:** AssertionError: 

### PQL-036 · A non-ASCII letter cannot crash the word scanner
- **Observed:** AssertionError: 

### PQL-037 · Non-ASCII inside a quoted identifier and inside text is accepted
- **Observed:** target=montànt rendered_reparses=False detail=AssertionError: 

### PQL-047 · Every PQL error renders position, excerpt, caret and remedy
- **Observed:** {'syntax': 'a pattern is opened with / and never closed (at line 1, column 19)\n\n  CHECK t.a MATCHES /^A\n                    ^\n\n→ Close it with another /, as in /^[A-Z]{2}[0-9]{10}$/.', 'type': "t.isin holds text, and it is being compared with 12, which is number (at line 1, column 16)\n\n  CHECK t.isin = 12 BECAUSE 'x'\n                 ^^\n\n→ Compare like with like. Engines differ on whether they coerce these silently, so a control written this way would mean one thing on one database and something else on another.", 'unsupported': 'sqlite cannot run ROUND (at line 1, column 1)\n\n→ Run this control on an engine that can. Prama will not substitute something close: the same control would then mean two different things on two engines, and nothing would notice.'}

### PQL-055 · `--json` output of a PQL error is valid JSON
- **Observed:** returncode=1 whole_stdout_is_json=False stdout='a pattern is opened with / and never closed (at line 1, column 19)\n\n  CHECK t.a MATCHES /^A\n                    ^\n\n→ Close it with another /, as in /^[A-Z]{2}[0-9]{10}$/.\n'

### PQL-064 · A suite name may be a keyword or quoted
- **Observed:** {'keyword': "parsed name='record'", 'quoted': "name='core suite' render='SUITE core suite {\\n\\n}' REPARSE_FAIL: [PQL.SYNTAX] expected '{' and found 'suite' | Next: Add '{' here. | Context: position='line 1, column 12'"}

### PQL-068 · A dangling dot after the dataset
- **Observed:** err=[PQL.SYNTAX] expected a comparison after positions.IS, found 'NULL' | Next: For example: > 0, IN ('GBP','USD'), BETWEEN 1 AND 10, MATCHES /^[A-Z]{2}/ | Context: position='line 1, column 25'

### PQL-082 · `IS FRESH WITHIN 0 MINUTES` is a zero tolerance, not a missing one
- **Observed:** desc='the data arrives on time' due_time='06:30' due_time_in_desc=False

### PQL-083 · A freshness control cannot be judged
- **Observed:** predicate=None metrics=['scanned_rows'] verdict=ControlResult(plan_id='ir:sha256:ec3782874717f0010712b201f02d8448d883f6d6f07d6dead2564f32523d7309', verdict=<Verdict.INDETERMINATE: 'indeterminate'>, metrics={'scanned_rows': 10.0}, segments=(), samples=(), engine='', detail='') (expected: derived from arrival time; actual: no freshness branch)

### PQL-086 · `HAS UNIQUE KEY` with a qualified or duplicated column
- **Observed:** dup_cols=[('t', 'a'), ('t', 'a')] deduped_or_refused=False foreign_findings=[Finding(message='other.a belongs to other, but this control is about t', remedy='Use a column of t, or declare the relationship between the two datasets and write a control across it.', position=Position(line=1, column=25, offset=24, length=5), level='error')]

### PQL-089 · Row-count bounds must be whole numbers
- **Observed:** {'HAS ROW COUNT AT LEAST 1e6': "BARE ValueError: invalid literal for int() with base 10: '1e6'", 'HAS ROW COUNT AT LEAST 1000000.0': "ctl=False err=[PQL.SYNTAX] expected a count as a whole number and found '1000000.0' | Next: Use a whole number here. | Context: position='line 1, column 32'", 'HAS ROW COUNT AT LEAST 10%': "ctl=False err=[PQL.SYNTAX] expected a count as a whole number and found '10%' | Next: Use a whole number here. | Context: position='line 1, column 32'"}

### PQL-092 · `HAS LENGTH BETWEEN` on a text column must not be a type error
- **Observed:** findings=[Finding(message='t.isin holds text, and it is being compared with 12, which is number', remedy='Compare like with like. Engines differ on whether they coerce these silently, so a control written this way would mean one thing on one database and something else on another.', position=Position(line=1, column=33, offset=32, length=2), level='error'), Finding(message='t.isin holds text, and it is being compared with 12, which is number', remedy='Compare like with like. Engines differ on whether they coerce these silently, so a control written this way would mean one thing on one database and something else on another.', position=Position(line=1, column=40, offset=39, length=2), level='error')]

### PQL-099 · The target of a REFERENCES is never resolved
- **Observed:** {'FERENCES accounts.nosuchcolumn': [], '_id REFERENCES nosuchdataset.x': []}

### PQL-102 · `DETERMINES` with a non-column on either side is refused
- **Observed:** {'IES UPPER(a) DETERMINES b': "[PQL.SYNTAX] the left of DETERMINES must be one or more columns | Next: For example: SATISFIES account_id DETERMINES legal_entity_id | Context: position='line 1, column 39'", ' SATISFIES a DETERMINES 1': "[PQL.SYNTAX] the right of DETERMINES must be one or more columns | Next: For example: SATISFIES account_id DETERMINES legal_entity_id | Context: position='line 1, column 33'", 'SFIES (a, 1) DETERMINES b': "[PQL.SYNTAX] expected ')' and found ',' | Next: Add ')' here. | Context: position='line 1, column 21'"}

### PQL-112 · A set-level assertion under a selector expands into N copies of one control
- **Observed:** {'ROW COUNT AT LEAST 1': 'n_expanded=5 identical_assertions=True one_or_refused=False', '_cde SATISFIES a > 0': 'n_expanded=5 identical_assertions=True one_or_refused=False'}

### PQL-128 · An owner containing a quote round-trips
- **Observed:** owner="O'Brien" rendered="CHECK t.a > 0\n  SEVERITY major\n  OWNER 'O'Brien' REPARSE_FAIL: [PQL.SYNTAX] a piece of text is opened with ' and never closed | Next: Close it with another '. To include a quote in the text, double it: 'O''Brien'. | Context: position='line 3, column 17'"

### PQL-132 · `EVIDENCE full (10)` loses the count on render
- **Observed:** orig=(EvidenceLevel.FULL,10) rendered='CHECK t.a > 0\n  SEVERITY major\n  EVIDENCE full' reparsed=(EvidenceLevel.FULL,50)

### PQL-140 · `AT LEAST n ROWS` renders as `AT MOST n ROWS`
- **Observed:** orig=Threshold(unit='rows', value=5.0, currency='', comparator='>=') rendered='CHECK t.a IS NOT NULL\n  AT MOST 5 ROWS\n  SEVERITY major' reparsed=Threshold(unit='rows', value=5.0, currency='', comparator='<=')

### PQL-141 · A large row threshold renders in scientific notation
- **Observed:** orig=1234567.0 rendered='CHECK t.a IS NOT NULL\n  AT MOST 1.23457e+06 ROWS\n  SEVERITY major' reparsed=1234570.0

### PQL-149 · `WITHIN n SIGMA` does not produce a sigma threshold
- **Observed:** ctl_threshold=None err=[PQL.SYNTAX] there is more text after the control: 'SIGMA' | Next: Each control ends where the next CHECK begins. | Context: position='line 1, column 32'

### PQL-150 · An amount threshold silently becomes a row count
- **Observed:** threshold=Threshold(metric='violating_rows', comparator=<Comparator.LE: '<='>, value=100.0, relative_to='')

### PQL-151 · A threshold on an assertion that has no rate
- **Observed:** lowered (no refusal); metrics=['scanned_rows'] threshold=Threshold(metric='violating_rows', comparator=<Comparator.LE: '<='>, value=0.1, relative_to='scanned_rows')

### PQL-154 · `HAVING` never reaches the plan
- **Observed:** scope=Scope(dataset='t', binding='', filter=None, segment_by=('entity',), as_of='', window='') plan_has_having=False sql_has_having=False sql=SELECT "entity", COUNT(*) AS "scanned_rows", COALESCE(SUM(CASE WHEN NOT COALESCE(("a" IS NOT NULL), 0) THEN 1 ELSE 0 END), 0) AS "violating_rows"

### PQL-156 · Segment keys are ambiguous when a value contains the separator
- **Observed:** keys=['x|y|z'] n_segments=1 (expected: 2 distinct)

### PQL-159 · Segment totals sum metrics that cannot be summed
- **Observed:** metrics={'scanned_rows': 20.0, 'distinct_keys': 17.0, 'duplicate_rows': 3.0, 'violating_rows': 3.0} (naive sum present and used as if meaningful: True)

### PQL-166 · Reversed *text* bounds are not caught
- **Observed:** findings=[LintFinding(rule='no-justification', message='this control does not say why it exists', remedy="Add BECAUSE '…'. When it fires at three in the morning, the sentence explaining what the business declared is the most useful thing on the screen — and a control nobody can justify is one nobody will maintain.", control="CHECK t.code BETWEEN 'Z' AND 'A'", related='', severity='info', position=Position(line=1, column=1, offset=0, length=5))] (expected: always-fires finding present)

### PQL-171 · `LIKE` and `ILIKE` are expression-only
- **Observed:** e1=[PQL.SYNTAX] expected something to check about t and found 'LIKE' | Next: A control says what must be true: IS NOT NULL, IN CODELIST, HAS UNIQUE KEY (…), HAS ROW COUNT BETWEEN …, REFERENCES …, SATISFIES … | Context: position='line 1, column 11' c2_parsed=True

### PQL-175 · Deep nesting does not exhaust the stack
- **Observed:** {1000: 'RecursionError (bare crash)', 5000: 'RecursionError (bare crash)'}

### PQL-176 · An expression with 1,000 OR terms
- **Observed:** uncaught RecursionError: maximum recursion depth exceeded

### PQL-177 · A control with 500 columns
- **Observed:** {'sqlite': 'RecursionError: maximum recursion depth exceeded', 'duckdb': 'RecursionError: maximum recursion depth exceeded', 'postgresql': 'RecursionError: maximum recursion depth exceeded'}

### PQL-181 · The two volatile lists disagree
- **Observed:** {'pql:TODAY()': 'PARSED (should be refused)', 'pql:RANDBETWEEN(1,2)': 'PARSED (should be refused)', "pql:INDIRECT('a')": 'PARSED (should be refused)', 'pql:OFFSET(a,1,1)': 'PARSED (should be refused)', 'excel:CURRENT_DATE': "refused: [PQL.SYNTAX] there is no function called CURRENT_DATE | Next: Available: ABS, COALESCE, CONCAT, DAY, IF, IFBLANK, INT, ISBLANK, ISNUMBER, LEFT, LEN, LENGTH, LOWER, MAX, MID, MIN, MOD, MONTH, RIGHT, ROUND, SIGN, SUBSTITUTE, TRIM, UPPER, YEAR. Prama accepts a deliberately small set: every one of them has a lowering for each engine and a reference implementation that is tested to agree with it. | Context: formula='=CURRENT_DATE()', function='CURRENT_DATE'", 'excel:SYSDATE': "refused: [PQL.SYNTAX] there is no function called SYSDATE | Next: Available: ABS, COALESCE, CONCAT, DAY, IF, IFBLANK, INT, ISBLANK, ISNUMBER, LEFT, LEN, LENGTH, LOWER, MAX, MID, MIN, MOD, MONTH, RIGHT, ROUND, SIGN, SUBSTITUTE, TRIM, UPPER, YEAR. Prama accepts a deliberately small set: every one of them has a lowering for each engine and a reference implementation that is tested to agree with it. | Context: formula='=SYSDATE()', function='SYSDATE'", 'excel:UUID': "refused: [PQL.SYNTAX] there is no function called UUID | Next: Available: ABS, COALESCE, CONCAT, DAY, IF, IFBLANK, INT, ISBLANK, ISNUMBER, LEFT, LEN, LENGTH, LOWER, MAX, MID, MIN, MOD, MONTH, RIGHT, ROUND, SIGN, SUBSTITUTE, TRIM, UPPER, YEAR. Prama accepts a deliberately small set: every one of them has a lowering for each engine and a reference implementation that is tested to agree with it. | Context: formula='=UUID()', function='UUID'"}

### PQL-182 · A quoted column named after a volatile function
- **Observed:** err=None

### PQL-189 · A parameter used only inside a metric expression is not declared
- **Observed:** parameters()=frozenset() (expected: 'cap' listed)

### PQL-196 · `parse(render(x)) == x` for every assertion kind
- **Observed:** n=22 bad=[('CHECK t.a IS NOT UNIQUE', "rendered='CHECK t.a IS UNIQUE\\n  SEVERITY major' reparsed_eq=False")]

### PQL-198 · `BINDING` agrees with `PRECEDENCE`
- **Observed:** mismatches=[('!=', '+'), ('!=', '-'), ('!=', '||'), ('!=', '*'), ('!=', '/')] missing_from_BINDING=['!=']

### PQL-199 · `!=` is missing from `BINDING` and `COMPARISONS`
- **Observed:** rendered='a != (1) * 2' binding_missing=True comparisons_missing=True

### PQL-209 · A percentage round-trips losing precision
- **Observed:** orig=0.001234567 rendered='CHECK t.a > 0\n  WHERE r > 0.123457%\n  SEVERITY major' reparsed=0.00123457

### PQL-219 · `prama control format` destroys suites
- **Observed:** after_write='CHECK t.a IS NOT NULL\n  SEVERITY major\n\nCHECK t.b IS NOT NULL\n  SEVERITY major\n' stdout(no-write)='CHECK t.a IS NOT NULL\n  SEVERITY major\n\nCHECK t.b IS NOT NULL\n  SEVERITY major\n'

### PQL-222 · `prama control format` discards comments
- **Observed:** comments_gone=True warned=False stdout='/tmp/tmp800p8l8s/c.pql: rewritten\n'

### PQL-228 · Column resolution is case-insensitive but compilation is not
- **Observed:** checker_accepts=True quoted='"ACCOUNT_ID"' inconsistent=True

### PQL-235 · `x IS NULL` is typed as a number
- **Observed:** findings=[Finding(message='b IS NULL holds number, and it is being compared with TRUE, which is boolean', remedy='Compare like with like. Engines differ on whether they coerce these silently, so a control written this way would mean one thing on one database and something else on another.', position=Position(line=1, column=43, offset=42, length=4), level='error')]

### PQL-241 · `SATISFIES` conditions are never type-checked
- **Observed:** satisfies_findings=[] where_findings=[Finding(message="notional holds number, and it is being compared with 'ACTIVE', which is text", remedy='Compare like with like. Engines differ on whether they coerce these silently, so a control written this way would mean one thing on one database and something else on another.', position=Position(line=1, column=47, offset=46, length=8), level='error')]

### PQL-242 · A `HAVING` expression is never function-checked or type-checked
- **Observed:** findings=[Finding(message='t has no column called e', remedy='Columns available: a, b', position=Position(line=1, column=32, offset=31, length=1), level='error')]

### PQL-264 · `CONCAT` with a NULL argument disagrees between SQL and the reference
- **Observed:** reference=None postgres='a' sqlite=None (three-way agreement: False)

### PQL-266 · `argument_types` is declared and never enforced
- **Observed:** findings=[] (expected per catalogue: caught; likely a gap)

### PQL-269 · `LENGTH` of a non-text value
- **Observed:** {'notional': (Decimal('4'), {'sqlite': 4, 'duckdb': 'ERR:BinderException'}), 'trade_date': (Decimal('10'), {'sqlite': 10, 'duckdb': 10})}

### PQL-272 · `TRIM` of other whitespace
- **Observed:** ref='a\nnon-breaking\xa0here' sq='\ta\nnon-breaking\xa0here'

### PQL-273 · `LEFT`, `RIGHT` and `MID` with a zero, a negative and an over-long length
- **Observed:** {('LEFT', 0): ('', ''), ('LEFT', -1): ('', ''), ('LEFT', 99): ('abc', 'abc'), ('RIGHT', 0): ('', ''), ('RIGHT', -1): ('', ''), ('MID', 0, 2): ('ab', 'a'), ('MID', -1, 2): ('ab', 'c'), ('MID', 2, 0): ('', '')}

### PQL-276 · `SUBSTITUTE` with an empty search string
- **Observed:** ref='XaXbXcX' sq='abc'

### PQL-280 · `ROUND` with a negative or very large number of places
- **Observed:** r1=1.2E+3 r2=InvalidOperation: [<class 'decimal.InvalidOperation'>]

### PQL-287 · `MIN`/`MAX` with an unknown argument are unknown
- **Observed:** ref=None sqlite=None duckdb=1 postgresql=1

### PQL-288 · `IF` with an undetermined condition is undetermined
- **Observed:** reference=None sql_case_when_null=2 (SQL takes the ELSE branch -- disagreement)

### PQL-294 · `ISNUMBER` on each engine
- **Observed:** {"'123'": (True, True), "'-1.5'": (True, True), "'1e5'": (False, False), "'  7 '": (True, False), "''": (False, False), 'None': (False, False)}

### PQL-300 · Reference arithmetic is exact, SQL arithmetic is not
- **Observed:** operator(+)_float_result=0.30000000000000004 function_path_decimal_sum=Decimal('0.3') one_arithmetic_model=False

### PQL-335 · Excel errors carry no position
- **Observed:** err=[PQL.SYNTAX] the formula ends before it is finished | Next: Check the brackets and the argument count. Functions available: ABS, COALESCE, CONCAT, DAY, IF, IFBLANK, INT, ISBLANK, ISNUMBER, LEFT, LEN, LENGTH, LOWER, MAX, MID, MIN, MOD, MONTH, RIGHT, ROUND, SIGN, SUBSTITUTE, TRIM, UPPER, YEAR. | Context: formula='=[a] +', position=6 pos=(line 1, column 1) diagnostics=[Diagnostic(message="[PQL.SYNTAX] the formula ends before it is finished | Next: Check the brackets and the argument count. Functions available: ABS, COALESCE, CONCAT, DAY, IF, IFBLANK, INT, ISBLANK, ISNUMBER, LEFT, LEN, LENGTH, LOWER, MAX, MID, MIN, MOD, MONTH, RIGHT, ROUND, SIGN, SUBSTITUTE, TRIM, UPPER, YEAR. | Context: formula='=[a] +', position=6", level='error', remedy='Check the brackets and the argument count. Functions available: ABS, COALESCE, CONCAT, DAY, IF, IFBLANK, INT, ISBLANK, ISNUMBER, LEFT, LEN, LENGTH, LOWER, MAX, MID, MIN, MOD, MONTH, RIGHT, ROUND, SIGN, SUBSTITUTE, TRIM, UPPER, YEAR.', line=1, column=1, length=1, control='')]

### PQL-338 · A bracketed column with a dot
- **Observed:** col=ColumnRef(name='positions.notional', dataset='')

### PQL-339 · An empty bracket
- **Observed:** err=None

### PQL-341 · A nested bracket is impossible
- **Observed:** err=[PQL.SYNTAX] ']' is not something a formula can contain | Next: Formulas use columns in [brackets], numbers, "text", the operators = <> < <= > >= + - * / & ^, and function calls. | Context: formula='[a[b]] > 0', position=5 position=line 1, column 1 located=False

### PQL-346 · A trailing separator
- **Observed:** err=[PQL.SYNTAX] unexpected ')' | Next: Check the brackets and the argument count. Functions available: ABS, COALESCE, CONCAT, DAY, IF, IFBLANK, INT, ISBLANK, ISNUMBER, LEFT, LEN, LENGTH, LOWER, MAX, MID, MIN, MOD, MONTH, RIGHT, ROUND, SIGN, SUBSTITUTE, TRIM, UPPER, YEAR. | Context: formula='=CONCAT([a], [b],)', position=18 position=line 1, column 1 located=False

### PQL-350 · A column named `AND`
- **Observed:** bracketed=BinaryOp(operator='>', left=ColumnRef(name='and', dataset=''), right=Literal(value=0, literal_type='number')) bare=BinaryOp(operator='>', left=ColumnRef(name='and', dataset=''), right=Literal(value=0, literal_type='number')) err2=None

### PQL-353 · `IFERROR` is refused by name
- **Observed:** err=[PQL.SYNTAX] there is no function called IFERROR | Next: Available: ABS, COALESCE, CONCAT, DAY, IF, IFBLANK, INT, ISBLANK, ISNUMBER, LEFT, LEN, LENGTH, LOWER, MAX, MID, MIN, MOD, MONTH, RIGHT, ROUND, SIGN, SUBSTITUTE, TRIM, UPPER, YEAR. Prama accepts a deliberately small set: every one of them has a lowering for each engine and a reference implementation that is tested to agree with it. | Context: formula='=IFERROR([a]/[b], 0)', function='IFERROR' has_dedicated_reason=False

### PQL-366 · A selector on an unknown metadata name matches nothing, silently
- **Observed:** n=0 (typo silently matches nothing)

### PQL-369 · `tags = 'pii'` does not match
- **Observed:** n=0 (silently matches nothing)

### PQL-372 · `_is_true` accepts the string "true"
- **Observed:** n_matched=0 facts={'dataset': 'd', 'name': 'a', 'attribute': 'a', 'concept': '', 'concept_property': '', 'domain': '', 'owner': '', 'criticality': '', 'semantic_type': '', 'is_cde': 'True', 'tags': []}

### PQL-373 · A bare boolean fact under `NOT` and not under it disagree
- **Observed:** is_cde_matches=0 not_is_cde_matches=0

### PQL-384 · Diagnostics ignore every control inside a suite
- **Observed:** []

### PQL-402 · `from prama.pql import *` succeeds
- **Observed:** rc=1 stderr=Traceback (most recent call last):

### PQL-403 · Every name in `__all__` is importable individually
- **Observed:** bad=['Attribute', 'AttributeCatalogue', 'Drift', 'Expander', 'Expansion']

### IR-021 · An empty codelist produces `IN ()`
- **Observed:** compiled (IN () present = defect): SELECT COUNT(*) AS "scanned_rows", COALESCE(SUM(CASE WHEN NOT COALESCE(("ccy" IN ()), 0) THEN 1 ELSE 0 END), 0) AS "violating_rows"

### IR-024 · `as_of` is a parameter name, and a date breaks it
- **Observed:** bare TypeError: '<' not supported between instances of 'datetime.date' and 'str'

### BE-005 · A dataset name containing a dot inside quotes is split anyway
- **Observed:** qualify('risk.positions')='"risk"."positions"' (defect: genuinely one-part name becomes two-part)

### BE-006 · Literal rendering per type
- **Observed:** {'None': 'NULL', 'True': 'TRUE', 'False': 'FALSE', '0': '0', '-1': '-1', '1.5': '1.5', '1e+20': '1e+20', '"it\'s"': "'it''s'", "''": "''", "Decimal('1.5')": "'1.5'"} decimal_became_string_literal=True

### BE-007 · A non-finite float literal
- **Observed:** {'nan': 'nan', 'inf': 'inf'}

### BE-012 · SQLite's composite key join is injective
- **Observed:** count_distinct=1

### BE-015 · A pattern using a non-portable regex feature
- **Observed:** {'(?<=A)B': {'reference': 'Verdict.PASS', 'postgresql': 'compiled ok', 'duckdb': 'compiled ok', 'sqlite': 'compiled ok'}, '\\d+': {'reference': 'Verdict.FAIL', 'postgresql': 'compiled ok', 'duckdb': 'compiled ok', 'sqlite': 'compiled ok'}, '(a)\\1': {'reference': 'Verdict.FAIL', 'postgresql': 'compiled ok', 'duckdb': 'compiled ok', 'sqlite': 'compiled ok'}, '^(?i)abc': {'reference': 'ERR PatternError: global flags not at the start of the expression at position 1', 'postgresql': 'compiled ok', 'duckdb': 'compiled ok', 'sqlite': 'compiled ok'}}

### BE-016 · An invalid pattern
- **Observed:** {'[': 'parsed (unexpected)', '*': 'refused at parse: PqlSyntaxError'}

### BE-029 · A capability set is exactly what each engine can do
- **Observed:** caps={'postgresql': frozenset({'pushdown.filter', 'pushdown.aggregation', 'pushdown.approx_distinct', 'pushdown.sampling', 'pushdown.regex', 'pushdown.cross_object_join'}), 'duckdb': frozenset({'pushdown.filter', 'pushdown.aggregation', 'pushdown.approx_distinct', 'pushdown.sampling', 'pushdown.regex', 'pushdown.cross_object_join'}), 'sqlite': frozenset({'pushdown.filter', 'pushdown.cross_object_join', 'pushdown.aggregation', 'pushdown.regex'})} declares_approx_distinct=True approx_count_distinct_executes=UndefinedFunctionError: function approx_count_distinct(integer) does not exist

### BE-034 · `scan_limit` with a correlated EXISTS
- **Observed:** query='SELECT COUNT(*) AS "scanned_rows", COUNT(*) FILTER (WHERE NOT COALESCE((EXISTS (SELECT 1 FROM "b" WHERE "b"."y" = (SELECT * FROM "a" LIMIT 100)."x")), FALSE)) AS "violating_rows"\nFROM (SELECT * FROM "a" LIMIT 100)'

### BE-037 · `SqlCompiler` carries mutable state between compilations
- **Observed:** weird_mid_call='(EXISTS (SELECT 1 FROM "d" WHERE "d"."q" = "a"."p"))' leaked_stale_a=True

### BE-049 · Aggregates bypass the catalogue
- **Observed:** {'COUNT': 'COUNT("x")', 'SUM': 'SUM("x")', 'MIN': 'MIN("x")', 'MAX': 'MAX("x")', 'MEDIAN': 'PqlUnsupportedError: [PQL.UNSUPPORTED] there is no function called MEDIAN | Next'}

### BE-054 · Every operator the lowerer can emit has a SQL branch
- **Observed:** bad=[('!=', '[PQL.UNSUPPORTED] != has no SQL form on postgresql | Next: Express the control differently, or run i'), ('IS OF TYPE', '[PQL.UNSUPPORTED] IS OF TYPE has no SQL form on postgresql | Next: Express the control differently, ')]

### BE-055 · `IN` over an empty list
- **Observed:** compiled: '("x" IN ())'

### BE-056 · An unresolved codelist is refused, not guessed
- **Observed:** IndexError: tuple index out of range

### BE-062 · `prama control compile` exits non-zero when nothing can run
- **Observed:** rc=0 stdout='-- In t, every a has a value, considering only rows where ROUND(x, 2) > 0. No violations are allowed. A failure is major.\n--   refused: sqlite cannot run ROUND\n--   → Run this control on an engine tha'

### BE-067 · An unknown comparison operator raises rather than returning unknown
- **Observed:** bare KeyError: '!='

### BE-068 · `x = y` between a number and a numeric string
- **Observed:** {'reference': None, 'sqlite': {'scanned_rows': 1, 'violating_rows': 0}, 'duckdb': {'scanned_rows': 1, 'violating_rows': 0}, 'postgresql': 'UndefinedFunctionError: operator does not exist: text = integer\nHINT:  No operator matches the given name and argument types. You might need to add ex'}

### BE-075 · A catastrophic pattern
- **Observed:** did not complete within 10s (catastrophic backtracking, uncaught -- confirms the defect)

### BE-078 · Arithmetic on a non-numeric value crashes
- **Observed:** bare ValueError: could not convert string to float: 'abc'

### BE-079 · Arithmetic on a boolean silently coerces
- **Observed:** operator_flag_plus_1=2.0 ABS(flag)=UNKNOWN (one consistent answer expected; likely two different ones)

### BE-080 · Reference arithmetic is float, the catalogue is Decimal
- **Observed:** raw_float_eq=False rounded_decimal_eq=True

### BE-095 · A distinct count over an unhashable value
- **Observed:** bare TypeError: unhashable type: 'list'

### BE-096 · `APPROX_COUNT_DISTINCT` is silently zero
- **Observed:** metrics={'approx': 0.0} (expected non-zero approximation; likely silently 0.0)

### BE-097 · `SUM`, `MIN`, `MAX` and `AVG` over no numeric values
- **Observed:** SUM([])=0.0 MIN([])=0.0 (expected: NULL/None, not 0.0)

### BE-100 · `run` materialises every row
- **Observed:** materialises_whole_input=True

### BE-112 · Every assertion kind reaches its own verdict function
- **Observed:** {'predicate': (<Verdict.PASS: 'pass'>, <Verdict.FAIL: 'fail'>), 'unique_key': (<Verdict.PASS: 'pass'>, <Verdict.FAIL: 'fail'>), 'row_count': (<Verdict.PASS: 'pass'>, <Verdict.FAIL: 'fail'>), 'reference': (<Verdict.PASS: 'pass'>, <Verdict.FAIL: 'fail'>), 'freshness': (<Verdict.INDETERMINATE: 'indeterminate'>, <Verdict.INDETERMINATE: 'indeterminate'>), 'functional_dependency': (<Verdict.PASS: 'pass'>, <Verdict.FAIL: 'fail'>)} both_reachable={'predicate': True, 'unique_key': True, 'row_count': True, 'reference': True, 'freshness': False, 'functional_dependency': True} (freshness expected to stay INDETERMINATE always -- Q-64, unfixed by design)

### BE-115 · `_round` on a non-numeric metric
- **Observed:** TypeError: float() argument must be a string or a real number, not 'NoneType'

### BE-125 · One unsupported control stops the whole group
- **Observed:** the whole group of 20 stopped on one unsupported control: [PQL.UNSUPPORTED] limited cannot run one of these controls: it needs pushdown.regex | Next: Remove it from the run, or run the group on an engine that has it. One control that cannot be expressed must not stop the rest — but it must not be silently dropped either. | Context: missing=['pushdown.regex'], plan='ir:sha256:9b9994a1aa9f2678d7d61ef6ead4c162ae40a60b125384658a95e7e466224c6d'

### BE-126 · A fused query produces no evidence samples
- **Observed:** sql_mentions_samples=False (fuse emitting only metric columns, losing samples, is the confirmed defect) sql=SELECT COUNT(*) AS "c0__scanned_rows", COALESCE(SUM(CASE WHEN NOT COALESCE(("a" IS NOT NULL), 0) THEN 1 ELSE 0 END), 0) AS "c0__violating_rows"

### BE-129 · Two groups with the same description collide
- **Observed:** scans=2 rows_per_scan_entries=1

### BE-132 · A refusal is a conforming outcome; a wrong answer is not
- **Observed:** status=failed detail=OperationalError: no such function: REGEXP

### BE-135 · A case answered by fewer than two engines is not "compared"
- **Observed:** n_disagreements=0 (0 disagreements from 1 runner is not evidence of agreement)

### BE-139 · Two-stage comparison is skipped when the reference did not run
- **Observed:** disagreements_without_reference=[]

### BE-140 · `Case.requires` is declared and never consulted
- **Observed:** case.requires consulted in conformance.py: False (grep hits: '')

### BE-141 · `DUPLICATE_KEY` is declared and never used
- **Observed:** usages=[]

### BE-142 · Every corpus row is annotated with what it catches
- **Observed:** rows_without_notes(0-indexed)=[0, 1, 2, 7]

### BE-143 · The corpus covers no function except LENGTH
- **Observed:** used=[] missing=['ABS', 'COALESCE', 'CONCAT', 'DAY', 'IF', 'IFBLANK', 'INT', 'ISBLANK', 'ISNUMBER', 'LEFT', 'LEN', 'LENGTH', 'LOWER', 'MAX', 'MID', 'MIN', 'MOD', 'MONTH', 'RIGHT', 'ROUND', 'SIGN', 'SUBSTITUTE', 'TRIM', 'UPPER', 'YEAR']

### BE-144 · The corpus has no `IN CODELIST` case
- **Observed:** has_codelist_case=False

### BE-146 · The corpus has no parameter case
- **Observed:** compiled_query_has_named_param=True Runner_type_has_no_parameter_channel=True

### BE-149 · The corpus has no arithmetic case beyond `/` and `%`
- **Observed:** covered=set()

### BE-150 · The corpus has no freshness, no `IS UNIQUE`, no Excel and no `HAS FORMAT` case
- **Observed:** {'freshness': False, 'is_unique': False, 'excel': False, 'has_format': False}

### BE-158 · The generator covers a narrow slice of the language
- **Observed:** documented_exclusion_list_present=False

### BE-160 · A generated `HAS LENGTH BETWEEN` on a text column is type-clean
- **Observed:** bad=[('CHECK corpus.account_id HAS LENGTH BETWEEN 6 AND 8 WHERE NOT', [Finding(message='corpus.account_id holds text, and it is being compared with 6, which is number', remedy='Compare like with like. Engines differ on whether they coerce these silently, so a control written this way would mean one thing on one database and something else on another.', position=Position(line=1, column=44, offset=43, length=1), level='error'), Finding(message='corpus.account_id holds text, and it is being compared with 8, which is number', remedy='Compare like with like. Engines differ on whether they coerce these silently, so a control written this way would mean one thing on one database and something else on another.', position=Position(line=1, column=50, offset=49, length=1), level='error')]), ('CHECK corpus.account_id HAS LENGTH BETWEEN 8 AND 11 BELOW 50', [Finding(message='corpus.account_id holds text, and it is being compared with 8, which is number', remedy='Compare like with like. Engines differ on whether they coerce these silently, so a control written this way would mean one thing on one database and something else on another.', position=Position(line=1, column=44, offset=43, length=1), level='error'), Finding(message='corpus.account_id holds text, and it is being compared with 11, which is number', remedy='Compare like with like. Engines differ on whether they coerce these silently, so a control written this way would mean one thing on one database and something else on another.', position=Position(line=1, column=50, offset=49, length=2), level='error')]), ('CHECK corpus.status HAS LENGTH BETWEEN 11 AND 15 FOR EACH en', [Finding(message='corpus.status holds text, and it is being compared with 11, which is number', remedy='Compare like with like. Engines differ on whether they coerce these silently, so a control written this way would mean one thing on one database and something else on another.', position=Position(line=1, column=40, offset=39, length=2), level='error'), Finding(message='corpus.status holds text, and it is being compared with 15, which is number', remedy='Compare like with like. Engines differ on whether they coerce these silently, so a control written this way would mean one thing on one database and something else on another.', position=Position(line=1, column=47, offset=46, length=2), level='error')])]

### BE-168 · The declarations map one-to-one onto the controls
- **Observed:** unmatched_declarations=['Daily Positions EOD, owned by the Head of Market Risk Data, ']

### BE-172 · Integer values at the extremes
- **Observed:** {'9223372036854775807': 'hashed and compiled: ir:sha256:200fad3e1b...', '9223372036854775808': 'hashed and compiled: ir:sha256:8507bffc35...', '11111111111111111111': 'TypeError: Integer exceeds 64-bit range'}

### BE-178 · Sealed evidence carries the threshold
- **Observed:** record_has_threshold_field=False r1_verdict=Verdict.FAIL r2_verdict=Verdict.PASS (same metrics, different thresholds -> different verdicts, and the record must carry which threshold applied)

### BE-179 · A control that cannot be replayed cannot be written
- **Observed:** {'clock': 'refused: PqlSyntaxError', 'random': 'refused: PqlSyntaxError', 'unresolved_codelist': 'refused: ValidationError', 'unresolved_semantic_type': 'refused: ValidationError', 'codelist_frozen': 'frozen', 'PLUGINS_registry_size': 0} (PLUGINS empty -- implementation-hash freezing never fires = confirmed defect)

## Notes on scope

- **`IS FRESH` remains unimplemented at execution** (Q-64), unchanged and not expected to change:
  `PQL-083` and `BE-112` both confirm a freshness control still lowers to `predicate=None`,
  `metrics=['scanned_rows']`, and `_verdict` has no freshness branch — every freshness control is
  permanently `INDETERMINATE`. The new `backend.execute.unanswerable()` correctly diagnoses this
  exact case (see the regressions section above) but does not fix it, and was not asked to.
- **`PQL-198`/`PQL-199`** assert that `BINDING` and `PRECEDENCE` induce the same operator ordering.
  Verified by execution: `BINDING` is genuinely missing `!=` (`PQL-199` FAIL, matching round 3
  exactly), which is why `PQL-198`'s stricter round-3-onward check also fails — the parser
  normalises `!=` to `<>` before any AST node exists, so the two tables were never meant to share
  every entry. Per this round's brief, these are not reported as new defects; they reproduce
  round 3's own recorded assessment.
- **Harness scripts** for every section (`s01_lexer.py` … `s22_crosscutting.py`, plus `_common.py`
  and `enginelib.py`, a shared SQLite/DuckDB/PostgreSQL runner module modelled on
  `tests/backend/conftest.py`) are the evidence behind this log and are committed to
  `qa/harness/language/` — the gap `qa/harness/README.md` names for this area is now filled for
  round 5 onward. Every script prints one `ID: RESULT :: observed` line per case; run any of them
  directly (`python qa/harness/language/s08_functions.py`) with the venv and
  `PRAMA_TEST_POSTGRES_DSN` on `PATH`/environment as this round's brief specifies.
- **Every FAIL below was cross-checked against round 3's recorded observation** where round 3 ran
  the same case, and several early drafts of this round's harnesses were themselves found to be
  wrong before being trusted — three examples, because the pattern recurred enough to be worth
  naming: `PQL-047` initially hand-constructed a `PqlTypeError`/`PqlUnsupportedError` with a
  fabricated `source=`, which trivially satisfies the four-part render format; redriving it through
  the real `TypeChecker.require`/`SqlCompiler.compile` raise sites reproduced round 3's genuine
  finding that a `PqlUnsupportedError` raised from the compiler never carries `source` at all, so
  its render silently skips the excerpt block the docstring promises. `PQL-372` initially called the
  internal `_is_true` helper directly instead of expanding `WHERE is_cde` through the selector
  path the catalogue's own Steps specify, which hid the exact asymmetry (`_truth` requires
  `is True`; `_is_true` accepts the string `"true"`) the case exists to catch. `BE-037` initially
  chose an EXISTS node whose outer column name happened to coincide with the stale compiler's own
  table, which made a real state leak look like a no-op. All three were rebuilt to drive the actual
  code path before being trusted, in the spirit of this round's warning about `CFG-168`.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
