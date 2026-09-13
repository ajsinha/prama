# QA test cases — the Prama web console, driven in a real browser

Surface under test: the HTML console mounted by `prama.web.webapp.mount_ui`, served by
`prama serve`. Driven with Playwright/Chromium against a real `uvicorn` process. `curl` is used
only where the assertion is purely a status code, a redirect target, or a response header —
those cases say so explicitly.

**These cases were written before execution.** Results are in `log-console.md`.

## Environment

```
export PATH="$PWD/.venv/bin:$PATH"
prama --config /tmp/qa-console/app.yaml db init
prama --config /tmp/qa-console/app.yaml tenant create acme-bank
prama --config /tmp/qa-console/app.yaml principal create alice --admin           --tenant acme-bank
prama --config /tmp/qa-console/app.yaml principal create bob   --role auditor    --tenant acme-bank
prama --config /tmp/qa-console/app.yaml principal create carol --role owner      --tenant acme-bank
prama --config /tmp/qa-console/app.yaml principal create dave  --role steward    --tenant acme-bank
prama --config /tmp/qa-console/app.yaml serve --port 19200
```

`tenancy.default_tenant` is deliberately **not** set: this is the authenticated deployment shape,
not the pre-authentication fixture shape. Every password is `a-long-qa-password`.

## The surface

48 UI routes are registered through one helper, `UiRoutes.page`. Every one of them takes a
permission from that helper: `declaration:read` for a GET and `declaration:write` for a mutating
verb, unless the registration passes `scope=` explicitly. Only the three sign-in/sign-out routes
pass anything (`scope=None`). The role grants under test come from
`prama.cli.principal.BUILTIN_ROLES`:

| role | holds `declaration:read` | holds `declaration:write` |
|---|---|---|
| admin | yes (`*`) | yes (`*`) |
| owner | yes (`declaration:*`) | yes (`declaration:*`) |
| steward | yes | **no** |
| auditor | yes | **no** |

Cases UI-071 onward exist to find out whether that mapping is the intended authorisation model or
an accident of the default, in **both** directions: a steward refused work that is their job, and
an auditor shown a page whose subject-matter scope they do not hold.

---

## A. Sign-in, session, and sign-out

### UI-001 — the sign-in page renders unauthenticated
**Precondition:** no cookie
**Steps:** 1. GET /sign-in in the browser
**Expected:** 200; a username field, a password field, a submit control; no redirect loop

### UI-002 — sign-in with empty username and empty password
**Precondition:** on /sign-in
**Steps:** 1. submit the form with both fields blank
**Expected:** the form is refused with a visible message; no 500; no session cookie issued

### UI-003 — sign-in with a username and no password
**Steps:** 1. fill username `alice`, leave password blank, submit
**Expected:** refused with a visible message; still on /sign-in

### UI-004 — sign-in with a wrong password
**Steps:** 1. `alice` / `wrong-password`, submit
**Expected:** refused; the message must not distinguish "no such user" from "wrong password"

### UI-005 — sign-in with an unknown username
**Steps:** 1. `nobody-here` / `a-long-qa-password`, submit
**Expected:** refused with the same message as UI-004

### UI-006 — sign-in with correct credentials as admin
**Steps:** 1. `alice` / `a-long-qa-password`, submit
**Expected:** 303 to `/estate` (or `?next=`); a `prama_session` cookie is set and **is sent back by
Chromium on the next request over plain http** — `security.cookies_https_only` defaults to true,
so this case is specifically checking that the console is usable over http on loopback

### UI-007 — sign-in as auditor, owner, steward
**Steps:** 1. repeat UI-006 for `bob`, `carol`, `dave`
**Expected:** each lands on a rendered page, not an error

### UI-008 — `?next=` is honoured for an internal path
**Steps:** 1. GET /declarations unauthenticated 2. sign in 3. observe landing page
**Expected:** either /declarations or /estate; never a 500

### UI-009 — `?next=` cannot be pointed off-site (open redirect)
**Steps:** 1. GET `/sign-in?next=https://example.com/evil` 2. sign in
**Expected:** lands on a path inside the console; the external host is discarded

### UI-010 — `?next=` with a protocol-relative URL
**Steps:** 1. GET `/sign-in?next=//example.com/evil` 2. sign in
**Expected:** as UI-009

### UI-011 — signing in twice in the same browser
**Steps:** 1. sign in as alice 2. GET /sign-in again 3. submit alice's credentials again
**Expected:** no error; a usable session afterwards

