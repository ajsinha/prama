<!-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE. -->

**Status (2026-09-27):** built. This includes templates, evaluation suites and the activation gate, stored payloads and the ledger verifier (`prama llm verify`). Evaluation graders are the deterministic set in `llm/evaluation.py`; the model-based rubric grader is not built, and the gate would ignore it anyway.

> Design note behind [23 — Intelligence and lineage roadmap](../23-intelligence-and-lineage-roadmap.md). Written 2026-09-27. Where this note and doc 23 disagree, doc 23's reconciliation wins.

# Prama LLM abstraction — design

Status: proposal. Builds on `prama.llm.spi` and does not replace it. Everything below keeps the four
invariants the current code already gets right: residency and sensitivity are enforced in
`ModelProvider.ask()` and nowhere else; an unreachable model is a `Response(incomplete=…)`, never an
exception; the request fingerprint is the provenance key; a model output is never a verdict.

## 0. What exists, and the defects this design fixes

| Existing | Keep | Defect to fix |
|---|---|---|
| `Request`/`Response`/`ModelProvider.ask→complete`, `Hosting.permits`, `permit_residency` | All of it | Single-turn only; no tools, streaming, embeddings, usage/cost, capabilities |
| `OpenAiCompatibleProvider` | Wire format | Sets `grammar_enforced=True` whenever it *sends* `guided_grammar`, although Ollama/LM Studio/OpenAI ignore that field — the record claims a constraint that was never applied |
| same | | Defaults `hosting=SELF_HOSTED`; pointed at `api.openai.com` it passes RESTRICTED data with no residency gate |
| `ProviderRegistry` | Instances per deployment | Built in code; nothing is configured, persisted, routed, budgeted or audited |
| `EGRESS_POINTS["model-inference"]` → `prama.llm.providers` | The gate | Each new provider module would import `urllib` and need its own egress row; the registry forbids duplicate modules |
| `assistant.safety.redact` / `_SECRET_SHAPES` | Patterns | Applied to *answers* only, never to *prompts* (FR-CHT-013) |

## 1. SPI changes (`src/prama/llm/spi.py`) — additive, exactly

New frozen dataclasses: `Message(role, content, tool_call_id="", name="")`,
`ToolSpec(name, description, parameters: JsonSchema)`, `ToolCall(id, name, arguments: dict)`,
`ResponseSchema(name, schema: dict, strict=True)`, `Usage(input, output, cached_input=0, estimated=False)`,
`Delta(text="", tool_call: ToolCall|None=None, usage: Usage|None=None, finish="")`,
`EmbedRequest(texts, sensitivity, context)`, `Embeddings(vectors, model, provider, usage)`,
`TokenCount(tokens, estimated)`, `ModelCapabilities`.

`Request` gains, all defaulted: `messages: tuple[Message,...] = ()` (when empty, `system`+`prompt` is the
turn, exactly as today), `tools`, `tool_choice: str = "auto"`, `response_schema`, `stop`, `top_p`,
`purpose: str = ""`, `template: TemplateRef|None` (id, version, content hash).
**`fingerprint` hashes a new field only when it is non-default**, so every legacy single-turn request
keeps its current fingerprint; a test pins one literal hex digest.

`Response` gains: `tool_calls`, `structured` (parsed JSON), `schema_valid: bool|None`, `finish_reason`,
`usage: Usage`, `cost_micros: int = 0`, `model_version` (e.g. OpenAI `system_fingerprint`),
`provider_request_id`, `call_id`. `input_tokens`/`output_tokens` stay as properties over `usage`.

`ModelCapabilities` (frozen): `chat, stream, tools, parallel_tools, embeddings, seed_honoured,
json_schema_native, grammar: frozenset{"gbnf","regex","json_schema"}, token_count_endpoint,
max_context, max_output`. `supports_grammar` becomes a derived property (`bool(caps.grammar)`).

`ModelProvider` gains three transports and three gated doors, mirroring `complete`/`ask`:

| Transport (no checks, overridable) | Default | Gated door (final, runs `permit` + `permit_residency`) |
|---|---|---|
| `complete(request)` | abstract (unchanged) | `ask(request)` (unchanged) |
| `complete_stream(request) -> Iterator[Delta]` | one `Delta` from `complete` | `ask_stream(request)` |
| `complete_embed(req) -> Embeddings` | `Unsupported` response | `ask_embed(req)` |
| `count_tokens(request) -> TokenCount` | `tokens.estimate()` (chars/3.5, `estimated=True`) | — (no egress unless the endpoint is used; then via `ask`-style gate) |

**Clearance.** `ask*` mints a private `_Clearance(egress="model-inference", fingerprint)` token after
the gate passes and passes it to the transport layer; `transport.HttpTransport.send()` refuses without
a clearance matching the request fingerprint. A provider written by a third party that bypasses `ask`
cannot reach the socket through Prama's transport.

## 2. Module layout

