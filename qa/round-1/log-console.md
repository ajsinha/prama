# QA execution log — the Prama web console

Cases: `cases-console.md`. Executed 2026-09-12/13 against `prama serve --port 19200`, SQLite at
`/tmp/qa-console/prama.db`, driven by Playwright against **Google Chrome 
(`channel="chrome"`)**. Every case below was run; nothing is inferred from reading the source
except where a case is explicitly marked NOT RUN with the reason.

---

## Two things that shaped the run

**1. Chromium was not installed.** `playwright.sync_api` imports, but
`~/.cache/ms-playwright` does not exist, so `chromium.launch()` fails with
*"Executable doesn't exist at .../chrome-headless-shell"*. The run proceeded against the system
Google Chrome via `channel="chrome"`, which is a real browser and satisfies the brief. Noted
because `pytest -q tests/web/test_axe.py` will fail on this machine for the same reason.

**2. The working tree changed underneath the run.** `git status` was clean at the start
(HEAD `46b4b3c`). Partway through, HEAD had moved to `3b82e40` and fourteen files under `src/`
were modified by another process, mid-edit — including `db/dao/semantic.py` and four
`web/routes/*.py` that call into it. The server process I had started held a half-updated import
of that tree and produced two 500s that **do not reproduce after a restart** (UI-148, UI-157).
They are logged honestly as artifacts, not defects. Every other finding in this log was
**re-verified against the tree as it stood after the restart** — see the re-verification block
under UI-172. I modified nothing under `src/`, `tests/`, `schema/` or `config/`.

**A setup note, not a product defect.** The task's `printf 'pw\npw\n' | prama principal create`
stores *both* lines as the password: `_read_password` does `sys.stdin.read().strip()` when stdin
is not a tty, with no confirm round. `printf '%s' 'pw' | …` is correct and is what this run used.

---

## FINDING 1 (blocker) — nobody can sign in to the console unless `tenancy.default_tenant` is set

`UI-006`, `UI-007`. This is the configuration the brief specified, and it is the configuration a
real multi-tenant deployment uses.

`AuthRoutes.sign_in` resolves the tenant like this:

```python
tenant_id = tenant.strip() or config.get_str("tenancy.default_tenant", "")
principal = None
if tenant_id:
    principal = await uow.principals.authenticate(tenant_id, username.strip(), password)
```

`tenant` is a `Form()` field — and **`auth/sign_in.html` renders no such field.** There is a
username input and a password input and nothing else. So in any deployment that does not set
`tenancy.default_tenant`, `tenant_id` is `""`, `authenticate` is never called, and
`principal` is `None` for every credential that has ever existed.

Observed, with `alice` an active admin holding the correct password:

```
POST /sign-in  username=alice&password=a-long-qa-password                     -> 401
POST /sign-in  username=alice&password=a-long-qa-password&tenant=<tenant-id>  -> 303 -> /estate
```

The console therefore has exactly two modes: `tenancy.default_tenant` set, in which case
`ui_caller` hands out `WILDCARD` to an **unauthenticated** visitor; or unset, in which case the
console cannot be entered at all. There is no authenticated multi-tenant mode.

It is compounded by the page's own diagnosis. `_no_way_in` returns `True` whenever
`tenancy.default_tenant` is empty — without counting anything — so the sign-in page tells the
operator:

> **Nobody has been created on this installation yet.** This form cannot succeed until somebody
> exists to sign in as: `prama principal create alice --admin`

Four principals existed. The one message pointing at the cause points away from it.

**Workaround used for the rest of this pass.** A hidden `tenant` input was injected into the real
form before submit. That drives the product's own POST handler and yields a genuine session
carrying the principal's real scopes, so every case downstream of sign-in is a real result.

---

## FINDING 2 (blocker) — every console write requires `declaration:write`, so the steward role is inert

`UI-098`, `UI-099`, `UI-093`, `UI-079`, `UI-080`.

`UiRoutes.page` derives the scope from the HTTP verb and **no registration overrides it**:
`declaration:read` for GET, `declaration:write` for anything mutating. Forty-five of the
forty-eight console routes are gated on those two scopes alone. Measured, signed in as each role:

