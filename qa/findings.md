# QA round 1 — findings

Ranked by what they cost a user, not by which surface found them. Every entry
names the agent that found it and whether it was reproduced by hand before being
acted on.

Fixed entries carry the commit. Open entries carry enough to reproduce.

---

## Fixed

### Q-01 · A piped password is not the password piped — **blocker**

`_read_password` did `sys.stdin.read().strip()`, taking the whole stream as one
value. Piping the password twice — the natural thing, because the interactive
path asks twice — stored a password containing a newline. The account was
created, the command printed `created alice`, and nobody could sign in to it.

Silent in both directions, which is what made it expensive: the CLI said
*created*, the console said *invalid credentials*, and neither was lying about
what it saw. Now one line, or two identical lines, or a refusal.

### Q-02 · The console cannot be signed into — **blocker**

`sign_in` took `form_field or tenancy.default_tenant`; `auth/sign_in.html`
renders no tenant field; so with the default unset the tenant was always `""`,
`authenticate` was never called, and every correct password got a 401. Passing
`tenant=acme-bank` did not help — that is a slug, and `authenticate` compares it
against an id, the same seam that broke `principal create --tenant`.

The tenant is now resolved from the form field as slug *or* id, then the
configured default, then — if there is exactly one estate — that one. A
single-estate install is the common case, and requiring somebody to name the
only tenant there is, in a field the form does not render, is how this happened.

### Q-03 · The sign-in page says nobody exists while principals do — **blocker**

`_no_way_in` returned `True` whenever the default tenant was empty, without
counting anything. The page announced *"Nobody has been created on this
installation yet"* while four principals existed, sending an operator to look
for a bug in `principal create`. It now distinguishes **no estates at all** —
true, and worth saying — from **several estates and no default**, where the
honest answer is that we do not know.

### Q-04 · Four by-parent reads leak across tenants — **critical**

`GET /datasets/{id}/attributes` with a valid key from another estate returned
**200 with the declarations in full**. Same for `/datasets/{id}/bindings` and
`/concepts/{id}/properties`. `AttributeDao.for_dataset`,
`ConceptPropertyDao.for_concept`, `BindingDao.for_dataset` and
`BindingDao.for_attribute` filtered on the parent and never on the estate.

The S2 fix scoped every by-*id* read on `VersionedDao` and missed the by-*parent*
reads on its subclasses — and the tenant sweep could not see them, because it
enumerates methods whose **first** parameter is `tenant_id`.
`TestEveryDaoReadTakesATenant` is the static half added alongside: every public
DAO read must accept a tenant somewhere, or be declared with the reason it does
not. Writing those declarations surfaced twenty more methods to examine; four
were the leaks, the rest are by-design or checked caller-side, and each now says
which.

### Q-05 · All four case studies crash — **blocker**

`cd case-studies/01-trading-book-sqlite && python run.py`, the command README and
QUICKSTART both give as "see it actually do something", died on a `TypeError`.
Behind it, `harness.serve()` calls `uvicorn.run()` — which calls
`asyncio.run()` — from inside a coroutine, so the console could never have
started even with the types right.

**Nothing under `tests/` exercised `case-studies/`.** They now run in the default
suite: ~2.5s each.

### Q-06 · `prama apikey` does not exist — **blocker**

The API's own 401 says *"Create one with `prama apikey create`"*. There was no
`apikey` group, so on a clean install the HTTP API could not be authenticated to
by any supported means. Found from both ends — the API agent following the
remedy, the operator agent looking for a way in.

Now issues, lists and revokes, with the plaintext shown once, `--principal`
required so every key is attributable, and a scopeless or invented-scope key
refused at creation rather than discovered on the first 403.

### Q-07 · `prama validators scan` named and never built — low

In `classify/plugins.py` for four waves. A guard now reads every `remedy=`
literal by AST and requires the commands they name to exist.

---

### Q-53 · `IS UNIQUE` did not test uniqueness — **blocker**

`ir/lower.py` mapped the `is_unique` operator to `IS NOT NULL` and left
`assertion_kind` as `"predicate"`, under a comment saying a unique-key predicate
cannot be a row predicate and *"the caller handles it"*. No caller did:
`_assertion` returned `"predicate"` for every `PredicateAssertion` without
looking at the operator. So

```
CHECK trades.uti IS UNIQUE  BECAUSE 'a UTI identifies one trade'
```

compiled to `COUNT(*) FILTER (WHERE NOT COALESCE(("uti" IS NOT NULL), FALSE))`
under the rendered English *"In trades, every uti is different from every
other."* One UTI repeated a million times passed, green, with evidence, and the
description on the record said uniqueness had been established.

This is the doctrine failure the project is named for — an artifact that builds,
validates, reads correctly and is wrong — and it shipped: the banking pack's
regime templates use that spelling and `contract/quality.py` maps
`duplicateCount`, `duplicatePercent` and `uniqueCount` onto it. The controls most
likely to be trusted without reading were the ones not being run.

Found by reading, not by running: `IS UNIQUE` appeared in no test in the
repository, so the full suite passed identically before and after the fix. It now
lowers to the one-column `unique_key` it always meant, taking that path's real
`COUNT(DISTINCT …)` test, and is asserted against the long spelling so the two
cannot drift apart.

Also fixed alongside: the parser discarded the negation, so `IS NOT UNIQUE`
parsed as `IS UNIQUE` — an author's mistake silently becoming its own opposite.
It is now carried and refused with a reason.

### Q-54 · The contract gate passed an empty file in `--json` mode — **blocker**

`contract check` refuses a data file with no rows, loudly: *"nothing was
checked."* The guard sat **below** the `if ctx.json_output:` early return, so
`prama --json contract check` — the spelling a build uses — skipped it. The gate
was open on exactly the path it exists to guard.

The narrowest reproduction is a contract declaring no properties: text mode exits
3, JSON mode exits 0. With columns promised, an empty file trips the
missing-column check by accident and the exit code comes out right for the wrong
reason, which is why this survived.

The emptiness is now decided before the output branches, and reported as its own
`checked` field, because a caller parsing the JSON could not otherwise tell
"nothing was checked" from "checked, and every promise held". On no rows the
column lists are empty rather than naming every promised column as missing —
that comparison is vacuous, and reporting it named the wrong cause.

The existing test covered the text path only, which is how the hole survived.

### Q-55 · `/capabilities` declared shipped features absent — high

The endpoint reported `pql`, `execution`, `evidence`, `monitoring`,
`reconciliation` and `connectors` as `False`, each annotated with the wave it was
due in, every one of which had shipped. Directly above the wrong values:

> Honest about what exists. A client that trusts this and finds it wrong will
> never trust it again.

Underclaiming is the same defect as overclaiming — the endpoint is wrong — and
harder to notice, because nobody complains about a promise you failed to make. A
client integrating against this would have refused to use features that work.

Each answer is now derived from the thing itself rather than restated, so a
capability that is removed stops reporting `True` without anyone remembering to
edit a dict. The test was a Wave-2 snapshot asserting `execution is False`; it
now asserts the property — no feature may be declared absent while its
implementation is importable — and would have failed the day Wave 5 landed.

### Q-56 · `config show --raw` warned on one path and not the other — medium

The warning that secrets are not redacted was printed after the `--json` early
return, so it appeared in text mode and not in JSON mode. `CommandContext` had no
stderr channel at all, so the warning could only go to stdout, where in JSON mode
it would corrupt the output a caller is parsing.

Reported as "`--raw --json` dumps unredacted secrets", which is not right: `--raw`
is gated behind `PRAMA_ALLOW_RAW_CONFIG=1` and redaction holds without it. The
real defect is smaller and still real — the loudest thing the command has to say
was inaudible on the path most likely to be piped somewhere.

`ctx.warn()` now writes to stderr, before the output, in both modes.

---

### Q-57 · A valid evidence window verifies as broken — **blocker**

I recorded EVD-049 as "not a defect" during the catalogue pass. That was
wrong, and the correction is worth stating precisely because the reasoning
failed in an instructive way.

`ledger.verify()` contains two checks. The **genesis** check is guarded —
`if str(payload.get("previous_hash", "")) != GENESIS and sequence == 0` — and
I verified that guard, at `ledger.py:197` and `verify_evidence.py:198`, and
concluded the finding was a misreading. It was the wrong check. Immediately
above the loop, `previous_hash` is seeded to `GENESIS` unconditionally, and
the **link** check at the bottom of the loop has no `sequence == 0` guard at
all. So the first record of any window whose sequence is not 0 is compared
against `GENESIS`, does not match, and is reported as breaking the chain.

Reproduced: a six-record chain verifies with no breaches; the untouched
window `[2:5]` of that same chain reports `link at seq 2 — this record does
not follow the one before it; the chain is broken here`.

This is not hypothetical. `Archivist.bundle()` (`retention.py:259`) exists to
export a *range* — its manifest carries `from_sequence` and `to_sequence`,
fields that have no meaning otherwise — and line 293 calls `verify()` on
exactly that range. Every archive bundle that does not begin at sequence 0
therefore reports itself as broken evidence.

The product's whole asset is that a verifier's word can be taken. A verifier
that cries wolf on valid evidence is one an operator learns to ignore, and an
ignored verifier is worse than none: it produces the habit of dismissing the
alarm that eventually matters. A false alarm and a false pass are the same
defect wearing different clothes.

The lesson for how I check these: I confirmed a guard existed, saw it was
correct, and stopped. The finding named a symptom, not a line; confirming one
plausible mechanism is sound is not the same as confirming the symptom does
not occur. Reproducing the symptom first would have cost one command.

---

### Q-58 · The `Co-Authored-By: Claude` commits are orphans, not history — **not a defect**

`OPS-074` reported two commits carrying the forbidden trailers, and I reported
the same thing from the same query. Both of us were wrong in the same way, which
is worth recording because the query looked conclusive.

`git log --all` includes `refs/original/`, the backup refs a previous
`filter-branch` leaves behind. The two commits — `07963c59` and `9fa19f16`,
dated 27 minutes before `.githooks/commit-msg` existed — lived only there. They
are ancestors of neither `develop` nor `main`, and the remote holds nothing but
those two branches.

Checked commit by commit rather than by grep: `develop` has 221 commits and
`main` 188, and **none** carries any Claude attribution. The hook has held since
the moment it was installed.

The orphans have since been expired and garbage-collected locally, so the query
that produced this finding now returns nothing.

The lesson is the same one as Q-57, one turn later: a query that names a symptom
is not a diagnosis. `--all` does not mean "all history", it means "all refs",
and the difference was the whole finding. I proposed rewriting 221 commits and
force-pushing two branches on the strength of it. Checking reachability first —
one `git merge-base --is-ancestor` — would have cost nothing.

---

### Q-59 · Evidence can be appended with an empty tenant — new, found while fixing B1

Not from the catalogue. `EvidenceDao.append` and `EvidenceDao.extend` both
declare `tenant_id: str = ""`, so a caller that forgets the estate writes
evidence attributed to `""` rather than being refused. Every current caller
passes one, so nothing is wrong in the ledger today; the defect is that the
signature permits it, in the one table whose whole value is that a record
belongs to somebody.

Found because the tenant-isolation sweep was strengthened from "accepts a
tenant" to "requires a tenant" while fixing `DB-201`/`DB-244`/`DB-245`, and the
new check immediately flagged `extend`. It flagged it as an unscoped *read*,
which it is not — `append` was in the sweep's `WRITES` exclusion list and
`extend` had been missed — but the underlying signature is worth fixing.

Deferred rather than folded into B1, which is about containment and secrets.
A batch that quietly grows to include whatever turns up next is a batch nobody
can review.

---

### Q-60 · The conformance suite had never met PostgreSQL — new, found during B3

While fixing the async engine I started a real PostgreSQL and ran the suite
against it. Two things followed, and both are worth recording.

**The `postgres` marker matched nothing.** `pyproject.toml` declares it,
`tests/conftest.py` declares `postgres_config`, and no test used either. So the
dialect with the broken async engine was also the dialect with no tests, which
is not a coincidence — DB-070 survived because nothing could have caught it.
`qa/regression-suite` now carries a `postgres`-marked test that connects for
real and skips cleanly when no server is reachable.

**The engine conformance suite fails on a real PostgreSQL.** With
`PRAMA_TEST_POSTGRES_DSN` set, `tests/backend/test_engine_conformance.py` fails
`modulo_on_a_negative` — which is `BE-024` from the language catalogue, found
independently by reading. The suite whose entire purpose is to prove the
engines agree had never been pointed at one of the three engines it names.

That belongs to B6, where the interpreter/SQL divergences are grouped, and it
arrives with a second source of evidence rather than one.

**A correction to my own method.** My first run with a DSN produced 25 failures
and 37 errors, and I nearly recorded that as a finding. The cause was my DSN:
the repository's convention is a plain `postgresql://` libpq string, and I had
passed the `postgresql+asyncpg://` driver form. The regression test now derives
the async URL itself so one variable serves both spellings. Twenty-five
failures that are your own setup look exactly like twenty-five defects until
you check.

---

### Q-61 · PCK-199 is not a defect — the partial case is deliberate and surfaced

The domain agent recorded `PCK-199` as a defect: one control passing and two
never running reports `PROVEN_CLEAN`. I started to change it, and a test stopped
me — `test_a_partly_run_obligation_is_not_unproven`, whose docstring states the
design directly: *"Two controls, one run. Something has been established, so
this is not the 'nothing has run' state — but the one that did not run is
counted."*

The three states answer whether anything has been *established*.
`ADDRESSED_UNPROVEN` means nothing ran; a partial run is not that. The
partiality is carried by `never_ran`, and `ObligationStanding.describe()`
renders it: `"3 control(s); 1 passed, 0 failed, 0 not established, 2 never
ran."`

The catalogue's own **Expected** read "something other than `PROVEN_CLEAN`, **or**
`never_ran` surfaced prominently". The second branch is met. The case was
written from reading the enum and not the description method beside it.

Recorded rather than quietly dropped, because "a test disagreed with me" is the
outcome I most want to notice. Changing the state would have passed the QA case
and broken a decision somebody made on purpose and wrote down — which is the
failure mode of fixing defects by their symptom.

---

### Q-62 · PostgreSQL cannot take a modulo of a double — new, found in B6

Not in the catalogue. PostgreSQL's `%` is defined for integer and numeric and
not for double precision, so `notional % 3` on a DOUBLE column raises *operator
does not exist: double precision % integer*. DuckDB and SQLite both accept it.

So the corpus case `modulo_on_a_negative` — which exists specifically to prove
the three engines agree about remainders — ran on two of them and could not run
on the third. `PostgresDialect.modulo` now casts both sides to NUMERIC, which
keeps a fractional dividend fractional; truncating to integer would have
silently changed what the control asks.

Found only because B3 pointed the conformance suite at a real PostgreSQL for the
first time. The suite whose entire purpose is cross-engine agreement had never
met one of the three engines it names, which is recorded separately as Q-60.

Two cases were added to the corpus so this cannot recur silently:
`division_by_zero` and `modulo_on_a_fraction`. Both fail against the old code.

---

### Q-63 · `plugins.disabled` works in the server and not the CLI — CLOSED

Wiring the plugin loader (CFG-036) exposed an asymmetry rather than removing
one. `create_app` reads `plugins.disabled` and passes it to `install_shipped`;
`prama.cli.main` cannot, because it installs before argparse has run and so
does not yet know whether `--config` names a different file. Reading a
configuration the caller is about to override would be worse than reading none.

So a validator switched off in configuration stays off in the server and loads
in the CLI. Disabling a plugin is a deployment decision and the server is where
it matters, which makes this tolerable and not correct.

The real fix is to load plugins lazily, on first use of the validator registry,
where the configuration is known. That is a refactor rather than a repair, and
it is not the kind of change to make inside a batch about inert settings.

**Closed in Batch D, and it needed no refactor at all.** The premise above —
that honouring the setting requires lazy loading — was wrong. `install_shipped`
had exactly one ordering requirement, *before any command runs*, and
`Application.run` satisfies it while also being after `--config` is parsed: the
`CommandContext` already exists there, and `run` was already reading
`ctx.config` for the logging level. Moving the call from `prama.cli.main` into
`Application.run` removed the asymmetry in two lines.

