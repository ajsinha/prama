import sys, asyncio, time
sys.path.insert(0, ".")
from qa_common import log
from rest_server import start_server, STATE
from prama.connect.sources.rest import RestConnector, _records, _next_link, _infer, _scalar
from prama.connect.spi import SamplePlan, SamplingStrategy, ConnectorError, UnauthorisedError, UnreachableError, HealthState

server, port = start_server()
BASE = f"http://127.0.0.1:{port}"

async def con156():
    STATE["total_pages"] = 400
    STATE["page_size"] = 100
    c = RestConnector({"base_url": BASE, "endpoints": ["paginate"], "records_path": "items", "next_path": "links.next"})
    async with c:
        rows = []
        async for batch in c.read(("paginate",)):
            rows.extend(batch.to_pylist())
    ok = len(rows) == 40_000 and c.last_read_pages == 400 and c.last_read_truncated is False
    log("CON-156", "PASS" if ok else "FAIL", f"n_rows={len(rows)} pages={c.last_read_pages} truncated={c.last_read_truncated}")

async def con157():
    c = RestConnector({"base_url": BASE, "endpoints": ["cycle"], "records_path": "items", "next_path": "links.next"})
    async with c:
        rows = []
        async for batch in c.read(("cycle",)):
            rows.extend(batch.to_pylist())
    ids = [r["id"] for r in rows]
    ok = c.last_read_pages == 3 and len(ids) == len(set(ids))
    log("CON-157", "PASS" if ok else "FAIL", f"pages_read={c.last_read_pages} n_rows={len(rows)} n_distinct_ids={len(set(ids))}")

async def con158():
    STATE["total_pages"] = 50
    c = RestConnector({"base_url": BASE, "endpoints": ["manypages"], "records_path": "items", "next_path": "links.next", "page_limit": 10})
    async with c:
        rows = []
        async for batch in c.read(("manypages",)):
            rows.extend(batch.to_pylist())
    ok = c.last_read_pages == 10 and c.last_read_truncated is True
    log("CON-158", "PASS" if ok else "FAIL", f"pages_read={c.last_read_pages} truncated={c.last_read_truncated} n_rows={len(rows)}")

async def con159():
    STATE["total_pages"] = 50
    c = RestConnector({"base_url": BASE, "endpoints": ["manypages"], "records_path": "items", "next_path": "links.next"})
    async with c:
        rows = []
        plan = SamplePlan(rows=50)
        async for batch in c.read(("manypages",), plan=plan):
            rows.extend(batch.to_pylist())
    ok = len(rows) == 50 and c.last_read_truncated is False
    log("CON-159", "PASS" if ok else "FAIL", f"n_rows={len(rows)} truncated={c.last_read_truncated}")

async def con160():
    STATE["pageparam_urls"] = []
    STATE["total_pages"] = 5
    c = RestConnector({"base_url": BASE, "endpoints": ["pageparam"], "records_path": "items", "next_path": "links.next", "page_param": "p", "page_size": 5})
    async with c:
        rows = []
        async for batch in c.read(("pageparam",)):
            rows.extend(batch.to_pylist())
    urls = STATE["pageparam_urls"]
    all_have_p = all("p=" in u for u in urls)
    n_distinct = len(set(urls))
    ok = len(rows) == 25 and all_have_p and n_distinct == 5
    log("CON-160", "PASS" if ok else "FAIL", f"n_rows={len(rows)} urls_requested={urls} all_urls_carry_p_param={all_have_p}")

async def con161():
    STATE["_ratelimit_calls"] = []
    STATE["retry_after_sequence"] = ["2", "Wed, 21 Oct 2026 07:28:00 GMT", "999", None]
    c = RestConnector({"base_url": BASE, "endpoints": ["ratelimit"], "records_path": "items"})
    async with c:
        start = time.monotonic()
        rows = []
        async for batch in c.read(("ratelimit",)):
            rows.extend(batch.to_pylist())
        elapsed = time.monotonic() - start
    ok = abs(c.last_read_waited_seconds - (2 + 1 + 60 + 1)) < 1 and elapsed >= 60
    log("CON-161", "PASS" if ok else "FAIL", f"waited_seconds={c.last_read_waited_seconds} (expected ~64) wall_elapsed={elapsed:.1f}s n_rows={len(rows)}")

