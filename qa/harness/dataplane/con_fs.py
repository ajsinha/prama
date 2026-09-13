import sys, asyncio, os, tempfile, time, threading
sys.path.insert(0, ".")
from qa_common import log
from prama.connect.sources.filesystem import FilesystemConnector
from prama.connect.spi import ConnectorError, UnauthorisedError, SamplePlan, SamplingStrategy, ReadPolicy

base = tempfile.mkdtemp()
root = os.path.join(base, "root")
os.makedirs(root)
with open(os.path.join(base, "secret.csv"), "w") as f:
    f.write("a,b\n1,2\n")
with open(os.path.join(root, "data.csv"), "w") as f:
    f.write("a,b\n1,2\n2,3\n")
with open(os.path.join(root, "notes.md"), "w") as f:
    f.write("# notes\n")
with open(os.path.join(root, "it's_data.csv"), "w") as f:
    f.write("a,b\n1,2\n3,4\n")
with open(os.path.join(root, "data.xyz"), "w") as f:
    f.write("nonsense")
with open(os.path.join(root, "README"), "w") as f:
    f.write("no extension")
with open(os.path.join(root, "empty.csv"), "w") as f:
    pass
with open(os.path.join(root, "header_only.csv"), "w") as f:
    f.write("a,b,c\n")

async def con132():
    c = FilesystemConnector({"root_path": root})
    obs = []
    async with c:
        try:
            r = await c.describe(("..", "secret.csv"))
            obs.append(f"describe(('..','secret.csv')): NO ERROR, columns={r.column_names}")
        except UnauthorisedError as e:
            obs.append(f"describe: UnauthorisedError (read policy) {e}")
        except ConnectorError as e:
            obs.append(f"describe: ConnectorError code={e.code} {e}")
        except Exception as e:
            obs.append(f"describe: {type(e).__name__}: {e}")
        try:
            gen = c.read(("..", "..", "etc", "passwd"))
            await gen.__anext__()
            obs.append("read(('..','..','etc','passwd')): NO ERROR (yielded data)")
        except UnauthorisedError as e:
            obs.append(f"read: UnauthorisedError (read policy) {e}")
        except ConnectorError as e:
            obs.append(f"read: ConnectorError code={e.code} {e}")
        except StopAsyncIteration:
            obs.append("read: StopAsyncIteration (empty)")
        except Exception as e:
            obs.append(f"read: {type(e).__name__}: {e}")
    escaped = any("Unauthorised" in o or "OBJECT_MISSING" in o for o in obs)
    leaked = any("NO ERROR" in o for o in obs)
    log("CON-132", "FAIL" if leaked else "PASS", "; ".join(obs))

async def con133():
    c = FilesystemConnector({"root_path": root})
    async with c:
        found = await c.discover()
        names = [o.leaf for o in found]
        target = ("it's_data.csv",)
        schema = await c.describe(target)
        rows = []
        async for batch in c.read(target):
            rows.extend(batch.to_pylist())
        reader_expr = c._reader(c._resolve(target))
    ok = "it's_data.csv" in names and len(schema.columns) == 2 and len(rows) == 2 and "it''s_data.csv" in reader_expr
    log("CON-133", "PASS" if ok else "FAIL", f"discovered={names} n_columns={len(schema.columns)} n_rows={len(rows)} reader_expr={reader_expr!r}")

async def con134():
    c = FilesystemConnector({"root_path": root})
    async with c:
        obs = {}
        for name in ("data.xyz", "README"):
            try:
                await c.describe((name,))
                obs[name] = "NO ERROR"
            except ConnectorError as e:
                obs[name] = (e.code, str(e), e.remedy)
    ok = (obs["data.xyz"][0] == "CONNECT.FORMAT_UNSUPPORTED"
          and obs["README"][0] == "CONNECT.FORMAT_UNSUPPORTED"
          and "no extension" in obs["README"][1]
          and all(ext in obs["data.xyz"][2] for ext in (".csv", ".parquet", ".json")))
    log("CON-134", "PASS" if ok else "FAIL", str(obs))

