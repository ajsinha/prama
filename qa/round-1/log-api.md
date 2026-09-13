# Prama — HTTP API execution log

Cases are in `cases-api.md` and were written before this run. Every case here carries its **actual**
result. Where a written expectation turned out to be wrong about the product rather than the product
being wrong, the case is marked PASS and the note says "expectation corrected".

## Run

| | |
|---|---|
| Date | 2026-09-12 / 13 (UTC) |
| Build | `develop` @ `46b4b3c`, `VERSION = 0.1.0`, `SCHEMA_VERSION = 1`, `IR_VERSION = 0.1.0` |
| Interpreter | CPython 3.13.15 from `~/.local/share/uv/python`, repo venv |
| Server | `prama --config /tmp/qa-api/app.yaml serve --port 19300` — a real uvicorn process |
| Transport | real HTTP over the loopback wire (httpx + curl). **Not** the ASGI test transport |
| Database | sqlite at `/tmp/qa-api/prama.db`, applied from `<repo>/schema/sqlite.sql` (digest `5df0746f832e`, 35 tables, 99 statements) |
| Tenancy | `tenancy.default_tenant` left empty, as instructed |
| Tenants | `acme-bank` (under test) and `rival-bank` (the intruder) |
| Requests issued | 285 (280 HTTP calls + 5 recorded observations) |
| Cases adjudicated | 272 |

Keys were minted through the library — `prama.db.security.ApiKeyIssuer` plus `uow.api_keys.create`,
the same path `tests/api/conftest.py` uses. Nothing under `src/`, `tests/`, `schema/` or `config/`
was modified. The server process was killed at the end of the run.

Raw evidence: `/tmp/qa-api/results.json` (every status line, header of interest and body),
`/tmp/qa-api/server.log` (the tracebacks behind the three 500s).

---

## Findings

Nine defects. Three are serious.

### F-01 — Most failure responses are **not** problem+json and carry none of the six fields
**Severity: high (contract).** 37 of the 138 failure responses observed breached the stated error
contract. Everything raised as a `PramaError` is rendered correctly by
`src/prama/api/errors.py`; everything raised by **FastAPI itself** is not, because `create_app` in
`src/prama/api/app.py` registers handlers only for `PramaError` and bare `Exception`:

```python
app.add_exception_handler(PramaError, prama_error_handler)
app.add_exception_handler(Exception, unexpected_error_handler)
```

`RequestValidationError` and Starlette's `HTTPException` are never mapped, so every schema
validation failure, every unknown path and every wrong method falls through to the framework
default.

Verbatim, API-238 (`POST /api/v1/datasets` with `{}`):

```
HTTP/1.1 422 Unprocessable Content
content-type: application/json

{"detail":[{"type":"missing","loc":["body","name"],"msg":"Field required","input":{}}]}
```

No `type`, no `title`, no `status`, no `code`, **no `remedy`**, no `correlation_id`. The integrator
who was promised "the field that lets an integrator fix their call without reading our source" gets
nothing. Same shape for `{"detail":"Not Found"}` (API-011, API-012, API-185) and
`{"detail":"Method Not Allowed"}` (API-013, API-014, API-017, API-018).

This is the single largest cause of failures in this run: 25 of the 50 FAIL verdicts are this one
defect seen through a different endpoint.

Affected: API-011, 012, 013, 014, 017, 018, 088, 118a, 159–167, 170–172, 174–179, 182, 185, 195–198,
200, 203, 213, 216, 217, 238, and the sweep API-190.

### F-02 — Three endpoints return another tenant's data
**Severity: critical (isolation).** `RIVAL` is a valid key belonging to `rival-bank`. Given only an
acme-bank object id — which is a ULID, but ULIDs are not secrets and leak through every error
message that quotes one — it reads acme-bank's declarations in full.

`GET /api/v1/datasets/{acme id}/attributes` as `RIVAL` (API-135):

```
HTTP/1.1 200 OK
content-type: application/json

[{"id":"01M2C2C5NJ50EGACNTZAAQVHJP","dataset_id":"01M2C2C5BHQEPCX7GN9E8SF91D",
  "name":"trade_id","ordinal":0,"definition":"The venue trade identifier.",
  "interpretation":"Unique within a venue and business date.","semantic_type":"identifier",
  "is_cde":true,"sensitivity":"internal",
  "concept_property_id":"01M2C2C66HD66GJZ1EX3W69DGP","meta":{…,"authored_by":"01M2C2BG…"}}]
```

`GET /api/v1/concepts/{acme id}/properties` as `RIVAL` (API-137) likewise returns
`Instrument.ISIN` with its definition and `mapped_attribute_count: 2`, and
`GET /api/v1/datasets/{acme id}/bindings` (API-136) returns both of acme's physical bindings —
schema and object names included.

Root cause: the three DAO methods those routes call take no tenant. In
`src/prama/db/dao/semantic.py`:

- `AttributeDao.for_dataset(dataset_id)` — filters on `SemAttribute.dataset_id` only
- `ConceptPropertyDao.for_concept(concept_id)` — filters on `SemConceptProperty.concept_id` only
- `BindingDao.for_dataset(dataset_id)` — filters on `SemBindingVersion.dataset_id` only

Compare the sibling methods in the same classes — `critical_data_elements(tenant_id)`,
`drifted(tenant_id)` — which do filter. The route handlers in
`src/prama/api/routes/semantic.py` and `graph.py` hold `caller.tenant_id` and never pass it:

```python
@router.get("/datasets/{dataset_id}/attributes", response_model=list[AttributeOut])
async def list_attributes(dataset_id: str, caller: Reader, uow: Uow) -> list[AttributeOut]:
    return [attribute_out(v, dataset_id=dataset_id)
            for v in await uow.attributes.for_dataset(dataset_id)]
```

The rest of tenant isolation is sound — 34 other cross-tenant probes all returned 404 with the
object verifiably unchanged, and every cross-tenant **write** was refused (API-145 to API-155).
`X-Prama-Tenant` is ignored entirely (API-158). This is three missed filters, not a design failure.

### F-03 — Three 500s, and the correlation-id header is missing on exactly those responses
**Severity: high.** Two distinct crashes, plus a header contract that fails on the one path it was
written for.

**(a) A naive `valid_at` crashes a read.** `GET /api/v1/datasets/{id}?valid_at=2026-01-01`
(API-214) and `?valid_at=2026-01-01T00:00:00` (API-215) both return 500. FastAPI happily parses
both into *timezone-naive* `datetime`s, the value reaches the DAO, and the type decorator's write
guard fires on a read bind parameter:

```
File "/home/ashutosh/PycharmProjects/prama/src/prama/db/types.py", line 56, in process_bind_param
    raise ValueError("refusing to store a naive datetime; attach UTC before persisting")
ValueError: refusing to store a naive datetime; attach UTC before persisting
```

A date with no time is the most natural thing a human types into a bitemporal query.

**(b) Deeply nested JSON crashes an amendment.** API-173 posts a 500-level nested object inside
`DatasetAmendIn.changes` — a free-form `dict[str, Any]` with no depth bound:

```
File "/home/ashutosh/PycharmProjects/prama/src/prama/core/pjson.py", line 96, in dumpb
    return _orjson.dumps(value, default=_default, option=option)
TypeError: Recursion limit reached
```

orjson's recursion limit is 254; an authenticated caller with `declaration:write` can reach it with
one request.

**(c) No `X-Correlation-Id` on a 500.** Verbatim:

```
HTTP/1.1 500 Internal Server Error
server: uvicorn
content-length: 342
content-type: application/problem+json

{"type":"https://prama.dev/problems/internal","title":"an unexpected error occurred",...}
```

Every other one of the 282 responses in this run carried the header; these three did not. The cause
is middleware ordering. `correlate` is registered with `app.middleware("http")`, which sits *inside*
Starlette's `ServerErrorMiddleware`, so when `call_next` raises, `correlate` never reaches its
`response.headers[...] = cid` line and the outer handler writes the response without it. The body
still carries `correlation_id`, so the id is recoverable — but the docstring's promise is explicit:

