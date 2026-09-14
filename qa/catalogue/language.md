# The language and the compiler

Test cases for `src/prama/pql/`, `src/prama/ir/` and `src/prama/backend/` — the
lexer, the parser, the AST, the type checker, the linter, the formatter, the
function catalogue, the Excel surface, selector expansion, the language
services, the engine-neutral IR, and the three SQL backends with the reference
interpreter that exists to disagree with them.

Id prefixes: **`PQL-`** for the language, **`IR-`** for the plan, **`BE-`** for
the backends.

Written from the code, under the rules in [the catalogue README](README.md).
**Nothing here has been executed.** Where a case is typed `negative` against a
claim the code makes about itself — a docstring saying "never", a remedy naming
a spelling, a comment naming a defect it prevents — the **Why** states what
reading the source suggests will happen, and the case exists to find out whether
it does. A case that turns out green is not wasted: it retires a doubt.

## Summary

| Area | Cases | P1 | P2 | P3 |
|---|---:|---:|---:|---:|
| 1 · The lexer — `pql/tokens.py` | 46 | 18 | 22 | 6 |
| 2 · Error presentation — `pql/errors.py` | 9 | 5 | 3 | 1 |
| 3 · Parsing structure — `pql/parser.py` | 57 | 29 | 24 | 4 |
| 4 · Modifiers, thresholds and the clause grammar — `pql/parser.py` | 47 | 23 | 23 | 1 |
| 5 · Expressions — `pql/parser.py` | 36 | 19 | 11 | 6 |
| 6 · The AST, rendering and the formatter — `pql/ast.py`, `cli/control.py::ControlFormatCommand` | 28 | 14 | 11 | 3 |
| 7 · The type checker — `pql/types.py` | 27 | 15 | 11 | 1 |
| 8 · The function catalogue — `pql/functions.py`, `pql/library.py` | 55 | 33 | 20 | 2 |
| 9 · The linter — `pql/lint.py` | 23 | 8 | 13 | 2 |
| 10 · The Excel surface — `pql/excel.py` | 30 | 11 | 16 | 3 |
| 11 · Selector expansion — `pql/expand.py` | 23 | 12 | 9 | 2 |
| 12 · Language services — `pql/analysis.py` | 20 | 13 | 7 | 0 |
| 13 · The package surface — `pql/__init__.py`, `pql/families.py` | 4 | 1 | 3 | 0 |
| 14 · The plan model and plan identity — `ir/model.py` | 44 | 39 | 5 | 0 |
| 15 · Dialects — `backend/dialect.py` | 29 | 25 | 4 | 0 |
| 16 · The SQL compiler — `backend/sql.py` | 33 | 24 | 9 | 0 |
| 17 · The reference interpreter — `backend/reference.py` | 40 | 27 | 11 | 2 |
| 18 · Judgement — `backend/execute.py` | 13 | 11 | 2 | 0 |
| 19 · Fusion — `backend/fuse.py` | 15 | 10 | 4 | 1 |
| 20 · Conformance, the corpus and the generator — `backend/conformance.py`, `corpus.py`, `generate.py` | 30 | 20 | 8 | 2 |
| 21 · The worked example — `backend/example.py` | 8 | 4 | 4 | 0 |
| 22 · Cross-cutting boundaries and scale | 12 | 8 | 3 | 1 |
| **Total** | **629** | **369** | **223** | **37** |

---

## 1 · The lexer — `pql/tokens.py`

### PQL-001 · Every token kind the lexer can emit is reachable
- **Area:** `pql/tokens.py::Lexer._next`, `TokenKind`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** tokenise `CHECK t."odd name" MATCHES /^A/ AND n > $d, 1.5e3 -- tail`
- **Expected:** one token of each of KEYWORD, IDENTIFIER, NUMBER, STRING, REGEX, PARAMETER, OPERATOR, PUNCTUATION, and a terminating END
- **Why:** nine kinds are declared; a kind nothing produces is a branch the parser carries for no reason, and a kind nothing consumes is a hole

### PQL-002 · An empty source tokenises to exactly one END token
- **Area:** `pql/tokens.py::tokenise`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** `tokenise("")`
- **Expected:** `[Token(END, "", Position(line=1, column=1, offset=0, length=1))]`
- **Why:** the empty file is the first thing an editor sends on a new buffer, and every downstream loop terminates on END

### PQL-003 · A source of only whitespace and comments tokenises to END
- **Area:** `pql/tokens.py::Lexer._skip_ignorable`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** `tokenise("  \t\r\n-- nothing\n/* nor this */\n")`
- **Expected:** one END token, at the end of the text
- **Why:** `_skip_ignorable` loops; a form of ignorable text it does not consume is an infinite loop rather than an error

### PQL-004 · A block comment that is never closed is refused, pointing at the opener
- **Area:** `pql/tokens.py::Lexer._skip_block_comment`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `tokenise("CHECK t.a IS NOT NULL /* forgot")`
- **Expected:** `PqlSyntaxError` "a comment is opened with /* and never closed"; the position is the `/*`, not the end of file; remedy names `*/` and `--`
- **Why:** the caret has to be on the opener — the reader knows where the file ends and needs to be told where the comment began

### PQL-005 · Nested block comments are not nested
- **Area:** `pql/tokens.py::Lexer._skip_block_comment`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** `tokenise("/* a /* b */ CHECK t.a IS NOT NULL */")`
- **Expected:** the comment ends at the first `*/`; the trailing `*/` is then a lexical error on `*`
- **Why:** `find("*/")` is non-nesting; whichever behaviour is chosen must be documented, because SQL dialects differ and people paste from them

### PQL-006 · A line comment runs to the newline and no further
- **Area:** `pql/tokens.py::Lexer._skip_ignorable`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** `tokenise("-- CHECK a\nCHECK t.a IS NOT NULL")`
- **Expected:** the first line is discarded; the control on line 2 tokenises, and its tokens report `line=2`
- **Why:** line accounting after a comment is what puts the caret on the right line for every later error

### PQL-007 · A line comment at end of file with no newline terminates cleanly
- **Area:** `pql/tokens.py::Lexer._skip_ignorable`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** `tokenise("CHECK t.a IS NOT NULL -- why")`
- **Expected:** END, no exception (`find` returns -1 and the whole remainder is consumed)
- **Why:** the `end < 0` branch is the one a file without a trailing newline takes, and most editors produce one

### PQL-008 · An unterminated single-quoted string is refused
- **Area:** `pql/tokens.py::Lexer._string`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `tokenise("CHECK t.a IS NOT NULL BECAUSE 'it matters")`
- **Expected:** `PqlSyntaxError` "a piece of text is opened with ' and never closed", remedy explaining `''` doubling
- **Why:** the commonest typo in a BECAUSE clause, and the error must not be reported at the end of the file

### PQL-009 · A string containing a newline is refused, not continued
- **Area:** `pql/tokens.py::Lexer._string`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `tokenise("BECAUSE 'line one\nline two'")`
- **Expected:** refused at the opening quote; a string does not span lines
- **Why:** the `if self.source[cursor] == "\\n": break` guard is what stops one missing quote swallowing the rest of a suite

### PQL-010 · A doubled quote inside a string is one quote in the value
- **Area:** `pql/tokens.py::Lexer._string`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** tokenise `'O''Brien'`
- **Expected:** one STRING token, `text == "'O''Brien'"`, `value == "O'Brien"`
- **Why:** text and value are different fields and both are used — `describe` prints text, the parser stores value

### PQL-011 · A string that is only a doubled quote is the one-character value `'`
- **Area:** `pql/tokens.py::Lexer._string`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** tokenise `''''`
- **Expected:** one STRING token with `value == "'"`; not two empty strings
- **Why:** the `startswith("''")` skip is a two-character lookahead and the four-quote case is where it is off by one

### PQL-012 · An empty string literal has an empty value
- **Area:** `pql/tokens.py::Lexer._string`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** none
- **Steps:** tokenise `''`
- **Expected:** STRING with `text == "''"` and `value == ""`
- **Why:** downstream code writes `token.value or token.text`, which for an empty value falls back to the *quoted* text

### PQL-013 · An unterminated quoted identifier is refused
- **Area:** `pql/tokens.py::Lexer._quoted_identifier`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `tokenise('CHECK "risk positions.a IS NOT NULL')`
- **Expected:** `PqlSyntaxError` "a quoted name is opened and never closed", remedy showing `"risk positions"`
- **Why:** an unclosed double quote otherwise consumes the remainder of the file as a name

### PQL-014 · A doubled double-quote inside a quoted identifier is one quote
- **Area:** `pql/tokens.py::Lexer._quoted_identifier`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** tokenise `"a""b"`
- **Expected:** IDENTIFIER with `value == 'a"b'`
- **Why:** the quoting rule must survive to the SQL compiler, which re-escapes with the same convention

### PQL-015 · An empty quoted identifier `""`
- **Area:** `pql/tokens.py::Lexer._quoted_identifier`, `parser.Parser._name`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `CHECK "".a IS NOT NULL`
- **Expected:** either a refusal naming the empty name, or a dataset whose name is genuinely `""` — never a dataset literally called `""` including its quotes
- **Why:** `_name` returns `token.value or token.text`; an empty value falls through to the raw text, so the dataset name silently becomes two quote characters

### PQL-016 · A quoted identifier may contain a dot without being qualified
- **Area:** `pql/tokens.py::_QUOTED_IDENTIFIER`, `backend/dialect.py::SqlDialect.qualify`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** compile a control whose target is `"schema.table"` (one quoted name containing a dot)
- **Expected:** documented behaviour; note that `qualify` splits on `.` unconditionally and will emit `"schema"."table"`
- **Why:** a name that round-trips through the lexer as one thing and through the dialect as two is a control pointed at a table that does not exist

### PQL-017 · A regular expression is recognised where a value cannot precede
- **Area:** `pql/tokens.py::Lexer._looks_like_regex`, `_previous_allows_division`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** tokenise `MATCHES /^[A-Z]{2}/`, `LIKE /x/`, `ILIKE /x/`
- **Expected:** REGEX in all three; the keyword lookback recognises MATCHES, LIKE and ILIKE
- **Why:** the whole `/` disambiguation rests on this three-name list; a fourth predicate added later without it silently becomes division

### PQL-018 · Division is recognised after a value, an identifier, `)` or `]`
- **Area:** `pql/tokens.py::Lexer._previous_allows_division`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** tokenise `a / b`, `1 / 2`, `(a) / 2`, `f(x) / 2`
- **Expected:** OPERATOR `/` in every case, never a REGEX
- **Why:** getting this wrong turns `amount / count` into an unterminated pattern and reports the error at the end of the control

### PQL-019 · A leading `/` at the start of the source is a pattern
- **Area:** `pql/tokens.py::Lexer._previous_allows_division`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** `tokenise("/abc/")`
- **Expected:** REGEX (`cursor < 0` returns False from `_previous_allows_division`)
- **Why:** the `cursor < 0` branch is only reachable from a source that begins with `/`, and nothing else exercises it

### PQL-020 · An unterminated pattern is refused
- **Area:** `pql/tokens.py::Lexer._regex`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `tokenise("CHECK t.a MATCHES /^[A-Z]{2}")`
- **Expected:** `PqlSyntaxError` "a pattern is opened with / and never closed", remedy giving a complete example
- **Why:** an ISIN pattern is long and a missing closing slash is easy; the error must name the pattern, not the control

### PQL-021 · An escaped slash inside a pattern does not close it
- **Area:** `pql/tokens.py::Lexer._regex`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** tokenise `/a\/b/`
- **Expected:** one REGEX token with `value == "a\\/b"` — the backslash is **kept**, not resolved
- **Why:** the escape is consumed for scanning but not unescaped in the value, so the pattern handed to `re.compile` and to the engine still contains `\/`; whether that is intended must be pinned

### PQL-022 · A pattern containing a newline is refused
- **Area:** `pql/tokens.py::Lexer._regex`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** tokenise `/^A\n B$/` written across two physical lines
- **Expected:** refusal at the opening slash
- **Why:** the same containment rule as a string; without it one slash eats the suite

### PQL-023 · A trailing backslash at the end of a pattern does not read past the end
- **Area:** `pql/tokens.py::Lexer._regex`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** `tokenise("/abc\\")`
- **Expected:** a clean `PqlSyntaxError`, not an `IndexError`; `cursor += 2` must not skip past `len(source)` undetected
- **Why:** `cursor += 2` on the last character leaves the loop condition to catch it; assert it is a language error, not a crash

### PQL-024 · `$` not followed by a name is refused
- **Area:** `pql/tokens.py::Lexer._parameter`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** tokenise `$ 1`, `$1`, `$`
- **Expected:** `PqlSyntaxError` "$ must be followed by a parameter name", remedy naming `$business_date`
- **Why:** `$1` is the positional spelling in several drivers and people will type it; refusing it by name is better than an error about `1`

### PQL-025 · A parameter's value excludes the `$`
- **Area:** `pql/tokens.py::Lexer._parameter`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** tokenise `$business_date`
- **Expected:** PARAMETER with `text == "$business_date"`, `value == "business_date"`
- **Why:** the SQL compiler emits `:{name}` from the value; a leading `$` there produces `:$business_date`, which no driver binds

### PQL-026 · Every number form the pattern admits
- **Area:** `pql/tokens.py::_NUMBER`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** none
- **Steps:** tokenise `0`, `1`, `1.5`, `1e3`, `1E+3`, `1e-3`, `1.5e-3`, `10%`, `0.1%`, `1.5e3%`
- **Expected:** one NUMBER token each, text exactly as written
- **Why:** the percent is part of the literal, and the exponent forms interact with `_threshold`, which does `float(text.rstrip("%"))`

### PQL-027 · Number forms the pattern refuses
- **Area:** `pql/tokens.py::_NUMBER`, `Lexer._next`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** tokenise `.5`, `1.`, `1_000`, `0x1F`, `1e`, `1%%`
- **Expected:** each either refused or split into tokens that the parser then refuses with a located message; none silently becomes a different number
- **Why:** `1.` lexes as `1` followed by `.`, which the parser reads as a qualification — a number that becomes a dotted name is a silent reinterpretation

### PQL-028 · A negative number is two tokens, not one
- **Area:** `pql/tokens.py::_NUMBER`, `parser.Parser._unary`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** tokenise `-10`
- **Expected:** OPERATOR `-` then NUMBER `10`
- **Why:** every place that calls `_number_token` directly (thresholds, row counts, durations, sample counts) therefore cannot accept a negative — which is the intended refusal and must be asserted as such

### PQL-029 · A keyword is recognised case-insensitively and keeps its spelling
- **Area:** `pql/tokens.py::Lexer._word`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** tokenise `check`, `Check`, `CHECK`
- **Expected:** KEYWORD in each case, with `text` preserving the author's casing and `upper` normalising it
- **Why:** `ast.Severity(token.text.lower())` and `Dimension(token.text.lower())` depend on text, not on upper — a mixed-case severity must still resolve

### PQL-030 · Every word in KEYWORDS lexes as a keyword
- **Area:** `pql/tokens.py::KEYWORDS`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** for each of the ~120 entries in `KEYWORDS`, tokenise it alone and assert `kind is KEYWORD`
- **Expected:** all keywords recognised; no entry is unreachable
- **Why:** the set is hand-maintained and several entries (`IMPORT`, `DEFINE`, `PACK`, `CONTRACT`, `MONITOR`, `RECONCILE`, `TRAILER`, `SEASONALITY`, `BUDGET`, `NORMALISING`, `CLASSIFY`, `DERIVES`, `CASE`, `THEN`, `ELSE`, `END`) are consumed by no production — each is a reserved-looking word the parser will reject in a position a user expects it to work

### PQL-031 · A keyword is usable as a column name
- **Area:** `pql/tokens.py` module docstring, `parser.Parser._name`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `CHECK trades.on IS NOT NULL`, `CHECK trades.severity IS NOT NULL`, `CHECK trades.source IS NOT NULL`, `CHECK trades.count IS NOT NULL`
- **Expected:** all four parse; the column names are `on`, `severity`, `source`, `count`
- **Why:** the module docstring makes exactly this promise — "a bank's columns are named severity, source, check_digit and on" — and it is the claim that decides whether the language survives its first real dataset

### PQL-032 · A keyword as a *dataset* name
- **Area:** `parser.Parser._target`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `CHECK schema.a IS NOT NULL`, `CHECK record.a IS NOT NULL`, `CHECK key.a IS NOT NULL`
- **Expected:** parses, target is the keyword's spelling
- **Why:** the same promise on the other side of the dot; `_target` calls `_name`, which accepts keywords, and nothing downstream should re-reject them

### PQL-033 · A keyword that begins a clause cannot be a column in that position
- **Area:** `parser.Parser._modifier_name`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `CHECK t.a IS NOT NULL WHERE where = 1`, then `CHECK t.where IS NOT NULL`
- **Expected:** documented: a column named `where`/`severity`/`on` is reachable after a dot but ambiguous as the first token of a modifier
- **Why:** "recognised, not reserved" has a boundary and it is exactly here; the boundary must be stated rather than discovered

### PQL-034 · An identifier may not begin with a digit
- **Area:** `pql/tokens.py::_IDENTIFIER`
- **Type:** negative
- **Priority:** P3
- **Precondition:** none
- **Steps:** parse `CHECK t.2fa IS NOT NULL`
- **Expected:** refused with a located error; the remedy should point at double-quoting
- **Why:** real warehouse columns are called `2fa_enabled`, and the refusal must name the escape hatch

### PQL-035 · A non-ASCII identifier is refused with the quoting remedy
- **Area:** `pql/tokens.py::Lexer._next`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `CHECK t.montànt IS NOT NULL`
- **Expected:** `PqlSyntaxError` on the accented character: "'à' does not belong in a control", remedy `"odd name"`
- **Why:** `character.isalpha()` is true for `à`, so it enters `_word`, but `_IDENTIFIER` is ASCII-only and `match` is asserted non-None — confirm this is an error and **not** an `AssertionError`

### PQL-036 · A non-ASCII letter cannot crash the word scanner
- **Area:** `pql/tokens.py::Lexer._word`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `tokenise("é")`
- **Expected:** a `PqlSyntaxError`, never `AssertionError: match is not None`
- **Why:** `_next` dispatches to `_word` on `character.isalpha()`, which is Unicode-aware, while `_IDENTIFIER` is `[A-Za-z_]` — the two disagree and the assert is the only thing between them

### PQL-037 · Non-ASCII inside a quoted identifier and inside text is accepted
- **Area:** `pql/tokens.py::Lexer._quoted_identifier`, `_string`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `CHECK "montànt".x IS NOT NULL BECAUSE 'ça compte — 日本'`
- **Expected:** both accepted, values preserved exactly, and the rendered control re-parses
- **Why:** the quoting escape hatch is only an escape hatch if it actually accepts what it was offered for

### PQL-038 · A stray character is refused with its own caret
- **Area:** `pql/tokens.py::Lexer._next`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** tokenise `CHECK t.a @ 1`, then `#`, `&`, `!`, `~`, `^`, backtick
- **Expected:** `"'@' does not belong in a control"` with `length=1` and the caret under the character
- **Why:** `!` alone is interesting: `!=` is an operator, so a lone `!` must be refused rather than half-matched

### PQL-039 · Every entry of OPERATORS lexes, longest first
- **Area:** `pql/tokens.py::OPERATORS`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** tokenise `<>`, `!=`, `>=`, `<=`, `||`, `=`, `>`, `<`, `+`, `-`, `*`, `/`, `%` each alone and in `a>=b`
- **Expected:** `>=` is one token, never `>` then `=`; `||` is one token, never two `|` (which is not in OPERATORS at all)
- **Why:** the ordering of the tuple is load-bearing and a reorder is invisible until a `>=` becomes a comparison against an assignment

### PQL-040 · A single `|` is refused
- **Area:** `pql/tokens.py::OPERATORS`, `PUNCTUATION`
- **Type:** negative
- **Priority:** P3
- **Precondition:** none
- **Steps:** tokenise `a | b`
- **Expected:** "'|' does not belong in a control"
- **Why:** `|` appears only as half of `||`; a lone one must not fall through to a punctuation branch

### PQL-041 · Every punctuation mark is emitted, including the ones no production uses
- **Area:** `pql/tokens.py::PUNCTUATION`
- **Type:** contract
- **Priority:** P3
- **Precondition:** none
- **Steps:** tokenise each of `( ) , . { } [ ] : ;`
- **Expected:** PUNCTUATION for all ten
- **Why:** `[`, `]`, `:` and `;` are lexed and consumed by no grammar rule, so they reach the parser as "expected X and found ';'" — confirm that message is comprehensible

### PQL-042 · Position: line, column, offset and length on every token
- **Area:** `pql/tokens.py::Lexer._here`, `_advance`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** tokenise a three-line control and assert every token's `(line, column, offset)` against the source text
- **Expected:** one-based line and column, zero-based offset, `length` equal to `len(text)` and never below 1
- **Why:** every error message, every editor squiggle and every console highlight is computed from these three numbers

### PQL-043 · Column resets after a newline inside a string is impossible, but after a comment it must
- **Area:** `pql/tokens.py::Lexer._advance`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** tokenise `-- comment\n  CHECK`
- **Expected:** the `CHECK` token reports `line=2, column=3`
- **Why:** `_advance` counts newlines one character at a time; a bulk skip that forgot to would leave every subsequent caret on the wrong line

### PQL-044 · A CRLF file reports the same columns as an LF file
- **Area:** `pql/tokens.py::Lexer._skip_ignorable`, `_advance`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a control file saved with Windows line endings
- **Steps:** tokenise the same control with `\n` and with `\r\n`; compare the token positions
- **Expected:** identical line numbers; `\r` is skipped as ignorable and must not shift the column of the following token by one
- **Why:** `\r` is consumed by `_skip_ignorable` *and* counted by `_advance` as a column, so a CRLF file's columns may be one out on continuation lines — which puts every caret in the wrong place for half the users

### PQL-045 · A one-byte source
- **Area:** `pql/tokens.py::tokenise`, `parser.parse`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse each of `C`, `(`, `'`, `/`, `$`, `1`, `-`
- **Expected:** a located `PqlSyntaxError` for each; no crash, no `IndexError`
- **Why:** single-character inputs are where lookahead-by-one goes off the end

### PQL-046 · A 10,000-character identifier
- **Area:** `pql/tokens.py::_IDENTIFIER`, `errors.PqlError.excerpt`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** parse a control whose column name is 10,000 characters, then force an error on it
- **Expected:** it lexes; the error excerpt is windowed to `CONTEXT_CHARS` either side with ellipses, and the caret still lines up
- **Why:** `excerpt` promises a window rather than a truncation, and a caret that has drifted is worse than no caret

## 2 · Error presentation — `pql/errors.py`

### PQL-047 · Every PQL error renders position, excerpt, caret and remedy
- **Area:** `pql/errors.py::PqlError.render`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** provoke one error of each subclass — `PqlSyntaxError`, `PqlTypeError`, `PqlUnsupportedError` — and call `render()`
- **Expected:** `"<message> (at line L, column C)"`, a blank line, the source line, a caret line, a blank line, `"→ <remedy>"`
- **Why:** the module docstring says every error carries "the position, the line as written, a caret under the offending text, and a remedy in the same register as the language"; that is four claims on one method

### PQL-048 · The caret spans exactly the offending text
- **Area:** `pql/errors.py::PqlError.excerpt`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** provoke an error on a five-character token and count the `^` characters
- **Expected:** five carets, starting under the token's first character
- **Why:** `"^" * max(1, length)` — a `length` of 0 must still produce one caret, and a token longer than the window must not overflow the line

### PQL-049 · A long line is windowed around the error, not truncated from the left
- **Area:** `pql/errors.py::PqlError.excerpt`, `CONTEXT_CHARS`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** provoke an error at column 300 of a 500-character WHERE clause
- **Expected:** a `…`-prefixed and `…`-suffixed window of 120 characters, with the caret offset by the prefix
- **Why:** the docstring states this explicitly; the caret offset calculation adds `len(prefix)` and is the part that goes wrong

### PQL-050 · An error with no source renders without an excerpt
- **Area:** `pql/errors.py::PqlError.excerpt`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** construct `PqlSyntaxError("x", remedy="y")` with no `source`, call `render()`
- **Expected:** message and remedy only; no blank excerpt block, no `IndexError`
- **Why:** several raise sites — `excel.py` throughout, and `lower.py` via `ValidationError` — supply no source, and the console renders whatever comes back

### PQL-051 · A position pointing past the end of the source produces no excerpt
- **Area:** `pql/errors.py::PqlError.excerpt`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** construct an error with `Position(line=99)` over a three-line source
- **Expected:** `excerpt()` returns `[]`; `render()` still names the position
- **Why:** the bounds check is the only thing between a stale position and an `IndexError` in the CLI's error path

### PQL-052 · `position` appears in the error context only when one was given
- **Area:** `pql/errors.py::PqlError.__init__`
- **Type:** contract
- **Priority:** P3
- **Precondition:** none
- **Steps:** build one error with a position and one without; inspect `.context`
- **Expected:** `"position"` present in the first, absent in the second
- **Why:** the API serialises `context` into `problem+json`; a key that is sometimes `"line 1, column 1"` meaning "unknown" is a lie in a machine-readable field

### PQL-053 · The three error codes are distinct and stable
- **Area:** `pql/errors.py::PqlError.code`, `PqlSyntaxError`, `PqlTypeError`, `PqlUnsupportedError`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** assert the codes are `PQL.INVALID`, `PQL.SYNTAX`, `PQL.TYPE`, `PQL.UNSUPPORTED`
- **Expected:** those four exact strings, one per class, unchanged across releases
- **Why:** a CI gate keys off the code to distinguish "your control is wrong" from "this engine cannot run it", and the two need different remedies from the operator

### PQL-054 · `PqlUnsupportedError` is raised at authoring time and never at execution
- **Area:** `pql/errors.py::PqlUnsupportedError` docstring, `backend/sql.py::SqlCompiler`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** grep every `raise PqlUnsupportedError` and confirm each is on a compile path, not inside a result-handling or row-iteration path
- **Expected:** every site is reachable only from `SqlCompiler.compile`, `Fuser.fuse` or `_call`/`_operation` beneath them
- **Why:** the docstring's claim — "Raised at authoring time and never at execution time" — is the one that makes `compile` a safe pre-flight check

### PQL-055 · `--json` output of a PQL error is valid JSON
- **Area:** `pql/errors.py::PqlError`, `cli/control.py::_read`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a `.pql` file with a syntax error
- **Steps:** `prama control check bad.pql --json`
- **Expected:** a JSON document carrying message, remedy, code and position — not the rendered prose with its caret
- **Why:** QA finding Q-37: `--json` on a PQL syntax error emitted prose, breaking the contract at the CI integration point; `_read` still calls `ctx.emit(exc.render())` unconditionally

## 3 · Parsing structure — `pql/parser.py`

### PQL-056 · A minimal control parses
- **Area:** `pql/parser.py::parse_control`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `parse_control("CHECK positions.account_id IS NOT NULL")`
- **Expected:** `Control(target="positions", assertion=PredicateAssertion(subject=ColumnRef("account_id","positions"), operator="is_not_null"))`, severity `major`, threshold `AT MOST 0 ROWS`, unknown policy `violation`
- **Why:** every default in the language is asserted by this one case, and each default is a decision

### PQL-057 · A control with no BECAUSE is **accepted** by the parser
- **Area:** `pql/parser.py::Parser._finish`, `pql/lint.py::Linter._missing_justification`
- **Type:** documentation
- **Priority:** P1
- **Precondition:** none
- **Steps:** `parse_control("CHECK t.a IS NOT NULL")`
- **Expected:** it parses; the *linter* reports `no-justification` at severity `info`, and nothing refuses it
- **Why:** the catalogue README's own worked example says a control with no BECAUSE is refused with a `PqlSyntaxError`. It is not. Either the language changes or the claim does — and until then every reader of the README has the wrong model

### PQL-058 · Text after a control is refused by `parse_control` and accepted by `parse`
- **Area:** `pql/parser.py::Parser.parse_control`, `Parser.parse`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** feed two controls to each entry point
- **Expected:** `parse_control` raises "there is more text after the control"; `parse` returns both
- **Why:** two entry points with different acceptance is a contract, and the editor uses the strict one

### PQL-059 · A document that is not a control is refused at the first token
- **Area:** `pql/parser.py::Parser.parse`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `SELECT * FROM t`, then `{ }`, then `CHECKS t.a IS NOT NULL`
- **Expected:** "expected a control and found …" with the remedy naming CHECK and SUITE and giving a whole example
- **Why:** somebody pasting SQL into a `.pql` file is the first user error, and the message is the one chance to redirect them

### PQL-060 · A suite parses and carries its controls
- **Area:** `pql/parser.py::Parser._suite`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `SUITE core { CHECK t.a IS NOT NULL CHECK t.b IS NOT NULL }`
- **Expected:** one `Suite(name="core")` with two controls; `Program.controls` is empty and `Program.all_controls` has two
- **Why:** the split between `controls` and `all_controls` is where `analysis.diagnostics` loses the suite (see the language-service section)

### PQL-061 · An empty suite parses
- **Area:** `pql/parser.py::Parser._suite`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** parse `SUITE core { }`
- **Expected:** a `Suite` with no controls; not an error
- **Why:** the `while not }` loop must not require at least one control, and an empty suite is what an import produces when nothing came across

### PQL-062 · An unclosed suite names the suite
- **Area:** `pql/parser.py::Parser._suite`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `SUITE core { CHECK t.a IS NOT NULL`
- **Expected:** "the suite 'core' is opened and never closed", remedy "Close it with }."
- **Why:** the error names the suite, which is the only way to find it in a 400-line file

### PQL-063 · A nested suite is refused
- **Area:** `pql/parser.py::Parser._suite`, `_control`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `SUITE a { SUITE b { } }`
- **Expected:** a located error saying CHECK was expected
- **Why:** suites do not nest; the refusal must say so rather than reporting a missing `}`

### PQL-064 · A suite name may be a keyword or quoted
- **Area:** `pql/parser.py::Parser._suite`, `_name`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** parse `SUITE record { }`, `SUITE "core suite" { }`
- **Expected:** both parse; `Suite.render()` re-emits them and the result re-parses
- **Why:** `Suite.render` emits the name unquoted, so a name with a space round-trips to something that does not parse

### PQL-065 · A duplicate suite name is not refused
- **Area:** `pql/parser.py::Parser.parse`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** parse two `SUITE core { … }` blocks in one file
- **Expected:** documented behaviour — two suites of the same name, or a refusal
- **Why:** downstream code keys suites by name; two with one name is an ambiguity nobody resolves

### PQL-066 · The target is the dataset, not the column
- **Area:** `pql/parser.py::Parser._target`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `CHECK positions.notional IS NOT NULL` and inspect `control.target`
- **Expected:** `"positions"`, with `notional` as the assertion's subject
- **Why:** the docstring states the consequence of getting it backwards — every column control's scope would be one column and the row count meaningless

### PQL-067 · A three-part name is refused
- **Area:** `pql/parser.py::Parser._target`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `CHECK warehouse.risk.positions IS NOT NULL`
- **Expected:** a located refusal; `_target` reads only one dot
- **Why:** `schema.table.column` is exactly what a DBA writes, and the refusal has to say how to spell it instead

### PQL-068 · A dangling dot after the dataset
- **Area:** `pql/parser.py::Parser._target`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `CHECK positions. IS NOT NULL`
- **Expected:** "expected a column name after the dot and found 'IS'"
- **Why:** `_name` accepts keywords, so `IS` would otherwise become the column name and the control would parse into nonsense

### PQL-069 · An assertion is required after the target
- **Area:** `pql/parser.py::Parser._assertion`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `CHECK positions`
- **Expected:** "expected something to check about positions and found the end of the control", remedy listing IS NOT NULL, IN CODELIST, HAS UNIQUE KEY, HAS ROW COUNT, REFERENCES, SATISFIES
- **Why:** the remedy is the language's own summary, and it must list constructs that all exist and all work

### PQL-070 · A column-level assertion with no column named is refused
- **Area:** `pql/parser.py::Parser._require_subject`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `CHECK positions IS NOT NULL`
- **Expected:** "this check is about a column, but no column was named", remedy naming HAS ROW COUNT and HAS UNIQUE KEY as the dataset-level forms
- **Why:** the natural first attempt, and the remedy teaches the distinction between row and set assertions

### PQL-071 · `IS NOT NULL` and `IS NULL` produce the right operators
- **Area:** `pql/parser.py::Parser._is_assertion`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse both forms
- **Expected:** `operator == "is_not_null"` and `"is_null"` respectively; `negated` is not used to express the difference
- **Why:** two encodings of negation would let a round-trip produce `IS NOT NOT NULL`

### PQL-072 · `IS NOT UNIQUE` silently loses its negation
- **Area:** `pql/parser.py::Parser._is_assertion`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `CHECK t.a IS NOT UNIQUE`
- **Expected:** either a refusal, or `negated=True` carried into the assertion — never the same AST as `IS UNIQUE`
- **Why:** `negated` is computed and then not passed to the `is_unique` branch, so `IS NOT UNIQUE` parses as `IS UNIQUE` and the control asserts the opposite of what is written

### PQL-073 · `IS UNIQUE` lowers to a uniqueness test, not a null check
- **Area:** `pql/parser.py::Parser._is_assertion`, `ir/lower.py::Lowerer._predicate`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a dataset with a duplicated, entirely non-null column
- **Steps:** parse, lower and execute `CHECK t.uti IS UNIQUE` over rows with duplicate values
- **Expected:** `fail`, with a violating count naming the duplicates
- **Why:** `_predicate` maps `is_unique` to `Expr.operation("IS NOT NULL", subject)` and `_assertion` returns `assertion_kind="predicate"`, so the control **passes** on duplicated data. `packs/banking/regimes.py` ships `CHECK {dataset}.{uti} IS UNIQUE` and `contract/quality.py` maps `duplicateCount`, `duplicatePercent` and `uniqueCount` onto it — three regulatory controls that check something else entirely

