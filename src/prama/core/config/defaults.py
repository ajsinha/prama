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
        # Off in development only because a developer on http://localhost would
        # otherwise never receive the cookie at all and would spend an afternoon
        # on it. Any real deployment sets it true.
        "cookies_https_only": True,
    },
    "tenancy": {
        # A single-tenant deployment names its one tenant here and nobody has to
        # sign in to look at a read-only page. Empty means multi-tenant, and an
        # unauthenticated request is then refused rather than guessed at.
        "default_tenant": "",
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
    },
}
