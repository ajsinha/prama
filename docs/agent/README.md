<img src="../assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

*Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.*

---

# The Prama agent

The agent is a daemon that runs on a machine **beside the data**: inside the customer's
network, holding the customer's credentials, reaching sources the Prama server cannot. It
asks the server for the work its zone may do, runs it locally, judges the result with the
same code the server would use, redacts what its zone may not send, and reports
**findings, never data**.

It is its own package, `prama-agent`, and it is independent of the server:

* it depends on `prama-kernel` (the plan model, judge, evidence record, residency policy
  and spool it shares with the server — one copy, so a verdict judged here is the verdict
  the server would give) and on `prama-sdk` (the only way it talks to the server);
* it never imports the server, and the server never imports it. The server's build
  (`tests/architecture/test_packages_standalone.py`) fails otherwise: it runs a full daemon
  cycle in an interpreter where the server cannot be imported, and builds the agent's wheel
  to check it carries nothing else and requires nothing else;
* it always **calls out**. The server never calls in, so installing it needs no inbound
  firewall rule, no open port in a secure zone, no VPN and no jump host.

The wire contract between the two halves is [the agent fleet over HTTP](../design/agent-fleet-http.md).

## Installing

```bash
python3 -m venv /opt/prama-agent
/opt/prama-agent/bin/pip install prama-agent                # SQLite sources; nothing of the server
/opt/prama-agent/bin/pip install 'prama-agent[duckdb]'      # DuckDB sources
/opt/prama-agent/bin/pip install 'prama-agent[postgres]'    # PostgreSQL sources (psycopg 3)
```

Python 3.11 or newer. A source naming an engine whose driver is not installed is refused
**at start**, with the command that installs it — not at three in the morning on the first
assignment.

A dedicated, unprivileged user is the right owner:

```bash
sudo useradd --system --home /var/lib/prama-agent --shell /usr/sbin/nologin prama-agent
sudo install -d -o prama-agent -g prama-agent -m 0700 /var/lib/prama-agent
sudo install -d -o root -g prama-agent -m 0750 /etc/prama-agent
```

## Enrolling

An administrator issues a **one-time enrolment token** for a zone on the server
(`POST /api/v1/fleet/tokens`). The zone is fixed there; an agent never chooses its own.
On the agent's machine, redeem it once:

```bash
sudo -u prama-agent PRAMA_AGENT_TOKEN=… \
  /opt/prama-agent/bin/prama-agent enrol \
    --server https://prama.example.com --name eu-01 --state /var/lib/prama-agent \
    --config /etc/prama-agent/agent.yaml
```

`--token` works too; the environment variable keeps the token out of shell history.
`--config` is optional and lets the enrolment carry the capabilities the configuration
implies. The answer — the agent's id, its zone, and its **key**, which the server shows
once and does not keep — is written to `identity.json` in the state directory with mode
0600, in a directory with mode 0700. Whoever can read that file can sign findings as this
agent; back it up as you would a private key.

Enrolling again over an existing identity is refused unless `--force` says so; the old
agent should then be revoked on the server.

## `agent.yaml`

```yaml
server:
  url: https://prama.example.com        # required
  ca_bundle: /etc/ssl/certs/corp-ca.pem # optional: verify the server with this CA
  insecure: false                       # permit plain http:// to another machine (don't)
  timeout_seconds: 30

state_dir: /var/lib/prama-agent         # required: identity.json, spool.json, contact.json

sources:                                # required: what this agent may read, by binding name
  warehouse:                            # the binding name assignments use
    engine: sqlite                      # sqlite | duckdb | postgres (postgresql is accepted)
    path: /srv/data/warehouse.db
  lake:
    engine: duckdb
    path: /srv/data/lake.duckdb
    datasets: [positions, prices]       # optional: datasets reachable through this source
  ledger:
    engine: postgres
    dsn: host=db.internal dbname=ledger user=prama_ro   # no password in it
    password_env: LEDGER_PASSWORD       # the variable that holds the password
  risk:
    engine: postgres
    dsn_env: RISK_DSN                   # or the whole DSN from the environment

residency:                              # required: what may leave this machine
  samples: mask                         # withhold | fingerprint | mask | send
  may_send: [trade_id, ccy]             # under mask: columns that may travel in clear
  never_send: [account_id]              # never in clear, whatever else is said
  max_sample_rows: 50
  investigate_at: the EU DQ workbench   # where to look when samples were withheld
  # zone: eu-frankfurt                  # optional; must equal the enrolled zone

poll:
  min_seconds: 5                        # the server's poll_after_seconds, bounded by these
  max_seconds: 300
  backoff_initial_seconds: 5            # when the server cannot be reached: doubling,
  backoff_max_seconds: 600              # capped here, jittered into the upper half

spool:
  capacity: 50000                       # findings held while the server is away
  batch_size: 500                       # findings per report

logging:
  level: INFO
  format: json                          # json | text, to stderr

# delegates:                            # optional: Python DQ delegates installed here,
#   paths: [/opt/prama-agent/delegates] # as the server's own `delegates:` section
```

Relative paths resolve against the directory of `agent.yaml`, and `$VARIABLES` in paths
expand. The whole file is validated at start and **every** problem is reported together.

**No credential is ever written in it.** A `password:`, `secret:`, `token:` or `key:` under a
source is refused, and so is a DSN carrying a password (`postgresql://user:pw@host/db`, or
`password=` in a keyword DSN). Name the environment variable instead (`password_env`,
`dsn_env`); it is read at each use, so a rotated password needs a restart of nothing but the
service's environment. Plain `http://` to anything but this machine is refused unless
`server.insecure: true` says, knowingly, that the network is trusted.