### PQL-074 · `IS VALID` with a bare name, a quoted name and a keyword
- **Area:** `pql/parser.py::Parser._is_assertion`, `_reference_literal`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `IS VALID isin`, `IS VALID 'isin'`, `IS VALID ISIN`
- **Expected:** all three parse to a text literal; the value is exactly as written, with no case normalisation
- **Why:** case matters downstream — see PQL-075

### PQL-075 · The parser's own remedy for `IS VALID` names a spelling that does not resolve
- **Area:** `pql/parser.py::Parser._is_assertion` remedy, `ir/lower.py::Lowerer._valid`, `classify/validators.py::ValidatorRegistry.find`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** follow the remedy literally — write `CHECK t.isin IS VALID ISIN` — then lower it
- **Expected:** the control lowers
- **Why:** `find` is a plain dict lookup and every shipped validator is registered lowercase, so `ISIN` raises "there is no semantic type called 'ISIN'". The same spelling appears in two shipped remedies (`_is_assertion` and `_reference_literal`). The catalogue rule is that every `remedy=` gets a case that follows it literally

### PQL-076 · `IN CODELIST` accepts the spelling its remedy gives
- **Area:** `pql/parser.py::Parser._reference_literal` remedy, `ir/lower.py::Lowerer._codelist`, `classify/codelists.py`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** follow the remedy: `CHECK t.ccy IN CODELIST iso4217`, lower it through `ir.resolve.resolved`
- **Expected:** resolves to the shipped ISO 4217 values
- **Why:** the same remedy-fidelity rule; and Q-14 recorded `compile` refusing `IN CODELIST` with a false remedy while `run` executed it — assert both paths now agree

### PQL-077 · An unregistered codelist is refused by name
- **Area:** `ir/lower.py::Lowerer._codelist`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** lower `CHECK t.ccy IN CODELIST nosuchlist` through `resolved`
- **Expected:** "the codelist 'nosuchlist' is not registered", remedy offering registration or an explicit set
- **Why:** the alternative is a control that compiles to `IN ()` and fails every row

### PQL-078 · `IS FRESH` in each of its four shapes
- **Area:** `pql/parser.py::Parser._freshness`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `IS FRESH WITHIN 30 MINUTES`, `… OF '06:30'`, `… CALENDAR 'TARGET2'`, `… OF '06:30' CALENDAR 'TARGET2'`
- **Expected:** all four parse; the optional clauses default to `""`
- **Why:** two optional clauses in a fixed order is four paths and only the last is ever written in an example

### PQL-079 · `IS FRESH` duration units
- **Area:** `pql/parser.py::Parser._duration_minutes`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `WITHIN 30 MINUTES`, `1 MINUTE`, `4 HOURS`, `1 HOUR`, `2 DAYS`, `1 DAY`
- **Expected:** 30, 1, 240, 60, 2880, 1440 minutes
- **Why:** six spellings, one factor table, and a singular/plural pair per unit

### PQL-080 · An unknown duration unit is refused by name
- **Area:** `pql/parser.py::Parser._duration_minutes`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `IS FRESH WITHIN 30 SECONDS`, then `WITHIN 30 WEEKS`
- **Expected:** "expected MINUTES, HOURS or DAYS and found 'SECONDS'"
- **Why:** seconds is the unit a person reaches for on a streaming feed, and the refusal must name what is available

### PQL-081 · A fractional or negative freshness tolerance is refused
- **Area:** `pql/parser.py::Parser._integer`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `IS FRESH WITHIN 1.5 HOURS`, then `WITHIN -5 MINUTES`
- **Expected:** "expected how long as a whole number and found '1.5'" for the first; a located refusal for the second
- **Why:** `_integer` refuses a decimal point and a percent, and a leading `-` never reaches it because `_number_token` demands a NUMBER token

### PQL-082 · `IS FRESH WITHIN 0 MINUTES` is a zero tolerance, not a missing one
- **Area:** `pql/parser.py::Parser._freshness`, `ast.FreshnessAssertion.describe`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `IS FRESH WITHIN 0 MINUTES OF '06:30'` and call `describe()`
- **Expected:** "the data arrives on time"; the due time is not lost
- **Why:** `describe` branches on `tolerance_minutes == 0` and drops `due_time` from the sentence, so a zero-tolerance control describes itself without the deadline it is about

### PQL-083 · A freshness control cannot be judged
- **Area:** `ir/lower.py::Lowerer._assertion`, `_metrics`, `backend/execute.py::_verdict`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** lower `CHECK t IS FRESH WITHIN 30 MINUTES OF '06:30'`, compile it, judge the metrics
- **Expected:** a verdict derived from the arrival time
- **Why:** lowering returns `predicate=None` for freshness, so `_metrics` emits only `scanned_rows`; `_verdict` has no `freshness` branch and falls to `threshold.evaluate`, which finds no `violating_rows` and returns INDETERMINATE — every freshness control in the product is permanently indeterminate

### PQL-084 · `HAS UNIQUE KEY` with one, several and many columns
- **Area:** `pql/parser.py::Parser._has_assertion`, `_column_list`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `HAS UNIQUE KEY (a)`, `(a, b, c)`, and a 50-column key
- **Expected:** the columns in written order; `is_structural` is True; the default threshold is strict
- **Why:** a declared key that tolerated duplicates would not be a key, and the default is what enforces that

### PQL-085 · `HAS UNIQUE KEY` with an empty list is refused
- **Area:** `pql/parser.py::Parser._column_list`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `CHECK t HAS UNIQUE KEY ()`
- **Expected:** a located refusal
- **Why:** `_column_list` calls `_column()` unconditionally, so the error is about the `)` — check it is comprehensible

### PQL-086 · `HAS UNIQUE KEY` with a qualified or duplicated column
- **Area:** `pql/parser.py::Parser._column`, `ir/lower.py::_any_null`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `HAS UNIQUE KEY (t.a, t.a)` and `HAS UNIQUE KEY (other.a)`
- **Expected:** the duplicate is either refused or de-duplicated; a foreign qualifier is refused by the type checker
- **Why:** `_columns_of` feeds key columns to `_resolve`, which catches the foreign dataset; nothing catches the repeat, which makes `COUNT(DISTINCT (a, a))` — a key over one column wearing two names

### PQL-087 · `HAS ROW COUNT` in each of its three shapes
- **Area:** `pql/parser.py::Parser._bounds`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `HAS ROW COUNT BETWEEN 1 AND 8`, `AT LEAST 7`, `AT MOST 100`
- **Expected:** `(1, 8)`, `(7, None)`, `(None, 100)`
- **Why:** three shapes, one assertion, and the min/max pair is read directly by `_row_count_verdict`

### PQL-088 · `HAS ROW COUNT` with anything else after it
- **Area:** `pql/parser.py::Parser._bounds`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `HAS ROW COUNT > 100`, `HAS ROW COUNT 100`
- **Expected:** "expected BETWEEN or AT LEAST/MOST after ROW COUNT", remedy with a whole example
- **Why:** `> 100` is what anybody would write first

### PQL-089 · Row-count bounds must be whole numbers
- **Area:** `pql/parser.py::Parser._integer`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `HAS ROW COUNT AT LEAST 1e6`, then `AT LEAST 1000000.0`, then `AT LEAST 10%`
- **Expected:** `1e6` is accepted by `_integer` (no `.` and no `%`) and becomes `int("1e6")` → assert this raises a *located* error and not a bare `ValueError`
- **Why:** `_integer` guards on the spelling and then calls `int(token.text)`, which cannot parse an exponent — a `ValueError` escaping the parser is a traceback in the CLI (Q-28)

### PQL-090 · `HAS ROW COUNT BETWEEN 0 AND 0`
- **Area:** `pql/parser.py::Parser._bounds`, `backend/execute.py::_row_count_verdict`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an empty table
- **Steps:** parse, lower and judge over zero rows
- **Expected:** `pass` — the only assertion kind for which an empty scope is a legitimate pass
- **Why:** `_row_count_verdict` is deliberately exempt from the empty-scope indeterminacy guard, and that exemption must be pinned so the guard is not later "fixed" onto it

### PQL-091 · `HAS LENGTH BETWEEN` parses and carries both bounds
- **Area:** `pql/parser.py::Parser._has_assertion`, `_between_bounds`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `CHECK t.isin HAS LENGTH BETWEEN 12 AND 12`
- **Expected:** `operator == "has_length_between"`, argument 12, upper 12
- **Why:** the equal-bounds case is how an exact length is written and is in the conformance corpus

### PQL-092 · `HAS LENGTH BETWEEN` on a text column must not be a type error
- **Area:** `pql/types.py::TypeChecker._check_predicate`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a catalogue declaring `isin VARCHAR(12)`
- **Steps:** type-check `CHECK t.isin HAS LENGTH BETWEEN 12 AND 12`
- **Expected:** no findings
- **Why:** `_check_predicate` skips the argument comparison only for `in_codelist`, `is_valid`, `has_format` and `matches`. `has_length_between` is not in the list, so the *text* subject is compared with the *number* bounds, `frozenset({"text","number"})` is not in `COMPARABLE`, and every length control on every text column reports a spurious error

### PQL-093 · `HAS FORMAT` cannot be executed anywhere
- **Area:** `pql/parser.py::Parser._has_assertion`, `ir/lower.py::Lowerer._predicate`, `backend/sql.py::SqlCompiler._operation`, `backend/reference.py::ReferenceEvaluator._operation`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse, lower, compile and interpret `CHECK t.iban HAS FORMAT iban`
- **Expected:** a working control, or a refusal at authoring time naming the gap
- **Why:** it parses, it describes itself in prose, it lowers to `Expr.operation("HAS FORMAT", …)` — and then the SQL compiler raises "HAS FORMAT has no SQL form" while the reference interpreter falls through to `_compare` and raises a bare `KeyError`. A documented surface that nothing can run, failing two different ways

### PQL-094 · `IS OF TYPE` is unreachable
- **Area:** `pql/parser.py::Parser._is_assertion`, `ast.PredicateAssertion._clause`, `ir/lower.py::Lowerer._predicate`
- **Type:** documentation
- **Priority:** P3
- **Precondition:** none
- **Steps:** attempt to parse any spelling of `IS OF TYPE`
- **Expected:** no grammar accepts it
- **Why:** `is_of_type` has a render, a plain-language form and a lowering, and `TYPE` is a keyword — three pieces of a feature with no way in. Either wire it or delete it; carrying it makes the catalogue look larger than it is

### PQL-095 · `HAS` followed by anything else
- **Area:** `pql/parser.py::Parser._has_assertion`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `CHECK t HAS PRECISION 2`, `HAS SCALE 2`, `HAS DUPLICATE PARTITIONS`
- **Expected:** "expected UNIQUE KEY, ROW COUNT, LENGTH or FORMAT after HAS, found …"
- **Why:** `PRECISION`, `SCALE`, `DUPLICATE` and `PARTITIONS` are all in KEYWORDS, so they look like language and are not

### PQL-096 · `IS` followed by anything else
- **Area:** `pql/parser.py::Parser._is_assertion`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `CHECK t.a IS INCREASING`, `IS NON DECREASING`, `IS TRUE`
- **Expected:** "expected NULL, UNIQUE, VALID, FRESH or IN after IS, found 'INCREASING'"
- **Why:** `INCREASING`, `DECREASING` and `NON` are keywords with no production — the error is the only thing telling a reader they are not features

### PQL-097 · `REFERENCES` parses and names both sides
- **Area:** `pql/parser.py::Parser._references`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `CHECK positions.account_id REFERENCES accounts.account_id`
- **Expected:** `ReferenceAssertion(column=…, target_dataset="accounts", target_column="account_id")`
- **Why:** the worked example depends on it and it is the only cross-dataset assertion in the language

### PQL-098 · `REFERENCES` with no dot on the right is refused
- **Area:** `pql/parser.py::Parser._references`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `CHECK t.a REFERENCES accounts`
- **Expected:** "expected '.' and found the end of the control"
- **Why:** a reference to a table rather than a column is the natural shorthand and must be refused, not guessed at

### PQL-099 · The target of a REFERENCES is never resolved
- **Area:** `pql/types.py::TypeChecker._columns_of`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a catalogue declaring `accounts(account_id)`
- **Steps:** type-check `CHECK positions.account_id REFERENCES accounts.nosuchcolumn`, and again with `REFERENCES nosuchdataset.x`
- **Expected:** a finding naming the unknown target
- **Why:** `_columns_of` appends only `assertion.column` for a `ReferenceAssertion`; the target dataset and column are never checked against the catalogue, so a referential control can name a table nobody has

### PQL-100 · `SATISFIES` with a bare expression
- **Area:** `pql/parser.py::Parser._satisfies`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `CHECK t SATISFIES NOT (status = 'CANCELLED' AND notional > 0)`
- **Expected:** an `ExpressionAssertion` with `source_syntax == "pql"`
- **Why:** the general escape hatch, and the one assertion whose condition is never type-checked (see the type-checker section)

### PQL-101 · `SATISFIES a DETERMINES b`
- **Area:** `pql/parser.py::Parser._satisfies`, `_as_columns`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `SATISFIES account_id DETERMINES legal_entity_id` and `SATISFIES (a, b) DETERMINES (c, d)`
- **Expected:** a `FunctionalDependencyAssertion` with the columns in order
- **Why:** `_as_columns` accepts exactly two AST shapes and the parenthesised form is the only way to write a composite determinant

### PQL-102 · `DETERMINES` with a non-column on either side is refused
- **Area:** `pql/parser.py::Parser._satisfies`, `_as_columns`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `SATISFIES UPPER(a) DETERMINES b`, then `SATISFIES a DETERMINES 1`, then `SATISFIES (a, 1) DETERMINES b`
- **Expected:** "the left/right of DETERMINES must be one or more columns" with an example
- **Why:** `_as_columns` returns None for any mixed list, and the error names which side

### PQL-103 · `SATISFIES EXCEL` requires a quoted formula
- **Area:** `pql/parser.py::Parser._excel`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `CHECK t SATISFIES EXCEL =AND([a]>0)` (unquoted)
- **Expected:** "EXCEL must be followed by the formula in quotes" with a complete example
- **Why:** the unquoted form is what somebody pastes from a spreadsheet, and the message is the only place the quoting rule is stated

### PQL-104 · The Excel marker is explicit, never sniffed
- **Area:** `pql/parser.py::Parser._excel` docstring
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `CHECK t SATISFIES a = 1` and `CHECK t SATISFIES EXCEL '=[a]=1'`
- **Expected:** the first is PQL (`=` is a comparison), the second is Excel; no input is routed by heuristics
- **Why:** the docstring's stated reason — "a parser guessing between the two would occasionally guess wrong on a control that then means something its author did not write"

### PQL-105 · A selector with no condition
- **Area:** `pql/parser.py::Parser._selector`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `CHECK EVERY ATTRIBUTE IS NOT NULL`
- **Expected:** `Selector(kind="attribute", where=None)`; `control.is_template` is True; the subject is a `SelectedAttribute`
- **Why:** the unconditioned selector covers the whole estate and is the widest thing anybody can approve by accident

### PQL-106 · A selector condition stops at `IS`
- **Area:** `pql/parser.py::Parser._selector_condition`, `_predicate_suffix`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `CHECK EVERY ATTRIBUTE WHERE is_cde IS NOT NULL`
- **Expected:** the condition is the bare column `is_cde`; the assertion is `IS NOT NULL`
- **Why:** the `_in_selector` flag exists only for this, and it is the ambiguity the docstring says is genuine even for a person

### PQL-107 · `IN` inside a selector condition still binds to the condition
- **Area:** `pql/parser.py::Parser._selector_condition`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `CHECK EVERY ATTRIBUTE WHERE tags IN ('pii') IS NOT NULL` and `… WHERE criticality IN ('tier1','tier2') IS NOT NULL`
- **Expected:** the `IN` belongs to the condition, the `IS NOT NULL` to the assertion
- **Why:** the docstring promises exactly this asymmetry between `IS` and `IN`, and it is the difference between a usable selector language and one that can only test equality

### PQL-108 · A selector condition cannot say `IS NULL`
- **Area:** `pql/parser.py::Parser._selector_condition` docstring
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `CHECK EVERY ATTRIBUTE WHERE domain IS NULL IS NOT NULL`
- **Expected:** the documented workaround `domain = ''` works, and the direct form produces a comprehensible error
- **Why:** the docstring states the workaround; the error a user actually hits must point at it

### PQL-109 · A concept selector
- **Area:** `pql/parser.py::Parser._selector`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `CHECK CONCEPT Instrument.ISIN IS VALID isin`
- **Expected:** `Selector(kind="concept", concept="Instrument", concept_property="ISIN")`
- **Why:** the second selector kind, matched on a different field, and the only one that is not an expression

### PQL-110 · A concept selector without the dotted property is refused
- **Area:** `pql/parser.py::Parser._selector`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `CHECK CONCEPT Instrument IS VALID isin`
- **Expected:** "expected '.' and found 'IS'"
- **Why:** a concept-wide selector is a thing somebody will try, and the refusal must say a property is required

### PQL-111 · `REFERENCES` under a selector is refused with a reason
- **Area:** `pql/parser.py::Parser._require_column`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `CHECK EVERY ATTRIBUTE WHERE is_cde REFERENCES accounts.id`
- **Expected:** "a reference names one column on each side, so it cannot be written against a selector", remedy showing the concrete form
- **Why:** the honest refusal rather than an expansion into something nobody wrote — and the only place `_require_column` is used

### PQL-112 · A set-level assertion under a selector expands into N copies of one control
- **Area:** `pql/parser.py::Parser._control`, `pql/expand.py::_rebind`
- **Type:** negative
- **Priority:** P2
- **Precondition:** an attribute catalogue with five matching attributes
- **Steps:** parse and expand `CHECK EVERY ATTRIBUTE WHERE is_cde HAS ROW COUNT AT LEAST 1`, and `CHECK EVERY ATTRIBUTE WHERE is_cde SATISFIES a > 0`
- **Expected:** a refusal, or one control — not five identical ones the linter will then report as duplicates
- **Why:** `_rebind` only substitutes into a `PredicateAssertion` whose subject is the placeholder; every other assertion kind is copied unchanged, so the selector multiplies a dataset-level claim by the attribute count

## 4 · Modifiers, thresholds and the clause grammar — `pql/parser.py`

### PQL-113 · Modifiers may appear in any order
- **Area:** `pql/parser.py::Parser._modifiers`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse the same control with `WHERE … SEVERITY … BECAUSE …` and with `BECAUSE … SEVERITY … WHERE …`
- **Expected:** identical ASTs (`Node.position` is excluded from equality)
- **Why:** the docstring says order-independence is deliberate; equality of the two parses is the only way to assert it

### PQL-114 · Every modifier keyword is recognised
- **Area:** `pql/parser.py::Parser._modifier_name`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse a control carrying each of WHERE, FOR EACH, SEVERITY, DIMENSION, BECAUSE, EVIDENCE, OWNER, TREAT UNKNOWN AS, ON FAIL, and a threshold in each of the AT/BELOW/WITHIN forms
- **Expected:** all ten clauses land on the right field
- **Why:** ten clauses in one dispatcher and one missing `elif` is a clause that silently ends the control

### PQL-115 · Each modifier given twice is refused, naming the clause
- **Area:** `pql/parser.py::Parser._modifiers`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** for each of the ten clause names, parse a control carrying it twice
- **Expected:** "<clause> is given twice for this control", remedy explaining the ambiguity
- **Why:** the `seen` set is the only defence against a second WHERE silently replacing the first, and every clause must be in it

### PQL-116 · Two different thresholds count as one duplicated clause
- **Area:** `pql/parser.py::Parser._modifiers`, `_modifier_name`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `CHECK t.a IS NOT NULL AT MOST 5 ROWS BELOW 10%`
- **Expected:** "threshold is given twice for this control"
- **Why:** all three threshold spellings map to the single clause name `threshold`, which is what makes a row threshold and a rate threshold mutually exclusive

### PQL-117 · An unknown clause ends the control rather than erroring in place
- **Area:** `pql/parser.py::Parser._modifier_name`, `Parser.parse`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `CHECK t.a IS NOT NULL SEVERTIY major`
- **Expected:** the error names the stray word and its position, not "expected a control"
- **Why:** `_modifier_name` returns None for anything it does not recognise, so a misspelled clause surfaces as a top-level "expected a control and found 'SEVERTIY'" a line later than the mistake

### PQL-118 · Each severity value parses, in any case
- **Area:** `pql/parser.py::Parser._severity`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `SEVERITY` with each of info, warning, minor, major, critical, in lower, upper and mixed case
- **Expected:** the matching `Severity` member each time
- **Why:** `Severity(token.text.lower())` — fifteen spellings, one lookup

### PQL-119 · An unknown severity lists the real ones
- **Area:** `pql/parser.py::Parser._severity`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `SEVERITY high`, `SEVERITY p1`, `SEVERITY 3`
- **Expected:** "'high' is not a severity", remedy "Use one of: info, warning, minor, major, critical."
- **Why:** `high` and `p1` are what every other tool calls it; the remedy is the translation table

### PQL-120 · `SEVERITY` at the end of the control
- **Area:** `pql/parser.py::Parser._severity`, `_advance`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `CHECK t.a IS NOT NULL SEVERITY`
- **Expected:** a located error, not an infinite loop
- **Why:** `_advance` does not move past END, so a consumer that loops on "advance until valid" would spin; assert termination

### PQL-121 · Each dimension value parses, and several may be listed
- **Area:** `pql/parser.py::Parser._dimensions`, `_dimension`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `DIMENSION completeness`, then all eight names, then `DIMENSION validity, consistency, accuracy`
- **Expected:** the eight members resolve; the list preserves order
- **Why:** dimensions drive the scorecard, and a silently dropped one is a dimension that scores as uncovered

### PQL-122 · An unknown dimension lists the real ones
- **Area:** `pql/parser.py::Parser._dimension`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `DIMENSION correctness`
- **Expected:** "'correctness' is not a quality dimension", remedy listing all eight
- **Why:** the eight DAMA dimensions are not the eight everybody remembers

### PQL-123 · A duplicated dimension in one list
- **Area:** `pql/parser.py::Parser._dimensions`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** parse `DIMENSION validity, validity`
- **Expected:** documented — de-duplicated, or kept as written and rendered as written
- **Why:** `Control.render` joins the tuple, so a repeat survives a format cycle and shows twice on the console

### PQL-124 · `BECAUSE` requires quoted text
- **Area:** `pql/parser.py::Parser._text`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `BECAUSE it matters`, then `BECAUSE "it matters"` (double quotes)
- **Expected:** "expected the reason this control exists, in quotes, and found …", remedy naming single quotes
- **Why:** double quotes lex as an *identifier*, so the error must distinguish the two quoting characters rather than saying "expected text"

### PQL-125 · A BECAUSE containing a quote round-trips
- **Area:** `pql/parser.py::Parser._text`, `ast.Control.render`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `BECAUSE 'the desk''s own rule'`, render, re-parse
- **Expected:** the value is `the desk's own rule` both times
- **Why:** `render` re-doubles the quote; a single round trip is the only thing that proves both halves agree

### PQL-126 · An empty BECAUSE is accepted and then behaves as absent
- **Area:** `pql/parser.py::Parser._text`, `ast.Control.render`, `lint.Linter._missing_justification`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `CHECK t.a IS NOT NULL BECAUSE ''`
- **Expected:** documented — `because` is `""`, `render` omits the clause entirely, and the linter reports `no-justification`
- **Why:** an author who wrote an empty reason is told they wrote none, and the formatter deletes their clause — both defensible, neither obvious

### PQL-127 · `OWNER` requires quoted text and survives rendering
- **Area:** `pql/parser.py::Parser._apply_modifier`, `ast.Control.render`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `OWNER 'Head of Market Risk Data'`, render, re-parse
- **Expected:** preserved exactly; `render` emits `OWNER '…'`
- **Why:** the owner reaches `Provenance.declared_by` and is what an evidence record names

### PQL-128 · An owner containing a quote round-trips
- **Area:** `ast.Control.render`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `OWNER 'O''Brien'`, render, re-parse
- **Expected:** the same value twice
- **Why:** `render` escapes `because` with `.replace("'", "''")` but emits `OWNER '{self.owner}'` **unescaped** — an owner with an apostrophe renders to text that will not re-parse

### PQL-129 · Each evidence level parses
- **Area:** `pql/parser.py::Parser._evidence`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `EVIDENCE counts`, `EVIDENCE samples`, `EVIDENCE full`, `EVIDENCE samples (10)`
- **Expected:** the matching level, and `max_samples` 50 by default and 10 when given
- **Why:** `EVIDENCE counts` disables the sample query entirely in `SqlCompiler._samples`

### PQL-130 · An unknown evidence level is refused
- **Area:** `pql/parser.py::Parser._evidence`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `EVIDENCE all`, `EVIDENCE rows`
- **Expected:** "'all' is not an evidence level", remedy "Use counts, samples, or full."
- **Why:** three values and none of them is the word a person guesses

### PQL-131 · `EVIDENCE samples (0)` and a very large sample count
- **Area:** `pql/parser.py::Parser._evidence`, `_integer`, `backend/sql.py::SqlCompiler._samples`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `EVIDENCE samples (0)` and `EVIDENCE samples (1000000)`; compile both
- **Expected:** `LIMIT 0` and `LIMIT 1000000` respectively — assert whether a zero-sample policy is meant to behave as `counts`, and whether any upper bound applies
- **Why:** nothing bounds the sample count, and the sample query is the one that reads whole rows out of a production table

### PQL-132 · `EVIDENCE full (10)` loses the count on render
- **Area:** `ast.EvidenceSpec.render`, `ast.Control.render`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `EVIDENCE full (10)`, render, re-parse, compare
- **Expected:** equality
- **Why:** `EvidenceSpec.render` emits the parenthesised count only for `samples`, so `full (10)` renders as `EVIDENCE full` and re-parses with `max_samples=50` — `parse(render(x)) == x` fails

### PQL-133 · `TREAT UNKNOWN AS PASS` requires a BECAUSE
- **Area:** `pql/parser.py::Parser._finish`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `CHECK t.a > 0 TREAT UNKNOWN AS PASS`
- **Expected:** "TREAT UNKNOWN AS PASS needs a BECAUSE", remedy giving a worked justification
- **Why:** the one place the language demands a justification, because inverting the unknown policy is the decision that hides a wholly null column

### PQL-134 · `TREAT UNKNOWN AS VIOLATION` and `AS FAIL` both mean violation
- **Area:** `pql/parser.py::Parser._unknown_policy`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse both spellings
- **Expected:** `UnknownPolicy.VIOLATION`, and no BECAUSE is required for either
- **Why:** two spellings of the default; only the departure needs justifying

### PQL-135 · `TREAT UNKNOWN AS` anything else
- **Area:** `pql/parser.py::Parser._unknown_policy`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `TREAT UNKNOWN AS NULL`, `TREAT UNKNOWN AS IGNORE`
- **Expected:** the refusal, whose remedy states why the default is inverted from SQL's
- **Why:** that remedy is where the language's central decision is explained to whoever is trying to override it

### PQL-136 · `TREAT UNKNOWN AS PASS BECAUSE …` written in either order
- **Area:** `pql/parser.py::Parser._modifiers`, `_finish`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse with BECAUSE before and after the TREAT clause
- **Expected:** both accepted — `_finish` runs after every modifier, so order does not matter
- **Why:** `_finish` is the one check that depends on two clauses at once, and it must not be order-sensitive

### PQL-137 · Each `ON FAIL` action parses
- **Area:** `pql/parser.py::Parser._fail_action`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `ON FAIL alert`, `block`, `quarantine`, `tag`
- **Expected:** the matching `FailAction`
- **Why:** four actions, and `block` is the one that stops a pipeline

### PQL-138 · An unknown `ON FAIL` action is refused
- **Area:** `pql/parser.py::Parser._fail_action`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `ON FAIL stop`, `ON FAIL page`
- **Expected:** "'stop' is not something to do on failure", remedy listing all four
- **Why:** `stop` and `page` are the words an operator reaches for

### PQL-139 · `AT MOST n ROWS` and `AT LEAST n ROWS`
- **Area:** `pql/parser.py::Parser._threshold`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse both; inspect `Threshold.unit`, `.value`, `.comparator`
- **Expected:** `("rows", n, "<=")` and `("rows", n, ">=")`
- **Why:** the comparator is the only field that distinguishes them and it is the one `render` ignores

### PQL-140 · `AT LEAST n ROWS` renders as `AT MOST n ROWS`
- **Area:** `ast.Threshold.render`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `CHECK t.a IS NOT NULL AT LEAST 5 ROWS`, render, re-parse, compare
- **Expected:** equality
- **Why:** `Threshold.render` for `unit == "rows"` emits `AT MOST` unconditionally, so a formatter pass silently inverts the threshold of every `AT LEAST` control. `prama control format --write` would commit the change

### PQL-141 · A large row threshold renders in scientific notation
- **Area:** `ast.Threshold.render`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `AT MOST 1234567 ROWS`, render, re-parse, compare the value
- **Expected:** 1234567 both times
- **Why:** `f"{value:g}"` gives six significant figures, so the rendered text is `AT MOST 1.23457e+06 ROWS` and re-parsing yields 1234570 — a formatter that changes what a control tolerates. This is finding C3 in another file

### PQL-142 · A fractional row threshold
- **Area:** `pql/parser.py::Parser._threshold`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `AT MOST 0.5 ROWS`
- **Expected:** documented — either refused as not a whole number of rows, or accepted and judged as `violating_rows <= 0.5`
- **Why:** `_threshold` uses `_number_token` rather than `_integer`, so half a row is accepted; half a row is not a thing

### PQL-143 · `ROWS` and `ROW` are both optional after a count threshold
- **Area:** `pql/parser.py::Parser._threshold`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `AT MOST 5 ROWS`, `AT MOST 1 ROW`, `AT MOST 5`
- **Expected:** all three parse to the same unit
- **Why:** `_match_keyword("ROWS","ROW")` is optional, so `AT MOST 5` is legal and means rows — assert it, because the bare form is ambiguous with the amount threshold

### PQL-144 · `BELOW` with and without a percent sign mean different things
- **Area:** `pql/parser.py::Parser._rate`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `BELOW 0.5%` and `BELOW 0.5`
- **Expected:** rates of 0.005 and 0.5 respectively — a hundredfold apart
- **Why:** a data owner writing `BELOW 0.5` meaning "half a percent" gets "half of all rows", the control never fires, and it appears on the coverage report as covered. The linter only catches `>= 1.0`

### PQL-145 · `BELOW 100%` is refused by the linter, not the parser
- **Area:** `pql/parser.py::Parser._rate`, `lint.Linter._never_fires`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `BELOW 100%`, then lint it
- **Expected:** parses; lint finding `never-fires` at severity `error`
- **Why:** the division of labour between refusing and warning, and `--strict` in CI is what turns the second into the first

### PQL-146 · `BELOW 0%` is a strict rate
- **Area:** `pql/parser.py::Parser._rate`, `ast.Threshold.is_strict`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `BELOW 0%`; inspect `is_strict` and `render()`
- **Expected:** `is_strict` is True, but `render` still emits the clause because the unit is not `rows`
- **Why:** `Control.render` omits a threshold only when it is strict *and* in rows; the rate case must survive the round trip

### PQL-147 · `WITHIN n CCY` is an amount threshold
- **Area:** `pql/parser.py::Parser._threshold`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `WITHIN 100 USD`, `WITHIN 0.01 GBP`, `WITHIN 100`
- **Expected:** `unit == "amount"` with currency `USD`/`GBP`/`""`
- **Why:** the currency is detected by "an identifier of exactly three characters", which is a guess that has to be pinned

### PQL-148 · A three-letter *keyword* is not read as a currency
- **Area:** `pql/parser.py::Parser._threshold`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `WITHIN 100 SUM`, `WITHIN 100 MIN`, `WITHIN 100 KEY`, `WITHIN 100 ROW`
- **Expected:** documented — the currency test requires `kind is IDENTIFIER`, so these keywords are left unconsumed and the control ends, producing a top-level "expected a control" a token later
- **Why:** `SUM` is not a currency but `SEK` is, and the distinction here is token *kind* rather than meaning

### PQL-149 · `WITHIN n SIGMA` does not produce a sigma threshold
- **Area:** `pql/parser.py::Parser._threshold`, `ast.Threshold.render`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `CHECK t.a IS NOT NULL WITHIN 2 SIGMA`
- **Expected:** `Threshold(unit="sigma", value=2)`
- **Why:** `Threshold.render` and `.describe` both have a `sigma` branch, and `_threshold` can never produce one — `SIGMA` is a five-character identifier, so the threshold becomes `amount=2` with no currency and `SIGMA` is left over to fail as a stray token

### PQL-150 · An amount threshold silently becomes a row count
- **Area:** `ir/lower.py::Lowerer._threshold`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** lower `CHECK t.a IS NOT NULL WITHIN 100 USD` and inspect the IR threshold
- **Expected:** the amount and currency reach the plan
- **Why:** `_threshold` handles only `rate`/`percent` specially; everything else becomes `Threshold(metric="violating_rows", value=100.0)`. "Differences up to 100 USD are tolerated" is compiled as "up to 100 violating rows are tolerated", and the currency is discarded without a word

### PQL-151 · A threshold on an assertion that has no rate
- **Area:** `pql/parser.py` module docstring, `ir/lower.py::Lowerer._metrics`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse and lower `CHECK t HAS ROW COUNT AT LEAST 1 BELOW 10%`
- **Expected:** refused at authoring time
- **Why:** the parser's own docstring lists "a threshold on an assertion that has no rate" as something it refuses. It does not: the row-count path emits only `scanned_rows`, the rate threshold divides `violating_rows` by it, the metric is absent, and the verdict silently becomes INDETERMINATE

### PQL-152 · `FOR EACH` with one and several columns
- **Area:** `pql/parser.py::Parser._segmentation`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `FOR EACH entity`, `FOR EACH entity, ccy`
- **Expected:** the columns in order; `having` is None
- **Why:** segmentation is what keeps a finding from being averaged away, and multi-column grouping is untested by the corpus

