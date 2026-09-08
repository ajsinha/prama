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
        "api_key_hash_rounds": 210000,
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
        "queue": {
            "max_bytes": "256mb",
            "max_items": 100000,
            "offer_timeout": "5s",
        },
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
        ],
        "disabled": [],
    },
}
