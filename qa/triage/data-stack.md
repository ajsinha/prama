# Triage: data-stack standing failures

Scope: the 142 cases (62 P1) listed for `connect/`, `db/`, `core/`, `evidence/`,
`execute/`, `lineage/`, `contract/`, `importers/`, `semantic/`, `profile/`,
`schedule/`, `integrate/`, `score/`, `calibrate/`, `security/` and the loose
`codelists.py`/`plugins.py`/`validators.py`/`classify.py`, cross-referenced
against `qa/logs-round4/*.md` and `qa/catalogue/*.md` for Observed/Precondition
/Steps/Expected/Why. Grouped by **cause**, not by file or keyword, per the
brief. 16 clusters cover 50 cases; 91 are genuine one-offs; 1 (`IMP-030`) is
not a defect. `CON-006`, `CON-009`, `PRO-009`, `PRO-058`, `SCH-041` are not in
this 142 at all — round 3 already removed them as not-a-defect before this
list was cut, which is consistent with the brief's note, not a contradiction
of it.

Two things this triage confirmed independently, neither tied to a single
catalogued case id — see §4.

---

## 1 · Batches, ordered by (cases closed ÷ effort)

| # | Batch | Cases | P1 | Repairs | Effort | Ratio |
|---|---|---:|---:|---|---|---:|
| C2 | The ISO 4217 version table retires a currency one version late | 2 | 2 | 1 | trivial | 2.0 |
| C9 | `ControlRun._run_one` records a placeholder snapshot kind and coverage, never what was actually read | 2 | 2 | 1 | trivial | 2.0 |
| C8 | An undeserialisable Kafka message is wrapped as a plain `dict` and sails through the isinstance check meant to catch it | 2 | 2 | 1 | trivial | 2.0 |
| C7 | `MongoConnector` never overrides `pushdown_capabilities()`, so a declared predicate can never reach `_sample` | 2 | 2 | 1 | trivial | 2.0 |
| C12 | A schema `CHECK` constraint enforces `drift_state`'s enum; the service layer that writes it does not | 2 | 1 | 1 | trivial | 2.0 |
| C16 | The IBAN length table's relationship to the live ISO 3166 registry is undocumented in both directions | 2 | 0 | 1 | trivial | 2.0 |
| C4 | Prama's own evidence verifier disagrees with the independent `verify_evidence.py` on two adversarial shapes | 3 | 3 | 2 | small | 1.5 |
| C3 | `to_array`'s mixed-type/unsigned fallback is bypassed by two of the four hand-built batch readers | 3 | 3 | 2 | small | 1.5 |
| C5 | `core/log.py`'s redaction has three independent blind spots | 4 | 1 | 3 | small | 1.33 |
| C6 | `SchemaVerifier` compares presence and nullability only — type, width, extra columns and unique indexes all verify clean when they should not | 5 | 2 | 4 | small | 1.25 |
| C1 | A raw Python exception escapes instead of the typed Prama error taxonomy | 12 | 5 | 12, one shared pattern | moderate | 1.0 |
| C11 | `plugins.py`'s static import scanner has three independent evasions | 3 | 2 | 3 | small | 1.0 |
| C10 | The `stranded` outcome (added to fix a real incident) was never plumbed into `drain()`'s loop-exit or `FleetReport` | 2 | 2 | 2 | small | 1.0 |
| C13 | A naive semicolon splitter, unaware of string literals, appears twice | 2 | 1 | 2 | small | 1.0 |
| C14 | A naive "take the last token" heuristic misreads a qualified/versioned name, in two importers | 2 | 0 | 2 | small | 1.0 |
| C15 | A broken or refused plugin is invisible outside a log line, in two ways | 2 | 0 | 2 | small | 1.0 |

**Total closed if every batch lands: 50 cases (28 P1).** Add the 91 one-offs
(34 P1, one of which — `IMP-030` — is withdrawn as not-a-defect, leaving 33) and
the realistic total is discussed in §5.

---

## 2 · Batch detail

### C1 — A raw Python exception escapes instead of the typed Prama error taxonomy
**Cases (12, 5 P1):** `CLI-140`(P2), `CON-153`(P1), `CTR-015`(P1), `CTR-047`(P2),
`IMP-007`(P1), `CFG-062`(P3), `DB-065`(P1), `DB-086`(P2), `DB-098`(P2),
`DB-179`(P1), `EVD-020`(P3), `EVD-110`(P2)

**What's wrong.** The same habit the language-stack triage found at 33 cases
reaches into this stack too, smaller but present in six different areas:
library code lets `AttributeError`, `KeyError`, `TypeError`, `ValueError`,
`ModuleNotFoundError`, `UnicodeDecodeError` or a raw driver exception propagate
out to a CLI/API caller instead of being caught and re-raised as the typed
taxonomy (`ValidationError`/`ConflictError`/`DatabaseError`/…).
- `CTR-015`: `contract/odcs.py::load` indexes `schemas[0]` and calls `.get` on
  it with no type check — a mapping, a list of strings, or a list of `None`
  each produce a different bare `KeyError`/`AttributeError`.
- `IMP-007`: `importers/spi.py::Collector.control` lets `PqlSyntaxError`
  escape `parse_control`, aborting an entire multi-hundred-test migration
  because one construct's carried-over expression doesn't parse — precisely
  what the importer's own stated contract (report the unmappable, keep going)
  exists to prevent.
- `CON-153`: `ObjectStoreConnector.open()` unconditionally calls `_connect()`,
  which builds malformed SQL for an unrecognised URI scheme — a raw
  `duckdb.ParserException` before `health()` (which *does* return the correct
  `MISCONFIGURED`) is ever reached through the idiomatic `async with
  connector:` pattern used everywhere else.
- `CTR-047`: `contract/diff.py::_freeze` raises a bare `TypeError: unhashable
  type: 'list'` for a nested JSON value reachable directly from `prama
  contract diff` on a `.jsonl` file.
- `CFG-062`: `FileSource.load` only catches `except OSError`;
  `UnicodeDecodeError` is a `ValueError` and escapes as a traceback for a
  latin-1 config file.
- `DB-065`: `EngineFactory.async_engine()` catches `SQLAlchemyError`; a
  missing driver raises `ModuleNotFoundError` (a plain `ImportError`) and
  escapes instead of becoming `DB.ENGINE_CREATE_FAILED` with the install hint.
- `DB-086`: closing a `UnitOfWork` does not set a flag any DAO call checks;
  the next call surfaces SQLAlchemy's raw "session is closed" error, breaking
  the layering claim that nothing above `prama.db` ever sees SQLAlchemy.
- `DB-098`: `UtcDateTime.process_result_value` calls
  `datetime.fromisoformat` with no try/except — a malformed stored timestamp
  raises stdlib's bare `ValueError` with no table or column named.
- `DB-179`: `VersionedDao.amend`/`correct` call `self._session.flush()`
  directly instead of through `UnitOfWork._guarded()`, so the losing side of a
  genuine concurrent-amendment race gets a raw `sqlite3.IntegrityError`
  instead of the documented `ConflictError` — data integrity is fine (only one
  current row survives), the *error* is not translated.
- `EVD-020`/`EVD-110`: `EvidenceRecord.from_dict`'s `float("eight")` and
  `Archivist.tier_of`'s naive/aware `datetime` subtraction on an offset-less
  `finished_at` both raise a bare stdlib exception with no record identified —
  the second one stops the entire retention sweep on one bad record.

**Repair.** Not one diff — twelve call sites — but one uniform, mechanical
pattern at each: identify the specific exception the underlying library or
stdlib call can raise, catch it, and re-raise the already-existing typed
error naming what was being read. No new taxonomy needed anywhere; every
target error type already exists in the codebase. This is exactly the shape
the language-stack triage's `C2` batch was, done as one sweep.

