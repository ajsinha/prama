# Triage: language / IR / backend standing failures

Scope: the 116 cases (51 P1) listed in the round-4 log against `pql/`, `ir/` and
`backend/` — `qa/logs-round4/language.md`, cross-referenced against
`qa/catalogue/language.md` for Precondition/Steps/Expected/Why. Grouped by
**cause**, not by file or keyword, per the brief. 20 clusters cover 63 cases;
47 are genuine one-offs; 4 belong to decisions already made (`Q-64`,
`Q-198/199`); 2 are not defects at all.

---

## 1 · Batches, ordered by (cases closed ÷ effort)

| # | Batch | Cases | P1 | Repairs | Effort | Ratio |
|---|---|---:|---:|---|---|---:|
| C2 | Bare Python exceptions escape instead of a typed Prama error | 11 | 3 | ~9, one shared pattern | small | 5.5 |
| C1 | `reference._arithmetic` uses `float`; `library._number` uses `Decimal` — one interpreter, two arithmetic models | 4 | 3 | 1 | trivial | 4.0 |
| C5 | Excel parser errors never carry a real position | 3 | 1 | 1 | trivial | 3.0 |
| C17 | Corpus/generator/example self-description is dead or incomplete | 5 | 0 | 5 trivial | small | 2.5 |
| C4 | `pql/expand.py` selector matching resolves every internal error to silent non-match | 4 | 1 | 3 | small | 2.0 |
| C6 | Excel bracket/name tokenizer accepts malformed identifiers silently | 2 | 1 | 2 | trivial | 2.0 |
| C7 | An empty codelist compiles to `IN ()`, which no engine parses | 2 | 0 | 1 | trivial | 2.0 |
| C8 | `Lowerer._threshold` builds an incoherent threshold instead of refusing | 2 | 1 | 1 | trivial | 2.0 |
| C11 | `ReferenceEvaluator._aggregate` returns `0.0` instead of `NULL`/refusal | 2 | 0 | 1 | trivial | 2.0 |
| C12 | `HAS LENGTH BETWEEN` on text is a false type error | 2 | 1 | 1 | trivial | 2.0 |
| C13 | `pql.__all__` names five things the module never imports | 2 | 0 | 1 | trivial | 2.0 |
| C15 | `SqlDialect.literal` mishandles `Decimal` and non-finite `float` | 2 | 1 | 2 | trivial | 2.0 |
| C22 | `%g` formatting loses precision on render (two render sites) | 2 | 1 | 1 pattern, 2 sites | trivial | 2.0 |
| C23 | The type checker does not walk every expression-bearing field of a control | 2 | 1 | 1 | trivial | 2.0 |
| C16 | The conformance corpus (`backend/corpus.py::CASES`) has large coverage gaps | 5 | 4 | N (coverage work; 2 need runner changes) | large | 1.25 |
| C9 | `SqlCompiler` carries the current source table as mutable instance state | 2 | 0 | 1 refactor | small | 1.0 |
| C14 | Two disagreeing "non-deterministic function" lists, plus a quoting bug in the same guard | 2 | 1 | 2 | small | 1.0 |
| C18 | No `MATCHES` pattern is ever validated before it is used | 3 | 2 | 2–3 | moderate | 1.0 |
| C19 | `backend/conformance.py` mistakes absence of evidence for agreement, in three places | 3 | 3 | 3 | moderate | 1.0 |
| C20 | Unbounded recursion crashes instead of a bounded refusal | 3 | 0 | 3 | moderate | 1.0 |

**Total closed if every batch lands: 63 cases (24 P1).** Add the 47 one-offs
(22 P1) and the realistic total is discussed in §5.

---

## 2 · Batch detail

### C2 — Bare Python exceptions escape instead of a typed Prama error
**Cases (11, 3 P1):** `PQL-035`(P2), `PQL-036`(P1), `PQL-037`(P2, partial),
`PQL-089`(P2), `PQL-280`(P2), `BE-056`(P2), `BE-067`(P1), `BE-095`(P3),
`BE-115`(P2), `IR-024`(P1), `BE-172`(P2)

**What's wrong.** Nine call sites across the lexer, parser, lowerer, SQL
compiler, reference interpreter and content-hashing let a raw `AssertionError`,
`ValueError`, `KeyError`, `IndexError` or `decimal.InvalidOperation` propagate
out of library code instead of being caught and re-raised as the typed
taxonomy (`PqlSyntaxError`/`PqlTypeError`/`PqlUnsupportedError`) or turned into
an `UNKNOWN` result. This is the same class the brief calls out by name —
smaller here (11 cases, not 33) but the identical shape: a systemic habit, not
a shared function.
- `PQL-035`+`PQL-036` are the *same* defect: `Lexer._word` asserts
  `match is not None` for a non-ASCII letter (`character.isalpha()` is
  Unicode-aware, `_IDENTIFIER` is ASCII-only), reached both by tokenising `é`
  directly (`PQL-036`) and by parsing `CHECK t.montànt IS NOT NULL`
  (`PQL-035`). One fix (raise `PqlSyntaxError` instead of asserting) closes
  both. `PQL-037` reaches the *same* assertion on the **re-parse** half of a
  round-trip test (the renderer apparently decides a non-ASCII name doesn't
  need quoting, so the bare form is re-tokenised and hits the same assert) —
  fixing the lexer closes the crash, but `PQL-037` will only fully pass once
  the render-side quoting decision is also checked for non-ASCII, so file it
  as "same root cause, one extra follow-up."
- `PQL-089`: `Parser._integer` calls `int(token.text)` on `"1e6"` — bare
  `ValueError`.
- `PQL-280`: `_round_half_up`'s `Decimal.quantize` raises
  `decimal.InvalidOperation` for `ROUND(1.5, 40)` — bare, mid-row.
- `BE-056`: `SqlCompiler._operation` reads `node.args[1].value` for an
  unresolved codelist before checking arity — bare `IndexError`.
- `BE-067`: `reference._compare`'s operator dict raises `KeyError` for `!=`
  (what the Excel parser actually produces).
- `BE-095`: `reference._distinct`'s `seen.add(value)` raises `TypeError` for
  an unhashable (list) column value — exactly where the reference interpreter
  is the engine of last resort (REST/JSON sources).
- `BE-115`: `execute._round` does `float(None)` for a driver-returned `NULL`
  metric — bare `TypeError`.
