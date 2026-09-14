"""Seed the round-4 fixture for con_sql_pg.py / con_jdbc.py against the SQL-connector's
own dedicated PostgreSQL instance (127.0.0.1:55433, container prama-qa-pg).

Round 3's own log records this container as "already running" with a `positions` table
pre-seeded; that seeding was never captured in a checked-in script (the same
never-saved-back pattern round 3's README documents for several harness scripts). The
container backing 55433 was recreated this morning (docker inspect: StartedAt
2026-09-13T10:10:34Z, a fresh anonymous volume), so round 3's fixture data is gone and
must be reconstructed from what the harness scripts and the catalogue's own Precondition
text require:
  - CON-094's own Precondition: "a table of 25,000 rows"
  - CON-099's requirement: `SELECT *` on the table yields columns in the order
    (id, ccy, amount) -- see round 3's own recorded Observed text
This is environment setup only -- no src/, tests/, schema/, config/ or catalogue file
is touched, and no assertion here is tuned to any single case's outcome.
"""
import asyncio
import asyncpg

DSN = "postgresql://prama:prama@127.0.0.1:55433/prama"

async def main():
    conn = await asyncpg.connect(DSN)
    await conn.execute("SET default_transaction_read_only = off")
    await conn.execute("DROP TABLE IF EXISTS positions")
    await conn.execute("CREATE TABLE positions (id integer, ccy varchar(3), amount numeric(18,2))")
    await conn.execute(
        "INSERT INTO positions (id, ccy, amount) "
        "SELECT n, (ARRAY['USD','GBP','EUR','JPY','CHF'])[1 + (n % 5)], (n * 1.11)::numeric(18,2) "
        "FROM generate_series(1, 25000) n"
    )
    n = await conn.fetchval("SELECT count(*) FROM positions")
    print("positions rows:", n)
    await conn.close()

asyncio.run(main())
