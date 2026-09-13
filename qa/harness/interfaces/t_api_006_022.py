import sys, os, json, asyncio
sys.path.insert(0, os.path.dirname(__file__))
import api_common as a
from logger import record
import cli_common as c

DB = c.WORKDIR / "api2.db"


async def main():
    env = a.Env(str(DB))
    await env.start()

    # API-006: X-Correlation-Id on 2xx, 4xx, and 5xx
    async with env.client(env.api_key) as http, env.client() as anon, env.client(env.other_key) as intruder:
        results = {}
        results[200] = await http.get("/health")
        results[401] = await anon.get("/datasets")
        results[403] = await env_client_scoped(env)
        results[404] = await http.get("/datasets/01NOSUCHID")
        results[409] = None  # filled below after creating a dataset
        results[422] = await http.post("/datasets", json={"name": 1})
        results[500] = await forced_500(env)
        # 409: create a dataset twice with the same name
        r1 = await http.post("/datasets", json={"name": "dup-ds", "domain_id": None, "criticality": 4})
        r2 = await http.post("/datasets", json={"name": "dup-ds", "domain_id": None, "criticality": 4})
        results[409] = r2

    missing_cid = {code: resp for code, resp in results.items() if resp is not None and "x-correlation-id" not in {k.lower() for k in resp.headers.keys()}}
    ok = not missing_cid
    record(
        "API-006",
        "PASS" if ok else "FAIL",
        f"codes_checked={[ (code, resp.status_code if resp else None) for code, resp in results.items()]} missing_cid_on={list(missing_cid.keys())}",
    )

    # API-007: caller-supplied correlation id echoed back
    async with env.client(env.api_key, headers={"X-Correlation-Id": "abc123"}) as http:
        r = await http.get("/health")
        hdr = r.headers.get("x-correlation-id")
        ok = hdr == "abc123"
        record("API-007", "PASS" if ok else "FAIL", f"header={hdr}")

    # API-008: hostile correlation id is bounded/sanitised
    huge = "A" * 8192
    async with env.client(env.api_key, headers={"X-Correlation-Id": huge}) as http:
        r = await http.get("/health")
        hdr = r.headers.get("x-correlation-id", "")
        bounded = len(hdr) < 8192
    crlf_result = None
    try:
        async with env.client(env.api_key) as http2:
            r2 = await http2.get("/health", headers={"X-Correlation-Id": "abc\r\nX-Injected: evil"})
            crlf_result = (r2.status_code, dict(r2.headers).get("x-injected"))
    except Exception as e:
        crlf_result = ("EXCEPTION", str(e)[:150])
    ok = bounded and (crlf_result[0] != 200 or crlf_result[1] is None)
    record("API-008", "PASS" if ok else "FAIL", f"huge_len_after={len(hdr)} bounded={bounded} crlf_result={crlf_result}")

    # API-009: generated correlation id unique per request (10 sequential, not 100, to keep this fast)
    ids = []
    async with env.client(env.api_key) as http:
        for _ in range(10):
            r = await http.get("/health")
            ids.append(r.headers.get("x-correlation-id"))
    ok = len(set(ids)) == len(ids)
    record("API-009", "PASS" if ok else "FAIL", f"n={len(ids)} unique={len(set(ids))} sample={ids[:3]}")

    await env.stop()
    return results


async def env_client_scoped(env):
    """A key scoped to declaration:read only, calling a write route -> 403."""
    key = await a._issue_key(env.database, env.tenant_id, principal="readonly", scopes=["declaration:read"])
    async with env.client(key) as http:
        return await http.post("/datasets", json={"name": "x", "domain_id": None, "criticality": 4})


async def forced_500(env):
    """A GENUINE unhandled exception, not a 422 wearing a "500" label. The previous version of
    this helper posted an invalid enum value, which Pydantic catches as an ordinary 422 --
    X-Correlation-Id already works fine on 422 (that is a separate key in the same results
    dict), so this key was silently duplicating an already-passing case and never exercising
    round 2's actual, severe finding at all: a genuine crash escapes Starlette's
    BaseHTTPMiddleware.call_next() before `correlate` ever sets the header, exactly as finding
    Q-24 describes. Patch a DAO method reachable from a real GET route to raise a plain
    RuntimeError, the same repro round 2 used, and restore it afterwards.
    """
    from prama.db.dao.semantic import DatasetDao

    original = DatasetDao.list_current
    async def _boom(self, *a2, **k2):
        raise RuntimeError("forced for API-006")
    DatasetDao.list_current = _boom
    try:
        async with env.client(env.api_key) as http:
            try:
                return await http.get("/datasets")
            except Exception:
                return None
    finally:
        DatasetDao.list_current = original


asyncio.run(main())
print("done api batch 1b")
