"""Shared SQL-engine runners for the round-4 language harnesses.

Mirrors the pattern in tests/backend/conftest.py: in-process SQLite and
DuckDB always available; PostgreSQL joins when PRAMA_TEST_POSTGRES_DSN names
a live server. Kept separate from the pytest fixtures because these scripts
run standalone, outside pytest.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""
from __future__ import annotations
import os
import sqlite3

from prama.connect.sources.query import register_regexp

DSN = os.environ.get("PRAMA_TEST_POSTGRES_DSN", "")

_sqlite_con = None
_duckdb_con = None


def sqlite_conn():
    global _sqlite_con
    if _sqlite_con is None:
        _sqlite_con = sqlite3.connect(":memory:")
        register_regexp(_sqlite_con)
    return _sqlite_con


def sqlite_scalar(expr_sql: str):
    cur = sqlite_conn().execute(f"SELECT {expr_sql}")
    row = cur.fetchone()
    return row[0] if row else None


def duckdb_conn():
    global _duckdb_con
    if _duckdb_con is None:
        import duckdb
        _duckdb_con = duckdb.connect()
    return _duckdb_con


def duckdb_scalar(expr_sql: str):
    global _duckdb_con
    try:
        return duckdb_conn().sql(f"SELECT {expr_sql}").fetchone()[0]
    except Exception:
        # A failed statement can leave the connection's transaction aborted;
        # reconnect so later, unrelated probes are not collateral damage.
        try:
            _duckdb_con.close()
        except Exception:
            pass
        _duckdb_con = None
        raise


_pg_conn = None


def postgres_available() -> bool:
    return bool(DSN)


def postgres_scalar(expr_sql: str):
    """Synchronous wrapper over asyncpg for a single scalar query."""
    import asyncio
    import asyncpg

    async def _run():
        con = await asyncpg.connect(DSN)
        try:
            return await con.fetchval(f"SELECT {expr_sql}")
        finally:
            await con.close()

    return asyncio.new_event_loop().run_until_complete(_run())