Checked before moving: nothing in `configure()` on any command reads the
registry, so building the parser first costs nothing, and CLI startup is
unchanged (1.3–1.8s either way, the spread being machine noise).

Worth recording as a caution about findings in general. This one carried a
confident prescription — "the real fix is to load plugins lazily" — written
while looking at the constraint rather than at the requirement, and it would
have bought a refactor to achieve what a move achieved. A finding's diagnosis
deserves the same scepticism as a test's green.

---

### Q-64 · `IS FRESH` has no execution strategy at all — **closed 2026-09-28**

> **Closed.** Freshness is measured on the column that records arrival: `CHECK t.loaded_at IS
> FRESH WITHIN 30 MINUTES OF '06:30' CALENDAR 'TARGET2'` lowers to `MAX(loaded_at)`, the
> judge finds the cycle due on the business calendar, and the verdict is PASS or FAIL. The
> instant of evaluation is recorded as a metric, so a replay reaches the same verdict. A
> rhythm names its arrival column (`Rhythm.arrival_column`). A rhythm without one generates
> no freshness control and reports why, instead of one that could never be red. The strict
> xfail in `tests/derive/test_generator.py` passed and was removed. The executed verdicts
> are in `tests/backend/test_freshness.py`. Found on the way: `CHECK t.col IS FRESH` rendered
> as `CHECK t IS FRESH`, dropping the column; fixed.

`PQL-083` recorded that a freshness plan carries no `violating_rows` metric, so
every freshness control is permanently indeterminate. Looking for the fix found
something worse: **nothing handles freshness at execution anywhere.** There is
no branch for it in `execute/run.py`, none in `backend/execute.py`, and no
`_freshness_verdict` beside the row-count, unique-key and dependency ones.

So `IS FRESH WITHIN 4 HOURS` parses, type-checks, lowers to a plan with an
`assertion_kind` of `"freshness"`, compiles to a query that counts rows, and is
then judged by a threshold reading a metric nobody emitted. It cannot pass and
it cannot fail.

This is the `BE-054` shape again — syntax the grammar accepts that no engine
runs — but one level deeper: the SQL compiles, so it does not even announce
itself as unsupported.

**It blocks a shipped template.** `gdpr-retention-floor` names `DATE_SUB`,
which no pack registers, so it cannot compile either. The obvious repair is to
express a retention floor as `IS FRESH WITHIN {retention_days} DAYS` — it says
exactly the right thing and needs no new function — and that would move the
template from "cannot compile" to "can never produce a verdict", which is worse
because it is quieter.

Deferred deliberately. Implementing freshness means deciding what it is
evaluated *against* — a snapshot time, a business date, the clock — and PQL
refuses the clock because evidence must replay. That is a design decision about
the language, not a repair, and it should not be made inside a batch about
domain packs.

Recorded here, and pinned in `qa/regression-suite` as a strict xfail so the day
somebody implements freshness, the test that proves the template is broken will
start failing and force this note to be closed.

---

### Q-65 · INC-010 needs a product decision, not a repair — half closed

`_shared_ancestor` orders candidates by `(vote count, name length)`, so the
*broadest* shared ancestor wins. Its own docstring forbids exactly that:
"Deepest rather than any: everything shares 'the raw feed' eventually, and an
incident about the raw feed when the fault is in one derived column sends
people to the wrong system." The ordering says the opposite of the paragraph
above it.

I changed it to prefer depth, measured properly from the graph rather than
guessed from the length of a name, and three tests failed — including
`test_one_upstream_defect_produces_one_incident`, which is the module's stated
acceptance criterion. In that fixture one feed column fans out to forty-eight
findings whose *only* common ancestor is the raw feed, so naming it is correct.

The two requirements conflict:

- one upstream defect must produce one incident, which wants the broadest
  ancestor when everything genuinely shares it;
- two findings sharing a nearer derived column should be their own incident,
  which wants the deepest.

Both are right, and choosing between them per-case is a grouping decision —
whether those two findings *split off* — not a question about which name to put
on a group already formed. That belongs in `_by_ancestor`, and it changes how
many incidents an estate sees on a bad morning, which is a product decision
about alert volume rather than a defect to repair quietly.

Reverted rather than left half-done. `INC-011`, the missing time window, is
independent and is fixed: two failures three days apart no longer merge because
everything in a warehouse shares a feed eventually.

---

## Open

Ranked. Each was reported by the agent named, and awaits reproduction before
remediation — this list is the work queue, not a set of confirmed defects.

### Correctness — the paths that decide "nothing to report"

The data-path agent's summary of its own findings is the sharpest line in the
pass: **"the paths that decide *nothing to report* are weaker than the paths
that decide *something to report*."**

| # | Finding | Reported by |
|---|---|---|
| Q-08 | A control on a **non-existent column** reports `pass` over 1,000 rows on SQLite (an unknown quoted identifier resolves to a string literal); the same control is an `error` on DuckDB | data path |
| Q-09 | An **empty table** reports `pass` — the absolute-threshold path, which every predicate control lowers to, is the only judgement path with no empty-scope guard | data path |
| Q-10 | The `IS VALID` **lower-bound caveat is attached only when the verdict would be `pass`** — so understated counts are recorded as completed measurements with no caveat | data path |
| Q-11 | `FOR EACH` is judged on `rows[0]` alone — one segment of five decides, and the samples in the same record contradict its own metrics | data path |
| Q-12 | `TREAT UNKNOWN AS PASS` does not reach `IS VALID` on SQLite (the REGEXP hook returns `False` for NULL, against its own docstring) | data path |
| Q-13 | Uniqueness and functional-dependency records carry no `violating_rows` | data path |
| Q-14 | `compile` refuses `IN CODELIST` with a false remedy while `run` executes it | data path |
| Q-15 | Sealed evidence does not carry the threshold: four records, identical metrics, two pass and two fail | data path |
| Q-16 | Bare `CURRENT_DATE` passes the non-determinism guard | data path |

### Tenancy and safety

| # | Finding | Reported by |
|---|---|---|
| Q-17 | `--tenant` accepts a non-existent id on seven of eight commands and reports a plausible empty result at exit 0; `control run --tenant 01NOSUCH` **writes a row into the evidence ledger** for a tenant that never existed | CLI |
| Q-18 | `bundle verify` exits 0 on a bundle containing a file nobody signed for, and marks it `"trustworthy": true` | CLI, operate |
| Q-19 | `bundle verify --publisher-key` exits 0 on an unsigned bundle — stripping the signature downgrades verification to a pass | CLI |
| Q-20 | `db verify` cannot see an **added column**, on SQLite or PostgreSQL — extra tables are reported, extra columns are invisible | CLI, operate |
| Q-21 | The steward role is inert: 45 of 48 console routes gate on `declaration:*` alone, so a steward is refused every write the console offers, and auditors read `/incidents` without `incident:read` | console |

### The error contract

| # | Finding | Reported by |
|---|---|---|
| Q-22 | 37 of 138 API failure responses are not `problem+json` — `RequestValidationError` and Starlette's `HTTPException` are unmapped, so validation failures, unknown paths and wrong methods return `{"detail": …}` with no `code`, `remedy` or `correlation_id` | API |
| Q-23 | Three 500s: a naive `valid_at` datetime hits a *write* guard on a *read*, and deep JSON hits orjson's recursion limit | API |
| Q-24 | `X-Correlation-Id` is missing on exactly the 500s — `correlate` is registered inside `ServerErrorMiddleware`, so it never runs when `call_next` raises | API |
| Q-25 | `known_at` alone is silently discarded, returning the *current* version for a year-2000 belief query — a wrong answer rather than a refusal, in the product whose thesis is evidence replay | API |
| Q-26 | 403/404 render as raw RFC-7807 JSON in the browser; there is no HTML error page | console |
| Q-27 | Two reproducible console 500s: an unvalidated `shape` reaching a DB `CHECK`, and the break-disposition error path crashing in `url_path_for` | console |
| Q-28 | 22 tracebacks reach the terminal from the CLI, mostly "directory where a file is expected" and malformed documents | CLI |

### Operability

| # | Finding | Reported by |
|---|---|---|
| Q-29 | `/api/v1/health` returns 200 `{"status":"ok"}` after the SQLite file is **deleted** — and the Helm chart uses it as both liveness and readiness probe | operate |
| Q-30 | `serve --port 99999` logs "Uvicorn running", never binds a socket, and stays alive | CLI |
| Q-31 | `serve` prints its success banner after every failure — port in use, bad host, refused secret | CLI |
| Q-32 | `serve`'s banner and its "no tenant configured" warning are never emitted when stdout is not a TTY | operate |
| Q-33 | **No documented backup procedure anywhere**; a naive `cp` of the WAL database during writes produced a backup with 7 of 37 rows that passes `PRAGMA integrity_check` | operate |
| Q-34 | Nothing exports an evidence bundle, though the runbook tells auditors to verify one | operate |
| Q-35 | The first literal stop in QUICKSTART is `prama version` → `command not found`; the uv path never activates the venv | operate |
| Q-36 | Four global flags are absent from the CLI reference that says "if a flag is not here it does not exist", and `generate_docs.py --check` passes anyway | operate |
| Q-37 | `--json` on a PQL syntax error emits prose, breaking the JSON contract at the CI integration point | CLI |
| Q-38 | `mcp serve` has no start-up schema check and hands raw SQLAlchemy errors, including generated SQL, to the MCP client | CLI |
| Q-39 | `pack parse --format iso8583` reports "No structural defects found" for a FIX message; `pack parse` always exits 0 | CLI |
| Q-40 | Relative `schema_dir` resolves against cwd rather than the config file; `db info`/`db verify` create database files as a side effect | operate |

### Interface

| # | Finding | Reported by |
|---|---|---|
| Q-41 | Every role is offered every action and then refused it | console |
| Q-42 | No sign-out control exists anywhere in the chrome | console |
| Q-43 | A control can be silenced `until not-a-date`; suppressing a nonexistent control 303s silently while activate 404s | console |
| Q-44 | Dataset names are neither trimmed nor bounded — 5,000 characters into a `VARCHAR(255)` is fine on SQLite and would raise on PostgreSQL | console |
| Q-45 | No security headers at all | console |
| Q-46 | Authorisation runs after body parsing, so a read-only key can enumerate the write schema via 422s | API |
| Q-47 | `page.total` ignores the filter beside it | API |
| Q-48 | Declaring a `reconciles_with` relationship generates nothing, though the console instructs you to do it | data path |


### From the catalogue reading (round 2 authoring)

Surfaced by reading the code to write test cases, not by executing anything.
**Each was reproduced by hand before being listed here**, and one of the
agent's four headline findings did not survive that — recorded below, because a
findings list that only keeps the hits is a list nobody can calibrate against.

| # | Finding | Severity | Verified |
|---|---|---|---|
| Q-49 | `default_resolver()` has no `file_root`, so `file:///etc/hostname` resolves — any file the process can read. `FileSecretProvider`'s own docstring says "without a root it would be a way to read any file the process can read", and the default is exactly that | **Critical** | Reproduced: returned the host name |
| Q-50 | `bundle.verify` computes `intact = manifest.content_hash == sha256(manifest.content())`, and `content_hash` is a *computed property* — so it is `X == X` and can never be false. The T11 tautology, in the artefact a bank checks before installing | **Critical** | Reproduced by reading: `content_hash` at `bundle.py:138` |
| Q-51 | `core/pjson.canonical` serialises with `ensure_ascii=False`; `scripts/verify_evidence.py::canonical` uses `json.dumps`'s default, which is `True`. Any record containing a non-ASCII character — a dataset named `posições_eod` — hashes differently in the two implementations, so the independent verifier reports a forgery | **Critical** | Reproduced: differing bytes and differing digests |
| Q-52 | `RedactionFilter` substitutes over `record.msg` only, never `record.args`, so the lazy-formatting logging call the standard library recommends writes credentials out in full | **High** | Reported, not yet reproduced |

**Not a defect — reported as the headline P1 and wrong.** The agent claimed
`Ledger.verify` and `scripts/verify_evidence.py` compare the first record's
`previous_hash` against `GENESIS` *unconditionally*, so every bundle not
starting at sequence 0 would report a broken chain at its own first record.
Both call sites guard with `and sequence == 0` — `ledger.py:197` and
`verify_evidence.py:198`. The construction was misread in both places.

Worth stating plainly: three of that agent's four headline findings were real,
including a path traversal in secret resolution, and the one it led with was
not. That is a good hit rate for a reading pass and a bad reason to trust one
without reproduction.

### Q-66 · `/controls/check` demands an authoring scope to lint text — open, found in round 3

Round 3's interfaces pass put seven console cases into 403 where round 2 had
them at 200. The cause is not damage: before B7 the console **authenticated a
session and then checked nothing**, so every page rendered for anybody who got
through the door. Adding `ui_scope` turned pages that always rendered into pages
that can refuse, and the round-2 harnesses — which signed in as `owner` — began
to be refused. That is the guard working.

One of the refusals is worth a decision rather than a fixture change.
`POST /controls/check` and `/controls/completions` now require
`control:propose`. Neither writes anything: `check` parses, type-checks and
lints a PQL string and returns findings. `owner` holds `control:approve` and
`control:read`, and deliberately not `control:propose` — the role split is
"the steward authors, the owner approves".

So the business owner — the persona in the first sentence of `docs/corpus/00`, the
"business-owned" in the product's own description — can activate a control but
cannot lint the text of one before approving it. Approving what you were not
permitted to check reads backwards, and the natural workaround is to grant
owners `control:propose`, which erases the separation the two scopes exist to
create.

`control:read` is the defensible requirement for both routes: they read the
language, not the estate. But that is a statement about what the role boundary
*means*, so it belongs to the product rather than to a QA pass, and it is
recorded here instead of changed. Related: [[Q-63]].

**Not** a regression. The round-2 PASS was a page that could not say no.

### Q-67 · The role built to attest cannot read an attestation — new, found in round 3

`BUILTIN_ROLES["owner"]` grants `attestation:sign` and not `attestation:read`.
Measured across all four built-in roles:

| role | `attestation:sign` | `attestation:read` | both |
|---|---|---|---|
| `admin` | yes | yes | yes — via `*` |
| `owner` | **yes** | **no** | **no** |
| `steward` | no | no | no |
| `auditor` | no | yes | no |

So the only principal who can sign an attestation and then look at it is the
wildcard admin. An `owner` — the role whose whole purpose is to attest, and the
persona the product is named for — can sign, and cannot open the draft before
signing it or the signed record afterwards through the console.

`tests/architecture/test_scopes.py` does not catch this, and is right not to by
its current rule: it checks that no role grants a permission no route requires,
and that no route requires a permission no role can hold. `attestation:read` is
held by `auditor`, so both directions pass. The missing rule is the third one —
**a role must hold the reads implied by the writes it holds.** Signing a thing
you cannot read is not a permission set anyone would write down on purpose.

Found because the B7 scope work made the console able to refuse at all; before
it, every page rendered for anybody who got through the door, so the gap existed
and could not be observed. Same shape as [[Q-66]]: the guard did not create these
problems, it made them visible.

The repair is one entry in `BUILTIN_ROLES` plus the third architecture rule, and
the counterfactual is cheap — grant, assert the console renders, revoke, assert
403. Batch it with Q-66 if Q-66 is decided as a change.

### Q-68 · A raw Python exception escapes where a typed error is promised — the one batch worth doing first

Found by triaging round 3's standing failures **by cause across areas** rather
than by area, after a first attempt at clustering grouped four cases together
that turned out to have four unrelated causes.

**33 of the 237 standing failures in the three completed areas are this one
class.** The product's own rule, stated in `CLAUDE.md`: *"No exception is
swallowed. The unit of work translates failures into the Prama error taxonomy
and they propagate; a DAO never returns a sentinel meaning 'something went
wrong'."* These are the places where nothing translates.

| area | count | shape |
|---|---:|---|
| interfaces | 18 | `Traceback` to the terminal from `prama` itself; `CLI-208` is a `KeyError` where a missing manifest field should be named |
| language | 14 | `TypeError`, `KeyError`, `IndexError`, `ValueError` out of the IR and backend layers |
| semantic | 1 | `SEM-222`: a raw `sqlalchemy.exc` reaches the caller, in the layer whose entire job is to translate it |