### PQL-153 · `FOR EACH … HAVING …`
- **Area:** `pql/parser.py::Parser._segmentation`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `FOR EACH entity HAVING COUNT(*) > 100`
- **Expected:** the having expression is parsed and stored
- **Why:** the clause exists in the AST, is rendered, and — assert it — is carried into the IR and the SQL; a HAVING that is parsed and dropped is a segment filter nobody applies

### PQL-154 · `HAVING` never reaches the plan
- **Area:** `pql/parser.py::Parser._segmentation`, `ir/lower.py::Lowerer.control`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** lower `CHECK t.a IS NOT NULL FOR EACH entity HAVING COUNT(*) > 100` and inspect `Scope`
- **Expected:** the HAVING condition appears in the plan and in the emitted SQL
- **Why:** `Lowerer.control` reads only `control.segmentation.columns`; the `having` expression is parsed, rendered, and then silently discarded, so a control that says "only segments with more than 100 rows" is executed over all of them

### PQL-155 · `FOR EACH` on a segment column that is null
- **Area:** `backend/reference.py::ReferenceEvaluator._by_segment`, `backend/sql.py::SqlCompiler.compile`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** rows whose segment column is NULL
- **Steps:** run a segmented control over rows with a null `entity` on the reference interpreter and on each SQL engine
- **Expected:** the same set of segment keys and the same per-segment verdicts
- **Why:** the reference builds the key with `str(row.get(c))` → `"None"`, while SQL `GROUP BY` produces a NULL group the driver returns as `None` and `_judge` stringifies as `"None"` — assert they coincide rather than assuming it

### PQL-156 · Segment keys are ambiguous when a value contains the separator
- **Area:** `backend/reference.py::ReferenceEvaluator._by_segment`, `backend/conformance.py::ConformanceRun._judge`, `backend/fuse.py::FusedQuery._unpack_segmented`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a two-column segmentation where one value contains `|`
- **Steps:** segment by `(a, b)` with rows `("x|y", "z")` and `("x", "y|z")`
- **Expected:** two distinct segments
- **Why:** all three places join with `"|"`, so the two rows collide into one key and one segment's verdict is reported for the other

### PQL-157 · `FOR EACH` is judged on every segment
- **Area:** `backend/execute.py::judge_segments`
- **Type:** regression
- **Priority:** P1
- **Precondition:** five segments, one of which fails
- **Steps:** run a segmented control and inspect the result
- **Expected:** five `SegmentResult` entries; the overall verdict is FAIL
- **Why:** QA finding Q-11 recorded `FOR EACH` being judged on `rows[0]` alone, with the record's own samples contradicting its metrics

### PQL-158 · An indeterminate segment beside passing segments
- **Area:** `backend/execute.py::judge_segments`
- **Type:** negative
- **Priority:** P1
- **Precondition:** three segments, one empty after the filter
- **Steps:** judge segments where one returns `scanned_rows == 0`
- **Expected:** the overall verdict is not a clean `pass`
- **Why:** the overall rule is FAIL if any fails, INDETERMINATE only if *all* are indeterminate, and PASS otherwise — so one segment nobody could evaluate is absorbed into a green control, which is the same shape as finding C5

### PQL-159 · Segment totals sum metrics that cannot be summed
- **Area:** `backend/execute.py::judge_segments`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a segmented `HAS UNIQUE KEY` control
- **Steps:** inspect `ControlResult.metrics` on the segmented result
- **Expected:** either no aggregate `distinct_keys`, or one computed correctly
- **Why:** `totals` adds every metric across segments, and the sum of per-segment distinct counts is not the overall distinct count — a number on the evidence record that means nothing

## 5 · Expressions — `pql/parser.py`

### PQL-160 · Operator precedence, loosest to tightest
- **Area:** `pql/parser.py::PRECEDENCE`, `_expression`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `a OR b AND c`, `a = 1 + 2 * 3`, `a + b || c`, and assert the tree shape
- **Expected:** OR loosest, then AND, then comparison, then `+ - ||`, then `* / %`
- **Why:** five levels; a wrong one silently regroups a filter and the control still runs

### PQL-161 · `NOT` binds between AND and comparison
- **Area:** `pql/parser.py::NOT_LEVEL`, `_expression`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `NOT side = 'BUY'`
- **Expected:** `NOT (side = 'BUY')`, never `(NOT side) = 'BUY'`
- **Why:** the comment states the failure exactly — the wrong parse is "a different control, and a valid-looking one"

### PQL-162 · `NOT NOT a`
- **Area:** `pql/parser.py::_expression`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** parse `WHERE NOT NOT a`
- **Expected:** two nested `UnaryOp`s; renders back as `NOT NOT a` and re-parses
- **Why:** `_expression(NOT_LEVEL)` recurses at the same level, which is what makes repetition legal — assert it terminates

### PQL-163 · `BETWEEN` does not swallow its own AND
- **Area:** `pql/parser.py::Parser._between_bounds`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `CHECK t.n BETWEEN 1 AND 100 SEVERITY minor`
- **Expected:** bounds 1 and 100, severity minor
- **Why:** the docstring names the failure: parsed at the wrong level, "the rest of the control disappears into a boolean expression"

### PQL-164 · `BETWEEN` inside a WHERE clause
- **Area:** `pql/parser.py::Parser._predicate_suffix`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `WHERE n BETWEEN 1 AND 100 AND status = 'ACTIVE'`
- **Expected:** the second AND joins two predicates; the first belongs to BETWEEN
- **Why:** the same hazard one grammar level down, where there is a following AND to be confused with

### PQL-165 · `BETWEEN` with reversed bounds is a lint error, not a parse error
- **Area:** `lint.Linter._always_fires`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse and lint `BETWEEN 100 AND 1`
- **Expected:** lint finding `always-fires` at severity `error`, remedy "The bounds are the wrong way round."
- **Why:** a control every row violates is a control nobody will keep, and the parser cannot know without evaluating

### PQL-166 · Reversed *text* bounds are not caught
- **Area:** `lint.Linter._always_fires`
- **Type:** negative
- **Priority:** P3
- **Precondition:** none
- **Steps:** lint `CHECK t.code BETWEEN 'Z' AND 'A'`
- **Expected:** the same `always-fires` finding
- **Why:** the check requires both literals to be `int | float`, so the text case — the one a currency or a code range is written in — passes the linter silently

### PQL-167 · `IN` with one, several and many values
- **Area:** `pql/parser.py::Parser._list_expression`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `IN ('GBP')`, `IN ('GBP','USD')`, and a list of 1,000 values
- **Expected:** all parse; the 1,000-value list compiles to a single `IN (…)` and does not blow any recursion limit
- **Why:** a codelist expands into exactly this shape, and ISO 4217 alone is ~180 values

### PQL-168 · `IN ()` is refused with a caret on the brackets
- **Area:** `pql/parser.py::Parser._list_expression`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `CHECK t.ccy IN ()`
- **Expected:** "an empty set of values", remedy naming `IS NULL` for the "must be empty" intent
- **Why:** the comment says it is caught here rather than by the linter because an empty set fails every row — a mistake, not a style

### PQL-169 · A trailing comma in a list
- **Area:** `pql/parser.py::Parser._list_expression`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `IN ('GBP', 'USD',)`
- **Expected:** a located refusal naming the `)`
- **Why:** a trailing comma is legal in most modern languages and illegal here; the error must be about the comma, not about the close bracket

### PQL-170 · `NOT IN`, `NOT BETWEEN`, `NOT MATCHES`, `NOT LIKE`, `NOT ILIKE` inside an expression
- **Area:** `pql/parser.py::Parser._predicate_suffix`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse each in a WHERE clause
- **Expected:** a single `BinaryOp` whose operator carries the `NOT ` prefix
- **Why:** the two-token lookahead (`NOT` followed by one of five keywords) is what distinguishes these from a boolean `NOT`

### PQL-171 · `LIKE` and `ILIKE` are expression-only
- **Area:** `pql/parser.py::Parser._predicate`, `_predicate_suffix`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `CHECK t.a LIKE 'x%'` as an assertion, then the same inside `WHERE`
- **Expected:** the assertion form is refused with "expected a comparison after t.a"; the WHERE form parses
- **Why:** an asymmetry between the assertion catalogue and the expression grammar that nothing states — and `LIKE` is the predicate everybody reaches for first

### PQL-172 · `LIKE` has no SQL form
- **Area:** `pql/parser.py::Parser._predicate_suffix`, `ir/lower.py::Lowerer._expression`, `backend/sql.py::SqlCompiler._operation`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** compile `CHECK t.a IS NOT NULL WHERE b LIKE 'x%'` for postgresql
- **Expected:** working SQL, or a refusal at authoring time
- **Why:** `LIKE`, `ILIKE`, `NOT LIKE` and `NOT ILIKE` lower to `Expr.operation("LIKE", …)`, which is in neither `INFIX` nor any branch of `_operation` — so the compiler raises "LIKE has no SQL form on postgresql" for a predicate the grammar accepts, and the reference interpreter raises a bare `KeyError` from `_compare`

### PQL-173 · A parenthesised expression
- **Area:** `pql/parser.py::Parser._primary`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `WHERE (a OR b) AND c`
- **Expected:** the parenthesis survives as tree shape; `render()` re-emits the brackets because the child binds more loosely
- **Why:** `render_within` is the only thing standing between a re-parse and a different control

### PQL-174 · An unclosed parenthesis
- **Area:** `pql/parser.py::Parser._primary`, `_expect_punctuation`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `WHERE (a OR b`
- **Expected:** "expected ')' and found the end of the control"
- **Why:** the commonest expression typo, and the position must be at the end rather than at the opening bracket

### PQL-175 · Deep nesting does not exhaust the stack
- **Area:** `pql/parser.py::Parser._expression`, `_primary`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse a WHERE clause with 1,000 nested parentheses, then 5,000
- **Expected:** either a parse or a located refusal — never a `RecursionError` traceback
- **Why:** recursive descent with no depth limit, reached from an HTTP endpoint that accepts PQL text; Q-23 already records orjson's recursion limit producing a 500

### PQL-176 · An expression with 1,000 OR terms
- **Area:** `pql/parser.py::Parser._expression`, `backend/sql.py::SqlCompiler._operation`
- **Type:** performance
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse, lower and compile `WHERE a=1 OR a=2 OR … (1,000 terms)`
- **Expected:** it completes in reasonable time and the emitted SQL is accepted by each engine
- **Why:** the loop in `_expression` is iterative but `Expr.requires` and `columns()` recurse over the whole left-leaning tree, once per call

### PQL-177 · A control with 500 columns
- **Area:** `pql/parser.py::Parser._column_list`, `ir/model.py::ControlPlan.columns`, `backend/sql.py::SqlCompiler._samples`
- **Type:** performance
- **Priority:** P3
- **Precondition:** none
- **Steps:** a `HAS UNIQUE KEY` over 500 columns; compile it
- **Expected:** the SQL is emitted and each dialect's `count_distinct` produces something the engine accepts
- **Why:** SQLite's composite form concatenates all 500 with `CHAR(31)` separators, DuckDB builds a 500-field struct, and PostgreSQL a 500-element row constructor — three different limits

### PQL-178 · A function call with zero, one and many arguments
- **Area:** `pql/parser.py::Parser._call`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `COUNT(*)`, `COUNT(a)`, `COUNT(DISTINCT a)`, `CONCAT(a, b, c)`
- **Expected:** `arguments == ()` for `COUNT(*)`; `distinct` True only for the third
- **Why:** `*` is consumed and discarded, so `COUNT(*)` and `COUNT()` produce the same AST — assert whether `COUNT()` should be refused

### PQL-179 · A bare non-deterministic name is refused
- **Area:** `pql/parser.py::Parser._identifier_expression`, `NON_DETERMINISTIC`
- **Type:** regression
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `CHECK t.d < CURRENT_DATE`, then the same for NOW, CURRENT_TIMESTAMP, CURRENT_TIME, GETDATE, SYSDATE, RANDOM, RAND, UUID, NEWID
- **Expected:** all ten refused, with the replay remedy naming `$business_date`
- **Why:** QA finding Q-16 — bare `CURRENT_DATE` parsed as a column of that name and sailed through the guard that only covered calls

### PQL-180 · The called form is refused too
- **Area:** `pql/parser.py::Parser._call`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `NOW()`, `RANDOM()`, `UUID()`
- **Expected:** the same refusal
- **Why:** two guards, two spellings, one message — and the message is where replay is explained

### PQL-181 · The two volatile lists disagree
- **Area:** `pql/parser.py::NON_DETERMINISTIC`, `pql/functions.py::VOLATILE`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `TODAY()`, `RANDBETWEEN(1,2)`, `INDIRECT('a')`, `OFFSET(a,1,1)` in PQL; then `CURRENT_DATE`, `SYSDATE`, `UUID` in an Excel formula
- **Expected:** every volatile name is refused on both surfaces with the same replay reason
- **Why:** `NON_DETERMINISTIC` has ten names and `VOLATILE` has six, overlapping in one (`NOW`). So `TODAY()` passes the PQL parser and fails later as a `ValidationError` with no position, while `CURRENT_DATE` passes the Excel parser and becomes a *column reference*. Two lists, one property

### PQL-182 · A quoted column named after a volatile function
- **Area:** `pql/parser.py::Parser._identifier_expression`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a real column called `current_date`
- **Steps:** parse `CHECK t."current_date" IS NOT NULL`
- **Expected:** documented — the quoted form is currently refused too, because `token.value` is compared against the list
- **Why:** the escape hatch for awkward names does not escape this guard, so a table with a column of that name cannot be checked at all

### PQL-183 · A function whose name is a keyword
- **Area:** `pql/parser.py::Parser._identifier_expression`, `_primary`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `WHERE LENGTH(a) > 5`, `WHERE COUNT(a) > 5`, `WHERE MIN(a) > 5`
- **Expected:** all three become `FunctionCall`; `LENGTH`, `COUNT` and `MIN` are keywords and must still call
- **Why:** `_primary` routes both IDENTIFIER and KEYWORD to `_identifier_expression`, which is what makes the catalogue reachable at all

### PQL-184 · A function cannot be an assertion subject
- **Area:** `pql/parser.py::Parser._target`, `_assertion`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `CHECK LENGTH(t.isin) = 12`
- **Expected:** a comprehensible refusal pointing at the required `SATISFIES` form
- **Why:** `_target` reads `LENGTH` as a dataset name and then fails on `(` with "expected something to check about LENGTH" — technically correct and useless, when the answer is `CHECK t SATISFIES LENGTH(isin) = 12`

### PQL-185 · Aggregate names are upper-cased, scalar names are not
- **Area:** `pql/parser.py::Parser._call`, `AGGREGATES`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `count(a)`, `upper(a)` and inspect `FunctionCall.name`
- **Expected:** `"COUNT"` and `"upper"`
- **Why:** the asymmetry is deliberate and load-bearing: `type_of` looks up `_AGGREGATE_TYPES` by `name.upper()` and `check_calls` by `name.upper()`, so the stored case must not change the answer

### PQL-186 · `MEDIAN` is in the aggregate list and nowhere else
- **Area:** `pql/parser.py::AGGREGATES`, `pql/types.py::_AGGREGATE_TYPES`, `backend/sql.py::_AGGREGATES`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** type-check and compile `CHECK t SATISFIES MEDIAN(notional) > 0`
- **Expected:** it works, or it is refused at authoring time with a reason
- **Why:** `MEDIAN` is a keyword and a parser aggregate, but is absent from `types._AGGREGATE_TYPES`, from `backend.sql._AGGREGATES` and from the function catalogue — so the type checker reports "there is no function called MEDIAN" and the compiler refuses it. Three lists of aggregates, all different

### PQL-187 · `MIN` and `MAX` collide with the scalar catalogue
- **Area:** `pql/types.py::_AGGREGATE_TYPES`, `pql/library.py::NUMBER_FUNCTIONS`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** type-check `CHECK t SATISFIES MIN(notional) > 0`
- **Expected:** no finding — `MIN(column)` is the aggregate
- **Why:** `_AGGREGATE_TYPES` spells them `MIN_AGG` and `MAX_AGG`, which the parser never produces, so `check_calls` falls through to the *scalar* `MIN` whose arity is `(2, VARIADIC)` and reports "MIN takes at least 2 argument(s), and was given 1". The compiler then renders `LEAST(x)` for it

### PQL-188 · A parameter in every position it is legal
- **Area:** `pql/parser.py::Parser._primary`, `ir/model.py::ControlPlan.parameters`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `CHECK t.d = $business_date`, `WHERE d >= $from AND d < $to`, `BETWEEN $lo AND $hi`
- **Expected:** every parameter name appears in `plan.parameters()` and in `CompiledControl.parameters`
- **Why:** the run refuses to execute a plan whose parameters it cannot bind, and a parameter the plan does not declare is one nobody binds

### PQL-189 · A parameter used only inside a metric expression is not declared
- **Area:** `ir/model.py::ControlPlan.parameters`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a plan whose metric expression references a parameter
- **Steps:** build such a plan and call `parameters()`
- **Expected:** the parameter is listed
- **Why:** `parameters()` walks `scope.filter`, `predicate` and `scope.as_of` only — a metric expression is not consulted, so the SQL emits `:name` for something the executor was never told to bind

### PQL-190 · `TRUE`, `FALSE` and `NULL` literals
- **Area:** `pql/parser.py::Parser._primary`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `WHERE flag = TRUE`, `WHERE a IS NULL`, `WHERE a = NULL`
- **Expected:** boolean and null literals with the right `literal_type`; `= NULL` parses and is *always unknown* at evaluation
- **Why:** `a = NULL` is the classic SQL mistake and the language reproduces it faithfully — assert the three-valued outcome rather than a false

### PQL-191 · A percentage literal inside an expression
- **Area:** `pql/parser.py::Parser._primary`, `ast.Literal.render`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `WHERE rate > 10%`, render, re-parse
- **Expected:** the value is 0.1 both times
- **Why:** a percentage is a number divided by a hundred at parse time, and `render` multiplies it back with `:g` — see the round-trip case for the precision loss

### PQL-192 · A unary sign on a non-literal
- **Area:** `pql/parser.py::Parser._unary`, `ir/lower.py::_fold_sign`, `backend/sql.py::SqlCompiler._operation`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse, lower and compile `WHERE -notional > 0` and `WHERE - (a + b) > 0`
- **Expected:** `_fold_sign` declines (the operand is not a literal), the IR keeps a unary op, and the SQL is `(-"notional")` — the sign is not dropped
- **Why:** the compiler comment names the failure: joining one operand with an infix separator yields the operand alone and "every engine agrees on the wrong answer"

### PQL-193 · `- -1` and `+ -1`
- **Area:** `pql/parser.py::Parser._unary`, `ir/lower.py::_fold_sign`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** parse `WHERE a > - -1`
- **Expected:** a nested unary that folds to the literal 1, or a nested op — never a dropped sign
- **Why:** `_fold_sign` only folds when the operand is a `Literal`, so the outer minus of a nested pair does not fold and both spellings must still mean 1

### PQL-194 · `-10` and `- 10` hash the same
- **Area:** `ir/lower.py::_fold_sign`, `ir/model.py::ControlPlan.plan_id`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** lower `BETWEEN -10 AND 10` and `BETWEEN - 10 AND 10`; compare `plan_id`
- **Expected:** identical
- **Why:** the comment states it: "two spellings of one control must not become two controls", and the plan id is what evidence names

### PQL-195 · A boolean is not folded as a sign
- **Area:** `ir/lower.py::_fold_sign`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** lower `WHERE a > -TRUE`
- **Expected:** not folded to `-1`; `isinstance(value, bool)` is excluded explicitly
- **Why:** `True` is an `int` in Python and folding it would turn a type error into the number one

## 6 · The AST, rendering and the formatter — `pql/ast.py`, `cli/control.py::ControlFormatCommand`

### PQL-196 · `parse(render(x)) == x` for every assertion kind
- **Area:** `pql/ast.py::Control.render`, `parser.parse_control`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** for each of the nine assertion kinds — predicate (each of its thirteen operators), unique key, row count, reference, freshness, expression, Excel expression, functional dependency — parse, render, re-parse and compare ASTs
- **Expected:** equality at every step
- **Why:** `Node.position` is excluded from equality precisely so this property can be asserted, and the docstring says comparing rendered strings instead "would have missed the parenthesisation bug that prompted this"

### PQL-197 · `render(parse(render(x))) == render(x)` — the formatter has a fixed point
- **Area:** `pql/ast.py::Control.render`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** render each corpus and worked-example control twice through a parse
- **Expected:** the second render is byte-identical to the first
- **Why:** a formatter whose output is not its own input produces an infinite diff in CI

### PQL-198 · `BINDING` agrees with `PRECEDENCE`
- **Area:** `pql/ast.py::BINDING`, `pql/parser.py::PRECEDENCE`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** derive the relative order of every operator from `PRECEDENCE` and compare with `BINDING`
- **Expected:** the two tables induce the same ordering
- **Why:** the comment on `BINDING` says it "must agree with the parser's PRECEDENCE, or the formatter emits text that means something else"; nothing derives one from the other

### PQL-199 · `!=` is missing from `BINDING` and `COMPARISONS`
- **Area:** `pql/ast.py::BINDING`, `COMPARISONS`, `pql/excel.py::OPERATORS`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** build a `BinaryOp(operator="!=")` — which is exactly what the Excel parser produces for `<>` — and render it inside a larger expression
- **Expected:** correct bracketing
- **Why:** `BINDING.get("!=")` misses and returns `ATOM_BINDING`, so a `!=` comparison is treated as binding tighter than multiplication and is never bracketed; `COMPARISONS` also misses it, so the type checker skips it

### PQL-200 · Bracketing is added exactly where meaning would change
- **Area:** `pql/ast.py::Expression.render_within`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** render `(a OR b) AND c`, `a - (b - c)`, `a / (b / c)`, `a AND (b OR c)`
- **Expected:** brackets retained in all four; `a AND b AND c` and `a - b - c` keep none
- **Why:** left-associativity plus the "right operand at equal binding" rule is the whole algorithm, and `a - (b - c)` is the case that proves it

### PQL-201 · `BETWEEN` bounds are bracketed above AND
- **Area:** `pql/ast.py::BinaryOp.render`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** render a `BETWEEN` whose upper bound is itself `x AND y`
- **Expected:** the bounds bracket, so the text does not read as `BETWEEN (lower AND upper)`
- **Why:** the comment says getting this wrong makes the rendered control "stop being this control"

### PQL-202 · `render_head` folds the column into the target
- **Area:** `pql/ast.py::PredicateAssertion.render_head`, `ReferenceAssertion.render_head`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** render a control on `positions.lei`
- **Expected:** `CHECK positions.lei IS NOT NULL`, never `CHECK positions positions.lei IS NOT NULL`
- **Why:** the docstring says the naive concatenation "emits the dataset twice, which does not parse", and a formatter whose output will not re-read is worse than none

### PQL-203 · `render_selected` omits the placeholder
- **Area:** `pql/ast.py::Assertion.render_selected`, `PredicateAssertion.render_selected`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** render `CHECK EVERY ATTRIBUTE WHERE is_cde IS NOT NULL`
- **Expected:** exactly that text; not `… is_cde ATTRIBUTE IS NOT NULL`
- **Why:** the `SelectedAttribute` placeholder renders as the word `ATTRIBUTE`, which is legal-looking and wrong

### PQL-204 · A `SelectedAttribute` that reaches execution fails loudly
- **Area:** `pql/ast.py::SelectedAttribute`, `ir/lower.py::Lowerer._expression`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** lower a template control without expanding it
- **Expected:** `ValidationError` "SelectedAttribute has no IR form", not a column named `""`
- **Why:** the placeholder's docstring makes exactly this promise, and it is the only thing stopping an unexpanded control from querying a nameless column

### PQL-205 · A control's default threshold is omitted from the render
- **Area:** `pql/ast.py::Control.render`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** render a control with the default threshold, then one with `AT MOST 5 ROWS`, then one with `BELOW 0%`
- **Expected:** the first omits the clause, the other two emit it
- **Why:** the condition is `not is_strict or unit != "rows"`, so a strict *rate* threshold is still printed — assert both halves

### PQL-206 · `SEVERITY` is always rendered, even at the default
- **Area:** `pql/ast.py::Control.render`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** render a control with no explicit severity
- **Expected:** `SEVERITY major` appears
- **Why:** the formatter adds a clause the author did not write; every other default is omitted, so the inconsistency should be deliberate

### PQL-207 · `Control.name` is never set and never rendered
- **Area:** `pql/ast.py::Control.name`, `pql/analysis.py::LanguageService.diagnostics`
- **Type:** documentation
- **Priority:** P3
- **Precondition:** none
- **Steps:** parse any control and inspect `.name`; then look at an editor diagnostic's `control` field
- **Expected:** consistent behaviour
- **Why:** no production assigns `name`, no render emits it, and `diagnostics` does `control.name or f"control {i+1}"` — so the fallback is the only branch that ever runs and the field is dead weight in the equality key

### PQL-208 · `derived_from` is excluded from equality
- **Area:** `pql/ast.py::Control.derived_from`
- **Type:** contract
- **Priority:** P1
- **Precondition:** an attribute catalogue
- **Steps:** expand a selector control, render one of the results, re-parse and compare with the expanded control
- **Expected:** equal — provenance is not part of what a control does
- **Why:** the field's comment says including it "would break `parse(render(x)) == x` for every expanded control — the property that makes an estate exportable and reviewable"

### PQL-209 · A percentage round-trips losing precision
- **Area:** `pql/ast.py::Literal.render`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `WHERE r > 0.1234567%`, render, re-parse and compare values
- **Expected:** equality
- **Why:** `f"{value*100:g}"` is six significant figures, so `0.001234567` renders as `0.123457%` — a formatter that changes a number

### PQL-210 · A float literal round-trips exactly
- **Area:** `pql/ast.py::Literal.render`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse and re-render `0.1`, `1e20`, `1e-20`, `1.7976931348623157e308`, `1234567890123456789`
- **Expected:** each re-parses to the same value; `str(float)` is round-trippable and `_NUMBER` must accept what it produces
- **Why:** `Literal.render` falls through to `str(self.value)`, and the lexer's number pattern is what decides whether that text is readable again

### PQL-211 · An integer literal stays an integer
- **Area:** `pql/parser.py::Parser._primary`, `pql/ast.py::Literal.render`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `> 1`, render
- **Expected:** `> 1`, not `> 1.0`
- **Why:** the parser chooses `int` or `float` by looking for `.` or `e` in the text, and the IR hashes the value — so `1` and `1.0` are two plan ids for one control

### PQL-212 · A text literal containing every awkward character
- **Area:** `pql/ast.py::Literal.render`, `backend/dialect.py::SqlDialect.literal`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** round-trip a literal containing `'`, `"`, `\`, a newline, a tab, a NUL and an emoji
- **Expected:** the PQL round trip preserves them or refuses them; the SQL literal escapes only `'`
- **Why:** `SqlDialect.literal` doubles quotes and does nothing else, so a backslash reaches PostgreSQL's standard-conforming-strings setting and a newline reaches the query text

### PQL-213 · `describe()` for every assertion kind
- **Area:** `pql/ast.py::Assertion.describe`, `Control.describe`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** call `describe()` on one control of every assertion kind and every predicate operator
- **Expected:** a grammatical English sentence in each case, ending in a full stop
- **Why:** `Control.describe` is carried into the plan as `description` and is what an evidence record shows to a data owner; a `KeyError` from an operator missing from `_plain` would be raised at lowering time

### PQL-214 · `describe()` states the unknown policy only when it departs from the default
- **Area:** `pql/ast.py::Control.describe`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** describe the same control with each unknown policy
- **Expected:** only the `PASS` version mentions undetermined rows
- **Why:** the comment says stating the default on every control "trains people to skip the line, and then they skip it on the one control where it was changed"

### PQL-215 · `describe()` omits the threshold for a strict structural assertion
- **Area:** `pql/ast.py::Control.describe`, `Assertion.is_structural`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** describe a `HAS UNIQUE KEY` with the default threshold, and the same with `AT MOST 5 ROWS`
- **Expected:** the first says nothing about tolerance; the second does
- **Why:** "a declared unique key that tolerated duplicates would not be a key" — the omission is the claim

### PQL-216 · `describe()` finishes the author's sentence
- **Area:** `pql/ast.py::Control.describe`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** describe controls whose BECAUSE ends with nothing, with `.`, with `?`, with trailing whitespace, and with an emoji
- **Expected:** exactly one terminating full stop in each case
- **Why:** the `rstrip` and `endswith((".","!","?"))` pair is the only punctuation logic in the product, and it is printed to a regulator

### PQL-217 · `describe()` on a selector control
- **Area:** `pql/ast.py::Control.describe`, `Selector.describe`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** describe `CHECK EVERY ATTRIBUTE WHERE is_cde IS NOT NULL` and `CHECK CONCEPT Instrument.ISIN IS VALID isin`
- **Expected:** "For every attribute where is_cde, every one has a value." and the concept equivalent
- **Why:** `_bare` renders a `SelectedAttribute` as the word "one" so the sentence does not shout the placeholder — assert the whole sentence reads

### PQL-218 · `Program.render` and `Suite.render` round-trip
- **Area:** `pql/ast.py::Program.render`, `Suite.render`, `_indent`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse a document with two top-level controls and two suites; render; re-parse; compare
- **Expected:** equality, with suite membership preserved
- **Why:** the only place indentation is generated, and the only place suite structure is emitted

### PQL-219 · `prama control format` destroys suites
- **Area:** `cli/control.py::ControlFormatCommand.run`, `_read`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a `.pql` file containing a `SUITE`
- **Steps:** `prama control format suite.pql`, then `--write`
- **Expected:** the suite survives
- **Why:** `_read` returns `parse(source).all_controls`, flattening suites away, and the formatter joins the controls at top level — so `--write` permanently deletes the `SUITE name { … }` wrapper from the file. `Suite.render` exists and is never called from the CLI

### PQL-220 · `prama control format` refuses to clobber an unparseable file
- **Area:** `cli/control.py::ControlFormatCommand.run`, `_read`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a `.pql` file with a syntax error
- **Steps:** `prama control format bad.pql --write`; check the file afterwards
- **Expected:** exit non-zero, the error rendered with its caret, and the file byte-identical
- **Why:** a formatter that truncates a file it could not read is the worst bug a formatter can have

### PQL-221 · `prama control format` is idempotent on its own output
- **Area:** `cli/control.py::ControlFormatCommand.run`
- **Type:** contract
- **Priority:** P1
- **Precondition:** any `.pql` file
- **Steps:** format, write, format again
- **Expected:** the second run reports "already canonical" and changes nothing
- **Why:** the command reports `rewritten` vs `already canonical` by comparing against the original source, so a non-idempotent render makes every run report a change

### PQL-222 · `prama control format` discards comments
- **Area:** `cli/control.py::ControlFormatCommand.run`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** a file with `--` and `/* */` comments between controls
- **Steps:** format with `--write`
- **Expected:** documented behaviour, and a warning before anything is deleted
- **Why:** the lexer discards comments and the AST has nowhere to put them, so `--write` silently deletes every comment in the estate — defensible only if it is said out loud

### PQL-223 · Formatting an expanded estate
- **Area:** `cli/control.py::ControlFormatCommand`, `pql/expand.py::Expander._bind`
- **Type:** functional
- **Priority:** P2
- **Precondition:** an expanded selector estate written to a file
- **Steps:** format it and re-parse
- **Expected:** every control round-trips; the generated `BECAUSE 'Selected by …'` survives
- **Why:** the generated justification contains the selector's rendered text, which contains quotes when the selector's condition does — and `render` escapes `because` but the selector text inside it was already escaped once

## 7 · The type checker — `pql/types.py`

### PQL-224 · A control against a declared dataset with correct columns has no findings
- **Area:** `pql/types.py::TypeChecker.check`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `Catalogue.of(positions={"account_id": "varchar", "notional": "numeric"})`
- **Steps:** check `CHECK positions.notional > 0`
- **Expected:** `[]`
- **Why:** the happy path; everything else is measured against it

### PQL-225 · An unknown column is a finding with a suggestion
- **Area:** `pql/types.py::TypeChecker._resolve`, `DatasetSchema.suggest`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a schema with `account_id`
- **Steps:** check `CHECK positions.acount_id IS NOT NULL`
- **Expected:** "positions has no column called acount_id", remedy "Did you mean account_id?"
- **Why:** the near-miss is the commonest mistake and the suggestion is what makes the checker worth running

### PQL-226 · A column with no near miss lists what is available
- **Area:** `pql/types.py::TypeChecker._resolve`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a schema with 20 columns
- **Steps:** check a control naming `zzz`
- **Expected:** "Columns available: …" with twelve names and a trailing `…`
- **Why:** the truncation at twelve is a deliberate limit; assert the ellipsis appears only when it should

### PQL-227 · The suggestion is case-insensitive and generous
- **Area:** `pql/types.py::DatasetSchema.suggest`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a schema with `account_id`
- **Steps:** suggest for `ACCOUNT_ID`, `accountid`, `account_ids`, `acct_id`
- **Expected:** the first three match at cutoff 0.6; the fourth documents where the cutoff lands
- **Why:** the docstring names the three mistakes it is tuned for — wrong case, missing underscore, plural

### PQL-228 · Column resolution is case-insensitive but compilation is not
- **Area:** `pql/types.py::DatasetSchema.column`, `backend/dialect.py::SqlDialect.quote`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a PostgreSQL table with a lower-case column `account_id`
- **Steps:** check and then compile `CHECK positions.ACCOUNT_ID IS NOT NULL`
- **Expected:** consistent behaviour — either both accept it or both refuse it
- **Why:** `column()` lower-cases both sides so the checker passes, and `quote()` emits `"ACCOUNT_ID"` verbatim so PostgreSQL reports a missing column at run time. The checker exists to stop exactly that

