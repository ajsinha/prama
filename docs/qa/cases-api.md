# Prama — HTTP API test cases

**Surface:** the HTTP API served by `prama serve` (FastAPI, mounted at `/api/v1`).
**Build:** `VERSION = 0.1.0`, branch `develop` at `46b4b3c`.
**Written:** before execution. Results live in `log-api.md`.

## Environment under test

| Item | Value |
|---|---|
| Config | `/tmp/qa-api/app.yaml` — sqlite at `/tmp/qa-api/prama.db`, `schema_dir: <repo>/schema`, long `security.session_secret`, `tenancy.default_tenant` deliberately **empty** |
| Server | real uvicorn process, `prama --config /tmp/qa-api/app.yaml serve --port 19300` (the wire, not the ASGI test transport) |
| Base URL | `http://127.0.0.1:19300` |
| Tenant A | `acme-bank` — the estate under test |
| Tenant B | `rival-bank` — the intruder's estate |

## Credentials

Minted through the library (`prama.db.security.ApiKeyIssuer` + `uow.api_keys.create`), the same
path `tests/api/conftest.py` uses. Nothing in the repository was modified to mint them.

| Alias | Tenant | Scopes | State |
|---|---|---|---|
| `WILD` | acme-bank | `*` | active |
| `READ` | acme-bank | `declaration:read` | active |
| `NONE` | acme-bank | `[]` (empty list) | active |
| `RELREAD` | acme-bank | `relationship:read` | active |
| `EXPIRED` | acme-bank | `*` | `expires_at` = yesterday |
| `REVOKED` | acme-bank | `*` | `revoked_at` set |
| `RIVAL` | rival-bank | `*` | active |
| `UNKNOWN` | — | — | well-formed `pk_test_…` string never issued |

> **Note on a credential that could not be minted.** `CallerIdentity.require_principal()` raises a
> `ValidationError` when a key carries no principal, and `deps.py` documents an `X-Prama-Principal`
> header. `schema/sqlite.sql` declares `api_key.principal_id` `NOT NULL`, so a principal-less key
> cannot exist. Cases API-239 and API-240 record that observation rather than asserting a defect.

## The contracts under test

Stated once here; individual cases refer to them by name.

- **PROBLEM** — every failure response is `Content-Type: application/problem+json` and its body
  carries `type`, `title`, `status`, `code`, `remedy` and `correlation_id`
  (`src/prama/api/errors.py::problem_document`).
- **CID** — every response, success or failure, carries an `X-Correlation-Id` header
  (`src/prama/api/app.py::correlate`).
- **NO500** — no request in this suite may produce a 5xx.
- **SCOPED** — a route's required scope is declared in its signature
  (`Reader` = `declaration:read`, `Writer` = `declaration:write`,
  `RelationshipReader` = `relationship:read`, `RelationshipWriter` = `relationship:write`).
- **TENANT** — the tenant comes from the key's own record, never from a header. An object of
  another tenant must be indistinguishable from one that does not exist: **404**, and unchanged.

## The 34 operations enumerated from `GET /api/v1/openapi.json`

| # | Method | Path | Scope in signature |
|---|---|---|---|
| 1 | GET | `/health` | none |
| 2 | GET | `/capabilities` | none |
| 3 | GET | `/relationship-kinds` | none |
| 4 | POST | `/datasets` | declaration:write |
| 5 | GET | `/datasets` | declaration:read |
| 6 | GET | `/datasets/{dataset_id}` | declaration:read |
| 7 | DELETE | `/datasets/{dataset_id}` | declaration:write |
| 8 | GET | `/datasets/{dataset_id}/history` | declaration:read |
| 9 | POST | `/datasets/{dataset_id}/amend` | declaration:write |
| 10 | POST | `/datasets/{dataset_id}/correct` | declaration:write |
| 11 | POST | `/datasets/{dataset_id}/attributes` | declaration:write |
| 12 | GET | `/datasets/{dataset_id}/attributes` | declaration:read |
| 13 | POST | `/datasets/{dataset_id}/bindings` | declaration:write |
| 14 | GET | `/datasets/{dataset_id}/bindings` | declaration:read |
| 15 | GET | `/critical-data-elements` | declaration:read |
| 16 | POST | `/concepts` | declaration:write |
| 17 | GET | `/concepts` | declaration:read |
| 18 | POST | `/concepts/{concept_id}/properties` | declaration:write |
| 19 | GET | `/concepts/{concept_id}/properties` | declaration:read |
| 20 | POST | `/attributes/{attribute_id}/mapping` | declaration:write |
| 21 | POST | `/journeys` | declaration:write |
| 22 | GET | `/journeys` | declaration:read |
| 23 | GET | `/journeys/{journey_id}` | declaration:read |
| 24 | PUT | `/journeys/{journey_id}/steps` | declaration:write |
| 25 | POST | `/connections` | declaration:write |
| 26 | GET | `/connections` | declaration:read |
| 27 | GET | `/bindings/drifted` | declaration:read |
| 28 | POST | `/relationships` | relationship:write |
| 29 | GET | `/relationships` | relationship:read |
| 30 | POST | `/relationships/{relationship_id}/confirm` | relationship:write |
| 31 | POST | `/relationships/{relationship_id}/reject` | relationship:write |
| 32 | GET | `/estate/maturity` | declaration:read |
| 33 | GET | `/estate/conflicts` | declaration:read |
| 34 | GET | `/estate/coverage-gaps` | declaration:read |

Plus `GET /api/v1/openapi.json` and `GET /api/v1/docs`, which FastAPI serves.

---

## A. Discovery, meta and routing

