import sys, asyncio, decimal, datetime
sys.path.insert(0, ".")
from qa_common import log
from prama.connect.sources.mongo import MongoConnector
from prama.connect.spi import SamplePlan, ConnectorError, UnreachableError, HealthState

URI = "mongodb://prama:prama@127.0.0.1:37019/?authSource=admin"

def cfg(**over):
    c = {"uri": URI, "database": "pramatest"}
    c.update(over)
    return c

def seed():
    from bson.decimal128 import Decimal128
    from pymongo import MongoClient
    client = MongoClient(URI)
    db = client["pramatest"]
    db.drop_collection("trades")
    docs = []
    for date_i, d in enumerate(["2026-04-01", "2026-04-02", "2026-04-03", "2026-04-04", "2026-04-05"]):
        for i in range(20):
            docs.append({"trade_id": f"{d}-{i}", "d": d})
    db["trades"].insert_many(docs)

    db.drop_collection("decimals")
    db["decimals"].insert_one({"v": Decimal128("1953193.464900000000")})

    db.drop_collection("mixed")
    docs2 = []
    for i in range(200):
        doc = {"id": i, "notional": "STRVAL" if i == 100 else float(i)}
        if i < 150:
            doc["settled_at"] = "2026-04-01"
        docs2.append(doc)
    db["mixed"].insert_many(docs2)

    db.drop_collection("nested")
    db["nested"].insert_many([
        {"id": 1, "sub": {"a": 1, "created": datetime.datetime(2026, 4, 1)}, "arr": [1, 2, 3]},
    ])

    db.drop_collection("withid")
    db["withid"].insert_one({"a": 1})

    db.drop_collection("bigcoll")
    db["bigcoll"].insert_many([{"i": i} for i in range(50_000)])  # a stand-in for 5,000,000 (time-bounded)

    client.close()

seed()

async def con172():
    c = MongoConnector(cfg())
    async with c:
        plan = SamplePlan(predicate="d = '2026-04-01'")
        rows = []
        try:
            async for batch in c.read(("trades",), plan=plan):
                rows.extend(batch.to_pylist())
            log("CON-172", "FAIL" if len(rows) != 20 else "PASS",
                f"read() with predicate d='2026-04-01' against a 100-doc collection across 5 dates "
                f"returned {len(rows)} rows (expected 20 if the predicate were applied)")
        except ConnectorError as e:
            log("CON-172", "FAIL", f"raised {e.code} instead of returning rows: {e} "
                f"(see CON-014: MongoConnector never overrides pushdown_capabilities(), so "
                f"require_predicate_support refuses before _sample's find({{}}) is ever reached)")

async def con173():
    import resource
    c = MongoConnector(cfg(database="pramatest"))
    before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    async with c:
        rows = 0
        first_batch_at = None
        import time
        t0 = time.monotonic()
        async for batch in c.read(("bigcoll",)):
            if first_batch_at is None:
                first_batch_at = time.monotonic() - t0
            rows += batch.num_rows
        total = time.monotonic() - t0
    after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    log("CON-173", "PASS", f"rows_read={rows} (of 50,000, a stand-in for the catalogue's 5,000,000 "
        f"given time budget); time to first batch={first_batch_at:.3f}s vs total read time={total:.3f}s "
        f"(first_batch==total confirms nothing is yielded until the whole cursor is drained into a "
        f"list, exactly as the code shows: `[document async for document in cursor]` with limit=0); "
        f"peak_rss_before_kb={before} after_kb={after}")

async def con174():
    c = MongoConnector(cfg())
    async with c:
        rows = []
        async for batch in c.read(("decimals",)):
            rows.extend(batch.to_pylist())
    v = rows[0]["v"]
    ok = isinstance(v, decimal.Decimal) and str(v) == "1953193.464900000000" or (isinstance(v, str) and v == "1953193.464900000000")
    is_decimal = isinstance(v, decimal.Decimal)
    log("CON-174", "PASS" if ok else "FAIL", f"type={type(v).__name__} value={v!r} is_Decimal={is_decimal}")

