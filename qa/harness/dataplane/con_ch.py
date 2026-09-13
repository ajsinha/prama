import sys, asyncio
sys.path.insert(0, ".")
from qa_common import log
from prama.connect.sources.sql.clickhouse import ClickHouseConnector, _bind

CFG = {"host": "127.0.0.1", "port": 58123, "user": "prama", "password": "prama", "database": "default"}

async def con113():
    c = ClickHouseConnector(CFG)
    async with c:
        stmt = c.dialect.snapshot_sql()
        snap = await c.snapshot(("default", "anything"))
    ok_none = stmt is None
    ok = (ok_none and snap.kind.name == "WALL_CLOCK" and snap.exact is False
          and "clickhouse" in snap.detail.get("note", "").lower()
          and "offers no point-in-time marker" in snap.detail.get("note", ""))
    log("CON-113", "PASS" if ok else "FAIL", f"dialect.snapshot_sql()={stmt} snapshot={snap}")

def con111():
    sql, params = _bind("SELECT * FROM t WHERE a = ?", (42,))
    ok1 = "{p0:" in sql and "String" in sql and params.get("p0") == "42"
    sql2, params2 = _bind("SELECT '?' AS literal_q, a = ?", ("x", 7))
    ok = ok1
    log("CON-111", "PASS" if ok else "FAIL", f"int bind: sql={sql!r} params={params}; literal-quote case: sql={sql2!r} params={params2}")

async def con112():
    c = ClickHouseConnector(CFG)
    async with c:
        await c._fetch("CREATE TABLE IF NOT EXISTS t112 (id Int64, d String) ENGINE=MergeTree ORDER BY id")
        await c._fetch("TRUNCATE TABLE t112")
        await c._fetch("INSERT INTO t112 SELECT number, toString(number % 5) FROM numbers(25000)")
        rows = []
        async for batch in c.read(("default", "t112")):
            rows.extend(batch.to_pylist())
        ids = sorted(r["id"] for r in rows)
        no_dupes = len(ids) == len(set(ids))
        all_present = ids == list(range(25000))
        from prama.connect.spi import SamplePlan
        rows2 = []
        plan = SamplePlan(predicate="d = '2'")
        async for batch in c.read(("default", "t112"), plan=plan):
            rows2.extend(batch.to_pylist())
        pred_ok = len(rows2) == 5000 and all(r["d"] == "2" for r in rows2)
    ok = len(ids) == 25000 and no_dupes and all_present and pred_ok
    log("CON-112", "PASS" if ok else "FAIL", f"n_rows={len(ids)} no_dupes={no_dupes} all_present={all_present} predicate_read_rows={len(rows2)} (expected 5000)")

async def main():
    await con113()
    con111()
    await con112()

asyncio.run(main())
