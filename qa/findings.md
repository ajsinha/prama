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