async def con135():
    c = FilesystemConnector({"root_path": root})
    async with c:
        found = await c.discover()
    names = sorted(o.leaf for o in found)
    ok = "notes.md" not in names and "data.csv" in names
    log("CON-135", "PASS" if ok else "FAIL", f"discovered={names}")

async def con136():
    big = os.path.join(root, "big.csv")
    with open(big, "wb") as f:
        f.write(b"a\n")
        chunk = (b"1" * 1023 + b"\n")
        for _ in range(200 * 1024):  # ~200MB
            f.write(chunk)
    c1 = FilesystemConnector({"root_path": root})
    async with c1:
        s1 = await c1.snapshot(("big.csv",))
    c2 = FilesystemConnector({"root_path": root, "max_file_bytes": 1024 * 1024})
    async with c2:
        s2 = await c2.snapshot(("big.csv",))
    ok = s1.detail.get("hashed_bytes") == 67_108_864 and s2.detail.get("hashed_bytes") == 1024 * 1024
    log("CON-136", "PASS" if ok else "FAIL", f"default_hashed_bytes={s1.detail.get('hashed_bytes')} (expected 67108864); 1MB_ceiling_hashed_bytes={s2.detail.get('hashed_bytes')} (expected 1048576)")
    os.remove(big)

async def con137():
    a = os.path.join(root, "twin_a.bin")
    b = os.path.join(root, "twin_b.bin")
    common = os.urandom(1024 * 1024)
    with open(a, "wb") as f:
        f.write(common); f.write(b"AAAA_TAIL_DIFFERS")
    with open(b, "wb") as f:
        f.write(common); f.write(b"BBBBBBBBBB_TAIL_IS_LONGER_AND_DIFFERENT")
    c = FilesystemConnector({"root_path": root, "max_file_bytes": 1024 * 1024, "file_pattern": "twin_*.bin"})
    # .bin has no reader, but snapshot doesn't need one -- use plain filenames via _resolve directly
    async with c:
        sa = await c.snapshot(("twin_a.bin",))
        sb = await c.snapshot(("twin_b.bin",))
    ok = sa.identifier != sb.identifier
    log("CON-137", "PASS" if ok else "FAIL", f"a={sa.identifier} b={sb.identifier} a_bytes={sa.detail.get('bytes')} b_bytes={sb.detail.get('bytes')} (size differs so digest differs even though first 1MB identical and hash truncated at 1MB)")

async def con138():
    small = os.path.join(root, "tiny.csv")
    with open(small, "w") as f:
        f.write("0123456789")  # exactly 10 bytes
    c = FilesystemConnector({"root_path": root})
    async with c:
        s = await c.snapshot(("tiny.csv",))
    ok = s.detail.get("hashed_bytes") == 10
    log("CON-138", "PASS" if ok else "FAIL", f"hashed_bytes={s.detail.get('hashed_bytes')} file_bytes={s.detail.get('bytes')}")

async def con139():
    c = FilesystemConnector({"root_path": root})
    obs = {}
    async with c:
        try:
            schema_h = await c.describe(("header_only.csv",))
            rows_h = []
            async for batch in c.read(("header_only.csv",)):
                rows_h.extend(batch.to_pylist())
            obs["header_only"] = (schema_h.estimated_rows, schema_h.column_names, len(rows_h))
        except Exception as e:
            obs["header_only"] = f"{type(e).__name__}: {e}"
        try:
            schema_e = await c.describe(("empty.csv",))
            rows_e = []
            async for batch in c.read(("empty.csv",)):
                rows_e.extend(batch.to_pylist())
            obs["empty"] = (schema_e.estimated_rows, schema_e.column_names, len(rows_e))
        except Exception as e:
            obs["empty"] = f"{type(e).__name__}: {e}"
    h_ok = isinstance(obs["header_only"], tuple) and obs["header_only"][0] == 0 and obs["header_only"][2] == 0
    ok = h_ok  # empty.csv's behaviour is simply recorded, per the catalogue's own wording
    log("CON-139", "PASS" if ok else "FAIL", f"header_only.csv={obs['header_only']}; empty.csv={obs['empty']}")