> It is the one thing a user can quote back to support, so it must survive the paths where
> everything else has gone wrong.

It does not survive exactly those paths.

### F-04 — Authorisation is decided after the request body is parsed
**Severity: medium.** API-088: `POST /api/v1/datasets` with a `declaration:read` key and the body
`{` returns **422**, not 403. A caller with read-only credentials can therefore enumerate the write
schema — field names, types, bounds and the full enum vocabularies — by sending deliberately wrong
bodies to endpoints they are not allowed to call. (API-177 shows a single 422 listing all thirteen
relationship kinds.) Contrast API-037, where an *unauthenticated* caller correctly gets 401 before
the body is looked at; the same ordering should apply to the scope guard.

### F-05 — `page.total` ignores the filter it is reported beside
**Severity: medium.** API-201: `GET /api/v1/datasets?unbound=true` returned 2 items and
`{"total": 4, "limit": 50, "offset": 0}`. `list_datasets` computes
`await uow.datasets.count_current(caller.tenant_id)` unconditionally, whatever branch produced the
items. A client paginating on that total pages into nothing; a screen reading it reports a number
that is not the number of things on the screen. Same on API-202 (`criticality=1`: 0 items, total 4).

### F-06 — `Allow` on a 405 names only one method
**Severity: low.** `PUT /api/v1/datasets` and `OPTIONS /api/v1/datasets` both answer
`405` with `allow: POST`, though the path also serves `GET`. RFC 9110 requires `Allow` to list
every supported method. Affected: API-014, API-018.

### F-07 — `HEAD` is not served on `GET` routes
**Severity: low.** `HEAD /api/v1/health` → `405`, `allow: GET`. Health probes and load balancers
commonly use HEAD. FastAPI's `APIRouter.get` does not add HEAD the way a plain Starlette `Route`
does, so no read endpoint answers it.

### F-08 — `known_at` on its own is silently discarded
**Severity: medium (correctness).** API-209:
`GET /api/v1/datasets/{DS1}?known_at=2000-01-01T00:00:00Z` returned **200 with the current
version** — the belief as of the year 2000 reported as version 3, recorded today. The route's
branch is:

```python
if valid_at and known_at:      ... as_of(...)
elif valid_at:                 ... valid_at(...)
else:                          ... current(...)
```

`known_at` alone falls into `else`. This is not a refusal the caller can see; it is a wrong answer
to a bitemporal question, in the product whose stated purpose is that "an evidence replay depends on
the second". Either honour it or refuse it — but do not answer a different question.

The full bitemporal path, where both are supplied, works correctly: API-211 asked for the belief at
a moment between the initial declaration and the correction and got version 1 with
`sensitivity: "internal"`, the pre-correction truth.

### F-09 — The 401 remedy names a CLI command that does not exist
**Severity: medium (doc rot).** Both 401 remedies send the reader to `prama apikey`:

> "Send `Authorization: Bearer pk_live_…`, or the X-Prama-API-Key header. Create one with
> `prama apikey create`."
> "Check the key is current and has not been revoked. `prama apikey list` shows which keys exist for
> a tenant and their state."

Following it literally (API-231):

```
prama: error: argument <command>: invalid choice: 'apikey' (choose from 'version', 'config',
'connect', 'connectors', 'bundle', 'contract', 'control', 'db', 'estate', 'lsp', 'mcp', 'pack',
'bench', 'principal', 'serve', 'tenant')
```

There is no `apikey` group, and `prama principal` offers only `create`, `list` and `roles`. As far
as the shipped CLI is concerned there is **no way to mint an API key at all** — the credential the
entire HTTP API requires. This QA pass had to mint keys through the library to proceed. Every other
remedy in the product was followed literally and worked (API-230, 232–237).

---

## Observations (not defects)

| # | Observation |
|---|---|
| O-01 | `/health`, `/capabilities` and `/relationship-kinds` take no caller and answer unauthenticated. Sensible for the first two; `/relationship-kinds` publishes the product's modelling vocabulary to anyone who can reach the port. |
| O-02 | When both `X-Prama-Api-Key` and `Authorization` are sent and disagree, `X-Prama-Api-Key` wins (`presented = x_prama_api_key or _bearer(authorization)`). Worth stating in the OpenAPI description. |
| O-03 | Tier-1 maker-checker is real and strict: an amendment needs an approver (API-096a) and the author may not be that approver (API-096). The refusal reads well. |
| O-04 | `GET /estate/maturity?domain_id=<nonexistent>` returns an all-zero score rather than a 404, so a typo in a domain id reads as "this domain has nothing declared". |
| O-05 | Slug generation drops non-Latin characters: `"取引 — Számla — ✅ — 🏦"` became `szamla`. Two differently-named CJK datasets would collide on slug. |
| O-06 | `/api/v1/docs` loads Swagger UI from `cdn.jsdelivr.net`. On an air-gapped host — the case `prama bundle seal ./offline` exists for — the docs page renders blank. |
| O-07 | An unknown key in `changes` returns **409 `ENTITY.CONFLICT`** ("unknown field(s) for SemDatasetVersion: ['not_a_column']"). It is a 4xx that names the field, but the family is wrong: this is bad input, not a conflict with stored data. |
| O-08 | `GET /datasets?unbound=true&criticality=1` silently ignores `criticality` — the route is `if/elif/else`. A supplied filter that is dropped without a word is a usability trap. |
| O-09 | Only `/datasets` paginates. `/relationships`, `/concepts`, `/journeys`, `/connections` return bare lists with a hard-coded internal cap of 500 and no way for a caller to know they were truncated. |
| O-10 | `POST /relationships/{id}/reject` on an already-confirmed relationship succeeds (API-227), flipping `status` from `confirmed` to `rejected` with no guard or warning. |
| O-11 | `deps.py` tells callers to "Send the X-Prama-Principal header identifying the acting user", but no route reads it (API-240 sends it and it is ignored), and the path that raises that message is unreachable — see the BLOCKED case below. |

---

## What worked well

Worth recording, because it is most of the surface.

- **Authentication is solid.** All 22 authentication cases passed. Revoked, expired, unknown,
  prefix-collision, wrong-scheme, empty, 8 KB and UTF-8 credentials are all refused with one
  indistinguishable 401 — deliberately non-enumerable, and it holds on the wire.
- **Scope enforcement is complete and uniform.** All 15 `declaration:read` routes accepted a
  read-only key; all 15 write routes refused it with 403, a remedy naming the scope and the sentence
  from `SCOPES`, and `context.held` showing what the credential actually carries. An empty scope
  list permitted nothing, including on read routes. `declaration:read` does not imply
  `relationship:read`. No side effects from any refusal.
- **Cross-tenant writes are all refused**, with 404 rather than 403, and every target object was
  re-read afterwards and found unchanged.
- **The bitemporal model is right** where it is exercised: amend opens a new validity period,
  correct supersedes a belief without touching validity, and `valid_at` + `known_at` together
  returned the genuine pre-correction answer.
- **Conflicts are real conflicts.** Duplicate names on datasets, attributes, concepts, properties
  and connections all returned 409 with actionable remedies; the same name in a second tenant
  returned 201, so uniqueness does not leak the other estate.
- **Semantic conflict detection works.** Mapping two attributes with different semantic types to
  one canonical property produced a critical conflict with a readable message.
- **Every remedy that named an action worked** — except F-09.

---

## Case results

Verdict key: **PASS** / **FAIL** / **BLOCKED** / **NOT RUN**.

### A. Discovery, meta and routing

