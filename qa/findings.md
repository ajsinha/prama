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

### Q-64 · `IS FRESH` has no execution strategy at all — open, and larger than PQL-083

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

So the business owner — the persona in the first sentence of `docs/00`, the
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
product sells — `docs/12` names reconciliation as banking's most expensive
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

### Q-82 · `control check` type-checks against an empty catalogue — the CI gate cannot type-check

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

**Not fixed here.** The repair is a `--catalogue` argument taking what `lsp
catalogue` already writes, and/or reading declarations when a database is
configured, which is a decision about how the CLI reaches the estate rather than
a bug to patch. Recorded with the two cases attached so the next batch has them.

**What this cost to find, and why it is the third of its kind today.** The
triage looked at two failing cases that shared a fixture with two passing ones
and concluded the fixture was at fault. That is a plausible reading and it
stopped one step early. So did I, in [[Q-81]], three times over on API
signatures. A diagnosis that explains the symptom is not the same as one that
has been checked — and the check here was one `--help` away.

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