### API-001 — the OpenAPI document is served and parses
**Precondition:** server running.
**Request:** `GET /api/v1/openapi.json`, no auth.
**Expected:** 200, `application/json`, parses, `openapi` = 3.x, `info.version` = `0.1.0`, 34 operations.

### API-002 — `/api/v1/docs` renders
**Request:** `GET /api/v1/docs`, no auth.
**Expected:** 200, `text/html`, body references the Swagger UI bundle and `/api/v1/openapi.json`.

### API-003 — `GET /health` happy path
**Request:** `GET /api/v1/health` with `WILD`.
**Expected:** 200, JSON with `status=ok`, `version`, `schema_version`, `dialect=sqlite`, `schema_file` pointing at the repo schema. CID.

### API-004 — `GET /health` needs no credential
**Request:** `GET /api/v1/health`, no `Authorization`.
**Expected:** 200 — the route declares no caller dependency, so this is by design for a liveness probe.

### API-005 — `GET /capabilities` happy path
**Request:** `GET /api/v1/capabilities`, no auth.
**Expected:** 200; `features` reports `semantic_layer/bitemporal_history/gitops/estate_maturity/conflict_detection` true and the later-wave features false. CID.

### API-006 — `GET /relationship-kinds` happy path
**Request:** `GET /api/v1/relationship-kinds` with `WILD`.
**Expected:** 200, a list of 13 kinds, each with `kind`, `prompt`, `generates`, `needs_match_keys`, `needs_tolerance`, `directional`, `carries_trust`.

### API-007 — `GET /relationship-kinds` unauthenticated
**Request:** same, no header.
**Expected:** 200 — the route takes no caller. Recorded as an observation about which routes are public, not as a pass/fail of the auth model.

### API-008 — `X-Correlation-Id` present on a success
**Request:** `GET /api/v1/capabilities`.
**Expected:** response carries `X-Correlation-Id` (CID).

### API-009 — a supplied correlation id is echoed, not replaced
**Request:** `GET /api/v1/health` with `X-Correlation-Id: qa-cid-000009`.
**Expected:** 200 and `X-Correlation-Id: qa-cid-000009`.

### API-010 — `X-Correlation-Id` present on a failure
**Request:** `GET /api/v1/datasets`, no auth.
**Expected:** 401 **and** the `X-Correlation-Id` header (CID applies to failures too).

### API-011 — unknown path under the API prefix
**Request:** `GET /api/v1/no-such-thing` with `WILD`.
**Expected:** 404. PROBLEM.

### API-012 — unknown path outside the API prefix
**Request:** `GET /totally-unknown` with `WILD`.
**Expected:** 404, no 5xx.

### API-013 — method not allowed
**Request:** `DELETE /api/v1/health` with `WILD`.
**Expected:** 405. PROBLEM. `Allow` header naming GET.

### API-014 — method not allowed on a collection
**Request:** `PUT /api/v1/datasets` with `WILD`.
**Expected:** 405, PROBLEM.

### API-015 — trailing slash on a collection
**Request:** `GET /api/v1/datasets/` with `WILD`.
**Expected:** either a 307 redirect to the canonical path or a 200. Not a 5xx. Whatever it is, it is consistent.

### API-016 — trailing slash on a meta route
**Request:** `GET /api/v1/health/` with `WILD`.
**Expected:** 307 or 404, not a 5xx.

### API-017 — `HEAD` on a GET route
**Request:** `HEAD /api/v1/health` with `WILD`.
**Expected:** 200 with no body, CID.

### API-018 — `OPTIONS` on a route
**Request:** `OPTIONS /api/v1/datasets` with `WILD`.
**Expected:** a 2xx/405 with an `Allow` header. Not a 5xx.

---

## B. Authentication

Unless stated, the probe is `GET /api/v1/datasets` (a `declaration:read` route) and, where a write
is named, `POST /api/v1/datasets` with `{"name":"auth-probe"}`.

### API-019 — no `Authorization` header at all
**Expected:** 401, PROBLEM, `code` = `AUTH.UNAUTHORISED`, `remedy` naming `Authorization: Bearer pk_live_…` or `X-Prama-API-Key`.

### API-020 — `Authorization: Bearer garbage`
**Expected:** 401, PROBLEM, the generic "that API key is not usable" refusal.

### API-021 — well-formed but never-issued key
**Precondition:** `UNKNOWN` = `pk_test_` + 43 random url-safe characters, never stored.
**Expected:** 401, PROBLEM, **the same** message and code as API-020 (deliberate non-enumerability).

### API-022 — a key sharing a real prefix but a wrong secret
**Precondition:** take `WILD`'s first 12 characters and append a different tail.
**Expected:** 401, PROBLEM — `issuer.verify` must fail even though `by_prefix` found a row.

### API-023 — revoked key
**Precondition:** `REVOKED`.
**Expected:** 401, PROBLEM, same refusal text as API-020.

### API-024 — expired key
**Precondition:** `EXPIRED` (`expires_at` = yesterday).
**Expected:** 401, PROBLEM, same refusal text.

### API-025 — key in `X-Prama-Api-Key` instead of `Authorization`
**Request:** `GET /api/v1/datasets` with `X-Prama-Api-Key: <WILD>`.
**Expected:** 200 — `deps.get_caller` accepts either header.

### API-026 — header-name casing of `X-Prama-Api-Key`
**Request:** `X-PRAMA-API-KEY: <WILD>`.
**Expected:** 200 — HTTP header names are case-insensitive.

### API-027 — `X-Prama-Api-Key` with a revoked key
**Expected:** 401, PROBLEM — the alternative header is not a bypass.

