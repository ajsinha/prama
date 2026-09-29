<img src="../assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

*Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.*

---

# Administration, identity, models and agents

Everything the console's Administration, Account, Models and Agents pages do, and what
`prama principal`, `prama apikey`, `prama llm` and `prama config show` do, from Python.

| Namespace | What it is for | Needs |
|---|---|---|
| `client.principals` | People and service principals: create, roles, password, disable | `admin` |
| `client.roles` | The built-in roles and every scope, with its meaning | `admin` |
| `client.api_keys` | Your own keys; and, for an administrator, every key in the estate | your key / `admin` |
| `client.account` | Who you are; change your own password | your key |
| `client.models` | The model gateway: providers, profiles, templates, prices, budgets, the call ledger, evaluations | `admin` |
| `client.agents` | Steward agents: create, give goals, run, the kill switch, decide what they ask | `admin` (the agent's own side: `agent:work`) |
| `client.config` | The effective configuration, always redacted | `admin` |
| `client.audit` | The append-only audit log | `admin` |

The rules behind people and keys live in one place, `src/prama/security/people.py`,
which the console and the API both call. A refusal on one surface is a refusal on the other.

Every example below starts from a signed-in client:

```python
import prama.sdk as prama

client = prama.connect()                     # reads config/application.yaml
# or: client = prama.Client("https://prama.example.com").as_key(key)
```

## People

```python
bo = client.principals.create("bo", roles=["steward"], password=initial_password)
client.principals.list()                     # everybody: roles, status, can_sign_in
client.principals.get("bo")                  # by username or id
client.principals.set_roles("bo", ["steward", "owner"])   # exactly these, replacing the rest
client.principals.reset_password("bo", new_password)      # their console sessions end
client.principals.disable("bo")              # offboarding
client.principals.enable("bo")
client.roles.list()                          # {"roles": [...], "scopes": {scope: meaning}}
```

Without a password a principal exists but cannot sign in — the right shape for a service
that will only ever use a key an administrator mints for it.

**What an administrator may not do.** Delete a person (evidence and attestations name their
actor, and an audit trail pointing at nobody answers nothing — disabling is the offboarding
verb); disable themselves or remove their own `admin` role (an estate that lost its last
administrator has to be repaired from a shell); or see a password or a key.

**Disabling is immediate everywhere.** A key acts as its principal, so every key a disabled
person holds stops working at once, and a new sign-in is refused. Enabling them again makes
the same keys work again, unless they were revoked or have expired.

## Your account and your keys

```python
client.account.get()           # you, your roles, this key's scopes, and those it may grant
client.account.change_password(current, new)

key = client.api_keys.create("nightly-report", ["report:read", "evidence:read"], days=30)
key["plaintext"]               # the only copy: only a prefix and a hash are stored
client.api_keys.list()         # yours, revoked and expired ones included
client.api_keys.revoke(key["id"])
```

**A key can never exceed its holder.** Each scope you ask for must be one the key you are
using already holds. A steward asking for `control:approve` is refused, a key narrowed to
`report:read` cannot mint its way back to anything wider, and the wildcard `*` is never
granted this way:

```python
steward.api_keys.create("ci", ["control:approve"])
# prama.ValidationError: you cannot grant control:approve
```

**Nor its holder as they are now.** A key keeps the scopes it was minted with, but a person's
roles change, and a person's key is only ever worth what their roles grant *today*. Take
somebody's owner role and every key they hold stops approving at once, while still doing
whatever their remaining roles allow; nothing needs revoking. `client.auth.me()` shows both
the key's `scopes` and its `effective_scopes`. A service account — a steward agent — holds no
roles, so its key is its grant.

```python
client.principals.set_roles("olu", ["steward"])
olu.datasets.approve(dataset_id)
# prama.ForbiddenError: your roles no longer grant 'declaration:approve', though this key was issued with it
```

An administrator sees and revokes every key in the estate, and can mint a key that acts as a
service principal. Its scopes are explicit, not inherited from roles:

```python
client.api_keys.list_all()                   # each with its owner and state
client.api_keys.issue("svc-etl", "etl", ["declaration:read"], days=90)
client.api_keys.revoke_any(key_id)
```

## Models

A provider says where a model runs and how it is hosted; a profile maps a purpose
(`author`, `explain`, `summarise`) to an ordered route of provider and model.

```python
client.models.add_provider(
    "local", kind="openai_compatible", hosting="self_hosted",
    dialect="ollama", endpoint="http://localhost:11434",
)
client.models.add_provider(
    "openai", kind="openai_compatible", hosting="hosted",
    endpoint="https://api.openai.com/v1", credential_ref="env://OPENAI_KEY",
)
client.models.set_profile("author", ["local:qwen2.5-coder", "openai:gpt-4o-mini"])
client.models.try_model("author", "Draft a completeness check for trades.")
```

**No secret is stored.** `credential_ref` is a reference — `env://…`, `file://…`,
`vault://…` — resolved only when a call is made. A value that is not a reference (a pasted
key) is refused, not stored, and so is a provider setting named like a credential
(`api_key`, `token`, `password`…). A listing shows only `"credential": "reference set"`.

Prices, budgets and the call ledger:

```python
client.models.set_price("openai", "gpt-4o-mini", input_per_million="0.15", output_per_million="0.60")
client.models.set_budget(limit="250.00", period="month")           # the estate, refused beyond
client.models.set_budget(limit="20", period="day", scope_kind="principal",
                         scope_id=person_id, action="warn")
client.models.budgets()        # each with what has been spent this period
client.models.calls(limit=20)  # hashes, tokens, cost, outcome — never the prompt's text
client.models.verify()         # {"intact": True, "checked": 412, "break": ""}
```

`verify` recomputes the ledger's hash chain, as `prama llm verify` does. Any altered record
breaks it, and `break` names the first call that no longer matches its seal.

Templates and evaluation. A template version is a draft until approved, and **its author
cannot approve it**. With `llm.eval.gate_activation` on, a new profile version and a
template approval both wait for a passing evaluation run:

```python
client.models.add_template({"name": "explain", "system": "...", "body": "Explain {{pql}}.",
                            "variables": [{"name": "pql", "trusted": True}]})
run = client.models.evaluate({
    "name": "explain-suite", "purpose": "explain", "template": "explain",
    "cases": [{"name": "names the check", "vars": {"pql": "CHECK t.a IS NOT NULL"},
               "expect": {"nonempty": True, "contains": ["null"]}}],
})
run["status"], run["report"]                 # graded by fixed checks, recorded
client.models.approve_template("explain", 1)            # by someone else
client.models.activate_profile("explain", 2)            # when gated
```

A model's output is a draft for a person. Evaluations grade a model against fixed,
deterministic expectations; nothing here decides anything about your data.

Sending a prompt as an ordinary user (`llm:use`, budgeted and rate-limited) is
`client.llm.chat`, not this namespace.

## Agents

A steward is a service principal with a human sponsor and a propose-only key. It reads, calls
models through the gateway, and proposes. It never holds `admin`, `control:approve`,
`attestation:sign` or a write scope.

```python
made = client.agents.create("librarian")     # made["api_key"]: its key, shown once
client.agents.tools()                        # the goal kinds the server can run
goal = client.agents.add_goal(made["id"], "curation.describe", schedule="6h")
task = client.agents.run(goal["id"])         # now, on the server; returns the finished task
client.agents.tasks()
client.agents.set_state(made["id"], "paused")    # or stopped, or revoked (final)
```

A remote agent runs elsewhere with its own key and calls out; the server never calls it:

```python
agent = prama.Client(url).as_key(made["api_key"])
(task,) = agent.agents.claim()["tasks"]
agent.agents.ask(task["task"], task["fencing_token"], {"tool": "close_break"}, "explained")
```

**A person decides; an agent never approves.** Granting a requested action and accepting a
model's drafted description need `admin`, which a steward cannot hold, and a steward's
principal is refused even if somebody minted it a wildcard key by hand. The decision records
who made it:

```python
(approval,) = client.agents.approvals()
client.agents.decide(approval["id"], grant=True)   # decided_by: you

for s in client.agents.suggestions():
    client.agents.decide_suggestion(s["id"], accept=True)
    # the dataset is amended with you as its author; the model is named only in the reason
```

## Configuration and the audit log

```python
shown = client.config.show(provenance=True)
shown["values"]["security.session_secret"]       # "***"
shown["provenance"]["database.dialect"]          # which layer set it

client.audit.list(limit=50)
client.audit.list(object_kind="principal", object_id=person_id)
```

The configuration is always redacted over the API. `prama config show --raw` exists on the
host; it is not offered over the network, because a secret fetchable by anybody holding an
admin key is one more place for it to leak from.