```
src/prama/llm/
  spi.py            extended (§1)
  kinds.py          ProviderKind(Plugin) — a factory: manifest, config fields, build(spec, secrets, gate) -> ModelProvider
  transport.py      THE ONLY network module in prama.llm: urllib POST/stream, SSE parser, AWS event-stream
                    parser (CRC32 via zlib), timeouts, Clearance check, Gate.require()  ← egress point module
  wire/openai.py    OpenAI chat/embeddings mapping + Dialect table (§3)
  wire/anthropic.py Messages API: tools, forced-tool structured output, SSE events, /v1/messages/count_tokens
  wire/bedrock.py   Converse / ConverseStream mapping
  wire/sigv4.py     stdlib SigV4 (hmac/hashlib), verified against AWS's published test vectors
  wire/vertex.py    phase 4; RS256 service-account JWT needs the `sso` extra (cryptography)
  providers/        was providers.py; __init__ re-exports NullProvider, ScriptedProvider,
                    OpenAiCompatibleProvider, AnthropicProvider, PQL_CONTROL_GRAMMAR (imports unchanged)
    bedrock.py, vertex.py
  jsonschema.py     stdlib validator for a declared subset (type, properties, required, enum, items,
                    additionalProperties, min*/max*, pattern); unknown keywords are REFUSED at save time
  tokens.py         estimators; TokenEstimator plugins
  redact.py         Redactor ABC; SecretShapeRedactor (moves _SECRET_SHAPES here; safety imports it),
                    PatternRedactor (email, phone, IBAN mod-97, PAN Luhn), ClassifiedValueRedactor
  templates.py      PromptTemplate/TemplateRef; render() fences untrusted variables via assistant.safety.fence
  routing.py        Router: profile version → ordered, policy-filtered candidates
  resilience.py     RetryPolicy (jittered exponential), CircuitBreaker per provider, deadlines
  budget.py         Pricing (integer micro-units), BudgetPolicy, Reservation
  cache.py          ResponseCache ABC; MemoryCache (bounded LRU); DatabaseCache via store port
  ledger.py         CallRecord, hash chain, CallLedger port
  store.py          ports (ABCs): ProviderStore, ProfileStore, TemplateStore, BudgetStore, PayloadStore
  gateway.py        LlmGateway (the pipeline, §6) + ProfileProvider(ModelProvider) adapter
  replay.py         exact | rerun | challenger
  eval/harness.py, eval/graders.py, eval/suites/*.yaml
src/prama/secrets/sealed.py         SealedSecretProvider (scheme `sealed`) + SealedSecretWriter (§5)
src/prama/db/models/llm.py, src/prama/db/dao/llm.py   ORM + DAOs implementing the store ports
src/prama/api/routes/llm.py, llm_admin.py              §9
src/prama/web/routes/llm_routes.py, templates/llm/*    §10
src/prama/cli/llm.py                                    prama llm …
```

`prama.llm` never imports `prama.db`; DAOs implement its ports and the API/web builders wire them
(architecture test). `EGRESS_POINTS["model-inference"].module` changes from `prama.llm.providers` to
`(planned) prama.llm.transport` — the only edit to `security/egress.py`.

**Entry-point groups** (added to `plugins.entry_point_groups`): `(planned) prama.llm_providers` (ProviderKind),
`(planned) prama.llm_redactors`, `(planned) prama.llm_tokenizers` (e.g. an optional tiktoken estimator), `(planned) prama.llm_graders`,
`(planned) prama.llm_caches`, and `(planned) prama.secret_providers` (so `sealed` and third-party vaults are discovered).

## 3. Provider kinds

| Kind key | Covers | Default hosting | Notes |
|---|---|---|---|
| `openai_compatible` + `dialect` | vLLM, Ollama, llama.cpp server, LM Studio, TGI, HF router/Endpoints, gateways | declared, **required** | Dialect table below |
| `openai` | api.openai.com | hosted | `response_format: json_schema strict`, tools, `seed`, `system_fingerprint` |
| `azure_openai` | Azure OpenAI | tenant | `/openai/deployments/{d}/chat/completions?api-version=` or `/openai/v1`; `api-key` header or Entra token ref |
| `anthropic` | Anthropic API | hosted | pinned `anthropic-version`; structured output by forced tool; SSE |
| `bedrock` | Converse/ConverseStream | tenant | SigV4 stdlib with access key/secret/session-token secret refs; `aws` extra (`botocore`) only for the credential chain (IRSA/IMDS/SSO) |
| `vertex` (optional) | Gemini/Claude on Vertex | tenant | `sso` extra for JWT; or Vertex's OpenAI-compatible endpoint via `openai_compatible` |
| `none`, `scripted` | as today | self_hosted | |

Dialect table (data, not branches; one test per row with a golden request body):

| dialect | grammar field → `grammar` capability | JSON schema | tokens endpoint | embeddings |
|---|---|---|---|---|
| `vllm` | `guided_grammar`, `guided_regex` → gbnf, regex | `guided_json` | `/tokenize` | `/v1/embeddings` |
| `llamacpp` | `grammar` → gbnf | `json_schema` | `/tokenize` | `/v1/embeddings` |
| `tgi` / `hf_endpoint` | `response_format{type:regex}` → regex | `response_format{type:json}` | — | — |
| `ollama` | none | `response_format json_schema` | — | `/v1/embeddings` |
| `lmstudio` | none | `response_format json_schema` | — | `/v1/embeddings` |
| `hf_router` | none | `response_format json_schema` (model-dependent → capability false) | — | — |
| `generic` | none | none | — | — |