### API-028 — wrong auth scheme
**Request:** `Authorization: Basic <base64 of WILD>`.
**Expected:** 401, PROBLEM, the *no key supplied* refusal (`_bearer` returns "" for a non-bearer scheme).

### API-029 — scheme casing
**Request:** `Authorization: bearer <WILD>` (lowercase).
**Expected:** 200 — `_bearer` lowercases the scheme.

### API-030 — empty bearer value
**Request:** `Authorization: Bearer ` (nothing after the space).
**Expected:** 401, PROBLEM, the "carried no API key" refusal.

### API-031 — `Authorization` present but empty
**Request:** `Authorization: ` (empty value).
**Expected:** 401, PROBLEM. Not a 5xx.

### API-032 — key with surrounding whitespace
**Request:** `Authorization: Bearer   <WILD>   `.
**Expected:** 200 — `_bearer` strips. (If it refuses, that is acceptable but must be a 401, not a 500.)

### API-033 — a very long bearer value (8 KB)
**Expected:** 401, PROBLEM. Not a 5xx, not a hang.

### API-034 — unicode in the bearer value
**Request:** `Authorization: Bearer 🔑ключ`.
**Expected:** 401, PROBLEM. Not a 5xx (the value is hashed as UTF-8).

### API-035 — NUL-ish / control characters in the key
**Request:** `Authorization: Bearer pk_test_%00abc` (percent-literal, sent as text).
**Expected:** 401, PROBLEM.

### API-036 — both headers present and disagreeing
**Request:** `X-Prama-Api-Key: <READ>` and `Authorization: Bearer <WILD>`.
**Expected:** `X-Prama-Api-Key` wins (it is read first). A write then fails 403. Recorded as the observed precedence.

### API-037 — unauthenticated **write** is refused before validation
**Request:** `POST /api/v1/datasets` with an invalid body and no auth.
**Expected:** 401 (not 422) — authentication is decided before the body is read, so an anonymous caller learns nothing about the schema. Either is defensible; the case records which happens.

### API-038 — a revoked key against a write
**Request:** `POST /api/v1/datasets` `{"name":"x"}` with `REVOKED`.
**Expected:** 401, PROBLEM, and no dataset created (verified by a subsequent list).

### API-039 — an expired key against a delete
**Request:** `DELETE /api/v1/datasets/{DS1}` with `EXPIRED`.
**Expected:** 401, PROBLEM, and `DS1` still current afterwards.

### API-040 — repeated bad keys do not lock anything out
**Request:** ten consecutive 401s with `UNKNOWN`, then one request with `WILD`.
**Expected:** the tenth is still a clean 401 and the `WILD` request is 200. No rate-limit 429 is claimed by the product; this records the actual behaviour.

---

## C. Authorisation

### API-041 … API-055 — `READ` (`declaration:read`) against every `declaration:read` route
One case each; **expected 200** for all fifteen.

| Case | Request |
|---|---|
| API-041 | `GET /datasets` |
| API-042 | `GET /datasets/{DS1}` |
| API-043 | `GET /datasets/{DS1}/history` |
| API-044 | `GET /datasets/{DS1}/attributes` |
| API-045 | `GET /datasets/{DS1}/bindings` |
| API-046 | `GET /critical-data-elements` |
| API-047 | `GET /concepts` |
| API-048 | `GET /concepts/{C1}/properties` |
| API-049 | `GET /journeys` |
| API-050 | `GET /journeys/{J1}` |
| API-051 | `GET /connections` |
| API-052 | `GET /bindings/drifted` |
| API-053 | `GET /estate/maturity` |
| API-054 | `GET /estate/conflicts` |
| API-055 | `GET /estate/coverage-gaps` |

### API-056 — `READ` against `GET /relationships`
**Expected:** 403, PROBLEM, `code` = `AUTH.FORBIDDEN`, remedy naming `relationship:read` — a `declaration:read` key does **not** imply relationship reads.

### API-057 … API-068 — `READ` against every `declaration:write` route
**Expected for each:** 403, PROBLEM, `code` = `AUTH.FORBIDDEN`, `remedy` naming `'declaration:write'` and the sentence from `SCOPES`, `context.scope` = `declaration:write`, `context.held` = `declaration:read`. And **no side effect**.

| Case | Request |
|---|---|
| API-057 | `POST /datasets` |
| API-058 | `POST /datasets/{DS1}/amend` |
| API-059 | `POST /datasets/{DS1}/correct` |
| API-060 | `DELETE /datasets/{DS1}` |
| API-061 | `POST /datasets/{DS1}/attributes` |
| API-062 | `POST /datasets/{DS1}/bindings` |
| API-063 | `POST /concepts` |
| API-064 | `POST /concepts/{C1}/properties` |
| API-065 | `POST /attributes/{A1}/mapping` |
| API-066 | `POST /journeys` |
| API-067 | `PUT /journeys/{J1}/steps` |
| API-068 | `POST /connections` |

### API-069 … API-071 — `READ` against the `relationship:write` routes
**Expected for each:** 403, PROBLEM, remedy naming `relationship:write`.

| Case | Request |
|---|---|
| API-069 | `POST /relationships` |
| API-070 | `POST /relationships/{R1}/confirm` |
| API-071 | `POST /relationships/{R1}/reject` |

### API-072 — the 403 body names the scope and quotes the vocabulary
**Request:** API-057's response.
**Expected:** `remedy` contains `declaration:write` and the sentence "declare, amend, correct and retire semantic objects" from `SCOPES`.

### API-073 — the 403 body reports what the credential *does* hold
**Expected:** `context.held` = `declaration:read`.

### API-074 … API-081 — `NONE` (empty scope list) against a representative set
**Expected for each:** 403 — an empty scope list permits nothing, deliberately.

