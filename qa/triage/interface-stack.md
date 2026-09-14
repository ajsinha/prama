# Interface-stack triage — 105 standing failures, grouped by cause

Scope: `cli/`, `api/`, `web/`, `lsp/`, `mcp/`, `assistant/`, `agent/` — the 105 cases listed in the
assignment (48 P1). Grouped by **what is wrong in the code**, not by directory or title vocabulary.
Every claim below was checked against `src/prama/**` directly (not just the QA logs), and against the
QA harness scripts under `qa/harness/interfaces/` where a case's own Observed text looked
inconsistent with what the source does. No file outside this document was written.

**Headline: 16 real clusters close 53 of the 105 cases with roughly 34 discrete code edits — not 53.
6 more cases are not defects at all (2 confirmed harness measurement bugs found this round, one
confirmed-stale catalogue assertion, one deliberate product decision, and 2 harness-fixture gaps).
The remaining 46 are genuinely one-off.** Realistic closable count: see the estimate at the end.

---

## 1 · Batches, ordered by (cases closed ÷ effort)

"Effort" is the count of distinct call sites needing an edit, not a time estimate. A cluster of 3
cases needing 3 separate edits is marked `3 cases / 3 repairs`, not folded into "one fix."

| # | Batch | Cases | P1 | Repairs | Ratio | Note |
|---|---|---:|---:|---:|---:|---|
| B1 | API/console errors bypass `problem+json` | 6 | 4 | 1 | 6.0 | register 2 exception handlers |
| B2 | ISO 8583 parser accepts wrong-format input as clean | 3 | 2 | 1 | 3.0 | one function, `_infer`/ISO 8583 |
| B3 | `list_datasets` filters are an if/elif chain | 3 | 1 | 1 | 3.0 | one function rewrite |
| B4 | Console errors render as raw JSON, not HTML | 2 | 2 | 1 | 2.0 | one handler, mirrors existing `NotSignedIn` |
| B5 | `DatasetService` has no field validation | 6 | 4 | 3 | 2.0 | `.declare`, `.amend`, one route-level fix |
| B6 | `list_relationships`: same if/elif + no paging | 2 | 0 | 1 | 2.0 | B3's twin; B-073 half is a contract change |
| B7 | agent `_assign` drops work / accumulation risk | 2 | 1 | 1 | 2.0 | must be fixed together, see below |
| B8 | `control_suppress` masks failure, no date check | 2 | 2 | 1 | 2.0 | one function |
| B9 | `pack calendar` bypasses `materialise()` | 2 | 0 | 1 | 2.0 | one call-site swap |
| B10 | `compile --fuse` doesn't isolate one bad control | 2 | 0 | 1 | 2.0 | one function |
| B11 | `get_dataset`'s bitemporal query handling | 2 | 2 | 1 | 2.0 | one function, two branches |
| B12 | `bundle verify` message conflates 3 causes | 2 | 1 | 1 | 2.0 | `security/bundle.py::verify`; CLI-211's exit-0 half is stale |
| B13 | Raw exceptions escape the CLI's typed boundary | 12 | 2 | 8 | 1.5 | mechanical, same pattern × 8 sites |
| B14 | `db verify` drift detection is incomplete | 3 | 3 | 3 | 1.0 | protects the no-migrations rule |
| B15 | `control format` destroys suites and comments | 2 | 1 | ~2 | 1.0 | PQL-219 cheap, PQL-222 needs AST work |
| B16 | Tenant scoping missing on by-parent/by-id reads | 2 | 2 | 4 | 0.5 | **security — do not deprioritise by ratio** |

Clusters total: **53 cases, 48 P1-and-above-weighted... 24 of the 53 are P1**, ~34 repairs.
Not-a-defect: 6. One-off: 46 (15 P1, 29 P2, 2 P3).

---

## 2 · The batches

### B1 · API/console errors bypass `problem+json` — API-010, API-011, API-012, API-013, API-017, API-058

**What's wrong.** `src/prama/api/app.py` registers exactly two exception handlers:
`add_exception_handler(PramaError, prama_error_handler)` and `add_exception_handler(Exception,
unexpected_error_handler)`. Starlette's `HTTPException` (raised for a 404/405 by the router itself)
and FastAPI's `RequestValidationError` (raised for a malformed query/body, e.g. an unparsable
`valid_at`) are neither `PramaError` nor caught by the generic `Exception` handler in time —
Starlette answers them with its own built-in handler first, producing bare `{"detail": "..."}`
JSON with `content-type: application/json`, before the request ever reaches Prama's error code.

**Cases:** API-010 (P1), API-011 (P1), API-012 (P1), API-013 (P1), API-017 (P3), API-058 (P2). 6
cases, **4 P1**. API-058 looked unrelated at first read (its own Observed already shows `422` for
every malformed `valid_at`), but the second element of its result tuple is a
`content-type == application/problem+json` check that is `False` in all three sub-cases — it is
the exact same gap wearing a different case number.

**One repair or N?** One. Two calls: `app.add_exception_handler(StarletteHTTPException,
starlette_problem_handler)` and `app.add_exception_handler(RequestValidationError,
validation_problem_handler)` in `api/app.py`, each building a `problem_document`-shaped body from
the exception FastAPI already gives you (status/detail for the first, `.errors()` for the second).

**Defect, decision, or stale?** Defect. `status_for`/`problem_document`/`STATUS_BY_TYPE` already
exist and work correctly for every `PramaError`; this is a coverage gap in what gets *turned into*
one, not a design question.

**Counterfactual.** Today: `assert (await client.get("/api/v1/nope")).headers["content-type"] ==
"application/problem+json"` fails (`application/json` instead). After the fix it passes. A careless
version of this test would only check `status_code == 404` — that already passes today and would
never have caught the missing `type`/`code`/`remedy`/`correlation_id` fields an integrator depends
on to branch programmatically (finding Q-22's whole point).

---

### B2 · ISO 8583 parser / format inference accept the wrong format as clean — CLI-238, PCK-084, PCK-085

**What's wrong.** `cli/pack.py::_infer` and the ISO 8583 parser it feeds do no structural sanity
check. `_infer`'s ISO 8583 branch is `stripped[:4].isdigit() and len > 20` — true for a numeric-
leading CSV export (PCK-085) — and the ISO 8583 parser itself accepts any bytes and reports "No
structural defects found" for a genuine FIX message read under `--format iso8583` (CLI-238 and
PCK-084 are **the same run of the same command against the same fixture**, catalogued twice —
`interfaces.md`'s CLI-238 and `domain.md`'s PCK-084 — confirmed by byte-identical Observed text:
`mti='8=FI' fields=0 amount='-'` in both).

