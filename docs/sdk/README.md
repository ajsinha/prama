<img src="../assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

*Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.*

---

# The Python SDK

Everything Prama does, from Python: declare an estate, derive and accept controls, run them,
read the evidence, work incidents and breaks, attest, manage people and models. The SDK is a
client of a **running** Prama server. It never opens Prama's database itself, so a script, a
notebook, a CI job and the case studies all act on the same estate the console shows, as a
named person with that person's permissions.

It is its own package, `prama-sdk`, imported as `prama_sdk`, and it never imports the server: a
client machine installs it alone, with `httpx` and `PyYAML` as its only dependencies.

```bash
pip install prama-sdk          # or, from a checkout: uv build --wheel sdk
```

Every endpoint of the HTTP API (`/api/v1`) has an SDK method, and every SDK method calls an
endpoint. `tests/sdk/test_parity.py` fails the build otherwise, so this stays true as the API
grows; adding a method is in [the developer guide](../developer/sdk-methods.md).

## Connecting

```python
import prama_sdk as prama

client = prama.connect(username="admin", password="prama-dev-admin")
print(client.auth.me())            # who you are, in which estate, with which scopes
```

`connect()` finds the server the way the server finds itself: it reads
`config/application.yaml` (with `application.local.yaml` beside it) and uses `server.host` and
`server.port`. To use another server, give it another configuration file or a URL:

```python
client = prama.connect(config="/etc/prama/application.yaml")
client = prama.connect("https://prama.example.com", api_key="pk_live_…")
```

A server bound to every interface (`0.0.0.0`) is reached on loopback. If nothing answers,
`connect` raises `ServerUnavailable`, naming the address it tried and how to start Prama.

### Credentials

First match wins:

1. `api_key=` passed explicitly;
2. the `PRAMA_API_KEY` environment variable;
3. `username=` and `password=`, exchanged for an **expiring** key (12 hours by default) that
   carries exactly the scopes your roles grant;
4. `PRAMA_USERNAME` and `PRAMA_PASSWORD` from the environment, likewise;
5. none: only the public endpoints (`client.system.health()`) answer.

On an installation with more than one estate, name the one you mean: `connect(...,
tenant="acme-bank")`. A key you minted by signing in is listed on your account page, and
`client.auth.revoke()` ends it at once.

The SDK refuses to send a credential over plain `http://` to anything but this machine. Use
`https://`, or pass `insecure=True` knowingly.

## Estates

An API key is bound to one estate. Creating an estate makes you its first administrator, with
the same username and password, and returns a key for it:

```python
made = client.tenants.create("acme-markets", "Acme Markets")
markets = client.as_key(made["credentials"]["api_key"])
markets.datasets.declare("Trades", description="Executed trades, as booked.")
```

In the console, sign-in asks for the estate once there is more than one, and the user menu
names the estate you are in and offers **Switch estate**.

## Approval: somebody else signs it off

A Tier-1 or Tier-2 declaration (a dataset, an amendment, a relationship, a journey) is
**held** when you make it, with `lifecycle_state` `proposed`, until somebody holding
`declaration:approve` approves it as themselves. The rules by tier are in
[the semantic layer](../architecture/semantic-layer.md); from Python:

```python
held = client.datasets.declare("FRTB Feeder", criticality=1)   # lifecycle_state: proposed
owner.datasets.approve(held["id"], reason="reviewed the grain")  # now active
owner.relationships.confirm(relationship_id)                     # confirming is approving
owner.journeys.approve(journey_id)
```