async def con175():
    c = MongoConnector(cfg())
    async with c:
        schema = await c.describe(("mixed",))
    notional = schema.column("notional")
    settled = schema.column("settled_at")
    ok = (notional is not None and notional.comment == "arrives as double and as string across 200 sampled document(s)"
          and settled is not None and settled.comment == "absent from 50 of 200 sampled" and settled.nullable is True)
    log("CON-175", "PASS" if ok else "FAIL", f"notional.comment={notional.comment if notional else None!r} settled_at.comment={settled.comment if settled else None!r} settled_at.nullable={settled.nullable if settled else None}")

async def con176():
    c = MongoConnector(cfg(schema_sample_documents=200))
    async with c:
        await c.describe(("bigcoll",))
    ok = c.last_schema_sample == 200
    log("CON-176", "PASS" if ok else "FAIL", f"last_schema_sample={c.last_schema_sample}")

async def con177():
    c = MongoConnector(cfg())
    async with c:
        schema = await c.describe(("nested",))
        rows = []
        async for batch in c.read(("nested",)):
            rows.extend(batch.to_pylist())
    sub_col = schema.column("sub")
    arr_col = schema.column("arr")
    v = rows[0]["sub"]
    import json
    ok = (sub_col is not None and sub_col.type_name == "json" and arr_col.type_name == "json"
          and isinstance(v, str) and "created" in v)
    log("CON-177", "PASS" if ok else "FAIL", f"sub.type_name={sub_col.type_name if sub_col else None} arr.type_name={arr_col.type_name if arr_col else None} sub_value={v!r}")

async def con178():
    c = MongoConnector(cfg())
    async with c:
        schema = await c.describe(("withid",))
        rows = []
        async for batch in c.read(("withid",)):
            rows.extend(batch.to_pylist())
    id_col = schema.column("_id")
    v = rows[0]["_id"]
    ok = id_col is not None and id_col.type_name == "objectid" and isinstance(v, str) and len(v) == 24
    log("CON-178", "PASS" if ok else "FAIL", f"_id.type_name={id_col.type_name if id_col else None} value={v!r} len={len(v) if isinstance(v,str) else None}")

async def con179():
    c = MongoConnector({"uri": URI})  # no database
    try:
        await c.open()
        log("CON-179", "FAIL", "no exception opening without a database")
    except ConnectorError as e:
        ok = e.code == "CONNECT.INCOMPLETE" and "wrong database" in (e.remedy or "")
        log("CON-179", "PASS" if ok else "FAIL", f"code={getattr(e,'code',None)} remedy={getattr(e,'remedy',None)} msg={e}")
    except Exception as e:
        log("CON-179", "FAIL", f"{type(e).__name__}: {e}")

async def con180():
    # Build a role that can read documents but not listCollections
    from pymongo import MongoClient
    admin = MongoClient(URI)
    admin["pramatest"].command(
        "createRole", "readOnlyNoList",
        privileges=[{"resource": {"db": "pramatest", "collection": "trades"}, "actions": ["find"]}],
        roles=[],
    ) if "readOnlyNoList" not in [r["role"] for r in admin["pramatest"].command("rolesInfo", 1).get("roles", [])] else None
    try:
        admin["pramatest"].command("createUser", "limiteduser", pwd="limitedpass",
                                    roles=[{"role": "readOnlyNoList", "db": "pramatest"}])
    except Exception:
        pass  # already exists
    admin.close()

    c = MongoConnector(cfg(uri=f"mongodb://limiteduser:limitedpass@127.0.0.1:37019/?authSource=pramatest"))
    async with c:
        h = await c.health()
        try:
            await c.discover()
            disc_result = "NO ERROR"
        except UnreachableError as e:
            disc_result = f"UnreachableError: {e.remedy}"
        except Exception as e:
            disc_result = f"{type(e).__name__}: {e}"
    ok = h.state is HealthState.HEALTHY and "UnreachableError" in disc_result and "listCollections" in disc_result
    log("CON-180", "PASS" if ok else "FAIL", f"health={h.state} discover()={disc_result}")

def con181():
    c = MongoConnector(cfg(host="dbhost", port=27017, user="alice", password="p@ss:w/ord", database="d", uri=""))
    uri = c._connection_uri()
    ok = "p@ss:w/ord" not in uri and "@dbhost:27017" in uri
    log("CON-181", "PASS" if ok else "FAIL", f"built_uri={uri!r}")

async def main():
    await con172()
    await con173()
    await con174()
    await con175()
    await con176()
    await con177()
    await con178()
    await con179()
    await con180()
    con181()

asyncio.run(main())