**Cases:** CLI-238 (P1), PCK-084 (P1), PCK-085 (P2). 3 cases, **2 P1**.

**One repair or N?** One: give the ISO 8583 parser (and by extension `_infer`) a real structural
check — an MTI must be 4 numeric digits, not `8=FI` — and use that same check in `_infer` instead
of the bare `isdigit()`/length heuristic.

**Defect, decision, or stale?** Defect — but read together with **CLI-239** (same command family,
set aside below): the "non-zero exit" half of CLI-238/PCK-084's Expected cannot be delivered,
because `PackParseCommand.run` always returns `EXIT_OK` **on purpose**, confirmed by a passing unit
test (`tests/cli/test_pack_cli.py::test_defects_are_reported_rather_than_raised`) with an explicit
comment: "Exiting non-zero would make it a finding about the tool." The fix here is to make the
parser actually *report* the mismatch as a defect line; exit code stays 0, matching the recorded
design decision.

**Counterfactual.** Today: `prama pack parse order.fix --format iso8583` prints "No structural
defects found." After the fix: it prints at least one defect naming the MTI as non-numeric. A
careless test would assert only `exit_code != 0` — that assertion is now known to be wrong for this
codebase and would fail forever against a correct implementation.

---

### B3 · `list_datasets`'s filters are an if/elif chain, not composable predicates — API-061, API-062, API-063

**What's wrong.** `api/routes/semantic.py::list_datasets`:

```python
if unbound:
    versions = await uow.datasets.unbound(caller.tenant_id)
elif criticality is not None:
    versions = await uow.datasets.by_criticality(caller.tenant_id, criticality)
else:
    versions = await uow.datasets.list_current(caller.tenant_id, limit=limit, offset=offset)
...
page=Page(total=await uow.datasets.count_current(caller.tenant_id), limit=limit, offset=offset)
```

`total` always calls `count_current` (ignores whichever filter ran) — API-061. `unbound` and
`criticality` together silently drop `criticality` — API-062. The `unbound` branch calls a DAO
method that takes no `limit`/`offset` at all, so `?unbound=true&limit=10` returns every row — API-063.

**Cases:** API-061 (P1), API-062 (P2), API-063 (P2). 3 cases, **1 P1**.

**One repair or N?** One — this is a single ~15-line function. Replace the if/elif chain with a
composed filter (unbound AND/OR criticality as independently-applicable predicates), thread
`limit`/`offset` through every branch, and make `total` reflect whatever predicate actually ran.

**Defect, decision, or stale?** Defect.

**Counterfactual.** Today: `GET /datasets?unbound=true&limit=3` on 11 unbound datasets returns all
11 with `page.limit` claiming 3. After the fix: 3 items, `page.total == 11`. A careless test would
only check `len(items) <= limit` on the *default* (no-filter) path — that already passes, since only
the filtered branches skip pagination.

---

### B4 · Console errors render as raw `problem+json`, never HTML — UI-011, UI-046

**What's wrong.** `web/webapp.py::mount_ui` installs exactly one UI-specific exception handler —
for `NotSignedIn` (redirects to `/sign-in`). Nothing else is registered for the UI mount, so every
`PramaError` a console route raises (403 AUTH.FORBIDDEN, 404 ENTITY.NOT_FOUND, …) falls through to
the *API's* global `prama_error_handler`, which always returns `application/problem+json` — correct
for the API, wrong for a browser navigating the console, which gets raw JSON with no chrome
(finding Q-26).

**Cases:** UI-011 (P1), UI-046 (P1). Both P1.

**One repair or N?** One — install a second handler on the UI mount, parallel to the existing
`NotSignedIn` one, that renders `PramaError` (and, ideally, `RequestValidationError`) into an HTML
error page using the console's own chrome/template, guarded to routes under the UI mount rather than
`/api/`.