### PQL-229 · An undeclared dataset is `unchecked`, not `error`
- **Area:** `pql/types.py::TypeChecker.check`
- **Type:** functional
- **Priority:** P1
- **Precondition:** an empty catalogue
- **Steps:** check any control
- **Expected:** one finding at level `unchecked`, naming the dataset, with a remedy about declaring or binding it
- **Why:** the module docstring: refusing to check at all "would be less useful than checking what can be checked and saying what could not"

### PQL-230 · An undeclared dataset suppresses every other check
- **Area:** `pql/types.py::TypeChecker.check`
- **Type:** negative
- **Priority:** P2
- **Precondition:** an empty catalogue
- **Steps:** check `CHECK t.a > 'ACTIVE' WHERE UPPER(b, c) = 1`
- **Expected:** the function-arity finding is reported even though the schema is unknown
- **Why:** `check` returns early after the `unchecked` finding, so only `_function_check` — which runs first, deliberately — survives; assert that the early return does not swallow anything else it should not

### PQL-231 · A column of another dataset is refused
- **Area:** `pql/types.py::TypeChecker._resolve`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a catalogue with `positions` and `accounts`
- **Steps:** check `CHECK positions.a IS NOT NULL WHERE accounts.b = 1`
- **Expected:** "accounts.b belongs to accounts, but this control is about positions", with a remedy about declaring the relationship
- **Why:** guessing at an undeclared join "would be worse than saying so", and this is the one cross-dataset guard

### PQL-232 · Comparable and incomparable family pairs
- **Area:** `pql/types.py::COMPARABLE`, `TypeChecker._compare`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a schema with one column of each family
- **Steps:** compare every ordered pair of `number`, `text`, `boolean`, `temporal`, `unknown`
- **Expected:** number/number, text/text, boolean/boolean, temporal/temporal and temporal/text are accepted; every pair involving `unknown` is accepted; the remaining pairs are findings
- **Why:** twenty-five combinations, five permitted, and the comment explains why text/number is not among them

### PQL-233 · Every entry of `TYPE_FAMILIES` maps
- **Area:** `pql/types.py::TYPE_FAMILIES`, `Column.family`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** for each of the ~40 source type names, build a `Column` and read `.family`
- **Expected:** the declared family; `VARCHAR(255)`, `NUMERIC(18,2)` and `TIMESTAMP WITH TIME ZONE` all resolve after the parenthesis is stripped and the case lowered
- **Why:** `base = type_name.lower().split("(")[0].strip()` is the whole normalisation, and `timestamp with time zone` contains spaces that survive it

### PQL-234 · An unrecognised source type becomes `unknown`, not an error
- **Area:** `pql/types.py::Column.family`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a column declared `HUGEINT`, `JSONB`, `ARRAY<INT>`, `GEOGRAPHY`
- **Steps:** compare each against a number and against text
- **Expected:** no findings — `unknown` suppresses type errors
- **Why:** the comment says "a wrong type error is worse than none", and warehouse type names are unbounded

### PQL-235 · `x IS NULL` is typed as a number
- **Area:** `pql/types.py::TypeChecker.type_of`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a declared schema
- **Steps:** type-check `CHECK t.a IS NOT NULL WHERE (b IS NULL) = TRUE`
- **Expected:** no finding — `IS NULL` yields a boolean
- **Why:** `type_of` for a `UnaryOp` returns `BOOLEAN if node.operator.isalpha() else NUMBER`, and `"IS NULL"` contains a space so `.isalpha()` is False — every null test is typed as a number, and comparing one with a boolean is reported as an error

### PQL-236 · A null literal is `unknown`, not an error against anything
- **Area:** `pql/types.py::TypeChecker.type_of`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a schema with a text column
- **Steps:** check `WHERE a = NULL`
- **Expected:** no type finding
- **Why:** `null` maps to `UNKNOWN`, which is comparable with everything — the type checker deliberately does not object to a construct that is always unknown at run time

### PQL-237 · A parameter suppresses type checking
- **Area:** `pql/types.py::TypeChecker.type_of`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a schema with a text column
- **Steps:** check `WHERE text_col > $threshold`
- **Expected:** no finding
- **Why:** "the run supplies it; its type is not knowable here, and guessing would produce errors on correct controls" — assert the suppression is total

### PQL-238 · The `IN` list is checked element by element
- **Area:** `pql/types.py::TypeChecker._compare`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a schema with `ccy VARCHAR(3)`
- **Steps:** check `CHECK t.ccy IN ('GBP', 2, 'EUR')`
- **Expected:** exactly one finding, naming the `2`
- **Why:** the recursion over `ListExpression` items is what turns one bad element into one precise message rather than one vague one

### PQL-239 · A `matches` against a non-text subject is a finding
- **Area:** `pql/types.py::TypeChecker._check_predicate`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a schema with `notional numeric`
- **Steps:** check `CHECK t.notional MATCHES /^[0-9]+$/`
- **Expected:** "a pattern cannot be matched against a number", remedy naming BETWEEN
- **Why:** the compiler casts to text before matching, so without this check the control would silently succeed on the string form of a number

### PQL-240 · The reference-argument operators skip the comparison
- **Area:** `pql/types.py::TypeChecker._check_predicate`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a schema with a text and a numeric column
- **Steps:** check `IS VALID isin`, `IN CODELIST iso4217`, `HAS FORMAT iban`, `MATCHES /x/` on both columns
- **Expected:** no spurious "text compared with text" findings — the argument names a thing, not a value
- **Why:** the skip list has four entries, and the one missing from it (`has_length_between`) is the defect in PQL-092

### PQL-241 · `SATISFIES` conditions are never type-checked
- **Area:** `pql/types.py::TypeChecker._type_check`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a schema with `notional numeric` and `status varchar`
- **Steps:** check `CHECK t SATISFIES notional > 'ACTIVE'`
- **Expected:** a finding — the same one `WHERE notional > 'ACTIVE'` produces
- **Why:** `_type_check` calls `_check_expression` on `control.where` only. The library's headline divergence — "No implicit coercion. Excel's `"1" + 1` is `2`. Here it is a type error at check time" — is unenforced on the surface where an Excel formula lands

### PQL-242 · A `HAVING` expression is never function-checked or type-checked
- **Area:** `pql/types.py::_expressions_of`, `_type_check`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a declared schema
- **Steps:** check `CHECK t.a IS NOT NULL FOR EACH e HAVING NONSENSE(b) > 1`
- **Expected:** "there is no function called NONSENSE"
- **Why:** `_expressions_of` walks `where` and four assertion attributes; `segmentation.having` is in neither it nor `_type_check`, though `_columns_of` does resolve its columns — so the names are checked and the calls are not

### PQL-243 · Unknown function names are caught before the schema is
- **Area:** `pql/types.py::TypeChecker.check`, `check_calls`
- **Type:** functional
- **Priority:** P1
- **Precondition:** an empty catalogue
- **Steps:** check `CHECK t.a IS NOT NULL WHERE UPPERR(b) = 'X'`
- **Expected:** "there is no function called UPPERR" plus the `unchecked` dataset finding
- **Why:** the comment explains the ordering: "a misspelled function is misspelled whether or not the dataset has been declared"

### PQL-244 · A wrong argument count is reported with the arity in words
- **Area:** `pql/types.py::check_calls`, `functions.Function.arity_words`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** check `UPPER(a, b)`, `LEFT(a)`, `CONCAT()`, `IF(a, b)`
- **Expected:** "exactly 1 argument(s)", "exactly 2", "at least 1", "exactly 3" respectively
- **Why:** three arity shapes, three sentences, and `arity_words` is where a variadic reads as unbounded

### PQL-245 · A refused volatile name is distinguished from an unknown one
- **Area:** `pql/types.py::check_calls`, `functions.VOLATILE`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** check `TODAY()` and `TODAYY()`
- **Expected:** the first says "TODAY is refused: it returns the current date" with the replay remedy; the second lists the catalogue
- **Why:** "refused" and "missing" are different problems with different answers

### PQL-246 · `require` raises on the first error and ignores `unchecked`
- **Area:** `pql/types.py::TypeChecker.require`
- **Type:** functional
- **Priority:** P1
- **Precondition:** an empty catalogue
- **Steps:** call `require` on a valid control against an unknown dataset, then on one with a bad function name
- **Expected:** the first returns; the second raises `PqlTypeError` carrying the position and source
- **Why:** the compile path uses `require`, so an `unchecked` control must still compile — that is what makes Prama usable before the estate is declared

### PQL-247 · Findings are returned in full, not one at a time
- **Area:** `pql/types.py::TypeChecker.check`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a declared schema
- **Steps:** check a control with three unknown columns and two bad function calls
- **Expected:** five findings in one call
- **Why:** the docstring: "a checker that stopped at the first error would make somebody fix a control one mistake per attempt"

### PQL-248 · `Finding.to_dict` survives a null position
- **Area:** `pql/types.py::Finding.to_dict`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** serialise a finding built with `position=None`
- **Expected:** `{"position": None}`, no `AttributeError`
- **Why:** the API and the console both serialise findings, and a 500 from a missing position is Q-23's shape

### PQL-249 · `Catalogue.get` is case-sensitive at the dataset level
- **Area:** `pql/types.py::Catalogue.get`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a catalogue keyed `Positions`
- **Steps:** look up `positions`, `Positions`, `POSITIONS`
- **Expected:** documented — `get` tries the exact key then the lower-cased key, so an upper-cased *stored* name is reachable only by its exact spelling
- **Why:** the asymmetry between dataset lookup (half case-insensitive) and column lookup (fully case-insensitive) is a trap when a catalogue is built from a warehouse that upper-cases everything

### PQL-250 · `Catalogue.of` builds from plain dictionaries
- **Area:** `pql/types.py::Catalogue.of`
- **Type:** functional
- **Priority:** P3
- **Precondition:** none
- **Steps:** `Catalogue.of(positions={"a": "int"})` and check a control against it
- **Expected:** one dataset, one column, family `number`, `nullable` True
- **Why:** every test and the quick-check path uses it, so its defaults are the defaults everybody sees

## 8 · The function catalogue — `pql/functions.py`, `pql/library.py`

### PQL-251 · `prama control functions` lists the catalogue and the per-engine coverage
- **Area:** `cli/control.py::ControlFunctionsCommand.run`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `prama control functions`, then `--engine sqlite`, then `--json`
- **Expected:** every registered name; a share per engine; each refused function named rather than counted
- **Why:** the comment says "'24 of 25' tells a reader something is missing and not whether it is the one they need"

### PQL-252 · `--engine` with an unknown name is refused
- **Area:** `cli/control.py::ControlFunctionsCommand.run`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `prama control functions --engine oracle`
- **Expected:** "no engine called 'oracle'", remedy listing postgresql, duckdb, sqlite
- **Why:** the engine list is the deployment decision this command exists to inform

### PQL-253 · Every function has a reference implementation
- **Area:** `pql/functions.py::Function.evaluate`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** assert `callable(f.evaluate)` for every registered function
- **Expected:** true for all 25; no function in the catalogue lacks one
- **Why:** the module docstring calls this the structural guarantee — "the compiler cannot acquire a function its independent check does not have"

### PQL-254 · A function with no SQL form cannot be constructed
- **Area:** `pql/functions.py::Function.__post_init__`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** construct a `Function` with neither `sql` nor `sql_by_engine`
- **Expected:** `ValidationError` "has no SQL form", remedy naming `unsupported_on`
- **Why:** the third of the three rules that keep the compiler and the interpreter from drifting apart

### PQL-255 · A function declared unsupported on *every* engine still constructs
- **Area:** `pql/functions.py::Function.__post_init__`, `Function.render`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** construct a function with `unsupported_on = frozenset(ENGINES)` and a `sql` template
- **Expected:** documented — it constructs, appears in the catalogue, and refuses on every engine
- **Why:** the post-init checks for a template, not for reachability, so a function nothing can run can still be advertised

### PQL-256 · A volatile name cannot be registered
- **Area:** `pql/functions.py::FunctionRegistry.register`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** register a function named `NOW`, then `TODAY`, `RAND`, `RANDBETWEEN`, `INDIRECT`, `OFFSET`
- **Expected:** `ValidationError` for each, naming what it returns and why replay forbids it
- **Why:** "a function that cannot replay does not exist" — asserted at registration, not at use

### PQL-257 · `get` on a volatile name explains rather than saying "unknown"
- **Area:** `pql/functions.py::FunctionRegistry.get`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** `FUNCTIONS.get("OFFSET")`
- **Expected:** "OFFSET is refused: it returns a reference resolved at evaluation time"
- **Why:** two different failures, two different remedies; being told a name is unknown when it is refused sends somebody to add it

### PQL-258 · `get` on an unknown name lists the catalogue
- **Area:** `pql/functions.py::FunctionRegistry.get`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `FUNCTIONS.get("VLOOKUP")`
- **Expected:** "there is no function called VLOOKUP", remedy listing every available name and explaining what used to happen
- **Why:** `VLOOKUP` is the first thing a spreadsheet user tries, and the message is the only place the answer is given

### PQL-259 · `find` returns None rather than raising
- **Area:** `pql/functions.py::FunctionRegistry.find`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** `FUNCTIONS.find("NOPE")`
- **Expected:** `None`
- **Why:** every caller in `types.py`, `sql.py`, `excel.py` and `analysis.py` uses `find` for control flow; a raising `find` would turn a diagnostic into a crash

### PQL-260 · Name lookup is case-insensitive
- **Area:** `pql/functions.py::FunctionRegistry.get`, `find`, `register`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** look up `upper`, `Upper`, `UPPER`
- **Expected:** the same function
- **Why:** the parser preserves the author's case for scalar functions, so the registry is where case stops mattering

### PQL-261 · `Function.render` refuses on an unsupported engine
- **Area:** `pql/functions.py::Function.render`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `FUNCTIONS.get("ROUND").render("sqlite", ["x", "2"])`
- **Expected:** `ValidationError` "sqlite cannot express ROUND", remedy refusing to substitute something close
- **Why:** the one function that is refused on an engine, and the refusal is the promise

### PQL-262 · The `{*}` variadic template and its per-engine separator
- **Area:** `pql/functions.py::Function.render`, `separator_by_engine`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** render `CONCAT` with three arguments on each engine
- **Expected:** `CONCAT(a, b, c)` on postgresql and duckdb; `(a || b || c)` on sqlite
- **Why:** the comment records the defect this prevents — a comma-joined list on SQLite rendered `(a, b, c)`, a row constructor that "parses and means something entirely different"

### PQL-263 · `CONCAT` of one argument on SQLite
- **Area:** `pql/library.py::TEXT_FUNCTIONS` CONCAT
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** render and execute `CONCAT(a)` on sqlite
- **Expected:** `(a)`, which evaluates to `a`
- **Why:** arity allows one argument and the template degenerates; assert it is still valid SQL

### PQL-264 · `CONCAT` with a NULL argument disagrees between SQL and the reference
- **Area:** `pql/library.py::CONCAT`, `backend/reference.py::ReferenceEvaluator._call`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a row with a null column
- **Steps:** evaluate `CONCAT(a, b)` where `b` is NULL, on the reference interpreter and on each engine
- **Expected:** agreement
- **Why:** the reference is strict — a null argument makes the result UNKNOWN, which its own `excel_divergence` says is deliberate — while PostgreSQL's `CONCAT` treats a NULL as the empty string and returns `'a'`. SQLite's `||` returns NULL and agrees. So the three-way agreement the catalogue claims does not hold for the one function whose divergence note is about exactly this case

### PQL-265 · `Function.expected_type` repeats the last declared family for a variadic tail
- **Area:** `pql/functions.py::Function.expected_type`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** ask `CONCAT` for the family of positions 0, 5 and 50
- **Expected:** `text` each time
- **Why:** the tail rule is the difference between a checkable variadic and one that types only its first argument

### PQL-266 · `argument_types` is declared and never enforced
- **Area:** `pql/functions.py::Function.argument_types`, `pql/types.py::check_calls`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a schema with `notional numeric`
- **Steps:** check `CHECK t.a IS NOT NULL WHERE UPPER(notional) = 'X'`
- **Expected:** a finding that `UPPER` expects text
- **Why:** `check_calls` verifies the name and the arity and never the families, and `_check_expression` only inspects comparison operands — so the declared per-position types of all 25 functions are decoration. `UPPER(numeric)` reaches PostgreSQL as "function upper(numeric) does not exist", at run time

### PQL-267 · `to_dict` reports the engines a function runs on
- **Area:** `pql/functions.py::Function.to_dict`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** serialise `ROUND` and `UPPER`
- **Expected:** `ROUND` lists postgresql and duckdb only
- **Why:** the console and the API render this and a deployment picks an engine from it

### PQL-268 · Each text function against its reference, including a NULL argument
- **Area:** `pql/library.py::TEXT_FUNCTIONS`, `tests/pql/test_function_catalogue.py::SAMPLES`
- **Type:** negative
- **Priority:** P1
- **Precondition:** duckdb and sqlite in process; postgresql if available
- **Steps:** for UPPER, LOWER, TRIM, LENGTH, LEN, LEFT, RIGHT, MID, SUBSTITUTE and CONCAT, run the SQL and the reference over a NULL argument and compare
- **Expected:** agreement, or a documented divergence per function
- **Why:** the existing gate's `SAMPLES` table contains an empty string, a negative and a zero — and **no NULL at all**. Strict-unknown is the catalogue's central rule and no function is tested against it on a real engine

### PQL-269 · `LENGTH` of a non-text value
- **Area:** `pql/library.py::LENGTH`, `LEN`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a numeric and a date column
- **Steps:** evaluate `LENGTH(notional)` and `LENGTH(trade_date)` on each engine and on the reference
- **Expected:** agreement
- **Why:** the reference does `len(str(value))`; PostgreSQL has no `length(numeric)` and raises; SQLite coerces; DuckDB coerces differently. Nothing casts, and the declared `argument_types=(TEXT,)` is not enforced

### PQL-270 · `LENGTH` counts characters, not bytes, on every engine
- **Area:** `pql/library.py::LENGTH`, `backend/dialect.py::SqlDialect.length`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a column containing `日本語` and `café`
- **Steps:** compare `LENGTH` across the engines and the reference
- **Expected:** 3 and 4 everywhere
- **Why:** a length control on a multi-byte column is the one that decides whether an identifier is the right size, and SQLite's `LENGTH` changes meaning for a BLOB

### PQL-271 · `TRIM` does not collapse interior spaces
- **Area:** `pql/library.py::TRIM`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** evaluate `TRIM('  a   b  ')` on every engine and the reference
- **Expected:** `'a   b'` everywhere
- **Why:** the divergence note states it — Excel's TRIM collapses runs, and "collapsing interior spaces on one side and not the other would make the same control give two answers"

### PQL-272 · `TRIM` of other whitespace
- **Area:** `pql/library.py::TRIM`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a value with a leading tab, a trailing newline and a non-breaking space
- **Steps:** compare reference and SQL
- **Expected:** agreement
- **Why:** Python's `.strip()` removes all Unicode whitespace; SQL `TRIM` removes spaces only — a divergence on exactly the values a dirty feed contains

### PQL-273 · `LEFT`, `RIGHT` and `MID` with a zero, a negative and an over-long length
- **Area:** `pql/library.py::LEFT`, `RIGHT`, `MID`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** none
- **Steps:** evaluate `LEFT('abc', 0)`, `LEFT('abc', -1)`, `LEFT('abc', 99)`, `RIGHT('abc', 0)`, `RIGHT('abc', -1)`, `MID('abc', 0, 2)`, `MID('abc', -1, 2)`, `MID('abc', 2, 0)` on every engine and the reference
- **Expected:** agreement
- **Why:** the existing gate's `_cases` explicitly substitutes `[2, 1]` for these positions with the comment "a negative is not a case anybody writes" — so the whole negative and zero space is excluded by construction, and SQL `SUBSTR` with a zero or negative start is exactly where the engines differ from Python slicing

### PQL-274 · `MID` counts from 1
- **Area:** `pql/library.py::MID`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `MID('abcdef', 1, 3)` and `MID('abcdef', 3, 2)`
- **Expected:** `'abc'` and `'cd'` on every engine and the reference
- **Why:** one-based is the spreadsheet convention and zero-based is the Python one; the off-by-one is in `max(0, int(n) - 1)`

### PQL-275 · `SUBSTITUTE` has no fourth argument
- **Area:** `pql/library.py::SUBSTITUTE`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** check `SUBSTITUTE(a, 'x', 'y', 2)`
- **Expected:** "SUBSTITUTE takes exactly 3 argument(s), and was given 4"; the divergence note is printed by `control explain`
- **Why:** the fourth argument is standard in Excel and its absence is a stated, reasoned divergence

### PQL-276 · `SUBSTITUTE` with an empty search string
- **Area:** `pql/library.py::SUBSTITUTE`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** `SUBSTITUTE('abc', '', 'X')` on every engine and the reference
- **Expected:** agreement
- **Why:** Python's `str.replace` with an empty needle inserts between every character; SQL `REPLACE` mostly returns the input unchanged — a silent divergence with no note

### PQL-277 · `ROUND` is half away from zero
- **Area:** `pql/library.py::_round_half_up`, `ROUND`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `ROUND(2.675, 2)`, `ROUND(-2.675, 2)`, `ROUND(0.5, 0)`, `ROUND(-0.5, 0)` on postgresql, duckdb and the reference
- **Expected:** 2.68, -2.68, 1, -1
- **Why:** "money is exact"; several engines round half to even by default and the explicit exact cast is what pins it

### PQL-278 · `ROUND` does not round twice
- **Area:** `pql/library.py::ROUND` `sql_by_engine`
- **Type:** regression
- **Priority:** P1
- **Precondition:** duckdb
- **Steps:** `ROUND(1953193.4649, 2)` on duckdb
- **Expected:** 1953193.46
- **Why:** the comment records the defect exactly — a bare `CAST(x AS NUMERIC)` is `DECIMAL(18,3)` in DuckDB, so the value rounds to .465 and then to .47, and "on a real blotter that was 131 rows in 3,000 reported as a cent out when they were not"

### PQL-279 · `ROUND` is refused on SQLite rather than approximated
- **Area:** `pql/library.py::ROUND` `unsupported_on`, `backend/sql.py::SqlCompiler._call`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** compile a control using `ROUND` for sqlite
- **Expected:** `PqlUnsupportedError` "sqlite cannot run ROUND", at authoring time
- **Why:** "a penny is exactly the size of error a hash total exists to detect" — the refusal is the feature

### PQL-280 · `ROUND` with a negative or very large number of places
- **Area:** `pql/library.py::_round_half_up`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** `ROUND(1234.5, -2)` and `ROUND(1.5, 40)` through the reference
- **Expected:** 1200 and a defined answer — never an uncaught `decimal.InvalidOperation`
- **Why:** `Decimal.quantize` raises when the result exceeds the context precision, and that exception escapes the reference interpreter mid-row

### PQL-281 · `INT` uses floor, not truncation
- **Area:** `pql/library.py::INT`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `INT(-7.5)` on every engine and the reference
- **Expected:** -8 everywhere
- **Why:** the divergence note says "TRUNC would round towards zero and disagree on negatives", and the negative is the only case that distinguishes them

### PQL-282 · `INT` on SQLite
- **Area:** `pql/library.py::INT`, `backend/dialect.py::SqliteDialect`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a stock Python `sqlite3` build
- **Steps:** compile and execute `INT(x)` on sqlite
- **Expected:** a result, or a refusal at authoring time
- **Why:** `INT` lowers to `FLOOR({0})` on every engine and declares no `unsupported_on`, but SQLite only has `floor()` when built with `SQLITE_ENABLE_MATH_FUNCTIONS` — so on a build without it the control fails at execution with "no such function: floor", which is exactly what `unsupported_on` exists to prevent

### PQL-283 · `MOD` by zero is unknown, not an error
- **Area:** `pql/library.py::_mod`, `MOD`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `MOD(5, 0)` on every engine and the reference
- **Expected:** NULL / UNKNOWN everywhere
- **Why:** "there are no error values here"; the `CASE WHEN {1} = 0 THEN NULL` guard is what makes that true on the SQL side

### PQL-284 · `MOD` takes the sign of the dividend
- **Area:** `pql/library.py::_mod`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `MOD(-10, 3)` and `MOD(10, -3)` on every engine and the reference
- **Expected:** agreement, and a stated divergence from Excel
- **Why:** Excel's MOD takes the sign of the *divisor* and returns 2 for `MOD(-10,3)`; Decimal and SQL both return -1. The `excel_divergence` note mentions only `#DIV/0!`, so the sign difference — the one that changes a verdict — is undocumented. The existing gate never pairs a negative dividend with a positive divisor

### PQL-285 · `SIGN` of zero, a negative and a null
- **Area:** `pql/library.py::SIGN`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** `SIGN(0)`, `SIGN(-7.5)`, `SIGN(NULL)`
- **Expected:** 0, -1, UNKNOWN, on every engine and the reference
- **Why:** three branches in one lambda, and the null path goes through `strict_unknown`

### PQL-286 · Scalar `MIN`/`MAX` require at least two arguments
- **Area:** `pql/library.py::MIN`, `MAX`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** check `MIN(a)` and `MIN(a, b, c)`
- **Expected:** the first is refused as an arity error *or* recognised as the aggregate; the second renders `LEAST(a,b,c)` on postgresql/duckdb and `MIN(a,b,c)` on sqlite
- **Why:** the scalar/aggregate collision — SQLite's two-argument `MIN` is a different function from its one-argument aggregate, and PQL's parser calls both `MIN`

### PQL-287 · `MIN`/`MAX` with an unknown argument are unknown
- **Area:** `pql/library.py::_extreme`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `MIN(a, b)` with `b` NULL, on every engine and the reference
- **Expected:** agreement
- **Why:** the docstring says "silently ignoring a missing value is how a minimum becomes a statement about the rows that happened to be populated" — and SQL's `LEAST` ignores NULLs on some engines and propagates on others, so this is a real three-way question

### PQL-288 · `IF` with an undetermined condition is undetermined
- **Area:** `pql/library.py::_if`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `IF(NULL, 1, 2)` on every engine and the reference
- **Expected:** UNKNOWN / NULL everywhere
- **Why:** "choosing a branch would be inventing an answer, and the branch it would invent is the one that passes"; SQL's `CASE WHEN NULL THEN 1 ELSE 2 END` returns **2**, which is exactly the branch the note warns about — assert the two agree or record that they do not

### PQL-289 · `IF` is not strict
- **Area:** `pql/library.py::IF`, `backend/reference.py::ReferenceEvaluator._call`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `IF(TRUE, 1, NULL)` and `IF(FALSE, NULL, 2)`
- **Expected:** 1 and 2 — a branch not taken must not make the result unknown
- **Why:** `strict_unknown=False` is what makes this possible, and it is one of four exceptions each of which must say why

### PQL-290 · `COALESCE` and `IFBLANK` return the first present value
- **Area:** `pql/library.py::_coalesce`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `COALESCE(NULL, NULL, 3)`, `COALESCE(NULL, NULL)`, `IFBLANK(NULL, 'x')`
- **Expected:** 3, UNKNOWN, `'x'` — matching SQL's `COALESCE` in each case
- **Why:** the all-null case is where `UNSET` and `NULL` have to coincide

### PQL-291 · `COALESCE` treats an empty string as present
- **Area:** `pql/library.py::_coalesce` vs `_is_blank`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** `COALESCE('', 'x')` and `ISBLANK('')`
- **Expected:** `''` and `True`
- **Why:** two functions in one file disagree about whether an empty string is missing, deliberately — and `IFBLANK`, whose name says blank, uses the `COALESCE` implementation

### PQL-292 · `ISBLANK` is true for both NULL and empty
- **Area:** `pql/library.py::ISBLANK`, `_is_blank`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `ISBLANK(NULL)`, `ISBLANK('')`, `ISBLANK('   ')`, `ISBLANK(0)`, `ISBLANK(FALSE)` on every engine and the reference
- **Expected:** True, True, True, False, False everywhere
- **Why:** the divergence note: "in a database an empty string and a NULL are the same defect wearing two hats, and a control that caught one and not the other would be turned off"

### PQL-293 · `ISBLANK` evaluates its argument twice in SQL
- **Area:** `pql/library.py::ISBLANK` sql template
- **Type:** performance
- **Priority:** P3
- **Precondition:** none
- **Steps:** compile `ISBLANK(expensive_expression)`
- **Expected:** the emitted SQL duplicates the expression; assert the cost is understood
- **Why:** `({0} IS NULL OR TRIM(CAST({0} AS VARCHAR)) = '')` substitutes `{0}` twice, so a nested function call is computed twice per row

### PQL-294 · `ISNUMBER` on each engine
- **Area:** `pql/library.py::ISNUMBER`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `ISNUMBER('123')`, `ISNUMBER('-1.5')`, `ISNUMBER('1e5')`, `ISNUMBER('  7 ')`, `ISNUMBER('')`, `ISNUMBER(NULL)`
- **Expected:** the reference and each engine agree
- **Why:** the reference strips whitespace before matching and the SQL regex does not — `'  7 '` is True in Python and False in SQL

### PQL-295 · `ISNUMBER` requires the regex capability
- **Area:** `pql/library.py::ISNUMBER.requires`, `backend/sql.py::SqlCompiler._call`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a dialect without `pushdown.regex`
- **Steps:** compile a control using `ISNUMBER` for such an engine
- **Expected:** `PqlUnsupportedError` naming the capability
- **Why:** the only function declaring `requires`, and the only exercise of the per-function capability gate

### PQL-296 · `YEAR`, `MONTH`, `DAY` on an ISO date
- **Area:** `pql/library.py::DATE_FUNCTIONS`, `_date_part`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** evaluate all three over `'2026-09-08'`, `'2024-02-29'`, `'2026-09-08T06:30:00Z'`
- **Expected:** agreement between the reference (regex over the text) and SQL (`SUBSTR` of the cast)
- **Why:** both read fixed character positions, so a timestamp with a different prefix length breaks both identically — or not

### PQL-297 · `YEAR` of a non-date
- **Area:** `pql/library.py::_date_part`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `YEAR('not a date')`, `YEAR('2026/09/08')`, `YEAR(20260908)`
- **Expected:** the reference returns UNKNOWN (`_ISO_DATE` does not match); SQL returns `CAST(SUBSTR(…,1,4) AS INTEGER)` — assert what each engine does with `'not '` and `'2026'`
- **Why:** PostgreSQL raises on an invalid integer cast, DuckDB returns NULL, SQLite returns 0 — three answers to one expression, none of them UNKNOWN

### PQL-298 · `YEAR` over a real DATE column
- **Area:** `pql/library.py::YEAR`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a column of engine-native `DATE` type
- **Steps:** evaluate `YEAR(trade_date)` on each engine
- **Expected:** agreement with the reference, which sees the driver's Python value
- **Why:** the SQL casts to VARCHAR and takes four characters, which assumes ISO rendering — true on all three engines, and a claim rather than a guarantee

### PQL-299 · A boolean is not a number
- **Area:** `pql/library.py::_number`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** `ABS(TRUE)`, `ROUND(TRUE, 0)`, `MIN(TRUE, 1)` through the reference
- **Expected:** UNKNOWN in each case
- **Why:** "Excel treats TRUE as 1. Prama does not: a boolean in an arithmetic position is a mistake worth surfacing" — and the arithmetic path in the reference interpreter does *not* agree (see the reference section)

### PQL-300 · Reference arithmetic is exact, SQL arithmetic is not
- **Area:** `pql/library.py::_number` (Decimal), `backend/reference.py::_arithmetic` (float)
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** sum `0.1 + 0.2` through a catalogue function and through the `+` operator, on the reference and on each engine
- **Expected:** one documented arithmetic model
- **Why:** the library's reference implementations use `Decimal` "because a reconciliation that summed in binary floating point would manufacture exactly the small discrepancies it exists to detect" — and `reference._arithmetic` coerces both operands with `float()`. Two arithmetic models in one interpreter

### PQL-301 · Every `excel_divergence` names what Excel does
- **Area:** `pql/library.py`, `cli/control.py::_divergences`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** for every function with a non-empty `excel_divergence`, assert the text names the Excel behaviour and the Prama behaviour
- **Expected:** both halves present in each of the notes
- **Why:** `prama control explain` prints these to the author, and a note that says only what Prama does is not a divergence note

### PQL-302 · `control explain` prints a divergence for every function in the control
- **Area:** `cli/control.py::_divergences`, `_function_names`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a control using `TRIM`, `ROUND` and `CONCAT`
- **Steps:** `prama control explain`
- **Expected:** three divergence lines plus the SQLite refusal note for `ROUND`
- **Why:** "a divergence discovered in production is worth less than one stated on the control"

### PQL-303 · `_function_names` finds calls in every clause
- **Area:** `cli/control.py::_function_names`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a control whose only function call is inside `FOR EACH … HAVING`
- **Steps:** `prama control explain` on it
- **Expected:** the divergence for that function is printed
- **Why:** the walker follows `__slots__` on `Node` subclasses — assert it reaches segmentation, list items and nested arguments, since the same blind spot exists in `_expressions_of`

### PQL-304 · The catalogue is closed under `default_registry`
- **Area:** `pql/library.py::default_registry`, `FUNCTIONS`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** assert `len(FUNCTIONS)` equals the number of declarations across the four tuples, and that every name is unique
- **Expected:** the counts match and no name is declared twice
- **Why:** `register` overwrites silently on a duplicate name, so two declarations of `LENGTH` would leave one unreachable and nothing would say so

### PQL-305 · A deployment-registered function is honoured everywhere
- **Area:** `pql/functions.py::FunctionRegistry.register`, `pql/types.py::check_calls`, `backend/sql.py::SqlCompiler._call`, `backend/reference.py::ReferenceEvaluator._call`
- **Type:** contract
- **Priority:** P2
- **Precondition:** a custom function registered into `FUNCTIONS`
- **Steps:** check, compile and interpret a control using it
- **Expected:** all four paths find it
- **Why:** "a deployment may add to it; nothing is removed" — four modules import the module-level singleton, so a late registration must reach all of them