`CLI-017` is the meta-case and it measured itself: of **224 CLI invocations
logged across every harness script in round 3, 14 produced an uncaught Python
traceback** rather than a typed refusal. The census lives in
`qa/harness/interfaces/cli_call_log.jsonl`.

**Why this batch and not another.** It has one cause, so one repair closes many
cases — which the previous ten batches conspicuously did not manage, closing 25
of 247. It needs no product decision: unlike [[Q-63]], [[Q-64]], [[Q-65]] and
[[Q-66]], nobody has to rule on what the right behaviour is, because the rule is
already written down. And the counterfactual is unusually strong: the assertion
is "zero tracebacks across the full invocation census", which fails loudly today
and cannot quietly stop checking the way a per-case assertion can.

The trap to avoid is a bare `except Exception` at the CLI boundary that formats
anything as a refusal. That would turn 33 loud failures into 33 silent ones and
pass the test — the flattering direction. Each site needs the specific typed
error naming what was wrong, and the top-level handler is the last resort that
should still be reached by nothing.

### Q-69 · A performance gate that straddles its own budget — new, found in round 3

`SCR-042` asserts a scoring pass completes inside a 30-second budget. Across
eight runs of code `git log` proves unchanged — zero commits to
`src/prama/score/trust.py` since round 2 — the observed time ranged from
**26.6s to 49.9s**. The budget sits inside the spread.

So the case passes or fails on machine load. Round 3 recorded it FAIL to match
round 2 rather than credit a coin flip, which is the right call for a log whose
job is comparison, but it leaves a gate that cannot answer the question it
was written to ask.

This is the counterfactual rule pointed at a timing assertion. A control that
cannot fail is worth nothing; a control that fails at random is worse, because
it trains whoever reads it to ignore a red result. The repair is one of:

- measure work rather than wall-clock — rows scanned per unit of a calibrated
  reference operation, so the number does not move with what else is running;
- raise the budget above the observed ceiling and label it a smoke bound, which
  is honest but concedes the case no longer measures performance;
- mark it `slow` and run it alone, on the model of
  `PRAMA_MEASURE_ESTATE_MAP=1` — the repository already has this pattern for
  exactly this reason, and this case predates it.

The third is closest to existing practice and cheapest. Note that the round-2
and round-3 logs both record FAIL, so this has never been a passing case; it
is being recorded now because round 3 is the first time anyone ran it eight
times and noticed the verdict was not stable.

### Q-70 · ULID monotonicity breaks under contention — new, found in round 3

`UlidFactory.new()` reads the clock **outside** the lock that protects the
state the reading is compared against (`src/prama/core/ids.py:48-63`):

```python
def new(self) -> str:
    ms = self._clock.epoch_millis()      # line 49 -- outside
    with self._lock:                     # line 50
        if ms == self._last_ms: ...
        else:
            self._last_ms = ms           # a stale ms is written back
```

The interleaving, with two threads either side of a millisecond boundary:

1. **A** reads `ms = 100`, and is descheduled before taking the lock.
2. **B** reads `ms = 101`, takes the lock, sets `_last_ms = 101`, emits an id.
3. **A** takes the lock. `100 != 101`, so it takes the `else` branch, sets
   `_last_ms = 100` — **regressing the high-water mark** — and emits an id
   stamped 100, which sorts *before* the id B already issued.

Confirmed by execution: 8 failures in 15 runs under heavy contention (16
threads, 100k ids), 25 passes in 25 runs in isolation. `git diff
ec16cfe..03dcf7c -- src/prama/core/ids.py` is empty, so this is pre-existing
and not remediation damage; round 2 recorded `CFG-168` as PASS because it
never ran the case under load.

**Why it matters — corrected in round 4, because the first version of this
paragraph was wrong.** It originally read: "the evidence ledger is a *sequence*,
and `Archivist.bundle()` exports a **range**, so an id that sorts before one
already issued is not cosmetic". Round 4's trust agent checked rather than
accepted it and found the ledger's `sequence` is a plain `int` counter
(`evidence/ledger.py:58`) with **no ULID import anywhere in the evidence
package**. The chain and the minting path are architecturally decoupled. The
severity argument was invented from the shape of the words "sequence" and
"range", not read from the code.

What the defect actually costs, from the two docstrings that state it:
`core/ids.py` — "they sort by time, so a B-tree index on a primary key is
append-friendly"; `UlidFactory` — "several stores rely on id order to page
deterministically". So: non-deterministic paging in those stores, and lost index
locality. Real, worth the one-line fix, and narrower than first claimed.

Recorded this way rather than quietly edited because a findings file that
silently improves its own reasoning is one nobody can calibrate against — and
because the error is instructive. It is the same move the QA rounds keep
catching in the product: a plausible claim, asserted from adjacency rather than
established by reading, that nothing downstream checks.

The repair is to move the clock read inside the lock — one line. The
counterfactual already exists and is unusually good: the case fails 8 times in
15 under contention against the current code, and must pass 25 of 25 after.
Note that a fix verified only in isolation proves nothing here, since the
unfixed code also passes 25 of 25 that way.

Second instance of the load-dependent class, with [[Q-69]]. Both were recorded
as PASS or FAIL by a single run before anyone ran them repeatedly.

### Q-71 · Four producers emit freshness controls, and four tests claim they run — tests fixed, freshness still open

Found while implementing [[Q-64]]'s interim — make `IS FRESH` refuse at lowering
rather than compile to a control that can never answer. The refusal was expected
to be a contained change. It is not, and what it breaks is the finding.

Removing the `FreshnessAssertion` branch from `ir/lower.py` so it falls through
to the existing "cannot yet be lowered" refusal fails exactly four tests:

| Test | The producer it covers |
|---|---|
| `tests/derive/test_generator.py::test_every_generated_control_lowers_to_a_plan` | the Γ generator, from a declared rhythm |
| `tests/importers/test_importers.py::…test_every_control_lowers_to_a_runnable_plan[soda]` | the soda importer |
| `tests/propose/test_end_to_end.py::test_every_proposed_control_would_actually_run` | the proposer |
| `qa/regression-suite/domain/test_shipped_templates_resolve.py::test_every_template_compiles_once_its_placeholders_are_filled` | shipped template `mifir-t1-report-arrives` |

So freshness is not a language corner nobody reaches. **Declaring a rhythm
generates one. Importing from soda generates one. The proposer proposes them.
Three shipped banking templates use `IS FRESH`** — `packs/banking/obligations.py`
and two in `packs/banking/regimes.py`.

**The second half is worse than the first.** Read those four test names again.
`test_every_proposed_control_would_actually_run`. `…lowers_to_a_runnable_plan`.
They assert that lowering *succeeds* — and lowering a freshness assertion does
succeed. It returns a plan, the plan compiles to real SQL, the SQL runs, and the
verdict is then read from a metric nobody emitted. Every one of those tests
passes today on a control that cannot pass and cannot fail.

Four tests named for runnability, none of which checks it. This is the house
failure mode exactly — *assert the rendered artefact, not the intent* — sitting
inside the tests written to enforce it.

**What this does to Q-64's options.** "Refuse loudly until freshness is
implemented" is no longer the cheap interim it looked like: it withdraws a
shipped MiFIR template and breaks three generators. The remaining choices are

- implement freshness against `Snapshot.captured_at`, which already exists on
  every evidence record and carries an `exact` flag — deterministic, replayable,
  and requiring no new concept in the language; or
- keep lowering, but have the verdict name *freshness has no execution strategy*
  rather than fall out of an absent `scanned_rows`, so the silence becomes a
  stated indeterminate.

The second is small and honest and leaves the templates shipping. The first is
the actual repair. Either way the four tests above need to assert a verdict
rather than a successful lowering, and that change should land first — it is
the control that would have caught this.

### Q-72 · `unanswerable()` — the control that would have caught Q-71

Landed as part of [[Q-71]]'s repair, recorded because it is the reusable half.

`backend/execute.py::unanswerable(plan)` returns why a plan can never reach PASS
or FAIL, or `""` when it can. It derives the answer from `VERDICT_METRICS` — the
metrics each dedicated verdict rule reads — and the plan's own declared metrics,
rather than from a restated list of supported assertion kinds. A restated list
is precisely what lets a new kind arrive and be judged by a threshold on a
metric nobody emits, which is how freshness got here.

The three producer tests now assert it for every kind **except** freshness, and
freshness is pinned by one strict xfail. The split matters: marking the whole
test xfail would have suspended the check for every other assertion kind in
order to tolerate one, and the next kind to arrive broken would have been
tolerated with it.

**Why a control that returns INDETERMINATE forever is worse than one that
refuses.** It occupies a line on a scorecard and contributes nothing, and
nobody investigates a control that has never been red. A refusal at least sends
somebody to the language. This is the same asymmetry the QA rounds keep
finding — *the paths that decide "nothing to report" are weaker than the paths
that decide "something to report"* — expressed in the verdict layer.

Still open, and deliberately not attempted inside a fix batch: freshness itself.
It needs `MAX(column)` compiled across three dialects whose date arithmetic
already disagreed once (`B6`), the snapshot's `captured_at` carried into the
verdict as a metric, a `_freshness_verdict` beside the other three, and a
decision about `IS FRESH` with no column named — which has nothing in the data
to measure and would otherwise fall back on the wall clock the language refuses.
That is a wave, not a batch.

### Q-73 · The incident tiebreak ranked columns by the length of their names

Batch D, from [[Q-65]]. `_shared_ancestor` ranked candidates by
``(vote count, len(key))`` — how many findings share the column, then **how many
characters are in its name**. The docstring says what the second term is for:

> Deepest rather than any: everything shares "the raw feed" eventually, and an
> incident about the raw feed when the fault is in one derived column sends
> people to the wrong system.

Name length is a proxy for depth only by coincidence, and the coincidence fails
in the ordinary direction: staging and ingestion columns carry the longest names
in most warehouses, and they are the shallowest things in the graph. On a shape
where `staging_raw.ingested_source_column` feeds `d.m`, which feeds both
findings, the old ranking chose the staging column — naming the raw feed when
the fault is in the derived column, which is the exact failure the docstring was
written to prevent.

Depth now comes from the lineage graph: how many sources a candidate has of its
own. A raw feed has none; a derived column has some.

**The counterfactual nearly did not exist.** The first scenario written to prove
this used `raw.feed` → `derived.mid`, and the old code passed it — `derived.mid`
is both deeper *and* longer, so the two rankings agree and the test proved
nothing. The regression test therefore uses a long-named shallow column and a
short-named deep one, which is the only shape where the rankings disagree, and a
second test renames the columns and asserts the verdict does not move: a
correlation's answer should be a property of the lineage, and under the old
tiebreak it was a property of somebody's naming convention.

**What is still open in [[Q-65]]**: the ordering between broadest and deepest
when the vote counts genuinely *differ*. One upstream defect must produce one
incident; two findings sharing a nearer derived column deserve their own. Those
conflict, and resolving them needs incidents that can have a parent — group by
deepest, link to a root, alert on the root — which changes what an incident is
and touches alerting, the console and the API. A wave, not a sort key.

### Q-74 · A failing test that skipped on every gate for a day

Found by `scripts/sync_test_counts.py`, which refused to write a number into the
README because the suite was not green — and it was not green in a way six full
gate runs had reported as green.

`tests/deploy/test_helm_chart.py` skips when `helm` is not on `PATH`, which is
correct and is announced loudly. Today a QA agent fetched a real helm binary
into `~/.local/bin` to run the `OPS-` cases by hand. The gate runs I launched
did not have that directory on `PATH`; the sync script's run did. The arithmetic
is the whole story:

| run | passed | skipped | failed |
|---|---:|---:|---:|
| my gate | 4,963 | 117 | 0 |
| sync | 4,983 | 96 | **1** |

Twenty-one tests moved from skipped to run, and one of them failed.

**What it caught.** `test_sqlite_with_one_replica_is_allowed` asserted that a
bare sqlite install renders. The `OPS-014` fix made the chart refuse it, on good
grounds: `readOnlyRootFilesystem` is on, so sqlite has nowhere to write, and an
`emptyDir` default would start a pod that loses the evidence ledger on its first
restart. The test encoded the pre-fix expectation and had been failing, unseen,
since that fix landed.

The test is now two: the evaluation path renders *with* `persistence.enabled=true`
and produces a `PersistentVolumeClaim`, and the refusal without it must name the
flag and say what is lost. The second half exists so that "update the test to
match the chart" cannot quietly become "accept whatever the chart does" — the
original concern was that the chart stay usable for the first thing anybody
tries, and that concern is still asserted.

**The transferable lesson is about skips, not helm.** A skip is a test that
reports neither pass nor fail, and a suite summarised as "4,963 passed" reads as
a green suite whatever the second number says. This is the same asymmetry the QA
rounds keep finding — *the paths that decide "nothing to report" are weaker than
the paths that decide "something to report"* — and here it hid a real failure
from six consecutive gates.

Worth noting what saved it: a script that **runs the suite rather than trusting a
recorded number**, and that refuses to publish a count from a red run. Its own
docstring says why — "a count taken from a red run is a claim about a product
that does not work". It was written to stop a number rotting and it caught a
defect instead.

### Q-75 · Two harnesses that reimplemented the product instead of calling it

Round 4, found independently by two agents in one afternoon, in unrelated files.
Recorded together because it is one defect wearing two coats, and because both
were invisible while green.

**`qa/harness/platform-core/cfg_165_176.py` (`CFG-168`).** Its `_TracedFactory`
did not call `UlidFactory.new()` at all. It was a hand-copied reimplementation
of the algorithm — clock read outside the lock, `==` rather than `<=` — written
in round 3 to get an honest trace of mint order without a racy append. It
described the shipped code accurately *at the moment it was written*, because
the shipped code was that algorithm. It describes nothing now. Re-run unmodified
against the fixed tree it reports `strictly increasing=False` in 9 of 10 trials,
and would have printed as a **regression that does not exist**.

Rewritten to wrap the real, unmodified `new()` with a tracing lock — true
serialisation order, zero product logic duplicated. 100,000 ids from 16 threads,
strictly increasing, on 5 consecutive runs including 3 under deliberate CPU load,
plus a jitter-clock variant returning a reading at-or-below the high-water mark
40% of the time. That is the verification `Q-70`'s fix deserved and had not had.

**`qa/harness/interfaces/ui_common.py`.** `UiEnv.BUILTIN_ROLES` was a hand-copy
of `prama.cli.principal.BUILTIN_ROLES`, and had not gained owner's
`attestation:read`. Verdict impact: zero. Consequence: the harness **could not
have exercised `Q-67`'s fix**, because its owner role was the old one. The fix
was verified for the first time only when the agent tested a real `owner`.

**Why this class is worse than an ordinary broken test.** A test that
reimplements what it tests passes for as long as the copy and the original agree,
and *diverges silently at exactly the moment the original changes* — which is the
moment a test is supposed to speak. Both of these were green. One would have
reported a phantom regression, the other quietly certified a fix it never
touched.

It is also this project's own doctrine turned on its tests. `CLAUDE.md` says
**derive, never restate** — "anything restated in a second place will drift,
silently, in the flattering direction". Both harnesses restated. The flattering
direction was, in one case, a false alarm and in the other a false assurance.

**The rule to apply going forward:** a harness may build fixtures, drive
interfaces and read output. It may not contain a second copy of the logic under
test. Where a harness needs the product's own table — roles, scopes, calendars —
it must import it rather than transcribe it.

### Q-76 · A bundle's declared range is not checked against what it contains — FIXED

Found in round 4 by the trust agent while going beyond the catalogue in the area
[[Q-70]] had put under suspicion. **Not caused by batches A–D**, and not scored
against any case — it is outside the catalogue's scope, which is why nothing had
looked.

`Bundle.check()` validates the record count, the content digest, the hash chain
and the head. It does **not** cross-validate `manifest.to_sequence` against the
sequence of the payload's actual last record. A manifest can therefore claim a
range it does not contain, and the bundle verifies clean.