**Bonus:** this likely also fixes UI-063's `banana`-criticality sub-case (currently `422
application/json`, should render as HTML per that case's own Expected) if the handler also covers
`RequestValidationError` on the UI mount — worth doing in the same PR, not counted as a 3rd case here
since UI-063's substantive failure (out-of-range integers) is B5's job.

**Defect, decision, or stale?** Defect.

**Counterfactual.** Today: `GET /estate` from a no-role principal returns
`content-type: application/problem+json` with raw JSON in the response body. After the fix: an HTML
page in console chrome saying the account holds no permissions. A careless test would check only
`status_code == 403` and `"hold" in body.lower()` — UI-011's own harness assertion does exactly
that, which is *why* it currently reads as almost-passing: the JSON body's `remedy` text happens to
contain the word "hold," masking that the response isn't HTML at all.

---

### B5 · `DatasetService.declare`/`.amend` perform no field validation — API-050, API-053, UI-061, UI-063, UI-064, UI-065

**What's wrong.** `src/prama/semantic/services/datasets.py::DatasetService.declare` takes `name`,
`criticality`, `shape` and passes every one of them straight to `self._uow.datasets.create(...)`
with no bound, no range check, no enum check. `.amend` does the same for `**changes`, splatting an
open dict into the DAO call with no allow-list — so `changes={"tenant_id": "other"}` reaches the DAO
verbatim (API-053). Neither the API's `DatasetIn.shape: str` (API-050) nor the web form's
`shape: Annotated[str, Form()] = "unbound"` (UI-064) constrain the value beyond what a `<select>`
happens to render; both routes' `except PramaError` blocks catch nothing, because the eventual
failure is a raw DB `CHECK` `IntegrityError`, not a `PramaError`. This is exactly the pattern this
codebase's own doctrine warns about — "Derive, never restate": the `SHAPES` tuple exists to *render*
the select, never to *validate* against it.

Two more failures are sibling bugs in the same neighbourhood, not the same function, but cheap to
fix in the same pass: UI-061 (name is neither trimmed nor bounded — accepted at 5,000 characters,
fine on SQLite, an `IntegrityError` waiting to happen on PostgreSQL's `VARCHAR`), and UI-065 (in
`web/routes/declaration_routes.py::declaration_create` itself: `Grain(...) if grain_attributes else
None` — a `grain_statement` submitted with no attributes is unconditionally discarded, not refused).

**Cases:** API-050 (P1), API-053 (P1), UI-061 (P1), UI-063 (P2, the out-of-range sub-cases only —
the `banana` sub-case is B4's), UI-064 (P1), UI-065 (P2). 6 cases, **4 P1**.

**One repair or N?** Three: add validation to `DatasetService.declare` (name bound/trim, `shape` in
`SHAPES`, `criticality` in 1–4 — this alone fixes API-050, UI-061, UI-063, UI-064, since both the API
route and the web route call this one service); add an allow-list check to `.amend` (fixes API-053);
and fix the grain/statement branch in `declaration_routes.py` itself (fixes UI-065, not shared with
the API since the API has no equivalent grain-from-form path). Raising `ValidationError` (a
`PramaError`) from the service means `status_for`/`problem_document` already produce a correct 422 —
no separate work needed on the response side.

**Defect, decision, or stale?** Defect, and a clean instance of the "derive, never restate" failure
mode this file's own doctrine names.

**Counterfactual.** Today: `POST /datasets` with `{"name": "x", "shape": "banana"}` returns `500
PRAMA.INTERNAL`. After the fix: `422` naming the permitted shapes. A careless test would assert only
`status_code != 200` — 500 already satisfies that; it would never distinguish "refused cleanly" from
"crashed."

---

### B6 · `list_relationships`: the same if/elif anti-pattern, plus no pagination wrapper at all — API-072, API-073

**What's wrong.** `api/routes/semantic.py::list_relationships` is B3's twin: `if dataset_id: ...
elif kind: ... elif confirmed_only: ... else: ...` — only the first-present filter is ever applied
(API-072). Unlike `list_datasets`, this endpoint returns a bare `list[RelationshipOut]` with no
`page`/`total`/`truncated` wrapper at all, and is hard-capped at `limit=500` in the `else` branch —
a client reading exactly 500 rows cannot tell whether that is everything (API-073).

**Cases:** API-072 (P2), API-073 (P2). Both P2, no P1.

**One repair or N?** One function, but two shapes of change: composing the filter predicates is a
pure bugfix; wrapping the response in a page object **changes the API's response schema** for every
existing caller (array → object). That half needs a product decision on how to ship it (additive
field vs. a versioned endpoint), not just a code change — flagging this explicitly rather than
quietly turning `list[RelationshipOut]` into something else.

**Defect, decision, or stale?** API-072 defect; API-073 defect-plus-a-decision-needed on the
breaking-change question. The catalogue's own Why notes the same silent cap exists on concepts,
journeys and connections — this repair is a template for those too, not in scope here.

**Counterfactual.** Today: `?dataset_id=X&kind=Y&confirmed_only=true` returns rows matching only
`dataset_id`. After the fix: the intersection, or an explicit refusal that the filters conflict. A
careless test would post a single filter at a time — every single-filter case already passes today.

---

### B7 · agent `coordinator._assign` drops unassignable work, and fixing that naively reintroduces unbounded growth — AGT-024, AGT-025

**What's wrong.** `agent/coordinator.py::_assign`:

```python
for plan, assignment in work.queue:
    fitness = fits(plan, message.capabilities, engine=assignment.engine)
    if not fitness.assignable:
        work.unassignable.append(Unassignable(...))
        continue
    ...
work.queue = remaining
```

A plan unassignable to *this* agent is appended to `work.unassignable` and simply never added to
`remaining` — so `work.queue = remaining` permanently drops it, even if a different, more capable
agent polls next (AGT-024). AGT-025's catalogue "Why" assumed this append runs on every poll
forever; measured, it doesn't — because once the plan is dropped from `work.queue`, `_assign`
short-circuits at `if work is None or not work.queue: return [], []` on every later poll, so
`work.unassignable` stops growing (it's evaluated once, not once per poll). **But** that only holds
because of AGT-024's bug: the naive fix for AGT-024 — leave the plan in the queue so other agents
can pick it up — means it gets re-evaluated (and re-appended to `work.unassignable`, unconditionally,
with no dedupe by `plan_id`) on every single poll from every still-incapable agent, which is exactly
the unbounded growth AGT-025 describes. **These two cannot be fixed independently**: keep the plan in
`remaining` for other agents, and de-duplicate `work.unassignable` by `plan_id` in the same change.

**Cases:** AGT-024 (P1), AGT-025 (P2). 2 cases.

**One repair or N?** One — both live in the same 15-line loop, and doing one without the other
either loses work (current bug) or leaks memory (the naive fix).

**Defect, decision, or stale?** Defect.

**Counterfactual.** Today: an incapable agent's `hello` permanently removes a plan from the queue;
a subsequently-polling capable agent never receives it (`capable_hello_assignments=()`). After the
fix: the capable agent receives it, and 1,000 polls from the incapable agent still report the hole
exactly once, not 1,000 times. A careless test would only assert "the capable agent eventually gets
it" without also driving 1,000 polls from the incapable one first — it would pass on a fix that reads
back into AGT-025.

---

### B8 · `control_suppress` masks every failure as success, and never validates `until` — UI-079, UI-080

**What's wrong.** `web/routes/control_routes.py::control_suppress`:

```python
try:
    await uow.controls.suppress(control_id, ..., until=until, because=because, by=...)
except PramaError as exc:
    flash_error_and_log(request, "That control could not be suppressed", exc)