`grammar_enforced` is true **only** when the dialect declares that grammar kind; otherwise the grammar
is not sent and the caller validates (fixes the §0 defect).

**Hosting honesty.** `llm_provider.hosting` has no default. The factory refuses `self_hosted` when the
kind is a vendor kind or the endpoint host matches a vendor suffix list (`api.openai.com`,
`.openai.azure.com`, `api.anthropic.com`, `router.huggingface.co`, `.endpoints.huggingface.cloud`,
`.amazonaws.com`, `.googleapis.com`). The region field is a jurisdiction ("EU"), validated against the
residency vocabulary.

## 4. Configuration keys (`core/config/defaults.py`, block `llm`)

Deployment policy only; providers/profiles/budgets are data in the DB (single authority), seeded
declaratively with `prama llm apply llm.yaml` (idempotent, prints a diff, like control import).

```yaml
llm:
  enabled: true
  offline: false            # true: build refuses any provider whose hosting != self_hosted, and any
                            # endpoint host outside loopback/RFC1918/egress.allowed_hosts
  allowed_kinds: []         # empty = all installed kinds
  egress: {allowed_hosts: []}
  timeouts: {connect: 5s, read: 60s, total: 120s, stream_idle: 30s}
  retries: {max_attempts: 3, base: 0.5s, cap: 8s, on: [429, 500, 502, 503, 504, timeout]}
  circuit: {failures: 5, cool_off: 60s}
  concurrency: {per_provider: 8}
  rate: {per_principal_rpm: 60, per_principal_tpm: 200000}
  cache: {enabled: true, backend: memory, ttl: 24h, max_entries: 10000}
  audit: {payloads: redacted, payload_retention: 30d}   # none | redacted | full
  redaction: {redactors: [secret_shapes, patterns, classified], on_restricted: refuse}
  eval: {gate_activation: true}
  credentials: {sealed: auto}   # auto = enabled only when a CMK key provider is configured
```

No secret appears here; credentials are `SecretRef`s on provider rows.

## 5. Credentials

A provider row stores `credential_ref` — `env://ANTHROPIC_API_KEY`, `file://…`, `vault://kv/llm#key`
— resolved through `SecretResolver` with `purpose="llm:<provider>"` (already audited, cached 300s,
invalidated on rotation). Bedrock takes three refs in `settings_json` names only.

Write-only UI entry needs somewhere to write. `SecretProvider` stays three read methods (the module's
stated position that Prama is not a secret manager holds); a separate `SealedSecretWriter` stores a
CMK `Envelope` (AAD = tenant + `sealed:<name>`) in `sealed_secret` and returns `sealed://<name>`,
which the read-only `SealedSecretProvider` resolves. No API ever returns the plaintext; responses carry
`SecretValue.fingerprint()` only. Without a CMK (and the `sso` extra) the UI offers references only and
says why.

## 6. The gateway pipeline (`LlmGateway.run`)

1. **Resolve** the profile's current version (pinned id+version onto the request).
2. **Render** the template version; each variable declares a sensitivity; request sensitivity = max.
3. **Redact** with the profile's redactors; counts by kind recorded, values never. `RESTRICTED`
   content with `on_restricted: refuse` stops here.
4. **Route**: candidates = profile route entries filtered by capability (tools/schema/stream needed),
   `offline`, circuit state, `Hosting.permits`, and the residency gate (`Gate.decide`, reporting only).
   Empty → `ResidencyRefused`/`ValidationError`, **audited as `refused_policy`**.
5. **Admit**: rate limiter (existing `core.concurrency.limits.RateLimiter`, per principal and API key)
   and budget reservation (§7).
6. **Cache** lookup — after policy, so a cached answer is never an oracle for a request that would now
   be refused. Key = tenant + fingerprint + provider + model + profile version; only `temperature==0`.
7. **Call** `provider.ask/ask_stream` with deadline; retry retryables on the same candidate; then fall
   back to the next candidate. Fallback never crosses to a less-local hosting class unless the profile
   sets `fallback_across_hosting: true`.
8. **Validate** output: JSON-schema (§1 subset) → at most `schema_repairs` (default 1) retry with the
   validator's message appended → otherwise `incomplete="schema: …"`, `schema_valid=False`.
   `scan_output` then `redact` on the answer.
9. **Record** a hash-chained `llm_call` row and the payload (per `audit.payloads`); release reservation.

`ProfileProvider(gateway, purpose)` is itself a `ModelProvider`, so `Assistant` and `Inducer` switch to
profiles with a one-line change in their builders and no change to their code. Streaming runs the
provider iterator in the supervisor's task group, feeding a byte-bounded `BoundedQueue` to the SSE
writer (back-pressure; client disconnect cancels and records `cancelled` with partial usage).

## 7. Budgets, pricing, cost