| Case | Request |
|---|---|
| API-074 | `GET /datasets` |
| API-075 | `GET /estate/maturity` |
| API-076 | `GET /concepts` |
| API-077 | `GET /relationships` |
| API-078 | `POST /datasets` |
| API-079 | `DELETE /datasets/{DS1}` |
| API-080 | `POST /relationships` |
| API-081 | `GET /critical-data-elements` |

### API-082 — `NONE` reports an empty held list legibly
**Expected:** `context.held` = `(none)` rather than an empty string.

### API-083 — `NONE` against a route with no scope requirement
**Request:** `GET /api/v1/health` with `NONE`.
**Expected:** 200 — meta routes take no caller at all.

### API-084 — `RELREAD` against `GET /relationships`
**Expected:** 200.

### API-085 — `RELREAD` against `GET /datasets`
**Expected:** 403, remedy naming `declaration:read`.

### API-086 — `RELREAD` against `POST /relationships`
**Expected:** 403, remedy naming `relationship:write`.

### API-087 — the wildcard key satisfies every scope
**Request:** `WILD` against one route of each of the four scopes.
**Expected:** 200/201 for all four; `permits()` short-circuits on `*`.

### API-088 — authorisation is decided before the body is parsed
**Request:** `POST /api/v1/datasets` with `READ` and a syntactically invalid body (`{`).
**Expected:** 403, not 422. A read-only caller must not be able to probe the schema.

---

## D. Happy paths — every write operation

Executed in dependency order; the identifiers they mint (`DS1`, `A1`, `C1`, `P1`, `J1`, `CN1`,
`B1`, `DS2`, `R1`) are reused by the groups above and below. All with `WILD`.

### API-089 — `POST /datasets` minimal body
**Request:** `{"name":"QA Trades"}`
**Expected:** 201, `DatasetOut` with `id`, `slug`, `criticality` 4, `shape` `unbound`, `is_bound` false, `meta.version` 1, `meta.is_current` true, `meta.authored_by` = alice's id.

### API-090 — `POST /datasets` full body
**Request:** name, description, purpose, criticality 2, shape `table`, grain, rhythm, temporality, authoritativeness, sensitivity, tags, `approved_by`, `reason`.
**Expected:** 201 and every field echoed. Creates `DS2`.

### API-091 — `GET /datasets` lists both
**Expected:** 200, `items` contains `DS1` and `DS2`, `page.total` ≥ 2, `page.limit` 50, `page.offset` 0.

### API-092 — `GET /datasets/{DS1}`
**Expected:** 200, the current version, `meta.version` 1.

### API-093 — `POST /datasets/{DS1}/attributes`
**Request:** `{"name":"trade_id","definition":"…","is_cde":true,"optionality":"mandatory"}`
**Expected:** 201, `AttributeOut`, `is_cde` true, `dataset_id` = `DS1`. Creates `A1`.

### API-094 — `GET /datasets/{DS1}/attributes`
**Expected:** 200, a list containing `A1`.

### API-095 — `GET /critical-data-elements`
**Expected:** 200, contains `A1` (declared `is_cde`).

### API-096 — `POST /datasets/{DS1}/amend`
**Request:** `{"reason":"the desk moved to T+1","changes":{"criticality":1}}`
**Expected:** 200, `meta.version` 2, `criticality` 1, `meta.change_reason` echoed.

### API-097 — `POST /datasets/{DS1}/correct`
**Request:** `{"reason":"we mis-stated the sensitivity","changes":{"sensitivity":"confidential"}}`
**Expected:** 200, a new belief version; `valid_from` unchanged from the amended version.

### API-098 — `GET /datasets/{DS1}/history`
**Expected:** 200, ≥3 versions, oldest first, each with a distinct `meta.version` or `recorded_at`.

### API-099 — `POST /concepts`
**Request:** `{"name":"Instrument","description":"A tradable instrument."}`
**Expected:** 201. Creates `C1`.

### API-100 — `GET /concepts`
**Expected:** 200, contains `C1`.

### API-101 — `POST /concepts/{C1}/properties`
**Request:** `{"name":"ISIN","definition":"ISO 6166 identifier","is_identifier":true}`
**Expected:** 201. Creates `P1`.

### API-102 — `GET /concepts/{C1}/properties`
**Expected:** 200, contains `P1` with `mapped_attribute_count` 0.

### API-103 — `POST /attributes/{A1}/mapping`
**Request:** `{"property_id":"<P1>"}`
**Expected:** 200, `AttributeOut` with `concept_property_id` = `P1`.

### API-104 — the mapping is reflected in the property's mapped count
**Request:** `GET /concepts/{C1}/properties`
**Expected:** 200, `mapped_attribute_count` = 1.

### API-105 — `POST /journeys`
**Request:** name, description, criticality, two steps (one `dataset` naming `DS1`, one `black_box`).
**Expected:** 201, `step_count` 2. Creates `J1`.

### API-106 — `GET /journeys`
**Expected:** 200, contains `J1`.

### API-107 — `GET /journeys/{J1}`
**Expected:** 200, `J1` with its steps.

### API-108 — `GET /journeys?dataset_id={DS1}`
**Expected:** 200, contains `J1` (blast radius of `DS1`).

### API-109 — `PUT /journeys/{J1}/steps`
**Request:** `{"reason":"reordered after the migration","steps":[…three steps…]}`
**Expected:** 200, `step_count` 3, a new `meta.version`.

### API-110 — `POST /connections`
**Request:** `{"name":"QA Warehouse","source_type":"postgres","config":{"host":"db.internal"},"credential_ref":"vault://qa/warehouse"}`
**Expected:** 201. Creates `CN1`. No secret is stored or echoed.

