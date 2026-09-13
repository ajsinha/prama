import sys, os, json, asyncio
sys.path.insert(0, os.path.dirname(__file__))
import api_common as a
from logger import record
import cli_common as c
from unittest.mock import patch

DB = c.WORKDIR / "api3.db"


async def main():
    env = a.Env(str(DB))
    await env.start()

    async with env.client(env.api_key) as http, env.client() as anon:
        # API-010 / API-011 / API-012 / API-013: problem+json across failure classes
        results = {}
        results["no-auth-401"] = await anon.get("/datasets")
        results["unknown-404"] = await http.get("/nope-does-not-exist")
        results["wrong-method-405"] = await http.delete("/health")
        results["422-body"] = await http.post("/datasets", json={"name": 1})
        results["duplicate-409"] = None
        r1 = await http.post("/datasets", json={"name": "dup-x", "criticality": 4})
        r2 = await http.post("/datasets", json={"name": "dup-x", "criticality": 4})
        results["duplicate-409"] = r2
        results["not-found-entity-404"] = await http.get("/datasets/01NOSUCHENTITY0000000000")

        bad_500 = None
        try:
            with patch("prama.db.dao.versioned.VersionedDao.list_current", side_effect=RuntimeError("SSN 123-45-6789 leaked")):
                bad_500 = await http.get("/datasets")
        except Exception as e:
            bad_500 = ("CLIENT_EXCEPTION", type(e).__name__, str(e)[:200])
        results["500-unhandled"] = bad_500

    required_fields = {"type", "title", "status", "code", "remedy", "correlation_id"}
    bad = {}
    for label, resp in results.items():
        if resp is None:
            continue
        if isinstance(resp, tuple):
            bad[label] = f"raw exception propagated to client: {resp}"
            continue
        ct = resp.headers.get("content-type", "")
        is_problem = "application/problem+json" in ct
        try:
            body = resp.json()
        except Exception:
            body = None
        missing = required_fields - set(body.keys()) if isinstance(body, dict) else required_fields
        if not is_problem or missing:
            bad[label] = f"status={resp.status_code} content_type={ct!r} missing_fields={missing} body={str(body)[:200]}"
    record(
        "API-010",
        "FAIL" if bad else "PASS",
        f"checked={list(results.keys())} bad={bad}",
    )
    # API-011
    r404 = results["unknown-404"]
    ok11 = "application/problem+json" in r404.headers.get("content-type", "") and "code" in r404.json() and "remedy" in r404.json()
    record("API-011", "PASS" if ok11 else "FAIL", f"status={r404.status_code} ct={r404.headers.get('content-type')} body={r404.text[:200]}")
    # API-012
    r405 = results["wrong-method-405"]
    ok12 = r405.status_code == 405 and "application/problem+json" in r405.headers.get("content-type", "") and "allow" in {k.lower() for k in r405.headers}
    record("API-012", "PASS" if ok12 else "FAIL", f"status={r405.status_code} ct={r405.headers.get('content-type')} allow={r405.headers.get('allow')} body={r405.text[:200]}")
    # API-013
    r422 = results["422-body"]
    body422 = r422.json()
    ok13 = r422.status_code == 422 and "application/problem+json" in r422.headers.get("content-type", "") and {"code", "remedy", "correlation_id"} <= set(body422.keys())
    record("API-013", "PASS" if ok13 else "FAIL", f"status={r422.status_code} body={body422}")

    # API-014: a 500 never leaks the exception text
    r500 = results["500-unhandled"]
    if isinstance(r500, tuple):
        record("API-014", "FAIL", f"the exception itself propagated to the client rather than a Response: {r500} -- see API-006/API-010")
    else:
        leaked = "SSN" in r500.text or "123-45-6789" in r500.text
        record("API-014", "FAIL" if leaked else "PASS", f"status={r500.status_code} leaked={leaked} body={r500.text[:300]}")

    # API-016: each error family maps to its documented status
    async with env.client(env.api_key) as http2, env.client() as anon2:
        m = {}
        m["unauthorised"] = (await anon2.get("/datasets")).status_code
        readonly_key = await a._issue_key(env.database, env.tenant_id, principal="ro2", scopes=["declaration:read"])
        async with env.client(readonly_key) as ro:
            m["forbidden"] = (await ro.post("/datasets", json={"name": "z", "criticality": 4})).status_code
        m["notfound"] = (await http2.get("/datasets/01NOSUCHENTITY0000000000")).status_code
        r1c = await http2.post("/datasets", json={"name": "conflict-x", "criticality": 4})
        r2c = await http2.post("/datasets", json={"name": "conflict-x", "criticality": 4})
        m["conflict"] = r2c.status_code
        m["validation"] = (await http2.post("/datasets", json={"name": 1})).status_code
    expected = {"unauthorised": 401, "forbidden": 403, "notfound": 404, "conflict": 409, "validation": 422}
    bad16 = {k: (m[k], expected[k]) for k in expected if m.get(k) != expected[k]}
    record("API-016", "PASS" if not bad16 else "FAIL", f"observed={m} bad={bad16}")

    # API-017: type URI derived from code
    async with env.client(env.api_key) as http3:
        r = await http3.get("/nope-xyz")
        body = r.json()
        derived = body.get("code", "").lower().replace(".", "-")
        ok17 = derived and derived in body.get("type", "")
        record("API-017", "PASS" if ok17 else "FAIL", f"code={body.get('code')} type={body.get('type')} derived={derived}")

    # API-018: instance names the path, no query string
    async with env.client(env.api_key) as http4:
        r = await http4.get("/datasets/abc?secret=token123")
        body = r.json()
        inst = body.get("instance", "")
        ok18 = "secret" not in inst and "token123" not in inst and "/datasets/abc" in inst
        record("API-018", "PASS" if ok18 else "FAIL", f"instance={inst!r}")

    # API-019: deep JSON refused, not a 500
    async with env.client(env.api_key) as http5:
        deep = "x"
        obj = "1"
        for _ in range(300):
            obj = f"[{obj}]"
        try:
            r = await http5.post("/datasets", content=f'{{"name": {obj}}}'.encode(), headers={"content-type": "application/json"})
            record("API-019", "PASS" if r.status_code == 422 else "FAIL", f"status={r.status_code} body={r.text[:200]}")
        except Exception as e:
            record("API-019", "FAIL", f"client-side exception: {type(e).__name__} {str(e)[:200]}")

    # API-020: huge body bounded
    async with env.client(env.api_key) as http6:
        big_payload = {"name": "x" * (100 * 1024 * 1024)}
        try:
            r = await http6.post("/datasets", json=big_payload, timeout=30)
            ok20 = r.status_code in (413, 422)
            record("API-020", "PASS" if ok20 else "FAIL", f"status={r.status_code} body={r.text[:200]}")
        except Exception as e:
            record("API-020", "FAIL", f"client-side exception (possible unbounded memory read): {type(e).__name__} {str(e)[:200]}")

    # API-021: wrong content type
    async with env.client(env.api_key) as http7:
        res21 = {}
        r_text = await http7.post("/datasets", content=b'{"name":"x","criticality":4}', headers={"content-type": "text/plain"})
        res21["text/plain"] = (r_text.status_code, r_text.headers.get("content-type"))
        r_form = await http7.post("/datasets", content=b"name=x", headers={"content-type": "application/x-www-form-urlencoded"})
        res21["form"] = (r_form.status_code, r_form.headers.get("content-type"))
        r_none = await http7.post("/datasets", content=b'{"name":"x","criticality":4}', headers={"content-type": ""})
        res21["none"] = (r_none.status_code, r_none.headers.get("content-type"))
    bad21 = {k: v for k, v in res21.items() if v[0] not in (400, 415, 422) or (v[1] and "problem+json" not in v[1])}
    record("API-021", "PASS" if not bad21 else "FAIL", f"{res21}")

    # API-022: truncated JSON body
    async with env.client(env.api_key) as http8:
        r = await http8.post("/datasets", content=b'{"name": "x"', headers={"content-type": "application/json"})
        ok22 = r.status_code == 422 and "problem+json" in r.headers.get("content-type", "")
        record("API-022", "PASS" if ok22 else "FAIL", f"status={r.status_code} ct={r.headers.get('content-type')} body={r.text[:200]}")

    await env.stop()


asyncio.run(main())
print("done api batch 1c")