Money is `INTEGER` micro-units (no REAL rounding); prices are per million tokens on `llm_model` rows
with `effective_from`, and each call records the `llm_model.id` it was priced with.
`cost = ceil(in*p_in + cached*p_cached + out*p_out) / 1e6`. Self-hosted models may carry a notional
price or zero. Spend is **derived from the ledger** (sum of `cost_micros` in period) plus live
`llm_reservation` rows (estimate = counted input + `max_tokens` × output price). The check-and-reserve
runs under a `lease` on `llm-budget:<tenant>` so a fleet cannot jointly overrun. Exhaustion →
`LLM.BUDGET_EXHAUSTED` (HTTP 429, `Retry-After` = period reset), or a warning when `action=warn`.
Scopes: tenant, profile, principal, api_key; periods day, month.

## 8. Determinism, replay, offline, evaluation

**Determinism.** Profiles have a `purpose_class`: `author` (anything that becomes a proposal) is
validated at save to `temperature=0` and a set seed; `explain`/`summarise` may differ. Recorded per
call: temperature, seed, model reported, `model_version`, capability `seed_honoured`. Downstream never
relies on two calls agreeing (spi doctrine unchanged).

**Replay** (`replay.py`, CLI and API): `exact` re-serves the stored response after verifying
`response_hash` (reproduces a downstream pipeline, e.g. re-validating an induced control); `rerun`
re-asks the same provider/model and reports a diff plus whether the fingerprint matched; `challenger`
runs another profile version. Replays are new ledger rows with `served_from='replay'`/`fallback_from`.

**Offline/air-gapped.** `llm.offline: true` refuses at build time (not call time) any non-self-hosted
provider and any non-local host; vendor kinds are hidden in the UI; eval suites run against recorded
payloads (`exact`) or local models. Nothing is downloaded; model weights are the operator's.

**Evaluation harness.** Suites are versioned YAML in the repo or uploaded: cases of template variables
or messages plus *structural* expectations. Graders (plugins, `deterministic: ClassVar[bool]`):
`json_schema_valid`, `pql_parses`, `pql_validates` (the Wave 6 validator in its sandbox), `tool_called`,
`contains`/`absent`, `declines_injection` (reuses `tests/assistant` corpus), `max_latency_ms`,
`max_cost_micros`. A model-based rubric grader may exist but is `deterministic=False` and the gate
ignores it. With `eval.gate_activation`, a profile or template version cannot become current without
a passing `llm_eval_run` for that exact pair. Vocabulary note: the no-model-verdict guard forbids the
word `verdict` in any module mentioning `llm`/`completion`, so the harness says `grade`/`outcome`.

## 9. Keeping CON-007

A model authors, ranks, explains, summarises. Nothing below lets its text become a pass/fail.

1. **Import direction (new architecture test).** The verdict side — `prama.execute`, `backend`, `ir`,
   `score`, `monitor`, `calibrate`, `recon`, `contract`, `evidence` — may not import `prama.llm`,
   `assistant`, `induce` or `mcp`, **transitively** over the import graph. Counterfactual: a synthetic
   module chain `execute_fixture → x → prama.llm` is flagged.
2. **Existing `TestModelVerdicts`** keeps covering every new module; `prama.llm` must not import
   `prama.db` or `prama.execute` (new).
3. **API surface.** `/api/v1/llm/*` routes require only `llm:*` scopes; a test enumerates every route's
   dependencies and imports and fails if one reaches a control-activation, attestation-sign or
   evidence-write DAO method.
4. **Provenance.** A structured model output headed for the estate goes only through
   `ProposeControl` → Wave 6 validator → proposal queue, carrying `origin="model:<call_id>"`; a test
   asserts the call id resolves to an `llm_call` row, and that activation requires `control:approve`
   by a principal (SoD test already exists).
5. **Evaluation** gates on deterministic graders only (§8).

## 10. Database (append to both `schema/sqlite.sql` and `schema/postgres.sql`, byte-identical)

`llm_call`/`llm_payload` belong to `EvidenceBase` (own retention, append-only, chained); the rest to `Base`.