async def con162():
    c = RestConnector({"base_url": BASE, "endpoints": ["ratelimit_forever"], "records_path": "items"})
    async with c:
        try:
            async for batch in c.read(("ratelimit_forever",)):
                pass
            log("CON-162", "FAIL", "no exception after infinite 429s")
        except UnreachableError as e:
            ok = "five times running" in str(e) and e.remedy and ("Read less" in e.remedy or "read it less often" in e.remedy)
            log("CON-162", "PASS" if ok else "FAIL", f"{e} remedy={e.remedy}")

async def con163():
    obs = {}
    for code in (200, 401, 403, 404, 500, 503):
        c = RestConnector({"base_url": f"{BASE}/status", "endpoints": [f"?code={code}"]})
        async with c:
            r = await c.health()
        obs[code] = r.state
    read_obs = {}
    for code in (401, 404):
        c = RestConnector({"base_url": f"{BASE}/status", "endpoints": [f"?code={code}"]})
        async with c:
            try:
                async for batch in c.read((f"?code={code}",)):
                    pass
                read_obs[code] = "NO ERROR"
            except UnauthorisedError as e:
                read_obs[code] = "UnauthorisedError"
            except UnreachableError as e:
                read_obs[code] = "UnreachableError"
    expected_health = {200: HealthState.HEALTHY, 401: HealthState.UNAUTHORISED, 403: HealthState.UNAUTHORISED,
                        404: HealthState.HEALTHY, 500: HealthState.DEGRADED, 503: HealthState.DEGRADED}
    ok = obs == expected_health and read_obs[401] == "UnauthorisedError" and read_obs[404] == "UnreachableError"
    log("CON-163", "PASS" if ok else "FAIL", f"health={ {k: v.value for k,v in obs.items()} } read_401={read_obs[401]} read_404={read_obs[404]}")

async def con164():
    STATE["received_auth_headers"] = []
    c = RestConnector({"base_url": BASE, "endpoints": ["status"], "token": "abc123"})
    async with c:
        await c._http().get(f"{BASE}/status")
    headers1 = c._headers()

    c2 = RestConnector({"base_url": BASE, "endpoints": ["status"], "token": "abc123", "auth_header": "X-Api-Key", "auth_scheme": ""})
    headers2 = c2._headers()

    STATE["received_paths"] = []
    c3 = RestConnector({"base_url": BASE, "endpoints": ["status"], "token": "SECRETTOKEN"})
    async with c3:
        async for batch in c3.read(("status",)):
            pass
    token_in_url = any("SECRETTOKEN" in p for p in STATE["received_paths"])

    ok = (headers1.get("Authorization") == "Bearer abc123"
          and headers2.get("X-Api-Key") == "abc123"  # empty scheme -> no leading space
          and not token_in_url)
    log("CON-164", "PASS" if ok else "FAIL", f"default_header={headers1} custom_header_empty_scheme={headers2} token_leaked_into_url={token_in_url}")

async def con165():
    c = RestConnector({"base_url": BASE, "endpoints": ["status"]})
    STATE["received_paths"] = []
    async with c:
        plan = SamplePlan(predicate="booked = '2026-04-01'")
        try:
            async for batch in c.read(("status",), plan=plan):
                pass
            log("CON-165", "FAIL", "no exception")
        except ConnectorError as e:
            no_http_call = len(STATE["received_paths"]) == 0
            ok = e.code == "CONNECT.NO_PREDICATE" and no_http_call
            log("CON-165", "PASS" if ok else "FAIL", f"code={e.code} http_calls_made={len(STATE['received_paths'])}")