At Tier 1 the approver must not be the author, and the same holds for activating a control
a person wrote ([controls](controls.md#a-controls-life)). An amendment cannot approve itself:
`lifecycle_state`, `approved_by` and `authored_by` are refused in its `changes`.

## Sync and async

`Client` blocks; `AsyncClient` has the same namespaces and every method returns a coroutine:

```python
async with prama.AsyncClient("http://127.0.0.1:5900", api_key=key) as client:
    page = await client.datasets.list()
```

Both can also run **in-process** against an application object (`Client(app=app)`), which is
how Prama's own tests drive the SDK: every layer runs except the socket.

## Errors

A refusal raises Prama's own error class, the one the server raised, with its message and its
remedy:

```python
try:
    client.datasets.get("01NOPE")
except prama.NotFoundError as error:
    print(error.message, "—", error.remedy)
```

`UnauthorisedError` (401), `ForbiddenError` (403, a missing scope), `NotFoundError`,
`ConflictError`, `ValidationError`, `RateLimitedError` (429, a model budget or a rate
exhausted), `ServerError` (5xx; its context carries the correlation id), and
`ServerUnavailable` when nothing answered at all. All derive from `prama.PramaError`.

## The namespaces

Forty-two namespaces cover 250 endpoints: everything the console and the CLI do, except what is
purely local to one machine (`prama db init`, `prama serve`, `prama lsp serve`). Each page
beside this one covers one area, with worked examples:

| Page | What it is | Namespaces |
|---|---|---|
| this page | Connecting, credentials, estates, approval, errors; declaring the semantic layer | `auth`, `tenants`, `system`, `datasets`, `relationships`, `concepts`, `journeys`, `connections`, `estate` |
| [controls](controls.md) | Deriving, authoring, activating and running controls, and the language | `controls`, `pql`, `proposals`, `derive`, `runs`, `schedule` |
| [evidence](evidence.md) | Reading and verifying the ledger, incidents, scores, attestations, report packs | `evidence`, `incidents`, `scorecards`, `attestations`, `reports` |
| [reconciliation](reconciliation.md) | What a reconciliation found, working its breaks, the period-end certificate | `reconciliation`, `breaks` |
| [contracts](contracts.md) | Gating a build on an ODCS contract, and diffing two versions of a dataset | `contracts` |
| [usage](usage.md) | Importing warehouse query history and ranking what to control first | `usage` |
| [administration](administration.md) | People, roles and keys; models, budgets and the call ledger; steward agents; configuration and audit | `principals`, `roles`, `api_keys`, `account`, `models`, `agents`, `config`, `audit` |
| [knowledge and code](knowledge-and-code.md) | Lineage, code intake and review, glossary, metadata, comments, delegates, packs, connectors | `lineage`, `code`, `glossary`, `metadata`, `comments`, `delegates`, `packs`, `connectors`, `llm` |
| [fleet](fleet.md) | Administering agents beside the data, and the calls an agent itself makes | `fleet` |

## A whole estate, from Python

The case studies (`case-studies/*/run.py`) are the long worked examples: each signs in to your
running server, creates an estate, declares it, derives and accepts controls, has the server run
them against the study's data, and reads back what the evidence says. The core of it:

```python
import prama_sdk as prama

admin = prama.connect(username="admin", password="prama-dev-admin", tenant="default")
made = admin.tenants.create("acme-markets", "Acme Markets")
client = admin.as_key(made["credentials"]["api_key"])

trades = client.datasets.declare(
    "Trades", description="Executed trades, as booked.", criticality=3,
    grain={"attributes": ["trade_id"], "statement": "one row per executed trade"},
)
client.datasets.add_attribute(trades["id"], "trade_id", optionality="mandatory")
client.datasets.add_attribute(trades["id"], "ccy", codelist=["USD", "EUR", "GBP"])

client.derive.dataset(trades["id"], declare=True, accept=True, reason="reviewed")

book = client.connections.create("book", "sqlite", config={"path": "/data/landing/book.db"})
report = client.runs.start(book["id"], datasets=["trades"])
print(report["summary"])
print(client.evidence.verify()["intact"])
```

The server reads the source itself, so its path must be under one of the server's `runs.roots`
(`config/application.yaml`); Prama's own database never may be. The connection kinds a run
can open are in [controls](controls.md#run-on-the-server).

---

<div align="center">
<img src="../assets/prama-mark.svg" width="30" alt=""/><br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.<br/>
See <a href="../../LICENSE">LICENSE</a> and <a href="../../NOTICE">NOTICE</a>. Third-party names and marks are the property of their respective owners.</sub>
</div>