- `IR-024`: `resolved()` accepts a `date` object for `as_of` (a parameter
  *name* field typed as `str`); `ControlPlan.parameters()` puts it in a set of
  strings and `compile`'s `sorted()` raises `TypeError` comparing `str` and
  `date`.
- `BE-172`: a 100-digit integer threshold raises `TypeError: Integer exceeds
  64-bit range` out of `content_hash`, uncaught.

**One repair or N?** N — nine distinct call sites (ten counting `PQL-037`'s
follow-up), each a small, mechanical try/raise-typed-error fix. Not one PR,
but one focused sweep with a well-understood pattern; the biggest win here is
recognizing them as one class rather than fixing them piecemeal as unrelated
crashes across five files.

**Defect or decision?** All defect.

**Counterfactual.** For `BE-067`: a test that calls `_compare("!=", 1, 2)` and
asserts it does *not* raise `KeyError` fails today (it raises) and passes once
`_compare` maps unknown operators to a typed refusal. A careless version of
this test would just wrap the call in `pytest.raises(Exception)` — that
passes today *and* after, because it never distinguishes "crashed" from
"refused cleanly," which is the entire point of the fix.

---

### C1 — `reference._arithmetic` uses `float`; `library._number` uses `Decimal`
**Cases (4, 3 P1):** `PQL-300`(P1), `BE-078`(P1), `BE-079`(P2), `BE-080`(P1)

**What's wrong.** The reference interpreter has two independent numeric
coercion paths for the same language: `pql/library.py::_number` (used by
function calls like `ROUND`) converts to `Decimal` specifically because, per
its own docstring, "a reconciliation that summed in binary floating point
would manufacture exactly the small discrepancies it exists to detect."
`backend/reference.py::_arithmetic` (used by the `+ - * /` operators) instead
does `float(x)`. One interpreter, two arithmetic models, and every symptom
traces to that one split:
- `PQL-300` catches it directly: `0.1 + 0.2` via the operator gives
  `0.30000000000000004`; via a catalogue function gives `Decimal('0.3')`.
- `BE-080` catches the same split from the other side: `(a+b)=c` disagrees
  with `ROUND(a+b,2)=c` over the same values.
- `BE-079` is a second consequence of the same `float()` call:
  `float(True) == 1.0`, so the operator path silently treats a boolean as a
  number, while `_number` deliberately refuses one.
- `BE-078` is a third consequence: `float("abc")` raises a bare `ValueError`
  (this case also belongs to C2's shape, but the actual fix is the same one
  as the other three — replace the ad hoc `float()` coercion with the shared
  `_number`-style conversion, which already returns `UNKNOWN` for
  non-numeric input instead of crashing).

**One repair or N?** One: make `reference._arithmetic` delegate to (or mirror)
`library._number`'s conversion instead of maintaining its own. This is a
concrete instance of the design doctrine already written down in
`CLAUDE.md` — "derive, never restate" — restated as two arithmetic models
that have already drifted.

**Defect or decision?** Defect — the library's own docstring states the
*intended* model (`Decimal`) and the interpreter's operator path just never
adopted it.

**Counterfactual.** A test that evaluates `0.1 + 0.2 = 0.3` through the `+`
operator and asserts the result equals the `Decimal` sum fails today (float
noise) and passes after unification. A careless version would round both
sides to the same number of places before comparing — that passes today too,
because rounding hides exactly the discrepancy the fix is about.

---

### C5 — Excel parser errors never carry a real position
**Cases (3, 1 P1):** `PQL-335`(P1), `PQL-341`(P3), `PQL-346`(P2)

**What's wrong.** Every `raise` in `pql/excel.py` passes the character offset
in `context=` but never in `position=`, so `PqlError.position` defaults to
line 1, column 1. `PQL-335` states this as the general finding; `PQL-341`
(nested bracket) and `PQL-346` (trailing separator in a call) are two
concrete instances of the same defect — both observed results explicitly
show `located=False` with `position=line 1, column 1` regardless of where the
real error is. `pql/analysis.py::_from_error` then reports line 1 to the
editor, which the module's own rule calls worse than reporting nothing.

**One repair or N?** One — thread the computed offset into `position=` at the
error-construction site(s) in `ExcelParser._error`.

**Defect or decision?** Defect, and a real regression risk: this file feeds
both the CLI and the language-server diagnostics path.

**Counterfactual.** A test that parses a malformed formula with the error 20
characters in and asserts `error.position.column != 1` fails today (always 1)
and passes once `_error` carries the real offset. A careless version would
just assert `position is not None` — that passes today too, since a
`Position(line=1, column=1)` object already exists, just a wrong one.

---

### C4 — `pql/expand.py` selector matching resolves every internal error to silent non-match
**Cases (4, 1 P1):** `PQL-366`(P1), `PQL-369`(P2), `PQL-372`(P2), `PQL-373`(P2)

**What's wrong.** Selector expansion (`CHECK EVERY ATTRIBUTE WHERE …`) treats
every kind of internal trouble as "no match," never as a warning or refusal —
the exact inverse failure mode of C2 (there, errors crash; here, they vanish):
- `PQL-366`: an unknown metadata name (a typo) makes `facts.get(name)` return
  `None`; every comparison against `None` is `False`, so the whole selector
  silently expands to zero controls.
- `PQL-369`: `tags = 'pii'` compares a `list` with a `str`; `_binary` builds
  the comparison eagerly, the `TypeError` is caught, and the catch turns into
  `False` — so a real tag never matches.
- `PQL-372` and `PQL-373` are the *same* defect seen twice: `_truth` requires
  `value is True` (strict) while `_is_true` accepts the case-insensitive
  string `"true"` (loose) — so `WHERE is_cde` and `WHERE NOT is_cde` can
  **both** exclude the same attribute when its value arrived from a warehouse
  as text. `PQL-372` asserts the loose acceptance directly; `PQL-373` asserts
  the resulting asymmetry. One fix (make `_truth` and `_is_true` agree)
  closes both.

**One repair or N?** Three, not one: (a) unify `_truth`/`_is_true`
(`PQL-372`+`PQL-373`), (b) make `_value` surface an unrecognized fact name
instead of swallowing it (`PQL-366`), (c) make `_binary` raise or refuse a
type-incompatible comparison instead of catching `TypeError` into `False`
(`PQL-369`). All three are the same *policy* fix, though — "ambiguity in
selector evaluation must be visible, never a silent zero" — so they belong in
one PR even though they touch three functions.