### API-111 — `GET /connections`
**Expected:** 200, contains `CN1` with a `health_state`.

### API-112 — `GET /connections?unhealthy_only=true`
**Expected:** 200, a list (possibly empty). Not a 5xx.

### API-113 — `POST /datasets/{DS1}/bindings` (dataset binding)
**Request:** `{"connection_id":"<CN1>","physical_ref":{"schema":"public","object":"trades"},"shape":"table"}`
**Expected:** 201, `target_kind` `dataset`. Creates `B1`.

### API-114 — `POST /datasets/{DS1}/bindings` (attribute binding)
**Request:** the same plus `"attribute_id":"<A1>"`.
**Expected:** 201, `target_kind` `attribute`.

### API-115 — `GET /datasets/{DS1}/bindings`
**Expected:** 200, contains both bindings.

### API-116 — binding makes the dataset bound
**Request:** `GET /datasets/{DS1}`
**Expected:** 200 and `is_bound` true.

### API-117 — `GET /bindings/drifted`
**Expected:** 200, an empty list (nothing has drifted).

### API-118 — `POST /relationships`
**Request:** `{"kind":"reconciles_to","from_dataset_id":"<DS1>","to_dataset_id":"<DS2>","match_keys":[{"left":"trade_id"}],"compare":["notional"],"tolerance":{"absolute":0.01}}`
**Expected:** 201, `RelationshipOut` with `generates` naming the control families. Creates `R1`.

### API-119 — `GET /relationships`
**Request:** with `WILD`.
**Expected:** 200, contains `R1`.

### API-120 — `GET /relationships?dataset_id={DS1}`
**Expected:** 200, contains `R1`.

### API-121 — `GET /relationships?kind=reconciles_to`
**Expected:** 200, contains `R1`.

### API-122 — `POST /relationships/{R1}/confirm`
**Request:** `{"reason":"the desk confirmed the mapping"}`
**Expected:** 200, `status` = confirmed.

### API-123 — `GET /relationships?confirmed_only=true`
**Expected:** 200, contains `R1`.

### API-124 — `POST /relationships/{R2}/reject`
**Precondition:** declare a second relationship `R2`.
**Expected:** 200, `status` = rejected, the reason recorded (not deleted — it is a training signal).

### API-125 — `GET /estate/maturity`
**Expected:** 200, `score`, `percent`, `stage`, `completion`, `components`, `next_actions` — decomposed, not a bare number.

### API-126 — `GET /estate/maturity?scope=domain&domain_id=…`
**Expected:** 200 or a 4xx that explains itself. Not a 5xx.

### API-127 — `GET /estate/conflicts`
**Expected:** 200, a list. Empty is fine at this point.

### API-128 — a real semantic conflict is reported
**Precondition:** map a second attribute (different `unit`) to `P1`.
**Expected:** `GET /estate/conflicts` returns ≥1 conflict naming `P1`, with `severity` and a `message`.

### API-129 — `GET /estate/coverage-gaps`
**Expected:** 200, an object of lists (unreachable / unowned / unshaped).

### API-130 — `DELETE /datasets/{DS3}` retires rather than deletes
**Precondition:** declare `DS3`.
**Expected:** 204 with an empty body; then `GET /datasets/{DS3}/history` still returns its versions.

### API-131 — a retired dataset disappears from the current list
**Expected:** `GET /datasets` no longer contains `DS3`.

---

## E. Tenant isolation

`RIVAL` is a fully valid key — of rival-bank. Every case targets an acme-bank id. **Expected: 404
(never 403, never 200), and the object unchanged afterwards.**

### API-132 — `GET /datasets` as `RIVAL`
**Expected:** 200 with an empty (or rival-only) list — acme's datasets must not appear.

### API-133 — `GET /datasets/{DS1}` as `RIVAL`
**Expected:** 404, PROBLEM.

### API-134 — `GET /datasets/{DS1}/history` as `RIVAL`
**Expected:** 200 with an **empty** list, or 404. Acme's versions must not be returned.

### API-135 — `GET /datasets/{DS1}/attributes` as `RIVAL`
**Expected:** 404 or an empty list. Acme's attribute `A1` must not be returned.

### API-136 — `GET /datasets/{DS1}/bindings` as `RIVAL`
**Expected:** 404 or an empty list. Acme's binding must not be returned.

### API-137 — `GET /concepts/{C1}/properties` as `RIVAL`
**Expected:** 404 or an empty list. Acme's property `P1` must not be returned.

### API-138 — `GET /journeys/{J1}` as `RIVAL`
**Expected:** 404, PROBLEM.

### API-139 — `GET /concepts` as `RIVAL`
**Expected:** 200, without `C1`.

### API-140 — `GET /journeys` as `RIVAL`
**Expected:** 200, without `J1`.

### API-141 — `GET /connections` as `RIVAL`
**Expected:** 200, without `CN1`.

### API-142 — `GET /critical-data-elements` as `RIVAL`
**Expected:** 200, without `A1`.

### API-143 — `GET /relationships` as `RIVAL`
**Expected:** 200, without `R1`.

### API-144 — `GET /relationships?dataset_id={DS1}` as `RIVAL`
**Expected:** 200, without `R1`.

### API-145 — `POST /datasets/{DS1}/amend` as `RIVAL`
**Expected:** 404. Then `GET /datasets/{DS1}` as `WILD` shows the version **unchanged**.

### API-146 — `POST /datasets/{DS1}/correct` as `RIVAL`
**Expected:** 404, and `DS1` unchanged.