**Binding.** An assignment names a binding; the agent runs it on the source of that name,
or on a source whose `datasets` lists the assignment's dataset. It never guesses: an
assignment for a binding this agent does not have becomes an *error finding*, reported to
the server, rather than a query run against whichever database happened to be there.

**Capabilities are derived, never typed.** The engines the agent advertises are those its
sources use; it is confined to datasets only if every source lists them; the delegates it
advertises are those its `delegates:` configuration admitted. An agent claiming what it
cannot do would be handed work it can only fail.

## Running

```bash
prama-agent run --config /etc/prama-agent/agent.yaml          # until stopped
prama-agent run --config /etc/prama-agent/agent.yaml --once   # drain what is queued now, then exit
prama-agent status --config /etc/prama-agent/agent.yaml       # [--json]
```

Each cycle is: **hello** (announce, and be handed the zone's work) → **run** each
assignment against the local source, judged with the plan's own threshold → **redact**
under the residency policy → **spool** the finding durably → **report** until the spool is
empty → **wait** `poll_after_seconds`, bounded by `poll:`.

* **The server is unreachable.** Findings stay in the spool (`spool.json`, written whole and
  moved into place, so it survives the daemon being killed), and the daemon retries with
  exponential backoff and jitter. Delivery is at-least-once; the server deduplicates by
  sequence, and the spool is hash-chained, so a finding lost in between is detectable. If
  the spool reaches `spool.capacity`, the *oldest* findings are dropped and the drop is
  recorded as a numbered **gap** that is reported to the server in the same channel as the
  evidence.
* **SIGTERM or SIGINT.** The assignment in hand finishes, what is spooled is delivered if
  the server answers, and the daemon exits 0. Assignments it had been handed and not
  started are not reported; the server's claim on them lapses and they return to the zone's
  queue.
* **A permanent refusal** (the agent was revoked, or its signature does not verify). The
  daemon exits **3** and records the refusal in `contact.json`; it will not start again
  until re-enrolled. A temporary refusal is backed off like an outage.

`status` prints the identity (never the key), zone, server, sources (never a credential),
the residency policy in words, how many findings are waiting, any gaps, and when the server
last answered. It exits 3 if the agent has been refused.

### As a systemd service

```ini
# /etc/systemd/system/prama-agent.service
[Unit]
Description=Prama agent (runs data quality controls beside the data)
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=prama-agent
Group=prama-agent
ExecStart=/opt/prama-agent/bin/prama-agent run --config /etc/prama-agent/agent.yaml
# Credentials by reference: LEDGER_PASSWORD=…, RISK_DSN=…, readable by root only.
EnvironmentFile=/etc/prama-agent/agent.env
Restart=on-failure
RestartSec=10
# Exit 3 is a permanent refusal: restarting a revoked agent only generates load.
RestartPreventExitStatus=3
# SIGTERM lets the assignment in hand finish; give a long control time to.
KillSignal=SIGTERM
TimeoutStopSec=300
# Hardening. The agent reads its sources and writes only its state directory.
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
ReadWritePaths=/var/lib/prama-agent
UMask=0077

[Install]
WantedBy=multi-user.target
```

```bash
sudo install -o root -g root -m 0600 agent.env /etc/prama-agent/agent.env
sudo systemctl daemon-reload && sudo systemctl enable --now prama-agent
journalctl -u prama-agent -f          # structured logs, one JSON object per line
```

## What leaves the machine, and what never does

**Leaves, always** — facts *about* the data, none of the data:

* the agent's id, version, capabilities (engines, datasets, delegates) and how many findings
  it holds;
* for each finding: the plan id and control id, dataset and binding names, the verdict,
  the metrics (row counts, violating counts, ratios), timings, the sample *count*, a hash
  linking it to the previous finding, and — for a source that failed — the error message;
* gaps: which sequence numbers were dropped, when, and why;
* the residency policy as applied, in words, so the server records *why* a finding has no
  samples rather than inferring it.

**Leaves only as the residency policy says** — failing rows. Under `withhold` nothing about
them leaves but their count, and the finding says they were withheld and where to
investigate. Under `fingerprint`, `mask` or `send` the finding carries a digest naming the
sample set; the rows themselves stay on this machine (`Agent.local_samples`) for an
investigator in the zone. A withheld sample is recorded distinctly from a control that had
none; why that distinction matters is [corpus/22 §3](../corpus/22-distributed-execution.md#3-what-crosses-the-boundary).

**Never leaves:**

* credentials, DSNs and passwords — they are read from the environment on this machine
  and are not in any message;
* the agent's key — it signs each message (HMAC-SHA256 over the message) and is never sent;
* raw scans, query results, and any row the policy did not permit.

The agent executes SQL the server compiled — it never compiles its own, because two
compilers is how one control comes to mean two things — and every source is opened
**read-only by construction** (SQLite `mode=ro`, DuckDB `read_only=True`, a read-only
PostgreSQL session), so a query cannot write through it whoever wrote the query.

## How it talks to the server

The daemon talks to the server only through a `FleetLink` with three calls (`enrol`,
`hello`, `report`), implemented by `SdkFleetLink` over the SDK's `client.fleet` namespace,
which calls the server's fleet API. With a `prama-sdk` that has no `client.fleet`, `enrol`
and `run` stop at start and say so (exit 1), because that is an installation problem. Against
a server that does not serve the fleet routes (an older one), the daemon treats the missing
route like an outage: it keeps its findings, backs off and retries rather than exiting.

How this daemon, the kernel it shares with the server, and the server's coordinator fit
together is drawn in [architecture/agents-and-fleet.md](../architecture/agents-and-fleet.md);
why the agent is built this way (outbound-only, findings not data, a terminal refusal) is
[corpus/22](../corpus/22-distributed-execution.md).
