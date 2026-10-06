"""Built-in defaults.

These are the values Prama runs on when no configuration file exists at all,
which makes ``pytest`` and ``prama db init`` work in a fresh clone without
ceremony. Every one of them is safe: SQLite in a local file, no network
listeners, no external calls, and every secret empty.

The tracked ``config/application.yaml`` restates these with commentary; this
mapping is the authority and the file is documentation. Where the two could
drift, a test compares them.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

DEFAULTS: dict[str, Any] = {
    "app": {
        "name": "Prama",
        "environment": "development",
        "instance_id": "${HOSTNAME:local}",
    },
    "logging": {
        "level": "INFO",
        "format": "text",
    },
    "security": {
        # Empty on purpose: a fresh clone must refuse to serve rather than run
        # on a public secret. Put the real value in application.local.yaml.
        "session_secret": "",
        # On by default, which is what a real deployment needs: a session
        # cookie that can travel over plain HTTP is one that can be read off
        # the wire. A developer on http://localhost will not receive it at all
        # and should turn it off in application.local.yaml rather than here.
        #
        # The comment used to say it was "off in development" while the value
        # beside it was True, which is the most misleading possible pairing —
        # a reader checking whether the default is safe is told it is not
        # (QA finding CFG-014).
        "cookies_https_only": True,
        # On an installation with nobody in it, create `admin` with the
        # password `prama-dev-admin` at startup (prama.security.bootstrap).
        # Every page carries a banner until it is changed.
        "bootstrap_admin": True,
        # Outside development the server refuses to start while that default
        # password is in force. True overrides the refusal, knowingly.
        "allow_default_admin_password": False,
    },
    "tenancy": {
        # A single-tenant deployment names its one tenant here and nobody has to
        # sign in to look at a read-only page. Empty means multi-tenant, and an
        # unauthenticated request is then refused rather than guessed at.
        "default_tenant": "",
    },
    "server": {
        # The console and the API share one listener. 5900 is Prama's port;
        # `prama serve`, `run_prama_web.py`, the image and the chart all read
        # it from here rather than restating it.
        # Every interface, so the console is reachable from another machine on the
        # network (a phone, a colleague's browser). 127.0.0.1 keeps it on this one.
        "host": "0.0.0.0",
        "port": 5900,
    },
    "agents": {
        # Steward agents run their goals inside `prama serve`. They exist only
        # when an administrator creates one, so on by default costs nothing.
        "enabled": True,
        "interval": "60s",
    },
    "secrets": {
        # Where file:// references are read from; empty means as written.
        "file_root": "",
        # HashiCorp Vault (KV v2) for vault:// references. Unset, a vault://
        # reference fails saying what to set. The token is itself a
        # credential: token_ref is a reference to it (env://VAULT_TOKEN),
        # never the token.
        "vault": {
            "address": "",
            "token_ref": "",
            "namespace": "",
            "ca_file": "",
            "region": "",
            "timeout_seconds": 10,
        },
    },
    "fleet": {
        # Agents beside the data (docs/design/agent-fleet-http.md). Each agent's
        # signing key is derived from this secret; empty falls back to
        # security.session_secret. Empty on purpose, like that one: set it in
        # application.local.yaml, never in a tracked file. Changing it
        # invalidates every enrolled agent's key.
        "secret": "",
        # How long an enrolment token is good for, by default.
        "token_hours": 1,
        # How long an agent holds a claimed assignment before it returns to
        # the queue for another agent.
        "lease_seconds": 900,
        # What an agent is told to wait between calls.
        "poll_seconds": 30,
        # Silence after which fleet health names an agent as stale.
        "stale_minutes": 15,
    },
    "delegates": {
        # DQ delegates: Python checks named from PQL (`USING DELEGATE 'x'`).
        # The server and every agent read their own copy of this section, so
        # each host runs exactly the delegates it is given.
        "enabled": True,
        # Directories of delegate files, vetted before import.
        "paths": [],
        # Also load distributions advertising the `prama.delegates` entry point.
        "entry_points": True,
        "disabled": [],
        # Run each delegate in a resource-limited subprocess.
        "sandbox": True,
        "timeout": 120,
        "memory_mb": 2048,
        # A larger dataset is refused, never truncated.
        "max_rows": 5000000,
        # Rows read from the engine's cursor at a time and streamed to the
        # delegate, so a large table is never held whole.
        "batch_rows": 10000,
        # Approved console uploads are written here, by content hash, to run.
        "upload_dir": "data/delegates",
    },
    "codeintake": {
        # Where received code is extracted while it is read; deleted after.
        "workdir": "data/code",
        # Seconds the sandboxed reader may take for one snapshot.
        "timeout": 300,
        "git": {
            # Empty: any public host. A list: only these hosts.
            "allowed_hosts": [],
        },
    },
    "observability": {
        # Prama's own operational metrics at GET /metrics, Prometheus format.
        # A token, if one is wanted, goes in the untracked local configuration.
        "metrics": {"enabled": True, "token": ""},
        # Spans to an OpenTelemetry collector: none or otlp (the `otel` extra).
        "tracing": {"exporter": "none", "endpoint": "", "service_name": "prama", "region": ""},
        # OpenLineage run events to a collector (Marquez, say): off without a URL.
        "openlineage": {"url": "", "namespace": "prama", "region": "", "timeout": 10},
    },
    "evidence": {
        "anchor": {
            # A witness outside Prama for the chain head after each run: none
            # or rfc3161 (a time-stamp authority). Off by default, because it
            # sends a digest to a third party and that is the operator's call.
            "kind": "none",
            # The authority's URL, e.g. https://freetsa.org/tsr.
            "url": "",
            # Where the authority is, for the residency gate.
            "region": "",
            # Seconds to wait for the authority.
            "timeout": 30,
        },
    },
    "scheduler": {
        # Off unless configured: a scheduler that ran against a default source
        # would produce evidence nobody asked for about data nobody named.
        "enabled": False,
        "interval": "60s",
        # The data the controls run against: a local .duckdb or .sqlite file.
        "against": "",
        "dialect": "duckdb",
    },
    "alerts": {
        # Off by default, so nothing is sent until an operator decides where
        # alerts go. On, a failing run alerts the dataset's owner, steward or
        # custodian (by the fault), once per incident, and a pass resolves it.
        "enabled": False,
        # Which notifier serves each role: log | webhook | email, or a
        # notifier a distribution adds on the prama.notifiers entry point.
        # `log` needs nothing configured, so turning alerts on is observable
        # before a webhook or a mail relay exists.
        "channels": {"owner": "log", "steward": "log", "custodian": "log"},
        # Notifier key -> where it delivers, for the residency gate. An alert
        # quotes failing values, so a channel outside the tenant's residency
        # is withheld rather than sent.
        "channel_regions": {},
        # An open incident is not announced again within this period unless
        # it worsens; the record of what was sent is in the database, so the
        # period holds across a restart and across servers.
        "quiet_period": "6h",
        # The hour (UTC, 0-23) after which the scheduler's tick sends the day's
        # digest of what did not need waking anybody. Needs the scheduler on.
        "digest_hour": 9,
        "webhook": {
            # The receiver. JSON is POSTed: subject, body, recipients, alert.
            "url": "",
            # A secret reference (env://..., file://..., vault://...), never
            # the secret: the body is signed with HMAC-SHA256 in
            # X-Prama-Signature when it is set.
            "secret_ref": "",
            "timeout": 10,
        },
        "email": {
            "host": "",
            "port": 587,
            "starttls": True,
            "sender": "",
            "username": "",
            # A secret reference for the relay password, never the password.
            "password_ref": "",
            "timeout": 30,
        },
    },
    "runs": {
        # Directories a run requested over the API may read a registered
        # connection's files from. Empty: no such run opens any file, which is
        # the safe default for a server whose operator has not decided. Must
        # not contain Prama's own database; a run refuses if it does.
        "roots": [],
    },
    "llm": {
        # Providers and profiles are data (the Models page, `prama llm`); this
        # is deployment policy only. Offline builds only self-hosted providers
        # on this host or a private network, by address.
        "offline": False,
        # Requests per minute per principal through /api/v1/llm, per server.
        "per_principal_rpm": 60,
        "audit": {
            # What of each model exchange is kept, beside the hashes the call
            # ledger always keeps: none, redacted (secrets, cards, IBANs and
            # emails removed) or full. Kept for payload_retention_days, then
            # blanked; the ledger's chain still verifies.
            "payloads": "none",
            "payload_retention_days": 30,
        },
        "eval": {
            # When on, a profile or template version becomes current only after
            # an evaluation run of that exact version passed.
            "gate_activation": False,
        },
    },
    "web": {
        "enabled": True,
        "preview": {
            # Empty means the studio can check and compile a control but not
            # run one, and it says so rather than showing an empty result that
            # reads as clean.
            "source": "",
            "dialect": "duckdb",
            "max_rows": 1_000_000,
            "backtest_days": 30,
        },
    },
    "database": {
        "dialect": "sqlite",
        "sqlite": {
            "path": "data/prama.db",
            "journal_mode": "WAL",
            "synchronous": "NORMAL",
            "busy_timeout": "5s",
            "foreign_keys": True,
        },
        "postgres": {
            "host": "localhost",
            "port": 5432,
            "database": "prama",
            "user": "prama",
            "password": "",
            "sslmode": "prefer",
            "application_name": "prama",
            "schema": "public",
            "statement_timeout": "60s",
        },
        "pool": {
            "size": 10,
            "max_overflow": 20,
            "timeout": "30s",
            "recycle": "30m",
            "pre_ping": True,
        },
        "schema_dir": "schema",
        "verify_on_start": True,
        "echo": False,
    },
    "concurrency": {
        "supervisor": {
            "shutdown_grace": "30s",
        },
        "lease": {
            "provider": "database",
            "ttl": "30s",
            "renew_interval": "10s",
            "clock_skew_allowance": "2s",
        },
    },
    "plugins": {
        # Every group here has a loader in prama.plugins.LOADERS, called once
        # at start by the CLI and the server alike, and
        # tests/architecture/test_plugin_groups.py fails the build on a group
        # that has none. Two groups were once listed and read by nothing, and
        # are gone because there is no seam for a plugin to fill:
        # prama.backends (a compile dialect must also be in the function
        # catalogue's engines and pass the conformance corpus, so an engine
        # ships in-tree) and prama.scorers (scoring methods are closed enums,
        # so a score always names the arithmetic that produced it).
        "entry_point_groups": [
            # Source connectors, registered beside the shipped ones; a
            # distribution cannot take a shipped connector's key.
            "prama.connectors",
            # Monitor detectors (prama.monitor.detect.Detector), by name.
            "prama.monitors",
            # Alert channels (prama.alert.notify.Notifier), named in
            # alerts.channels and configured under alerts.<key>.
            "prama.notifiers",
            # Validators arrive here. A distribution advertising one is checked
            # for purity before it is usable, and its implementation hash is
            # folded into the plan id of every control that names it.
            "prama.validators",
        ],
        # Entry points an operator has switched off by name. Present in the
        # shipped YAML since plugins existed, absent from here, and read by
        # nothing — because the loader itself had no caller (QA finding
        # CFG-036). This mapping is the authority and the file is
        # documentation, so a key that lives only in the file is a setting
        # nobody can rely on.
        "disabled": [],
    },
}