Why that deserves a case of its own: a bundle is the artefact handed to an
auditor, and the range fields are how the auditor knows *which period they are
looking at*. Every integrity property the bundle checks is about the records
being unaltered; none is about the records being **the ones the manifest says**.
A payload that is internally perfect and mislabelled passes today — and
mislabelling is the cheaper attack, because nothing has to be forged, only
described wrongly.

The repair is a comparison, not a mechanism: `to_sequence` must equal the last
record's sequence and `from_sequence` the first. The counterfactual is equally
cheap — export a genuine range, edit one integer in the manifest, require
`check()` to refuse. Compare [[Q-50]], where `intact` compared a computed
property against itself and could never be false: both are checks that look like
checks.

Found only because the agent was told to go beyond re-running saved cases in the
area under suspicion. The suspicion was misplaced — see the correction in
[[Q-70]] — and the looking paid anyway.

### Q-77 · Retyping a library's refusal broke a caller — RESOLVED, translation moved to the boundary

`BCH-015` and `BCH-016` passed in round 3 and fail in round 4. Attributable to a
specific commit: Batch B (`53b9043`) changed `bench/corpus.py`'s `rate` and
`rows` refusals from `ValueError` to `prama.core.errors.ValidationError`, so
that `prama bench run --rows 0` would produce a typed refusal instead of a stack
trace ([[Q-68]]).

`ValidationError` derives from `PramaError`, which derives from `Exception`. It
is **not** a `ValueError`. The catalogue's `Expected` for both cases reads
"`ValueError` naming the value", and the refusal messages are byte-identical and
still name the bad value — only the type moved.

The round-4 agent classed this with round 3's `OPS-003`: a correct change whose
side effect is a stale catalogue precondition. That is probably right, and it is
**not** the whole story, so it is recorded rather than waved through.

**The evidence that it is a real contract change, not just a stale test:** the
saved harness `bch_001_061.py` caught `ValueError` and crashed mid-run when the
type changed, taking `BCH-017`–`BCH-061` with it until the agent repaired it. A
test is a caller. It is the only caller that broke here — no product code catches
`ValueError` around `corpus.build`, checked by grep — but "no *internal* caller
broke" is a weaker claim than it sounds for a function in a package whose whole
purpose is to be run by other people's benchmark scripts.

**The design question, left open deliberately.** Two defensible shapes:

- **What was done.** The library raises the taxonomy directly. Simple, and the
  CLI needs no adapter. Cost: a Python-idiomatic `except ValueError` around a
  bad-value refusal stops working, which is the one thing a caller would
  reasonably have written.
- **The alternative.** The library keeps `ValueError` — Python's documented
  meaning for "right type, wrong value", which `rate=1.5` exactly is — and the
  CLI command translates at its boundary. `CLAUDE.md` arguably points here: *"the
  unit of work translates failures into the Prama error taxonomy"* describes
  translation **at a boundary**, not taxonomy all the way down.

Making `ValidationError` inherit from `ValueError` as well would satisfy both and
was considered and rejected: Batch B also uses `ValidationError` for an
unwritable path and an unreadable file, which are not value errors in any sense,
so the inheritance would be a lie for those call sites.

**Resolved: the second option.** The library raises `ValueError` again, with
the messages unchanged, and `prama.cli.bench` translates at its own boundary.
Both contracts now hold — `BCH-015`/`BCH-016` see the `ValueError` they name,
and `prama bench run --rows 0` still answers with a typed refusal rather than a
stack trace.

The remedy text moved to the CLI with the translation, which is where it always
belonged: that layer knows the flags are called `--rate` and `--rows`, and the
library does not. A remedy naming a flag, raised from a module that has never
heard of the command line, was a small piece of the same confusion.

`qa/regression-suite/platform/test_bench_refusals_keep_both_contracts.py` holds
both halves in one file **on purpose**. Either can be satisfied by reintroducing
the other's defect — assert only the `ValueError` and the traceback returns;
assert only the typed refusal and the library contract breaks again — so a fix
that trades one for the other fails half the file rather than passing a whole
one. A third test pins *where* the translation lives, because the two response
tests both pass if somebody moves the taxonomy back into the library and drops
the CLI's `except` in the same change.

One note on that third test, because it was briefly wrong in an instructive way.
It first asserted `"ValidationError" not in inspect.getsource(corpus.build)` —
and failed, because the function's new comment *explains why the taxonomy is not
raised there*. A check that cannot distinguish a prohibition from its own
rationale is exactly the kind this suite exists to be sceptical of. It now looks
for `raise ValidationError`.

### Q-78 · Exact arithmetic that becomes float at the moment of the verdict — reconciliation half FIXED, interpreter half open

Found by the round-4 triage, in two places independently, and **not tied to any
catalogued case** — which is why four rounds of QA did not surface it. Both were
verified by reading the code, not taken from the triage reports.

**Reconciliation.** `recon/classify.py` carries every amount as `Decimal` — the
whole engine does — and then:

```python
def _within_tolerance(self, difference: Decimal, magnitude: Decimal) -> bool:
    return self._tolerance.permits(float(difference), float(magnitude))
```

The conversion happens at the exact instant the break/no-break decision is made,
because `semantic/relationships.py::Tolerance` declares `absolute` and
`relative` as native `float`. A difference of exactly one cent against a
tolerance of exactly one cent is then decided in binary floating point, where
neither value is representable.

**The reference interpreter.** `backend/reference.py::_arithmetic` uses
`float()`; `pql/library.py::_number` uses `Decimal`. One interpreter, two
arithmetic models, depending on which path reaches the value. Four catalogued
cases sit on this (`PQL-300`, `BE-078`, `BE-079`, `BE-080`), three of them P1 —
but they read as four separate rounding complaints rather than one cause.

**Why this is worse here than in most systems.** The reference interpreter
exists to be the oracle the compiled SQL is checked against; the conformance
suite's whole job is to require three engines to agree with it. An oracle that
computes in `float` on one path and `Decimal` on another cannot be the thing
three engines are held to. And a reconciliation verdict is *the* artefact this
product sells — `docs/corpus/12` names reconciliation as banking's most expensive
quality failure. "Declare it. Prove it. Trust it." does not survive a pass/fail
boundary evaluated in a representation that cannot hold the numbers on either
side of it.

The repair is not one line. `Tolerance` would have to carry `Decimal` bounds,
and every producer of a `Tolerance` — declaration parsing, the Γ generator, the
importers — would have to supply them. That is a contained wave, not a batch.

**The counterfactual is unusually easy and unusually convincing**: a
reconciliation with a tolerance of `0.01` and a difference of exactly `0.01`,
and the same for `0.1 + 0.2` against `0.3`. Today the verdict depends on
representation; afterwards it must not. A careless version of that test uses
values that happen to be representable — `0.5`, `0.25` — and passes before and
after, proving nothing.

Related: [[Q-51]], where the same class of mismatch between two implementations
of one calculation made an independent verifier report a forgery.

---

**Reconciliation half: fixed.** `Tolerance` carries `Decimal` bounds, coerced in
`__post_init__` from whatever a caller has — a form string, a YAML value, a pack
constant. The conversion goes through `str()` deliberately: `Decimal(0.0001)` is
the binary approximation to sixty digits, `Decimal(str(0.0001))` is exactly what
the author wrote.

**Five conversion sites, where the triage had named one.** `mypy` found the other
four once the type became exact, which is the argument for changing the
declaration rather than only the call:

| site | what it decides |
|---|---|
| `recon/classify.py::_within_tolerance` | break or no break, two-sided |
| `recon/nway.py::_all_agree` | whether an n-way reconciliation balances at all |
| `recon/nway.py` (odd-one-out) | **which side gets blamed** |
| `recon/nway.py` (per-entry) | which entries become breaks |
| `web/routes/relationship_routes.py` | `float(percent) / 100` on the analyst's typed text |

The last is its own small defect: the console took what an analyst typed, made
it a float, and divided by 100 — so "0.1%" became a bound that is not exactly a
tenth of a percent before the declaration was even stored.

`Tolerance.render()` needed repairing alongside, and that is worth recording
rather than hiding: with `Decimal` bounds it began printing *"within 1.0 EUR or
0.100%"* where it had printed *"within 1 EUR or 0.1%"*. Arithmetically correct
and wrong on a screen — the sentence a data owner approves had changed without
anybody changing the materiality. A `_plain()` helper normalises for display
only; verdicts never see it.

**One consequence found by the gate, not by the triage or by me.** With
`Decimal` bounds, `Tolerance.to_dict()` serialised to JSON as a **string** —
`"1.0"` where the API had always sent the number `1.0`. JSON has no exact
decimal type, so a client reading `tolerance.absolute` and multiplying by it
would have got string concatenation. That is [[Q-77]] in the other direction:
there, an internal fix broke a library contract; here it would have broken a
wire contract.

`to_dict` now converts back to `float` on the way out, and only there. It is the
declared bound being *reported*, never a verdict — every comparison happens
server-side on the `Decimal`, and a materiality a person typed round-trips
through a double without loss at any scale money is written in. The exactness is
kept where it decides something and dropped where it would break a caller.

**Interpreter half: still open, deliberately.** `reference._arithmetic` converts
to `float` while `pql/library.py::_number` uses `Decimal` and says why in its
own docstring — *"a reconciliation that summed in binary floating point would
manufacture exactly the small discrepancies it exists to detect"*. The rule is
written down in one file and contradicted in its sibling.

It is not a type change. `_arithmetic` is the **oracle** the IR conformance
suite holds DuckDB, SQLite and PostgreSQL against, so changing its arithmetic
changes what three engines are required to agree with. Its `%` uses `math.fmod`
rather than Python's `%` precisely because Python floors where every SQL engine
truncates — evidence that the float semantics here were chosen to match the
engines, not inherited by accident. Making the oracle exact may be right, but it
is a question about what conformance *means*, and answering it inside a batch
about tolerance bounds would be the kind of change this project keeps having to
revert.

### Q-79 · A triage finding that was wrong, recorded because the process matters

The data-stack triage reported the ISO 4217 table as retiring every currency one
version late, presenting it as two cases closed by one edit (`CLS-059`,
`CLS-061`). It is not a defect. `classify/codelists.py` reads:

```python
_ISO4217_2024 = _ISO4217_2023 | {"ZWG"}              # ZWG added, ZWL still valid
_ISO4217_2025 = (_ISO4217_2024 | {"XCG"}) - {"ZWL"}  # XCG added, ZWL retired
```

directly beneath a comment ending *"The outgoing code is retired one version
later, which is what 'still accepted for a period' means."* The lag **is** the
`CLS-062` fix: removing an outgoing currency in the same step is how a correct
payment file gets rejected mid-transition. Round 3's judgement — that
`CLS-059`/`CLS-061` are stale catalogue probe dates — stands.

The agent saw the shape of an off-by-one and did not read the comment that
exists to explain why the offset is deliberate. It had been warned, in its own
brief, that a batch which "fixes" a deliberate decision is worse than no batch.

Recorded because the near-miss is the point: three of this effort's remediation
attempts have been reverted for exactly this reason ([[Q-61]], [[Q-64]],
[[Q-65]]), and the only thing that caught it this time was checking a claim that
contradicted a decision already on record. **A triage finding is a hypothesis.**
The ones that contradict something previously decided deserve more scepticism
than the ones that do not, not less — the temptation is to treat them as
discoveries.

### Q-80 · Batch H — six catalogue cases corrected, and two that were not

Six cases asserted behaviour the product deliberately does not have. Each was
verified against the code before editing, and each corrected expectation was
then run against the product to confirm it holds — because "change the test
because the code is right" is the move most likely to be wrong, and [[Q-79]] is
this week's evidence that a confident reading can be.

| case | was | is |
|---|---|---|
| `UI-006` | 403 for every console POST | 403, except the four language routes that declare `control:read` |
| `OPS-003` | sqlite renders without a volume | renders with `persistence.enabled`, including a PVC |
| `IMP-030` | strict `< 2 %` imports as `BELOW 2%` | precondition uses `<= 2 %`; the strict form is refused on purpose |
| `CLS-059` | ZWL absent at 2024-04-05, and at 2025-01-01 | valid until 2025-03-30, absent 2025-03-31 |
| `CLS-061` | ANG absent at 2025-03-31 | still valid; XCG's half unchanged |
| `PQL-350` | a bare `and` is read as an operator | both forms parse to `ColumnRef('and')` |

**Two cases were dropped from this batch after checking.** `BCH-015`/`BCH-016`
needed no edit at all — [[Q-77]]'s repair restored `ValueError` to the library,
so the catalogue's existing `Expected` is satisfied as written. Editing them
would have written the defect into the case.

**`PQL-198`/`PQL-199` were moved out, to the "derive, never restate" work.**
They assert that `PRECEDENCE` and `BINDING` induce the same ordering, and it is
tempting to call them over-strict because the parser normalises `!=` to `<>`
before any AST node exists. But `BINDING`'s own comment says it *"must agree
with the parser's PRECEDENCE, or the formatter emits text that means something
else"* — the code claims the invariant these cases test. Weakening the case to
match two hand-maintained tables that disagree is the wrong direction; deriving
one from the other is the right one.

**What this batch cost to get right.** `CLS-059` was corrected twice. The first
correction fixed the third step — ZWL is valid at 2024-04-05, because retirement
lags by one version — and left the fourth step asserting `False` at 2025-01-01.
That is also wrong, and for a *different* reason: the 2025 version takes effect
on 2025-03-31, so 2025-01-01 is still inside the 2024 version. The second error
was invisible while the first one stood, and only surfaced because the corrected
expectation was executed rather than reasoned about.

A case edited to match the code, and then not run, is worth less than the broken
case it replaced: it now agrees with the implementation by assumption rather
than by test, which is the failure this catalogue exists to prevent.

### Q-81 · Batch M — three single-repair items, and what each nearly got wrong

**E — every API error is now `problem+json`.** `api/app.py` registered handlers
for `PramaError` and `Exception`, and Starlette answered its own
`HTTPException` (an unknown path, a wrong method) and FastAPI's
`RequestValidationError` (a malformed parameter) *first* — with
`{"detail": "Not Found"}` and `content-type: application/json`. The two error
classes a caller hits most often were the only ones outside the documented
contract. Closes `API-010`, `API-011`, `API-012`, `API-013`, `API-017`,
`API-058` — four P1.

The `router_error_handler` omits `remedy` rather than inventing one. There is no
`PramaError` to ask, and a made-up remedy in front of somebody who mistyped a
URL is worse than none. `validation_error_handler` keeps FastAPI's `.errors()`
verbatim in `context`, because the field name is the only part a caller can act
on — and stringifies each value, since `.errors()` can carry an exception object
under `ctx` that would turn a 422 into a 500.

**G — the operations screens declare their subject.** `OperationsRoutes` set no
`SUBJECT`, so `/incidents`, `/reconciliation`, `/scorecards` and `/evidence` all
fell back to `declaration:read`. A caller granted the scope for browsing the
dataset catalogue could read every incident, break, scorecard and evidence
record in the estate. `TriageRoutes` sets `SUBJECT = "incident"` and got it
right, which is how the omission surfaced: the incident *detail* route required
`incident:read` while the incident *list* did not.

No class-level `SUBJECT` was added, because these four serve four different
subjects — a single one would have been the same mistake with a better default.

**F — [[Q-76]] closed.** `Bundle.check()` now compares the manifest's
`from_sequence`/`to_sequence` against the sequences actually present, before the
chain is verified.

**Three API mistakes in one batch, all mine, all caught by running things.**
The `UI-009` test was fine, but both others started from invented interfaces:
`Ledger.append(tenant_id=..., kind=..., payload=...)` — it takes an
`EvidenceRecord`; `Archivist.bundle(from_sequence=..., to_sequence=...)` — it
takes a list of records. And the API test used `valid_at="not-a-date"` assuming
it was date-validated. It is not; that request returns **200**, so two
assertions were failing for a reason unrelated to the defect. Switched to
`limit="lots"`, which `Query(ge=1, le=500)` genuinely refuses.

That is the fourth time today a counterfactual failed for the wrong reason. The
pattern is consistent enough to name: **writing a test against an interface from
memory produces a red that means nothing**, and red is exactly the colour that
stops people looking closer.