| Case | Request | Status | Content-Type | Verdict | Observed |
|---|---|---|---|---|---|
| API-001 | `GET http://127.0.0.1:19300/api/v1/openapi.json` | 200 | application/json | **PASS** | openapi 3.1.0, info.version 0.1.0, 25 paths / 34 operations |
| API-002 | `GET http://127.0.0.1:19300/api/v1/docs` | 200 | text/html | **PASS** | Swagger UI HTML; assets are loaded from cdn.jsdelivr.net (O-06) |
| API-003 | `GET /health` | 200 | application/json | **PASS** | status ok, dialect sqlite, schema_file is the repo schema |
| API-004 | `GET /health` | 200 | application/json | **PASS** | 200 with no credential — the route declares no caller (by design) |
| API-005 | `GET /capabilities` | 200 | application/json | **PASS** | features exactly as the source declares |
| API-006 | `GET /relationship-kinds` | 200 | application/json | **PASS** | 13 kinds, all seven fields present |
| API-007 | `GET /relationship-kinds` | 200 | application/json | **PASS** | 200 unauthenticated — observation O-01, not a defect |
| API-008 | `GET /capabilities` | 200 | application/json | **PASS** | X-Correlation-Id present |
| API-009 | `GET /health` | 200 | application/json | **PASS** | echoed verbatim: qa-cid-000009 |
| API-010 | `GET /datasets` | 401 | application/problem+json | **PASS** | 401 and X-Correlation-Id both present |
| API-011 | `GET /no-such-thing` | 404 | application/json | **FAIL** | status correct, but the body is FastAPI's `{"detail": …}` in `application/json` — PROBLEM breached (F-01) |
| API-012 | `GET http://127.0.0.1:19300/totally-unknown` | 404 | application/json | **FAIL** | status correct, but the body is FastAPI's `{"detail": …}` in `application/json` — PROBLEM breached (F-01) |
| API-013 | `DELETE /health` | 405 | application/json | **FAIL** | 405 and `Allow: GET` correct; status correct, but the body is FastAPI's `{"detail": …}` in `application/json` — PROBLEM breached (F-01) |
| API-014 | `PUT /datasets` | 405 | application/json | **FAIL** | 405; `Allow: POST` omits GET (F-06); status correct, but the body is FastAPI's `{"detail": …}` in `application/json` — PROBLEM breached (F-01) |
| API-015 | `GET /datasets/` | 307 | — | **PASS** | 307 to http://127.0.0.1:19300/api/v1/datasets, CID present |
| API-016 | `GET /health/` | 307 | — | **PASS** | 307 to /api/v1/health |
| API-017 | `HEAD /health` | 405 | application/json | **FAIL** | HEAD on a GET route is 405 (F-07) |
| API-018 | `OPTIONS /datasets` | 405 | application/json | **FAIL** | 405 with `Allow: POST` — GET omitted (F-06); status correct, but the body is FastAPI's `{"detail": …}` in `application/json` — PROBLEM breached (F-01) |

### B. Authentication

| Case | Request | Status | Content-Type | Verdict | Observed |
|---|---|---|---|---|---|
| API-019 | `GET /datasets` | 401 | application/problem+json | **PASS** | 401 AUTH.UNAUTHORISED, 'this request carried no API key' |
| API-019b | `POST /datasets` | 401 | application/problem+json | **PASS** | same refusal on a write |
| API-020 | `GET /datasets` | 401 | application/problem+json | **PASS** | 401 'that API key is not usable' |
| API-021 | `GET /datasets` | 401 | application/problem+json | **PASS** | identical title/code/remedy to API-020 — not enumerable |
| API-022 | `GET /datasets` | 401 | application/problem+json | **PASS** | prefix matched, hash did not; same generic refusal |
| API-023 | `GET /datasets` | 401 | application/problem+json | **PASS** | revoked key refused, same wording |
| API-024 | `GET /datasets` | 401 | application/problem+json | **PASS** | expired key refused, same wording |
| API-025 | `GET /datasets` | 200 | application/json | **PASS** | 200 via X-Prama-Api-Key |
| API-026 | `GET /datasets` | 200 | application/json | **PASS** | 200 — header name case-insensitive |
| API-027 | `GET /datasets` | 401 | application/problem+json | **PASS** | 401 — the alternative header is not a bypass |
| API-028 | `GET /datasets` | 401 | application/problem+json | **PASS** | 401 'carried no API key' — Basic is not a bearer |
| API-029 | `GET /datasets` | 200 | application/json | **PASS** | 200 — scheme comparison is case-insensitive |
| API-030 | `GET /datasets` | — | — | **PASS** | 401 'carried no API key' (run with curl; httpx refuses the header) |
| API-031 | `GET /datasets` | 401 | application/problem+json | **PASS** | 401, no 5xx |
| API-032 | `GET /datasets` | — | — | **PASS** | 200 — whitespace stripped (run with curl) |
| API-033 | `GET /datasets` | 401 | application/problem+json | **PASS** | 401 on an 8 KB bearer, no 5xx, no hang |
| API-034 | `GET /datasets` | — | — | **PASS** | 401 on a UTF-8 bearer (run with curl) |
| API-035 | `GET /datasets` | 401 | application/problem+json | **PASS** | 401 |
| API-036 | `POST /datasets` | 403 | application/problem+json | **PASS** | X-Prama-Api-Key wins: the READ key decided, so the write was 403 (O-02) |
| API-037 | `POST /datasets` | 401 | application/problem+json | **PASS** | 401, not 422 — authentication precedes body parsing |
| API-038 | `POST /datasets` | 401 | application/problem+json | **PASS** | 401 |
| API-038b | `GET /datasets?limit=500` | 200 | application/json | **PASS** | no dataset named revoked-write exists |
| API-039 | `DELETE /datasets/01M2C2C5BHQEPCX7GN9E8SF91D` | 401 | application/problem+json | **PASS** | 401 |
| API-039b | `GET /datasets/01M2C2C5BHQEPCX7GN9E8SF91D` | 200 | application/json | **PASS** | DS1 still current |
| API-040 | `GET /datasets` | 401 | application/problem+json | **PASS** | ten consecutive clean 401s; no lockout, no 429, no 5xx |
| API-040b | `GET /datasets` | 200 | application/json | **PASS** | 200 immediately afterwards |
| API-239 | _(sweep / observation)_ | — | — | **BLOCKED** | not executable: api_key.principal_id is NOT NULL in the schema, so no principal-less key can exist |
| API-240 | `GET /datasets` | 200 | application/json | **PASS** | 200 — X-Prama-Principal is ignored; no route reads it (O-11) |

### C. Authorisation