**Defect, all twelve.** Every one contradicts a stated contract (an importer
that must keep going, a layering guarantee, "no exception is swallowed" read
in the other direction — here nothing swallows it, it just isn't translated).

**Counterfactual.** Today: `contract/odcs.py`'s three malformed-shape cases in
`CTR-015` each raise a different bare exception; a test asserting
`pytest.raises(Exception)` passes today and would keep passing after a fix
that raised the *wrong* typed error. The real regression guard has to assert
`pytest.raises(ValidationError)` **and** that the message names the shape
problem (`"schema"` being a mapping vs a list) — a careless fix that wraps
everything in one generic `except Exception: raise ValidationError("bad
contract")` would pass a loose test and fail this one, because it can't say
*which* shape was wrong.

---

### C2 — The ISO 4217 version table retires a currency one version late
**Cases (2, 2 P1):** `CLS-059`(P1), `CLS-061`(P1)

**What's wrong.** `classify/codelists.py` builds each year's currency set by
layering on the *previous* year's, but every retirement is attached to the
`_ISO4217_20XX` constant one version **after** the `CodeListVersion` whose own
`note` announces it:
```python
_ISO4217_2024: Final = _ISO4217_2023 | {"ZWG"}                    # note: "ZWG replaces ZWL"
_ISO4217_2025: Final = (_ISO4217_2024 | {"XCG"}) - {"ZWL"}         # ZWL actually removed HERE
_ISO4217_2026: Final = _ISO4217_2025 - {"ANG"}                     # note on 2025: "XCG replaces ANG"; ANG actually removed HERE
```
`CLS-059` (ZWL still valid on 2025-01-01, when the 2024-04-05 version's own
note says it was retired) and `CLS-061` (ANG still valid past 2025-03-31,
when the 2025 version's own note says XCG replaced it) are the *same*
authoring slip, hit at two different transitions — additions land on time,
every retirement lands one version late.

**Repair.** One coordinated edit: move `- {"ZWL"}` into `_ISO4217_2024`'s
definition and `- {"ANG"}` into `_ISO4217_2025`'s, and check whether
`_ISO4217_2026` still needs to exist as a distinct version once its only
change moves earlier.

**Defect**, both. This is not "the catalogue's example was off by a
detail" — the version each note describes and the version that actually
performs the removal are provably different constants.

**Counterfactual.** Today: `ISO_4217.contains("ZWL", when=date(2025,1,1))` is
`True`; a control checking a currency column against `IN CODELIST iso4217`
reports last year's correctly-closed ZWL trades as valid a year after they
should read invalid, and (per `CLS-061`) reports ANG as valid for a full year
after its own replacement note says otherwise. A fix that only patches the
2024/2025 boundary and not 2025/2026 would pass `CLS-059` but still fail
`CLS-061` — the counterfactual has to move *both* subtractions, not just
silence the one test being looked at.

---

### C9 — `ControlRun._run_one` records a placeholder snapshot kind and coverage
**Cases (2, 2 P1):** `EXE-018`(P1), `EXE-019`(P1)

**What's wrong.** `execute/run.py::ControlRun._run_one` writes
`SnapshotRef(kind="wall_clock", ...)` and `coverage="full"` as **literals**,
unconditionally, regardless of what the connector or the watermark scope
actually reported. `connector.snapshot()` (PostgreSQL's LSN, SQLite's file
digest, Snowflake's Time Travel query id — all real, all wired elsewhere) is
never consulted; `execute/watermark.py::Coverage`, built to distinguish "the
whole table" from "just today's incremental rows", is never connected either.

**Repair.** One rewrite of the evidence-construction half of `_run_one`:
read the actual snapshot kind off the connector when it has one, and read the
actual coverage off the sample plan / watermark scope that was used.

**Defect.** This is the sharpest instance of the evidence-integrity theme in
this stack: "positions_eod passed" after a full scan and after a sampled
incremental run are two different claims, and the evidence record currently
cannot tell them apart from each other or say which snapshot it replays
against.

**Counterfactual.** Today: any `ControlRun` against SQLite — which has a real
`FILE_DIGEST` snapshot mechanism — still writes `kind="wall_clock"`. A test
that only asserts `record.snapshot.kind in SnapshotKind` would pass on the
unfixed code (wall_clock is a legal kind); the real test has to assert the
kind matches what the specific connector under test actually offers, and that
a sampled run's `coverage` differs from a full run's — a fix that hardcodes
`kind="exact"` instead of `"wall_clock"` would pass the loose version and fail
this one.

---

### C8 — An undeserialisable Kafka message sails through the dead-letter check
**Cases (2, 2 P1):** `CON-096`(P1), `EXE-096`(P1)

**What's wrong.** `execute/kafka.py::KafkaTransport._message` wraps a body
that isn't JSON as `{"_unreadable": True, "_raw": ..., "_why": ...}` — which
*is* a `dict`. `execute/inflight.py::Pipeline._judge`'s `isinstance(payload,
dict)` guard therefore treats it as an ordinary message and evaluates every
assertion against the note instead of dead-lettering it as unreadable; it
only happens to render `passed` today because the reproduction's stub
assertion never fires — a real assertion checking an expected field would
find it absent and misreport a *content* violation instead of what actually
happened, an unreadable message. Filed once under `connect/` (`CON-096`,
about `_Budget.report`/`_record_read`'s neighbouring code) and once under
`execute/` (`EXE-096`) — the catalogue's own structure, not two bugs.

**Repair.** One check: `Pipeline._judge` (or `_message`) needs to recognise
the `_unreadable` sentinel before the `isinstance(dict)` branch and route to
the dead letter, not the assertion evaluator.

**Defect**, confirmed by direct reproduction, matching the module's own
docstring exactly.

**Counterfactual.** Today: a pipeline with one assertion checking
`payload["amount"] is not None` on a batch containing one undeserialisable
message reports that message as a **content violation** ("amount is
missing"), not as unreadable. A test asserting only "the disposition is not
`passed`" would pass on a lucky assertion set (as the reproduction's own stub
did) without proving the message reached the dead letter for the right
reason; the real test has to assert the disposition is specifically
`dead_lettered` (or equivalent) and that no ordinary assertion is evaluated
against `_raw`/`_why` at all.

---

### C7 — `MongoConnector` never declares it can apply a predicate
**Cases (2, 2 P1):** `CON-172`(P1), `CON-014`(P1)

**What's wrong.** `MongoConnector` never overrides `pushdown_capabilities()`,
so `supports("pushdown.predicate")` is `False` at the instance level even
though the manifest's `CAPABILITIES` declares `PREDICATE_PUSHDOWN`.
`require_predicate_support()` therefore refuses **every** predicate-bearing
Mongo read before `_sample()`'s unconditional `collection.find({})` — which
genuinely ignores `plan.predicate` and would read the whole collection — is
ever reached with a predicate attached. The two catalogued cases describe the
same mechanism from two angles (the SPI contract in general, `CON-014`; the
Mongo-specific manifestation, `CON-172`) and `CON-172`'s own log entry says so
directly ("see CON-014").

**Repair.** One fix, and it has to be the *real* fix, not just the loud
refusal removed: either wire `_sample()` to actually apply `plan.predicate`
in the Mongo query and then have `pushdown_capabilities()` correctly declare
it, or (if predicate pushdown genuinely isn't supported) drop
`PREDICATE_PUSHDOWN` from the manifest so the capability declaration and the
runtime behaviour agree either way.

**Defect, but safer than either case assumed.** Today's actual failure mode
is a loud `CONNECT.NO_PREDICATE` refusal, not a silent whole-collection read
mislabelled as one segment (what both cases' `Why` predicted). Still wrong —
the declared capability is real work not yet done — but worth recording as
"defect, milder than catalogued" rather than the security-grade "quiet
disaster" both cases were written to catch.

**Counterfactual.** Today: `MongoConnector(...).read(('t',), plan=SamplePlan(
predicate="d = '2026-04-01'"))` raises `ConnectorError(CONNECT.NO_PREDICATE)`.
A fix that only silences the refusal (e.g. drops the `require_predicate_support`
check) without making `_sample()` actually filter would pass a test that only
checks "no exception raised" while resurrecting exactly the whole-collection
misattribution the SPI's refusal exists to prevent — the real test has to
assert the returned row count matches the predicate, not just that the call
succeeded.

---

### C12 — A schema `CHECK` constraint enforces `drift_state`'s enum; the service does not
**Cases (2, 1 P1):** `SEM-222`(P1), `SEM-223`(P3)

**What's wrong.** `schema/sqlite.sql`'s `ck_sem_binding_drift` restricts
`drift_state` to `('unknown', 'intact', 'missing', 'retyped', 'renamed')`, but
`semantic/services/graph.py::BindingService.record_drift` is written as if
any string is a legal value it can store and branch on (`status == "broken"`
only for the literal `"missing"`). A value the business genuinely might type
— `"changed"` (`SEM-222`) or `"gone"` (`SEM-223`) — reaches the database and
raises a raw, untranslated `IntegrityError`/500 rather than either completing
or being cleanly refused at the service boundary.

**Repair.** One validation, added once, at the top of `record_drift`: check
`drift_state` against the same five-value enum the schema already enforces,
and raise `ValidationError` naming the allowed values for anything else.

**Defect**, both — same root cause, `SEM-223` is the sharper of the two
symptoms of the identical gap.

**Counterfactual.** Today: `record_drift(drift_state="changed")` raises
`sqlalchemy.exc.IntegrityError: CHECK constraint failed:
ck_sem_binding_drift`. A test only asserting "an exception is raised" would
pass on the unfixed code; the real test asserts the specific type
(`ValidationError`, not `DatabaseError`/`IntegrityError`) and that the message
names `drift_state` and the allowed values — a fix that merely catches and
re-wraps the `IntegrityError` without checking the value *before* the write
would still leak the DB's own vocabulary into the message and fail that
stricter test.

---

### C16 — The IBAN length table's relationship to ISO 3166 is undocumented
**Cases (2, 0 P1):** `CLS-029`(P2), `CLS-030`(P2)

**What's wrong.** `validators.py::IbanValidator.LENGTHS` is a hand-maintained
snapshot with no stated relationship to `classify/codelists.py::ISO_3166`.
`CLS-029`: `XK` (Kosovo, user-assigned) is in `LENGTHS` and not in
`ISO_3166` — correct, but unexplained, so a control combining `IBAN_COUNTRY`
with `IN CODELIST iso3166` flags every Kosovan IBAN. `CLS-030`: `SO`, `FK`,
`MN`, `NI`, `DJ`, `RU` are absent from `LENGTHS` entirely, and the one refusal
message the code has conflates "not in our table yet" with "does not issue
IBANs" — a wrong statement about the world handed to a steward.

**Repair.** One pass: add the small set of deliberate extras (with a comment
saying why, as `CLS-029`'s own `Why` asks for) and the missing IBAN-issuing
countries, and split the refusal reason into the two cases it currently
conflates.

**Defect**, both — same underlying gap (an unaudited static table), different
symptom (silent extra vs silent gap).

**Counterfactual.** A regression guard that only asserts `set(LENGTHS) ==
set(ISO_3166.latest.codes)` would fail on `XK` forever, since that entry is
*supposed* to differ — the real test has to assert every difference is
named in a comment or a side table, not that the two sets are equal.

---

### C4 — Prama's own evidence verifier disagrees with the independent one
**Cases (3, 3 P1):** `EVD-006`(P1), `EVD-014`(P1), `EVD-144`(P1)

**What's wrong.** The whole claim of `evidence/ledger.py` is "verification
does not require Prama" — the test suite is supposed to make that provable by
requiring `Ledger.verify()` and the independent stdlib-only
`scripts/verify_evidence.py` to agree on every case. They do not, for two
separate reasons:
- `EVD-006`: Prama's own `core/pjson.py::canonical` serialises with
  `ensure_ascii=False`; the independent verifier's `canonical()` uses the
  stdlib default `ensure_ascii=True`, which escapes non-ASCII to `\uXXXX`
  before hashing — so a record with `münchen.positionen` hashes differently
  in the two implementations, and the independent verifier would report every
  non-ASCII record as altered.
- `EVD-014`: `EvidenceRecord.from_dict` silently drops any key it does not
  recognise before Prama's own `verify()` rehashes the record — so adding an
  unknown key (e.g. `"note": "approved by treasury"`) to a stored record is
  invisible to Prama's verifier (it rehashes the *cleaned* object) while the
  independent verifier, which hashes the payload byte-for-byte as found,
  correctly reports a breach. The tool that is supposed to be checkable
  without Prama is the one catching what Prama's own check misses.
- `EVD-144` is the corpus test that runs both verifiers over eleven
  adversarial shapes and records the disagreements; it fails as the umbrella
  case for exactly these two causes (`erased_tampered`'s disagreement belongs
  to a case outside this triage's scope; `extra_key`'s is `EVD-014`).

**Repair.** Two independent fixes — align `ensure_ascii` between the two
`canonical()` implementations (one line, either direction, as long as they
agree), and stop `from_dict` from dropping unknown keys before the hash is
recomputed (or hash the raw payload rather than the reconstructed object) —
and `EVD-144` then closes as a consequence, not a third fix.

**Defect**, all three, and among the highest-value fixes in this whole
scope: this is precisely the "checks everything except what it claims to
check" shape the brief's Q-76 thread describes, reached a second way.

**Counterfactual.** Today: forging a record by adding an unrecognised key and
leaving every hash untouched makes `Ledger.verify()` report `breaches=[]`
(intact) while `scripts/verify_evidence.py` correctly exits non-zero. A test
that only calls Prama's own `verify()` would pass on the tampered file; the
real test (which `EVD-144` already is) has to run *both* implementations over
the same bytes and require agreement — a fix that only makes the independent
script more lenient (instead of making Prama's own verifier stricter) would
make the two agree by weakening the one that is supposed to be the
harder-to-fool implementation, and should be treated as a regression, not a
fix.

---

### C3 — `to_array`'s mixed-type fallback is bypassed by two of four readers
**Cases (3, 3 P1):** `CON-043`(P1), `CON-167`(P1), `CON-044`(P1)

**What's wrong.** `connect/sources/sql/base.py::to_array` exists to give
every hand-built Arrow batch the same mixed-type and unsigned-integer
fallback. `sql/base.py` and `mongo.py` route through it; `sqlite.py`'s
`_read_batch` calls `pa.array(list(column))` directly and `rest.py`'s `read`
calls `pa.RecordBatch.from_pydict(...)`, both bypassing it entirely.
`CON-043` is the direct grep-and-confirm of the gap; `CON-167` and `CON-044`
are its two concrete symptoms — a REST endpoint with one string value among
199 floats, and a SQLite column with no declared type holding both an int and
a string, each raise `pyarrow.lib.ArrowInvalid` and the object becomes
**unreadable** through exactly the two connectors that skip the shared
helper, on exactly the ordinary data shape (`REST`'s and SQLite's dynamic
typing) `to_array` was written to survive.

**Repair.** Two edits, not three: route `sqlite.py::_read_batch` and
`rest.py::read` through `to_array` the same way `sql/base.py` and `mongo.py`
already do. `CON-043`, `CON-167` and `CON-044` all close together.

**Defect**, all three, confirmed by direct reproduction of both symptoms.

**Counterfactual.** Today: reading a REST endpoint whose numeric field is a
string in one row of 200 raises `ArrowInvalid` instead of producing a batch.
A fix that wraps the existing `from_pydict` call in a `try/except
ArrowInvalid: return empty batch` would make the crash go away but silently
drop the very rows `to_array`'s mixed-type handling is supposed to
*preserve as data* — the real test asserts the batch contains all 200 values
(mixed types included), not merely that no exception was raised.

---

### C5 — `core/log.py`'s redaction has three independent blind spots
**Cases (4, 1 P1):** `CFG-082`(P2), `SEC-210`(P2), `CFG-088`(P2), `SEC-209`(P1)

**What's wrong.** All four live in `core/log.py`'s redaction machinery, and
two of them are literally the same defect filed under two qa-areas:
- `CFG-082` and `SEC-210` are the **same** bug — `redact_mapping` recurses
  into `dict` only, so a `list` of mappings (a list of connection configs,
  `{"credentials": [...]}`) passes through unmasked either way it's phrased.
  One repair (recurse into `list` too) closes both.
- `CFG-088`: `_SENSITIVE_TEXT` only matches `key: value`/`key=value`; a DSN
  (`postgresql://prama:hunter2@host/db`) embeds the password after a colon
  inside a URL and is not matched — the single most likely thing to be
  logged, unredacted.
- `SEC-209`: `RedactionFilter.filter` substitutes over `record.msg` (the
  *template*) and never touches `record.args`, so the lazy-formatting call
  the logging docs recommend (`log.warning("password=%s", secret)`) writes
  the credential in full — the pattern-matching redaction only works on
  messages already formatted, which is the style the codebase discourages.

**Repair.** Three independent, small edits, naturally one working session on
one file: make `redact_mapping` recurse into lists; extend `_SENSITIVE_TEXT`
(or add a second pattern) to catch a DSN's embedded credential; have
`RedactionFilter.filter` also redact each element of `record.args` (or format
the message before matching).

**Defect**, all four — this is a security control with three real gaps, not
one case with three symptoms.

**Counterfactual.** Today: `_log.warning("password=%s", "hunter2")` writes
`password=hunter2` to the log verbatim (confirmed directly). A fix that
redacts only `record.msg`'s pattern matches (leaving `record.args` alone,
addressing only `CFG-088`-shaped literal DSNs) would pass a test that emits a
pre-formatted string but still fail one that uses the `%s`-argument style —
which is the style the codebase's own convention recommends, so the
counterfactual is the *common* case, not an edge one.

---

### C6 — `SchemaVerifier` compares presence and nullability only
**Cases (5, 2 P1):** `DB-047`(P1), `DB-048`(P2), `DB-050`(P2), `DB-052`(P1),
`DB-055`(P2)

**What's wrong.** `db/schema/verifier.py::SchemaVerifier.verify` was built to
guard exactly the "no migrations, the schema files are the authority" rule in
`CLAUDE.md`, and has four separate blind spots against it:
- `DB-047`/`DB-048` are the **same** gap: the loader captures
  `ColumnSpec.type` (which carries `VARCHAR(n)`'s width) but the verifier
  never reads it — a column retyped `VARCHAR(128)` → `TEXT`, or shrunk to
  `VARCHAR(8)`, verifies clean either way. One repair (compare `.type`)
  closes both.
- `DB-050`: `verify` iterates `table.columns` — the *declared* set — so it
  can never discover a column present live but absent from the schema file;
  a `NOT NULL` column added out-of-band verifies clean and the first insert
  omitting it then fails with no prior warning.
- `DB-052`: `DriftKind.MISSING_INDEX` is one kind covering both `ix_` and
  `uq_` indexes, and only `MISSING_INDEX` outside the `uq_` case is genuinely
  informational — a dropped `uq_ev_record_sequence` (the exact constraint
  that keeps the evidence chain from forking) verifies clean, `BLOCKING`
  treats it as no worse than a missing performance index.
- `DB-055`: `_recorded_state`'s `except SQLAlchemyError: return None, None`
  was written for "table absent" but also catches a genuine inability to
  connect at all — an unreachable database looks identical to an
  unbootstrapped one.

**Repair.** Four edits to one file, one working session: compare
`ColumnSpec.type` (closes two cases), iterate live columns as well as
declared ones, move `uq_`-prefixed `MISSING_INDEX` into `BLOCKING`
specifically, and narrow `_recorded_state`'s except clause (or re-raise after
distinguishing "no such table" from anything else).

**Defect**, all five — and strategically the most important cluster in this
scope given the "no migrations" doctrine: this is the control that is
supposed to make schema drift a loud failure, and four of its five stated
guarantees have a hole.

**Counterfactual.** Today: dropping `uq_ev_record_sequence` and calling
`verify()` returns `report.ok == True` (confirmed directly). A test that only
checks `verify()` returns *some* `Drift` naming the index would pass on a fix
that added it to `MISSING_INDEX` without also moving it into `BLOCKING`
(informational drift is still "reported"); the real test asserts
`report.ok is False` specifically for the dropped unique index, since an
informational-only report is functionally the same as today's silent pass
for anyone gating on `ok`.

---

### C11 — `plugins.py`'s static import scanner has three evasions
**Cases (3, 2 P1):** `CLS-119`(P2), `CLS-124`(P1), `CLS-127`(P1)

**What's wrong.** Three independent ways past the same admission scan:
- `CLS-119`: `FORBIDDEN` is an allowlist-by-omission — `shutil`, `tempfile`,
  `sqlite3`, `ftplib`, `smtplib` and seven others reach the filesystem or the
  network under names the scan doesn't know to flag, contradicting "no clock,
  no network, no filesystem, no model."
- `CLS-124`: `_local_imports` resolves only `root / f"{name}.py"` for the
  *last* dotted segment of a relative import, so `from .helpers.impure import
  check` (a helper one directory down) is invisible — the same evasion class
  H3 closed, one package level deeper.
- `CLS-127`: `scan_source` returns `[]` on `SyntaxError`, and `[]` means
  "nothing forbidden" everywhere else it's used — a helper file that fails to
  parse (and that the validator being admitted never imports at Python import
  time, so the loader's own "it refuses on import" fallback doesn't apply
  either) scans clean.

**Repair.** Three edits to one file, naturally one PR: widen `FORBIDDEN` (or
switch the scan to a denylist maintained alongside a documented allowlist),
resolve `_local_imports` recursively through subpackages, and have
`scan_source` raise/refuse rather than return `[]` on a parse failure.

**Defect**, all three — a security control (the plugin sandbox) with three
real, independently-exploitable gaps.

**Counterfactual.** Today: a validator helper doing `import shutil;
shutil.copy(...)` is admitted without refusal. A fix that adds `shutil` alone
to `FORBIDDEN` would pass `CLS-119`'s specific probe list but leave every
other unlisted stdlib module (and the subpackage-resolution and
syntax-error gaps) open — the real regression guard has to assert the
admission boundary's *default* is refuse-unless-allowed, not
allow-unless-named, or the next unlisted module reopens the same hole.

---

### C10 — The `stranded` outcome was never fully plumbed through
**Cases (2, 2 P1):** `EXE-043`(P1), `EXE-050`(P1)

**What's wrong.** A `stranded` work-item status exists (added for a prior
incident, X4) but two of its consumers don't know about it:
- `EXE-043`: `take_one()` returns a `stranded` outcome (not `None`) and
  requeues the unit when the recorder is permanently unreachable, but
  `drain(limit=0)`'s loop only stops on `outcome is None` — confirmed
  directly: 200/200 calls against a permanently-failing recorder return
  `stranded`, never `None`, so `drain` would spin forever rather than the
  merely-transient case X4 fixed.