### UI-012 — HTML in the username field is escaped
**Steps:** 1. submit username `<script>alert(1)</script>` 2. inspect the rendered error
**Expected:** the string appears escaped as text or not at all; no dialog; no raw `<script>` in the DOM

### UI-013 — a very long username (4000 chars)
**Steps:** 1. submit a 4000-character username
**Expected:** refused cleanly; no 500; no truncation crash

### UI-014 — a unicode username
**Steps:** 1. submit `ॐ-अलिस-日本語-🌍` with a password
**Expected:** refused cleanly, correctly rendered, no `UnicodeDecodeError`

### UI-015 — sign-out
**Precondition:** signed in as alice
**Steps:** 1. find the sign-out control in the console chrome 2. use it
**Expected:** a sign-out control exists somewhere a signed-in person can reach it; using it ends
the session

### UI-016 — a page after sign-out
**Steps:** 1. sign out 2. GET /estate
**Expected:** 303 to /sign-in

### UI-017 — the browser Back button after sign-out
**Steps:** 1. sign out 2. press Back to a page rendered while signed in 3. reload
**Expected:** the reload redirects to /sign-in; a cached body may briefly show, but no fresh data loads

### UI-018 — a captured cookie is dead after sign-out
**Precondition:** capture the `prama_session` cookie value while signed in
**Steps:** 1. sign out 2. replay the captured cookie against /estate with curl (status code only)
**Expected:** 303 to /sign-in — server-side revocation, not client-side deletion

### UI-019 — a session outlives a principal change
**Steps:** 1. sign in as dave 2. from the CLI re-create/alter dave 3. reload a page
**Expected:** the session is refused and a sign-in is required

### UI-020 — a forged/garbage session cookie
**Steps:** 1. set `prama_session=not-a-real-cookie` 2. GET /estate (curl, status only)
**Expected:** 303 to /sign-in, never a 500

---

## B. Unauthenticated access to every route (leak check)

Each case: request the path with **no cookie** and record the status and body. Expected for all of
them: `303 -> /sign-in` with an empty body, or for POST routes a refusal. A `200` with content, or
a `500`, is a finding. `curl` is sufficient here and is used — the assertion is a status code and a
`location` header. UI-021 is additionally repeated in the browser to confirm the redirect is
followed to a usable sign-in page.

### UI-021 — GET / unauthenticated
### UI-022 — GET /estate unauthenticated
### UI-023 — GET /estate/graph.json unauthenticated
### UI-024 — GET /estate/gaps unauthenticated
### UI-025 — GET /estate/{unknown-id} unauthenticated
### UI-026 — GET /declarations unauthenticated
### UI-027 — GET /declarations/new unauthenticated
### UI-028 — POST /declarations/new unauthenticated
### UI-029 — POST /declarations/suggest unauthenticated
### UI-030 — GET /relationships unauthenticated
### UI-031 — GET /relationships/new unauthenticated
### UI-032 — POST /relationships/new unauthenticated
### UI-033 — GET /controls unauthenticated
### UI-034 — GET /controls/studio unauthenticated
### UI-035 — GET /controls/build unauthenticated
### UI-036 — POST /controls/check unauthenticated
### UI-037 — POST /controls/compile unauthenticated
### UI-038 — POST /controls/save unauthenticated
### UI-039 — POST /controls/preview unauthenticated
### UI-040 — GET /controls/backtest unauthenticated
### UI-041 — GET /proposals unauthenticated
### UI-042 — GET /incidents unauthenticated
### UI-043 — GET /reconciliation unauthenticated
### UI-044 — GET /scorecards unauthenticated
### UI-045 — GET /evidence unauthenticated
### UI-046 — GET /attestations unauthenticated
### UI-047 — GET /attestations/new unauthenticated
### UI-048 — GET /reports unauthenticated
### UI-049 — GET /reports/declarations and /reports/controls unauthenticated
### UI-050 — GET /static/css/prama.css unauthenticated
**Expected for UI-050 only:** 200. Static assets are public by design; this case exists so that a
blanket "everything redirects" result is not mistaken for a working static mount.

---

## C. Every screen as admin, empty estate

Signed in as `alice`. Chromium. For every case: record the HTTP status, assert the page has a
heading and the primary navigation, and collect **every** `console` message and `pageerror`. A
JavaScript error is a FAIL for the case even when the HTML renders — the estate map is client-side.

### UI-051 — /estate as admin, empty estate
**Expected:** 200; renders; an empty-state sentence that explains what to do next, not a bare table