```
POST                                       admin  auditor  owner  steward
/declarations/new                           422     403     422     403
/controls/save                              422     403     422     403
/controls/{id}/activate                     404     403     404     403
/controls/{id}/suppress                     303     403     303     403
/reconciliation/breaks/{id}/accept          500     403     500     403
/attestations/new                           422     403     422     403
/proposals/accept                           422     403     422     403
```

A **steward** — "works incidents and breaks; proposes controls but does not approve them", holding
`incident:*`, `break:*`, `control:propose` — is refused **every** write the console offers. The
role's entire job is unavailable through the console.

The same default is over-permissive in the other direction. An **owner** holds no `break:*` and
may nevertheless assign, explain and accept reconciliation breaks. An **auditor** holds neither
`incident:read` nor `break:read` and reads `/incidents` and `/reconciliation` at 200.

Every role reads every page — 21 of 25 paths at 200 for all four, identical:

```
/estate /estate/gaps /declarations /declarations/new /relationships /relationships/new
/controls /controls/studio /controls/build /controls/backtest /proposals /incidents
/reconciliation /scorecards /evidence /attestations /attestations/new /reports
/reports/declarations /reports/controls                 -> 200 for admin, auditor, owner, steward
```

The role vocabulary in `BUILTIN_ROLES` is real, tested by `tests/architecture/test_scopes.py`, and
consulted by the console for exactly two of its sixteen scopes.

---

## FINDING 3 — the console has no error page; 403 and 404 render as raw JSON

`UI-101`, `UI-055`, `UI-133`, `UI-144`, `UI-111`. `mount_ui` installs an exception handler for
`NotSignedIn` and for nothing else, so every other failure falls through to the API's RFC-7807
handler and the person gets a JSON document in the browser window.

As `bob` (auditor), clicking "Declare a dataset" and submitting:

> `{"type":"https://prama.dev/problems/auth-forbidden","title":"this credential does not carry the 'declaration:write' scope","status":403,"code":"AUTH.FORBIDDEN","remedy":"Issue a key with 'declaration:write' — it may decl…`

`GET /estate/01ZZZZ…` (404), `GET /incidents/NOSUCHCONTROL` (404) and a bad `criticality` (422,
a raw Pydantic error array) all do the same. The remedies are well written and none of them reach
a reader.

---

## FINDING 4 — the console offers every role every action, then refuses it

`UI-087`. Measured on the rendered page, per role:

```
auditor  /declarations  ['Declare a dataset', …]   /proposals ['Accept', 'Reject it']   /attestations ['Sign an attestation']
steward  /declarations  ['Declare a dataset', …]   /proposals ['Accept', 'Reject it']   /attestations ['Sign an attestation']
owner    /declarations  ['Declare a dataset', …]   /proposals ['Accept', 'Reject it']   /attestations ['Sign an attestation']
```

Identical for all three. Every one of those buttons 403s for the auditor and the steward, into the
JSON page of Finding 3. `caller.scopes` is on the identity at render time and no template reads it.

---

## FINDING 5 — there is no way to sign out of the console

`UI-015`. `POST /sign-out` exists and works correctly. Nothing links to it: no `a`, `button` or
`form` anywhere in the rendered chrome references it, and `grep -rn "sign_out" templates/` returns
nothing. There is also no "signed in as …" indicator, so the console never says who you are.
Signing out requires constructing a POST by hand.

The route itself is good: it moves the principal's `updated_at`, which `ui_caller` uses to refuse
every session minted earlier. A cookie captured before sign-out was verified dead afterwards
(UI-018). The same mechanism means **signing in a second time silently kills your first session**
(UI-019) — observed on two cookie jars for `dave`.

---

## FINDING 6 — a control can be silenced until an unparseable date, and silencing a control that does not exist quietly succeeds

`UI-135`. Through the real form on `/controls`, with `until=not-a-date` and a reason, the submit
succeeds and `/controls` then reports:

> Silenced — payments_transactions … **silenced until not-a-date — because reasons**

`until` is stored verbatim. The estate has stopped checking something and the field that says when
it starts again holds a string no clock will ever reach. The schema convention is ISO-8601 UTC text
in `VARCHAR(32)`; nothing enforces it here.