- `EXE-050`: `FleetReport` exposes `done`/`lost`/`failed` and names the last
  two in `render()`/`to_dict()`; `stranded` is in neither, so a stranded
  fleet reports "0 units completed, 0 records written, 1 still queued" with
  no mention of why — the exact invisibility X4 was fixed to remove, one
  layer out.

**Repair.** Two edits: give `drain` a real termination condition for a
permanently-stranded unit (a retry ceiling, or treat repeated `stranded` as
terminal after N attempts), and add `stranded` to `FleetReport`'s counters
and rendered summary.

**Defect**, both — genuinely two different consumers of the same status, not
one bug filed twice.

**Counterfactual.** Today: `drain()` against a permanently-failing recorder
does not return (confirmed: 200 consecutive `stranded` outcomes, 0 `None`).
A fix that only patches `FleetReport` (visibility) without changing `drain`'s
loop condition would still hang the caller forever, passing a test that only
checks the *report's* content and never actually calls `drain()` to
completion — the real test has to bound `drain`'s own runtime, not just
inspect what it eventually returns.

---

### C13 — A naive semicolon splitter, unaware of string literals, twice
**Cases (2, 1 P1):** `DB-031`(P1), `LIN-046`(P2)

**What's wrong.** Two unrelated modules split SQL text on `;` with no
string-literal awareness, and both have a case proving it: `DB-031`
(`db/schema/loader.py::_split`) breaks one `CREATE TABLE` into two truncated
fragments when a `DEFAULT 'a;b'` is present; `LIN-046`
(`lineage/sql.py::extract`) reports two statements for one `INSERT`
containing `WHERE note = 'a;\nb'`. Same shape, two independent
implementations, two independent fixes.