### Q-82 · `control check` type-checks against an empty catalogue — FIXED

`CLI-109` and `CLI-110` were reported by the round-4 triage as "structurally
unreachable — a harness fixture conflict, not a product bug", on the reasoning
that they share a fixture with `CLI-111`/`CLI-112` which deliberately leaves a
dataset undeclared. Checked before repairing the fixture, and the diagnosis is
wrong in the more interesting direction.

`cli/control.py:55` reads:

```python
checker = TypeChecker(Catalogue())
```

An empty catalogue, unconditionally, with no option to supply one — `prama
control check --help` offers only `--strict`. So:

- every dataset reference resolves to `[unchecked] nothing is known about …`,
  so a clean file never prints "Nothing to report." (`CLI-109`);
- a column's type is unknowable, so a type error cannot be detected at all
  (`CLI-110`).

Neither case can pass, and no fixture makes them pass.

**The command's own help says "parse, type-check and lint", and `CLAUDE.md`
lists it as the CI gate**: `prama control check suite.pql — parse, type-check
and lint; non-zero on error`. Two of those three work. The type-check is
advertised, wired, and given nothing to check against.

The mechanism exists everywhere else. `web/routes/control_routes.py::_catalogue`
builds one from the estate's declarations, and its docstring explains why that
must be derived rather than restated. `prama lsp catalogue --tenant acme --out
cat.json` exports exactly that for an editor, and `prama lsp serve --catalogue`
consumes it. The console can type-check a control; the CI gate cannot.

Same shape as [[Q-63]] — a capability present in the server and absent from the
CLI — and the same consequence: a person runs the gate, sees it pass, and
believes something was checked.

**Fixed: the same flag, the same loader, the same refusal as `lsp serve`.**
`prama control check --catalogue cat.json` reads what `prama lsp catalogue`
already writes, through `load_catalogue` — no new mechanism, because one already
existed and only the gate was denied it.

Reading declarations from a database directly was considered and not done. The
LSP's own comment says why a file: *"so an editor keeps working on a train and a
laptop with no warehouse credentials still underlines a typo."* The same holds
for CI, where there may be no database at all. One mechanism, two consumers.

`load_catalogue` refuses a missing file rather than falling back to an empty
one, and the gate inherits that. A caller who passed `--catalogue` and got a
green run has been told their schemas were checked; falling back would make that
a lie, which is strictly worse than not offering the flag.

The `[unchecked]` diagnostic without a catalogue is unchanged and is asserted by
its own test, because the obvious wrong repair is to silence it — a file nobody
verified would then read as verified, which is the confusion that diagnostic
level exists to prevent.

`CLI-109` and `CLI-110` pass with a catalogue supplied.

**What this cost to find, and why it is the third of its kind today.** The
triage looked at two failing cases that shared a fixture with two passing ones
and concluded the fixture was at fault. That is a plausible reading and it
stopped one step early. So did I, in [[Q-81]], three times over on API
signatures. A diagnosis that explains the symptom is not the same as one that
has been checked — and the check here was one `--help` away.

### Q-83 · Batch K — two lists derived, and a third that was right to differ

`CLAUDE.md`'s **derive, never restate** applied where the language itself is
defined: *"anything restated in a second place will drift, silently, in the
flattering direction"*.

**`PQL-198`/`PQL-199` — one ordering, two derived tables.** `parser.PRECEDENCE`
decided how a control's text is grouped when read; `ast.BINDING` decided where
brackets go when it is written back; and `BINDING`'s own comment said the two
*"must agree with the parser's PRECEDENCE, or the formatter emits text that
means something else"*. Nothing derived one from the other, so "must agree" was
a hope, and they did not: `PRECEDENCE` listed `!=` and `BINDING` did not, so
`BINDING.get(op, ATOM_BINDING)` scored it **100** — tighter than multiplication
— and a `!=` comparison would never be bracketed.

`ast.PRECEDENCE_LEVELS` is now the single source. `BINDING` is that plus the
keyword predicates; `parser.PRECEDENCE` is that minus `NOT` (parsed in the unary
chain) plus the surface aliases. Every binding value is identical to before and
`COMPARISON_LEVEL` still indexes the comparison tuple — the refactor changes
where the operators are written down, not what they mean.

The alias is **declared** rather than implied: `OPERATOR_ALIASES = {"!=": "<>"}`.
That was the crux. `!=` belongs to what the parser *reads*, never to what the
renderer *writes*, and burying that in parser control flow is what made a
missing `BINDING` entry look like an oversight. The test asserts both
directions, including that `!=` must **not** be in `BINDING` — an unreachable
entry is a claim that it is reachable.

**Why these two cases were not simply weakened in [[Q-80]].** It is tempting to
call them over-strict, since no AST node can carry `!=` today. But that argument
rests on a normalisation living in a third place while the comment claims the
invariant outright. Batch H deliberately left them for this.

**The aggregates were not what the triage described.** It reported "three
aggregate lists" disagreeing. `backend/sql.py::_AGGREGATES` is what Prama's
compiler *emits*; `lineage/sql.py::_AGGREGATES` is what to recognise in **other
people's SQL** — warehouse views this module did not write, which is why it
carries `percentile_cont` and `listagg` that Prama never renders. Those should
differ, and deriving one from the other wholesale would have been wrong.

A first comparison made them look disjoint, and that was an artefact of my own
check: one set is upper-case and the other lower-case. Compared properly, one
real gap — **`approx_count_distinct` is emitted by the compiler and was not
recognised by lineage**, so an edge through it was not marked attenuating.
Lineage now unions its foreign-SQL names with whatever the backend emits,
because anything the compiler renders as an aggregate certainly is one. The
difference that should exist is kept; the overlap that should hold is derived.

`NON_DETERMINISTIC` no longer exists — only `VOLATILE` — so the third
disagreement the triage listed had already been resolved.

Two of the three items in this batch were not the thing the triage said they
were. That is now four batches running where verifying the diagnosis changed
what got done ([[Q-79]], [[Q-80]], [[Q-82]], and this), and the ratio is
consistent enough to treat as the normal case rather than the exception.

### Q-84 · `UI-123` — superseding without a reason, and a test helper with the same defect

`attestation_sign` validated the signer's name and, when `supersedes` was set,
checked the superseded attestation belonged to the caller's estate ([[Q-75]]'s
`UI-122`, which worked). It never checked `supersedes_because`, so an
attestation could be withdrawn with an empty reason and the row was written.

The catalogue's *Why* carries the argument: **"an attestation withdrawn without
a reason is an audit trail with a hole in exactly the interesting place."** Every
other record here carries its justification — a control has `BECAUSE`, an
incident its signals, a break its explanation. The one record that says "what I
previously attested no longer stands" could be written with nothing.

**The fix is three lines. Measuring it took four attempts**, and the failures
are the reason this entry exists.

1. `attestations.for_tenant` — does not exist. Every case failed, including the
   ones that should pass, which is at least a loud way to be wrong. Sixth
   invented interface in this session.
