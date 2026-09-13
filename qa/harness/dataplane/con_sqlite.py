import sys, asyncio, sqlite3, tempfile, os, time
sys.path.insert(0, ".")
from qa_common import log
from prama.connect.sources.sqlite import SqliteConnector
from prama.connect.spi import SamplePlan, SamplingStrategy, ConnectorError

tmpdir = tempfile.mkdtemp()
dbpath = os.path.join(tmpdir, "t.db")
conn = sqlite3.connect(dbpath)
conn.execute("CREATE TABLE positions (id INTEGER PRIMARY KEY AUTOINCREMENT, ccy TEXT)")
conn.executemany("INSERT INTO positions (ccy) VALUES (?)", [("GBP",)]*1000)
conn.execute("CREATE VIEW broken_view AS SELECT * FROM dropped_table")
conn.commit()
conn.close()

def con122():
    c = SqliteConnector({"database_path": dbpath})
    ro_conn = c._connect()
    try:
        ro_conn.execute("DELETE FROM positions")
        log("CON-122", "FAIL", "DELETE succeeded through _connect()'s connection")
    except sqlite3.OperationalError as e:
        ok = "readonly" in str(e).lower()
        log("CON-122", "PASS" if ok else "FAIL", f"{type(e).__name__}: {e}")
    finally:
        ro_conn.close()

async def con123():
    c1 = SqliteConnector({"database_path": dbpath})
    snap1 = await c1.snapshot(("positions",))
    conn2 = sqlite3.connect(dbpath)
    conn2.execute("INSERT INTO positions (ccy) VALUES ('USD')")
    conn2.commit()
    conn2.close()
    time.sleep(0.01)
    c2 = SqliteConnector({"database_path": dbpath})  # fresh connector
    snap2 = await c2.snapshot(("positions",))
    ok = snap1.identifier != snap2.identifier
    log("CON-123", "PASS" if ok else "FAIL", f"before={snap1.identifier} after={snap2.identifier}")

async def con124():
    c = SqliteConnector({"database_path": dbpath})
    s1 = await c.snapshot(("positions",))
    s2 = await c.snapshot(("positions",))
    ok = s1.identifier == s2.identifier and s1.exact is True
    log("CON-124", "PASS" if ok else "FAIL", f"id1={s1.identifier} id2={s2.identifier} exact={s1.exact}")

async def con125():
    p2 = os.path.join(tmpdir, "t2.db")
    c = sqlite3.connect(p2)
    c.execute("CREATE TABLE t (a TEXT)")
    c.execute("INSERT INTO t VALUES ('AAAA')")
    c.commit()
    c.close()
    conn3 = SqliteConnector({"database_path": p2})
    s_before = await conn3.snapshot(("t",))
    st = os.stat(p2)
    # edit in place preserving length: same-length replacement string
    with open(p2, "r+b") as f:
        data = f.read()
        idx = data.find(b"AAAA")
        f.seek(idx)
        f.write(b"BBBB")
    os.utime(p2, ns=(st.st_atime_ns, st.st_mtime_ns))  # restore mtime exactly
    conn4 = SqliteConnector({"database_path": p2})
    s_after = await conn4.snapshot(("t",))
    ok = s_before.identifier == s_after.identifier
    log("CON-125", "PASS" if ok else "FAIL", f"before={s_before.identifier} after={s_after.identifier} (in-place same-length edit with restored mtime is undetected, as stated)")

async def con126():
    c = SqliteConnector({"database_path": dbpath})
    found = await c.discover()
    view = next((o for o in found if o.leaf == "broken_view"), None)
    ok = view is not None and view.estimated_rows is None
    log("CON-126", "PASS" if ok else "FAIL", f"broken_view found={view is not None} estimated_rows={view.estimated_rows if view else None}")

async def con127():
    c = SqliteConnector({"database_path": dbpath})
    found = await c.discover()
    names = [o.leaf for o in found]
    ok = "sqlite_sequence" not in names
    log("CON-127", "PASS" if ok else "FAIL", f"objects={names}")

async def con128():
    c = SqliteConnector({"database_path": dbpath})
    obs = []
    all_ok = True
    for method, args in (("describe", ((),)), ("snapshot", ((),))):
        try:
            await getattr(c, method)(*args)
            all_ok = False
            obs.append(f"{method}: no error")
        except ConnectorError as e:
            ok = e.code == "CONNECT.OBJECT_MISSING" and e.remedy == "Give the table or view name."
            all_ok = all_ok and ok
            obs.append(f"{method}: code={e.code} remedy={e.remedy!r}")
    try:
        await c.read(()).__anext__()
        all_ok = False
        obs.append("read: no error")
    except ConnectorError as e:
        ok = e.code == "CONNECT.OBJECT_MISSING" and e.remedy == "Give the table or view name."
        all_ok = all_ok and ok
        obs.append(f"read: code={e.code} remedy={e.remedy!r}")
    log("CON-128", "PASS" if all_ok else "FAIL", "; ".join(obs))

async def con129():
    c = SqliteConnector({"database_path": dbpath})
    plan42 = SamplePlan(strategy=SamplingStrategy.SYSTEMATIC, rows=100, seed=42)
    r1 = [b.to_pylist() for b in [x async for x in c.read(("positions",), plan=plan42)]]
    ids1 = [row["id"] for batch in r1 for row in batch]
    r2 = [b.to_pylist() for b in [x async for x in c.read(("positions",), plan=plan42)]]
    ids2 = [row["id"] for batch in r2 for row in batch]
    plan43 = SamplePlan(strategy=SamplingStrategy.SYSTEMATIC, rows=100, seed=43)
    r3 = [b.to_pylist() for b in [x async for x in c.read(("positions",), plan=plan43)]]
    ids3 = [row["id"] for batch in r3 for row in batch]
    ok = ids1 == ids2 and ids1 != ids3
    log("CON-129", "PASS" if ok else "FAIL", f"seed42_run1_len={len(ids1)} identical_rerun={ids1==ids2} differs_at_seed43={ids1!=ids3}")

def con130():
    c = SqliteConnector({"database_path": dbpath})
    plan0 = SamplePlan(strategy=SamplingStrategy.SYSTEMATIC, rows=100, seed=0)
    sql = c._select("positions", plan0, 100, 0)
    ok = "ORDER BY (rowid * 1 % 1000003)" in sql
    log("CON-130", "PASS" if ok else "FAIL", sql)

async def con131():
    p3 = os.path.join(tmpdir, "t3.db")
    cc = sqlite3.connect(p3)
    cc.execute("CREATE TABLE big (id INTEGER PRIMARY KEY)")
    cc.executemany("INSERT INTO big (id) VALUES (?)", [(i,) for i in range(1, 25001)])
    cc.commit()
    cc.close()
    c = SqliteConnector({"database_path": p3})
    plan = SamplePlan(strategy=SamplingStrategy.SYSTEMATIC, seed=7)
    ids = []
    async for batch in c.read(("big",), plan=plan):
        ids.extend(r["id"] for r in batch.to_pylist())
    ok = len(ids) == len(set(ids)) and len(ids) == 25000
    log("CON-131", "PASS" if ok else "FAIL", f"n_rows={len(ids)} n_distinct={len(set(ids))}")

async def main():
    con122()
    await con123()
    await con124()
    await con125()
    await con126()
    await con127()
    await con128()
    await con129()
    con130()
    await con131()

asyncio.run(main())