**Repair.** Two edits (or one shared quote-aware splitter introduced in
`core/` and used by both) — not mergeable into a single diff since the two
regexes live in different files with different surrounding logic.

**Defect**, both — `DB-031`'s own docstring names this exact failure mode as
the thing it hasn't yet had to survive; `LIN-046` hits the identical mistake
independently.

**Counterfactual.** Today: `schema/sqlite.sql`/`schema/postgres.sql` don't
currently contain a `;` inside a string literal, so this has never fired in
production — which is exactly why a test that only runs the *shipped* schema
files would never catch it. The real test (as both cases already do) injects
a semicolon into a string literal deliberately; a fix that special-cases only
the one literal shape in the reproduction (e.g. only `DEFAULT '...'`) rather
than genuinely tracking quote state would pass that test and still break on
a semicolon inside a `CHECK` constraint's string comparison.

---

### C14 — A naive "last token" heuristic misreads a qualified name
**Cases (2, 0 P1):** `IMP-014`(P2), `IMP-051`(P2)

**What's wrong.** Two importers each take the last fragment of a
delimiter-split string as "the meaningful part" of a name, and both have a
case where that fragment is the wrong one: `IMP-014` — dbt's
`_dereference` takes `parts[-1]` of a comma-split `ref('accounts', v=2)`,
correct for `source(schema, table)` and wrong for a versioned `ref`, so the
generated control references a dataset literally called `v=2` (and, observed
directly, produces unparseable PQL rather than even that). `IMP-051` — Great
Expectations' dataset-name derivation does `.split(".")[-1]` on
`expectation_suite_name`, so `"warehouse.orders.critical"` yields the dataset
`critical`, not `orders`, and every control in the file is written against a
table that does not exist.