| Case | Request | Status | Content-Type | Verdict | Observed |
|---|---|---|---|---|---|
| API-041 | `GET /datasets` | 200 | application/json | **PASS** | 200 with a declaration:read key |
| API-042 | `GET /datasets/01M2C2C5BHQEPCX7GN9E8SF91D` | 200 | application/json | **PASS** | 200 with a declaration:read key |
| API-043 | `GET /datasets/01M2C2C5BHQEPCX7GN9E8SF91D/history` | 200 | application/json | **PASS** | 200 with a declaration:read key |
| API-044 | `GET /datasets/01M2C2C5BHQEPCX7GN9E8SF91D/attributes` | 200 | application/json | **PASS** | 200 with a declaration:read key |
| API-045 | `GET /datasets/01M2C2C5BHQEPCX7GN9E8SF91D/bindings` | 200 | application/json | **PASS** | 200 with a declaration:read key |
| API-046 | `GET /critical-data-elements` | 200 | application/json | **PASS** | 200 with a declaration:read key |
| API-047 | `GET /concepts` | 200 | application/json | **PASS** | 200 with a declaration:read key |
| API-048 | `GET /concepts/01M2C2C630B7AHG22EM2F7ZKKD/properties` | 200 | application/json | **PASS** | 200 with a declaration:read key |
| API-049 | `GET /journeys` | 200 | application/json | **PASS** | 200 with a declaration:read key |
| API-050 | `GET /journeys/01M2C2C6FJ1YVQPCKEK5NCR1RY` | 200 | application/json | **PASS** | 200 with a declaration:read key |
| API-051 | `GET /connections` | 200 | application/json | **PASS** | 200 with a declaration:read key |
| API-052 | `GET /bindings/drifted` | 200 | application/json | **PASS** | 200 with a declaration:read key |
| API-053 | `GET /estate/maturity` | 200 | application/json | **PASS** | 200 with a declaration:read key |
| API-054 | `GET /estate/conflicts` | 200 | application/json | **PASS** | 200 with a declaration:read key |
| API-055 | `GET /estate/coverage-gaps` | 200 | application/json | **PASS** | 200 with a declaration:read key |
| API-056 | `GET /relationships` | 403 | application/problem+json | **PASS** | 403, remedy names relationship:read |
| API-057 | `POST /datasets` | 403 | application/problem+json | **PASS** | 403 AUTH.FORBIDDEN, remedy names declaration:write, context.held=declaration:read, no side effect |
| API-058 | `POST /datasets/01M2C2C5BHQEPCX7GN9E8SF91D/amend` | 403 | application/problem+json | **PASS** | 403 AUTH.FORBIDDEN, remedy names declaration:write, context.held=declaration:read, no side effect |
| API-059 | `POST /datasets/01M2C2C5BHQEPCX7GN9E8SF91D/correct` | 403 | application/problem+json | **PASS** | 403 AUTH.FORBIDDEN, remedy names declaration:write, context.held=declaration:read, no side effect |
| API-060 | `DELETE /datasets/01M2C2C5BHQEPCX7GN9E8SF91D` | 403 | application/problem+json | **PASS** | 403 AUTH.FORBIDDEN, remedy names declaration:write, context.held=declaration:read, no side effect |
| API-061 | `POST /datasets/01M2C2C5BHQEPCX7GN9E8SF91D/attributes` | 403 | application/problem+json | **PASS** | 403 AUTH.FORBIDDEN, remedy names declaration:write, context.held=declaration:read, no side effect |
| API-062 | `POST /datasets/01M2C2C5BHQEPCX7GN9E8SF91D/bindings` | 403 | application/problem+json | **PASS** | 403 AUTH.FORBIDDEN, remedy names declaration:write, context.held=declaration:read, no side effect |
| API-063 | `POST /concepts` | 403 | application/problem+json | **PASS** | 403 AUTH.FORBIDDEN, remedy names declaration:write, context.held=declaration:read, no side effect |
| API-064 | `POST /concepts/01M2C2C630B7AHG22EM2F7ZKKD/properties` | 403 | application/problem+json | **PASS** | 403 AUTH.FORBIDDEN, remedy names declaration:write, context.held=declaration:read, no side effect |
| API-065 | `POST /attributes/01M2C2C5NJ50EGACNTZAAQVHJP/mapping` | 403 | application/problem+json | **PASS** | 403 AUTH.FORBIDDEN, remedy names declaration:write, context.held=declaration:read, no side effect |
| API-066 | `POST /journeys` | 403 | application/problem+json | **PASS** | 403 AUTH.FORBIDDEN, remedy names declaration:write, context.held=declaration:read, no side effect |
| API-067 | `PUT /journeys/01M2C2C6FJ1YVQPCKEK5NCR1RY/steps` | 403 | application/problem+json | **PASS** | 403 AUTH.FORBIDDEN, remedy names declaration:write, context.held=declaration:read, no side effect |
| API-068 | `POST /connections` | 403 | application/problem+json | **PASS** | 403 AUTH.FORBIDDEN, remedy names declaration:write, context.held=declaration:read, no side effect |
| API-069 | `POST /relationships` | 403 | application/problem+json | **PASS** | 403 AUTH.FORBIDDEN, remedy names relationship:write |
| API-070 | `POST /relationships/01M2C2C7AHPN6XYMWPEQJS8KQV/confirm` | 403 | application/problem+json | **PASS** | 403 AUTH.FORBIDDEN, remedy names relationship:write |
| API-071 | `POST /relationships/01M2C2C7AHPN6XYMWPEQJS8KQV/reject` | 403 | application/problem+json | **PASS** | 403 AUTH.FORBIDDEN, remedy names relationship:write |
| API-072 | `POST /datasets` | 403 | application/problem+json | **PASS** | remedy quotes the SCOPES sentence verbatim |
| API-073 | `POST /datasets` | 403 | application/problem+json | **PASS** | context.held = declaration:read |
| API-074 | `GET /datasets` | 403 | application/problem+json | **PASS** | 403 — an empty scope list permits nothing |
| API-075 | `GET /estate/maturity` | 403 | application/problem+json | **PASS** | 403 — an empty scope list permits nothing |
| API-076 | `GET /concepts` | 403 | application/problem+json | **PASS** | 403 — an empty scope list permits nothing |
| API-077 | `GET /relationships` | 403 | application/problem+json | **PASS** | 403, remedy names relationship:read |
| API-078 | `POST /datasets` | 403 | application/problem+json | **PASS** | 403 — an empty scope list permits nothing |
| API-079 | `DELETE /datasets/01M2C2C5BHQEPCX7GN9E8SF91D` | 403 | application/problem+json | **PASS** | 403 — an empty scope list permits nothing |
| API-080 | `POST /relationships` | 403 | application/problem+json | **PASS** | 403, remedy names relationship:write |
| API-081 | `GET /critical-data-elements` | 403 | application/problem+json | **PASS** | 403 — an empty scope list permits nothing |
| API-082 | `GET /datasets` | 403 | application/problem+json | **PASS** | context.held = (none) |
| API-083 | `GET /health` | 200 | application/json | **PASS** | 200 — meta routes take no caller |
| API-084 | `GET /relationships` | 200 | application/json | **PASS** | 200 |
| API-085 | `GET /datasets` | 403 | application/problem+json | **PASS** | 403, remedy names declaration:read |
| API-086 | `POST /relationships` | 403 | application/problem+json | **PASS** | 403, remedy names relationship:write |
| API-087a | `GET /datasets` | 200 | application/json | **PASS** | 200 |
| API-087b | `POST /concepts` | 201 | application/json | **PASS** | 201 |
| API-087c | `GET /relationships` | 200 | application/json | **PASS** | 200 |
| API-087d | `POST /relationships` | 201 | application/json | **PASS** | 201 |
| API-088 | `POST /datasets` | 422 | application/json | **FAIL** | 422, not 403 — the body is parsed before the scope guard runs (F-04); status correct, but the body is FastAPI's `{"detail": …}` in `application/json` — PROBLEM breached (F-01) |

### D. Happy paths

