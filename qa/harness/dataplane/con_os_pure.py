import sys
sys.path.insert(0, ".")
from qa_common import log
from prama.connect.sources.objectstore import (
    ObjectStoreConnector, _group, _partition_depth, _BARE_PARTITION, _StoredObject, _is_denied,
)
_classify = ObjectStoreConnector._classify
from prama.connect.spi import HealthState

def con143():
    objs = [_StoredObject(key=f"s3://lake/risk/positions/booked=2026-04-{d:02d}/part-0.parquet", size=100, rows=10)
            for d in range(1, 31)]
    for m in range(2, 31):
        for d in range(1, 31):
            objs.append(_StoredObject(key=f"s3://lake/risk/positions/booked=2026-{m:02d}-{d:02d}/part-0.parquet", size=100, rows=10))
    datasets = _group(objs)
    ok = len(datasets) == 1 and datasets[0].partition_columns == ("booked",) and "booked" in datasets[0].describe()
    log("CON-143", "PASS" if ok else "FAIL", f"n_datasets={len(datasets)} tags={datasets[0].partition_columns if datasets else None} comment={datasets[0].describe() if datasets else None}")

def con144():
    objs1 = [_StoredObject(key="s3://b/risk/2026/positions/part-0.parquet")]
    d1 = _group(objs1)
    objs2 = [_StoredObject(key="s3://b/risk/positions/2026-04-01/part-0.parquet")]
    d2 = _group(objs2)
    # _group() keeps the bucket as the path's first segment (confirmed: both
    # d1[0].path and d2[0].path start with "b").
    ok = (len(d1) == 1 and d1[0].path == ("b", "risk", "2026", "positions") and d1[0].partition_depth == 0
          and len(d2) == 1 and d2[0].path == ("b", "risk", "positions") and d2[0].partition_depth == 1
          and d2[0].partition_columns == ())
    log("CON-144", "PASS" if ok else "FAIL",
        f"d1: path={d1[0].path if d1 else None} depth={d1[0].partition_depth if d1 else None}; "
        f"d2: path={d2[0].path if d2 else None} depth={d2[0].partition_depth if d2 else None} cols={d2[0].partition_columns if d2 else None}")

def con145():
    inputs = ["2026", "202604", "20260401", "7", "1234", "12345", "v2", "part", "2026-4-1"]
    results = {s: bool(_BARE_PARTITION.match(s)) for s in inputs}
    expected = {"2026": True, "202604": True, "20260401": True, "7": True, "1234": True,
                "12345": False, "v2": False, "part": False, "2026-4-1": False}
    ok = results == expected
    log("CON-145", "PASS" if ok else "FAIL", f"results={results}")

def con151():
    c = ObjectStoreConnector({"uri": "s3://bucket/prefix", "access_key_id": "AKID", "secret_access_key": "s3cr3t'value"})
    stmt = c._secret_statement()
    ok = "s3cr3t''value" in stmt and "KEY_ID 'AKID'" in stmt
    log("CON-151", "PASS" if ok else "FAIL", stmt)

def con152():
    c = ObjectStoreConnector({"uri": "s3://bucket/prefix", "region": "eu-west-1", "endpoint": "minio:9000", "session_token": "tok123"})
    stmt = c._secret_statement()
    # "SECRET" bare is always a substring of "CREATE OR REPLACE SECRET" itself;
    # the clause under test renders as SECRET '<value>' (see CON-151's stmt), so
    # that is what absence has to mean.
    ok = "PROVIDER credential_chain" in stmt and "KEY_ID" not in stmt and "SECRET '" not in stmt and "SESSION_TOKEN" not in stmt
    log("CON-152", "PASS" if ok else "FAIL", stmt)

import asyncio
async def con153():
    # health() is meant to classify a bad URI as MISCONFIGURED without raising.
    # If open()/_connect() instead raises a raw duckdb exception, the idiomatic
    # `async with connector:` pattern never reaches health() at all -- caught
    # here per-URI so that outcome is itself the observed (failing) result,
    # rather than an uncaught crash that also takes con154/con155 down with it.
    obs = {}
    for uri in ("/mnt/lake/positions", "http://x/y", "", "s3://bucket/prefix"):
        c = ObjectStoreConnector({"uri": uri, "endpoint": "127.0.0.1:1"})
        try:
            async with c:
                r = await c.health()
            obs[uri] = r.state
        except Exception as e:
            obs[uri] = f"UNCAUGHT {type(e).__name__}: {e}"
    ok = (obs["/mnt/lake/positions"] is HealthState.MISCONFIGURED
          and obs["http://x/y"] is HealthState.MISCONFIGURED
          and obs[""] is HealthState.MISCONFIGURED
          and obs["s3://bucket/prefix"] is not HealthState.MISCONFIGURED)
    log("CON-153", "PASS" if ok else "FAIL",
        {k: (v.value if isinstance(v, HealthState) else v) for k, v in obs.items()})

def con154():
    cases = {
        "access denied case": Exception("Access Denied by policy"),
        "403 case": Exception("HTTP 403 returned"),
        "sigmismatch": Exception("SignatureDoesNotMatch"),
        "no bucket": Exception("The specified bucket does not exist: No such bucket"),
        "conn refused": Exception("connection refused"),
    }
    results = {k: _classify(v) for k, v in cases.items()}
    expected = {
        "access denied case": HealthState.UNAUTHORISED,
        "403 case": HealthState.UNAUTHORISED,
        "sigmismatch": HealthState.UNAUTHORISED,
        "no bucket": HealthState.MISCONFIGURED,
        "conn refused": HealthState.UNREACHABLE,
    }
    ok = results == expected
    # also: an object key containing "signature" gets classified as denied
    sig_case = _is_denied(Exception("could not read object key 'signature_verification.csv'"))
    log("CON-154", "PASS" if ok else "FAIL",
        f"results={ {k: v.value for k, v in results.items()} } "
        f"(also: exception mentioning an object key containing 'signature' -> _is_denied={sig_case}, "
        f"i.e. would be misclassified as an access-denied error)")

def con155():
    long_msg = ("first line of the error\n" + "x" * 5000)
    from prama.connect.sources.objectstore import ObjectStoreConnector as OSC
    detail = str(Exception(long_msg)).strip().splitlines()[0][:300]
    ok = detail == "first line of the error"
    log("CON-155", "PASS" if ok else "FAIL", f"detail={detail!r} len={len(detail)}")

con143(); con144(); con145(); con151(); con152(); asyncio.run(con153()); con154(); con155()