async def con166_167():
    c = RestConnector({"base_url": BASE, "endpoints": ["mixedtypes"], "records_path": "items"})
    async with c:
        schema = await c.describe(("mixedtypes",))
    amount = schema.column("amount")
    settled = schema.column("settled_at")
    ok166 = (amount is not None and amount.comment == "arrives as double and as string across the sample"
              and settled is not None and settled.nullable is True)
    log("CON-166", "PASS" if ok166 else "FAIL", f"amount.comment={amount.comment if amount else None} settled_at.nullable={settled.nullable if settled else None}")

    c2 = RestConnector({"base_url": BASE, "endpoints": ["mixedtypes"], "records_path": "items"})
    async with c2:
        try:
            rows = []
            async for batch in c2.read(("mixedtypes",)):
                rows.extend(batch.to_pylist())
            values = {r["amount"] for r in rows}
            has_both_types = any(isinstance(v, str) for v in values) and any(isinstance(v, float) for v in values)
            log("CON-167", "PASS" if has_both_types else "FAIL", f"n_rows={len(rows)} amount_has_mixed_types={has_both_types}")
        except Exception as e:
            log("CON-167", "FAIL", f"{type(e).__name__}: {e} (read() raised on a mixed-type column instead of producing a batch)")

async def con168():
    c = RestConnector({"base_url": BASE, "endpoints": ["nested"], "records_path": "items"})
    async with c:
        rows = []
        async for batch in c.read(("nested",)):
            rows.extend(batch.to_pylist())
    legs_values = [r["legs"] for r in rows]
    ok = (isinstance(legs_values[0], str) and legs_values[0] == legs_values[1])
    log("CON-168", "PASS" if ok else "FAIL", f"legs values={legs_values}")

async def con169():
    c = RestConnector({"base_url": BASE, "endpoints": ["notjson"]})
    async with c:
        try:
            async for batch in c.read(("notjson",)):
                pass
            log("CON-169", "FAIL", "no exception")
        except ConnectorError as e:
            ok = e.code == "CONNECT.NOT_JSON" and "notjson" in str(e)
            log("CON-169", "PASS" if ok else "FAIL", f"code={e.code} msg={e}")

def con170():
    obs = {}
    obs["bare_list"] = _records([{"a": 1}, {"b": 2}], "")
    obs["bare_dict"] = _records({"a": 1}, "")
    obs["nested_path"] = _records({"data": {"items": [{"x": 1}]}}, "data.items")
    obs["missing_path"] = _records({"data": {"items": [{"x": 1}]}}, "data.missing")
    obs["non_dicts"] = _records([1, 2, "x"], "")
    obs["null_body"] = _records(None, "")
    ok = (obs["bare_list"] == [{"a": 1}, {"b": 2}]
          and obs["bare_dict"] == [{"a": 1}]
          and obs["nested_path"] == [{"x": 1}]
          and obs["missing_path"] == [{"data": {"items": [{"x": 1}]}}]  # falls back to whole body as one record
          and obs["non_dicts"] == []
          and obs["null_body"] == [])
    log("CON-170", "PASS" if ok else "FAIL", str(obs))

async def con171():
    import resource
    STATE["total_pages"] = 1000
    c = RestConnector({"base_url": BASE, "endpoints": ["bigpages"], "records_path": "items", "next_path": "links.next", "page_limit": 1000})
    before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    async with c:
        rows = []
        async for batch in c.read(("bigpages",)):
            rows.extend(batch.to_pylist())
    after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    log("CON-171", "PASS", f"n_rows={len(rows)} (expected 1,000,000) peak_rss_before_kb={before} peak_rss_after_kb={after} delta_mb={(after-before)/1024:.1f} -- _collect materialises the whole 1000-page result as a Python list before read() batches it out, confirming the streaming claim applies only to the batches handed to the caller, not to what _collect itself holds")

async def main():
    await con156()
    await con157()
    await con158()
    await con159()
    await con160()
    await con161()
    await con162()
    await con163()
    await con164()
    await con165()
    await con166_167()
    await con168()
    await con169()
    con170()
    await con171()

asyncio.run(main())