Separately, for a control id that does not exist:

```
POST /controls/NOSUCH/activate  -> 404   (correct)
POST /controls/NOSUCH/suppress  -> 303 -> /controls, no flash message at all
```

Two handlers on the same resource disagree about what a missing control means, and the one that
disagrees reports success.

---

## FINDING 7 — 500s from unvalidated input

`UI-112`, `UI-172`. Two reproduce on the current tree.

**An invalid `shape` reaches the INSERT.** `criticality` is caught by Pydantic (422); `shape` is
validated nowhere in the application and is caught by the database:

```
POST /declarations/new  name=shape.probe2&shape=not-a-shape  -> 500
sqlalchemy.exc.IntegrityError: (sqlite3.IntegrityError) CHECK constraint failed: ck_sem_dataset_shape
```

The CHECK constraint did its job and no bad row landed. The layer above it did not.

**The break-disposition error path crashes.** `ReconRoutes._act` catches `PramaError`, flashes it,
then redirects to `break_workbench` with the `definition` it was given. When `definition` is empty
the redirect itself raises:

```
POST /reconciliation/breaks/XYZ/accept   reason=x  (no definition)  -> 500
  prama.core.errors.NotFoundError: RecBreak 'XYZ' does not exist     <- caught and flashed
  AssertionError: Must not be empty                                  <- url_path_for, uncaught
```

The recovery path from a failed action is the thing that fails. The workbench template does carry
`<input type="hidden" name="definition">`, so this is not reachable by clicking — it needs a direct
POST. 22 occurrences in the server log across the run.

---

## FINDING 8 — declaration input is not normalised or bounded

`UI-106`, `UI-107`.

**Names are not trimmed.** `"  spaced.name  "` is stored with its padding:

```sql
select '['||name||']' from sem_dataset_version where name <> trim(name);
[  spaced.name  ]
```

The slug derives correctly (`spaced_name`) and HTML collapses the whitespace on screen, so the
console looks right while `spaced.name` and `  spaced.name  ` are two distinct declarations whose
duplicate check will never meet.

**Length is not bounded.** A 5000-character name was accepted into a `VARCHAR(255)` column:

```
select length(name), length(slug) from sem_dataset_version order by length(name) desc limit 1;
(5000, 128)
```

The slug was truncated to its 128; the name was not. SQLite ignores the width, PostgreSQL does
not — the same declaration that succeeds here raises `value too long for type character
varying(255)` on the other supported engine. It also destroys the layout of `/declarations`,
`/estate/gaps` and both report packs, which is how it was noticed.

---

## FINDING 9 — a Tier-1 dataset cannot be declared from the console

`UI-104`. Submitting the form with criticality 1:

> That declaration could not be recorded: `[INPUT.INVALID]` **a Tier-1 dataset declaration requires
> approval before it takes effect** | Next: *Submit it for review. It will be held as proposed
> until an approver signs it off.* | Context: `criticality=1, requirement='maker_checker'`

The policy is right. The remedy names an action the console does not offer: there is no
"submit for review" control on the form, and no queue that would receive it. Tier 1 — the tier the
product exists for — is a dead end in the UI. `/estate` confirms it: **TIER 1 · REGULATORY 0**
after seven declarations.

---

## FINDING 10 — a raw Python exception message is shown to the user

`UI-119`. A non-numeric tolerance on `/relationships/new`:

> That relationship could not be recorded: **could not convert string to float: 'abc'**

`_parse_tolerance` calls `float()` unguarded. Every neighbouring failure on the same form is a
properly shaped error — *"an absolute tolerance cannot be negative | Next: Use a positive
materiality threshold"*, *"a relative tolerance of 5.0 is not a fraction between 0 and 1 | Next:
Express 0.1% as 0.001"*. This one is a `ValueError` string.

(Also noted on that form: the field is named `tolerance_relative_percent` and placeholder `0.1`,
but the accepted value is a fraction — `0.1` means 10%, and the error has to explain it.)

---

## FINDING 11 — no security headers

`UI-170`. A full response from `/estate`, signed in:

```
date / server / content-length / content-type / x-correlation-id / vary: Cookie
```