```sql
CREATE TABLE IF NOT EXISTS sealed_secret (
    id            VARCHAR(26)   NOT NULL PRIMARY KEY,
    tenant_id     VARCHAR(26)   NOT NULL REFERENCES tenant (id) ON DELETE CASCADE,
    name          VARCHAR(128)  NOT NULL,
    envelope_json TEXT          NOT NULL,
    fingerprint   VARCHAR(64)   NOT NULL,
    created_at    VARCHAR(32)   NOT NULL,
    created_by    VARCHAR(26),
    rotated_at    VARCHAR(32),
    CONSTRAINT uq_sealed_secret_name UNIQUE (tenant_id, name)
);
CREATE TABLE IF NOT EXISTS llm_provider (
    id             VARCHAR(26)   NOT NULL PRIMARY KEY,
    tenant_id      VARCHAR(26)   NOT NULL REFERENCES tenant (id) ON DELETE CASCADE,
    name           VARCHAR(64)   NOT NULL,
    kind           VARCHAR(64)   NOT NULL,
    dialect        VARCHAR(32)   NOT NULL DEFAULT '',
    hosting        VARCHAR(16)   NOT NULL,
    endpoint       VARCHAR(512)  NOT NULL DEFAULT '',
    region         VARCHAR(32)   NOT NULL DEFAULT '',
    credential_ref VARCHAR(512),
    settings_json  TEXT          NOT NULL DEFAULT '{}',
    enabled        INTEGER       NOT NULL DEFAULT 1,
    created_at     VARCHAR(32)   NOT NULL,
    created_by     VARCHAR(26),
    updated_at     VARCHAR(32)   NOT NULL,
    updated_by     VARCHAR(26),
    CONSTRAINT uq_llm_provider_name UNIQUE (tenant_id, name),
    CONSTRAINT ck_llm_provider_hosting CHECK (hosting IN ('hosted', 'tenant', 'self_hosted')),
    CONSTRAINT ck_llm_provider_enabled CHECK (enabled IN (0, 1))
);
CREATE TABLE IF NOT EXISTS llm_model (
    id                   VARCHAR(26)   NOT NULL PRIMARY KEY,
    tenant_id            VARCHAR(26)   NOT NULL REFERENCES tenant (id) ON DELETE CASCADE,
    provider_id          VARCHAR(26)   NOT NULL REFERENCES llm_provider (id) ON DELETE CASCADE,
    model                VARCHAR(128)  NOT NULL,
    capabilities_json    TEXT          NOT NULL DEFAULT '{}',
    context_window       INTEGER       NOT NULL DEFAULT 0,
    price_in_micros      INTEGER       NOT NULL DEFAULT 0,
    price_cached_micros  INTEGER       NOT NULL DEFAULT 0,
    price_out_micros     INTEGER       NOT NULL DEFAULT 0,
    currency             VARCHAR(3)    NOT NULL DEFAULT 'USD',
    effective_from       VARCHAR(32)   NOT NULL,
    created_at           VARCHAR(32)   NOT NULL,
    CONSTRAINT uq_llm_model_price UNIQUE (provider_id, model, effective_from)
);
CREATE TABLE IF NOT EXISTS llm_template (
    id              VARCHAR(26)   NOT NULL PRIMARY KEY,
    tenant_id       VARCHAR(26)   NOT NULL REFERENCES tenant (id) ON DELETE CASCADE,
    name            VARCHAR(128)  NOT NULL,
    current_version INTEGER,
    created_at      VARCHAR(32)   NOT NULL,
    CONSTRAINT uq_llm_template_name UNIQUE (tenant_id, name)
);
CREATE TABLE IF NOT EXISTS llm_template_version (
    id                   VARCHAR(26)   NOT NULL PRIMARY KEY,
    template_id          VARCHAR(26)   NOT NULL REFERENCES llm_template (id) ON DELETE CASCADE,
    version              INTEGER       NOT NULL,
    system_text          TEXT          NOT NULL DEFAULT '',
    body                 TEXT          NOT NULL,
    variables_json       TEXT          NOT NULL DEFAULT '[]',
    response_schema_json TEXT,
    content_hash         VARCHAR(64)   NOT NULL,
    status               VARCHAR(16)   NOT NULL DEFAULT 'draft',
    eval_run_id          VARCHAR(26),
    recorded_at          VARCHAR(32)   NOT NULL,
    recorded_by          VARCHAR(26),
    approved_at          VARCHAR(32),
    approved_by          VARCHAR(26),
    CONSTRAINT uq_llm_template_version UNIQUE (template_id, version),
    CONSTRAINT ck_llm_template_status CHECK (status IN ('draft', 'approved', 'retired'))
);
CREATE TABLE IF NOT EXISTS llm_profile (
    id              VARCHAR(26)   NOT NULL PRIMARY KEY,
    tenant_id       VARCHAR(26)   NOT NULL REFERENCES tenant (id) ON DELETE CASCADE,
    purpose         VARCHAR(64)   NOT NULL,
    current_version INTEGER,
    created_at      VARCHAR(32)   NOT NULL,
    CONSTRAINT uq_llm_profile_purpose UNIQUE (tenant_id, purpose)
);
CREATE TABLE IF NOT EXISTS llm_profile_version (
    id                 VARCHAR(26)   NOT NULL PRIMARY KEY,
    profile_id         VARCHAR(26)   NOT NULL REFERENCES llm_profile (id) ON DELETE CASCADE,
    version            INTEGER       NOT NULL,
    purpose_class      VARCHAR(16)   NOT NULL DEFAULT 'author',
    params_json        TEXT          NOT NULL DEFAULT '{}',
    overridable_json   TEXT          NOT NULL DEFAULT '[]',
    max_sensitivity    VARCHAR(16)   NOT NULL DEFAULT 'internal',
    redactors_json     TEXT          NOT NULL DEFAULT '[]',
    template_id        VARCHAR(26)   REFERENCES llm_template (id),
    template_version   INTEGER,
    timeout_ms         INTEGER       NOT NULL DEFAULT 60000,
    max_attempts       INTEGER       NOT NULL DEFAULT 3,
    schema_repairs     INTEGER       NOT NULL DEFAULT 1,
    cache_ttl_s        INTEGER       NOT NULL DEFAULT 86400,
    fallback_across_hosting INTEGER  NOT NULL DEFAULT 0,
    eval_run_id        VARCHAR(26),
    note               TEXT          NOT NULL DEFAULT '',
    recorded_at        VARCHAR(32)   NOT NULL,
    recorded_by        VARCHAR(26),
    CONSTRAINT uq_llm_profile_version UNIQUE (profile_id, version),
    CONSTRAINT ck_llm_profile_class CHECK (purpose_class IN ('author', 'explain', 'summarise', 'embed')),
    CONSTRAINT ck_llm_profile_fallback CHECK (fallback_across_hosting IN (0, 1))
);
CREATE TABLE IF NOT EXISTS llm_profile_route (
    profile_version_id VARCHAR(26)  NOT NULL REFERENCES llm_profile_version (id) ON DELETE CASCADE,
    position           INTEGER      NOT NULL,
    provider_id        VARCHAR(26)  NOT NULL REFERENCES llm_provider (id),
    model              VARCHAR(128) NOT NULL,
    params_json        TEXT         NOT NULL DEFAULT '{}',
    PRIMARY KEY (profile_version_id, position)
);
CREATE TABLE IF NOT EXISTS llm_budget (
    id            VARCHAR(26)   NOT NULL PRIMARY KEY,
    tenant_id     VARCHAR(26)   NOT NULL REFERENCES tenant (id) ON DELETE CASCADE,
    scope_kind    VARCHAR(16)   NOT NULL,
    scope_id      VARCHAR(64)   NOT NULL DEFAULT '',
    period        VARCHAR(8)    NOT NULL,
    limit_micros  INTEGER,
    limit_tokens  INTEGER,
    action        VARCHAR(8)    NOT NULL DEFAULT 'refuse',
    updated_at    VARCHAR(32)   NOT NULL,
    updated_by    VARCHAR(26),
    CONSTRAINT uq_llm_budget_scope UNIQUE (tenant_id, scope_kind, scope_id, period),
    CONSTRAINT ck_llm_budget_kind CHECK (scope_kind IN ('tenant', 'profile', 'principal', 'api_key')),
    CONSTRAINT ck_llm_budget_period CHECK (period IN ('day', 'month')),
    CONSTRAINT ck_llm_budget_action CHECK (action IN ('refuse', 'warn'))
);
CREATE TABLE IF NOT EXISTS llm_reservation (
    id             VARCHAR(26)  NOT NULL PRIMARY KEY,
    tenant_id      VARCHAR(26)  NOT NULL,
    scopes_json    TEXT         NOT NULL,
    reserved_micros INTEGER     NOT NULL,
    reserved_tokens INTEGER     NOT NULL,
    expires_at     VARCHAR(32)  NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_llm_reservation_tenant ON llm_reservation (tenant_id, expires_at);
CREATE TABLE IF NOT EXISTS llm_call (
    id                  VARCHAR(26)   NOT NULL PRIMARY KEY,
    tenant_id           VARCHAR(26)   NOT NULL,
    sequence            INTEGER       NOT NULL,
    started_at          VARCHAR(32)   NOT NULL,
    finished_at         VARCHAR(32)   NOT NULL,
    principal_id        VARCHAR(26),
    api_key_id          VARCHAR(26),
    surface             VARCHAR(32)   NOT NULL,
    purpose             VARCHAR(64)   NOT NULL DEFAULT '',
    profile_id          VARCHAR(26),
    profile_version     INTEGER,
    template_id         VARCHAR(26),
    template_version    INTEGER,
    provider_id         VARCHAR(26),
    provider_kind       VARCHAR(64)   NOT NULL DEFAULT '',
    hosting             VARCHAR(16)   NOT NULL DEFAULT '',
    destination_region  VARCHAR(32)   NOT NULL DEFAULT '',
    jurisdiction        VARCHAR(32)   NOT NULL DEFAULT '',
    sensitivity         VARCHAR(16)   NOT NULL,
    model_requested     VARCHAR(128)  NOT NULL DEFAULT '',
    model_reported      VARCHAR(128)  NOT NULL DEFAULT '',
    model_version       VARCHAR(128)  NOT NULL DEFAULT '',
    price_model_id      VARCHAR(26),
    request_fingerprint VARCHAR(64)   NOT NULL,
    prompt_hash         VARCHAR(64)   NOT NULL,
    response_hash       VARCHAR(64)   NOT NULL DEFAULT '',
    payload_digest      VARCHAR(64),
    redactions_json     TEXT          NOT NULL DEFAULT '{}',
    temperature         REAL          NOT NULL DEFAULT 0,
    seed                INTEGER,
    input_tokens        INTEGER       NOT NULL DEFAULT 0,
    cached_tokens       INTEGER       NOT NULL DEFAULT 0,
    output_tokens       INTEGER       NOT NULL DEFAULT 0,
    tokens_estimated    INTEGER       NOT NULL DEFAULT 0,
    cost_micros         INTEGER       NOT NULL DEFAULT 0,
    latency_ms          INTEGER       NOT NULL DEFAULT 0,
    attempts            INTEGER       NOT NULL DEFAULT 1,
    fallback_from       VARCHAR(26),
    served_from         VARCHAR(16)   NOT NULL DEFAULT 'provider',
    schema_valid        INTEGER,
    grammar_enforced    INTEGER       NOT NULL DEFAULT 0,
    outcome             VARCHAR(24)   NOT NULL,
    outcome_detail      TEXT          NOT NULL DEFAULT '',
    correlation_id      VARCHAR(64),
    previous_hash       VARCHAR(64)   NOT NULL,
    record_hash         VARCHAR(64)   NOT NULL,
    CONSTRAINT ck_llm_call_served CHECK (served_from IN ('provider', 'cache', 'replay')),
    CONSTRAINT ck_llm_call_outcome CHECK (outcome IN ('ok', 'incomplete', 'refused_policy',
        'refused_budget', 'refused_rate', 'error', 'cancelled')),
    CONSTRAINT ck_llm_call_flags CHECK (tokens_estimated IN (0, 1) AND grammar_enforced IN (0, 1)
        AND (schema_valid IS NULL OR schema_valid IN (0, 1)))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_llm_call_sequence ON llm_call (tenant_id, sequence);
CREATE INDEX IF NOT EXISTS ix_llm_call_time ON llm_call (tenant_id, started_at);
CREATE INDEX IF NOT EXISTS ix_llm_call_profile ON llm_call (profile_id, started_at);
CREATE INDEX IF NOT EXISTS ix_llm_call_principal ON llm_call (principal_id, started_at);
CREATE TABLE IF NOT EXISTS llm_payload (
    digest         VARCHAR(64)  NOT NULL PRIMARY KEY,
    tenant_id      VARCHAR(26)  NOT NULL,
    request_json   TEXT         NOT NULL,
    response_json  TEXT         NOT NULL DEFAULT '',
    mode           VARCHAR(16)  NOT NULL,
    created_at     VARCHAR(32)  NOT NULL,
    expires_at     VARCHAR(32),
    CONSTRAINT ck_llm_payload_mode CHECK (mode IN ('redacted', 'full'))
);
CREATE INDEX IF NOT EXISTS ix_llm_payload_expiry ON llm_payload (expires_at);
CREATE TABLE IF NOT EXISTS llm_eval_run (
    id               VARCHAR(26)  NOT NULL PRIMARY KEY,
    tenant_id        VARCHAR(26)  NOT NULL,
    suite            VARCHAR(128) NOT NULL,
    suite_hash       VARCHAR(64)  NOT NULL,
    profile_id       VARCHAR(26),
    profile_version  INTEGER,
    template_id      VARCHAR(26),
    template_version INTEGER,
    cases            INTEGER      NOT NULL DEFAULT 0,
    passed           INTEGER      NOT NULL DEFAULT 0,
    status           VARCHAR(16)  NOT NULL DEFAULT 'running',
    report_json      TEXT         NOT NULL DEFAULT '{}',
    started_at       VARCHAR(32)  NOT NULL,
    finished_at      VARCHAR(32),
    started_by       VARCHAR(26),
    CONSTRAINT ck_llm_eval_status CHECK (status IN ('running', 'passed', 'failed', 'error'))
);
```