**Repair.** Two edits, different files, different specific parsing fixes
(strip a `v=N` version suffix before taking the last comma-fragment; take a
documented segment convention — or refuse and ask — for the suite name
rather than blindly the last dot-fragment).

**Defect**, both — not mergeable into one fix since the delimiter and the
correct segment differ per importer, but worth fixing in the same pass since
they're the same lesson: a qualified/versioned name's meaningful segment is
not reliably "whatever comes last."

**Counterfactual.** Today: `imp.read(doc)` for a versioned `ref` produces
`PqlSyntaxError` (confirmed) rather than a wrong-but-parseable control. A fix
that merely prevents the crash (e.g. quoting `v=2` so it parses as an
identifier) without extracting `accounts` would pass a test asserting only
"no exception" while still writing every generated control against the wrong
dataset — the real test asserts the rendered control's target table name.

---

### C15 — A broken or refused plugin is invisible outside a log line
**Cases (2, 0 P1):** `CFG-260`(P2), `CFG-262`(P2)

**What's wrong.** Both in `core/registry.py`, both about the same discovery
path, two different gaps: `CFG-260` — `Registry.discover()`'s docstring
promises a broken plugin's failure "is visible in health output," but
`Registry` tracks no failure state at all, and the only `/health` route in
the codebase reports database state exclusively — the only trace is a
`_log.warning()`. `CFG-262` — `_entry_points_for`'s `except Exception: return
[]` makes a corrupted/unreadable distribution-metadata directory
indistinguishable from an installation with zero plugins, violating
`CLAUDE.md`'s own "no exception is swallowed" rule in the direction that
hides an installation problem rather than reports one.

**Repair.** Two edits: give `Registry` a failure-tracking attribute the
`/health` route can read (closes `CFG-260`), and have `_entry_points_for`
distinguish "genuinely empty" from "could not enumerate" and raise/report the
latter (closes `CFG-262`).

**Defect**, both — plausibly one PR since they share a file and a theme
(plugin-discovery observability), but two distinct code paths, not one.

**Counterfactual.** Today: corrupting `importlib.metadata`'s entry-point
enumeration makes `_entry_points_for` return `[]`, indistinguishable from an
intentionally empty install (confirmed directly). A fix that only adds
logging (satisfying "the failure is visible" in the loosest reading) without
changing the `except Exception: return []` return value would still make
`discover()`'s *caller* unable to tell a broken install from an empty one
programmatically — the real test asserts the caller can distinguish the two
states without reading a log file.

---

## 3 · Not a defect

- **`IMP-030`** (P1) — the catalogue's own worked example
  (`invalid_percent(ccy) < 2 %`) happens to land on a refusal that
  `importers/soda.py::_threshold` makes **deliberately**: a strict `<` bound
  on a percentage metric has no representable predecessor (unlike an integer
  count, where `< 5` cleanly becomes `<= 4`), so treating it as inclusive
  would silently widen the control. The code's own comment says so in as many
  words: *"A strict bound on a rate has no representable predecessor, so
  treating it as inclusive would widen the control silently. The contract
  importer refuses the same shape for the same reason."* — and `CTR-031`'s
  neighbouring contract-importer code does refuse the identical shape, on
  purpose. The catalogue's second sub-case (`missing_percent(x) = 0` →
  `BELOW 0%`) is the one that actually exercises what the case titles itself
  around (percent-suffix parsing), and it already passes. Recommend closing
  `IMP-030` as a bad worked example, not reopening the refusal.

`CON-006`, `CON-009`, `PRO-009`, `PRO-058`, `SCH-041` — confirmed absent from
this 142-case list entirely, consistent with round 3's not-a-defect finding
already having removed them before this cut was made. Nothing to re-litigate.

No other case in this scope reads as a deliberate product decision being
mistaken for a bug — the ambiguous one, `SCH-046` (whether cost-ascending or
anti-starvation is the *intended* shedding order), is left as a genuine
defect in §5's tail rather than moved here, because the code and its own
docstring actively disagree with each other; that disagreement needs a
product decision to resolve, but it is not itself a case of an over-strict
catalogue — something here has to change, docstring or code.

---

## 4 · The two threads asked for specifically

**Float/Decimal mixing.** `recon/classify.py` (behind the `classify.py`
catalogue entries — `RCN-060`/`RCN-064`/`RCN-068`) carries every reconciliation
break amount as `Decimal` throughout — `difference`, `magnitude`, the
rounding/multiple-detection helpers all declare and operate on `Decimal`. But
the actual pass/fail boundary — `_within_tolerance` — converts both arguments
to `float` before calling out:
```python
def _within_tolerance(self, difference: Decimal, magnitude: Decimal) -> bool:
    return self._tolerance.permits(float(difference), float(magnitude))
