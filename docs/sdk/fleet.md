<img src="../assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

*Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.*

---

# The agent fleet from Python

`client.fleet` is both halves of the [agent fleet](../design/agent-fleet-http.md): the
administration of agents that run beside the data, and the three calls an agent itself
makes. How agents, the kernel and the server fit is in
[Agents and the fleet](../architecture/agents-and-fleet.md); running the daemon is the
[agent operator's guide](../agent/README.md). You need the agent-side calls only to write
an agent of your own: `prama-agent` already makes them.

## Administering the fleet

Everything here needs `admin`, except `dispatch`, which runs the estate's controls and so
needs `control:approve`.

```python
import prama_sdk as prama

client = prama.connect()

issued = client.fleet.issue_token("eu-frankfurt", name="eu-01", hours=2)
# {"token": "pft_…", "zone": "eu-frankfurt", "name": "eu-01", "expires_at": "…"}
```

The token is shown once, and the server keeps only its SHA-256 digest. It is redeemed
once, and not after it expires (`hours`, default `fleet.token_hours`). The zone is fixed
here, by you: the agent never names one, so it cannot ask for another zone's work.

```python
client.fleet.dispatch("eu-frankfurt", engine="sqlite", datasets=["trades"])
# {"zone": …, "engine": …, "queued": [...], "already_queued": [...], "unassignable": [...]}
```

`dispatch` queues the active controls on those datasets (every active control, if
`datasets` is left out) for the zone, each compiled by the server for `engine`. A control
already queued or claimed there is not queued twice. `unassignable` names what nothing can
run, with the reasons: a control that will not compile for the engine (not queued), and a
control no active agent in the zone can run today (queued all the same, for an agent that
enrols or upgrades later).

```python
client.fleet.agents()                   # id, name, zone, state, version, capabilities,
                                        # last seen, pending findings, last sequence
client.fleet.suspend(agent_id)          # refused until resumed; its claims return to the queue
client.fleet.resume(agent_id)           # a revoked agent is never resumed (ConflictError)
client.fleet.revoke(agent_id)           # its next message gets a permanent refusal
client.fleet.health()
```

`health` reports agents that have been silent longer than `fleet.stale_minutes`, queued,
claimed and expired claims per zone, what nothing in its zone can run, and the gaps agents
have reported in their own evidence. Silence is reported rather than inferred: a dead agent
and an agent whose datasets are all clean both send no failures.

## The agent's side

An agent holds no API key and never sees a scope, so it uses a client with no credential.
Its calls are authenticated by the token (enrolment) and then by its signature.

```python
from prama_sdk import Client

agent = Client("https://prama.example.com")      # no api_key
enrolled = agent.fleet.enrol(
    token, name="eu-01", version="1.0.0",
    capabilities={"engines": ["sqlite"], "max_concurrency": 4},
)
# {"agent_id": "01…", "key": "<64 hex characters>", "zone": "eu-frankfurt",
#  "poll_after_seconds": 30}
key = bytes.fromhex(enrolled["key"])            # store it with mode 0600; shown once
```

The server stores no key; it derives one from `fleet.secret` when it needs it
([identity and trust](../design/agent-fleet-http.md#identity-and-trust)).

```python
receipt = agent.fleet.hello(hello.to_dict(), key=key)      # a Hello message
answer = agent.fleet.report(report.to_dict(), key=key)     # a Report message
```

`hello` and `report` take the message as the kernel's `to_dict()` gives it
(`prama_kernel.agent.protocol.Hello` and `Report`), whole, and the key as bytes. The SDK
signs the message's canonical JSON and sends `X-Prama-Agent` and `X-Prama-Signature`; the
server rebuilds the message with `from_dict` and checks the signature over `signable()`.
Pass every field: a field left out here and filled with its default there is a different
message, and does not verify.

The answer to either is a **Receipt** or a **Refusal**, never an HTTP error:

* `hello` → a Receipt carrying the zone's queued `assignments` that fit the agent's
  capabilities, up to its free slots, each now claimed by this agent under a lease
  (`fleet.lease_seconds`); and `unassignable`, the zone's work this agent cannot run and
  why. A claim not reported within its lease returns to the queue.
* `report` → a Receipt with `accepted_through` (the highest of the agent's sequences
  accepted), `duplicates` (records at or below it: a redelivery, counted and dropped) and
  `rejected` (a jump, named with the sequence that was expected, the record still kept;
  or a record about a plan never assigned to the agent's zone, which is not recorded).
* A **Refusal** has a `reason`, a `remedy` and `permanent`. An unknown agent, a wrong
  signature and a revoked agent are permanent: stop. A suspended agent's is not: keep
  running, keep spooling, and try again.

```python
if "reason" in answer:
    stop = answer["permanent"]
```

## Configuration and signing

The `fleet.*` keys (the key-derivation secret, token lifetime, lease, poll interval and
staleness threshold) are in the
[configuration reference](../operations/configuration-reference.md); `fleet.secret` belongs
only in `config/application.local.yaml`.

The SDK writes the kernel's canonical JSON with the standard library (`prama_sdk.signing`),
and `tests/sdk/test_fleet_signing.py` holds it byte-equal to the kernel for Hello and Report
messages, so a client signs exactly what the server verifies.

---

<div align="center">
<img src="../assets/prama-mark.svg" width="30" alt=""/><br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.<br/>
See <a href="../../LICENSE">LICENSE</a> and <a href="../../NOTICE">NOTICE</a>. Third-party names and marks are the property of their respective owners.</sub>
</div>
