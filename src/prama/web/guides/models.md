<!-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE. -->

# Models: providers, profiles and the call ledger

The language models Prama may use, which one serves which purpose, what they may cost, and the
record of every call. The page is **Admin → Models** (`/models`). Models draft controls, explain
findings, summarise and search; **they never decide a verdict**, so with no model configured every
control, verdict and piece of evidence works exactly the same.

## To add a provider

A provider is where a model runs. On **Models**, fill in **Add provider**, or:

```bash
# A local Ollama: nothing leaves this machine.
prama llm provider add local --kind openai_compatible --hosting self_hosted \
    --dialect ollama --endpoint http://localhost:11434

# A vendor API: hosted, with the key held by the secrets layer, never here.
prama llm provider add vendor --kind anthropic --hosting hosted \
    --credential-ref env://ANTHROPIC_API_KEY
```

1. **Choose the kind.** `openai_compatible` covers OpenAI, Hugging Face, vLLM, Ollama, llama.cpp, LM
   Studio and TGI. The others need a little more:
   - `bedrock`: the AWS region (the provider's `aws_region` setting, else `--region`), and a
     credential reference resolving to `ACCESS_KEY_ID:SECRET_ACCESS_KEY[:SESSION_TOKEN]`;
   - `azure_openai`: `--endpoint https://<resource>.openai.azure.com`, and the route's model is the
     **deployment name**;
   - `vertex`: the endpoint
     `https://<location>-aiplatform.googleapis.com/v1/projects/<project>/locations/<location>/endpoints/openapi`,
     a credential resolving to an OAuth access token, and Vertex model names such as
     `google/gemini-2.0-flash-001`.
2. **Declare the hosting.** It decides what data may be sent: `self_hosted` anything, `tenant` (a
   vendor's model in your own cloud) anything but restricted data, `hosted` only public and internal
   data. A vendor's API cannot be declared self-hosted.
3. **Choose the server dialect** for a local server. It matters for constrained output: vLLM enforces
   a grammar and a regex, llama.cpp a grammar only, the rest neither, and Prama records a constraint
   as enforced only when the server applies it.
4. **Give a credential reference** (`env://NAME`, `vault://path`), never a key. The page never shows one.

## To route a purpose to a model

A profile maps a purpose to an ordered route of `provider:model`. **Save as a new version** on the
page, or:

```bash
prama llm profile set author --route local:qwen2.5-coder:7b --route vendor:claude-sonnet-5
prama llm profile show
```

Each step is tried in order, and the route never falls back to a *less local* model unless the profile
allows it. Every save is a new version, so you can tell which model wrote a proposal. A purpose with
no profile goes to the built-in **mock**, which answers with nothing and says no model is configured,
so model-assisted extras simply do not appear.

| Purpose | What for |
|---|---|
| `author`, `explain`, `summarise` | drafting and explaining controls, incident briefs |
| `lineage` | proposing lineage for code the parsers could not read |
| `curate` | drafting descriptions for datasets that have none |
| `discover` | explaining which datasets fit a stated purpose |
| `embed` | embedding dataset profiles for meaning-based search |

## To control spend

1. **Save price** for each model: currency units per million input and output tokens. Each call is
   costed from the price in force when it started.
2. **Save budget** for the estate, per day or month, to either **refuse** further calls (HTTP 429, and
   the refusal is recorded) or **warn**. Budgets for a profile, a person or an API key are set through
   the API (`PUT /api/v1/models/budgets`) or the SDK's `client.models.set_budget`.

Every model call is checked against the budgets, whichever path makes it: the console, the API,
stewards, code intake, search or the CLI. Spend is derived from the call ledger, so the two cannot
disagree.

## To try a prompt, and read the ledger

Use **Try a prompt** on the page, or:

```bash
prama llm ask author "Write a control that trades.notional is never null"
prama llm calls          # newest first: purpose, model, hosting, tokens, latency, outcome
prama llm verify         # recompute the ledger's hash chain
```

Every call, refusals and failures included, is recorded and hash-chained per estate. By default only
hashes of the prompt and answer are kept; `llm.audit.payloads: redacted` keeps each exchange with
secrets, card numbers, IBANs and emails removed, and `full` keeps it exactly, blanked after
`llm.audit.payload_retention_days`. The chain still verifies after payloads expire.

## To gate a prompt or profile on an evaluation

```bash
prama llm template add explain.yaml               # a new draft version
prama llm eval run explain-suite.yaml             # deterministic checks only
prama llm template approve explain 3 --by <id>    # someone other than its author
```

An evaluation suite lists cases and what each answer must satisfy (`nonempty`, `contains`, `absent`,
`matches`, `json_valid`, `json_keys`, `pql_parses`, `max_latency_ms`); no model grades another. With
`llm.eval.gate_activation: true`, `prama llm profile set` records a version without making it current;
`prama llm eval run suite.yaml --profile-version N` then `prama llm profile activate <purpose> N` does.

## For programs and air-gapped estates

Programs call the server, never a provider: `POST /api/v1/llm/chat` with a key holding `llm:use`,
naming a `purpose` and a `prompt`. The server applies the profile, residency, redaction, the budget
and a per-person rate limit (`llm.per_principal_rpm`). Set `llm.offline: true` to use only
self-hosted providers on this machine or a private address.

## Go deeper

- [Intelligence: the gateway](../../../../docs/architecture/intelligence.md#the-gateway): the order of budget, routing, policy, redaction and record on every call.
- [Writing a model provider](../../../../docs/developer/llm-providers.md): adding a provider dialect.
- [LLM gateway: design](../../../../docs/design/llm-gateway.md): the design note.