Payload expiry blanks `llm_payload` rows; `llm_call` keeps the hashes, so the chain verifies across the
gap (the `ev_sample` pattern). Admin changes also write `audit_event`. A test asserts the CHECK lists
equal the Python enums (as for `ev_record`).

## 11. HTTP API (`/api/v1/llm`)

New scopes in `security/scopes.SCOPES`, granted in `BUILTIN_ROLES` (test_scopes checks both directions):
`llm:invoke`, `llm:read` (usage, profiles, call metadata), `llm:audit` (payloads), `llm:manage`
(providers, models, profiles, templates, budgets, evals), `llm:credential` (write credentials; separate
for segregation of duties).

| Method & path | Scope | Notes |
|---|---|---|
| `POST /chat` | invoke | `{profile, messages \| template+variables, tools?, response_schema?, sensitivity, context:{dataset,jurisdiction}, max_tokens?, idempotency_key?}`; only params in `overridable_json` may be overridden. `Accept: text/event-stream` streams |
| `POST /embed`, `POST /count-tokens` | invoke | |
| `GET /profiles` | read | profiles the caller may use, with capabilities |
| `GET /usage?group_by=profile\|principal\|day` | read | derived from `llm_call` |
| `GET /calls`, `GET /calls/{id}` | read | payload only with `llm:audit` |
| `POST /calls/{id}/replay` `{mode}` | invoke + audit | |
| `GET/POST/PATCH /providers`, `POST /providers/{id}/test` | manage | test = tiny capped prompt, audited |
| `PUT /providers/{id}/credential` | credential | body `{value}` or `{reference}`; returns `{reference, fingerprint}` only |
| `…/models`, `…/profiles/{purpose}/versions`, `…/templates/{name}/versions`, `…/budgets`, `…/evals` | manage | versions are POSTed, never edited; `activate` needs eval gate + a second principal for templates |

