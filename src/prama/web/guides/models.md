<!-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE. -->

# Models: providers, profiles and the call ledger

Models draft controls, explain findings and summarise; **they never decide a verdict**. A
deterministic engine does, and a build test fails if any verdict-producing module can import the
model layer.

## Providers

A provider is where a model runs. Add one on the **Models** page (user menu → *Models*) or:

```bash
# A local Ollama serving Qwen or Llama: nothing leaves this machine.
prama llm provider add local --kind openai_compatible --hosting self_hosted \
    --dialect ollama --endpoint http://localhost:11434

# A vendor API: hosted, with the key held by the secrets layer, never here.
prama llm provider add vendor --kind anthropic --hosting hosted \
    --credential-ref env://ANTHROPIC_API_KEY
```

- **No model configured? The mock.** When a purpose has no profile, Prama routes it to a built-in
  **mock** model. The mock always answers with **nothing**, plus a note saying that no LLM is
  configured. This is deliberate: a placeholder that produced words would be stored or shown as
  if it were a real answer. Every model-assisted extra quietly does not appear. Deterministic
  controls, verdicts and evidence never depend on a model, so they are unaffected. Each call is
  still recorded in the call ledger as `mock`. You can also name the mock explicitly with
  `--kind mock`.
- **Amazon Bedrock**: `--kind bedrock --hosting tenant` with the AWS region in the provider's
  settings (`aws_region`) and a credential reference resolving to
  `ACCESS_KEY_ID:SECRET_ACCESS_KEY[:SESSION_TOKEN]`. Requests are signed with SigV4, checked against
  AWS's own published example.
- **Azure OpenAI**: `--kind azure_openai --hosting tenant --endpoint https://<resource>.openai.azure.com`.
  The route's model is the **deployment name**. The key is sent as `api-key`, and the API version
  is pinned.
- **Google Vertex AI**: `--kind vertex --hosting hosted`, with the endpoint set to
  `https://<location>-aiplatform.googleapis.com/v1/projects/<project>/locations/<location>/endpoints/openapi`.
  The credential reference resolves to an OAuth access token. Models are Vertex names, such as
  `google/gemini-2.0-flash-001`.
- **OpenAI, Hugging Face and other OpenAI-shaped APIs**: `--kind openai_compatible --hosting hosted`
  with the vendor's endpoint and a credential reference.
- **Hosting is required** and decides what data may be sent: `self_hosted` may receive anything,
  `tenant` (a vendor's model in your own cloud) anything but restricted data, and `hosted` only
  public and internal data. A vendor's API cannot be declared self-hosted.
- **Server dialect** matters for constrained output. vLLM enforces a grammar and a regex,
  llama.cpp a grammar only, and Ollama, LM Studio, TGI and OpenAI neither. Prama records a
  constraint as enforced only when the server really applies it.
- **Credentials** are references such as `env://NAME` or `vault://path`. The page never shows a
  key.

## Profiles

A profile maps a purpose (`author`, `explain`, `summarise`) to an ordered route of `provider:model`:

```bash
prama llm profile set author --route local:qwen2.5-coder:7b --route vendor:claude-sonnet-5
prama llm profile show
```

The gateway tries each step in order and retries a failure once before moving on. **It never falls
back to a less local model** unless the profile allows it. Saving a profile makes a new version,
so you can always tell which model wrote a proposal.

## Budgets and cost

Set a price per million tokens for each model (Models page, or `uow.llm.set_price`). Every call is
then costed in integer micro-units from the price in force when it started. A budget for the
estate, a profile, a person or an API key, per day or month, either **refuses** further calls
(HTTP 429, and the refusal is recorded) or **warns**. Spend is always derived from the call
ledger, so it cannot disagree with it.

## For programs and agents

Programs and Prama agents call the server rather than a provider:

```bash
curl -X POST http://127.0.0.1:5900/api/v1/llm/chat \
     -H "Authorization: Bearer pk_live_…" -H "content-type: application/json" \
     -d '{"purpose": "author", "prompt": "Write a control that trades.notional is never null"}'
```

The key needs the `llm:use` scope. The server applies the profile, residency, redaction, the
budget and a per-person rate limit, and records the call. No program needs a provider key.

## Offline

Set `llm.offline: true` in `config/application.yaml` for an air-gapped estate. Only self-hosted
providers on this machine or a private network address are then used.

## Templates, evaluation and the gate

A **prompt template** is a feature's instructions, with named `{{ variables }}`. Each variable
declares a sensitivity, and whether it is trusted, meaning Prama composed it itself. Everything
untrusted reaches the model fenced, marked as data rather than instructions.

```bash
prama llm template add explain.yaml               # a new draft version
prama llm eval run explain-suite.yaml             # grade it: deterministic checks only
prama llm template approve explain 3 --by <id>    # someone other than its author
```

An **evaluation suite** lists cases and what each answer must satisfy: `nonempty`, `contains`,
`absent`, `matches`, `json_valid`, `json_keys`, `pql_parses` or `max_latency_ms`. No model grades
another model.

With `llm.eval.gate_activation: true`, `prama llm profile set` records a new version without
making it current. After a passing run, `prama llm eval run suite.yaml --profile-version N` and
then `prama llm profile activate <purpose> N` make it current. With no model configured nothing
can pass, because the mock answers with nothing.

## Stored payloads

By default only hashes are kept. Set `llm.audit.payloads: redacted` to keep each exchange with
secrets, card numbers, IBANs and emails removed, or `full` to keep it exactly. Stored payloads
are blanked after `payload_retention_days`. `prama llm verify` recomputes the call ledger's hash
chain, and it still verifies after payloads expire.

## The call ledger

Every call, including refusals and failures, is recorded with its purpose, model, hosting,
tokens, latency and outcome. Prompts and answers are stored as hashes, never as text. Records
are hash-chained per estate, like the evidence ledger. Secrets and card numbers are removed from
prompts before they leave.

```bash
prama llm ask author "Write a control that trades.notional is never null"
prama llm calls
```