## 9 · The linter — `pql/lint.py`

### PQL-306 · A rate threshold of 100% or more can never fail
- **Area:** `pql/lint.py::Linter._never_fires`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** lint `BELOW 100%`, `BELOW 150%`, `BELOW 1` (no percent sign)
- **Expected:** `never-fires` at severity `error` for all three, remedy explaining that such a control "appears on the coverage report and covers nothing"
- **Why:** the bare `BELOW 1` form is the one an author writes meaning "1%" and it is caught only because 1.0 is the boundary

### PQL-307 · A rate threshold just under 100% is not flagged
- **Area:** `pql/lint.py::Linter._never_fires`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** lint `BELOW 99.9%`
- **Expected:** no finding
- **Why:** the `>= 1.0` boundary must be exact; a strict `>` or a rounded comparison would let 100% through

### PQL-308 · A row count with no bounds and one with a zero minimum
- **Area:** `pql/lint.py::Linter._never_fires`, `_vacuous`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** lint a `RowCountAssertion` with both bounds None, and `HAS ROW COUNT AT LEAST 0`
- **Expected:** "a row count with no bounds asserts nothing" and "every dataset has at least zero rows", both at severity `error`
- **Why:** `AT LEAST 0` is what a generated control produces when the volume is unknown, and it is coverage that covers nothing

### PQL-309 · Reversed numeric BETWEEN bounds
- **Area:** `pql/lint.py::Linter._always_fires`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** lint `BETWEEN 100 AND 1`
- **Expected:** `always-fires` at severity `error`
- **Why:** a control every row violates pages somebody every run until it is turned off

### PQL-310 · Reversed row-count bounds
- **Area:** `pql/lint.py::Linter._always_fires`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** lint `HAS ROW COUNT BETWEEN 100 AND 1`
- **Expected:** "the row count range is empty, so this can never pass"
- **Why:** the second of the two decidable emptiness cases

### PQL-311 · Equal BETWEEN bounds are not flagged
- **Area:** `pql/lint.py::Linter._always_fires`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** lint `HAS LENGTH BETWEEN 12 AND 12`
- **Expected:** no finding
- **Why:** an exact length is the commonest legitimate use of BETWEEN and the comparison must be strict

### PQL-312 · A missing justification is `info`, not an error
- **Area:** `pql/lint.py::Linter._missing_justification`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** lint `CHECK t.a IS NOT NULL`, then run `prama control check --strict` over the same file
- **Expected:** severity `info`; `--strict` turns it into a non-zero exit
- **Why:** the escalation path from advisory to gate is the whole design of `--strict`, and `info` is what makes the default usable

### PQL-313 · Exact duplicates are found by meaning, not by text
- **Area:** `pql/lint.py::Linter._duplicates`, `_identity`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** lint two controls that differ only in clause order, severity, dimension, owner, evidence and BECAUSE
- **Expected:** one `duplicate` finding, naming the other control
- **Why:** the docstring: "a suite copied with its clauses reordered and its BECAUSE reworded is still caught"

### PQL-314 · Two controls differing only in threshold are not duplicates
- **Area:** `pql/lint.py::_identity`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** lint the same assertion with `AT MOST 0 ROWS` and `AT MOST 5 ROWS`
- **Expected:** no duplicate finding
- **Why:** the threshold is in the identity key precisely because it changes what the control computes

### PQL-315 · `ON FAIL` and `DIMENSION` are not in the identity key
- **Area:** `pql/lint.py::_identity`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** lint two identical assertions differing only in `ON FAIL block` vs `alert`
- **Expected:** documented — they are reported as duplicates
- **Why:** one blocks the pipeline and one sends an email; whether that is "the same thing computed twice" is a decision worth stating, since `on_fail` is excluded from the key and `unknown_policy` is not

### PQL-316 · Duplicate detection over an unhashable control
- **Area:** `pql/lint.py::Linter._duplicates`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** lint a control whose assertion contains a `ListExpression` of 1,000 literals, and one containing a pattern literal
- **Expected:** no `TypeError`; the identity key hashes
- **Why:** `_identity` puts whole frozen dataclasses into a dict key, which requires every nested value to be hashable — a literal holding a list would raise

### PQL-317 · `IS NOT NULL` beside a null-sensitive predicate is subsumed
- **Area:** `pql/lint.py::Linter._implies`, `NULL_SENSITIVE`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** lint `CHECK t.n > 0` together with `CHECK t.n IS NOT NULL`
- **Expected:** `subsumed`, with the message explaining that an unknown counts as a violation
- **Why:** this is the language's central decision showing up as a lint rule — it is only true because the default unknown policy is `violation`

### PQL-318 · Subsumption does not apply under `TREAT UNKNOWN AS PASS`
- **Area:** `pql/lint.py::Linter._implies`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** lint the same pair with the `IS NOT NULL` control carrying `TREAT UNKNOWN AS PASS`
- **Expected:** no subsumption finding
- **Why:** the implication rests entirely on the unknown policy; removing the guard would advise deleting the only control that still catches nulls

### PQL-319 · Every member of `NULL_SENSITIVE` actually fails on a null
- **Area:** `pql/lint.py::NULL_SENSITIVE`, `backend/reference.py::ReferenceEvaluator.is_violation`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a row with a null column
- **Steps:** for each of `in`, `between`, `matches`, `is_valid`, `has_format`, `has_length_between`, `in_codelist` and the six comparisons, run the control over the null row under the default policy
- **Expected:** a violation in every case
- **Why:** the set is asserted by hand and drives a recommendation to delete a control; a member that does not in fact fail on a null is advice to delete real coverage

### PQL-320 · Subsumption requires the same scope
- **Area:** `pql/lint.py::Linter._implies`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** lint the null-sensitive pair with different `WHERE` clauses, then with different `FOR EACH`
- **Expected:** no finding in either case
- **Why:** "different scopes are not comparable without reasoning about the filters, which is where a solver would be needed and a wrong answer would be expensive"

### PQL-321 · Subsumption requires both thresholds to be strict
- **Area:** `pql/lint.py::Linter._implies`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** lint the null-sensitive pair where the stronger control tolerates 5 rows
- **Expected:** no finding
- **Why:** "a stricter predicate under a looser tolerance implies nothing"

### PQL-322 · A narrower `IN` subsumes a wider one
- **Area:** `pql/lint.py::Linter._implies`, `_literal_set`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** lint `IN ('GBP')` together with `IN ('GBP','USD')` on the same column
- **Expected:** `subsumed` on the wider one, naming the subset relationship
- **Why:** strict subset, so two identical `IN` lists must *not* be reported here — they are a duplicate instead

### PQL-323 · An `IN` list containing non-literals is not compared
- **Area:** `pql/lint.py::_literal_set`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** lint `IN ($a, 'GBP')` against `IN ('GBP','USD')`
- **Expected:** no finding
- **Why:** the set is empty when any element is not a literal, and "where subsumption cannot be decided by the rules, the linter says nothing"

### PQL-324 · Subsumption reports each control at most once
- **Area:** `pql/lint.py::Linter._subsumed`
- **Type:** functional
- **Priority:** P2
- **Precondition:** three controls where two both subsume the third
- **Steps:** lint them
- **Expected:** one finding for the third control, naming one of the two
- **Why:** the `break` after the first hit; without it a widely-covered control produces one finding per coverer

### PQL-325 · Subsumption is not reported in both directions
- **Area:** `pql/lint.py::Linter._subsumed`, `_implies`
- **Type:** functional
- **Priority:** P2
- **Precondition:** the null-sensitive pair
- **Steps:** lint them and count findings
- **Expected:** exactly one
- **Why:** the loop tries every ordered pair, so a symmetric `_implies` would advise deleting both halves of a pair

### PQL-326 · Linting 5,000 controls
- **Area:** `pql/lint.py::Linter.check_all`, `_subsumed`
- **Type:** performance
- **Priority:** P2
- **Precondition:** a 5,000-control estate
- **Steps:** run `prama control check` over it and time it
- **Expected:** it completes in a time a CI gate tolerates
- **Why:** `_subsumed` is O(n²) with an AST comparison inside, so a bank-sized estate is 25 million `_implies` calls — and a tier-one bank's estate is exactly the scale the product is sold at

### PQL-327 · `LintFinding.render` and `to_dict` are consistent
- **Area:** `pql/lint.py::LintFinding.render`, `to_dict`
- **Type:** contract
- **Priority:** P3
- **Precondition:** a finding with and without a `related` control
- **Steps:** render and serialise both
- **Expected:** `related` appears in the prose only when set, and always as a key in the dict
- **Why:** the CLI prints one and `--json` emits the other, and a CI gate keys off the second

### PQL-328 · `control.render()` inside a finding does not crash on a selector control
- **Area:** `pql/lint.py::Linter._vacuous`, `_never_fires`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an unexpanded template control
- **Steps:** lint `CHECK EVERY ATTRIBUTE HAS ROW COUNT AT LEAST 0`
- **Expected:** a finding whose `control` field is the selector's first rendered line
- **Why:** every finding calls `control.render().splitlines()[0]`, which goes through the selector branch of `Control.render`

## 10 · The Excel surface — `pql/excel.py`

### PQL-329 · An Excel formula compiles to the same AST as its PQL equivalent
- **Area:** `pql/excel.py::parse_formula`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `SATISFIES EXCEL '=AND([quantity] > 0, [notional] = [quantity] * [price])'` and the PQL `SATISFIES quantity > 0 AND notional = quantity * price`; compare the conditions
- **Expected:** structurally identical `Expression` trees
- **Why:** the module's whole design — "no second IR, no second evaluator, no second conformance suite"

### PQL-330 · The leading `=` is optional
- **Area:** `pql/excel.py::ExcelParser.__init__`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `'=[a] > 0'` and `'[a] > 0'`
- **Expected:** the same tree
- **Why:** "refusing it would be pedantry about the one habit this surface exists to accommodate"

### PQL-331 · Excel `<>` produces an operator nothing downstream can handle
- **Area:** `pql/excel.py::OPERATORS`, `_binary`; `backend/sql.py::INFIX`; `backend/reference.py::_compare`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse, lower, compile and interpret `SATISFIES EXCEL '=[currency] <> "USD"'` — the third example in the module's own docstring
- **Expected:** working SQL and a working reference evaluation
- **Why:** `OPERATORS` maps `<>` to `"!="`, which is absent from `ast.COMPARISONS`, from `ast.BINDING`, and from `backend.sql.INFIX`. The SQL compiler raises "!= has no SQL form on postgresql"; the reference interpreter falls through to `_compare`, whose dict lookup raises an uncaught `KeyError` mid-row. The documented example does not run

### PQL-332 · Excel precedence puts `&` below comparison
- **Area:** `pql/excel.py::PRECEDENCE`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `'=[a] & [b] = "xy"'`
- **Expected:** `CONCAT(a, b) = "xy"` — concatenation binds tighter than the comparison
- **Why:** the table's comment says this is why it is a table: "Excel puts concatenation below comparison, and getting that backwards would silently reassociate every formula that mixes them"

### PQL-333 · `&` becomes `CONCAT`
- **Area:** `pql/excel.py::ExcelParser._binary`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `'=[a] & [b] & [c]'`
- **Expected:** nested `CONCAT` calls that lower and compile on every engine
- **Why:** the operator inherits the catalogue's per-engine lowering and its unknown rule "rather than acquiring its own" — including the NULL divergence in PQL-264

### PQL-334 · `^` is refused with a reason
- **Area:** `pql/excel.py::ExcelParser._binary`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `'=[a]^2 > 4'`
- **Expected:** "^ is not supported", remedy explaining engine disagreement about precision and fractional exponents of negatives
- **Why:** `^` is in both `PRECEDENCE` and `OPERATORS`, so it is accepted by the tokeniser and refused only at the very last step — assert the refusal actually fires

### PQL-335 · Excel errors carry no position
- **Area:** `pql/excel.py::ExcelParser._error`, `pql/errors.py::PqlError`, `pql/analysis.py::_from_error`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse a malformed formula and render the error; then feed the same text through `LanguageService.diagnostics`
- **Expected:** either a real position or an explicitly unlocated diagnostic
- **Why:** every raise in this file passes the offset in `context` and **no** `position=`, so `PqlError.position` defaults to line 1 column 1. `analysis._at` then reports line 1, and the module's own rule — "an editor will happily underline line 1 column 1 and send the reader to the wrong place, which is worse than underlining nothing" — is broken by its sibling

### PQL-336 · An empty formula
- **Area:** `pql/excel.py::ExcelParser.parse`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `''`, `'='`, `'   '`
- **Expected:** "the formula is empty" in each case, not an `IndexError`
- **Why:** `SATISFIES EXCEL ''` is what an empty spreadsheet cell produces

### PQL-337 · A trailing token after the formula is refused
- **Area:** `pql/excel.py::ExcelParser.parse`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `'=[a] > 0 [b]'`
- **Expected:** "unexpected '[b]' after the formula"
- **Why:** a formula that parses a prefix and silently drops the rest is a control that checks half of what was written

### PQL-338 · A bracketed column with a dot
- **Area:** `pql/excel.py::_TOKEN` `name` group, `ExcelParser.name`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `'=positions.notional > 0'` and inspect the resulting `ColumnRef`
- **Expected:** `ColumnRef(name="notional", dataset="positions")`
- **Why:** the `name` token pattern is `[A-Za-z_][A-Za-z0-9_.]*`, so the dot is swallowed into the name and the result is a column literally called `positions.notional`, which compiles to the quoted identifier `"positions.notional"` — a column that does not exist, resolving to nothing

### PQL-339 · An empty bracket
- **Area:** `pql/excel.py::ExcelParser.primary`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `'=[] > 0'`
- **Expected:** a refusal
- **Why:** `token.text[1:-1].strip()` yields `""`, producing a `ColumnRef` with an empty name that compiles to `"" > 0`

### PQL-340 · A bracketed name with spaces and punctuation
- **Area:** `pql/excel.py::_TOKEN` `bracket` group
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `'=[notional amount] > 0'`, `'=[a-b] > 0'`, `'=[日本] > 0'`
- **Expected:** each becomes a column of that exact name, stripped of surrounding whitespace
- **Why:** brackets are the escape hatch for real column names and must accept what a spreadsheet allows

### PQL-341 · A nested bracket is impossible
- **Area:** `pql/excel.py::_TOKEN`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** parse `'=[a[b]] > 0'`
- **Expected:** a located refusal
- **Why:** `\[[^\]]*\]` stops at the first `]`, leaving `]` as an unmatched character the tokeniser rejects

### PQL-342 · Doubled double quotes inside an Excel string
- **Area:** `pql/excel.py::ExcelParser.primary`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `'=[a] = "say ""hi"""'`
- **Expected:** the literal value `say "hi"`
- **Why:** "Excel escapes a quote by doubling it, and so does SQL" — the two conventions coinciding is the reason it is safe

### PQL-343 · A single-quoted string is not a string
- **Area:** `pql/excel.py::_TOKEN`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `"=[a] = 'USD'"`
- **Expected:** a refusal naming `'`
- **Why:** the PQL surface uses single quotes and the Excel surface uses double — somebody moving between them will get it wrong, and the message is the only correction

### PQL-344 · Argument separators: comma and semicolon
- **Area:** `pql/excel.py::ExcelParser.call`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `'=IF([a]>0, 1, 2)'` and `'=IF([a]>0; 1; 2)'`
- **Expected:** identical trees
- **Why:** "a European locale's Excel separates arguments with a semicolon, and a user pasting their own formula should not have to know that Prama is not localised"

### PQL-345 · Mixed separators in one call
- **Area:** `pql/excel.py::ExcelParser.call`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** parse `'=IF([a]>0, 1; 2)'`
- **Expected:** documented — accepted, since the loop tests both marks each time
- **Why:** accepting a mixture is a consequence rather than a decision, and it should be one or the other deliberately

### PQL-346 · A trailing separator
- **Area:** `pql/excel.py::ExcelParser.call`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `'=CONCAT([a], [b],)'`
- **Expected:** a located refusal
- **Why:** after the comma the parser calls `expression()`, which takes `)` and reaches `primary`'s final `raise`

### PQL-347 · `AND` and `OR` as functions and as infix operators
- **Area:** `pql/excel.py::ExcelParser.expression`, `_connective`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `'=AND([a]>0, [b]>0)'` and `'=[a]>0 AND [b]>0'`
- **Expected:** the same left-leaning `BinaryOp` chain
- **Why:** one surface with two spellings of the same connective, both lowering to the IR's own boolean operator so the three-valued logic is the language's

### PQL-348 · `AND` with fewer than two arguments is refused
- **Area:** `pql/excel.py::ExcelParser._connective`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `'=AND([a]>0)'`
- **Expected:** "AND takes at least two arguments"
- **Why:** Excel's `AND(x)` is legal and returns x; this is an undocumented divergence, so the message has to carry the explanation

### PQL-349 · `NOT` in both spellings
- **Area:** `pql/excel.py::ExcelParser.unary`, `call`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `'=NOT([a]>0)'` and `'=NOT [a]>0'`
- **Expected:** a `UnaryOp`; assert the precedence of the second — `unary` binds it tighter than the comparison, so `NOT [a]>0` is `(NOT [a]) > 0`
- **Why:** the PQL parser deliberately puts NOT *below* comparison for exactly this reason, and the Excel parser puts it above — the same text means two different things on the two surfaces

### PQL-350 · A column named `AND`
- **Area:** `pql/excel.py::ExcelParser.expression`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a column called `and`
- **Steps:** parse `'=[and] > 0'` and `'=and > 0'`
- **Expected:** both forms parse to the same `ColumnRef(name='and')`
- **Why:** the risk is that `expression()` tests `token.text.upper()` against
  `PRECEDENCE` regardless of token kind, which would make a bare identifier that
  happens to spell a connective into an operator. It does not: round 4 parsed both
  forms and both yield `BinaryOp('>', ColumnRef('and'), Literal(0))`. This case
  predicted a defect that is not there, and asserted the prediction rather than
  the property — so it failed against correct code. What it should hold the parser
  to is that bracketing is optional for a name that collides with a connective.

### PQL-351 · An unknown function lists the catalogue
- **Area:** `pql/excel.py::ExcelParser.call`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `'=VLOOKUP([a], [b], 2, FALSE)'`
- **Expected:** "there is no function called VLOOKUP", remedy listing every name and explaining the deliberately small set
- **Why:** VLOOKUP is the single most-expected Excel function and its refusal is where the "familiarity, never compatibility" promise is actually made

### PQL-352 · A volatile function is refused before the catalogue is consulted
- **Area:** `pql/excel.py::ExcelParser.call`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `'=TODAY()'`, `'=NOW()'`, `'=RAND()'`, `'=RANDBETWEEN(1,9)'`, `'=INDIRECT("A1")'`, `'=OFFSET([a],1,1)'`
- **Expected:** all six refused with the replay reason
- **Why:** the VOLATILE check precedes `FUNCTIONS.find`, so the refusal explains rather than saying "unknown"

### PQL-353 · `IFERROR` is refused by name
- **Area:** `pql/excel.py::ExcelParser.call`, `pql/library.py::IFBLANK`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `'=IFERROR([a]/[b], 0)'`
- **Expected:** "there is no function called IFERROR"; the `IFBLANK` divergence note explains why there is nothing to catch
- **Why:** "IFERROR is deliberately absent — there are no error values to catch"; a user who hits this needs the reason, not a list

### PQL-354 · Excel arity errors match the PQL ones
- **Area:** `pql/excel.py::ExcelParser.call`, `pql/types.py::check_calls`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** write `LEFT([a])` in an Excel formula and `LEFT(a)` in PQL; compare the messages
- **Expected:** the same sentence, from `arity_words`
- **Why:** two surfaces, one catalogue — a different message for the same mistake teaches people the two are different systems

### PQL-355 · An A1-style reference is refused
- **Area:** `pql/excel.py::_TOKEN`, module docstring
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `'=A1 > 0'` and `'=SUM(A1:B2)'`
- **Expected:** `A1` becomes a column reference (documented), and `A1:B2` is refused on the `:`
- **Why:** "there are no A1 references: this is a formula over a named dataset, not a grid" — the refusal for a range is the only place that is enforced, and a bare `A1` silently becomes a column

### PQL-356 · Excel round-trips through the AST unchanged
- **Area:** `pql/ast.py::ExpressionAssertion.render`, `source_syntax`, `source`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `SATISFIES EXCEL '=AND([a]>0, [b]>0)'`, render, re-parse and compare
- **Expected:** the rendered text is `SATISFIES EXCEL '=AND([a]>0, [b]>0)'`, and the re-parse is equal
- **Why:** the field comment says `parse(render(x)) == x` "has to hold for both syntaxes, and it cannot if the Excel form is lost on the way in"

### PQL-357 · An Excel formula containing a quote round-trips
- **Area:** `pql/ast.py::ExpressionAssertion.render`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `SATISFIES EXCEL '=[a] = "it''s"'` — an Excel formula whose PQL wrapper needs escaping
- **Expected:** it round-trips
- **Why:** two levels of quoting, one escaped by `render` and one by the Excel tokeniser, and they meet exactly here

### PQL-358 · `describe()` of an Excel control shows the formula as written
- **Area:** `pql/ast.py::ExpressionAssertion.describe`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** describe an Excel control
- **Expected:** "every row satisfies the formula =AND([a]>0, [b]>0)" — the author's text, not a PQL translation
- **Why:** "the control renders back as what they typed rather than as a translation they would not recognise"

## 11 · Selector expansion — `pql/expand.py`

### PQL-359 · A selector expands to one control per matched attribute
- **Area:** `pql/expand.py::Expander.expand`, `_bind`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a catalogue of five attributes, three of them CDEs
- **Steps:** expand `CHECK EVERY ATTRIBUTE WHERE is_cde IS NOT NULL`
- **Expected:** three concrete controls, each with `target` set to the attribute's dataset, the placeholder replaced, `selector` cleared and `derived_from` set
- **Why:** the feature that lets an estate be declared rather than typed

### PQL-360 · An expanded control renders and re-parses as an ordinary control
- **Area:** `pql/expand.py::Expander._bind`
- **Type:** contract
- **Priority:** P1
- **Precondition:** as above
- **Steps:** render each expanded control and re-parse it
- **Expected:** equality
- **Why:** "an expanded control is a concrete control and must render as one, or its text will not re-parse" — the `selector=None` clearing is what makes that true

### PQL-361 · An expanded control acquires a justification
- **Area:** `pql/expand.py::Expander._bind`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a selector with no BECAUSE
- **Steps:** expand and inspect `because`
- **Expected:** `Selected by EVERY ATTRIBUTE WHERE is_cde`
- **Why:** the generated estate has to pass its own linter, and `no-justification` would otherwise fire on every generated control

### PQL-362 · An empty expansion is not an error
- **Area:** `pql/expand.py::Expander.expand`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a catalogue with no matching attributes
- **Steps:** expand
- **Expected:** an empty list, and a caller that can tell the difference between "no controls" and "the estate is covered"
- **Why:** the comment says the risk is "an empty expansion that looked like a covered estate would be a coverage report built on nothing" — assert that something downstream actually reports it

### PQL-363 · `expand` on a non-template control is refused
- **Area:** `pql/expand.py::Expander._selector_of`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** call `expand` on `CHECK positions.a IS NOT NULL`
- **Expected:** `ValidationError` "this control names a dataset, so there is nothing to expand"
- **Why:** `expand_all` routes on `is_template`, so a direct call is the only way in and it must fail loudly

### PQL-364 · `expand_all` passes concrete controls through untouched
- **Area:** `pql/expand.py::Expander.expand_all`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a mixed list
- **Steps:** expand a list of two templates and three concrete controls
- **Expected:** the three concrete ones are returned identically (by equality, and by identity)
- **Why:** an estate is a mixture, and a rewrite of the concrete half would change controls nobody edited

### PQL-365 · Every metadata fact a selector can match on
- **Area:** `pql/expand.py::Attribute.facts`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a fully-populated attribute
- **Steps:** write one selector per fact — dataset, name, attribute, concept, concept_property, domain, owner, criticality, semantic_type, is_cde, tags
- **Expected:** each matches
- **Why:** eleven keys, and one that is mapped but not documented (`attribute` as an alias for `name`) is a selector vocabulary nobody can discover

### PQL-366 · A selector on an unknown metadata name matches nothing, silently
- **Area:** `pql/expand.py::_value`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a catalogue of five attributes
- **Steps:** expand `CHECK EVERY ATTRIBUTE WHERE is_cdee IS NOT NULL` (a typo)
- **Expected:** a refusal, or a warning naming the unrecognised field
- **Why:** `facts.get(name)` returns None for anything unknown, every comparison against None is False, and the expansion is empty — so a typo in a selector silently produces a covered-looking estate with zero controls in it

### PQL-367 · `tags IN ('pii')` matches an attribute carrying that tag
- **Area:** `pql/expand.py::_binary`
- **Type:** functional
- **Priority:** P1
- **Precondition:** an attribute with `tags=("pii","gdpr")`
- **Steps:** expand `WHERE tags IN ('pii')`
- **Expected:** it matches
- **Why:** the special case — the selector's value is searched *inside* the tag list, which is the reverse of what `IN` normally means, and the comment says it is so the clause "reads the way somebody expects it to"

### PQL-368 · `tags NOT IN (…)`
- **Area:** `pql/expand.py::_binary`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** attributes with and without a `pii` tag
- **Steps:** expand `WHERE tags NOT IN ('pii')`
- **Expected:** exactly the attributes without it
- **Why:** the reversed-membership special case must invert consistently, and `not found` is computed after the list search

### PQL-369 · `tags = 'pii'` does not match
- **Area:** `pql/expand.py::_binary`
- **Type:** negative
- **Priority:** P2
- **Precondition:** an attribute tagged `pii`
- **Steps:** expand `WHERE tags = 'pii'`
- **Expected:** a refusal or a match — not a silent non-match
- **Why:** `_binary` builds the whole comparison dict eagerly, so `list > str` raises `TypeError`, which is caught and turned into `False`; comparing a tag list with a string therefore matches nothing and says nothing

### PQL-370 · Selector logic is two-valued
- **Area:** `pql/expand.py::_truth`
- **Type:** functional
- **Priority:** P1
- **Precondition:** an attribute with an empty `domain`
- **Steps:** expand `WHERE domain = 'Credit Risk'` and `WHERE NOT (domain = 'Credit Risk')`
- **Expected:** the attribute is excluded by the first and included by the second — there is no third state
- **Why:** the docstring is explicit that this differs from row predicates, and "quietly including it would put a control on something nobody classified"

### PQL-371 · `IS NULL` in a selector treats empty string as null
- **Area:** `pql/expand.py::_value`
- **Type:** functional
- **Priority:** P2
- **Precondition:** an attribute with an empty `domain`
- **Steps:** evaluate a selector using the `IS NULL` unary form directly against the facts
- **Expected:** True for both `None` and `""`
- **Why:** the parser will not produce this from selector text (`IS` ends the condition), so it is reachable only programmatically — which means it is untested unless asserted

### PQL-372 · `_is_true` accepts the string "true"
- **Area:** `pql/expand.py::_is_true`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an attribute whose `is_cde` came from a text column as `"True"`
- **Steps:** expand `WHERE is_cde`
- **Expected:** it matches
- **Why:** metadata arrives from a warehouse as text, and the case-insensitive string acceptance is the only thing that makes it work — but only inside `NOT`, since `_truth` uses `is True`

### PQL-373 · A bare boolean fact under `NOT` and not under it disagree
- **Area:** `pql/expand.py::_truth`, `_is_true`
- **Type:** negative
- **Priority:** P2
- **Precondition:** an attribute with `is_cde` set to the string `"true"`
- **Steps:** expand `WHERE is_cde` and `WHERE NOT is_cde`
- **Expected:** exactly one of the two matches
- **Why:** `_truth` requires `value is True`, so the string does not match; `_not` goes through `_is_true`, which accepts the string — so `is_cde` and `NOT is_cde` both exclude the attribute

### PQL-374 · A concept selector matches exactly and case-sensitively
- **Area:** `pql/expand.py::AttributeCatalogue.matching`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an attribute mapped to `Instrument.ISIN`
- **Steps:** expand `CONCEPT Instrument.ISIN`, `CONCEPT instrument.isin`
- **Expected:** documented — exact string equality, so the second matches nothing
- **Why:** concept names come from a semantic layer people type by hand

### PQL-375 · An `Expansion` digest is stable and order-independent
- **Area:** `pql/expand.py::Expansion.of`
- **Type:** contract
- **Priority:** P1
- **Precondition:** the same attributes in two different orders
- **Steps:** build both expansions and compare digests
- **Expected:** identical — the names are sorted before hashing
- **Why:** "drift is a comparison rather than a diff", and an order-dependent digest would report drift on every catalogue rebuild

### PQL-376 · Two different coverage sets have different digests
- **Area:** `pql/expand.py::Expansion.of`
- **Type:** contract
- **Priority:** P1
- **Precondition:** two attribute sets differing by one
- **Steps:** compare digests
- **Expected:** different
- **Why:** a 16-hex-character truncation of SHA-256 is 64 bits — enough, and worth asserting that the truncation is deliberate

### PQL-377 · An empty expansion has a digest
- **Area:** `pql/expand.py::Expansion.of`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** no matching attributes
- **Steps:** build the expansion
- **Expected:** a digest of the empty string, and `count == 0`
- **Why:** an approved expansion covering nothing must be distinguishable from one that was never taken

### PQL-378 · `Drift` reports additions and removals
- **Area:** `pql/expand.py::Expander.drift`, `Drift.render`
- **Type:** functional
- **Priority:** P1
- **Precondition:** an approved expansion and a catalogue that has since gained four attributes and lost one
- **Steps:** call `drift` and render it
- **Expected:** "This selector now covers 4 more: …; and no longer covers 1: …."
- **Why:** the sentence a person approves; the whole materialisation design exists so that this is a decision rather than a surprise

### PQL-379 · `Drift` with no change says so
- **Area:** `pql/expand.py::Drift.render`
- **Type:** functional
- **Priority:** P2
- **Precondition:** an unchanged catalogue
- **Steps:** render the drift
- **Expected:** "This selector covers exactly what it covered when it was approved."
- **Why:** the no-change message is what an operator sees most often, and an empty string there reads as an error

### PQL-380 · `Drift` truncates a long list at five
- **Area:** `pql/expand.py::Drift.render`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** twenty new attributes
- **Steps:** render
- **Expected:** five names and a trailing `…`, with the full count stated first
- **Why:** the count is the number that matters and must not be lost to the truncation

### PQL-381 · Expansion is materialised, never re-evaluated at run time
- **Area:** `pql/expand.py` module docstring
- **Type:** contract
- **Priority:** P1
- **Precondition:** an approved expansion
- **Steps:** tag a new attribute so it would match, then run the estate
- **Expected:** the new attribute is **not** silently covered; the drift is reported instead
- **Why:** the docstring's central claim — "nobody approved the new control, nobody was told, and the first anybody hears of it is an alert about a dataset they did not know was in scope"

## 12 · Language services — `pql/analysis.py`

### PQL-382 · Diagnostics for empty and whitespace-only text
- **Area:** `pql/analysis.py::LanguageService.diagnostics`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** none
- **Steps:** `diagnostics("")`, `diagnostics("   \n")`
- **Expected:** `[]`
- **Why:** an editor sends the buffer on every keystroke, including the first; a parse error on an empty file would light the whole gutter

### PQL-383 · A syntax error becomes one located diagnostic
- **Area:** `pql/analysis.py::_from_error`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `diagnostics("CHECK positions")`
- **Expected:** one diagnostic at level `error`, with the line, column and length of the offending token, and the remedy
- **Why:** the four numbers are what the editor underlines

### PQL-384 · Diagnostics ignore every control inside a suite
- **Area:** `pql/analysis.py::LanguageService.diagnostics`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a catalogue declaring `positions`
- **Steps:** `diagnostics("SUITE core { CHECK positions.nosuchcolumn IS NOT NULL }")`
- **Expected:** a diagnostic naming the unknown column
- **Why:** the loop is `for control in program.controls`, not `program.all_controls`, so every control inside a `SUITE` — which is how a real estate is written — receives no type checking, no lint and no unknown-column warning in either editor

### PQL-385 · Lint severities are flattened to "warning"
- **Area:** `pql/analysis.py::LanguageService.diagnostics`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a control with `BELOW 100%` and no BECAUSE
- **Steps:** read the diagnostics
- **Expected:** the `never-fires` finding at error level and the `no-justification` finding at information level
- **Why:** both are emitted as `level="warning"` regardless of `LintFinding.severity`, so a control that can never fire and a control missing a comment underline identically in the editor

### PQL-386 · A repeated message is reported once, across all controls
- **Area:** `pql/analysis.py::LanguageService.diagnostics`
- **Type:** negative
- **Priority:** P2
- **Precondition:** two controls, both naming the same unknown column
- **Steps:** read the diagnostics
- **Expected:** documented — the `said` set suppresses the second, so only the first control is underlined
- **Why:** the comment justifies the de-duplication for the "nothing is known about X" case only; it is applied to *every* message, so a real error on control 7 is invisible because control 2 had the same one

### PQL-387 · `unchecked` is a third level, not a warning
- **Area:** `pql/analysis.py::Diagnostic.severity`
- **Type:** contract
- **Priority:** P1
- **Precondition:** an empty catalogue
- **Steps:** read a diagnostic for an undeclared dataset and check `.level` and `.severity`
- **Expected:** `"unchecked"` and LSP severity 3 (information)
- **Why:** "a warning says 'this is probably wrong'; unchecked says 'nobody has looked'. Rendering the second as the first trains people to dismiss both"

### PQL-388 · `has_position` is false when there is no position
- **Area:** `pql/analysis.py::Diagnostic.has_position`, `_at`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a finding with `position=None`
- **Steps:** convert it and read `has_position`
- **Expected:** False, with line/column/length all zero
- **Why:** "zeros rather than ones. One-one is a real place, and a diagnostic that claims it sends the reader to the top of the file to look for a problem that is somewhere else"