SSE events: `meta` (call id, provider, model, profile version), `delta`, `tool_call`, `usage`, `done`
(full `Response.to_dict()`), `error` (Prama error code + remedy); `: keepalive` every 15 s. Errors:
`RESIDENCY.REFUSED` 403, `LLM.SENSITIVITY_REFUSED` 403, `LLM.RATE_LIMITED`/`LLM.BUDGET_EXHAUSTED` 429
with `Retry-After`, provider failure 200 with `incomplete` (unchanged doctrine), `LLM.NO_PROFILE` 404.
Prama's own agents and external tools use `RemoteGatewayProvider` (a `ModelProvider` over this API),
so the server — not the caller — holds credentials, enforces residency and writes the ledger.

## 12. UI (`/llm/…`, console routes + Jinja templates)

- **Providers**: list with kind, hosting badge, region, health (last test), circuit state; add/edit
  form derived from the kind's declared config fields (as connector forms are). Offline mode hides
  remote kinds and says why.
- **Credentials**: write-only — `type=password`, never a `value` attribute, shows reference and
  fingerprint + last-resolved time from the secret-access audit; "rotate" writes a new envelope.
- **Models & prices**: per provider, price history.
- **Profiles**: purpose → ordered route, params, redactors, max sensitivity; version history with
  diff; activation button disabled until an eval run passes.
