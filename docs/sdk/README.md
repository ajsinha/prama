<img src="../assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

*Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.*

---

# The Python SDK

Everything Prama does, from Python: declare an estate, derive and accept controls, run them,
read the evidence, work incidents and breaks, attest, manage people and models. The SDK is a
client of a **running** Prama server. It never opens Prama's database itself, so a script, a
notebook, a CI job and the case studies all act on the same estate the console shows, as a
named person with that person's permissions.

Every endpoint of the HTTP API (`/api/v1`) has an SDK method, and every SDK method calls an
endpoint. `tests/sdk/test_parity.py` fails the build otherwise, so this stays true as the API
grows.

## Connecting

```python
import prama.sdk as prama

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
`ConflictError`, `ValidationError`, and `ServerUnavailable` when nothing answered at all.

## The namespaces

Each area of Prama is a namespace on the client. The pages beside this one describe each area
with worked examples.

| Namespace | What it is for |
|---|---|
| `auth`, `tenants`, `system` | signing in, who you are, estates, health |
| `datasets`, `relationships`, `concepts`, `journeys`, `connections`, `estate` | the semantic layer and where data lives |
| `metadata`, `comments`, `lineage`, `llm`, `agents`, `delegates` | business context, discussion, lineage, models, agents, Python checks |