```
`semantic/relationships.py::Tolerance` (the class `permits` belongs to)
declares its own bounds as `absolute: float | None` and `relative: float |
None` natively — so the conversion isn't a local slip, it's forced by
`Tolerance`'s own type. This is the identical shape the language-stack triage
found in `reference._arithmetic`/`library._number`: careful `Decimal`
arithmetic everywhere **except** at the one comparison whose outcome is the
verdict, which happens in `float`. No catalogued case in this scope names
this directly (`RCN-060`/`064`/`068` each test a different downstream
classification bug), but it is real, confirmed by reading the source, and it
means a break sitting exactly on a tolerance boundary can replay differently
depending on IEEE-754 rounding of a value that was exact up to that point —
in an evidence-first product where a verdict must replay identically, this
is worth its own fix: make `Tolerance` (and `permits`) `Decimal`-native, the
same direction the language-stack fix is presumably taking `library._number`.

**The Q-76 shape.** `evidence/retention.py::Bundle.check()` is confirmed to
have exactly the gap described: it checks record count against
`manifest.records`, the payload's SHA-256 against `manifest.payload_digest`,
the hash chain's integrity, and `chain_head` against `manifest.chain_head` —
but never compares the payload's actual first/last record `sequence` against
`manifest.from_sequence`/`to_sequence`, and never compares the freshly
recomputed `merkle_root` (which `verify()`'s own `Verification.merkle_root`
already computes and returns) against `manifest.merkle_root` either.
Concretely: because `payload_digest` covers only the payload file and not the
manifest, a manifest hand-edited (or produced by a bug) to claim
`to_sequence=1000` while the payload's own last record has `sequence=450`
would still pass `check()` cleanly — record count, digest, chain and head can
all be internally consistent while the manifest's claimed range is simply
false. Same shape as Q-76, same file family, a second instance rather than a
coincidence: `check()`'s own docstring says it exists precisely because "the
failure that matters for an archive is not a forged record — it is a
truncated file, and only the manifest's count reveals that," and the
`from_sequence`/`to_sequence`/`merkle_root` fields are exactly the manifest's
other claims about what's inside, left unchecked. No catalogued case in this
142 names this directly either — worth a case if one doesn't already exist
elsewhere in this project's evidence/security backlog.

---

## 5 · One-offs (91 cases, 33 P1 after withdrawing `IMP-030`)

Each of these is a genuinely distinct defect — different mechanism, different
file, not fixable by the same edit as any neighbour, even where several share
a module. Listed by qa-area for scanning, not because area implies cause.

### dataplane (16)
| ID | P | What |
|---|---|---|
| CON-021 | P1 | `ReadPolicy.permits_path` treats a bare (non-wildcard) allow-list entry as a prefix with no separator anchoring — `risk` admits `riskier.positions` |
| CON-055 | P1 | postgres's `schemas` field is wrongly `required=True` (no default), so the secret-refusal case it's meant to test never gets reached — the secret refusal itself works once `schemas` is supplied |
| CON-062 | P2 | `register_builtin(registry or default_registry())` — `ConnectorRegistry` has `__len__` but no `__bool__`, so a fresh **empty** registry is falsy and registrations silently land in the process-wide singleton instead |
| CON-099 | P1 | `run_metric_query` reads `_stream_columns`, set only by `_stream()`; calling it after a `read()` labels the metric's own columns with the *previous* read's stale, `zip(strict=False)`-truncated names |
| CON-118 | P1 | `SqlDialect.select_sql` (unlike `stream_sql`) never applies `plan.predicate` — latent today since `SqlConnector.read` uses `stream_sql`, live for any future/third-party caller of `select_sql` |
| CON-129 | P2 | `ORDER BY (rowid * seed % 1000003)` only reorders once the product wraps the modulus — every seed up to roughly the table's own row count produces plain rowid order, not a systematic sample |
| CON-142 | P1 | `FilesystemConnector.read` builds no `_Budget` at all — `ReadPolicy`'s row/byte ceilings are silently not applied (same underlying gap likely affects `objectstore.py`/`rest.py`/`mongo.py`, only this one is a scored case) |
| CON-181 | P1 | `MongoConnector._connection_uri` interpolates a raw, un-percent-encoded password into an f-string URI — `@`/`:`/`/` in the password split the authority |
| CON-206 | P1 | `FeedDefinition.to_dict`/`from_dict` round-trip loses `earliest` and the trailer's `total_field`/`amount_field`/`header_lines`/`total_tolerance` entirely |
| CON-217 | P1 | `TrailerChecker`'s shortfall renders with an explicit `+` sign (`f"{shortfall:+,}"`) — a deficit reads as `(+3)`, as though 3 extra rows arrived |
| CON-219 | P2 | `_check_total` passes `observed_count=trailer_index` (a *line* index) where `check`'s sibling branch passes the actual data-row count — same field, two meanings, in one method |
| PRO-021 | P1 | `TDigest.merge` concatenates two centroid lists without re-sorting; correct only when the two digests' value ranges happen not to overlap — the realistic case (splitting one column across segments) returns garbage quantiles |
| PRO-063 | P3 | `from prama.profile import from_rows` fails outright — not merely missing from `__all__`, the import block never pulls it in at all |
| PRO-099 | P1 | The generic-name filter (`_is_generic`) only gates the NAMING signal; the CONTAINMENT signal runs over every shared column pair unfiltered, so a generic column whose values happen to overlap still proposes a relationship |
| SCH-014 | P2 | `CalendarTrigger` (unlike `IntervalTrigger`) has no `offset_minutes` field at all — every 06:30-scheduled control fires simultaneously, defeating the stagger that exists specifically for controls landing right after a feed |
| SCH-046 | P1 | Sort key `(priority.rank, -deferrals, cost, identifier)` makes deferrals outrank cost — contradicts the docstring's stated "cost ascending, deferred-longest only as a tiebreak"; needs a product decision on which rule is intended, then the other side fixed |

### domain (32)
| ID | P | What |
|---|---|---|
| CLS-069 | P3 | Two `CodeListVersion`s sharing one `effective_from` are not refused at construction — resolves last-wins by declaration order, undocumented |
| CLS-070 | P2 | `CodeList.contains` case-folds for `case_sensitive=False`; `CodeListVersion.__contains__` (the more natural `in` spelling) does not |
| CLS-076 | P2 | `CodeListRegistry.register` overwrites a name silently; the sibling `ValidatorRegistry.register` refuses for the identical reason |
| CLS-130 | P2 | `PROBES` (seven strings) contains no `None`, though `judge(None)` is a documented contract a plugin may override and crash on |
| CLS-134 | P2 | `PluginRegistry` exposes only admitted names — a refused plugin is discoverable nowhere except the log |
| CTR-006 | P1 | `controls_from` reads `schemas[0]` only — quality blocks on every other schema in a multi-schema contract are dropped with no mention, unlike `load`, which at least names what it drops |
| CTR-014 | P1 | `_logical_type` maps everything but date/timestamp to `string`, and `_TYPE_TO_SEMANTIC['string']` is `''` — a `semantic_type='lei'` declaration is silently deleted by export/import, unreported because `string` is a real ODCS type |
| CTR-031 | P1 | `_render` renders every freshness window as `f"{window} day"` unconditionally — a 4-hour promise imports as a 4-day control, 24x looser, silently |
| CTR-048 | P2 | A keyless diff's set-based comparison collapses 3 identical left-side rows into 1 with no indication a 2-row loss occurred |
| CTR-050 | P1 | `_key_of` on a `--key` column absent from every row collapses all rows onto one key (`row.get(name)` → `None` for all) instead of refusing the typo'd column name |
| IMP-005 | P2 | `ImportResult.is_complete` is `not self.unmapped` — ignores `caveats` entirely, so an import where every null now counts as a violation still reports "complete" |
| IMP-018 | P2 | `_proportion`'s `(1.0 - 95) * 100` has no bound on the input — a percentage typed where a proportion is expected produces `BELOW -9400%` |
| IMP-023 | P2 | `_split` returns `("", {})` for a multi-key test mapping — reported as unmapped with an empty, unfindable name |
| IMP-037 | P2 | `_row_count`'s own comment claims it avoids emitting "AT LEAST 0" (a control that can never fire); the code has no guard for it and both `> -1` and `>= 0` produce exactly that |
| IMP-049 | P2 | The one-sided-range remedy hardcodes `>` (`f"CHECK ... > {low if low is not None else high}"`) — for a `max_value`-only bound this tells the user to write the *inverted* check |
| IMP-054 | P2 | A `.replace("  ", " ")` whitespace-collapse pass is applied to the whole rendered control string, including inside string literals — `"NEW  YORK"` becomes `"NEW YORK"`, a different value than the source declared |
| INT-006 | P1 | `badges_from` has three reachable outcomes (FAILING/NOT_ESTABLISHED/HEALTHY); `Standing.UNPROVEN` is defined, labelled, and never constructed by anything |
| INT-017 | P2 | `badges_from` never sets `Badge.jurisdiction` — every generated badge reads `''`, indistinguishable from "declared as unrestricted" at the egress gate |
| INT-031 | P2 | `str(item.get("name",""))` on a nameless manifest entry produces the dataset key `''`, and the plan/controller apply `CREATE` for it without complaint |
| INT-041 | P1 | `reconcile_all` builds its outcome tuple by comprehension — one resource's transient status-write failure aborts every resource after it in the loop, contradicting the stated "one failure must not take the others down" |
| INT-042 | P1 | `_payload` returns `{**declared, "managedBy": ...}` — the whole manifest fragment unfiltered — so the claim "nothing here can approve or activate" rests entirely on a downstream store, not on anything in this module |
| LIN-009 | P2 | `blast_radius` sets `truncated=True` whenever a frontier item's depth hits the max, even when that node has no outgoing edges — a complete traversal reports as incomplete |
| LIN-011 | P2 | `below_floor` increments per traversal/edge, not per distinct column — one column reached five ways via aggregation reports as 5 |
| LIN-024 | P2 | The orphan-rate claim in the module's own docstring is computed nowhere in the module |
| LIN-029 | P1 | `_split_alias`'s implicit-alias heuristic misreads `a + b` as expression `a +` aliased `b`, producing a wrong edge silently instead of the `unnamed_output` gap |
| LIN-037 | P2 | `sources[alias] = table; sources[table] = table` write into one dict — a second table's own-name entry overwrites the first table's, so `FROM orders o JOIN customers orders` resolves every unaliased `orders` reference to `customers` |
| LIN-042 | P2 | A synthetic `t.*` node from `_filter_edges` surfaces through `columns`, `columns_of`, `orphans` and every impact list with no documented meaning |
| LIN-043 | P1 | `_SELECT` is non-greedy to the *first* `from` — a CTE's own SELECT is parsed instead of the outer query, silently, with no gap recorded |
| LIN-045 | P1 | Only the first branch of a `UNION` is matched — the second source table contributes no edges and nothing is reported |
| LIN-047 | P2 | `_target`'s bracket/quote stripping is naive — `[dbo].[Orders]` becomes `'dbo].[Orders'`, backtick-quoted names return `None` |
| LIN-051 | P2 | `\bdeclare\b[^;]*;` consumes to the *next* semicolon — a `DECLARE` section with no terminator before the first real statement eats that statement too |
| RCN-060 | P2 | The unvalued-record branch is detected by `"carry no" in normalisation_text` — a coincidental substring in unrelated prose misclassifies a genuine break as configuration-caused |
| RCN-064 | P2 | A 12/13 split population (two distinct FX ratios) is reattributed to FX wholesale rather than left as two findings — the "close set must be more than half" rule isn't enforced |
| RCN-068 | P3 | `'points' if len(faults) == 1 else 'point'` — the two arms of the pluralisation are swapped |

### platform-core (16)
| ID | P | What |
|---|---|---|
| CFG-021 | P3 | No negative-value guard anywhere `backtest_days` is read (`preview_routes.py` passes it straight into date arithmetic) |
| CFG-040 | P2 | `PoolSettings.validate` checks `size <= 0` but never validates `max_overflow` — a negative value silently defeats the pool cap (SQLAlchemy treats it as unbounded) |
| CFG-048 | P1 | `concurrency.lease.provider` is never read anywhere in `src/` — `Database.lease_provider()` unconditionally returns `DatabaseLeaseProvider`, the config key is decorative |
| CFG-094 | P2 | `JsonFormatter` uses `formatTime`'s default local-time converter, never overridden to `gmtime` — the emitted `Z`-suffixed timestamp is local wall-clock on a non-UTC host |
| CFG-112 | P2 | `to_duration_seconds` accepts a negative numeric duration (`-5` → `-5.0`) while the equivalent string form (`'-5s'`) is correctly refused — the two representations disagree |
| CFG-162 | P2 | One bare `datetime.now(UTC)` call site outside `core/clock.py` (`cli/apikey.py:98`) — UTC-aware so not wrong data, but outside the deterministic-replay discipline |
| CFG-205 | P2 | `TaskSupervisor._run`'s backoff/restart bookkeeping runs unconditionally after every iteration, success or failure — a healthy `ALWAYS` poller is throttled with the same exponential backoff as a crash loop |
| CFG-292 | P2 | `next_business_day`'s `while` loop has no ceiling — a calendar with no business days iterates thousands of years of CPU before an unhandled `OverflowError` |
| CFG-305 | P2 | `register()` lower-cases the dict key; `names()` returns those lower-cased keys — a caller who registered `TARGET2` never sees that case in any listing |
| DB-068 | P1 | `path: ':memory:'` gives the sync engine (`initialise()`) and the async engine (`start()`) separate `StaticPool`s — two physically separate in-memory databases; the schema one creates is invisible to the other |
| DB-076 | P2 | `upsert` with every column in the conflict key produces `... DO UPDATE SET ` with an empty assignment list — a syntax error on both engines, not a refusal |
| DB-125 | P2 | `TenantScopedDao.list_for_tenant` passes a negative `limit` straight to SQLAlchemy — SQLite reads `LIMIT -1` as unbounded and returns the whole result set |
| DB-155 | P2 | `active_for_principal` has no docstring stating "active" means "not revoked," not "not expired" — the dangerous behaviour itself doesn't happen (`api/deps.py` separately checks `expires_at`), only the documentation is missing |
| DB-208 | P2 | `JourneyDao.containing` loads `list_current(limit=10_000)` and filters in Python — past the hardcoded ceiling, a real match is silently missed |
| DB-209 | P3 | `ConnectionDao.unhealthy` has the identical 10,000-row ceiling — an operations screen can report "all healthy" because the broken connection is #10,001 |
| DB-239 | P1 | `EvidenceDao.erase`'s only protection for `content_hash`/`record_hash` is two bare `assert` statements — confirmed stripped under `python -O`/`PYTHONOPTIMIZE=1` |

### semantic (6)
| ID | P | What |
|---|---|---|
| DER-058 | P1 | `ast.Literal.render()` never escapes an internal `/` in a PATTERN literal — any value-domain regex containing an ordinary unescaped slash (path-shaped codes, `dd/mm/yyyy`) generates a control that does not re-parse |
| IND-011 | P1 | `_subject_of`/`_probes` only walks a plain predicate's `.subject` — `ExpressionAssertion` (what `SATISFIES` produces) has no such attribute, so a tautology like `SATISFIES 1 = 1` gets zero probes and is `Validated` despite never being able to fail |
| SEM-060 | P2 | `RelationshipKind.FEEDS.generates` omits the "RCA path" control family `docs/03` §2.4 promises for it |
| SEM-145 | P3 | `MaturityScore.percent` uses bare `round()`; `round(0.5)` banker's-rounds to `0`, so a score of exactly `0.005` reports `0%` instead of `1%` |
| SEM-163 | P2 | `temporality`/`sensitivity`/`authoritativeness` have no `CHECK` constraint in `schema/sqlite.sql`, unlike the sibling enum columns `criticality`/`shape`/`lifecycle_state` on the same table — `declare()` accepts any string for all three |
| SEM-215 | P1 | `ConnectorRegistry.create()` validates the config *after* `_resolve_credential` has injected the live secret — `ConnectorConfigSchema.validate()` then unconditionally refuses the very credential the method just injected, breaking every connector whose credential field is marked `secret=True` (the norm) |

### trust (19)
| ID | P | What |
|---|---|---|
| CAL-011 | P2 | `ConformalCalibrator` is a linear scan, not the documented `bisect`/suffix-sum lookup — 49s against a 10s budget for 10,000 p-values over 100,000 points |
| CAL-048 | P1 | An empty `CalibrationCurve` has `calibration_error=0.0` and `meets_target=True` unguarded — a monitor that has seen nothing reports meeting the calibration target |
| EVD-036 | P3 | Erasing a sequence not present in the ledger is neither refused nor reported — the caller gets the unchanged ledger back, believing the request was satisfied |
| EVD-072 | P2 | `sign(head, b"")` is accepted and returns a normal-looking hex signature — the shipped `security.session_secret` is empty by design, so this is the value a misconfigured deployment actually has |
| EVD-073 | P2 | No CLI or API surface renders a signed chain head at all — the required "an HMAC proves nothing to a non-key-holder" caveat has nowhere to appear, since nothing shows the word "signed" |
| EVD-084 | P2 | `SampleStore` is content-addressed with no reference counting or documentation of the fact — two runs' byte-identical failing rows share one digest, and `forget()`-ing one expires both |
| EVD-087 | P2 | `EvidenceRecord`'s fields do not include which columns a sample masked — once `SampleStore.forget()` runs, that information is gone with no trace |
| EVD-122 | P1 | `Manifest.verification`'s prose describes content_hash/record_hash/link/tombstone but never the tombstone **seal**, the **Merkle root**, or the **payload digest** — all of which the verifier actually checks; a reimplementation from the prose alone would under-check |
| EVD-124 | P1 | `Archivist.bundle` exists and nothing in `cli/` or `api/` ever constructs an `Archivist` or calls it — the runbook's "an auditor wants to verify a bundle" procedure begins at a file nothing in the product creates |
| SCR-019 | P2 | `Measurement.rate` with `violations > scanned` (reachable through a join) returns a silent negative rate that drags a weighted composite below zero with no flag |
| SCR-022 | P3 | `Score.to_dict`'s 6-decimal round can turn `0.9999996` into a presented `1.0` — a near-failing dataset renders as a clean 100% |
| SCR-041 | P2 | `TrustPropagator` truncates a derivation at `_max_depth` but the rendered explanation never states the truncation happened |
| SCR-042 | P1 | `_paths_to` enumerates and keeps *every* path rather than the best one per node — a 6-wide, 8-level graph is ~1.7M path tuples for one column, over budget |
| SEC-039 | P1 | `EGRESS_POINTS['source-read']` is documented as carrying "the dataset's declared jurisdiction," but `connect/sources/rest.py`'s call site passes `self._region` (the connector's own configured region — the same value as the destination) instead |
| SEC-123 | P2 | The CEF exporter reserves `cs1`..`cs4` for fixed fields (tenant/objectKind/objectId/correlationId) and starts arbitrary detail keys at `cs5` — only 2 of a possible 6 slots (and 2 of 8 offered keys) are ever actually available |
| SEC-134 | P2 | SOC 2 criterion CC6.6's note says customer-managed keys "are not built"; `security/cmk.py` demonstrably is (encrypt/decrypt/`LocalTestKeyProvider` all present and exercised by 22 other cases) |
| SEC-154 | P2 | `build_manifest` skips only `manifest.json`/`manifest.sig` by name — `manifest.ed25519` from a prior seal is catalogued as a regular entry, then excluded by `verify`, so a **second** seal of the same directory produces a bundle that never verifies again |
| SEC-173 | P3 | `_LOOKS_LIKE_A_SECRET` is defined, documented as the mechanism for a useful "don't try to resolve a password as a URI" error, and referenced nowhere |
| SEC-215 | P2 | `SecretResolver.register` silently replaces an existing provider for a scheme with no stated rule and no docstring — a plugin can take over the `env` scheme |

---

## 6 · Honest estimate

**Realistically closable in one coordinated effort: roughly 90–100 of the
142** — the 50 in the 16 clusters above, plus a comfortable majority of the
91 one-offs (`IMP-030` already withdrawn as not-a-defect), most of which are
single-function, single-file, low-ambiguity fixes once someone is looking at
the right fifteen lines (the detail column above is close to the diff itself
for most of them). The genuinely hard remainder is smaller: `SCR-042`
(algorithmic — bounding path explosion needs a real design, not a guard
clause), `PRO-021` (TDigest merge needs a proper k-way merge, not a
concatenate-and-flush), `SCH-046` (needs a product decision before any code
changes), `EVD-124`/`INT-042` (each needs a scoping decision — build the
missing CLI/API surface, or explicitly declare it out of scope — before
"fixing" makes sense), and the handful of documentation-vs-reality drifts
(`SEC-134`, `SEM-060`, `EVD-122`, `EVD-073`) where the fix might be updating
the prose rather than the code, which is a decision for whoever owns that
sentence, not a triage call.

**Two big causes vs. a long tail: closer to the tail than the language-stack
triage found.** `C1` (raw exceptions, 12 cases) is the only cluster over 5
cases in this scope — nothing here rivals that triage's `C2` (11 cases) *and*
`C1` (float/Decimal, 4 cases) both landing above a 4.0 ratio. The two biggest
single-cause wins by clarity and confidence are `C2` (the ISO 4217 version
table — 2 cases, 1 repair, and about as concrete a bug as this triage found)
and `C6` (`SchemaVerifier`'s four blind spots — 5 cases, arguably the
highest-*strategic*-value cluster given `CLAUDE.md`'s "no migrations, the
schema files are the authority" doctrine, even though its cases-closed/effort
ratio is middling). 91 of 142 cases (64%) are one-offs — a materially longer
tail than the language stack's 47 of 116 (41%). That's a data point about
this stack, not a methodology gap: connectors, importers and lineage parsing
are each doing many small, independent things to many different data shapes,
and most of the defects found here are exactly that — one shape, handled
wrong, once each — rather than one habit repeated. The two things that *do*
repeat across files rather than concentrate in one (the raw-exception habit,
`C1`; and the two source-verified architectural findings in §4) are the ones
worth fixing first regardless of the ratio table, because each recurrence is
evidence the same blind spot exists everywhere nobody has tested yet, not
just at the twelve or so places this list happens to name.
