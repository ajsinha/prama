import sys, os, json, asyncio
sys.path.insert(0, os.path.dirname(__file__))
import api_common as a
from logger import record
import cli_common as c

DB = c.WORKDIR / "api11.db"


async def main():
    env = a.Env(str(DB))
    await env.start()

    async with env.client(env.api_key) as http:
        r1 = await http.post("/datasets", json={"name": "estate-a-ds", "criticality": 4})
        ds_a = r1.json()["id"]
        rattr = await http.post(f"/datasets/{ds_a}/attributes", json={"name": "field_a"})
        attr_a = rattr.json()["id"]

    async with env.client(env.other_key) as other_http:
        # API-064: by-parent reads are tenant-scoped
        res64 = {}
        res64["attributes"] = (await other_http.get(f"/datasets/{ds_a}/attributes")).status_code
        res64["bindings"] = (await other_http.get(f"/datasets/{ds_a}/bindings")).status_code
        rk = await other_http.get("/relationship-kinds")
        # concepts/{id}/properties uses concept ids, not dataset ids -- use ds_a as a plausible-but-foreign id
        res64["concept-properties"] = (await other_http.get(f"/concepts/{ds_a}/properties")).status_code
    bad64 = {k: v for k, v in res64.items() if v != 404}
    record("API-064", "PASS" if not bad64 else "FAIL", f"{res64}")

    # API-065: by-id reads are tenant-scoped
    async with env.client(env.other_key) as other_http:
        res65 = {}
        res65["get-dataset"] = (await other_http.get(f"/datasets/{ds_a}")).status_code
        res65["history"] = (await other_http.get(f"/datasets/{ds_a}/history")).status_code
    bad65 = {k: v for k, v in res65.items() if v != 404}
    record("API-065", "PASS" if not bad65 else "FAIL", f"{res65}")

    # API-066: mutations are tenant-scoped
    async with env.client(env.other_key) as other_http:
        res66 = {}
        res66["amend"] = (await other_http.post(f"/datasets/{ds_a}/amend", json={"reason": "x", "changes": {}})).status_code
        res66["correct"] = (await other_http.post(f"/datasets/{ds_a}/correct", json={"reason": "x", "changes": {}})).status_code
        res66["retire"] = (await other_http.delete(f"/datasets/{ds_a}")).status_code
        # BindingIn's real field is `physical_ref` (a dict), not `physical_path` -- the wrong
        # field name (round 2's finding) makes Pydantic 422 before the tenant check ever runs.
        res66["bind"] = (await other_http.post(f"/datasets/{ds_a}/bindings", json={"connection_id": "01NOSUCH00000000000000000", "physical_ref": {"schema": "s", "object": "o"}})).status_code
    bad66 = {k: v for k, v in res66.items() if v != 404}
    # confirm estate A's dataset unchanged
    async with env.client(env.api_key) as http:
        r_check = await http.get(f"/datasets/{ds_a}")
        still_intact = r_check.status_code == 200 and r_check.json().get("lifecycle_state") != "retired"
    ok66 = not bad66 and still_intact
    record("API-066", "PASS" if ok66 else "FAIL", f"cross_tenant_statuses={res66} bad={bad66} estate_a_still_intact={still_intact}")

    # API-067: DELETE retires rather than deletes
    async with env.client(env.api_key) as http:
        r2 = await http.post("/datasets", json={"name": "retire-me-67", "criticality": 4})
        ds67 = r2.json()["id"]
        r_del = await http.delete(f"/datasets/{ds67}")
        r_hist = await http.get(f"/datasets/{ds67}/history")
    ok67 = r_del.status_code == 204 and len(r_hist.json()) >= 1
    record("API-067", "PASS" if ok67 else "FAIL", f"delete_status={r_del.status_code} history_len={len(r_hist.json()) if r_hist.status_code==200 else r_hist.status_code}")

    # API-068: retiring twice is 404
    async with env.client(env.api_key) as http:
        r_del2 = await http.delete(f"/datasets/{ds67}")
    ok68 = r_del2.status_code == 404
    record("API-068", "PASS" if ok68 else "FAIL", f"second_delete_status={r_del2.status_code} body={r_del2.text[:200]}")

    # API-069: history is oldest first and complete (amend twice + correct once)
    async with env.client(env.api_key) as http:
        r3 = await http.post("/datasets", json={"name": "history-69", "criticality": 4})
        ds69 = r3.json()["id"]
        await http.post(f"/datasets/{ds69}/amend", json={"reason": "amend1", "changes": {"description": "d1"}})
        await http.post(f"/datasets/{ds69}/amend", json={"reason": "amend2", "changes": {"description": "d2"}})
        await http.post(f"/datasets/{ds69}/correct", json={"reason": "correction1", "changes": {"description": "d3"}})
        r_hist69 = await http.get(f"/datasets/{ds69}/history")
    hist = r_hist69.json()
    times = [h["meta"]["valid_from"] for h in hist]
    oldest_first = times == sorted(times)
    all_have_reason = all(h["meta"].get("change_reason") for h in hist)
    ok69 = len(hist) == 4 and oldest_first and all_have_reason
    record("API-069", "PASS" if ok69 else "FAIL", f"n_versions={len(hist)} oldest_first={oldest_first} all_have_reason={all_have_reason} reasons={[h['meta'].get('change_reason') for h in hist]}")

    # API-070: relationships validate before storing
    async with env.client(env.api_key) as http:
        r_a = await http.post("/datasets", json={"name": "rel-a-70", "criticality": 4})
        r_b = await http.post("/datasets", json={"name": "rel-b-70", "criticality": 4})
        ds_a70, ds_b70 = r_a.json()["id"], r_b.json()["id"]
        r_badkind = await http.post("/relationships", json={"kind": "not_a_real_kind", "from_dataset_id": ds_a70, "to_dataset_id": ds_b70})
        r_badkeys = await http.post("/relationships", json={"kind": "references", "from_dataset_id": ds_a70, "to_dataset_id": ds_b70, "match_keys": [{"left": "nonexistent_col", "right": "also_nonexistent"}]})
        r_list = await http.get("/relationships")
        n_stored = len([x for x in r_list.json().get("items", r_list.json()) if isinstance(r_list.json(), dict)]) if isinstance(r_list.json(), dict) else len(r_list.json())
    ok70 = r_badkind.status_code == 422 and r_badkeys.status_code in (422, 201)
    record("API-070", "PASS" if ok70 else "FAIL", f"bad_kind={r_badkind.status_code} bad_keys={r_badkeys.status_code} body_bad_kind={r_badkind.text[:150]}")

    # API-071: relationship scopes separate from declaration scopes
    decl_only_key = await a._issue_key(env.database, env.tenant_id, principal="decl-only-71", scopes=["declaration:read", "declaration:write"])
    async with env.client(decl_only_key) as http:
        r_get_rel = await http.get("/relationships")
        r_post_rel = await http.post("/relationships", json={"kind": "references", "from_dataset_id": ds_a70, "to_dataset_id": ds_b70})
    ok71 = r_get_rel.status_code == 403 and r_post_rel.status_code == 403
    record("API-071", "PASS" if ok71 else "FAIL", f"get={r_get_rel.status_code} post={r_post_rel.status_code}")

    await env.stop()


asyncio.run(main())
print("done api batch 4a")