### PQL-389 · Completions after a dot offer that dataset's columns only
- **Area:** `pql/analysis.py::LanguageService.completions`, `_context`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a catalogue with two datasets
- **Steps:** complete at the cursor in `CHECK positions.`
- **Expected:** only `positions`' columns, each with its declared type and nullability
- **Why:** "offering every column in the estate would produce a control that parses, type-checks against the wrong dataset and fails at compile time with a message about SQL"

### PQL-390 · Completions after a dot on an undeclared dataset are empty
- **Area:** `pql/analysis.py::LanguageService.completions`
- **Type:** functional
- **Priority:** P1
- **Precondition:** an empty catalogue
- **Steps:** complete at `CHECK unknown.`
- **Expected:** `[]` — never a guess
- **Why:** "a suggestion the estate cannot satisfy is worse than no suggestion, because it gets accepted"

### PQL-391 · Completions at the start offer datasets, functions and keywords
- **Area:** `pql/analysis.py::LanguageService.completions`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a catalogue with one dataset
- **Steps:** complete on the prefix `co`
- **Expected:** matching datasets (kind 7), functions (kind 3) and keywords (kind 14), each prefix-matched case-insensitively
- **Why:** three sources, three LSP kinds, and the kinds are "in the LSP's own numbering so the protocol layer does no translation"

### PQL-392 · Completion prefix matching is case-insensitive
- **Area:** `pql/analysis.py::LanguageService.completions`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a dataset called `Positions`
- **Steps:** complete on `pos` and on `POS`
- **Expected:** the dataset appears both times
- **Why:** a user types in whatever case is convenient and the estate is stored in whatever case the warehouse used

### PQL-393 · Hover on a declared column
- **Area:** `pql/analysis.py::LanguageService.hover`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a catalogue with `positions.notional numeric` declared not-null
- **Steps:** hover the column half of `positions.notional`
- **Expected:** title `positions.notional`; body naming the type, the nullability and the family
- **Why:** answered from the estate "never from a glossary maintained beside them"

### PQL-394 · Hover on the dataset half of a dotted name
- **Area:** `pql/analysis.py::_word_at`
- **Type:** functional
- **Priority:** P1
- **Precondition:** as above
- **Steps:** hover the `positions` half
- **Expected:** the dataset hover, listing its columns — not the column hover
- **Why:** "returning the whole dotted name either way answers the second question both times, which is wrong in the half where somebody is checking a dataset name"

### PQL-395 · Hover on an undeclared dataset says nothing has been checked
- **Area:** `pql/analysis.py::LanguageService.hover`
- **Type:** functional
- **Priority:** P1
- **Precondition:** an empty catalogue
- **Steps:** hover `positions` in `CHECK positions.a IS NOT NULL`
- **Expected:** a hover saying the name is not declared and that a control against it "will parse and will not be verified"
- **Why:** "that is the one hover somebody most needs, and without the flag it is the one hover that comes back empty"

### PQL-396 · Hover on a wrong column of a declared dataset suggests
- **Area:** `pql/analysis.py::LanguageService.hover`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a declared dataset
- **Steps:** hover a mistyped column
- **Expected:** "Not a declared column of positions. Did you mean `account_id`? Declared: …"
- **Why:** `schema.suggest` is called twice in the expression; assert it agrees with itself and is not empty in one place and not the other

### PQL-397 · Hover on a function and on a keyword
- **Area:** `pql/analysis.py::LanguageService.hover`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** hover `ROUND`, then `BECAUSE`
- **Expected:** the function hover names the summary, the return family, the engines it is refused on and the Excel divergence; the keyword hover says "A PQL keyword."
- **Why:** the resolution order is dataset → function → keyword, so a dataset called `round` would shadow the function — assert the order is deliberate

### PQL-398 · Hover at the boundaries of a word
- **Area:** `pql/analysis.py::_word_at`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** hover at column 0, at the first character, at the last character, one past the last, and two past
- **Expected:** the word for the middle three, nothing for the outer two
- **Why:** `match.start() < column <= match.end() + 1` is an inclusive-on-one-side range and is the sole cursor rule

### PQL-399 · Hover on a line or column out of range
- **Area:** `pql/analysis.py::_line_of`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a three-line document
- **Steps:** hover line 0, line 99, column 9999
- **Expected:** an empty hover, never an `IndexError`
- **Why:** an editor sends the cursor position it has, which can lag the buffer by a keystroke

### PQL-400 · The console editor and the LSP give identical answers
- **Area:** `pql/analysis.py::LanguageService`
- **Type:** contract
- **Priority:** P1
- **Precondition:** the same text and catalogue
- **Steps:** call `diagnostics`, `completions` and `hover` through the console endpoint and through `prama lsp serve`
- **Expected:** identical results
- **Why:** the module docstring's reason for existing — "two implementations of 'is this column real' is precisely how an editor comes to underline something the compiler accepts, and once that happens people stop reading the underlines"

### PQL-401 · The language layer does not import the IR
- **Area:** `pql/analysis.py` module docstring, `tests/architecture`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** import-scan `src/prama/pql/**` for any reference to `prama.ir` or `prama.backend`
- **Expected:** none
- **Why:** the docstring records that the architecture test "caught this file importing `prama.ir` for exactly that convenience"

## 13 · The package surface — `pql/__init__.py`, `pql/families.py`

### PQL-402 · `from prama.pql import *` succeeds
- **Area:** `pql/__init__.py::__all__`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** execute `from prama.pql import *`
- **Expected:** no error
- **Why:** `__all__` names `Attribute`, `AttributeCatalogue`, `Drift`, `Expander` and `Expansion`, none of which the module imports — a star import raises `AttributeError` on the first of them, and any tool that introspects `__all__` sees five names that are not there

### PQL-403 · Every name in `__all__` is importable individually
- **Area:** `pql/__init__.py`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** `getattr(prama.pql, name)` for every entry of `__all__`
- **Expected:** all resolve
- **Why:** the package surface is the documented API; five dead entries means the expansion API is either meant to be public and is not exported, or is not and should not be listed

### PQL-404 · The five type families are the only ones
- **Area:** `pql/families.py::FAMILIES`, `pql/types.py::TYPE_FAMILIES`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** assert every value of `TYPE_FAMILIES` and every `Function.returns`/`argument_types` entry is a member of `FAMILIES`
- **Expected:** no value outside the five
- **Why:** the leaf module exists so the checker and the catalogue share one vocabulary; a sixth family invented in either would type-check against nothing

### PQL-405 · `UNKNOWN` is comparable with everything
- **Area:** `pql/families.py::UNKNOWN`, `pql/types.py::TypeChecker._compare`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a schema with an undeclared-type column
- **Steps:** compare it with a number, text, a boolean and a date
- **Expected:** no findings in any case
- **Why:** "refusing would make every control over an unprofiled dataset fail to check" — and Prama is pointed at unprofiled data by design

## 14 · The plan model and plan identity — `ir/model.py`

### IR-001 · A plan id is a hash of the plan's meaning
- **Area:** `ir/model.py::ControlPlan.meaning`, `content_hash`, `plan_id`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** lower a control twice in two processes and compare `plan_id`
- **Expected:** identical, and of the form `ir:sha256:<64 hex>`
- **Why:** an evidence record names the plan id; a hash that varies by process makes replay impossible

### IR-002 · Two controls that say the same thing in different words share a plan id
- **Area:** `ir/model.py::ControlPlan.meaning`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** lower `CHECK t.n BETWEEN -10 AND 10` and `CHECK t.n BETWEEN - 10 AND 10`; also two controls differing only in clause order
- **Expected:** identical ids
- **Why:** "the hash identifies the meaning rather than the paperwork" — otherwise deduplication, caching and "has this actually changed" all stop working

### IR-003 · Severity, dimensions, BECAUSE, description and provenance are outside the hash
- **Area:** `ir/model.py::ControlPlan.meaning`, `Provenance`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** lower the same control with different severity, dimensions, owner and justification; compare ids
- **Expected:** identical
- **Why:** "including them would make an edited comment look like a changed control, and every cached result would be discarded for nothing"

### IR-004 · Evidence level is outside the hash
- **Area:** `ir/model.py::ControlPlan.meaning`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** lower the same control with `EVIDENCE counts` and `EVIDENCE full`
- **Expected:** the same plan id
- **Why:** the comment says sampling depth "changes what is kept, not what is computed" — assert it, because the evidence policy *does* change the emitted sample query

### IR-005 · An edited control gets a different id
- **Area:** `ir/model.py::ControlPlan.content_hash`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** change the threshold, then the filter, then the unknown policy, then the predicate, then a segment column — one at a time
- **Expected:** a different id for each change
- **Why:** five fields in `meaning`, and one that does not move the hash is a control that can be edited without the evidence noticing

### IR-006 · The binding is part of the hash
- **Area:** `ir/model.py::Scope.binding`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** lower the same control against two bindings
- **Expected:** two different plan ids
- **Why:** "the same control against two bindings is two controls, and conflating them would let evidence from one be replayed against the other"

### IR-007 · The IR version is in the hash
- **Area:** `ir/model.py::IR_VERSION`, `meaning`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** assert `meaning()["ir_version"]` is present and equals `IR_VERSION`
- **Expected:** present in every plan, and changing the constant changes every plan id
- **Why:** "an evidence record names the version it was produced under, so a control replayed years later is interpreted the way it was when it ran"; a version bump must invalidate every id

### IR-008 · The canonical encoding sorts keys and handles every value type
- **Area:** `ir/model.py::content_hash`, `core/pjson.canonical`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** hash a plan whose `detail` contains nested dicts inserted in two different orders, and one containing `None`, a float, a bool and a list
- **Expected:** the same hash for the two orders; no `TypeError` for any value
- **Why:** "a hash that depends on dict insertion order is not a hash of the content"

### IR-009 · A residual makes a plan hash differently
- **Area:** `ir/lower.py::Lowerer.control`, `ir/model.py::meaning`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** lower `IS VALID 'lei'` (two-stage) and `IS VALID 'uuid'` (pattern-complete); compare the `detail` in each plan
- **Expected:** the first carries `residual_validators`, the second does not, and the ids differ
- **Why:** "two plans that check different things must never share an id" — a screen-only plan and a two-stage plan look identical in SQL

### IR-010 · Editing a validator changes the plan id of every control using it
- **Area:** `ir/lower.py::Lowerer._valid`, `classify/plugins.PLUGINS.provenance`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a validator with a registered implementation hash
- **Steps:** lower a two-stage control, change the validator implementation, lower again
- **Expected:** different plan ids
- **Why:** "somebody edits the check digit routine, and last month's evidence silently starts meaning something else while claiming to be the same control"

### IR-011 · Residuals are de-duplicated and ordered
- **Area:** `ir/lower.py::Lowerer.control`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** lower a control that applies the same validator to the same column twice, and one that applies two validators
- **Expected:** one residual in the first case; a deterministic sorted order in the second
- **Why:** the residual list is in the hash, so a non-deterministic order is a non-deterministic plan id

### IR-012 · `is_two_stage` and `residual_validators` agree
- **Area:** `ir/model.py::ControlPlan.is_two_stage`, `residual_validators`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** assert `is_two_stage` is exactly `bool(residual_validators)` for every corpus plan
- **Expected:** the two agree on every plan
- **Why:** "False means it is not [sufficient]. Reporting one anyway is how a control over a column of fabricated identifiers runs green for a year"

### IR-013 · A residual over a non-column subject is refused
- **Area:** `ir/lower.py::Lowerer._valid`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** lower `CHECK t SATISFIES UPPER(lei) IS VALID 'lei'`-shaped input, i.e. an `IS VALID` whose subject is an expression
- **Expected:** `ValidationError` "IS VALID 'lei' can only be applied to a column", with the two-stage explanation
- **Why:** "a residual nobody can locate is a residual nobody will apply, and the failure mode of dropping it silently is a green control over invalid data"

### IR-014 · A complete (pattern) validator produces no residual
- **Area:** `ir/lower.py::Lowerer._valid`, `classify/validators.SemanticValidator.screen_is_complete`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** lower `IS VALID 'uuid'`, `'ulid'`, `'email'`, `'bic'`, `'mic'`, `'uti'`, `'upi'`, `'hex_colour'`
- **Expected:** no residual; the screen is the whole check
- **Why:** eight of the twenty shipped validators are complete, and marking one incomplete by mistake would make every control using it permanently two-stage

### IR-015 · An unknown semantic type is refused
- **Area:** `ir/lower.py::Lowerer._valid`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** lower `IS VALID 'nosuchtype'`
- **Expected:** "there is no semantic type called 'nosuchtype'", remedy explaining that an unresolved type "would compile to a check that passes everything, which is worse than no control because it looks like coverage"
- **Why:** the refusal is the promise

### IR-016 · Every assertion kind lowers
- **Area:** `ir/lower.py::Lowerer._assertion`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** lower one control of each assertion type and read `assertion_kind`
- **Expected:** `predicate`, `unique_key`, `row_count`, `reference`, `freshness`, `functional_dependency` — six kinds, each carrying the detail its strategy needs
- **Why:** the `detail` dict is where a backend gets everything the predicate could not express

### IR-017 · An assertion with no lowering is refused by name
- **Area:** `ir/lower.py::Lowerer._assertion`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** lower a bare `Assertion()` instance
- **Expected:** `ValidationError` "Assertion cannot yet be lowered to a plan", remedy saying the language "deliberately refuses to pretend it can run something it cannot"
- **Why:** the honest gap, and the only thing stopping a new assertion type from silently compiling to nothing

### IR-018 · Every predicate operator lowers to a positive predicate
- **Area:** `ir/lower.py::Lowerer._predicate`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** lower each of the thirteen operator forms and assert the predicate reads "true means the row is fine"
- **Expected:** `violating_rows` is uniformly `count_if(NOT predicate)`
- **Why:** "no backend has to remember which assertions were written the other way round"

### IR-019 · A negated predicate wraps in NOT
- **Area:** `ir/lower.py::Lowerer._predicate`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** lower `NOT IN`, `NOT BETWEEN`, `NOT MATCHES`
- **Expected:** an outer `NOT` around the positive form
- **Why:** the `is_unique` early return sits in the middle of this and must not swallow the negation for the others

### IR-020 · A codelist is resolved into the plan, not looked up at run time
- **Area:** `ir/lower.py::Lowerer._codelist`
- **Type:** contract
- **Priority:** P1
- **Precondition:** the shipped ISO 4217 list
- **Steps:** lower `IN CODELIST iso4217` and inspect the IR
- **Expected:** an `IN` over an explicit literal set; the plan id changes if the list changes
- **Why:** "the plan hash would be identical before and after somebody edited the list, and two runs with different verdicts would claim to be the same control"

### IR-021 · An empty codelist produces `IN ()`
- **Area:** `ir/lower.py::Lowerer._codelist`, `backend/sql.py::SqlCompiler.expression`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a registered codelist with no values
- **Steps:** lower and compile
- **Expected:** a refusal, not `IN ()`
- **Why:** the parser refuses a hand-written `IN ()` because "an empty set fails every row"; the codelist path has no such guard and emits SQL no engine will parse

### IR-022 · `as_of` freezes the codelist at a stated date
- **Area:** `ir/resolve.py::resolved`, `classify/codelists.REGISTRY.resolve`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a codelist with a dated change (ZWG replacing ZWL in 2024)
- **Steps:** resolve the same control at two dates and compare the literal sets and the plan ids
- **Expected:** different sets, different ids
- **Why:** "a list edited on Tuesday cannot silently change what Monday's evidence meant"

### IR-023 · `resolved` with no `as_of` produces the same id as a bare `Lowerer`
- **Area:** `ir/resolve.py::resolved`
- **Type:** regression
- **Priority:** P1
- **Precondition:** none
- **Steps:** compare `resolved(control).plan_id` with `Lowerer(codelists=CODELISTS.resolve(None)).control(control).plan_id`
- **Expected:** identical
- **Why:** the comment records the defect: passing the default explicitly "produced a *different plan id* for the same control — the Lowerer's own default is the empty string and `None` serialises as null"

### IR-024 · `as_of` is a parameter name, and a date breaks it
- **Area:** `ir/resolve.py::resolved`, `ir/model.py::Scope.as_of`, `ControlPlan.parameters`, `backend/sql.py::SqlCompiler.compile`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** call `resolved(control, as_of=date(2026, 1, 1))` and then compile the plan
- **Expected:** a coherent result or a typed refusal
- **Why:** `Scope.as_of` is documented and typed as "the parameter name holding the run's business date", and `resolved` forwards the `date` object into it. `parameters()` then puts a `date` into a set of strings and `compile` does `tuple(sorted(...))`, which raises `TypeError: '<' not supported between instances of 'str' and 'datetime.date'`. Two meanings for one field

### IR-025 · Every call site uses `resolved`
- **Area:** `ir/resolve.py` module docstring
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** grep for `Lowerer(` outside `ir/resolve.py` and the tests
- **Expected:** none, or each with a stated reason
- **Why:** the module exists because "each caller remembering is how three of six call sites end up subtly different" — and `backend/conformance.py::plan_for` still constructs a bare `Lowerer()`, so no conformance case can use a codelist

### IR-026 · Predicate metrics: scanned and violating
- **Area:** `ir/lower.py::Lowerer._metrics`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** lower any predicate control
- **Expected:** two metrics; `violating_rows` has `applies_unknown_policy=True` and `scanned_rows` does not
- **Why:** the flag is stated rather than inferred "because a backend that guessed 'the one called violating_rows is special' would apply the policy to the wrong metric the first time another counted condition was added — which is exactly what happened with the null-key count"

### IR-027 · Unique-key metrics: scanned, distinct and null keys
- **Area:** `ir/lower.py::Lowerer._metrics`, `_any_null`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** lower `HAS UNIQUE KEY (a, b)`
- **Expected:** three metrics, no `violating_rows`; the null-key condition is `a IS NULL OR b IS NULL`
- **Why:** "emitting a literal zero for it would put a meaningless number on the record", and every engine's `COUNT(DISTINCT)` ignores nulls, so they need their own count

### IR-028 · A single-column key's null condition is not an OR chain
- **Area:** `ir/lower.py::_any_null`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** lower `HAS UNIQUE KEY (a)` and inspect the null-key metric
- **Expected:** a single `IS NULL`, not `a IS NULL OR a IS NULL`
- **Why:** the `len(tests) == 1` branch; without it the plan id of a one-column key would differ from its natural form

### IR-029 · Functional-dependency metrics are not the unique-key test
- **Area:** `ir/lower.py::Lowerer._metrics`
- **Type:** functional
- **Priority:** P1
- **Precondition:** rows where each account appears many times under one entity
- **Steps:** lower `SATISFIES account_id DETERMINES entity` and judge it
- **Expected:** `pass`
- **Why:** the comment: "testing distinct-against-scanned would fail every legitimate dataset, which is a control that cannot be satisfied dressed as one that is failing"

### IR-030 · A row-count plan has one metric and no predicate
- **Area:** `ir/lower.py::Lowerer._metrics`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** lower `HAS ROW COUNT BETWEEN 1 AND 8`
- **Expected:** only `scanned_rows`; `predicate is None`; `detail` carries `minimum` and `maximum`
- **Why:** "the row count *is* the metric; there is no per-row violation"

### IR-031 · A reference plan lowers to EXISTS, not a null check
- **Area:** `ir/lower.py::Lowerer._assertion`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** lower `a.x REFERENCES b.y`
- **Expected:** `Expr.operation("EXISTS", column, target dataset, target column)` and `assertion_kind == "reference"`
- **Why:** "lowering a referential control to IS NOT NULL would leave it passing on every orphan — a control that looks present, reports green, and checks something else entirely"

### IR-032 · A reference plan declares the cross-object-join capability
- **Area:** `ir/model.py::Expr.requires`, `ControlPlan.requires`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a dialect without `pushdown.cross_object_join`
- **Steps:** compile a reference control for it
- **Expected:** refused, naming the capability
- **Why:** "an engine that cannot join across the two has to be told before the control is approved, not when it runs"

### IR-033 · `requires` aggregates from every part of the plan
- **Area:** `ir/model.py::ControlPlan.requires`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** build plans needing regex (in the predicate, and separately in the filter), aggregation (unique key, functional dependency, segmentation), approximate distinct, and cross-object join
- **Expected:** every requirement surfaces in `plan.requires`
- **Why:** `_check_capabilities` refuses on this set alone, so a requirement that does not propagate is a control that compiles and then cannot run

### IR-034 · `columns()` finds every column the plan touches
- **Area:** `ir/model.py::ControlPlan.columns`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** build a plan with columns in the predicate, the filter, a segment, a metric expression, `key_columns`, `determinant` and `dependent`
- **Expected:** all appear
- **Why:** the sample query projects exactly this set, so a missed column is a sample row that omits the evidence

### IR-035 · A threshold with a missing metric is indeterminate
- **Area:** `ir/model.py::Threshold.evaluate`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** evaluate a threshold naming `violating_rows` against metrics that lack it
- **Expected:** `INDETERMINATE`
- **Why:** "the control did not demonstrate anything, and saying so is the honest answer"

### IR-036 · An empty scope is indeterminate for every threshold path
- **Area:** `ir/model.py::Threshold.evaluate`
- **Type:** regression
- **Priority:** P1
- **Precondition:** none
- **Steps:** evaluate with `scanned_rows = 0` for an absolute threshold and for a rate threshold
- **Expected:** `INDETERMINATE` in both cases
- **Why:** QA finding Q-09 — the guard lived inside the `relative_to` branch alone, so a percentage threshold refused an empty scan and the absolute one, which every predicate control lowers to, reported PASS

### IR-037 · A missing `scanned_rows` disables the empty-scope guard
- **Area:** `ir/model.py::Threshold.evaluate`
- **Type:** negative
- **Priority:** P1
- **Precondition:** metrics with `violating_rows` but no `scanned_rows`
- **Steps:** evaluate
- **Expected:** not a clean PASS
- **Why:** the guard is `metrics.get("scanned_rows", -1.0) == 0.0`, so a backend that omits the metric — which `ConformanceRun._judge` does whenever the engine returns NULL for it — falls straight back to the path Q-09 fixed

### IR-038 · A rate threshold with a zero denominator is indeterminate
- **Area:** `ir/model.py::Threshold.evaluate`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** none
- **Steps:** evaluate a `relative_to` threshold where the denominator metric is 0 and where it is absent
- **Expected:** `INDETERMINATE` in both cases
- **Why:** a division by zero here would be an exception in the judgement path, which every control passes through

### IR-039 · Every comparator holds correctly at its boundary
- **Area:** `ir/model.py::Comparator.holds`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** none
- **Steps:** for each of `<=`, `<`, `>=`, `>`, `=`, `<>`, evaluate at the threshold exactly, just below and just above
- **Expected:** the six standard answers; `=` and `<>` on floats behave as exact comparisons
- **Why:** the corpus has a case "exactly on 0 and exactly on 1000" for precisely this reason

### IR-040 · `Verdict.is_actionable` covers fail, error and indeterminate
- **Area:** `ir/model.py::Verdict.is_actionable`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** check all five verdicts
- **Expected:** FAIL, ERROR and INDETERMINATE are actionable; PASS and SKIPPED are not
- **Why:** "a sample too small to support the declared confidence has not shown that the data is good; it has shown that we did not look hard enough" — an indeterminate that is not actionable is a pass in disguise

### IR-041 · `Expr.to_dict` is lossless for the hash
- **Area:** `ir/model.py::Expr.to_dict`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** serialise a literal `None`, a literal `0`, a literal `False`, a column with and without a declared type, and an op with no args
- **Expected:** two expressions that mean different things never serialise identically
- **Why:** `value` is emitted only when non-None *or* the kind is `lit`, and `type` only when it is not `unknown` — so a typed and an untyped column reference differ in the hash while meaning the same thing, and the plan id depends on whether a catalogue was available at lowering time

### IR-042 · `to_json` round-trips a plan
- **Area:** `ir/model.py::ControlPlan.to_json`, `to_dict`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** serialise every corpus plan
- **Expected:** valid sorted JSON in every case, with the plan id embedded
- **Why:** the IR is what `prama control compile` shows a DBA and what an evidence bundle carries; a plan that will not serialise cannot be published

### IR-043 · A plan whose detail holds a non-JSON value
- **Area:** `ir/model.py::ControlPlan.meaning`, `core/pjson`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** hash a plan whose `detail` contains a `Decimal`, a `date`, a `set` and a NaN
- **Expected:** a defined hash in each case, matching the documented encodings, or a clear refusal
- **Why:** `detail` is an untyped `dict[str, Any]` inside the hash, and the encoding of a non-finite float is `null` — two different NaNs hashing the same is a choice worth pinning

### IR-044 · The backend never reaches back to the AST
- **Area:** `ir/model.py` module docstring, `tests/architecture`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** import-scan `src/prama/backend/**` for `prama.pql.ast`
- **Expected:** none — the compiler imports `pql.errors` and `pql.library`, but no AST node
- **Why:** "a backend that could would eventually diverge from the one that did not"

## 15 · Dialects — `backend/dialect.py`

### BE-001 · Three dialects are registered and reachable by name
- **Area:** `backend/dialect.py::DIALECTS`, `dialect`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `dialect("postgresql")`, `dialect("duckdb")`, `dialect("sqlite")`
- **Expected:** the matching instances
- **Why:** the dialect name is a configuration value and a CLI flag, and this is the only lookup

### BE-002 · An unknown dialect is refused, listing the real ones
- **Area:** `backend/dialect.py::dialect`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `dialect("oracle")`, `dialect("")`, `dialect("POSTGRESQL")`
- **Expected:** `RegistryError` "no SQL dialect named …", remedy listing all three; note that the lookup is case-sensitive
- **Why:** a mis-cased dialect in a config file must fail at start-up, not produce a wrong quoting style

### BE-003 · Identifier quoting escapes an embedded quote
- **Area:** `backend/dialect.py::SqlDialect.quote`
- **Type:** security
- **Priority:** P1
- **Precondition:** none
- **Steps:** quote `a"b`, `a""b`, `a'b`, `a;DROP TABLE x--`, `a\nb`, and an empty string
- **Expected:** the double quote is doubled in every case and the result is a single well-formed quoted identifier
- **Why:** column names come from a warehouse catalogue and from user-supplied PQL, and this is the only escaping between them and the query

### BE-004 · Dataset names are qualified part by part
- **Area:** `backend/dialect.py::SqlDialect.qualify`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** qualify `positions`, `risk.positions`, `db.risk.positions`
- **Expected:** each part quoted separately and joined with dots
- **Why:** a binding is a physical name that may already carry a schema

### BE-005 · A dataset name containing a dot inside quotes is split anyway
- **Area:** `backend/dialect.py::SqlDialect.qualify`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a table genuinely named `risk.positions` in the default schema
- **Steps:** qualify it
- **Expected:** a way to express it
- **Why:** `qualify` splits unconditionally, so the one-part name becomes a two-part reference and the table cannot be addressed at all

### BE-006 · Literal rendering per type
- **Area:** `backend/dialect.py::SqlDialect.literal`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** render `None`, `True`, `False`, `0`, `-1`, `1.5`, `1e20`, `"it's"`, `""`, and a `Decimal("1.5")`
- **Expected:** `NULL`, the engine's boolean spelling, numeric literals, an escaped string — and a defined answer for the Decimal
- **Why:** `isinstance(value, int | float)` excludes `Decimal`, so an exact number falls through to the string branch and is emitted as the *text* `'1.5'` — a silent type change in a money comparison

### BE-007 · A non-finite float literal
- **Area:** `backend/dialect.py::SqlDialect.literal`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** render `float("nan")` and `float("inf")`
- **Expected:** a refusal or an engine-valid spelling
- **Why:** `repr(float("inf"))` is `inf`, which is not SQL on any of the three engines

### BE-008 · Booleans are `1`/`0` on SQLite and `TRUE`/`FALSE` elsewhere
- **Area:** `backend/dialect.py::SqliteDialect.boolean`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** compile the same `COALESCE(pred, FALSE)` violation condition for each engine
- **Expected:** `FALSE` on postgresql and duckdb, `0` on sqlite
- **Why:** SQLite has no boolean type, and a literal `FALSE` there is an unknown column reference

### BE-009 · `count_if` uses FILTER where the engine has it
- **Area:** `backend/dialect.py::SqlDialect.count_if`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** render a count_if on each engine
- **Expected:** `COUNT(*) FILTER (WHERE …)` on postgresql and duckdb; `COALESCE(SUM(CASE WHEN … THEN 1 ELSE 0 END), 0)` on sqlite
- **Why:** the `COALESCE` on the portable path is what stops an empty table returning NULL and "turning an empty table into an indeterminate verdict for the wrong reason"

### BE-010 · `count_if` over an empty table returns zero on every engine
- **Area:** `backend/dialect.py::SqlDialect.count_if`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** an empty table
- **Steps:** execute the metric query on each engine
- **Expected:** `0`, not NULL, in every case
- **Why:** the empty-scope verdict is decided by `scanned_rows`, and a NULL `violating_rows` would be dropped by `_judge` and change the reason for the indeterminacy

### BE-011 · `count_distinct` over one column and over several
- **Area:** `backend/dialect.py::SqlDialect.count_distinct`, `DuckDbDialect.count_distinct`, `SqliteDialect.count_distinct`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** render a one-column and a three-column distinct count on each engine and execute both over the corpus
- **Expected:** the same number on all three
- **Why:** three different constructions — a row constructor, a struct and a `CHAR(31)`-joined string — for one meaning, and only execution proves they agree

### BE-012 · SQLite's composite key join is injective
- **Area:** `backend/dialect.py::SqliteDialect.count_distinct`
- **Type:** negative
- **Priority:** P1
- **Precondition:** rows whose key parts contain the separator characters `CHAR(31)` and `CHAR(30)`
- **Steps:** count distinct over `(a, b)` where one row is `("x\x1fy", "z")` and another is `("x", "y\x1fz")`
- **Expected:** two distinct keys
- **Why:** the comment says a separator "that cannot occur in the data would be a guess" and calls the sentinel "explicit about what it assumes" — the assumption is still an assumption and must be tested against a row that breaks it

### BE-013 · `count_distinct` with a subset condition
- **Area:** `backend/dialect.py::SqlDialect._distinct_over`
- **Type:** functional
- **Priority:** P1
- **Precondition:** rows with null key parts
- **Steps:** render and execute the `where`-qualified form on each engine
- **Expected:** the same count; the FILTER form and the `CASE WHEN … THEN … END` form agree
- **Why:** "SQL is inconsistent about nulls here" — the docstring names the exact inconsistency, and the two constructions are how it is neutralised

### BE-014 · Regular expressions per engine
- **Area:** `backend/dialect.py::PostgresDialect.regex_match`, `DuckDbDialect.regex_match`, `SqliteDialect.regex_match`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** render `MATCHES /^[A-Z]{2}/` on each engine and execute it
- **Expected:** `~`, `regexp_matches(…)` and `REGEXP` respectively, all matching the same rows
- **Why:** three flavours — POSIX, RE2 and Python — and a pattern using a feature only one of them has is a control that means three things

### BE-015 · A pattern using a non-portable regex feature
- **Area:** `backend/dialect.py::regex_flavour`, `backend/reference.py::_matches`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** run `MATCHES /(?<=A)B/` (lookbehind), `/\d+/`, `/(a)\1/` (backreference), `/^(?i)abc/` on every engine and the reference
- **Expected:** agreement, or a refusal naming the flavour
- **Why:** RE2 has no lookbehind and no backreferences, POSIX has no `\d`, and Python has all three — nothing validates a pattern against the target engine's flavour, so the same control matches different rows on different engines

### BE-016 · An invalid pattern
- **Area:** `backend/reference.py::ReferenceEvaluator._matches`, `backend/dialect.py::regex_match`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** run `MATCHES /[/` and `MATCHES /*/`
- **Expected:** a refusal at authoring time
- **Why:** `re.compile` raises `re.error` from inside a per-row evaluation in the reference interpreter, and the engines raise at execution — a malformed pattern should be caught when the control is written

### BE-017 · The base dialect refuses regular expressions with a remedy
- **Area:** `backend/dialect.py::SqlDialect.regex_match`, `Unsupported`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a dialect with no regex support
- **Steps:** compile a `MATCHES` control for it
- **Expected:** `PqlUnsupportedError` carrying the capability name, a detail naming the expression and the pattern, and the remedy refusing to substitute `LIKE`
- **Why:** "a dialect never approximates" — the one thing a dialect is not permitted to do, stated in the module docstring

### BE-018 · SQLite claims the regex capability that a bare connection does not have
- **Area:** `backend/dialect.py::SqliteDialect.capabilities`, `connect/sources/query.register_regexp`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a plain `sqlite3` connection with no REGEXP function registered
- **Steps:** compile a `MATCHES` control for sqlite and run the SQL on that connection
- **Expected:** the control is refused, or the capability is conditional on the connection
- **Why:** the dialect declares `REGEX` unconditionally and the docstring admits it is "real for Prama's own executor and absent for a bare connection". `prama control compile --dialect sqlite` hands a DBA SQL that fails with "no such function: REGEXP"

### BE-019 · `as_text` is applied before every regex
- **Area:** `backend/dialect.py::SqlDialect.as_text`, `backend/sql.py::SqlCompiler._regex`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a DATE and a NUMERIC column
- **Steps:** compile `MATCHES` on each and execute on duckdb
- **Expected:** the cast is present and the query binds
- **Why:** "DuckDB says `regexp_matches(DATE, ...)` has no candidate, which surfaces as a control that cannot run rather than as a wrong answer"

### BE-020 · The textual form of a date is ISO-8601 on every engine
- **Area:** `backend/dialect.py::SqlDialect.as_text`, `backend/reference.py::_matches`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a DATE column and a TIMESTAMP column
- **Steps:** compare `CAST(col AS VARCHAR)` across the three engines and `str(value)` in the reference
- **Expected:** the same text
- **Why:** the docstring asserts "all three shipped engines render a date as ISO-8601, which is what any pattern for a date expects" — a claim about three third-party products, asserted and not tested

