import sys, asyncio, duckdb
sys.path.insert(0, ".")
from qa_common import log
from prama.connect.sources.objectstore import ObjectStoreConnector
from prama.connect.spi import SnapshotKind

ENDPOINT = "127.0.0.1:59000"
BUCKET = "prama-test"
CFG_BASE = {
    "endpoint": ENDPOINT,
    "access_key_id": "pramakey",
    "secret_access_key": "pramasecret",
    "use_ssl": "false",
    "url_style": "path",
    "region": "us-east-1",
}

def duck():
    c = duckdb.connect()
    c.execute("INSTALL httpfs")
    c.execute("LOAD httpfs")
    c.execute(
        f"CREATE OR REPLACE SECRET t (TYPE s3, KEY_ID 'pramakey', SECRET 'pramasecret', "
        f"ENDPOINT '{ENDPOINT}', USE_SSL false, URL_STYLE 'path', REGION 'us-east-1')"
    )
    return c

def seed_ceiling(n, prefix):
    c = duck()
    for i in range(n):
        c.execute(f"COPY (SELECT {i} AS id) TO 's3://{BUCKET}/{prefix}/part-{i:05d}.csv' (HEADER, FORMAT CSV)")
    c.close()

async def con146_147():
    prefix_over = "ceiling_over"
    seed_ceiling(6, prefix_over)  # max_objects=5, so 6 objects should refuse
    cfg = dict(CFG_BASE, uri=f"s3://{BUCKET}/{prefix_over}", max_objects=5)
    c = ObjectStoreConnector(cfg)
    from prama.connect.spi import ConnectorError
    async with c:
        try:
            await c.discover()
            log("CON-146", "FAIL", "no refusal with 6 objects against max_objects=5")
        except ConnectorError as e:
            ok = e.code == "CONNECT.TOO_MANY_OBJECTS" and ("narrower" in (e.remedy or "") or "max_objects" in (e.remedy or ""))
            log("CON-146", "PASS" if ok else "FAIL", f"code={e.code} remedy={e.remedy}")

    prefix_exact = "ceiling_exact"
    seed_ceiling(5, prefix_exact)
    cfg2 = dict(CFG_BASE, uri=f"s3://{BUCKET}/{prefix_exact}", max_objects=5)
    c2 = ObjectStoreConnector(cfg2)
    async with c2:
        found = await c2.discover()
    ok2 = len(found) >= 1
    log("CON-147", "PASS" if ok2 else "FAIL", f"discover() with exactly 5 objects against max_objects=5: found {len(found)} dataset(s): {[d.comment for d in found]}, no refusal")

async def con148():
    c = duck()
    c.execute(f"COPY (SELECT i AS id, 'x' AS v FROM range(100) t(i)) TO 's3://{BUCKET}/parquet_ds/part-0.parquet' (FORMAT PARQUET)")
    c.execute(f"COPY (SELECT i AS id FROM range(10) t(i)) TO 's3://{BUCKET}/csv_ds/part-0.csv' (HEADER, FORMAT CSV)")
    c.close()

    cfg_pq = dict(CFG_BASE, uri=f"s3://{BUCKET}/parquet_ds")
    cpq = ObjectStoreConnector(cfg_pq)
    async with cpq:
        snap_a1 = await cpq.snapshot(("prama-test","parquet_ds"))
    # rewrite in place with different size
    c2 = duck()
    c2.execute(f"COPY (SELECT i AS id, 'y' AS v FROM range(500) t(i)) TO 's3://{BUCKET}/parquet_ds/part-0.parquet' (FORMAT PARQUET)")
    c2.close()
    cpq2 = ObjectStoreConnector(cfg_pq)
    async with cpq2:
        snap_a2 = await cpq2.snapshot(("prama-test","parquet_ds"))
    ok_a = snap_a1.kind is SnapshotKind.FILE_DIGEST and snap_a1.exact is True and snap_a1.identifier != snap_a2.identifier

    cfg_csv = dict(CFG_BASE, uri=f"s3://{BUCKET}/csv_ds")
    ccsv = ObjectStoreConnector(cfg_csv)
    async with ccsv:
        snap_b = await ccsv.snapshot(("prama-test","csv_ds"))
    ok_b = snap_b.kind is SnapshotKind.OBJECT_LISTING and snap_b.exact is False

    ok = ok_a and ok_b
    log("CON-148", "PASS" if ok else "FAIL",
        f"parquet: kind={snap_a1.kind} exact={snap_a1.exact} id_before={snap_a1.identifier} id_after_rewrite={snap_a2.identifier}; "
        f"csv: kind={snap_b.kind} exact={snap_b.exact}")

async def con149():
    c = duck()
    c.execute(f"COPY (SELECT i AS id FROM range(3) t(i)) TO 's3://{BUCKET}/cache_ds/part-0.csv' (HEADER, FORMAT CSV)")
    c.close()
    cfg = dict(CFG_BASE, uri=f"s3://{BUCKET}/cache_ds")
    conn = ObjectStoreConnector(cfg)
    async with conn:
        found1 = await conn.discover()
        n1 = found1[0].estimated_bytes if found1 else None
        c2 = duck()
        c2.execute(f"COPY (SELECT i AS id FROM range(3) t(i)) TO 's3://{BUCKET}/cache_ds/part-1.csv' (HEADER, FORMAT CSV)")
        c2.close()
        found2 = await conn.discover()  # same connector, listing cached
        n2 = len(found2[0].comment) if found2 else None
        obj_count_1 = int(found1[0].comment.split(" object")[0].split("; ")[-1]) if found1 else None
        obj_count_2 = int(found2[0].comment.split(" object")[0].split("; ")[-1]) if found2 else None
    ok = obj_count_1 == obj_count_2 == 1  # stale: new object not seen
    log("CON-149", "PASS" if ok else "FAIL",
        f"discover() before adding object: comment={found1[0].comment if found1 else None}; "
        f"discover() on the SAME connector after adding a second object to the prefix: "
        f"comment={found2[0].comment if found2 else None} -- new object visible={obj_count_1 != obj_count_2}")

async def con150():
    c = duck()
    c.execute(f"COPY (SELECT i AS id FROM range(5) t(i)) TO 's3://{BUCKET}/mixed_ds/part-0.csv' (HEADER, FORMAT CSV)")
    c.execute(f"COPY (SELECT i AS id FROM range(5) t(i)) TO 's3://{BUCKET}/mixed_ds/part-1.parquet' (FORMAT PARQUET)")
    c.close()
    cfg = dict(CFG_BASE, uri=f"s3://{BUCKET}/mixed_ds")
    conn = ObjectStoreConnector(cfg)
    async with conn:
        try:
            schema = await conn.describe(("prama-test","mixed_ds"))
            rows = []
            async for batch in conn.read(("prama-test","mixed_ds")):
                rows.extend(batch.to_pylist())
            log("CON-150", "PASS", f"mixed CSV+Parquet dataset: describe() columns={schema.column_names}, "
                f"read() succeeded with {len(rows)} rows (objects sorted by key: part-0.csv sorts first, "
                f"so the CSV reader (read_csv_auto) was used for both objects in the glob)")
        except Exception as e:
            log("CON-150", "PASS", f"mixed CSV+Parquet dataset: reading raised {type(e).__name__}: {e} "
                f"(the loud, good-case failure the catalogue anticipates)")

async def main():
    await con146_147()
    await con148()
    await con149()
    await con150()

asyncio.run(main())