No `Content-Security-Policy`, no `X-Content-Type-Options`, no `X-Frame-Options` or
`frame-ancestors`, no `Referrer-Policy`, no `Strict-Transport-Security`. The console renders
user-supplied dataset names and descriptions on every page; output escaping was verified correct
everywhere (UI-109, UI-110, UI-121, UI-132, UI-141), so CSP is the missing second layer rather
than the only one. The session cookie itself is correct: `httponly; samesite=lax; secure`,
`Max-Age=1209600`.

---

## FINDING 12 — smaller things

- **`/controls/save` is unreachable.** `UI-130`. The route is registered and works, and no
  template or script in the console posts to it — `grep -rn "control_save\|/controls/save"
  templates/ static/js/` returns nothing. The rule builder ends at *"Copy this into a suite file,
  or paste it into the studio"*. A control reaches the estate only via `/proposals`, which is
  derived from declarations; a control a person wrote cannot be saved from the console at all.
- **`GET /controls/backtest` renders a raw SSE stream as a web page.** `UI-065`. Status 200, body
  `event: failed\ndata: {"message": "no preview source is configured…"}\nevent: done\ndata:
  {"completed": 0}` shown as plain text in the browser window.
- **`HEAD` on a console page returns 405.** `UI-168`. Routes register `methods=["GET"]` and
  Starlette does not add HEAD, so a health check or link checker sees a hard failure.
- **`/reconciliation/{unknown-definition}` returns 200**, with the empty state for a real queue,
  rather than 404.
- **Relationships have no duplicate check.** `UI-118`/`UI-122`. Three identical
  `spaced.name references <img …>` rows were created and all three listed. Datasets do have one
  and it works (`UI-105`: *"a dataset named 'dup.check.me' already exists in this tenant"*).
- **Match keys are not validated.** `a;;b , c` was accepted and echoed back as *"on a;;b, c"*.
- **A non-Latin name cannot be declared.** `UI-108`. `डेटासेट・日本語・🌍` →
  *"contains no characters usable in an identifier | Next: Give the object a name containing
  letters or digits."* Those are letters. Refused cleanly and with a good message, so not a
  defect — but the identifier derivation is ASCII-only and the message says otherwise.

---

## What is genuinely good, measured

- **No unauthenticated leak anywhere.** All 30 routes in section B redirect `303 -> /sign-in` with
  a zero-length body. `/static/**` serves 200 as it should.
- **Zero JavaScript errors.** Every screen was visited with `pageerror` and `console` listeners
  attached, as all four roles. Nothing, on any page, in any role. The estate map initialises
  (7 canvas/svg nodes with 7 datasets declared), CodeMirror mounts, the theme picker, the density
  toggle and the responsive nav all work and persist.
- **No broken links.** 32 distinct same-origin hrefs harvested across 19 screens; every one
  returns < 400. All 11 nav items 200. All 11 static assets 200.
- **Output escaping is correct everywhere it was probed.** `<script>alert('xss')</script>`,
  `<img src=x onerror=alert(1)>` and `<script>alert(9)</script>` inside a PQL string literal were
  stored and re-rendered on `/declarations`, `/estate`, `/relationships`, `/controls`,
  `/attestations` and both report packs. No dialog ever fired, no raw tag ever appeared in the DOM,
  `&lt;script&gt;` present in every case.
- **Open redirect is closed, including the backslash form.** `next=https://example.com/evil`,
  `next=//example.com/evil` and `next=/\evil.example` all land on `/estate`; `next=/declarations`
  is honoured.
- **Tampered display cookies fall back safely.** `prama_theme='"><script>alert(1)</script>'` →
  `data-theme="light"`, nothing injected; `prama_density=../../etc/passwd` → `comfortable`.
- **The empty states are the best thing in the product.** Not one page shows a bare table. From
  `/incidents`: *"No control has executed against this estate. Nothing on this page is a statement
  about data quality — it is a statement that nothing has been examined yet. 0 dataset(s) are
  declared. An empty list on this page is the absence of observation, not the absence of
  problems — and the two must never be shown the same way."* `/relationships/new` over an empty
  estate says *"A relationship needs two datasets and 0 are declared"* rather than showing two
  empty dropdowns.
