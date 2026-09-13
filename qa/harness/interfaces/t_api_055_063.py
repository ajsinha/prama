import sys, os, json, asyncio, datetime
sys.path.insert(0, os.path.dirname(__file__))
import api_common as a
from logger import record
import cli_common as c

DB = c.WORKDIR / "api10.db"


async def main():
    env = a.Env(str(DB))
    await env.start()

    # setup: a dataset amended twice
    async with env.client(env.api_key) as http:
        r = await http.post("/datasets", json={"name": "bitemporal-ds-55", "criticality": 4})
        ds_id = r.json()["id"]
        t0 = r.json()["meta"]["valid_from"]
        await asyncio.sleep(1.2)
        r2 = await http.post(f"/datasets/{ds_id}/amend", json={"reason": "first amend", "changes": {"description": "v2"}})
        t1 = r2.json()["meta"]["valid_from"]
        await asyncio.sleep(1.2)
        r3 = await http.post(f"/datasets/{ds_id}/amend", json={"reason": "second amend", "changes": {"description": "v3"}})
        t2 = r3.json()["meta"]["valid_from"]

        # API-055: valid_at alone returns the version valid then
        mid_instant = t1  # exactly at the second version's valid_from; ask for a point between v1 and v2 instead
        # pick an instant strictly between t0 and t1
        from datetime import timezone
        t0dt = datetime.datetime.fromisoformat(t0.replace("Z", "+00:00"))
        t1dt = datetime.datetime.fromisoformat(t1.replace("Z", "+00:00"))
        between = (t0dt + (t1dt - t0dt) / 2).isoformat()
        r_at = await http.get(f"/datasets/{ds_id}", params={"valid_at": between})
        ok55 = r_at.status_code == 200 and r_at.json().get("description") == ""  # v1 had no description
        record("API-055", "PASS" if ok55 else "FAIL", f"status={r_at.status_code} body_desc={r_at.json().get('description') if r_at.status_code==200 else r_at.text[:200]}")

        # API-056: known_at alone is refused, not silently discarded
        r_known = await http.get(f"/datasets/{ds_id}", params={"known_at": "2000-01-01T00:00:00Z"})
        ok56 = r_known.status_code == 422
        record(
            "API-056",
            "PASS" if ok56 else "FAIL",
            f"status={r_known.status_code} body={r_known.text[:300]} -- "
            f"api/routes/semantic.py::get_dataset: `if valid_at and known_at: ... elif valid_at: ... else: "
            f"current` -- known_at alone falls into the `else` branch and silently returns the CURRENT "
            f"version rather than refusing, exactly matching finding Q-25's predicted shape",
        )

        # API-057: naive valid_at does not 500
        try:
            r_naive = await http.get(f"/datasets/{ds_id}", params={"valid_at": "2026-01-01T00:00:00"})
            ok57 = r_naive.status_code == 422
            detail57 = f"status={r_naive.status_code} body={r_naive.text[:250]}"
        except Exception as e:
            ok57 = False
            detail57 = f"client exception: {type(e).__name__} {str(e)[:250]}"
        record("API-057", "PASS" if ok57 else "FAIL", detail57)

        # API-058: unparsable valid_at
        res58 = {}
        for label, val in [("yesterday", "yesterday"), ("empty", ""), ("garbage-date", "0000-00-00")]:
            try:
                r = await http.get(f"/datasets/{ds_id}", params={"valid_at": val})
                res58[label] = (r.status_code, "problem+json" in r.headers.get("content-type", ""))
            except Exception as e:
                res58[label] = ("EXCEPTION", str(e)[:100])
        bad58 = {k: v for k, v in res58.items() if v[0] != 422 or v[1] is False}
        record("API-058", "PASS" if not bad58 else "FAIL", f"{res58}")

        # API-059: valid_at before the dataset existed
        r_past = await http.get(f"/datasets/{ds_id}", params={"valid_at": "2000-01-01T00:00:00Z"})
        ok59 = r_past.status_code == 404 and "widen" in r_past.text.lower()
        record("API-059", "PASS" if ok59 else "FAIL", f"status={r_past.status_code} body={r_past.text[:250]}")

    # API-060: pagination edges
    async with env.client(env.api_key) as http:
        res60 = {}
        res60["limit=0"] = (await http.get("/datasets", params={"limit": 0})).status_code
        res60["limit=1"] = (await http.get("/datasets", params={"limit": 1})).status_code
        res60["limit=500"] = (await http.get("/datasets", params={"limit": 500})).status_code
        res60["limit=501"] = (await http.get("/datasets", params={"limit": 501})).status_code
        res60["offset=-1"] = (await http.get("/datasets", params={"offset": -1})).status_code
        r_past_offset = await http.get("/datasets", params={"offset": 100000})
        res60["offset-past-end"] = (r_past_offset.status_code, len(r_past_offset.json().get("items", [])), r_past_offset.json().get("page", {}).get("total"))
    ok60 = res60["limit=0"] == 422 and res60["limit=501"] == 422 and res60["offset=-1"] == 422 and res60["limit=1"] == 200 and res60["offset-past-end"][1] == 0
    record("API-060", "PASS" if ok60 else "FAIL", f"{res60}")

    # setup for filter tests: create 10 unbound datasets among others
    async with env.client(env.api_key) as http:
        for i in range(10):
            await http.post("/datasets", json={"name": f"unbound-ds-{i}", "criticality": 4})
        r_all = await http.get("/datasets", params={"limit": 500})
        total_all = r_all.json()["page"]["total"]
        r_unbound = await http.get("/datasets", params={"unbound": "true"})
        total_unbound = r_unbound.json()["page"]["total"]
        n_items_unbound = len(r_unbound.json()["items"])

    # API-061: page.total respects the filter
    ok61 = total_unbound < total_all and total_unbound == n_items_unbound
    record(
        "API-061",
        "PASS" if ok61 else "FAIL",
        f"total_all={total_all} total_unbound_reported={total_unbound} n_items_actually_returned={n_items_unbound} -- "
        f"api/routes/semantic.py::list_datasets always calls uow.datasets.count_current(tenant_id) for "
        f"`total`, regardless of the unbound/criticality filter actually applied",
    )

    # API-062: unbound and criticality together
    async with env.client(env.api_key) as http:
        r_both = await http.get("/datasets", params={"unbound": "true", "criticality": 1})
        items_both = r_both.json().get("items", [])
        criticalities_seen = {it.get("criticality") for it in items_both}
    ok62 = criticalities_seen <= {1} or r_both.status_code in (400, 422)
    record(
        "API-062",
        "PASS" if ok62 else "FAIL",
        f"status={r_both.status_code} criticalities_in_result={criticalities_seen} n_items={len(items_both)} -- "
        f"the if/elif chain in list_datasets applies `unbound` first and never consults `criticality` at "
        f"all when both are given, returning a superset the caller did not ask for",
    )

    # API-063: a filtered listing ignores limit/offset entirely
    async with env.client(env.api_key) as http:
        r_limited = await http.get("/datasets", params={"unbound": "true", "limit": 3})
    n_returned = len(r_limited.json().get("items", []))
    claimed_limit = r_limited.json().get("page", {}).get("limit")
    ok63 = n_returned <= 3
    record(
        "API-063",
        "PASS" if ok63 else "FAIL",
        f"requested_limit=3 items_actually_returned={n_returned} page_block_claims_limit={claimed_limit} -- "
        f"uow.datasets.unbound(tenant_id) takes no limit/offset at all, so the unbound branch returns "
        f"every matching row regardless of ?limit=",
    )

    await env.stop()


asyncio.run(main())
print("done api batch 3b")
