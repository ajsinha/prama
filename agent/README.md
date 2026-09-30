# prama-agent

The Prama agent: a daemon that runs on a machine beside the data, executes the
controls its zone is given against sources only it can reach, judges them with
the same code the server uses, redacts under the zone's residency policy, and
reports **findings, never data**. It always calls out; the server never calls in.

```bash
pip install prama-agent                 # prama-kernel, prama-sdk, PyYAML; nothing of the server
pip install 'prama-agent[duckdb]'       # DuckDB sources
pip install 'prama-agent[postgres]'     # PostgreSQL sources (psycopg 3)

prama-agent enrol --server https://prama.example.com --token … --name eu-01 --state /var/lib/prama-agent
prama-agent run --config /etc/prama-agent/agent.yaml
prama-agent status --config /etc/prama-agent/agent.yaml
```

It depends on `prama-kernel` (the deterministic code it shares with the server)
and `prama-sdk` (the only way it talks to the server), and never imports the
server; the server's build fails if it does.

The guide — `agent.yaml` reference, running under systemd, and exactly what
leaves the machine — is `docs/agent/README.md` in the Prama repository.

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential; see the LICENSE file in the Prama repository.