return redirect_to(request, "control_list")
```

The `return redirect_to(...)` is **outside** the try/except — success and failure both end in a 303
to `/controls`, distinguished only by a flash message nothing in the HTTP response proves happened
(UI-079; the sibling `activate` route has no such try/except and correctly 404s). Nothing here
validates `until` as a parseable date before it reaches the DAO — `until="not-a-date"` is stored
as-is, silencing the control until a typo is manually noticed (UI-080).

**Cases:** UI-079 (P1), UI-080 (P1). Both P1.

**One repair or N?** One function: render a proper 404 when the target control doesn't exist
(matching `activate`'s pattern) instead of unconditionally redirecting, and parse/validate `until`
before calling `suppress`.

**Defect, decision, or stale?** Defect.

**Counterfactual.** Today: `POST /controls/01NOSUCH/suppress` returns 303 to `/controls`. After the
fix: 404. A careless test asserting only `"success" not in flash_message` would pass today (the
flash message *is* an error) while still returning the wrong status code — status code is the load-
bearing assertion here, not the flash text.

---

### B9 · `pack calendar` bypasses `materialise()`, so neither the horizon nor ad-hoc closures apply — PCK-030, PCK-031

**What's wrong.** Both cases' own catalogue "Why" already names the cause: `PackCalendarCommand`
calls `observed(rules, [year])` directly rather than `spec(...).materialise(...)`. `materialise` is
where the year range is checked against `FIRST_YEAR`/`LAST_YEAR` and where `self.closures` (ad-hoc
dates added via `with_closures`) get unioned into the rule-derived set. Calling `observed()` raw
skips both, so `--year 1850` computes and prints closures for a year outside the pack's own claimed
`describe()` range (PCK-030), and an ad-hoc closure never appears in the listing though `describe()`
counts it (PCK-031).

**Cases:** PCK-030 (P2), PCK-031 (P3). Neither P1.

**One repair or N?** One — swap the call site to use `materialise`.

**Defect, decision, or stale?** Defect.

**Counterfactual.** Today: `prama pack calendar TARGET2 --year 1850` exits 0 and prints closures.
After the fix: refused, naming the supported range. A careless test checking only that the command
doesn't crash (`exit_code in (0, 1)`, no message check) would pass either way.

---

### B10 · `control compile --fuse` doesn't isolate one unlowerable control from the rest — CLI-136, CLI-137

**What's wrong.** The non-fused compile path catches `PqlUnsupportedError` per-control and excludes
just that control, reporting the rest. The `--fuse` branch has no equivalent: `ControlCompileCommand
.run` appends to `plans` only on success, exits `EXIT_OK` unconditionally regardless (CLI-136), and
with `--dialect` combined, a single unlowerable control aborts the whole fused compile with a raw
`PqlUnsupportedError`-flavoured refusal rather than annotating just that control as excluded and
fusing the rest (CLI-137) — both are the same gap: the fused branch lacks the per-control
try/except the unfused branch already has.

**Cases:** CLI-136 (P2), CLI-137 (P2). Neither P1.

**One repair or N?** One — port the existing per-control exclusion handling from the unfused branch
into the fused one, and make the exit code reflect "something was excluded."

**Defect, decision, or stale?** Defect.

**Counterfactual.** Today: a 3-control suite with one `ROUND`-using control on sqlite `--fuse`
exits 0 (silently compiling 2 of 3) or exits 1 with the whole compile aborted, depending on ordering
— neither is "2 compiled, 1 excluded, exit code says so." After the fix: it is. A careless test
checking only `exit_code != 0 or "excluded" in out` conflates the two current wrong behaviours and
would not catch a fix that merely picks one of them.

---

### B11 · `get_dataset`'s bitemporal query handling — API-056, API-057

**What's wrong.** Same function, two branches:

```python
if valid_at and known_at:
    version = await uow.datasets.as_of(...)
elif valid_at:
    ...
else:
    current = ...