### UI-052 — /estate map canvas initialises with no JS error
**Expected:** the sigma/graphology map either draws or shows an explicit "nothing declared" state;
zero page errors

### UI-053 — /estate/graph.json as admin
**Expected:** 200 JSON with nodes/edges arrays (empty is fine)

### UI-054 — /estate/gaps as admin, empty estate
**Expected:** 200; explains that there is nothing to find gaps in

### UI-055 — /estate/{unknown-id} as admin
**Expected:** 404 with a readable page, not a 500 and not a blank 200

### UI-056 — /declarations as admin, empty
**Expected:** 200; empty state points at "declare a dataset"

### UI-057 — /declarations/new as admin
**Expected:** 200; the form has name, description, grain, shape, criticality, purpose

### UI-058 — /relationships as admin, empty
### UI-059 — /relationships/new as admin, empty estate
**Expected:** 200; the two dataset selects are present and visibly empty, with an explanation —
not two silently empty dropdowns that make the form unusable with no reason given

### UI-060 — /controls as admin, empty
### UI-061 — /controls/studio as admin
**Expected:** 200; the PQL editor (CodeMirror) mounts; zero JS errors

### UI-062 — /controls/build as admin
**Expected:** 200; the rule builder renders

### UI-063 — GET /controls/check as admin
**Expected:** 405. The route is POST-only. Recorded so that "screen does not exist" is
distinguished from "screen is broken".

### UI-064 — GET /controls/preview as admin
**Expected:** 405, as UI-063

### UI-065 — /controls/backtest as admin
**Expected:** 200 or a documented refusal; no 500

### UI-066 — /proposals as admin, empty
### UI-067 — /incidents as admin, empty
### UI-068 — /reconciliation as admin, empty
### UI-069 — /scorecards as admin, empty
### UI-070 — /evidence as admin, empty
**Expected for UI-066..UI-070:** 200 each, each with an empty state that says why it is empty

### UI-071 — /attestations as admin, empty
### UI-072 — /attestations/new as admin, empty estate
**Expected:** 200; the period and scope defaults are filled in; the control list is empty but explained

### UI-073 — /reports as admin
### UI-074 — /reports/declarations as admin
### UI-075 — /reports/controls as admin
**Expected:** 200 each; a report over an empty estate must still produce a document

---

## D. The role matrix

For each role the same set of reads and the same set of writes. A **read** that 403s for a role
whose job requires it is a finding. A **read** that succeeds for a role that does not hold the
subject-matter scope is also a finding, in the other direction.

### UI-076 — /estate as auditor
### UI-077 — /declarations as auditor
### UI-078 — /controls as auditor
### UI-079 — /incidents as auditor
**Note:** `auditor` does **not** hold `incident:read`. Expected: either refused, or the page is
judged in-scope for `auditor` and the role grant is wrong. Record which.
### UI-080 — /reconciliation as auditor
**Note:** `auditor` does not hold `break:read`. As UI-079.
### UI-081 — /evidence as auditor
### UI-082 — /scorecards as auditor
### UI-083 — /attestations as auditor
### UI-084 — /reports as auditor
### UI-085 — POST /declarations/new as auditor
**Expected:** refused. An auditor "reads everything and changes nothing".
### UI-086 — POST /controls/save as auditor
**Expected:** refused
### UI-087 — the write controls are absent from the page for an auditor
**Steps:** 1. GET /declarations and /controls as auditor 2. look for "Declare", "Activate", "Suppress"
**Expected:** an action the role cannot perform is not offered. Offering it and then refusing it is
a usability defect, reported as such.

### UI-088 — /estate as owner
### UI-089 — /declarations as owner
### UI-090 — POST /declarations/new as owner
**Expected:** allowed — declaring datasets is the owner's defining job
### UI-091 — POST /controls/{id}/activate as owner
**Expected:** allowed — `control:approve`
### UI-092 — /incidents as owner
### UI-093 — /reconciliation/{definition} break accept as owner
**Note:** `owner` does not hold `break:write`. Record which way it goes.

### UI-094 — /estate as steward
### UI-095 — /incidents as steward
### UI-096 — /reconciliation as steward
### UI-097 — POST an incident triage action as steward
**Expected:** allowed — `incident:*` is the steward's defining grant
### UI-098 — POST a break assign/explain/accept as steward
**Expected:** allowed — `break:*`
### UI-099 — POST /controls/save as steward
**Expected:** allowed — `control:propose`
### UI-100 — POST /declarations/new as steward
**Expected:** refused — a steward holds `declaration:read` only