| Case | Request | Status | Content-Type | Verdict | Observed |
|---|---|---|---|---|---|
| API-089 | `POST /datasets` | 201 | application/json | **PASS** | 201, version 1, authored_by = alice |
| API-090 | `POST /datasets` | 201 | application/json | **PASS** | 201, every field echoed including grain, rhythm and tags |
| API-091 | `GET /datasets` | 200 | application/json | **PASS** | both datasets listed, page.total 2 |
| API-092 | `GET /datasets/01M2C2C5BHQEPCX7GN9E8SF91D` | 200 | application/json | **PASS** | 200 |
| API-093 | `POST /datasets/01M2C2C5BHQEPCX7GN9E8SF91D/attributes` | 201 | application/json | **PASS** | 201, is_cde true |
| API-094 | `GET /datasets/01M2C2C5BHQEPCX7GN9E8SF91D/attributes` | 200 | application/json | **PASS** | 200, contains trade_id |
| API-095 | `GET /critical-data-elements` | 200 | application/json | **PASS** | 200, contains trade_id |
| API-096a | `POST /datasets/01M2C2C5BHQEPCX7GN9E8SF91D/amend` | 422 | application/problem+json | **PASS** | 422 INPUT.INVALID 'a Tier-1 dataset amendment requires approval' — expectation corrected, the control is right |
| API-096 | `POST /datasets/01M2C2C5BHQEPCX7GN9E8SF91D/amend` | 422 | application/problem+json | **PASS** | 422 again: 'cannot be approved by its own author'. Segregation of duties enforced. Expectation corrected (O-03) |
| API-097 | `POST /datasets/01M2C2C5BHQEPCX7GN9E8SF91D/correct` | 200 | application/json | **PASS** | 200, version 2, valid_from unchanged, recorded_at later — a correction, not an amendment |
| API-098 | `GET /datasets/01M2C2C5BHQEPCX7GN9E8SF91D/history` | 200 | application/json | **PASS** | 3 versions oldest first, valid_to / superseded_at chained correctly |
| API-099 | `POST /concepts` | 201 | application/json | **PASS** | 201 |
| API-100 | `GET /concepts` | 200 | application/json | **PASS** | 200 |
| API-101 | `POST /concepts/01M2C2C630B7AHG22EM2F7ZKKD/properties` | 201 | application/json | **PASS** | 201 |
| API-102 | `GET /concepts/01M2C2C630B7AHG22EM2F7ZKKD/properties` | 200 | application/json | **PASS** | 200, mapped_attribute_count 0 |
| API-103 | `POST /attributes/01M2C2C5NJ50EGACNTZAAQVHJP/mapping` | 200 | application/json | **PASS** | 200, concept_property_id set |
| API-104 | `GET /concepts/01M2C2C630B7AHG22EM2F7ZKKD/properties` | 200 | application/json | **PASS** | mapped_attribute_count 1 |
| API-105a | `POST /journeys` | 422 | application/problem+json | **PASS** | 422 'a Tier-2 journey declaration requires approval' — expectation corrected |
| API-105 | `POST /journeys` | 201 | application/json | **PASS** | 201 with approved_by, step_count 2 |
| API-106 | `GET /journeys` | 200 | application/json | **PASS** | 200 |
| API-107 | `GET /journeys/01M2C2C6FJ1YVQPCKEK5NCR1RY` | 200 | application/json | **PASS** | 200 |
| API-108 | `GET /journeys?dataset_id=01M2C2C5BHQEPCX7GN9E8SF91D` | 200 | application/json | **PASS** | 200, J1 returned for DS1's blast radius |
| API-109 | `PUT /journeys/01M2C2C6FJ1YVQPCKEK5NCR1RY/steps` | 200 | application/json | **PASS** | 200, step_count 3 |
| API-110 | `POST /connections` | 201 | application/json | **PASS** | 201, credential_ref stored as a reference, no secret |
| API-111 | `GET /connections` | 200 | application/json | **PASS** | 200, health_state unknown, is_usable false |
| API-112 | `GET /connections?unhealthy_only=true` | 200 | application/json | **PASS** | 200 |
| API-113 | `POST /datasets/01M2C2C5BHQEPCX7GN9E8SF91D/bindings` | 201 | application/json | **PASS** | 201, target_kind dataset |
| API-114 | `POST /datasets/01M2C2C5BHQEPCX7GN9E8SF91D/bindings` | 201 | application/json | **PASS** | 201, target_kind attribute |
| API-115 | `GET /datasets/01M2C2C5BHQEPCX7GN9E8SF91D/bindings` | 200 | application/json | **PASS** | 200, both bindings |
| API-116 | `GET /datasets/01M2C2C5BHQEPCX7GN9E8SF91D` | 200 | application/json | **PASS** | is_bound true, shape table, new version 'bound to a source' |
| API-117 | `GET /bindings/drifted` | 200 | application/json | **PASS** | 200, [] |
| API-118a | `POST /relationships` | 422 | application/json | **FAIL** | 422 for kind 'reconciles_to' (test-data error; the kind is reconciles_with) but status correct, but the body is FastAPI's `{"detail": …}` in `application/json` — PROBLEM breached (F-01) |
| API-118 | `POST /relationships` | 201 | application/json | **PASS** | 201, generates = reconciliation / break_workflow / certificate |
| API-119 | `GET /relationships` | 200 | application/json | **PASS** | 200 |
| API-120 | `GET /relationships?dataset_id=01M2C2C5BHQEPCX7GN9E8SF91D` | 200 | application/json | **PASS** | 200 |
| API-121 | `GET /relationships?kind=reconciles_with` | 200 | application/json | **PASS** | 200 |
| API-122 | `POST /relationships/01M2C2C7AHPN6XYMWPEQJS8KQV/confirm` | 200 | application/json | **PASS** | 200, status confirmed |
| API-123 | `GET /relationships?confirmed_only=true` | 200 | application/json | **PASS** | 200 |
| API-124a | `POST /relationships` | 422 | application/problem+json | **PASS** | two 422s guiding the caller (match key, then tolerance), then 201 — expectation corrected |
| API-124 | `POST /relationships/None/reject` | 404 | application/problem+json | **PASS** | 200, status rejected, reason recorded |
| API-125 | `GET /estate/maturity` | 200 | application/json | **PASS** | score 0.8, percent 80, six weighted components, next_actions with effort and value |
| API-126 | `GET /estate/maturity?scope=domain&domain_id=01CCCCCCCCCCCCCCCCCCCCCCCC` | 200 | application/json | **PASS** | 200 for an unknown domain_id: an all-zero score rather than a 404 (O-04) |
| API-127 | `GET /estate/conflicts` | 200 | application/json | **PASS** | 200, [] |
| API-128a | `POST /datasets/01M2C2C5CVXWCDA134KRH14XP2/attributes` | 201 | application/json | **PASS** | precondition: a second attribute declared, 201 |
| API-128b | `POST /attributes/01M2C2C7Z5VX53XBRZZTYC9YA2/mapping` | 200 | application/json | **PASS** | precondition: mapped to the same property with a different unit, 200 |
| API-128 | `GET /estate/conflicts` | 200 | application/json | **PASS** | 2 conflicts on Instrument.ISIN, one critical, with a readable message |
| API-129 | `GET /estate/coverage-gaps` | 200 | application/json | **PASS** | 200, unowned / no_grain / no_rhythm populated |
| API-130a | `POST /datasets` | 201 | application/json | **PASS** | precondition: DS3 declared, 201 |
| API-130 | `DELETE /datasets/01M2C2C89NCA2BB7VR0N8AWHE8` | 204 | — | **PASS** | 204 with an empty body |
| API-130b | `GET /datasets/01M2C2C89NCA2BB7VR0N8AWHE8/history` | 200 | application/json | **PASS** | history survives retirement |
| API-131 | `GET /datasets?limit=500` | 200 | application/json | **PASS** | DS3 absent from the current list |

### E. Tenant isolation