async def con140():
    big1 = os.path.join(root, "conc1.csv")
    big2 = os.path.join(root, "conc2.csv")
    for p, tag in ((big1, "x"), (big2, "y")):
        with open(p, "w") as f:
            f.write("a\n")
            for i in range(200_000):
                f.write(f"{tag}{i}\n")
    c = FilesystemConnector({"root_path": root})
    async with c:
        async def consume(path):
            n = 0
            async for batch in c.read((path,)):
                n += batch.num_rows
            return n

        async def interleaved():
            g1 = c.read(("conc1.csv",))
            g2 = c.read(("conc2.csv",))
            n1 = n2 = 0
            done1 = done2 = False
            while not (done1 and done2):
                if not done1:
                    try:
                        b1 = await g1.__anext__()
                        n1 += b1.num_rows
                    except StopAsyncIteration:
                        done1 = True
                if not done2:
                    try:
                        b2 = await g2.__anext__()
                        n2 += b2.num_rows
                    except StopAsyncIteration:
                        done2 = True
            return n1, n2
        n1, n2 = await interleaved()
    ok = n1 == 200_000 and n2 == 200_000
    log("CON-140", "PASS" if ok else "FAIL", f"conc1_rows={n1} conc2_rows={n2} (expected 200000 each)")

async def con141():
    big = os.path.join(root, "ticker_test.csv")
    with open(big, "w") as f:
        f.write("a\n")
        for i in range(500_000):
            f.write(f"{i}\n")
    ticks = []
    stop = False
    async def ticker():
        while not stop:
            ticks.append(time.monotonic())
            await asyncio.sleep(0.001)
    c = FilesystemConnector({"root_path": root})
    async with c:
        t = asyncio.ensure_future(ticker())
        rows = 0
        async for batch in c.read(("ticker_test.csv",)):
            rows += batch.num_rows
        nonlocal_stop = True
    globals()["_stop_flag"] = True
    # stop ticker
    task_stop = True
    await asyncio.sleep(0)
    t.cancel()
    try:
        await t
    except asyncio.CancelledError:
        pass
    gaps = [b - a for a, b in zip(ticks, ticks[1:])]
    max_gap = max(gaps) if gaps else 0
    ok = rows == 500_000 and len(ticks) > 5 and max_gap < 0.5
    log("CON-141", "PASS" if ok else "FAIL", f"rows_read={rows} ticks_recorded={len(ticks)} max_gap_seconds={max_gap:.4f}")

async def con142():
    big = os.path.join(root, "budget_test.parquet")
    import pyarrow as pa
    import pyarrow.parquet as pq
    tbl = pa.table({"id": list(range(100_000))})
    pq.write_table(tbl, big)
    policy = ReadPolicy(max_rows_read=100, max_bytes_scanned=1024)
    c = FilesystemConnector({"root_path": root}, policy=policy)
    async with c:
        rows = 0
        async for batch in c.read(("budget_test.parquet",)):
            rows += batch.num_rows
    ok = rows == 100  # would FAIL (be > 100) if the policy is ignored
    log("CON-142", "FAIL" if rows != 100 else "PASS", f"rows_read={rows} against ReadPolicy(max_rows_read=100) on a 100,000-row file (policy honoured={rows==100})")

async def main():
    await con132()
    await con133()
    await con134()
    await con135()
    await con136()
    await con137()
    await con138()
    await con139()
    await con140()
    await con141()
    await con142()

asyncio.run(main())