### BE-021 · Division is true division on every engine
- **Area:** `backend/dialect.py::SqlDialect.as_real`, `SqliteDialect.as_real`
- **Type:** regression
- **Priority:** P1
- **Precondition:** the corpus
- **Steps:** run `SATISFIES (row_id / 2) > 0` on all three engines and the reference
- **Expected:** the same verdict everywhere
- **Why:** finding C4 — "SQLite and PostgreSQL do integer division on two integers, so `row_id / 2` is 0 for row 1, while DuckDB and the reference interpreter give 0.5"

### BE-022 · `as_real` uses the engine's own spelling
- **Area:** `backend/dialect.py::SqliteDialect.as_real`, `double_type`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** render a division on each engine
- **Expected:** `DOUBLE PRECISION` on postgresql and duckdb, `REAL` on sqlite
- **Why:** the comment on `double_type` says a fixture writing `"REAL" if dialect == "sqlite"` "would be the one place in the codebase deciding behaviour from an engine name"

### BE-023 · Modulo takes the sign of the dividend on every engine
- **Area:** `backend/dialect.py::SqlDialect.modulo`, `backend/reference.py::_arithmetic`
- **Type:** regression
- **Priority:** P1
- **Precondition:** the corpus row with `notional = -10`
- **Steps:** run `SATISFIES (notional % 3) <> 2` on all three engines and the reference
- **Expected:** the same verdict
- **Why:** finding C4's other half — "`-10 % 3` is -1 in SQL and 2 in Python, so the reference interpreter reported a violation the engines did not"

### BE-024 · Modulo by zero
- **Area:** `backend/dialect.py::SqlDialect.modulo`, `backend/reference.py::_arithmetic`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a row with a zero divisor
- **Steps:** run `SATISFIES (a % b) = 0` where `b` is 0
- **Expected:** agreement — the reference returns UNKNOWN; PostgreSQL raises a division-by-zero error, which aborts the whole query
- **Why:** the library's `MOD` function guards with a `CASE WHEN`; the bare `%` operator does not, so the two spellings of the same operation behave differently

### BE-025 · `exists_in` is a correlated EXISTS, never `IN (SELECT …)`
- **Area:** `backend/dialect.py::SqlDialect.exists_in`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a target column containing a NULL
- **Steps:** run a referential control against it
- **Expected:** orphans are still found
- **Why:** "`NOT IN` becomes unknown for every row and the control silently stops finding orphans. That is the classic SQL trap, and it is worth spending a subquery to avoid"

### BE-026 · A NULL foreign key under each unknown policy
- **Area:** `backend/dialect.py::SqlDialect.exists_in`, `backend/reference.py::ReferenceEvaluator._exists`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a row whose FK is NULL
- **Steps:** run a referential control with the default policy and with `TREAT UNKNOWN AS PASS`
- **Expected:** the SQL and the reference agree in both cases
- **Why:** both return **false** rather than unknown for a null value, so `TREAT UNKNOWN AS PASS` cannot reach a null FK — the same shape as Q-12

### BE-027 · `is_not_distinct_from` per engine
- **Area:** `backend/dialect.py::SqlDialect.is_not_distinct_from`, `SqliteDialect.is_not_distinct_from`
- **Type:** functional
- **Priority:** P2
- **Precondition:** two rows with NULL keys
- **Steps:** render and execute on each engine
- **Expected:** `IS NOT DISTINCT FROM` on postgresql and duckdb, `IS` on sqlite, both null-safe
- **Why:** the only null-safe equality in the product, used where a null is a real key value

### BE-028 · `limit` wraps rather than appends
- **Area:** `backend/dialect.py::SqlDialect.limit`, `backend/sql.py::SqlCompiler.compile`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** compile with `scan_limit=100`
- **Expected:** the limit bounds the *scan*, not the single row of aggregate results
- **Why:** the comment: "a trailing LIMIT would bound the single row of results and leave the scan exactly as expensive — a cap that reads as applied and is not, which is worse than none"

### BE-029 · A capability set is exactly what each engine can do
- **Area:** `backend/dialect.py::capabilities`, `supports`, `missing`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** for each engine, assert the declared set against what it actually supports by executing one probe query per capability
- **Expected:** no engine declares a capability it lacks or omits one it has
- **Why:** `missing()` is the entire refusal mechanism, and `SAMPLING` is declared by two engines and used by nothing

## 16 · The SQL compiler — `backend/sql.py`

### BE-030 · The compiled shape is one aggregate query
- **Area:** `backend/sql.py::SqlCompiler.compile`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** compile a filtered predicate control for each engine
- **Expected:** `SELECT <metrics> FROM <source> WHERE <filter>` with one column per metric, aliased by name
- **Why:** "one pass, one set of numbers, and a denominator recorded beside every numerator — so a rate is never computed from two queries that saw different data"

### BE-031 · A segmented control groups and returns the segment columns first
- **Area:** `backend/sql.py::SqlCompiler.compile`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** compile a `FOR EACH entity` control
- **Expected:** the grouping columns are projected, the `GROUP BY` is present, and `metric_names` begins with the segment columns
- **Why:** `_judge` reads the segment key by name from the row, so the names and the projection must agree exactly

### BE-032 · Capabilities are checked before any SQL is emitted
- **Area:** `backend/sql.py::SqlCompiler._check_capabilities`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a plan needing regex on an engine without it
- **Steps:** compile
- **Expected:** one `PqlUnsupportedError` naming every missing capability at once
- **Why:** "discovering a missing capability halfway through emitting SQL produces an error about a fragment; checking up front produces one about the control"

### BE-033 · `scan_limit` produces a subquery with no alias
- **Area:** `backend/sql.py::SqlCompiler.compile`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** compile with `scan_limit=100` for postgresql and execute
- **Expected:** valid SQL
- **Why:** the source becomes `(SELECT * FROM "t" LIMIT 100)` and PostgreSQL requires "subquery in FROM must have an alias" — so the cap that exists to protect a production warehouse is the one thing that will not run there

### BE-034 · `scan_limit` with a correlated EXISTS
- **Area:** `backend/sql.py::SqlCompiler.compile`, `_exists`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a referential control
- **Steps:** compile it with `scan_limit=100`
- **Expected:** valid SQL
- **Why:** `self._source` becomes the parenthesised subquery text, and `_exists` then emits `(SELECT * FROM "t" LIMIT 100)."col"` — syntactically impossible on every engine

### BE-035 · The outer column of an EXISTS is qualified
- **Area:** `backend/sql.py::SqlCompiler._exists`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a control where the outer and inner columns have the same name
- **Steps:** compile `a.account_id REFERENCES b.account_id` and execute over data with a known orphan
- **Expected:** the orphan is found
- **Why:** the comment: "unqualified it resolves to the innermost scope … and the condition becomes that table's column compared with itself, which is true for every non-null row. The control then reports no orphans, for ever, on any engine"

### BE-036 · `metric_sql` and `compile` produce the same metric SQL
- **Area:** `backend/sql.py::SqlCompiler.metric_sql`, `_metric`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** compare the fused and unfused renderings of the same metric
- **Expected:** identical text
- **Why:** "re-deriving it there would give two definitions of what a violation count is, which is the one thing this file exists to prevent"

### BE-037 · `SqlCompiler` carries mutable state between compilations
- **Area:** `backend/sql.py::SqlCompiler._source`, `metric_sql`
- **Type:** concurrency
- **Priority:** P2
- **Precondition:** one compiler instance
- **Steps:** compile a referential control, then call `expression()` on an unrelated plan's filter containing an EXISTS, then compile again
- **Expected:** each result reflects its own source
- **Why:** `_source` is instance state written by `compile` and `metric_sql` and read by `_exists`; `Fuser._empty_group` calls `expression()` without setting it, so a filter containing an EXISTS is rendered against whatever table was compiled last

### BE-038 · The violation condition inverts the unknown policy
- **Area:** `backend/sql.py::SqlCompiler._violation_condition`
- **Type:** functional
- **Priority:** P1
- **Precondition:** rows with a null in the predicate's column
- **Steps:** compile and execute under both policies on each engine
- **Expected:** `NOT COALESCE(pred, FALSE)` counts the null as a violation; `COALESCE(NOT (pred), FALSE)` does not
- **Why:** "the inversion of SQL's own default and the reason `COALESCE` appears rather than a bare `NOT`" — the single most consequential line in the compiler

### BE-039 · `TREAT UNKNOWN AS PASS` reaches every predicate form
- **Area:** `backend/sql.py::SqlCompiler._violation_condition`, `backend/reference.py::ReferenceEvaluator.is_violation`
- **Type:** regression
- **Priority:** P1
- **Precondition:** null values
- **Steps:** run `TREAT UNKNOWN AS PASS` with `IS VALID`, `MATCHES`, `IN`, `BETWEEN`, `REFERENCES` and a comparison, on every engine and the reference
- **Expected:** the null row passes in every case
- **Why:** QA finding Q-12 — the policy did not reach `IS VALID` on SQLite because the REGEXP hook returned `False` for NULL, against its own docstring; a false is not an unknown and the policy only acts on unknowns

### BE-040 · A plan with no predicate has a constant violation condition
- **Area:** `backend/sql.py::SqlCompiler._violation_condition`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a row-count, unique-key, freshness or functional-dependency plan
- **Steps:** compile
- **Expected:** the condition is the engine's false literal and no sample query is emitted
- **Why:** `_samples` returns `""` when the predicate is None, so four assertion kinds produce no evidence rows at all — which is Q-13 ("uniqueness and functional-dependency records carry no violating_rows")

### BE-041 · The sample query selects only failing rows, bounded
- **Area:** `backend/sql.py::SqlCompiler._samples`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a control with violations
- **Steps:** compile and execute the sample query
- **Expected:** only violating rows, at most `max_samples` of them, projecting exactly `plan.columns()`
- **Why:** evidence is what a regulator reads, and a sample that includes passing rows is a sample nobody can use

### BE-042 · `EVIDENCE counts` emits no sample query
- **Area:** `backend/sql.py::SqlCompiler._samples`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** compile with each evidence level
- **Expected:** `sample_query == ""` for `counts`, non-empty for `samples` and `full`
- **Why:** the level is how a deployment keeps personal data out of the ledger

### BE-043 · A control over no columns projects `*`
- **Area:** `backend/sql.py::SqlCompiler._samples`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a plan whose `columns()` is empty
- **Steps:** compile the sample query
- **Expected:** `SELECT *` and a comment about the risk
- **Why:** `SELECT *` on an evidence path is how an unexpected column of personal data enters the ledger

### BE-044 · Every `Expr` kind compiles
- **Area:** `backend/sql.py::SqlCompiler.expression`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** compile one expression of each kind — `col`, `lit`, `param`, `list`, `call`, `op`
- **Expected:** correct SQL for each; a `None` node compiles to the true literal
- **Why:** six kinds, one dispatcher, and the fall-through is `_operation`

### BE-045 · Parameters are named, not positional
- **Area:** `backend/sql.py::SqlCompiler.expression`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** compile a control with three parameters
- **Expected:** `:name` for each, and `CompiledControl.parameters` sorted and complete
- **Why:** "a control with three parameters bound by position is one edit away from silently checking the wrong dates"

### BE-046 · An unknown function is refused at compile time
- **Area:** `backend/sql.py::SqlCompiler._call`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a plan referencing `NONSENSE_FN`
- **Steps:** compile
- **Expected:** `PqlUnsupportedError` listing the catalogue
- **Why:** "an unrecognised name used to compile straight through to SQL, which is how a typo became a control that ran and meant something nobody intended" — and the reference interpreter returned UNKNOWN for the same expression, so the two disagreed silently

### BE-047 · A function unsupported on the target engine is refused
- **Area:** `backend/sql.py::SqlCompiler._call`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** compile a `ROUND` control for sqlite
- **Expected:** "sqlite cannot run ROUND" with the no-substitution remedy
- **Why:** the refusal path is the promise, and `ROUND` is the only function that exercises it

### BE-048 · A function needing a capability the engine lacks is refused
- **Area:** `backend/sql.py::SqlCompiler._call`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a dialect without `pushdown.regex`
- **Steps:** compile an `ISNUMBER` control
- **Expected:** "…cannot run ISNUMBER: it needs pushdown.regex"
- **Why:** the per-function capability gate, separate from the per-plan one

### BE-049 · Aggregates bypass the catalogue
- **Area:** `backend/sql.py::_AGGREGATES`, `SqlCompiler._call`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** compile a row expression containing `COUNT(x)`, `SUM(x)`, `MIN(x)`, `MAX(x)`, `MEDIAN(x)`
- **Expected:** consistent treatment
- **Why:** `_AGGREGATES` holds COUNT, SUM, AVG, STDDEV and APPROX_COUNT_DISTINCT. `MIN` and `MAX` are missing, so they route to the *scalar* catalogue entries and render as `LEAST(x)`/`GREATEST(x)` with one argument; `MEDIAN` is missing from both and is refused. The parser's `AGGREGATES` set lists all seven — three lists, three answers

### BE-050 · Every operator in `INFIX` renders
- **Area:** `backend/sql.py::INFIX`, `SqlCompiler._operation`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** compile one expression per entry of `INFIX`
- **Expected:** a parenthesised infix rendering, with `/` and `%` routed through the dialect
- **Why:** fourteen operators, two of which "do not mean the same thing on every engine and are asked, rather than assumed, of the dialect"

### BE-051 · An infix operator with too few operands is a compiler defect
- **Area:** `backend/sql.py::SqlCompiler._operation`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a hand-built `Expr.operation("+", one_arg)`
- **Steps:** compile
- **Expected:** `PqlUnsupportedError` "…needs two operands", whose remedy says "This is a defect in the compiler rather than in the control"
- **Why:** an honest internal error rather than an emitted fragment — and the remedy is addressed to the right person

### BE-052 · Unary sign renders with no space
- **Area:** `backend/sql.py::SqlCompiler._operation`
- **Type:** regression
- **Priority:** P1
- **Precondition:** none
- **Steps:** compile `Expr.operation("-", column)`
- **Expected:** `(-"col")`
- **Why:** "joining a single operand with an infix separator yields the operand alone, which silently drops the sign — and every engine agrees on the wrong answer, so nothing notices"

### BE-053 · Every keyword operator renders
- **Area:** `backend/sql.py::SqlCompiler._operation`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** compile `NOT`, `IS NULL`, `IS NOT NULL`, `IN`, `NOT IN`, `BETWEEN`, `NOT BETWEEN`, `EXISTS`, `MATCHES`, `NOT MATCHES`
- **Expected:** correct SQL for each
- **Why:** ten branches and a fall-through that refuses everything else

### BE-054 · Every operator the lowerer can emit has a SQL branch
- **Area:** `backend/sql.py::SqlCompiler._operation`, `ir/lower.py::Lowerer._expression`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** enumerate every operator string the lowerer can produce and compile one expression for each
- **Expected:** no "has no SQL form" refusals for anything the grammar accepts
- **Why:** the lowerer passes operator strings straight through from the AST, so `LIKE`, `ILIKE`, `NOT LIKE`, `NOT ILIKE`, `!=`, `HAS FORMAT` and `IS OF TYPE` all reach a compiler that has no branch for any of them

### BE-055 · `IN` over an empty list
- **Area:** `backend/sql.py::SqlCompiler.expression`
- **Type:** negative
- **Priority:** P2
- **Precondition:** an `Expr.values()` with no items
- **Steps:** compile
- **Expected:** a refusal
- **Why:** it renders `IN ()`, which every engine rejects at parse time — and the only way to produce it is an empty codelist, which nothing guards

### BE-056 · An unresolved codelist is refused, not guessed
- **Area:** `backend/sql.py::SqlCompiler._operation`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a plan carrying an `IN CODELIST` op
- **Steps:** compile
- **Expected:** "the codelist … has not been resolved"; and assert it does not `IndexError` when the op has fewer than two arguments
- **Why:** the branch reads `node.args[1].value` before checking anything

### BE-057 · A regex on a non-text operand is cast first
- **Area:** `backend/sql.py::SqlCompiler._regex`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a DATE column
- **Steps:** compile `MATCHES` on it for duckdb and execute
- **Expected:** the cast is emitted and the query binds
- **Why:** "without this, a perfectly ordinary 'the trade date looks like a date' control is a control that cannot run"

### BE-058 · `CompiledControl.is_complete` is false for a two-stage plan
- **Area:** `backend/sql.py::CompiledControl.is_complete`
- **Type:** contract
- **Priority:** P1
- **Precondition:** an `IS VALID 'lei'` plan
- **Steps:** compile and read `is_complete` and `residual_validators`
- **Expected:** False, with the pairs listed
- **Why:** "reporting a pass from an incomplete query is the failure the two-stage design exists to prevent, and carrying the fact on the compiled artefact — rather than expecting every call site to remember — is what makes it hard to do by accident"

### BE-059 · The lower-bound caveat is attached regardless of the verdict
- **Area:** `backend/sql.py::CompiledControl.is_complete`, the execution path
- **Type:** regression
- **Priority:** P1
- **Precondition:** a two-stage control whose verdict would be `fail`
- **Steps:** run it and inspect the evidence record
- **Expected:** the caveat is present
- **Why:** QA finding Q-10 — "the IS VALID lower-bound caveat is attached only when the verdict would be pass, so understated counts are recorded as completed measurements with no caveat"

### BE-060 · `CompiledControl.to_dict` is serialisable and complete
- **Area:** `backend/sql.py::CompiledControl.to_dict`
- **Type:** contract
- **Priority:** P2
- **Precondition:** every corpus plan
- **Steps:** serialise each compiled control
- **Expected:** valid JSON carrying the plan id, the dialect, both queries, the metric names, the parameters, the residuals and `is_complete`
- **Why:** this is what the API returns and what a DBA reads before granting access

### BE-061 · `prama control compile` reports refusals rather than crashing
- **Area:** `cli/control.py::ControlCompileCommand.run`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a file mixing runnable and unrunnable controls
- **Steps:** `prama control compile suite.pql --dialect sqlite`
- **Expected:** SQL for the runnable ones, a `-- refused:` comment and remedy for the rest, and a count at the end
- **Why:** "a refusal is information, not a crash: it is the engine saying which control it cannot run, before anything is scheduled against it"

### BE-062 · `prama control compile` exits non-zero when nothing can run
- **Area:** `cli/control.py::ControlCompileCommand.run`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a file every control of which is refused
- **Steps:** run it and check the exit code
- **Expected:** a non-zero exit
- **Why:** the command always returns `EXIT_OK`, so a CI step that compiles an estate for its target engine passes while compiling nothing

## 17 · The reference interpreter — `backend/reference.py`

### BE-063 · Kleene AND, OR and NOT, exhaustively
- **Area:** `backend/reference.py::_and`, `_or`, `_not`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** evaluate all nine combinations of {true, false, unknown} for AND and OR, and all three for NOT
- **Expected:** false dominates AND, true dominates OR, unknown survives both, and NOT of unknown is unknown
- **Why:** "Python's `and` and `or` are two-valued and its `None` is falsy; using them would quietly turn every unknown into a false and lose exactly the distinction the language is built around"

### BE-064 · Kleene logic matches every SQL engine
- **Area:** `backend/reference.py::_and`, `_or`, `_not`, `backend/sql.py`
- **Type:** contract
- **Priority:** P1
- **Precondition:** rows with nulls
- **Steps:** run `SATISFIES a AND b`, `a OR b`, `NOT a` over rows covering all nine truth combinations, on all three engines and the reference
- **Expected:** identical violation counts
- **Why:** four independent implementations of three-valued logic, and the corpus has no case that puts an unknown on both sides of a connective

### BE-065 · A comparison with an unknown operand is unknown, never false
- **Area:** `backend/reference.py::_compare`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a null column
- **Steps:** evaluate `notional > 0` on a null row
- **Expected:** UNKNOWN
- **Why:** "this is the whole reason a null-heavy column silently passes a naive rule: `notional > 0` is not false for a null, it is unknown, and treating the two the same is how the mistake gets made"

### BE-066 · An incomparable pair is unknown, not an arbitrary ordering
- **Area:** `backend/reference.py::_compare`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a text column compared with a number
- **Steps:** evaluate it
- **Expected:** UNKNOWN
- **Why:** "the type checker refuses this at authoring time; reaching here means it was not checked, and unknown is the honest answer" — and `SATISFIES` conditions are never type-checked, so this path is live

### BE-067 · An unknown comparison operator raises rather than returning unknown
- **Area:** `backend/reference.py::_compare`
- **Type:** negative
- **Priority:** P1
- **Precondition:** an `Expr.operation("!=", a, b)` — what the Excel parser produces
- **Steps:** evaluate it over one row
- **Expected:** a typed refusal, or the comparison
- **Why:** the dict lookup raises `KeyError`, and only `TypeError` is caught — so a bad operator crashes the interpreter mid-row instead of being refused, and the same is true for `LIKE`, `ILIKE`, `HAS FORMAT` and `IS OF TYPE`

### BE-068 · `x = y` between a number and a numeric string
- **Area:** `backend/reference.py::_compare`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a row where a text column holds `'1'` and a numeric column holds `1`
- **Steps:** evaluate `a = b` on each engine and the reference
- **Expected:** agreement
- **Why:** Python returns False, PostgreSQL raises a type error, SQLite compares by storage class and DuckDB coerces — four answers, and only the type checker stands between them

### BE-069 · `IN` with a NULL in the list
- **Area:** `backend/reference.py::_membership`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** evaluate `x IN (1, 2, NULL)` and `x NOT IN (1, 2, NULL)` for x = 1 and x = 3, on every engine and the reference
- **Expected:** `IN` is true for 1 and unknown for 3; `NOT IN` is false for 1 and **unknown** for 3
- **Why:** the docstring calls it "the part everybody forgets… the classic SQL bug, and an engine that got it right while the interpreter got it wrong would show up as a conformance failure — which is the point". The corpus has no such case

### BE-070 · `IN` with an unknown subject
- **Area:** `backend/reference.py::_membership`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a null column
- **Steps:** evaluate `NULL IN ('a')` and `NULL NOT IN ('a')`
- **Expected:** UNKNOWN for both
- **Why:** the early return is what makes the default policy count a null as a violation for a codelist control

### BE-071 · `BETWEEN` is inclusive and three-valued
- **Area:** `backend/reference.py::ReferenceEvaluator._operation`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** evaluate `x BETWEEN 0 AND 1000` for x = 0, 1000, -1, 1001 and NULL, and `NOT BETWEEN` for each
- **Expected:** inclusive at both bounds, unknown for the null, and `NOT BETWEEN` the Kleene negation
- **Why:** the corpus has the boundary case; it has no `NOT BETWEEN` case and no null case for it

### BE-072 · `MATCHES` uses search, not fullmatch
- **Area:** `backend/reference.py::ReferenceEvaluator._matches`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** evaluate `MATCHES /A/` against `'BAB'` on every engine and the reference
- **Expected:** true everywhere — PostgreSQL's `~` and DuckDB's `regexp_matches` are also unanchored
- **Why:** an unanchored pattern is what most people write, and a fullmatch on one side would make a shape check pass for a value with a prefix

### BE-073 · `MATCHES` against a non-string value
- **Area:** `backend/reference.py::ReferenceEvaluator._matches`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a numeric and a decimal column
- **Steps:** evaluate `MATCHES /^[0-9.]+$/` on `1.10` in each engine and in the reference
- **Expected:** agreement
- **Why:** the reference does `str(value)` and the compiler emits `CAST(x AS VARCHAR)`; Python renders a `Decimal('1.10')` as `1.10` and a float as `1.1`, and the engines differ again — the cast and the stringification are two different functions

### BE-074 · The pattern cache is unbounded
- **Area:** `backend/reference.py::ReferenceEvaluator._patterns`
- **Type:** performance
- **Priority:** P3
- **Precondition:** a plan whose pattern is built per row
- **Steps:** evaluate over 1,000,000 rows
- **Expected:** bounded memory
- **Why:** the cache is keyed on the pattern text with no eviction; patterns are literals today, so this is a latent rather than live problem — assert the assumption

### BE-075 · A catastrophic pattern
- **Area:** `backend/reference.py::ReferenceEvaluator._matches`
- **Type:** performance
- **Priority:** P2
- **Precondition:** a control with `MATCHES /(a+)+b/` and a row of 40 `a`s
- **Steps:** evaluate
- **Expected:** it completes, or the pattern is refused
- **Why:** Python's `re` backtracks; RE2 (DuckDB) does not; PostgreSQL does. A control an author writes becomes a denial of service against the interpreter, which also runs the streaming and file paths

### BE-076 · Arithmetic with an unknown operand is unknown
- **Area:** `backend/reference.py::_arithmetic`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a null column
- **Steps:** evaluate `a + b`, `a - b`, `a * b`, `a / b`, `a % b` with one operand null
- **Expected:** UNKNOWN in every case
- **Why:** SQL propagates NULL through arithmetic, and the early return is what matches it

### BE-077 · Division and modulo by zero are unknown
- **Area:** `backend/reference.py::_arithmetic`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** evaluate `a / 0` and `a % 0`
- **Expected:** UNKNOWN — "an error would abort a control over one bad row; zero would silently change the answer"
- **Why:** PostgreSQL *does* raise on division by zero and aborts the query, so this is a documented divergence rather than agreement — assert which it is

### BE-078 · Arithmetic on a non-numeric value crashes
- **Area:** `backend/reference.py::_arithmetic`
- **Type:** negative
- **Priority:** P1
- **Precondition:** two text columns
- **Steps:** evaluate `SATISFIES a + b > 0` over a row where both are text
- **Expected:** UNKNOWN, matching `_compare`'s treatment of an incomparable pair
- **Why:** `float(values[0])` raises an uncaught `ValueError`, so the whole control dies on one row of dirty data — in the interpreter that is specifically the engine of last resort for feed files and mainframe extracts

### BE-079 · Arithmetic on a boolean silently coerces
- **Area:** `backend/reference.py::_arithmetic`, `pql/library.py::_number`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a boolean column
- **Steps:** evaluate `SATISFIES flag + 1 = 2` and `SATISFIES ABS(flag) = 1`
- **Expected:** one consistent answer
- **Why:** `float(True)` is 1.0 so the operator path treats a boolean as a number, while the catalogue's `_number` deliberately refuses one — "a boolean in an arithmetic position is a mistake worth surfacing, not a 1 worth guessing", enforced in one half of the interpreter

### BE-080 · Reference arithmetic is float, the catalogue is Decimal
- **Area:** `backend/reference.py::_arithmetic`, `pql/library.py::_number`
- **Type:** negative
- **Priority:** P1
- **Precondition:** monetary values
- **Steps:** evaluate `SATISFIES (a + b) = c` and `SATISFIES ROUND(a + b, 2) = c` over values where binary floating point is inexact
- **Expected:** the same answer from both
- **Why:** one interpreter with two arithmetic models; the library's own docstring says a float reconciliation "would manufacture exactly the small discrepancies it exists to detect"

### BE-081 · A unary sign on an unknown or non-numeric value
- **Area:** `backend/reference.py::_sign`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** evaluate `-a` where `a` is NULL and where it is text
- **Expected:** UNKNOWN in both cases
- **Why:** the only operator in the interpreter that checks the operand's type before acting

### BE-082 · A strict function with an unknown argument is unknown
- **Area:** `backend/reference.py::ReferenceEvaluator._call`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** evaluate every strict function with one unknown argument
- **Expected:** UNKNOWN in every case
- **Why:** "returning 0 for LENGTH(NULL) would make a length check silently pass on every null"

### BE-083 · The four non-strict functions answer rather than propagate
- **Area:** `backend/reference.py::ReferenceEvaluator._call`, `pql/library.py`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** evaluate `ISBLANK(NULL)`, `IF(TRUE, 1, NULL)`, `COALESCE(NULL, 1)`, `IFBLANK(NULL, 1)`, `ISNUMBER(NULL)`
- **Expected:** True, 1, 1, 1, False
- **Why:** "the exceptions declare themselves" — and there are five of them, not four as the field comment says

### BE-084 · An unrecognised function is unknown, not an error
- **Area:** `backend/reference.py::ReferenceEvaluator._call`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a plan containing `COUNT(x)` as a row expression
- **Steps:** evaluate
- **Expected:** documented — the reference returns UNKNOWN while the SQL compiler renders a real aggregate
- **Why:** the comment says "the compiler refuses these now, so reaching here means an aggregate or a drift" — an aggregate in a row expression is exactly the case where the two paths silently disagree

### BE-085 · `UNSET` is converted to UNKNOWN on the way out
- **Area:** `backend/reference.py::ReferenceEvaluator._call`, `pql/functions.UnknownValue`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** evaluate `MOD(5, 0)` and check that the result is `None`, not the `UNSET` singleton
- **Expected:** `None`; `UNSET` never escapes `_call`
- **Why:** `UNSET` has no truth value and raises `TypeError` if anything tests it; letting one escape into a Kleene operator would crash the run

### BE-086 · `UnknownValue` refuses to be a boolean
- **Area:** `pql/functions.py::UnknownValue.__bool__`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** evaluate `bool(UNSET)`
- **Expected:** `TypeError` whose message says "collapsing it to True or False here is how a null becomes a pass"
- **Why:** the loudest guard in the codebase, and its value is entirely in never being caught silently

### BE-087 · `UnknownValue` is a singleton
- **Area:** `pql/functions.py::UnknownValue.__new__`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** `UnknownValue() is UnknownValue() is UNSET`
- **Expected:** True
- **Why:** every comparison against it is `is`, so a second instance would be invisible to all of them

### BE-088 · A violation is the negation of the predicate, with the policy applied
- **Area:** `backend/reference.py::ReferenceEvaluator.is_violation`
- **Type:** contract
- **Priority:** P1
- **Precondition:** rows that are true, false and unknown for the predicate
- **Steps:** evaluate under both policies
- **Expected:** false is always a violation; unknown follows the policy; true is a violation only when a residual fails
- **Why:** "this one line is the language's central decision, and the reason the interpreter exists: if the compiler expresses it differently, the two disagree here rather than in production"

### BE-089 · A screen pass is not a control pass for a two-stage plan
- **Area:** `backend/reference.py::ReferenceEvaluator.is_violation`, `fails_residual`
- **Type:** contract
- **Priority:** P1
- **Precondition:** the corpus row `AAAAAAAAAAAAAAAAAA00`
- **Steps:** run `IS VALID 'lei'` on the reference
- **Expected:** three violations — two from the screen and the fabricated LEI from the check characters
- **Why:** "every value has the right shape, and the shape was never the standard"

### BE-090 · `fails_residual` is shared with the streaming path
- **Area:** `backend/reference.py::ReferenceEvaluator.fails_residual`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a fabricated identifier
- **Steps:** run the same control in batch and in flight
- **Expected:** the same verdict
- **Why:** finding T3 — "a control that caught a fabricated identifier overnight passed it in flight… The alternative to sharing it is two copies of the rule, which is how they came to differ"

### BE-091 · A null value skips the residual
- **Area:** `backend/reference.py::ReferenceEvaluator.fails_residual`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a null in a two-stage column
- **Steps:** run the control under both policies
- **Expected:** the null is already a violation by the screen under the default policy, and the residual does not double-count it
- **Why:** `if value is None: continue` — a null is not an invalid identifier, it is a missing one, and the two are different findings

### BE-092 · A residual naming an unknown validator
- **Area:** `backend/reference.py::ReferenceEvaluator.fails_residual`, `classify/validators.ValidatorRegistry.get`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a plan carrying a residual for a validator no longer registered
- **Steps:** run it
- **Expected:** a typed refusal naming the validator
- **Why:** `VALIDATORS.get` raises a `ValidationError` from inside a per-row loop — a plan replayed after a plugin was removed dies in the middle of the scan

### BE-093 · A filter keeps a row only when it is definitely true
- **Area:** `backend/reference.py::ReferenceEvaluator._passes_filter`
- **Type:** contract
- **Priority:** P1
- **Precondition:** rows where the filter is unknown
- **Steps:** run a filtered control on the reference and on each engine
- **Expected:** the unknown rows are excluded from both the numerator and the denominator, identically
- **Why:** "a row we cannot tell is in scope is not in scope, and counting it would put rows in the denominator that the engine never looked at" — the *opposite* rule from the assertion case, in the same file

### BE-094 · `COUNT_DISTINCT` skips keys with any unknown part
- **Area:** `backend/reference.py::ReferenceEvaluator._distinct`
- **Type:** contract
- **Priority:** P1
- **Precondition:** rows with a null in one part of a composite key
- **Steps:** run a unique-key control on every engine and the reference
- **Expected:** the same distinct count, and the same `null_key_rows`
- **Why:** "matching SQL's COUNT(DISTINCT) is not deference — it is the only way the count means the same thing here as it does on the three engines"

### BE-095 · A distinct count over an unhashable value
- **Area:** `backend/reference.py::ReferenceEvaluator._distinct`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a row whose column holds a list (a JSON array from a REST source)
- **Steps:** run a unique-key control over it
- **Expected:** a typed refusal, not a `TypeError` from `seen.add`
- **Why:** the reference interpreter is the engine for sources with no query engine, which is exactly where a column holds a list

### BE-096 · `APPROX_COUNT_DISTINCT` is silently zero
- **Area:** `backend/reference.py::ReferenceEvaluator._metrics`, `_aggregate`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a plan with an approximate-distinct metric
- **Steps:** run it on the reference
- **Expected:** an approximation, or a refusal
- **Why:** `_metrics` handles COUNT, COUNT_IF and COUNT_DISTINCT and sends everything else to `_aggregate`, whose dict has no entry for it — so it returns `0.0`, which is a metric on the evidence record that is simply wrong

### BE-097 · `SUM`, `MIN`, `MAX` and `AVG` over no numeric values
- **Area:** `backend/reference.py::ReferenceEvaluator._aggregate`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an empty scope, and a scope where every value is null
- **Steps:** evaluate each aggregate
- **Expected:** agreement with SQL, where `SUM` of no rows is NULL and `MIN` of no rows is NULL
- **Why:** the reference returns `0.0` for all four, and a sum of zero and a sum of nothing are different facts