| Case | Request | Status | Content-Type | Verdict | Observed |
|---|---|---|---|---|---|
| API-132 | `GET /datasets` | 200 | application/json | **PASS** | 200, no acme dataset present |
| API-133 | `GET /datasets/01M2C2C5BHQEPCX7GN9E8SF91D` | 404 | application/problem+json | **PASS** | 404 ENTITY.NOT_FOUND |
| API-134 | `GET /datasets/01M2C2C5BHQEPCX7GN9E8SF91D/history` | 200 | application/json | **PASS** | 200 with an empty list |
| API-135 | `GET /datasets/01M2C2C5BHQEPCX7GN9E8SF91D/attributes` | 200 | application/json | **FAIL** | 200 and acme's attribute returned in full (F-02) |
| API-136 | `GET /datasets/01M2C2C5BHQEPCX7GN9E8SF91D/bindings` | 200 | application/json | **FAIL** | 200 and both of acme's bindings returned (F-02) |
| API-137 | `GET /concepts/01M2C2C630B7AHG22EM2F7ZKKD/properties` | 200 | application/json | **FAIL** | 200 and acme's concept property returned, mapped_attribute_count included (F-02) |
| API-138 | `GET /journeys/01M2C2C6FJ1YVQPCKEK5NCR1RY` | 404 | application/problem+json | **PASS** | 404 |
| API-139 | `GET /concepts` | 200 | application/json | **PASS** | 200, C1 absent |
| API-140 | `GET /journeys` | 200 | application/json | **PASS** | 200, J1 absent |
| API-141 | `GET /connections` | 200 | application/json | **PASS** | 200, CN1 absent |
| API-142 | `GET /critical-data-elements` | 200 | application/json | **PASS** | 200, empty |
| API-143 | `GET /relationships` | 200 | application/json | **PASS** | 200, empty |
| API-144 | `GET /relationships?dataset_id=01M2C2C5BHQEPCX7GN9E8SF91D` | 200 | application/json | **PASS** | 200, empty |
| API-145 | `POST /datasets/01M2C2C5BHQEPCX7GN9E8SF91D/amend` | 404 | application/problem+json | **PASS** | 404 |
| API-145b | `GET /datasets/01M2C2C5BHQEPCX7GN9E8SF91D` | 200 | application/json | **PASS** | DS1 unchanged |
| API-146 | `POST /datasets/01M2C2C5BHQEPCX7GN9E8SF91D/correct` | 404 | application/problem+json | **PASS** | 404 |
| API-146b | `GET /datasets/01M2C2C5BHQEPCX7GN9E8SF91D` | 200 | application/json | **PASS** | DS1 unchanged (version 3, confidential) |
| API-147 | `DELETE /datasets/01M2C2C5BHQEPCX7GN9E8SF91D` | 404 | application/problem+json | **PASS** | 404, explicitly not a 204 |
| API-147b | `GET /datasets/01M2C2C5BHQEPCX7GN9E8SF91D` | 200 | application/json | **PASS** | DS1 still current |
| API-148 | `POST /datasets/01M2C2C5BHQEPCX7GN9E8SF91D/attributes` | 404 | application/problem+json | **PASS** | 404 |
| API-148b | `GET /datasets/01M2C2C5BHQEPCX7GN9E8SF91D/attributes` | 200 | application/json | **PASS** | attributes unchanged: ['trade_id'] |
| API-149 | `POST /datasets/01M2C2C5BHQEPCX7GN9E8SF91D/bindings` | 404 | application/problem+json | **PASS** | 404 |
| API-149b | `GET /datasets/01M2C2C5BHQEPCX7GN9E8SF91D/bindings` | 200 | application/json | **PASS** | still exactly 2 bindings |
| API-150 | `POST /concepts/01M2C2C630B7AHG22EM2F7ZKKD/properties` | 404 | application/problem+json | **PASS** | 404 |
| API-150b | `GET /concepts/01M2C2C630B7AHG22EM2F7ZKKD/properties` | 200 | application/json | **PASS** | properties unchanged: ['ISIN'] |
| API-151a | `POST /concepts` | 201 | application/json | **PASS** | rival fixture created |
| API-151b | `POST /concepts/01M2C2GAMDSMW5EBBJXV81P89C/properties` | 201 | application/json | **PASS** | rival fixture created |
| API-151 | `POST /attributes/01M2C2C5NJ50EGACNTZAAQVHJP/mapping` | 404 | application/problem+json | **PASS** | 404 |
| API-151c | `GET /datasets/01M2C2C5BHQEPCX7GN9E8SF91D/attributes` | 200 | application/json | **PASS** | trade_id still mapped to acme's P1 |
| API-152 | `PUT /journeys/01M2C2C6FJ1YVQPCKEK5NCR1RY/steps` | 404 | application/problem+json | **PASS** | 404 |
| API-152b | `GET /journeys/01M2C2C6FJ1YVQPCKEK5NCR1RY` | 200 | application/json | **PASS** | step_count still 3 |
| API-153a | `POST /datasets` | 201 | application/json | **PASS** | rival fixture created |
| API-153 | `POST /relationships` | 404 | application/problem+json | **PASS** | 404 — a relationship cannot reach into another estate |
| API-154 | `POST /relationships/01M2C2C7AHPN6XYMWPEQJS8KQV/confirm` | 404 | application/problem+json | **PASS** | 404 |
| API-154b | `GET /relationships` | 200 | application/json | **PASS** | R1 still confirmed |
| API-155 | `POST /relationships/01M2C2C7AHPN6XYMWPEQJS8KQV/reject` | 404 | application/problem+json | **PASS** | 404 |
| API-155b | `GET /relationships` | 200 | application/json | **PASS** | R1 still confirmed |
| API-156 | `GET /estate/maturity` | 200 | application/json | **PASS** | 200 over rival's own estate |
| API-157 | `GET /estate/coverage-gaps` | 200 | application/json | **PASS** | 200, no acme object named |
| API-158 | `GET /datasets` | 200 | application/json | **PASS** | 200, rival's view only — X-Prama-Tenant ignored entirely |

### F. Validation and the error contract

| Case | Request | Status | Content-Type | Verdict | Observed |
|---|---|---|---|---|---|
| API-159 | `POST /datasets` | 422 | application/json | **FAIL** | status correct, but the body is FastAPI's `{"detail": …}` in `application/json` — PROBLEM breached (F-01) |
| API-160 | `POST /datasets` | 422 | application/json | **FAIL** | status correct, but the body is FastAPI's `{"detail": …}` in `application/json` — PROBLEM breached (F-01) |
| API-161 | `POST /datasets` | 422 | application/json | **FAIL** | status correct, but the body is FastAPI's `{"detail": …}` in `application/json` — PROBLEM breached (F-01) |
| API-162 | `POST /datasets` | 422 | application/json | **FAIL** | status correct, but the body is FastAPI's `{"detail": …}` in `application/json` — PROBLEM breached (F-01) |
| API-163 | `POST /datasets` | 422 | application/json | **FAIL** | status correct, but the body is FastAPI's `{"detail": …}` in `application/json` — PROBLEM breached (F-01) |
| API-164 | `POST /datasets` | 422 | application/json | **FAIL** | status correct, but the body is FastAPI's `{"detail": …}` in `application/json` — PROBLEM breached (F-01) |
| API-165 | `POST /datasets` | 422 | application/json | **FAIL** | 422 — extra='forbid' works as designed; status correct, but the body is FastAPI's `{"detail": …}` in `application/json` — PROBLEM breached (F-01) |
| API-166 | `POST /datasets` | 422 | application/json | **FAIL** | status correct, but the body is FastAPI's `{"detail": …}` in `application/json` — PROBLEM breached (F-01) |
| API-167 | `POST /datasets` | 422 | application/json | **FAIL** | 422 max_length enforced, not truncated; status correct, but the body is FastAPI's `{"detail": …}` in `application/json` — PROBLEM breached (F-01) |
| API-168 | `POST /datasets` | 201 | application/json | **PASS** | 201, all 100 000 characters stored and echoed |
| API-169 | `POST /datasets` | 201 | application/json | **PASS** | 201, name echoed byte-for-byte; slug is 'szamla' — CJK and emoji are dropped (O-05) |
| API-170 | `POST /datasets` | 422 | application/json | **FAIL** | status correct, but the body is FastAPI's `{"detail": …}` in `application/json` — PROBLEM breached (F-01) |
| API-171 | `POST /datasets` | 422 | application/json | **FAIL** | status correct, but the body is FastAPI's `{"detail": …}` in `application/json` — PROBLEM breached (F-01) |
| API-172 | `POST /datasets` | 422 | application/json | **FAIL** | status correct, but the body is FastAPI's `{"detail": …}` in `application/json` — PROBLEM breached (F-01) |
| API-173 | `POST /datasets/01M2C2C5BHQEPCX7GN9E8SF91D/amend` | 500 | application/problem+json | **FAIL** | 500 PRAMA.INTERNAL and no X-Correlation-Id header (F-03) |
| API-174 | `POST /datasets` | 422 | application/json | **FAIL** | status correct, but the body is FastAPI's `{"detail": …}` in `application/json` — PROBLEM breached (F-01) |
| API-175 | `POST /datasets` | 422 | application/json | **FAIL** | 422, integers not coerced; status correct, but the body is FastAPI's `{"detail": …}` in `application/json` — PROBLEM breached (F-01) |
| API-176 | `POST /datasets` | 422 | application/json | **FAIL** | status correct, but the body is FastAPI's `{"detail": …}` in `application/json` — PROBLEM breached (F-01) |
| API-177 | `POST /relationships` | 422 | application/json | **FAIL** | 422 listing all 13 kinds; status correct, but the body is FastAPI's `{"detail": …}` in `application/json` — PROBLEM breached (F-01) |
| API-178 | `POST /datasets` | 422 | application/json | **FAIL** | status correct, but the body is FastAPI's `{"detail": …}` in `application/json` — PROBLEM breached (F-01) |
| API-179 | `POST /datasets/01M2C2C5BHQEPCX7GN9E8SF91D/amend` | 422 | application/json | **FAIL** | status correct, but the body is FastAPI's `{"detail": …}` in `application/json` — PROBLEM breached (F-01) |
| API-180 | `POST /datasets/01M2C2C5BHQEPCX7GN9E8SF91D/amend` | 409 | application/problem+json | **PASS** | 409 ENTITY.CONFLICT naming the unknown field — a 4xx, but the wrong family for bad input (O-07) |
| API-181 | `POST /datasets/01M2C2C5CVXWCDA134KRH14XP2/correct` | 200 | application/json | **PASS** | 200, a no-op correction is accepted |
| API-182 | `PUT /journeys/01M2C2C6FJ1YVQPCKEK5NCR1RY/steps` | 422 | application/json | **FAIL** | status correct, but the body is FastAPI's `{"detail": …}` in `application/json` — PROBLEM breached (F-01) |
| API-183 | `GET /datasets/01AAAAAAAAAAAAAAAAAAAAAAAA` | 404 | application/problem+json | **PASS** | 404 with the documented remedy |
| API-184 | `GET /datasets/not-a-ulid` | 404 | application/problem+json | **PASS** | 404, not 422 or 500 |
| API-185 | `GET /datasets/..%2f..%2fetc%2fpasswd` | 404 | application/json | **FAIL** | 404 — no traversal, but Starlette's routing 404; status correct, but the body is FastAPI's `{"detail": …}` in `application/json` — PROBLEM breached (F-01) |
| API-186 | `GET /datasets/' OR '1'='1` | 404 | application/problem+json | **PASS** | 404, estate unchanged, no injection |
| API-187 | `GET /datasets/zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz` | 404 | application/problem+json | **PASS** | 404 on a 4 KB identifier |
| API-188 | `POST /attributes/01M2C2C5NJ50EGACNTZAAQVHJP/mapping` | 404 | application/problem+json | **PASS** | 404, remedy 'Declare the property before mapping attributes to it.' |
| API-189 | `POST /datasets/01M2C2C5BHQEPCX7GN9E8SF91D/bindings` | 404 | application/problem+json | **PASS** | 404, remedy 'Configure the connection before binding through it.' |
| API-190 | _(sweep / observation)_ | — | — | **FAIL** | 37 of 138 failure responses were not problem+json and carried none of the six fields (F-01) |
| API-191 | _(sweep / observation)_ | — | — | **FAIL** | three 500s: API-173, API-214, API-215 (F-03) |