- **The studio is honest about what it cannot do.** *"Nothing to preview against. This deployment
  has no preview source configured, so a control can be checked and compiled here but not run.
  … Until then the studio will tell you whether a control is sound and cannot tell you what it
  will find."*
- **Attestations are properly sealed.** Signing produced a content hash, a seal, an evidence root
  and *"Unchanged since signing, and the seal verifies"*; the pack renders and a qualified
  attestation says so.

---

## Case-by-case results

### A. Sign-in, session, sign-out

| Case | Result | Observed |
|---|---|---|
| UI-001 | PASS | 200; username, password, submit all present |
| UI-002 | PASS | HTML5 `required` blocks; *"Please fill out this field."* |
| UI-003 | PASS | blocked on the password field |
| UI-004 | PASS | 401, *"Those details did not work."* |
| UI-005 | PASS | 401, identical message — no username oracle |
| UI-006 | **FAIL** | Finding 1. Correct admin credentials → 401 |
| UI-007 | **FAIL** | Finding 1; all four roles |
| UI-008 | PASS | `next=/declarations` honoured after sign-in |
| UI-009 | PASS | external host discarded → `/estate` |
| UI-010 | PASS | `//example.com/evil` discarded; `/\evil.example` also discarded |
| UI-011 | PASS | second sign-in fine; `/estate` 200 after |
| UI-012 | PASS | no dialog; no raw `<script>` in the DOM |
| UI-013 | PASS | 4000-char username refused cleanly, 401 |
| UI-014 | PASS | `ॐ-अलिस-日本語-🌍` refused cleanly, rendered correctly |
| UI-015 | **FAIL** | Finding 5 — no sign-out control anywhere |
| UI-016 | PASS | `/estate` after sign-out → `/sign-in` |
| UI-017 | PASS | Back lands on `/sign-in`; reload stays there |
| UI-018 | PASS | captured cookie dead after sign-out (303) |
| UI-019 | PASS | second sign-in invalidates the first session |
| UI-020 | PASS | garbage cookie → 303, no 500 |

### B. Unauthenticated access — UI-021 … UI-050

**All 30 PASS.** 29 routes `303 -> /sign-in`, body length 0; `GET /` `307 -> /estate` then 303;
`/static/css/prama.css` 200 (10952 bytes), as intended. `curl` used — the assertion is a status
code and a `location` header. UI-021 re-run in Chrome: the redirect is followed to a usable
sign-in page.

### C. Every screen as admin, empty estate

| Case | Result | Observed |
|---|---|---|
| UI-051 – UI-054 | PASS | 200; explanatory empty states; no JS errors |
| UI-055 | **FAIL** | 404 correct, but the body is raw JSON (Finding 3) |
| UI-056 – UI-062 | PASS | 200 each; CodeMirror mounts; builder renders |
| UI-063, UI-064 | PASS | 405 — POST-only, as expected |
| UI-065 | **FAIL** | raw SSE text rendered as a page (Finding 12) |
| UI-066 – UI-075 | PASS | 200 each; packs render over an empty estate |

### D. The role matrix

| Case | Result | Observed |
|---|---|---|
| UI-076 – UI-078 | PASS | auditor reads estate, declarations, controls |
| UI-079 | **FAIL** | auditor reads `/incidents` without `incident:read` |
| UI-080 | **FAIL** | auditor reads `/reconciliation` without `break:read` |
| UI-081 – UI-084 | PASS | evidence, scorecards, attestations, reports all 200 |
| UI-085, UI-086 | PASS | auditor 403 on both writes |
| UI-087 | **FAIL** | Finding 4 |
| UI-088 – UI-092 | PASS | owner reads and writes as designed |
| UI-093 | **FAIL** | owner accepts breaks without `break:write` |
| UI-094 – UI-096 | PASS | steward reads all three |
| UI-097 | NOT RUN | the console registers no incident-write route at all — `/incidents/{id}` is the only triage route and it is a GET |
| UI-098 | **FAIL** | steward 403 on assign/explain/accept (Finding 2) |
| UI-099 | **FAIL** | steward 403 on `/controls/save` (Finding 2) |
| UI-100 | PASS | steward correctly refused `/declarations/new` |
| UI-101 | **FAIL** | Finding 3 — raw JSON 403 |