- **Templates**: versioned editor, variables with sensitivity, response schema; approve (second person).
- **Playground**: pick profile/template, fill variables, see redaction preview, routed candidate and
  *why others were excluded*, stream the answer, tokens/cost/latency, "replay"/"compare".
- **Usage & cost**: by day/profile/principal against budgets; **Audit**: call list with filters,
  chain-verify status, payload view (llm:audit).
- **Budgets**: per scope/period, refuse/warn, current burn derived from the ledger.

## 13. Tests (each guard with its counterfactual)

- `(planned) tests/llm/test_spi_compat.py`: pinned legacy fingerprint; adding a default field leaves it unchanged,
  a non-default one changes it.
- `test_wire_<kind>.py`: golden request bodies per dialect; tool calls; SSE/event-stream fixtures incl.
  a CRC-corrupted frame; `grammar_enforced` false for `ollama` (fails against today's code).
- `test_sigv4.py`: AWS SigV4 test-suite vectors.
- `test_transport_clearance.py`: send without clearance refused; clearance for another fingerprint refused.
- `test_routing.py`: EU-bound prompt with `[anthropic(US), ollama(local)]` → ollama; only remote →
  refused and ledgered `refused_policy`; no silent cross-hosting fallback.
- `test_hosting_honesty.py`: `openai_compatible` at `api.openai.com` declared self_hosted → refused.
- `test_budget.py`: two gateways over one DB race to the limit; overrun ≤ 0 under the lease, and
  > 0 with the lease disabled (the counterfactual).
- `test_cache.py`: temperature>0 not cached; cross-tenant miss; a cached entry for a request now
  residency-refused is still refused.
- `test_redact.py`: PAN/IBAN/secret shapes; plaintext absent from payload, ledger, logs (caplog).
- `test_ledger.py`: chain verifies; edited row detected; expired payload still verifies.
- `test_schema.py`: invalid → one repair → `schema_valid=False`; unsupported keyword refused at save.
- `(planned) tests/api/test_llm_api.py`: 403 without scope, 429 with Retry-After, SSE order, disconnect →
  `cancelled`, credential PUT never echoes the value (response, audit_event, logs).
- `(planned) tests/web/test_llm_pages.py`: credential page renders no secret; axe pass.
- `tests/architecture`: transport is the only network module in `prama.llm`; `complete_stream`/
  `complete_embed` join `complete` in the no-direct-call guard; CON-007 import-direction test (§9);
  `prama.llm` ↛ `prama.db`; scopes both directions.
- Live conformance, opt-in: `PRAMA_TEST_OLLAMA_URL`, `…_VLLM_URL`, `…_LLAMACPP_URL`, `…_ANTHROPIC_KEY`,
  `…_BEDROCK_*`. Manifests stay `verification="code_complete"` until run live; a test asserts no
  docstring claims otherwise.

## 14. Phased plan

**Phase 1 — local models, profiled and audited (small, shippable).** SPI additions (messages, usage,
capabilities, response schema + stdlib validator, estimated token counts) with pinned fingerprints;
`transport.py` extraction + clearance + egress row move; `openai_compatible` dialects (vllm, ollama,
llamacpp, lmstudio, tgi) with honest `grammar_enforced`; hosting honesty; tables `llm_provider`,
`llm_profile`, `llm_profile_version`, `llm_profile_route`, `llm_call`; gateway steps 1, 4, 7, 8, 9
(routing, timeouts, retries, fallback, ledger); `ProfileProvider` wired into Assistant and Inducer;
CLI `prama llm provider add|list|test`, `profile set|show`, `ask`, `calls`; `llm.offline`. CON-007
import-direction test lands here.
**Phase 2 — the server as the only door.** `/api/v1/llm` with scopes, SSE, rate limits; Anthropic
tools + streaming; `llm_model` pricing, budgets + reservations; cache; redactors; `llm_payload`.
**Phase 3 — governance and UI.** Console pages; sealed credentials; versioned templates with
approval; eval harness + activation gate; replay.
**Phase 4 — clouds.** Bedrock (SigV4 stdlib; `aws` extra for credential chain), Azure OpenAI, OpenAI,
HF endpoints/router, embeddings routes; Vertex optional.
**Phase 5 — reach.** `RemoteGatewayProvider` for data-zone agents; SIEM export of `llm_call`; MCP
read tools for usage.