### G. Pagination

| Case | Request | Status | Content-Type | Verdict | Observed |
|---|---|---|---|---|---|
| API-192 | `GET /datasets` | 200 | application/json | **PASS** | limit 50, offset 0, total 4 |
| API-193 | `GET /datasets?limit=1` | 200 | application/json | **PASS** | 1 item, total still 4 |
| API-194 | `GET /datasets?limit=1&offset=1` | 200 | application/json | **PASS** | a different first item from API-193 |
| API-195 | `GET /datasets?limit=0` | 422 | application/json | **FAIL** | 422 ge=1 enforced; status correct, but the body is FastAPI's `{"detail": …}` in `application/json` — PROBLEM breached (F-01) |
| API-196 | `GET /datasets?limit=-1` | 422 | application/json | **FAIL** | status correct, but the body is FastAPI's `{"detail": …}` in `application/json` — PROBLEM breached (F-01) |
| API-197 | `GET /datasets?limit=100000` | 422 | application/json | **FAIL** | 422 le=500 enforced; status correct, but the body is FastAPI's `{"detail": …}` in `application/json` — PROBLEM breached (F-01) |
| API-198 | `GET /datasets?offset=-1` | 422 | application/json | **FAIL** | status correct, but the body is FastAPI's `{"detail": …}` in `application/json` — PROBLEM breached (F-01) |
| API-199 | `GET /datasets?offset=100000` | 200 | application/json | **PASS** | 200, empty items, total still 4 |
| API-200 | `GET /datasets?limit=abc` | 422 | application/json | **FAIL** | status correct, but the body is FastAPI's `{"detail": …}` in `application/json` — PROBLEM breached (F-01) |
| API-201 | `GET /datasets?unbound=true` | 200 | application/json | **FAIL** | items = 2 but page.total = 4 — total ignores the filter (F-05) |
| API-202 | `GET /datasets?criticality=1` | 200 | application/json | **PASS** | 200, no criticality-1 dataset exists; page.total still 4 (F-05) |
| API-203 | `GET /datasets?criticality=9` | 422 | application/json | **FAIL** | status correct, but the body is FastAPI's `{"detail": …}` in `application/json` — PROBLEM breached (F-01) |
| API-204 | `GET /datasets?unbound=true&criticality=1` | 200 | application/json | **PASS** | unbound wins; the supplied criticality filter is silently dropped (O-08) |
| API-205 | `GET /relationships` | 200 | application/json | **PASS** | 200, a bare list with no page object and a hidden cap of 500 (O-09) |

### H. Bitemporal queries

| Case | Request | Status | Content-Type | Verdict | Observed |
|---|---|---|---|---|---|
| API-206 | `GET /datasets/01M2C2C5BHQEPCX7GN9E8SF91D?valid_at=2026-09-13T00:27:44Z` | 200 | application/json | **PASS** | 200, version 3 |
| API-207 | `GET /datasets/01M2C2C5BHQEPCX7GN9E8SF91D?valid_at=2000-01-01T00:00:00Z` | 404 | application/problem+json | **PASS** | 404 with the widen-the-window remedy |
| API-208 | `GET /datasets/01M2C2C5BHQEPCX7GN9E8SF91D?valid_at=2099-01-01T00:00:00Z` | 200 | application/json | **PASS** | 200, current version — validity is open-ended |
| API-209 | `GET /datasets/01M2C2C5BHQEPCX7GN9E8SF91D?known_at=2000-01-01T00:00:00Z` | 200 | application/json | **FAIL** | 200 with the CURRENT version. known_at on its own is silently discarded (F-08) |
| API-210 | `GET /datasets/01M2C2C5BHQEPCX7GN9E8SF91D?valid_at=2026-09-13T00:27:44Z&known_at=2026-09-13T00:27:44Z` | 200 | application/json | **PASS** | 200, version 3 |
| API-211 | `GET /datasets/01M2C2C5BHQEPCX7GN9E8SF91D?valid_at=2026-09-13T00:27:44Z&known_at=2026-09-13T00:23:47.922177Z` | 200 | application/json | **PASS** | 200, version 1 — the pre-correction belief, sensitivity 'internal' |
| API-212 | `GET /datasets/01M2C2C5BHQEPCX7GN9E8SF91D?valid_at=2026-09-13T00:27:44Z&known_at=2000-01-01T00:00:00Z` | 404 | application/problem+json | **PASS** | 404 |
| API-213 | `GET /datasets/01M2C2C5BHQEPCX7GN9E8SF91D?valid_at=yesterday` | 422 | application/json | **FAIL** | 422; status correct, but the body is FastAPI's `{"detail": …}` in `application/json` — PROBLEM breached (F-01) |
| API-214 | `GET /datasets/01M2C2C5BHQEPCX7GN9E8SF91D?valid_at=2026-01-01` | 500 | application/problem+json | **FAIL** | 500 PRAMA.INTERNAL, no X-Correlation-Id (F-03) |
| API-215 | `GET /datasets/01M2C2C5BHQEPCX7GN9E8SF91D?valid_at=2026-01-01T00:00:00` | 500 | application/problem+json | **FAIL** | 500 PRAMA.INTERNAL, no X-Correlation-Id (F-03) |
| API-216 | `GET /datasets/01M2C2C5BHQEPCX7GN9E8SF91D?valid_at=2026-01-01T00:00:00%2B99:00` | 422 | application/json | **FAIL** | 422; status correct, but the body is FastAPI's `{"detail": …}` in `application/json` — PROBLEM breached (F-01) |
| API-217 | `GET /datasets/01M2C2C5BHQEPCX7GN9E8SF91D?valid_at=` | 422 | application/json | **FAIL** | 422; status correct, but the body is FastAPI's `{"detail": …}` in `application/json` — PROBLEM breached (F-01) |