### E. Declaration forms

| Case | Result | Observed |
|---|---|---|
| UI-102 | PASS | HTML5 blocks the empty submit |
| UI-103 | PASS | name alone accepted, defaults to Tier 4 |
| UI-104 | **FAIL** | Finding 9 — Tier 1 is a dead end |
| UI-105 | PASS | *"a dataset named 'dup.check.me' already exists in this tenant"* |
| UI-106 | **FAIL** | Finding 8 — name stored untrimmed |
| UI-107 | **FAIL** | Finding 8 — 5000 chars into `VARCHAR(255)` |
| UI-108 | PASS | refused cleanly with a clear message |
| UI-109, UI-110 | PASS | escaped; no dialog; no `onerror` in the DOM |
| UI-111 | PASS | 422 (raw Pydantic array — presentation covered by Finding 3) |
| UI-112 | **FAIL** | Finding 7 — 500, `CHECK constraint failed: ck_sem_dataset_shape` |
| UI-113 | NOT RUN | `#profile` is gated on `preview_configured`; absent in this deployment |
| UI-114 | PASS | double submit → exactly one row, second 422 |

### F. Relationship forms

| Case | Result | Observed |
|---|---|---|
| UI-115 | PASS | required selects block the empty submit |
| UI-116 | PASS | *"a relationship must join two different datasets"* |
| UI-117 | PASS | 422, *"the from dataset '01ZZZ…' does not exist"* |
| UI-118 | PASS | parsed, no 500 — but unvalidated (Finding 12) |
| UI-119 | **FAIL** | Finding 10 — raw `ValueError` text |
| UI-120 | PASS | negative and 500% both refused with good messages |
| UI-121, UI-122 | PASS | created; dataset names escaped on the list |
| UI-123 | NOT RUN | relationships are created `confirmed`; no confirm affordance renders. Direct `POST /relationships/XYZ/confirm` → 404 |
| UI-124 | PASS | 404 for an unknown relationship |

### G. Controls and the studio

| Case | Result | Observed |
|---|---|---|
| UI-125 | PASS | findings panel renders; no JS error |
| UI-126 | PASS | *"`[PQL.SYNTAX]` expected a control and found 'CHEKC'"*, with position |
| UI-127 | PASS | empty document handled, no 500 |
| UI-128 | PASS | 200 KB of PQL: 8.1 s, no hang, no error |
| UI-129 | PASS | readable error fragment |
| UI-130 | **FAIL** | Finding 12 — `/controls/save` unreachable from the console |
| UI-131 | PASS | 422 |
| UI-132 | PASS | escaped; no dialog |
| UI-133 | PASS | 404 (raw JSON — Finding 3) |
| UI-134 | NOT RUN | accepting a proposal puts the control straight into RUNNING, so no activate affordance ever renders. Direct POST on an unknown id → 404 |
| UI-135 | **FAIL** | Finding 6 |
| UI-136 | PASS | *"unknown rule '' | Next: Choose one of: not_null, in_list, matches, …"* |
| UI-137 | PASS | the "nothing to preview against" message quoted above |
| UI-138 | PASS | both return 200 JSON on garbage input |

### H. Attestations

| Case | Result | Observed |
|---|---|---|
| UI-139 | PASS | required blocks name and statement |
| UI-140 | PASS | signed; hash, seal and evidence root shown; detail 200 |
| UI-141 | PASS | escaped on list and detail |
| UI-142 | PASS | 5000-character statement accepted |
| UI-143 | PASS | second attestation created — deliberate (*"a correction supersedes it"*) |
| UI-144 | PASS | 404 for both the unknown attestation and its pack |
| UI-145 | PASS | pack renders, correctly marked *"This attestation is qualified"* |

### I. Populated estate

