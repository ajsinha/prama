import asyncio, sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from prama.db import Database
from prama.core.config import ConfigurationBuilder
from prama.core.config.defaults import DEFAULTS

def line(id_, result, observed):
    print(f"{id_}: {result} :: {observed}")

async def main():
    # point at a port nothing is listening on, to simulate the database being unreachable
    cfg = (
        ConfigurationBuilder()
        .with_defaults(DEFAULTS)
        .with_mapping({
            "database": {
                "dialect": "postgres",
                "postgres": {"host": "127.0.0.1", "port": 55499, "database": "prama", "user": "prama", "password": "prama"},
                "schema_dir": "/home/ashutosh/PycharmProjects/prama/schema",
            },
            "security": {"session_secret": "x", "cookies_https_only": False},
        }, name="test")
        .build()
    )
    db = Database.from_config(cfg)
    db._started = True  # bypass start() gate to test health() directly against an unreachable db
    try:
        h = await db.health()
        line("OPS-010", "FAIL", f"health() against unreachable db did not raise: {h!r}")
    except Exception as e:
        line("OPS-010", "PASS", f"health() against unreachable postgres (wrong port) raised as expected: {type(e).__name__}: {str(e)[:150]}")

asyncio.run(main())