### BE-098 · A missing related dataset is raised, never answered
- **Area:** `backend/reference.py::MissingRelatedDataset`, `_exists`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a referential control with no `related` supplied
- **Steps:** run it on the reference
- **Expected:** `MissingRelatedDataset`, naming the dataset and how to supply it
- **Why:** "assuming the value is present reports green on an estate nobody checked, and assuming it is absent reports every row as an orphan"

### BE-099 · The related value set is built once
- **Area:** `backend/reference.py::ReferenceEvaluator._value_sets`
- **Type:** performance
- **Priority:** P2
- **Precondition:** a 100,000-row target dataset
- **Steps:** run a referential control over 100,000 source rows
- **Expected:** one pass over the target, not one per source row
- **Why:** the memo is keyed on `(dataset, column)`; without it the interpreter is quadratic on exactly the control that reaches two datasets

### BE-100 · `run` materialises every row
- **Area:** `backend/reference.py::ReferenceEvaluator.run`
- **Type:** performance
- **Priority:** P2
- **Precondition:** a 10,000,000-row feed file
- **Steps:** run a control through the reference interpreter
- **Expected:** bounded memory, or a documented limit
- **Why:** `[dict(r) for r in rows]` copies the whole input into memory before anything is evaluated, in the path described as "the engine of last resort" for mainframe extracts

### BE-101 · The reference produces no evidence samples
- **Area:** `backend/reference.py::ReferenceEvaluator.run`, `backend/execute.py::judge`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a control with violations and `EVIDENCE samples (10)`
- **Steps:** run it on the reference and read `ControlResult.samples`
- **Expected:** up to ten violating rows
- **Why:** `judge` never sets `samples`, so every control run through the interpreter — which is every control over a source with no query engine — produces a finding with no evidence rows behind it

### BE-102 · The reference shares nothing with the compiler but the IR
- **Area:** `backend/reference.py` imports
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** import-scan the module for `backend.sql` and `backend.dialect`
- **Expected:** neither appears
- **Why:** "agreement between implementations that share a compiler is agreement about the compiler, not about the meaning". It does import `pql.library`, which the compiler also uses to render function SQL — assert that sharing the *catalogue* is intended while sharing the *lowering* is not

## 18 · Judgement — `backend/execute.py`

### BE-103 · Judgement is engine-independent
- **Area:** `backend/execute.py::judge`
- **Type:** contract
- **Priority:** P1
- **Precondition:** the same metric values from four sources
- **Steps:** judge them with the same plan
- **Expected:** the same verdict
- **Why:** "the engines compute numbers; this decides what the numbers mean, once, so two backends cannot disagree about a threshold even if they disagree about everything else"

### BE-104 · A duplicate count is derived, not asked for
- **Area:** `backend/execute.py::_derive`
- **Type:** functional
- **Priority:** P1
- **Precondition:** the corpus, where `(account_id, instrument_id)` repeats once
- **Steps:** judge the unique-key case
- **Expected:** `duplicate_rows == 1`, `violating_rows == 1` — not 2
- **Why:** the corpus case says exactly this: "the violating count is 1 and not 2"

### BE-105 · Null keys are counted as themselves, not as duplicates
- **Area:** `backend/execute.py::_derive`
- **Type:** functional
- **Priority:** P1
- **Precondition:** rows with null key parts
- **Steps:** judge a unique-key control over them
- **Expected:** `violating_rows == duplicates + null_key_rows`, with the two reported separately
- **Why:** "a null key identifies nothing, so it cannot be one row per anything; it counts once, as itself"

### BE-106 · A functional-dependency violation is counted in determinants
- **Area:** `backend/execute.py::_derive`, `_dependency_verdict`
- **Type:** functional
- **Priority:** P1
- **Precondition:** the corpus, where `ccy` carries two entities
- **Steps:** judge
- **Expected:** `violating_rows == pairs - determinants`, a count of determinants
- **Why:** "'four rows disagree' and 'one account has two entities' are different findings and only the second names the problem"

### BE-107 · A derived metric with a missing input is left alone
- **Area:** `backend/execute.py::_derive`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** metrics missing `distinct_keys`
- **Steps:** judge a unique-key plan
- **Expected:** no `violating_rows` is invented; the verdict is INDETERMINATE
- **Why:** deriving from a missing input would produce a number that looks computed

### BE-108 · An empty scope is indeterminate for a unique key and a dependency
- **Area:** `backend/execute.py::_distinctness_verdict`, `_dependency_verdict`
- **Type:** functional
- **Priority:** P1
- **Precondition:** an empty table
- **Steps:** judge both kinds
- **Expected:** INDETERMINATE in both cases
- **Why:** "nothing to be unique. Not a pass: an empty scope has demonstrated nothing, and reporting green is how a broken feed goes unnoticed"

### BE-109 · An empty table fails a row-count minimum
- **Area:** `backend/execute.py::_row_count_verdict`
- **Type:** functional
- **Priority:** P1
- **Precondition:** an empty table
- **Steps:** judge `HAS ROW COUNT BETWEEN 1 AND 8`
- **Expected:** FAIL, not INDETERMINATE
- **Why:** the comment in `Threshold.evaluate` says row counts deliberately do not go through the empty-scope guard, "which `_row_count_verdict` decides separately"

### BE-110 · A row count with no metric is indeterminate
- **Area:** `backend/execute.py::_row_count_verdict`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** metrics with no `scanned_rows`
- **Steps:** judge
- **Expected:** INDETERMINATE
- **Why:** the guard is the only thing between a missing metric and a `KeyError` in the judgement path

### BE-111 · A row count exactly on each bound
- **Area:** `backend/execute.py::_row_count_verdict`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** tables of 0, 1, 8 and 9 rows
- **Steps:** judge `BETWEEN 1 AND 8`
- **Expected:** fail, pass, pass, fail
- **Why:** inclusive bounds, asserted at both ends

### BE-112 · Every assertion kind reaches its own verdict function
- **Area:** `backend/execute.py::_verdict`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** judge one plan of each of the six assertion kinds
- **Expected:** each reaches a verdict rule that can produce PASS and FAIL
- **Why:** `_verdict` names three kinds and sends the other three to `threshold.evaluate` — and `freshness` has no metric for it to read, so it can only ever be INDETERMINATE

### BE-113 · `comparable()` excludes engine, samples and timings
- **Area:** `backend/execute.py::ControlResult.comparable`
- **Type:** contract
- **Priority:** P1
- **Precondition:** two results from different engines
- **Steps:** compare
- **Expected:** the comparison covers only the verdict, the metrics and the sorted segments
- **Why:** "a conformance failure should mean the engines disagree about the *data*, not that one of them returned its rows in a different order"

### BE-114 · Metrics are compared at nine decimal places
- **Area:** `backend/execute.py::_round`
- **Type:** contract
- **Priority:** P1
- **Precondition:** two engines whose rate differs in the last bits
- **Steps:** compare the results
- **Expected:** they agree
- **Why:** "a conformance suite that compared raw doubles would fail on arithmetic rather than on meaning, and would teach everyone to ignore it"

### BE-115 · `_round` on a non-numeric metric
- **Area:** `backend/execute.py::_round`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a driver returning a `Decimal` or `None` for a metric
- **Steps:** build a result and call `comparable()`
- **Expected:** a defined answer, not a `TypeError`
- **Why:** `float(None)` raises, and PostgreSQL returns a `Decimal` for `SUM` — the metric dict is typed `dict[str, float]` and populated from a driver

## 19 · Fusion — `backend/fuse.py`

### BE-116 · Controls sharing a scope are grouped
- **Area:** `backend/fuse.py::Fuser.group`, `_empty_group`
- **Type:** functional
- **Priority:** P1
- **Precondition:** twenty controls over one dataset with one filter
- **Steps:** group them
- **Expected:** one group of twenty
- **Why:** "twenty controls become one query with twenty-one columns" — the whole reason the module exists

### BE-117 · A different filter, binding, dataset or segmentation splits the group
- **Area:** `backend/fuse.py::Fuser.group`, `ScanGroup.key`
- **Type:** functional
- **Priority:** P1
- **Precondition:** controls differing in each of the four key fields
- **Steps:** group them
- **Expected:** four groups
- **Why:** "what decides whether two controls can share a pass is narrow and checkable"

### BE-118 · Thresholds and severities do not split a group
- **Area:** `backend/fuse.py::Fuser.group`
- **Type:** functional
- **Priority:** P1
- **Precondition:** two controls identical but for their thresholds
- **Steps:** group them
- **Expected:** one group
- **Why:** "those are applied afterwards, to numbers the single query already produced"

### BE-119 · Two filters that compile to the same SQL share a group
- **Area:** `backend/fuse.py::Fuser._empty_group`
- **Type:** functional
- **Priority:** P2
- **Precondition:** two filters written differently that render identically
- **Steps:** group them
- **Expected:** one group
- **Why:** "grouping on the tree would miss that" — the comment says the compiled text is the key precisely for this

### BE-120 · Grouping order is stable
- **Area:** `backend/fuse.py::Fuser.group`
- **Type:** contract
- **Priority:** P2
- **Precondition:** the same plan list twice
- **Steps:** group and fuse
- **Expected:** byte-identical SQL
- **Why:** "a diff of generated SQL stays readable" — and a DBA reviews that diff

### BE-121 · Identical metric expressions are emitted once
- **Area:** `backend/fuse.py::Fuser.fuse`
- **Type:** functional
- **Priority:** P1
- **Precondition:** twenty controls over one scope, each computing `scanned_rows`
- **Steps:** fuse
- **Expected:** one `COUNT(*)` column, with `columns` mapping that alias to all twenty owners
- **Why:** "an engine asked for the same aggregate fifty times will compute it fifty times"

### BE-122 · `unpack` splits one answer back into one result per control
- **Area:** `backend/fuse.py::FusedQuery.unpack`, `_metrics_for`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a fused query over five controls
- **Steps:** execute and unpack
- **Expected:** five results, each with only its own metrics and its own verdict
- **Why:** a shared alias owned by several controls is the part that can be mis-attributed

### BE-123 · `unpack` over an empty result set
- **Area:** `backend/fuse.py::FusedQuery.unpack`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a query returning no rows
- **Steps:** unpack
- **Expected:** one result per control, each INDETERMINATE — not an `IndexError`
- **Why:** `rows[0] if rows else {}` produces empty metrics, which must reach the missing-metric branch of the threshold

### BE-124 · A fused segmented query
- **Area:** `backend/fuse.py::FusedQuery._unpack_segmented`
- **Type:** functional
- **Priority:** P1
- **Precondition:** three controls segmented by the same column
- **Steps:** fuse, execute and unpack
- **Expected:** three results, each with the same segment keys and its own per-segment metrics
- **Why:** `row[c]` raises a `KeyError` if a segment column is missing from the projection, in the middle of unpacking

### BE-125 · One unsupported control stops the whole group
- **Area:** `backend/fuse.py::Fuser.fuse`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a group of twenty controls, one of which needs a capability the engine lacks
- **Steps:** fuse
- **Expected:** the behaviour the remedy promises
- **Why:** the remedy says "one control that cannot be expressed must not stop the rest — but it must not be silently dropped either", and the code raises on the first one, stopping all twenty. The message describes a design the implementation does not have

### BE-126 · A fused query produces no evidence samples
- **Area:** `backend/fuse.py::Fuser.fuse`
- **Type:** negative
- **Priority:** P2
- **Precondition:** controls with `EVIDENCE samples`
- **Steps:** fuse and run
- **Expected:** samples for the failing controls
- **Why:** `fuse` emits only metric columns; `--fuse` therefore trades every sample row in the group for one scan, which is a decision nobody is told about

### BE-127 · Cost is counted in scans, not controls
- **Area:** `backend/fuse.py::Fuser.cost`, `RunCost.render`
- **Type:** functional
- **Priority:** P1
- **Precondition:** twenty controls in three groups
- **Steps:** `cost()` and render
- **Expected:** "20 control(s) in 3 scan(s) — 17 fewer passes over the data than running them separately"
- **Why:** "a scan is what the source pays for and the control count is what a dashboard likes"

### BE-128 · `rows_read` is None when any dataset's size is unknown
- **Area:** `backend/fuse.py::RunCost.rows_read`
- **Type:** functional
- **Priority:** P1
- **Precondition:** three groups, one over an unmeasured dataset
- **Steps:** read `rows_read`
- **Expected:** None, and the rendered sentence omits the row count
- **Why:** "a total that quietly omits the datasets nobody has measured looks precise and is short by however much they hold"

### BE-129 · Two groups with the same description collide
- **Area:** `backend/fuse.py::Fuser.cost`, `RunCost.rows_per_scan`
- **Type:** negative
- **Priority:** P2
- **Precondition:** two groups over the same dataset and filter, differing only in binding
- **Steps:** `cost()` and inspect `rows_per_scan`
- **Expected:** two entries
- **Why:** the dict is keyed on `g.describe()`, which does not mention the binding — so one entry is lost and `rows_read` under-counts by a whole scan while `scans` still says two

### BE-130 · `cost` with no plans
- **Area:** `backend/fuse.py::RunCost.controls_per_scan`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** an empty plan list
- **Steps:** `cost([])` and render
- **Expected:** `0.0` and a sentence, not a `ZeroDivisionError`
- **Why:** `prama control compile --fuse` on a file where every control failed to lower reaches exactly this

## 20 · Conformance, the corpus and the generator — `backend/conformance.py`, `corpus.py`, `generate.py`

### BE-131 · The corpus runs on every engine and they agree
- **Area:** `backend/conformance.py::ConformanceRun.compare`
- **Type:** contract
- **Priority:** P1
- **Precondition:** duckdb and sqlite in process, postgresql where available, and the reference
- **Steps:** run all 23 cases on all four
- **Expected:** no disagreements
- **Why:** "the claim Wave 4 makes is that a control written once means the same thing wherever it runs. This is where that claim is either true or found out"

### BE-132 · A refusal is a conforming outcome; a wrong answer is not
- **Area:** `backend/conformance.py::ConformanceRun.run_case`
- **Type:** contract
- **Priority:** P1
- **Precondition:** the regex case and sqlite without a REGEXP hook
- **Steps:** run it
- **Expected:** status `refused`, and the run still conforms
- **Why:** "that distinction is the entire value of the exercise"

### BE-133 · A driver error is a conformance failure
- **Area:** `backend/conformance.py::ConformanceRun.run_case`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a case whose SQL will not execute
- **Steps:** run it
- **Expected:** status `failed`, reported as a disagreement with the exception type and message
- **Why:** a query the compiler emitted and the engine rejected is the compiler being wrong, not the engine

### BE-134 · An engine that refuses everything is filtered out before comparison
- **Area:** `backend/conformance.py::ConformanceRun.compare`, `summarise`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a compiler change that makes one engine refuse every case
- **Steps:** run `summarise` and read `engines_that_ran` and `cases_compared`
- **Expected:** the report shows one fewer engine and the drop in comparisons
- **Why:** finding T7 — "a compiler change that made SQLite refuse everything left the gate green while it compared one SQL engine against the interpreter"

### BE-135 · A case answered by fewer than two engines is not "compared"
- **Area:** `backend/conformance.py::ConformanceRun.compare`, `summarise`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a case only the reference can run
- **Steps:** run `compare`
- **Expected:** it is not counted as agreement
- **Why:** `compare` builds a set of distinct answers and a single answer is trivially unanimous — `summarise` counts `cases_compared` but `compare` itself does not use it, so the disagreement list can be empty because nothing was compared

### BE-136 · A two-stage case declares what its screen must find
- **Area:** `backend/conformance.py::ConformanceRun._compare_two_stage`, `corpus.Case.screen_violations`
- **Type:** regression
- **Priority:** P1
- **Precondition:** the `semantic_type_two_stage` case
- **Steps:** run it and then neuter the screen so DuckDB finds nothing
- **Expected:** the neutered version fails the gate
- **Why:** finding T4 — "'fewer' includes **none**: a screen that rejects nothing is excused unconditionally, so a neutered predicate and a working one produce the same green report"

### BE-137 · A two-stage case with no declared screen count is itself a disagreement
- **Area:** `backend/conformance.py::ConformanceRun._compare_two_stage`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a two-stage case added without `screen_violations`
- **Steps:** run the suite
- **Expected:** a disagreement telling the corpus author to declare it
- **Why:** the gate closes against its own future editors, which is the only kind of gate that stays closed

### BE-138 · A screen may not find more than the exact check
- **Area:** `backend/conformance.py::ConformanceRun._compare_two_stage`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a declared `screen_violations` above the reference's count
- **Steps:** run
- **Expected:** a disagreement saying "a screen is a necessary condition and cannot reject more than the standard does"
- **Why:** "an engine may never find more, because that would mean the screen rejected a value the standard accepts, and the control would be reporting a violation on good reference data"

### BE-139 · Two-stage comparison is skipped when the reference did not run
- **Area:** `backend/conformance.py::ConformanceRun._compare_two_stage`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a run with no corpus rows supplied
- **Steps:** run the two-stage case
- **Expected:** a failure, not silence
- **Why:** the method returns `[]` when the reference is absent, so every two-stage case — the thesis of the product — is excused whenever the interpreter is not among the runners

### BE-140 · `Case.requires` is declared and never consulted
- **Area:** `backend/corpus.py::Case.requires`, `backend/conformance.py`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** grep `conformance.py` for `case.requires`
- **Expected:** it is used to decide which engines may legitimately refuse a case
- **Why:** the field says "capabilities without which an engine may legitimately refuse this case" and nothing reads it — so a refusal is accepted from any engine for any case, including one it should have been able to run

### BE-141 · `DUPLICATE_KEY` is declared and never used
- **Area:** `backend/corpus.py::DUPLICATE_KEY`
- **Type:** documentation
- **Priority:** P3
- **Precondition:** none
- **Steps:** grep for it
- **Expected:** the unique-key case is built from it, or it is deleted
- **Why:** the constant carries the reasoning ("fails by exactly one row, which is the count the engines must agree on") and the case restates the columns by hand — two statements of one fact, which is how they drift

### BE-142 · Every corpus row is annotated with what it catches
- **Area:** `backend/corpus.py::ROW_NOTES`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** compare `ROWS` against `ROW_NOTES`
- **Expected:** each row either has a note or is provably ordinary
- **Why:** "so a future edit cannot quietly remove the case that mattered" — rows 1, 2 and 7 carry no note, so nothing stops them being changed

### BE-143 · The corpus covers no function except LENGTH
- **Area:** `backend/corpus.py::CASES`, `pql/library.py`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** list the functions exercised by the 23 cases
- **Expected:** every catalogue function appears in at least one end-to-end case
- **Why:** 24 of the 25 shipped functions appear in no conformance case at all. `test_function_catalogue` executes each against its reference in isolation, over a fixed sample table that contains **no NULL** — so no function is tested inside a control, inside a violation count, or against the unknown policy

### BE-144 · The corpus has no `IN CODELIST` case
- **Area:** `backend/corpus.py::CASES`, `backend/conformance.py::ConformanceRun.plan_for`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** add an `IN CODELIST iso4217` case and run it
- **Expected:** it lowers and runs on every engine
- **Why:** `plan_for` builds a bare `Lowerer()` with no codelists, so a codelist case cannot be added without changing the runner — the one language feature whose values are frozen into the plan has no portability coverage at all

### BE-145 · The corpus has no `REFERENCES` case
- **Area:** `backend/corpus.py::CASES`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a second corpus table
- **Steps:** add a referential case and run it on all four
- **Expected:** the same orphan count everywhere
- **Why:** the correlated-EXISTS construction, the outer-column qualification and the `MissingRelatedDataset` refusal are three of the most failure-prone pieces in the compiler, and none is in the gate

### BE-146 · The corpus has no parameter case
- **Area:** `backend/corpus.py::CASES`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** add a `$business_date` case and run it
- **Expected:** the named parameter binds on every driver
- **Why:** `:name` binding differs between `sqlite3`, `duckdb` and `psycopg`, and nothing in the gate ever binds one

### BE-147 · The corpus has no empty-scope case
- **Area:** `backend/corpus.py::CASES`
- **Type:** negative
- **Priority:** P1
- **Precondition:** an empty corpus table
- **Steps:** run every case over it
- **Expected:** INDETERMINATE everywhere except the row-count cases
- **Why:** Q-09 was an empty-scope defect and the fix has no conformance case, so the same regression can return on any one engine

### BE-148 · The corpus has no NULL-in-`IN`-list case
- **Area:** `backend/corpus.py::CASES`, `backend/reference.py::_membership`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** add `CHECK corpus.ccy NOT IN ('XXX', NULL)` and run it
- **Expected:** agreement
- **Why:** the interpreter's own docstring calls this "the classic SQL bug" and says "an engine that got it right while the interpreter got it wrong would show up as a conformance failure — which is the point" — and no case puts it there

### BE-149 · The corpus has no arithmetic case beyond `/` and `%`
- **Area:** `backend/corpus.py::CASES`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** add cases for `+`, `-`, `*` and `||` over nulls and negatives
- **Expected:** agreement between the four paths
- **Why:** `/` and `%` were added only after finding C4, and "the corpus had no arithmetic case at all, so the gate never saw it" — the other four operators are still in that position

### BE-150 · The corpus has no freshness, no `IS UNIQUE`, no Excel and no `HAS FORMAT` case
- **Area:** `backend/corpus.py::CASES`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** attempt to add one case for each
- **Expected:** each lowers, compiles and runs
- **Why:** all four are grammar the language accepts and none of them has any end-to-end coverage — which is why `IS UNIQUE` lowering to a null check, `HAS FORMAT` having no SQL form, and Excel's `<>` producing an uncompilable operator are all invisible today

### BE-151 · The corpus has no quoting or identifier-edge case
- **Area:** `backend/corpus.py::COLUMNS`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** add a column whose name is a reserved word, one with a space, one with an embedded quote, and one with a non-ASCII character
- **Expected:** the compiled SQL quotes them correctly on all three engines
- **Why:** `quote` is the only escaping in the SQL path and every corpus column is a plain lower-case ASCII identifier

### BE-152 · The DDL is accepted by every engine
- **Area:** `backend/corpus.py::create_table`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** execute the generated DDL on all three engines
- **Expected:** it is accepted, with `DOUBLE PRECISION` mapped to `REAL` on sqlite
- **Why:** the fixture asks the dialect for the type name rather than branching on the engine, which is the same rule the compiler follows

### BE-153 · The insert placeholder per driver
- **Area:** `backend/corpus.py::insert_rows`, `example.py::insert_positions`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** generate the statement with `?` and with `$`
- **Expected:** `?` repeated for the first, `$1 … $9` for the second
- **Why:** three drivers, two placeholder styles, and a fixture that gets it wrong fails in a way that looks like a compiler bug

### BE-154 · A generated control is reproducible from its seed
- **Area:** `backend/generate.py::ControlGenerator.one`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** generate seed 42 twice, in two processes
- **Expected:** identical PQL
- **Why:** "a suite that reports 'some generated control disagreed' and cannot say which is worse than no suite, since nobody can act on it"

### BE-155 · Seed reproducibility across Python versions
- **Area:** `backend/generate.py::ControlGenerator`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** 3.13 and 3.14
- **Steps:** generate the same seed on both
- **Expected:** identical PQL, or a documented statement that seeds are only comparable within one interpreter version
- **Why:** the repository pins 3.13 and states the suite also passes on 3.14; `random.sample` and `randrange` are implementation details, and a repro from a bug report has to reproduce

### BE-156 · Every generated control parses and lowers
- **Area:** `backend/generate.py::ControlGenerator.many`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** generate 1,000 controls and parse, type-check and lower each
- **Expected:** no parse errors and no lowering failures
- **Why:** "generating nonsense and calling the resulting errors findings is the commonest way a fuzzer becomes noise nobody reads"

### BE-157 · Generated controls sometimes match and sometimes do not
- **Area:** `backend/generate.py::NUMBERS`, `TEXT_VALUES`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** run 250 generated controls and count the distinct verdicts
- **Expected:** a mixture of pass, fail and indeterminate
- **Why:** "a generator whose predicates never matched would compare three engines all returning zero" — the anti-vacuity guard the adversarial review found sound, and which must stay sound

### BE-158 · The generator covers a narrow slice of the language
- **Area:** `backend/generate.py::ControlGenerator._assertion`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** enumerate the constructs the generator can emit
- **Expected:** a stated list, and a stated exclusion list
- **Why:** it emits eight assertion shapes and never `MATCHES`, `IN CODELIST`, `IS VALID`, `REFERENCES`, `DETERMINES`, `SATISFIES EXCEL`, any function call, any arithmetic, any parameter or any multi-column segmentation — a fuzzer's coverage should be written down, not inferred

### BE-159 · A generated `TREAT UNKNOWN AS PASS` is emitted in the threshold position
- **Area:** `backend/generate.py::ControlGenerator._threshold`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** find a seed producing it and parse the result
- **Expected:** it parses — modifiers are order-independent — and the control has no threshold
- **Why:** the method is named `_threshold` and returns a clause that is not one, so a control carrying it is never given a tolerance; whether that is intended should be stated

### BE-160 · A generated `HAS LENGTH BETWEEN` on a text column is type-clean
- **Area:** `backend/generate.py::ControlGenerator._assertion`, `pql/types.py::_check_predicate`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a catalogue for the corpus
- **Steps:** type-check every generated control
- **Expected:** no findings
- **Why:** the generator emits length checks on textual columns, which is the shape that produces a spurious type error — the fuzzer never type-checks, so the defect is invisible to it

## 21 · The worked example — `backend/example.py`

### BE-161 · Every control in the shipped suite parses
- **Area:** `backend/example.py::SUITE`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `parse(SUITE)`
- **Expected:** one suite of seven controls
- **Why:** "the example in the document and the example that runs cannot drift apart, because they are the same text"

### BE-162 · Every control in the suite lowers and compiles on every engine
- **Area:** `backend/example.py::SUITE`
- **Type:** functional
- **Priority:** P1
- **Precondition:** the shipped codelists
- **Steps:** lower each control through `resolved` and compile for all three dialects
- **Expected:** SQL or a stated refusal for each
- **Why:** the suite uses `IN CODELIST`, `REFERENCES` and `DETERMINES`, none of which the conformance corpus exercises — this is their only coverage

### BE-163 · Each expectation is met exactly
- **Area:** `backend/example.py::EXPECTED`, `POSITIONS`, `ACCOUNTS`
- **Type:** functional
- **Priority:** P1
- **Precondition:** the example tables loaded
- **Steps:** run all seven controls and compare with `EXPECTED`
- **Expected:** six fail and one passes, each catching the fault its entry names
- **Why:** four planted faults, seven controls and an explicit statement of which catches which — the one place the product demonstrates detection end to end

### BE-164 · The row-count control passes
- **Area:** `backend/example.py::EXPECTED`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** eight rows, seven of them ACTIVE
- **Steps:** run `HAS ROW COUNT BETWEEN 1 AND 2000000 WHERE trade_status = 'ACTIVE'`
- **Expected:** pass
- **Why:** the one passing control, and the only proof that the suite is not simply failing everything

### BE-165 · One row fires two controls and the linter says so
- **Area:** `backend/example.py::EXPECTED`, `pql/lint.py::Linter._subsumed`
- **Type:** functional
- **Priority:** P2
- **Precondition:** the example suite
- **Steps:** lint it
- **Expected:** the `IS NOT NULL` and `BETWEEN` pair on `notional_amount` is reported as subsumed
- **Why:** the expectation text says so in prose — "one row fires two controls and the linter flags the pair as subsumed" — which makes it a claim, and both halves have to hold

### BE-166 · The example's unique key spans three columns including a date
- **Area:** `backend/example.py::SUITE`
- **Type:** functional
- **Priority:** P1
- **Precondition:** the example table
- **Steps:** run the key control on all three engines
- **Expected:** one duplicate, counted identically
- **Why:** a three-column key over a VARCHAR date is where the three `count_distinct` constructions differ most

### BE-167 · `NOT_YET_IMPLEMENTED` is honest
- **Area:** `backend/example.py::NOT_YET_IMPLEMENTED`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** attempt to parse each of the three declared-but-unbuilt constructs
- **Expected:** each is refused, and the refusal is comprehensible
- **Why:** `MONITOR`, `RECONCILE` and `DERIVES` are all keywords the lexer recognises, so they produce "expected a control and found 'MONITOR'" rather than "MONITOR is not implemented yet" — the module lists the gap and the language does not name it

### BE-168 · The declarations map one-to-one onto the controls
- **Area:** `backend/example.py::DECLARATIONS`, `SUITE`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** for each of the seven declarations, find the control whose BECAUSE quotes it
- **Expected:** a complete mapping
- **Why:** "every control below traces back to one of these lines, which is what makes the suite reviewable by the person who owns the data rather than only by its author"

## 22 · Cross-cutting boundaries and scale

### BE-169 · The complete pipeline on one control, on every engine
- **Area:** `pql.parse` → `types.require` → `ir.resolve.resolved` → `backend.sql.compile` → execution → `backend.execute.judge`
- **Type:** contract
- **Priority:** P1
- **Precondition:** each engine available
- **Steps:** take one control of each assertion kind through all six stages
- **Expected:** a verdict at the end, or a refusal at the compile stage — never an exception from a stage in between
- **Why:** every finding in this catalogue that spans two modules lives in a seam this walk crosses

### BE-170 · A 500-control suite compiles, fuses and runs
- **Area:** the whole path
- **Type:** performance
- **Priority:** P2
- **Precondition:** a 500-control estate over ten datasets
- **Steps:** check, lint, lower, fuse and run
- **Expected:** it completes; the fused plan is roughly one scan per distinct scope
- **Why:** the scale the product is sold at, and the linter's O(n²) subsumption pass is in it

### BE-171 · A control whose text is 1 MB
- **Area:** `pql/tokens.py::Lexer`, `parser.Parser`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** parse a control with a 1 MB `IN` list
- **Expected:** it parses in linear time, or is refused with a size limit
- **Why:** `_advance` steps one character at a time and `excerpt` splits the source on every error — both linear in the source, called per token and per error

### BE-172 · Integer values at the extremes
- **Area:** `pql/parser.py::Parser._primary`, `backend/dialect.py::SqlDialect.literal`, `ir/model.py::content_hash`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** use `9223372036854775807`, `9223372036854775808` and a 100-digit integer as a threshold and as a comparison operand
- **Expected:** the plan hashes, the SQL is emitted, and each engine either accepts it or the control is refused
- **Why:** Python integers are unbounded and `BIGINT` is not; a literal larger than the engine's range is an overflow at execution time

### BE-173 · Float precision at the boundary of a threshold
- **Area:** `backend/execute.py::_round`, `ir/model.py::Comparator.holds`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a rate threshold of exactly 20% over 1 violation in 5 rows
- **Steps:** judge on every engine
- **Expected:** the same verdict
- **Why:** `0.2` is not representable, `1/5` is computed differently by each engine's division, and the corpus has a case for "1/8 against 20%" for exactly this reason

### BE-174 · NULL in every position
- **Area:** the whole path
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a table where every column is null in at least one row
- **Steps:** run one control of every predicate operator over it, under both unknown policies, on every engine and the reference
- **Expected:** the four paths agree on every combination
- **Why:** the language's central decision is about nulls, and this is the matrix that proves it holds everywhere rather than in the cases the corpus happens to contain

### BE-175 · Zero and negative values in every numeric position
- **Area:** the whole path
- **Type:** boundary
- **Priority:** P1
- **Precondition:** rows with zero and negative notionals
- **Steps:** run comparisons, `BETWEEN`, arithmetic, `ABS`, `SIGN`, `INT`, `MOD` and `ROUND` over them
- **Expected:** agreement across the four paths
- **Why:** the corpus has one negative (`-10`) and one zero, both on the same column, and they are the only ones in the gate

### BE-176 · Unicode in data, in column names and in patterns
- **Area:** the whole path
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a table with a non-ASCII column name and non-ASCII values
- **Steps:** run a `LENGTH`, a `MATCHES` and an `IN` control over it on every engine
- **Expected:** agreement, and correctly quoted identifiers
- **Why:** three engines, three collations and three regex flavours, and nothing in the gate is outside ASCII

### BE-177 · Evidence records name the plan that produced them
- **Area:** `ir/model.py::ControlPlan.plan_id`, `backend/execute.py::ControlResult.plan_id`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a run
- **Steps:** trace the plan id from the lowering through the compiled control, the result and the evidence record
- **Expected:** the same string at every step
- **Why:** "an evidence record can name exactly what produced it" is the property the whole content-addressing design exists for

### BE-178 · Sealed evidence carries the threshold
- **Area:** `ir/model.py::ControlPlan.meaning`, the evidence path
- **Type:** regression
- **Priority:** P1
- **Precondition:** four runs with identical metrics and two different thresholds
- **Steps:** seal the evidence and read the records back
- **Expected:** the threshold is on the record, so the verdicts are explicable from it alone
- **Why:** QA finding Q-15 — "four records, identical metrics, two pass and two fail"

### BE-179 · A control that cannot be replayed cannot be written
- **Area:** `pql/parser.py::NON_DETERMINISTIC`, `pql/functions.py::VOLATILE`, `ir/lower.py::Lowerer._codelist`, `_valid`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** enumerate every way a control's verdict could depend on something outside the plan — the clock, a random source, an unresolved codelist, an unresolved semantic type, a validator implementation — and assert each is refused or frozen into the plan
- **Expected:** five refusals or freezes, and no sixth way in
- **Why:** "evidence that cannot be re-derived is not evidence" is the product's central claim, and this is the complete list of places it is kept

### BE-180 · No model output can decide a verdict
- **Area:** `backend/execute.py`, `ir/model.py::Threshold.evaluate`, `tests/architecture/test_layering.py`
- **Type:** security
- **Priority:** P1
- **Precondition:** none
- **Steps:** import-scan the judgement path for any dependency on `prama.llm` or `prama.assistant`
- **Expected:** none
- **Why:** `CON-007` and `NFR-AI-002` — "a deterministic, versioned engine decides", and the judgement path is where that is either true or not

