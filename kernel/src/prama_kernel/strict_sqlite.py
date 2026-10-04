"""SQLite that refuses a column it cannot find, instead of inventing a string.

SQLite reads a double-quoted identifier it cannot resolve as a **string
literal**, for MySQL compatibility. A control compiled to
``"notionall" IS NOT NULL`` (one letter too many) therefore tests the constant
``'notionall'``, which is never null, and passes every row without reading the
column. The same control is an error on DuckDB and PostgreSQL. QA finding Q-08.

Prama turned this off for its own database and nowhere else, so every control
over a SQLite *source* (the server's connectors, the agent beside the data)
could still pass a typo. Every SQLite connection that runs a control is opened
through :func:`connect` now.

Turning it off needs ``Connection.setconfig``, which arrived in Python 3.12.
An interpreter without it gets a refusal, not a connection that quietly keeps
the old behaviour: a control that cannot fail is worth nothing, and a best
effort that silently does not happen is how this defect survived the first fix.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from prama_kernel.errors import ConfigError

__all__ = ["connect", "strict"]


def strict(connection: sqlite3.Connection) -> sqlite3.Connection:
    """Switch off double-quoted string literals on *connection*, or refuse it."""
    setconfig = getattr(connection, "setconfig", None)
    dml = getattr(sqlite3, "SQLITE_DBCONFIG_DQS_DML", None)
    ddl = getattr(sqlite3, "SQLITE_DBCONFIG_DQS_DDL", None)
    if setconfig is None or dml is None or ddl is None:
        connection.close()
        raise ConfigError(
            "this Python cannot make SQLite refuse an unknown column",
            remedy=(
                "Use Python 3.12 or newer (Prama pins 3.13). Without it a control on "
                "a misspelled column reads it as a string and passes every row."
            ),
        )
    setconfig(dml, False)
    setconfig(ddl, False)
    return connection


def connect(database: str, **options: Any) -> sqlite3.Connection:
    """``sqlite3.connect``, strict: an unknown double-quoted identifier is an error."""
    return strict(sqlite3.connect(database, **options))