### I. Idempotence and conflicts

| Case | Request | Status | Content-Type | Verdict | Observed |
|---|---|---|---|---|---|
| API-218 | `POST /datasets` | 409 | application/problem+json | **PASS** | 409 ENTITY.CONFLICT, 'a dataset named QA Trades already exists in this tenant' |
| API-219 | `POST /datasets/01M2C2C5BHQEPCX7GN9E8SF91D/amend` | 200 | application/json | **PASS** | 200 — following the remedy works |
| API-220 | `POST /datasets/01M2C2C5BHQEPCX7GN9E8SF91D/attributes` | 409 | application/problem+json | **PASS** | 409 with the documented remedy |
| API-221 | `POST /datasets/01M2C2C5CVXWCDA134KRH14XP2/attributes` | 201 | application/json | **PASS** | 201 — uniqueness is per dataset |
| API-222 | `POST /concepts` | 409 | application/problem+json | **PASS** | 409 |
| API-223 | `POST /concepts/01M2C2C630B7AHG22EM2F7ZKKD/properties` | 409 | application/problem+json | **PASS** | 409 |
| API-224 | `POST /connections` | 409 | application/problem+json | **PASS** | 409 |
| API-225 | `DELETE /datasets/01M2C2C89NCA2BB7VR0N8AWHE8` | 404 | application/problem+json | **PASS** | 404 'no current version to retire', not a second 204 |
| API-226 | `POST /relationships/01M2C2C7AHPN6XYMWPEQJS8KQV/confirm` | 200 | application/json | **PASS** | 200, idempotent re-confirmation |
| API-227 | `POST /relationships/01M2C2C7AHPN6XYMWPEQJS8KQV/reject` | 200 | application/json | **PASS** | 200 — a confirmed relationship can be flipped to rejected with no guard (O-10) |
| API-228 | `POST /datasets/01M2C2C89NCA2BB7VR0N8AWHE8/amend` | 404 | application/problem+json | **PASS** | 404 |
| API-229 | `POST /datasets` | 201 | application/json | **PASS** | 201 — uniqueness is per tenant, so no cross-estate leak |

### J. Following the remedies

| Case | Request | Status | Content-Type | Verdict | Observed |
|---|---|---|---|---|---|
| API-230 | `GET /datasets` | 200 | application/json | **PASS** | 200 — the 401 remedy's header works |
| API-231 | _(sweep / observation)_ | — | — | **FAIL** | `prama apikey` is not a command; the 401 remedy names a CLI that does not exist (F-09) |
| API-232 | `POST /datasets` | 201 | application/json | **PASS** | 201 — a key with exactly declaration:write does what the 403 remedy promises |
| API-233a | `GET /datasets` | 200 | application/json | **PASS** | 200 |
| API-233 | `GET /datasets/01M2C2C5BHQEPCX7GN9E8SF91D` | 200 | application/json | **PASS** | 200 |
| API-234 | `GET /datasets/01M2C2C5BHQEPCX7GN9E8SF91D?valid_at=2026-09-13T00:23:48Z` | 200 | application/json | **PASS** | 200 — widening valid_at works |
| API-235 | `POST /datasets/01M2C2C5BHQEPCX7GN9E8SF91D/attributes` | 201 | application/json | **PASS** | 201 — a different name works |
| API-236a | `POST /concepts/01M2C2C630B7AHG22EM2F7ZKKD/properties` | 201 | application/json | **PASS** | 201 |
| API-236 | `POST /attributes/01M2C2C5NJ50EGACNTZAAQVHJP/mapping` | 200 | application/json | **PASS** | 200 |
| API-237a | `POST /connections` | 201 | application/json | **PASS** | 201 |
| API-237 | `POST /datasets/01M2C2C5CVXWCDA134KRH14XP2/bindings` | 201 | application/json | **PASS** | 201 |
| API-238 | `POST /datasets` | 422 | application/json | **FAIL** | the 422 body is `{"detail": [...]}` with no remedy at all (F-01) |
| API-CID-SWEEP | _(sweep / observation)_ | — | — | **FAIL** | 3 of 280 responses had no X-Correlation-Id header — all three 500s (F-03) |
---

## Summary

| Verdict | Count |
|---|---|
| **Total cases** | **272** |
| Passed | 221 |
| Failed | 50 |
| Blocked | 1 |
| Not run | 0 |

285 requests were issued to produce those 272 verdicts (API-040 is ten repeats; five entries are
recorded observations and sweeps rather than single calls).

### The 50 failures, by root cause

| Finding | Cases | Count |
|---|---|---|
| **F-01** failure responses that are not problem+json | API-011, 012, 013, 014, 017, 018, 088, 118a, 159–167, 170–172, 174–179, 182, 185, 190, 195–198, 200, 203, 213, 216, 217, 238 | 38 |
| **F-02** cross-tenant read leak | API-135, 136, 137 | 3 |
| **F-03** 500s and the missing correlation-id header | API-173, 191, 214, 215, API-CID-SWEEP | 5 |
| **F-04** authorisation after body parsing | API-088 (also counted under F-01) | — |
| **F-05** `page.total` ignores the filter | API-201 | 1 |
| **F-06** `Allow` names one method | API-014, 018 (also counted under F-01) | — |
| **F-07** HEAD not served | API-017 (also counted under F-01) | — |
| **F-08** `known_at` silently discarded | API-209 | 1 |
| **F-09** the 401 remedy names a nonexistent command | API-231 | 1 |

Several cases fail for more than one reason (API-088 is both F-01 and F-04; API-014, 017 and 018
are both F-01 and a routing defect). Each is counted once, against its most consequential cause.

### The one blocked case

**API-239** — minting a principal-less API key, to exercise
`CallerIdentity.require_principal()`'s `ValidationError` and the `X-Prama-Principal` header it
recommends. Not executable: `schema/sqlite.sql` declares `api_key.principal_id` `NOT NULL`, so the
insert fails before an HTTP request can be made:

```
sqlite3.IntegrityError: NOT NULL constraint failed: api_key.principal_id
```

Every key therefore carries a principal, so `require_principal()` can never raise and the
`X-Prama-Principal` header it names is never read. Unconfirmed whether that is deliberate; recorded
as O-11.

### Ranked for triage

1. **F-02** — cross-tenant read leak on three endpoints. Three missing `tenant_id` filters.
2. **F-03(a)** — a 500 reachable from a query string a human would plausibly type.
3. **F-01** — the error contract holds for Prama's own errors and not for FastAPI's. One
   `RequestValidationError` handler and one `HTTPException` handler would close 38 cases.
4. **F-08** — a bitemporal question answered with the wrong version, silently.
5. **F-09** — the product's own remedy points at a command that does not exist, and there appears
   to be no shipped way to mint the credential the API requires.
6. **F-03(b,c)**, **F-04**, **F-05**, then **F-06/F-07**.

---

## Closing state

The server started for this run was killed. `/tmp/qa-api/` holds the configuration, the scratch
database, `results.json` (every response captured verbatim), `server.log` (the three tracebacks) and
the harness scripts. Nothing under `src/`, `tests/`, `schema/` or `config/` was modified, and no
commit was made.