### API-147 — `DELETE /datasets/{DS1}` as `RIVAL`
**Expected:** 404 (explicitly not a 204), and `DS1` still current afterwards.

### API-148 — `POST /datasets/{DS1}/attributes` as `RIVAL`
**Expected:** 404, and `DS1` still has exactly its acme attributes.

### API-149 — `POST /datasets/{DS1}/bindings` as `RIVAL`
**Expected:** 404, and no new binding on `DS1`.

### API-150 — `POST /concepts/{C1}/properties` as `RIVAL`
**Expected:** 404, and `C1` still has exactly `P1`.

### API-151 — `POST /attributes/{A1}/mapping` as `RIVAL`
**Precondition:** rival declares its own concept property `P2`.
**Expected:** 404, and `A1`'s mapping unchanged (still `P1`).

### API-152 — `PUT /journeys/{J1}/steps` as `RIVAL`
**Expected:** 404, and `J1`'s steps unchanged.

### API-153 — `POST /relationships` across tenants as `RIVAL`
**Request:** `from_dataset_id` = `DS1` (acme), `to_dataset_id` = rival's own dataset.
**Expected:** 404 or 422 — a relationship must not be declarable onto another estate's dataset.

### API-154 — `POST /relationships/{R1}/confirm` as `RIVAL`
**Expected:** 404, and `R1`'s status unchanged.

### API-155 — `POST /relationships/{R1}/reject` as `RIVAL`
**Expected:** 404, and `R1`'s status unchanged.

### API-156 — `GET /estate/maturity` as `RIVAL`
**Expected:** 200, computed over rival's (empty) estate, not acme's.

### API-157 — `GET /estate/coverage-gaps` as `RIVAL`
**Expected:** 200, naming no acme object.

### API-158 — a header cannot choose the tenant
**Request:** `GET /datasets` with `RIVAL` plus `X-Prama-Tenant: <acme tenant id>`.
**Expected:** 200 and rival's view only — the header is ignored entirely.

---

## F. Validation and the error contract

Unless stated, the target is `POST /api/v1/datasets` with `WILD`.

### API-159 — completely empty body
**Request:** `POST /datasets` with `Content-Type: application/json` and a zero-byte body.
**Expected:** 422, PROBLEM.

### API-160 — `{}` (required field missing)
**Expected:** 422, PROBLEM, naming `name`.

### API-161 — `null` where a value is required
**Request:** `{"name": null}`
**Expected:** 422, PROBLEM.

### API-162 — wrong type: string where a number goes
**Request:** `{"name":"x","criticality":"very high"}`
**Expected:** 422, PROBLEM.

### API-163 — number out of the declared range
**Request:** `{"name":"x","criticality":9}`
**Expected:** 422, PROBLEM (`ge=1, le=4`).

### API-164 — number below the declared range
**Request:** `{"name":"x","criticality":0}`
**Expected:** 422, PROBLEM.

### API-165 — a field that does not exist
**Request:** `{"name":"x","nonexistent_field":"boo"}`
**Expected:** 422 — `PramaModel` sets `extra="forbid"` precisely so a typo is not silently dropped.

### API-166 — empty string where `min_length=1`
**Request:** `{"name":""}`
**Expected:** 422, PROBLEM.

### API-167 — a very long string (name, 10 000 chars)
**Expected:** 422 (`max_length=255`), PROBLEM. Not a 5xx and not a truncating 201.

### API-168 — a very long string in an unbounded field (`description`, 100 000 chars)
**Expected:** 201 (the column is `TEXT`), or a 4xx that says so. Not a 5xx.

### API-169 — unicode in a name
**Request:** `{"name":"取引 — Számla — ✅ — 🏦"}`
**Expected:** 201, the name echoed byte-for-byte, and a usable `slug`.

### API-170 — an array where an object goes
**Request:** `POST /datasets` with body `[]`.
**Expected:** 422, PROBLEM.

### API-171 — a bare string where an object goes
**Request:** body `"hello"`.
**Expected:** 422, PROBLEM.

### API-172 — malformed JSON
**Request:** body `{"name": `.
**Expected:** 422 (or 400), PROBLEM. Not a 5xx.

### API-173 — deeply nested JSON (500 levels) in a free-form field
**Request:** `{"name":"nest","grain":{"attributes":["a"],"statement":"…"},"tags":[]}` with a 500-deep structure in `DatasetAmendIn.changes` instead.
**Expected:** a 4xx, or a 200 that stores it. Not a 5xx and not a recursion-limit crash.

### API-174 — an object where an array goes
**Request:** `{"name":"x","tags":{"a":"b"}}`
**Expected:** 422, PROBLEM.

### API-175 — an array of the wrong element type
**Request:** `{"name":"x","tags":[1,2,3]}`
**Expected:** 422, or 201 with coerced strings. Recorded either way.

### API-176 — grain with an empty attribute list
**Request:** `{"name":"x","grain":{"attributes":[]}}`
**Expected:** 422 (`min_length=1`), PROBLEM.

### API-177 — a bad enum value
**Request:** `POST /relationships` with `{"kind":"not_a_kind", …}`
**Expected:** 422, PROBLEM, listing the permitted kinds.

### API-178 — wrong `Content-Type`
**Request:** `POST /datasets` with `Content-Type: text/plain` and a valid JSON body.
**Expected:** 422 or 415, PROBLEM. Not a 5xx.

### API-179 — amend with an empty reason
**Request:** `POST /datasets/{DS1}/amend` `{"reason":"","changes":{}}`
**Expected:** 422 (`min_length=1`) — the model demands a reason.

### API-180 — amend with a `changes` key that is not a field
**Request:** `{"reason":"why","changes":{"not_a_column":"x"}}`
**Expected:** a 4xx naming the unknown field. **Not** a 500, and not a silent 200.