**Defect or decision?** Defect. `PQL-366` is the highest-value single case in
this cluster: a typo'd selector currently produces an estate that looks
covered and covers nothing, with no error anywhere.

**Counterfactual.** A test that expands `WHERE is_cdee` (typo) against a
five-attribute catalogue and asserts a `Finding`/refusal exists fails today
(silently 0 controls, no diagnostic) and passes once `_value` flags unknown
names. A careless version would assert `len(expanded) == 0` — that passes
today for the wrong reason (silent failure looks identical to "correctly
matched nothing").

---

### C6 — Excel bracket/name tokenizer accepts malformed identifiers silently
**Cases (2, 1 P1):** `PQL-338`(P1), `PQL-339`(P2)

**What's wrong.** Two different regex gaps in the same tokenizing area, both
producing a `ColumnRef` that cannot possibly resolve, with no error at parse
time: `PQL-338`'s bare `name` pattern (`[A-Za-z_][A-Za-z0-9_.]*`) swallows the
dot in `positions.notional`, producing one column literally named
`"positions.notional"` instead of `dataset="positions", name="notional"`.
`PQL-339`'s empty-bracket case (`[]`) strips to `""` and produces a
`ColumnRef` with an empty name.

**One repair or N?** Two — different regexes, same file/method
(`ExcelParser.primary`/`_TOKEN`), naturally one PR.

**Defect or decision?** Defect, both.

**Counterfactual.** For `PQL-338`: a test parsing `=positions.notional > 0`
and asserting `ColumnRef(name="notional", dataset="positions")` fails today
(`name="positions.notional"`) and passes once the dot splits the token. A
careless version would only assert `col.name.endswith("notional")` — passes
either way.

---

### C7 — An empty codelist compiles to `IN ()`, which no engine parses
**Cases (2, 0 P1):** `IR-021`(P2), `BE-055`(P2)

**What's wrong.** `BE-055`'s own catalogue entry says it plainly: "the only
way to produce it is an empty codelist" — `IR-021` is that exact scenario.
The hand-written `IN ('a','b')` case is refused by the parser ("an empty set
fails every row"); the codelist path has no equivalent guard, so
`Lowerer._codelist` (or `SqlCompiler.expression`) happily emits `IN ()`.

**One repair or N?** One — refuse an empty codelist at the point it is
resolved, matching the parser's existing behavior for a literal empty list.

**Defect or decision?** Defect.

**Counterfactual.** A test that registers a codelist with zero values, lowers
a control against it, and asserts compilation refuses (rather than emitting
SQL) fails today (`IN ()` is emitted) and passes after. A careless version
would only check that the SQL *string* doesn't contain `"IN ()"` — a fix that
swaps to `IN (NULL)` or `1=0` would satisfy that check without actually
refusing, which is not what the parser does for the hand-written case.

---

### C8 — `Lowerer._threshold` builds an incoherent threshold instead of refusing
**Cases (2, 1 P1):** `PQL-150`(P1), `PQL-151`(P2)

**What's wrong.** `_threshold` only special-cases `rate`/`percent`;
everything else — including a currency amount (`WITHIN 100 USD`) — becomes
`Threshold(metric="violating_rows", value=100.0)` with the currency silently
discarded (`PQL-150`). Symmetrically, when a rate threshold is attached to an
assertion whose metrics don't include the denominator it needs (row-count
assertions only emit `scanned_rows`), lowering doesn't refuse — the parser's
own module docstring says this combination should be refused at authoring
time, and it silently becomes `INDETERMINATE` instead (`PQL-151`). Both are
the same shape: `_threshold`/`_metrics` accepts an assertion/threshold
combination it cannot represent instead of refusing it.

**One repair or N?** Likely one: add a coherence check in `_threshold` (or
`_metrics`) — refuse a non-percent unit that isn't `rows`/`violating_rows`,
and refuse a rate threshold when the assertion has no rate metric.

**Defect or decision?** Defect. `PQL-151` is explicitly named in the parser's
own docstring as something that should already be refused.

**Counterfactual.** A test that lowers `CHECK t.a IS NOT NULL WITHIN 100 USD`
and asserts a refusal (not a silently-substituted row-count threshold) fails
today and passes after. A careless version would just assert
`threshold.value == 100.0` — passes today too, since the number survives;
only the *meaning* (rows vs. currency) is wrong.

---

### C9 — `SqlCompiler` carries the current source table as mutable instance state
**Cases (2, 0 P1):** `BE-034`(P2), `BE-037`(P2)

**What's wrong.** `self._source` is written by `compile`/`metric_sql` and read
by `_exists`, rather than threaded through as a parameter. Two independent
symptoms follow directly from that design: with `scan_limit` set, `_exists`
renders `(SELECT * FROM "t" LIMIT 100)."col"` — syntactically invalid on
every engine, because the "source" is the whole limited subquery text, not a
table reference (`BE-034`). And because `Fuser._empty_group` calls
`expression()` without ever setting `_source`, a filter containing an
`EXISTS` gets compiled against whatever table was compiled last —
demonstrated directly in the observed text ("`leaked_stale_a=True`")
(`BE-037`).

**One repair or N?** One architectural fix — stop storing `_source` on
`self`; pass it explicitly to whatever needs it. Both symptoms disappear
together.

**Defect or decision?** Defect, and the concurrency-flavored one (`BE-037`) is
the kind of bug `CLAUDE.md`'s "concurrency is structured" rule exists to
prevent, even though `SqlCompiler` itself isn't threaded — a shared compiler
instance reused across calls has the same shape as shared mutable state
across a task group.

**Counterfactual.** A test that compiles control A, then calls `expression()`
directly on an unrelated filter containing an `EXISTS`, then asserts the
`EXISTS` references its *own* table (not A's) fails today and passes once
`_source` stops being instance state. A careless version would only test
sequential *compiles* of unrelated controls, never an interleaved
`expression()` call — which is exactly how round 3 apparently missed this,
per the round-4 methodology note about `BE-037`'s first draft.

---

### C11 — `ReferenceEvaluator._aggregate` returns `0.0` instead of `NULL`/refusal
**Cases (2, 0 P1):** `BE-096`(P2), `BE-097`(P2)

**What's wrong.** Two different empty-value defaults in the same function.
`_metrics` sends `APPROX_COUNT_DISTINCT` to `_aggregate`, whose dict has no
entry for it, so the lookup's default (`0.0`) is returned as if it were a
real approximation (`BE-096`). Separately, `SUM`/`MIN`/`MAX`/`AVG` over no
numeric values *also* return `0.0` in `_aggregate` itself, when SQL's own
answer for `SUM`/`MIN`/`MAX` of zero rows is `NULL`, and "a sum of zero and a
sum of nothing are different facts" per the catalogue (`BE-097`).

**One repair or N?** Likely one pass over `_aggregate`: change the
missing-function default from `0.0` to a refusal, and change the
no-numeric-values default from `0.0` to `None`/`NULL`.

**Defect or decision?** Defect.

**Counterfactual.** A test that runs `SUM` over a scope with zero numeric
rows and asserts the metric is `None` (not `0.0`) fails today and passes
after. A careless version would assert `metric in (0.0, None)` — passes
either way, which erases exactly the distinction the case exists to make.

---

### C12 — `HAS LENGTH BETWEEN` on a text column is a false type error
**Cases (2, 1 P1):** `PQL-092`(P1), `BE-160`(P2)

**What's wrong.** `TypeChecker._check_predicate` skips the
subject-vs-argument type comparison for `in_codelist`, `is_valid`,
`has_format` and `matches` — but not for `has_length_between`. So a control
this ordinary — `CHECK t.isin HAS LENGTH BETWEEN 12 AND 12` — is flagged as
comparing text with number, on every text column, always. `PQL-092` catches
this directly by type-checking the control. `BE-160` catches the *identical*
defect as a side effect of type-checking the corpus generator's own output —
same error message, same missing-exemption cause, confirmed by comparing both
Observed texts (`"holds text, and it is being compared with 12, which is
number"` vs. the generator's `"holds text, and it is being compared with 6,
which is number"`).

**One repair or N?** One — add `has_length_between` (and check whether
`has_length` needs the same treatment) to `_check_predicate`'s exemption
list.

**Defect or decision?** Defect. This is a real false positive on one of the
most ordinary controls in the language.

**Counterfactual.** A test that type-checks `CHECK t.isin HAS LENGTH BETWEEN
12 AND 12` against a schema declaring `isin` as text and asserts zero
findings fails today (two spurious findings) and passes after. A careless
version would assert `len(findings) < 2` — passes today too if only one of
the two bound comparisons is exempted by mistake.

---

### C13 — `pql.__all__` names five things the module never imports
**Cases (2, 0 P1):** `PQL-402`(P2), `PQL-403`(P2)

**What's wrong.** `pql/__init__.py::__all__` lists `Attribute`,
`AttributeCatalogue`, `Drift`, `Expander`, `Expansion` — none of which the
module actually imports. `PQL-402` catches it via `from prama.pql import *`
raising `AttributeError`; `PQL-403` catches the identical cause via
`getattr(prama.pql, name)` on each entry. One fix closes both.

**One repair or N?** One, but it requires a decision first: are these five
names meant to be public? If yes, import them; if no, remove them from
`__all__`. Either way it's a single edit to `pql/__init__.py`.

**Defect or decision?** Defect (a broken contract either way — the
current state is neither "exported" nor "not listed," it's both at once).

**Counterfactual.** `from prama.pql import *` in a fresh interpreter fails
today with `AttributeError` and succeeds after. A careless version of this
test would `try/except ImportError` around the whole star-import and treat
any success as pass — that's the actual test here, so there isn't a weaker
version worth naming; the risk is the opposite direction (asserting only
`Expander` importable and missing the other four).

---

### C15 — `SqlDialect.literal` mishandles `Decimal` and non-finite `float`
**Cases (2, 1 P1):** `BE-006`(P1), `BE-007`(P2)

**What's wrong.** Two gaps in one method. `isinstance(value, int | float)`
excludes `Decimal`, so an exact monetary value falls through to the string
branch and is emitted as the *text* literal `'1.5'` instead of a number
(`BE-006`) — a silent type change directly in a money comparison. Separately,
`repr(float("inf"))` is the Python string `"inf"`, which is not valid SQL on
any of the three engines, and nothing guards non-finite floats (`BE-007`).

**One repair or N?** Two edits, same method, naturally one PR: widen the
numeric branch to include `Decimal`, and add a finite-check (refuse or emit
the engine's NaN/Infinity spelling) for `float`.

**Defect or decision?** Defect, both — `BE-006` especially, since
`Decimal` is exactly what money is represented as elsewhere in this codebase.

**Counterfactual.** A test that renders `dialect.literal(Decimal("1.5"))`
against PostgreSQL and asserts the result is numeric SQL (not a quoted
string) fails today (`'1.5'`) and passes after. A careless version would
assert `"1.5" in rendered` — passes either way, string or number.

---

### C22 — `%g` formatting loses precision on render (two render sites)
**Cases (2, 1 P1):** `PQL-141`(P1), `PQL-209`(P2)

**What's wrong.** The same formatting mistake in two different `render()`
methods: `ast.Threshold.render` uses `f"{value:g}"` for a row-count bound
(six significant figures — `1234567` renders as `1.23457e+06` and re-parses
as `1234570`), and `ast.Literal.render` uses `f"{value*100:g}"` for a
percentage (`0.001234567` renders as `0.123457%` and re-parses losing
precision). Same root technique, two call sites.

**One repair or N?** One pattern (use a format that preserves full precision,
e.g. `repr()`-based or an explicit high-precision spec) applied at both call
sites.

**Defect or decision?** Defect. Both are formatter-silently-changes-meaning
bugs — exactly the class `prama control format --write` would commit to disk.

**Counterfactual.** A test that parses `AT MOST 1234567 ROWS`, renders it,
re-parses, and asserts the value is unchanged fails today (`1234570`) and
passes once `:g` is replaced. A careless version would only test round-trip
on a *small* value (e.g. `5`) — six-figure `:g` formatting is invisible below
a million, so that test would pass both today and after, for the wrong
reason.

---

### C23 — The type checker does not walk every expression-bearing field of a control
**Cases (2, 1 P1):** `PQL-241`(P1), `PQL-242`(P2)

**What's wrong.** `TypeChecker._type_check` calls `_check_expression` on
`control.where` only, so a `SATISFIES` condition — the surface an Excel
formula lands on — is never type-checked at all (`PQL-241`). Separately,
`_expressions_of` (which drives function-name/arity checking) walks `where`
plus four assertion attributes, but not `segmentation.having`, so `HAVING
NONSENSE(b) > 1` never gets a "no function called NONSENSE" finding even
though `_columns_of` *does* resolve `having`'s columns (`PQL-242`). Both are
the same structural gap: the module has no single canonical list of "every
expression location on a Control," so type-checking and function-checking
each maintain their own, and neither is complete.

**One repair or N?** One, in spirit — introduce a shared
`all_expressions_of(control)` helper and drive both `_type_check` and
`_expressions_of` from it, rather than each hand-listing locations. This is
the same "derive, never restate" pattern as C1.

**Defect or decision?** Defect.

**Counterfactual.** A test that type-checks `CHECK t SATISFIES notional >
'ACTIVE'` against a schema and asserts a finding (mismatched types) fails
today (zero findings) and passes after `_type_check` covers assertion
conditions. A careless version would test only `WHERE`-clause type errors
(which already work) and never construct a `SATISFIES`-only control — which
is exactly how this gap stayed invisible.

---

### C16 — The conformance corpus (`backend/corpus.py::CASES`) has large coverage gaps
**Cases (5, 4 P1):** `BE-143`(P1), `BE-144`(P1), `BE-146`(P1), `BE-149`(P2),
`BE-150`(P1)

**What's wrong.** The three-way (SQLite/DuckDB/PostgreSQL/reference)
conformance corpus is much smaller than the language it's meant to guard: 24
of 25 catalogue functions appear in **no** end-to-end case (`BE-143`); there
is no `IN CODELIST` case, and adding one requires a runner change because
`ConformanceRun.plan_for` builds a bare `Lowerer()` with no codelists
(`BE-144`); there is no parameter case, and adding one requires a runner
change because named-parameter binding differs across `sqlite3`/`duckdb`/
`psycopg` and nothing in the gate ever binds one (`BE-146`); arithmetic
coverage stops at `/` and `%` (`BE-149`); and freshness, `IS UNIQUE`, Excel
and `HAS FORMAT` have no case at all — which is exactly why `IS UNIQUE`
lowering to a null check, `HAS FORMAT` having no SQL form (see `BE-054`), and
Excel's `<>` producing an uncompilable operator were all invisible until this
round (`BE-150`).

**One repair or N?** N, and larger than the other batches: three of the five
(`BE-143`, `BE-149`, `BE-150`) are pure content — new `CASES` entries. Two
(`BE-144`, `BE-146`) additionally need `ConformanceRun`/`plan_for` changed to
accept codelists and to bind named parameters before a case can even be
added. Budget this as a small project, not a PR.

**Defect or decision?** Defect (a real, load-bearing coverage gap), but
closing it is test-authoring work, not a bug fix — closer in spirit to the
corpus work the round-4 harness scripts themselves represent than to a code
change. Worth sequencing after the higher-ratio batches above, not instead of
them.

**Counterfactual.** For `BE-144`: a corpus case exercising `IN CODELIST
iso4217` that runs and agrees across all three engines fails to exist today
(cannot even be added without a runner change) and exists after. A careless
version of "fixed" would add the case only for the reference interpreter,
skipping the two engines it can't yet run against — which would look like
coverage without actually being conformance-tested.

---

### C17 — Corpus/generator/example self-description is dead or incomplete
**Cases (5, 0 P1):** `BE-140`(P2), `BE-141`(P3), `BE-142`(P2), `BE-158`(P2),
`BE-168`(P2)

**What's wrong.** Five small, independent pieces of metadata that describe
the test infrastructure to itself have gone stale: `Case.requires` is
declared ("capabilities without which an engine may legitimately refuse this
case") and never consulted, so a refusal is accepted from any engine for any
case (`BE-140`); `DUPLICATE_KEY` is declared with its own reasoning comment
and never used, while the case it should back restates the columns by hand
(`BE-141`); corpus rows 0, 1, 2 and 7 have no `ROW_NOTES` entry, so nothing
stops a future edit from silently deleting whichever one mattered (`BE-142`);
`ControlGenerator`'s coverage exclusions (no `MATCHES`, `IN CODELIST`,
`REFERENCES`, functions, arithmetic, parameters, multi-column segmentation)
are nowhere written down (`BE-158`); and `backend/example.py`'s seven
declarations don't map one-to-one onto the controls that are supposed to
quote them (`BE-168`).

**One repair or N?** Five small, independent edits — none is more than a
constant, a docstring, or a dict entry. Good candidate for one cleanup pass
even though the causes are distinct, purely because each is cheap.

**Defect or decision?** Documentation debt, not runtime defects — except
`BE-140`, where "consulted" means real logic (deciding which refusals are
legitimate), not just a comment.

**Counterfactual.** For `BE-142`: a test asserting every entry in `ROWS` has
a corresponding `ROW_NOTES` entry fails today (4 missing) and passes once
they're filled in. A careless version would assert `len(ROW_NOTES) > 0` —
passes today already.

---

### C18 — No `MATCHES` pattern is ever validated before it is used
**Cases (3, 2 P1):** `BE-015`(P1), `BE-016`(P1), `BE-075`(P2)

**What's wrong.** Three distinct gaps, one shared absence: nothing validates
a regex pattern before it reaches a per-row evaluation or a compiled engine.
`BE-016`: a malformed pattern (`[`) is silently accepted at parse time — only
`re.compile` inside the reference interpreter, or the engine itself at
execution, will ever notice. `BE-015`: a pattern using a non-portable feature
(lookbehind, backreference, an inline flag mid-pattern) compiles fine on
every engine but the *reference* disagrees with SQLite/DuckDB/PostgreSQL on
what it matches, because RE2 and POSIX support a different feature set than
Python's `re` — so the same control matches different rows on different
engines, silently. `BE-075`: a catastrophic pattern (`(a+)+b` against 40
`a`s) doesn't complete in Python's backtracking engine, a denial-of-service
against the interpreter reachable from an authored control.

**One repair or N?** Two to three: a syntax-validity check (closes `BE-016`)
and a portability check against the target dialect's regex flavour (closes
`BE-015`) can share one validation gate called from wherever `MATCHES`
patterns are accepted. `BE-075` is harder — static ReDoS detection is not
reliable — and more likely needs a runtime guard (timeout/executor bound)
than a "fix," so budget it separately even inside this batch.

**Defect or decision?** Defect, all three — though `BE-075`'s remedy is
mitigation, not correctness.

**Counterfactual.** For `BE-016`: a test that authors `MATCHES /[/` and
asserts a `PqlSyntaxError` at parse time (not at row-evaluation or engine
execution time) fails today (`'[' parses fine) and passes once a validation
gate exists. A careless version would just assert the control eventually
raises *somewhere* in the pipeline — passes today too, at the wrong, much
later, less useful point.

---

### C19 — `backend/conformance.py` mistakes absence of evidence for agreement
**Cases (3, 3 P1):** `BE-132`(P1), `BE-135`(P1), `BE-139`(P1)

**What's wrong.** Three different functions in one file, each confusing "we
didn't get an answer" with "we got the right answer" — the conformance
harness's whole reason to exist:
- `BE-132`: SQLite lacking a `REGEXP` hook raises `OperationalError`, which
  `run_case` reports as `status=failed` when the catalogue's own contract
  says an engine that legitimately cannot run a case should report `refused`
  — "that distinction is the entire value of the exercise," per the
  catalogue.
- `BE-135`: `compare()` builds a set of distinct answers; a single answer
  from a single engine is trivially "unanimous," so a case only the
  reference interpreter could run is counted as agreement rather than as
  compared-by-fewer-than-two.
- `BE-139`: `_compare_two_stage` returns `[]` — no disagreements — whenever
  the reference interpreter didn't run, which excuses the two-stage
  comparison (the product's actual thesis) from ever running at all in that
  case, silently.

**One repair or N?** Three — different functions, different specific logic,
no shared helper today. All three fit the same acceptance criterion, though:
"a comparison must require at least two real answers before it can report
agreement," so review them together.

**Defect or decision?** Defect, all three, and high-value: this is the
harness that all the other conformance findings (`BE-143`–`BE-150`, etc.)
depend on for their own trustworthiness.

**Counterfactual.** For `BE-135`: a run where only the reference answers a
case, then a test asserting `cases_compared` for that case is `0` (not
counted as agreement) fails today and passes once `compare()` requires ≥2
answers. A careless version would assert `disagreements == []` — passes
today too, since "no disagreements" is exactly the misleading signal the
case exists to catch.

---

### C20 — Unbounded recursion crashes instead of a bounded refusal
**Cases (3, 0 P1):** `PQL-175`(P2), `PQL-176`(P2), `PQL-177`(P3)

**What's wrong.** Three different recursive routines, each with no depth
bound, each producing a bare `RecursionError` traceback for a legitimate-if-
large input reachable from an HTTP endpoint: `Parser._expression`/`_primary`
on 1,000+ nested parentheses (`PQL-175`); `Expr.requires`/`columns()`
recursing over a 1,000-term left-leaning `OR` tree once per call, even though
the parse loop itself is iterative (`PQL-176`); and the SQL compiler's
composite-key building (SQLite's `CHAR(31)`-separated concatenation, DuckDB's
struct, PostgreSQL's row constructor) over 500 columns (`PQL-177`).

**One repair or N?** Three — different functions in different files, no
single shared traversal to fix. Same *class* of defect throughout, though:
recursive descent / recursive tree-walk / recursive SQL-building with no
depth limit, matching `PQL-175`'s own catalogue note that Q-23 already
recorded a sibling case (`orjson`'s recursion limit producing a 500).

**Defect or decision?** Defect, all three.

**Counterfactual.** For `PQL-176`: a test that compiles a `WHERE` clause with
1,000 `OR` terms and asserts it completes (or is refused with a located
error) rather than raising fails today (bare `RecursionError`) and passes
once `Expr.requires`/`columns()` become iterative or gain an explicit depth
guard. A careless version would test only 100 terms — Python's default
recursion limit (1000) comfortably survives that, so the test would pass
today for the wrong reason (input too small to trigger the defect).

---

### C14 — Two disagreeing "non-deterministic function" lists, plus a quoting bug in the same guard
**Cases (2, 1 P1):** `PQL-181`(P1), `PQL-182`(P3)

**What's wrong.** `pql/parser.py::NON_DETERMINISTIC` (10 names) and
`pql/functions.py::VOLATILE` (6 names) overlap in exactly one name (`NOW`).
Confirmed by execution: `TODAY()`, `RANDBETWEEN(1,2)`, `INDIRECT('a')` and
`OFFSET(a,1,1)` all parse in PQL when they should be refused for replay
safety, later failing as an unlocated `ValidationError` instead of a clean
syntax refusal (`PQL-181`) — this half of the finding is confirmed. The
catalogue's companion claim, that the Excel surface silently turns
`CURRENT_DATE`/`SYSDATE`/`UUID` into column references, is **not** confirmed:
round 4's own observation shows all three correctly refused as "no function
called X" (Excel simply never defines them). Separately, `PQL-182`: the
`NON_DETERMINISTIC` guard in `Parser._identifier_expression` compares
`token.value` rather than checking whether the token was quoted, so a real
column *named* `current_date` cannot be checked at all, even quoted — the
escape hatch that exists for exactly this situation doesn't escape this
guard.

**One repair or N?** Two changes, same area (`Parser._identifier_expression`
and the two list constants), reasonably one PR: unify or reconcile
`NON_DETERMINISTIC`/`VOLATILE` on the PQL side, and make the guard check
token kind (quoted vs. bare) instead of raw text.

**Defect or decision?** Defect on the PQL-side list gap and the quoting bug.
The Excel-side half of `PQL-181`'s catalogue prediction did not reproduce —
note that when writing this up, don't claim it as confirmed.

**Counterfactual.** A test that parses `CHECK t.a > TODAY()` and asserts a
refusal at parse time fails today (parses fine, fails later unlocated) and
passes once `NON_DETERMINISTIC` includes it. A careless version would assert
only that evaluating the compiled control eventually errors somewhere — true
today already, just far too late and unlocated to be useful.

---

## 3 · Not a defect

- **`PQL-083`, `BE-112` → already decided (`Q-64`).** Both are the freshness
  execution gap: `PQL-083` catches it at the lowering/judging boundary
  directly; `BE-112` catches the identical fact while checking that every
  assertion kind reaches its own verdict function ("`freshness` expected to
  stay `INDETERMINATE` always — Q-64, unfixed by design," per its own
  Observed text). Neither is a new finding.

- **`PQL-198`, `PQL-199` → already decided.** `BINDING` and `PRECEDENCE`
  never shared an alphabet by design — the parser normalises `!=` to `<>`
  before any AST node exists. Round 4 reconfirms round 3's own assessment
  verbatim; these are not new defects and shouldn't be re-litigated.

- **`PQL-350` — the catalogue's own predicted defect did not reproduce.**
  Precondition: a column literally named `and`. Expected (per the catalogue,
  itself flagged as a prediction rather than a confirmed fact): the bracketed
  form `[and]` works and the bare form `and > 0` is misread as an operator.
  Observed: **both** forms parse correctly to
  `BinaryOp(operator='>', left=ColumnRef(name='and'), ...)`, with no error.
  The round-4 harness marked this FAIL only because the observed behaviour
  doesn't match the catalogue's predicted defect — but the actual behaviour
  is fine. Nothing to fix; close as "verified, not a defect."

- **`PQL-001` — likely a test-probe artifact, not a code defect.** The case
  asserts one token of each of nine kinds appears when tokenising `CHECK
  t."odd name" MATCHES /^A/ AND n > $d, 1.5e3 -- tail`. That probe string
  contains a double-quoted *identifier* (`"odd name"`) but no single-quoted
  *string literal* — and PQL string literals are single-quoted (as in
  `BECAUSE '…'`, used correctly elsewhere in this same log). `STRING` not
  appearing in the token stream is exactly what a probe with no string
  literal in it should produce, lexer bug or not. Before treating this as a
  defect, re-run with a probe that includes `BECAUSE 'x'` or similar; if
  `STRING` still doesn't appear, only then is it real.

---

## 4 · Genuinely one-off (47 cases, 22 P1)

Each of the following needs its own, unrelated repair. Grouped below only by
subsystem for readability — this is *not* a proposed batching, per the
brief's own warning against grouping by module.

**AST render / round-trip (each a distinct bug in `ast.py`):**
`PQL-128` (P2, `OWNER` apostrophe not escaped, unlike `BECAUSE`),
`PQL-132` (P2, `EVIDENCE full (10)` loses its count — paren emitted only for
the `samples` kind), `PQL-140` (P1, `Threshold.render` emits `AT MOST`
unconditionally for `unit == "rows"`, inverting every `AT LEAST` control),
`PQL-196` (P1, `CHECK t.a IS NOT UNIQUE` renders as `IS UNIQUE`, dropping the
negation).

**Parser / grammar (each independent):**
`PQL-064` (P3, `Suite.render` doesn't quote a name that needs it),
`PQL-068` (P2, dangling dot after dataset gives a confusing downstream error
instead of naming the dot), `PQL-082` (P2, `describe()` drops the due time
for a zero-tolerance freshness control — a wording bug, unrelated to `Q-64`'s
execution gap), `PQL-086` (P2, duplicate column in `HAS UNIQUE KEY` not
caught), `PQL-099` (P2, `REFERENCES` target dataset/column never resolved
against the catalogue), `PQL-102` (P2, weak signal — two of three malformed
`DETERMINES` forms already give the right message; the third falls back to a
generic paren-mismatch error), `PQL-112` (P2, a set-level assertion under a
selector expands into N identical copies instead of one control or a
refusal), `PQL-149` (P2, `WITHIN n SIGMA` can never be produced by the
parser even though render/describe both have a sigma branch), `PQL-154` (P1,
`HAVING` is parsed, rendered, and then silently dropped by `Lowerer.control`
— never reaches SQL; structurally the same "declared grammar, no semantics"
shape as `Q-64`, just smaller — recommend either implementing it or refusing
it at parse time until it is, rather than leaving it silently inert),
`PQL-156` (P2, segment keys collide when a value contains the `|`
separator — three join sites, one case), `PQL-159` (P2, segment totals sum
`distinct_keys` across segments, which is not a meaningful number),
`PQL-166` (P3, the linter's always-fires check requires numeric bounds, so
reversed *text* bounds like `BETWEEN 'Z' AND 'A'` pass silently),
`PQL-171` (P2, `LIKE`/`ILIKE` parse inside `WHERE` but are refused as a
top-level assertion, an undocumented asymmetry), `PQL-189` (P2, a parameter
used only inside a metric expression is missing from
`ControlPlan.parameters()`, so SQL binds a name the executor was never told
about), `PQL-228` (P1, column resolution is case-insensitive in the type
checker but case-sensitive in compilation — the checker exists to prevent
exactly this), `PQL-235` (P2, `type_of` types `IS NULL` as a number because
`"IS NULL".isalpha()` is `False`, so it's compared with a boolean and
misreported as a type error), `PQL-266` (P1, `Function.argument_types` is
declared per-function and never enforced — `UPPER(numeric)` passes the
checker and fails at PostgreSQL execution instead), `PQL-353` (P2, `IFERROR`
is refused with the generic "no such function" list instead of the dedicated
explanation the `IFBLANK` divergence note already has for exactly this case),
`PQL-384` (P1, `LanguageService.diagnostics` loops over `program.controls`
instead of `program.all_controls`, so **every control inside a `SUITE`** —
how a real estate is written — gets no type-checking, linting or
unknown-column diagnostics in either editor).

**Function library divergences (each function's own edge case):**
`PQL-264` (P1, `CONCAT` with a `NULL` argument: reference is UNKNOWN,
PostgreSQL returns the non-null side, SQLite agrees with the reference —
three engines, two answers), `PQL-269` (P1, `LENGTH` of a non-text column:
PostgreSQL has no `length(numeric)` and raises; SQLite/DuckDB coerce
differently), `PQL-272` (P2, `TRIM` strips all Unicode whitespace in Python
but only spaces in SQL), `PQL-273` (P1, `LEFT`/`RIGHT`/`MID` with a zero,
negative, or over-long length — the existing test gate explicitly excludes
this input space by substituting safe values), `PQL-276` (P2, `SUBSTITUTE`
with an empty search string: Python inserts between every character, SQL
`REPLACE` returns the input unchanged), `PQL-287` (P1, `MIN`/`MAX` with an
unknown argument: reference/SQLite return `None`, DuckDB/PostgreSQL return
`1`, ignoring the unknown — the function's own docstring calls silent
ignoring a defect), `PQL-288` (P1, `IF(NULL, 1, 2)`: reference is UNKNOWN,
SQL's `CASE WHEN NULL THEN 1 ELSE 2 END` takes the ELSE branch — exactly the
"invented answer" the docstring warns against), `PQL-294` (P1, `ISNUMBER('
7 ')`: reference strips whitespace before matching, the SQL regex does not).

**Backend / dialect (each independent):**
`BE-005` (P2, `qualify()` splits a genuinely one-part quoted name containing
a dot as if it were two-part), `BE-012` (P1, SQLite's `CHAR(31)`/`CHAR(30)`
composite-key separator isn't injective against data containing those exact
bytes), `BE-029` (P1, PostgreSQL is declared to support
`pushdown.approx_distinct` but has no `approx_count_distinct` function —
loosely related to `BE-096`'s reference-side zero-default, but a different
subsystem: SQL-emission capability declaration, not the reference
interpreter), `BE-049` (P1, `_AGGREGATES` is missing `MIN`/`MAX` — they
silently route to the scalar catalogue and render as `LEAST(x)`/`GREATEST(x)`
with one argument — and `MEDIAN` is missing from both the SQL and reference
catalogues; three separate hand-maintained aggregate lists disagree),
`BE-054` (P1, seven operators the lowerer can legally emit —
`LIKE`/`ILIKE`/`NOT LIKE`/`NOT ILIKE`/`!=`/`HAS FORMAT`/`IS OF TYPE` — have
no SQL branch in `SqlCompiler._operation`), `BE-068` (P1, `x = y` between a
number and a numeric string: Python says False, PostgreSQL raises, SQLite
compares by storage class, DuckDB coerces — four answers; likely should be
prevented upstream by the type checker rather than reconciled at this layer),
`BE-100` (P2, `run()` materialises the entire input into memory before
evaluating anything — no bound, on the code path documented as the engine of
last resort for large feed files), `BE-125` (P1, one control in a group of
twenty that needs an unsupported capability stops the whole group, though
the emitted remedy text promises otherwise), `BE-126` (P2, `--fuse` silently
drops every evidence sample row in the group in exchange for one scan, with
no warning), `BE-129` (P2, `Fuser.cost()`'s dict is keyed on
`g.describe()`, which omits the binding, so two distinct groups collide into
one), `BE-178` (P1, sealed evidence has no threshold field, so two runs with
identical metrics and different thresholds produce different verdicts with
no way to explain why from the record alone — this is QA finding `Q-15`),
`BE-179` (P1, four of five replay-safety mechanisms work correctly — clock,
random, unresolved codelist, unresolved semantic type all refuse cleanly;
the fifth, implementation-hash freezing for semantic-type validators, never
fires because the `PLUGINS` registry is empty).

**Error presentation (each independent):**
`PQL-047` (P1, a `PqlUnsupportedError` raised from the SQL compiler never
carries `source=`, so its `render()` silently skips the excerpt/caret block
the module docstring promises for every error — unrelated to C5's Excel
position bug, a different error class and a different file), `PQL-055` (P1,
`prama control check --json` on a syntax error still emits the rendered
prose with its caret instead of a JSON document — QA finding `Q-37`; `_read`
calls `ctx.emit(exc.render())` unconditionally regardless of `--json`).

**Lexer (each independent):**
`PQL-005` (P3, nested `/* */` comments produce a confusing "unclosed regex
pattern" error rather than the predicted "stray `*`" error — worse than
expected, not better, but low priority), `PQL-015` (P2, an empty quoted
identifier `""` is silently accepted as a dataset literally named `""`).

---

## 5 · How many of the 116 are realistically closable

**Around 100–105 of 116.** The two exclusions are principled, not
optimistic: 4 cases already belong to decisions made elsewhere (`Q-64`,
`Q-198/199`) and 2 are not defects (`PQL-350`, and `PQL-001` pending
re-verification with a corrected probe) — 110 remain as real, closable
defects. Of those, the harder tail is small: `BE-075`'s ReDoS case is
mitigation, not a clean fix; `C16`'s corpus-coverage gaps (5 cases) are
genuine test-authoring work, not bug fixes, and two of them need a runner
change first; a handful of P3 boundary cases (`PQL-341`, `BE-095`,
`PQL-064`, `PQL-005`, `BE-141`) are low-value and could reasonably be
deprioritized rather than closed this wave.

**The shape, honestly:** two clusters do disproportionate work — C2 (bare
exceptions, 11 cases) and C1 (arithmetic unification, 4 cases, 3 of them
P1) — but neither is a single-diff fix the way the prior round's 33-case
finding was; both are one *recognized pattern* applied at several sites.
Past those two, the batches are mostly pairs (2 cases apiece) sharing one
real repair — a healthy sign that the catalogue's granularity is fine and
the module-based batching from an earlier round was the actual problem, not
the case list. The tail is genuinely long: 47 one-off cases (22 of them P1)
that need individual attention no matter how the rest is sequenced. That
tail, not the clusters, is where most of the wave's calendar time will go —
each is small, but there are a lot of them, and several (`PQL-228`,
`PQL-266`, `PQL-384`, `BE-178`) are P1s with real product impact on their
own.

**What surprised me:**
1. `PQL-092` and `BE-160` are the *same* bug caught by a hand-written
   control and by the corpus generator's own output — a clean confirmation
   that generator-driven type-checking (as `BE-160` itself argues the
   generator should do more of) finds real defects for free.
2. `PQL-300` and `BE-080` are the same defect (`reference._arithmetic`'s
   `float()` vs `library._number`'s `Decimal()`) approached from opposite
   ends of the codebase — one from the language layer, one from the backend
   layer — and together with `BE-078`/`BE-079` it's a 4-case, 3-P1 cluster
   behind one line of reasoning.
3. The "two hand-maintained lists disagree" shape recurs at least four
   times independently: `PQL-198`/`PQL-199` (already decided, not a defect),
   `PQL-181` (`NON_DETERMINISTIC` vs `VOLATILE`), `BE-049` (three aggregate
   lists), and `PQL-241`/`PQL-242` (two different "walk every expression"
   lists in the type checker). `CLAUDE.md`'s own design doctrine — "derive,
   never restate" — reads like it was written in response to exactly this
   pattern, and it's still live in at least three places.
4. `PQL-181`'s catalogue prediction was only half right: the PQL-side list
   gap is real, but the predicted Excel-side failure (`CURRENT_DATE`
   silently becoming a column reference) did not reproduce — Excel already
   refuses it, just not with a replay-specific message. Worth remembering
   when scoping the fix: don't "fix" a behavior that's already correct.
5. `PQL-350` looked, from its title, like it belonged with `PQL-198`/`PQL-199`
   (another "two things don't agree" case) — but the actual Observed text
   shows the code handles it *correctly*; the catalogue's own predicted
   defect is what's wrong here, not the code.