2. `attestations.current` — reads correctly and is wrong. It filters
   `superseded_by IS NULL`, so a **successful** supersede leaves the count
   unchanged: it cannot distinguish "the write was refused" from "the write
   happened and replaced the old row". That is *precisely* the `status_code !=
   303` measurement this case exists because of, reproduced inside the test
   written to fix it.
3. `attestations.history` — every row ever signed, superseded included. Correct.

Step 2 surfaced only because the file carried a control asserting that a
supersede **with** a reason still works. That test exists so the file cannot be
satisfied by refusing every supersede — removing the capability rather than
guarding it. It caught a measurement error instead, which is not the job it was
written for and is the strongest argument for writing it.

**The gate then caught a test that relied on the defect.**
`tests/web/test_attestation_flow.py::test_a_superseded_attestation_says_so_on_its_page`
superseded with no reason, so the guard refused it and the page never said "was
superseded". Worth noting rather than quietly patching: the sibling test twenty
lines above **already supplied a reason**. The codebase knew the rule and one
path did not follow it, which is evidence the guard matches the intended design
rather than imposing a new one.

### Q-85 · Batch J — six of eight CLI sites, and why the first probe of all eight was worthless

[[Q-68]]'s class, continued. The round-4 triage enumerated eight call sites in
`cli/` where a plain Python exception escapes `Application.run`'s
`except PramaError`, and was explicit that this is **eight repairs, not one**.
Three are done.

| site | what escaped |
|---|---|
| `connect/sources/query.py::executor_for` | a directory passed `exists()` and reached DuckDB: `_duckdb.IOException: Is a directory` |
| `cli/lsp.py::LspCatalogueCommand` | unguarded `write_text` → `NotADirectoryError` |
| `cli/bundle.py::_load` | unguarded `json.loads`, then `payload["product"]` and `entry["sha256"]` indexed directly |

**The first attempt to reproduce all eight found no traceback anywhere, and that
was not good news.** Every invocation refused earlier for want of a tenant or a
schema — `no tenant to run`, `that contract declares no schema` — so not one of
them reached the code under test. "No traceback" meant "never got there". Only
after building a configured estate with a real database and tenant did three
reproduce.

That is the same failure as `CLI-109`/`CLI-110` in [[Q-82]], as the
`status_code != 303` measurement in [[Q-84]], and as my own `current`-instead-of-
`history` helper in the same entry: **a check that cannot reach the thing it
describes reports the answer you were hoping for.** Four instances in one
session, in four different shapes.

**`exists()` where `is_file()` was meant is now the third appearance of one
shape** — after `cli/contract.py::_rows` and `_load` in the same file. A
directory satisfies `exists()`, and each of these then hands it to something
that assumes a file: DuckDB, `read_text`, `open`. Worth naming as a class rather
than fixing three times and calling it three bugs.

**Two sites could not be reproduced at all** — `apikey --expires-in-days`
overflow (`CLI-081`) and `estate export --out` under a file (`CLI-185`) — and
are recorded as unreproduced rather than as fixed. They may have been closed by
earlier batches or my invocation may still miss them; both readings are
consistent with what was observed, and claiming the favourable one is the habit
this file exists to resist.

**Three more sites closed after the first pass**, all reproduced first:

| site | what escaped |
|---|---|
| `cli/contract.py::_rows` | `.exists()` where `.is_file()` was meant → `IsADirectoryError` |
| `cli/contract.py::_load` | `read_text` sat *above* its own try, and a bare JSON scalar was then used as a mapping → `AttributeError: 'str' object has no attribute 'get'` |
| `cli/bundle.py::_private_key` | a malformed PEM → `ValueError` with a link to somebody else's FAQ; an RSA key → `TypeError: sign() missing 2 required positional arguments` |

The RSA one is the most worth reading. `Manifest.sign` calls
`private_key.sign(data)` with no padding and no algorithm, which *is* the
Ed25519 interface — the format is fixed by design so a customer checking a
bundle offline needs no algorithm negotiation. A well-formed RSA key sailed
through loading and died at the signature, naming a method the operator never
invoked. It now refuses at the key, says which algorithm it found, and gives the
`openssl genpkey -algorithm ed25519` line.

`cli/contract.py::_load` is the site [[Q-81]] records me walking past in Batch B:
I read the function, saw the JSON parse already wrapped, fixed `_rows` beside it
and never noticed the `read_text` one line above the `try`. It took the triage
to find it and a reproduction to confirm it.

**That makes `exists()`-where-`is_file()`-was-meant four sites**, not three:
`connect/sources/query.py`, `cli/contract.py::_rows`, `_load`, and the earlier
`_rows` repair. Four is not a coincidence; it is an idiom this codebase reaches
for and gets wrong, and worth a lint rule rather than a fifth fix.

**Remaining in J**: two interface sites that could not be reproduced, the
data-stack twelve, and the language-stack eleven. `CLI-017`, the whole-session
census over `qa/harness/interfaces/cli_call_log.jsonl`, is the measure that will
say when it is finished — it read 14 in round 3 and 2 in round 4, and a by-hand
enumeration under-counted both times.

### Q-86 · Two reading-back paths, and a remedy whose branch could never fire

Batch J continued into the data stack. `EVD-020` and `CFG-062`, both on a
**reading-back** path, which is where an untyped exception costs most: the
caller already suspects the thing they are holding.

**`CFG-062` is the one worth keeping.** `FileSource.load` wrapped `read_text` in
`except OSError`, and the remedy inside that clause already read *"Check the
file's permissions and **encoding (UTF-8 is expected)**"*. But
`UnicodeDecodeError` is a `ValueError`, not an `OSError`. The clause never
fired, and a latin-1 config file produced a traceback.

**The message existed; the branch that could show it did not.** That is a
different defect from never having considered encoding, and a more irritating
one, because the author obviously had — the remedy is *right there*, unreachable
by one line of class hierarchy. A reviewer reading that function sees encoding
handled.

Caught by name rather than by widening to `except Exception`, which would have
swallowed every other `read_text` failure with it. A test asserts a missing file
still refuses for *its own* reason, because adding an `except` above an existing
one is exactly how the earlier branch becomes unreachable — the same mistake
one level along.

**`EVD-020`** built metrics with `float(v)`, so a stored `"eight"` raised
stdlib's `could not convert string to float` naming no record, no metric and no
ledger. It runs during replay, so its message is read at the moment somebody is
asking whether a chain can be trusted. It now names all three.

**Eight invented interfaces this session.** `FileSource` is abstract, `_freeze`
takes two arguments, `EngineFactory` takes another — three more in this batch
alone, each costing a probe that proved nothing. The pattern is settled enough
to state as a rule: **read the signature first, not after the red.** A probe
written from memory fails for its own reasons and those reasons look exactly
like the defect not being there.

**Four of the data stack's twelve.** `CTR-015` and `DB-098` followed, and both
take input **this codebase did not write** — an ODCS contract exported by another
tool, and a row whose timestamp was stored by something that is not Prama. That
is where assuming a shape becomes a traceback about a file somebody is trying to
import.

`CTR-015` produced **three different bare exceptions for three shapes of one
mistake**: a mapping made `schemas[0]` a `KeyError: 0`, while a list of strings
and a list of nulls each made `.get` an `AttributeError` naming only the type.

`DB-098` is the one to keep. `datetime.fromisoformat` raises `Invalid isoformat
string` naming neither the table nor the column, while reading rows back — so
the only person who sees it is holding a row they cannot explain. The remedy now
points where it should: Prama writes ISO-8601 UTC text into `VARCHAR(32)` so
timestamps sort chronologically, and a value that will not parse was written by
something else. *Find the writer rather than correcting the row.*

Reading signatures before probing worked: four reproductions, four hits, no
invented interfaces in that round. `CTR-047` did not reproduce from a direct
call to `_freeze` and needs the `.jsonl` path the triage describes; the
remaining eight are untouched.

---

## What held

Recorded because it calibrates the rest, and because a findings list with no
"what worked" section is a list somebody stops believing.

**Authentication** passed all 22 API cases — revoked, expired, unknown,
prefix-collision, wrong-scheme, empty, 8 KB and UTF-8 credentials all produce one
indistinguishable, non-enumerable 401. **Scope enforcement** is uniform across
all 30 scoped API routes, with remedies quoting the vocabulary verbatim.
`X-Prama-Tenant` is ignored entirely.

**The central thesis holds.** Twelve fabricated LEIs and six fabricated ISINs
with valid shape and wrong check digits produced `indeterminate` with the unrun
residual named — not a green tick. Every count on a complete assertion was the
planted number exactly. Thresholds flip on the right row. The evidence chain
resisted record tampering, payload tampering, truncation, and a fully re-chained
forgery.

**The console leaks nothing.** Zero unauthenticated leaks across 30 routes, zero
JavaScript errors on 19 screens × 4 roles, no broken links, output escaping
correct everywhere probed, and the open redirect closed including the backslash
form. The empty states are good.

**Configuration** is the strongest area measured: 35 of 36, with typed refusals,
provenance, placeholder cycles and secret redaction all correct.

## Q-87 — a versioned DAO's flush escaped the error taxonomy

**Where** `src/prama/db/dao/versioned.py`, thirteen call sites. **From** `DB-179`.

`create`, `amend` and `correct` called `self._session.flush()` directly.
`UnitOfWork._guarded` — which translates SQLAlchemy's failures into the Prama
taxonomy — was not in that path, so a violated constraint reached the caller as
`sqlalchemy.exc.IntegrityError: (sqlite3.IntegrityError) UNIQUE constraint
failed: ctl_control.tenant_id, ctl_control.identity`.

`CLAUDE.md`: *"Only `src/prama/db/**` may import `sqlalchemy`."*
`tests/architecture/test_layering.py` enforces it by import scanning, and **an
import scan cannot see what a function raises**. The rule held for every line of
code and failed on the exception. It matters because a duplicate identity is
recoverable — read the existing control and amend it, which is what
`ConflictError`'s remedy says — while the raw error names an index the caller
has never heard of and reads like corruption.

**The triage's account of how to reach it was wrong.** It described the losing
side of a concurrent amendment. That race does not occur on SQLite: writers
serialise, so the second session reads the winner's committed row and amends
forward from it. The staged test reproduced nothing. The reachable path needs no
concurrency — two `create` calls in one session, deterministic on every engine.
A real defect and a wrong story about it are separable.

**Repair.** The translation moved to `src/prama/db/guard.py` and both the unit of
work and `Dao._guarded_flush` call it. Extracted rather than copied, because a
second copy is the restatement `CLAUDE.md` warns about — and the extraction
itself dropped the `DatabaseError` remedy on the first attempt, which mypy
caught. That is luck, not design: a copied translation that loses a remedy is
invisible to every test that only checks the exception type.

**Regression** `qa/regression-suite/data/test_versioned_dao_refuses_in_the_taxonomy.py`.

## Q-88 — a whole cluster of the regression suite was invisible to git

**Where** `.gitignore:22`, an unanchored `data/`. **Found while** committing Q-87.

The Q-87 regression lived in `qa/regression-suite/data/`. `pytest` collected it,
it passed, and `git status` did not mention it — an unanchored pattern matches a
directory of that name at **any** depth, so the directory was not untracked and
offered, it was absent. It would have run on this machine forever and existed
nowhere else.

**The rule had already been learnt once and not generalised.** `.gitignore`'s own
comment two lines below records that `logs/` was anchored after it swallowed
`docs/qa/logs/` — *"a test log nobody can review"*. The identical mistake sat
directly above it, unfixed, because that repair fixed the instance rather than
the class. Worth stating plainly: the fix that teaches nothing is the one written
as a patch to a line instead of a question about a category.

This is the round's recurring shape for the fifth time: **a check that cannot
reach the thing it describes returns the answer you were hoping for.** A green
suite says nothing about whether the suite is in the repository.

**Repair.** `/data/`, anchored to the root, where the runtime scratch directory
it was written for actually lives. Guarded by
`tests/architecture/test_nothing_is_silently_untracked.py`, which asks
`git check-ignore` about every module the runner would import rather than
reimplementing pattern matching — which is how a test of `.gitignore` acquires
`.gitignore`'s bug.

## Q-89 — the same stored timestamp read back as two different instants

**Where** `src/prama/db/types.py::UtcDateTime.process_result_value`.
**Found while** fixing `EVD-110`, in the code `EVD-110`'s fix was derived from.

The function has two paths. A datetime the driver had already parsed got
`replace(tzinfo=UTC)` — naive means UTC. A *string* got
`fromisoformat(text).astimezone(UTC)`, and `astimezone` on a naive value reads it
as **local time**. Same column, same bytes, two instants.

Invisible on a UTC host, which is most CI. On `Asia/Kolkata` the two paths were
5½ hours apart. And it fell exactly along the engine boundary: SQLite hands back
text, PostgreSQL's driver hands back a datetime — so **the same row read
differently on the two engines** whose schema files this project keeps
byte-identical precisely so they cannot mean different things. The rule that
makes the two engines agree is enforced on the schema, and the disagreement was
in the code that reads the column.

Worth stating because it is not a typo: both lines are correct-looking, and
`astimezone(UTC)` is the more idiomatic-looking of the two. It is wrong here
only because of what a naive value *means* in this column — which
`process_bind_param` already settles by refusing to store one.

**Repair.** The text path now branches the way the driver path always did.
**Regression** `qa/regression-suite/data/test_a_timestamp_without_an_offset_means_utc.py`,
which pins `TZ` in a subprocess: every assertion in it would have passed on a UTC
host before the fix, which is why the defect survived.

## Q-90 — one un-tierable record stopped the whole retention sweep

**Where** `src/prama/evidence/retention.py::Archivist.tier_of`. **From** `EVD-110`.

A naive `finished_at` subtracted from an aware clock reading raised `TypeError:
can't subtract offset-naive and offset-aware datetimes`. Nothing catches it, and
`plan()` iterates the entire ledger — so one record written by something other
than Prama stopped the sweep and every record after it went un-tiered.

The function already had an `except ValueError` for an unparseable timestamp,
chosen with visible care: *"A record whose timestamp cannot be read stays hot
rather than being aged out on a guess."* The author thought about the value being
**wrong** and not about it being **incomplete**. That is the more common shape of
this mistake than not having thought about it at all.

**Repair.** A naive value is read as UTC, matching `db/types.py` and what
`CLAUDE.md` says the column holds — not by widening the `except` to `TypeError`,
which would have been correct by accident and would have swept naive timestamps
into the same "stay hot" bucket as unreadable ones.

## Q-91 — a missing driver escaped the one error written to explain it

**Where** `src/prama/db/engine.py`, both constructors. **From** `DB-065`.

`except SQLAlchemyError` around `create_engine`. A driver that is not installed
raises `ModuleNotFoundError` — an `ImportError`, not a `SQLAlchemyError` — so it
escaped untranslated. The sting: `_creation_error`'s remedy already carries
`dialect.driver_hint`, *the exact sentence naming the package to install*, and
the one failure that hint exists for was the only one that could not reach it.

Third instance this round of the same shape — `CFG-062` was `except OSError`
around a `UnicodeDecodeError` with a remedy already saying "UTF-8 is expected".
**The help was written and the branch that could show it did not run.** That is a
different defect from not having anticipated the case, and a more annoying one,
because the author clearly had.

## Q-92 — a closed unit of work reported in SQLAlchemy's voice

**Where** `src/prama/db/session.py::UnitOfWork`. **From** `DB-086`.

`close()` set `self._closed`; nothing ever read it. Using a unit of work after
its `async with` block surfaced SQLAlchemy's own wording about instances not
bound to a session — above `prama.db`, which the layering rule forbids, and
which `tests/architecture/test_layering.py` cannot see because it scans imports
and this is an exception.

The message matters more than the type. The cause is nearly always the same
mistake — a value read outside the block that created it — and stdlib-flavoured
wording sends people to look at the database.

**Repair.** One guard at `_dao`, the chokepoint all twenty-odd DAO properties
already pass through, plus `flush`/`commit`/`rollback`, which are reachable
without touching a DAO and are what a caller reaches for when trying to "just
save it" after the fact.
**Regression** `qa/regression-suite/data/test_the_database_layer_keeps_its_exceptions.py`.

## Q-93 — one unparseable control aborted a whole migration

**Where** `src/prama/importers/spi.py::Collector.control`. **From** `IMP-007` (P1).

`parse_control` raised `PqlSyntaxError` and nothing caught it, so one
carried-over expression that did not parse stopped an entire multi-hundred
control import.

The reason this is the best finding in the batch is the class it happened in.
`Collector`'s docstring states the contract outright: *"an importer built around
a collector cannot forget to report a construct it skipped, because skipping
means calling `unmapped` and there is nowhere else to put it."* The design was
right, the argument for it was written down — and the single method that does the
parsing had a second exit. **A structure that makes the right thing the only
available move still has to be checked for doors nobody meant to leave open.**

**Repair.** A parse failure becomes an `Unmapped` entry quoting the source
construct, and the import continues. Deliberately *not* a silent skip: a
migration that quietly loses controls reads as a complete one, which is worse
than the crash it replaces. The regression asserts both halves.

## Q-94 — two entry points, the same question, two answers

**Where** `src/prama/connect/sources/objectstore.py`. **From** `CON-153` (P1).

`health()` checked the URI scheme and returned `MISCONFIGURED` with a clear
sentence naming the accepted schemes. `open()` did not look, and `_connect`
builds the scheme straight into DuckDB SQL — so `async with connector:`, the
idiomatic form used everywhere else in the codebase, produced
`_duckdb.InvalidInputException: Secret provider 'credential_chain' not found for
type 'ftp'`.

The knowledge was present and the path people actually take did not consult it.
**Repair.** `_scheme_problem()` — one sentence, derived once; `open()` refuses on
it and `health()` reports it.

## Q-95 — a nested JSON value broke the keyless diff

**Where** `src/prama/contract/diff.py::_freeze`. **From** `CTR-047`.

`_freeze` put raw values into a set, so a list or object raised `TypeError:
unhashable type: 'list'`. `.jsonl` is one of the two formats `prama contract
diff` accepts, which makes a nested value ordinary input rather than an edge
case — and `prama contract diff` runs in a build.

**Repair.** `_hashable` converts recursively: a list keeps its order (meaningful
in JSON), an object does not (not meaningful). Converting rather than refusing,
because two rows with the same nested value *are* the same row.

## Q-96 — the driver's words for a mistake made three layers up

**Where** `src/prama/connect/sources/query.py::executor_for`. **From** `CLI-140`.

A file that exists, is a file, and is still not a database — a CSV named
`.duckdb`, a truncated download — handed the caller `_duckdb.IOException`. The
engine's complaint is the useful part and is kept in `context["detail"]`; what it
cannot know is which path was typed and which flag put it there.

## Q-97 — the same helper written five times, twice by the fix for a restatement

**Where** `first_line`, now `src/prama/core/errors.py`.

Reducing somebody else's exception to its first line had been open-coded five
times: `db/session.py`, `db/guard.py`, `connect/sources/query.py`,
`connect/sources/objectstore.py` and `db/schema/bootstrap.py`. **Two of those
copies were written by me during this round** — one while extracting `guarded`
specifically so the translation would not be restated, and one an hour later in
`query.py`, having just recorded the lesson in `Q-87`.

And it had already drifted: three copies truncate at 400 characters, two at 300.
Nobody chose that; it is what a restatement looks like after a while.

Worth recording plainly because the doctrine is not the hard part. *"Anything
restated in a second place will drift, silently, in the flattering direction"* is
written in `CLAUDE.md`, I quoted it in `Q-87`'s own text, and then wrote the
fourth and fifth copies anyway. Knowing the rule does not make one notice the
instance; only looking for the instance does.

**Repair.** One definition in `core.errors`, which every layer already imports,
and five callers.

## Q-98 — the release gate could not tell silence from agreement

**Where** `src/prama/backend/conformance.py`, two functions. **From** `BE-135`,
`BE-139` (both P1).

`CLAUDE.md` names this file as the mechanism behind the project's central habit:
*"Assert the rendered artefact, not the intent… The IR conformance suite is this
habit as a release gate."* Two of its functions confused "we did not get an
answer" with "we got the right answer".

`compare()` built a set of distinct answers and reported a disagreement when it
held more than one. **A set of one answer is trivially unanimous**, so a case
only the reference interpreter could run was scored as agreement. Run against
the interpreter alone, the harness said:

```
conforming: True | cases_compared: 0 / 25
```

The number that contradicts the verdict was printed directly beside it. An
earlier finding (T7) had added `cases_compared` for precisely this reason, and
the verdict never consulted it. **Measuring the right thing and not deciding on
it is a distinct failure from not measuring it, and it looks healthier**, because
the report contains the evidence that it is wrong. Anybody reading that line
would have caught it; nobody had to read it.

`_compare_two_stage` returned `[]` — no disagreements — whenever the reference
interpreter had not answered. The two-stage comparison is the product's actual
thesis: a SQL screen plus an exact check, each catching what the other cannot.
The single most valuable comparison in the suite was the one that could be
skipped without a word.

This is the fifth and sixth instance this round of one shape: **a check that
cannot reach the thing it describes returns the answer you were hoping for.**
Here it is pointed at the release gate itself.

**Repair.** A case fewer than two engines answered is reported, naming how many
did; a two-stage case with no reference answer is reported as uncompared. The
control matters more than the repair — making a gate stricter is easy and
worthless if it fails honest runs — so the regression runs the real corpus
against a real DuckDB alongside the interpreter, and `tests/backend`'s 135 cases
over DuckDB and SQLite stay green.

**Regression** `qa/regression-suite/language/test_conformance_needs_two_answers.py`.

## Not a defect — `BE-132`, SQLite reporting `failed` rather than `refused`

Triaged as a defect: SQLite lacking a `REGEXP` hook raises `OperationalError`,
which `run_case` reports as `failed`, where the catalogue says an engine that
legitimately cannot run a case should report `refused`.

**It is a decision, and the decision is written down.** `SqliteDialect` claims
`pushdown.regex` and says why, in the comment above `regex_flavour`: SQLite
reserves `REGEXP` and calls a host-registered function of that name, *"which is
exactly what `prama.connect.sources.query` does for every SQLite connection it
opens. The capability is therefore real for Prama's own executor and absent for a
bare connection — where it fails loudly as 'no such function: REGEXP' rather than
quietly matching nothing."*

So a bare connection reaching the harness is a misconfigured runner, and `failed`
is the correct report for it. Recorded here rather than dropped, because a
findings list that keeps only the hits is one nobody can calibrate against — and
because this is the second time this round I have nearly repaired a documented
decision (see `Q-79`, the ISO 4217 lag). The tell is the same both times: a
comment that explains the trade-off rather than describing the code.

## Q-99 — an empty codelist fails every row on SQLite and crashes DuckDB

**Where** `src/prama/ir/lower.py::Lowerer._codelist`. **From** `IR-021`, `BE-055`.

The parser already refuses a hand-written `IN ()`: *"an empty set fails every
row, so it is a mistake rather than a style, and the caret can point at the
brackets."* A codelist that resolves to nothing is the same control with the
values arriving from somewhere else, and had no equivalent guard.

**The triage said this produced SQL no engine parses. Half of that is true, and
the untrue half is the dangerous one.** DuckDB rejects `IN ()` outright. SQLite
*accepts* it and evaluates it as false. So one control crashes on one engine
and, on the other, reports **every row in the dataset as a violation** —
silently, with a verdict, in a run that looks entirely normal.

A control that fails everything reads as a data emergency. The cause is a list
somebody emptied. That is a worse hour than a parse error, and the engines
disagreeing about it is exactly the class of divergence this project keeps two
byte-identical schema files to avoid.

**Repair.** Refused where the codelist resolves, in the parser's own words so
that a user meeting the two forms of the same mistake gets one answer.

## Q-100 — the reference interpreter answered questions it could not answer

**Where** `src/prama/backend/reference.py::ReferenceEvaluator._aggregate`.
**From** `BE-096`, `BE-097`.

Two `0.0` defaults in one function, in the interpreter that every SQL engine is
compared against — so a confident wrong number here does not surface as an
interpreter defect, it surfaces as a *backend* defect somewhere else.

`.get(aggregate, 0.0)` had no entry for `APPROX_COUNT_DISTINCT`, so it returned
**zero, presented as a real approximation**.

`SUM`/`MIN`/`MAX`/`AVG` over no numeric values returned `0.0`, where SQL answers
NULL. A sum of zero and a sum of nothing are different facts: the first says the
values cancelled, the second says there were none. A threshold of `>= 0` passes
on one and should never be reached by the other.

**The repair is derived, not invented.** The SQL side of the harness already
drops a NULL metric — `_judge` builds its dict with `if row.get(n) is not None`
— so the interpreter now omits the metric too. Both sides say the same thing
about "no answer", which is the only condition under which comparing them means
anything. And the unsupported aggregate raises `PqlUnsupportedError`, which
`_run_reference` now reports as `refused` rather than `failed` — the rule the
compiled path fifteen lines above already followed: *"A refusal is a conforming
outcome. It is the promise being kept."*

Together with `Q-98` this is the third finding this round inside the release
gate. All three have the same shape, and it is worth naming once more: **the
harness kept substituting a confident value for one it did not have.** Zero for
an unknown aggregate, zero for an empty set, agreement for a single answer, no
disagreement for an absent reference. Each is individually defensible as a
default and collectively they mean the gate could not distinguish working from
untested.

## Q-101 — README and docs/corpus/19 disagree about what is built

**Where** `README.md` §Status, against `docs/corpus/19-implementation-roadmap.md`.
**From** the user's note that the README is obsolete.

Three claims, checked against the roadmap rather than against memory:

**"six of eight GA connectors" — stale, and understating.** `19 §W3.11` says
*"8 of 8 written; 7 verified, 1 not"*, names each verified connector and the
live service it was verified against, and says plainly that Snowflake *"is
written and has never met an account"* and ODBC *"is not built"*. Corrected in
the README to match, with the section cited so the next reader can check rather
than trust.

Worth noting which direction it rotted. A stale number that **understates** is
the comfortable kind — nobody is misled about capability — but it is the same
defect, and it means the sentence was not derived from anything. The next edit
could as easily move it the other way.

**"Eleven waves are complete" — unverifiable from the roadmap, which disagrees
with itself.** Its wave map table lists ten waves; the document then contains a
"Wave 11 — The expression layer" section that the map does not mention. And of
the eleven wave sections, only Waves 1 and 2 carry `**COMPLETE**` in their
headings — the marker was maintained twice and then abandoned.

**Not changed, deliberately.** Whether a wave is complete is the author's
judgement about scope, not something I can derive from the repository: the
per-task tables carry ✅/◑ marks that say more than a heading does. Editing the
README to match a marker that has itself rotted would be restating a stale fact
in a second place. Recorded for the author to settle.

**The general point.** `README.md` now derives two numbers — the test count and
the catalogue count — from the code, and states three more in prose. Prose is
where drift lives. The two that drifted here (4,985 vs 5,083; 4,662 vs 4,660)
were both caught by a script; the three that remain were caught by reading, and
only because somebody said the file looked old.

## Q-102 — `prama.pql.__all__` named five things the module never imported

**Where** `src/prama/pql/__init__.py`. **From** `PQL-402`, `PQL-403`.

`Attribute`, `AttributeCatalogue`, `Drift`, `Expander`, `Expansion` were listed
in `__all__` and imported nowhere, so `from prama.pql import *` raised
`AttributeError`.

The state was neither "exported" nor "not listed" but **both at once**, which is
why nothing caught it: every ordinary import of the package worked, and only the
two forms nobody uses in this codebase — a star import, and `getattr` over
`__all__` — could see it.

All five live in `pql/expand.py`, a sibling. So it was never a question of what
should be public: the names were chosen, written into the contract, and the
import line was never added.

**Repair** one import block, and a check over **every** `prama.*` module rather
than this one, since a list that can drift in one can drift in any. No other
module was found wrong. Written as a single test that names every offender
rather than 350 parametrised cases — the isolation is prettier and the
information is identical, and the suite count is published in the README.

## Q-103 — a regular expression was validated nowhere

**Where** `src/prama/pql/parser.py::_pattern`, `src/prama/backend/dialect.py`.
**From** `BE-016` (P1), `BE-015` (P1), `BE-075` (P2).

`/[/` parsed without complaint and was first noticed by `re.compile` inside the
reference interpreter, or by the engine, at execution — a run that starts, costs
a scan, and then fails, instead of a control that never compiles.

**The triage's account of the portability half was wrong, and the correction is
the useful part.** It said non-portable features make engines *"silently match
different rows"*. Measured against a real DuckDB, lookaround and backreferences
are not silent at all: RE2 rejects them outright. What was silent was the
**timing** — the control compiled, the run began, and one engine refused
mid-flight while the interpreter and SQLite were happy.

**Two genuinely silent divergences do exist, and I did not fix either.**
Measured, not assumed:

* `\d` is Unicode-aware in Python and ASCII-only in RE2, so `/^\d+$/` matches
  `١٢٣` on SQLite and on the interpreter and not on DuckDB — no error anywhere,
  different rows, same control.
* `[[:alpha:]]` is a POSIX class RE2 honours and Python reads as a nested set,
  so it matches on DuckDB and not on SQLite.

Neither is findable by scanning a pattern for forbidden constructs, because
**nothing about the pattern is forbidden** — the flavours disagree about what it
means. Refusing `\d` is not defensible; it is the most common construct in the
language. They are recorded in `dialect.py` and asserted by the regression, so a
later edit cannot delete the note and leave the repair reading as a complete
portability guarantee.

The corpus's only `MATCHES` case uses explicit `[0-9A-Z]` rather than `\d`,
which suggests somebody had already thought about this and wrote around it
rather than writing it down.

**`BE-075` (catastrophic backtracking) is not fixed.** `(a+)+b` against a long
non-matching subject does not complete in Python's engine — a denial of service
against the interpreter, reachable from an authored control. Static ReDoS
detection is not reliable; the triage said budget it separately and it was
right. The regression asserts what is true today — such a pattern parses — so
that the day a runtime bound is added, the test fails and somebody has to come
back and say so.

**Repair** syntax validated at `_pattern`, the one place every `MATCHES` pattern
passes through, where the caret can point at it; RE2's real gaps returned as the
existing `Unsupported` from `DuckDbDialect.regex_match`, so the refusal travels
the path the dialect already has rather than a new one. SQLite keeps accepting
lookbehind, because it runs Python's `re` and genuinely supports it — refusing
it everywhere would be the easy over-correction, removing a capability from the
engine that has it.

**Found while writing the test:** `/*x/` is not a pattern at all — `/*` opens a
block comment and the lexer refuses it earlier, for a different and correct
reason. It was in the first draft's parametrised list and passed, which would
have read as proof the new gate worked.

## Q-104 — a mistyped selector produced an estate that looked covered

**Where** `src/prama/pql/expand.py`. **From** `PQL-366` (P1), `PQL-369`,
`PQL-372`, `PQL-373`.

Selector expansion resolved every kind of internal trouble to "no match" —
**the exact inverse of the failure this round found everywhere else in the
language stack**, where trouble escaped as a bare Python exception. There it
crashed; here it vanished. Both are the same underlying habit: not deciding what
to do about a case, and letting the language's default decide instead.

`PQL-366` is the one that matters. `facts.get(name)` returns `None` for a typo,
every comparison against `None` is `False`, so `WHERE is_cdee` expanded to zero
controls with no diagnostic. That does not produce an error — **it produces an
estate that looks covered and covers nothing.** The declaration is on the
record, a coverage report counts it, and no control was ever generated. Of every
defect found this round this is the one whose consequence is furthest from its
cause.

`PQL-369`: `tags = 'pii'` compares a list with a string and is never equal, so
it matched nothing — while `tags IN ('pii')`, the same intent spelled
differently, matched. And `criticality > 3` raised `TypeError`, caught and
turned into `False`, so a string-versus-integer comparison read as *"no
attribute is that critical"*.

`PQL-372`/`PQL-373` are one defect seen twice. `_truth` required the literal
`True`; `_is_true`, used by the `NOT` branch, also accepted the string `"true"`.
For a flag that arrived from a warehouse as text, `WHERE is_cde` **and** `WHERE
NOT is_cde` both excluded the attribute — neither half of a partition, which is
the one thing a partition may not do. Two functions answering the same question
differently, eleven lines apart.

**Repair**, as one policy rather than three patches: ambiguity in a selector
must be visible. The fact names are checked against the mapping the predicate is
actually evaluated against — derived, not restated, so adding a fact cannot
leave a second list behind — with a spelling suggestion, because the available
names are known exactly and there is no reason to make somebody diff two lists.
`_truth` now uses `_is_true`, so the two agree by construction. A comparison
that cannot be true is refused and names the spelling that works.

**The distinction the repair had to preserve**: a domain with no CDEs yet is a
legitimate empty expansion. Refusing that too would have replaced a silent wrong
answer with a loud wrong answer, and the regression asserts it still works.

## Q-105 — a threshold the assertion could not carry, reinterpreted instead of refused

**Where** `src/prama/ir/lower.py::Lowerer._threshold`. **From** `PQL-150` (P1),
`PQL-151`.

`_threshold` special-cased `rate`/`percent` and sent everything else to a
`violating_rows` count.

**`PQL-150`.** `CHECK t.a IS NOT NULL WITHIN 100 USD` became
`Threshold(metric="violating_rows", value=100.0)`: the currency dropped, the
number kept. *"Within 100 US dollars of error"* and *"at most 100 bad rows"* are
different controls. This is the kind of wrong that **reads correct in a diff** —
the figure the author typed is right there in the plan, and only its unit
changed.

**`PQL-151`, where the triage was wrong in a useful direction.** A rate
threshold needs a `violating_rows` metric to be a rate *of* anything, and a
row-count assertion emits only `scanned_rows`. Triage expected `INDETERMINATE`.
Measured, the verdict comes from the row-count path and is **identical with the
clause and without it** — the clause is silently discarded. That is worse than
indeterminate: the author believes they constrained something and the run agrees
with them.

The parser's own module docstring already listed *"a threshold on an assertion
that has no rate"* among the things it refuses at authoring time. It did not.

## Q-106 — the first repair for Q-105 was wrong, and the wrongness is the finding

The first version asked whether the emitted metrics contained `violating_rows`.
They do not for `unique_key` or `functional_dependency` either — but
`backend/execute.py` **derives** one for both, from the distinct counts. So the
check refused two legitimate assertion kinds.

Three existing generated-equivalence tests caught it within a minute. That is
the counterfactual discipline paying for itself in the opposite direction from
usual: not a new test catching an old defect, but old tests catching a new one.

**The lesson is about where the answer lived.** "Does this assertion have
violations?" is answered in two files — one that emits metrics and one that
derives them — and asking only the first gives a confident wrong answer. The
repair names it once, in `ir/model.py::KINDS_WITHOUT_VIOLATIONS`, and the
regression asserts that set against **what the pipeline actually produces**
rather than trusting it. A frozen set of strings is a list somebody must
remember to update; the same set checked against the thing it describes cannot
quietly become false.

## Q-107 — the control generator emitted controls that should not exist

**Where** `src/prama/backend/generate.py`. **Found by** `Q-105`'s repair.

The generator chose an assertion and a threshold independently, so it emitted
`HAS ROW COUNT … BELOW n%` — precisely the combination `PQL-151` is about. The
generated-equivalence suite has been exercising it for as long as it has
existed, and three engines dutifully agreed about a control that should never
have lowered.

**A generator that can produce invalid inputs makes agreement about them
meaningless**, and it is a plausible reason the combination went unnoticed:
something was testing it, and passing. It now consults the same
`KINDS_WITHOUT_VIOLATIONS` the lowerer does, and the regression lowers 300
generated controls to assert the two cannot drift apart. The random draw is
still consumed either way, so existing seeds keep their meaning.

## Q-108 — the length check was inverted, not merely noisy

**Where** `src/prama/pql/types.py::TypeChecker._check_predicate`.
**From** `PQL-092` (P1), `BE-160`.

The checker exempts `in_codelist`, `is_valid`, `has_format` and `matches` from
the subject-versus-argument type comparison — *"the argument names a thing, not
a value"* — and did not exempt `has_length_between`. So `CHECK t.isin HAS LENGTH
BETWEEN 12 AND 12`, about as ordinary a control as this language has, was
reported as comparing text with a number. Twice, once per bound, on every text
column, always.

**The defect is not that it was noisy.** Exempting the comparison and stopping
there is the obvious fix and would have left the other half untouched: `CHECK
t.notional HAS LENGTH BETWEEN 1 AND 3` — the character length of a *number* —
reported nothing at all. The check **rejected the correct control and accepted
the incorrect one**, so the obvious repair would have made the checker quieter
and no more correct. The repair adds the positive check the exemption implies:
a length applies to text, and a length bound is a number.

`BE-160` is the same defect from the other side — type-checking the corpus
generator's own output produced the identical message about a different column.
Two catalogue cases, one cause, and they read as unrelated until the messages
are put side by side.

## Q-109 — my fixture typed every column `unknown`, and the test looked passed

**Found while writing** `Q-108`'s regression.

The first fixture declared columns as `text` and `number`. `text` happens to be
a real SQL type name and resolved; **`number` is not, and resolved to
`unknown`** — which the checker exempts from every comparison. So the
number-column case reported zero findings and looked as though that half of the
defect did not exist.

`TYPE_FAMILIES` holds actual SQL type names — `varchar`, `numeric`, `int`,
`real`. A fixture that silently types every column `unknown` turns a
type-checking test into one that checks nothing, and it fails *open*: every
assertion about "no findings" passes.

This is the session's recurring shape arriving in my own test — the sixth
instance, and the second time it has been in something I wrote rather than
something I was reviewing. **A check that cannot reach the thing it describes
returns the answer you were hoping for**, and a fixture is a check.

Also caught in the same file: one parametrised case (`'12' AND 12`) passed the
counterfactual against the unrepaired code, because the old subject-comparison
message happened to contain the word "number" too. Asserting on a substring that
both the right and the wrong message contain is not an assertion. It now
requires the phrase only the new finding uses.

## Q-110 — a test that measured the machine rather than the code

**Where** `qa/regression-suite/interfaces/test_serve_and_errors.py`.
**Found by** a gate run on a host under load average 50.

`test_it_reaches_a_pipe` starts `prama serve`, sleeps **four seconds**, sends
SIGINT and asserts the banner reached the pipe. The four seconds were an
assumption about how fast this machine is. It held for months, and on a host
where something else was using every core the server had not finished starting —
so the test read an empty banner and failed.

**The failure mode is the part worth recording.** An empty banner is exactly
what the defect this test exists to catch produces: `prama serve > log` with the
banner stuck in an unflushed buffer. So under load the test reports the very
defect it is guarding against, and the only way to tell a real regression from a
busy machine is to run it again on a quiet one. A test that asks to be re-run is
a test people stop reading.

It passed in a foreground run twenty minutes earlier on the same tree, and
passed in isolation immediately after failing — which is the signature.

**Repair.** It waits by connecting to the port rather than by sleeping. The
banner is written during startup, so a server that accepts a connection has
already printed it; polling the thing the assertion depends on replaces a guess
about duration with an observation of the state. The deadline is sixty seconds,
which is not a timing assumption but a bound on hanging.

**Checked for the category rather than the instance** (the lesson from `Q-88`):
this was the only fixed sleep used as a readiness signal in either suite. The
other timing values are subprocess `timeout=` bounds, and
`tests/web/test_estate_map_scale.py` is already opt-in and documented as
timing-sensitive for exactly this reason.

## Q-111 — a published performance gate that measured the machine

**Where** `tests/execute/test_inflight.py::test_it_fits_the_published_budget`.
**Found by** the same loaded host as `Q-110`, on the next run.

The test asserts `docs/corpus/15 §7`'s claim — five milliseconds added at p99 — over
500 messages. Under contention it failed with a p99 several times the budget.
The pipeline had not changed; the process simply was not being given a CPU.

**Both obvious repairs are wrong.** Making it opt-in, the way
`tests/web/test_estate_map_scale.py` already is, would quietly retire a
*published gate* — `docs/corpus/15` states this as a threshold Prama must meet, and a
gate nobody runs by default is not a gate. Loosening the budget would move a
published number to whatever this laptop happens to manage. Both are the
flattering direction, and both would leave the documentation claiming something
the suite no longer checks.

**Repair: measure whether the measurement was possible.** `process_time` against
`perf_counter` gives the share of the run during which this process actually
held a CPU. When most of the wall clock was spent descheduled, the p99 is a fact
about the host, and the honest report is that nothing was measured — which is a
**skip**, naming the share observed. A pass would be a lie and a failure would
be a false alarm.

It cannot go falsely green: with the budget forced to an impossible value on a
quiet host, the test raises with *"p99 was 0.05 ms against a published budget of
0.00 ms, on a host that gave this process 100% of a CPU — so this is the
pipeline, not the machine"*. The strictness is unchanged; only the ability to
tell the two apart is new.

**`Q-110` and this are the same defect in two tests**, and the pair is the
argument for the shape: a timing assertion has two inputs, the code and the
host, and a test that cannot separate them reports the wrong one. Neither was
found by review — both needed a machine busy enough to break them, which is the
sort of thing that happens once and then does not happen again for months.

## Q-112 — the Excel surface and the PQL parser disagreed about `a.b`

**Where** `src/prama/pql/excel.py`. **From** `PQL-338` (P1), `PQL-339`.

The tokenizer's bare-name pattern is `[A-Za-z_][A-Za-z0-9_.]*` — the dot is
*inside* the character class — so `positions.notional` became **one column
literally called `"positions.notional"`**, rather than `dataset="positions",
name="notional"`. Nothing resolves to that, and the formula parsed cleanly.

The PQL parser has always split a qualified name on the dot. **Two surfaces onto
the same language disagreed about what `a.b` means**, and only one was right —
which is the same class of defect as `Q-89` (two code paths disagreeing about a
naive timestamp) and `Q-104` (`_truth` and `_is_true` disagreeing about `"true"`).
Three instances this round of *the same question answered twice, differently*.

`PQL-339`: `[]` stripped to `""` and produced a `ColumnRef` with an empty name.

**The distinction the repair had to get right**, and why this is not a one-line
regex change: **brackets are the quoting mechanism.** `[total.gbp]` must keep
its dot, because quoting is how a column genuinely called `total.gbp` is reached
at all. Splitting on the dot everywhere would fix the bare case and make the
quoted one unreachable — one silently wrong reference traded for another.

So a bare identifier splits, exactly as the PQL parser splits it, and a
bracketed one does not. The regression asserts the Excel result **against the
PQL parser's** rather than against a remembered shape, so the two cannot drift
apart again.

More than one dot is now refused, because the PQL parser refuses it too:
accepting it would make the Excel surface strictly more permissive than the
language it writes.

## Q-113 — the rule with no guard, and the seven sites it was hiding

**Where** `tests/architecture/test_the_taxonomy_holds_at_the_boundary.py`, new.
**Prompted by** the user asking what could be done about the number of findings.

Twenty-six findings this round cluster into five shapes, and the largest — eight
of them — is one rule: a bare exception escaping the Prama taxonomy. `CLAUDE.md`
states it. `tests/architecture/test_layering.py` has twenty-five tests enforcing
it, **every one an import scan or a text scan**, and none asserts what a function
raises. I wrote the sentence *"an import scan cannot see what a function raises"*
into five separate findings before acting on it.

`qa/regression-suite/interfaces/test_no_command_shows_a_traceback.py` guards the
**CLI** boundary, pinned to nine invocations from a 224-call census. Six of the
eight were below it — a DAO flush, an engine factory, a unit of work, a
collector, a connector's `open`, a diff — reachable from the API and the console
too.

**The guard.** Every public reader in `prama.*` — anything named `load`,
`parse`, `read`, `from_dict` — is *discovered*, then called with input of the
right type and wrong content. Only a `PramaError` may escape. The surface is
derived, so a reader written next month is covered the day it is written.

It found **seven more sites on its first run**, in seconds: five `from_dict`
readers indexing a required key without checking (`FeedDefinition`,
`Provenance`, `Envelope`, `MatchKey`, `RelationshipDeclaration`),
`EvidenceRecord.from_dict` letting stdlib's *"invalid literal for int()"*
through for a non-numeric `sequence`, and `cli/lsp.load_catalogue` answering
`IsADirectoryError` for a directory — **the fifth `exists()`-where-`is_file()`
was meant** this round.

The directory case is refused *separately* from the missing-file case rather
than folded into one `is_file()` check. Two existing tests pinned the old
message and caught the blur: a path that is missing and a path that is a
directory are different mistakes with different fixes, and one message covering
both names neither. The same argument the empty-codelist refusal makes against
reusing "not registered" for "registered but empty" — and the existing tests
made it before I did.

**Repaired with one helper, not seven guards.** `core.errors.required_field`
names the document, the missing key, and — the part worth having — the keys that
*are* present, because the usual cause is a document from another tool that
spells the field differently.

## Q-114 — the guard nearly reversed a decision the user had already made

Building `Q-113`'s guard took three wrong versions, and the third is the one
worth recording.

**First**, it reported 167 escapes, none real: it fed a `str` to
`from_dict(document: dict)` and counted the `AttributeError`. Passing the wrong
*type* is the caller's mistake; this file is about the right type with wrong
*content*. That is `Q-109` again — the tool built to prevent a class of defect
committing that class.

**Second**, still 237, because the type matcher tested `"any" in annotation`
before the container cases, and `dict[str, Any]` contains `any`. The substring
was in the annotation; it was not what the annotation meant.

**Third, and the one that matters.** With the noise gone it flagged
`EntityId.parse("")`, `Column.parse("")` and `Request.parse({})` — all raising
`ValueError` with careful, informative messages. Those are not defects: **`Q-77`
resolved, deliberately, that the library raises `ValueError` for "right type,
wrong value" and the boundary translates.** Had I "fixed" them I would have
silently reversed a decision the user made, across the codebase, in the name of
a rule.

So the guard encodes that line instead of ignoring it: for a `ValueError`, the
question is not the type but **who raised it**. And that needed care too —
asking only whether the deepest frame is inside `prama` is not enough, because
`int("x")` raises from C and the deepest *Python* frame is our own file. The
line is read: a refusal we chose is a `raise` statement; a refusal we inherited
is an `int(...)` on a line that raises nothing. That distinction is what made
`EvidenceRecord.from_dict` visible.

**The general lesson.** A guard is a claim about what is allowed, so writing one
means discovering every deliberate exception to it. Three of the ten sites the
guard first reported were decisions, not defects — and a guard that cannot tell
them apart does not get fixed, it gets disabled.

## Q-115 — a money threshold compared as text, and 9 was greater than 10

**Where** `src/prama/backend/dialect.py::SqlDialect.literal`.
**From** `BE-006` (P1), `BE-007`.

`literal` tested `isinstance(value, int | float)` and sent everything else to
the string branch. `Decimal` is neither, so it was emitted **quoted**.

**The triage called this "a silent type change". It is worse than that.** A
quoted number makes the comparison lexical, and measured against real engines:

```
SELECT '9.0' > '10.0'   -->  true     on DuckDB and on SQLite
SELECT  9.0  >  10.0    -->  false
```

So a control reading `amount > 10.00` — written with the `Decimal` this codebase
uses for money everywhere else — **passes rows of nine pounds**, and reports a
verdict, on financial data, with nothing wrong anywhere in the run.

Of the twenty-nine findings this round, **this is the only one that produces a
wrong answer on real data.** Everything else was a crash, a false alarm, an
unhelpful message, or a gate that could not see. This one is quiet and says
PASS. It is worth stating plainly because the severity is inverted from the
noise: the loudest defects this round were the least dangerous.

`BE-007`: `repr(float("inf"))` is the Python string `inf`, which parses as SQL
on none of the three engines. Refused rather than given an engine-specific
spelling — a threshold of infinity is an authoring mistake, usually a division
that produced one earlier, and the three engines spell it three ways.

**The repair that would have been wrong**: rendering the `Decimal` through
`float`. It passes the "not quoted" assertion and throws the scale away —
`Decimal("10.00")` becomes `10.0` — so the regression asserts the scale
survives as well as the quoting.

## Q-116 — the verifier that needs no Prama and Prama's own disagreed

**Where** `scripts/verify_evidence.py::canonical`, `src/prama/evidence/ledger.py::verify`.
**From** `EVD-006` (P1), `EVD-014` (P1), `EVD-144` (P1); triage batch data-stack `C4`.

Two separate causes, both reproduced before repair:

- **`EVD-006`.** Prama hashes UTF-8 (`ensure_ascii=False`); the independent
  verifier used the stdlib default and escaped `münchen.positionen` to `ü`
  before hashing. It reported every non-ASCII record as altered.
  **The direction of the fix matters.** Changing Prama's side would have
  re-hashed every chain already stored, so the independent verifier moved.
- **`EVD-014`.** `EvidenceRecord.from_dict` keeps only the fields it knows,
  and `verify` rehashed the rebuilt record. So `"note": "approved by treasury"`
  added to a stored record was invisible to Prama and caught by the
  independent verifier. `verify` now treats any field the record's version
  does not define as an alteration. Two readers of the same bytes must not
  disagree about whether the bytes were changed.

`EVD-144` closes as a consequence, not as a third fix.

Regression: `tests/evidence/test_independent_verifier.py::TestTheTwoVerifiersAgree`.
Both tests failed before repair for the stated reasons: the first on the
content hash, the second on Prama reporting no breach. The control is that the
untouched bundle passes in both verifiers.

## Q-117 — one language, two arithmetic models

**Where** `src/prama/backend/reference.py::_arithmetic`, `::_compare`.
**From** `PQL-300` (P1), `BE-078` (P1), `BE-079`, `BE-080` (P1); triage batch language-stack `C1`.

Operators did `float(x)` while every function went through
`library._number` and got `Decimal`. So `0.1 + 0.2` was `0.30000000000000004`
through `+` and `0.3` through `ROUND`. `TRUE` counted as 1, and text crashed
with a bare `ValueError`. The operators now use the same conversion
(`library.exact_number`): anything that is not a number is unknown.

**The second half, which the triage did not name.** Making the sum exact is
not enough. `Decimal("0.3") == 0.3` is **false** in Python, because the float
is not 0.3. So `a + b = c` over a float column would have gone from wrong by
rounding to wrong by exactness. `_compare` reads a float as the decimal it
prints as when it meets a `Decimal`. The regression asserts the comparison, not
only the sum. Modulo keeps SQL's truncation, because `Decimal`'s `%`
truncates just as `math.fmod` did.

Regression: `tests/pql/test_numbers_survive.py::TestOperatorArithmeticIsExact`,
with whole-number arithmetic and division by zero as the controls.

## Q-118 — `:g` kept six significant figures, and the formatter would write them

**Where** `src/prama/pql/ast.py`: `Literal.render`, `Threshold.render`, `Threshold.describe`.
**From** `PQL-141` (P1), `PQL-209`; triage batch language-stack `C22`.

`AT MOST 1234567 ROWS` rendered as `1.23457e+06` and re-read as 1234570.
`prama control format --write` would have committed that to disk. All nine
`:g` sites now go through `ast.exact`, which scales in `Decimal` too, so a rate
of 0.001234567 is `0.1234567%` rather than what `* 100` gives in binary. As
the triage warned, the round trip is tested at seven digits, not only on `5`:
`:g` is invisible below a million, so a small-value test would pass for the
wrong reason. `5` is kept as the control.

## Q-119 — two hand-kept lists of where a condition lives, neither complete

**Where** `src/prama/pql/types.py`: `_type_check`, `_expressions_of`.
**From** `PQL-241` (P1), `PQL-242`; triage batch language-stack `C23`.

Type checking covered `WHERE` only, so a `SATISFIES` condition, the surface
an Excel formula lands on, was never type-checked. Function checking missed
`HAVING`, so `HAVING NONSENSE(b) > 1` passed. Both now derive from
`_conditions_of`, one list of every boolean condition a control carries. The
regression's control is that the same type mistake in `WHERE` is still caught.

## Q-120 — the compiler remembered the last table it compiled

**Where** `src/prama/backend/sql.py::SqlCompiler`, `src/prama/backend/fuse.py::_empty_group`.
**From** `BE-034`, `BE-037`; triage batch language-stack `C9`.

`self._source` was set by one call and read by the next:
- With a scan limit, the correlated subquery was qualified by the whole
  `(SELECT … LIMIT n)` text, which is a syntax error on every engine. The
  limited scan is now aliased `prama_scan`, and the outer column names the
  alias. The PostgreSQL case needed this regardless, because PostgreSQL
  requires an alias on a derived table.
- A filter compiled by the fuser inherited whatever table was compiled last.
  The source is now scoped to one call and restored afterwards, and the
  fuser passes its own table.

The regression runs the scan-limited referential control on SQLite and
counts the orphan.

## Q-121 — deep input was a RecursionError, reachable over HTTP

**Where** `pql/parser.py`, `ir/lower.py`, `ir/model.py`, `pql/ast.py`, `backend/dialect.py`.
**From** `PQL-175`, `PQL-176`, `PQL-177`; triage batch language-stack `C20`.

- Parentheses: nesting is bounded at `MAX_NESTING` (64), with a located
  refusal.
- A thousand-term OR: lowering, rendering and the IR walkers each recursed
  once per term. The IR walkers now iterate over `Expr.walk`, and rendering
  walks a same-operator run iteratively.
- AND/OR chains longer than `FLAT_CHAIN` (64) lower to one n-ary node.
  **Only long ones.** Flattening every chain would change the plan id of
  every existing control with three ANDs, and plan ids are sealed into
  evidence.
- A 500-column key: the same flattening for the null test. **The remaining
  limit is SQLite's own**: expression depth 1000, and a key column costs
  three levels. SQLite now refuses keys over 240 columns while compiling,
  saying why, instead of failing at run time. DuckDB and PostgreSQL run the
  key.

The tests use 1,000 terms and 500 columns, not 100: Python's default limit is
1,000 frames, so a small case passes whether or not the walk is recursive.

## Q-122 — `'GBP' / qty` lexed as a pattern; found by the guard on its first run

**Where** `src/prama/pql/tokens.py::_previous_allows_division`.
**From** the new differential guard,
`tests/architecture/test_same_question_same_answer.py`, not from a catalogue
case.

`/` is either division or the start of a `/pattern/`. The lexer decides by
the character before it: a value allows division. Closing brackets, digits
and identifiers counted as values, but **the end of a string or a quoted
name did not**. So `'GBP' / qty <> notional` read `/ qty <> notional …` as an
unclosed pattern, while the Excel surface read the same expression correctly.
Dividing text is still a type error, but it is now the type checker that says
so; the lexer no longer misreads the text.

**Why this is the point of the guard.** `Q-112` pinned one disagreement
between the two surfaces (`a.b`). The guard generates 400 seeded expressions
from the syntax both share and requires the same tree from each. On its
first run it found six failures, all this one cause. None of the
catalogue's cases covered it.

The second guard from the handover, **absence-only regressions**, is built as
a ratchet (`tests/architecture/test_no_vacuous_regressions.py`). The 33
existing tests of that shape are listed for review; a new one fails the build.

## Q-123 — the model layer claimed a grammar it never applied, trusted an unstated hosting, and sent secrets

**Where** `src/prama/llm/providers.py`, `src/prama/llm/spi.py::ModelProvider.ask`, new `src/prama/llm/redact.py`.
**From** the LLM gateway design (docs/design/llm-gateway.md §0); Wave 12's first item.

- **Grammar.** `grammar_enforced=True` was recorded whenever the field was
  *sent*. Ollama, LM Studio, TGI's chat route and OpenAI ignore it silently.
  A per-server `Dialect` table now records what each server actually honours:
  vLLM a grammar and a regex, llama.cpp a grammar only, the rest nothing.
  An unknown server is `generic`, which enforces nothing.
- **Hosting.** The default was self-hosted, which is exempt from residency
  checks. `hosting` is now required, and a known vendor host (OpenAI, Azure,
  Anthropic, Hugging Face, AWS, Google, Mistral, Together, Groq) cannot be
  declared self-hosted.
- **Redaction.** Secret shapes were checked on answers only. `ask()` now
  withholds them from prompts too, on the one path every provider shares.
  It also withholds card numbers that pass the Luhn check; the control is
  that a 13-digit trade id survives. The patterns moved from
  `assistant/safety.py` to `llm/redact.py`, so the lower layer owns them and
  there is one list.

## Q-124 — a schema-qualified dataset lost its quotes on the way out

**Where** `src/prama/pql/ast.py`: `ColumnRef.render` and every `render_head`.
**From** building lineage-derived proposals (Wave 15), not from a catalogue case.

PQL reads a dataset reference with one dot, so a schema-qualified dataset is
written quoted: `CHECK "stg.trades".notional IS NOT NULL`. That parses. But
`render()` wrote it back as `stg.trades.notional`, which does not. A control
over any schema-qualified table could not survive `prama control format`, and
proposal text built from rendered AST would not re-read. Both are the
formatter-changes-meaning class again (see Q-118).

`ast.quote_dataset` writes a name bare when the parser can read it bare, and
quoted otherwise, in all three places a dataset is written. The regression
round-trips three forms (column, `REFERENCES`, `HAS UNIQUE KEY`). The control
is that `p.a` is still written bare.