### API-181 — correct with no changes
**Request:** `{"reason":"nothing actually changed","changes":{}}`
**Expected:** a 200 or a 4xx. Not a 5xx.

### API-182 — journey steps with `min_length=1` reason
**Request:** `PUT /journeys/{J1}/steps` `{"reason":"","steps":[]}`
**Expected:** 422, PROBLEM.

### API-183 — a non-existent id on a read
**Request:** `GET /datasets/01AAAAAAAAAAAAAAAAAAAAAAAA`
**Expected:** 404, PROBLEM, `remedy` naming the identifier check.

### API-184 — a syntactically invalid id
**Request:** `GET /datasets/not-a-ulid`
**Expected:** 404 (or 422), PROBLEM. Not a 5xx.

### API-185 — an id containing a path separator
**Request:** `GET /datasets/..%2f..%2fetc%2fpasswd`
**Expected:** 404, PROBLEM. No traversal.

### API-186 — a SQL-shaped id
**Request:** `GET /datasets/' OR '1'='1`
**Expected:** 404, PROBLEM, and the estate unchanged.

### API-187 — a very long id (4 KB)
**Expected:** 404 or 414. Not a 5xx.

### API-188 — mapping to a non-existent property
**Request:** `POST /attributes/{A1}/mapping` `{"property_id":"01BBBBBBBBBBBBBBBBBBBBBBBB"}`
**Expected:** 404, PROBLEM, remedy "Declare the property before mapping attributes to it."

### API-189 — binding through a non-existent connection
**Request:** `POST /datasets/{DS1}/bindings` with a bogus `connection_id`.
**Expected:** 404, PROBLEM, remedy naming connection configuration.

### API-190 — every error observed in this run carries the six PROBLEM fields
**Expected:** a sweep over every non-2xx response captured: all are `application/problem+json` and all carry `type`, `title`, `status`, `code`, `remedy`, `correlation_id`. Any that does not is a finding.

### API-191 — no response in this run is a 5xx
**Expected:** NO500 holds across the whole suite.

---

## G. Pagination

### API-192 — default page
**Request:** `GET /datasets`
**Expected:** 200, `page.limit` 50, `page.offset` 0, `page.total` = the true count.

### API-193 — `limit=1`
**Expected:** 200, exactly 1 item, `page.total` unchanged.

### API-194 — `offset=1`
**Expected:** 200, a different first item from API-193.

### API-195 — `limit=0`
**Expected:** 422 (`ge=1`), PROBLEM.

### API-196 — `limit=-1`
**Expected:** 422, PROBLEM.

### API-197 — `limit=100000`
**Expected:** 422 (`le=500`), PROBLEM — a caller cannot ask for an unbounded scan.

### API-198 — `offset=-1`
**Expected:** 422, PROBLEM.

### API-199 — a huge offset past the end
**Request:** `offset=100000`
**Expected:** 200, empty `items`, `page.total` still the true count.

### API-200 — a non-numeric limit
**Request:** `limit=abc`
**Expected:** 422, PROBLEM.

### API-201 — `page.total` ignores the filters
**Request:** `GET /datasets?unbound=true`
**Expected:** 200. Whether `page.total` reflects the filter or the whole estate is recorded — a `total` that disagrees with a filtered `items` is a reporting defect.

### API-202 — `GET /datasets?criticality=1`
**Expected:** 200, only criticality-1 datasets.

### API-203 — `criticality=9`
**Expected:** 422 (`ge=1, le=4`), PROBLEM.

### API-204 — filter precedence
**Request:** `GET /datasets?unbound=true&criticality=1`
**Expected:** the route's `if/elif` means `unbound` wins. Recorded as observed behaviour, since silently ignoring a supplied filter is a usability finding.

### API-205 — `GET /relationships` has no pagination
**Expected:** 200 with an internal cap of 500 and no `page` object. Recorded: the list endpoints other than `/datasets` are uncapped from the caller's point of view.

---

## H. Bitemporal queries on `/datasets/{id}`

### API-206 — `valid_at` = now
**Expected:** 200, the current version.

### API-207 — `valid_at` before the first declaration
**Request:** `valid_at=2000-01-01T00:00:00Z`
**Expected:** 404, PROBLEM, remedy "widen the valid_at / known_at window".

### API-208 — `valid_at` in the future
**Request:** `valid_at=2099-01-01T00:00:00Z`
**Expected:** 200 with the current version (its validity is open-ended), or 404. Recorded either way.

### API-209 — `known_at` alone
**Request:** `known_at=2000-01-01T00:00:00Z`
**Expected:** the route's `elif` means `known_at` **alone is ignored** and the current version is returned. That is a silent wrong answer to a bitemporal question; the case records it.

### API-210 — `valid_at` **and** `known_at`, both now
**Expected:** 200, the current version.

### API-211 — `valid_at` now, `known_at` before the correction
**Precondition:** `DS1` was amended (API-096) then corrected (API-097).
**Expected:** 200, the **pre-correction** belief. This is the case an evidence replay depends on.

### API-212 — `valid_at` now, `known_at` before anything was recorded
**Expected:** 404, PROBLEM.

### API-213 — malformed `valid_at`
**Request:** `valid_at=yesterday`
**Expected:** 422, PROBLEM.

### API-214 — a date with no time
**Request:** `valid_at=2026-01-01`
**Expected:** 200 or 422. Not a 5xx.

### API-215 — a timezone-naive timestamp
**Request:** `valid_at=2026-01-01T00:00:00`
**Expected:** 200 or 422, and if accepted, consistent with the UTC interpretation. Not a 5xx.