```

`known_at` given **alone** (no `valid_at`) falls into the `else` branch and silently returns the
*current* version for what was supposed to be a year-2000 belief query — a wrong answer, not a
refusal, in a product whose thesis is evidence replay (API-056). Separately, a naive `valid_at` (no
UTC offset) reaches a guard intended for the *write* path and 500s instead of being refused with a
422 naming the missing timezone (API-057, finding Q-23).

**Cases:** API-056 (P1), API-057 (P1). Both P1.

**One repair or N?** One — add a branch that refuses `known_at`-without-`valid_at` explicitly, and
validate `valid_at`'s offset before it reaches the write-path guard, raising `ValidationError`
(422) instead.

**Defect, decision, or stale?** Defect.

**Counterfactual.** Today: `GET /datasets/{id}?known_at=2000-01-01T00:00:00Z` returns 200 with the
*current* dataset version. After the fix: 422 naming `valid_at` as required alongside it. A careless
test checking only `status_code == 200` (i.e., "it didn't crash") would pass on the wrong-answer
behaviour — the defect here is a silently wrong answer, not a crash, so status-code-only checks are
exactly the wrong tool.

---

### B12 · `bundle verify`'s failure message conflates three different causes — CLI-211, SEC-144

**What's wrong.** `security/bundle.py::verify` produces one generic sentence — "the publisher
signature does not verify against the key given: the bundle was altered, or signed by somebody
else" — for three different situations: a wrong key was given (accurate), a key was given but the
signature file was stripped entirely (SEC-144 — the message doesn't say "no signature was found,"
even though the underlying Q-19 *security* defect this case exists to catch, a stripped signature
silently downgrading to a pass, is confirmed fixed: `verify_exit=3`, refused), and **no key was
given at all** (CLI-211 — the message still opens with "does not verify against the key given,"
which is simply inaccurate when nothing was compared against anything).

**Cases:** CLI-211 (P2), SEC-144 (P1). 2 cases.

**One repair or N?** One — teach `verify` to distinguish "no key provided" from "key provided,
signature absent" from "key provided, signature present but wrong," and have the CLI render each as
its own sentence.

**Defect, decision, or stale?** Mixed, and worth separating explicitly:
- SEC-144's remaining gap is real but now purely cosmetic — the security property (no downgrade to a
  pass) already holds; only the message's specificity is missing. Its P1 label overstates today's
  urgency.
- CLI-211's *exit code* expectation (0, "a pass," when no key was given) is **stale**: it predates
  the same hardening SEC-144 records, and shipping it as written would contradict SEC-144's own
  stated design principle — "asking for provenance and being told nothing must not read as
  provenance established." The correct behaviour is exit 3 (as today), with a corrected message. Do
  not implement CLI-211's literal exit-0 expectation.

**Counterfactual.** Today: `prama bundle verify` (no `--publisher-key`, signed bundle) exits 3 with
"does not verify against the key given." After the fix: exits 3, message reads "no key was given to
check it against" (or equivalent), distinct from the wrong-key and stripped-signature wordings. A
careless test asserting only `exit_code == 3` already passes today and would never catch the message
regression this batch exists to fix.

---

### B13 · Raw exceptions escape the CLI's typed-error boundary at 8 call sites — CLI-081, CLI-139, CLI-164, CLI-185, CLI-198, CLI-208, CLI-209, CLI-253, CTR-060, SEC-161, SEC-166, CLI-017

**What's wrong.** `cli/base.py::Application.run` catches exactly `except PramaError as exc:` — there
is no catch-all. Every one of the following raises a plain Python exception that is never converted:

| Site | Exception | Case(s) |
|---|---|---|
| `apikey.py`, `--expires-in-days` overflow | `OverflowError` | CLI-081 |
| `bundle.py::_load` — `json.loads` unguarded, then `payload["product"]`/`payload["entries"]`/`entry["sha256"]` indexed directly | `json.JSONDecodeError`, `KeyError` | CLI-208, CLI-209, SEC-161 |
| `bundle.py::_private_key` — `load_pem_private_key(data, password=None)`; later, signing with an RSA key with no padding/algorithm args | `TypeError` (×2 shapes) | CLI-198, SEC-166 |
| `estate.py::EstateExportCommand.run` — `path.parent.mkdir(...)` when the parent segment exists as a file | `NotADirectoryError` | CLI-185 |
| `lsp.py::LspCatalogueCommand.run` — `Path(ctx.args.out).write_text(...)` unguarded | `OSError` | CLI-253 |
| `control.py::ControlRunCommand.run` — `--against` a directory reaches the executor unguarded | `IsADirectoryError` | CLI-139 |
| `contract.py::_rows` — checks `.exists()`, not `.is_file()`; a directory or an unreadable file reaches `.open()`/`.read_text()` | `IsADirectoryError`, `PermissionError` | CLI-164 |
| `contract.py::_load` — `target.read_text()` is called **before** the try/except that wraps only the parse step; a bare-string JSON payload is used as a dict downstream with no type check | `IsADirectoryError`, `AttributeError` | CTR-060 |

`CLI-017` is the whole-session aggregate over `qa/harness/interfaces/cli_call_log.jsonl` (241
invocations this round); it counted exactly 2 uncaught exceptions this run — both `CLI-164`'s — and
will read 0 once B13 lands. It is not an independent 9th repair; it is B13's own regression test,
already in the tree.

**Cases:** CLI-081 (P3), CLI-139 (P2), CLI-164 (P2), CLI-185 (P2), CLI-198 (P2), CLI-208 (P2),
CLI-209 (P2), CLI-253 (P2), CTR-060 (P1), SEC-161 (P2), SEC-166 (P3), CLI-017 (P1). 12 cases, **2
P1**.

**One repair or N?** **N — 8 repairs**, one per call site, all following the identical mechanical
pattern (wrap the builtin exception, raise the taxonomy's `ValidationError`/similar with a `remedy`
naming the path). Cheap individually; do not report this as "one fix."

**Defect, decision, or stale?** Defect, all 8 sites. This is the exact class the assignment
singled out — the reason it was worth naming `cli_call_log.jsonl` explicitly is that a
by-hand enumeration (which is how the prior batch found "12 of 14") will keep under-counting; the
census is the only way to know the true remaining count. It reads **2** this round; after B13, it
should read **0**, and should stay in whatever regression gate runs this harness so a 9th site never
sits undiscovered again.

**Counterfactual.** Today: `prama contract check c.json --data adir/` prints a raw Python traceback
to stderr, exit code determined by CPython's default (1) rather than a chosen one. After the fix: a
typed refusal naming the path, exit 1. A careless version of `CLI-017`'s own check — grepping stdout
for the literal string `"Traceback"` — is exactly what round 3's version of this aggregate did and
is why it under-counted; the corrected version (used this round) counts the harness's own
`UNCAUGHT_EXCEPTION` sentinel from the actual process exit path, which is why it found CLI-164 when
the prior batch's by-hand list did not.

---

### B14 · `db verify` / `SchemaVerifier` drift detection is incomplete — CLI-032, CLI-033, CLI-034

**What's wrong.** Three distinct, compounding gaps in schema drift detection — the only safety net
CLAUDE.md's "no migrations, ever" rule has:
- **CLI-032**: an extra table *is* detected and described in the output ("`[extra_table] zz_extra:
  present in the …`"), but classified `0 blocking, 1 informational` — so `db verify` exits 0 on
  drift it just printed. This is a severity-classification bug, not a detection bug.
- **CLI-033**: an added column is not detected **at all** — `db verify --json` after `ALTER TABLE
  tenant ADD COLUMN zz_new_col TEXT` reports `drifts=[]`.
- **CLI-034**: `SchemaVerifier` (`src/prama/db/schema/verifier.py`) has no `DriftKind` enum value for
  a changed column type at all — only `MISSING_TABLE`/`MISSING_COLUMN`/`NULLABILITY`/
  `MISSING_INDEX`/`EXTRA_TABLE`/`DIGEST`/`VERSION` exist. A `VARCHAR(64)` silently becoming `TEXT` is
  invisible by construction, not by bug.

**Cases:** CLI-032 (P1), CLI-033 (P1), CLI-034 (P1). All 3 P1.

**One repair or N?** Three, in the same module: fix the blocking/informational classification for
extra tables; add added-column detection to the table/column diff; add a `DriftKind.COLUMN_TYPE`
(or similar) and the comparison that populates it.

**Defect, decision, or stale?** Defect — and the highest-stakes cluster in this triage relative to
its size, because it directly undermines the "a live schema that has drifted is a loud failure,
never a silent migration" guarantee CLAUDE.md states as a hard rule. An added or retyped column that
`db verify` cannot see is exactly the failure mode that rule exists to prevent.

**Counterfactual.** Today: `sqlite3 x.db "ALTER TABLE tenant ADD COLUMN zz_new_col TEXT"; prama db
verify` exits 0, "no drift." After the fix: exit 3, naming the column. A careless test exercising
only the *already-covered* drift kinds (missing table, missing column via a whole-table diff) would
never touch the column-diff or type-diff code paths this cluster is about — which is presumably how
these three shipped without column-level coverage in the first place.

---

### B15 · `control format` destroys suites and discards comments — PQL-219, PQL-222

**What's wrong.** `cli/control.py::ControlFormatCommand.run` (via `_read`) calls
`parse(source).all_controls`, which flattens a `SUITE name { … }` wrapper away; the formatter then
joins the individual controls at top level and `--write` **permanently deletes** the `SUITE`
declaration from the file on disk — `Suite.render` exists in the codebase and is simply never called
from this command (PQL-219, a real data-loss bug on a formatter, which is meant to be the safest
command in the CLI). Separately, the lexer discards `--`/`/* */` comments and the AST has nowhere to
put them even if it didn't, so `--write` silently deletes every comment in a file with no warning
(PQL-222).

**Cases:** PQL-219 (P1), PQL-222 (P2).

**One repair or N?** Two, of very different size. PQL-219 is cheap: call `Suite.render` for a
parsed suite instead of flattening it — the rendering logic already exists. PQL-222 is not cheap as
a full fix (comment-preserving formatting needs the lexer to retain comment tokens and the AST to
carry them through, a real language-tooling change); the catalogue's own bar is lower — "documented
behaviour, and a warning before anything is deleted" — so a warning printed before `--write` proceeds
on a file containing comments is a legitimate, much cheaper partial close.

**Defect, decision, or stale?** Defect. PQL-219 in particular should be treated as a priority
independent of this cluster's aggregate ratio: it is data loss caused by running the tool advertised
as safe to run (`prama control format`, no `--write` needed to observe the bug in principle, though
the loss itself requires `--write`).

**Counterfactual.** Today: `prama control format suite.pql --write` on a file containing `SUITE
name { CHECK … }` leaves behind two bare `CHECK` statements with no `SUITE` wrapper. After the fix:
the `SUITE` wrapper survives a round trip. A careless test checking only that the file "still parses
after formatting" would pass either way — a flattened suite is still syntactically valid PQL, just a
different (and wrong) program.

---

### B16 · Tenant scoping missing on by-parent and by-id reads — API-064, API-065

**What's wrong.** `api/routes/semantic.py::list_attributes`, `graph.py::list_properties`,
`graph.py::list_bindings` (by-parent reads) and `semantic.py`'s dataset-history route (by-id) call
DAO methods that do not filter on `tenant_id`. Given estate B's dataset id and estate A's API key:
`/datasets/{B}/attributes`, `/datasets/{B}/bindings`, `/concepts/{B}/properties` all return **200
with the full declarations**, and `GET /datasets/{B}/history` returns 200 as well (the plain
`GET /datasets/{B}` correctly 404s — the tenant check exists somewhere in this file, just not
everywhere it needs to).

**Cases:** API-064 (P1), API-065 (P1). Both P1, both security findings — this is a cross-tenant
data-leak class, the most severe thing in this triage.

**One repair or N?** N — 4 call sites (3 for API-064's three routes, 1 for API-065's history route),
each needing the same shape of fix: verify the parent dataset/entity belongs to `caller.tenant_id`
before running the by-parent/by-id query, mirroring the pattern `attestation.py::in_tenant` already
uses correctly elsewhere in this codebase (see B12/UI-122's discussion below — that helper is the
model to copy, not to write from scratch).

**Defect, decision, or stale?** Defect — unambiguously; this is finding Q-04 from an earlier round,
re-confirmed live this round on all four routes.

**Counterfactual.** Today: `GET /datasets/{other_tenant_dataset_id}/attributes` with this tenant's
key returns 200 with the other tenant's attribute declarations. After the fix: 404 (not 403 — a 403
would itself be an oracle confirming the id exists in *some* tenant, which the catalogue's own Why
explicitly calls out as the wrong refusal shape). A careless test checking only `status_code != 200`
would accept a 403 here, silently reintroducing the enumeration oracle the catalogue is specifically
guarding against.

---

## 3 · Not a defect — set these aside

| Id | Severity | Why it's not a defect to fix |
|---|---|---|
| `UI-006` | P1 | **Given as a known example.** A deliberate, correct side effect of Batch C's `control:read` fix (Q-66): 4 language routes now correctly return 200 for an auditor. The catalogue's blanket "403 for every POST route" predates that fix. Narrow the catalogue's Expected; do not touch the routes. |
| `CLI-176` | P2 | **Confirmed stale wording match, not a behaviour gap.** The harness requires the error text contain `"no such"`, `"not present"`, `"unknown"`, or `"does not"`; the actual (better) message — `"the key column(s) pk are in neither side's rows"` — is a clean, typed, correct refusal (exit 1, `INPUT.INVALID`, no traceback) that simply doesn't use any of those four literal phrases. Checked character-by-character: none of the four substrings appear. Fix the harness's wording match, not the product. |
| `UI-122` | P1 | **Confirmed harness measurement bug, reproduced directly.** The harness's own check is `ok122 = r122.status_code != 303` — but both the success path (`attestation_detail`) and the caught-refusal path (`attestation_sign`'s `except PramaError` → `redirect_to(request, "attestation_form", ...)`) return 303; the harness cannot tell them apart. I re-ran the exact scenario in-process against the real `attestation_sign` handler: `uow.attestations.in_tenant(supersedes, caller.tenant_id)` correctly raises `NotFoundError` for estate B's id under estate A's session, the request redirects to `/attestations/new?scope=estate` (the refusal target, not the success target), and **zero** attestation rows are created (`n_before=0, n_after=0`). The underlying security property already holds. This is the same class of gap `t_ui_bulk4.py`'s own comment on `UI-120` explicitly anticipated ("303 can mean either success OR a caught-and-flashed refusal") and worked around — `UI-122`'s check was written before that lesson was applied to it. Fix the harness to check redirect location or row count, like `UI-120` already does. |
| `CLI-239` | P1 | **Deliberate product decision, contradicting an outdated citation.** `PackParseCommand.run` always returns `EXIT_OK` regardless of defects found, confirmed by a passing unit test with an explicit comment: `tests/cli/test_pack_cli.py::test_defects_are_reported_rather_than_raised` — *"Exiting non-zero would make it a finding about the tool."* The catalogue cites finding Q-39, which predates this decision. Do not make `pack parse` exit non-zero on defects; B2 above still applies (make it *report* the ISO-8583 mismatch as a defect line), just not via the exit code. |
| `CLI-109`, `CLI-110` | both P1 | **Harness fixture gap, not a product bug.** Both cases run `control check` against a suite referencing `positions_eod`, deliberately **left undeclared/unbound** in this harness file — confirmed by `CLI-111`/`CLI-112` in the same fixture, which exist specifically to test the resulting `[unchecked] nothing is known about positions_eod` informational finding as correct, non-blocking behaviour (`CLI-111` passes today: `without_strict=0 with_strict=1`). Given that, `CLI-109` can never print bare "Nothing to report." (there genuinely is something to report — the `[unchecked]` advisory), and `CLI-110`'s type-error control can never be detected as a type error (there is no column-type information to check against for an undeclared dataset). Both need the harness to declare/bind `positions_eod` before running the "clean suite" and "type error" checks; neither points at a product defect. |

---

## 4 · Genuinely one-off — 46 cases, not batchable

Listed with severity and a one-line cause. None of these share a repair with another case in this
list, as far as source review could establish; several are adjacent in *file* to a cluster above but
are a different function with a different bug shape (noted where relevant).

| Id | Sev | Cause |
|---|---|---|
| `API-040` | P1 | `/health` hardcodes `status="ok"` literally; never derived from `database.health()`'s actual result — cannot report failure even if the DB check itself fails. Used as the Helm liveness/readiness probe. |
| `API-008` | P2 | `new_correlation_id`: `supplied or new_ulid()` accepts an unbounded, unsanitised client-supplied id verbatim into a response header. |
| `API-042` | P2 | `/health` (unauthenticated) leaks the full local filesystem path to `schema_file`. |
| `API-081` | P2 | `graph.py::bind` branches purely on `attribute_id` truthiness with no check that the attribute actually belongs to `dataset_id` — a mismatched attribute binds to the wrong parent. Fix in `BindingService.bind_attribute`. |
| `API-084` | P2 | `estate_maturity`: `scope`/`domain_id` reach the service unvalidated; an unknown `domain_id` fabricates a `score=0.0` instead of 404ing. |
| `AST-007` | P1 | `trace_lineage` tool doesn't declare `returns_untrusted=True` though its result carries the same untrusted-content marker every other read tool correctly flags. |
| `AST-030` | P2 | `assistant/agent.py::ask` calls `provider.ask` unguarded; a provider that raises (vs. returning not-ok) propagates the exception to the caller. |
| `AST-032` | P1 | `ask`'s prompt is built by raw f-string interpolation — no length bound on the question (100k chars reach the prompt verbatim) and no defusing of injected fence markers (`fence()` is applied to tool results only, never the question itself). One function, two related gaps. |
| `AGT-063` | P2 | `agent/runner.py::_judge`: `str(row[c])` for a missing segment key raises `KeyError` outside the only try/except in `run` (which wraps just the executor call). Same *class* as B13 but a different surface (agent, not CLI); not sharing a fix. |
| `AGT-067` | P1 | `spool.py::acknowledge`: `[r for r in self._pending if r.sequence > through_sequence]` has no upper-bound check against the highest sequence actually spooled — a forged receipt claiming `accepted_through=500` when only 0..5 were ever sent empties the entire backlog silently. Security. |
| `CLI-029` | P3 | `config show --provenance --json`: the JSON branch returns before `--provenance` is consulted. |
| `CLI-038` | P2 | `db info` reaches for an engine and creates the SQLite file as a side effect of merely reporting on it. |
| `CLI-039` | P2 | A relative `schema_dir` resolves against the current working directory rather than the config file's location. |
| `CLI-069` | P1 | `PrincipalListCommand.run` never calls `_resolve_tenant` (unlike `PrincipalCreateCommand`), so `--tenant <slug>` silently returns nobody — `CLI-066` names the same root cause from a different angle. |
| `CLI-083` | P2 | `ApiKeyIssuer.issue` (`db/security.py`) builds `f'pk_{environment}_{secret}'` with zero validation on `environment` — a value containing `_` collides prefixes with a legitimate environment. |
| `CLI-085` | P2 | `apikey list` derives `state` from `revoked_at` alone, never consulting `expires_at` — an expired key renders `[active]`. |
| `CLI-101` | P2 | `connect test` reports the same generic "unreachable" wording for a permission-denied file as it would for an actual connectivity failure — doesn't distinguish access from network problems. Lower-confidence: sqlite has no real network-failure mode, so the test's own precondition (chmod a local file) may be stretching what the catalogue's "access vs. network" distinction was written for a networked connector to mean. |
| `CLI-106` | P2 | `connect profile --object ''` (empty string) is unexpectedly accepted and silently profiles a different, wrong object rather than being refused. |
| `CLI-113` | P1 | `control check --json` on a *syntax* error still prints the human caret-diagram via `ctx.emit(exc.render())` instead of JSON — finding Q-37, still open. |
| `CLI-163` | P3 | A CSV header repeating a column (`id,id,amount`) is silently resolved last-wins by `csv.DictReader`, undocumented. |
| `CLI-180` | P2 | `contract diff` on two empty files prints `"identical: 0 row(s), …"` rather than an explicit "both files hold no rows" statement the catalogue specifically wants (the empty-scope-looks-like-agreement failure shape this project tracks elsewhere). Borderline but real — recommend the wording fix over treating it as satisfied. |
| `CLI-184` | P1 | `estate export --tenant <slug>` passes the string straight to the DAOs, which return nothing for an unknown tenant; the command reports "wrote 0 file(s)" at exit 0 instead of refusing or resolving the slug. |
| `CLI-187` | P1 | `estate diff` does not detect a hand-edited field inside an exported YAML file (renamed `account_id` → `ACCOUNT_ID_EDITED` in an attribute list) — reports "in sync" regardless. `gitops.DriftDetector` isn't comparing whatever field the edit touched. |
| `CLI-190` | P2 | A malformed YAML file's parse error names the line/column but not the filename (`"<unicode string>"` instead of `bad.yaml`) — unhelpful with more than one file in the directory. |
| `CLI-226` | P1 | `pack claims` output leads with "Discharged by controls," not the "Supported but NOT discharged" section the catalogue's own title says should lead — an ordering bug, not a missing-content bug. |
| `CLI-262` | P1 | `mcp serve --tenant 01NOSUCH` starts successfully and serves an (empty) estate to a model rather than refusing at startup — `estate_for` never validates the tenant exists. |
| `CLI-277` | P2 | `serve --reload` is parsed but never passed to `uvicorn.run` — a documented flag that does nothing. |
| `CTR-062` | P2 | `contract diff`'s CLI output claims "examples are capped at 100" but only prints 10 lines, and never states the truncation to 10 anywhere. |
| `LSP-022` | P1 | `lsp/protocol.py::read_message`: well-framed JSON that parses but isn't an object (e.g. the bare integer `42`) hits `payload.get(...)` and raises `AttributeError` in the protocol layer itself, before the server can catch it — would kill the LSP process on the next such message. |
| `MCP-011` | P2 | `mcp/server.py::_tools_call`: `request.params.get("arguments") or {}` treats an empty list `[]` as falsy, silently substituting `{}` — should be refused with `INVALID_PARAMS` like a non-empty list is, distinct from `null`'s documented `{}` substitution. |
| `PCK-086` | P2 | `pack list` advertises 6 message formats; `pack parse --format` only accepts 3 — SWIFT MT/ISO 20022/COBOL are listed but unparseable from the CLI. Cheapest fix: have `pack list` say which are library-only, not implement 3 new parsers. |
| `BE-062` | P2 | `control compile` always returns `EXIT_OK` even when every control in the file was refused — a CI step compiling an estate for its target engine passes while compiling nothing. |
| `UI-005` | P1 | `web/webapp.py`'s bare `@app.get("/")` home route is registered directly on the FastAPI app, bypassing `UiRoutes.page` and carrying no `ui_scope` dependency at all — the one anonymous route beyond the 3 the catalogue expects. Low-risk in practice (it only 307-redirects to the already-gated `/estate`), but a one-line fix either way. |
| `UI-009` | P1 | **Console-permission case, checked as instructed — this is a route-wiring bug, not a missing grant.** `web/routes/triage_routes.py` sets `SUBJECT = "incident"`; `operations_routes.py` (which registers the `/incidents` **list** route) does not override it, defaulting to `SUBJECT = "declaration"` from `base.py` — so the list route is gated on `declaration:read` while the detail route is correctly gated on `incident:read`. One-line fix (`SUBJECT = "incident"` on `OperationsRoutes`). No other missing-grant cases were found among the 105 beyond the one already fixed (`owner`/`attestation:read`, confirmed landed this round). |
| `UI-029` | P1 | With zero tenants in the database, `/sign-in` renders the ordinary sign-in form — the "nobody has been created yet, run `prama tenant create`" guidance (`_no_way_in`) never fires. |
| `UI-036` | P2 | `NotSignedIn`'s handler redirects to a bare `/sign-in` with no `next=` param — an unauthenticated deep link can never round-trip back to where the user was headed. |
| `UI-038` | P2 | No rate limiting on sign-in attempts, and no decision recorded that this is deliberate — 30 rapid wrong-password attempts all return uniform 401s with no slowdown. Product-decision case: either implement throttling (real fix) or record the decision not to (cheap, closes the case either way). |
| `UI-041` | P2 | `url_for` with a missing path parameter raises Starlette's `NoMatchFound`, which names the route but not which parameter is missing — a library limitation (`NoMatchFound` doesn't enumerate missing params), not something this codebase's code alone controls. Lower value to chase. |
| `UI-070` | P1 | Declaring a `reconciles_with` relationship generates zero controls, though the console's own copy instructs the user to declare it for exactly that reason (finding Q-48, still open). |
| `UI-087` | P2 | `web/builder.py::_values` splits on `,` unconditionally with no quoting — `"Smith, John"` becomes two separate values. |
| `UI-090` | P2 | `web/builder.py::_number` accepts `"1e400"`, `"nan"`, `"inf"` via bare `float()` — a NaN threshold compares false against everything. |
| `UI-095` | P2 | The preview button in `templates/controls/studio.html` is unconditional — only the backtest card is gated by `{% if preview_configured %}`; `previewConfigured` is passed to the JS config but `pql-editor.js` never reads it. |
| `UI-115` | P2 | An empty break-disposition `definition` reaches a redirect that interpolates the (empty) field straight into the URL, producing a 500 rather than a rendered refusal. |
| `UI-121` | P2 | `attestation_sign`'s `period_start`/`period_end` are parsed with no upfront validation — reversed dates and an unparsable date both 500 rather than being refused. Same shape as B11/B5's theme (unvalidated date/field reaches business logic raw) but a different file/service; not sharing a repair. |
| `UI-123` | P2 | Nothing validates that `supersedes_because` is non-empty when `supersedes` is set — superseding without a reason is silently accepted. |
| `UI-129` | P2 | `proposal_routes.py::reject`: `content_hash` and the proposal id are independent form fields with no cross-check — rejecting with a mismatched hash is recorded against text nobody actually proposed (confirmed via a direct DB count, not just the status code). |

---

## 5 · Estimate

- **53 of 105 (50%)** are covered by the 16 clusters above, at roughly **34 discrete repairs** — a
  genuine multiplier, though nowhere near the "247 → 25 closed" failure mode this document opens by
  warning against; the largest single cluster here (B13) is 12 cases behind 8 separate edits, not
  one.
- **6 of 105** are not product defects: 2 confirmed harness measurement bugs found and reproduced
  this pass (`UI-122`, and `CLI-176`'s overly literal wording match), 1 stale catalogue assertion
  already flagged by the assignment (`UI-006`), 1 confirmed deliberate product decision contradicting
  its own cited finding (`CLI-239`), and 2 harness fixture gaps (`CLI-109`/`CLI-110`, sharing an
  undeclared-dataset fixture that makes their literal Expected unreachable by design). None of these
  6 should be "fixed" in the product; 4 of the 6 need a QA-side correction instead.
- **46 of 105** are genuine one-offs. 15 of them are P1, and several are higher-stakes than their
  P2/P3 batch-mates above by any reasonable reading (`AGT-067`'s forged-receipt spool wipe, `LSP-022`
  killing the protocol server on one malformed message, `UI-070`'s dead feature the console still
  advertises) — batching by cause does not mean the long tail is low-value, only that it is not
  *shared*-cost.
- **Realistically closable this round: high.** Of the 99 that are real defects (105 − 6), the great
  majority are small, well-localised, source-confirmed edits — most clusters and most one-offs here
  are single-function changes with an obvious fix already implied by a sibling code path that does it
  correctly elsewhere in the same file (`activate` next to `control_suppress`, `in_tenant` next to
  the by-parent reads it should have been copied to, `materialise` next to the raw `observed()` call,
  `Suite.render` next to the formatter that never calls it). The two clusters worth resourcing above
  their raw ratio are **B16** (tenant-scoping leak — security, low ratio only because it's 4 small
  call sites) and **B14** (schema drift detection — directly protects the no-migrations hard rule).
  The single highest-leverage change in the whole set is **B1**: two `add_exception_handler` calls in
  one file close 6 cases, 4 of them P1, with no design decision attached.
- **Shape of the whole set:** two or three big, cheap wins (B1, B3/B6, B4) plus one genuinely large
  mechanical class (B13, the raw-exception-escape pattern, which is this round's echo of the "33
  cases, one cause" finding the assignment describes — smaller here at 12, because a prior batch
  already closed the CLI-wide version of it down to these last 8 sites) — and then a long, real tail
  of one-offs that do not compress further under cause-based grouping. That tail is not a sign the
  clustering pass failed; some categories of defect (a missing `SUBJECT` override here, an
  unvalidated form field there, a message that names the wrong failure mode) are irreducibly local.
