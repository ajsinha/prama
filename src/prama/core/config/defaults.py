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
        "host": "127.0.0.1",
        "port": 5900,
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
    "scheduler": {
        # Off unless configured: a scheduler that ran against a default source
        # would produce evidence nobody asked for about data nobody named.
        "enabled": False,
        "interval": "60s",
        # The data the controls run against: a local .duckdb or .sqlite file.
        "against": "",
        "dialect": "duckdb",
    },
    "llm": {
        # Providers and profiles are data (the Models page, `prama llm`); this
        # is deployment policy only. Offline builds only self-hosted providers
        # on this host or a private network, by address.
        "offline": False,
        # Requests per minute per principal through /api/v1/llm, per server.
        "per_principal_rpm": 60,
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
        "entry_point_groups": [
            "prama.connectors",
            "prama.backends",
            "prama.monitors",
            "prama.notifiers",
            "prama.scorers",
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