### UI-101 — what a refusal looks like in the browser
**Steps:** 1. as auditor, POST a form the role cannot perform
**Expected:** an HTML page a person can read, with the remedy; not a raw JSON body and not a stack
trace in the browser window

---

## E. Forms — declarations

All against `/declarations/new` as `alice` unless stated.

### UI-102 — submit the declaration form completely empty
**Expected:** refused with a message naming the missing field; no 500

### UI-103 — submit with only a name
**Expected:** either accepted with defaults, or refused naming what else is needed. Record which.

### UI-104 — submit a valid declaration
**Steps:** 1. name `payments.transactions`, a description, a grain, criticality 2. submit
**Expected:** 303 to a dataset or list page; the dataset appears on /declarations and /estate

### UI-105 — submit the identical declaration twice
**Expected:** the second is refused as a duplicate with a readable message, or is idempotent.
A 500 or a silent second copy is a finding.

### UI-106 — a name with a leading/trailing space
### UI-107 — a name of 5000 characters
**Expected:** refused by validation or stored to the column width; never a database error surfaced
as a 500

### UI-108 — a unicode dataset name `डेटासेट・日本語・🌍`
**Expected:** accepted or refused cleanly, and rendered correctly wherever it is echoed back

### UI-109 — `<script>alert('xss')</script>` in the description
**Expected:** stored escaped; on /declarations and /estate the string is visible as text; no dialog
fires and no `<script>` node is created. Checked in the browser by counting `script` nodes and by
registering a dialog handler.

### UI-110 — `<img src=x onerror=alert(1)>` in the dataset name
**Expected:** as UI-109; specifically no `onerror` attribute in the rendered DOM

### UI-111 — an invalid criticality value posted directly
**Steps:** 1. POST /declarations/new with `criticality=not-a-tier` (curl with a session cookie;
the browser select cannot express it)
**Expected:** 400-class refusal, not a 500

### UI-112 — an invalid shape value posted directly
**Expected:** as UI-111

### UI-113 — the "profile" button on the declaration form
**Steps:** 1. click the `#profile` button with no connection configured
**Expected:** a readable message; no unhandled JS error and no hung spinner

### UI-114 — double-submit the declaration form
**Steps:** 1. fill it 2. click submit twice quickly
**Expected:** one dataset created, or a clean duplicate refusal

---

## F. Forms — relationships

### UI-115 — /relationships/new submitted empty
**Expected:** refused; required selects block it or the server refuses

### UI-116 — a relationship with from == to
**Expected:** refused with a message, or accepted deliberately. Record which.

### UI-117 — a relationship with a non-existent dataset id posted directly
**Expected:** 400/404-class refusal, not a 500

### UI-118 — match keys given as free text with odd separators (`a;;b , c`)
**Expected:** parsed or refused; no 500

### UI-119 — a tolerance that is not a number (`abc`)
**Expected:** refused with a message naming the field

### UI-120 — a negative tolerance and a relative percent > 100
**Expected:** refused or accepted deliberately; no 500

### UI-121 — `<script>` in the relationship description
**Expected:** escaped on /relationships

### UI-122 — a valid relationship between two declared datasets
**Expected:** created; appears on /relationships and as an edge in /estate/graph.json

### UI-123 — confirm a relationship, then confirm it again
**Expected:** idempotent or a readable refusal

### UI-124 — reject a relationship that does not exist
**Expected:** 404-class, not a 500

---

## G. Forms — controls and the studio

### UI-125 — /controls/studio with valid PQL, "Check"
**Steps:** 1. type a control over the declared dataset 2. trigger the check
**Expected:** findings panel renders; no JS error

### UI-126 — /controls/studio with syntactically invalid PQL
**Expected:** the parse error is shown with a position, not a stack trace

### UI-127 — /controls/studio with an empty document, "Check"
**Expected:** a readable "nothing to check", not a 500

### UI-128 — /controls/studio with 200 KB of PQL
**Expected:** refused or handled; no hang beyond a reasonable timeout

### UI-129 — POST /controls/compile with invalid PQL
**Expected:** a readable error fragment

### UI-130 — POST /controls/save with valid PQL
**Expected:** the control is created and appears on /controls

### UI-131 — POST /controls/save with an empty body
**Expected:** refused, not a 500

### UI-132 — `<script>` inside a PQL string literal, saved and listed
**Expected:** escaped on /controls

### UI-133 — POST /controls/{unknown}/activate
**Expected:** 404-class, not a 500