| Case | Result | Observed |
|---|---|---|
| UI-146 | PASS | 7 datasets, 3 relationships; map draws; no JS error |
| UI-147 | PASS | nodes and edges present and correct |
| UI-148 | PASS (after restart) | 500 during the concurrent edit, 200 after. `TypeError: AttributeDao.for_dataset() missing 1 required keyword-only argument: 'tenant_id'` — the call site on disk passes it; the server held a half-updated import. **Artifact, not a defect.** |
| UI-149 – UI-151 | PASS | gaps, declarations and controls all reflect the new data |
| UI-152 | PASS | 2 proposals derived; Accept works; control reaches RUNNING |
| UI-153 – UI-155 | PASS | correctly still "nothing has been examined" — no run has occurred |
| UI-156 | PASS | *"All 7 covered. 7 … declared but not connected"* |
| UI-157 | PASS (after restart) | same artifact as UI-148 |

### J. Links, buttons, client-side errors

| Case | Result | Observed |
|---|---|---|
| UI-158 | PASS | all 11 nav items 200, zero JS errors |
| UI-159 | PASS | 32 distinct same-origin links, none ≥ 400 |
| UI-160 | PASS | 11 referenced assets, none failing |
| UI-161 | PASS | zero page errors and zero `console.error` on 19 screens × 4 roles |
| UI-162 | PASS | `light → wallstreet`, persists via `prama_theme` |
| UI-163 | PASS | `comfortable → compact`, persists via `prama_density` |
| UI-164 | PASS | falls back to `light` / `comfortable`; nothing injected |
| UI-165 | PASS | at 390×780 the toggler shows and all 11 items become reachable |

### K. Miscellaneous and negative

| Case | Result | Observed |
|---|---|---|
| UI-166 | PASS | `?page=-1&sort=<script>` → 200, nothing injected |
| UI-167 | PASS | `/estate/..%2f..%2fetc%2fpasswd` → 404 |
| UI-168 | **FAIL** | `HEAD /estate` → 405 (Finding 12) |
| UI-169 | PASS | 405 on all seven POST-only routes; `GET /proposals/accept` → 404, not shadowed |
| UI-170 | **FAIL** | Finding 11 — no security headers |
| UI-171 | PASS | `/openapi.json` → 404; no schema document is served at all, so no console path can appear in one |
| UI-172 | **FAIL** | 59 tracebacks: 22 `AssertionError` (Finding 7), 6 `TypeError` (the concurrent-edit artifact), the rest expected `ValidationError`/`NotFoundError`/`ConflictError` from negative cases |

**Re-verification after the tree settled.** Server restarted against the current tree; Findings 1,
2, 6, 7, 11 and UI-168 all reproduce identically, and UI-148/UI-157 do not. The full 25-path sweep
was re-run for all four roles: 21×200, 2×404, 2×405, zero JS errors, zero unexpected statuses.

---

## Summary

| | Count |
|---|---|
| **Total cases** | **172** |
| Passed | 148 |
| Failed | 20 |
| Blocked | 0 |
| Not run | 4 |

**Not run (4):** UI-097 (no incident-write route exists in the console), UI-113 and the backtest
button (`#profile` and `#backtest` are gated on `preview_configured`, unset here), UI-123 (no
confirm affordance renders — relationships are created already confirmed), UI-134 (no activate
affordance renders — accepting a proposal goes straight to RUNNING). Each was covered as far as
the surface allows by a direct POST, recorded in the row.

**The 20 failures, by finding:** F1 sign-in blocker (UI-006, 007) · F2 scope model (UI-079, 080,
093, 098, 099) · F3 no error page (UI-055, 101) · F4 actions offered then refused (UI-087) ·
F5 no sign-out (UI-015) · F6 suppression (UI-135) · F7 500s (UI-112, 172) · F8 input
normalisation (UI-106, 107) · F9 Tier 1 dead end (UI-104) · F10 raw exception text (UI-119) ·
F11 security headers (UI-170) · F12 smaller (UI-065, 130, 168).

**Release view.** Findings 1 and 2 are blockers: with the brief's configuration the console cannot
be entered at all, and once entered — via the tenant field the form declines to render — the
steward role can perform no action the console offers. Everything behind those two gates is in
good shape: no leaks, no JS errors, no broken links, correct escaping everywhere, and empty states
better than most shipped products have.

**Cleanup.** The server on port 19200 was stopped at the end of the run. All scratch output,
screenshots and driver scripts are under `/tmp/qa-console/`. Nothing under `src/`, `tests/`,
`schema/` or `config/` was modified, and no commit or push was made.
