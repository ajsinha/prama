<img src="../assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

> ***pramā*** (Sanskrit **प्रमा**) — *valid knowledge: a cognition that is both true and arrived at
> by a reliable means*. Its companion ***pramāṇa*** (प्रमाण) is *the instrument by which valid
> knowledge is obtained*. Prama is that instrument for an organisation's data — it does not decide
> what is true, it is how a belief about data becomes **justified**.
>
> **Declare it. Prove it. Trust it.**


---
# 22 — Distributed Execution: Prama Agents

Requirements: [`FR-EXE-020`](04-requirements-functional.md), `NFR-SCA`, `NFR-PRV`.
Architecture context: [06 §3.4, §6](06-architecture.md). Evidence: [06 §3.5](06-architecture.md).
Implementation: the protocol, residency, spool and signing in `prama_kernel.agent`; the server's
coordinator in `src/prama/agent/`; the daemon in `prama-agent`. How they fit:
[architecture/agents-and-fleet.md](../architecture/agents-and-fleet.md).

**Design stance.** One control plane cannot check an enterprise estate, and the reason is not
throughput. It is that the data is in three hundred places, behind firewalls, under different
regulators, in jurisdictions that forbid it leaving. A design that scales by adding servers to the
middle solves the easy problem. **An agent runs beside the data, does the work there, and sends
findings rather than data.**

---

## As built

The outbound-only customer-hosted worker is built as three pieces: the daemon
`prama-agent`; the protocol, capability matching, residency, spool and signing in
the shared kernel (`prama_kernel.agent`); and on the server `prama.agent.fleet`
(enrolment, keys, claimed assignments, the fleet API) with `prama.agent.assign`
(the server compiles every assignment). `prama.execute` holds the claim/lease
machinery, in-flight enforcement with dead-lettering, and the broker seam, on `prama.core.concurrency` (supervised task groups, byte-bounded queues and
leases), which everything must use: there are no bare threads in this codebase
and no unbounded queues.