### API-216 — a nonsense timezone offset
**Request:** `valid_at=2026-01-01T00:00:00+99:00`
**Expected:** 422, PROBLEM. Not a 5xx.

### API-217 — an empty `valid_at`
**Request:** `valid_at=`
**Expected:** 422 or 200 (treated as absent). Not a 5xx.

---

## I. Idempotence and conflicts

### API-218 — declaring the same dataset name twice
**Request:** `POST /datasets` `{"name":"QA Trades"}` twice.
**Expected:** the second is 409, PROBLEM, `code` in the `*.CONFLICT` family, with a remedy that names the action to take.

### API-219 — the 409's remedy is usable
**Expected:** following the remedy literally (amend the existing declaration) succeeds.

### API-220 — declaring the same attribute name twice on one dataset
**Expected:** 409, PROBLEM, remedy "Amend the existing attribute, or choose a different name."

### API-221 — the same attribute name on a *different* dataset
**Expected:** 201 — the uniqueness is per dataset.

### API-222 — declaring the same concept twice
**Expected:** 409 or 201. Recorded.

### API-223 — the same concept property twice
**Expected:** 409 or 201. Recorded.

### API-224 — the same connection name twice
**Expected:** 409 or 201. Recorded.

### API-225 — retiring an already-retired dataset
**Request:** `DELETE /datasets/{DS3}` twice.
**Expected:** the second is 404 with the "no current version to retire" message — explicitly **not** a second 204.

### API-226 — confirming an already-confirmed relationship
**Expected:** 200 or 409. Not a 5xx.

### API-227 — rejecting an already-confirmed relationship
**Expected:** a defined outcome, not a 5xx.

### API-228 — amending a retired dataset
**Expected:** 404, PROBLEM.

### API-229 — the same name in *two different tenants*
**Precondition:** rival declares a dataset also called "QA Trades".
**Expected:** 201 — uniqueness is per tenant, not global. A 409 here would leak the other estate's contents.

---

## J. Following the remedies

Each case takes the `remedy` string from an earlier response, performs literally what it names, and
records whether it works.

### API-230 — the 401 remedy
**Source:** API-019. `"Send Authorization: Bearer pk_live_…, or the X-Prama-API-Key header."`
**Action:** re-send with `X-Prama-API-Key`.
**Expected:** 200.

### API-231 — the 401 remedy names a CLI command
**Source:** API-019 / API-020 mention `prama apikey create` and `prama apikey list`.
**Action:** run `prama --config … apikey list` and `prama apikey create`.
**Expected:** the commands exist and do what the remedy says. If `apikey` is not a command, the remedy sends the reader to something that does not exist — a finding.

### API-232 — the 403 remedy
**Source:** API-057. `"Issue a key with 'declaration:write' …"`
**Action:** mint exactly such a key and retry.
**Expected:** 201.

### API-233 — the 404 remedy on a dataset
**Source:** API-183. `"Check the identifier, or list the declared datasets."`
**Action:** `GET /datasets`, take a real id, retry.
**Expected:** 200.

### API-234 — the 404 remedy on a bitemporal miss
**Source:** API-207. `"Check the identifier, or widen the valid_at / known_at window."`
**Action:** widen to a `valid_at` after the declaration.
**Expected:** 200.

### API-235 — the 409 remedy on a duplicate attribute
**Source:** API-220. `"Amend the existing attribute, or choose a different name."`
**Action:** choose a different name.
**Expected:** 201.

### API-236 — the 404 remedy on mapping
**Source:** API-188. `"Declare the property before mapping attributes to it."`
**Action:** declare a property, retry the mapping.
**Expected:** 200.

### API-237 — the 404 remedy on binding
**Source:** API-189. `"Configure the connection before binding through it."`
**Action:** configure a connection, retry.
**Expected:** 201.

### API-238 — the 422 remedy on a validation failure
**Source:** API-160.
**Expected:** the body carries a `remedy` that tells the caller which field to fix. A FastAPI-default
`{"detail": […]}` body carries no `remedy` at all, which would breach PROBLEM.

---

## K. The credential model's unreachable paths

### API-239 — a key with no principal
**Action:** mint an API key with `principal_id = NULL` and call a route that records an author.
**Expected:** 422 with the message `CallerIdentity.require_principal()` raises. If the key cannot be
minted at all, the case is BLOCKED and the observation recorded.

### API-240 — the `X-Prama-Principal` header
**Request:** `GET /api/v1/datasets` with `X-Prama-Principal: <another principal's id>`.
**Expected:** the header is ignored — identity comes from the key's record and nothing else. A
response that differs because of the header would be a serious defect.

---

## Preconditions recorded as their own cases

Three cases below were written as single requests but executed as two, because the first attempt hit
a deliberate product control the case had not anticipated. Both attempts are logged.

### API-096a — a Tier-1 amendment with no approver
**Request:** `POST /datasets/{DS1}/amend` `{"reason":"…","changes":{"criticality":1}}`
**Expected (revised):** 422 — a Tier-1 declaration requires maker-checker approval.

### API-105a — a Tier-2 journey with no approver
**Request:** `POST /journeys` with `criticality: 2` and no `approved_by`.
**Expected (revised):** 422 — held as proposed until an approver signs it off.

### API-118a — an invalid relationship kind
**Request:** `POST /relationships` with `{"kind":"reconciles_to", …}`
**Expected (revised):** 422 listing the thirteen permitted kinds. Whether that 422 is problem+json
is the point of the case.

### API-CID-SWEEP — `X-Correlation-Id` across every response in the run
**Expected:** the header is present on all of them, success and failure alike.