### UI-134 — POST /controls/{id}/activate then again
**Expected:** idempotent or a readable refusal

### UI-135 — POST /controls/{id}/suppress
**Expected:** succeeds for a role holding `control:approve`

### UI-136 — the rule builder at /controls/build, submitted empty
**Expected:** refused, not a 500

### UI-137 — /controls/preview posted with no connection configured
**Expected:** a readable "no connection" message streamed or rendered; no 500 and no hang

### UI-138 — /controls/completions and /controls/hover posted with garbage
**Expected:** JSON or an HTML fragment; no 500

---

## H. Forms — attestations

### UI-139 — /attestations/new submitted empty
**Expected:** refused naming the missing attester name and statement

### UI-140 — sign an attestation with a valid name and statement
**Expected:** created; appears on /attestations; a detail page renders

### UI-141 — `<script>` in the attester name and statement
**Expected:** escaped on the list and detail pages

### UI-142 — a 5000-character statement
**Expected:** accepted or refused cleanly

### UI-143 — sign the same attestation twice
**Expected:** a second attestation, or a readable refusal; no 500

### UI-144 — /attestations/{unknown} and /attestations/{unknown}/pack
**Expected:** 404-class, not a 500

### UI-145 — an attestation pack downloads
**Expected:** a response with a sensible content type; no 500

---

## I. Populated estate — every screen revisited

After UI-104, UI-122, UI-130 and a CLI-driven run, revisit every screen as admin and record
status, JS errors, and whether the page shows the new data.

### UI-146 — /estate populated
### UI-147 — /estate/graph.json populated
### UI-148 — /estate/{id} for a real dataset
### UI-149 — /estate/gaps populated
### UI-150 — /declarations populated
### UI-151 — /controls populated
### UI-152 — /proposals populated
### UI-153 — /incidents populated
### UI-154 — /scorecards populated
### UI-155 — /evidence populated
### UI-156 — /reports/declarations populated
### UI-157 — /reports/controls populated

---

## J. Links, buttons, and client-side errors

### UI-158 — every primary navigation item from /estate
**Steps:** 1. as admin, click each of the eleven nav items in turn 2. record the landing status
**Expected:** eleven 200s; no 404 and no 500

### UI-159 — every in-page link on every rendered screen
**Steps:** 1. collect every `a[href]` on each screen 2. request each same-origin href
**Expected:** no 404 and no 500 from any link the console itself offers

### UI-160 — every static asset referenced by the base template
**Expected:** 200 for each CSS, JS and font the pages reference; a 404 on a vendor asset is a
finding even though the page still renders

### UI-161 — JavaScript errors across every screen
**Steps:** 1. visit every screen with `page.on("pageerror")` and `page.on("console")` attached
**Expected:** zero page errors and zero `console.error` on every screen

### UI-162 — the theme picker
**Steps:** 1. change the theme select 2. reload
**Expected:** the theme persists; no JS error

### UI-163 — the density toggle
**Expected:** toggles; persists; no JS error

### UI-164 — a tampered theme cookie
**Steps:** 1. set the theme cookie to `"><script>alert(1)</script>` 2. GET /estate
**Expected:** falls back to a permitted value; nothing injected into an attribute

### UI-165 — the responsive nav toggle at a narrow viewport
**Expected:** the collapsed menu opens and every item is reachable

---

## K. Miscellaneous and negative

### UI-166 — a page with an unexpected query string
**Steps:** 1. GET `/declarations?page=-1&sort=<script>`
**Expected:** renders or refuses; no 500, nothing injected

### UI-167 — a path-parameter route given a path-traversal value
**Steps:** 1. GET `/estate/..%2f..%2fetc%2fpasswd`
**Expected:** 404-class; no file content

### UI-168 — HEAD on a GET page
**Expected:** same status as GET, empty body (curl; status only)

### UI-169 — a POST route called with GET, for every POST-only route
**Expected:** 405 for each (curl; status only)

### UI-170 — security headers on a console response
**Steps:** 1. inspect response headers on /estate (curl; headers only)
**Expected:** record what is and is not present — CSP, X-Content-Type-Options, X-Frame-Options,
Referrer-Policy — and whether the session cookie carries HttpOnly, SameSite and Secure

### UI-171 — the OpenAPI document does not describe console pages
**Expected:** `include_in_schema=False` holds; console paths absent from /openapi.json

### UI-172 — server log during the whole run
**Expected:** no unhandled traceback in `/tmp/qa-console/server.log` for any case that was not
expected to fail