The streaming path (`prama.execute.stream`, `inflight`, `transport` and the
`kafka` transport, verified against a live broker) and its rule, **commit after
enforcement, never before**, are described once, in
[06 §3.4.1](06-architecture.md#341-the-broker-seam-and-commit-ordering). The
daemon that runs beside the data is `prama-agent`
([operator's guide](../agent/README.md)); how its parts fit is
[architecture/agents-and-fleet.md](../architecture/agents-and-fleet.md).

**Not built:** §9's open questions are still open. The multi-node transport
throughput harness that would answer DEC-17's second half does not exist, and
nothing here has been run across more than one machine.

---

## 1. The four properties that matter

Everything else follows from these, and each is enforced somewhere specific rather than promised.

| Property | Why it decides adoption | Where it lives |
|---|---|---|
| **Outbound-only** | No inbound firewall rule, no port open in a secure zone, no VPN, no jump host — and no year-long conversation with network security | `prama_kernel.agent.protocol` |
| **Data stays home** | Residency, GDPR, and the fact that "findings" quietly containing a hundred failing rows has moved the data and called it something else | `prama_kernel.agent.residency` |
| **Survives an outage** | The estate goes unchecked precisely during the incident that took the network out, and that gap is where an auditor looks | `prama_kernel.agent.spool` |
| **Trust is verified, not assumed** | An agent runs on a machine the control plane cannot see, holding production credentials | `prama.agent.fleet` (enrolment, keys, revocation) |

---

## 2. Outbound-only, and what it costs

The agent always initiates. Four messages and no more, because every message is a thing to version,
secure and reason about:

```
agent ──── Hello ────────▶  who I am, what I can do, how much I can take
      ◀─── Receipt ──────   here is your work; call back in N seconds
agent ──── Report ───────▶  findings, and any gaps in them
      ◀─── Receipt ──────   accepted through sequence K
      ◀─── Refusal ─────    (or: stop, and here is why)
```

**What it costs.** Work reaches an agent when the agent next asks, so there is latency between
deciding and doing, and the control plane cannot make anything happen on demand. Both are stated
rather than hidden. "The control plane cannot reach into your network" is a property a bank pays
for, not a limitation it tolerates.

**A refusal is terminal.** A revoked agent stops rather than retrying, because an agent that has
been revoked and keeps calling is load and log noise for as long as somebody leaves it running. A
*suspension* is not terminal: the agent keeps working and spooling, because the reason for a
suspension is usually operational and losing a day of evidence to it would be a second problem.

---

## 3. What crosses the boundary

Three tiers. The boundaries between them are not configurable.

| Tier | Contents | Rule |
|---|---|---|
| **Always crosses** | Counts, verdicts, plan identities, hashes, timings | Facts *about* the data, containing none of it |
| **Crosses by declaration** | A digest naming the redacted sample set | Only under a declared policy, per zone. As built, the rows themselves never leave the agent under any disposition: only their count and digest do |
| **Never crosses** | Credentials, connection strings, raw scans | The agent holds the credential; the control plane holds a reference |

Sample disposition is one of four, declared per zone:

- **`SEND`** — rows travel as they are. Only where the control plane is inside the same trust and
  residency boundary as the data.
- **`MASK`** — an **allow-list** of columns travels in clear and everything else is masked. An
  allow-list because a deny-list is one new column away from leaking, and new columns appear without
  anybody telling the policy.
- **`FINGERPRINT`** — only a per-row hash travels, so the same bad row recurring is recognisable
  without the row being known.
- **`WITHHOLD`** — nothing travels, and the record says where to investigate instead.

**A withheld sample is not an absent sample.** If residency forbids samples, the evidence says so,
distinctly from a control that passed and had none to send. Conflating them sends an investigator
looking for rows that were never collected — and, worse, lets a zone that is silently dropping
everything look identical to a zone that is clean. Withholding is also not discarding: the rows stay
on the agent, where somebody inside the zone can still look at them.

---

## 4. Trust

Three questions the control plane cannot answer by assumption.

**Which agent is this?** Enrolment is a one-time token, issued by somebody with authority and
redeemed once for a credential. A replayable token is a credential that never expires, handed out
over whatever channel installed the agent. The registry keeps no key at all: as built, each agent's
key is derived on demand from the fleet secret (`HMAC-SHA256(fleet.secret, "agent:" + tenant + ":" +
agent_id)`), so a stolen registry yields no credentials. The fleet secret is then the thing whose theft
is an agent fleet, which is why it lives only in the untracked local configuration.

**Is it still trusted?** Identities are revocable, and a revoked agent's correctly-signed findings
are **rejected**. Verifying a signature and then accepting the finding anyway is how a revocation
list becomes decorative.

**What is it for?** An agent is enrolled into a zone, and work is assigned *by zone, never by
request*. A compromised agent in the reporting zone cannot obtain the trading estate's controls,
because what it receives is decided from its enrolment rather than from anything it said.

**Silence is reported.** An agent that has died and an agent whose datasets are all clean produce
the same absence of findings, and only one of them is a problem.

---

## 5. Version skew

Agents in a bank upgrade on the bank's schedule, measured in quarters. A control plane that assumed
its fleet matched its own version would send a plan half the fleet cannot execute and find out when
the runs failed — at night, in a zone nobody can log into.

So an agent declares what it supports — IR versions, engines, connectors, pushdown capabilities,
concurrency — in **the same vocabulary the connectors and backends already publish**, so a plan's
requirements and an agent's abilities are compared directly rather than through a translation nobody
maintains.

The important case is the negative one. A control no agent in a zone can run is reported as
**unassignable**, with every reason collected rather than the first — an agent short of three things
needs upgrading once, not three times. It is never silently skipped: silently skipped work is what
makes a coverage report a lie, green because nothing looked.

An agent that declares *no* pushdown capabilities is not second-guessed. The alternative is that
every agent in the fleet stops working the day the control plane learns a new capability name.

---

## 6. Surviving an outage

The agent spools findings locally and keeps running. Three properties make the spool trustworthy
rather than merely convenient.

**Durable and bounded.** Findings survive a restart — written whole and moved into place, because a
spool half-written by a process that died is a spool that will not load, turning one outage into a
permanent loss. A corrupt spool is a *gap*, not a crash: refusing to start would leave the estate
unchecked over exactly the kind of incident that corrupted it.

**Overflow drops the oldest, and records it.** Dropping the newest would be easier and would mean a
long outage hides the recent failures rather than the old ones — precisely backwards. The drop is
reported as a numbered gap in the same channel as the evidence, not only in a log nobody reads.

**Hash-chained per agent.** Each finding links to the one before, so the control plane can tell a
spool replayed intact from one that lost its middle.

**Delivery is at-least-once, and the ledger deduplicates.** An agent that sent a batch and heard
nothing must send it again; the same finding therefore arrives twice, and the second is recognised
by sequence and dropped. Exactly-once delivery over an unreliable network is a thing people claim
and nobody has. Saying at-least-once and deduplicating is the honest version.

---

## 7. What the agent does *not* do

Deliberate omissions, each one a place where a distributed system usually goes wrong.

| It does not | Because |
|---|---|
| Compile its own SQL | A second compiler in the estate is how one control comes to mean two things on two machines. The control plane sends the compiled query. |
| Re-derive a plan from a control | Same reason. It judges with the plan it was given, using the *shared* judging code, so an agent's verdict is the control plane's verdict. |
| Choose its own work | Assignment is by zone. See §4. |
| Hold credentials it does not need | It reads its sources' credentials from its own environment (`password_env`, `dsn_env`); the control plane never sees them. |
| Stop on a failed source | An agent that stopped on the first unreadable source would take the rest of its zone's controls down with it. A failure is an `error` verdict *with its reason*, and the next control runs. |

---

## 8. Topologies

| Topology | Agents | Typical buyer |
|---|---|---|
| **Single control plane, no agents** | — | Evaluation, small estates, one warehouse |
| **Zone agents** | One or more per residency or network zone | The ordinary enterprise shape |
| **Per-datacentre** | One per site, each with local sources | Banks with regional data centres |
| **Air-gapped agent** | Agent with no egress; evidence exported by hand as signed NDJSON | Central banks, defence |

The air-gapped case works because the evidence format is
[verifiable without Prama](19-implementation-roadmap.md): newline-delimited JSON with a documented
hash chain. An agent that can never reach the control plane still produces an audit trail somebody
can carry out on a disk and check.

---

## 9. Open questions

Honest, and not yet decided.

- **Transport.** The protocol is defined by its messages, not its wire format. What is built is plain
  HTTP polling ([the fleet contract](../design/agent-fleet-http.md)); long-poll, gRPC streaming and a
  queue-backed variant all fit the same four messages. Deciding on measured behaviour, not preference.
- **Assignment fairness across zones.** Work is queued per zone and taken by whichever agent asks.
  Two agents in one zone therefore share by arrival, which is fair enough for equal machines and
  wrong for unequal ones. A weighted claim is the likely answer and is not built.
- **Agent-side scheduling.** Cadence is currently decided centrally. An agent that lost contact for
  a day would keep running its last assignment set rather than adapting. Moving the cadence policy
  agent-side would fix that and would mean two places decide when things run, which is worse. Not
  yet resolved.
- **Key rotation.** Enrolment issues a key; nothing rotates it. Rotation without an inbound channel
  means the agent must ask, which is straightforward and not written.

---

<div align="center">
<img src="../assets/prama-mark.svg" width="30" alt=""/><br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.<br/>
See <a href="../../LICENSE">LICENSE</a> and <a href="../../NOTICE">NOTICE</a>. Third-party names and marks are the property of their respective owners.</sub>
</div>
