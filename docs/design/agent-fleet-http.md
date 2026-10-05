<img src="../assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

*Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.*

---

# The agent fleet over HTTP

A **Prama agent** is a daemon beside the data that reports findings, never data
([what it is](../architecture/agents-and-fleet.md); [why](../corpus/22-distributed-execution.md)).
This page is the contract between the two halves. The server side lives in
`prama.agent` (coordinator, registry, compilation of assignments) and a fleet API;
the agent side in `agent/src/prama_agent`. Message shapes are the kernel's
(`prama_kernel.agent.protocol`): `Hello`, `Assignment`, `Report`, `Receipt`,
`Refusal`, each with `to_dict` / `from_dict`, and a signed message's `signable()`
is identical after a JSON round trip (`tests/agent/test_protocol_roundtrip.py`).

## Identity and trust

* An administrator issues a **one-time enrolment token** for a zone. The zone is
  fixed at issue, never chosen by the agent.
* The agent redeems it once (`POST /fleet/enrol`) and receives its `agent_id`
  and a **key**, shown once, stored by the agent in its state directory with mode
  0600. The server stores no key: it is derived,
  `HMAC-SHA256(fleet secret, "agent:" + tenant_id + ":" + agent_id)`, where the
  fleet secret is `fleet.secret` from the untracked local configuration, falling
  back to `security.session_secret`. Revoking an agent is a state change, not a key
  deletion.
* Every agent message after enrolment is **signed**:
  `X-Prama-Agent: <agent_id>` and `X-Prama-Signature: <hex HMAC-SHA256(key,
  message.signable())>`. The server rebuilds the message with `from_dict`,
  recomputes the signature over `signable()`, and compares in constant time
  (`prama_kernel.agent.signing.verify_payload`).
* An agent that is unknown, suspended or revoked, or whose signature does not
  verify, gets a **Refusal**, not an HTTP error: the protocol answer is the body.
  A revoked agent's refusal is `permanent: true`, and the daemon stops.
* Agents never hold API keys and never see a scope. The fleet's agent-facing
  routes authenticate the signature instead, and are listed with that reason in
  `tests/architecture/test_scopes.py`.

## Endpoints (under `/api/v1`)

| Method and path | Who | Body → answer |
|---|---|---|
| `POST /fleet/tokens` | administrator | `{zone, name?, hours?}` → `{token, zone, expires_at}` (plaintext once) |
| `GET /fleet/agents` | administrator | → every agent: id, name, zone, state, version, capabilities, last seen, pending findings, last sequence |
| `POST /fleet/agents/{id}/suspend`, `/resume`, `/revoke` | administrator | → the agent |
| `GET /fleet/health` | administrator | → stale agents, queued work per zone, unassignable controls |
| `POST /fleet/dispatch` | `control:approve` | `{zone, datasets?, engine}` → queues the active controls on those datasets as assignments for the zone, compiled by the server (`prama.agent.assign.assignment_for`); → `{zone, engine, queued, already_queued, unassignable}` |
| `POST /fleet/enrol` | the token holder | `{token, name, version, capabilities}` → `{agent_id, key, zone, poll_after_seconds}` |
| `POST /fleet/hello` | a signed agent | `Hello` → `Receipt` (with the zone's assignments that fit its capabilities) or `Refusal` |
| `POST /fleet/report` | a signed agent | `Report` → `Receipt` (`accepted_through`, `duplicates`, `rejected`) or `Refusal` |

Assignments are **claimed**: `hello` hands a queued assignment to one agent and marks
it claimed, so two agents in a zone never both run it; a claim not reported within
its lease returns to the queue. A report is **at-least-once**: the server dedupes by
the agent's own sequence (records at or below the agent's `last_sequence` are
duplicates; a jump is named in `rejected` with the expected sequence, and the record is
still kept, because refusing it would lose evidence that did arrive) and appends accepted
records to the tenant's evidence ledger. A record about a plan never assigned to the
agent's zone advances its sequence but is not recorded: it is listed in `rejected` with the
reason, so a compromised agent cannot write evidence about work it was never given. The
server, not the message, names the control a record is about (the one the plan was
dispatched for) and who sent it (`triggered_by: agent:<id>`). Gaps an agent reports are stored and shown in
fleet health: a hole in the evidence is said where the evidence is.

## Storage

Tables in both schema files, byte-identical apart from headers: agents (`fl_agent`),
enrolment tokens (`fl_token`, the token's digest only), queued and claimed
assignments (`fl_assignment`), and reported gaps (`fl_gap`). VARCHAR/TEXT/INTEGER/REAL
only; timestamps as ISO-8601 text.

## The daemon

The agent side of this contract is `prama-agent`: `enrol` calls `POST /fleet/enrol`, and `run`
loops against `/fleet/hello` and `/fleet/report`. Operating it is
[the agent guide](../agent/README.md).
