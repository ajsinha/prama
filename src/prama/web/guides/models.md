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

## The call ledger

Every call, including refusals and failures, is recorded with its purpose, model, hosting,
tokens, latency and outcome. Prompts and answers are stored as hashes, never as text. Records
are hash-chained per estate, like the evidence ledger. Secrets and card numbers are removed from
prompts before they leave.

```bash
prama llm ask author "Write a control that trades.notional is never null"
prama llm calls
```
